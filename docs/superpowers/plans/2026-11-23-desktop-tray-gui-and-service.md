# Desktop System Tray GUI & Background Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cross-platform desktop system tray application and background service for Distributed Shape Packing volunteers featuring CPU core sliders, pause/snooze controls, active time window scheduling, live telemetry, and zero-elevation autostart on system boot.

**Architecture:** A thread-safe controller (`controller.py`) manages the background worker execution and schedule/snooze timers. A cross-platform autostart manager (`autostart.py`) configures user-level startup across Windows (Registry), macOS (LaunchAgents), and Linux (XDG Autostart). A lightweight Tkinter window (`gui.py`) coupled with a dynamic `pystray` system tray icon (`tray.py`) delivers responsive control with zero heavy framework bloat.

**Tech Stack:** Python 3, `tkinter`, `pystray`, `Pillow`, `urllib`, `threading`, `queue`, `unittest`/`pytest`.

## Global Constraints

- Must run on standard Python with `tkinter` and `pystray`; no PyQt/PySide or C++ GUI framework dependencies.
- Compute worker execution must never block the Tkinter event loop or system tray thread.
- System startup must operate entirely at the user level (no administrator / root requirements).
- All settings and worker credentials must be preserved in `~/.shape_packing_worker.json`.

---

### Task 1: Worker State Machine & Scheduling Controller

**Files:**
- Create: `src/shape_packing/client/controller.py`
- Test: `tests/test_client_controller.py`

**Interfaces:**
- Consumes: `src/shape_packing/client/native_worker.py` (`WorkerConfig`, `run_worker_cycle`, `deregister_with_server`, `flush_in_flight_heartbeat`)
- Produces: `WorkerState`, `ScheduleConfig`, and `WorkerController` managing thread lifecycle, time windows, and snooze timers.

- [x] **Step 1: Write the failing test suite**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Implement `src/shape_packing/client/controller.py`**
- [x] **Step 4: Run test to verify it passes**

