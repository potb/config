import io
import json
import logging
import subprocess
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path

import numpy as np

from meeting_notes import asr, chunks, diarize, fetch, voices

from .helpers import NOW, PipelineCase

RATE = diarize.SAMPLE_RATE


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


def tone(seconds, value=0.1):
    return np.full(int(seconds * RATE), value, dtype=np.float32)


def speaker_audio(pattern):
    return np.concatenate([tone(seconds, value) for seconds, value in pattern])


def fake_probs(audio):
    frames = len(audio) // diarize.VAD_FRAME
    return [float(np.abs(audio[i * diarize.VAD_FRAME:(i + 1) * diarize.VAD_FRAME]).mean() > 0.01) for i in range(frames)]


def fake_embedder(seed=1):
    rng = np.random.default_rng(seed)
    bases = {1: np.eye(256)[0], -1: np.eye(256)[1], 2: np.eye(256)[2]}

    def embed(segment):
        mean = float(segment.mean())
        key = 2 if mean > 0.15 else (1 if mean > 0 else -1)
        vector = bases[key] + rng.normal(0, 0.05, 256)
        return vector / np.linalg.norm(vector)

    return embed


def unit(index):
    return np.eye(256)[index]


def write_print(directory, name, vector, seconds=100.0):
    voices.write(directory, voices.record(name, vector, seconds, ["m0"]))


class AssembleTest(PipelineCase):
    def items(self, offsets):
        return [(NOW + timedelta(seconds=offset), Path(f"c{index}.mp4")) for index, offset in enumerate(offsets)]

    def test_contiguous_gap_and_corrupt_chunk(self):
        lengths = {"c0.mp4": 30.0, "c1.mp4": 30.0, "c2.mp4": None, "c3.mp4": 30.0, "c4.mp4": 30.0}
        items = self.items([0, 31, 61, 91, 125])

        def decode(path):
            seconds = lengths[path.name]
            return None if seconds is None else tone(seconds)

        audio, pieces, skipped = diarize.assemble(items, decode)
        self.assertEqual(skipped, ["c2.mp4"])
        self.assertEqual([p.name for p in pieces], ["c0.mp4", "c1.mp4", "c3.mp4", "c4.mp4"])
        offsets = [round(p.offset, 3) for p in pieces]
        self.assertEqual(offsets[:2], [0.0, 30.0])
        self.assertAlmostEqual(offsets[2], 60.0 + 30.0, places=3)
        self.assertAlmostEqual(offsets[3], 90.0 + 30.0 + 4.0, places=3)
        self.assertEqual(len(audio), int(round(pieces[-1].offset * RATE)) + 30 * RATE)
        self.assertTrue(np.all(audio[60 * RATE:90 * RATE] == 0))

    def test_small_gap_stays_contiguous(self):
        items = self.items([0, 31.4])
        audio, pieces, _ = diarize.assemble(items, lambda path: tone(30))
        self.assertEqual(pieces[1].offset, 30.0)
        self.assertEqual(len(audio), 60 * RATE)

    def test_sorted_by_time(self):
        items = list(reversed(self.items([0, 30])))
        _, pieces, _ = diarize.assemble(items, lambda path: tone(30))
        self.assertEqual([p.name for p in pieces], ["c0.mp4", "c1.mp4"])

    def test_others_chunks_only(self):
        self.cfg.audio_dir.mkdir(parents=True)
        self.assertEqual(diarize.thread_env(self.cfg, {})["OPENBLAS_NUM_THREADS"], "4")
        for kind in ("input", "output"):
            (self.cfg.audio_dir / chunks.chunk_name("dev", kind, NOW)).write_bytes(b"x")
        found = diarize.others_chunks(self.cfg.audio_dir, NOW, NOW + timedelta(minutes=1))
        self.assertEqual([path.name for _, path in found], [chunks.chunk_name("dev", "output", NOW)])

    def test_decode_failure_is_none(self):
        run = lambda argv, **kw: subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"moov atom not found")
        self.assertIsNone(diarize.decode_chunk(self.cfg, Path("x.mp4"), run))
        good = lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout=tone(1).tobytes(), stderr=b"")
        self.assertEqual(len(diarize.decode_chunk(self.cfg, Path("x.mp4"), good)), RATE)


