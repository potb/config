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
HERE_WORDS = {"ici", "here", "moi"}
HERE_MAX_AGE_S = 30 * 60


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


def current_position():
    path = Path(os.environ.get("LOC_DATA_DIR", "/var/lib/owntracks")) / "latest.json"
    try:
        rec = json.loads(path.read_text())
    except (OSError, ValueError):
        raise NoResult("position inconnue : aucune position reçue du téléphone")
    age = int(time.time()) - int(rec["ts"])
    if age > HERE_MAX_AGE_S:
        raise NoResult(f"position trop ancienne ({age // 60} min), demande où est l'utilisateur")
    return {
        "coord": (rec["lat"], rec["lon"]),
        "name": f"position actuelle (il y a {age // 60} min, ±{int(rec.get('acc_m') or 0)} m)",
        "stop": None,
    }


def resolve_place(text):
    if text.strip().lower() in HERE_WORDS:
        return current_position()
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


TRACK_FILE = Path(os.environ.get("TRANSIT_TRACK_FILE", "/var/lib/openclaw/workspace/memory/trajets.json"))
WATCH_WINDOW_S = 3 * 3600
DELAY_ALERT_MIN = 5
WALK_SPEED_MPS = 1.3


def load_tracked():
    try:
        return json.loads(TRACK_FILE.read_text())
    except (OSError, ValueError):
        return {"trajets": []}


def save_tracked(data):
    TRACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = TRACK_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.replace(TRACK_FILE)


def trip_status(trip_id):
    def run(source):
        d = call(source, "v6/trip", tripId=trip_id)
        leg = next((leg for leg in d.get("legs", []) if leg["mode"] != "WALK"), None)
        if not leg:
            raise NoResult("course introuvable")
        return leg

    source, leg, errors = with_fallback(run)
    return source, leg, errors


def stop_on_leg(leg, stop_id, prefer):
    stops = [leg["from"], *leg.get("intermediateStops", []), leg["to"]]
    matches = [s for s in stops if s.get("stopId") == stop_id or s.get("parentId") == stop_id]
    if matches:
        return matches[0]
    return stops[0] if prefer == "first" else stops[-1]


def ground_distance_m(lat1, lon1, lat2, lon2):
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def observe_step(step):
    source, leg, errors = trip_status(step["trip_id"])
    if leg is None:
        return {"etat": "introuvable", "erreurs": errors}
    board = stop_on_leg(leg, step.get("arret_depart_id"), "first")
    alight = stop_on_leg(leg, step.get("arret_arrivee_id"), "last")
    dep = board.get("departure") or board.get("scheduledDeparture")
    arr = alight.get("arrival") or alight.get("scheduledArrival")
    return {
        "etat": "annule" if leg.get("cancelled") or board.get("cancelled") else "ok",
        "source": source,
        "realtime": bool(leg.get("realTime")),
        "depart": dep,
        "arrivee": arr,
        "retard_depart_min": delay_min(board.get("departure"), board.get("scheduledDeparture")),
        "retard_arrivee_min": delay_min(alight.get("arrival"), alight.get("scheduledArrival")),
        "voie": board.get("track"),
        "alertes": alerts_of(leg),
        "arret_lat": board.get("lat"),
        "arret_lon": board.get("lon"),
    }


def changes_between(old, new, step):
    out = []
    label = f"{step.get('ligne') or step['trip_id'][:40]} {step.get('de', '')}".strip()
    if new["etat"] != (old or {}).get("etat"):
        if new["etat"] == "annule":
            out.append(f"{label} : course annulée")
        elif new["etat"] == "introuvable":
            out.append(f"{label} : course introuvable (horaires modifiés ?), recalcule le trajet")
    old_delay = (old or {}).get("retard_depart_min") or 0
    new_delay = new.get("retard_depart_min") or 0
    if new["etat"] == "ok" and abs(new_delay - old_delay) >= DELAY_ALERT_MIN:
        out.append(f"{label} : départ {hhmm(new['depart'])}, retard {new_delay} min (avant {old_delay})")
    if (old or {}).get("voie") and new.get("voie") and old["voie"] != new["voie"]:
        out.append(f"{label} : changement de voie {old['voie']} vers {new['voie']}")
    for alert in new.get("alertes", []):
        if alert not in (old or {}).get("alertes", []):
            out.append(f"{label} : alerte « {alert[:160]} »")
    return out


def connection_break(prev_obs, next_obs, min_transfer_min):
    if not prev_obs or not next_obs or "arrivee" not in prev_obs or "depart" not in next_obs:
        return None
    if not prev_obs.get("arrivee") or not next_obs.get("depart"):
        return None
    margin = (parse_time(next_obs["depart"]) - parse_time(prev_obs["arrivee"])).total_seconds() / 60
    return round(margin) if margin < min_transfer_min else None


def reachability(first_obs):
    here = Path(os.environ.get("LOC_DATA_DIR", "/var/lib/owntracks")) / "latest.json"
    try:
        rec = json.loads(here.read_text())
    except (OSError, ValueError):
        return None
    if time.time() - rec["ts"] > HERE_MAX_AGE_S or first_obs.get("arret_lat") is None or not first_obs.get("depart"):
        return None
    dist = ground_distance_m(rec["lat"], rec["lon"], first_obs["arret_lat"], first_obs["arret_lon"])
    walk_min = dist * 1.3 / WALK_SPEED_MPS / 60
    left = (parse_time(first_obs["depart"]).timestamp() - time.time()) / 60
    return {"distance_m": round(dist), "marche_min": round(walk_min), "reste_min": round(left)}


