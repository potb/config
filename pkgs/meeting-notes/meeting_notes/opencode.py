import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

AGENT = "meeting-notes"
TITLE_PREFIX = "meeting-notes"
API_TIMEOUT = 120
PREVIEW = 300
NOT_FOUND = ("SessionNotFoundError", "Session not found")
TOKEN_BYTES = 3


def ident():
    return f"{os.getpid()}-{secrets.token_hex(TOKEN_BYTES)}"


def run_name(stamp, run_ident):
    return f"{stamp}-{run_ident}"


def title(name):
    return f"{TITLE_PREFIX} {name}"


def run_argv(cfg, session_title, prompt):
    model = ["--model", cfg.notes_model] if cfg.notes_model else []
    return [
        cfg.opencode,
        "run",
        "--standalone",
        "--agent",
        AGENT,
        *model,
        "--archived",
        "--format",
        "json",
        "--title",
        session_title,
        prompt,
    ]


def delete_argv(cfg, session_id):
    return [cfg.opencode, "session", "delete", "--standalone", session_id]


def api_get_argv(cfg, path):
    return [cfg.opencode, "api", "get", "--standalone", path]


def search_path(session_title):
    return f"/api/session?search={quote(session_title)}&limit=50"


def children_path(session_id):
    return f"/api/session?parentID={quote(session_id)}&limit=50"


def read_output(path):
    events, other = [], []
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return events, other
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except ValueError:
            other.append(line)
            continue
        if isinstance(event, dict):
            events.append(event)
        else:
            other.append(line)
    return events, other


def session_ids(events):
    found = []
    for event in events:
        candidates = [event.get("sessionID")]
        part = event.get("part")
        if isinstance(part, dict):
            candidates.append(part.get("sessionID"))
        for sid in candidates:
            if isinstance(sid, str) and sid and sid not in found:
                found.append(sid)
    return found


def _items(payload):
    try:
        data = json.loads(payload)
    except ValueError:
        return []
    items = data.get("data") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]]


def titled_sessions(payload, session_title):
    return [item["id"] for item in _items(payload) if item.get("title") == session_title]


def child_sessions(payload, parent):
    return [item["id"] for item in _items(payload) if item.get("parentID") == parent]


def _clock(event):
    stamp = event.get("timestamp")
    if not isinstance(stamp, (int, float)):
        return "--:--:--"
    return datetime.fromtimestamp(stamp / 1000, timezone.utc).strftime("%H:%M:%S")


def _preview(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= PREVIEW else text[:PREVIEW] + "..."


def _tool_line(part):
    state = part.get("state") if isinstance(part.get("state"), dict) else {}
    status = state.get("status", "?")
    head = f"tool {part.get('tool', '?')} {_preview(state.get('input', {}))} -> {status}"
    if status == "error":
        return f"{head}: {_preview(state.get('error', ''))}"
    if "output" in state:
        return f"{head}: {_preview(state['output'])}"
    return head


def totals(events):
    total = {"steps": 0, "cost": 0.0, "input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0}
    for event in events:
        part = event.get("part")
        if event.get("type") != "step_finish" or not isinstance(part, dict):
            continue
        total["steps"] += 1
        cost = part.get("cost")
        if isinstance(cost, (int, float)):
            total["cost"] += cost
        tokens = part.get("tokens") if isinstance(part.get("tokens"), dict) else {}
        cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
        for key, value in (
            ("input", tokens.get("input")),
            ("output", tokens.get("output")),
            ("reasoning", tokens.get("reasoning")),
            ("cache_read", cache.get("read")),
            ("cache_write", cache.get("write")),
        ):
            if isinstance(value, int):
                total[key] += value
    return total


def summary(total):
    return (
        f"steps {total['steps']}, cost {total['cost']:.4f} USD, tokens input {total['input']} "
        f"output {total['output']} reasoning {total['reasoning']} "
        f"cache read {total['cache_read']} cache write {total['cache_write']}"
    )


def render(events, other, header=()):
    lines = list(header)
    for event in events:
        kind = event.get("type")
        part = event.get("part") if isinstance(event.get("part"), dict) else {}
        if kind in ("step_start", "step_finish"):
            continue
        if kind == "text":
            text = part.get("text", "")
            lines.append(f"{_clock(event)} text:")
            lines.extend(f"  {line}" for line in str(text).splitlines() or [""])
        elif kind == "tool_use":
            lines.append(f"{_clock(event)} {_tool_line(part)}")
        else:
            body = {key: value for key, value in event.items() if key not in ("timestamp", "sessionID")}
            lines.append(f"{_clock(event)} {kind or 'event'}: {_preview(body)}")
    if other:
        lines.append("output:")
        lines.extend(f"  {line}" for line in other)
    lines.append(summary(totals(events)))
    return "\n".join(lines) + "\n"


def capture(run, argv, cwd, scratch):
    scratch = Path(scratch)
    scratch.unlink(missing_ok=True)
    try:
        result = run(argv, cwd=cwd, timeout=API_TIMEOUT, log=scratch)
        try:
            text = scratch.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
    finally:
        scratch.unlink(missing_ok=True)
    return result.returncode, text


def find_sessions(run, cfg, session_title, cwd, scratch):
    code, text = capture(run, api_get_argv(cfg, search_path(session_title)), cwd, scratch)
    if code:
        return []
    return titled_sessions(text, session_title)


def find_children(run, cfg, parent, cwd, scratch):
    code, text = capture(run, api_get_argv(cfg, children_path(parent)), cwd, scratch)
    if code:
        return []
    return child_sessions(text, parent)


def owned_sessions(run, cfg, ids, session_title, cwd, scratch):
    roots = list(ids) or find_sessions(run, cfg, session_title, cwd, scratch)
    owned = []
    queue = list(roots)
    while queue:
        sid = queue.pop(0)
        if sid in owned:
            continue
        owned.append(sid)
        queue.extend(find_children(run, cfg, sid, cwd, scratch))
    return owned


def gone(run, cfg, session_id, cwd, scratch):
    code, text = capture(run, api_get_argv(cfg, f"/api/session/{session_id}"), cwd, scratch)
    return bool(code) and any(marker in text for marker in NOT_FOUND)


def delete_sessions(run, cfg, ids, cwd, scratch):
    failed = []
    for sid in ids:
        code, _ = capture(run, delete_argv(cfg, sid), cwd, scratch)
        if code and not gone(run, cfg, sid, cwd, scratch):
            failed.append(sid)
    return failed