```python
# src/shape_packing/client/controller.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dt_time
from enum import Enum
import os
import queue
import threading
import time
from typing import Any, Callable, Dict, Optional

from .native_worker import (
    WorkerConfig,
    deregister_with_server,
    flush_in_flight_heartbeat,
    run_worker_cycle,
)


class WorkerState(str, Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    SNOOZED = "SNOOZED"
    SCHEDULED_IDLE = "SCHEDULED_IDLE"
    ERROR = "ERROR"


def parse_time_str(val: str, default: dt_time) -> dt_time:
    """Parse HH:MM 24-hour time string into datetime.time."""
    try:
        parts = val.strip().split(":")
        return dt_time(int(parts[0]), int(parts[1]))
    except Exception:
        return default


def is_within_schedule(now_time: dt_time, start: dt_time, end: dt_time) -> bool:
    """Evaluate whether current time falls within an active schedule window."""
    if start <= end:
        return start <= now_time < end
    # Crosses midnight (e.g. 22:00 to 07:00)
    return now_time >= start or now_time < end


@dataclass
class ScheduleConfig:
    enabled: bool = False
    start_time: str = "22:00"
    end_time: str = "07:00"

    @property
    def start(self) -> dt_time:
        return parse_time_str(self.start_time, dt_time(22, 0))

    @property
    def end(self) -> dt_time:
        return parse_time_str(self.end_time, dt_time(7, 0))


@dataclass
class TelemetrySnapshot:
    state: WorkerState
    problem: str = ""
    n: int = 0
    best_s: Optional[float] = None
    attempts_cycle: int = 0
    total_attempts: int = 0
    records_broken: int = 0
    snooze_remaining_seconds: float = 0.0
    status_message: str = ""


class WorkerController:
    """Thread-safe controller managing worker lifecycle, schedule, and snooze timers."""

    def __init__(
        self,
        cycle_fn: Optional[Callable] = None,
        config: Optional[WorkerConfig] = None,
        schedule: Optional[ScheduleConfig] = None,
    ):
        self._cycle_fn = cycle_fn or run_worker_cycle
        self.config = config or WorkerConfig()
        self.schedule = schedule or ScheduleConfig()

        self._state = WorkerState.STOPPED
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._snooze_deadline: Optional[float] = None
        self._is_manually_paused: bool = False

        self._total_attempts: int = 0
        self._records_broken: int = 0
        self._current_problem: str = ""
        self._current_n: int = 0
        self._current_best_s: Optional[float] = None
        self._status_message: str = "Stopped"

        self.event_queue: queue.Queue = queue.Queue()

    def get_state(self) -> WorkerState:
        with self._lock:
            return self._state

    def get_snooze_remaining_seconds(self) -> float:
        with self._lock:
            if self._state == WorkerState.SNOOZED and self._snooze_deadline:
                return max(0.0, self._snooze_deadline - time.time())
            return 0.0

    def get_snapshot(self) -> TelemetrySnapshot:
        with self._lock:
            return TelemetrySnapshot(
                state=self._state,
                problem=self._current_problem,
                n=self._current_n,
                best_s=self._current_best_s,
                attempts_cycle=0,
                total_attempts=self._total_attempts,
                records_broken=self._records_broken,
                snooze_remaining_seconds=self.get_snooze_remaining_seconds(),
                status_message=self._status_message,
            )

    def set_cores(self, cores: int) -> None:
        """Dynamically update CPU core count for Rayon/OpenMP."""
        with self._lock:
            cores = max(1, cores)
            self.config.cores = cores
            os.environ["RAYON_NUM_THREADS"] = str(cores)
            os.environ["OMP_NUM_THREADS"] = str(cores)

    def start(self, config: Optional[WorkerConfig] = None) -> None:
        """Start worker thread and enter active or scheduled crunching."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            if config:
                self.config = config
                self.set_cores(config.cores)

            self._is_manually_paused = False
            self._snooze_deadline = None
            self._stop_event.clear()
            self._state = WorkerState.RUNNING
            self._status_message = "Starting..."

            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="WorkerControllerLoop")
            self._thread.start()

    def pause(self) -> None:
        """Manually pause the worker."""
        with self._lock:
            self._is_manually_paused = True
            self._snooze_deadline = None
            self._state = WorkerState.PAUSED
            self._status_message = "Paused by user"
            self._emit_event()

    def resume(self) -> None:
        """Resume execution from paused or snoozed state."""
        with self._lock:
            self._is_manually_paused = False
            self._snooze_deadline = None
            self._state = WorkerState.RUNNING
            self._status_message = "Resumed"
            self._emit_event()

    def snooze(self, minutes: float = 30.0, seconds: Optional[float] = None) -> None:
        """Temporarily pause crunching for a specified duration."""
        with self._lock:
            duration = seconds if seconds is not None else (minutes * 60.0)
            self._is_manually_paused = False
            self._snooze_deadline = time.time() + duration
            self._state = WorkerState.SNOOZED
            self._status_message = f"Snoozed for {int(duration / 60) if duration >= 60 else duration}m"
            self._emit_event()

    def stop(self) -> None:
        """Gracefully stop worker execution, flush heartbeats, and deregister node."""
        with self._lock:
            self._stop_event.set()
            self._state = WorkerState.STOPPED
            self._status_message = "Stopped"

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            self._thread = None

        try:
            flush_in_flight_heartbeat(self.config)
            deregister_with_server(self.config)
        except Exception:
            pass

        self._emit_event()

    def _emit_event(self) -> None:
        self.event_queue.put(self.get_snapshot())

    def _run_loop(self) -> None:
        backoff = 2.0
        while not self._stop_event.is_set():
            # 1. Check manual pause
            with self._lock:
                if self._is_manually_paused:
                    self._state = WorkerState.PAUSED
                    self._status_message = "Paused"
                    self._emit_event()
                    time.sleep(0.5)
                    continue

                # 2. Check snooze
                if self._snooze_deadline is not None:
                    remaining = self._snooze_deadline - time.time()
                    if remaining > 0:
                        self._state = WorkerState.SNOOZED
                        rem_m = int(remaining // 60)
                        self._status_message = f"Snoozed ({rem_m}m left)"
                        self._emit_event()
                        time.sleep(min(1.0, remaining))
                        continue
                    else:
                        self._snooze_deadline = None

                # 3. Check schedule
                if self.schedule.enabled:
                    now = datetime.now().time()
                    if not is_within_schedule(now, self.schedule.start, self.schedule.end):
                        self._state = WorkerState.SCHEDULED_IDLE
                        self._status_message = f"Sleeping (Active {self.schedule.start_time} - {self.schedule.end_time})"
                        self._emit_event()
                        time.sleep(5.0)
                        continue

                self._state = WorkerState.RUNNING

            # 4. Execute work cycle
            try:
                res = self._cycle_fn(self.config, stop_event=self._stop_event)
                attempts = res.get("attempts_completed", 0)
                problem = res.get("problem", "")
                metric_s = res.get("metric_s")
                is_record = res.get("is_new_record", False)

                with self._lock:
                    self._total_attempts += attempts
                    if problem:
                        self._current_problem = problem
                    if metric_s is not None:
                        self._current_best_s = metric_s
                    if is_record:
                        self._records_broken += 1
                    self._status_message = f"Crunching {self._current_problem}"
                    backoff = 2.0

                self._emit_event()
                time.sleep(0.05)
            except Exception as exc:
                with self._lock:
                    self._state = WorkerState.ERROR
                    self._status_message = f"Connection error: {exc}"
                self._emit_event()
                time.sleep(min(30.0, backoff))
                backoff = min(60.0, backoff * 1.5)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest tests/test_client_controller.py -v`  
