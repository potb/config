import os
import signal
import subprocess
from datetime import datetime, timezone

from . import chunks, detect

SEGMENT_OPTIONS = [
    "-ac",
    "1",
    "-ar",
    "16000",
    "-c:a",
    "aac",
    "-f",
    "segment",
    "-segment_time",
    str(chunks.CHUNK_SECONDS),
    "-reset_timestamps",
    "1",
    "-strftime",
    "1",
]


class Recorder:
    def __init__(self, cfg, run=detect.run, popen=subprocess.Popen, killpg=os.killpg, environ=None):
        self.cfg = cfg
        self.run = run
        self.popen = popen
        self.killpg = killpg
        self.environ = os.environ if environ is None else environ
        self.procs = []

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

    def _default_sink(self):
        try:
            sink = self.run(["pactl", "get-default-sink"]).strip()
        except (OSError, subprocess.SubprocessError):
            return None
        return sink or None

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
        self.procs.append(self._spawn(self._argv("default", "mic", "input")))
        sink = self._default_sink()
        if sink:
            self.procs.append(self._spawn(self._argv(f"{sink}.monitor", "system", "output")))

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

    def stop(self, timeout=5):
        procs, self.procs = self.procs, []
        for proc in procs:
            if proc.poll() is None:
                self._signal(proc, signal.SIGINT)
        for proc in procs:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                if self._wait(proc, timeout):
                    break
                self._signal(proc, sig)
            else:
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
