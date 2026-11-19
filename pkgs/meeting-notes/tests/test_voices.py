import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import numpy as np

from meeting_notes import cli, diarize, voices
from meeting_notes.config import Config

from .test_cli import env_for


def unit(*pairs):
    vector = np.zeros(256)
    for index, value in pairs:
        vector[index] = value
    return vector / np.linalg.norm(vector)


def prints(*items):
    return [voices.record(name, vector, 60, []) for name, vector in items]


class MatchTest(unittest.TestCase):
    def test_threshold(self):
        stored = prints(("Ada", unit((0, 1))), ("Bob", unit((1, 1))))
        low = unit((0, 0.55), (2, 0.835))
        high = unit((0, 0.7), (2, 0.714))
        result = voices.match([low, high], stored)
        self.assertIsNone(result[0]["name"])
        self.assertAlmostEqual(result[0]["cosine"], 0.55, places=2)
        self.assertEqual(result[1]["name"], "Ada")

    def test_margin(self):
        stored = prints(("Ada", unit((0, 1))), ("Bob", unit((1, 1))))
        close = unit((0, 0.75), (1, 0.65))
        clear = unit((0, 0.9), (1, 0.3))
        result = voices.match([close, clear], stored)
        self.assertIsNone(result[0]["name"])
        self.assertLess(result[0]["margin"], voices.MATCH_MARGIN)
        self.assertEqual(result[1]["name"], "Ada")
        self.assertAlmostEqual(result[1]["margin"], 0.6, places=1)

    def test_each_print_once_best_cluster_wins(self):
        stored = prints(("Ada", unit((0, 1))), ("Bob", unit((1, 1))))
        weaker = unit((0, 0.8), (3, 0.6))
        stronger = unit((0, 0.95), (3, 0.31))
        bob = unit((1, 1))
        result = voices.match([weaker, stronger, bob], stored)
        self.assertEqual([item["name"] for item in result], [None, "Ada", "Bob"])

    def test_no_prints(self):
        result = voices.match([unit((0, 1))], [])
        self.assertEqual(result, [{"name": None, "cosine": None, "margin": None}])

    def test_single_print_margin_is_against_zero(self):
        result = voices.match([unit((0, 1))], prints(("Ada", unit((0, 1)))))
        self.assertEqual(result[0]["name"], "Ada")
        self.assertAlmostEqual(result[0]["margin"], 1.0)

    def test_slug(self):
        self.assertEqual(voices.slug("Peïo Thibault"), "peio-thibault")
        with self.assertRaises(voices.VoiceError):
            voices.slug("!!")

    def test_merge_weights_by_seconds(self):
        old = voices.record("Ada", unit((0, 1)), 300, ["m1"])
        merged = voices.merge(old, "Ada", unit((1, 1)), 100, "m2")
        vector = np.array(merged["vector"])
        self.assertAlmostEqual(vector[0] / vector[1], 3.0, places=5)
        self.assertEqual(merged["seconds"], 400)
        self.assertEqual(merged["meetings"], ["m1", "m2"])
        with self.assertRaises(voices.VoiceError):
            voices.merge(merged, "Ada", unit((1, 1)), 100, "m2")

    def test_bad_vector_rejected(self):
        with self.assertRaises(voices.VoiceError):
            voices.record("Ada", np.zeros(256), 1, [])
        with self.assertRaises(voices.VoiceError):
            voices.record("Ada", np.ones(10), 1, [])

    def test_load_skips_broken_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            voices.write(tmp, voices.record("Ada", unit((0, 1)), 1, []))
            (Path(tmp) / "broken.json").write_text("{")
            with self.assertLogs("meeting_notes.voices", level="WARNING") as logs:
                self.assertEqual([item["name"] for item in voices.load(tmp)], ["Ada"])
            self.assertIn("broken.json", logs.output[0])
            self.assertEqual(voices.load(Path(tmp) / "missing"), [])


class VoicesCliTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.env = env_for(self.root)
        self.cfg = Config.from_env(self.env)

    def call(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["voices", *argv], environ=self.env)
        return code, out.getvalue(), err.getvalue()

    def diarized(self, mid, status="ok"):
        folder = self.cfg.meeting_dir(mid)
        folder.mkdir(parents=True)
        data = {
            "status": status,
            "clusters": [
                {"id": "S1", "name": None, "seconds": 120.0, "turns": []},
                {"id": "S2", "name": None, "seconds": 40.0, "turns": []},
            ],
        }
        (folder / diarize.SPEAKERS_JSON).write_text(json.dumps(data))
        embeddings = np.stack([unit((0, 1)), unit((0, 1), (2, 0.2)), unit((1, 1)), unit((1, 1), (3, 0.1))])
        np.savez(
            folder / diarize.SPEAKERS_NPZ,
            embeddings=embeddings.astype(np.float32),
            windows=np.zeros((4, 2), dtype=np.float32),
            labels=np.array([0, 0, 1, -1], dtype=np.int32),
        )

    def stored(self, name):
        return voices.find(self.cfg.voices_dir, name)

    def test_list_empty(self):
        code, out, _ = self.call("list")
        self.assertEqual(code, 0)
        self.assertIn("no voice prints", out)

    def test_add_list_remove(self):
        self.diarized("m1")
        code, out, err = self.call("add", "--id", "m1", "--speaker", "S2", "--name", "Quentin")
        self.assertEqual(code, 0, err)
        self.assertIn("created Quentin", out)
        entry = self.stored("Quentin")
        self.assertEqual(entry["meetings"], ["m1"])
        self.assertEqual(entry["seconds"], 40.0)
        self.assertAlmostEqual(entry["vector"][1], 1.0, places=5)
        self.assertEqual(sorted(entry), ["confirmed_at", "meetings", "name", "seconds", "vector"])
        path = self.cfg.voices_dir / "quentin.json"
        self.assertTrue(path.is_file())
        self.assertEqual(self.cfg.voices_dir.stat().st_mode & 0o777, 0o700)
        code, out, _ = self.call("list")
        self.assertIn("Quentin: 40 s, meetings m1", out)
        self.assertNotIn("vector", out)
        code, out, _ = self.call("remove", "--name", "Quentin")
        self.assertEqual(code, 0)
        self.assertFalse(path.exists())
        code, _, err = self.call("remove", "--name", "Quentin")
        self.assertEqual(code, 1)
        self.assertIn("no voice print named Quentin", err)

    def test_add_updates_existing_print_weighted(self):
        self.diarized("m1")
        self.diarized("m2")
        self.call("add", "--id", "m1", "--speaker", "S1", "--name", "Ada")
        code, out, _ = self.call("add", "--id", "m2", "--speaker", "S2", "--name", "Ada")
        self.assertEqual(code, 0)
        self.assertIn("updated Ada", out)
        entry = self.stored("Ada")
        self.assertEqual(entry["meetings"], ["m1", "m2"])
        self.assertEqual(entry["seconds"], 160.0)
        self.assertGreater(entry["vector"][0], entry["vector"][1] * 2.5)
        code, _, err = self.call("add", "--id", "m2", "--speaker", "S2", "--name", "Ada")
        self.assertEqual(code, 1)
        self.assertIn("already holds meeting m2", err)

    def test_add_errors(self):
        code, _, err = self.call("add", "--id", "nope", "--speaker", "S1", "--name", "Ada")
        self.assertEqual(code, 1)
        self.assertIn("no readable speakers.json", err)
        self.diarized("m1")
        code, _, err = self.call("add", "--id", "m1", "--speaker", "S9", "--name", "Ada")
        self.assertEqual(code, 1)
        self.assertIn("found S1, S2", err)
        (self.cfg.meeting_dir("m1") / diarize.SPEAKERS_NPZ).unlink()
        code, _, err = self.call("add", "--id", "m1", "--speaker", "S1", "--name", "Ada")
        self.assertEqual(code, 1)
        self.assertIn("no window embeddings", err)
        self.assertIsNone(self.stored("Ada"))

    def test_add_refuses_failed_diarization(self):
        self.diarized("m1", status="failed")
        code, _, err = self.call("add", "--id", "m1", "--speaker", "S1", "--name", "Ada")
        self.assertEqual(code, 1)
        self.assertIn("was not diarized", err)

    def test_import_npz_and_json(self):
        npz = self.root / "prints.npz"
        np.savez(npz, Bastien=unit((4, 2)), Quentin=unit((5, 1)))
        code, out, err = self.call("import", "--name", "Bastien", "--file", str(npz), "--key", "Bastien", "--id", "m0")
        self.assertEqual(code, 0, err)
        entry = self.stored("Bastien")
        self.assertAlmostEqual(entry["vector"][4], 1.0)
        self.assertEqual(entry["meetings"], ["m0"])
        code, _, err = self.call("import", "--name", "Bastien", "--file", str(npz), "--key", "Bastien")
        self.assertEqual(code, 1)
        self.assertIn("remove it first", err)
        code, _, err = self.call("import", "--name", "Hugo", "--file", str(npz), "--key", "Hugo")
        self.assertEqual(code, 1)
        self.assertIn("no array 'Hugo'", err)
        source = self.root / "result.json"
        source.write_text(json.dumps({"prints": {"Quentin": unit((5, 1)).tolist()}}))
        code, _, err = self.call("import", "--name", "Quentin", "--file", str(source), "--key", "Quentin", "--seconds", "90")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.stored("Quentin")["seconds"], 90.0)

    def test_voices_needs_action(self):
        code, _, _ = self.call()
        self.assertEqual(code, 2)
