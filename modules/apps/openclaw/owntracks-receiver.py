#!/usr/bin/env python3
# OwnTracks HTTP receiver, plus reads for a tagged tailnet node and ingest from
# an iOS Shortcut.
#
# Write (OwnTracks app or Shortcut). Basic auth, and Tailscale-User-Login must
# be an allowed login. Serve sets that header and overwrites a client value.
# Tagged nodes do not get a login, so they cannot write.
#
#   POST /pub
#   {"_type":"location","lat":48.8566,"lon":2.3522,"acc":12,"tst":1710000000,"tid":"sc","batt":80,"alt":35}
#
# _type, lat and lon are required. acc, tst, batt and alt may be omitted.
# Numbers may be JSON numbers or strings ("48.85" or "48,85"). A missing or
# unreadable tst uses the server clock. tst >= 1e11 is treated as milliseconds.
# tid "sc" marks a Shortcut fix. Optional OwnTracks fields (vel, cog, bs, t, m,
# …) are stored when present. latest.json keeps the greatest tst. A fix within
# 25 m and 60 s of that latest fix is not appended to history.jsonl; a newer
# one still replaces latest.json.
#
# Read. Authorization: Bearer <owntracks-read-token>. The Basic password is not
# accepted. Tagged nodes use this because Serve does not set Tailscale-User-Login
# for them.
#
#   GET /latest                         last fix, plus age_s and acc_m
#   GET /history?since=<unix epoch>     points and transitions with tst >= since
#   POST /request                       queue one reportLocation command; the
#                                       next successful write is answered with
#                                       [{"_type":"cmd","action":"reportLocation"}]
import base64
import hashlib
import hmac
import json
import math
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DATA_DIR = Path(os.environ["LOC_DATA_DIR"])
HOST = os.environ.get("LOC_HOST", "127.0.0.1")
PORT = int(os.environ.get("LOC_PORT", "8765"))
ALLOWED_LOGINS = {x for x in os.environ.get("LOC_ALLOWED_LOGINS", "").split() if x}
MAX_BODY = 64 * 1024
TOKEN_MAX = 256
DEDUPE_M = 25
DEDUPE_S = 60
# 1e11 seconds is year 5138; values at least this large are epoch milliseconds.
MS_EPOCH = 100_000_000_000

HISTORY = DATA_DIR / "history.jsonl"
LATEST = DATA_DIR / "latest.json"
TRANSITIONS = DATA_DIR / "transitions.jsonl"
REPORT_FLAG = DATA_DIR / "report.pending"
MOTIS_STATE = Path(os.environ.get("LOC_MOTIS_STATE", "/var/lib/motis"))
REGION_RECHECK_M = 2000
REGION_STAY_S = 30 * 60
REGION_TRANSIT_KMH = 50
REGION_RENEW_S = 48 * 3600

ERR_UNAUTH = b'{"error":"unauthorized"}'
ERR_BAD_LENGTH = b'{"error":"bad length"}'
ERR_TOO_LARGE = b'{"error":"too large"}'
ERR_BAD_LOCATION = b'{"error":"bad location"}'
ERR_NO_POSITION = b'{"error":"no position"}'
REPORT_CMD = b'[{"_type":"cmd","action":"reportLocation"}]'

_lock = threading.Lock()
_regions = {"mtime": None, "data": []}
_last_region = {"lat": None, "lon": None, "id": None}
_candidate = {"id": None, "since": None}
_requested = {"id": None, "at": 0}


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
    if moved_m(rec["lat"], rec["lon"]) >= REGION_RECHECK_M:
        _last_region.update(lat=rec["lat"], lon=rec["lon"], id=region_of(rec["lat"], rec["lon"]))
    if (rec.get("speed_kmh") or 0) > REGION_TRANSIT_KMH:
        return
    region = _last_region["id"]
    if region is None:
        _candidate.update(id=None, since=None)
        return
    if region != _candidate["id"]:
        _candidate.update(id=region, since=rec["ts"])
    if rec["ts"] - _candidate["since"] < REGION_STAY_S:
        return
    if region == _requested["id"] and time.time() - _requested["at"] < REGION_RENEW_S:
        return
    folder = MOTIS_STATE / "requests"
    try:
        if time.time() - (folder / region).stat().st_mtime < REGION_RENEW_S:
            _requested.update(id=region, at=time.time())
            return
    except OSError:
        pass
    try:
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{region}.")
        os.write(fd, b"position\n")
        os.fchmod(fd, 0o664)
        os.close(fd)
        os.replace(tmp, folder / region)
        _requested.update(id=region, at=time.time())
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


