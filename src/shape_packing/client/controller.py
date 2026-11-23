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

            self._thread = threading.Thread(
                target=self._run_loop, daemon=True, name="WorkerControllerLoop"
            )
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
            self._status_message = (
                f"Snoozed for {int(duration / 60) if duration >= 60 else duration}m"
            )
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
                    if not is_within_schedule(
                        now, self.schedule.start, self.schedule.end
                    ):
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
