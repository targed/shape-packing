# Milestone 4 Investigation & Lifecycle Execution Blueprint: Native Worker Daemon

## 1. Observation

Direct observations from examining the codebase, specifications, and system environment:

### 1.1 Solver Interface Contracts (`src/shape_packing/solver_interface.py`)
- In `_run_pyo3_solver` (lines 71-98):
  ```python
  return {
      "success": True,
      "score": final_metric,
      "S": S,
      "values": values,
      "backend": "pyo3",
      "output": f"Final side length: {final_metric}",
  }
  ```
- In `_run_rust_cli_solver` (lines 198-203):
  ```python
  return {
      "success": True,
      "score": score,
      "values": values,
      "backend": "cli",
      "output": stdout,
  }
  ```
- In `run_solver` (lines 218-230):
  ```python
  def run_solver(
      n_shapes: int,
      inner_shape: str,
      container_shape: str,
      attempts: int = 1000,
      tolerance: float = 1e-30,
      finalstep: float = 0.0001,
      time_limit: Optional[float] = None,
      initial_positions: Optional[List[float]] = None,
      target_s: Optional[float] = None,
      solution_file: Optional[str] = None,
      no_build: bool = True,
  ) -> Dict[str, Any]:
  ```
- **Crucial field distinction**: `run_solver` returns `"score"` (and optionally `"S"` in PyO3), whereas `docs/superpowers/plans/2026-11-20-distributed-shape-packing.md` Task 4 mock (line 862) uses `"best_s"`. The worker must normalize this with:
  `metric_s = result.get("best_s", result.get("score"))`. Coordinates are returned under `"values"` (a flat list of $3 \cdot N$ floats `[x0, y0, theta0, ...]`).

### 1.2 Work Lease & Coordinator Contracts (`src/shape_packing/server/app.py` & `scheduler.py`)
- `assign_work` in `scheduler.py` (lines 220-229) returns:
  ```python
  {
      "work_id": work_id,
      "problem": prob_dict["id"],
      "inner_token": prob_dict["inner_token"],
      "container_token": prob_dict["container_token"],
      "n": int(prob_dict["n"]),
      "target_s": float(target_s),
      "recommended_attempts": int(recommended_attempts),
      "lease_seconds": int(ls),
  }
  ```
- `GET /api/v1/work` in `app.py` (line 150) adds `"timeout_seconds": assignment["lease_seconds"]`.
  When no work is available, it returns HTTP 204 No Content (line 148: `Response(status_code=status.HTTP_204_NO_CONTENT)`).
- `POST /api/v1/solutions` in `app.py` (lines 46-51, 154-285):
  Accepts `{"work_id": Optional[str], "worker_id": str, "problem": str, "s": float, "coordinates": List[float]}`.
  Performs in-process geometric SAT verification (`verify_solution`). Valid improvements return HTTP 200 with `{"status": "accepted", "verified": True, "is_new_record": True, "metric_s": ...}`.
- `POST /api/v1/heartbeat` in `app.py` (lines 54-59, 287-324) and `scheduler.py` (lines 304-340):
  Accepts `{"worker_id": str, "work_id": str, "attempts_completed": int, "best_local_s": Optional[float]}`.
  `scheduler.py:record_heartbeat` increments attempts incrementally:
  `total_attempts = workers.total_attempts + excluded.total_attempts` and `problems.total_attempts = total_attempts + attempts`.
  **Heartbeat semantics**: `attempts_completed` represents incremental attempts completed during this heartbeat. Passing `0` acts as a pure keep-alive ping that updates `workers.last_seen_at = CURRENT_TIMESTAMP` without modifying attempt totals.

### 1.3 Operating System Scheduling & Idle Priority
- Direct command test execution:
  `python3 -c "import os; print('has nice:', hasattr(os, 'nice'), 'has setpriority:', hasattr(os, 'setpriority'))"`
  Returned: `has nice: True has setpriority: True`.
  Setting `os.setpriority(os.PRIO_PROCESS, 0, 19)` sets process nice to 19 directly without relative increment bugs.
- On Windows: `ctypes.windll.kernel32.SetPriorityClass` with `IDLE_PRIORITY_CLASS = 0x00000040` sets the process to idle class without external dependencies.

### 1.4 Signal Handling Rules
- In Python, `signal.signal` must be called on the main interpreter thread (`ValueError: signal only works in main thread of the main interpreter`).
- Handler cannot perform blocking I/O; it must set a `threading.Event` to trigger shutdown in the execution loop.

---

## 2. Logic Chain