def digest_token(token):
    # Hash a fixed-size buffer so compare_digest does not short-circuit on
    # length and the hash itself does not scale with the guess.
    raw = token.encode()
    if len(raw) > TOKEN_MAX:
        raw = b""
    return hashlib.sha256(bytes([len(raw)]) + raw + bytes(TOKEN_MAX - len(raw))).digest()


def load_read_token_digest():
    path = os.environ.get("LOC_READ_TOKEN_FILE")
    if not path:
        sys.exit("LOC_READ_TOKEN_FILE is required")
    token = Path(path).read_text().strip()
    if not token or any(c.isspace() for c in token):
        sys.exit(f"{path} must contain a single token")
    return digest_token(token)


def safe_compare(got, expected):
    if not isinstance(got, str) or len(got) != len(expected):
        hmac.compare_digest(expected, expected)
        return False
    return hmac.compare_digest(got, expected)


def token_matches(presented):
    return hmac.compare_digest(digest_token(presented), READ_TOKEN_DIGEST)


EXPECTED_AUTH = load_expected_auth()
READ_TOKEN_DIGEST = load_read_token_digest()


def as_float(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            text = text[:-1].strip()
        if not text:
            return None
        if "," in text and "." not in text:
            text = text.replace(",", ".")
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number):
        return None
    return number


def num(value):
    number = as_float(value)
    if number is None:
        return None
    if number.is_integer() and abs(number) < 2**53:
        return int(number)
    return number


def optional_num(msg, key, minimum=None, maximum=None):
    if key not in msg or msg[key] is None:
        return None
    number = num(msg[key])
    if number is None:
        return None
    if minimum is not None and number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def epoch_seconds(value, now):
    if value is None or value is False or value == "":
        return now
    number = as_float(value)
    if number is None or number < 0:
        return now
    if number >= MS_EPOCH:
        number /= 1000.0
    return int(number)


def device_name(header, tid):
    for raw in (header, tid):
        if raw is None:
            continue
        text = raw.strip() if isinstance(raw, str) else str(raw).strip()
        if text:
            return text[:64]
    return None


