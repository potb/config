import json
import logging
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from meeting_notes import backends, chunks, state, watch
from meeting_notes.asr import LiveResult
from meeting_notes.backend_native import NativeBackend
from meeting_notes.backend_screenpipe import Event as ScreenpipeEvent
from meeting_notes.backend_screenpipe import ScreenpipeBackend
from meeting_notes.config import Config
from meeting_notes.detect import Event

UTC = timezone.utc
T0 = datetime(2026, 11, 17, 9, 0, 0, tzinfo=UTC)


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


def at(seconds):
    return T0 + timedelta(seconds=seconds)


def make_cfg(root, **env):
    base = {
        "HOME": str(root),
        "MEETING_NOTES_DATA_DIR": str(Path(root) / "data"),
        "MEETING_NOTES_MEETINGS_DIR": str(Path(root) / "Meetings"),
        "MEETING_NOTES_OWNER": "Ada",
        "MEETING_NOTES_CLAUDE": "/bin/claude",
    }
    base.update(env)
    return Config.from_env(base)


class FakeBackend:
    name = "native"

    def __init__(self):
        self.queue = []
        self.manual = []
        self.manual_events = []
        self.closed = False

    def poll(self, now):
        events, self.queue = self.queue, []
        return events

    def manual_start(self, app, title):
        self.manual.append(("start", app, title))
        if self.name == "screenpipe":
            return None
        events, self.manual_events = self.manual_events, []
        return events

    def manual_stop(self):
        self.manual.append(("stop",))
        events, self.manual_events = self.manual_events, []
        return events

    def close(self):
        self.closed = True


class FakeAsr:
    def __init__(self, slow=False):
        self.slow = slow
        self.calls = []

    def asr_prompt(self, cfg):
        return "prompt"

    def live_pass(self, cfg, start, prompt, should_stop, clock=None):
        self.calls.append(clock())
        return LiveResult(1, self.slow)


class FakePending:
    def __init__(self, cfg):
        self.cfg = cfg
        self.calls = []

    def list_pending(self, cfg, now):
        self.calls.append(now)
        items = []
        st = state.load(cfg.state_path)
        for mid, meeting in st["meetings"].items():
            status = (st["processed"].get(mid) or {}).get("status")
            if meeting.get("end") and status not in state.TERMINAL:
                items.append({"id": mid, "start": meeting["start"], "end": meeting["end"]})
        return items


class FakeNotify:
    def __init__(self):
        self.sent = []

    def send(self, title, body, run):
        self.sent.append((title, body))
        return True


class FakeCleanup:
    def __init__(self):
        self.calls = []

    def run(self, cfg, now):
        self.calls.append(now)
        return {}


class WatchCase(unittest.TestCase):
    live = "0"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.cfg = make_cfg(self.root, MEETING_NOTES_LIVE=self.live)
        self.now = T0
        self.backend = FakeBackend()
        self.asr = FakeAsr()
        self.pending = FakePending(self.cfg)
        self.notify = FakeNotify()
        self.cleanup = FakeCleanup()
        self.runs = []
        self.watcher = self.build()

    def build(self):
        return watch.Watcher(
            self.cfg,
            self.backend,
            lambda: self.now,
            self.fake_run,
            asr=self.asr,
            pending=self.pending,
            notify=self.notify,
            cleanup=self.cleanup,
            threaded=False,
            self_cmd=["/bin/meeting-notes"],
        )

    fetch_code = 0

    def fake_run(self, argv, cwd=None, timeout=None, log=None):
        self.runs.append({"argv": list(argv), "cwd": cwd, "timeout": timeout, "log": log})
        if argv[:2] == ["/bin/meeting-notes", "fetch"]:
            if self.fetch_code:
                return subprocess.CompletedProcess(argv, self.fetch_code)
            out = self.cfg.meeting_dir(argv[2])
            out.mkdir(parents=True, exist_ok=True)
            (out / "fetched.ok").write_text("")
        return subprocess.CompletedProcess(argv, 0)

    def tick(self, seconds):
        self.now = at(seconds)
        self.watcher.tick(self.now)

    def start(self, seconds, app="zoom", title="Sync"):
        self.backend.queue.append(Event("start", app, title, None, at(seconds)))

    def end(self, seconds):
        self.backend.queue.append(Event("end", "zoom", "Sync", None, at(seconds)))

    def meetings(self):
        return state.load(self.cfg.state_path)["meetings"]

    def claude_runs(self):
        return [r for r in self.runs if r["argv"][0] == "/bin/claude"]

    def fetch_runs(self):
        return [r for r in self.runs if r["argv"][:2] == ["/bin/meeting-notes", "fetch"]]

    def chunk(self, kind, seconds):
        self.cfg.audio_dir.mkdir(parents=True, exist_ok=True)
        path = self.cfg.audio_dir / chunks.chunk_name("dev", kind, at(seconds))
        path.write_bytes(b"x")
        stamp = at(seconds).timestamp()
        os.utime(path, (stamp, stamp))


