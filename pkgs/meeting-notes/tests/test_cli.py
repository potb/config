import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from meeting_notes import cli, state, watch
from meeting_notes.config import Config

UTC = timezone.utc


def env_for(root, **extra):
    base = {
        "HOME": str(root),
        "MEETING_NOTES_DATA_DIR": str(Path(root) / "data"),
        "MEETING_NOTES_MEETINGS_DIR": str(Path(root) / "Meetings"),
        "MEETING_NOTES_OWNER": "Ada",
    }
    base.update(extra)
    return base


class CliCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.env = env_for(self.root)
        self.cfg = Config.from_env(self.env)

    def call(self, *argv, **kw):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv), environ=kw.pop("environ", self.env), **kw)
        return code, out.getvalue(), err.getvalue()


class ControlTest(CliCase):
    def test_start_default(self):
        code, _, _ = self.call("start")
        self.assertEqual(code, 0)
        data = json.loads((self.cfg.control_dir / "start.json").read_text())
        self.assertEqual(data, {"app": "Manual", "title": None})

    def test_start_with_app_and_title(self):
        self.call("start", "--app", "Zoom", "--title", "Standup")
        data = json.loads((self.cfg.control_dir / "start.json").read_text())
        self.assertEqual(data, {"app": "Zoom", "title": "Standup"})

    def test_stop(self):
        code, _, _ = self.call("stop")
        self.assertEqual(code, 0)
        self.assertTrue((self.cfg.control_dir / "stop").exists())

    def test_tick_consumes_cli_files(self):
        calls = []

        class Backend:
            name = "native"

            def poll(self, now):
                return []

            def manual_start(self, app, title):
                calls.append(("start", app, title))

            def manual_stop(self):
                calls.append(("stop",))

            def close(self):
                pass

        class Quiet:
            def list_pending(self, cfg, now):
                return []

            def run(self, cfg, now):
                return {}

        now = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)
        watcher = watch.Watcher(
            self.cfg,
            Backend(),
            lambda: now,
            lambda *a, **k: subprocess.CompletedProcess(a, 0),
            pending=Quiet(),
            cleanup=Quiet(),
            threaded=False,
            self_cmd=["meeting-notes"],
        )
        self.call("start", "--title", "Standup")
        watcher.tick(now)
        self.call("stop")
        watcher.tick(now + timedelta(seconds=5))
        self.assertEqual(calls, [("start", "Manual", "Standup"), ("stop",)])
        self.assertEqual(list(self.cfg.control_dir.iterdir()), [])


class StatusTest(CliCase):
    def test_status_json(self):
        now = datetime.now(UTC)
        with state.locked(self.cfg.state_path) as st:
            for n in range(7):
                mid = state.start_meeting(st, "native", "zoom", f"M{n}", now - timedelta(hours=10 - n), "auto")
                state.end_meeting(st, mid, now - timedelta(hours=9 - n))
                state.set_processed(st, mid, status="done", at=f"2026-11-1{n}T00:00:00Z")
            active = state.start_meeting(st, "native", "meet", "Live one", now, "manual", live="running")
            st["last_run"] = "2026-11-17T08:00:00Z"
        self.cfg.runs_dir.mkdir(parents=True)
        (self.cfg.runs_dir / "20261117-080000.log").write_text("")
        (self.cfg.runs_dir / "20261117-090000-fetch-x.log").write_text("")
        code, out, _ = self.call("status", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["active"]["id"], active)
        self.assertEqual(data["live"], "running")
        self.assertEqual(data["last_run"]["pending"], "2026-11-17T08:00:00Z")
        self.assertEqual(data["last_run"]["log"], "20261117-080000.log")
        self.assertEqual(len(data["processed"]), 5)
        self.assertEqual(data["processed"][0]["at"], "2026-11-16T00:00:00Z")

    def test_status_text_empty(self):
        code, out, _ = self.call("status")
        self.assertEqual(code, 0)
        self.assertIn("no active meeting", out)


