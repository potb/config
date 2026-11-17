import os
from dataclasses import dataclass
from pathlib import Path

BACKENDS = ("native", "screenpipe")


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


def _str(environ, name, default):
    raw = environ.get(name)
    return raw if raw else default


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
    claude: str
    retention_days: int
    min_minutes: int
    slack: bool
    screenpipe: str
    screenpipe_url: str
    audio_dir: Path

    @classmethod
    def from_env(cls, environ=os.environ):
        home = Path(environ.get("HOME") or Path.home())
        data_dir = _path(environ, "MEETING_NOTES_DATA_DIR", home / ".local/share/meeting-notes")
        backend = _str(environ, "MEETING_NOTES_BACKEND", "native")
        if backend not in BACKENDS:
            raise ValueError(f"MEETING_NOTES_BACKEND must be one of {BACKENDS}, got {backend!r}")
        default_audio = data_dir / "audio" if backend == "native" else home / ".screenpipe/data"
        model = environ.get("MEETING_NOTES_MODEL")
        vad_model = environ.get("MEETING_NOTES_VAD_MODEL")
        return cls(
            data_dir=data_dir,
            meetings_dir=_path(environ, "MEETING_NOTES_MEETINGS_DIR", home / "Meetings"),
            backend=backend,
            live=_flag(environ, "MEETING_NOTES_LIVE", False),
            language=_str(environ, "MEETING_NOTES_LANGUAGE", "fr"),
            owner=_str(environ, "MEETING_NOTES_OWNER", "Peïo"),
            whisper=_str(environ, "MEETING_NOTES_WHISPER", "whisper-cli"),
            model=Path(model) if model else None,
            vad_model=Path(vad_model) if vad_model else None,
            ffmpeg=_str(environ, "MEETING_NOTES_FFMPEG", "ffmpeg"),
            claude=_str(environ, "MEETING_NOTES_CLAUDE", "claude"),
            retention_days=_int(environ, "MEETING_NOTES_RETENTION_DAYS", 7),
            min_minutes=_int(environ, "MEETING_NOTES_MIN_MINUTES", 5),
            slack=_flag(environ, "MEETING_NOTES_SLACK", False),
            screenpipe=_str(environ, "MEETING_NOTES_SCREENPIPE", "screenpipe"),
            screenpipe_url=_str(environ, "MEETING_NOTES_SCREENPIPE_URL", "http://127.0.0.1:3030"),
            audio_dir=_path(environ, "MEETING_NOTES_AUDIO_DIR", default_audio),
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

    def meeting_dir(self, meeting_id):
        return self.work_dir / meeting_id

    def screens_dir(self, meeting_id):
        return self.meeting_dir(meeting_id) / "screens"
