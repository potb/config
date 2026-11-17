import json
from datetime import datetime, timezone
from itertools import groupby

from . import asr as asr_module
from . import state


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


def _screen(cfg, meeting, start, end, screenpipe):
    if meeting.get("backend") == "screenpipe":
        items = screenpipe.search_screen(cfg, start, end) or []
        return "".join(f"{item}\n" for item in items)
    directory = cfg.screens_dir(meeting["id"])
    if not directory.is_dir():
        return ""
    return "".join(f"{entry.name}\n" for entry in sorted(directory.iterdir()))


def fetch(cfg, mid, asr=asr_module, screenpipe=None):
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
    lines = asr.transcribe(cfg, start, end, asr.asr_prompt(cfg), floor=floor, skipped=skipped)
    meta = {**meeting, "owner": cfg.owner, "transcript_source": "local" if lines else "none"}
    if skipped:
        meta["skipped_chunks"] = skipped
    _write(out / "meta.json", json.dumps(meta, indent=2, sort_keys=True))
    _write(out / "transcript.txt", _transcript(lines))
    _write(out / "screen.txt", _screen(cfg, meeting, start, end, screenpipe))
    _write(out / "fetched.ok", "")
    return out
