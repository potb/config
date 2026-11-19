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

    def test_diarization_settings(self):
        c = Config.from_env(env())
        self.assertFalse(c.diarization)
        self.assertEqual(c.diarization_threads, 4)
        self.assertEqual(c.diarization_max_delay, 180)
        self.assertIsNone(c.speaker_model)
        self.assertEqual(c.voices_dir, Path(HOME) / ".local/share/meeting-notes/voices")
        c = Config.from_env(env(
            MEETING_NOTES_DIARIZATION="1",
            MEETING_NOTES_DIARIZATION_THREADS="2",
            MEETING_NOTES_DIARIZATION_MAX_DELAY="60",
            MEETING_NOTES_SPEAKER_MODEL="/s.onnx",
            MEETING_NOTES_DIARIZATION_VAD_MODEL="/v.onnx",
            MEETING_NOTES_VOICES_DIR="/voices",
        ))
        self.assertTrue(c.diarization)
        self.assertEqual((c.diarization_threads, c.diarization_max_delay), (2, 60))
        self.assertEqual((c.speaker_model, c.speech_vad_model), (Path("/s.onnx"), Path("/v.onnx")))
        self.assertEqual(c.voices_dir, Path("/voices"))

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

    def test_ignore_apps_env(self):
        self.assertEqual(Config.from_env(env()).ignore_apps, ())
        c = Config.from_env(env(MEETING_NOTES_IGNORE_APPS=" Obs, VoiceChat ,,"))
        self.assertEqual(c.ignore_apps, ("obs", "voicechat"))

    def test_slack_defaults(self):
        c = Config.from_env(env())
        self.assertEqual(c.slack_post_to, "dm")
        self.assertEqual(c.slack_channel, "")
        self.assertEqual(c.slack_user, "")

    def test_slack_destination_settings(self):
        c = Config.from_env(
            env(
                MEETING_NOTES_SLACK_POST_TO="channel",
                MEETING_NOTES_SLACK_CHANNEL="C0C23NA7EKX",
                MEETING_NOTES_SLACK_USER="U0C228DMEV9",
            )
        )
        self.assertEqual(c.slack_post_to, "channel")
        self.assertEqual(c.slack_channel, "C0C23NA7EKX")
        self.assertEqual(c.slack_user, "U0C228DMEV9")

    def test_slack_empty_post_to_means_dm(self):
        self.assertEqual(Config.from_env(env(MEETING_NOTES_SLACK_POST_TO="")).slack_post_to, "dm")

    def test_invalid_slack_post_to(self):
        with self.assertRaises(ValueError) as ctx:
            Config.from_env(env(MEETING_NOTES_SLACK_POST_TO="everyone"))
        self.assertIn("MEETING_NOTES_SLACK_POST_TO", str(ctx.exception))

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
