import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

INPUT_CLASS = "Stream/Input/Audio"
RECORDER_BINARIES = (
    "ffmpeg",
    "screenpipe",
    "pw-record",
    "pw-cat",
    "parecord",
    "parec",
    "arecord",
    "rec",
    "sox",
    "whisper",
    "meeting-notes",
)
RECORDER_PREFIXES = ("whisper", ".whisper", ".meeting-notes")
LIVE_STATES = ("running", "idle")
GENERIC_STATES = ("running",)
BROWSERS = ("chrome", "chromium", "firefox")
BROWSER_LABELS = {"chrome": "Google Chrome", "chromium": "Chromium", "firefox": "Firefox"}
BROWSER_SUFFIX = re.compile(
    r"\s+[-–—]\s+(Google Chrome|Chromium|Mozilla Firefox|Firefox)$", re.I
)
MEET_PREFIX = "Meet - "
MAX_ANCESTORS = 8
NATIVE_APPS = {
    "zoom": "Zoom",
    "whatsapp": "WhatsApp",
    "discord": "Discord",
    "teams": "Teams",
    "jitsi": "Jitsi",
}
WEB_APPS = (
    ("WhatsApp", re.compile(r"^(\(\d+\)\s*)?WhatsApp", re.I)),
    ("Teams", re.compile(r"\|\s*Microsoft Teams", re.I)),
    ("Zoom", re.compile(r"^(Zoom Meeting|Zoom Workplace)$|^app\.zoom\.us", re.I)),
    ("Discord", re.compile(r"^Discord\b|-\s*Discord$", re.I)),
    ("Jitsi", re.compile(r"(^|[|-]\s*)Jitsi Meet$", re.I)),
    ("Whereby", re.compile(r"(^|[|-]\s*)Whereby$", re.I)),
    ("Webex", re.compile(r"(^|[|-]\s*)(Cisco\s+)?Webex(\s+Meetings?)?$", re.I)),
)
NO_FOCUS = sys.maxsize


class Stream(NamedTuple):
    pid: int | None
    binary: str
    app: str
    state: str
    monitor: bool = False
    passive: bool = False


class Client(NamedTuple):
    address: str
    cls: str
    title: str
    pid: int | None
    at: tuple
    size: tuple
    stable_id: str = ""
    focus: int = -1


class Candidate(NamedTuple):
    app: str
    title: str
    window: Client | None
    generic: bool = False


class Event(NamedTuple):
    kind: str
    app: str
    title: str
    window: Client | None
    at: object


def run(argv, env=None):
    return subprocess.run(
        argv, check=True, capture_output=True, text=True, timeout=10, env=env
    ).stdout


