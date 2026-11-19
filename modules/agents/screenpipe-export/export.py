#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCREENPIPE = "http://127.0.0.1:3030"
HONCHO = "https://api.honcho.dev/v3"
WORKSPACE = os.environ.get("HONCHO_WORKSPACE", "")
KEY_FILE = os.environ.get("HONCHO_API_KEY_FILE", "")
HOURS = int(os.environ.get("EXPORT_HOURS", "2"))
MAX_HOURS = int(os.environ.get("EXPORT_MAX_HOURS", "24"))
MEETINGS = os.environ.get("EXPORT_MEETINGS", "1").strip().lower() not in ("", "0", "false", "no", "off")
MEETING_STATE = os.environ.get("MEETING_NOTES_STATE", "~/.local/share/meeting-notes/state.json")
MEETINGS_RECORD = os.environ.get("EXPORT_MEETINGS_STATE", "~/.local/state/screenpipe-export/meetings.json")
DRY_RUN = os.environ.get("EXPORT_DRY_RUN", "") == "1" or "--dry-run" in sys.argv[1:]
HONCHO_KEY = ""
SP_TOKEN = ""
MIN_TEXT = 60
MIN_AUDIO = 15
BATCH = 90
MEETING_BATCH = 20
MAX_MESSAGE = 4000
OWNER = "peio"
COLLEAGUE = "colleague"
NOTES_PEER = "meeting-notes"
LAYER_NOTES = "meeting-notes"
LAYER_TRANSCRIPT = "meeting-transcript"
TERMINAL = {"done", "skipped", "skipped_short", "posted", "dm_only", "failed"}
SKIPPED = {"skipped", "skipped_short"}
EXPORTABLE = TERMINAL - SKIPPED
TURN = re.compile(r"^\*\*\[([01]?\d|2[0-3]):([0-5]\d)\]\s*(.+?)\s*:\*\*\s*(.*)$")
PARTICIPANTS = re.compile(r"Participants\s*:\s*(.*)$")
UNKNOWN_SPEAKER = re.compile(r"^(participant|speaker|unknown|inconnu)\b", re.I)
SKIP = re.compile(
    r"1password|bitwarden|keepass|keychain|passbolt|vault|bank|banque|bnp|"
    r"societe generale|société générale|qonto|revolut|paypal|impots|impôts|"
    r"urssaf|credit agricole|crédit agricole|stripe dashboard|password|"
    r"mot de passe|secret|2fa|authenticator",
    re.I,
)


def warn(*a):
    print(*a, file=sys.stderr, flush=True)


