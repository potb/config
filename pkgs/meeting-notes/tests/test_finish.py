import dataclasses
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from pathlib import Path
from unittest import mock

from meeting_notes import finish, slack, state

from .helpers import NOW, TOKEN, FakeCurl, PipelineCase, make_cfg

REAL_CURL = slack._curl


def slack_env(root, **extra):
    cfg = dataclasses.replace(make_cfg(root), **extra)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    (cfg.data_dir / ".env").write_text(f"# c\nSLACK_BOT_TOKEN={TOKEN}\n")
    return cfg


class SlackTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.cfg = slack_env(self.root, slack=True, slack_user="U42", slack_channel="C9")
        self.fake = FakeCurl().patch(self)
        self.file = self.root / "notes.md"
        self.file.write_text("hello notes")

    def test_load_env(self):
        (self.cfg.data_dir / ".env").write_text(f"# c\nSLACK_BOT_TOKEN='{TOKEN}'\nSLACK_USER_ID=U7\n")
        env = slack.load_env(self.cfg)
        self.assertEqual(env["SLACK_BOT_TOKEN"], TOKEN)
        self.assertEqual(env["SLACK_USER_ID"], "U7")

    def test_call_keeps_token_out_of_argv(self):
        slack.call(self.cfg, "auth.test", {})
        argv = self.fake.calls[0]["argv"]
        self.assertEqual(argv[0], "/bin/curl")
        self.assertEqual(argv[1:4], ["-sS", "--config", "-"])
        self.assertNotIn(TOKEN, " ".join(argv))
        self.assertEqual(self.fake.calls[0]["input"], f'header = "Authorization: Bearer {TOKEN}"\n')

    def test_error_never_leaks_token(self):
        fake = FakeCurl({"chat.postMessage": {"ok": False, "error": "channel_not_found"}}).patch(self)
        with self.assertRaises(slack.SlackError) as ctx:
            slack.call(self.cfg, "chat.postMessage", {"channel": "C1"})
        self.assertEqual(str(ctx.exception), "chat.postMessage failed: channel_not_found")
        self.assertNotIn(TOKEN, str(ctx.exception))
        fake.assert_no_token(self)

    def test_curl_failure_never_leaks_token(self):
        FakeCurl(curl_code=7).patch(self)
        with self.assertRaises(slack.SlackError) as ctx:
            slack.call(self.cfg, "auth.test", {})
        self.assertEqual(str(ctx.exception), "curl exited 7")

    def test_missing_curl(self):
        with mock.patch.object(slack, "_curl", REAL_CURL):
            with self.assertRaises(slack.SlackError) as ctx:
                slack.call(self.cfg, "x", {}, which=lambda n: None)
        self.assertEqual(str(ctx.exception), "curl not found in PATH")

    def test_missing_token(self):
        (self.cfg.data_dir / ".env").write_text("SLACK_USER_ID=U1\n")
        with self.assertRaises(slack.SlackError) as ctx:
            slack.call(self.cfg, "auth.test", {})
        self.assertIn("SLACK_BOT_TOKEN missing", str(ctx.exception))

    def test_token_file_wins_over_env_file(self):
        secret = self.cfg.data_dir / "token"
        secret.write_text("xoxb-from-file\n")
        cfg = dataclasses.replace(self.cfg, slack_token_file=secret)
        self.assertEqual(slack._token(cfg), "xoxb-from-file")

    def test_unreadable_token_file_falls_back_to_env_file(self):
        cfg = dataclasses.replace(self.cfg, slack_token_file=self.cfg.data_dir / "missing")
        self.assertEqual(slack._token(cfg), slack._token(self.cfg))

    def test_empty_token_file_and_no_env_is_missing(self):
        secret = self.cfg.data_dir / "token"
        secret.write_text("\n")
        (self.cfg.data_dir / ".env").write_text("SLACK_USER_ID=U1\n")
        cfg = dataclasses.replace(self.cfg, slack_token_file=secret)
        with self.assertRaises(slack.SlackError) as ctx:
            slack.call(cfg, "auth.test", {})
        self.assertIn("SLACK_BOT_TOKEN missing", str(ctx.exception))

    def test_malformed_token_rejected(self):
        (self.cfg.data_dir / ".env").write_text('SLACK_BOT_TOKEN=abc"def\n')
        with self.assertRaises(slack.SlackError):
            slack.call(self.cfg, "auth.test", {})
        self.assertEqual(self.fake.calls, [])

    def test_form_call_urlencodes_payload(self):
        slack.call(self.cfg, "files.getUploadURLExternal", {"filename": "a b.md", "length": 3}, form=True)
        argv = self.fake.calls[0]["argv"]
        self.assertIn("Content-Type: application/x-www-form-urlencoded", argv)
        self.assertEqual(self.fake.calls[0]["payload"], {"filename": "a b.md", "length": "3"})

    def test_user_id_prefers_config_then_env_file(self):
        self.assertEqual(slack.user_id(self.cfg), "U42")
        legacy = dataclasses.replace(self.cfg, slack_user="")
        (legacy.data_dir / ".env").write_text(f"SLACK_BOT_TOKEN={TOKEN}\nSLACK_USER_ID=U7\n")
        self.assertEqual(slack.user_id(legacy), "U7")
        (legacy.data_dir / ".env").write_text(f"SLACK_BOT_TOKEN={TOKEN}\n")
        with self.assertRaises(slack.SlackError):
            slack.user_id(legacy)

    def test_destination(self):
        self.assertEqual(slack.destination(self.cfg), "U42")
        channel = dataclasses.replace(self.cfg, slack_post_to="channel")
        self.assertEqual(slack.destination(channel), "C9")
        self.assertEqual(slack.destination(channel, sensitive=True), "U42")
        with self.assertRaises(slack.SlackError):
            slack.destination(dataclasses.replace(channel, slack_channel=""))

    def test_allowed(self):
        channel = dataclasses.replace(self.cfg, slack_post_to="channel")
        self.assertTrue(slack.allowed(self.cfg, False))
        self.assertFalse(slack.allowed(self.cfg, True))
        self.assertTrue(slack.allowed(channel, False))
        self.assertTrue(slack.allowed(channel, True))
        self.assertFalse(slack.allowed(dataclasses.replace(channel, slack=False), False))

    def test_header_with_and_without_duration(self):
        meeting = {"start": "2026-05-20T10:00:00Z", "end": "2026-05-20T10:47:20Z"}
        self.assertEqual(slack.header("Sync", meeting), "*Sync* · 47 min")
        self.assertEqual(slack.header("Sync", {"start": meeting["start"], "end": None}), "*Sync*")
        self.assertEqual(slack.header("Sync", None), "*Sync*")
        self.assertEqual(slack.header("Sync", {"start": meeting["end"], "end": meeting["start"]}), "*Sync*")
        self.assertEqual(slack.header("Sync", {"start": "bad", "end": "worse"}), "*Sync*")
        short = {"start": meeting["start"], "end": "2026-05-20T10:00:10Z"}
        self.assertEqual(slack.header("Sync", short), "*Sync* · 1 min")

    def test_header_escapes_mrkdwn_control_characters(self):
        self.assertEqual(slack.header("<!channel> & <!here>"), "*&lt;!channel&gt; &amp; &lt;!here&gt;*")
        self.assertEqual(slack.header("<@U1|x>"), "*&lt;@U1|x&gt;*")
        self.assertEqual(slack.header("a &lt; b"), "*a &amp;lt; b*")

    def test_is_dm(self):
        self.assertTrue(slack.is_dm(self.cfg, "D100"))
        self.assertFalse(slack.is_dm(self.cfg, "C9"))
        self.assertFalse(slack.is_dm(dataclasses.replace(self.cfg, slack_channel="D100"), "D100"))

    def test_file_title(self):
        self.assertEqual(slack.file_title("Sync", "Notes"), "Sync – Notes")

    def test_post_header_returns_thread_and_dm_channel(self):
        ts, channel = slack.post_header(self.cfg, "Sync")
        self.assertEqual((ts, channel), ("1700000000.000100", "D100"))
        self.assertEqual(self.fake.payloads("chat.postMessage"), [{"channel": "U42", "text": "*Sync*"}])

    def test_post_header_without_ts_fails(self):
        FakeCurl({"chat.postMessage": {"ok": True}}).patch(self)
        with self.assertRaises(slack.SlackError):
            slack.post_header(self.cfg, "Sync")

    def test_upload_sequence(self):
        slack.upload(self.cfg, "D100", "1.5", self.file, "Sync – Notes")
        self.assertEqual(
            self.fake.methods(),
            ["files.getUploadURLExternal", "files.completeUploadExternal"],
        )
        self.assertEqual(
            self.fake.payloads("files.getUploadURLExternal"),
            [{"filename": "notes.md", "length": str(len("hello notes"))}],
        )
        self.assertEqual(len(self.fake.uploads), 1)
        self.assertEqual(self.fake.uploads[0]["url"], "https://files.slack.com/upload/v1/1")
        self.assertEqual(self.fake.uploads[0]["body"], b"hello notes")
        self.assertEqual(
            self.fake.payloads("files.completeUploadExternal"),
            [{"files": [{"id": "F1", "title": "Sync – Notes"}], "channel_id": "D100", "thread_ts": "1.5"}],
        )
        self.fake.assert_no_token(self)

    def test_upload_bytes_post_needs_no_token_or_config(self):
        slack.upload(self.cfg, "D100", "1.5", self.file, "t")
        post = self.fake.uploads[0]["argv"]
        self.assertNotIn("--config", post)
        self.assertIsNone(self.fake.inputs[1])
        self.assertNotIn("Authorization", " ".join(post))

    def test_upload_without_thread_omits_thread_ts(self):
        slack.upload(self.cfg, "D100", None, self.file, "t")
        self.assertNotIn("thread_ts", self.fake.payloads("files.completeUploadExternal")[0])

    def test_upload_rejects_non_https_url(self):
        FakeCurl({"files.getUploadURLExternal": {"ok": True, "upload_url": "http://x/y", "file_id": "F1"}}).patch(self)
        with self.assertRaises(slack.SlackError):
            slack.upload(self.cfg, "D100", "1.5", self.file, "t")

    def test_upload_byte_post_failure(self):
        FakeCurl(upload_code=22).patch(self)
        with self.assertRaises(slack.SlackError) as ctx:
            slack.upload(self.cfg, "D100", "1.5", self.file, "t")
        self.assertIn("curl exited 22", str(ctx.exception))
        self.assertNotIn(TOKEN, str(ctx.exception))

    def test_upload_slot_error(self):
        FakeCurl({"files.getUploadURLExternal": {"ok": False, "error": "missing_scope"}}).patch(self)
        with self.assertRaises(slack.SlackError) as ctx:
            slack.upload(self.cfg, "D100", "1.5", self.file, "t")
        self.assertIn("missing_scope", str(ctx.exception))

    def test_check_dm_mode(self):
        lines = slack.check(self.cfg)
        self.assertEqual(self.fake.methods(), ["auth.test", "conversations.open"])
        self.assertEqual(self.fake.payloads("conversations.open"), [{"users": "U42"}])
        self.assertIn("team: Acme (T1)", lines)
        self.assertIn("bot: notesbot (UBOT)", lines)
        self.assertIn("dm: D100 with U42", lines)
        self.assertNotIn(TOKEN, "\n".join(lines))

    def test_check_channel_mode_joins(self):
        channel = dataclasses.replace(self.cfg, slack_post_to="channel")
        lines = slack.check(channel)
        self.assertEqual(self.fake.methods(), ["auth.test", "conversations.join", "conversations.open"])
        self.assertEqual(self.fake.payloads("conversations.join"), [{"channel": "C9"}])
        self.assertIn("channel: meetings (C9)", lines)
        self.fake.assert_no_token(self)

    def test_check_failure_raises_slack_error(self):
        FakeCurl({"conversations.join": {"ok": False, "error": "method_not_supported_for_channel_type"}}).patch(self)
        channel = dataclasses.replace(self.cfg, slack_post_to="channel")
        with self.assertRaises(slack.SlackError) as ctx:
            slack.check(channel)
        self.assertIn("method_not_supported_for_channel_type", str(ctx.exception))


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

    def slack_cfg(self, **extra):
        return slack_env(self.root, slack=True, slack_user="U1", slack_channel="C1", **extra)

    def test_sensitive_dm_mode_never_posts_to_slack(self):
        cfg = self.slack_cfg()
        fake = FakeCurl().patch(self)
        self.run_main("--stage", "notes", "--notes", str(self.notes), "--sensitive", "legal", cfg=cfg)
        self.assertEqual(self.status(), state.NOTES_SAVED)
        self.run_main("--stage", "transcript", "--transcript", str(self.transcript), cfg=cfg)
        self.assertEqual(fake.argvs, [])
        self.assertEqual(self.status(), state.DONE)

    def test_sensitive_whole_dm_mode_never_posts_to_slack(self):
        cfg = self.slack_cfg()
        fake = FakeCurl().patch(self)
        self.assertEqual(self.run_main("--notes", str(self.notes), "--sensitive", cfg=cfg), 0)
        self.assertEqual(fake.argvs, [])
        self.assertEqual(self.status(), state.DONE)

    def test_sensitive_with_empty_reason_dm_mode_never_posts_to_slack(self):
        cfg = self.slack_cfg()
        fake = FakeCurl().patch(self)
        self.run_main("--stage", "notes", "--notes", str(self.notes), "--sensitive", "", cfg=cfg)
        self.assertEqual(self.status(), state.NOTES_SAVED)
        self.assertTrue(self.load()["processed"][self.mid]["sensitive"])
        self.run_main("--stage", "transcript", "--transcript", str(self.transcript), cfg=cfg)
        self.assertEqual(fake.argvs, [])
        self.assertEqual(self.status(), state.DONE)

    def test_sensitive_whole_with_blank_reason_dm_mode_never_posts_to_slack(self):
        cfg = self.slack_cfg()
        fake = FakeCurl().patch(self)
        self.assertEqual(self.run_main("--notes", str(self.notes), "--sensitive", "  ", cfg=cfg), 0)
        self.assertEqual(fake.argvs, [])
        self.assertTrue(self.load()["processed"][self.mid]["sensitive"])

    def test_sensitive_with_empty_reason_channel_mode_goes_to_dm(self):
        cfg = self.slack_cfg(slack_post_to="channel")
        fake = FakeCurl().patch(self)
        self.run_main("--stage", "notes", "--notes", str(self.notes), "--sensitive", "", cfg=cfg)
        self.assertEqual(fake.payloads("chat.postMessage")[0]["channel"], "U1")

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

    def test_dm_mode_notes_then_transcript(self):
        cfg = self.slack_cfg()
        fake = FakeCurl().patch(self)
        self.assertEqual(self.run_main("--stage", "notes", "--notes", str(self.notes), cfg=cfg), 0)
        self.assertEqual(
            fake.payloads("chat.postMessage"), [{"channel": "U1", "text": "*Sync* · 30 min"}]
        )
        self.assertEqual(self.status(), state.NOTES_POSTED)
        info = self.load()["processed"][self.mid]
        self.assertEqual(info["slack_ts"], "1700000000.000100")
        self.assertEqual(info["slack_channel"], "D100")
        self.assertEqual(
            fake.payloads("files.getUploadURLExternal"),
            [{"filename": "notes.md", "length": str(len("notes"))}],
        )
        self.assertEqual(fake.uploads[0]["body"], b"notes")
        self.assertEqual(
            fake.payloads("files.completeUploadExternal"),
            [
                {
                    "files": [{"id": "F1", "title": "Sync – Notes"}],
                    "channel_id": "D100",
                    "thread_ts": "1700000000.000100",
                }
            ],
        )
        self.assertEqual(
            self.run_main("--stage", "transcript", "--transcript", str(self.transcript), cfg=cfg), 0
        )
        self.assertEqual(self.status(), state.POSTED)
        self.assertEqual(len(fake.payloads("chat.postMessage")), 1)
        last = fake.payloads("files.completeUploadExternal")[1]
        self.assertEqual(
            last,
            {
                "files": [{"id": "F2", "title": "Sync – Transcript"}],
                "channel_id": "D100",
                "thread_ts": "1700000000.000100",
            },
        )
        self.assertEqual(fake.payloads("files.getUploadURLExternal")[1]["filename"], "transcript.md")
        self.assertEqual(fake.uploads[1]["body"], b"transcript")
        fake.assert_no_token(self)

    def test_title_argument_names_header_and_files(self):
        cfg = self.slack_cfg()
        fake = FakeCurl().patch(self)
        self.run_main("--stage", "notes", "--notes", str(self.notes), "--title", "Board", cfg=cfg)
        self.assertEqual(fake.payloads("chat.postMessage")[0]["text"], "*Board* · 30 min")
        self.assertEqual(fake.payloads("files.completeUploadExternal")[0]["files"][0]["title"], "Board – Notes")

    def test_header_without_end_has_no_duration(self):
        open_meeting = self.add(NOW - timedelta(hours=1), None, title="Open")
        cfg = self.slack_cfg()
        fake = FakeCurl().patch(self)
        self.run_main("--stage", "notes", "--notes", str(self.notes), cfg=cfg, mid=open_meeting)
        self.assertEqual(fake.payloads("chat.postMessage")[0]["text"], "*Open*")

    def test_channel_mode_posts_to_channel(self):
        cfg = self.slack_cfg(slack_post_to="channel")
        fake = FakeCurl().patch(self)
        self.run_main("--stage", "notes", "--notes", str(self.notes), cfg=cfg)
        self.assertEqual(fake.payloads("chat.postMessage")[0]["channel"], "C1")
        self.assertEqual(fake.payloads("files.completeUploadExternal")[0]["channel_id"], "C1")
        info = self.load()["processed"][self.mid]
        self.assertEqual(info["slack_channel"], "C1")
        self.run_main("--stage", "transcript", "--transcript", str(self.transcript), cfg=cfg)
        self.assertEqual(fake.payloads("files.completeUploadExternal")[1]["channel_id"], "C1")
        self.assertEqual(self.status(), state.POSTED)

    def test_sensitive_channel_mode_goes_to_dm_only(self):
        cfg = self.slack_cfg(slack_post_to="channel")
        fake = FakeCurl().patch(self)
        self.run_main("--stage", "notes", "--notes", str(self.notes), "--sensitive", "legal", cfg=cfg)
        self.assertEqual(fake.payloads("chat.postMessage")[0]["channel"], "U1")
        self.assertEqual(fake.payloads("files.completeUploadExternal")[0]["channel_id"], "D100")
        self.assertEqual(self.status(), state.NOTES_POSTED)
        info = self.load()["processed"][self.mid]
        self.assertEqual(info["sensitive"], "legal")
        self.assertEqual(info["slack_channel"], "D100")
        self.run_main("--stage", "transcript", "--transcript", str(self.transcript), cfg=cfg)
        self.assertEqual(self.status(), state.POSTED)
        self.assertEqual(fake.payloads("files.completeUploadExternal")[1]["channel_id"], "D100")
        for call in fake.calls:
            self.assertNotIn("C1", [str(v) for v in call["payload"].values()])

    def test_sensitive_flag_from_notes_stage_holds_for_transcript(self):
        cfg = self.slack_cfg(slack_post_to="channel")
        fake = FakeCurl().patch(self)
        self.run_main("--stage", "notes", "--notes", str(self.notes), "--sensitive", "legal", cfg=cfg)
        info = self.load()["processed"][self.mid]
        del info["slack_ts"]
        del info["slack_channel"]
        with state.locked(cfg.state_path) as st:
            st["processed"][self.mid] = info
        fake.calls.clear()
        self.run_main("--stage", "transcript", "--transcript", str(self.transcript), cfg=cfg)
        self.assertEqual(fake.payloads("chat.postMessage")[0]["channel"], "U1")
        self.assertEqual(self.status(), state.DM_ONLY)

    def test_sensitive_whole_channel_mode_goes_to_dm(self):
        cfg = self.slack_cfg(slack_post_to="channel")
        fake = FakeCurl().patch(self)
        self.assertEqual(self.run_main("--notes", str(self.notes), "--sensitive", "hr", cfg=cfg), 0)
        self.assertEqual(fake.payloads("chat.postMessage")[0]["channel"], "U1")
        self.assertEqual(fake.payloads("files.completeUploadExternal")[0]["channel_id"], "D100")
        self.assertEqual(self.status(), state.POSTED)

    def test_transcript_fallback_without_slack_ts(self):
        self.run_main("--stage", "notes", "--notes", str(self.notes))
        self.assertEqual(self.status(), state.NOTES_SAVED)
        cfg = self.slack_cfg()
        fake = FakeCurl().patch(self)
        code = self.run_main("--stage", "transcript", "--transcript", str(self.transcript), cfg=cfg)
        self.assertEqual(code, 0)
        self.assertEqual(
            fake.payloads("chat.postMessage"), [{"channel": "U1", "text": "*Sync* · 30 min"}]
        )
        complete = fake.payloads("files.completeUploadExternal")
        self.assertEqual(len(complete), 1)
        self.assertEqual(complete[0]["thread_ts"], "1700000000.000100")
        self.assertEqual(complete[0]["channel_id"], "D100")
        self.assertEqual(complete[0]["files"][0]["title"], "Sync – Transcript")
        self.assertEqual(self.status(), state.DM_ONLY)

    def test_transcript_fallback_in_channel_mode_posts_header_to_channel(self):
        self.run_main("--stage", "notes", "--notes", str(self.notes))
        cfg = self.slack_cfg(slack_post_to="channel")
        fake = FakeCurl().patch(self)
        self.run_main("--stage", "transcript", "--transcript", str(self.transcript), cfg=cfg)
        self.assertEqual(fake.payloads("chat.postMessage")[0]["channel"], "C1")
        self.assertEqual(self.status(), state.DM_ONLY)

    def test_whole_posts_header_and_notes(self):
        cfg = self.slack_cfg()
        fake = FakeCurl().patch(self)
        self.assertEqual(self.run_main("--notes", str(self.notes), cfg=cfg), 0)
        self.assertEqual(
            fake.methods(),
            [
                "chat.postMessage",
                "files.getUploadURLExternal",
                "files.completeUploadExternal",
            ],
        )
        self.assertEqual(self.status(), state.POSTED)

    def test_slack_failure_leaves_state_untouched_and_hides_token(self):
        cfg = self.slack_cfg()
        fake = FakeCurl({"files.completeUploadExternal": {"ok": False, "error": "not_in_channel"}}).patch(self)
        sink = io.StringIO()
        with redirect_stdout(sink), redirect_stderr(sink):
            code = finish.main(
                ["--id", self.mid, "--stage", "notes", "--notes", str(self.notes)], cfg=cfg
            )
        self.assertEqual(code, 1)
        self.assertIn("not_in_channel", sink.getvalue())
        self.assertNotIn(TOKEN, sink.getvalue())
        self.assertIsNone(self.status())
        fake.assert_no_token(self)

    def failing_upload(self):
        return FakeCurl({"files.completeUploadExternal": {"ok": False, "error": "not_in_channel"}}).patch(self)

    def test_notes_retry_after_failed_upload_reuses_header(self):
        cfg = self.slack_cfg()
        first = self.failing_upload()
        args = ("--stage", "notes", "--notes", str(self.notes))
        self.assertEqual(self.run_main(*args, cfg=cfg), 1)
        self.assertEqual(len(first.payloads("chat.postMessage")), 1)
        self.assertIsNone(self.status())
        saved = self.load()["slack_threads"][self.mid]
        self.assertEqual(saved["slack_ts"], "1700000000.000100")
        self.assertEqual(saved["slack_channel"], "D100")
        second = FakeCurl().patch(self)
        self.assertEqual(self.run_main(*args, cfg=cfg), 0)
        self.assertEqual(second.payloads("chat.postMessage"), [])
        complete = second.payloads("files.completeUploadExternal")
        self.assertEqual(len(complete), 1)
        self.assertEqual(complete[0]["thread_ts"], "1700000000.000100")
        self.assertEqual(complete[0]["channel_id"], "D100")
        self.assertEqual(self.status(), state.NOTES_POSTED)
        info = self.load()["processed"][self.mid]
        self.assertEqual(info["slack_files"], ["notes"])
        self.assertNotIn("slack_threads", self.load())

    def test_whole_retry_after_failed_upload_reuses_header(self):
        cfg = self.slack_cfg()
        self.failing_upload()
        self.assertEqual(self.run_main("--notes", str(self.notes), cfg=cfg), 1)
        second = FakeCurl().patch(self)
        self.assertEqual(self.run_main("--notes", str(self.notes), cfg=cfg), 0)
        self.assertEqual(second.payloads("chat.postMessage"), [])
        self.assertEqual(len(second.payloads("files.completeUploadExternal")), 1)
        self.assertEqual(self.status(), state.POSTED)
        self.assertNotIn("slack_threads", self.load())

    def test_transcript_fallback_retry_after_failed_upload_reuses_header(self):
        self.run_main("--stage", "notes", "--notes", str(self.notes))
        cfg = self.slack_cfg()
        first = self.failing_upload()
        args = ("--stage", "transcript", "--transcript", str(self.transcript))
        self.assertEqual(self.run_main(*args, cfg=cfg), 1)
        self.assertEqual(len(first.payloads("chat.postMessage")), 1)
        self.assertEqual(self.status(), state.NOTES_SAVED)
        second = FakeCurl().patch(self)
        self.assertEqual(self.run_main(*args, cfg=cfg), 0)
        self.assertEqual(second.payloads("chat.postMessage"), [])
        self.assertEqual(
            second.payloads("files.completeUploadExternal")[0]["thread_ts"], "1700000000.000100"
        )
        self.assertEqual(self.status(), state.DM_ONLY)
        self.assertNotIn("slack_threads", self.load())

    def test_retry_uploads_only_missing_files(self):
        cfg = self.slack_cfg()
        with state.locked(cfg.state_path) as st:
            state.save_thread(
                cfg.state_path,
                st,
                self.mid,
                {"slack_ts": "5.5", "slack_channel": "D100", "slack_files": ["notes"]},
            )
        fake = FakeCurl().patch(self)
        self.assertEqual(self.run_main("--stage", "notes", "--notes", str(self.notes), cfg=cfg), 0)
        self.assertEqual(fake.argvs, [])
        info = self.load()["processed"][self.mid]
        self.assertEqual(info["slack_ts"], "5.5")
        self.assertEqual(info["slack_files"], ["notes"])
        self.assertEqual(self.status(), state.NOTES_POSTED)

    def test_sensitive_transcript_never_uploads_into_stored_channel_thread(self):
        cfg = self.slack_cfg(slack_post_to="channel")
        fake = FakeCurl().patch(self)
        self.run_main("--stage", "notes", "--notes", str(self.notes), cfg=cfg)
        self.assertEqual(self.load()["processed"][self.mid]["slack_channel"], "C1")
        fake.calls.clear()
        fake.uploads.clear()
        code = self.run_main(
            "--stage", "transcript", "--transcript", str(self.transcript), "--sensitive", "legal", cfg=cfg
        )
        self.assertEqual(code, 0)
        self.assertEqual(fake.payloads("chat.postMessage"), [{"channel": "U1", "text": "*Sync* · 30 min"}])
        complete = fake.payloads("files.completeUploadExternal")
        self.assertEqual([call["channel_id"] for call in complete], ["D100"])
        self.assertEqual(self.status(), state.DM_ONLY)
        for call in fake.calls:
            self.assertNotIn("C1", [str(v) for v in call["payload"].values()])

    def test_stored_sensitive_flag_blocks_stored_channel_thread(self):
        cfg = self.slack_cfg(slack_post_to="channel")
        fake = FakeCurl().patch(self)
        self.run_main("--stage", "notes", "--notes", str(self.notes), cfg=cfg)
        with state.locked(cfg.state_path) as st:
            st["processed"][self.mid]["sensitive"] = True
        fake.calls.clear()
        self.run_main("--stage", "transcript", "--transcript", str(self.transcript), cfg=cfg)
        self.assertEqual(fake.payloads("chat.postMessage")[0]["channel"], "U1")
        self.assertEqual(fake.payloads("files.completeUploadExternal")[0]["channel_id"], "D100")

    def test_sensitive_transcript_dm_mode_skips_stored_thread(self):
        cfg = self.slack_cfg()
        fake = FakeCurl().patch(self)
        self.run_main("--stage", "notes", "--notes", str(self.notes), cfg=cfg)
        fake.calls.clear()
        self.run_main(
            "--stage", "transcript", "--transcript", str(self.transcript), "--sensitive", cfg=cfg
        )
        self.assertEqual(fake.calls, [])
        self.assertEqual(self.status(), state.DONE)

    def test_sensitive_retry_does_not_reuse_channel_header(self):
        cfg = self.slack_cfg(slack_post_to="channel")
        self.failing_upload()
        args = ("--stage", "notes", "--notes", str(self.notes))
        self.assertEqual(self.run_main(*args, cfg=cfg), 1)
        second = FakeCurl().patch(self)
        self.assertEqual(self.run_main(*args, "--sensitive", "hr", cfg=cfg), 0)
        self.assertEqual(second.payloads("chat.postMessage")[0]["channel"], "U1")
        self.assertEqual(second.payloads("files.completeUploadExternal")[0]["channel_id"], "D100")

    def test_header_title_is_escaped(self):
        cfg = self.slack_cfg()
        fake = FakeCurl().patch(self)
        self.run_main(
            "--stage", "notes", "--notes", str(self.notes), "--title", "<!channel> a & <@U9>", cfg=cfg
        )
        self.assertEqual(
            fake.payloads("chat.postMessage")[0]["text"], "*&lt;!channel&gt; a &amp; &lt;@U9&gt;* · 30 min"
        )

    def test_dry_run_never_calls_slack(self):
        cfg = self.slack_cfg()
        fake = FakeCurl().patch(self)
        self.run_main("--stage", "notes", "--notes", str(self.notes), "--dry-run", cfg=cfg)
        self.assertEqual(fake.argvs, [])