class StartEndTest(WatchCase):
    def test_start_then_end_processes_after_settle(self):
        self.start(0)
        self.tick(0)
        meetings = self.meetings()
        self.assertEqual(len(meetings), 1)
        mid, meeting = next(iter(meetings.items()))
        self.assertEqual(meeting["start"], "2026-11-17T09:00:00Z")
        self.assertIsNone(meeting["end"])
        self.assertEqual(meeting["source"], "auto")
        self.assertEqual(meeting["backend"], "native")
        self.assertEqual(meeting["live"], "off")
        self.end(600)
        self.tick(620)
        self.assertEqual(self.meetings()[mid]["end"], "2026-11-17T09:10:00Z")
        calls = len(self.pending.calls)
        self.tick(650)
        self.assertEqual(len(self.pending.calls), calls)
        self.assertEqual(self.claude_runs(), [])
        self.tick(680)
        self.assertEqual(len(self.pending.calls), calls + 1)
        self.assertEqual([r["argv"] for r in self.fetch_runs()], [["/bin/meeting-notes", "fetch", mid]])
        self.assertEqual(self.fetch_runs()[0]["timeout"], watch.FETCH_TIMEOUT)
        self.assertEqual(len(self.claude_runs()), 1)
        self.assertLess(self.runs.index(self.fetch_runs()[0]), self.runs.index(self.claude_runs()[0]))

    def test_no_claude_run_without_pending(self):
        self.tick(0)
        self.assertEqual(len(self.pending.calls), 1)
        self.assertEqual(self.runs, [])

    def test_fetched_meeting_is_not_fetched_again(self):
        self.start(0)
        self.tick(0)
        mid = next(iter(self.meetings()))
        self.cfg.meeting_dir(mid).mkdir(parents=True)
        (self.cfg.meeting_dir(mid) / "fetched.ok").write_text("")
        self.end(600)
        self.tick(600)
        self.tick(660)
        self.assertEqual(self.fetch_runs(), [])
        self.assertEqual(len(self.claude_runs()), 1)

    def test_catchup_every_fifteen_minutes(self):
        self.tick(0)
        self.tick(600)
        self.assertEqual(len(self.pending.calls), 1)
        self.tick(900)
        self.assertEqual(len(self.pending.calls), 2)

    def test_settle_matches_pending_threshold(self):
        self.pending.SETTLE_SECONDS = 120
        self.start(0)
        self.tick(0)
        self.end(600)
        self.tick(600)
        self.tick(660)
        shifted = self.pending.calls[-1]
        self.assertEqual(shifted, at(660) + timedelta(seconds=120 - watch.SETTLE_SECONDS))

    def test_stale_open_meeting_closed_on_startup(self):
        with state.locked(self.cfg.state_path) as st:
            mid = state.start_meeting(st, "native", "zoom", "Old", at(-3600), "auto")
        self.tick(0)
        self.assertEqual(self.meetings()[mid]["end"], "2026-11-17T08:00:00Z")

    def test_stale_meeting_ends_at_last_chunk_not_restart(self):
        with state.locked(self.cfg.state_path) as st:
            mid = state.start_meeting(st, "native", "zoom", "Old", at(-3600), "auto")
        self.chunk("input", -3000)
        last = self.cfg.audio_dir / chunks.chunk_name("dev", "input", at(-3000))
        stamp = at(-2970).timestamp()
        os.utime(last, (stamp, stamp))
        self.tick(36000)
        self.assertEqual(self.meetings()[mid]["end"], "2026-11-17T08:10:30Z")

    def test_close_ends_current_meeting(self):
        self.start(0)
        self.tick(0)
        mid = next(iter(self.meetings()))
        self.now = at(300)
        self.watcher.close()
        self.assertEqual(self.meetings()[mid]["end"], "2026-11-17T09:05:00Z")
        self.assertTrue(self.backend.closed)

    def test_failed_fetch_marks_failed_after_max_attempts(self):
        self.fetch_code = 1
        self.start(0)
        self.tick(0)
        mid = next(iter(self.meetings()))
        self.end(600)
        self.tick(600)
        self.tick(660)
        self.assertEqual(self.claude_runs(), [])
        info = state.load(self.cfg.state_path)["processed"][mid]
        self.assertEqual(info["attempts"], 1)
        self.assertIn("fetch", info["last_error"])
        for n in range(1, watch.MAX_ATTEMPTS + 2):
            self.tick(660 + n * watch.CATCHUP_SECONDS)
        info = state.load(self.cfg.state_path)["processed"][mid]
        self.assertEqual(info["status"], state.FAILED)
        self.assertEqual(len(self.fetch_runs()), watch.MAX_ATTEMPTS)
        self.assertEqual(self.claude_runs(), [])

    def test_unfinished_claude_run_marks_failed(self):
        self.start(0)
        self.tick(0)
        mid = next(iter(self.meetings()))
        self.end(600)
        self.tick(600)
        self.tick(660)
        for n in range(1, watch.MAX_ATTEMPTS + 2):
            self.tick(660 + n * watch.CATCHUP_SECONDS)
        self.assertEqual(len(self.claude_runs()), watch.MAX_ATTEMPTS)
        self.assertEqual(state.load(self.cfg.state_path)["processed"][mid]["status"], state.FAILED)

    def test_screenpipe_events(self):
        self.backend.name = "screenpipe"
        self.backend.queue.append(
            ScreenpipeEvent("start", 7, "Google Meet", "Weekly", "2026-11-17T09:00:00Z", None)
        )
        self.tick(0)
        mid, meeting = next(iter(self.meetings().items()))
        self.assertEqual(meeting["backend"], "screenpipe")
        self.assertEqual(meeting["screenpipe_id"], 7)
        self.backend.queue.append(
            ScreenpipeEvent("end", 7, "Google Meet", "Weekly", "2026-11-17T09:00:00Z", "2026-11-17T09:30:00Z")
        )
        self.tick(1810)
        self.assertEqual(self.meetings()[mid]["end"], "2026-11-17T09:30:00Z")