1. **Solver Invocation Logic**:
   - From Observation 1.1, the worker must support an injected `solver_fn` (for unit tests / mock verification) and default to `shape_packing.solver_interface.run_solver`.
   - From Observation 1.1, solver outputs use `"score"` in production and `"best_s"` in tests. The client must extract `metric_s = result.get("best_s") if "best_s" in result else result.get("score")`, falling back to `"final_metric"` or `"S"`.
   - If `result.get("success")` is True, `metric_s` is a finite positive number, and `metric_s < target_s`, the worker flags `found_improvement = True` and submits to `/api/v1/solutions` with payload `{"work_id": work["work_id"], "worker_id": config.worker_id, "problem": work["problem"], "s": metric_s, "coordinates": values}`.

2. **OS Priority Scheduling Logic**:
   - From Observation 1.3, volunteer computing requires background idle CPU execution so regular user activities remain unaffected.
   - On POSIX, `os.setpriority(os.PRIO_PROCESS, 0, 19)` is preferred over `os.nice(19)` because `os.nice` adds an offset (calling it twice increases nice beyond 19 or raises `OSError`).
   - On Windows, `ctypes.windll.kernel32.SetPriorityClass(handle, 0x00000040)` achieves identical idle scheduling.
   - All priority changes must be wrapped in `try/except Exception` to handle unprivileged containers, mobile OSes, or restricted environments without crashing.

3. **Heartbeat Reporting Thread Logic**:
   - From Observation 1.2, work assignments have lease timeouts (default 300s). If a solver runs for minutes without contacting the server, the lease will expire.
   - From Observation 1.2, `record_heartbeat` handles attempts incrementally. Therefore:
     - Periodic heartbeats sent *while* the solver is running should either report newly completed chunk attempts or send `attempts_completed = 0` as a keepalive.
     - A dedicated `HeartbeatReporter` background daemon thread protects `_unreported_attempts` with a `threading.Lock()`.
     - When `flush()` executes, it atomically extracts `attempts_to_send`, sends `/api/v1/heartbeat`, and if the network call fails, re-credits the attempts back to `_unreported_attempts` to prevent lost compute.
     - On cycle completion or shutdown, a final flush reports all remaining attempts before the cycle terminates.

4. **Graceful Shutdown Logic**:
   - From Observation 1.4, SIGINT (`Ctrl+C`) and SIGTERM must be intercepted on the main thread and set a `stop_event: threading.Event`.
   - Signal registration must catch `(ValueError, AttributeError)` so that importing or invoking `native_worker` in secondary threads (e.g. within pytest fixtures) does not raise `ValueError`.
   - While idle or backing off, `stop_event.wait(timeout=delay)` unblocks immediately on signal arrival, avoiding unresponsive sleep delays.
   - During compute execution, the worker completes the active chunk/batch, immediately flushes in-flight attempts and solutions to coordinator endpoints, and exits cleanly.

5. **Main Worker Cycle Design**:
   - Function signature:
     ```python
     def run_worker_cycle(
         config: WorkerConfig,
         stop_event: Optional[threading.Event] = None,
         max_cycles: Optional[int] = 1,
         solver_fn: Optional[Callable] = None,
         request_fn: Optional[Callable] = None,
     ) -> Dict[str, Any]
     ```
   - When `max_cycles == 1` (default for unit testing and Task 4 step 1):
     Executes a single work unit and returns `{"status": "completed", "attempts_completed": N, "found_improvement": bool}`.
   - When `max_cycles is None` or `> 1` (daemon mode):
     Loops while `not stop_event.is_set()` and `(max_cycles is None or cycles_run < max_cycles)`, leasing work, running solver, and handling idle 204 backoff.

---

## 3. Caveats

- **Rust binary build dependency**: `solver_interface.py` tries to load PyO3 or the compiled CLI binary in `packer_rs/target/release`. If neither is compiled, `run_solver` returns `{"success": False, "error": ...}`. The native worker client handles this failure cleanly and continues heartbeating/backoff.
- **Lease expiration semantics**: In `scheduler.py`, `record_heartbeat` updates worker `last_seen_at` and records attempts, but does not extend `active_leases.expires_at`. Therefore, recommended attempts per lease should not exceed what the worker can finish within `lease_seconds`.
- **Subprocess signals**: If `packer_rs` is run via subprocess CLI, `SIGINT` from terminal goes to the entire process group. The Python worker must ensure its signal handler runs before the subprocess is killed, or let the subprocess exit and flush attempts in `finally:`.

---

## 4. Conclusion & Execution Blueprint