def record_of(msg, device):
    now = int(time.time())
    lat = as_float(msg.get("lat"))
    lon = as_float(msg.get("lon"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    tst = msg.get("tst") if "tst" in msg else None
    charging = None
    if "bs" in msg and msg["bs"] is not None:
        bs = num(msg["bs"])
        if bs is not None:
            charging = bs in (2, 3)
    rec = {
        "lat": lat,
        "lon": lon,
        "acc_m": optional_num(msg, "acc", minimum=0),
        "alt_m": optional_num(msg, "alt"),
        "speed_kmh": optional_num(msg, "vel", minimum=0),
        "course_deg": optional_num(msg, "cog"),
        "battery_pct": optional_num(msg, "batt", minimum=0, maximum=100),
        "charging": charging,
        "trigger": msg.get("t") if isinstance(msg.get("t"), str) else None,
        "monitoring": optional_num(msg, "m"),
        "motion": msg.get("motionactivities") if isinstance(msg.get("motionactivities"), list) else None,
        "wifi": msg.get("SSID") if isinstance(msg.get("SSID"), str) else None,
        "regions": msg.get("inregions") if isinstance(msg.get("inregions"), list) else None,
        "ts": epoch_seconds(tst, now),
        "received_at": now,
        "device": device,
    }
    return {k: v for k, v in rec.items() if v is not None}


def distance_m(lat1, lon1, lat2, lon2):
    dlat = (lat1 - lat2) * 111320
    dlon = (lon1 - lon2) * 111320 * math.cos(math.radians(lat1))
    return math.hypot(dlat, dlon)


def near_duplicate(rec, previous):
    if not previous:
        return False
    try:
        if abs(int(rec["ts"]) - int(previous["ts"])) > DEDUPE_S:
            return False
        return distance_m(rec["lat"], rec["lon"], float(previous["lat"]), float(previous["lon"])) <= DEDUPE_M
    except (KeyError, TypeError, ValueError):
        return False


def load_latest():
    try:
        data = json.loads(LATEST.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_latest(rec):
    tmp = LATEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False))
    tmp.replace(LATEST)


def append_jsonl(path, rec):
    with path.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def store(rec):
    previous = load_latest()
    if near_duplicate(rec, previous):
        if rec["ts"] > previous.get("ts", 0):
            write_latest(rec)
        return
    append_jsonl(HISTORY, rec)
    if previous is None or rec["ts"] >= previous.get("ts", 0):
        write_latest(rec)


def transition_of(msg, device):
    now = int(time.time())
    lat = as_float(msg.get("lat")) if "lat" in msg else None
    lon = as_float(msg.get("lon")) if "lon" in msg else None
    tst = msg.get("tst") if "tst" in msg else None
    return {
        "event": msg.get("event"),
        "region": msg.get("desc"),
        "lat": lat,
        "lon": lon,
        "ts": epoch_seconds(tst, now),
        "received_at": now,
        "device": device,
    }


def ts_of(rec):
    try:
        return int(rec.get("ts", 0))
    except (TypeError, ValueError):
        return None


def read_jsonl(path, since):
    out = []
    try:
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                ts = ts_of(rec)
                if ts is not None and ts >= since:
                    out.append(rec)
    except OSError:
        pass
    out.sort(key=lambda rec: ts_of(rec) or 0)
    return out


def request_report():
    REPORT_FLAG.write_text("1\n")


def take_report():
    if not REPORT_FLAG.exists():
        return False
    try:
        REPORT_FLAG.unlink()
    except OSError:
        return False
    return True


def parse_since(qs):
    raw = (qs.get("since") or [None])[0]
    if raw is None or str(raw).strip() == "":
        return None, "since required"
    try:
        return int(float(raw)), None
    except (TypeError, ValueError, OverflowError):
        return None, "bad since"


def dump(obj):
    return json.dumps(obj, ensure_ascii=False).encode()


class Handler(BaseHTTPRequestHandler):
    server_version = "owntracks-receiver"
    sys_version = ""

    def reply(self, code, body=b"[]"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def route(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        return path, parse_qs(parsed.query, keep_blank_values=True)

    def write_authorized(self):
        if not safe_compare(self.headers.get("Authorization", ""), EXPECTED_AUTH):
            return False
        return self.headers.get("Tailscale-User-Login", "") in ALLOWED_LOGINS

    def read_authorized(self):
        header = self.headers.get("Authorization", "")
        scheme, sep, rest = header.partition(" ")
        presented = rest if sep and scheme.lower() == "bearer" else ""
        return token_matches(presented)

    def ingest(self, msg):
        device = device_name(self.headers.get("X-Limit-D"), msg.get("tid"))
        kind = msg.get("_type")
        if kind == "location":
            rec = record_of(msg, device)
            if rec is None:
                return 400
            with _lock:
                store(rec)
                request_region_for(rec)
            return 200
        if kind == "transition":
            with _lock:
                append_jsonl(TRANSITIONS, transition_of(msg, device))
            return 200
        return 200

    def do_POST(self):
        path, _qs = self.route()
        if path == "/request":
            if not (self.read_authorized() or self.write_authorized()):
                return self.reply(401, ERR_UNAUTH)
            with _lock:
                request_report()
            return self.reply(200, b'{"ok":true}')
        if not self.write_authorized():
            return self.reply(401, ERR_UNAUTH)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.reply(400, ERR_BAD_LENGTH)
        if length < 0:
            return self.reply(400, ERR_BAD_LENGTH)
        if length > MAX_BODY:
            return self.reply(413, ERR_TOO_LARGE)
        raw = self.rfile.read(length) if length else b""
        code = 200
        if raw.strip():
            try:
                msg = json.loads(raw)
            except ValueError:
                msg = None
            if isinstance(msg, dict):
                code = self.ingest(msg)
        if code != 200:
            return self.reply(code, ERR_BAD_LOCATION)
        with _lock:
            cmd = take_report()
        return self.reply(200, REPORT_CMD if cmd else b"[]")

    def do_GET(self):
        if not self.read_authorized():
            return self.reply(401, ERR_UNAUTH)
        path, qs = self.route()
        if path == "/latest":
            with _lock:
                rec = load_latest()
            if rec is None:
                return self.reply(404, ERR_NO_POSITION)
            view = dict(rec)
            ts = rec.get("ts")
            if isinstance(ts, (int, float)) and not isinstance(ts, bool):
                view["age_s"] = int(time.time()) - int(ts)
            return self.reply(200, dump(view))
        if path == "/history":
            since, err = parse_since(qs)
            if err:
                return self.reply(400, dump({"error": err}))
            with _lock:
                points = read_jsonl(HISTORY, since)
                transitions = read_jsonl(TRANSITIONS, since)
            return self.reply(200, dump({"since": since, "points": points, "transitions": transitions}))
        return self.reply(404, b'{"error":"not found"}')

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
