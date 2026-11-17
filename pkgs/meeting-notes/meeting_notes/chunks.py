import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHUNK_SECONDS = 30
LEAD_SECONDS = 35
GRACE_SECONDS = 10
STABLE_SECONDS = 10
TS_FORMAT = "%Y-%m-%d_%H-%M-%S"
SIDES = {"input": "me", "output": "others"}

CHUNK_RE = re.compile(
    r"^(?P<dev>.+) \((?P<kind>input|output)\)_(?P<ts>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.mp4$"
)


def chunk_name(device, kind, t0_utc):
    stamp = t0_utc.astimezone(timezone.utc).strftime(TS_FORMAT)
    return f"{device} ({kind})_{stamp}.mp4"


def ffmpeg_pattern(device, kind):
    return f"{device} ({kind})_%Y-%m-%d_%H-%M-%S.mp4"


def parse(name):
    match = CHUNK_RE.match(name)
    if not match:
        return None
    t0 = datetime.strptime(match["ts"], TS_FORMAT).replace(tzinfo=timezone.utc)
    return match["dev"], SIDES[match["kind"]], t0


def _scan(directory):
    directory = Path(directory)
    if not directory.is_dir():
        return
    for entry in directory.iterdir():
        parsed = parse(entry.name)
        if parsed:
            yield entry, parsed


def meeting_chunks(directory, start, end, floor=None):
    lower = start - timedelta(seconds=LEAD_SECONDS)
    if floor is not None and floor > lower:
        lower = floor
    found = [
        (t0, entry.name, entry)
        for entry, (_, _, t0) in _scan(directory)
        if lower <= t0 <= end
    ]
    return [entry for _, _, entry in sorted(found)]


def newest_by_side(directory):
    newest = {"me": None, "others": None}
    for entry, (_, side, _) in _scan(directory):
        mtime = entry.stat().st_mtime
        if newest[side] is None or mtime > newest[side]:
            newest[side] = mtime
    return newest


def is_complete(t0, path, now):
    if now < t0 + timedelta(seconds=CHUNK_SECONDS + GRACE_SECONDS):
        return False
    return now.timestamp() - Path(path).stat().st_mtime >= STABLE_SECONDS
