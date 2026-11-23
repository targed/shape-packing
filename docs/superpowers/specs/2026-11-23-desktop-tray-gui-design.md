# Desktop System Tray GUI & Background Service Design

**Status:** Approved  
**Date:** 2026-11-23  
**Target:** Distributed Shape Packing Volunteer Computing Platform  
**Component:** `src.shape_packing.client`

---

## 1. Executive Summary

This specification defines the desktop GUI and background daemon for the **Distributed Shape Packing** volunteer computing client. It provides non-technical volunteers and casual contributors with a lightweight, cross-platform desktop application that runs quietly in the system tray, automatically starts on boot if enabled, respects user-configured CPU core limits, supports scheduled crunching windows (e.g. night crunching), and provides quick pause and snooze options.

---

## 2. Requirements & Constraints

### 2.1 Functional Requirements
1. **System Tray Integration**:
   - Dockable into Windows Taskbar notification area, macOS Menu Bar, and Linux System Tray using `pystray`.
   - Dynamic icon reflecting current state:
     - 🟢 **Green**: Actively computing.
     - 🟡 **Yellow**: Manually paused or snoozed.
     - 🔵 **Blue**: Scheduled idle (outside active time window).
     - 🔴 **Red**: Connection error (re-attempting).
     - ⚫ **Gray**: Stopped.
   - Right-click tray menu with status summary, Pause/Resume, Snooze presets (30m, 1h, 2h), Show Window, and Quit.
2. **Desktop Control Window**:
   - Built with Python standard library `tkinter` with zero heavy GUI dependencies (no PyQt/PySide/wxPython).
   - CPU core slider from 1 to `os.cpu_count()`.
   - Start / Pause button with instant state reflection.
   - Snooze dropdown / buttons (30m, 1h, 2h, custom).
   - Active time window restriction (e.g. `22:00` to `07:00` with midnight-crossing support).
   - Live telemetry: Leased problem ID, $N$, current best $s$, attempts completed, and records broken.
3. **Cross-Platform Auto-Start & Daemon Mode**:
   - One-click checkbox: `[x] Start automatically when I log in (minimized to tray)`.
   - Zero administrative/root elevation required.
   - **Windows**: `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run` key with `pythonw.exe`.
   - **macOS**: `~/Library/LaunchAgents/com.shapepacking.worker.plist` LaunchAgent.
   - **Linux**: `~/.config/autostart/shape-packing-worker.desktop` XDG desktop entry.
   - CLI subcommands for shell scripts, cron jobs, and headless machines:
     `python -m src.shape_packing.client.autostart enable/disable/status`.
4. **Resilience & Graceful Exit**:
   - Closing the window minimizes to tray if `minimize_on_close` is active.
   - Explicit Quit flushes in-flight heartbeats, deregisters the worker from the coordinator, and shuts down threads cleanly.

---

## 3. System Architecture & Component Design

```text
┌────────────────────────────────────────────────────────┐
│                      User Interface                     │
│  ┌───────────────────────┐   ┌──────────────────────┐  │
│  │   WorkerApp (Tkinter) │   │  TrayManager (pystray)│  │
│  └───────────┬───────────┘   └──────────┬───────────┘  │
└──────────────┼──────────────────────────┼──────────────┘
               │                          │
               ▼                          ▼
┌────────────────────────────────────────────────────────┐
│        WorkerController (Thread-safe State & Events)   │
│  - State Machine: STOPPED, RUNNING, PAUSED, SNOOZED,   │
│                   SCHEDULED_IDLE, ERROR                │
│  - Time Range Validator & Snooze Countdown Timer       │
│  - Configuration & Worker ID Persistence               │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│        Compute Daemon (native_worker.py)               │
│  - Runs Rayon solver in background worker thread       │
│  - Leases problems, tracks heartbeats, submits records │
└────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────┴─────────────────────────────┐
│        Platform Autostart Manager (autostart.py)       │
│  - Windows: Registry HKCU Run key                      │
│  - macOS: ~/Library/LaunchAgents plist                 │
│  - Linux: ~/.config/autostart .desktop entry           │
│  - CLI: python -m ...autostart enable/disable/status   │
└────────────────────────────────────────────────────────┘
```