Expected: PASS (all tests pass)

---

### Task 2: Cross-Platform Autostart Manager & CLI Service Tool

**Files:**
- Create: `src/shape_packing/client/autostart.py`
- Test: `tests/test_client_autostart.py`

**Interfaces:**
- Consumes: Standard library `winreg`, `os`, `sys`, `platform`, `subprocess`
- Produces: `AutostartManager` class and `main()` CLI subcommands (`enable`, `disable`, `status`).

- [x] **Step 1: Write the failing test suite**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Implement `src/shape_packing/client/autostart.py`**
- [x] **Step 4: Run test to verify it passes**

```python
# src/shape_packing/client/autostart.py
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from typing import Any, Dict, Optional

APP_NAME = "ShapePackingWorker"
MACOS_PLIST_LABEL = "com.shapepacking.worker"


def get_worker_command(minimized: bool = True) -> str:
    """Resolve the appropriate Python executable and CLI invocation."""
    exe = sys.executable
    if platform.system().lower() == "windows":
        # Prefer pythonw.exe to prevent terminal popup window
        dirname, fname = os.path.split(exe)
        pythonw_candidate = os.path.join(dirname, "pythonw.exe")
        if os.path.exists(pythonw_candidate):
            exe = pythonw_candidate

    min_flag = " --minimized" if minimized else ""
    return f'"{exe}" -m src.shape_packing.client.gui{min_flag}'


class AutostartManager:
    """Manages cross-platform user-level autostart on system boot."""

    def __init__(self):
        self.platform = platform.system().lower()

    def is_enabled(self) -> bool:
        if self.platform == "windows":
            return self._is_enabled_windows()
        elif self.platform == "darwin":
            return self._is_enabled_macos()
        elif self.platform == "linux":
            return self._is_enabled_linux()
        return False

    def enable(self, minimized: bool = True) -> bool:
        cmd = get_worker_command(minimized=minimized)
        if self.platform == "windows":
            return self._enable_windows(cmd)
        elif self.platform == "darwin":
            return self._enable_macos(cmd)
        elif self.platform == "linux":
            return self._enable_linux(cmd)
        return False

    def disable(self) -> bool:
        if self.platform == "windows":
            return self._disable_windows()
        elif self.platform == "darwin":
            return self._disable_macos()
        elif self.platform == "linux":
            return self._disable_linux()
        return False

    def status(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "enabled": self.is_enabled(),
            "command": get_worker_command(minimized=True),
        }

    # --- Windows Implementation ---
    def _is_enabled_windows(self) -> bool:
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, APP_NAME)
                return bool(val)
        except Exception:
            return False

    def _enable_windows(self, cmd: str) -> bool:
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                return True
        except Exception:
            return False

    def _disable_windows(self) -> bool:
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP_NAME)
                return True
        except FileNotFoundError:
            return True
        except Exception:
            return False

    # --- macOS Implementation ---
    def _get_macos_plist_path(self) -> str:
        return os.path.expanduser(f"~/Library/LaunchAgents/{MACOS_PLIST_LABEL}.plist")

    def _is_enabled_macos(self) -> bool:
        return os.path.exists(self._get_macos_plist_path())

    def _enable_macos(self, cmd: str) -> bool:
        plist_path = self._get_macos_plist_path()
        os.makedirs(os.path.dirname(plist_path), exist_ok=True)
        content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{MACOS_PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>-m</string>
        <string>src.shape_packing.client.gui</string>
        <string>--minimized</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
        try:
            with open(plist_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception:
            return False

    def _disable_macos(self) -> bool:
        plist_path = self._get_macos_plist_path()
        if os.path.exists(plist_path):
            try:
                os.remove(plist_path)
                return True
            except Exception:
                return False
        return True

    # --- Linux Implementation ---
    def _get_linux_desktop_path(self) -> str:
        return os.path.expanduser("~/.config/autostart/shape-packing-worker.desktop")

    def _is_enabled_linux(self) -> bool:
        return os.path.exists(self._get_linux_desktop_path())

    def _enable_linux(self, cmd: str) -> bool:
        desktop_path = self._get_linux_desktop_path()
        os.makedirs(os.path.dirname(desktop_path), exist_ok=True)
        content = f"""[Desktop Entry]
Type=Application
Version=1.0
Name=Shape Packing Worker
Comment=Distributed Shape Packing Volunteer Node
Exec={cmd}
Terminal=false
Categories=Utility;Math;Science;
"""
        try:
            with open(desktop_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception:
            return False

    def _disable_linux(self) -> bool:
        desktop_path = self._get_linux_desktop_path()
        if os.path.exists(desktop_path):
            try:
                os.remove(desktop_path)
                return True
            except Exception:
                return False
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Distributed Shape Packing Autostart Service Tool")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("enable", help="Enable automatic startup on login")
    subparsers.add_parser("disable", help="Disable automatic startup on login")

    status_parser = subparsers.add_parser("status", help="Query autostart configuration status")
    status_parser.add_argument("--json", action="store_true", help="Format output as JSON")

    args = parser.parse_args()
    mgr = AutostartManager()

    if args.command == "enable":
        ok = mgr.enable()
        print("Autostart successfully enabled." if ok else "Failed to enable autostart.")
        sys.exit(0 if ok else 1)
    elif args.command == "disable":
        ok = mgr.disable()
        print("Autostart successfully disabled." if ok else "Failed to disable autostart.")
        sys.exit(0 if ok else 1)
    elif args.command == "status":
        stat = mgr.status()
        if getattr(args, "json", False):
            print(json.dumps(stat, indent=2))
        else:
            print(f"Platform: {stat['platform']}")
            print(f"Autostart Enabled: {stat['enabled']}")
            print(f"Command: {stat['command']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest tests/test_client_autostart.py -v`  
