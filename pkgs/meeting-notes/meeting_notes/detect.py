import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

INPUT_CLASS = "Stream/Input/Audio"
RECORDER_BINARIES = ("ffmpeg", "screenpipe")
LIVE_STATES = ("running", "idle")
BROWSERS = ("chrome", "chromium", "firefox")
MEET_PREFIX = "Meet - "
NATIVE_APPS = {
    "zoom": "Zoom",
    "whatsapp": "WhatsApp",
    "discord": "Discord",
    "teams": "Teams",
    "jitsi": "Jitsi",
}


class Stream(NamedTuple):
    pid: int | None
    binary: str
    app: str
    state: str


class Client(NamedTuple):
    address: str
    cls: str
    title: str
    pid: int | None
    at: tuple
    size: tuple
    stable_id: str = ""


class Candidate(NamedTuple):
    app: str
    title: str
    window: Client | None


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
        )
        for obj in objs or []
    ]


def _names(stream):
    return (Path(stream.binary).name.lower(), stream.app.lower())


def _is_recorder(stream):
    binary = Path(stream.binary).name.lower()
    return any(binary == name or binary.startswith(f".{name}") for name in RECORDER_BINARIES)


def _match_stream(stream, clients):
    names = _names(stream)
    if any("slack" in name for name in names):
        huddles = [
            c
            for c in clients
            if "Huddle" in c.title and (c.pid == stream.pid or "slack" in c.cls.lower())
        ]
        if not huddles:
            return None
        return Candidate("Slack", huddles[0].title, huddles[0])
    for key, label in NATIVE_APPS.items():
        if any(key in name for name in names):
            window = next((c for c in clients if c.pid == stream.pid), None)
            if window is None:
                window = next((c for c in clients if key in c.cls.lower()), None)
            return Candidate(label, window.title if window else label, window)
    if any(browser in name for name in names for browser in BROWSERS):
        meet = [c for c in clients if c.title.startswith(MEET_PREFIX)]
        if not meet:
            return None
        window = next((c for c in meet if c.pid == stream.pid), meet[0])
        return Candidate("Google Meet", window.title, window)
    return None


def match_call(streams, clients, ignore_pids=()):
    ignored = set(ignore_pids or ())
    for stream in streams:
        if stream.state not in LIVE_STATES:
            continue
        if _is_recorder(stream) or stream.pid in ignored:
            continue
        found = _match_stream(stream, clients)
        if found:
            return found
    return None


@dataclass
class Detector:
    poll: int = 5
    start_polls: int = 2
    end_grace: int = 20

    def __post_init__(self):
        self.active = None
        self.manual = False
        self.started_at = None
        self._streak = 0
        self._first_seen = None
        self._absent_since = None
        self._suppressed = False

    def _event(self, kind, at):
        app, title, window = self.active
        return Event(kind, app, title, window, at)

    def _close(self, at):
        event = self._event("end", at)
        self.active = None
        self.manual = False
        self.started_at = None
        self._streak = 0
        self._first_seen = None
        self._absent_since = None
        return [event]

    def feed(self, now, candidate):
        if self.manual:
            return []
        if self._suppressed:
            if candidate is None:
                self._suppressed = False
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