### 4.1 Process Priority Implementation (`set_process_idle_priority`)
```python
def set_process_idle_priority() -> bool:
    """
    Set current process to idle/lowest background OS scheduling priority.
    
    POSIX (Linux, macOS):
        Sets nice to 19 via os.setpriority(os.PRIO_PROCESS, 0, 19) or os.nice(19).
    Windows:
        Sets priority class to IDLE_PRIORITY_CLASS (0x00000040) via ctypes.
    
    Returns:
        bool: True if idle priority was successfully applied, False on fallback.
    """
    import sys
    if sys.platform == "win32":
        try:
            import ctypes
            IDLE_PRIORITY_CLASS = 0x00000040
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            res = ctypes.windll.kernel32.SetPriorityClass(handle, IDLE_PRIORITY_CLASS)
            return bool(res)
        except Exception:
            return False
    else:
        try:
            if hasattr(os, "setpriority") and hasattr(os, "PRIO_PROCESS"):
                os.setpriority(os.PRIO_PROCESS, 0, 19)
                return True
            elif hasattr(os, "nice"):
                os.nice(19)
                return True
        except (OSError, PermissionError, AttributeError):
            return False
    return False
```

### 4.2 Periodic Heartbeat Reporter Thread (`HeartbeatReporter`)
```python
class HeartbeatReporter:
    """
    Thread-safe background daemon that flushes attempt counts and keeps leases alive.
    """
    def __init__(
        self,
        server_url: str,
        worker_id: str,
        work_id: str,
        interval_seconds: float = 30.0,
        request_fn: Optional[Callable] = None,
    ):
        self.server_url = server_url.rstrip("/")
        self.worker_id = worker_id
        self.work_id = work_id
        self.interval_seconds = interval_seconds
        self.request_fn = request_fn or send_request

        self._lock = threading.Lock()
        self._unreported_attempts = 0
        self._best_local_s: Optional[float] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="HeartbeatReporter")
        self._thread.start()

    def record_attempts(self, count: int, best_s: Optional[float] = None) -> None:
        with self._lock:
            self._unreported_attempts += count
            if best_s is not None:
                if self._best_local_s is None or best_s < self._best_local_s:
                    self._best_local_s = best_s

    def flush(self, force: bool = False) -> bool:
        with self._lock:
            attempts_to_send = self._unreported_attempts
            best_s_to_send = self._best_local_s
            self._unreported_attempts = 0

        if not force and attempts_to_send == 0:
            return True

        url = f"{self.server_url}/api/v1/heartbeat"
        payload = {
            "worker_id": self.worker_id,
            "work_id": self.work_id,
            "attempts_completed": attempts_to_send,
            "best_local_s": best_s_to_send,
        }
        try:
            self.request_fn(url, method="POST", payload=payload)
            return True
        except Exception:
            # Re-credit attempts if network call failed so they can be retried on next flush
            with self._lock:
                self._unreported_attempts += attempts_to_send
            return False

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self.flush(force=True)

    def _run(self) -> None:
        while not self._stop_event.wait(timeout=self.interval_seconds):
            self.flush(force=True)
```

### 4.3 Signal Handling Registration
```python
_GLOBAL_STOP_EVENT = threading.Event()

def setup_signal_handlers(stop_event: Optional[threading.Event] = None) -> threading.Event:
    """Register SIGINT and SIGTERM handlers to set the provided or global stop_event."""
    ev = stop_event or _GLOBAL_STOP_EVENT

    def _handler(sig, frame):
        sig_name = "SIGINT" if sig == signal.SIGINT else ("SIGTERM" if sig == signal.SIGTERM else str(sig))
        print(f"\n[Worker] Caught {sig_name}. Finishing in-flight batch and flushing heartbeats...", file=sys.stderr)
        ev.set()

    try:
        signal.signal(signal.SIGINT, _handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _handler)
    except (ValueError, AttributeError):
        # Graceful fallback when invoked from secondary threads in test environments
        pass

    return ev
```

