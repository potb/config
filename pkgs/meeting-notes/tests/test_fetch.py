import json
import subprocess
from datetime import timedelta
from unittest import mock

from meeting_notes import fetch

from .helpers import NOW, PipelineCase


class FakeAsr:
    def __init__(self, lines):
        self.lines = lines

    def asr_prompt(self, cfg):
        return "prompt"

    def transcribe(self, cfg, start, end, prompt, floor=None, skipped=None, spans=None):
        self.floor = floor
        if skipped is not None:
            skipped.extend(getattr(self, "bad", []))
        if spans is not None and self.lines:
            spans.extend(getattr(self, "spans", [None] * len(self.lines)))
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

    def run_fetch(self, lines, screens=None, cfg=None, ocr=None):
        return fetch.fetch(
            cfg or self.cfg,
            self.mid,
            asr=FakeAsr(lines),
            screenpipe=FakeScreenpipe(screens or []),
            ocr=ocr or (lambda cfg, path: None),
        )

    def shots(self, *names):
        directory = self.cfg.screens_dir(self.mid)
        directory.mkdir(parents=True)
        for name in names:
            (directory / name).write_bytes(b"x")
        return directory

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

    def test_native_screen_lists_captures_when_ocr_fails(self):
        self.shots("b.png", "a.png")
        self.run_fetch([])
        self.assertEqual((self.out / "screen.txt").read_text().splitlines(), ["## a.png", "## b.png"])

    def test_native_screen_holds_ocr_text_without_repeats(self):
        self.shots("b.png", "a.png")
        texts = {"a.png": "Hugo Danaguezian\n\n  Peio Thibault \n", "b.png": "Peio Thibault\nInventaire\n"}
        self.run_fetch([], ocr=lambda cfg, path: texts[path.name])
        self.assertEqual(
            (self.out / "screen.txt").read_text().splitlines(),
            ["## a.png", "Hugo Danaguezian", "Peio Thibault", "## b.png", "Inventaire"],
        )

    def test_native_screen_keeps_heading_for_failed_capture(self):
        self.shots("a.png", "b.png")
        self.run_fetch([], ocr=lambda cfg, path: "Slide\n" if path.name == "b.png" else None)
        self.assertEqual((self.out / "screen.txt").read_text().splitlines(), ["## a.png", "## b.png", "Slide"])

    def test_ocr_image_runs_tesseract_with_languages(self):
        self.shots("a.png")
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, stdout="Bonjour\n")

        path = self.cfg.screens_dir(self.mid) / "a.png"
        with mock.patch.object(fetch.subprocess, "run", run):
            self.assertEqual(fetch.ocr_image(self.cfg, path), "Bonjour\n")
        argv, kwargs = calls[0]
        self.assertEqual(argv[-5:], [self.cfg.tesseract, str(path), "stdout", "-l", "eng+fra"])
        self.assertEqual(kwargs["timeout"], fetch.OCR_TIMEOUT)

    def test_ocr_image_returns_none_on_failure(self):
        path = self.root / "a.png"
        failures = [
            mock.Mock(side_effect=OSError("missing")),
            mock.Mock(side_effect=subprocess.TimeoutExpired("tesseract", 1)),
            mock.Mock(return_value=subprocess.CompletedProcess([], 1, stdout="partial")),
        ]
        for run in failures:
            with mock.patch.object(fetch.subprocess, "run", run):
                self.assertIsNone(fetch.ocr_image(self.cfg, path))

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
