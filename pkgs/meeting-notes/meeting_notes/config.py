import os
from dataclasses import dataclass
from pathlib import Path

BACKENDS = ("native", "screenpipe")
SLACK_DESTINATIONS = ("dm", "channel")
NEVER = "never"


def _flag(environ, name, default):
    raw = environ.get(name)
    if raw is None or raw == "":
        return default
    if raw not in ("0", "1"):
        raise ValueError(f"{name} must be 0 or 1, got {raw!r}")
    return raw == "1"


def _int(environ, name, default):
    raw = environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None


def _retention(environ, name, default):
    raw = environ.get(name)
    if raw is None or raw == "":
        return default
    if raw == NEVER:
        return None
    days = _int(environ, name, default)
    if days < 1:
        raise ValueError(f"{name} must be a positive number of days or {NEVER!r}, got {raw!r}")
    return days


def _str(environ, name, default):
    raw = environ.get(name)
    return raw if raw else default


def _list(environ, name):
    raw = environ.get(name) or ""
    return tuple(item.strip().lower() for item in raw.split(",") if item.strip())


def _path(environ, name, default):
    raw = environ.get(name)
    return Path(raw) if raw else default


@dataclass(frozen=True)
class Config:
    data_dir: Path
    meetings_dir: Path
    backend: str
    live: bool
    language: str
    owner: str
    whisper: str
    model: Path | None
    vad_model: Path | None
    ffmpeg: str
    opencode: str
    notes_model: str
    tesseract: str
    ocr_languages: str
    retention_days: int | None
    min_minutes: int
    slack: bool
    slack_post_to: str
    slack_channel: str
    slack_user: str
    slack_token_file: Path | None
    screenpipe: str
    screenpipe_url: str
    audio_dir: Path
    ignore_apps: tuple[str, ...] = ()
    diarization: bool = False
    diarization_threads: int = 4
    diarization_max_delay: int = 180
    speaker_model: Path | None = None
    speech_vad_model: Path | None = None
    voices_dir: Path | None = None
    vad_bin: str = "whisper-vad-speech-segments"
    mic_source: str = ""
    monitor_source: str = ""
    glossary_repo: Path | None = None

    @classmethod
    def from_env(cls, environ=os.environ):
        home = Path(environ.get("HOME") or Path.home())
        data_dir = _path(environ, "MEETING_NOTES_DATA_DIR", home / ".local/share/meeting-notes")
        backend = _str(environ, "MEETING_NOTES_BACKEND", "native")
        if backend not in BACKENDS:
            raise ValueError(f"MEETING_NOTES_BACKEND must be one of {BACKENDS}, got {backend!r}")
        slack_post_to = _str(environ, "MEETING_NOTES_SLACK_POST_TO", "dm")
        if slack_post_to not in SLACK_DESTINATIONS:
            raise ValueError(
                f"MEETING_NOTES_SLACK_POST_TO must be one of {SLACK_DESTINATIONS}, got {slack_post_to!r}"
            )
        default_audio = data_dir / "audio" if backend == "native" else home / ".screenpipe/data"
        model = environ.get("MEETING_NOTES_MODEL")
        vad_model = environ.get("MEETING_NOTES_VAD_MODEL")
        whisper = _str(environ, "MEETING_NOTES_WHISPER", "whisper-cli")
        sibling = Path(whisper).parent / "whisper-vad-speech-segments" if "/" in whisper else None
        return cls(
            data_dir=data_dir,
            meetings_dir=_path(environ, "MEETING_NOTES_MEETINGS_DIR", home / "Meetings"),
            backend=backend,
            live=_flag(environ, "MEETING_NOTES_LIVE", False),
            language=_str(environ, "MEETING_NOTES_LANGUAGE", "fr"),
            owner=_str(environ, "MEETING_NOTES_OWNER", "Peïo"),
            whisper=whisper,
            model=Path(model) if model else None,
            vad_model=Path(vad_model) if vad_model else None,
            ffmpeg=_str(environ, "MEETING_NOTES_FFMPEG", "ffmpeg"),
            opencode=_str(environ, "MEETING_NOTES_OPENCODE", "opencode"),
            notes_model=_str(environ, "MEETING_NOTES_NOTES_MODEL", "claude-agent/sonnet"),
            tesseract=_str(environ, "MEETING_NOTES_TESSERACT", "tesseract"),
            ocr_languages=_str(environ, "MEETING_NOTES_OCR_LANGUAGES", "eng+fra"),
            retention_days=_retention(environ, "MEETING_NOTES_RETENTION_DAYS", 7),
            min_minutes=_int(environ, "MEETING_NOTES_MIN_MINUTES", 5),
            slack=_flag(environ, "MEETING_NOTES_SLACK", False),
            slack_post_to=slack_post_to,
            slack_channel=_str(environ, "MEETING_NOTES_SLACK_CHANNEL", ""),
            slack_user=_str(environ, "MEETING_NOTES_SLACK_USER", ""),
            slack_token_file=_path(environ, "MEETING_NOTES_SLACK_TOKEN_FILE", None),
            screenpipe=_str(environ, "MEETING_NOTES_SCREENPIPE", "screenpipe"),
            screenpipe_url=_str(environ, "MEETING_NOTES_SCREENPIPE_URL", "http://127.0.0.1:3030"),
            audio_dir=_path(environ, "MEETING_NOTES_AUDIO_DIR", default_audio),
            ignore_apps=_list(environ, "MEETING_NOTES_IGNORE_APPS"),
            diarization=_flag(environ, "MEETING_NOTES_DIARIZATION", False),
            diarization_threads=_int(environ, "MEETING_NOTES_DIARIZATION_THREADS", 4),
            diarization_max_delay=_int(environ, "MEETING_NOTES_DIARIZATION_MAX_DELAY", 180),
            speaker_model=_path(environ, "MEETING_NOTES_SPEAKER_MODEL", None),
            speech_vad_model=_path(environ, "MEETING_NOTES_DIARIZATION_VAD_MODEL", None),
            voices_dir=_path(environ, "MEETING_NOTES_VOICES_DIR", data_dir / "voices"),
            vad_bin=_str(environ, "MEETING_NOTES_VAD_BIN", str(sibling) if sibling else "whisper-vad-speech-segments"),
            mic_source=_str(environ, "MEETING_NOTES_MIC_SOURCE", ""),
            monitor_source=_str(environ, "MEETING_NOTES_MONITOR_SOURCE", ""),
            glossary_repo=_path(environ, "MEETING_NOTES_GLOSSARY_REPO", None),
        )

    @property
    def state_path(self):
        return self.data_dir / "state.json"

    @property
    def control_dir(self):
        return self.data_dir / "control"

    @property
    def work_dir(self):
        return self.data_dir / "work"

    @property
    def cache_dir(self):
        return self.work_dir / "asr-cache"

    @property
    def runs_dir(self):
        return self.data_dir / "runs"

    @property
    def key_path(self):
        return self.data_dir / "screenpipe.key"

    @property
    def pipe_md(self):
        return self.data_dir / "pipe.md"

    @property
    def glossary(self):
        return self.data_dir / "glossary.md"

    @property
    def company(self):
        try:
            return " ".join((self.data_dir / "company").read_text(encoding="utf-8").split())
        except OSError:
            return ""

    def meeting_dir(self, meeting_id):
        return self.work_dir / meeting_id

    def screens_dir(self, meeting_id):
        return self.meeting_dir(meeting_id) / "screens"