class ControlTest(WatchCase):
    def test_start_control_consumed(self):
        self.cfg.control_dir.mkdir(parents=True)
        start = self.cfg.control_dir / "start.json"
        start.write_text(json.dumps({"app": "Manual", "title": "Standup"}))
        self.backend.manual_events = [Event("start", "Manual", "Standup", None, at(0))]
        self.tick(0)
        self.assertFalse(start.exists())
        self.assertEqual(self.backend.manual, [("start", "Manual", "Standup")])
        meeting = next(iter(self.meetings().values()))
        self.assertEqual(meeting["source"], "manual")
        self.assertEqual(meeting["title"], "Standup")

    def test_stop_control_consumed(self):
        self.start(0)
        self.tick(0)
        stop = self.cfg.control_dir / "stop"
        stop.parent.mkdir(parents=True, exist_ok=True)
        stop.write_text("")
        self.backend.manual_events = [Event("end", "zoom", "Sync", None, at(300))]
        self.tick(300)
        self.assertFalse(stop.exists())
        self.assertEqual(self.backend.manual, [("stop",)])
        self.assertEqual(next(iter(self.meetings().values()))["end"], "2026-11-17T09:05:00Z")

    def test_manual_start_marks_next_polled_start(self):
        self.cfg.control_dir.mkdir(parents=True)
        (self.cfg.control_dir / "start.json").write_text(json.dumps({"app": "Manual", "title": None}))
        self.backend.name = "screenpipe"
        self.tick(0)
        self.backend.queue.append(ScreenpipeEvent("start", 3, "Manual", None, None, None))
        self.tick(10)
        meeting = next(iter(self.meetings().values()))
        self.assertEqual(meeting["source"], "manual")
        self.assertEqual(meeting["start"], "2026-11-17T09:00:10Z")

    def test_manual_start_during_meeting_does_not_leak(self):
        self.start(0)
        self.tick(0)
        self.cfg.control_dir.mkdir(parents=True)
        (self.cfg.control_dir / "start.json").write_text(json.dumps({"title": "x"}))
        self.tick(10)
        self.end(600)
        self.tick(600)
        self.start(700)
        self.tick(700)
        sources = sorted(m["source"] for m in self.meetings().values())
        self.assertEqual(sources, ["auto", "auto"])

    def test_invalid_start_json_removed(self):
        self.cfg.control_dir.mkdir(parents=True)
        start = self.cfg.control_dir / "start.json"
        start.write_text("{nope")
        self.tick(0)
        self.assertFalse(start.exists())
        self.assertEqual(self.backend.manual, [("start", "Manual", "Manual")])


