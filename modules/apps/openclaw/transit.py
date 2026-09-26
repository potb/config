#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Paris")
SOURCES = {
    "local": os.environ.get("TRANSIT_LOCAL_URL", "http://127.0.0.1:8090"),
    "transitous": os.environ.get("TRANSIT_FALLBACK_URL", "https://api.transitous.org"),
}
UA = os.environ.get("TRANSIT_USER_AGENT", "potb-transit/1.0 (+https://github.com/potb/config)")
MOTIS_STATE = Path(os.environ.get("TRANSIT_MOTIS_STATE", "/var/lib/motis"))
NETWORK_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError, ValueError, KeyError)


class NoResult(Exception):
    pass


def call(source, path, **params):
    params = {k: v for k, v in params.items() if v is not None}
    url = f"{SOURCES[source]}/api/{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def loaded_regions():
    try:
        return json.loads((MOTIS_STATE / "current" / "manifest.json").read_text())["regions"]
    except (OSError, ValueError, KeyError):
        return []


def region_catalog():
    try:
        return json.loads((MOTIS_STATE / "catalog" / "regions.json").read_text())
    except (OSError, ValueError):
        return []


def point_in_ring(lon, lat, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def region_of(lat, lon):
    for region in region_catalog():
        for polygon in region["polygons"]:
            if point_in_ring(lon, lat, polygon[0]) and not any(point_in_ring(lon, lat, hole) for hole in polygon[1:]):
                return region["id"]
    return None


def request_region(region_id):
    path = MOTIS_STATE / "requests" / region_id
    try:
        path.parent.mkdir(exist_ok=True)
        path.touch()
        return True
    except PermissionError:
        try:
            path.unlink(missing_ok=True)
            path.touch()
            return True
        except OSError:
            return False
    except OSError:
        return False


def note_regions(points):
    loaded = set(loaded_regions())
    regions = {region_of(lat, lon) for lat, lon in points}
    regions.discard(None)
    requested, local_covers = [], bool(regions) and regions <= loaded
    for region in sorted(regions):
        if request_region(region) and region not in loaded:
            requested.append(region)
    return local_covers, requested


def with_fallback(fn, sources=("local", "transitous")):
    errors = {}
    for source in sources:
        try:
            result = fn(source)
            if result:
                return source, result, errors
            errors[source] = "aucun résultat"
        except NoResult as e:
            errors[source] = str(e) or "aucun résultat"
        except urllib.error.HTTPError as e:
            errors[source] = f"HTTP {e.code}"
        except NETWORK_ERRORS as e:
            errors[source] = str(e)[:200]
    return None, None, errors


def parse_time(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def hhmm(iso):
    return parse_time(iso).astimezone(TZ).strftime("%H:%M") if iso else None


def delay_min(real, scheduled):
    if not real or not scheduled:
        return None
    return round((parse_time(real) - parse_time(scheduled)).total_seconds() / 60)


def alerts_of(obj):
    out = []
    for alert in obj.get("alerts", []) or []:
        text = alert.get("headerText") or alert.get("descriptionText")
        if text and text not in out:
            out.append(text)
    return out


def as_coord(text):
    parts = text.split(",")
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def geocode(source, text, stop_only=False):
    hits = call(source, "v1/geocode", text=text, type="STOP" if stop_only else None)
    if not hits:
        raise NoResult(f"lieu introuvable : {text}")
    return hits


def resolve_place(text):
    coord = as_coord(text)
    if coord:
        return {"coord": coord, "name": text, "stop": None}
    errors = []
    for source in ("transitous", "local"):
        try:
            hit = geocode(source, text)[0]
            return {
                "coord": (hit["lat"], hit["lon"]),
                "name": hit.get("name", text),
                "stop": hit["id"] if hit.get("type") == "STOP" else None,
            }
        except (NoResult, *NETWORK_ERRORS) as e:
            errors.append(f"{source}: {e}")
    raise NoResult("; ".join(errors))


def place_param(place):
    return f"{place['coord'][0]},{place['coord'][1]}"


def leg_view(leg):
    frm, to = leg["from"], leg["to"]
    view = {
        "mode": leg["mode"],
        "ligne": leg.get("routeShortName") or leg.get("displayName") or leg.get("tripShortName"),
        "direction": leg.get("headsign"),
        "exploitant": leg.get("agencyName"),
        "de": frm.get("name"),
        "vers": to.get("name"),
        "depart_prevu": hhmm(frm.get("scheduledDeparture")),
        "depart": hhmm(frm.get("departure")),
        "arrivee_prevue": hhmm(to.get("scheduledArrival")),
        "arrivee": hhmm(to.get("arrival")),
        "retard_min": delay_min(frm.get("departure"), frm.get("scheduledDeparture")),
        "realtime": bool(leg.get("realTime")),
        "annule": bool(leg.get("cancelled")),
        "voie": frm.get("track"),
        "alertes": alerts_of(leg),
        "trip_id": leg.get("tripId"),
        "arret_id": frm.get("stopId"),
    }
    return {k: v for k, v in view.items() if k == "realtime" or not (v is None or v is False or v == [])}


def walk_minutes(legs):
    return round(sum(leg["duration"] for leg in legs if leg["mode"] == "WALK") / 60)


def cmd_plan(a):
    frm, to = resolve_place(a.frm), resolve_place(a.to)
    local_covers, requested = note_regions([frm["coord"], to["coord"]])

    def run(source):
        d = call(source, "v6/plan", fromPlace=place_param(frm), toPlace=place_param(to), time=a.at,
                 arriveBy=str(a.arrive).lower() if a.arrive else None, numItineraries=a.n)
        its = [it for it in d.get("itineraries", []) if any(leg["mode"] != "WALK" for leg in it["legs"])]
        if not its:
            raise NoResult()
        return [{
            "depart": hhmm(it["startTime"]),
            "arrivee": hhmm(it["endTime"]),
            "duree_min": round(it["duration"] / 60),
            "marche_min": walk_minutes(it["legs"]),
            "correspondances": it["transfers"],
            "etapes": [leg_view(leg) for leg in it["legs"] if leg["mode"] != "WALK"],
        } for it in its[: a.n]]

    order = ("local", "transitous") if local_covers or not requested else ("transitous", "local")
    source, res, errors = with_fallback(run, order)
    return {
        "source": source, "de": frm["name"], "vers": to["name"], "itineraires": res,
        "regions_demandees": requested or None, "erreurs": errors or None,
    }


def cmd_trip(a):
    def run(source):
        d = call(source, "v6/trip", tripId=a.trip_id)
        leg = next((leg for leg in d.get("legs", []) if leg["mode"] != "WALK"), None)
        if not leg:
            raise NoResult("course introuvable")
        stops = [leg["from"], *leg.get("intermediateStops", []), leg["to"]]
        return {
            "ligne": leg.get("routeShortName") or leg.get("displayName"),
            "direction": leg.get("headsign"),
            "realtime": bool(leg.get("realTime")),
            "annule": bool(leg.get("cancelled")),
            "alertes": alerts_of(leg),
            "arrets": [{
                "nom": s.get("name"),
                "arret_id": s.get("stopId"),
                "prevu": hhmm(s.get("scheduledDeparture") or s.get("scheduledArrival")),
                "estime": hhmm(s.get("departure") or s.get("arrival")),
                "retard_min": delay_min(s.get("departure") or s.get("arrival"),
                                        s.get("scheduledDeparture") or s.get("scheduledArrival")),
                **({"annule": True} if s.get("cancelled") else {}),
                **({"voie": s["track"]} if s.get("track") else {}),
            } for s in stops],
        }

    source, res, errors = with_fallback(run)
    return {"source": source, **(res or {}), "erreurs": errors or None}


def stop_ids(source, text):
    if ":" in text or "_" in text:
        return [text]
    hits = [h for h in geocode(source, text, stop_only=True) if h.get("type") == "STOP"]
    if not hits:
        raise NoResult(f"pas d'arrêt nommé {text!r}")
    return [hits[0]["id"]]


def cmd_departures(a):
    def run(source):
        stop_id = stop_ids(source, a.stop)[0]
        d = call(source, "v6/stoptimes", stopId=stop_id, n=a.n, time=a.at, withAlerts="true")
        if not d.get("stopTimes"):
            raise NoResult()
        return [{
            "arret": st["place"].get("name"),
            "ligne": st.get("routeShortName") or st.get("displayName"),
            "direction": st.get("headsign"),
            "mode": st.get("mode"),
            "prevu": hhmm(st["place"].get("scheduledDeparture")),
            "estime": hhmm(st["place"].get("departure")),
            "retard_min": delay_min(st["place"].get("departure"), st["place"].get("scheduledDeparture")),
            "voie": st["place"].get("track"),
            "realtime": bool(st.get("realTime")),
            "annule": bool(st.get("cancelled") or st.get("tripCancelled")),
            "trip_id": st["tripId"],
        } for st in d["stopTimes"]]

    source, res, errors = with_fallback(run)
    return {"source": source, "departs": res, "erreurs": errors or None}


def cmd_geocode(a):
    def run(source):
        return [{
            "nom": h.get("name"),
            "type": h.get("type"),
            "id": h.get("id"),
            "coord": f"{h['lat']},{h['lon']}",
        } for h in geocode(source, a.text)[:5]]

    source, res, errors = with_fallback(run, ("transitous", "local"))
    return {"source": source, "resultats": res, "erreurs": errors or None}


def cmd_regions(a):
    loaded = loaded_regions()
    out = {"chargees": loaded}
    try:
        manifest = json.loads((MOTIS_STATE / "current" / "manifest.json").read_text())
        out["depuis"] = datetime.fromtimestamp(manifest["built_at"], TZ).isoformat(timespec="minutes")
        out["epinglees"] = manifest.get("pinned", [])
    except (OSError, ValueError, KeyError):
        pass
    requests_dir = MOTIS_STATE / "requests"
    if requests_dir.exists():
        out["demandees"] = sorted(p.name for p in requests_dir.iterdir())
    if a.at:
        coord = as_coord(a.at) or resolve_place(a.at)["coord"]
        region = region_of(*coord)
        out["region_du_lieu"] = region
        out["couverte_localement"] = region in loaded
    if a.request:
        known = {r["id"] for r in region_catalog()}
        if a.request not in known:
            sys.exit(f"région inconnue {a.request!r} ; connues : {', '.join(sorted(known))}")
        out["demande_envoyee"] = request_region(a.request)
    return out


def main():
    p = argparse.ArgumentParser(prog="transit", description="Transports en commun : MOTIS local puis Transitous.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("plan", help="itinéraire de A à B")
    s.add_argument("frm", metavar="DE")
    s.add_argument("to", metavar="VERS")
    s.add_argument("--at", help="date ISO 8601 (défaut : maintenant)")
    s.add_argument("--arrive", action="store_true", help="--at est l'heure d'arrivée")
    s.add_argument("-n", type=int, default=3)
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("trip", help="état d'une course, arrêt par arrêt")
    s.add_argument("trip_id")
    s.set_defaults(fn=cmd_trip)

    s = sub.add_parser("departures", help="prochains départs à un arrêt")
    s.add_argument("stop")
    s.add_argument("--at")
    s.add_argument("-n", type=int, default=10)
    s.set_defaults(fn=cmd_departures)

    s = sub.add_parser("geocode", help="chercher un arrêt ou une adresse")
    s.add_argument("text")
    s.set_defaults(fn=cmd_geocode)

    s = sub.add_parser("regions", help="régions chargées localement")
    s.add_argument("--at", help="lieu ou lat,lon : dans quelle région, couverte ou non")
    s.add_argument("--request", metavar="REGION", help="demander le chargement d'une région")
    s.set_defaults(fn=cmd_regions)

    a = p.parse_args()
    started = time.monotonic()
    out = a.fn(a)
    out["duree_s"] = round(time.monotonic() - started, 1)
    json.dump({k: v for k, v in out.items() if v is not None}, sys.stdout, ensure_ascii=False, indent=1)
    print()


if __name__ == "__main__":
    main()
