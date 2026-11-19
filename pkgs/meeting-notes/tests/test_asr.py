import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from meeting_notes import asr, chunks
from meeting_notes.config import Config

T0 = datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)


def volume(mean, peak):
    return (
        "[Parsed_volumedetect_0 @ 0x1] n_samples: 480000\n"
        f"[Parsed_volumedetect_0 @ 0x1] mean_volume: {mean} dB\n"
        f"[Parsed_volumedetect_0 @ 0x1] max_volume: {peak} dB\n"
    )


def words(count):
    return " ".join(f"mot{i}" for i in range(count))


def whisper_json(items):
    return json.dumps(
        {
            "transcription": [
                {"offsets": {"from": int(start * 1000), "to": int(start * 1000) + 2000}, "text": f" {text}"}
                for start, text in items
            ]
        }
    )


class FakeRun:
    def __init__(self, cfg, mean=-20.0, peak=-5.0, outputs=None, whisper_code=0, on_whisper=None):
        self.cfg = cfg
        self.mean = mean
        self.peak = peak
        self.outputs = list(outputs or [])
        self.whisper_code = whisper_code
        self.on_whisper = on_whisper
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        if "volumedetect" in argv:
            return SimpleNamespace(returncode=0, stdout="", stderr=volume(self.mean, self.peak))
        if self.cfg.whisper in argv:
            if self.on_whisper:
                self.on_whisper()
            if self.whisper_code:
                return SimpleNamespace(returncode=self.whisper_code, stdout="", stderr="boom")
            prefix = argv[argv.index("-of") + 1]
            Path(prefix + ".json").write_text(self.outputs.pop(0))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def whisper_calls(self):
        return [c for c in self.calls if self.cfg.whisper in c]


class AsrCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.model = self.root / "ggml-large.bin"
        self.vad = self.root / "vad.bin"
        self.model.write_text("m")
        self.vad.write_text("v")
        self.cfg = Config.from_env(
            {
                "HOME": str(self.root),
                "MEETING_NOTES_DATA_DIR": str(self.root / "data"),
                "MEETING_NOTES_MODEL": str(self.model),
                "MEETING_NOTES_VAD_MODEL": str(self.vad),
                "MEETING_NOTES_WHISPER": "whisper-cli",
                "MEETING_NOTES_FFMPEG": "ffmpeg",
            }
        )
        self.cfg.audio_dir.mkdir(parents=True)

    def make_chunk(self, kind, t0, device="Mic"):
        path = self.cfg.audio_dir / chunks.chunk_name(device, kind, t0)
        path.write_bytes(b"x")
        old = (t0 + timedelta(seconds=120)).timestamp()
        os.utime(path, (old, old))
        return path

    def cache_files(self):
        return sorted(self.cfg.cache_dir.glob("*.json")) if self.cfg.cache_dir.exists() else []


class ArgvTests(AsrCase):
    def test_whisper_argv_exact(self):
        argv = asr.whisper_argv(self.cfg, "/w/a.wav", "/w/out", "prompt text", "fr")
        self.assertEqual(
            argv,
            [
                "whisper-cli", "-m", str(self.model), "-f", "/w/a.wav",
                "--vad", "--vad-model", str(self.vad),
                "-bs", "8", "-bo", "5", "-l", "fr",
                "--prompt", "prompt text", "-oj", "-of", "/w/out", "-np",
            ],
        )

    def test_prefilter_argv_exact(self):
        calls = []
        asr.prefilter(self.cfg, "/a/in.mp4", "/w/out.wav", lambda argv: calls.append(argv) or SimpleNamespace(returncode=0, stdout="", stderr=""))
        self.assertEqual(
            calls,
            [[
                "ffmpeg", "-y", "-loglevel", "error", "-i", "/a/in.mp4",
                "-ar", "16000", "-ac", "1",
                "-af", "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11", "/w/out.wav",
            ]],
        )

    def test_low_priority_linux(self):
        self.assertEqual(
            asr.low_priority(self.cfg, ["a", "b"], platform="linux"),
            ["ionice", "-c3", "nice", "-n19", "a", "b"],
        )

    def test_low_priority_darwin_with_taskpolicy(self):
        self.assertEqual(
            asr.low_priority(self.cfg, ["a"], platform="darwin", exists=lambda p: True),
            ["/usr/sbin/taskpolicy", "-b", "a"],
        )

    def test_low_priority_darwin_without_taskpolicy(self):
        self.assertEqual(
            asr.low_priority(self.cfg, ["a"], platform="darwin", exists=lambda p: False),
            ["nice", "-n19", "a"],
        )


