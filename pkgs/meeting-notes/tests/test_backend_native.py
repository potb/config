import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from meeting_notes.backend_native import NativeBackend
from meeting_notes.config import Config

UTC = timezone.utc
FIXTURES = Path(__file__).parent / "fixtures" / "native"
T0 = datetime(2026, 11, 17, 9, 0, 0, tzinfo=UTC)
ENV = {"HYPRLAND_INSTANCE_SIGNATURE": "sig"}


def NO_PARENT(pid):
    return None


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def at(seconds):
    return T0 + timedelta(seconds=seconds)


class FakeRecorder:
    def __init__(self):
        self.running = False
        self.starts = 0
        self.stops = 0

    def start(self):
        self.running = True
        self.starts += 1

    def stop(self):
        self.running = False
        self.stops += 1

    def alive(self):
        return self.running

    def pids(self):
        return [7100] if self.running else []


class World:
    def __init__(self):
        self.scene = "idle"
        self.broken = False
        self.grims = []

    def __call__(self, argv, env=None):
        if self.broken and argv[0] != "grim":
            raise subprocess.CalledProcessError(1, argv)
        if argv[0] == "grim":
            self.grims.append(argv)
            return ""
        data = fixture(self.scene)
        if argv[0] == "pw-dump":
            return json.dumps(data["pw_dump"])
        return json.dumps(data["clients"])


class NativeBackendTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config.from_env({"HOME": self.tmp.name})
        self.world = World()
        self.recorder = FakeRecorder()
        self.now = T0
        self.backend = NativeBackend(
            self.cfg,
            run=self.world,
            clock=lambda: self.now,
            recorder=self.recorder,
            environ=ENV,
            ppid=NO_PARENT,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def step(self, second, scene):
        self.world.scene = scene
        self.now = at(second)
        return self.backend.poll(self.now)

    def test_meet_lifecycle_drives_recorder_and_captures(self):
        self.assertEqual(self.step(0, "meet"), [])
        self.assertIsNone(self.backend.active())
        events = self.step(5, "meet")
        self.assertEqual([e.kind for e in events], ["start"])
        self.assertEqual(self.recorder.starts, 1)
        active = self.backend.active()
        self.assertEqual(active["app"], "Google Meet")
        self.assertEqual(active["title"], "Meet - abc-defg-hij - Google Chrome")
        self.assertEqual(active["window"].address, "0x5600b7")
        self.assertEqual(active["started_at"], at(0))
        screens = self.cfg.screens_dir("20261117-090000")
        self.assertEqual(
            self.world.grims,
            [["grim", "-T", "180000b7", str(screens / "2026-11-17_09-00-05.png")]],
        )
        for second in range(10, 305, 5):
            self.step(second, "meet")
        self.assertEqual(len(self.world.grims), 1)
        self.step(305, "meet")
        self.assertEqual(len(self.world.grims), 2)
        self.assertTrue(self.world.grims[1][-1].endswith("2026-11-17_09-05-05.png"))
        ended = []
        for second in range(310, 335, 5):
            ended += self.step(second, "idle")
        self.assertEqual([(e.kind, e.at) for e in ended], [("end", at(310))])
        self.assertEqual(self.recorder.stops, 1)
        self.assertIsNone(self.backend.active())
        self.assertFalse(self.cfg.state_path.exists())

    def test_no_capture_when_window_is_gone(self):
        self.step(0, "meet")
        self.step(5, "meet")
        self.assertEqual(len(self.world.grims), 1)
        for second in range(10, 320, 5):
            self.step(second, "zoom")
        self.assertEqual(len(self.world.grims), 1)

    def test_ignore_apps_config_reaches_detection(self):
        cfg = Config.from_env({"HOME": self.tmp.name, "MEETING_NOTES_IGNORE_APPS": "chrome"})
        backend = NativeBackend(
            cfg,
            run=self.world,
            clock=lambda: self.now,
            recorder=self.recorder,
            environ=ENV,
            ppid=NO_PARENT,
        )
        self.world.scene = "chrome_no_meet"
        for second in (0, 5, 10):
            self.now = at(second)
            self.assertEqual(backend.poll(self.now), [])
        self.assertIsNone(backend.active())
        self.assertEqual(self.recorder.starts, 0)

    def test_generic_meeting_ends_after_four_hours_and_stays_off_until_stream_stops(self):
        self.step(0, "chrome_no_meet")
        events = self.step(5, "chrome_no_meet")
        self.assertEqual([e.kind for e in events], ["start"])
        self.assertEqual(self.recorder.starts, 1)
        ended = self.step(5 + 4 * 3600, "chrome_no_meet")
        self.assertEqual([e.kind for e in ended], ["end"])
        self.assertEqual(self.recorder.stops, 1)
        for second in (10, 15, 20):
            self.assertEqual(self.step(5 + 4 * 3600 + second, "chrome_no_meet"), [])
        self.assertEqual(self.recorder.starts, 1)
        self.step(5 + 4 * 3600 + 30, "idle")
        self.step(5 + 4 * 3600 + 35, "chrome_no_meet")
        events = self.step(5 + 4 * 3600 + 40, "chrome_no_meet")
        self.assertEqual([e.kind for e in events], ["start"])

    def test_recorder_streams_are_ignored(self):
        for second in range(0, 60, 5):
            self.assertEqual(self.step(second, "recorders"), [])
        self.assertEqual(self.recorder.starts, 0)

    def test_snapshot_failure_does_not_end_meeting(self):
        self.step(0, "meet")
        self.step(5, "meet")
        self.world.broken = True
        for second in range(10, 120, 5):
            self.assertEqual(self.step(second, "meet"), [])
        self.assertIsNotNone(self.backend.active())

    def test_manual_start_and_stop(self):
        events = self.backend.manual_start("Manual", "Standup")
        self.assertEqual([(e.kind, e.app, e.title, e.at) for e in events], [("start", "Manual", "Standup", T0)])
        self.assertEqual(self.recorder.starts, 1)
        self.assertEqual(
            self.backend.active(),
            {"app": "Manual", "title": "Standup", "window": None, "started_at": T0},
        )
        for second in range(5, 60, 5):
            self.assertEqual(self.step(second, "idle"), [])
        self.assertEqual(self.world.grims, [])
        self.now = at(60)
        events = self.backend.manual_stop()
        self.assertEqual([(e.kind, e.at) for e in events], [("end", at(60))])
        self.assertEqual(self.recorder.stops, 1)
        self.assertIsNone(self.backend.active())

    def test_close_stops_recorder(self):
        self.step(0, "zoom")
        self.step(5, "zoom")
        self.backend.close()
        self.assertEqual(self.recorder.stops, 1)
        self.assertFalse(self.recorder.running)


if __name__ == "__main__":
    unittest.main()
