import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
SKIPPED_SHORT = "skipped_short"
SKIPPED = "skipped"
NOTES_SAVED = "notes_saved"
DONE = "done"
FAILED = "failed"
NOTES_POSTED = "notes_posted"
POSTED = "posted"
DM_ONLY = "dm_only"
TERMINAL = {DONE, SKIPPED, SKIPPED_SHORT, POSTED, DM_ONLY, FAILED}
RESUME_TRANSCRIPT = {NOTES_SAVED, NOTES_POSTED}


def iso(moment):
    if isinstance(moment, str):
        return moment
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso():
    return iso(datetime.now(timezone.utc))


def _default():
    return {"version": VERSION, "meetings": {}, "processed": {}, "last_run": None}


def _migrate(st):
    st.setdefault("meetings", {})
    st.setdefault("processed", {})
    st.setdefault("last_run", None)
    st["version"] = VERSION
    return st


def load(path):
    path = Path(path)
    try:
        raw = path.read_text()
    except FileNotFoundError:
        return _default()
    return _migrate(json.loads(raw))


def save(path, st):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as handle:
        json.dump(st, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


@contextmanager
def locked(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with open(lock_path, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            st = load(path)
            yield st
            save(path, st)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def meeting_id(start_utc):
    if start_utc.tzinfo is not None:
        start_utc = start_utc.astimezone(timezone.utc)
    return start_utc.strftime("%Y%m%d-%H%M%S")


def start_meeting(st, backend, app, title, start, source, **extra):
    base = meeting_id(start)
    mid = base
    n = 1
    while mid in st["meetings"]:
        n += 1
        mid = f"{base}-{n}"
    record = {
        "id": mid,
        "backend": backend,
        "app": app,
        "title": title,
        "start": iso(start),
        "end": None,
        "source": source,
        "live": "off",
    }
    record.update(extra)
    st["meetings"][mid] = record
    return mid


def end_meeting(st, mid, end):
    st["meetings"][mid]["end"] = iso(end)


def previous_end(st, mid):
    start = st["meetings"][mid]["start"]
    ends = [
        m["end"]
        for other, m in st["meetings"].items()
        if other != mid and m.get("end") and m["start"] < start and m["end"] <= start
    ]
    if not ends:
        return None
    return datetime.strptime(max(ends), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def active_meeting(st):
    open_ones = [m for m in st["meetings"].values() if m.get("end") is None]
    if not open_ones:
        return None
    return max(open_ones, key=lambda m: m["start"])


def set_processed(st, mid, **info):
    info.setdefault("at", now_iso())
    st["processed"][mid] = info


def processed(st, mid):
    return st["processed"].get(mid)
