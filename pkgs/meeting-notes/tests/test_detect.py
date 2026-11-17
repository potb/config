import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from meeting_notes import detect

UTC = timezone.utc
FIXTURES = Path(__file__).parent / "fixtures" / "native"
T0 = datetime(2026, 11, 17, 9, 0, 0, tzinfo=UTC)


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def candidate(name, ignore_pids=()):
    data = fixture(name)
    return detect.match_call(
        detect.parse_pw_dump(data["pw_dump"]),
        detect.parse_clients(data["clients"]),
        ignore_pids,
    )


def at(seconds):
    return T0 + timedelta(seconds=seconds)


def run_sequence(detector, names, poll=5):
    events = []
    for index, name in enumerate(names):
        for event in detector.feed(at(index * poll), candidate(name)):
            events.append((index, event))
    return events


class ParseTest(unittest.TestCase):
    def test_parse_pw_dump_keeps_input_streams_only(self):
        self.assertEqual(detect.parse_pw_dump(fixture("idle")["pw_dump"]), [])
        streams = detect.parse_pw_dump(fixture("meet")["pw_dump"])
        self.assertEqual(
            streams, [detect.Stream(4100, "chrome", "Google Chrome input", "running")]
        )

    def test_parse_pw_dump_reads_string_pids(self):
        streams = detect.parse_pw_dump(fixture("slack_huddle")["pw_dump"])
        self.assertEqual(streams, [detect.Stream(6100, "slack", "Slack", "running")])

    def test_parse_pw_dump_tolerates_missing_fields(self):
        objs = [
            {"type": "PipeWire:Interface:Node"},
            {"type": "PipeWire:Interface:Node", "info": None},
            {
                "type": "PipeWire:Interface:Node",
                "info": {"props": {"media.class": "Stream/Input/Audio"}},
            },
        ]
        self.assertEqual(detect.parse_pw_dump(objs), [detect.Stream(None, "", "", "")])

    def test_parse_clients(self):
        clients = detect.parse_clients(fixture("meet")["clients"])
        self.assertEqual(
            clients[1],
            detect.Client(
                "0x5600b7",
                "google-chrome",
                "Meet - abc-defg-hij - Google Chrome",
                4100,
                (1280, 40),
                (1280, 1400),
                "180000b7",
            ),
        )


class MatchTest(unittest.TestCase):
    def test_idle_is_nothing(self):
        self.assertIsNone(candidate("idle"))

    def test_meet_tab(self):
        found = candidate("meet")
        self.assertEqual(found.app, "Google Meet")
        self.assertEqual(found.title, "Meet - abc-defg-hij - Google Chrome")
        self.assertEqual(found.window.address, "0x5600b7")

    def test_chrome_without_meet_tab_is_nothing(self):
        self.assertIsNone(candidate("chrome_no_meet"))

    def test_slack_huddle(self):
        found = candidate("slack_huddle")
        self.assertEqual(found.app, "Slack")
        self.assertEqual(found.window.address, "0x5600c1")

    def test_slack_without_huddle_is_nothing(self):
        data = fixture("slack_huddle")
        data["clients"][0]["title"] = "general - Acme - Slack"
        streams = detect.parse_pw_dump(data["pw_dump"])
        clients = detect.parse_clients(data["clients"])
        self.assertIsNone(detect.match_call(streams, clients, ()))

    def test_zoom_by_binary_with_window_of_same_pid(self):
        found = candidate("zoom")
        self.assertEqual(found.app, "Zoom")
        self.assertEqual(found.title, "Zoom Meeting")
        self.assertEqual(found.window.address, "0x5600d4")

    def test_app_name_match_is_case_insensitive_and_window_by_class(self):
        streams = [detect.Stream(900, "electron", "Discord", "running")]
        clients = [detect.Client("0x1", "discord", "General - Discord", 901, (0, 0), (10, 10))]
        found = detect.match_call(streams, clients, ())
        self.assertEqual(found.app, "Discord")
        self.assertEqual(found.window.address, "0x1")

    def test_app_without_window(self):
        streams = [detect.Stream(900, "teams-for-linux", "teams-for-linux", "running")]
        found = detect.match_call(streams, [], ())
        self.assertEqual(found.app, "Teams")
        self.assertIsNone(found.window)

    def test_recorders_never_match(self):
        self.assertIsNone(candidate("recorders"))

    def test_ignored_pids(self):
        self.assertIsNone(candidate("zoom", ignore_pids=[5200]))
        self.assertIsNone(candidate("meet", ignore_pids={4100}))


