import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from meeting_notes import chunks

UTC = timezone.utc


class ChunksTest(unittest.TestCase):
    def test_round_trip(self):
        t0 = datetime(2026, 10, 29, 14, 3, 0, tzinfo=UTC)
        for device, kind, side in [
            ("MacBook Pro Microphone", "input", "me"),
            ("Display 1 (Speakers)", "output", "others"),
        ]:
            name = chunks.chunk_name(device, kind, t0)
            self.assertEqual(chunks.parse(name), (device, side, t0))

    def test_real_name(self):
        name = "MacBook Pro Microphone (input)_2026-10-29_14-03-00.mp4"
        self.assertEqual(
            chunks.chunk_name(
                "MacBook Pro Microphone",
                "input",
                datetime(2026, 10, 29, 14, 3, tzinfo=UTC),
            ),
            name,
        )
        self.assertEqual(
            chunks.parse(name),
            (
                "MacBook Pro Microphone",
                "me",
                datetime(2026, 10, 29, 14, 3, tzinfo=UTC),
            ),
        )

    def test_pattern(self):
        self.assertEqual(
            chunks.ffmpeg_pattern("Mic", "input"),
            "Mic (input)_%Y-%m-%d_%H-%M-%S.mp4",
        )

    def test_parse_rejects(self):
        self.assertIsNone(chunks.parse("notes.txt"))
        self.assertIsNone(chunks.parse("Mic (other)_2026-10-29_14-03-00.mp4"))

    def test_constant(self):
        self.assertEqual(chunks.CHUNK_SECONDS, 30)

    def test_regex_exact(self):
        self.assertEqual(
            chunks.CHUNK_RE.pattern,
            r"^(?P<dev>.+) \((?P<kind>input|output)\)_(?P<ts>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.mp4$",
        )

    def make(self, d, device, kind, t0, mtime=None):
        p = Path(d) / chunks.chunk_name(device, kind, t0)
        p.write_bytes(b"x")
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    def test_meeting_chunks_window(self):
        base = datetime(2026, 10, 29, 14, 0, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as d:
            early = self.make(d, "M", "input", base - timedelta(seconds=90))
            edge = self.make(d, "M", "input", base - timedelta(seconds=30))
            mid = self.make(d, "O", "output", base + timedelta(minutes=1))
            late = self.make(d, "M", "input", base + timedelta(minutes=20))
            Path(d, "junk.txt").write_text("x")
            got = chunks.meeting_chunks(Path(d), base, base + timedelta(minutes=10))
            self.assertEqual(got, [edge, mid])
            self.assertNotIn(early, got)
            self.assertNotIn(late, got)

    def test_newest_by_side(self):
        base = datetime(2026, 10, 29, 14, 0, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as d:
            self.make(d, "M", "input", base, mtime=100)
            self.make(d, "M", "input", base + timedelta(seconds=30), mtime=200)
            self.make(d, "O", "output", base, mtime=150)
            self.assertEqual(
                chunks.newest_by_side(Path(d)), {"me": 200, "others": 150}
            )
            with tempfile.TemporaryDirectory() as e:
                self.assertEqual(
                    chunks.newest_by_side(Path(e)), {"me": None, "others": None}
                )

    def test_is_complete(self):
        t0 = datetime(2026, 10, 29, 14, 0, 0, tzinfo=UTC)
        now = t0 + timedelta(seconds=100)
        with tempfile.TemporaryDirectory() as d:
            p = self.make(
                d, "M", "input", t0, mtime=(t0 + timedelta(seconds=60)).timestamp()
            )
            self.assertTrue(chunks.is_complete(t0, p, now))
            self.assertFalse(chunks.is_complete(t0, p, t0 + timedelta(seconds=39)))
            fresh = self.make(
                d, "O", "output", t0, mtime=(now - timedelta(seconds=5)).timestamp()
            )
            self.assertFalse(chunks.is_complete(t0, fresh, now))


if __name__ == "__main__":
    unittest.main()