Expected: PASS (all tests pass)

---

### Task 3: System Tray Icon Manager (`pystray` Integration)

**Files:**
- Create: `src/shape_packing/client/tray.py`
- Test: `tests/test_client_tray.py`

**Interfaces:**
- Consumes: `Pillow` (PIL), `pystray` (optional), `src/shape_packing/client/controller.py` (`WorkerState`, `WorkerController`)
- Produces: `TrayManager` and `create_status_icon(color, size)` generating clean RGBA icons.

- [x] **Step 1: Write the failing test suite**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Implement `src/shape_packing/client/tray.py`**
- [x] **Step 4: Run test to verify it passes**

```python
# src/shape_packing/client/tray.py
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from PIL import Image, ImageDraw

from .controller import WorkerController, WorkerState

logger = logging.getLogger(__name__)

COLOR_MAP = {
    WorkerState.RUNNING.value: "#22c55e",       # Green
    WorkerState.PAUSED.value: "#f59e0b",        # Amber
    WorkerState.SNOOZED.value: "#f59e0b",       # Amber
    WorkerState.SCHEDULED_IDLE.value: "#3b82f6", # Blue
    WorkerState.ERROR.value: "#ef4444",         # Red
    WorkerState.STOPPED.value: "#64748b",       # Gray
}


def create_status_icon(state_or_color: str, size: int = 64) -> Image.Image:
    """Generate an in-memory RGBA circular status icon for the system tray."""
    color = COLOR_MAP.get(state_or_color, state_or_color if state_or_color.startswith("#") else "#64748b")
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Draw outer antialiased circle
    margin = max(2, int(size * 0.08))
    draw.ellipse((margin, margin, size - margin, size - margin), fill=color)

    # Draw inner subtle accent dot
    inner_m = int(size * 0.35)
    draw.ellipse((inner_m, inner_m, size - inner_m, size - inner_m), fill="#ffffff88")
    return image


class TrayManager:
    """Manages the pystray system tray icon and context menu."""

    def __init__(
        self,
        controller: Optional[WorkerController] = None,
        on_toggle_window: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
    ):
        self.controller = controller
        self.on_toggle_window = on_toggle_window
        self.on_quit = on_quit
        self._icon = None
        self._is_supported = False

        try:
            import pystray
            self._pystray = pystray
            self._is_supported = True
        except ImportError:
            self._pystray = None
            self._is_supported = False
            logger.info("pystray is not installed; running in standard window mode.")

    def is_supported(self) -> bool:
        return self._is_supported

    def start(self) -> None:
        """Start system tray icon in detached thread."""
        if not self._is_supported or not self._pystray:
            return

        icon_image = create_status_icon(WorkerState.STOPPED.value)
        menu = self._build_menu()
        self._icon = self._pystray.Icon("ShapePackingWorker", icon_image, "Shape Packing Worker", menu=menu)

        # Run pystray in background thread so it doesn't block Tkinter
        t = threading.Thread(target=self._icon.run, daemon=True, name="SystemTrayThread")
        t.start()

    def update_state(self, state: WorkerState, tooltip_text: Optional[str] = None) -> None:
        """Update tray icon color and tooltip."""
        if not self._icon or not self._is_supported:
            return
        try:
            self._icon.icon = create_status_icon(state.value)
            if tooltip_text:
                self._icon.title = f"Shape Packing ({tooltip_text})"
        except Exception:
            pass

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    def _build_menu(self):
        p = self._pystray

        def _pause_resume(icon, item):
            if self.controller:
                if self.controller.get_state() == WorkerState.RUNNING:
                    self.controller.pause()
                else:
                    self.controller.resume()

        def _snooze_30m(icon, item):
            if self.controller:
                self.controller.snooze(minutes=30)

        def _snooze_1h(icon, item):
            if self.controller:
                self.controller.snooze(minutes=60)

        def _toggle_win(icon, item):
            if self.on_toggle_window:
                self.on_toggle_window()

        def _quit_app(icon, item):
            if self.on_quit:
                self.on_quit()

        return p.Menu(
            p.MenuItem("Show/Hide Control Window", _toggle_win, default=True),
            p.Menu.SEPARATOR,
            p.MenuItem("Pause / Resume", _pause_resume),
            p.MenuItem("Snooze 30 min", _snooze_30m),
            p.MenuItem("Snooze 1 hour", _snooze_1h),
            p.Menu.SEPARATOR,
            p.MenuItem("Quit Worker", _quit_app),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest tests/test_client_tray.py -v`  
