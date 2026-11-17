import io
import json
import os
import stat
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from meeting_notes import screenpipe
from meeting_notes.config import Config

FIXTURES = Path(__file__).parent / "fixtures" / "screenpipe"


def fixture(name):
    return (FIXTURES / name).read_bytes()


class FakeOpener:
    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        path = request.full_url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
        answer = self.routes[(request.get_method(), "/" + path)]
        if isinstance(answer, Exception):
            raise answer
        return answer


def make_config(root, **extra):
    env = {"HOME": str(root), "MEETING_NOTES_DATA_DIR": str(Path(root) / "data")}
    env.update(extra)
    return Config.from_env(env)


class EnsureKeyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = make_config(self.tmp.name)

    def test_creates_key_file_with_mode_600(self):
        key = screenpipe.ensure_key(self.cfg)
        mode = stat.S_IMODE(os.stat(self.cfg.key_path).st_mode)
        self.assertEqual(mode, 0o600)
        self.assertGreaterEqual(len(key), 32)

    def test_key_is_stable_between_calls(self):
        first = screenpipe.ensure_key(self.cfg)
        second = screenpipe.ensure_key(self.cfg)
        self.assertEqual(first, second)
        self.assertEqual(self.cfg.key_path.read_text().strip(), first)

    def test_existing_key_is_reused(self):
        self.cfg.key_path.parent.mkdir(parents=True)
        self.cfg.key_path.write_text("fixed-key\n")
        self.assertEqual(screenpipe.ensure_key(self.cfg), "fixed-key")

    def test_no_temporary_file_left_behind(self):
        screenpipe.ensure_key(self.cfg)
        self.assertEqual([p.name for p in self.cfg.data_dir.iterdir()], ["screenpipe.key"])


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = make_config(self.tmp.name)
        self.key = screenpipe.ensure_key(self.cfg)

    def client(self, routes):
        opener = FakeOpener(routes)
        return screenpipe.Client(self.cfg, opener), opener

    def test_every_request_carries_bearer_and_client_header(self):
        client, opener = self.client(
            {
                ("GET", "/meetings/status"): fixture("status_active.json"),
                ("GET", "/meetings/7"): fixture("meeting_7_open.json"),
                ("POST", "/meetings/start"): fixture("ok.json"),
                ("POST", "/meetings/stop"): fixture("ok.json"),
                ("POST", "/audio/start"): fixture("ok.json"),
                ("POST", "/audio/stop"): fixture("ok.json"),
                ("GET", "/health"): fixture("health.json"),
            }
        )
        client.status()
        client.meeting(7)
        client.start_meeting("Google Meet", "Sync")
        client.stop_meeting()
        client.audio_start()
        client.audio_stop()
        client.health()
        self.assertEqual(len(opener.requests), 7)
        for request in opener.requests:
            self.assertEqual(request.get_header("Authorization"), f"Bearer {self.key}")
            self.assertEqual(request.get_header("X-screenpipe-client"), "api")

    def test_status_parses_json(self):
        client, _ = self.client({("GET", "/meetings/status"): fixture("status_active.json")})
        self.assertEqual(client.status()["activeMeetingId"], 7)

    def test_start_meeting_posts_json_body(self):
        client, opener = self.client({("POST", "/meetings/start"): fixture("ok.json")})
        client.start_meeting("Zoom", "Review")
        request = opener.requests[0]
        self.assertEqual(json.loads(request.data), {"app": "Zoom", "title": "Review"})
        self.assertEqual(request.get_header("Content-type"), "application/json")

    def test_url_uses_config_base(self):
        cfg = make_config(self.tmp.name, MEETING_NOTES_SCREENPIPE_URL="http://127.0.0.1:4040")
        opener = FakeOpener({("GET", "/health"): fixture("health.json")})
        screenpipe.Client(cfg, opener).health()
        self.assertEqual(opener.requests[0].full_url, "http://127.0.0.1:4040/health")

    def test_http_error_propagates(self):
        error = urllib.error.HTTPError("http://x/health", 401, "Unauthorized", {}, io.BytesIO(b""))
        client, _ = self.client({("GET", "/health"): error})
        with self.assertRaises(urllib.error.HTTPError):
            client.health()

    def test_key_absent_from_repr_and_str(self):
        client, _ = self.client({})
        self.assertNotIn(self.key, repr(client))
        self.assertNotIn(self.key, str(client))
        self.assertNotIn(self.key, repr(vars(client).get("cfg")))

    def test_key_not_printed_or_logged(self):
        client, _ = self.client({("GET", "/health"): fixture("health.json")})
        with self.assertNoLogs(level="DEBUG"):
            with mock.patch("sys.stdout", new=io.StringIO()) as out, mock.patch("sys.stderr", new=io.StringIO()) as err:
                screenpipe.ensure_key(self.cfg)
                client.health()
        self.assertNotIn(self.key, out.getvalue() + err.getvalue())


class SearchScreenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = make_config(self.tmp.name)

    def search(self, routes_by_type, app="Google Meet"):
        opener = FakeSearchOpener(routes_by_type)
        client = screenpipe.Client(self.cfg, opener)
        text = client.search_screen("2026-11-17T09:00:00Z", "2026-11-17T09:42:00Z", app)
        return text, opener

    def test_merges_accessibility_and_ocr_and_dedupes(self):
        text, _ = self.search(
            {"accessibility": fixture("search_accessibility.json"), "ocr": fixture("search_ocr.json")}
        )
        self.assertEqual(text.count("Alice Martin  Bob Durand"), 1)
        self.assertIn("Roadmap Q1", text)
        self.assertIn("--- Google Meet / Meet @ ", text)

    def test_query_carries_range_and_filter(self):
        _, opener = self.search({"accessibility": fixture("search_accessibility.json"), "ocr": fixture("search_empty.json")})
        first = opener.queries[0]
        self.assertEqual(first["start_time"], ["2026-11-17T09:00:00Z"])
        self.assertEqual(first["end_time"], ["2026-11-17T09:42:00Z"])
        self.assertEqual(first["app_name"], ["Google Meet"])
        self.assertEqual(first["content_type"], ["accessibility"])

    def test_empty_gives_placeholder(self):
        text, _ = self.search({"accessibility": fixture("search_empty.json"), "ocr": fixture("search_empty.json")})
        self.assertEqual(text, "(no screen text captured for the call window)\n")

    def test_budget_is_12000_characters(self):
        big = json.dumps(
            {
                "data": [
                    {
                        "content": {
                            "text": f"{i:04d}" + "x" * 996,
                            "app_name": "Google Meet",
                            "window_name": "Meet",
                            "timestamp": "2026-11-17T09:05:00Z",
                        }
                    }
                    for i in range(40)
                ]
            }
        ).encode()
        text, _ = self.search({"accessibility": big, "ocr": fixture("search_empty.json")})
        self.assertLessEqual(len(text), screenpipe.SCREEN_CHAR_BUDGET)
        self.assertGreater(len(text), 10000)

    def test_failed_search_is_skipped(self):
        error = urllib.error.URLError("down")
        text, _ = self.search({"accessibility": error, "ocr": fixture("search_ocr.json")})
        self.assertIn("Roadmap Q1", text)

    def test_browser_call_adds_window_name_filter(self):
        _, opener = self.search(
            {"accessibility": fixture("search_empty.json"), "ocr": fixture("search_empty.json")},
            app="Google Meet",
        )
        filters = {tuple(sorted((k, v[0]) for k, v in q.items() if k in ("app_name", "window_name"))) for q in opener.queries}
        self.assertIn((("window_name", "Meet"),), filters)
        self.assertIn((("window_name", "Google Meet"),), filters)


class FakeSearchOpener:
    def __init__(self, by_type):
        self.by_type = by_type
        self.queries = []

    def __call__(self, request):
        from urllib.parse import parse_qs, urlsplit

        parts = urlsplit(request.full_url)
        query = parse_qs(parts.query)
        self.queries.append(query)
        answer = self.by_type[query["content_type"][0]]
        if isinstance(answer, Exception):
            raise answer
        return answer


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_server_argv(self):
        cfg = make_config(self.tmp.name, MEETING_NOTES_SCREENPIPE="/bin/screenpipe", MEETING_NOTES_SCREENPIPE_URL="http://127.0.0.1:4040")
        argv = screenpipe.server_argv(cfg)
        self.assertEqual(
            argv,
            ["/bin/screenpipe", "record", "--port", "4040", "--disable-telemetry", "-a", "disabled"],
        )

    def test_default_port(self):
        cfg = make_config(self.tmp.name)
        self.assertEqual(screenpipe.server_argv(cfg)[3], "3030")

    def test_exec_server_passes_key_in_env(self):
        cfg = make_config(self.tmp.name)
        with mock.patch("os.execvpe") as execvpe:
            screenpipe.exec_server(cfg)
        argv0, argv, env = execvpe.call_args.args
        self.assertEqual(argv0, cfg.screenpipe)
        self.assertEqual(argv, screenpipe.server_argv(cfg))
        self.assertEqual(env["SCREENPIPE_API_KEY"], cfg.key_path.read_text().strip())
        self.assertEqual(stat.S_IMODE(os.stat(cfg.key_path).st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
