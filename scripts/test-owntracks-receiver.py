#!/usr/bin/env python3
"""Exercise the OwnTracks receiver: writes, Shortcut ingest, bearer reads, reportLocation."""

import base64
import importlib.util
import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIVER = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "modules/apps/openclaw/owntracks-receiver.py"
LOC = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "modules/apps/openclaw/loc.py"

PASSWORD = "test-password"
TOKEN = "read-token-value"
LOGIN = "peio.thibault@gmail.com"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def basic_headers(login=LOGIN):
    raw = base64.b64encode(f"owntracks:{PASSWORD}".encode()).decode()
    headers = {"Authorization": f"Basic {raw}"}
    if login is not None:
        headers["Tailscale-User-Login"] = login
    return headers


def bearer_headers(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


class Client:
    def __init__(self, port):
        self.port = port
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, path, headers=None, body=None):
        data = None if body is None else (body if isinstance(body, bytes) else body.encode())
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers=headers or {},
            method=method,
        )
        try:
            with self.opener.open(req, timeout=5) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as err:
            return err.code, err.read()

    def json(self, method, path, headers=None, body=None):
        status, raw = self.request(method, path, headers, body)
        return status, json.loads(raw.decode() or "null")


def raw_post(port, path, headers, content_length, body=b""):
    sock = socket.create_connection(("127.0.0.1", port))
    try:
        lines = [f"POST {path} HTTP/1.0", f"Content-Length: {content_length}"]
        lines.extend(f"{key}: {value}" for key, value in headers.items())
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode() + body)
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        sock.close()
    head, _, resp = b"".join(chunks).partition(b"\r\n\r\n")
    return int(head.split()[1]), resp


def chunked_body(body):
    parts = [body[:7], body[7:]] if len(body) > 7 else [body]
    raw = b""
    for part in parts:
        if not part:
            continue
        raw += f"{len(part):x}\r\n".encode() + part + b"\r\n"
    return raw + b"0\r\n\r\n"


def read_response(sock):
    sock.settimeout(3)
    data = b""
    while b"\r\n\r\n" not in data:
        piece = sock.recv(4096)
        if not piece:
            break
        data += piece
    head, _, rest = data.partition(b"\r\n\r\n")
    status = int(head.split()[1])
    length = 0
    for line in head.split(b"\r\n")[1:]:
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())
    while len(rest) < length:
        piece = sock.recv(4096)
        if not piece:
            break
        rest += piece
    return status, rest[:length], head


def send_chunked(sock, path, headers, body, close=False):
    lines = [f"POST {path} HTTP/1.1", "Host: 127.0.0.1", "Transfer-Encoding: chunked"]
    if close:
        lines.append("Connection: close")
    lines.extend(f"{key}: {value}" for key, value in headers.items())
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode() + chunked_body(body))


