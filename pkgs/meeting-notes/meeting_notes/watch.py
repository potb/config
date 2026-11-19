import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import asr as asr_module
from . import chunks, state
from . import cleanup as cleanup_module
from . import diarize as diarize_module
from . import notify as notify_module
from . import pending as pending_module

LOG = logging.getLogger(__name__)

POLL_SECONDS = {"native": 5, "screenpipe": 10}
LIVE_SECONDS = 20
SLOW_STREAK = 2
SETTLE_SECONDS = 60
CATCHUP_SECONDS = 900
CLEANUP_SECONDS = 3600
SILENCE_SECONDS = 90
FETCH_TIMEOUT = 3 * 3600
CLAUDE_TIMEOUT = 3600
DEFAULT_TIMEOUT = 60
KILL_GRACE = 10
TIMEOUT_CODE = 124
MAX_ATTEMPTS = 3
CLAUDE_BATCH = 3
SIDES = ("me", "others")
NOTIFY_TITLE = "meeting-notes"

ALLOWED_TOOLS = (
    "Bash(meeting-notes pending)",
    "Bash(meeting-notes finish:*)",
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
)

DENIED_TOOLS = (
    "Read(**/*.png)",
    "Read(**/*.jpg)",
    "Read(**/.env)",
    "Read(**/voices/**)",
    "Read(**/*.npz)",
    "Write(**/voices/**)",
    "Edit(**/voices/**)",
)

SLACK_SENTENCE = {
    False: (
        "Slack is disabled: do not send, post or share anything, anywhere. Save the notes and "
        "the transcript locally through meeting-notes finish only."
    ),
    True: (
        "meeting-notes finish does all the posting: Claude must never post, send or share "
        "anything itself, anywhere, and never call Slack or any other service. Save the notes "
        "and the transcript through meeting-notes finish only."
    ),
}

PROMPT = """You process the meetings recorded for OWNER. In every transcript the microphone \
side, 'me', is OWNER; 'others' is the system audio, the other participants.

Follow pipe.md in the current directory step by step, and use glossary.md in the current \
directory for names, products and terms. The watcher has already fetched each pending \
meeting into work/<id>/: never fetch or transcribe yourself. To name the participants, \
use meta.json and screen.txt, which holds the OCR text of the captures in \
work/<id>/screens/*.png. Never open the captures themselves: the OCR text is the only \
screen input. In transcript.txt an 'others:<Name>' label comes from a voice print the owner \
confirmed and is reliable; 'others:S1', 'others:S2'... are distinct unknown voices, so give \
each S label one name from meta.json, screen.txt and the content, keep it the same through \
the meeting, and add '(?)' only when truly unsure. A short interjection can carry the wrong \
label.

SLACK_RULE Never read, print or source .env or any other credentials file."""


def prompt(cfg):
    return PROMPT.replace("SLACK_RULE", SLACK_SENTENCE[bool(cfg.slack)]).replace("OWNER", cfg.owner)


def claude_argv(cfg):
    model = ["--model", cfg.claude_model] if cfg.claude_model else []
    return [
        cfg.claude,
        "-p",
        prompt(cfg),
        *model,
        "--permission-mode",
        "acceptEdits",
        "--allowedTools",
        *ALLOWED_TOOLS,
        "--disallowedTools",
        *DENIED_TOOLS,
        "--add-dir",
        str(cfg.meetings_dir),
    ]


def poll_seconds(cfg):
    return POLL_SECONDS.get(cfg.backend, POLL_SECONDS["native"])


def utcnow():
    return datetime.now(timezone.utc)


def stamp(now):
    return now.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")


def list_pending(cfg, now, pending=pending_module):
    lag = getattr(pending, "SETTLE_SECONDS", SETTLE_SECONDS) - SETTLE_SECONDS
    return pending.list_pending(cfg, now + timedelta(seconds=max(0, lag)))


def is_fetched(cfg, mid):
    return (cfg.meeting_dir(mid) / "fetched.ok").exists()


def list_ready(cfg, now, pending=pending_module):
    return [item for item in list_pending(cfg, now, pending) if item.get("resume") or is_fetched(cfg, item["id"])]


def _killpg(proc, sig):
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        pass


