from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
import queue
import sys
import threading
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
    server_url: str = "https://shape-packing-ggd4d5e8c2ctggam.eastus-01.azurewebsites.net"
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
                return DesktopConfig(
                    **{
                        k: v
                        for k, v in data.items()
                        if k in DesktopConfig.__annotations__
                    }
                )
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
            if self.tray.is_active():
                self.root.withdraw()
            self._start_crunching()

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        # Header status bar
        header_frame = ttk.Frame(container)
        header_frame.pack(fill=tk.X, pady=(0, 12))

        self.status_canvas = tk.Canvas(
            header_frame, width=16, height=16, highlightthickness=0
        )
        self.status_canvas.pack(side=tk.LEFT, padx=(0, 6))
        self.status_dot = self.status_canvas.create_oval(
            2, 2, 14, 14, fill="#64748b", outline=""
        )

        self.status_label = ttk.Label(
            header_frame, text="STOPPED", font=("Helvetica", 11, "bold")
        )
        self.status_label.pack(side=tk.LEFT)

        self.problem_label = ttk.Label(
            header_frame, text="", foreground="#64748b", font=("Helvetica", 9)
        )
        self.problem_label.pack(side=tk.RIGHT)

        # Connection Card
        conn_frame = ttk.LabelFrame(container, text="Coordinator Connection", padding=8)
        conn_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(conn_frame, text="Server:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.server_entry = ttk.Entry(conn_frame)
        self.server_entry.insert(0, self.desktop_cfg.server_url)
        self.server_entry.grid(row=0, column=1, sticky=tk.EW, padx=(6, 0), pady=2)

        ttk.Label(conn_frame, text="Username:").grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
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
        self.cores_label = ttk.Label(
            core_header, text=f"{self.cores_var.get()} / {max_cores} Cores"
        )
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

        self.toggle_btn = ttk.Button(
            btn_row, text="Start Crunching", command=self._toggle_run
        )
        self.toggle_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.snooze_btn = ttk.Menubutton(btn_row, text="Snooze 30m ▼")
        snooze_menu = tk.Menu(self.snooze_btn, tearoff=False)
        snooze_menu.add_command(
            label="Snooze 30 Minutes", command=lambda: self.controller.snooze(minutes=30)
        )
        snooze_menu.add_command(
            label="Snooze 1 Hour", command=lambda: self.controller.snooze(minutes=60)
        )
        snooze_menu.add_command(
            label="Snooze 2 Hours", command=lambda: self.controller.snooze(minutes=120)
        )
        self.snooze_btn["menu"] = snooze_menu
        self.snooze_btn.pack(side=tk.RIGHT)

        # Schedule row
        sched_row = ttk.Frame(ctrl_frame)
        sched_row.pack(fill=tk.X)
        self.sched_var = tk.BooleanVar(value=self.desktop_cfg.schedule_enabled)
        self.sched_cb = ttk.Checkbutton(
            sched_row,
            text="Active hours only:",
            variable=self.sched_var,
            command=self._on_schedule_toggle,
        )
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

        self.records_label = ttk.Label(
            telem_frame,
            text="World Records Broken: 0",
            font=("Helvetica", 9, "bold"),
            foreground="#059669",
        )
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
        self.controller.schedule.start_time = (
            self.start_time_entry.get().strip() or "22:00"
        )
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
        self.desktop_cfg.server_url = (
            self.server_entry.get().strip() or "https://shape-packing-ggd4d5e8c2ctggam.eastus-01.azurewebsites.net"
        )
        self.desktop_cfg.username = self.user_entry.get().strip() or "volunteer"
        self.desktop_cfg.cores = int(self.cores_var.get())
        self.desktop_cfg.schedule_enabled = self.sched_var.get()
        self.desktop_cfg.schedule_start = self.start_time_entry.get().strip() or "22:00"
        self.desktop_cfg.schedule_end = self.end_time_entry.get().strip() or "07:00"
        self.desktop_cfg.minimize_on_close = self.min_close_var.get()
        save_desktop_config(self.desktop_cfg)

    def _start_crunching(self) -> None:
        username = self.user_entry.get().strip() or "volunteer"
        server = self.server_entry.get().strip() or "https://shape-packing-ggd4d5e8c2ctggam.eastus-01.azurewebsites.net"
        self.toggle_btn.configure(text="Connecting...", state=tk.DISABLED)
        self.status_label.configure(text="CONNECTING")
        self.status_canvas.itemconfig(self.status_dot, fill="#3b82f6")

        def _bg_register() -> None:
            cached_id = load_cached_worker_id(username)
            try:
                worker_id = register_with_server(
                    server, username, worker_id=cached_id, timeout=5.0
                )
                save_cached_worker_id(username, worker_id)
                cfg = WorkerConfig(
                    server_url=server,
                    username=username,
                    worker_id=worker_id,
                    cores=int(self.cores_var.get()),
                )
                self.root.after(0, lambda: self._on_register_success(cfg))
            except Exception as exc:
                err_str = str(exc)
                self.root.after(0, lambda: self._on_register_error(server, err_str))

        threading.Thread(
            target=_bg_register, daemon=True, name="WorkerRegisterThread"
        ).start()

    def _on_register_success(self, cfg: WorkerConfig) -> None:
        self.toggle_btn.configure(text="Pause Crunching", state=tk.NORMAL)
        self._on_schedule_toggle()
        self.controller.start(cfg)

    def _on_register_error(self, server: str, error_msg: str) -> None:
        self.toggle_btn.configure(text="Start Crunching", state=tk.NORMAL)
        self.status_label.configure(text="STOPPED")
        self.status_canvas.itemconfig(self.status_dot, fill="#64748b")
        messagebox.showerror(
            "Coordinator Error",
            f"Failed to connect to coordinator at {server}:\n{error_msg}\n\nPlease check the URL or ensure the server is running.",
        )

    def _toggle_run(self) -> None:
        state = self.controller.get_state()
        if state == WorkerState.STOPPED:
            self._start_crunching()
        elif state == WorkerState.RUNNING:
            self.controller.pause()
            self.toggle_btn.configure(text="Resume Crunching")
        elif state in (
            WorkerState.PAUSED,
            WorkerState.SNOOZED,
            WorkerState.SCHEDULED_IDLE,
        ):
            self.controller.resume()
            self.toggle_btn.configure(text="Pause Crunching")

    def _poll_events(self) -> None:
        try:
            while not self.controller.event_queue.empty():
                try:
                    snap: TelemetrySnapshot = self.controller.event_queue.get_nowait()
                    self._update_display(snap)
                except queue.Empty:
                    break
        except Exception:
            pass
        finally:
            try:
                self.root.after(250, self._poll_events)
            except Exception:
                pass

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
        self.attempts_label.configure(
            text=f"Attempts Completed: {snap.total_attempts:,}"
        )
        self.records_label.configure(text=f"World Records Broken: {snap.records_broken}")

        # Update button text
        if snap.state == WorkerState.RUNNING:
            self.toggle_btn.configure(text="Pause Crunching")
        elif snap.state in (
            WorkerState.PAUSED,
            WorkerState.SNOOZED,
            WorkerState.SCHEDULED_IDLE,
        ):
            self.toggle_btn.configure(text="Resume Crunching")
        else:
            self.toggle_btn.configure(text="Start Crunching")

        self.tray.update_state(
            snap.state,
            tooltip_text=f"{snap.state.value} ({self.cores_var.get()} cores)",
        )

    def _toggle_window(self) -> None:
        def _do_toggle():
            if self.root.state() == "withdrawn":
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
            else:
                self.root.withdraw()

        self.root.after(0, _do_toggle)

    def _on_close_window(self) -> None:
        if self.min_close_var.get() and self.tray.is_active():
            self.root.withdraw()
        else:
            self._on_quit()

    def _on_quit(self) -> None:
        def _do_quit():
            self._persist_settings()
            self.tray.stop()
            self.controller.stop()
            self.root.destroy()

        self.root.after(0, _do_quit)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Distributed Shape Packing Desktop GUI Client"
    )
    parser.add_argument(
        "--minimized",
        "--minimize",
        "--minamize",
        dest="minimized",
        action="store_true",
        help="Start application minimized to system tray",
    )
    args = parser.parse_args()

    root = tk.Tk()
    app = WorkerApp(root, start_minimized=args.minimized)
    root.mainloop()


if __name__ == "__main__":
    main()
