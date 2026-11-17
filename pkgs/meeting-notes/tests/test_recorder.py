import signal
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from meeting_notes import chunks, recorder
from meeting_notes.config import Config
from meeting_notes.detect import Client

UTC = timezone.utc


def make_cfg(tmp):
    return Config.from_env({"HOME": tmp, "MEETING_NOTES_FFMPEG": "/nix/store/x-ffmpeg/bin/ffmpeg"})


class FakeProc:
    def __init__(self, pid, survives=()):
        self.pid = pid
        self.returncode = None
        self.survives = set(survives)
        self.signals = []

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("ffmpeg", timeout)
        return self.returncode


class FakePopen:
    def __init__(self, survives=()):
        self.calls = []
        self.procs = []
        self.survives = survives

    def __call__(self, argv, **kwargs):
        proc = FakeProc(9000 + len(self.procs), self.survives)
        self.calls.append((list(argv), kwargs))
        self.procs.append(proc)
        return proc


class FakeKill:
    def __init__(self, popen):
        self.popen = popen
        self.sent = []

    def __call__(self, pid, sig):
        self.sent.append((pid, sig))
        for proc in self.popen.procs:
            if proc.pid == pid and sig not in proc.survives:
                proc.returncode = -sig


def fake_run(sink="alsa_output.pci-0000_0b_00.4.analog-stereo\n", fail=False):
    calls = []

    def run(argv, env=None):
        calls.append(list(argv))
        if fail:
            raise subprocess.CalledProcessError(1, argv)
        return sink

    run.calls = calls
    return run


class RecorderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(self.tmp.name)
        self.popen = FakePopen()
        self.kill = FakeKill(self.popen)

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, run=None, popen=None):
        popen = popen or self.popen
        self.kill.popen = popen
        return recorder.Recorder(self.cfg, run=run or fake_run(), popen=popen, killpg=self.kill)

    def expected(self, source, device, kind):
        return [
            "/nix/store/x-ffmpeg/bin/ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-f",
            "pulse",
            "-i",
            source,
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "aac",
            "-f",
            "segment",
            "-segment_time",
            "30",
            "-reset_timestamps",
            "1",
            "-strftime",
            "1",
            str(self.cfg.audio_dir / chunks.ffmpeg_pattern(device, kind)),
        ]

    def test_start_launches_exact_ffmpeg_commands(self):
        run = fake_run()
        rec = self.make(run=run)
        rec.start()
        self.assertEqual(run.calls, [["pactl", "get-default-sink"]])
        self.assertEqual(len(self.popen.calls), 2)
        mic, system = self.popen.calls
        self.assertEqual(mic[0], self.expected("default", "mic", "input"))
        self.assertEqual(
            system[0],
            self.expected("alsa_output.pci-0000_0b_00.4.analog-stereo.monitor", "system", "output"),
        )
        for _, kwargs in self.popen.calls:
            self.assertEqual(kwargs["env"]["TZ"], "UTC")
            self.assertTrue(kwargs["start_new_session"])
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertTrue(self.cfg.audio_dir.is_dir())
        self.assertTrue(rec.alive())
        self.assertEqual(rec.pids(), [9000, 9001])

    def test_start_twice_does_not_spawn_again(self):
        rec = self.make()
        rec.start()
        rec.start()
        self.assertEqual(len(self.popen.calls), 2)

    def test_pattern_with_fixed_instant_matches_chunk_re(self):
        instant = datetime(2026, 11, 17, 9, 30, 0, tzinfo=UTC)
        for device, kind in [("mic", "input"), ("system", "output")]:
            name = Path(self.expected("default", device, kind)[-1]).name
            produced = instant.strftime(name)
            self.assertIsNotNone(chunks.CHUNK_RE.match(produced))
            self.assertEqual(chunks.parse(produced)[2], instant)

    def test_missing_sink_records_mic_only(self):
        rec = self.make(run=fake_run(fail=True))
        rec.start()
        self.assertEqual(len(self.popen.calls), 1)
        self.assertEqual(self.popen.calls[0][0][8], "default")

    def test_stop_sends_sigint_to_process_groups(self):
        rec = self.make()
        rec.start()
        rec.stop()
        self.assertEqual(self.kill.sent, [(9000, signal.SIGINT), (9001, signal.SIGINT)])
        self.assertFalse(rec.alive())
        self.assertEqual(rec.pids(), [])

    def test_stop_escalates_to_sigterm_then_sigkill(self):
        popen = FakePopen(survives={signal.SIGINT, signal.SIGTERM})
        rec = self.make(popen=popen)
        rec.start()
        rec.stop(timeout=0)
        self.assertEqual(
            [sig for pid, sig in self.kill.sent if pid == 9000],
            [signal.SIGINT, signal.SIGTERM, signal.SIGKILL],
        )

    def test_stop_tolerates_vanished_group(self):
        def gone(pid, sig):
            raise ProcessLookupError(pid)

        rec = recorder.Recorder(self.cfg, run=fake_run(), popen=self.popen, killpg=gone)
        rec.start()
        for proc in self.popen.procs:
            proc.returncode = 0
        rec.stop()
        self.assertFalse(rec.alive())

    def test_alive_false_when_one_process_died(self):
        rec = self.make()
        rec.start()
        self.popen.procs[1].returncode = 1
        self.assertFalse(rec.alive())

    def test_not_alive_before_start(self):
        self.assertFalse(self.make().alive())


class ScreenshotTest(unittest.TestCase):
    def test_grim_captures_the_window_by_stable_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(tmp)
            calls = []

            def run(argv, env=None):
                calls.append(list(argv))
                return ""

            window = Client("0x1", "google-chrome", "Meet - abc", 4100, (1280, 40), (1280, 1400), "18000209")
            now = datetime(2026, 11, 17, 9, 5, 0, tzinfo=UTC)
            path = recorder.screenshot(cfg, "20261117-090000", window, run, now)
            expected = cfg.screens_dir("20261117-090000") / "2026-11-17_09-05-00.png"
            self.assertEqual(path, expected)
            self.assertEqual(calls, [["grim", "-T", "18000209", str(expected)]])
            self.assertTrue(expected.parent.is_dir())

    def test_no_capture_without_stable_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(tmp)
            calls = []

            def run(argv, env=None):
                calls.append(list(argv))
                return ""

            window = Client("0x1", "google-chrome", "Meet - abc", 4100, (1280, 40), (1280, 1400))
            now = datetime(2026, 11, 17, 9, 5, 0, tzinfo=UTC)
            self.assertIsNone(recorder.screenshot(cfg, "m", window, run, now))
            self.assertEqual(calls, [])

    def test_grim_failure_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(tmp)

            def run(argv, env=None):
                raise subprocess.CalledProcessError(1, argv)

            window = Client("0x1", "zoom", "Zoom", 1, (0, 0), (10, 10), "18000001")
            now = datetime(2026, 11, 17, 9, 5, 0, tzinfo=UTC)
            self.assertIsNone(recorder.screenshot(cfg, "m", window, run, now))


if __name__ == "__main__":
    unittest.main()
