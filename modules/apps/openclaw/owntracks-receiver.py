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
# Numbers may be JSON numbers or strings ("48.856613" or "48,856613"). A missing
# or unreadable tst uses the server clock. tst >= 1e11 is treated as milliseconds.
# A chunked body with no Content-Length is read in full before the response.
# application/x-www-form-urlencoded, and lat/lon on the /pub query string, are
# accepted when the body is not a JSON location.
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
ERR_BAD_BODY = b'{"error":"bad body"}'
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
    size = len(raw)
    if size > TOKEN_MAX:
        raw, size = b"", TOKEN_MAX + 1
    return hashlib.sha256(size.to_bytes(2, "big") + raw + bytes(TOKEN_MAX - len(raw))).digest()


def load_read_token_digest():
    path = os.environ.get("LOC_READ_TOKEN_FILE")
    if not path:
        sys.exit("LOC_READ_TOKEN_FILE is required")
    token = Path(path).read_text().strip()
    if not token or any(c.isspace() for c in token):
        sys.exit(f"{path} must contain a single token")
    if len(token.encode()) > TOKEN_MAX:
        sys.exit(f"{path} must be at most {TOKEN_MAX} bytes")
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


def note(msg):
    # Journal via stderr. Messages are fixed phrases: no coordinates, no headers.
    print(f"owntracks-receiver: {msg}", file=sys.stderr, flush=True)


class BodyError(Exception):
    def __init__(self, code, reason):
        self.code = code
        self.reason = reason


LOCATION_FIELDS = ("lat", "lon", "acc", "alt", "tst", "tid", "batt", "vel", "cog", "bs", "t")


def message_from_pairs(pairs):
    lat = pairs.get("lat")
    lon = pairs.get("lon")
    if lat in (None, "") or lon in (None, ""):
        return None
    msg = {"_type": "location", "lat": lat, "lon": lon}
    for key in LOCATION_FIELDS:
        if key in ("lat", "lon"):
            continue
        value = pairs.get(key)
        if value not in (None, ""):
            msg[key] = value
    return msg


def pairs_from_query(qs):
    return {key: values[0] for key, values in qs.items() if values}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "owntracks-receiver"
    sys_version = ""

    def setup(self):
        super().setup()
        self.request.settimeout(30)

    def log_error(self, fmt, *args):
        if args and isinstance(args[0], TimeoutError):
            note("connection timed out")

    def reply(self, code, body=b"[]"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def read_exact(self, count):
        buf = bytearray()
        while len(buf) < count:
            piece = self.rfile.read(count - len(buf))
            if not piece:
                raise BodyError(400, "truncated body")
            buf.extend(piece)
        return bytes(buf)

    def read_chunked(self):
        buf = bytearray()
        while True:
            line = self.rfile.readline(80)
            if not line.endswith(b"\n"):
                raise BodyError(400, "bad chunked encoding")
            token = line.split(b";", 1)[0].strip()
            try:
                size = int(token, 16)
            except ValueError:
                raise BodyError(400, "bad chunked encoding")
            if size < 0:
                raise BodyError(400, "bad chunked encoding")
            if size == 0:
                for _ in range(16):
                    trailer = self.rfile.readline(1024)
                    if trailer in (b"\r\n", b"\n"):
                        return bytes(buf)
                    if not trailer.endswith(b"\n"):
                        raise BodyError(400, "bad chunked encoding")
                raise BodyError(400, "bad chunked encoding")
            if len(buf) + size > MAX_BODY:
                raise BodyError(413, "body too large")
            buf.extend(self.read_exact(size))
            if self.read_exact(2) != b"\r\n":
                raise BodyError(400, "bad chunked encoding")

    def read_body(self):
        codings = [part.strip().lower() for part in self.headers.get("Transfer-Encoding", "").split(",") if part.strip()]
        if codings:
            if codings != ["chunked"]:
                raise BodyError(400, "unsupported transfer encoding")
            return self.read_chunked()
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return b""
        try:
            length = int(raw_length)
        except ValueError:
            raise BodyError(400, "bad length")
        if length < 0:
            raise BodyError(400, "bad length")
        if length > MAX_BODY:
            raise BodyError(413, "body too large")
        if length == 0:
            return b""
        return self.read_exact(length)

    def content_type(self):
        return self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()

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
                note("rejected location: coordinates missing or unusable")
                return 400
            if float(rec["lat"]).is_integer() and float(rec["lon"]).is_integer():
                note("stored location with integral lat and lon")
            with _lock:
                store(rec)
                request_region_for(rec)
            return 200
        if kind == "transition":
            with _lock:
                append_jsonl(TRANSITIONS, transition_of(msg, device))
            return 200
        return 200

    def reject_body(self, err):
        self.close_connection = True
        note(f"rejected body: {err.reason}")
        if err.code == 413:
            return self.reply(413, ERR_TOO_LARGE)
        if err.reason == "bad length":
            return self.reply(400, ERR_BAD_LENGTH)
        return self.reply(400, ERR_BAD_BODY)

    def interpret(self, raw, qs, path):
        # JSON wins when the body is a JSON object, including when a client
        # labels that object as a form. A real form is not valid JSON.
        if raw.strip():
            try_json = self.content_type() != "application/x-www-form-urlencoded" or raw.lstrip()[:1] in (b"{", b"[")
            if try_json:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    msg = None
                if isinstance(msg, dict):
                    return self.ingest(msg)
            if self.content_type() == "application/x-www-form-urlencoded" and b"=" in raw:
                try:
                    parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True, max_num_fields=32)
                except (UnicodeError, ValueError):
                    note("rejected form: undecodable")
                    return 400
                msg = message_from_pairs(pairs_from_query(parsed))
                if msg is None:
                    note("rejected form: no coordinates")
                    return 400
                return self.ingest(msg)
            fallback = message_from_pairs(pairs_from_query(qs)) if path == "/pub" else None
            if fallback is not None:
                return self.ingest(fallback)
            note("ignored body: not json")
            return 200
        if path == "/pub":
            fallback = message_from_pairs(pairs_from_query(qs))
            if fallback is not None:
                return self.ingest(fallback)
        return 200

    def do_POST(self):
        try:
            self.handle_post()
        except BodyError as err:
            self.reject_body(err)
        except Exception as exc:
            self.close_connection = True
            note(f"ingest failed: {type(exc).__name__}")
            try:
                self.reply(500, b'{"error":"internal"}')
            except Exception:
                return

    def discard_body(self):
        # Read a small body before rejecting so the socket is not closed with
        # unread bytes, which the client reports as a dropped connection.
        try:
            self.read_body()
        except BodyError:
            self.close_connection = True

    def handle_post(self):
        path, qs = self.route()
        if path == "/request":
            if not (self.read_authorized() or self.write_authorized()):
                self.close_connection = True
                note("rejected write: unauthorized")
                self.discard_body()
                return self.reply(401, ERR_UNAUTH)
            self.read_body()
            with _lock:
                request_report()
            return self.reply(200, b'{"ok":true}')
        if not self.write_authorized():
            self.close_connection = True
            note("rejected write: unauthorized")
            self.discard_body()
            return self.reply(401, ERR_UNAUTH)
        raw = self.read_body()
        code = self.interpret(raw, qs, path)
        if code == 400:
            return self.reply(400, ERR_BAD_LOCATION)
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
