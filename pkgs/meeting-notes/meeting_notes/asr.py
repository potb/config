import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import chunks

LOG = logging.getLogger(__name__)
CACHE_VERSION = 1
SILENCE_MAX_DB = -50.0
LOUD_MEAN_DB = -35.0
MIN_WORDS = 6
SLOW_SECONDS = 10.0
TASKPOLICY = "/usr/sbin/taskpolicy"

HALLUCINATIONS = frozenset(
    {
        "merci d'avoir regardé cette vidéo",
        "merci d'avoir regardé la vidéo",
        "merci d'avoir regardé",
        "sous-titrage st' 501",
        "sous-titrage société radio-canada",
        "thanks for watching",
        "thank you for watching",
        "...",
    }
)
HALLUCINATION_MARKERS = ("amara.org",)

LiveResult = namedtuple("LiveResult", "done slow")
_VOLUME_RE = re.compile(r"(mean|max)_volume:\s*(-?\d+(?:\.\d+)?|-inf)\s*dB")


class AsrError(RuntimeError):
    pass


class UnreadableChunk(AsrError):
    pass


def default_run(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def glossary_terms(path):
    path = Path(path)
    if not path.is_file():
        return []
    terms = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        term = line.lstrip("-*+ ").strip()
        if term and term not in terms:
            terms.append(term)
    return terms


def asr_prompt(cfg):
    terms = glossary_terms(cfg.glossary)
    if not terms:
        return ""
    joined = ", ".join(terms)
    if cfg.language == "fr":
        return f"Réunion de travail. Termes et noms propres fréquents : {joined}."
    return f"Work meeting. Frequent terms and proper names: {joined}."


def low_priority(cfg, argv, platform=sys.platform, exists=os.path.exists):
    if platform.startswith("linux"):
        return ["ionice", "-c3", "nice", "-n19", *argv]
    if platform == "darwin" and exists(TASKPOLICY):
        return [TASKPOLICY, "-b", *argv]
    return ["nice", "-n19", *argv]


def prefilter_argv(cfg, src, wav):
    return [
        cfg.ffmpeg, "-y", "-loglevel", "error", "-i", str(src),
        "-ar", "16000", "-ac", "1",
        "-af", "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11", str(wav),
    ]


def prefilter(cfg, src, wav, run=default_run, prefix=()):
    result = run([*prefix, *prefilter_argv(cfg, src, wav)])
    if result.returncode != 0:
        raise AsrError(f"ffmpeg prefilter failed: {result.stderr}")


def whisper_argv(cfg, wav, prefix, prompt, language):
    return [
        cfg.whisper, "-m", str(cfg.model), "-f", str(wav),
        "--vad", "--vad-model", str(cfg.vad_model),
        "-bs", "8", "-bo", "5", "-l", language,
        "--prompt", prompt, "-oj", "-of", str(prefix), "-np",
    ]


def volume_levels(cfg, path, run, prefix=()):
    argv = [
        *prefix, cfg.ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
        "-af", "volumedetect", "-f", "null", "-",
    ]
    result = run(argv)
    if result.returncode != 0:
        raise UnreadableChunk(f"ffmpeg volumedetect failed: {result.stderr}")
    levels = {}
    for kind, value in _VOLUME_RE.findall((result.stdout or "") + (result.stderr or "")):
        levels[kind] = float("-inf") if value == "-inf" else float(value)
    return levels.get("mean", float("-inf")), levels.get("max", float("-inf"))


def cache_path(cfg, path):
    model = Path(cfg.model).name if cfg.model else "none"
    return Path(cfg.cache_dir) / f"{Path(path).name}.{model}.v{CACHE_VERSION}.json"


def cached(cfg, path):
    return cache_path(cfg, path).is_file()


def _read_cache(cfg, path):
    try:
        data = json.loads(cache_path(cfg, path).read_text(encoding="utf-8"))
        return [[float(offset), text] for offset, text in data["segments"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_cache(cfg, path, segments):
    target = cache_path(cfg, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(json.dumps({"segments": segments}, ensure_ascii=False))
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _is_hallucination(text):
    norm = text.strip().lower().rstrip(" .!?…")
    if norm in HALLUCINATIONS or text.strip().lower() in HALLUCINATIONS:
        return True
    return any(marker in norm for marker in HALLUCINATION_MARKERS)


def _parse_whisper(prefix):
    try:
        data = json.loads(Path(f"{prefix}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AsrError(f"whisper output unreadable: {exc}") from exc
    segments = []
    for item in data.get("transcription", []):
        text = (item.get("text") or "").strip()
        if not text or _is_hallucination(text):
            continue
        offset = float(item.get("offsets", {}).get("from", 0)) / 1000.0
        segments.append([offset, text])
    return segments


def _word_count(segments):
    return sum(len(text.split()) for _, text in segments)


def _decode(cfg, wav, workdir, prompt, tag, run, prefix):
    out = str(Path(workdir) / tag)
    argv = [*prefix, *whisper_argv(cfg, wav, out, prompt, cfg.language)]
    result = run(argv)
    if result.returncode != 0:
        raise AsrError(f"whisper failed: {result.stderr}")
    return _parse_whisper(out)


def transcribe_chunk(cfg, path, side, prompt, run=default_run, low=False, timer=time.monotonic):
    hit = _read_cache(cfg, path)
    if hit is not None:
        return hit, 0.0
    started = timer()
    prefix = low_priority(cfg, []) if low else []
    mean, peak = volume_levels(cfg, path, run, prefix)
    if peak < SILENCE_MAX_DB:
        _write_cache(cfg, path, [])
        return [], timer() - started
    with tempfile.TemporaryDirectory(prefix="asr-") as workdir:
        wav = Path(workdir) / "chunk.wav"
        prefilter(cfg, path, wav, run, prefix)
        segments = _decode(cfg, wav, workdir, prompt, "first", run, prefix)
        if _word_count(segments) < MIN_WORDS and mean > LOUD_MEAN_DB:
            retry = _decode(cfg, wav, workdir, "", "retry", run, prefix)
            if _word_count(retry) > _word_count(segments):
                segments = retry
    _write_cache(cfg, path, segments)
    return segments, timer() - started


def live_pass(cfg, start, prompt, should_stop, run=default_run, clock=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = clock()
    done = 0
    for path in chunks.meeting_chunks(cfg.audio_dir, start, now):
        parsed = chunks.parse(path.name)
        if not parsed:
            continue
        _, side, t0 = parsed
        if should_stop():
            break
        if not chunks.is_complete(t0, path, now) or cached(cfg, path):
            continue
        before = clock()
        try:
            transcribe_chunk(cfg, path, side, prompt, run, low=True)
        except AsrError:
            continue
        done += 1
        if (clock() - before).total_seconds() > SLOW_SECONDS:
            return LiveResult(done, True)
    return LiveResult(done, False)


def available(cfg, which=shutil.which):
    if not which(cfg.whisper) or not which(cfg.ffmpeg):
        return False
    return all(p is not None and Path(p).is_file() for p in (cfg.model, cfg.vad_model))


def transcribe(cfg, start, end, prompt, run=default_run, available=available, floor=None, skipped=None):
    if not available(cfg):
        return None
    paths = chunks.meeting_chunks(cfg.audio_dir, start, end, floor=floor)
    if not paths:
        return None
    lines = []
    for path in paths:
        parsed = chunks.parse(path.name)
        if not parsed:
            continue
        _, side, t0 = parsed
        try:
            segments, _ = transcribe_chunk(cfg, path, side, prompt, run)
        except UnreadableChunk as error:
            LOG.warning("skipping unreadable chunk %s: %s", path.name, error)
            if skipped is not None:
                skipped.append(path.name)
            continue
        for offset, text in segments:
            lines.append((t0 + timedelta(seconds=offset), side, text))
    return sorted(lines, key=lambda line: (line[0], line[1]))


def prune_cache(cfg, days, now=None):
    directory = Path(cfg.cache_dir)
    if not directory.is_dir():
        return 0
    cutoff = (now or datetime.now(timezone.utc)).timestamp() - days * 86400
    removed = 0
    for entry in directory.iterdir():
        if entry.is_file() and entry.stat().st_mtime < cutoff:
            entry.unlink()
            removed += 1
    return removed
