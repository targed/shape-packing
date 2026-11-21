# Desktop System Tray Worker GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide non-technical volunteers with a lightweight desktop application wrapping `native_worker.py` featuring a system tray icon, one-click start/stop, core count slider, and live compute statistics.

**Architecture:** A Python GUI module (`src/shape_packing/client/gui_worker.py`) built using standard library `tkinter` with an optional `pystray` system tray fallback. The GUI executes `run_worker_cycle` inside a background worker thread, communicating status (current problem, attempts completed, best $s$) via a thread-safe message queue.

**Tech Stack:** Python 3, `tkinter`, `threading`, `queue`, `src.shape_packing.client.native_worker`.

**Spec:** `docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md`

## Global Constraints

- Must run using Python standard library `tkinter` with no mandatory external GUI framework dependencies (PyQt / PySide / wxPython).
- Worker thread must run independently of the UI main loop to ensure zero interface stuttering or freeze events.
- On window close or Quit, it must trigger a graceful shutdown, completing in-flight search and flushing heartbeats to the coordinator.

---

### Task 1: GUI State Manager & Background Worker Thread

**Files:**
- Create: `src/shape_packing/client/gui_controller.py`
- Test: `tests/test_gui_controller.py`

**Interfaces:**
- Consumes: `src/shape_packing/client/native_worker.py`
- Produces: `WorkerGUIController` class managing background thread lifecycle and event callbacks.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gui_controller.py
import time
import pytest
from unittest.mock import MagicMock
from src.shape_packing.client.gui_controller import WorkerGUIController
from src.shape_packing.client.native_worker import WorkerConfig

def test_controller_start_and_stop():
    mock_cycle = MagicMock(return_value={"status": "completed", "attempts_completed": 100})
    controller = WorkerGUIController(cycle_fn=mock_cycle)

    config = WorkerConfig(server_url="http://localhost:8000", username="gui_tester", cores=1)
    controller.start(config)
    assert controller.is_running() is True

    time.sleep(0.15)
    controller.stop()
    assert controller.is_running() is False
    assert mock_cycle.call_count >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gui_controller.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# src/shape_packing/client/gui_controller.py
from __future__ import annotations
import threading
import time
from typing import Callable, Optional
from .native_worker import WorkerConfig, run_worker_cycle, flush_in_flight_heartbeat

class WorkerGUIController:
    """Manages background compute thread execution for desktop GUI."""

    def __init__(self, cycle_fn: Optional[Callable] = None):
        self._cycle_fn = cycle_fn or run_worker_cycle
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._config: Optional[WorkerConfig] = None
        self.on_status_update: Optional[Callable[[str, int], None]] = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, config: WorkerConfig) -> None:
        if self.is_running():
            return
        self._config = config
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._config:
            flush_in_flight_heartbeat(self._config)

    def _worker_loop(self) -> None:
        total_attempts = 0
        while not self._stop_event.is_set():
            try:
                res = self._cycle_fn(self._config, stop_event=self._stop_event)
                attempts = res.get("attempts_completed", 0)
                total_attempts += attempts
                if self.on_status_update:
                    self.on_status_update("Running", total_attempts)
                time.sleep(0.05)
            except Exception as e:
                if self.on_status_update:
                    self.on_status_update(f"Error: {e}", total_attempts)
                time.sleep(2.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gui_controller.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/shape_packing/client/gui_controller.py tests/test_gui_controller.py
git commit -m "feat(client): implement GUI worker thread lifecycle controller"
```

---

### Task 2: Tkinter Desktop Application UI

**Files:**
- Create: `src/shape_packing/client/gui_worker.py`

**Interfaces:**
- Consumes: `src/shape_packing/client/gui_controller.py`
- Produces: Executable desktop application window with server URL, core slider, start/stop button, and system tray support.

- [ ] **Step 1: Write Tkinter application in `src/shape_packing/client/gui_worker.py`**

```python
# src/shape_packing/client/gui_worker.py
from __future__ import annotations
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from .native_worker import (
    WorkerConfig,
    load_cached_worker_id,
    save_cached_worker_id,
    register_with_server,
)
from .gui_controller import WorkerGUIController

class WorkerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Distributed Shape Packing")
        self.root.geometry("420x360")
        self.root.resizable(False, False)

        self.controller = WorkerGUIController()
        self.controller.on_status_update = self._on_status_update

        # Layout
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Distributed Shape Packing", font=("Helvetica", 14, "bold")).pack(pady=4)
        ttk.Label(frame, text="Volunteer Compute Node", font=("Helvetica", 9), foreground="#64748b").pack(pady=(0, 12))

        # Inputs
        ttk.Label(frame, text="Coordinator Server:").pack(anchor=tk.W)
        self.server_entry = ttk.Entry(frame)
        self.server_entry.insert(0, "http://localhost:8000")
        self.server_entry.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(frame, text="Username:").pack(anchor=tk.W)
        self.user_entry = ttk.Entry(frame)
        self.user_entry.insert(0, "volunteer")
        self.user_entry.pack(fill=tk.X, pady=(0, 8))

        # Cores Slider
        max_cores = os.cpu_count() or 4
        ttk.Label(frame, text="Allocated Cores:").pack(anchor=tk.W)
        self.cores_var = tk.IntVar(value=min(4, max_cores))
        self.cores_scale = ttk.Scale(frame, from_=1, to=max_cores, variable=self.cores_var, orient=tk.HORIZONTAL)
        self.cores_scale.pack(fill=tk.X)
        self.cores_label = ttk.Label(frame, text=f"{self.cores_var.get()} Cores")
        self.cores_label.pack(anchor=tk.E, pady=(0, 12))
        self.cores_scale.configure(command=lambda v: self.cores_label.configure(text=f"{int(float(v))} Cores"))

        # Buttons
        self.toggle_btn = ttk.Button(frame, text="Start Crunching", command=self._toggle_run)
        self.toggle_btn.pack(fill=tk.X, pady=8)

        # Status
        self.status_label = ttk.Label(frame, text="Status: Idle", foreground="#475569")
        self.status_label.pack(pady=4)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _toggle_run(self):
        if self.controller.is_running():
            self.controller.stop()
            self.toggle_btn.configure(text="Start Crunching")
            self.status_label.configure(text="Status: Stopped")
        else:
            username = self.user_entry.get().strip() or "volunteer"
            server = self.server_entry.get().strip() or "http://localhost:8000"
            cached_id = load_cached_worker_id(username)
            try:
                worker_id = register_with_server(server, username, worker_id=cached_id)
                save_cached_worker_id(username, worker_id)
            except Exception as e:
                messagebox.showerror("Connection Error", f"Failed to register with coordinator:\n{e}")
                return

            config = WorkerConfig(
                server_url=server,
                username=username,
                worker_id=worker_id,
                cores=int(self.cores_var.get()),
            )
            self.controller.start(config)
            self.toggle_btn.configure(text="Stop Crunching")

    def _on_status_update(self, status: str, attempts: int):
        self.root.after(0, lambda: self.status_label.configure(text=f"Status: {status} ({attempts:,} attempts)"))

    def _on_close(self):
        if self.controller.is_running():
            self.controller.stop()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = WorkerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add src/shape_packing/client/gui_worker.py
git commit -m "feat(client): implement desktop GUI worker application with Tkinter"
```
