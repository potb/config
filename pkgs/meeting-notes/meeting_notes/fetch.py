import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone
from itertools import groupby

from . import asr as asr_module
from . import diarize as diarize_module
from . import state

LOG = logging.getLogger(__name__)
OCR_TIMEOUT = 120
LINE_LIMIT = 1500
SENTENCE_END = (".", "?", "!", "\u2026")
PAUSE_END = (",", ";", ":")


def _parse(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _write(path, text):
    path.write_text(text, encoding="utf-8")


def units(text):
    return len(text.encode("utf-16-le")) // 2


def _rank(text, start, index, marks):
    tail = text[start:index].rstrip()[-1:]
    if tail in SENTENCE_END:
        return 2
    if tail in PAUSE_END or index in marks:
        return 1
    return 0


def _fit(text, start, budget):
    low, high = start, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if units(text[start:middle]) <= budget:
            low = middle
        else:
            high = middle - 1
    return low


def cuts(text, budget, marks=()):
    marks = set(marks)
    pieces = []
    start = 0
    while True:
        while pieces and start < len(text) and text[start] == " ":
            start += 1
        if pieces and start >= len(text):
            return pieces
        end = _fit(text, start, budget)
        if end >= len(text):
            pieces.append((start, len(text)))
            return pieces
        end = max(end, start + 1)
        spaces = [index for index in range(start + 1, end + 1) if text[index] == " "]
        floor = start + (end - start) // 2
        best = None
        for rank in (2, 1):
            found = [index for index in spaces if index >= floor and _rank(text, start, index, marks) >= rank]
            if found:
                best = found[-1]
                break
        if best is None:
            best = spaces[-1] if spaces else end
        pieces.append((start, best))
        start = best


def _moment(segments, offset):
    begin, size, when, until = segments[0]
    for segment in segments:
        if segment[0] <= offset:
            begin, size, when, until = segment
    if offset <= begin or until is None or size == 0:
        return when
    span = max(0.0, (until - when).total_seconds())
    return when + timedelta(seconds=span * min(1.0, (offset - begin) / size))


def _transcript(lines):
    lines = list(lines or [])
    following = [line[0] for line in lines[1:]] + [None]
    rows = []
    position = 0
    for side, group in groupby(lines, key=lambda line: line[1]):
        group = list(group)
        budget = LINE_LIMIT - units(f"[00:00:00] {side} | ")
        segments, offset = [], 0
        for index, line in enumerate(group):
            segments.append((offset, len(line[2]), line[0], following[position + index]))
            offset += len(line[2]) + 1
        position += len(group)
        text = " ".join(line[2] for line in group)
        marks = {begin - 1 for begin, _, _, _ in segments[1:]}
        for start, end in cuts(text, budget, marks):
            stamp = _moment(segments, start).astimezone().strftime("%H:%M:%S")
            piece = text[start:end] if end == len(text) else text[start:end].rstrip()
            rows.append(f"[{stamp}] {side} | {piece}")
    return "".join(row + "\n" for row in rows)


def bounded(text, limit=None):
    limit = LINE_LIMIT if limit is None else limit
    rows = []
    for line in text.splitlines():
        if units(line) <= limit:
            rows.append(line)
        else:
            rows.extend(line[start:end].rstrip() for start, end in cuts(line, limit))
    return "".join(row + "\n" for row in rows)


def ocr_image(cfg, path):
    try:
        result = subprocess.run(
            ["nice", "-n", "10", cfg.tesseract, str(path), "stdout", "-l", cfg.ocr_languages],
            capture_output=True,
            text=True,
            timeout=OCR_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _captures(directory, ocr, cfg):
    seen = set()
    blocks = []
    for entry in sorted(directory.iterdir()):
        text = ocr(cfg, entry)
        if text is None:
            blocks.append(f"## {entry.name}\n")
            continue
        fresh = []
        for line in (raw.strip() for raw in text.splitlines()):
            if line and line not in seen:
                seen.add(line)
                fresh.append(line)
        blocks.append(f"## {entry.name}\n" + "".join(f"{line}\n" for line in fresh))
    return "".join(blocks)


def _screen(cfg, meeting, start, end, screenpipe, ocr):
    if meeting.get("backend") == "screenpipe":
        items = screenpipe.search_screen(cfg, start, end) or []
        return "".join(f"{item}\n" for item in items)
    directory = cfg.screens_dir(meeting["id"])
    if not directory.is_dir():
        return ""
    return _captures(directory, ocr, cfg)


def _speakers(cfg, mid, lines, spans, speakers):
    try:
        return speakers(cfg, mid, lines, spans)
    except Exception as error:
        LOG.warning("diarization of %s crashed, keeping plain others: %s", mid, error)
        return lines, {"status": "failed", "reason": f"{type(error).__name__}: {error}"}


def fetch(cfg, mid, asr=asr_module, screenpipe=None, ocr=ocr_image, speakers=diarize_module.relabel):
    with state.locked(cfg.state_path) as st:
        meeting = dict(st["meetings"][mid])
        floor = state.previous_end(st, mid)
    if screenpipe is None and meeting.get("backend") == "screenpipe":
        from . import screenpipe as screenpipe_module

        screenpipe = screenpipe_module
    start = _parse(meeting["start"])
    end = _parse(meeting["end"])
    out = cfg.meeting_dir(mid)
    out.mkdir(parents=True, exist_ok=True)
    skipped = []
    spans = []
    lines = asr.transcribe(cfg, start, end, asr.asr_prompt(cfg), floor=floor, skipped=skipped, spans=spans)
    meta = {**meeting, "owner": cfg.owner, "transcript_source": "local" if lines else "none"}
    if skipped:
        meta["skipped_chunks"] = skipped
    if lines:
        lines, meta["diarization"] = _speakers(cfg, mid, lines, spans, speakers)
    _write(out / "meta.json", json.dumps(meta, indent=2, sort_keys=True))
    _write(out / "transcript.txt", _transcript(lines))
    _write(out / "screen.txt", bounded(_screen(cfg, meeting, start, end, screenpipe, ocr)))
    _write(out / "fetched.ok", "")
    return out