def cmd_track(a):
    data = load_tracked()
    if a.action == "list":
        return data
    if a.action == "rm":
        before = len(data["trajets"])
        data["trajets"] = [t for t in data["trajets"] if t["id"] != a.value]
        save_tracked(data)
        return {"supprime": before - len(data["trajets"])}
    if a.action == "add":
        spec = json.loads(a.value)
        if not spec.get("etapes"):
            raise NoResult("un trajet a besoin d'au moins une étape avec trip_id")
        trip = {
            "id": spec.get("id") or f"t{int(time.time())}",
            "nom": spec.get("nom", ""),
            "etapes": [{
                "trip_id": e["trip_id"],
                "ligne": e.get("ligne"),
                "de": e.get("de"),
                "vers": e.get("vers"),
                "arret_depart_id": e.get("arret_depart_id") or e.get("arret_id"),
                "arret_arrivee_id": e.get("arret_arrivee_id"),
            } for e in spec["etapes"]],
            "correspondance_min": spec.get("correspondance_min", 4),
            "suivre_position": spec.get("suivre_position", True),
            "vu": {},
        }
        data["trajets"] = [t for t in data["trajets"] if t["id"] != trip["id"]] + [trip]
        save_tracked(data)
        return {"ajoute": trip["id"], "etapes": len(trip["etapes"])}
    raise NoResult(f"action inconnue {a.action}")


def cmd_watch(a):
    data = load_tracked()
    now = time.time()
    report, kept = [], []
    for trip in data["trajets"]:
        observed = [observe_step(step) for step in trip["etapes"]]
        first_dep = observed[0].get("depart")
        last_arr = observed[-1].get("arrivee")
        if last_arr and parse_time(last_arr).timestamp() < now - 1800:
            continue
        kept.append(trip)
        if first_dep and parse_time(first_dep).timestamp() > now + WATCH_WINDOW_S and not a.all:
            continue
        seen = trip.get("vu", {})
        messages = []
        for i, (step, obs) in enumerate(zip(trip["etapes"], observed)):
            messages += changes_between(seen.get(str(i)), obs, step)
        for i in range(len(observed) - 1):
            margin = connection_break(observed[i], observed[i + 1], trip.get("correspondance_min", 4))
            key = f"corresp{i}"
            if margin is not None and seen.get(key) != margin:
                messages.append(f"correspondance {i + 1} compromise : {margin} min pour changer")
                seen[key] = margin
        if trip.get("suivre_position") and observed[0]["etat"] == "ok":
            r = reachability(observed[0])
            if r and r["reste_min"] >= 0 and r["marche_min"] > r["reste_min"] and not seen.get("trop_loin"):
                messages.append(
                    f"{trip['etapes'][0].get('ligne') or 'premier départ'} : il est à {r['distance_m']} m de l'arrêt "
                    f"(~{r['marche_min']} min à pied) et le départ est dans {r['reste_min']} min"
                )
                seen["trop_loin"] = True
        for i, obs in enumerate(observed):
            seen[str(i)] = {k: obs.get(k) for k in ("etat", "retard_depart_min", "voie", "alertes")}
        trip["vu"] = seen
        if messages or a.all:
            report.append({
                "trajet": trip["id"],
                "nom": trip.get("nom"),
                "changements": messages,
                "etapes": [{
                    "ligne": s.get("ligne"), "de": s.get("de"),
                    "depart": hhmm(o.get("depart")), "arrivee": hhmm(o.get("arrivee")),
                    "retard_min": o.get("retard_depart_min"), "realtime": o.get("realtime"), "etat": o.get("etat"),
                } for s, o in zip(trip["etapes"], observed)],
            })
    data["trajets"] = kept
    if not a.dry_run:
        save_tracked(data)
    return {"a_signaler": [r for r in report if r["changements"]], **({"tous": report} if a.all else {})}


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

    s = sub.add_parser("track", help="trajets suivis : add '<json>', list, rm <id>")
    s.add_argument("action", choices=["add", "list", "rm"])
    s.add_argument("value", nargs="?", default="")
    s.set_defaults(fn=cmd_track)

    s = sub.add_parser("watch", help="vérifie les trajets suivis, ne sort que ce qui a changé")
    s.add_argument("--all", action="store_true", help="montrer tous les trajets, même sans changement")
    s.add_argument("--dry-run", action="store_true", help="ne pas enregistrer l'état vu")
    s.set_defaults(fn=cmd_watch)

    a = p.parse_args()
    started = time.monotonic()
    try:
        out = a.fn(a)
    except NoResult as e:
        out = {"erreur": str(e)}
    out["duree_s"] = round(time.monotonic() - started, 1)
    json.dump({k: v for k, v in out.items() if v is not None}, sys.stdout, ensure_ascii=False, indent=1)
    print()


if __name__ == "__main__":
    main()
