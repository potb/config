import io
import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from meeting_notes import screenpipe
from meeting_notes.backend_screenpipe import Event, ScreenpipeBackend
from meeting_notes.config import Config

FIXTURES = Path(__file__).parent / "fixtures" / "screenpipe"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


class FakeClient:
    def __init__(self, statuses, meetings=None):
        self.statuses = list(statuses)
        self.meetings = meetings or {}
        self.calls = []

    def status(self):
        self.calls.append("status")
        answer = self.statuses.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def meeting(self, meeting_id):
        self.calls.append(("meeting", meeting_id))
        answer = self.meetings[meeting_id]
        if isinstance(answer, list):
            return answer.pop(0)
        return answer

    def audio_start(self):
        self.calls.append("audio_start")

    def audio_stop(self):
        self.calls.append("audio_stop")

    def start_meeting(self, app, title):
        self.calls.append(("start_meeting", app, title))

    def stop_meeting(self):
        self.calls.append("stop_meeting")

    def audio_calls(self):
        return [c for c in self.calls if c in ("audio_start", "audio_stop")]


NOW = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)


def make_backend(client):
    cfg = Config.from_env({"HOME": "/nonexistent-home"})
    return ScreenpipeBackend(cfg, client, lambda: NOW)


class SequenceTest(unittest.TestCase):
    def test_inactive_active_inactive_gives_start_then_end(self):
        client = FakeClient(
            [fixture("status_inactive.json"), fixture("status_active.json"), fixture("status_inactive.json")],
            {7: [fixture("meeting_7_open.json"), fixture("meeting_7_closed.json")]},
        )
        backend = make_backend(client)
        self.assertEqual(backend.poll(NOW), [])
        self.assertFalse(backend.active())
        started = backend.poll(NOW)
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0].kind, "start")
        self.assertEqual(started[0].screenpipe_id, 7)
        self.assertEqual(started[0].app, "Google Meet")
        self.assertEqual(started[0].title, "Weekly sync")
        self.assertEqual(started[0].start, "2026-11-17T09:00:00Z")
        self.assertTrue(backend.active())
        ended = backend.poll(NOW)
        self.assertEqual(len(ended), 1)
        self.assertEqual(ended[0].kind, "end")
        self.assertEqual(ended[0].screenpipe_id, 7)
        self.assertEqual(ended[0].start, "2026-11-17T09:00:00Z")
        self.assertEqual(ended[0].end, "2026-11-17T09:42:00Z")
        self.assertFalse(backend.active())
        self.assertEqual(client.audio_calls(), ["audio_stop", "audio_start", "audio_stop"])

    def test_steady_active_emits_nothing(self):
        client = FakeClient(
            [fixture("status_active.json")] * 3,
            {7: fixture("meeting_7_open.json")},
        )
        backend = make_backend(client)
        self.assertEqual(len(backend.poll(NOW)), 1)
        self.assertEqual(backend.poll(NOW), [])
        self.assertEqual(backend.poll(NOW), [])
        self.assertEqual(client.audio_calls(), ["audio_start"])

    def test_audio_stop_on_first_poll_only_when_inactive(self):
        client = FakeClient([fixture("status_inactive.json")] * 3)
        backend = make_backend(client)
        for _ in range(3):
            backend.poll(NOW)
        self.assertEqual(client.audio_calls(), ["audio_stop"])

    def test_first_poll_active_does_not_audio_stop(self):
        client = FakeClient([fixture("status_active.json")], {7: fixture("meeting_7_open.json")})
        backend = make_backend(client)
        backend.poll(NOW)
        self.assertEqual(client.audio_calls(), ["audio_start"])

    def test_end_falls_back_to_clock_when_meeting_has_no_end(self):
        client = FakeClient(
            [fixture("status_active.json"), fixture("status_inactive.json")],
            {7: fixture("meeting_7_open.json")},
        )
        backend = make_backend(client)
        backend.poll(NOW)
        ended = backend.poll(NOW)
        self.assertEqual(ended[0].end, "2026-11-17T09:00:00Z")

    def test_switch_between_meetings_ends_old_and_starts_new(self):
        second = dict(fixture("status_active.json"), activeMeetingId=8)
        client = FakeClient(
            [fixture("status_active.json"), second],
            {
                7: [fixture("meeting_7_open.json"), fixture("meeting_7_closed.json")],
                8: dict(fixture("meeting_7_open.json"), id=8, title="Other"),
            },
        )
        backend = make_backend(client)
        backend.poll(NOW)
        events = backend.poll(NOW)
        self.assertEqual([(e.kind, e.screenpipe_id) for e in events], [("end", 7), ("start", 8)])


