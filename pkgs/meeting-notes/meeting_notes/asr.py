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
CACHE_VERSION = 2
SILENCE_MAX_DB = -50.0
LOUD_MEAN_DB = -35.0
MIN_WORDS = 6
SLOW_SECONDS = 10.0
VAD_THRESHOLD = "0.6"
PROMPT_MAX_CHARS = 550
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
HALLUCINATION_MARKERS = ("amara.org", "bit.ly")
HALLUCINATION_PHRASES = ("follow me", "sous-titrage", "réalisé par")
PHRASE_MAX_WORDS = 15

_WARNED = set()
LiveResult = namedtuple("LiveResult", "done slow")
Span = namedtuple("Span", "chunk offset following end words", defaults=(None, ()))
_VOLUME_RE = re.compile(r"(mean|max)_volume:\s*(-?\d+(?:\.\d+)?|-inf)\s*dB")
_VAD_RE = re.compile(r"Detected\s+(\d+)\s+speech segments")
_EDGE_RE = re.compile(r"^[\W_]+|[\W_]+$")


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
        if not line.startswith(("- ", "* ", "+ ")):
            continue
        term = line[2:].split(" — ")[0].strip()
        if term and term not in terms:
            terms.append(term)
    return terms


def asr_prompt(cfg):
    terms = glossary_terms(cfg.glossary)
    if not terms:
        return ""
    company = cfg.company
    if cfg.language == "fr":
        place = f" chez {company}," if company else ""
        head, tail = f"Réunion de travail{place} avec {cfg.owner}. Termes : ", "."
    else:
        place = f" at {company}," if company else ""
        head, tail = f"Work meeting{place} with {cfg.owner}. Terms: ", "."
    kept = []
    for term in terms:
        if term in (company, cfg.owner):
            continue
        if len(head) + len(", ".join([*kept, term])) + len(tail) > PROMPT_MAX_CHARS:
            break
        kept.append(term)
    return f"{head}{', '.join(kept)}{tail}"


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
        "-af", "highpass=f=80", str(wav),
    ]


def prefilter(cfg, src, wav, run=default_run, prefix=()):
    result = run([*prefix, *prefilter_argv(cfg, src, wav)])
    if result.returncode != 0:
        raise AsrError(f"ffmpeg prefilter failed: {result.stderr}")


def whisper_argv(cfg, wav, prefix, prompt, language):
    return [
        cfg.whisper, "-m", str(cfg.model), "-f", str(wav),
        "--vad", "--vad-model", str(cfg.vad_model), "-vt", VAD_THRESHOLD,
        "--suppress-nst", "-bs", "8", "-bo", "5", "-l", language,
        "--prompt", prompt, "-oj", "-ojf", "-of", str(prefix), "-np",
    ]


def vad_argv(cfg, wav):
    return [str(cfg.vad_bin), "-vm", str(cfg.vad_model), "-vt", VAD_THRESHOLD, "-np", "-f", str(wav)]


def vad_available(cfg, which=shutil.which):
    return bool(cfg.vad_bin) and which(str(cfg.vad_bin)) is not None


def speech_segments(cfg, wav, run, prefix=()):
    result = run([*prefix, *vad_argv(cfg, wav)])
    if result.returncode != 0:
        raise AsrError(f"whisper-vad-speech-segments failed: {result.stderr}")
    found = _VAD_RE.search(result.stdout or "")
    if not found:
        raise AsrError("whisper-vad-speech-segments printed no segment count")
    return int(found.group(1))


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
        return [
            [float(begin), float(end), str(text), [[float(a), float(b), str(w)] for a, b, w in words]]
            for begin, end, text, words in data["segments"]
        ]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
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


def _normalize(text):
    return " ".join(_EDGE_RE.sub("", text.strip().lower()).split())


def _is_hallucination(text):
    lowered = text.strip().lower()
    norm = _normalize(text)
    if norm in HALLUCINATIONS or lowered in HALLUCINATIONS:
        return True
    if any(marker in lowered for marker in HALLUCINATION_MARKERS):
        return True
    return len(norm.split()) <= PHRASE_MAX_WORDS and any(phrase in norm for phrase in HALLUCINATION_PHRASES)


def _words(tokens, start, stop):
    timed = [token.get("offsets", {}) for token in tokens]
    low = min((float(t.get("from", 0)) for t in timed), default=0.0) / 1000.0
    high = max((float(t.get("to", 0)) for t in timed), default=0.0) / 1000.0
    scale = (stop - start) / (high - low) if high > low else 1.0

    def place(value):
        return round(min(stop, max(start, start + (value - low) * scale)), 3)

    words = []
    for token in tokens:
        piece = token.get("text") or ""
        if piece.startswith("[_"):
            continue
        offsets = token.get("offsets", {})
        begin = place(float(offsets.get("from", 0)) / 1000.0)
        end = place(float(offsets.get("to", 0)) / 1000.0)
        stripped = piece.strip()
        if not stripped:
            continue
        glued = not piece.startswith(" ") or not any(ch.isalnum() for ch in stripped)
        if words and glued:
            words[-1][1] = max(words[-1][1], end)
            words[-1][2] += stripped if piece.startswith(" ") else piece
        else:
            words.append([begin, end, stripped])
    return words


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
        offsets = item.get("offsets", {})
        begin = float(offsets.get("from", 0)) / 1000.0
        end = float(offsets.get("to", 0)) / 1000.0
        segments.append([begin, end, text, _words(item.get("tokens", []), begin, end)])
    return segments


def _word_count(segments):
    return sum(len(segment[2].split()) for segment in segments)


def _retry_wins(first, retry):
    before, after = _word_count(first), _word_count(retry)
    return after > before and after >= 2 * before


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
    use_vad = vad_available(cfg)
    if not use_vad:
        if cfg.vad_bin not in _WARNED:
            _WARNED.add(cfg.vad_bin)
            LOG.warning("%s not found, falling back to the -50 dB volume threshold", cfg.vad_bin)
        if peak < SILENCE_MAX_DB:
            _write_cache(cfg, path, [])
            return [], timer() - started
    with tempfile.TemporaryDirectory(prefix="asr-") as workdir:
        wav = Path(workdir) / "chunk.wav"
        prefilter(cfg, path, wav, run, prefix)
        if use_vad and speech_segments(cfg, wav, run, prefix) == 0:
            _write_cache(cfg, path, [])
            return [], timer() - started
        segments = _decode(cfg, wav, workdir, prompt, "first", run, prefix)
        if _word_count(segments) < MIN_WORDS and (use_vad or mean > LOUD_MEAN_DB):
            retry = _decode(cfg, wav, workdir, "", "retry", run, prefix)
            if _retry_wins(segments, retry):
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


def transcribe(cfg, start, end, prompt, run=default_run, available=available, floor=None, skipped=None, spans=None):
    if not available(cfg):
        return None
    paths = chunks.meeting_chunks(cfg.audio_dir, start, end, floor=floor)
    if not paths:
        return None
    rows = []
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
        for index, (begin, end, text, words) in enumerate(segments):
            following = segments[index + 1][0] if index + 1 < len(segments) else None
            span = Span(path.name, begin, following, end, tuple(tuple(word) for word in words))
            rows.append((t0 + timedelta(seconds=begin), side, text, span))
    rows.sort(key=lambda row: (row[0], row[1]))
    if spans is not None:
        spans.extend(row[3] for row in rows)
    return [row[:3] for row in rows]


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
