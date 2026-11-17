import datetime as dt
import json
import os
import secrets
import urllib.request
from urllib.parse import urlencode, urlsplit

SCREEN_CHAR_BUDGET = 12000
NO_SCREEN_TEXT = "(no screen text captured for the call window)\n"
CALL_KEYWORDS = ("Meet", "Zoom", "Teams", "Huddle", "Slack", "Webex", "Whereby")
TIMEOUT = 10


def ensure_key(cfg):
    path = cfg.key_path
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(32)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(key + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError:
            return path.read_text().strip()
    finally:
        os.unlink(tmp)
    return key


def default_opener(request):
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def local_hms(stamp):
    moment = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()
    return moment.strftime("%H:%M:%S")


class Client:
    def __init__(self, cfg, opener=default_opener):
        self._base = cfg.screenpipe_url.rstrip("/")
        self._key = ensure_key(cfg)
        self._opener = opener

    def __repr__(self):
        return f"Client(base={self._base!r})"

    def _request(self, method, path, body=None, params=None):
        url = self._base + path
        if params:
            url += "?" + urlencode(params)
        data = None
        headers = {
            "Authorization": f"Bearer {self._key}",
            "X-Screenpipe-Client": "api",
        }
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        raw = self._opener(request)
        if not raw:
            return None
        return json.loads(raw)

    def status(self):
        return self._request("GET", "/meetings/status")

    def meeting(self, meeting_id):
        return self._request("GET", f"/meetings/{meeting_id}")

    def start_meeting(self, app, title):
        return self._request("POST", "/meetings/start", body={"app": app, "title": title})

    def stop_meeting(self):
        return self._request("POST", "/meetings/stop")

    def audio_start(self):
        return self._request("POST", "/audio/start")

    def audio_stop(self):
        return self._request("POST", "/audio/stop")

    def health(self):
        return self._request("GET", "/health")

    def _filters(self, app):
        if not app:
            return []
        filters = [{"app_name": app}, {"window_name": app}]
        for keyword in CALL_KEYWORDS:
            if keyword.lower() in app.lower():
                filters.append({"window_name": keyword})
        return filters

    def search_screen(self, start, end, app):
        window = {"start_time": start, "end_time": end, "limit": 15, "max_content_length": 1500}
        seen = set()
        blocks = []
        used = 0
        full = False
        for flt in self._filters(app):
            for content_type in ("accessibility", "ocr"):
                try:
                    result = self._request("GET", "/search", params={**window, **flt, "content_type": content_type})
                except (OSError, ValueError):
                    continue
                for item in (result or {}).get("data", []):
                    content = item.get("content", {})
                    text = (content.get("text") or "").strip()
                    key = text[:200]
                    if not text or key in seen:
                        continue
                    seen.add(key)
                    block = (
                        f"--- {content.get('app_name')} / {content.get('window_name')}"
                        f" @ {local_hms(content['timestamp'])}\n{text}\n"
                    )
                    if used + len(block) > SCREEN_CHAR_BUDGET:
                        full = True
                        break
                    blocks.append(block)
                    used += len(block)
                if full:
                    break
            if blocks:
                break
        return "".join(blocks) or NO_SCREEN_TEXT


def server_argv(cfg):
    port = urlsplit(cfg.screenpipe_url).port
    return [cfg.screenpipe, "record", "--port", str(port), "--disable-telemetry", "-a", "disabled"]


def exec_server(cfg):
    env = dict(os.environ, SCREENPIPE_API_KEY=ensure_key(cfg))
    argv = server_argv(cfg)
    os.execvpe(argv[0], argv, env)