class PendingTest(CliCase):
    def test_pending_json(self):
        now = datetime.now(UTC).replace(microsecond=0)
        with state.locked(self.cfg.state_path) as st:
            mid = state.start_meeting(st, "native", "zoom", "Sync", now - timedelta(minutes=40), "auto")
            state.end_meeting(st, mid, now - timedelta(minutes=10))
        self.cfg.meeting_dir(mid).mkdir(parents=True)
        (self.cfg.meeting_dir(mid) / "fetched.ok").write_text("")
        code, out, _ = self.call("pending")
        self.assertEqual(code, 0)
        items = json.loads(out)
        self.assertEqual([item["id"] for item in items], [mid])

    def test_pending_lists_only_meetings_ready_for_claude(self):
        now = datetime.now(UTC).replace(microsecond=0)
        ids = []
        with state.locked(self.cfg.state_path) as st:
            for offset in (90, 70, 50, 30):
                mid = state.start_meeting(
                    st, "native", "zoom", f"M{offset}", now - timedelta(minutes=offset), "auto"
                )
                state.end_meeting(st, mid, now - timedelta(minutes=offset - 15))
                ids.append(mid)
        for mid in ids[1:]:
            self.cfg.meeting_dir(mid).mkdir(parents=True)
            (self.cfg.meeting_dir(mid) / "fetched.ok").write_text("")
        code, out, _ = self.call("pending")
        self.assertEqual(code, 0)
        self.assertEqual([item["id"] for item in json.loads(out)], ids[1:])

    def test_pending_empty(self):
        code, out, _ = self.call("pending")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])


class DelegateTest(CliCase):
    def test_finish_delegates(self):
        with mock.patch("meeting_notes.finish.main", return_value=0) as finish:
            code, _, _ = self.call("finish", "--id", "x", "--skip", "personal")
        self.assertEqual(code, 0)
        args, kwargs = finish.call_args
        self.assertEqual(args[0], ["--id", "x", "--skip", "personal"])
        self.assertEqual(kwargs["cfg"], self.cfg)

    def test_fetch_unknown(self):
        code, _, err = self.call("fetch", "nope")
        self.assertEqual(code, 1)
        self.assertIn("unknown meeting", err)

    def test_fetch(self):
        with state.locked(self.cfg.state_path) as st:
            mid = state.start_meeting(st, "native", "zoom", "Sync", datetime(2026, 11, 17, 9, tzinfo=UTC), "auto")
            state.end_meeting(st, mid, datetime(2026, 11, 17, 10, tzinfo=UTC))
        with mock.patch("meeting_notes.fetch.fetch", return_value=self.cfg.meeting_dir(mid)) as fetch:
            code, out, _ = self.call("fetch", mid)
        self.assertEqual(code, 0)
        self.assertEqual(fetch.call_args.args[:2], (self.cfg, mid))
        self.assertIn(mid, out)

    def test_cleanup(self):
        with mock.patch("meeting_notes.cleanup.run", return_value={"audio": 2}) as run:
            code, out, _ = self.call("cleanup")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"audio": 2})
        self.assertEqual(run.call_args.args[0], self.cfg)

    def test_watch(self):
        with mock.patch("meeting_notes.watch.main", return_value=0) as main:
            code, _, _ = self.call("watch")
        self.assertEqual(code, 0)
        self.assertEqual(main.call_args.args[0], self.cfg)

    def test_screenpipe(self):
        with mock.patch("meeting_notes.screenpipe.exec_server") as server:
            code, _, _ = self.call("screenpipe")
        self.assertEqual(code, 0)
        self.assertEqual(server.call_args.args[0], self.cfg)


class CheckTest(CliCase):
    def test_all_present(self):
        model = self.root / "model.bin"
        vad = self.root / "vad.bin"
        model.write_bytes(b"m")
        vad.write_bytes(b"v")
        env = env_for(self.root, MEETING_NOTES_MODEL=str(model), MEETING_NOTES_VAD_MODEL=str(vad))
        code, out, _ = self.call("check", environ=env, which=lambda name: f"/bin/{name}")
        self.assertEqual(code, 0)
        self.assertIn("backend: native", out)
        self.assertIn("live: off", out)

    def test_missing_tool(self):
        code, out, _ = self.call("check", which=lambda name: None if name == "whisper-cli" else f"/bin/{name}")
        self.assertEqual(code, 1)
        self.assertIn("missing", out)

    def test_no_secret(self):
        self.cfg.key_path.parent.mkdir(parents=True)
        self.cfg.key_path.write_text("supersecretkey\n")
        env = env_for(self.root, MEETING_NOTES_BACKEND="screenpipe")
        code, out, err = self.call("check", environ=env, which=lambda name: f"/bin/{name}")
        self.assertNotIn("supersecretkey", out + err)
        self.assertIn("backend: screenpipe", out)


class ExitCodeTest(CliCase):
    def test_bad_config(self):
        code, _, err = self.call("status", environ=env_for(self.root, MEETING_NOTES_LIVE="yes"))
        self.assertEqual(code, 2)
        self.assertIn("MEETING_NOTES_LIVE", err)

    def test_unknown_command(self):
        code, _, _ = self.call("frobnicate")
        self.assertEqual(code, 2)

    def test_no_command(self):
        code, _, _ = self.call()
        self.assertEqual(code, 2)

    def test_help(self):
        code, out, _ = self.call("--help")
        self.assertEqual(code, 0)
        self.assertIn("finish", out)


if __name__ == "__main__":
    unittest.main()
