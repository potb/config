import gzip
import html
import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Paris")
BASE = os.environ.get("TRANSIT_PRIM_URL", "https://prim.iledefrance-mobilites.fr/marketplace")
UA = os.environ.get("TRANSIT_USER_AGENT", "potb-transit/1.0 (+https://github.com/potb/config)")
NAVITIA = "v2/navitia"
NAVITIA_TIME = "%Y%m%dT%H%M%S"
ISO_UTC = "%Y-%m-%dT%H:%M:%SZ"
DAY_S = 86400
LIVE_WINDOW_S = 3600
LIVE_MATCH_S = 15 * 60
BOARDING_SLACK = timedelta(hours=1)
MAX_ALERTS = 6
SOUTH_WEST_NORTH_EAST = (48.10, 1.40, 49.30, 3.60)

PHYSICAL_MODES = {
    "Metro": "SUBWAY",
    "Bus": "BUS",
    "BusRapidTransit": "BUS",
    "Shuttle": "BUS",
    "Tramway": "TRAM",
    "RapidTransit": "RAIL",
    "LocalTrain": "RAIL",
    "Train": "RAIL",
    "LongDistanceTrain": "RAIL",
    "Funicular": "FUNICULAR",
    "Coach": "COACH",
    "Ferry": "FERRY",
    "Boat": "FERRY",
    "Air": "AIRPLANE",
}
STREET_MODES = {"walking": "WALK", "bike": "BIKE", "bss": "BIKE", "car": "CAR"}
PLACE_TYPES = {"stop_area": "STOP", "address": "ADDRESS", "poi": "PLACE"}


class NoResult(Exception):
    pass


class UnknownObject(NoResult):
    pass


def api_key():
    key = os.environ.get("PRIM_API_KEY")
    if key:
        return key.strip()
    path = os.environ.get("PRIM_API_KEY_FILE")
    if path:
        try:
            return Path(path).read_text().strip() or None
        except OSError:
            return None
    return None


def configured():
    return api_key() is not None


def in_idf(lat, lon):
    south, west, north, east = SOUTH_WEST_NORTH_EAST
    return south <= lat <= north and west <= lon <= east


def is_trip_id(text):
    return text.startswith("vehicle_journey:")


def is_stop_id(text):
    return re.match(r"stop_(area|point):", text) is not None


def idfm_number(motis_id):
    match = re.search(r"_IDFM:(\d+)$", motis_id)
    return match.group(1) if match else None


def covers_stop(stop_id):
    return is_stop_id(stop_id) or idfm_number(stop_id) is not None


def unzip(raw, headers):
    return gzip.decompress(raw) if headers.get("Content-Encoding") == "gzip" else raw


def failure(error):
    if error.code in (401, 403):
        return NoResult("PRIM : clé API refusée")
    if error.code == 429:
        return NoResult("PRIM : quota de requêtes dépassé")
    try:
        detail = json.loads(unzip(error.read(), error.headers))["error"]
    except (OSError, ValueError, KeyError, TypeError):
        return error
    kind = UnknownObject if detail.get("id") == "unknown_object" else NoResult
    return kind(f"PRIM : {detail.get('message') or detail.get('id')}")


