from datetime import datetime, timezone

from . import detect, state
from .recorder import Recorder, screenshot

CAPTURE_SECONDS = 300


def _utcnow():
    return datetime.now(timezone.utc)


class NativeBackend:
    name = "native"

    def __init__(self, cfg, run=detect.run, clock=_utcnow, recorder=None, detector=None, environ=None):
        self.cfg = cfg
        self.run = run
        self.clock = clock
        self.environ = environ
        self.recorder = recorder if recorder is not None else Recorder(cfg, run=run)
        self.detector = detector if detector is not None else detect.Detector()
        self.window = None
        self.meeting_id = None
        self.last_capture = None

    def _capture(self, now):
        if self.window is None or self.meeting_id is None:
            return
        if screenshot(self.cfg, self.meeting_id, self.window, self.run, now) is not None:
            self.last_capture = now

    def _handle(self, events, now):
        for event in events:
            if event.kind == "start":
                self.recorder.start()
                self.window = event.window
                self.meeting_id = state.meeting_id(event.at)
                self.last_capture = None
                self._capture(now)
            elif event.kind == "end":
                self.recorder.stop()
                self.window = None
                self.meeting_id = None
                self.last_capture = None
        return events

    def _refresh_window(self, clients):
        if self.window is None:
            return
        self.window = next((c for c in clients if c.address == self.window.address), None)

    def _due(self, now):
        if self.last_capture is None:
            return True
        return (now - self.last_capture).total_seconds() >= CAPTURE_SECONDS

    def poll(self, now=None):
        now = now or self.clock()
        snap = detect.snapshot(self.run, self.environ)
        if snap is None:
            return []
        streams, clients = snap
        candidate = detect.match_call(streams, clients, self.recorder.pids())
        events = self._handle(self.detector.feed(now, candidate), now)
        if self.detector.active is not None and not events:
            self._refresh_window(clients)
            if self._due(now):
                self._capture(now)
        return events

    def manual_start(self, app, title):
        now = self.clock()
        return self._handle(self.detector.force_start(app, title, now), now)

    def manual_stop(self):
        now = self.clock()
        return self._handle(self.detector.force_stop(now), now)

    def active(self):
        if self.detector.active is None:
            return None
        app, title, window = self.detector.active
        return {"app": app, "title": title, "window": window, "started_at": self.detector.started_at}

    def close(self):
        self.recorder.stop()
