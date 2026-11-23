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
    # Controller & Scheduling
    "WorkerController",
    "WorkerState",
    "ScheduleConfig",
    "TelemetrySnapshot",
    # Autostart
    "AutostartManager",
    # System Tray
    "TrayManager",
    "create_status_icon",
    # Desktop GUI
    "WorkerApp",
    "DesktopConfig",
    "load_desktop_config",
    "save_desktop_config",
]

_SUBMODULE_MAP = {
    "WorkerController": ".controller",
    "WorkerState": ".controller",
    "ScheduleConfig": ".controller",
    "TelemetrySnapshot": ".controller",
    "AutostartManager": ".autostart",
    "TrayManager": ".tray",
    "create_status_icon": ".tray",
    "WorkerApp": ".gui",
    "DesktopConfig": ".gui",
    "load_desktop_config": ".gui",
    "save_desktop_config": ".gui",
}


def __getattr__(name: str) -> Any:
    if name in __all__:
        submod = _SUBMODULE_MAP.get(name, ".native_worker")
        mod = importlib.import_module(submod, __package__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