class LiveTest(WatchCase):
    live = "1"

    def test_live_passes_every_twenty_seconds(self):
        self.start(0)
        self.tick(0)
        mid = next(iter(self.meetings()))
        self.assertEqual(self.meetings()[mid]["live"], "running")
        self.tick(10)
        self.assertEqual(self.asr.calls, [])
        self.tick(20)
        self.tick(40)
        self.assertEqual(self.asr.calls, [at(20), at(40)])
        self.end(50)
        self.tick(50)
        self.tick(80)
        self.assertEqual(len(self.asr.calls), 2)
        self.assertEqual(self.meetings()[mid]["live"], "done")

    def test_slow_live_stops_after_two_slow_passes_in_a_row(self):
        self.asr.slow = True
        self.start(0)
        self.tick(0)
        mid = next(iter(self.meetings()))
        self.tick(20)
        self.assertEqual(self.meetings()[mid]["live"], "running")
        self.tick(40)
        self.assertEqual(len(self.asr.calls), 2)
        self.assertEqual(self.meetings()[mid]["live"], "stopped_slow")
        self.tick(60)
        self.tick(100)
        self.assertEqual(len(self.asr.calls), 2)
        self.end(120)
        self.tick(120)
        self.assertEqual(self.meetings()[mid]["live"], "stopped_slow")

    def test_one_slow_pass_then_fast_keeps_live(self):
        self.asr.slow = True
        self.start(0)
        self.tick(0)
        mid = next(iter(self.meetings()))
        self.tick(20)
        self.asr.slow = False
        self.tick(40)
        self.asr.slow = True
        self.tick(60)
        self.assertEqual(len(self.asr.calls), 3)
        self.assertEqual(self.meetings()[mid]["live"], "running")

    def test_live_off_when_disabled(self):
        cfg = make_cfg(self.root, MEETING_NOTES_LIVE="0")
        self.cfg = cfg
        self.watcher = self.build()
        self.start(0)
        self.tick(0)
        self.tick(20)
        self.assertEqual(self.asr.calls, [])

    def test_live_thread_stops(self):
        live = watch.Live(self.watcher, "m", T0)
        live.stop()
        live.loop()
        live.step()
        self.assertEqual(self.asr.calls, [])


