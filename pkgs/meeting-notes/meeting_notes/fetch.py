import json
import logging
import subprocess
from datetime import datetime, timezone
from itertools import groupby

from . import asr as asr_module
from . import diarize as diarize_module
from . import state

LOG = logging.getLogger(__name__)
OCR_TIMEOUT = 120


def _parse(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _write(path, text):
    path.write_text(text, encoding="utf-8")


def _transcript(lines):
    rows = []
    for side, group in groupby(lines or [], key=lambda line: line[1]):
        group = list(group)
        stamp = group[0][0].astimezone().strftime("%H:%M:%S")
        text = " ".join(line[2] for line in group)
        rows.append(f"[{stamp}] {side} | {text}")
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
    _write(out / "screen.txt", _screen(cfg, meeting, start, end, screenpipe, ocr))
    _write(out / "fetched.ok", "")
    return out