def default_run(argv, cwd=None, timeout=DEFAULT_TIMEOUT, log=None):
    handle = None
    if log is not None:
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        handle = open(log, "ab")
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=handle or subprocess.DEVNULL,
            stderr=subprocess.STDOUT if handle else subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _killpg(proc, signal.SIGTERM)
            try:
                proc.wait(timeout=KILL_GRACE)
            except subprocess.TimeoutExpired:
                _killpg(proc, signal.SIGKILL)
                proc.wait()
            code = TIMEOUT_CODE
    finally:
        if handle is not None:
            handle.close()
    return subprocess.CompletedProcess(argv, code)


def default_self_cmd():
    argv0 = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    if argv0 is not None and argv0.name == "meeting-notes" and argv0.is_file():
        return [str(argv0.absolute())]
    found = shutil.which("meeting-notes")
    if found:
        return [found]
    return [sys.executable, "-c", "import sys; from meeting_notes.cli import main; sys.exit(main())"]


def _moment(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return value


class Live:
    def __init__(self, watcher, mid, start):
        self.watcher = watcher
        self.mid = mid
        self.start = start
        self.stopped = threading.Event()
        self.last = None
        self.slow_streak = 0

    def step(self):
        if self.stopped.is_set():
            return
        w = self.watcher
        result = w.asr.live_pass(w.cfg, self.start, w.asr.asr_prompt(w.cfg), self.stopped.is_set, clock=w.clock)
        if result.slow:
            self.slow_streak += 1
        elif result.done:
            self.slow_streak = 0
        if self.slow_streak >= SLOW_STREAK and not self.stopped.is_set():
            self.stopped.set()
            w.set_live(self.mid, "stopped_slow")
            LOG.warning("live transcription too slow, stopped for %s", self.mid)

    def loop(self):
        while not self.stopped.wait(LIVE_SECONDS):
            try:
                self.step()
            except Exception:
                LOG.exception("live pass failed for %s", self.mid)

    def stop(self):
        self.stopped.set()


class Watcher:
    def __init__(
        self,
        cfg,
        backend,
        clock,
        run,
        asr=asr_module,
        pending=pending_module,
        notify=notify_module,
        cleanup=cleanup_module,
        threaded=True,
        self_cmd=None,
    ):
        self.cfg = cfg
        self.backend = backend
        self.clock = clock
        self.run = run
        self.asr = asr
        self.pending = pending
        self.notify = notify
        self.cleanup = cleanup
        self.threaded = threaded
        self.self_cmd = list(self_cmd) if self_cmd is not None else default_self_cmd()
        self.current = None
        self.live = None
        self.audio_since = None
        self.audio_alert = False
        self.manual_pending = False
        self.settle = []
        self.last_catchup = None
        self.last_cleanup = None
        self.started = False
        self.stopping = threading.Event()
        self.wake = threading.Event()
        self.process_lock = threading.Lock()
        self.worker = None

    def tick(self, now):
        if not self.started:
            self.started = True
            self._guard(self._recover, now)
        for step in (self._control, self._poll, self._drive_live, self._schedule, self._audio, self._cleanup):
            self._guard(step, now)

    def _guard(self, step, now):
        try:
            step(now)
        except Exception:
            LOG.exception("%s failed", step.__name__)

    def _last_audio(self, start, now):
        latest = start
        for path in chunks.meeting_chunks(self.cfg.audio_dir, start, now):
            try:
                moment = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            except OSError:
                continue
            latest = max(latest, min(moment, now))
        return latest

    def _recover(self, now):
        with state.locked(self.cfg.state_path) as st:
            stale = [mid for mid, m in st["meetings"].items() if m.get("end") is None]
            for mid in stale:
                start = _moment(st["meetings"][mid]["start"], now)
                state.end_meeting(st, mid, self._last_audio(start, now))
                if st["meetings"][mid].get("live") == "running":
                    st["meetings"][mid]["live"] = "done"
        for mid in stale:
            LOG.warning("closed stale meeting %s", mid)

    def _control(self, now):
        directory = self.cfg.control_dir
        start = directory / "start.json"
        if start.exists():
            try:
                data = json.loads(start.read_text())
            except (OSError, ValueError):
                LOG.warning("invalid %s, using defaults", start)
                data = {}
            start.unlink(missing_ok=True)
            if not isinstance(data, dict):
                data = {}
            app = data.get("app") or "Manual"
            title = data.get("title") or app
            self.manual_pending = True
            try:
                events = self.backend.manual_start(app, title)
            except Exception:
                self.manual_pending = False
                raise
            if events is not None:
                self._handle(events, now)
                self.manual_pending = False
        stop = directory / "stop"
        if stop.exists():
            stop.unlink(missing_ok=True)
            self._handle(self.backend.manual_stop() or [], now)

    def _poll(self, now):
        self._handle(self.backend.poll(now) or [], now)

    def _handle(self, events, now):
        for event in events:
            if event.kind == "start":
                self._begin(event, now)
            elif event.kind == "end":
                self._end(event, now)

    def _begin(self, event, now):
        if self.current is not None:
            self._close(now, now)
        at = _moment(getattr(event, "at", None) or getattr(event, "start", None), now)
        source = "manual" if self.manual_pending else "auto"
        self.manual_pending = False
        extra = {"live": "running" if self.cfg.live else "off"}
        screenpipe_id = getattr(event, "screenpipe_id", None)
        if screenpipe_id is not None:
            extra["screenpipe_id"] = screenpipe_id
        with state.locked(self.cfg.state_path) as st:
            mid = state.start_meeting(st, self.backend.name, event.app, event.title, at, source, **extra)
        LOG.info("meeting %s started (%s, %s)", mid, event.app, source)
        self.current = mid
        self.audio_since = now
        self.audio_alert = False
        if self.cfg.live:
            self._start_live(mid, at, now)

    def _end(self, event, now):
        if self.current is None:
            return
        at = _moment(getattr(event, "at", None) or getattr(event, "end", None), now)
        self._close(at, now)

    def _close(self, at, now):
        mid = self.current
        self._stop_live()
        with state.locked(self.cfg.state_path) as st:
            state.end_meeting(st, mid, at)
            if st["meetings"][mid].get("live") == "running":
                st["meetings"][mid]["live"] = "done"
        LOG.info("meeting %s ended", mid)
        self.current = None
        self.audio_since = None
        self.audio_alert = False
        self.settle.append(now + timedelta(seconds=SETTLE_SECONDS))

    def set_live(self, mid, value):
        with state.locked(self.cfg.state_path) as st:
            if mid in st["meetings"]:
                st["meetings"][mid]["live"] = value

    def _start_live(self, mid, start, now):
        self.live = Live(self, mid, start)
        self.live.last = now
        if self.threaded:
            threading.Thread(target=self.live.loop, name=f"live-{mid}", daemon=True).start()

    def _stop_live(self):
        if self.live is not None:
            self.live.stop()
            self.live = None

    def _drive_live(self, now):
        live = self.live
        if self.threaded or live is None or live.stopped.is_set():
            return
        if (now - live.last).total_seconds() >= LIVE_SECONDS:
            live.last = now
            live.step()

    def _schedule(self, now):
        due = any(moment <= now for moment in self.settle)
        catchup = self.last_catchup is None or (now - self.last_catchup).total_seconds() >= CATCHUP_SECONDS
        if not (due or catchup):
            return
        self.settle = [moment for moment in self.settle if moment > now]
        if catchup:
            self.last_catchup = now
        self.request_process(now)

    def request_process(self, now):
        if not self.threaded:
            self.process(now)
            return
        if self.worker is None:
            self.worker = threading.Thread(target=self._work, name="process", daemon=True)
            self.worker.start()
        self.wake.set()

    def _work(self):
        while not self.stopping.is_set():
            self.wake.wait()
            self.wake.clear()
            if self.stopping.is_set():
                break
            try:
                self.process()
            except Exception:
                LOG.exception("process failed")

    def _fetched(self, mid):
        return is_fetched(self.cfg, mid)

    def _attempt(self, mid, error):
        with state.locked(self.cfg.state_path) as st:
            info = dict(state.processed(st, mid) or {})
            if info.get("status") in state.TERMINAL:
                return
            info.pop("at", None)
            info["attempts"] = info.get("attempts", 0) + 1
            info["last_error"] = error
            if info["attempts"] >= MAX_ATTEMPTS:
                info["status"] = state.FAILED
            state.set_processed(st, mid, **info)
        if info.get("status") == state.FAILED:
            LOG.warning("meeting %s failed after %s attempts: %s", mid, info["attempts"], error)

    def process(self, now=None):
        now = now or self.clock()
        with self.process_lock:
            items = list_pending(self.cfg, now, self.pending)
            if not items:
                return False
            ready = []
            for item in items:
                mid = item["id"]
                if not item.get("resume") and not self._fetched(mid):
                    if self._defer(item, now):
                        continue
                    result = self.fetch(mid, now)
                    if result.returncode or not self._fetched(mid):
                        self._attempt(mid, f"fetch exited {result.returncode}")
                        continue
                ready.append(mid)
            if not ready:
                return False
            result = self.run_claude(now)
            with state.locked(self.cfg.state_path) as st:
                unfinished = [
                    mid
                    for mid in ready[:CLAUDE_BATCH]
                    if (state.processed(st, mid) or {}).get("status") not in state.TERMINAL
                ]
            for mid in unfinished:
                self._attempt(mid, f"claude exited {result.returncode} without finishing")
            return True

    def _defer(self, item, now):
        if not diarize_module.available(self.cfg):
            return False
        active = state.active_meeting(state.load(self.cfg.state_path))
        if active is None or active["id"] == item["id"]:
            return False
        ended = _moment(item.get("end"), now)
        waited = (now - ended).total_seconds() / 60
        limit = self.cfg.diarization_max_delay
        if waited >= limit:
            LOG.info(
                "meeting %s is active but %s waited %.0f min, the %s min cap: diarizing now at low priority",
                active["id"], item["id"], waited, limit,
            )
            return False
        LOG.info(
            "deferring fetch and diarization of %s while meeting %s is active (waited %.0f of %s min)",
            item["id"], active["id"], waited, limit,
        )
        return True

    def fetch(self, mid, now):
        log =self.cfg.runs_dir / f"{stamp(now)}-fetch-{mid}.log"
        self.cfg.runs_dir.mkdir(parents=True, exist_ok=True)
        result = self.run([*self.self_cmd, "fetch", mid], cwd=None, timeout=FETCH_TIMEOUT, log=log)
        if result.returncode:
            LOG.warning("fetch %s exited %s, see %s", mid, result.returncode, log)
        return result

    def run_claude(self, now):
        log = self.cfg.runs_dir / f"{stamp(now)}.log"
        self.cfg.runs_dir.mkdir(parents=True, exist_ok=True)
        self.cfg.data_dir.mkdir(parents=True, exist_ok=True)
        LOG.info("running claude, log %s", log)
        result = self.run(claude_argv(self.cfg), cwd=self.cfg.data_dir, timeout=CLAUDE_TIMEOUT, log=log)
        if result.returncode:
            LOG.warning("claude exited %s, see %s", result.returncode, log)
        return result

    def _audio(self, now):
        if self.current is None:
            return
        newest = chunks.newest_by_side(self.cfg.audio_dir)
        floor = self.audio_since.timestamp()
        moment = now.timestamp()
        silent = [side for side in SIDES if moment - max(newest.get(side) or 0, floor) >= SILENCE_SECONDS]
        if silent and not self.audio_alert:
            self.audio_alert = True
            body = f"No audio from {' and '.join(silent)} for {SILENCE_SECONDS} s"
            LOG.warning(body)
            self.notify.send(NOTIFY_TITLE, body, self.run)
        elif not silent and self.audio_alert:
            self.audio_alert = False
            self.notify.send(NOTIFY_TITLE, "Recording audio is back", self.run)

    def _cleanup(self, now):
        if self.last_cleanup is not None and (now - self.last_cleanup).total_seconds() < CLEANUP_SECONDS:
            return
        self.last_cleanup = now
        removed = self.cleanup.run(self.cfg, now)
        LOG.info("cleanup %s", removed)

    def close(self):
        if self.current is not None:
            now = self.clock()
            self._guard(lambda moment: self._close(moment, moment), now)
        self._stop_live()
        self.stopping.set()
        self.wake.set()
        self.backend.close()


def main(cfg=None, backend=None):
    from . import backends
    from .config import Config

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = cfg or Config.from_env()
    backend = backend or backends.make(cfg, utcnow)
    watcher = Watcher(cfg, backend, utcnow, default_run)
    stop = threading.Event()

    def _stop(signum, frame):
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    interval = poll_seconds(cfg)
    LOG.info("watching with %s backend, live %s", backend.name, "on" if cfg.live else "off")
    try:
        while not stop.is_set():
            watcher.tick(utcnow())
            stop.wait(interval)
    finally:
        watcher.close()
    return 0
