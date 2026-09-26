#!/usr/bin/env python3
import base64
import hmac
import json
import math
import os
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA_DIR = Path(os.environ["LOC_DATA_DIR"])
HOST = os.environ.get("LOC_HOST", "127.0.0.1")
PORT = int(os.environ.get("LOC_PORT", "8765"))
ALLOWED_LOGINS = {x for x in os.environ.get("LOC_ALLOWED_LOGINS", "").split() if x}
MAX_BODY = 64 * 1024

HISTORY = DATA_DIR / "history.jsonl"
LATEST = DATA_DIR / "latest.json"
MOTIS_STATE = Path(os.environ.get("LOC_MOTIS_STATE", "/var/lib/motis"))
REGION_RECHECK_M = 2000

_regions = {"mtime": None, "data": []}
_last_region = {"lat": None, "lon": None, "id": None}


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


def region_catalog():
    path = MOTIS_STATE / "catalog" / "regions.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    if mtime != _regions["mtime"]:
        try:
            _regions["data"] = json.loads(path.read_text())
            _regions["mtime"] = mtime
        except (OSError, ValueError):
            return _regions["data"]
    return _regions["data"]


def region_of(lat, lon):
    for region in region_catalog():
        for polygon in region["polygons"]:
            if point_in_ring(lon, lat, polygon[0]) and not any(point_in_ring(lon, lat, h) for h in polygon[1:]):
                return region["id"]
    return None


def moved_m(lat, lon):
    if _last_region["lat"] is None:
        return float("inf")
    dlat = (lat - _last_region["lat"]) * 111320
    dlon = (lon - _last_region["lon"]) * 111320 * math.cos(math.radians(lat))
    return math.hypot(dlat, dlon)


def request_region_for(rec):
    if time.time() - rec["ts"] > 3600:
        return
    moved = moved_m(rec["lat"], rec["lon"])
    stale = time.time() - _last_region.get("touched", 0) > 86400
    if moved < REGION_RECHECK_M and not stale:
        return
    region = region_of(rec["lat"], rec["lon"]) if moved >= REGION_RECHECK_M else _last_region["id"]
    _last_region.update(lat=rec["lat"], lon=rec["lon"])
    if region is None or (region == _last_region["id"] and not stale):
        return
    _last_region.update(id=region, touched=time.time())
    folder = MOTIS_STATE / "requests"
    try:
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{region}.")
        os.fchmod(fd, 0o664)
        os.close(fd)
        os.replace(tmp, folder / region)
    except OSError as e:
        print(f"owntracks-receiver: cannot request region {region}: {e}", file=sys.stderr, flush=True)


def load_expected_auth():
    user = os.environ.get("LOC_USER")
    password_file = os.environ.get("LOC_PASSWORD_FILE")
    if not user or not password_file:
        sys.exit("LOC_USER and LOC_PASSWORD_FILE are required")
    password = Path(password_file).read_text().strip()
    if not password:
        sys.exit(f"{password_file} is empty")
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


EXPECTED_AUTH = load_expected_auth()


def record_of(msg, device):
    now = int(time.time())
    rec = {
        "lat": msg["lat"],
        "lon": msg["lon"],
        "acc_m": msg.get("acc"),
        "alt_m": msg.get("alt"),
        "speed_kmh": msg.get("vel"),
        "course_deg": msg.get("cog"),
        "battery_pct": msg.get("batt"),
        "charging": msg.get("bs") in (2, 3) if "bs" in msg else None,
        "trigger": msg.get("t"),
        "monitoring": msg.get("m"),
        "motion": msg.get("motionactivities"),
        "wifi": msg.get("SSID"),
        "regions": msg.get("inregions"),
        "ts": int(msg.get("tst", now)),
        "received_at": now,
        "device": device,
    }
    return {k: v for k, v in rec.items() if v is not None}


def store(rec):
    line = json.dumps(rec, ensure_ascii=False)
    with HISTORY.open("a") as f:
        f.write(line + "\n")
    try:
        previous = json.loads(LATEST.read_text())
    except (OSError, ValueError):
        previous = None
    if previous is None or rec["ts"] >= previous.get("ts", 0):
        tmp = LATEST.with_suffix(".tmp")
        tmp.write_text(line)
        tmp.replace(LATEST)


def transition_of(msg, device):
    return {
        "event": msg.get("event"),
        "region": msg.get("desc"),
        "lat": msg.get("lat"),
        "lon": msg.get("lon"),
        "ts": int(msg.get("tst", time.time())),
        "received_at": int(time.time()),
        "device": device,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "owntracks-receiver"
    sys_version = ""

    def reply(self, code, body=b"[]"):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        if not hmac.compare_digest(self.headers.get("Authorization", ""), EXPECTED_AUTH):
            return False
        return self.headers.get("Tailscale-User-Login", "") in ALLOWED_LOGINS

    def do_POST(self):
        if not self.authorized():
            return self.reply(401, b'{"error":"unauthorized"}')
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.reply(400, b'{"error":"bad length"}')
        if length > MAX_BODY:
            return self.reply(413, b'{"error":"too large"}')
        raw = self.rfile.read(length) if length else b""
        if not raw.strip():
            return self.reply(200)
        try:
            msg = json.loads(raw)
        except ValueError:
            return self.reply(200)
        if not isinstance(msg, dict):
            return self.reply(200)
        device = self.headers.get("X-Limit-D") or msg.get("tid")
        kind = msg.get("_type")
        if kind == "location" and "lat" in msg and "lon" in msg:
            rec = record_of(msg, device)
            store(rec)
            request_region_for(rec)
        elif kind == "transition":
            with (DATA_DIR / "transitions.jsonl").open("a") as f:
                f.write(json.dumps(transition_of(msg, device), ensure_ascii=False) + "\n")
        self.reply(200)

    def do_GET(self):
        self.reply(405, b'{"error":"POST only"}')

    def log_message(self, fmt, *args):
        pass


def main():
    if not ALLOWED_LOGINS:
        sys.exit("LOC_ALLOWED_LOGINS is required")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"owntracks-receiver listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