class GlossaryTests(AsrCase):
    def test_terms_and_prompt(self):
        self.cfg.glossary.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.glossary.write_text("# Glossaire\n\n- Kubernetes\n* Nix\nKubernetes\n\nHerdr\n")
        self.assertEqual(asr.glossary_terms(self.cfg.glossary), ["Kubernetes", "Nix", "Herdr"])
        prompt = asr.asr_prompt(self.cfg)
        self.assertIn("Kubernetes, Nix, Herdr", prompt)
        self.assertNotIn("Costo", prompt)

    def test_missing_glossary(self):
        self.assertEqual(asr.glossary_terms(self.cfg.glossary), [])
        self.assertEqual(asr.asr_prompt(self.cfg), "")


class ChunkTests(AsrCase):
    def test_segments_and_cache(self):
        path = self.make_chunk("input", T0)
        run = FakeRun(self.cfg, outputs=[whisper_json([(0.0, words(8)), (12.5, words(7))])])
        segments, elapsed = asr.transcribe_chunk(self.cfg, path, "me", "p", run)
        self.assertEqual(segments, [[0.0, words(8)], [12.5, words(7)]])
        self.assertGreaterEqual(elapsed, 0)
        self.assertEqual(len(self.cache_files()), 1)

    def test_cache_hit_calls_nothing(self):
        path = self.make_chunk("input", T0)
        run = FakeRun(self.cfg, outputs=[whisper_json([(1.0, words(9))])])
        first, _ = asr.transcribe_chunk(self.cfg, path, "me", "p", run)
        again = FakeRun(self.cfg)
        second, elapsed = asr.transcribe_chunk(self.cfg, path, "me", "p", again)
        self.assertEqual(again.calls, [])
        self.assertEqual(second, first)
        self.assertEqual(elapsed, 0.0)

    def test_cache_keyed_by_model(self):
        path = self.make_chunk("input", T0)
        asr.transcribe_chunk(self.cfg, path, "me", "p", FakeRun(self.cfg, outputs=[whisper_json([(0, words(8))])]))
        other = self.root / "ggml-small.bin"
        other.write_text("m")
        cfg2 = Config.from_env(
            {
                "HOME": str(self.root),
                "MEETING_NOTES_DATA_DIR": str(self.root / "data"),
                "MEETING_NOTES_MODEL": str(other),
                "MEETING_NOTES_VAD_MODEL": str(self.vad),
            }
        )
        run = FakeRun(cfg2, outputs=[whisper_json([(0, words(8))])])
        asr.transcribe_chunk(cfg2, path, "me", "p", run)
        self.assertEqual(len(run.whisper_calls()), 1)
        self.assertEqual(len(self.cache_files()), 2)

    def test_silent_chunk_cached_empty(self):
        path = self.make_chunk("output", T0)
        run = FakeRun(self.cfg, mean=-70.0, peak=-60.0)
        segments, _ = asr.transcribe_chunk(self.cfg, path, "others", "p", run)
        self.assertEqual(segments, [])
        self.assertEqual(run.whisper_calls(), [])
        cached = json.loads(self.cache_files()[0].read_text())
        self.assertEqual(cached["segments"], [])
        again = FakeRun(self.cfg)
        asr.transcribe_chunk(self.cfg, path, "others", "p", again)
        self.assertEqual(again.calls, [])

    def test_hallucinations_filtered(self):
        path = self.make_chunk("input", T0)
        run = FakeRun(
            self.cfg,
            outputs=[
                whisper_json(
                    [
                        (0.0, "Sous-titres réalisés par la communauté d'Amara.org"),
                        (3.0, words(8)),
                        (9.0, "Merci d'avoir regardé cette vidéo !"),
                    ]
                )
            ],
        )
        segments, _ = asr.transcribe_chunk(self.cfg, path, "me", "p", run)
        self.assertEqual(segments, [[3.0, words(8)]])

    def test_retry_without_prompt_when_short_and_loud(self):
        path = self.make_chunk("input", T0)
        run = FakeRun(
            self.cfg,
            mean=-20.0,
            outputs=[whisper_json([(0.0, words(2))]), whisper_json([(0.0, words(8))])],
        )
        segments, _ = asr.transcribe_chunk(self.cfg, path, "me", "glossaire", run)
        calls = run.whisper_calls()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][calls[0].index("--prompt") + 1], "glossaire")
        self.assertEqual(calls[1][calls[1].index("--prompt") + 1], "")
        self.assertEqual(segments, [[0.0, words(8)]])

    def test_no_retry_when_quiet(self):
        path = self.make_chunk("input", T0)
        run = FakeRun(self.cfg, mean=-40.0, peak=-20.0, outputs=[whisper_json([(0.0, words(2))])])
        asr.transcribe_chunk(self.cfg, path, "me", "p", run)
        self.assertEqual(len(run.whisper_calls()), 1)

    def test_error_writes_no_cache(self):
        path = self.make_chunk("input", T0)
        run = FakeRun(self.cfg, whisper_code=1)
        with self.assertRaises(asr.AsrError):
            asr.transcribe_chunk(self.cfg, path, "me", "p", run)
        self.assertEqual(self.cache_files(), [])

    def test_low_priority_option_prefixes_every_command(self):
        path = self.make_chunk("input", T0)
        run = FakeRun(self.cfg, outputs=[whisper_json([(0.0, words(8))])])
        asr.transcribe_chunk(self.cfg, path, "me", "p", run, low=True)
        self.assertTrue(run.calls)
        for call in run.calls:
            self.assertEqual(call[:5], asr.low_priority(self.cfg, ["x"])[:4] + [call[4]])