def get(path, **params):
    key = api_key()
    if not key:
        raise NoResult("PRIM non configuré : pas de clé API")
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    request = urllib.request.Request(
        f"{BASE}/{path}?{query}",
        headers={"apikey": key, "User-Agent": UA, "Accept-Encoding": "gzip"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(unzip(response.read(), response.headers))
    except urllib.error.HTTPError as e:
        raise failure(e) from e


def navitia_time(text):
    return datetime.strptime(text, NAVITIA_TIME)


def iso(local):
    if not local:
        return None
    local = navitia_time(local) if isinstance(local, str) else local
    return local.replace(tzinfo=TZ).astimezone(timezone.utc).strftime(ISO_UTC)


def to_navitia(iso_text):
    when = datetime.fromisoformat(iso_text.replace("Z", "+00:00"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=TZ)
    return when.astimezone(TZ).strftime(NAVITIA_TIME)


def seconds_of_day(text):
    return int(text[:2]) * 3600 + int(text[2:4]) * 60 + int(text[4:6])


def mode_of(physical_mode_id):
    return PHYSICAL_MODES.get((physical_mode_id or "").split(":")[-1], "TRANSIT")


def link_ids(links, kind):
    return [link["id"] for link in links or [] if link.get("type") == kind and link.get("id")]


def physical_mode_of(route):
    return ((route or {}).get("physical_modes") or [{}])[0].get("id")


def trip_id_of(vehicle_journey, stop_point, base_departure):
    return f"{vehicle_journey}@{stop_point}@{base_departure}"


def split_trip_id(trip_id):
    parts = trip_id.split("@")
    if len(parts) != 3:
        raise NoResult("identifiant de course PRIM sans date : reprends le trip_id de transit plan ou departures")
    return parts


def plain(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def period_covers(disruption, when, slack=timedelta(0)):
    return any(
        navitia_time(period["begin"]) - slack <= when <= navitia_time(period["end"]) + slack
        for period in disruption.get("application_periods", [])
    )


def alert_of(disruption, when):
    if disruption.get("status") == "past" or "Ascenseur" in disruption.get("tags", []):
        return None
    if not period_covers(disruption, when):
        return None
    by_channel = {}
    for message in disruption.get("messages", []):
        for kind in message.get("channel", {}).get("types", []):
            by_channel.setdefault(kind, plain(message.get("text")))
    title = by_channel.get("title") or by_channel.get("notification")
    body = by_channel.get("web") or by_channel.get("mobile") or title
    if not (title or body):
        return None
    return {"headerText": title or body, "descriptionText": body}


def add_alert(alerts, alert):
    if alert and len(alerts) < MAX_ALERTS and all(alert["headerText"] != seen["headerText"] for seen in alerts):
        alerts.append(alert)


def coord_of(obj):
    return float(obj["coord"]["lat"]), float(obj["coord"]["lon"])


def words(text):
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", folded)


def names_all_words(name, wanted):
    present = words(name)
    return all(any(have.startswith(word) for have in present) for word in wanted)


def geocode(text, stop_only):
    params = {"q": text, "count": 5}
    if stop_only:
        params["type[]"] = "stop_area"
    wanted = words(text)
    hits = []
    for place in get(f"{NAVITIA}/places", **params).get("places", []):
        kind = place["embedded_type"]
        if kind in PLACE_TYPES and names_all_words(place.get("name", ""), wanted):
            lat, lon = coord_of(place[kind])
            hits.append({"id": place["id"], "name": place.get("name"), "lat": lat, "lon": lon, "type": PLACE_TYPES[kind]})
    return hits


def stop_view(row):
    stop = row["stop_point"]
    lat, lon = coord_of(stop)
    return {
        "name": stop["name"],
        "stopId": stop["id"],
        "parentId": (stop.get("stop_area") or {}).get("id"),
        "lat": lat,
        "lon": lon,
        "scheduledDeparture": iso(row.get("base_departure_date_time")),
        "departure": iso(row.get("departure_date_time")),
        "scheduledArrival": iso(row.get("base_arrival_date_time")),
        "arrival": iso(row.get("arrival_date_time")),
    }


def walking_leg(section):
    return {
        "mode": STREET_MODES.get(section.get("mode", "walking"), "WALK"),
        "duration": section["duration"],
        "from": {"name": (section.get("from") or {}).get("name")},
        "to": {"name": (section.get("to") or {}).get("name")},
    }


def apply_live(leg, visit):
    leg["from"]["departure"] = visit["at"].strftime(ISO_UTC)
    leg["realTime"] = True
    leg["cancelled"] = visit["status"] == "cancelled"


def transit_leg(section, disruptions, live):
    info = section["display_informations"]
    rows = section["stop_date_times"]
    boarding = navitia_time(section["departure_date_time"])
    alerts = []
    for ident in link_ids(section.get("links"), "disruption") + link_ids(info.get("links"), "disruption"):
        add_alert(alerts, alert_of(disruptions.get(ident, {}), boarding))
    vehicle_journey = link_ids(section["links"], "vehicle_journey")[0]
    line = (link_ids(section["links"], "line") or [None])[0]
    leg = {
        "mode": mode_of((link_ids(section["links"], "physical_mode") or [""])[0]),
        "duration": section["duration"],
        "from": stop_view(rows[0]),
        "to": stop_view(rows[-1]),
        "intermediateStops": [stop_view(row) for row in rows[1:-1]],
        "routeShortName": info.get("code") or info.get("label"),
        "displayName": info.get("name"),
        "headsign": info.get("headsign") or info.get("direction"),
        "agencyName": info.get("company") or info.get("network"),
        "realTime": section.get("data_freshness") == "realtime",
        "cancelled": False,
        "alerts": alerts,
        "tripId": trip_id_of(vehicle_journey, rows[0]["stop_point"]["id"], rows[0]["base_departure_date_time"]),
    }
    visit = live(line, rows[0]["stop_point"]["id"], boarding) if live and not leg["realTime"] else None
    if visit:
        apply_live(leg, visit)
    return leg


def journey_legs(journey, disruptions):
    legs, first_transit = [], True
    for section in journey["sections"]:
        if section["type"] in ("street_network", "crow_fly", "transfer"):
            legs.append(walking_leg(section))
        elif section["type"] == "public_transport":
            legs.append(transit_leg(section, disruptions, live_visit if first_transit else None))
            first_transit = False
    return legs


def plan(origin, destination, at, arrive_by, count):
    data = get(
        f"{NAVITIA}/journeys",
        **{
            "from": f"{origin[1]};{origin[0]}",
            "to": f"{destination[1]};{destination[0]}",
            "count": count,
            "data_freshness": "realtime",
            "datetime": to_navitia(at) if at else None,
            "datetime_represents": "arrival" if arrive_by else None,
        },
    )
    if data.get("error"):
        raise NoResult(f"PRIM : {data['error'].get('message') or data['error'].get('id')}")
    disruptions = {d["id"]: d for d in data.get("disruptions", [])}
    return {
        "itineraries": [
            {
                "startTime": iso(journey["departure_date_time"]),
                "endTime": iso(journey["arrival_date_time"]),
                "duration": journey["duration"],
                "transfers": journey["nb_transfers"],
                "legs": journey_legs(journey, disruptions),
            }
            for journey in data.get("journeys", [])
        ]
    }


class ServiceDay:
    def __init__(self, stop_times, boarding_stop, boarding_departure):
        self.rows = []
        previous = 0
        for stop_time in stop_times:
            arrival = seconds_of_day(stop_time["arrival_time"])
            while arrival < previous:
                arrival += DAY_S
            departure = seconds_of_day(stop_time["departure_time"])
            while departure < arrival:
                departure += DAY_S
            previous = departure
            self.rows.append((stop_time, arrival, departure))
        self.boarding = navitia_time(boarding_departure)
        time_of_day = self.boarding.hour * 3600 + self.boarding.minute * 60 + self.boarding.second
        visits = [row for row in self.rows if row[0]["stop_point"]["id"] == boarding_stop]
        if not visits:
            raise NoResult("arrêt de montée absent de la course : horaires modifiés ?")
        match = next((row for row in visits if row[2] % DAY_S == time_of_day), visits[0])
        self.midnight = self.boarding - timedelta(seconds=match[2])

    def at(self, seconds):
        return self.midnight + timedelta(seconds=seconds)

    def amended(self, time_of_day, scheduled):
        base = seconds_of_day(time_of_day)
        candidates = (self.midnight + timedelta(seconds=base + shift) for shift in (-DAY_S, 0, DAY_S))
        return min(candidates, key=lambda candidate: abs(candidate - scheduled))


def trip_update(disruptions, bare_id, boarding):
    newest = None
    for disruption in disruptions:
        if disruption.get("status") == "past" or not period_covers(disruption, boarding, BOARDING_SLACK):
            continue
        for impacted in disruption.get("impacted_objects", []):
            pt = impacted["pt_object"]
            if pt.get("embedded_type") == "trip" and pt["id"] == bare_id:
                if newest is None or disruption.get("updated_at", "") > newest[0].get("updated_at", ""):
                    newest = (disruption, impacted)
    return newest


def alerts_along(data, route, stop_ids, boarding):
    wanted = {(route.get("line") or {}).get("id"), route.get("id")} | stop_ids
    alerts = []
    for disruption in data.get("disruptions", []):
        for impacted in disruption.get("impacted_objects", []):
            pt = impacted["pt_object"]
            if pt.get("embedded_type") in ("line", "route", "stop_point", "stop_area") and pt["id"] in wanted:
                add_alert(alerts, alert_of(disruption, boarding))
                break
    return alerts


def trip(trip_id):
    vehicle_journey, boarding_stop, boarding_departure = split_trip_id(trip_id)
    try:
        data = get(f"{NAVITIA}/vehicle_journeys/{vehicle_journey}", data_freshness="realtime", depth=2)
    except UnknownObject as e:
        raise NoResult("course introuvable") from e
    if not data.get("vehicle_journeys"):
        raise NoResult("course introuvable")
    journey = data["vehicle_journeys"][0]
    day = ServiceDay(journey["stop_times"], boarding_stop, boarding_departure)
    update = trip_update(data.get("disruptions", []), vehicle_journey.removeprefix("vehicle_journey:"), day.boarding)
    cancelled, amendments = False, {}
    if update:
        disruption, impacted = update
        cancelled = disruption.get("severity", {}).get("effect") == "NO_SERVICE"
        amendments = {s["stop_point"]["id"]: s for s in impacted.get("impacted_stops", [])}
    stops = []
    for stop_time, arrival, departure in day.rows:
        stop = stop_time["stop_point"]
        amendment = amendments.get(stop["id"], {})
        scheduled_arrival, scheduled_departure = day.at(arrival), day.at(departure)
        real_arrival, real_departure = scheduled_arrival, scheduled_departure
        if amendment.get("amended_arrival_time"):
            real_arrival = day.amended(amendment["amended_arrival_time"], scheduled_arrival)
        if amendment.get("amended_departure_time"):
            real_departure = day.amended(amendment["amended_departure_time"], scheduled_departure)
        lat, lon = coord_of(stop)
        stops.append(
            {
                "name": stop["name"],
                "stopId": stop["id"],
                "parentId": (stop.get("stop_area") or {}).get("id"),
                "lat": lat,
                "lon": lon,
                "scheduledArrival": iso(scheduled_arrival),
                "arrival": iso(real_arrival),
                "scheduledDeparture": iso(scheduled_departure),
                "departure": iso(real_departure),
                "cancelled": amendment.get("stop_time_effect") == "deleted" or stop_time.get("skipped_stop", False),
            }
        )
    route = journey.get("journey_pattern", {}).get("route", {})
    line = route.get("line", {})
    stop_ids = {s["stopId"] for s in stops} | {s["parentId"] for s in stops if s["parentId"]}
    return {
        "legs": [
            {
                "mode": mode_of(physical_mode_of(route)),
                "routeShortName": line.get("code"),
                "displayName": line.get("name"),
                "headsign": journey.get("headsign"),
                "realTime": update is not None,
                "cancelled": cancelled,
                "alerts": alerts_along(data, route, stop_ids, day.boarding),
                "from": stops[0],
                "to": stops[-1],
                "intermediateStops": stops[1:-1],
            }
        ]
    }


def stop_refs(stop_id):
    if is_stop_id(stop_id):
        return [stop_id]
    number = idfm_number(stop_id)
    if number is None:
        raise NoResult("arrêt hors Île-de-France : PRIM ne le connaît pas")
    return [f"stop_area:IDFM:{number}", f"stop_point:IDFM:{number}"]


def monitoring_ref(stop_ref):
    match = re.match(r"stop_(area|point):IDFM:(\d+)$", stop_ref)
    if not match:
        return None
    kind = "StopArea:SP" if match.group(1) == "area" else "StopPoint:Q"
    return f"STIF:{kind}:{match.group(2)}:"


@lru_cache(maxsize=16)
def passages(monitoring):
    try:
        data = get("stop-monitoring", MonitoringRef=monitoring)
        deliveries = data["Siri"]["ServiceDelivery"]["StopMonitoringDelivery"]
    except (NoResult, OSError, ValueError, KeyError):
        return {}
    grouped = defaultdict(list)
    for delivery in deliveries:
        for visit in delivery.get("MonitoredStopVisit", []):
            journey = visit["MonitoredVehicleJourney"]
            call = journey.get("MonitoredCall", {})
            line = re.match(r"STIF:Line::(\w+):", journey.get("LineRef", {}).get("value", ""))
            stop = re.search(r"StopPoint:Q:(\d+):", visit.get("MonitoringRef", {}).get("value", ""))
            expected = call.get("ExpectedDepartureTime") or call.get("ExpectedArrivalTime")
            if line and stop and expected:
                grouped[(f"line:IDFM:{line.group(1)}", f"stop_point:IDFM:{stop.group(1)}")].append(
                    {
                        "at": datetime.fromisoformat(expected.replace("Z", "+00:00")),
                        "status": call.get("DepartureStatus", ""),
                    }
                )
    return grouped


def closest_visit(pool, scheduled, taken=()):
    free = [v for v in pool if id(v) not in taken]
    if not free:
        return None
    visit = min(free, key=lambda v: abs((v["at"] - scheduled).total_seconds()))
    return visit if abs((visit["at"] - scheduled).total_seconds()) <= LIVE_MATCH_S else None


def departs_soon(local_naive):
    return (local_naive.replace(tzinfo=TZ) - datetime.now(TZ)).total_seconds() < LIVE_WINDOW_S


def live_visit(line, stop_point, boarding):
    ref = monitoring_ref(stop_point)
    if not ref or not departs_soon(boarding):
        return None
    visit = closest_visit(passages(ref).get((line, stop_point), []), boarding.replace(tzinfo=TZ))
    return visit if visit and visit["status"] != "noReport" else None


def departure_row(departure):
    times = departure["stop_date_time"]
    stop = departure["stop_point"]
    line = departure["route"].get("line", {})
    info = departure["display_informations"]
    vehicle_journey = link_ids(departure.get("links"), "vehicle_journey")[0]
    return {
        "place": {
            "name": stop["name"],
            "scheduledDeparture": iso(times["base_departure_date_time"]),
            "departure": iso(times["departure_date_time"]),
        },
        "routeShortName": info.get("code") or line.get("code"),
        "displayName": info.get("name"),
        "headsign": info.get("headsign") or info.get("direction"),
        "mode": mode_of(physical_mode_of(departure["route"])),
        "realTime": times.get("data_freshness") == "realtime",
        "cancelled": False,
        "tripId": trip_id_of(vehicle_journey, stop["id"], times["base_departure_date_time"]),
    }


def overlay_passages(departures, rows, stop_ref):
    monitoring = monitoring_ref(stop_ref)
    if not monitoring:
        return
    pool = passages(monitoring)
    taken = set()
    for departure, row in sorted(zip(departures, rows), key=lambda pair: pair[0]["stop_date_time"]["base_departure_date_time"]):
        if row["realTime"]:
            continue
        stop_point = departure["stop_point"]["id"]
        line = departure["route"].get("line", {}).get("id")
        scheduled = navitia_time(departure["stop_date_time"]["base_departure_date_time"]).replace(tzinfo=TZ)
        visit = closest_visit(pool.get((line, stop_point), []), scheduled, taken)
        if visit and visit["status"] != "noReport":
            taken.add(id(visit))
            row["place"]["departure"] = visit["at"].strftime(ISO_UTC)
            row["realTime"] = True
            row["cancelled"] = visit["status"] == "cancelled"


def stoptimes(stop_id, count, at):
    last_error = NoResult("arrêt introuvable")
    for ref in stop_refs(stop_id):
        try:
            data = get(
                f"{NAVITIA}/{ref.split(':', 1)[0]}s/{ref}/departures",
                count=count,
                data_freshness="realtime",
                from_datetime=to_navitia(at) if at else None,
            )
        except UnknownObject as e:
            last_error = e
            continue
        departures = [d for d in data.get("departures", []) if link_ids(d.get("links"), "vehicle_journey")]
        rows = [departure_row(d) for d in departures]
        first = navitia_time(to_navitia(at)) if at else datetime.now(TZ).replace(tzinfo=None)
        if departs_soon(first):
            overlay_passages(departures, rows, ref)
        return {"stopTimes": rows}
    raise last_error


def call(path, params):
    if path == "v1/geocode":
        return geocode(params["text"], params.get("type") == "STOP")
    if path == "v6/plan":
        origin = tuple(float(x) for x in params["fromPlace"].split(","))
        destination = tuple(float(x) for x in params["toPlace"].split(","))
        if not (in_idf(*origin) and in_idf(*destination)):
            raise NoResult("hors Île-de-France : PRIM ne couvre pas ce trajet")
        return plan(origin, destination, params.get("time"), params.get("arriveBy") == "true", params.get("numItineraries") or 3)
    if path == "v6/trip":
        return trip(params["tripId"])
    if path == "v6/stoptimes":
        return stoptimes(params["stopId"], params.get("n") or 10, params.get("time"))
    raise NoResult(f"PRIM : appel {path} non pris en charge")