class FailureTest(unittest.TestCase):
    def test_network_error_gives_no_event_and_no_crash(self):
        client = FakeClient([urllib.error.URLError("refused")])
        backend = make_backend(client)
        with self.assertLogs("meeting_notes", level="WARNING"):
            self.assertEqual(backend.poll(NOW), [])

    def test_unauthorized_gives_no_event_and_no_crash(self):
        error = urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, io.BytesIO(b""))
        client = FakeClient([error])
        backend = make_backend(client)
        with self.assertLogs("meeting_notes", level="WARNING"):
            self.assertEqual(backend.poll(NOW), [])

    def test_failure_mid_meeting_keeps_state(self):
        client = FakeClient(
            [fixture("status_active.json"), urllib.error.URLError("down"), fixture("status_inactive.json")],
            {7: [fixture("meeting_7_open.json"), fixture("meeting_7_closed.json")]},
        )
        backend = make_backend(client)
        backend.poll(NOW)
        with self.assertLogs("meeting_notes", level="WARNING"):
            self.assertEqual(backend.poll(NOW), [])
        self.assertTrue(backend.active())
        self.assertEqual(backend.poll(NOW)[0].kind, "end")

    def test_invalid_json_gives_no_event(self):
        client = FakeClient([ValueError("bad json")])
        backend = make_backend(client)
        with self.assertLogs("meeting_notes", level="WARNING"):
            self.assertEqual(backend.poll(NOW), [])


class ManualTest(unittest.TestCase):
    def test_manual_start_and_stop_call_client(self):
        client = FakeClient([])
        backend = make_backend(client)
        backend.manual_start("Zoom", "Review")
        backend.manual_stop()
        self.assertEqual(client.calls, [("start_meeting", "Zoom", "Review"), "stop_meeting"])

    def test_close_stops_audio_when_active(self):
        client = FakeClient([fixture("status_active.json")], {7: fixture("meeting_7_open.json")})
        backend = make_backend(client)
        backend.poll(NOW)
        backend.close()
        self.assertEqual(client.audio_calls(), ["audio_start", "audio_stop"])

    def test_close_without_meeting_does_nothing(self):
        client = FakeClient([])
        backend = make_backend(client)
        backend.close()
        self.assertEqual(client.calls, [])


class IntegrationWithClientTest(unittest.TestCase):
    def test_backend_over_real_client_with_mock_opener(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cfg = Config.from_env({"HOME": tmp.name})
        key = screenpipe.ensure_key(cfg)
        bodies = {
            ("GET", "/meetings/status"): [
                (FIXTURES / "status_active.json").read_bytes(),
                (FIXTURES / "status_inactive.json").read_bytes(),
            ],
            ("GET", "/meetings/7"): [(FIXTURES / "meeting_7_open.json").read_bytes(), (FIXTURES / "meeting_7_closed.json").read_bytes()],
            ("POST", "/audio/start"): [b"{}"],
            ("POST", "/audio/stop"): [b"{}"],
        }
        seen = []

        def opener(request):
            seen.append(request)
            return bodies[(request.get_method(), "/" + request.full_url.split("/", 3)[3])].pop(0)

        backend = ScreenpipeBackend(cfg, screenpipe.Client(cfg, opener), lambda: NOW)
        kinds = [e.kind for e in backend.poll(NOW) + backend.poll(NOW)]
        self.assertEqual(kinds, ["start", "end"])
        for request in seen:
            self.assertEqual(request.get_header("Authorization"), f"Bearer {key}")
        self.assertIsInstance(Event("start", 1, "a", "t", None, None), Event)


if __name__ == "__main__":
    unittest.main()
