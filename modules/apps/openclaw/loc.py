#!/usr/bin/env python3
import argparse
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_DIR = Path(os.environ.get("LOC_DATA_DIR", "/var/lib/owntracks"))
TZ = ZoneInfo("Europe/Paris")
STALE_AFTER_S = 30 * 60


def age_text(seconds):
    if seconds < 120:
        return f"il y a {seconds} s"
    if seconds < 7200:
        return f"il y a {seconds // 60} min"
    if seconds < 172800:
        return f"il y a {seconds // 3600} h"
    return f"il y a {seconds // 86400} j"


def local_time(ts):
    return datetime.fromtimestamp(ts, TZ).isoformat(timespec="minutes")


def distance_m(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def read_latest():
    try:
        return json.loads((DATA_DIR / "latest.json").read_text())
    except (OSError, ValueError):
        return None


def read_history(since):
    path = DATA_DIR / "history.jsonl"
    out = []
    try:
        with path.open() as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("ts", 0) >= since:
                    out.append(rec)
    except OSError:
        pass
    return sorted(out, key=lambda r: r["ts"])


def with_context(rec):
    age = int(time.time()) - int(rec["ts"])
    out = dict(rec)
    out["heure"] = local_time(rec["ts"])
    out["age_s"] = age
    out["age"] = age_text(age)
    out["perimee"] = age > STALE_AFTER_S
    out["coord"] = f"{rec['lat']},{rec['lon']}"
    out["precision"] = "zone approximative" if (rec.get("acc_m") or 0) > 500 else "precise"
    return out


def cmd_latest(_a):
    rec = read_latest()
    if rec is None:
        return {"erreur": "aucune position reçue"}
    return with_context(rec)


def cmd_coord(a):
    rec = read_latest()
    if rec is None:
        sys.exit("aucune position reçue")
    age = int(time.time()) - int(rec["ts"])
    if age > a.max_age * 60:
        sys.exit(f"position trop ancienne ({age_text(age)})")
    print(f"{rec['lat']},{rec['lon']}")
    return None


def stays(points, radius_m=150, min_minutes=10):
    out, current = [], None
    for p in points:
        if current and distance_m(current["centre"], p) <= radius_m:
            current["fin"] = p["ts"]
            current["n"] += 1
            continue
        if current and (current["fin"] - current["debut"]) >= min_minutes * 60:
            out.append(current)
        current = {"centre": {"lat": p["lat"], "lon": p["lon"]}, "debut": p["ts"], "fin": p["ts"], "n": 1}
    if current and (current["fin"] - current["debut"]) >= min_minutes * 60:
        out.append(current)
    return [{
        "coord": f"{s['centre']['lat']:.5f},{s['centre']['lon']:.5f}",
        "de": local_time(s["debut"]),
        "a": local_time(s["fin"]),
        "duree_min": round((s["fin"] - s["debut"]) / 60),
    } for s in out]


def cmd_history(a):
    since = time.time() - a.hours * 3600
    points = read_history(since)
    travelled = sum(distance_m(p, q) for p, q in zip(points, points[1:]))
    return {
        "depuis": local_time(since),
        "points": len(points),
        "distance_km": round(travelled / 1000, 1),
        "arrets": stays(points),
        "derniere": with_context(points[-1]) if points else None,
        **({"trace": [{"heure": local_time(p["ts"]), "coord": f"{p['lat']},{p['lon']}", "acc_m": p.get("acc_m")} for p in points]} if a.full else {}),
    }


def cmd_transitions(a):
    since = time.time() - a.hours * 3600
    out = []
    try:
        with (DATA_DIR / "transitions.jsonl").open() as f:
            for line in f:
                try:
                    t = json.loads(line)
                except ValueError:
                    continue
                if t.get("ts", 0) >= since:
                    out.append({"heure": local_time(t["ts"]), "evenement": t.get("event"), "lieu": t.get("region")})
    except OSError:
        pass
    return {"transitions": out}


def main():
    p = argparse.ArgumentParser(prog="loc", description="Position de l'utilisateur (iPhone via OwnTracks).")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("latest", help="dernière position connue et son âge").set_defaults(fn=cmd_latest)
    s = sub.add_parser("coord", help="lat,lon seul, pour transit ; échoue si trop ancien")
    s.add_argument("--max-age", type=int, default=30, help="minutes (défaut 30)")
    s.set_defaults(fn=cmd_coord)
    s = sub.add_parser("history", help="résumé des N dernières heures")
    s.add_argument("hours", nargs="?", type=float, default=24)
    s.add_argument("--full", action="store_true", help="inclure tous les points")
    s.set_defaults(fn=cmd_history)
    s = sub.add_parser("transitions", help="entrées et sorties de lieux enregistrés")
    s.add_argument("hours", nargs="?", type=float, default=24)
    s.set_defaults(fn=cmd_transitions)
    a = p.parse_args()
    out = a.fn(a)
    if out is not None:
        json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
        print()


if __name__ == "__main__":
    main()
