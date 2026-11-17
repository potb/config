from datetime import datetime, timedelta, timezone

from . import state

SETTLE_SECONDS = 120


def _parse(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def list_pending(cfg, now):
    cutoff = now - timedelta(seconds=SETTLE_SECONDS)
    items = []
    with state.locked(cfg.state_path) as st:
        for mid, meeting in st["meetings"].items():
            if not meeting.get("end"):
                continue
            start = _parse(meeting["start"])
            end = _parse(meeting["end"])
            if end > cutoff:
                continue
            info = state.processed(st, mid) or {}
            status = info.get("status")
            if status in state.TERMINAL:
                continue
            minutes = int((end - start).total_seconds() // 60)
            resume = status in state.RESUME_TRANSCRIPT
            if not resume and minutes < cfg.min_minutes:
                state.set_processed(st, mid, status=state.SKIPPED_SHORT)
                continue
            item = {
                "id": mid,
                "title": meeting.get("title"),
                "app": meeting.get("app"),
                "start": meeting["start"],
                "end": meeting["end"],
                "minutes": minutes,
                "backend": meeting.get("backend"),
            }
            if resume:
                item["resume"] = "transcript"
                item["dir"] = info.get("dir")
                item["sensitive"] = bool(info.get("sensitive"))
            items.append(item)
        st["last_run"] = state.iso(now)
    return sorted(items, key=lambda item: (item["start"], item["id"]))
