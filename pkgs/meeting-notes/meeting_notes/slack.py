import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

API = "https://slack.com/api/"
UPLOAD_PREFIX = "https://"
MIDDLE_DOT = "·"
EN_DASH = "–"


class SlackError(RuntimeError):
    pass


def load_env(cfg):
    path = cfg.data_dir / ".env"
    env = {}
    if not path.is_file():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip("'\"")
    return env


def _run(argv, input=None):
    return subprocess.run(argv, input=input, capture_output=True, text=True, check=False)


def _curl(which):
    curl = (which or shutil.which)("curl")
    if not curl:
        raise SlackError("curl not found in PATH")
    return curl


def _token_from_file(cfg):
    if not cfg.slack_token_file:
        return None
    try:
        return cfg.slack_token_file.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _token(cfg):
    token = _token_from_file(cfg) or load_env(cfg).get("SLACK_BOT_TOKEN")
    if not token:
        raise SlackError("SLACK_BOT_TOKEN missing in .env and no readable token file")
    if any(ch in token for ch in '"\\\r\n'):
        raise SlackError("Slack bot token is malformed")
    return token


def call(cfg, method, payload, run=None, which=None, form=False):
    token = _token(cfg)
    curl = _curl(which)
    if form:
        content_type = "application/x-www-form-urlencoded"
        body = urlencode(payload)
    else:
        content_type = "application/json; charset=utf-8"
        body = json.dumps(payload)
    argv = [
        curl,
        "-sS",
        "--config",
        "-",
        "-X",
        "POST",
        "-H",
        f"Content-Type: {content_type}",
        "-d",
        body,
        API + method,
    ]
    result = (run or _run)(argv, input=f'header = "Authorization: Bearer {token}"\n')
    if result.returncode != 0:
        raise SlackError(f"curl exited {result.returncode}")
    try:
        reply = json.loads(result.stdout)
    except ValueError:
        raise SlackError("invalid response from Slack") from None
    if not reply.get("ok"):
        raise SlackError(f"{method} failed: {reply.get('error', 'unknown')}")
    return reply


def user_id(cfg):
    uid = cfg.slack_user or load_env(cfg).get("SLACK_USER_ID")
    if not uid:
        raise SlackError("Slack user id missing: set MEETING_NOTES_SLACK_USER")
    return uid


def channel_id(cfg):
    if not cfg.slack_channel:
        raise SlackError("Slack channel id missing: set MEETING_NOTES_SLACK_CHANNEL")
    return cfg.slack_channel


def allowed(cfg, sensitive):
    if not cfg.slack:
        return False
    return not sensitive or cfg.slack_post_to == "channel"


def destination(cfg, sensitive=False):
    if cfg.slack_post_to == "channel" and not sensitive:
        return channel_id(cfg)
    return user_id(cfg)


def _parse(moment):
    return datetime.strptime(moment, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def minutes(meeting):
    start = (meeting or {}).get("start")
    end = (meeting or {}).get("end")
    if not start or not end:
        return None
    try:
        seconds = (_parse(end) - _parse(start)).total_seconds()
    except ValueError:
        return None
    if seconds <= 0:
        return None
    return max(1, round(seconds / 60))


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def is_dm(cfg, channel):
    return channel.startswith("D") and channel != cfg.slack_channel


def header(title, meeting=None):
    text = f"*{escape(title)}*"
    length = minutes(meeting)
    if length:
        text += f" {MIDDLE_DOT} {length} min"
    return text


def file_title(title, kind):
    return f"{title} {EN_DASH} {kind}"


def post_header(cfg, title, meeting=None, sensitive=False, **kw):
    payload = {"channel": destination(cfg, sensitive), "text": header(title, meeting)}
    reply = call(cfg, "chat.postMessage", payload, **kw)
    ts, channel = reply.get("ts"), reply.get("channel")
    if not ts or not channel:
        raise SlackError("chat.postMessage reply has no ts or channel")
    return ts, channel


def _send_bytes(upload_url, path, run=None, which=None):
    if not upload_url.startswith(UPLOAD_PREFIX):
        raise SlackError("upload url from Slack is not https")
    argv = [
        _curl(which),
        "-sS",
        "--fail",
        "-X",
        "POST",
        "-H",
        "Content-Type: application/octet-stream",
        "--data-binary",
        f"@{path}",
        upload_url,
    ]
    result = (run or _run)(argv)
    if result.returncode != 0:
        raise SlackError(f"file upload failed: curl exited {result.returncode}")


def upload(cfg, channel, thread_ts, path, title, run=None, which=None):
    path = Path(path)
    slot = call(
        cfg,
        "files.getUploadURLExternal",
        {"filename": path.name, "length": path.stat().st_size},
        run=run,
        which=which,
        form=True,
    )
    if not slot.get("upload_url") or not slot.get("file_id"):
        raise SlackError("files.getUploadURLExternal reply has no upload_url or file_id")
    _send_bytes(slot["upload_url"], path, run=run, which=which)
    payload = {"files": [{"id": slot["file_id"], "title": title}], "channel_id": channel}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    return call(cfg, "files.completeUploadExternal", payload, run=run, which=which)


def post_dm(cfg, text, run=None, which=None):
    payload = {"channel": user_id(cfg), "text": escape(text)}
    return call(cfg, "chat.postMessage", payload, run=run, which=which)


def check(cfg, run=None, which=None):
    kw = {"run": run, "which": which}
    lines = []
    auth = call(cfg, "auth.test", {}, **kw)
    lines.append(f"team: {auth.get('team', '?')} ({auth.get('team_id', '?')})")
    lines.append(f"bot: {auth.get('user', '?')} ({auth.get('user_id', '?')})")
    lines.append(f"post to: {cfg.slack_post_to}")
    if cfg.slack_post_to == "channel":
        joined = call(cfg, "conversations.join", {"channel": channel_id(cfg)}, **kw)
        room = joined.get("channel") or {}
        lines.append(f"channel: {room.get('name', '?')} ({room.get('id', channel_id(cfg))})")
    opened = call(cfg, "conversations.open", {"users": user_id(cfg)}, **kw)
    lines.append(f"dm: {(opened.get('channel') or {}).get('id', '?')} with {user_id(cfg)}")
    return lines