def _pid(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _flag(raw):
    if isinstance(raw, str):
        return raw.strip().lower() in ("true", "1", "yes")
    return bool(raw)


def _focus(raw):
    value = _pid(raw)
    return -1 if value is None else value


def read_ppid(pid, proc="/proc"):
    try:
        text = (Path(proc) / str(pid) / "stat").read_text()
        return int(text.rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return None


def lineage(pid, ppid=read_ppid, depth=MAX_ANCESTORS):
    if pid is None:
        return ()
    chain = [pid]
    for _ in range(depth):
        parent = ppid(chain[-1])
        if not parent or parent <= 1 or parent in chain:
            break
        chain.append(parent)
    return tuple(chain)


def parse_pw_dump(objs):
    streams = []
    for obj in objs or []:
        info = obj.get("info") or {}
        props = info.get("props") or {}
        if props.get("media.class") != INPUT_CLASS:
            continue
        streams.append(
            Stream(
                _pid(props.get("application.process.id")),
                props.get("application.process.binary") or "",
                props.get("application.name") or "",
                info.get("state") or "",
                _flag(props.get("stream.capture.sink")),
                _flag(props.get("node.passive")),
            )
        )
    return streams


def parse_clients(objs):
    return [
        Client(
            obj.get("address") or "",
            obj.get("class") or "",
            obj.get("title") or "",
            _pid(obj.get("pid")),
            tuple(obj.get("at") or (0, 0)),
            tuple(obj.get("size") or (0, 0)),
            str(obj.get("stableId") or ""),
            _focus(obj.get("focusHistoryID")),
        )
        for obj in objs or []
    ]


def _names(stream):
    return (Path(stream.binary).name.lower(), stream.app.lower())


def _is_recorder(stream):
    for name in _names(stream):
        if not name:
            continue
        if name in RECORDER_BINARIES or name.startswith(RECORDER_PREFIXES):
            return True
        if any(name.startswith(f".{binary}") for binary in RECORDER_BINARIES):
            return True
    return False


def _focus_rank(client):
    return client.focus if client.focus >= 0 else NO_FOCUS


def _stream_windows(clients, chain):
    own = [c for c in clients if c.pid is not None and c.pid in chain]
    return sorted(own, key=lambda c: (chain.index(c.pid), _focus_rank(c)))


def _is_ignored(stream, clients, chain, ignore_apps):
    needles = [item.strip().lower() for item in ignore_apps or () if item and item.strip()]
    if not needles:
        return False
    haystack = [*_names(stream), *(c.cls.lower() for c in _stream_windows(clients, chain))]
    return any(needle in text for needle in needles for text in haystack if text)


def _browser_key(stream):
    names = _names(stream)
    return next((b for b in BROWSERS if any(b in name for name in names)), None)


def _browser_windows(stream, clients, chain):
    key = _browser_key(stream)
    own = [c for c in _stream_windows(clients, chain) if key in c.cls.lower()]
    others = sorted(
        (c for c in clients if key in c.cls.lower() and c not in own), key=_focus_rank
    )
    return own + others


def _page_title(title):
    return BROWSER_SUFFIX.sub("", title.strip())


def _is_slack(stream):
    return any("slack" in name for name in _names(stream))


def _match_specific(stream, clients, chain):
    names = _names(stream)
    own = _stream_windows(clients, chain)
    if _is_slack(stream):
        huddles = [
            c
            for c in clients
            if "Huddle" in c.title and (c in own or "slack" in c.cls.lower())
        ]
        if not huddles:
            return None
        return Candidate("Slack", huddles[0].title, huddles[0])
    for key, label in NATIVE_APPS.items():
        if any(key in name for name in names):
            window = own[0] if own else None
            if window is None:
                window = next((c for c in clients if key in c.cls.lower()), None)
            return Candidate(label, window.title if window else label, window)
    if _browser_key(stream):
        meet = [c for c in clients if c.title.startswith(MEET_PREFIX)]
        if not meet:
            return None
        window = next((c for c in own if c in meet), None)
        if window is None:
            window = sorted(meet, key=_focus_rank)[0]
        return Candidate("Google Meet", window.title, window)
    return None


def _match_web_app(stream, clients, chain):
    if stream.state not in GENERIC_STATES or not _browser_key(stream):
        return None
    for window in _browser_windows(stream, clients, chain):
        page = _page_title(window.title)
        for label, pattern in WEB_APPS:
            if pattern.search(page):
                return Candidate(label, window.title, window)
    return None


def _match_generic(stream, clients, chain):
    if stream.state not in GENERIC_STATES or _is_slack(stream):
        return None
    key = _browser_key(stream)
    if key:
        label = BROWSER_LABELS[key]
        windows = _browser_windows(stream, clients, chain)
        window = windows[0] if windows else None
        return Candidate(label, (window.title if window else "") or label, window, True)
    windows = _stream_windows(clients, chain)
    window = windows[0] if windows else None
    app = (window.cls if window else "") or stream.app or Path(stream.binary).name
    if not app:
        return None
    return Candidate(app, (window.title if window else "") or app, window, True)


def match_call(streams, clients, ignore_pids=(), ignore_apps=(), ppid=read_ppid):
    ignored = set(ignore_pids or ())
    eligible = []
    for stream in streams:
        if stream.monitor or stream.passive or stream.state not in LIVE_STATES:
            continue
        if _is_recorder(stream) or stream.pid in ignored:
            continue
        chain = lineage(stream.pid, ppid)
        if _is_ignored(stream, clients, chain, ignore_apps):
            continue
        eligible.append((stream, chain))
    for rule in (_match_specific, _match_web_app, _match_generic):
        for stream, chain in eligible:
            found = rule(stream, clients, chain)
            if found:
                return found
    return None


@dataclass
class Detector:
    poll: int = 5
    start_polls: int = 2
    end_grace: int = 20
    max_generic: int = 14400

    def __post_init__(self):
        self.active = None
        self.manual = False
        self.started_at = None
        self._generic = False
        self._streak = 0
        self._first_seen = None
        self._absent_since = None
        self._suppressed = False
        self._capped = False

    def _event(self, kind, at):
        app, title, window = self.active
        return Event(kind, app, title, window, at)

    def _close(self, at):
        event = self._event("end", at)
        self.active = None
        self.manual = False
        self.started_at = None
        self._generic = False
        self._streak = 0
        self._first_seen = None
        self._absent_since = None
        return [event]

    def _over_cap(self, now):
        if self.active is None or not self._generic:
            return False
        return (now - self.started_at).total_seconds() >= self.max_generic

    def feed(self, now, candidate):
        if self.manual:
            return []
        if self._suppressed:
            if candidate is None:
                self._suppressed = False
            return []
        if self._over_cap(now):
            self._capped = True
            return self._close(now)
        if self._capped:
            if candidate is None:
                self._capped = False
            elif candidate.generic:
                return []
        if self.active is None:
            if candidate is None:
                self._streak = 0
                self._first_seen = None
                return []
            self._streak += 1
            if self._first_seen is None:
                self._first_seen = now
            if self._streak < self.start_polls:
                return []
            self.active = (candidate.app, candidate.title, candidate.window)
            self._generic = candidate.generic
            self._capped = False
            self.started_at = self._first_seen
            self._absent_since = None
            return [self._event("start", self.started_at)]
        if candidate is not None:
            self._absent_since = None
            return []
        if self._absent_since is None:
            self._absent_since = now
        if (now - self._absent_since).total_seconds() >= self.end_grace:
            return self._close(self._absent_since)
        return []

    def force_start(self, app, title, now):
        if self.active is not None:
            self.manual = True
            return []
        self.active = (app, title, None)
        self._generic = False
        self.manual = True
        self.started_at = now
        self._absent_since = None
        return [self._event("start", now)]

    def force_stop(self, now):
        if self.active is None:
            return []
        self._suppressed = True
        return self._close(now)


def _hyprland_env(environ):
    env = dict(environ)
    if env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return env
    runtime = env.get("XDG_RUNTIME_DIR")
    if not runtime:
        return None
    root = Path(runtime) / "hypr"
    try:
        instances = [entry for entry in root.iterdir() if entry.is_dir()]
    except OSError:
        return None
    if not instances:
        return None
    newest = max(instances, key=lambda entry: entry.stat().st_mtime)
    env["HYPRLAND_INSTANCE_SIGNATURE"] = newest.name
    return env


def snapshot(run=run, environ=None):
    environ = os.environ if environ is None else environ
    try:
        streams = parse_pw_dump(json.loads(run(["pw-dump"])))
        env = _hyprland_env(environ)
        if env is None:
            return None
        clients = parse_clients(json.loads(run(["hyprctl", "clients", "-j"], env=env)))
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError, TypeError):
        return None
    return streams, clients