class LiveTests(AsrCase):
    def clock(self, start):
        state = {"now": start}

        def now():
            return state["now"]

        def advance(seconds):
            state["now"] += timedelta(seconds=seconds)

        return now, advance

    def test_slow_chunk_stops_with_flag(self):
        self.make_chunk("input", T0)
        self.make_chunk("input", T0 + timedelta(seconds=30))
        now, advance = self.clock(T0 + timedelta(minutes=5))
        run = FakeRun(
            self.cfg,
            outputs=[whisper_json([(0.0, words(8))]), whisper_json([(0.0, words(8))])],
            on_whisper=lambda: advance(11),
        )
        result = asr.live_pass(self.cfg, T0, "p", lambda: False, run, now)
        self.assertTrue(result.slow)
        self.assertEqual(len(run.whisper_calls()), 1)
        self.assertEqual(result.done, 1)

    def test_fast_chunks_all_done_and_prefixed(self):
        self.make_chunk("input", T0)
        self.make_chunk("output", T0 + timedelta(seconds=30), device="Spk")
        now, advance = self.clock(T0 + timedelta(minutes=5))
        run = FakeRun(
            self.cfg,
            outputs=[whisper_json([(0.0, words(8))]), whisper_json([(0.0, words(8))])],
            on_whisper=lambda: advance(2),
        )
        result = asr.live_pass(self.cfg, T0, "p", lambda: False, run, now)
        self.assertFalse(result.slow)
        self.assertEqual(result.done, 2)
        for call in run.calls:
            self.assertEqual(call[:4], asr.low_priority(self.cfg, [])[:4])

    def test_skips_cached_and_incomplete(self):
        done = self.make_chunk("input", T0)
        asr.transcribe_chunk(self.cfg, done, "me", "p", FakeRun(self.cfg, outputs=[whisper_json([(0.0, words(8))])]))
        self.make_chunk("input", T0 + timedelta(seconds=30))
        now, _ = self.clock(T0 + timedelta(seconds=45))
        run = FakeRun(self.cfg)
        result = asr.live_pass(self.cfg, T0, "p", lambda: False, run, now)
        self.assertEqual(run.calls, [])
        self.assertEqual(result.done, 0)
        self.assertFalse(result.slow)

    def test_should_stop(self):
        self.make_chunk("input", T0)
        now, _ = self.clock(T0 + timedelta(minutes=5))
        run = FakeRun(self.cfg)
        result = asr.live_pass(self.cfg, T0, "p", lambda: True, run, now)
        self.assertEqual(run.calls, [])
        self.assertEqual(result.done, 0)


