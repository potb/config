import json
from datetime import timedelta
from pathlib import Path

from meeting_notes import pending, state

from .helpers import NOW, PipelineCase


def at(minutes):
    return NOW - timedelta(minutes=minutes)


class PendingTest(PipelineCase):
    def test_lists_finished_meetings_with_fields(self):
        mid = self.add(at(60), at(30), title="Review")
        items = pending.list_pending(self.cfg, NOW)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["id"], mid)
        self.assertEqual(item["minutes"], 30)
        self.assertEqual(
            sorted(item), ["app", "backend", "end", "id", "minutes", "start", "title"]
        )
        json.dumps(items)

    def test_open_meeting_excluded(self):
        self.add(at(60), None)
        self.assertEqual(pending.list_pending(self.cfg, NOW), [])

    def test_recent_end_excluded(self):
        self.add(at(40), NOW - timedelta(seconds=119))
        self.assertEqual(pending.list_pending(self.cfg, NOW), [])

    def test_end_exactly_120_seconds_included(self):
        self.add(at(40), NOW - timedelta(seconds=120))
        self.assertEqual(len(pending.list_pending(self.cfg, NOW)), 1)

    def test_short_meeting_marked_skipped_short(self):
        mid = self.add(at(10), at(7))
        self.assertEqual(pending.list_pending(self.cfg, NOW), [])
        self.assertEqual(self.load()["processed"][mid]["status"], state.SKIPPED_SHORT)

    def test_terminal_excluded(self):
        for status in sorted(state.TERMINAL):
            self.add(at(120), at(60), status=status)
        self.assertEqual(pending.list_pending(self.cfg, NOW), [])

    def test_resume_transcript(self):
        mid = self.add(
            at(120), at(60), status=state.NOTES_SAVED, dir="/m/x", sensitive=True
        )
        items = pending.list_pending(self.cfg, NOW)
        self.assertEqual(items[0]["id"], mid)
        self.assertEqual(items[0]["resume"], "transcript")
        self.assertEqual(items[0]["dir"], "/m/x")
        self.assertTrue(items[0]["sensitive"])

    def test_pipe_names_the_emitted_resume_value(self):
        self.add(at(120), at(60), status=state.NOTES_SAVED, dir="/m/x", sensitive="legal")
        item = pending.list_pending(self.cfg, NOW)[0]
        pipe = (Path(__file__).resolve().parents[1] / "pipe.md").read_text(encoding="utf-8")
        self.assertIn(f'"resume": "{item["resume"]}"', pipe)
        self.assertIs(item["sensitive"], True)
        self.assertIn('"sensitive": true', pipe)

    def test_notes_posted_resumes(self):
        self.add(at(120), at(60), status=state.NOTES_POSTED, dir="/m/y")
        self.assertEqual(pending.list_pending(self.cfg, NOW)[0]["resume"], "transcript")

    def test_sorted_by_start(self):
        late = self.add(at(50), at(20))
        early = self.add(at(120), at(90))
        self.assertEqual(
            [i["id"] for i in pending.list_pending(self.cfg, NOW)], [early, late]
        )

    def test_updates_last_run(self):
        pending.list_pending(self.cfg, NOW)
        self.assertEqual(self.load()["last_run"], state.iso(NOW))

    def test_idempotent(self):
        self.add(at(60), at(30))
        self.add(at(20), at(18))
        first = pending.list_pending(self.cfg, NOW)
        second = pending.list_pending(self.cfg, NOW)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)
