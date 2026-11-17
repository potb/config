import json
import multiprocessing
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from meeting_notes import state

UTC = timezone.utc


def bump(path, n):
    for _ in range(n):
        with state.locked(Path(path)) as st:
            st["counter"] = st.get("counter", 0) + 1


class StateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state.json"

    def test_load_default(self):
        st = state.load(self.path)
        self.assertEqual(
            st, {"version": 1, "meetings": {}, "processed": {}, "last_run": None}
        )

    def test_migrate_unversioned(self):
        self.path.write_text(json.dumps({"meetings": {"a": {"id": "a"}}}))
        st = state.load(self.path)
        self.assertEqual(st["version"], 1)
        self.assertEqual(st["processed"], {})
        self.assertIsNone(st["last_run"])
        self.assertIn("a", st["meetings"])

    def test_save_atomic(self):
        st = state.load(self.path)
        state.save(self.path, st)
        self.assertEqual(sorted(os.listdir(self.tmp.name)), ["state.json"])
        self.assertEqual(state.load(self.path), st)

    def test_meeting_id(self):
        t = datetime(2026, 10, 29, 14, 3, 7, tzinfo=UTC)
        self.assertEqual(state.meeting_id(t), "20261029-140307")

    def test_start_end_active(self):
        st = state.load(self.path)
        t = datetime(2026, 10, 29, 14, 3, 7, tzinfo=UTC)
        mid = state.start_meeting(
            st, "native", "zoom", "Sync", t, "auto", screenpipe_id=4
        )
        m = st["meetings"][mid]
        self.assertEqual(m["start"], "2026-10-29T14:03:07Z")
        self.assertIsNone(m["end"])
        self.assertEqual(m["source"], "auto")
        self.assertEqual(m["screenpipe_id"], 4)
        self.assertEqual(m["live"], "off")
        self.assertEqual(state.active_meeting(st)["id"], mid)
        state.end_meeting(st, mid, datetime(2026, 10, 29, 14, 30, tzinfo=UTC))
        self.assertEqual(st["meetings"][mid]["end"], "2026-10-29T14:30:00Z")
        self.assertIsNone(state.active_meeting(st))

    def test_collision(self):
        st = state.load(self.path)
        t = datetime(2026, 10, 29, 14, 3, 7, tzinfo=UTC)
        ids = [
            state.start_meeting(st, "native", "a", "t", t, "manual")
            for _ in range(3)
        ]
        self.assertEqual(
            ids, ["20261029-140307", "20261029-140307-2", "20261029-140307-3"]
        )

    def test_processed(self):
        st = state.load(self.path)
        self.assertIsNone(state.processed(st, "x"))
        state.set_processed(st, "x", status="done", dir="/d")
        p = state.processed(st, "x")
        self.assertEqual(p["status"], "done")
        self.assertTrue(p["at"].endswith("Z"))
        self.assertIn("done", state.TERMINAL)
        self.assertNotIn("notes_saved", state.TERMINAL)
        self.assertEqual(state.RESUME_TRANSCRIPT, {"notes_saved", "notes_posted"})

    def test_locked_saves(self):
        with state.locked(self.path) as st:
            st["last_run"] = "2026-10-29T00:00:00Z"
        self.assertEqual(state.load(self.path)["last_run"], "2026-10-29T00:00:00Z")
        self.assertTrue(Path(str(self.path) + ".lock").exists())

    def test_locked_concurrency(self):
        procs = [
            multiprocessing.Process(target=bump, args=(str(self.path), 25))
            for _ in range(2)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join()
            self.assertEqual(p.exitcode, 0)
        self.assertEqual(state.load(self.path)["counter"], 50)


if __name__ == "__main__":
    unittest.main()