class PipelineTest(PipelineCase):
    def test_speech_regions_merge_and_pad(self):
        frame = diarize.VAD_FRAME / RATE
        probs = [0.0] * 10 + [0.9] * 20 + [0.0] * 5 + [0.9] * 20 + [0.0] * 15 + [0.9] * 2 + [0.0] * 40
        regions = diarize.speech_regions(probs, len(probs) * frame)
        self.assertEqual(len(regions), 1)
        self.assertAlmostEqual(regions[0][0], 10 * frame - diarize.REGION_PAD)
        self.assertAlmostEqual(regions[0][1], 55 * frame + diarize.REGION_PAD)

    def test_windows(self):
        self.assertEqual(diarize.windows([(0.0, 1.0)]), [(0.0, 1.0)])
        spans = diarize.windows([(0.0, 4.0)])
        self.assertEqual(spans[0], (0.0, 1.5))
        self.assertEqual(spans[-1], (2.25, 3.75))
        self.assertEqual(diarize.windows([(0.0, 4.5)])[-1], (3.0, 4.5))
        self.assertEqual(diarize.windows([(0.0, 4.2)])[-1], (2.7, 4.2))
        self.assertEqual(diarize.windows([(0.0, 0.5)]), [])

    def test_two_speakers_found_and_matched(self):
        audio = speaker_audio([(10, 0.1), (10, -0.1)] * 8)
        prints = [voices.record("Ada", unit(0), 100, []), voices.record("Bob", unit(5), 100, [])]
        summary, arrays = diarize.diarize_audio(audio, fake_probs, fake_embedder(), prints)
        self.assertEqual(len(summary["clusters"]), 2)
        names = {c["id"]: c["name"] for c in summary["clusters"]}
        self.assertEqual(sorted(names.values(), key=str), ["Ada", None])
        for cluster in summary["clusters"]:
            self.assertAlmostEqual(cluster["seconds"], 80, delta=3)
        self.assertEqual(len(arrays["labels"]), len(arrays["embeddings"]))
        self.assertEqual(set(arrays["labels"].tolist()), {0, 1})

    def test_three_speakers(self):
        audio = speaker_audio([(10, 0.1), (10, -0.1), (10, 0.3)] * 6)
        summary, _ = diarize.diarize_audio(audio, fake_probs, fake_embedder(), [])
        self.assertEqual([c["id"] for c in summary["clusters"]], ["S1", "S2", "S3"])
        self.assertTrue(all(c["name"] is None and c["cosine"] is None for c in summary["clusters"]))

    def test_under_two_minutes_of_speech(self):
        audio = speaker_audio([(50, 0.1), (60, 0.0), (50, -0.1)])
        with self.assertRaises(diarize.TooLittleSpeech):
            diarize.diarize_audio(audio, fake_probs, fake_embedder(), [])

    def test_run_writes_speakers_files(self):
        start = NOW - timedelta(hours=1)
        mid = self.add(start, start + timedelta(minutes=6))
        self.cfg.audio_dir.mkdir(parents=True)
        pattern = [(10, 0.1), (10, -0.1)] * 18
        audio = speaker_audio(pattern)
        pieces = {}
        for index in range(12):
            name = chunks.chunk_name("dev", "output", start + timedelta(seconds=30 * index))
            (self.cfg.audio_dir / name).write_bytes(b"x")
            pieces[name] = audio[index * 30 * RATE:(index + 1) * 30 * RATE]
        bad = chunks.chunk_name("dev", "output", start + timedelta(seconds=360))
        (self.cfg.audio_dir / bad).write_bytes(b"x")
        data = diarize.run(
            self.cfg, mid, probs=fake_probs, embed=fake_embedder(), decode=lambda path: pieces.get(path.name)
        )
        saved = json.loads((self.cfg.meeting_dir(mid) / diarize.SPEAKERS_JSON).read_text())
        self.assertEqual(saved, data)
        self.assertEqual(saved["status"], "ok")
        self.assertEqual(saved["skipped_chunks"], [bad])
        self.assertEqual(len(saved["chunks"]), 12)
        self.assertEqual(len(saved["clusters"]), 2)
        self.assertTrue((self.cfg.meeting_dir(mid) / diarize.SPEAKERS_NPZ).is_file())

    def test_main_records_too_little_speech(self):
        start = NOW - timedelta(hours=1)
        mid = self.add(start, start + timedelta(minutes=6))
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(diarize.main(self.cfg, mid), 0)
        self.assertIn("no others chunks", out.getvalue())
        saved = json.loads((self.cfg.meeting_dir(mid) / diarize.SPEAKERS_JSON).read_text())
        self.assertEqual(saved["status"], "skipped")


