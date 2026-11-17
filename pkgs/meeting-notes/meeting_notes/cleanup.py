import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import asr, chunks, state


def _parse(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _inside(path, parent):
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
    except ValueError:
        return False
    return True


def _expired(cfg, st, now):
    cutoff = now - timedelta(days=cfg.retention_days)
    for mid, meeting in st["meetings"].items():
        info = state.processed(st, mid) or {}
        if info.get("status") not in state.TERMINAL or not meeting.get("end"):
            continue
        if _parse(meeting["end"]) <= cutoff:
            yield mid, meeting, state.previous_end(st, mid)


def run(cfg, now, run_cmd=None):
    removed = {"audio": 0, "screens": 0, "wav": 0, "cache": 0}
    with state.locked(cfg.state_path) as st:
        expired = list(_expired(cfg, st, now))
    for mid, meeting, floor in expired:
        if meeting.get("backend") == "native" and not _inside(cfg.audio_dir, cfg.meetings_dir):
            for path in chunks.meeting_chunks(
                cfg.audio_dir, _parse(meeting["start"]), _parse(meeting["end"]), floor=floor
            ):
                path.unlink(missing_ok=True)
                removed["audio"] += 1
        screens = cfg.screens_dir(mid)
        if screens.is_dir():
            shutil.rmtree(screens)
            removed["screens"] += 1
        for wav in cfg.meeting_dir(mid).glob("*.wav"):
            wav.unlink()
            removed["wav"] += 1
    removed["cache"] = asr.prune_cache(cfg, cfg.retention_days, now)
    return removed
