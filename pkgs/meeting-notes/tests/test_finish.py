import dataclasses
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from meeting_notes import finish, slack, state

from .helpers import NOW, PipelineCase, make_cfg


def reply(payload):
    def run(argv, **kw):
        run.argv = argv
        run.input = kw.get("input")
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    return run


class SlackTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = make_cfg(Path(tmp.name))
        self.cfg.data_dir.mkdir(parents=True)
        (self.cfg.data_dir / ".env").write_text(
            "# c\nSLACK_BOT_TOKEN=xoxb-secret\nSLACK_USER_ID='U42'\n"
        )

    def test_load_env(self):
        env = slack.load_env(self.cfg)
        self.assertEqual(env["SLACK_BOT_TOKEN"], "xoxb-secret")
        self.assertEqual(env["SLACK_USER_ID"], "U42")

    def test_dm_goes_to_user_id_and_hides_token(self):
        run = reply({"ok": True})
        slack.dm(self.cfg, "hello", run=run, which=lambda n: "/bin/curl")
        self.assertEqual(run.argv[0], "/bin/curl")
        self.assertNotIn("xoxb-secret", " ".join(run.argv))
        self.assertIn("xoxb-secret", run.input)
        self.assertIn('"channel": "U42"', " ".join(run.argv))

    def test_error_never_leaks_token(self):
        run = reply({"ok": False, "error": "bad"})
        with self.assertRaises(slack.SlackError) as ctx:
            slack.call(self.cfg, "chat.postMessage", {}, run=run, which=lambda n: "/bin/curl")
        self.assertNotIn("xoxb-secret", str(ctx.exception))

    def test_missing_curl(self):
        with self.assertRaises(slack.SlackError):
            slack.call(self.cfg, "x", {}, run=None, which=lambda n: None)