CLUSTERS = {
    "status": "ok",
    "chunks": [
        {"name": "a.mp4", "start": "x", "offset": 0.0, "seconds": 30.0},
        {"name": "b.mp4", "start": "x", "offset": 30.0, "seconds": 30.0},
    ],
    "clusters": [
        {"id": "S1", "name": None, "seconds": 20, "turns": [[0.0, 10.0], [35.0, 45.0]]},
        {"id": "S2", "name": "Bastien", "seconds": 25, "turns": [[10.0, 30.0], [45.0, 50.0]]},
    ],
}


def line(seconds, side):
    return (NOW + timedelta(seconds=seconds), side, "x")


class LabelTest(PipelineCase):
    def test_largest_overlap_and_ends(self):
        lines = [line(0, "others"), line(8, "others"), line(1, "me"), line(30 + 3, "others"), line(30 + 14, "others")]
        spans = [
            asr.Span("a.mp4", 0.0, 8.0),
            asr.Span("a.mp4", 8.0, None),
            asr.Span("m.mp4", 1.0, None),
            asr.Span("b.mp4", 3.0, 14.0),
            asr.Span("b.mp4", 14.0, None),
        ]
        labels = diarize.labels_for(lines, spans, CLUSTERS)
        self.assertEqual(labels, ["others:S1", "others:Bastien", "me", "others:S1", "others:Bastien"])

    def test_unknown_chunk_or_no_overlap_stays_others(self):
        lines = [line(0, "others"), line(55, "others")]
        spans = [asr.Span("gone.mp4", 0.0, None), asr.Span("b.mp4", 25.0, 29.0)]
        self.assertEqual(diarize.labels_for(lines, spans, CLUSTERS), ["others", "others"])


class FakeRunner:
    def __init__(self, cfg, mid, code=0, data=None, timeout=False):
        self.cfg, self.mid, self.code, self.data, self.timeout = cfg, mid, code, data, timeout
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.timeout:
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        if self.data is not None:
            target = self.cfg.meeting_dir(self.mid) / diarize.SPEAKERS_JSON
            target.write_text(json.dumps(self.data))
        return subprocess.CompletedProcess(argv, self.code, stdout="", stderr="Traceback\nboom")


