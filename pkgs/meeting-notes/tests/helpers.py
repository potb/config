import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import parse_qs

from meeting_notes import slack, state
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


TOKEN = "xoxb-secret-token"
SLACK_API = "https://slack.com/api/"


class FakeCurl:
    def __init__(self, replies=None, curl_code=0, upload_code=0):
        self.replies = replies or {}
        self.curl_code = curl_code
        self.upload_code = upload_code
        self.calls = []
        self.uploads = []
        self.argvs = []
        self.inputs = []
        self.files = 0

    def methods(self):
        return [call["method"] for call in self.calls]

    def payloads(self, method):
        return [call["payload"] for call in self.calls if call["method"] == method]

    def _payload(self, argv):
        body = argv[argv.index("-d") + 1]
        header = argv[argv.index("-H") + 1]
        if "json" in header:
            return json.loads(body)
        return {key: values[0] for key, values in parse_qs(body).items()}

    def _default(self, method, payload):
        if method == "auth.test":
            return {"ok": True, "team": "Acme", "team_id": "T1", "user": "notesbot", "user_id": "UBOT", "bot_id": "B1"}
        if method == "chat.postMessage":
            channel = payload["channel"]
            return {"ok": True, "ts": "1700000000.000100", "channel": "D100" if channel.startswith("U") else channel}
        if method == "files.getUploadURLExternal":
            self.files += 1
            return {"ok": True, "upload_url": f"https://files.slack.com/upload/v1/{self.files}", "file_id": f"F{self.files}"}
        if method == "files.completeUploadExternal":
            return {"ok": True, "files": payload["files"]}
        if method == "conversations.join":
            return {"ok": True, "channel": {"id": payload["channel"], "name": "meetings"}}
        if method == "conversations.open":
            return {"ok": True, "channel": {"id": "D100"}}
        return {"ok": True}

    def __call__(self, argv, input=None):
        self.argvs.append(list(argv))
        self.inputs.append(input)
        url = argv[-1]
        if not url.startswith(SLACK_API):
            body = Path(argv[argv.index("--data-binary") + 1][1:]).read_bytes()
            self.uploads.append({"url": url, "body": body, "argv": list(argv)})
            return SimpleNamespace(returncode=self.upload_code, stdout="OK", stderr="")
        method = url[len(SLACK_API):]
        payload = self._payload(argv)
        self.calls.append({"method": method, "payload": payload, "argv": list(argv), "input": input})
        if self.curl_code:
            return SimpleNamespace(returncode=self.curl_code, stdout="", stderr="")
        reply = self.replies.get(method)
        if reply is None:
            reply = self._default(method, payload)
        elif callable(reply):
            reply = reply(payload)
        return SimpleNamespace(returncode=0, stdout=json.dumps(reply), stderr="")

    def patch(self, test):
        runner = mock.patch.object(slack, "_run", self)
        finder = mock.patch.object(slack, "_curl", lambda which: "/bin/curl")
        runner.start()
        finder.start()
        test.addCleanup(runner.stop)
        test.addCleanup(finder.stop)
        return self

    def assert_no_token(self, test):
        for argv in self.argvs:
            test.assertNotIn(TOKEN, " ".join(argv))