### 3.1 Module Manifest
- **`src/shape_packing/client/controller.py`**:
  Manages worker thread, schedule evaluation, snooze timers, and thread-safe UI message queues.
- **`src/shape_packing/client/autostart.py`**:
  Encapsulates platform-specific user-level startup installation, removal, and queries.
- **`src/shape_packing/client/tray.py`**:
  Generates in-memory dynamic status icons via Pillow and manages the `pystray.Icon` lifecycle.
- **`src/shape_packing/client/gui.py`**:
  Implements the `tkinter` control window and connects to `WorkerController`.

---

## 4. State Machine & Scheduling Logic

### 4.1 State Transitions

```text
       ┌───────────┐
       │  STOPPED  │◄─────────────────────────────┐
       └─────┬─────┘                              │
             │ Start clicked                      │
             ▼                                    │ Stop clicked / Quit
    ┌─────────────────┐  Schedule Closed   ┌──────┴──────────┐
    │     RUNNING     ├───────────────────►│ SCHEDULED_IDLE  │
    └────┬───────┬────┘◄───────────────────┴─────────────────┘
         │       │       Schedule Opened
         │       │ Snooze clicked
         │       ▼
         │  ┌─────────┐   Timer Expired
         │  │ SNOOZED ├───────────────────► (RUNNING or SCHEDULED_IDLE)
         │  └────┬────┘
         │       │
         ▼       ▼ Pause clicked
       ┌───────────┐
       │  PAUSED   │
       └─────┬─────┘
             │ Resume clicked
             ▼
     (RUNNING or SCHEDULED_IDLE)
```

### 4.2 Time Window Evaluation
A schedule range is specified as two 24-hour strings: `start_time` (e.g. `"22:00"`) and `end_time` (e.g. `"07:00"`).

```python
def is_within_schedule(now_time: datetime.time, start: datetime.time, end: datetime.time) -> bool:
    if start <= end:
        return start <= now_time < end
    else:  # Crosses midnight (e.g. 22:00 to 07:00)
        return now_time >= start or now_time < end
```

---

## 5. Configuration Schema (`~/.shape_packing_worker.json`)

```json
{
  "username": "volunteer_user",
  "worker_id": "c1f7a28e-5b12-4f89-8d19-913a85b9b212",
  "server_url": "http://localhost:8000",
  "cores": 4,
  "autostart": true,
  "start_minimized": true,
  "minimize_on_close": true,
  "schedule_enabled": false,
  "schedule_start": "22:00",
  "schedule_end": "07:00"
}
```

---

## 6. Autostart Mechanism Details

1. **Windows**:
   - Module: Standard library `winreg`.
   - Key: `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`.
   - Entry: `"ShapePackingWorker" = '"<pythonw_path>" -m src.shape_packing.client.gui --minimized'`.
2. **macOS**:
   - Path: `~/Library/LaunchAgents/com.shapepacking.worker.plist`.
   - Uses `launchctl load -w` and `launchctl unload -w`.
3. **Linux**:
   - Path: `~/.config/autostart/shape-packing-worker.desktop`.
   - Exec: `python3 -m src.shape_packing.client.gui --minimized`.

---

## 7. Testing Strategy

1. **Unit Tests (`tests/test_client_controller.py`)**:
   - Test `WorkerController` start, pause, resume, snooze, and stop transitions.
   - Test midnight-crossing schedule evaluations.
   - Verify thread-safe event queue delivery without deadlocks.
2. **Autostart Tests (`tests/test_client_autostart.py`)**:
   - Test Windows registry mocks, macOS plist generation, and Linux desktop file generation.
   - Test CLI enable/disable/status command output parsing.
3. **GUI Smoke & Headless Fallback Tests (`tests/test_client_gui.py`)**:
   - Test app initialization in headless virtual frame / mock Tk environment.
   - Test graceful fallback when system tray is unavailable.