class RelabelTest(PipelineCase):
    def setUp(self):
        super().setUp()
        self.speaker_model = self.root / "speaker.onnx"
        self.vad_model = self.root / "vad.onnx"
        self.speaker_model.write_bytes(b"m")
        self.vad_model.write_bytes(b"v")
        from .helpers import make_cfg

        self.cfg = make_cfg(
            self.root,
            MEETING_NOTES_DIARIZATION="1",
            MEETING_NOTES_DIARIZATION_THREADS="3",
            MEETING_NOTES_SPEAKER_MODEL=str(self.speaker_model),
            MEETING_NOTES_DIARIZATION_VAD_MODEL=str(self.vad_model),
        )
        self.mid = "m1"
        self.lines = [line(0, "others"), line(1, "me"), line(8, "others")]
        self.spans = [asr.Span("a.mp4", 0.0, 8.0), asr.Span("m.mp4", 1.0, None), asr.Span("a.mp4", 8.0, None)]

    def relabel(self, runner):
        return diarize.relabel(
            self.cfg, self.mid, self.lines, self.spans, runner=runner,
            self_cmd=["/bin/meeting-notes"], low_priority=lambda cfg, argv: ["ionice", "-c3", "nice", "-n19", *argv],
        )

    def test_success_labels_and_low_priority_argv(self):
        runner = FakeRunner(self.cfg, self.mid, data=CLUSTERS)
        lines, info = self.relabel(runner)
        self.assertEqual([side for _, side, _ in lines], ["others:S1", "me", "others:Bastien"])
        self.assertEqual(info, {"status": "ok", "speakers": 2, "named": ["Bastien"]})
        argv, kwargs = runner.calls[0]
        self.assertEqual(argv, ["ionice", "-c3", "nice", "-n19", "/bin/meeting-notes", "diarize", "m1"])
        self.assertEqual(kwargs["env"]["OMP_NUM_THREADS"], "3")
        self.assertEqual(kwargs["timeout"], diarize.TIMEOUT)

    def test_real_low_priority_on_linux(self):
        self.assertEqual(
            asr.low_priority(self.cfg, ["x"], platform="linux"), ["ionice", "-c3", "nice", "-n19", "x"]
        )

    def assert_fallback(self, runner, status="failed"):
        lines, info = self.relabel(runner)
        self.assertEqual(lines, self.lines)
        self.assertEqual(info["status"], status)
        saved = json.loads((self.cfg.meeting_dir(self.mid) / diarize.SPEAKERS_JSON).read_text())
        self.assertEqual(saved["status"], status)
        return info

    def test_crash_falls_back(self):
        info = self.assert_fallback(FakeRunner(self.cfg, self.mid, code=1))
        self.assertIn("exited 1", info["reason"])

    def test_timeout_falls_back(self):
        info = self.assert_fallback(FakeRunner(self.cfg, self.mid, timeout=True))
        self.assertIn("timed out", info["reason"])

    def test_missing_binary_falls_back(self):
        def runner(argv, **kwargs):
            raise FileNotFoundError("ionice")

        self.assert_fallback(runner)

    def test_too_little_speech_falls_back(self):
        data = {"status": "skipped", "reason": "only 40 s of speech"}
        info = self.assert_fallback(FakeRunner(self.cfg, self.mid, data=data), status="skipped")
        self.assertEqual(info["reason"], "only 40 s of speech")

    def test_stale_speakers_json_is_not_reused(self):
        target = self.cfg.meeting_dir(self.mid)
        target.mkdir(parents=True)
        (target / diarize.SPEAKERS_JSON).write_text(json.dumps(CLUSTERS))
        self.assert_fallback(FakeRunner(self.cfg, self.mid, code=0))

    def test_missing_models_skip_without_running(self):
        self.speaker_model.unlink()
        runner = FakeRunner(self.cfg, self.mid, data=CLUSTERS)
        lines, info = self.relabel(runner)
        self.assertEqual(lines, self.lines)
        self.assertEqual(info, {"status": "skipped", "reason": "missing speaker model"})
        self.assertEqual(runner.calls, [])

    def test_disabled(self):
        from .helpers import make_cfg

        self.cfg = make_cfg(self.root)
        _, info = self.relabel(FakeRunner(self.cfg, self.mid, data=CLUSTERS))
        self.assertEqual(info, {"status": "skipped", "reason": "disabled"})


class FetchFallbackTest(PipelineCase):
    def test_crashing_diarization_keeps_plain_others(self):
        from .test_fetch import FakeAsr, FakeScreenpipe

        start = NOW - timedelta(hours=1)
        mid = self.add(start, NOW - timedelta(minutes=30))
        lines = [(start, "others", "salut"), (start + timedelta(seconds=5), "me", "bonjour")]

        def boom(cfg, mid, lines, spans):
            raise RuntimeError("onnxruntime exploded")

        out = fetch.fetch(self.cfg, mid, asr=FakeAsr(lines), screenpipe=FakeScreenpipe([]), speakers=boom)
        text = (out / "transcript.txt").read_text()
        self.assertIn("] others | salut", text)
        meta = json.loads((out / "meta.json").read_text())
        self.assertEqual(meta["diarization"]["status"], "failed")
        self.assertTrue((out / "fetched.ok").exists())

    def test_labels_reach_the_transcript(self):
        from .test_fetch import FakeAsr, FakeScreenpipe

        start = NOW - timedelta(hours=1)
        mid = self.add(start, NOW - timedelta(minutes=30))
        lines = [
            (start, "others", "salut"),
            (start + timedelta(seconds=3), "others", "ça va"),
            (start + timedelta(seconds=6), "others", "oui"),
        ]
        named = ["others:Bastien", "others:Bastien", "others:S2"]

        def speakers(cfg, mid, lines, spans):
            return [(at, label, text) for (at, _, text), label in zip(lines, named)], {"status": "ok"}

        out = fetch.fetch(self.cfg, mid, asr=FakeAsr(lines), screenpipe=FakeScreenpipe([]), speakers=speakers)
        rows = (out / "transcript.txt").read_text().splitlines()
        self.assertEqual(len(rows), 2)
        self.assertIn("others:Bastien | salut ça va", rows[0])
        self.assertIn("others:S2 | oui", rows[1])