class FinishTest(PipelineCase):
    def setUp(self):
        super().setUp()
        self.mid = self.add(NOW - timedelta(hours=1), NOW - timedelta(minutes=30))
        self.notes = self.root / "Meetings" / "x" / "notes.md"
        self.notes.parent.mkdir(parents=True)
        self.notes.write_text("notes")
        self.transcript = self.notes.parent / "transcript.md"
        self.transcript.write_text("transcript")

    def run_main(self, *args, cfg=None, mid=None):
        sink = io.StringIO()
        with redirect_stdout(sink), redirect_stderr(sink):
            return finish.main(["--id", mid or self.mid, *args], cfg=cfg or self.cfg)

    def status(self):
        return (self.load()["processed"].get(self.mid) or {}).get("status")

    def test_stage_notes_marks_notes_saved(self):
        self.assertEqual(self.run_main("--stage", "notes", "--notes", str(self.notes)), 0)
        info = self.load()["processed"][self.mid]
        self.assertEqual(info["status"], state.NOTES_SAVED)
        self.assertEqual(info["dir"], str(self.notes.parent))
        self.assertNotIn("sensitive", info)

    def test_stage_notes_sensitive(self):
        self.run_main("--stage", "notes", "--notes", str(self.notes), "--sensitive")
        self.assertTrue(self.load()["processed"][self.mid]["sensitive"])

    def test_transcript_requires_notes_saved(self):
        code = self.run_main("--stage", "transcript", "--transcript", str(self.transcript))
        self.assertNotEqual(code, 0)
        self.assertIsNone(self.status())

    def test_sequence_notes_notes_transcript(self):
        self.run_main("--stage", "notes", "--notes", str(self.notes))
        self.assertEqual(self.status(), state.NOTES_SAVED)
        before = self.load()
        self.assertEqual(self.run_main("--stage", "notes", "--notes", str(self.notes)), 0)
        self.assertEqual(self.load(), before)
        self.assertEqual(
            self.run_main("--stage", "transcript", "--transcript", str(self.transcript)), 0
        )
        self.assertEqual(self.status(), state.DONE)

    def test_transcript_stage_rerun_writes_nothing(self):
        self.run_main("--stage", "notes", "--notes", str(self.notes))
        self.run_main("--stage", "transcript", "--transcript", str(self.transcript))
        before = self.load()
        self.assertEqual(
            self.run_main("--stage", "transcript", "--transcript", str(self.transcript)), 0
        )
        self.assertEqual(self.load(), before)

    def test_notes_stage_after_done_writes_nothing(self):
        self.run_main("--notes", str(self.notes))
        before = self.load()
        self.assertEqual(self.run_main("--stage", "notes", "--notes", str(self.notes)), 0)
        self.assertEqual(self.load(), before)

    def test_no_stage_marks_done(self):
        self.assertEqual(self.run_main("--notes", str(self.notes)), 0)
        self.assertEqual(self.status(), state.DONE)

    def test_skip(self):
        self.assertEqual(self.run_main("--skip"), 0)
        self.assertEqual(self.status(), state.SKIPPED)

    def test_skip_with_reason(self):
        self.assertEqual(self.run_main("--skip", "personal"), 0)
        info = self.load()["processed"][self.mid]
        self.assertEqual(info["status"], state.SKIPPED)
        self.assertEqual(info["skip_reason"], "personal")

    def test_sensitive_with_reason(self):
        code = self.run_main("--stage", "notes", "--notes", str(self.notes), "--sensitive", "cap table")
        self.assertEqual(code, 0)
        self.assertEqual(self.load()["processed"][self.mid]["sensitive"], "cap table")
        code = self.run_main("--stage", "transcript", "--transcript", str(self.transcript), "--sensitive", "cap table")
        self.assertEqual(code, 0)
        self.assertEqual(self.status(), state.DONE)

    def slack_cfg(self):
        cfg = dataclasses.replace(self.cfg, slack=True)
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        (cfg.data_dir / ".env").write_text("SLACK_USER_ID=U1\n")
        return cfg

    def test_sensitive_never_posts_to_slack(self):
        cfg = self.slack_cfg()
        dm = mock.Mock(return_value={"ok": True, "ts": "1.2", "channel": "D1"})
        with mock.patch.object(slack, "dm", dm):
            self.run_main("--stage", "notes", "--notes", str(self.notes), "--sensitive", "legal", cfg=cfg)
            self.assertEqual(self.status(), state.NOTES_SAVED)
            self.run_main("--stage", "transcript", "--transcript", str(self.transcript), cfg=cfg)
        dm.assert_not_called()
        self.assertEqual(self.status(), state.DONE)

    def test_sensitive_whole_never_posts_to_slack(self):
        cfg = self.slack_cfg()
        dm = mock.Mock(return_value={"ok": True})
        with mock.patch.object(slack, "dm", dm):
            self.assertEqual(self.run_main("--notes", str(self.notes), "--sensitive", cfg=cfg), 0)
        dm.assert_not_called()
        self.assertEqual(self.status(), state.DONE)

    def test_sensitive_with_empty_reason_never_posts_to_slack(self):
        cfg = self.slack_cfg()
        dm = mock.Mock(return_value={"ok": True, "ts": "1.2", "channel": "D1"})
        with mock.patch.object(slack, "dm", dm):
            self.run_main("--stage", "notes", "--notes", str(self.notes), "--sensitive", "", cfg=cfg)
            self.assertEqual(self.status(), state.NOTES_SAVED)
            self.assertTrue(self.load()["processed"][self.mid]["sensitive"])
            self.run_main("--stage", "transcript", "--transcript", str(self.transcript), cfg=cfg)
        dm.assert_not_called()
        self.assertEqual(self.status(), state.DONE)

    def test_sensitive_whole_with_blank_reason_never_posts_to_slack(self):
        cfg = self.slack_cfg()
        dm = mock.Mock(return_value={"ok": True})
        with mock.patch.object(slack, "dm", dm):
            self.assertEqual(self.run_main("--notes", str(self.notes), "--sensitive", "  ", cfg=cfg), 0)
        dm.assert_not_called()
        self.assertTrue(self.load()["processed"][self.mid]["sensitive"])

    def test_skip_with_empty_reason_skips(self):
        self.assertEqual(self.run_main("--skip", ""), 0)
        self.assertEqual(self.status(), state.SKIPPED)

    def test_notes_outside_meetings_rejected(self):
        outside = self.root / "secret.txt"
        outside.write_text("secret")
        self.assertNotEqual(self.run_main("--stage", "notes", "--notes", str(outside)), 0)
        self.assertIsNone(self.status())

    def test_transcript_outside_meetings_rejected(self):
        self.run_main("--stage", "notes", "--notes", str(self.notes))
        outside = self.root / "authorized_keys"
        outside.write_text("key")
        code = self.run_main("--stage", "transcript", "--transcript", str(outside))
        self.assertNotEqual(code, 0)
        self.assertFalse((self.notes.parent / "authorized_keys").exists())
        self.assertEqual(self.status(), state.NOTES_SAVED)

    def test_notes_under_data_meetings_accepted(self):
        notes = self.cfg.data_dir / "meetings" / "y" / "notes.md"
        notes.parent.mkdir(parents=True)
        notes.write_text("notes")
        self.assertEqual(self.run_main("--stage", "notes", "--notes", str(notes)), 0)
        self.assertEqual(self.status(), state.NOTES_SAVED)

    def test_dry_run_writes_nothing(self):
        before = self.load()
        code = self.run_main("--stage", "notes", "--notes", str(self.notes), "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(self.load(), before)

    def test_unknown_meeting(self):
        self.assertNotEqual(self.run_main("--skip", mid="nope"), 0)

    def test_slack_disabled_never_calls_slack(self):
        boom = mock.Mock(side_effect=AssertionError("slack called"))
        with mock.patch.object(slack, "call", boom):
            self.run_main("--stage", "notes", "--notes", str(self.notes))
            self.run_main("--stage", "transcript", "--transcript", str(self.transcript))
        boom.assert_not_called()
        self.assertEqual(self.status(), state.DONE)

    def test_slack_enabled_path(self):
        cfg = dataclasses.replace(self.cfg, slack=True)
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        (cfg.data_dir / ".env").write_text("SLACK_USER_ID=U1\n")
        calls = []

        def fake(cfg, method, payload, **kw):
            calls.append(method)
            return {"ok": True, "ts": "1.2", "channel": "D1"}

        with mock.patch.object(slack, "call", fake):
            self.run_main("--stage", "notes", "--notes", str(self.notes), cfg=cfg)
            self.assertEqual(self.status(), state.NOTES_POSTED)
            self.run_main(
                "--stage", "transcript", "--transcript", str(self.transcript), cfg=cfg
            )
        self.assertEqual(self.status(), state.POSTED)
        self.assertTrue(calls)
