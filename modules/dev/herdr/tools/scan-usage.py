import json
import os
import select
import shutil
import subprocess
import sys
import time

CACHE = os.path.expanduser("~/.config/herdr-app/data/usage/usage.json")
FRESH_S = 240
WAIT_S = 20
REQUEST = {"type": "control_request", "request_id": "herdr-usage", "request": {"subtype": "get_usage", "skip_behaviors": True}}


def cached():
    try:
        with open(CACHE) as f:
            return json.load(f)
    except Exception:
        return None


def out(obj):
    if "error" in obj:
        old = cached()
        if old and old.get("limits"):
            old["staleError"] = obj["error"]
            sys.stdout.write(json.dumps(old))
            return
    obj["ts"] = int(time.time() * 1000)
    if "error" not in obj:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE + ".tmp", "w") as f:
            json.dump(obj, f)
        os.replace(CACHE + ".tmp", CACHE)
    sys.stdout.write(json.dumps(obj))


def ask_claude():
    claude = shutil.which("claude")
    if not claude:
        return None, "claude CLI not found"
    proc = subprocess.Popen(
        [claude, "-p", "--safe-mode", "--no-session-persistence",
         "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd="/tmp",
    )
    try:
        proc.stdin.write(json.dumps(REQUEST) + "\n")
        proc.stdin.flush()
        end = time.time() + WAIT_S
        while time.time() < end:
            ready, _, _ = select.select([proc.stdout], [], [], 0.5)
            if not ready:
                if proc.poll() is not None:
                    break
                continue
            line = proc.stdout.readline()
            if not line:
                break
            if '"control_response"' in line:
                msg = json.loads(line).get("response") or {}
                if msg.get("subtype") != "success":
                    return None, msg.get("error") or "claude refused"
                return msg.get("response") or {}, None
        return None, "no reply from claude"
    finally:
        proc.kill()
        proc.wait()


def main():
    old = cached()
    if old and old.get("limits") and time.time() * 1000 - old.get("ts", 0) < FRESH_S * 1000:
        sys.stdout.write(json.dumps(old))
        return
    resp, err = ask_claude()
    if err:
        return out({"error": err})
    if not resp.get("rate_limits_available"):
        return out({"error": "no plan limits"})
    data = resp.get("rate_limits") or {}

    limits = []
    five = data.get("five_hour")
    if five and five.get("utilization") is not None:
        limits.append({"label": "Session", "percent": five["utilization"], "resetsAt": five.get("resets_at"), "windowH": 5})
    for lim in data.get("limits") or []:
        if lim.get("group") != "weekly":
            continue
        scope = ((lim.get("scope") or {}).get("model") or {}).get("display_name")
        limits.append({
            "label": scope or "Week",
            "percent": lim.get("percent") or 0,
            "resetsAt": lim.get("resets_at"),
            "windowH": 168,
            "severity": lim.get("severity"),
            "active": bool(lim.get("is_active")),
        })
    out({"limits": limits})


main()
