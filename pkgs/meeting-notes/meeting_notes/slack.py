import json
import shutil
import subprocess

API = "https://slack.com/api/"


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


def call(cfg, method, payload, run=_run, which=shutil.which):
    env = load_env(cfg)
    token = env.get("SLACK_BOT_TOKEN")
    if not token:
        raise SlackError("SLACK_BOT_TOKEN missing in .env")
    curl = which("curl")
    if not curl:
        raise SlackError("curl not found in PATH")
    argv = [
        curl,
        "-sS",
        "--config",
        "-",
        "-X",
        "POST",
        "-H",
        "Content-Type: application/json; charset=utf-8",
        "-d",
        json.dumps(payload),
        API + method,
    ]
    result = run(argv, input=f'header = "Authorization: Bearer {token}"\n')
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
    uid = load_env(cfg).get("SLACK_USER_ID")
    if not uid:
        raise SlackError("SLACK_USER_ID missing in .env")
    return uid


def dm(cfg, text, thread_ts=None, **kw):
    payload = {"channel": user_id(cfg), "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    return call(cfg, "chat.postMessage", payload, **kw)
