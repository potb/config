import os
from datetime import timedelta

from meeting_notes import chunks, cleanup, state

from .helpers import NOW, PipelineCase, parse_iso


def chunk(directory, t0):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / chunks.chunk_name("mic", "input", t0)
    path.write_bytes(b"x")
    return path


class CleanupTest(PipelineCase):
    def old(self, days, **kw):
        end = NOW - timedelta(days=days)
        return self.add(end - timedelta(minutes=30), end, **kw)

    def artefacts(self, mid):
        start = parse_iso(self.load()["meetings"][mid]["start"])
        audio = chunk(self.cfg.audio_dir, start + timedelta(minutes=5))
        shot = self.cfg.screens_dir(mid) / "a.png"
        shot.parent.mkdir(parents=True)
        shot.write_bytes(b"x")
        wav = self.cfg.meeting_dir(mid) / "a.wav"
        keep = self.cfg.meeting_dir(mid) / "transcript.txt"
        wav.write_bytes(b"x")
        keep.write_text("t")
        return audio, shot, wav, keep

    def test_removes_after_retention(self):
        mid = self.old(8, status=state.DONE)
        audio, shot, wav, keep = self.artefacts(mid)
        cleanup.run(self.cfg, NOW, None)
        self.assertFalse(audio.exists())
        self.assertFalse(shot.exists())
        self.assertFalse(wav.exists())
        self.assertTrue(keep.exists())

    def test_removes_window_embeddings_keeps_speakers_json(self):
        mid = self.old(8, status=state.DONE)
        self.artefacts(mid)
        embeddings = self.cfg.meeting_dir(mid) / "speakers.npz"
        speakers = self.cfg.meeting_dir(mid) / "speakers.json"
        embeddings.write_bytes(b"x")
        speakers.write_text("{}")
        removed = cleanup.run(self.cfg, NOW, None)
        self.assertFalse(embeddings.exists())
        self.assertTrue(speakers.exists())
        self.assertEqual(removed["embeddings"], 1)

    def test_keeps_chunk_of_previous_meeting(self):
        end = NOW - timedelta(days=8)
        self.add(end - timedelta(minutes=40), end - timedelta(minutes=10, seconds=20))
        self.add(end - timedelta(minutes=10), end, status=state.DONE)
        tail = chunk(self.cfg.audio_dir, end - timedelta(minutes=10, seconds=30))
        cleanup.run(self.cfg, NOW, None)
        self.assertTrue(tail.exists())

    def test_keeps_inside_retention(self):
        mid = self.old(6, status=state.DONE)
        paths = self.artefacts(mid)
        cleanup.run(self.cfg, NOW, None)
        for path in paths:
            self.assertTrue(path.exists())

    def test_exactly_retention_removed(self):
        mid = self.old(7, status=state.DONE)
        audio, *_ = self.artefacts(mid)
        cleanup.run(self.cfg, NOW, None)
        self.assertFalse(audio.exists())

    def test_non_terminal_kept(self):
        mid = self.old(30, status=state.NOTES_SAVED)
        audio, shot, wav, _ = self.artefacts(mid)
        cleanup.run(self.cfg, NOW, None)
        for path in (audio, shot, wav):
            self.assertTrue(path.exists())

    def test_unprocessed_kept(self):
        mid = self.old(30)
        audio, *_ = self.artefacts(mid)
        cleanup.run(self.cfg, NOW, None)
        self.assertTrue(audio.exists())

    def test_screenpipe_backend_audio_untouched(self):
        mid = self.old(10, status=state.DONE, backend="screenpipe")
        audio, shot, wav, _ = self.artefacts(mid)
        cleanup.run(self.cfg, NOW, None)
        self.assertTrue(audio.exists())
        self.assertFalse(shot.exists())
        self.assertFalse(wav.exists())

    def test_meetings_dir_untouched(self):
        mid = self.old(10, status=state.DONE)
        self.artefacts(mid)
        notes = self.cfg.meetings_dir / "2026-05-01 Sync" / "notes.md"
        notes.parent.mkdir(parents=True)
        notes.write_text("n")
        old = (NOW - timedelta(days=100)).timestamp()
        os.utime(notes, (old, old))
        cleanup.run(self.cfg, NOW, None)
        self.assertTrue(notes.exists())

    def test_prunes_asr_cache(self):
        self.cfg.cache_dir.mkdir(parents=True)
        stale = self.cfg.cache_dir / "old.json"
        fresh = self.cfg.cache_dir / "new.json"
        stale.write_text("{}")
        fresh.write_text("{}")
        old = (NOW - timedelta(days=30)).timestamp()
        os.utime(stale, (old, old))
        os.utime(fresh, (NOW.timestamp(), NOW.timestamp()))
        cleanup.run(self.cfg, NOW, None)
        self.assertFalse(stale.exists())
        self.assertTrue(fresh.exists())