class DetectorTest(unittest.TestCase):
    def test_meet_sequence(self):
        detector = detect.Detector()
        names = ["idle", "meet", "meet", "meet", "idle", "idle", "idle", "idle", "idle", "idle"]
        events = run_sequence(detector, names)
        self.assertEqual([(i, e.kind) for i, e in events], [(2, "start"), (8, "end")])
        start = events[0][1]
        self.assertEqual(start.app, "Google Meet")
        self.assertEqual(start.title, "Meet - abc-defg-hij - Google Chrome")
        self.assertEqual(start.window.address, "0x5600b7")
        self.assertEqual(start.at, at(5))
        end = events[1][1]
        self.assertEqual(end.app, "Google Meet")
        self.assertEqual(end.at, at(20))
        self.assertEqual(at(40) - end.at, timedelta(seconds=20))

    def test_brief_absence_does_not_end(self):
        detector = detect.Detector()
        names = ["meet", "meet", "idle", "idle", "idle", "meet", "meet", "idle"]
        events = run_sequence(detector, names)
        self.assertEqual([e.kind for _, e in events], ["start"])
        self.assertIsNotNone(detector.active)

    def test_single_positive_poll_does_not_start(self):
        detector = detect.Detector()
        events = run_sequence(detector, ["idle", "meet", "idle", "meet", "idle"])
        self.assertEqual(events, [])

    def test_recorders_and_chrome_alone_never_trigger(self):
        detector = detect.Detector()
        names = ["recorders"] * 6 + ["chrome_no_meet"] * 6
        self.assertEqual(run_sequence(detector, names), [])

    def test_manual_mode_ignores_detector(self):
        detector = detect.Detector()
        started = detector.force_start("Manual", "Standup", at(0))
        self.assertEqual([e.kind for e in started], ["start"])
        self.assertEqual((started[0].app, started[0].title, started[0].at), ("Manual", "Standup", at(0)))
        for second in range(5, 120, 5):
            self.assertEqual(detector.feed(at(second), None), [])
        for second in range(120, 140, 5):
            self.assertEqual(detector.feed(at(second), candidate("zoom")), [])
        stopped = detector.force_stop(at(140))
        self.assertEqual([(e.kind, e.app, e.at) for e in stopped], [("end", "Manual", at(140))])
        self.assertIsNone(detector.active)

    def test_force_start_adopts_running_meeting(self):
        detector = detect.Detector()
        run_sequence(detector, ["meet", "meet"])
        self.assertEqual(detector.force_start("Manual", "Standup", at(10)), [])
        self.assertTrue(detector.manual)
        for second in range(15, 100, 5):
            self.assertEqual(detector.feed(at(second), None), [])
        stopped = detector.force_stop(at(100))
        self.assertEqual([(e.kind, e.app) for e in stopped], [("end", "Google Meet")])

    def test_force_stop_of_detected_meeting_waits_for_mic_to_drop(self):
        detector = detect.Detector()
        run_sequence(detector, ["meet", "meet"])
        self.assertEqual([e.kind for e in detector.force_stop(at(10))], ["end"])
        meet = candidate("meet")
        for second in range(15, 60, 5):
            self.assertEqual(detector.feed(at(second), meet), [])
        self.assertEqual(detector.feed(at(60), None), [])
        detector.feed(at(65), meet)
        self.assertEqual([e.kind for e in detector.feed(at(70), meet)], ["start"])

    def test_force_stop_without_meeting(self):
        self.assertEqual(detect.Detector().force_stop(at(0)), [])


class FakeRun:
    def __init__(self, outputs, fail=()):
        self.outputs = outputs
        self.fail = set(fail)
        self.calls = []

    def __call__(self, argv, env=None):
        self.calls.append((list(argv), env))
        if argv[0] in self.fail:
            raise subprocess.CalledProcessError(1, argv)
        return self.outputs[argv[0]]


class SnapshotTest(unittest.TestCase):
    def outputs(self):
        data = fixture("meet")
        return {"pw-dump": json.dumps(data["pw_dump"]), "hyprctl": json.dumps(data["clients"])}

    def test_snapshot_with_signature(self):
        run = FakeRun(self.outputs())
        environ = {"HYPRLAND_INSTANCE_SIGNATURE": "sig", "XDG_RUNTIME_DIR": "/nonexistent"}
        streams, clients = detect.snapshot(run, environ)
        self.assertEqual(streams[0].binary, "chrome")
        self.assertEqual(clients[1].pid, 4100)
        self.assertEqual(run.calls[0][0], ["pw-dump"])
        self.assertEqual(run.calls[1][0], ["hyprctl", "clients", "-j"])
        self.assertEqual(run.calls[1][1]["HYPRLAND_INSTANCE_SIGNATURE"], "sig")

    def test_snapshot_finds_newest_hyprland_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            hypr = Path(tmp) / "hypr"
            for name, mtime in [("old", 1000), ("new", 2000), ("mid", 1500)]:
                (hypr / name).mkdir(parents=True)
                os.utime(hypr / name, (mtime, mtime))
            run = FakeRun(self.outputs())
            result = detect.snapshot(run, {"XDG_RUNTIME_DIR": tmp})
            self.assertIsNotNone(result)
            self.assertEqual(run.calls[1][1]["HYPRLAND_INSTANCE_SIGNATURE"], "new")

    def test_snapshot_failure_returns_none(self):
        environ = {"HYPRLAND_INSTANCE_SIGNATURE": "sig"}
        self.assertIsNone(detect.snapshot(FakeRun(self.outputs(), fail=["pw-dump"]), environ))
        self.assertIsNone(detect.snapshot(FakeRun(self.outputs(), fail=["hyprctl"]), environ))
        broken = FakeRun({"pw-dump": "not json", "hyprctl": "[]"})
        self.assertIsNone(detect.snapshot(broken, environ))

        def missing(argv, env=None):
            raise FileNotFoundError(argv[0])

        self.assertIsNone(detect.snapshot(missing, environ))

    def test_snapshot_without_any_hyprland_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = FakeRun(self.outputs())
            self.assertIsNone(detect.snapshot(run, {"XDG_RUNTIME_DIR": tmp}))


if __name__ == "__main__":
    unittest.main()