def history_lines(data_dir):
    path = data_dir / "history.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    os.environ["NO_PROXY"] = "127.0.0.1"
    work = Path(tempfile.mkdtemp(prefix="owntracks-test-"))
    data = work / "data"
    data.mkdir()
    (work / "motis").mkdir()
    (work / "password").write_text(PASSWORD + "\n")
    (work / "token").write_text(TOKEN + "\n")
    os.environ["LOC_DATA_DIR"] = str(data)
    os.environ["LOC_MOTIS_STATE"] = str(work / "motis")
    os.environ["LOC_USER"] = "owntracks"
    os.environ["LOC_PASSWORD_FILE"] = str(work / "password")
    os.environ["LOC_READ_TOKEN_FILE"] = str(work / "token")
    os.environ["LOC_ALLOWED_LOGINS"] = LOGIN

    receiver = load_module(RECEIVER, "owntracks_receiver_under_test")
    loc = load_module(LOC, "loc_under_test")

    httpd = receiver.ThreadingHTTPServer(("127.0.0.1", 0), receiver.Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.02)
    else:
        sys.exit("receiver did not listen")

    client = Client(port)
    write = basic_headers()
    read = bearer_headers()

    try:
        def latest():
            return client.json("GET", "/latest", read)

        def post(path, payload, headers=None):
            body = payload if isinstance(payload, (bytes, str)) else json.dumps(payload)
            return client.json("POST", path, write if headers is None else headers, body)

        status, body = latest()
        assert status == 404 and body == {"error": "no position"}, (status, body)
        print("ok empty latest is 404")

        status, body = client.json("GET", "/latest")
        assert status == 401 and body == {"error": "unauthorized"}, (status, body)
        print("ok latest without a token is 401")

        status, body = client.json("GET", "/latest", basic_headers())
        assert status == 401, (status, body)
        print("ok basic auth cannot read")

        status, _body = client.json("GET", "/latest", bearer_headers("x"))
        assert status == 401, status
        status, _body = client.json("GET", "/latest", bearer_headers("y" * 300))
        assert status == 401, status
        status, _body = client.json("GET", "/history?since=0", bearer_headers(TOKEN + "x"))
        assert status == 401, status
        assert receiver.token_matches(TOKEN)
        assert not receiver.token_matches("x")
        assert not receiver.token_matches("y" * 300)
        assert not receiver.token_matches("")
        status, _body = client.json("GET", "/latest", bearer_headers("z" * receiver.TOKEN_MAX))
        assert status == 401, status
        assert not receiver.token_matches("z" * receiver.TOKEN_MAX)
        assert receiver.digest_token("y" * 300) != receiver.digest_token("")
        assert receiver.digest_token("y" * 300) == receiver.digest_token("w" * 400)
        print("ok wrong bearer lengths are rejected")

        owntracks = {
            "_type": "location",
            "lat": 48.1,
            "lon": 2.2,
            "acc": 15,
            "alt": 40,
            "vel": 3,
            "cog": 180,
            "batt": 55,
            "bs": 2,
            "t": "p",
            "m": 1,
            "tid": "ph",
            "tst": 1700000000,
            "SSID": "cafe",
            "inregions": ["Home"],
            "motionactivities": ["walking"],
        }
        headers = basic_headers()
        headers["X-Limit-D"] = "phone"
        status, body = post("/pub", owntracks, headers)
        assert status == 200 and body == [], (status, body)
        status, got = latest()
        assert status == 200, got
        assert got["lat"] == 48.1 and got["lon"] == 2.2
        assert got["acc_m"] == 15 and got["alt_m"] == 40
        assert got["speed_kmh"] == 3 and got["course_deg"] == 180
        assert got["battery_pct"] == 55 and got["charging"] is True
        assert got["trigger"] == "p" and got["monitoring"] == 1
        assert got["wifi"] == "cafe" and got["regions"] == ["Home"]
        assert got["motion"] == ["walking"]
        assert got["device"] == "phone" and got["ts"] == 1700000000
        assert abs(got["age_s"] - (int(time.time()) - 1700000000)) <= 1
        print("ok owntracks payload is stored and readable")

        status, body = post("/pub", owntracks, basic_headers(login=None))
        assert status == 401 and body == {"error": "unauthorized"}
        print("ok write without the login header is refused")

        wrong = basic_headers()
        wrong["Authorization"] = "Basic " + base64.b64encode(b"owntracks:nope").decode()
        status, body = post("/pub", owntracks, wrong)
        assert status == 401 and body == {"error": "unauthorized"}
        print("ok write with the wrong password is refused")

        status, body = post("/pub", owntracks, basic_headers("other@example.com"))
        assert status == 401, body
        print("ok write with the wrong login is refused")

        status, body = post("/pub", {"_type": "location", "lat": 1, "lon": 2, "tst": 1700000001}, bearer_headers())
        assert status == 401, body
        assert len(history_lines(data)) == 1
        print("ok bearer token cannot write a fix")

        status, body = post("/pub", {"_type": "location", "lat": 49, "lon": 3, "tst": 1690000000, "tid": "ph"})
        assert status == 200 and body == []
        status, got = latest()
        assert got["ts"] == 1700000000 and got["lat"] == 48.1
        assert len(history_lines(data)) == 2
        print("ok an older fix does not replace latest")

        status, body = post("/pub", {"_type": "location", "lat": 47, "lon": 1, "tst": 1710000000, "tid": "ph"})
        assert status == 200 and body == []
        status, got = latest()
        assert got["ts"] == 1710000000 and got["lat"] == 47
        assert len(history_lines(data)) == 3
        print("ok a newer fix replaces latest")

        before = len(history_lines(data))
        status, body = post("/pub", {"_type": "location", "lat": 47.00005, "lon": 1, "tst": 1710000030, "acc": 4, "tid": "ph"})
        assert status == 200 and body == []
        assert len(history_lines(data)) == before
        status, got = latest()
        assert got["ts"] == 1710000030 and got["acc_m"] == 4
        print("ok a near-duplicate updates latest without a history line")

        before = len(history_lines(data))
        status, _body = post("/pub", {"_type": "location", "lat": 47.00055, "lon": 1, "tst": 1710000050, "tid": "ph"})
        assert len(history_lines(data)) == before + 1
        status, got = latest()
        assert got["ts"] == 1710000050
        print("ok a fix just outside 25 m is kept")

        before = len(history_lines(data))
        status, _body = post("/pub", {"_type": "location", "lat": 47.00055, "lon": 1, "tst": 1710000170, "tid": "ph"})
        assert len(history_lines(data)) == before + 1
        print("ok the same place 120 s later is kept")

        shortcut = {
            "_type": "location",
            "lat": "46,5",
            "lon": "4.25",
            "acc": "12.5",
            "tst": "1720000000",
            "tid": "sc",
            "batt": "80%",
            "alt": "35",
            "vel": "0",
        }
        status, body = post("/pub", shortcut)
        assert status == 200 and body == [], (status, body)
        status, got = latest()
        assert got["lat"] == 46.5 and got["lon"] == 4.25
        assert got["acc_m"] == 12.5 and got["battery_pct"] == 80
        assert got["alt_m"] == 35 and got["speed_kmh"] == 0
        assert got["device"] == "sc" and got["ts"] == 1720000000
        print("ok shortcut strings, comma decimals and a percent are stored")

        status, body = post("/pub", {"_type": "location", "lat": "45", "lon": "5", "tst": 1720001000000, "tid": "sc"})
        assert status == 200 and body == []
        status, got = latest()
        assert got["ts"] == 1720001000 and got["lat"] == 45
        print("ok millisecond tst is scaled down")

        before_latest = latest()[1]
        started = int(time.time())
        status, body = post("/pub", {"_type": "location", "lat": 44, "lon": 6, "tid": "sc"})
        assert status == 200 and body == []
        status, got = latest()
        assert started <= got["ts"] <= int(time.time())
        assert got["lat"] == 44 and got["device"] == "sc"
        assert got["ts"] >= before_latest["ts"]
        print("ok a missing tst uses the server clock")

        fresh = got
        status, body = post("/pub", {"_type": "location", "lat": 200, "lon": 2, "tst": fresh["ts"] + 10})
        assert status == 400 and body == {"error": "bad location"}, (status, body)
        status, body = post("/pub", {"_type": "location", "lat": "nope", "lon": "2"})
        assert status == 400, body
        status, got = latest()
        assert got["ts"] == fresh["ts"] and got["lat"] == 44
        print("ok an unusable location is refused and not stored")

        status, body = post("/pub", "not json")
        assert status == 200 and body == []
        status, body = post("/pub", {"_type": "status", "tst": fresh["ts"] + 50})
        assert status == 200 and body == []
        status, got = latest()
        assert got["ts"] == fresh["ts"]
        print("ok non-json and non-location bodies stay a tolerant 200")

        status, body = post(
            "/pub",
            {"_type": "transition", "event": "enter", "desc": "Maison", "lat": "44,0", "lon": "6", "tst": "1710002000", "tid": "ph"},
        )
        assert status == 200 and body == []
        status, hist = client.json("GET", "/history?since=1710000000", read)
        assert status == 200, hist
        assert hist["since"] == 1710000000
        stamps = [point["ts"] for point in hist["points"]]
        assert stamps == sorted(stamps)
        assert 1690000000 not in stamps and 1700000000 not in stamps
        assert 1710000000 in stamps and 1720000000 in stamps and fresh["ts"] in stamps
        assert 1710000030 not in stamps
        regions = [item["region"] for item in hist["transitions"]]
        assert regions == ["Maison"], hist["transitions"]
        assert hist["transitions"][0]["event"] == "enter"
        assert hist["transitions"][0]["lat"] == 44
        status, later = client.json("GET", f"/history?since={fresh['ts'] + 1}", read)
        assert later["points"] == [] and later["transitions"] == []
        status, missing = client.json("GET", "/history", read)
        assert status == 400 and missing == {"error": "since required"}
        status, bad = client.json("GET", "/history?since=nope", read)
        assert status == 400 and bad == {"error": "bad since"}
        status, missing = client.json("GET", "/nope", read)
        assert status == 404
        status, slash = client.json("GET", "/latest/", read)
        assert status == 200 and slash["ts"] == fresh["ts"]
        print("ok history, transitions and query errors")

        view = loc.with_context({"lat": 44, "lon": 6, "ts": fresh["ts"], "acc_m": 12, "device": "sc"})
        assert view["source"] == "raccourci"
        assert view["age_s"] >= 0
        other = loc.with_context({"lat": 44, "lon": 6, "ts": fresh["ts"], "acc_m": 12, "device": "phone"})
        assert other["source"] == "owntracks"
        print("ok loc labels a shortcut fix")

        status, body = client.json("POST", "/request", read)
        assert status == 200 and body == {"ok": True}, (status, body)
        status, body = post("/pub", {"_type": "location", "lat": 43, "lon": 7, "tst": fresh["ts"] + 20, "tid": "ph"})
        assert status == 200 and body == [{"_type": "cmd", "action": "reportLocation"}], body
        status, got = latest()
        assert got["ts"] == fresh["ts"] + 20
        status, body = post("/pub", {"_type": "location", "lat": 42.5, "lon": 7.5, "tst": fresh["ts"] + 200, "tid": "ph"})
        assert status == 200 and body == []
        print("ok reportLocation is returned once on the next write")

        status, body = client.json("POST", "/request")
        assert status == 401, body
        status, body = post("/pub?u=owntracks&d=phone", b"", bearer_headers())
        assert status == 401
        status, body = client.json("POST", "/request", basic_headers())
        assert status == 200 and body == {"ok": True}
        status, resp = raw_post(port, "/pub", basic_headers(), receiver.MAX_BODY + 1)
        assert status == 413, status
        status, body = post("/pub", b"")
        assert body == [{"_type": "cmd", "action": "reportLocation"}], body
        status, body = post("/pub", b"")
        assert body == []
        print("ok a too-large write does not drop the queued command")

        status, body = client.json("POST", "/request", read)
        assert body == {"ok": True}
        status, body = post("/pub", {"_type": "location", "lat": 999, "lon": 0, "tst": fresh["ts"] + 400})
        assert status == 400 and body == {"error": "bad location"}, (status, body)
        status, got = latest()
        assert got["ts"] == fresh["ts"] + 200
        status, body = post("/pub", {"_type": "location", "lat": 41, "lon": 8, "tst": fresh["ts"] + 500, "tid": "ph"})
        assert body == [{"_type": "cmd", "action": "reportLocation"}], body
        print("ok a bad location does not consume the queued command")

        status, body = client.json("POST", "/request", read)
        assert body == {"ok": True}
        errors = io.StringIO()
        previous_err = sys.stderr
        sys.stderr = errors
        try:
            status, body = post("/pub", {"_type": "location", "lat": 999, "lon": 0, "tst": fresh["ts"] + 550})
        finally:
            sys.stderr = previous_err
        logged = errors.getvalue()
        assert "rejected location: coordinates missing or unusable" in logged, logged
        assert "999" not in logged and "password" not in logged and "Bearer" not in logged
        assert status == 400 and body == {"error": "bad location"}, (status, body)
        print("ok a rejection is logged without coordinates or credentials")

        status, body = client.json("POST", "/request", read)
        assert body == {"ok": True}
        status, body = post("/pub", b"{")
        assert body == [{"_type": "cmd", "action": "reportLocation"}]
        print("ok a queued command survives bad json and is then consumed")

        precise = {"_type": "location", "lat": 48.856613, "lon": 2.294481, "alt": 35.25, "tst": fresh["ts"] + 600, "tid": "sc"}
        status, body = post("/pub", precise)
        assert status == 200 and body == [], (status, body)
        status, got = latest()
        assert got["lat"] == 48.856613 and got["lon"] == 2.294481 and got["alt_m"] == 35.25
        print("ok a fractional JSON number keeps its fraction")

        status, body = post("/pub", {"_type": "location", "lat": "48.856613", "lon": "2.294481", "tst": fresh["ts"] + 700, "tid": "sc"})
        assert status == 200 and body == []
        status, got = latest()
        assert got["lat"] == float("48.856613") and got["lon"] == float("2.294481")
        print("ok a dotted coordinate string keeps its fraction")

        comma = b'{"_type":"location","lat":"48,856613","lon":"2,294481","alt":"35,25","tst":%d,"tid":"sc"}' % (fresh["ts"] + 800)
        sock = socket.create_connection(("127.0.0.1", port))
        try:
            send_chunked(sock, "/pub", basic_headers(), comma)
            status, raw, _head = read_response(sock)
            send_chunked(
                sock,
                "/pub",
                basic_headers(),
                b'{"_type":"location","lat":"41.25","lon":"8.5","tst":%d,"tid":"sc"}' % (fresh["ts"] + 900),
                close=True,
            )
            status2, raw2, _head2 = read_response(sock)
        finally:
            sock.close()
        assert status == 200 and json.loads(raw) == [], (status, raw)
        assert status2 == 200 and json.loads(raw2) == []
        status, got = latest()
        assert got["lat"] == 41.25 and got["ts"] == fresh["ts"] + 900
        assert any(point["lat"] == float("48.856613") and point["alt_m"] == 35.25 for point in history_lines(data))
        print("ok chunked bodies on one connection store string coordinates")

        form = f"lat=48%2C856700&lon=2.100001&alt=12.5&tst={fresh['ts'] + 1000}&tid=sc"
        status, body = post("/pub", form, {**basic_headers(), "Content-Type": "application/x-www-form-urlencoded; charset=utf-8"})
        assert status == 200 and body == [], (status, body)
        status, got = latest()
        assert got["lat"] == float("48.856700") and got["lon"] == 2.100001 and got["alt_m"] == 12.5
        print("ok a form body is accepted")

        query = f"/pub?lat=48.856800&lon=2%2C100002&tst={fresh['ts'] + 1100}&tid=sc"
        status, body = post(query, b"")
        assert status == 200 and body == [], (status, body)
        status, got = latest()
        assert got["lat"] == 48.856800 and got["lon"] == float("2.100002") and got["device"] == "sc"
        print("ok query-string coordinates on /pub are accepted")

        sock = socket.create_connection(("127.0.0.1", port))
        try:
            lines = [
                "POST /pub HTTP/1.1",
                "Host: 127.0.0.1",
                "Transfer-Encoding: chunked",
                "Connection: close",
            ]
            lines.extend(f"{key}: {value}" for key, value in basic_headers().items())
            sock.sendall(("\r\n".join(lines) + "\r\n\r\n10001\r\n").encode())
            status, raw, _head = read_response(sock)
        finally:
            sock.close()
        assert status == 413, status
        status, got = latest()
        assert got["ts"] == fresh["ts"] + 1100
        print("ok an oversized chunk is rejected")
    finally:
        httpd.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    main()
