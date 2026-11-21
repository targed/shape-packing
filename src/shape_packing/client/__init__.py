"""Distributed shape packing native client package."""

from __future__ import annotations
import importlib
from typing import Any

__all__ = [
    "WorkerConfig",
    "send_request",
    "register_with_server",
    "set_process_idle_priority",
    "set_idle_priority",
    "HeartbeatReporter",
    "flush_in_flight_heartbeat",
    "set_in_flight_work",
    "handle_signal",
    "setup_signal_handlers",
    "run_worker_cycle",
    "run_worker_loop",
    "main",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        mod = importlib.import_module(".native_worker", __package__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