def screenpipe_token():
    out = subprocess.run([os.environ.get("SCREENPIPE_BIN", "screenpipe"), "auth", "token"], capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        raise SystemExit(f"screenpipe auth token failed: {out.stderr.strip()[:200]}")
    return out.stdout.strip().splitlines()[0].strip()


def sp(path, **params):
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(
        f"{SCREENPIPE}{path}?{q}", headers={"Authorization": f"Bearer {SP_TOKEN}"}
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


def honcho(method, path, body=None, quiet=False):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{HONCHO}/workspaces/{WORKSPACE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {HONCHO_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if not quiet:
            warn(f"honcho {method} {path} -> {e.code}: {e.read()[:200]!r}")
        return None


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cursor_file():
    path = os.environ.get("EXPORT_STATE", "~/.local/state/screenpipe-export/cursor")
    return os.path.expanduser(path)


def read_cursor():
    try:
        with open(cursor_file()) as f:
            return datetime.fromisoformat(f.read().strip().replace("Z", "+00:00"))
    except Exception:
        return None


def write_cursor(dt):
    path = cursor_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(iso(dt))


def msg_key(msg):
    return (msg.get("peer_id"), " ".join((msg.get("content") or "").split()))


def stored(sid):
    keys, ids, page = set(), set(), 1
    while page <= 20:
        d = honcho("POST", f"/sessions/{sid}/messages/list", {"page": page, "size": 50}, quiet=True)
        if not d:
            return keys
        items = d.get("items") or []
        seen = [m for m in items if m.get("id") not in ids]
        if not seen:
            return keys
        for m in seen:
            ids.add(m.get("id"))
            keys.add(msg_key(m))
        page += 1
    return keys


def fresh(sid, msgs):
    seen = stored(sid)
    out = []
    for m in msgs:
        k = msg_key(m)
        if k in seen:
            continue
        seen.add(k)
        out.append(m)
    return out


def search(content_type, start, end):
    rows, offset = [], 0
    while True:
        d = sp(
            "/search",
            content_type=content_type,
            limit=200,
            offset=offset,
            start_time=start,
            end_time=end,
            max_content_length=4000,
            order="ascending",
        )
        got = d.get("data", [])
        rows += got
        total = (d.get("pagination") or {}).get("total")
        offset += len(got)
        if not got or len(got) < 200 or (total is not None and offset >= total):
            return rows


def hour_activity(start, end):
    out = []
    t = start.replace(minute=0, second=0, microsecond=0)
    while t < end:
        e = min(t + timedelta(hours=1), end)
        try:
            d = sp(
                "/activity-summary",
                start_time=iso(t),
                end_time=iso(e),
                include_apps="true",
                include_windows="true",
                max_snippets=0,
            )
        except Exception as exc:
            warn(f"activity-summary {iso(t)}: {exc}")
            t = e
            continue
        apps = d.get("apps") or []
        if apps:
            parts = ", ".join(f"{a.get('name')} {round(a.get('minutes') or 0)}m" for a in apps[:8])
            msg = f"Active apps: {parts}"
            wins = d.get("windows") or []
            if wins:
                msg += ". Windows: " + "; ".join(
                    f"{str(w.get('window_name') or '')[:60]} ({round(w.get('minutes') or 0)}m)"
                    for w in wins[:5]
                )
            out.append((iso(t), msg))
        t = e
    return out


def bucket(ts):
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        t = datetime.now(timezone.utc)
    return "screen-" + t.astimezone(timezone.utc).strftime("%Y-%m-%d-%H")


def export_screen():
    global SP_TOKEN
    SP_TOKEN = screenpipe_token()

    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = read_cursor() or (end - timedelta(hours=HOURS))
    start = start.replace(minute=0, second=0, microsecond=0)
    start = max(start, end - timedelta(hours=MAX_HOURS))
    if start >= end:
        warn(f"nothing to export, cursor is at {iso(start)}")
        return True
    sessions = OrderedDict()

    last = {}
    agg = OrderedDict()
    for row in search("ocr", iso(start), iso(end)):
        c = row.get("content") or {}
        text = (c.get("text") or "").strip()
        app = c.get("app_name") or ""
        win = c.get("window_name") or ""
        url = c.get("browser_url") or ""
        if len(text) < MIN_TEXT:
            continue
        if SKIP.search(app) or SKIP.search(win) or SKIP.search(url):
            continue
        sig = (app, win, text[:120])
        if last.get(sig):
            continue
        last[sig] = True
        try:
            t = datetime.fromisoformat(str(c.get("timestamp")).replace("Z", "+00:00"))
            slot = t.replace(minute=(t.minute // 5) * 5, second=0, microsecond=0)
        except Exception:
            slot = datetime.now(timezone.utc)
        key = (slot, app, win)
        lines = agg.setdefault(key, {"lines": [], "url": url})
        for line in text.splitlines():
            line = " ".join(line.split())
            if len(line) >= 12 and line not in lines["lines"]:
                lines["lines"].append(line)

    for (slot, app, win), a in agg.items():
        body = " | ".join(a["lines"])[:1600]
        if len(body) < MIN_TEXT:
            continue
        header = app or "app"
        if win:
            header += f" — {win}"
        if a["url"]:
            header += f" ({a['url']})"
        sid = bucket(slot)
        sessions.setdefault(sid, []).append(
            {
                "peer_id": "peio",
                "content": f"[{header}] {body}",
                "created_at": iso(slot),
                "metadata": {"layer": "screen-ocr", "app": app, "window": win},
            }
        )

    for row in search("audio", iso(start), iso(end)):
        c = row.get("content") or {}
        text = (c.get("transcription") or c.get("text") or "").strip()
        if len(text) < MIN_AUDIO:
            continue
        dev = c.get("device_name") or ""
        sid = bucket(c.get("timestamp"))
        sessions.setdefault(sid, []).append(
            {
                "peer_id": "peio" if "input" in dev.lower() else "colleague",
                "content": text[:800],
                "created_at": str(c.get("timestamp") or iso(datetime.now(timezone.utc))),
                "metadata": {"layer": "speech", "device": dev},
            }
        )

    for ts, msg in hour_activity(start, end):
        sessions.setdefault(bucket(ts), []).append(
            {
                "peer_id": "peio",
                "content": msg,
                "created_at": ts,
                "metadata": {"layer": "screen-activity"},
            }
        )

    total = 0
    failed = 0
    collected = sum(len(m) for m in sessions.values())
    for sid, msgs in sessions.items():
        msgs.sort(key=lambda m: m["created_at"])
        peers = {m["peer_id"] for m in msgs}
        for peer in sorted(peers):
            honcho("POST", "/peers", {"id": peer})
        pending = fresh(sid, msgs)
        for i in range(0, len(pending), 90):
            batch = pending[i : i + 90]
            if honcho("POST", f"/sessions/{sid}/messages", {"messages": batch}) is None:
                failed += 1
            else:
                total += len(batch)
    if failed:
        warn(f"exported {total} of {collected} collected messages, {failed} batches failed, cursor stays at {iso(start)}")
        return False
    write_cursor(end)
    warn(f"exported {total} new messages of {collected} collected across {len(sessions)} sessions ({iso(start)} → {iso(end)})")
    return True


def slug(text):
    plain = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def parse_time(text):
    try:
        return datetime.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_participants(line):
    found = PARTICIPANTS.search(line)
    if not found:
        return []
    text = re.sub(r"\([^)]*\)", "", found.group(1).strip().rstrip("_"))
    return [name.strip() for name in text.split(",") if name.strip()]


def parse_transcript(text):
    names, turns = [], []
    for raw in text.splitlines():
        line = raw.strip()
        turn = TURN.match(line)
        if turn:
            turns.append(
                {
                    "hour": int(turn.group(1)),
                    "minute": int(turn.group(2)),
                    "label": turn.group(3),
                    "text": turn.group(4).strip(),
                }
            )
        elif not line or line.startswith("#"):
            continue
        elif line.startswith("_"):
            if not turns:
                names = names or parse_participants(line)
        elif turns:
            turns[-1]["text"] = f"{turns[-1]['text']}\n{line}".strip()
    return names, [t for t in turns if t["text"]]


def speaker_peer(label, names):
    label = label.strip()
    if "?" in label or UNKNOWN_SPEAKER.match(label):
        return COLLEAGUE
    name = slug(label)
    if not name:
        return COLLEAGUE
    if name == OWNER:
        return OWNER
    full = {slug(n) for n in names if slug(n) == name or slug(n).startswith(name + "-")}
    if len(full) == 1:
        return full.pop()
    return name


def hard_split(text, limit):
    out = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit + 1)
        if cut < limit // 2:
            cut = max(cut, text.rfind(" ", 0, limit + 1))
        if cut <= 0:
            cut = limit
        out.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        out.append(text)
    return out


def pack(units, limit):
    out, current = [], ""
    for unit in units:
        if current and len(current) + 2 + len(unit) > limit:
            out.append(current)
            current = unit
        else:
            current = f"{current}\n\n{unit}" if current else unit
    if current:
        out.append(current)
    return out


def split_text(text, limit):
    units = []
    for para in re.split(r"\n\s*\n", text.strip()):
        para = para.strip()
        if para:
            units += hard_split(para, limit)
    return pack(units, limit)


def notes_parts(text, limit):
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    units = []
    for section in re.split(r"(?m)^(?=## )", text):
        section = section.strip()
        if len(section) > limit:
            units += split_text(section, limit)
        elif section:
            units.append(section)
    return pack(units, limit)


def timed_groups(turns, start, tz):
    local = start.astimezone(tz)
    day = local.date()
    offset = 0
    previous = local.hour * 60 + local.minute
    groups = []
    for turn in turns:
        minutes = turn["hour"] * 60 + turn["minute"]
        if minutes < previous - 720:
            offset += 1
        previous = minutes
        last = groups[-1] if groups else None
        if last and last["label"] == turn["label"] and last["minutes"] == minutes and last["offset"] == offset:
            last["texts"].append(turn["text"])
            continue
        moment = datetime(day.year, day.month, day.day, turn["hour"], turn["minute"], tzinfo=tz) + timedelta(days=offset)
        groups.append(
            {"label": turn["label"], "minutes": minutes, "offset": offset, "moment": moment, "texts": [turn["text"]]}
        )
    return groups


def meeting_meta(meeting):
    return {
        "meeting_id": meeting["id"],
        "title": meeting.get("title") or "",
        "app": meeting.get("app") or "",
        "start": meeting.get("start") or "",
        "end": meeting.get("end") or "",
    }


def build_messages(meeting, notes, transcript, tz=None):
    base = meeting_meta(meeting)
    start = parse_time(meeting["start"])
    end = parse_time(meeting.get("end")) or start
    tz = tz or start.astimezone().tzinfo
    names, turns = parse_transcript(transcript)
    out = []
    groups = timed_groups(turns, start, tz)
    for group in groups:
        label = group["label"][:80]
        clock = f"{group['minutes'] // 60:02d}:{group['minutes'] % 60:02d}"
        prefix = f"[{clock}] {label}: "
        parts = split_text("\n\n".join(group["texts"]), MAX_MESSAGE - len(prefix))
        for i, part in enumerate(parts):
            meta = {"layer": LAYER_TRANSCRIPT, **base, "speaker": label, "time": clock}
            if len(parts) > 1:
                meta["part"] = f"{i + 1}/{len(parts)}"
            out.append(
                {
                    "peer_id": speaker_peer(label, names),
                    "content": prefix + part,
                    "created_at": iso(group["moment"]),
                    "metadata": meta,
                }
            )
    notes_at = max([end] + [g["moment"].astimezone(timezone.utc) for g in groups])
    parts = notes_parts(notes, MAX_MESSAGE)
    for i, part in enumerate(parts):
        meta = {"layer": LAYER_NOTES, **base}
        if len(parts) > 1:
            meta["part"] = f"{i + 1}/{len(parts)}"
        out.append({"peer_id": NOTES_PEER, "content": part, "created_at": iso(notes_at), "metadata": meta})
    out.sort(key=lambda m: m["created_at"])
    return out


def flagged(value):
    return value not in (None, False)


def eligible(st, base):
    processed = st.get("processed") or {}
    out = []
    for mid, meeting in (st.get("meetings") or {}).items():
        info = processed.get(mid) or {}
        if not isinstance(meeting, dict) or not isinstance(info, dict):
            continue
        if info.get("status") not in EXPORTABLE:
            continue
        if flagged(info.get("sensitive")) or flagged(meeting.get("sensitive")):
            continue
        if flagged(info.get("skip_reason")) or flagged(meeting.get("skip_reason")):
            continue
        if not info.get("dir") or not meeting.get("end") or not parse_time(meeting.get("start")):
            continue
        folder = Path(str(info["dir"])).expanduser()
        if not folder.is_absolute():
            folder = base / folder
        notes, transcript = folder / "notes.md", folder / "transcript.md"
        if not notes.is_file() and not transcript.is_file():
            continue
        out.append(
            {
                "id": str(meeting.get("id") or mid),
                "title": meeting.get("title"),
                "app": meeting.get("app"),
                "start": meeting["start"],
                "end": meeting["end"],
                "notes": notes if notes.is_file() else None,
                "transcript": transcript if transcript.is_file() else None,
            }
        )
    return sorted(out, key=lambda m: (m["start"], m["id"]))


def read_text(path):
    if path is None:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def load_json(path):
    try:
        with open(os.path.expanduser(str(path))) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        warn(f"cannot read {path}: {exc}")
        return None


def load_record(path):
    record = load_json(path)
    if not isinstance(record, dict):
        record = {}
    record.setdefault("version", 1)
    if not isinstance(record.get("exported"), dict):
        record["exported"] = {}
    if not isinstance(record.get("partial"), dict):
        record["partial"] = {}
    return record


def save_record(path, record):
    path = os.path.expanduser(str(path))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(record, f, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def meeting_session(meeting):
    return f"meeting-{meeting['id']}"


def meeting_messages(meeting):
    return build_messages(meeting, read_text(meeting["notes"]), read_text(meeting["transcript"]))


def send_meeting(meeting, msgs, record, record_path):
    sid = meeting_session(meeting)
    for peer in sorted({m["peer_id"] for m in msgs}):
        honcho("POST", "/peers", {"id": peer})
    partial = record["partial"].get(meeting["id"]) or {}
    sent = partial.get("sent", 0) if partial.get("total") == len(msgs) else 0
    positions = {id(m): i for i, m in enumerate(msgs)}
    pending = fresh(sid, msgs[sent:])
    total = 0
    for i in range(0, len(pending), MEETING_BATCH):
        batch = pending[i : i + MEETING_BATCH]
        try:
            reply = honcho("POST", f"/sessions/{sid}/messages", {"messages": batch})
        except OSError as exc:
            warn(f"meeting {meeting['id']}: {exc}")
            reply = None
        if reply is None:
            return total, False
        total += len(batch)
        record["partial"][meeting["id"]] = {"sent": positions[id(batch[-1])] + 1, "total": len(msgs)}
        save_record(record_path, record)
    record["partial"].pop(meeting["id"], None)
    record["exported"][meeting["id"]] = {"at": iso(datetime.now(timezone.utc)), "session": sid, "messages": len(msgs)}
    save_record(record_path, record)
    return total, True


def describe_meeting(meeting, msgs):
    print(f"{meeting_session(meeting)} {meeting.get('title') or ''!r} {meeting['start']}: {len(msgs)} messages, {sum(len(m['content']) for m in msgs)} chars")
    groups = OrderedDict()
    for m in msgs:
        key = (m["peer_id"], m["metadata"]["layer"])
        count, size = groups.get(key, (0, 0))
        groups[key] = (count + 1, size + len(m["content"]))
    for (peer, layer), (count, size) in sorted(groups.items()):
        print(f"  {peer} {layer}: {count} messages, {size} chars")


def export_meetings(dry=False):
    state_path = Path(os.path.expanduser(MEETING_STATE))
    st = load_json(state_path)
    if not isinstance(st, dict):
        return True
    record = load_record(MEETINGS_RECORD)
    todo = [m for m in eligible(st, state_path.parent) if m["id"] not in record["exported"]]
    if dry:
        total = 0
        for meeting in todo:
            msgs = meeting_messages(meeting)
            total += len(msgs)
            describe_meeting(meeting, msgs)
        print(f"dry run: {len(todo)} meetings, {total} messages, {len(record['exported'])} already exported, no network call, no state written")
        return True
    sent, failed = 0, 0
    for meeting in todo:
        try:
            msgs = meeting_messages(meeting)
            if not msgs:
                continue
            count, ok = send_meeting(meeting, msgs, record, MEETINGS_RECORD)
        except Exception as exc:
            warn(f"meeting {meeting['id']}: {exc}")
            count, ok = 0, False
        sent += count
        if not ok:
            failed += 1
            warn(f"meeting {meeting['id']}: batch failed, will retry next run")
    if todo:
        warn(f"exported {sent} new meeting messages across {len(todo)} meetings, {failed} failed")
    return not failed


def main():
    if DRY_RUN:
        if MEETINGS:
            export_meetings(dry=True)
        return
    if not WORKSPACE or not KEY_FILE:
        raise SystemExit("HONCHO_WORKSPACE and HONCHO_API_KEY_FILE are required")
    global HONCHO_KEY
    HONCHO_KEY = open(os.path.expanduser(KEY_FILE)).read().strip()
    ok = True
    try:
        ok = export_screen()
    except (Exception, SystemExit) as exc:
        warn(f"screen export failed: {exc}")
        ok = False
    if MEETINGS:
        try:
            ok = export_meetings() and ok
        except Exception as exc:
            warn(f"meeting export failed: {exc}")
            ok = False
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
