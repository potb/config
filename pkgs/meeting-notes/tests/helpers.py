import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from meeting_notes import state
from meeting_notes.config import Config

UTC = timezone.utc
NOW = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)


def make_cfg(root, **env):
    base = {
        "HOME": str(root),
        "MEETING_NOTES_DATA_DIR": str(Path(root) / "data"),
        "MEETING_NOTES_MEETINGS_DIR": str(Path(root) / "Meetings"),
    }
    base.update(env)
    return Config.from_env(base)


def parse_iso(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


class PipelineCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.cfg = make_cfg(self.root)

    def add(self, start, end, title="Sync", backend="native", **info):
        with state.locked(self.cfg.state_path) as st:
            mid = state.start_meeting(st, backend, "zoom", title, start, "test")
            if end is not None:
                state.end_meeting(st, mid, end)
            if info:
                state.set_processed(st, mid, **info)
        return mid

    def load(self):
        return state.load(self.cfg.state_path)
