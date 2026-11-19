import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

ROLE_FRAME = 23
ROLE_COMBO_BOX = 11
ROLE_ENTRY = 79
ROLE_PUSH_BUTTON = 43
ROLE_DOCUMENT_FRAME = 82
ROLE_DOCUMENT_WEB = 95
ADDRESS_ROLES = {ROLE_ENTRY, ROLE_COMBO_BOX}
OPAQUE_ROLES = {ROLE_PUSH_BUTTON, ROLE_DOCUMENT_FRAME, ROLE_DOCUMENT_WEB}

STATE_ACTIVE = 1
STATE_FOCUSED = 12

ALLOWED_SCHEMES = ("http://", "https://", "chrome://")
PRIVATE_MARKERS = ("incognito", "navigation privée", "navigation privee", "inprivate")
BROWSER_TITLE_SUFFIXES = (" - Google Chrome", " - Chromium")
BROWSER_APP_NAMES = ("chrome", "chromium")

REGISTRY = "org.a11y.atspi.Registry"
ROOT_PATH = "/org/a11y/atspi/accessible/root"
ACCESSIBLE = "org.a11y.atspi.Accessible"
TEXT = "org.a11y.atspi.Text"

MAX_DEPTH = 14
MAX_NODES = 400
SEARCH_BUDGET_SECONDS = 4.0
CALL_TIMEOUT_SECONDS = 2.0
BACKOFF_CAP_SECONDS = 60.0
LOG_EVERY_SECONDS = 60.0


class AtspiError(Exception):
    pass


class TransportError(AtspiError):
    pass


NULL_PATHS = {"", "/", "/org/a11y/atspi/null", "/org/a11y/atspi/accessible/null"}


def is_null_ref(dest, path):
    return not dest or not path or path in NULL_PATHS or path.endswith("/null")


def parse_call(stdout):
    payload = json.loads(stdout)
    return payload.get("data", [])


def parse_properties(stdout):
    return [json.loads(line)["data"] for line in stdout.splitlines() if line.strip()]


def parse_refs(data):
    if not data:
        return []
    return [(ref[0], ref[1]) for ref in data[0] if not is_null_ref(ref[0], ref[1])]


def has_state(words, bit):
    index, offset = divmod(bit, 32)
    if index >= len(words):
        return False
    return bool(words[index] & (1 << offset))


def is_browser_class(window_class):
    lowered = (window_class or "").lower()
    return "chrome" in lowered or "chromium" in lowered


def is_private(*titles):
    for title in titles:
        lowered = (title or "").casefold()
        if any(marker in lowered for marker in PRIVATE_MARKERS):
            return True
    return False


def is_address_name(name):
    lowered = (name or "").lower()
    return "address" in lowered


def page_title(window_title):
    title = window_title or ""
    for suffix in BROWSER_TITLE_SUFFIXES:
        position = title.rfind(suffix)
        if position != -1:
            return title[:position]
    return title


def clean_url(value):
    text = (value or "").strip()
    if not text.lower().startswith(ALLOWED_SCHEMES):
        return None
    if any(character.isspace() for character in text):
        return None
    parts = urlsplit(text)
    netloc = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme.lower(), netloc.lower(), parts.path, "", ""))


def host_of(url):
    return urlsplit(url).hostname or ""


def pick_window(windows, window_title):
    frames = [window for window in windows if window["role"] == ROLE_FRAME]
    if len(frames) == 1:
        return frames[0]
    base = page_title(window_title)
    if base:
        named = [window for window in frames if window["name"].startswith(base)]
        if len(named) == 1:
            return named[0]
    active = [window for window in frames if has_state(window.get("states", []), STATE_ACTIVE)]
    if len(active) == 1:
        return active[0]
    return None


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_entry(url, title, ts):
    return {"ts": ts, "url": url, "host": host_of(url), "title": page_title(title)}


def read_entries(path):
    entries = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return entries


def last_url(path):
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 8192))
            tail = handle.read().decode("utf-8", "replace")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        try:
            return json.loads(line)["url"]
        except (ValueError, KeyError, TypeError):
            continue
    return None


class Recorder:
    def __init__(self, path, max_bytes):
        self.path = path
        self.max_bytes = max_bytes
        self.previous = last_url(path)

    def record(self, url, title, ts=None):
        if url == self.previous:
            return False
        entry = make_entry(url, title, ts or utc_now())
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.rotate()
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.previous = url
        return True

    def rotate(self):
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return
        if size >= self.max_bytes:
            os.replace(self.path, self.path + ".1")


class ThrottledLog:
    def __init__(self, every=LOG_EVERY_SECONDS, clock=time.monotonic, stream=sys.stderr):
        self.every = every
        self.clock = clock
        self.stream = stream
        self.last = None
        self.suppressed = 0

    def error(self, message):
        now = self.clock()
        if self.last is not None and now - self.last < self.every:
            self.suppressed += 1
            return False
        suffix = f" ({self.suppressed} similar suppressed)" if self.suppressed else ""
        print(f"screenpipe-url: {message}{suffix}", file=self.stream, flush=True)
        self.last = now
        self.suppressed = 0
        return True


