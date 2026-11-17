import logging
import sys

LOG = logging.getLogger(__name__)


def _applescript(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _argv(title, body, platform):
    if platform == "darwin":
        script = (
            f'display notification "{_applescript(body)}" '
            f'with title "{_applescript(title)}"'
        )
        return ["osascript", "-e", script]
    return ["notify-send", "-a", "meeting-notes", title, body]


def send(title, body, run, platform=sys.platform):
    argv = _argv(title, body, platform)
    try:
        result = run(argv)
    except Exception as error:
        LOG.warning("notification failed: %s", error)
        return False
    code = getattr(result, "returncode", 0)
    if code:
        LOG.warning("notification exited %s: %s", code, getattr(result, "stderr", ""))
        return False
    return True
