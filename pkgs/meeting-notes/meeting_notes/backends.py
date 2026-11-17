from datetime import datetime, timezone

from .backend_native import NativeBackend
from .backend_screenpipe import ScreenpipeBackend


def utcnow():
    return datetime.now(timezone.utc)


def make(cfg, clock=utcnow):
    if cfg.backend == "native":
        return NativeBackend(cfg, clock=clock)
    if cfg.backend == "screenpipe":
        from .screenpipe import Client

        return ScreenpipeBackend(cfg, Client(cfg), clock)
    raise ValueError(f"unknown backend {cfg.backend!r}")