class TranscribeTests(AsrCase):
    def test_absolute_sorted_lines(self):
        self.make_chunk("output", T0 + timedelta(seconds=30), device="Spk")
        self.make_chunk("input", T0)
        run = FakeRun(
            self.cfg,
            outputs=[
                whisper_json([(4.0, words(8))]),
                whisper_json([(1.5, words(9))]),
            ],
        )
        lines = asr.transcribe(self.cfg, T0, T0 + timedelta(minutes=2), "p", run, available=lambda cfg: True)
        self.assertEqual(
            lines,
            [
                (T0 + timedelta(seconds=4), "me", words(8)),
                (T0 + timedelta(seconds=31.5), "others", words(9)),
            ],
        )

    def test_spans_follow_the_sorted_lines(self):
        others = self.make_chunk("output", T0 + timedelta(seconds=30), device="Spk")
        mic = self.make_chunk("input", T0)
        run = FakeRun(
            self.cfg,
            outputs=[
                whisper_json([(4.0, words(8))]),
                whisper_json([(1.5, words(9)), (12.0, words(7))]),
            ],
        )
        spans = []
        lines = asr.transcribe(
            self.cfg, T0, T0 + timedelta(minutes=2), "p", run, available=lambda cfg: True, spans=spans
        )
        self.assertEqual([line[1] for line in lines], ["me", "others", "others"])
        self.assertEqual(
            spans,
            [
                asr.Span(mic.name, 4.0, None),
                asr.Span(others.name, 1.5, 12.0),
                asr.Span(others.name, 12.0, None),
            ],
        )

    def test_unreadable_chunk_is_skipped(self):
        bad = self.make_chunk("input", T0)
        self.make_chunk("input", T0 + timedelta(seconds=30))
        base = FakeRun(self.cfg, outputs=[whisper_json([(2.0, words(8))])])

        def run(argv):
            if str(bad) in argv:
                return SimpleNamespace(returncode=1, stdout="", stderr="moov atom not found")
            return base(argv)

        skipped = []
        lines = asr.transcribe(
            self.cfg, T0, T0 + timedelta(minutes=2), "p", run, available=lambda cfg: True, skipped=skipped
        )
        self.assertEqual(lines, [(T0 + timedelta(seconds=32), "me", words(8))])
        self.assertEqual(skipped, [bad.name])

    def test_whisper_failure_fails_the_transcription(self):
        path = self.make_chunk("input", T0)
        skipped = []
        with self.assertRaises(asr.AsrError):
            asr.transcribe(
                self.cfg,
                T0,
                T0 + timedelta(minutes=2),
                "p",
                FakeRun(self.cfg, whisper_code=1),
                available=lambda cfg: True,
                skipped=skipped,
            )
        self.assertEqual(skipped, [])
        self.assertFalse(asr.cached(self.cfg, path))

    def test_prefilter_failure_fails_the_transcription(self):
        self.make_chunk("input", T0)
        base = FakeRun(self.cfg)

        def run(argv):
            if "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11" in argv:
                return SimpleNamespace(returncode=1, stdout="", stderr="Cannot allocate memory")
            return base(argv)

        with self.assertRaises(asr.AsrError):
            asr.transcribe(self.cfg, T0, T0 + timedelta(minutes=2), "p", run, available=lambda cfg: True)

    def test_floor_excludes_previous_meeting_chunk(self):
        previous = self.make_chunk("input", T0 - timedelta(seconds=20))
        current = self.make_chunk("input", T0 + timedelta(seconds=5))
        self.assertEqual(
            chunks.meeting_chunks(self.cfg.audio_dir, T0, T0 + timedelta(minutes=1), floor=T0 - timedelta(seconds=5)),
            [current],
        )
        self.assertIn(previous, chunks.meeting_chunks(self.cfg.audio_dir, T0, T0 + timedelta(minutes=1)))

    def test_concurrent_cache_writes_do_not_collide(self):
        path = self.make_chunk("input", T0)
        real = os.replace
        nested = []

        def replace(src, dst):
            if not nested:
                nested.append(True)
                asr._write_cache(self.cfg, path, [[0.0, "live"]])
            return real(src, dst)

        with mock.patch("os.replace", replace):
            asr._write_cache(self.cfg, path, [[0.0, "fetch"]])
        self.assertEqual(asr._read_cache(self.cfg, path), [[0.0, "fetch"]])
        self.assertEqual(list(self.cfg.cache_dir.glob("*.tmp")), [])

    def test_none_when_unavailable(self):
        self.make_chunk("input", T0)
        run = FakeRun(self.cfg)
        self.assertIsNone(asr.transcribe(self.cfg, T0, T0 + timedelta(minutes=1), "p", run, available=lambda cfg: False))
        self.assertEqual(run.calls, [])

    def test_none_without_chunks(self):
        run = FakeRun(self.cfg)
        self.assertIsNone(asr.transcribe(self.cfg, T0, T0 + timedelta(minutes=1), "p", run, available=lambda cfg: True))


class HousekeepingTests(AsrCase):
    def test_available(self):
        which = lambda name: "/bin/" + name
        self.assertTrue(asr.available(self.cfg, which=which))
        self.assertFalse(asr.available(self.cfg, which=lambda name: None))
        self.vad.unlink()
        self.assertFalse(asr.available(self.cfg, which=which))

    def test_prune_cache(self):
        self.cfg.cache_dir.mkdir(parents=True)
        old = self.cfg.cache_dir / "old.json"
        fresh = self.cfg.cache_dir / "fresh.json"
        old.write_text("{}")
        fresh.write_text("{}")
        past = (datetime.now(timezone.utc) - timedelta(days=9)).timestamp()
        os.utime(old, (past, past))
        removed = asr.prune_cache(self.cfg, 7)
        self.assertEqual(removed, 1)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())


if __name__ == "__main__":
    unittest.main()