class AudioWatchTest(WatchCase):
    def test_alert_once_then_recovery(self):
        self.chunk("input", 0)
        self.chunk("output", 0)
        self.start(0)
        self.tick(0)
        self.tick(60)
        self.assertEqual(self.notify.sent, [])
        self.chunk("input", 80)
        self.tick(95)
        self.assertEqual(len(self.notify.sent), 1)
        self.assertIn("others", self.notify.sent[0][1])
        self.assertNotIn("me", self.notify.sent[0][1].split("from ")[1])
        self.tick(100)
        self.tick(150)
        self.assertEqual(len(self.notify.sent), 1)
        self.chunk("input", 150)
        self.chunk("output", 155)
        self.tick(160)
        self.assertEqual(len(self.notify.sent), 2)
        self.assertIn("back", self.notify.sent[1][1])

    def test_no_alert_without_meeting(self):
        self.tick(0)
        self.tick(500)
        self.assertEqual(self.notify.sent, [])

    def test_alert_counts_from_meeting_start(self):
        self.start(1000)
        self.tick(1000)
        self.tick(1080)
        self.assertEqual(self.notify.sent, [])
        self.tick(1090)
        self.assertEqual(len(self.notify.sent), 1)


class CleanupTest(WatchCase):
    def test_hourly(self):
        self.tick(0)
        self.tick(1800)
        self.assertEqual(self.cleanup.calls, [at(0)])
        self.tick(3600)
        self.assertEqual(self.cleanup.calls, [at(0), at(3600)])


class ClaudeTest(WatchCase):
    def test_exact_argv(self):
        self.now = at(0)
        self.watcher.run_claude(self.now)
        self.assertEqual(len(self.runs), 1)
        call = self.runs[0]
        self.assertEqual(
            call["argv"],
            [
                "/bin/claude",
                "-p",
                watch.prompt(self.cfg),
                "--permission-mode",
                "acceptEdits",
                "--allowedTools",
                "Bash(meeting-notes pending)",
                "Bash(meeting-notes finish:*)",
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep",
                "--add-dir",
                str(self.cfg.meetings_dir),
            ],
        )
        self.assertEqual(call["cwd"], self.cfg.data_dir)
        self.assertEqual(call["timeout"], 3600)
        self.assertEqual(call["log"], self.cfg.runs_dir / "20261117-090000.log")
        self.assertTrue(self.cfg.runs_dir.is_dir())

    def test_prompt(self):
        text = watch.prompt(self.cfg)
        self.assertIn("Ada", text)
        self.assertNotIn("Quentin", text)
        for needle in ("pipe.md", "glossary.md", "work/<id>/screens/*.png", ".env", "Slack"):
            self.assertIn(needle, text)
        self.assertIn("'me'", text)


class RunnerTest(unittest.TestCase):
    def test_default_run_logs_and_returns_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "runs" / "a.log"
            result = watch.default_run(["sh", "-c", "echo hi; exit 3"], cwd=tmp, timeout=10, log=log)
            self.assertEqual(result.returncode, 3)
            self.assertEqual(log.read_text(), "hi\n")

    def test_default_run_timeout_kills_group(self):
        result = watch.default_run(["sh", "-c", "sleep 30 & wait"], timeout=0.2)
        self.assertEqual(result.returncode, watch.TIMEOUT_CODE)


class PollTest(unittest.TestCase):
    def test_intervals(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(watch.poll_seconds(make_cfg(tmp)), 5)
            self.assertEqual(watch.poll_seconds(make_cfg(tmp, MEETING_NOTES_BACKEND="screenpipe")), 10)


class BackendsTest(unittest.TestCase):
    def test_make(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsInstance(backends.make(make_cfg(tmp)), NativeBackend)
            backend = backends.make(make_cfg(tmp, MEETING_NOTES_BACKEND="screenpipe"))
            self.assertIsInstance(backend, ScreenpipeBackend)
            self.assertNotIn(make_cfg(tmp).key_path.read_text().strip(), repr(backend.client))


if __name__ == "__main__":
    unittest.main()