### 4.4 Main Worker Execution Cycle (`run_worker_cycle`)
```python
def run_worker_cycle(
    config: WorkerConfig,
    stop_event: Optional[threading.Event] = None,
    max_cycles: Optional[int] = 1,
    solver_fn: Optional[Callable] = None,
    request_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Execute work leasing, solver batches, solution submission, and heartbeats.
    
    If max_cycles == 1 (default):
        Runs a single work unit and returns the result dict.
    If max_cycles is None or > 1:
        Runs continuous loop until stop_event is set or max_cycles reached.
    """
    ev = stop_event or _GLOBAL_STOP_EVENT
    req = request_fn or send_request

    cycles_completed = 0
    total_attempts = 0
    improvements_found = 0
    last_cycle_result: Dict[str, Any] = {"status": "idle", "attempts_completed": 0, "found_improvement": False}

    while not ev.is_set():
        if max_cycles is not None and cycles_completed >= max_cycles:
            break

        work_url = f"{config.server_url.rstrip('/')}/api/v1/work?worker_id={config.worker_id}&cores={config.cores}"
        try:
            work = req(work_url, method="GET")
        except Exception as e:
            if max_cycles == 1:
                return {"status": "error", "error": str(e), "attempts_completed": 0, "found_improvement": False}
            ev.wait(timeout=5.0)
            continue

        if not work:
            last_cycle_result = {"status": "idle", "attempts_completed": 0, "found_improvement": False}
            if max_cycles == 1:
                return last_cycle_result
            ev.wait(timeout=config.poll_interval if hasattr(config, "poll_interval") else 2.0)
            continue

        # Execute single work unit
        work_id = work["work_id"]
        problem = work["problem"]
        target_s = float(work["target_s"])
        attempts = int(work.get("recommended_attempts", 2000))
        inner_token = str(work["inner_token"])
        container_token = str(work["container_token"])
        n = int(work["n"])

        reporter = HeartbeatReporter(
            server_url=config.server_url,
            worker_id=config.worker_id,
            work_id=work_id,
            interval_seconds=getattr(config, "heartbeat_interval", 30.0),
            request_fn=req,
        )
        reporter.start()

        try:
            if solver_fn:
                solver_res = solver_fn(
                    inner_shape=inner_token,
                    container_shape=container_token,
                    n=n,
                    attempts=attempts,
                    target_s=target_s,
                )
            else:
                from ..solver_interface import run_solver
                solver_res = run_solver(
                    n_shapes=n,
                    inner_shape=inner_token,
                    container_shape=container_token,
                    attempts=attempts,
                    target_s=target_s,
                )

            # Normalize metrics and coordinates
            metric_s = solver_res.get("best_s")
            if metric_s is None:
                metric_s = solver_res.get("score")
            if metric_s is None:
                metric_s = solver_res.get("final_metric")
            if metric_s is None and "S" in solver_res:
                metric_s = solver_res.get("S")

            coords = solver_res.get("values")
            if coords is None:
                coords = solver_res.get("coordinates", [])

            found_improvement = False
            if (
                solver_res.get("success")
                and metric_s is not None
                and not math.isnan(metric_s)
                and metric_s < target_s
            ):
                found_improvement = True
                improvements_found += 1
                sol_url = f"{config.server_url.rstrip('/')}/api/v1/solutions"
                req(
                    sol_url,
                    method="POST",
                    payload={
                        "work_id": work_id,
                        "worker_id": config.worker_id,
                        "problem": problem,
                        "s": float(metric_s),
                        "coordinates": [float(c) for c in coords],
                    },
                )

            reporter.record_attempts(attempts, best_s=metric_s if metric_s and metric_s > 0 else None)
            total_attempts += attempts
            cycles_completed += 1

            last_cycle_result = {
                "status": "completed",
                "attempts_completed": attempts,
                "found_improvement": found_improvement,
                "metric_s": metric_s,
            }
        finally:
            reporter.stop()

        if max_cycles == 1:
            return last_cycle_result

    if max_cycles == 1:
        return last_cycle_result

    return {
        "status": "stopped" if ev.is_set() else "completed",
        "cycles_completed": cycles_completed,
        "attempts_completed": total_attempts,
        "improvements_found": improvements_found,
    }
```

---

## 5. Verification Method

1. **Verify Priority Setting**:
   Execute in Python terminal:
   `python3 -c "import os; from src.shape_packing.client.native_worker import set_process_idle_priority; assert set_process_idle_priority() in (True, False)"`
2. **Verify Single-Cycle Contract with Mock Solver**:
   Run `pytest tests/test_native_worker.py -v`.
   Check that `cycle_result["attempts_completed"] == 100`, `cycle_result["found_improvement"] is True`, and both `/solutions` and `/heartbeat` requests are properly sent.
3. **Verify Signal Handling and Stop Event**:
   In a test case:
   ```python
   def test_stop_event_terminates_worker_loop():
       stop_event = threading.Event()
       stop_event.set()
       result = run_worker_cycle(config, stop_event=stop_event, max_cycles=None)
       assert result["status"] == "stopped" or result["cycles_completed"] == 0
   ```
4. **Invalidation Conditions**:
   - If `run_worker_cycle` fails to report heartbeat when `solver_fn` throws or exits.
   - If `set_process_idle_priority()` raises uncaught exceptions on platforms without root permissions.
   - If `attempts_completed` in heartbeats are double-counted rather than reported as incremental progress.
