import logging
import os
import signal
import subprocess
from datetime import datetime, timezone

from . import chunks, detect
from . import notify as notify_module

LOG = logging.getLogger(__name__)
NOTIFY_TITLE = "meeting-notes"
STOP_SECONDS = 5

SEGMENT_OPTIONS = [
    "-ac",
    "1",
    "-ar",
    "16000",
    "-c:a",
    "aac",
    "-f",
    "segment",
    "-segment_format_options",
    "movflags=+frag_keyframe+empty_moov+default_base_moof:frag_duration=1000000:flush_packets=1",
    "-segment_time",
    str(chunks.CHUNK_SECONDS),
    "-reset_timestamps",
    "1",
    "-strftime",
    "1",
]


class SourceError(Exception):
    pass


def _pactl(run, command):
    try:
        value = run(["pactl", command]).strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return value or None


def others_source(cfg, run=detect.run):
    if cfg.monitor_source:
        return cfg.monitor_source
    sink = _pactl(run, "get-default-sink")
    return f"{sink}.monitor" if sink else None


def mic_source(cfg, others, run=detect.run):
    name = cfg.mic_source or _pactl(run, "get-default-source")
    if not name:
        raise SourceError("no microphone source: pactl get-default-source gave nothing")
    if name.endswith(".monitor"):
        raise SourceError(f"microphone source {name} is a monitor, not a microphone")
    if others and name == others:
        raise SourceError(f"microphone source {name} is the same as the others source")
    return name


def resolve_sources(cfg, run=detect.run):
    others = others_source(cfg, run)
    return {"me": mic_source(cfg, others, run), "others": others}


class Recorder:
    def __init__(
        self,
        cfg,
        run=detect.run,
        popen=subprocess.Popen,
        killpg=os.killpg,
        environ=None,
        notify=notify_module.send,
    ):
        self.cfg = cfg
        self.run = run
        self.popen = popen
        self.killpg = killpg
        self.environ = os.environ if environ is None else environ
        self.notify = notify
        self.procs = []
        self.sources = None

    def _argv(self, source, device, kind):
        output = self.cfg.audio_dir / chunks.ffmpeg_pattern(device, kind)
        return [
            self.cfg.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-f",
            "pulse",
            "-i",
            source,
            *SEGMENT_OPTIONS,
            str(output),
        ]

    def _spawn(self, argv):
        env = dict(self.environ, TZ="UTC")
        return self.popen(
            argv,
            env=env,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def start(self):
        if self.procs:
            if self.alive():
                return
            self.stop()
        self.cfg.audio_dir.mkdir(parents=True, exist_ok=True)
        others = others_source(self.cfg, self.run)
        try:
            me = mic_source(self.cfg, others, self.run)
        except SourceError as error:
            me = None
            LOG.error("not recording the me side: %s", error)
            self.notify(NOTIFY_TITLE, f"Microphone not recorded: {error}", self.run)
        if others is None:
            LOG.error("not recording the others side: pactl get-default-sink gave nothing")
        self.sources = {"me": me, "others": others}
        LOG.info("recording sources: me %s, others %s", me, others)
        if me:
            self.procs.append(self._spawn(self._argv(me, "mic", "input")))
        if others:
            self.procs.append(self._spawn(self._argv(others, "system", "output")))

    def _signal(self, proc, sig):
        try:
            self.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    def _wait(self, proc, timeout):
        try:
            proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    def stop(self, timeout=STOP_SECONDS):
        procs, self.procs = self.procs, []
        for proc in procs:
            if proc.poll() is None:
                self._signal(proc, signal.SIGINT)
        for proc in procs:
            if self._wait(proc, timeout):
                continue
            LOG.warning("ffmpeg %s did not finish its chunk in %s s, killing it", proc.pid, timeout)
            self._signal(proc, signal.SIGKILL)
            self._wait(proc, timeout)

    def alive(self):
        return bool(self.procs) and all(proc.poll() is None for proc in self.procs)

    def pids(self):
        return [proc.pid for proc in self.procs]


def screenshot(cfg, meeting_id, window, run=detect.run, now=None):
    now = now or datetime.now(timezone.utc)
    stamp = now.astimezone(timezone.utc).strftime(chunks.TS_FORMAT)
    directory = cfg.screens_dir(meeting_id)
    path = directory / f"{stamp}.png"
    if not window.stable_id:
        return None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        run(["grim", "-T", window.stable_id, str(path)])
    except (OSError, subprocess.SubprocessError):
        return None
    return path
