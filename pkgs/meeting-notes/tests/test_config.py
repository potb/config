import unittest
from pathlib import Path

from meeting_notes.config import Config

HOME = "/home/tester"


def env(**extra):
    return {"HOME": HOME, **extra}


class ConfigTest(unittest.TestCase):
    def test_defaults(self):
        c = Config.from_env(env())
        data = Path(HOME) / ".local/share/meeting-notes"
        self.assertEqual(c.data_dir, data)
        self.assertEqual(c.meetings_dir, Path(HOME) / "Meetings")
        self.assertEqual(c.backend, "native")
        self.assertFalse(c.live)
        self.assertEqual(c.language, "fr")
        self.assertEqual(c.owner, "Peïo")
        self.assertEqual(c.whisper, "whisper-cli")
        self.assertIsNone(c.model)
        self.assertIsNone(c.vad_model)
        self.assertEqual(c.ffmpeg, "ffmpeg")
        self.assertEqual(c.claude, "claude")
        self.assertEqual(c.retention_days, 7)
        self.assertEqual(c.min_minutes, 5)
        self.assertFalse(c.slack)
        self.assertEqual(c.screenpipe, "screenpipe")
        self.assertEqual(c.screenpipe_url, "http://127.0.0.1:3030")
        self.assertEqual(c.audio_dir, data / "audio")

    def test_derived_paths(self):
        c = Config.from_env(env(MEETING_NOTES_DATA_DIR="/d"))
        self.assertEqual(c.state_path, Path("/d/state.json"))
        self.assertEqual(c.control_dir, Path("/d/control"))
        self.assertEqual(c.work_dir, Path("/d/work"))
        self.assertEqual(c.cache_dir, Path("/d/work/asr-cache"))
        self.assertEqual(c.runs_dir, Path("/d/runs"))
        self.assertEqual(c.key_path, Path("/d/screenpipe.key"))
        self.assertEqual(c.pipe_md, Path("/d/pipe.md"))
        self.assertEqual(c.glossary, Path("/d/glossary.md"))
        self.assertEqual(c.meeting_dir("x"), Path("/d/work/x"))
        self.assertEqual(c.screens_dir("x"), Path("/d/work/x/screens"))

    def test_screenpipe_audio_dir(self):
        c = Config.from_env(env(MEETING_NOTES_BACKEND="screenpipe"))
        self.assertEqual(c.audio_dir, Path(HOME) / ".screenpipe/data")

    def test_explicit_audio_dir(self):
        c = Config.from_env(env(MEETING_NOTES_AUDIO_DIR="/a"))
        self.assertEqual(c.audio_dir, Path("/a"))

    def test_invalid_backend(self):
        with self.assertRaises(ValueError):
            Config.from_env(env(MEETING_NOTES_BACKEND="other"))

    def test_overrides(self):
        c = Config.from_env(
            env(
                MEETING_NOTES_LIVE="1",
                MEETING_NOTES_SLACK="1",
                MEETING_NOTES_LANGUAGE="auto",
                MEETING_NOTES_RETENTION_DAYS="3",
                MEETING_NOTES_MIN_MINUTES="10",
                MEETING_NOTES_MODEL="/m.bin",
                MEETING_NOTES_VAD_MODEL="/v.bin",
                MEETING_NOTES_WHISPER="/bin/w",
            )
        )
        self.assertTrue(c.live)
        self.assertTrue(c.slack)
        self.assertEqual(c.language, "auto")
        self.assertEqual(c.retention_days, 3)
        self.assertEqual(c.min_minutes, 10)
        self.assertEqual(c.model, Path("/m.bin"))
        self.assertEqual(c.vad_model, Path("/v.bin"))
        self.assertEqual(c.whisper, "/bin/w")

    def test_invalid_flag_and_int(self):
        with self.assertRaises(ValueError):
            Config.from_env(env(MEETING_NOTES_LIVE="yes"))
        with self.assertRaises(ValueError):
            Config.from_env(env(MEETING_NOTES_RETENTION_DAYS="x"))

    def test_frozen(self):
        c = Config.from_env(env())
        with self.assertRaises(Exception):
            c.owner = "x"


if __name__ == "__main__":
    unittest.main()
