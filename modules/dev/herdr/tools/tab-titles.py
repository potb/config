import glob
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
SESSIONS = os.path.join(HOME, ".claude", "sessions")
PROJECTS = os.path.join(HOME, ".claude", "projects")
HEAD_LINES = 400
TAIL_BYTES = 256 * 1024
MAX_LEN = 80


def terminal_of(pid):
    try:
        with open("/proc/%d/environ" % pid, "rb") as f:
            for kv in f.read().split(b"\0"):
                if kv.startswith(b"HC_TERMINAL_ID="):
                    return kv.split(b"=", 1)[1].decode() or None
    except Exception:
        pass
    return None


def live_sessions():
    out = {}
    try:
        names = os.listdir(SESSIONS)
    except Exception:
        return out
    for n in names:
        if not n.endswith(".json") or not n[:-5].isdigit():
            continue
        try:
            with open(os.path.join(SESSIONS, n)) as f:
                d = json.load(f)
            pid = int(d.get("pid") or n[:-5])
        except Exception:
            continue
        sid = d.get("sessionId")
        term = terminal_of(pid) if sid else None
        if term:
            out[term] = sid
    return out


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return ""
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def prompt_title(text):
    text = text.strip()
    cmd = re.search(r"<command-name>/?([^<]+)</command-name>", text)
    if cmd:
        args = re.search(r"<command-args>([^<]*)</command-args>", text)
        return " ".join(filter(None, [cmd.group(1).strip(), (args.group(1).strip() if args else "")]))
    if not text or text.startswith("<") or text.startswith("Caveat:"):
        return ""
    return text.splitlines()[0].strip()


def title_of(path):
    custom = ai = None
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - TAIL_BYTES))
            tail = f.read().decode("utf-8", "replace")
    except Exception:
        return None
    for line in tail.splitlines():
        if '"custom-title"' in line or '"ai-title"' in line:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("type") == "custom-title" and r.get("customTitle"):
                custom = r["customTitle"]
            elif r.get("type") == "ai-title" and r.get("aiTitle"):
                ai = r["aiTitle"]
    if custom or ai:
        return custom or ai
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= HEAD_LINES:
                    break
                if '"type":"user"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("isMeta") or r.get("isSidechain"):
                    continue
                t = prompt_title(text_of((r.get("message") or {}).get("content")))
                if t:
                    return t
    except Exception:
        pass
    return None


def main():
    titles = {}
    for term, sid in live_sessions().items():
        found = glob.glob(os.path.join(PROJECTS, "*", sid + ".jsonl"))
        if not found:
            continue
        t = title_of(found[0])
        if t:
            titles[term] = t[:MAX_LEN]
    sys.stdout.write(json.dumps(titles))


main()