class Backoff:
    def __init__(self, base, cap=BACKOFF_CAP_SECONDS):
        self.base = base
        self.cap = cap
        self.failures = 0

    def success(self):
        self.failures = 0

    def failure(self):
        self.failures += 1

    def delay(self):
        if self.failures == 0:
            return self.base
        return min(self.cap, self.base * (2 ** min(self.failures, 10)))


def run_command(argv, timeout=CALL_TIMEOUT_SECONDS):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise TransportError(f"{argv[0]}: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip()[:200]
        message = f"{argv[0]} exited {result.returncode}: {detail}"
        if "connect" in detail.lower() or "timed out" in detail.lower():
            raise TransportError(message)
        raise AtspiError(message)
    return result.stdout


def active_window(runner=run_command):
    try:
        return json.loads(runner(["hyprctl", "-j", "activewindow"]))
    except ValueError as error:
        raise AtspiError(f"hyprctl: {error}") from error


class Atspi:
    def __init__(self, runner=run_command):
        self.runner = runner
        self.address = None

    def connect(self):
        stdout = self.runner(
            ["busctl", "--user", "--json=short", "call", "org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus", "GetAddress"]
        )
        self.address = parse_call(stdout)[0]

    def busctl(self, *args):
        if self.address is None:
            self.connect()
        timeout = f"--timeout={CALL_TIMEOUT_SECONDS / 2:g}"
        try:
            return self.runner(["busctl", f"--address={self.address}", "--json=short", timeout, *args])
        except TransportError:
            self.address = None
            raise

    def call(self, dest, path, interface, method, *arguments):
        if is_null_ref(dest, path):
            raise AtspiError(f"null accessible {dest} {path}")
        stdout = self.busctl("call", dest, path, interface, method, *arguments)
        try:
            return parse_call(stdout)
        except (ValueError, AttributeError) as error:
            raise AtspiError(f"unreadable busctl output for {method} on {path}") from error

    def first(self, dest, path, interface, method, *arguments):
        data = self.call(dest, path, interface, method, *arguments)
        if not isinstance(data, list) or not data:
            raise AtspiError(f"empty reply to {method} on {path}")
        return data[0]

    def children(self, dest, path):
        try:
            return parse_refs(self.call(dest, path, ACCESSIBLE, "GetChildren"))
        except (TypeError, IndexError) as error:
            raise AtspiError(f"unreadable children of {path}") from error

    def role(self, dest, path):
        return self.first(dest, path, ACCESSIBLE, "GetRole")

    def states(self, dest, path):
        return self.first(dest, path, ACCESSIBLE, "GetState")

    def name_and_count(self, dest, path):
        if is_null_ref(dest, path):
            raise AtspiError(f"null accessible {dest} {path}")
        stdout = self.busctl("get-property", dest, path, ACCESSIBLE, "Name", "ChildCount")
        try:
            name, count = parse_properties(stdout)
        except (ValueError, KeyError, TypeError) as error:
            raise AtspiError(f"unreadable properties of {path}") from error
        return name, count

    def text(self, dest, path):
        return self.first(dest, path, TEXT, "GetText", "ii", "--", "0", "-1")


class Finder:
    def __init__(self, atspi, clock=time.monotonic):
        self.atspi = atspi
        self.clock = clock
        self.app = None
        self.entries = {}
        self.visited = 0
        self.broken = 0

    def browser_apps(self):
        apps = []
        for dest, path in self.atspi.children(REGISTRY, ROOT_PATH):
            try:
                name, _ = self.atspi.name_and_count(dest, path)
            except AtspiError:
                continue
            if any(word in name.lower() for word in BROWSER_APP_NAMES):
                apps.append((dest, path))
        return apps

    def windows(self, app):
        found = []
        for dest, path in self.atspi.children(*app):
            try:
                name, _ = self.atspi.name_and_count(dest, path)
                role = self.atspi.role(dest, path)
            except AtspiError:
                continue
            found.append({"dest": dest, "path": path, "name": name, "role": role})
        return found

    def window_for(self, window_title):
        if self.app:
            choice = self.window_in(self.app, window_title)
            if choice:
                return choice
            self.app = None
        for app in self.browser_apps():
            choice = self.window_in(app, window_title)
            if choice:
                self.app = app
                return choice
        return None

    def window_in(self, app, window_title):
        try:
            return self.choose(self.windows(app), window_title)
        except AtspiError:
            return None

    def choose(self, windows, window_title):
        choice = pick_window(windows, window_title)
        if choice or len([window for window in windows if window["role"] == ROLE_FRAME]) < 2:
            return choice
        for window in windows:
            if window["role"] == ROLE_FRAME:
                try:
                    window["states"] = self.atspi.states(window["dest"], window["path"])
                except AtspiError:
                    window["states"] = []
        return pick_window(windows, window_title)

    def address_bar(self, window):
        key = (window["dest"], window["path"])
        cached = self.entries.get(key)
        if cached and self.still_address_bar(window["dest"], cached):
            return cached
        found = self.search(window["dest"], window["path"])
        if found is None:
            self.entries.pop(key, None)
            return None
        self.entries[key] = found
        return found

    def still_address_bar(self, dest, path):
        try:
            name, _ = self.atspi.name_and_count(dest, path)
            return is_address_name(name) and self.atspi.role(dest, path) in ADDRESS_ROLES
        except AtspiError:
            return False

    def search(self, dest, root):
        deadline = self.clock() + SEARCH_BUDGET_SECONDS
        stack = [(dest, root, 0)]
        self.visited = 0
        self.broken = 0
        while stack:
            if self.visited >= MAX_NODES or self.clock() > deadline:
                return None
            node_dest, path, depth = stack.pop()
            self.visited += 1
            try:
                role = self.atspi.role(node_dest, path)
                name, count = self.atspi.name_and_count(node_dest, path)
                if role in ADDRESS_ROLES and is_address_name(name):
                    return path
                if count == 0 or depth >= MAX_DEPTH or role in OPAQUE_ROLES:
                    continue
                children = self.atspi.children(node_dest, path)
            except AtspiError:
                self.broken += 1
                continue
            stack.extend((child_dest, child, depth + 1) for child_dest, child in reversed(children) if child_dest == node_dest)
        return None

    def read(self, window_title):
        window = self.window_for(window_title)
        if window is None:
            raise AtspiError("no Chrome window on the accessibility bus")
        if is_private(window["name"]):
            return {"skip": "private"}
        path = self.address_bar(window)
        if path is None:
            raise AtspiError(
                f"address bar not found ({self.visited} nodes visited, {self.broken} unreadable,"
                " Chrome may not have built its accessibility tree yet)"
            )
        dest = window["dest"]
        try:
            states = self.atspi.states(dest, path)
            if has_state(states, STATE_FOCUSED):
                return {"skip": "editing"}
            return {"value": self.atspi.text(dest, path)}
        except AtspiError:
            self.entries.pop((dest, window["path"]), None)
            raise


def tick(finder, recorder, runner=run_command):
    window = active_window(runner)
    if not is_browser_class(window.get("class")):
        return "not-browser"
    title = window.get("title", "")
    if is_private(title):
        return "private"
    result = finder.read(title)
    if "skip" in result:
        return result["skip"]
    url = clean_url(result["value"])
    if url is None:
        return "rejected"
    return "written" if recorder.record(url, title) else "unchanged"


def settings(environ):
    state = environ.get("SCREENPIPE_URL_STATE") or os.path.expanduser("~/.local/state/screenpipe-url/urls.jsonl")
    interval = float(environ.get("SCREENPIPE_URL_INTERVAL", "2.5"))
    max_mb = float(environ.get("SCREENPIPE_URL_MAX_MB", "10"))
    return state, interval, int(max_mb * 1024 * 1024)


def probe_report(finder, runner=run_command):
    report = {}
    try:
        window = active_window(runner)
        report.update(active_class=window.get("class"), active_title=window.get("title"))
        title = window.get("title", "") if is_browser_class(window.get("class")) else ""
        chosen = finder.window_for(title)
        report["window"] = chosen
        if chosen:
            path = finder.address_bar(chosen)
            report.update(address_bar=path, visited=finder.visited, unreadable=finder.broken)
            if path:
                raw = finder.atspi.text(chosen["dest"], path)
                report["focused"] = has_state(finder.atspi.states(chosen["dest"], path), STATE_FOCUSED)
                report["raw_length"] = len(raw)
                report["clean_url"] = clean_url(raw)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    return report


def probe():
    report = probe_report(Finder(Atspi()))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("address_bar") else 1


def main(argv):
    if "--probe" in argv:
        return probe()
    state, interval, max_bytes = settings(os.environ)
    recorder = Recorder(state, max_bytes)
    finder = Finder(Atspi())
    backoff = Backoff(interval)
    log = ThrottledLog()
    while True:
        guarded_tick(finder, recorder, backoff, log)
        time.sleep(backoff.delay())


def guarded_tick(finder, recorder, backoff, log, runner=run_command):
    try:
        status = tick(finder, recorder, runner)
    except AtspiError as error:
        status = None
        log.error(str(error))
    except Exception as error:
        status = None
        log.error(f"{type(error).__name__}: {error}")
    if status is None:
        backoff.failure()
    else:
        backoff.success()
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
