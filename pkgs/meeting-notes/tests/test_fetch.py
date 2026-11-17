import json
from datetime import timedelta

from meeting_notes import fetch

from .helpers import NOW, PipelineCase


class FakeAsr:
    def __init__(self, lines):
        self.lines = lines

    def asr_prompt(self, cfg):
        return "prompt"

    def transcribe(self, cfg, start, end, prompt, floor=None, skipped=None):
        self.floor = floor
        if skipped is not None:
            skipped.extend(getattr(self, "bad", []))
        return self.lines


class FakeScreenpipe:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def search_screen(self, cfg, start, end):
        self.calls.append((start, end))
        return self.items


def local(moment):
    return moment.astimezone().strftime("%H:%M:%S")


class FetchTest(PipelineCase):
    def setUp(self):
        super().setUp()
        self.start = NOW - timedelta(hours=1)
        self.mid = self.add(self.start, NOW - timedelta(minutes=30), title="Review")
        self.out = self.cfg.meeting_dir(self.mid)

    def run_fetch(self, lines, screens=None, cfg=None):
        return fetch.fetch(
            cfg or self.cfg,
            self.mid,
            asr=FakeAsr(lines),
            screenpipe=FakeScreenpipe(screens or []),
        )

    def meta(self):
        return json.loads((self.out / "meta.json").read_text())

    def test_meta(self):
        self.run_fetch([])
        meta = self.meta()
        self.assertEqual(meta["id"], self.mid)
        self.assertEqual(meta["title"], "Review")
        self.assertEqual(meta["owner"], self.cfg.owner)

    def test_transcript_format_and_merge(self):
        t = self.start
        lines = [
            (t, "me", "bonjour"),
            (t + timedelta(seconds=2), "me", "a tous"),
            (t + timedelta(seconds=5), "others", "salut"),
            (t + timedelta(seconds=9), "me", "ok"),
        ]
        self.run_fetch(lines)
        text = (self.out / "transcript.txt").read_text().splitlines()
        self.assertEqual(
            text,
            [
                f"[{local(t)}] me | bonjour a tous",
                f"[{local(t + timedelta(seconds=5))}] others | salut",
                f"[{local(t + timedelta(seconds=9))}] me | ok",
            ],
        )

    def test_no_transcript_writes_empty_and_source_none(self):
        self.run_fetch(None)
        self.assertEqual((self.out / "transcript.txt").read_text(), "")
        self.assertEqual(self.meta()["transcript_source"], "none")

    def test_source_local(self):
        self.run_fetch([(self.start, "me", "x")])
        self.assertEqual(self.meta()["transcript_source"], "local")

    def test_native_screen_lists_captures(self):
        shots = self.cfg.screens_dir(self.mid)
        shots.mkdir(parents=True)
        (shots / "b.png").write_bytes(b"x")
        (shots / "a.png").write_bytes(b"x")
        self.run_fetch([])
        self.assertEqual((self.out / "screen.txt").read_text().splitlines(), ["a.png", "b.png"])

    def test_screenpipe_backend_uses_search_screen(self):
        mid = self.add(
            NOW - timedelta(hours=3), NOW - timedelta(hours=2), backend="screenpipe"
        )
        sp = FakeScreenpipe(["Slide un", "Slide deux"])
        fetch.fetch(self.cfg, mid, asr=FakeAsr([]), screenpipe=sp)
        self.assertEqual(len(sp.calls), 1)
        screen = self.cfg.meeting_dir(mid) / "screen.txt"
        self.assertEqual(screen.read_text().splitlines(), ["Slide un", "Slide deux"])

    def test_native_does_not_call_screenpipe(self):
        sp = FakeScreenpipe(["x"])
        fetch.fetch(self.cfg, self.mid, asr=FakeAsr([]), screenpipe=sp)
        self.assertEqual(sp.calls, [])

    def test_floor_is_previous_meeting_end(self):
        previous_end = self.start - timedelta(seconds=20)
        self.add(previous_end - timedelta(minutes=10), previous_end)
        fake = FakeAsr([])
        fetch.fetch(self.cfg, self.mid, asr=fake, screenpipe=FakeScreenpipe([]))
        self.assertEqual(fake.floor, previous_end)

    def test_skipped_chunks_in_meta(self):
        fake = FakeAsr([(self.start, "me", "x")])
        fake.bad = ["Mic (input)_2026-05-20_11-00-00.mp4"]
        fetch.fetch(self.cfg, self.mid, asr=fake, screenpipe=FakeScreenpipe([]))
        self.assertEqual(self.meta()["skipped_chunks"], fake.bad)
        self.assertTrue((self.out / "fetched.ok").exists())

    def test_fetched_ok_written_last(self):
        order = []
        real = fetch._write

        def spy(path, text):
            order.append(path.name)
            real(path, text)

        fetch._write = spy
        self.addCleanup(setattr, fetch, "_write", real)
        self.run_fetch([])
        self.assertEqual(order[-1], "fetched.ok")
        self.assertEqual(set(order), {"meta.json", "transcript.txt", "screen.txt", "fetched.ok"})