Expected: PASS

---

### Task 4: Tkinter Desktop Application UI & User Settings Persistence

**Files:**
- Create: `src/shape_packing/client/gui.py`
- Test: `tests/test_client_gui.py`

**Interfaces:**
- Consumes: `src/shape_packing/client/controller.py`, `src/shape_packing/client/autostart.py`, `src/shape_packing/client/tray.py`
- Produces: Complete graphical desktop app `WorkerApp` and `main()` entrypoint.

- [x] **Step 1: Write the failing test suite**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Implement `src/shape_packing/client/gui.py`**
- [x] **Step 4: Run test to verify it passes**

```python
# src/shape_packing/client/gui.py
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from .autostart import AutostartManager
from .controller import ScheduleConfig, TelemetrySnapshot, WorkerController, WorkerState
from .native_worker import (
    WorkerConfig,
    load_cached_worker_id,
    register_with_server,
    save_cached_worker_id,
)
from .tray import TrayManager

CONFIG_PATH = os.path.expanduser("~/.shape_packing_worker.json")


@dataclass
class DesktopConfig:
    server_url: str = "http://localhost:8000"
    username: str = "volunteer"
    worker_id: Optional[str] = None
    cores: int = 4
    autostart: bool = False
    start_minimized: bool = False
    minimize_on_close: bool = True
    schedule_enabled: bool = False
    schedule_start: str = "22:00"
    schedule_end: str = "07:00"


def load_desktop_config(path: str = CONFIG_PATH) -> DesktopConfig:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return DesktopConfig(**{k: v for k, v in data.items() if k in DesktopConfig.__annotations__})
        except Exception:
            pass
    return DesktopConfig()


def save_desktop_config(cfg: DesktopConfig, path: str = CONFIG_PATH) -> None:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(cfg), f, indent=2)
    except Exception:
        pass


class WorkerApp:
    """Desktop GUI Control Panel for Distributed Shape Packing volunteers."""

    def __init__(self, root: tk.Tk, start_minimized: bool = False):
        self.root = root
        self.root.title("Distributed Shape Packing Worker")
        self.root.geometry("460x520")
        self.root.resizable(False, False)

        self.desktop_cfg = load_desktop_config()
        self.autostart_mgr = AutostartManager()

        sched = ScheduleConfig(
            enabled=self.desktop_cfg.schedule_enabled,
            start_time=self.desktop_cfg.schedule_start,
            end_time=self.desktop_cfg.schedule_end,
        )
        self.controller = WorkerController(schedule=sched)

        self.tray = TrayManager(
            controller=self.controller,
            on_toggle_window=self._toggle_window,
            on_quit=self._on_quit,
        )
        self.tray.start()

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_window)

        # Start periodic queue polling
        self.root.after(200, self._poll_events)

        if start_minimized or self.desktop_cfg.start_minimized:
            self.root.withdraw()
            self._start_crunching()

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        # Header status bar
        header_frame = ttk.Frame(container)
        header_frame.pack(fill=tk.X, pady=(0, 12))

        self.status_canvas = tk.Canvas(header_frame, width=16, height=16, highlightthickness=0)
        self.status_canvas.pack(side=tk.LEFT, padx=(0, 6))
        self.status_dot = self.status_canvas.create_oval(2, 2, 14, 14, fill="#64748b", outline="")

        self.status_label = ttk.Label(header_frame, text="STOPPED", font=("Helvetica", 11, "bold"))
        self.status_label.pack(side=tk.LEFT)

        self.problem_label = ttk.Label(header_frame, text="", foreground="#64748b", font=("Helvetica", 9))
        self.problem_label.pack(side=tk.RIGHT)

        # Connection Card
        conn_frame = ttk.LabelFrame(container, text="Coordinator Connection", padding=8)
        conn_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(conn_frame, text="Server:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.server_entry = ttk.Entry(conn_frame)
        self.server_entry.insert(0, self.desktop_cfg.server_url)
        self.server_entry.grid(row=0, column=1, sticky=tk.EW, padx=(6, 0), pady=2)

        ttk.Label(conn_frame, text="Username:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.user_entry = ttk.Entry(conn_frame)
        self.user_entry.insert(0, self.desktop_cfg.username)
        self.user_entry.grid(row=1, column=1, sticky=tk.EW, padx=(6, 0), pady=2)
        conn_frame.columnconfigure(1, weight=1)

        # Compute Resources Card
        comp_frame = ttk.LabelFrame(container, text="Compute Resources", padding=8)
        comp_frame.pack(fill=tk.X, pady=(0, 8))

        max_cores = os.cpu_count() or 4
        self.cores_var = tk.IntVar(value=min(self.desktop_cfg.cores, max_cores))

        core_header = ttk.Frame(comp_frame)
        core_header.pack(fill=tk.X)
        ttk.Label(core_header, text="Allocated Cores:").pack(side=tk.LEFT)
        self.cores_label = ttk.Label(core_header, text=f"{self.cores_var.get()} / {max_cores} Cores")
        self.cores_label.pack(side=tk.RIGHT)

        self.cores_scale = ttk.Scale(
            comp_frame,
            from_=1,
            to=max_cores,
            variable=self.cores_var,
            orient=tk.HORIZONTAL,
            command=self._on_cores_slider,
        )
        self.cores_scale.pack(fill=tk.X, pady=(4, 0))

        # Controls & Scheduling Card
        ctrl_frame = ttk.LabelFrame(container, text="Execution & Schedule", padding=8)
        ctrl_frame.pack(fill=tk.X, pady=(0, 8))

        btn_row = ttk.Frame(ctrl_frame)
        btn_row.pack(fill=tk.X, pady=(0, 6))

        self.toggle_btn = ttk.Button(btn_row, text="Start Crunching", command=self._toggle_run)
        self.toggle_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.snooze_btn = ttk.Menubutton(btn_row, text="Snooze 30m ▼")
        snooze_menu = tk.Menu(self.snooze_btn, tearoff=False)
        snooze_menu.add_command(label="Snooze 30 Minutes", command=lambda: self.controller.snooze(minutes=30))
        snooze_menu.add_command(label="Snooze 1 Hour", command=lambda: self.controller.snooze(minutes=60))
        snooze_menu.add_command(label="Snooze 2 Hours", command=lambda: self.controller.snooze(minutes=120))
        self.snooze_btn["menu"] = snooze_menu
        self.snooze_btn.pack(side=tk.RIGHT)

        # Schedule row
        sched_row = ttk.Frame(ctrl_frame)
        sched_row.pack(fill=tk.X)
        self.sched_var = tk.BooleanVar(value=self.desktop_cfg.schedule_enabled)
        self.sched_cb = ttk.Checkbutton(sched_row, text="Active hours only:", variable=self.sched_var, command=self._on_schedule_toggle)
        self.sched_cb.pack(side=tk.LEFT)

        self.start_time_entry = ttk.Entry(sched_row, width=6)
        self.start_time_entry.insert(0, self.desktop_cfg.schedule_start)
        self.start_time_entry.pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(sched_row, text="to").pack(side=tk.LEFT, padx=2)
        self.end_time_entry = ttk.Entry(sched_row, width=6)
        self.end_time_entry.insert(0, self.desktop_cfg.schedule_end)
        self.end_time_entry.pack(side=tk.LEFT, padx=2)

        # Telemetry Card
        telem_frame = ttk.LabelFrame(container, text="Telemetry & Results", padding=8)
        telem_frame.pack(fill=tk.X, pady=(0, 8))

        self.attempts_label = ttk.Label(telem_frame, text="Attempts Completed: 0")
        self.attempts_label.pack(anchor=tk.W)

        self.records_label = ttk.Label(telem_frame, text="World Records Broken: 0", font=("Helvetica", 9, "bold"), foreground="#059669")
        self.records_label.pack(anchor=tk.W)

        # Footer Checkboxes
        foot_frame = ttk.Frame(container)
        foot_frame.pack(fill=tk.X, pady=(4, 0))

        self.autostart_var = tk.BooleanVar(value=self.autostart_mgr.is_enabled())
        self.autostart_cb = ttk.Checkbutton(
            foot_frame,
            text="Start automatically on system boot",
            variable=self.autostart_var,
            command=self._on_autostart_toggle,
        )
        self.autostart_cb.pack(anchor=tk.W)

        self.min_close_var = tk.BooleanVar(value=self.desktop_cfg.minimize_on_close)
        self.min_close_cb = ttk.Checkbutton(
            foot_frame,
            text="Minimize to system tray on close",
            variable=self.min_close_var,
        )
        self.min_close_cb.pack(anchor=tk.W)

    def _on_cores_slider(self, val: str) -> None:
        cores = int(float(val))
        self.cores_label.configure(text=f"{cores} / {os.cpu_count() or 4} Cores")
        self.controller.set_cores(cores)
        self._persist_settings()

    def _on_schedule_toggle(self) -> None:
        self.controller.schedule.enabled = self.sched_var.get()
        self.controller.schedule.start_time = self.start_time_entry.get().strip() or "22:00"
        self.controller.schedule.end_time = self.end_time_entry.get().strip() or "07:00"
        self._persist_settings()

    def _on_autostart_toggle(self) -> None:
        enabled = self.autostart_var.get()
        if enabled:
            ok = self.autostart_mgr.enable(minimized=True)
        else:
            ok = self.autostart_mgr.disable()
        self.desktop_cfg.autostart = enabled
        self._persist_settings()

    def _persist_settings(self) -> None:
        self.desktop_cfg.server_url = self.server_entry.get().strip() or "http://localhost:8000"
        self.desktop_cfg.username = self.user_entry.get().strip() or "volunteer"
        self.desktop_cfg.cores = int(self.cores_var.get())
        self.desktop_cfg.schedule_enabled = self.sched_var.get()
        self.desktop_cfg.schedule_start = self.start_time_entry.get().strip() or "22:00"
        self.desktop_cfg.schedule_end = self.end_time_entry.get().strip() or "07:00"
        self.desktop_cfg.minimize_on_close = self.min_close_var.get()
        save_desktop_config(self.desktop_cfg)

    def _start_crunching(self) -> None:
        username = self.user_entry.get().strip() or "volunteer"
        server = self.server_entry.get().strip() or "http://localhost:8000"
        cached_id = load_cached_worker_id(username)

        try:
            worker_id = register_with_server(server, username, worker_id=cached_id)
            save_cached_worker_id(username, worker_id)
        except Exception as exc:
            messagebox.showerror("Coordinator Error", f"Failed to register with server at {server}:\n{exc}")
            return

        cfg = WorkerConfig(
            server_url=server,
            username=username,
            worker_id=worker_id,
            cores=int(self.cores_var.get()),
        )
        self._on_schedule_toggle()
        self.controller.start(cfg)
        self.toggle_btn.configure(text="Pause Crunching")

    def _toggle_run(self) -> None:
        state = self.controller.get_state()
        if state == WorkerState.STOPPED:
            self._start_crunching()
        elif state == WorkerState.RUNNING:
            self.controller.pause()
            self.toggle_btn.configure(text="Resume Crunching")
        elif state in (WorkerState.PAUSED, WorkerState.SNOOZED, WorkerState.SCHEDULED_IDLE):
            self.controller.resume()
            self.toggle_btn.configure(text="Pause Crunching")

    def _poll_events(self) -> None:
        while not self.controller.event_queue.empty():
            try:
                snap: TelemetrySnapshot = self.controller.event_queue.get_nowait()
                self._update_display(snap)
            except Exception:
                break
        self.root.after(300, self._poll_events)

    def _update_display(self, snap: TelemetrySnapshot) -> None:
        color_map = {
            WorkerState.RUNNING: "#22c55e",
            WorkerState.PAUSED: "#f59e0b",
            WorkerState.SNOOZED: "#f59e0b",
            WorkerState.SCHEDULED_IDLE: "#3b82f6",
            WorkerState.ERROR: "#ef4444",
            WorkerState.STOPPED: "#64748b",
        }
        color = color_map.get(snap.state, "#64748b")
        self.status_canvas.itemconfig(self.status_dot, fill=color)
        self.status_label.configure(text=snap.state.value)

        if snap.problem:
            self.problem_label.configure(text=f"Leased: {snap.problem}")
        self.attempts_label.configure(text=f"Attempts Completed: {snap.total_attempts:,}")
        self.records_label.configure(text=f"World Records Broken: {snap.records_broken}")

        # Update button text
        if snap.state == WorkerState.RUNNING:
            self.toggle_btn.configure(text="Pause Crunching")
        elif snap.state in (WorkerState.PAUSED, WorkerState.SNOOZED, WorkerState.SCHEDULED_IDLE):
            self.toggle_btn.configure(text="Resume Crunching")
        else:
            self.toggle_btn.configure(text="Start Crunching")

        self.tray.update_state(snap.state, tooltip_text=f"{snap.state.value} ({self.cores_var.get()} cores)")

    def _toggle_window(self) -> None:
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.lift()
        else:
            self.root.withdraw()

    def _on_close_window(self) -> None:
        if self.min_close_var.get() and self.tray.is_supported():
            self.root.withdraw()
        else:
            self._on_quit()

    def _on_quit(self) -> None:
        self._persist_settings()
        self.tray.stop()
        self.controller.stop()
        self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Distributed Shape Packing Desktop GUI Client")
    parser.add_argument("--minimized", action="store_true", help="Start application minimized to system tray")
    args = parser.parse_args()

    root = tk.Tk()
    app = WorkerApp(root, start_minimized=args.minimized)
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest tests/test_client_gui.py -v`  
Expected: PASS

---

### Task 5: Export Interfaces & Documentation Updates

**Files:**
- Modify: `src/shape_packing/client/__init__.py`
- Modify: `pyproject.toml` (add `pystray>=0.19.0`)
- Modify: `requirements.txt`
- Modify: `docs/08_distributed_system.md`
- Modify: `README.md`

- [x] **Step 1: Export GUI and Autostart classes in `src/shape_packing/client/__init__.py`**
- [x] **Step 2: Add `pystray>=0.19.0` to dependencies**
- [x] **Step 3: Document desktop GUI and autostart in `README.md` and `docs/08_distributed_system.md`**
- [x] **Step 4: Run full test suite to verify no regressions**

Run: `py -3.14 -m pytest tests/test_client_controller.py tests/test_client_autostart.py tests/test_client_tray.py tests/test_client_gui.py -v`  
Expected: All 4 test files PASS.
