import logging
from dataclasses import dataclass

from meeting_notes.state import iso

log = logging.getLogger("meeting_notes.screenpipe")

START = "start"
END = "end"


@dataclass(frozen=True)
class Event:
    kind: str
    screenpipe_id: int
    app: str | None
    title: str | None
    start: str | None
    end: str | None


class ScreenpipeBackend:
    name = "screenpipe"

    def __init__(self, cfg, client, clock):
        self.cfg = cfg
        self.client = client
        self.clock = clock
        self._current = None
        self._seen_first = False

    def active(self):
        return self._current is not None

    def manual_start(self, app, title):
        self.client.start_meeting(app, title)

    def manual_stop(self):
        self.client.stop_meeting()

    def close(self):
        if self._current is not None:
            self._audio("audio_stop")
            self._current = None

    def poll(self, now):
        try:
            status = self.client.status() or {}
        except (OSError, ValueError) as error:
            log.warning("screenpipe status failed: %s", error)
            return []
        active_id = status.get("activeMeetingId") if status.get("active") else None
        first = not self._seen_first
        self._seen_first = True
        if active_id is None and first:
            self._audio("audio_stop")
        events = []
        if self._current is not None and active_id != self._current["id"]:
            events.append(self._end(now))
        if active_id is not None and self._current is None:
            events.append(self._begin(active_id, status.get("meetingApp")))
        return events

    def _audio(self, name):
        try:
            getattr(self.client, name)()
        except (OSError, ValueError) as error:
            log.warning("screenpipe %s failed: %s", name, error)

    def _meeting(self, meeting_id):
        try:
            return self.client.meeting(meeting_id) or {}
        except (OSError, ValueError) as error:
            log.warning("screenpipe meeting %s failed: %s", meeting_id, error)
            return {}

    def _begin(self, meeting_id, status_app):
        meeting = self._meeting(meeting_id)
        self._audio("audio_start")
        app = meeting.get("meeting_app") or status_app
        start = meeting.get("meeting_start") or iso(self.clock())
        self._current = {"id": meeting_id, "app": app, "title": meeting.get("title"), "start": start}
        return Event(START, meeting_id, app, meeting.get("title"), start, None)

    def _end(self, now):
        current = self._current
        meeting = self._meeting(current["id"])
        self._audio("audio_stop")
        self._current = None
        end = meeting.get("meeting_end") or iso(self.clock())
        return Event(
            END,
            current["id"],
            meeting.get("meeting_app") or current["app"],
            meeting.get("title") or current["title"],
            meeting.get("meeting_start") or current["start"],
            end,
        )
