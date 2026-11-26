"""Native worker daemon for distributed shape packing optimization.

This module implements the volunteer computing worker client daemon adhering
to Milestone 4 requirements:
- Standard library networking only (`urllib.request`, zero third-party networking dependencies).
- Loopback proxy bypass for local testing and container development environments.
- Idle OS scheduling priority (`nice` on POSIX, `SetPriorityClass` on Windows).
- Incremental and flush-on-exit heartbeat reporting.
- Candidate solution submission upon verified target improvement.
- Graceful shutdown handling for SIGINT and SIGTERM.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import dataclass
import io
import json
import math
import os
import signal
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request


_SHUTDOWN: bool = False
_GLOBAL_STOP_EVENT = threading.Event()

_IN_FLIGHT_STATE: Dict[str, Any] = {
    "work_id": None,
    "attempts": 0,
    "best_s": None,
    "lock": threading.Lock(),
}


_WORKER_SECRETS: Dict[str, str] = {}


@dataclass
class WorkerConfig:
    """Configuration parameters for distributed native worker daemon."""

    server_url: str = "https://shape-packing-ggd4d5e8c2ctggam.eastus-01.azurewebsites.net"
    username: str = "anonymous"
    client_type: str = "native"
    worker_id: Optional[str] = None
    worker_secret: Optional[str] = None
    cores: int = 1
    poll_interval: float = 5.0
    heartbeat_interval: float = 30.0
    timeout: float = 10.0
    max_backoff: float = 60.0
    coordinator_url: Optional[str] = None

    def __post_init__(self) -> None:
        if self.coordinator_url is not None:
            self.server_url = self.coordinator_url
        if not self.server_url:
            raise ValueError("server_url cannot be empty")
        parsed_url = urllib.parse.urlparse(self.server_url)
        if parsed_url.scheme.lower() not in ("http", "https") or not parsed_url.netloc:
            raise ValueError(f"server_url must be a valid http(s) URL, got: {self.server_url!r}")

        # Strip trailing slashes to avoid double-slash route formatting
        self.server_url = self.server_url.rstrip("/")
        self.coordinator_url = self.server_url

        if self.cores < 1:
            raise ValueError(f"cores must be >= 1, got {self.cores}")

        # Limit Rust Rayon and OpenMP concurrency to allocated cores
        os.environ["RAYON_NUM_THREADS"] = str(self.cores)
        os.environ["OMP_NUM_THREADS"] = str(self.cores)

    @classmethod
    def from_env(cls, **overrides: Any) -> WorkerConfig:
        """Construct WorkerConfig by ingesting environment variables with optional overrides."""
        server_url = os.environ.get("SHAPE_PACKING_SERVER_URL", "https://shape-packing-ggd4d5e8c2ctggam.eastus-01.azurewebsites.net")
        username = os.environ.get("SHAPE_PACKING_USERNAME", "anonymous")
        worker_id = os.environ.get("SHAPE_PACKING_WORKER_ID", None)
        cores_env = os.environ.get("SHAPE_PACKING_CORES", None)
        if cores_env is not None:
            try:
                cores = int(cores_env)
            except ValueError:
                cores = 1
        else:
            cores = 1

        kwargs: Dict[str, Any] = {
            "server_url": server_url,
            "username": username,
            "worker_id": worker_id,
            "cores": cores,
        }
        kwargs.update(overrides)
        return cls(**kwargs)


def _get_opener(url: str) -> Optional[urllib.request.OpenerDirector]:
    """Return a custom urllib opener with proxy bypass if target is a loopback host."""
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname in ("127.0.0.1", "localhost", "::1"):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return None


def send_request(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
    data: Optional[Dict[str, Any]] = None,
    opener: Optional[urllib.request.OpenerDirector] = None,
) -> Dict[str, Any]:
    """Execute an HTTP request using Python standard library urllib only.

    Handles:
    - HTTP 200: Decodes and returns parsed JSON dictionary.
    - HTTP 204: Returns empty dictionary `{}` without JSONDecodeError.
    - HTTP 400: Reads error payload, stores in `exc.error_data` & `exc.error_body`, and re-raises HTTPError.
    - Network / timeout / connection refused: Re-raises URLError / TimeoutError.
    - Loopback hosts: Bypasses environment proxy via ProxyHandler({}).
    - Opener injection: Supports optional `opener` for custom handlers or testing.
    """
    body_dict = payload if payload is not None else data

    req_headers = {
        "Accept": "application/json",
        "User-Agent": "shape-packing-worker/1.0",
    }
    encoded_body: Optional[bytes] = None
    if body_dict is not None:
        req_headers["Content-Type"] = "application/json"
        encoded_body = json.dumps(body_dict).encode("utf-8")

    if headers:
        req_headers.update(headers)

    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed_url.scheme!r}")

    req = urllib.request.Request(
        url,
        data=encoded_body,
        headers=req_headers,
        method=method.upper(),
    )

    try:
        active_opener = opener or _get_opener(url)
        if active_opener is not None:
            resp_ctx = active_opener.open(req, timeout=timeout)
        else:
            resp_ctx = urllib.request.urlopen(req, timeout=timeout)

        cm = resp_ctx if hasattr(resp_ctx, "__enter__") else nullcontext(resp_ctx)

        with cm as resp:
            status_code = getattr(resp, "status", None)
            if status_code is None and hasattr(resp, "getcode"):
                status_code = resp.getcode()
            if status_code == 204:
                return {}

            raw_bytes = resp.read(10_000_001)
            if isinstance(raw_bytes, (bytes, bytearray)) and len(raw_bytes) > 10_000_000:
                raise ValueError("Coordinator response exceeded 10 MB safety limit")
            if not raw_bytes:
                return {}

            if isinstance(raw_bytes, str):
                raw_text = raw_bytes
            else:
                raw_text = raw_bytes.decode("utf-8", errors="replace")
            if not raw_text.strip():
                return {}

            return json.loads(raw_text)

    except urllib.error.HTTPError as exc:
        try:
            err_bytes = exc.read(1_000_000)
            exc.fp = io.BytesIO(err_bytes)
            exc.read = exc.fp.read
            err_text = err_bytes.decode("utf-8", errors="replace")
            exc.error_body = err_text
            try:
                err_json = json.loads(err_text) if err_text.strip() else {}
            except Exception:
                err_json = {}
            exc.error_data = err_json
        except Exception:
            if not hasattr(exc, "error_body"):
                exc.error_body = ""
            if not hasattr(exc, "error_data"):
                exc.error_data = {}
        raise exc


def _auth_headers(
    config: Optional[WorkerConfig] = None,
    worker_id: Optional[str] = None,
    worker_secret: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Build Authorization Bearer header dict when a worker_secret is available."""
    secret = worker_secret
    if not secret and config is not None:
        secret = config.worker_secret
        if not secret and config.worker_id:
            secret = _WORKER_SECRETS.get(config.worker_id)
    if not secret and worker_id:
        secret = _WORKER_SECRETS.get(worker_id)
    if secret:
        return {"Authorization": f"Bearer {secret}"}
    return None


def register_with_server(
    server_url: str,
    username: str,
    worker_id: Optional[str] = None,
    timeout: float = 10.0,
    worker_secret: Optional[str] = None,
) -> str:
    """Register worker node with coordinator and return the assigned worker_id."""
    url = f"{server_url.rstrip('/')}/api/v1/workers/register"
    payload = {
        "username": username,
        "client_type": "native",
        "worker_id": worker_id,
    }
    secret = worker_secret or (_WORKER_SECRETS.get(worker_id) if worker_id else None)
    kwargs: Dict[str, Any] = {"method": "POST", "payload": payload, "timeout": timeout}
    if secret:
        kwargs["headers"] = {"Authorization": f"Bearer {secret}"}
    resp = send_request(url, **kwargs)
    data = resp[1] if isinstance(resp, tuple) and len(resp) >= 2 else resp
    if isinstance(data, dict) and "worker_id" in data:
        assigned_id = data["worker_id"]
        if isinstance(data.get("worker_secret"), str) and data["worker_secret"]:
            _WORKER_SECRETS[assigned_id] = data["worker_secret"]
        return assigned_id
    raise ValueError(f"Registration failed: invalid response {resp}")


CONFIG_CACHE_PATH = os.path.expanduser("~/.shape_packing_worker.json")


def load_cached_worker_id(username: str, path: Optional[str] = None) -> Optional[str]:
    """Retrieve persisted worker_id for a username from local configuration file."""
    cache_path = path or CONFIG_CACHE_PATH
    try:
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("username") == username:
                    return data.get("worker_id")
    except Exception:
        pass
    return None


def load_cached_worker_secret(username: str, path: Optional[str] = None) -> Optional[str]:
    """Retrieve persisted worker_secret for a username from local configuration file."""
    cache_path = path or CONFIG_CACHE_PATH
    try:
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("username") == username:
                    secret = data.get("worker_secret")
                    return secret if isinstance(secret, str) and secret else None
    except Exception:
        pass
    return None


def save_cached_worker_id(
    username: str,
    worker_id: str,
    path: Optional[str] = None,
    worker_secret: Optional[str] = None,
) -> None:
    """Persist worker_id (and optional worker_secret) for a username to local configuration file."""
    cache_path = path or CONFIG_CACHE_PATH
    try:
        os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
        data: Dict[str, Any] = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as rf:
                    data = json.load(rf)
            except Exception:
                data = {}
        data["username"] = username
        data["worker_id"] = worker_id
        secret_to_save = worker_secret or _WORKER_SECRETS.get(worker_id)
        if secret_to_save:
            data["worker_secret"] = secret_to_save
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        if os.name == "posix":
            os.chmod(cache_path, 0o600)
    except Exception:
        pass


def deregister_with_server(
    config: WorkerConfig,
    request_fn: Optional[Callable] = None,
    timeout: float = 3.0,
) -> bool:
    """Notify coordinator on graceful exit to release leases and mark offline."""
    if not config.worker_id:
        return False
    req = request_fn or send_request
    url = f"{config.server_url.rstrip('/')}/api/v1/workers/deregister"
    kwargs: Dict[str, Any] = {
        "method": "POST",
        "payload": {"worker_id": config.worker_id},
        "timeout": timeout,
    }
    hdrs = _auth_headers(config=config)
    if hdrs:
        kwargs["headers"] = hdrs
    try:
        req(url, **kwargs)
        return True
    except Exception:
        return False


def set_process_idle_priority() -> bool:
    """Set current process to idle/lowest background OS scheduling priority.

    POSIX (Linux, macOS):
        Sets nice level to 19 via os.nice(19) or os.setpriority(os.PRIO_PROCESS, 0, 19).
    Windows:
        Sets priority class to IDLE_PRIORITY_CLASS (0x00000040) via ctypes.

    Returns:
        bool: True if idle priority was successfully applied, False on fallback.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            idle_priority_class = 0x00000040
            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.SetPriorityClass.restype = wintypes.BOOL
            handle = kernel32.GetCurrentProcess()
            res = kernel32.SetPriorityClass(handle, idle_priority_class)
            return bool(res)
        except Exception:
            return False
    else:
        try:
            if hasattr(os, "nice"):
                os.nice(19)
                return True
            elif hasattr(os, "setpriority") and hasattr(os, "PRIO_PROCESS"):
                os.setpriority(os.PRIO_PROCESS, 0, 19)
                return True
        except (OSError, PermissionError, AttributeError):
            return False
    return False


set_idle_priority = set_process_idle_priority


def set_in_flight_work(
    work_id: Optional[str],
    attempts: int = 0,
    best_s: Optional[float] = None,
) -> None:
    """Update global in-flight compute tracking for graceful shutdown flushes."""
    with _IN_FLIGHT_STATE["lock"]:
        _IN_FLIGHT_STATE["work_id"] = work_id
        _IN_FLIGHT_STATE["attempts"] = attempts
        _IN_FLIGHT_STATE["best_s"] = best_s


def flush_in_flight_heartbeat(
    config: WorkerConfig,
    request_fn: Optional[Callable] = None,
) -> bool:
    """Flush pending in-flight attempts to /api/v1/heartbeat on graceful shutdown."""
    req = request_fn or send_request
    with _IN_FLIGHT_STATE["lock"]:
        work_id = _IN_FLIGHT_STATE.get("work_id") or "in_flight_work"
        attempts = _IN_FLIGHT_STATE.get("attempts", 0)
        best_s = _IN_FLIGHT_STATE.get("best_s")
        _IN_FLIGHT_STATE["attempts"] = 0
        _IN_FLIGHT_STATE["work_id"] = None
        _IN_FLIGHT_STATE["best_s"] = None

    if attempts <= 0:
        return False

    url = f"{config.server_url.rstrip('/')}/api/v1/heartbeat"
    payload = {
        "worker_id": config.worker_id,
        "work_id": work_id,
        "attempts_completed": attempts,
        "best_local_s": best_s,
    }
    try:
        kwargs: Dict[str, Any] = {"method": "POST", "payload": payload}
        hdrs = _auth_headers(config=config)
        if hdrs:
            kwargs["headers"] = hdrs
        req(url, **kwargs)
        return True
    except Exception:
        return False


class HeartbeatReporter:
    """Thread-safe background daemon that flushes attempt counts and keeps leases alive."""

    def __init__(
        self,
        server_url: str,
        worker_id: Optional[str],
        work_id: str,
        interval_seconds: float = 30.0,
        request_fn: Optional[Callable] = None,
        worker_secret: Optional[str] = None,
    ):
        self.server_url = server_url.rstrip("/")
        self.worker_id = worker_id
        self.work_id = work_id
        self.interval_seconds = interval_seconds
        self.request_fn = request_fn or send_request
        self.worker_secret = worker_secret

        self._lock = threading.Lock()
        self._unreported_attempts = 0
        self._best_local_s: Optional[float] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the background heartbeat reporter thread."""
        set_in_flight_work(self.work_id, 0, None)
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="HeartbeatReporter"
        )
        self._thread.start()

    def record_attempts(self, count: int, best_s: Optional[float] = None) -> None:
        """Record completed solver attempts and update best local score."""
        with self._lock:
            self._unreported_attempts += count
            if best_s is not None:
                if self._best_local_s is None or best_s < self._best_local_s:
                    self._best_local_s = best_s
            unrep = self._unreported_attempts
            b_s = self._best_local_s

        set_in_flight_work(self.work_id, unrep, b_s)

    def flush(self, force: bool = False, completed: bool = False) -> bool:
        """Flush accumulated attempts to coordinator heartbeat endpoint."""
        with self._lock:
            attempts_to_send = self._unreported_attempts
            best_s_to_send = self._best_local_s
            self._unreported_attempts = 0

        set_in_flight_work(self.work_id, 0, None)

        if not force and attempts_to_send == 0:
            return True

        url = f"{self.server_url}/api/v1/heartbeat"
        payload: Dict[str, Any] = {
            "worker_id": self.worker_id,
            "work_id": self.work_id,
            "attempts_completed": attempts_to_send,
            "best_local_s": best_s_to_send,
        }
        if completed:
            payload["completed"] = True
        try:
            kwargs: Dict[str, Any] = {"method": "POST", "payload": payload}
            hdrs = _auth_headers(worker_id=self.worker_id, worker_secret=self.worker_secret)
            if hdrs:
                kwargs["headers"] = hdrs
            self.request_fn(url, **kwargs)
            return True
        except Exception:
            # Re-credit attempts if network call failed so they can be retried on next flush
            with self._lock:
                self._unreported_attempts += attempts_to_send
                current_unreported = self._unreported_attempts
                current_best_s = self._best_local_s
            set_in_flight_work(self.work_id, current_unreported, current_best_s)
            return False

    def stop(self) -> None:
        """Stop the background heartbeat thread and perform a final attempt flush."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self.flush(force=True, completed=True)

    def _run(self) -> None:
        while not self._stop_event.wait(timeout=self.interval_seconds):
            self.flush(force=True)


def handle_signal(sig: int, frame: Any) -> None:
    """Signal handler setting shutdown flag and unblocking waiting threads."""
    global _SHUTDOWN
    _SHUTDOWN = True
    _GLOBAL_STOP_EVENT.set()


def setup_signal_handlers(
    stop_event: Optional[threading.Event] = None,
) -> threading.Event:
    """Register SIGINT and SIGTERM handlers to set the provided or global stop_event."""
    ev = stop_event or _GLOBAL_STOP_EVENT

    def _sig_handler(sig: int, frame: Any) -> None:
        handle_signal(sig, frame)
        ev.set()

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _sig_handler)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, _sig_handler)
    except (ValueError, AttributeError):
        pass

    return ev


def _invoke_solver(
    solver_fn: Callable,
    inner_token: str,
    container_token: str,
    n: int,
    attempts: int,
    target_s: Optional[float],
) -> Dict[str, Any]:
    """Invoke solver function with flexible parameter signatures."""
    try:
        return solver_fn(
            inner_shape=inner_token,
            container_shape=container_token,
            n_shapes=n,
            n=n,
            attempts=attempts,
            target_s=target_s,
        )
    except TypeError:
        try:
            return solver_fn(
                inner_shape=inner_token,
                container_shape=container_token,
                n=n,
                attempts=attempts,
                target_s=target_s,
            )
        except TypeError:
            return solver_fn(
                n_shapes=n,
                inner_shape=inner_token,
                container_shape=container_token,
                attempts=attempts,
                target_s=target_s,
            )


def run_worker_cycle(
    config: WorkerConfig,
    arg2: Any = None,
    stop_event: Optional[threading.Event] = None,
    max_cycles: Optional[int] = 1,
    solver_fn: Optional[Callable] = None,
    request_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Execute a single work unit cycle (lease, solve, submit improvement, heartbeat).

    Accepts positional or keyword arguments for stop_event, solver_fn, and max_cycles.
    """
    if arg2 is not None:
        if isinstance(arg2, threading.Event) or hasattr(arg2, "is_set"):
            if stop_event is None:
                stop_event = arg2
        elif callable(arg2):
            if solver_fn is None:
                solver_fn = arg2
        elif isinstance(arg2, int):
            max_cycles = arg2

    ev = stop_event or _GLOBAL_STOP_EVENT
    req = request_fn or send_request

    encoded_worker_id = urllib.parse.quote(str(config.worker_id or ""), safe="")
    work_url = (
        f"{config.server_url.rstrip('/')}/api/v1/work"
        f"?worker_id={encoded_worker_id}&cores={config.cores}"
    )

    auth_hdrs = _auth_headers(config=config)
    work_kwargs: Dict[str, Any] = {"method": "GET"}
    if auth_hdrs:
        work_kwargs["headers"] = auth_hdrs
    resp = req(work_url, **work_kwargs)
    work = resp[1] if isinstance(resp, tuple) and len(resp) >= 2 else resp

    if not work or not isinstance(work, dict) or not work.get("work_id"):
        return {"status": "idle", "attempts_completed": 0, "found_improvement": False}

    work_id = work["work_id"]
    problem = work.get("problem", "")
    target_s = work.get("target_s")
    attempts = max(1, min(int(work.get("recommended_attempts", 2000)), 100_000))
    inner_token = str(work.get("inner_token", "3"))
    container_token = str(work.get("container_token", "CIRCLE"))
    n = max(1, min(int(work.get("n", 3)), 200))

    reporter = HeartbeatReporter(
        server_url=config.server_url,
        worker_id=config.worker_id,
        work_id=work_id,
        interval_seconds=getattr(config, "heartbeat_interval", 30.0),
        request_fn=req,
        worker_secret=config.worker_secret,
    )
    reporter.start()

    found_improvement = False
    metric_s_float: Optional[float] = None

    try:
        if solver_fn:
            result = _invoke_solver(
                solver_fn,
                inner_token=inner_token,
                container_token=container_token,
                n=n,
                attempts=attempts,
                target_s=target_s,
            )
        else:
            from ..solver_interface import run_solver

            result = run_solver(
                n_shapes=n,
                inner_shape=inner_token,
                container_shape=container_token,
                attempts=attempts,
                target_s=target_s,
            )

        metric_s = result.get("best_s")
        if metric_s is None:
            metric_s = result.get("score")
        if metric_s is None:
            metric_s = result.get("final_metric")
        if metric_s is None and "S" in result:
            metric_s = result.get("S")

        coords = result.get("values")
        if coords is None:
            coords = result.get("coordinates", [])

        success = bool(result.get("success", False))

        target_s_float = float(target_s) if target_s is not None else None
        metric_s_float = float(metric_s) if metric_s is not None else None

        # Record attempts immediately upon solver batch completion so volunteer compute
        # is credited even if candidate solution submission fails or is rejected by coordinator
        reporter.record_attempts(
            attempts,
            best_s=(
                metric_s_float
                if (metric_s_float is not None and metric_s_float > 0)
                else None
            ),
        )

        if (
            success
            and metric_s_float is not None
            and not math.isnan(metric_s_float)
            and not math.isinf(metric_s_float)
        ):
            if target_s_float is None or metric_s_float < target_s_float:
                found_improvement = True
                sol_url = f"{config.server_url.rstrip('/')}/api/v1/solutions"
                sol_kwargs: Dict[str, Any] = {
                    "method": "POST",
                    "payload": {
                        "work_id": work_id,
                        "worker_id": config.worker_id,
                        "problem": problem,
                        "s": metric_s_float,
                        "coordinates": [float(c) for c in coords],
                    },
                }
                if auth_hdrs:
                    sol_kwargs["headers"] = auth_hdrs
                req(sol_url, **sol_kwargs)

    finally:
        reporter.stop()

    return {
        "status": "completed",
        "attempts_completed": attempts,
        "found_improvement": found_improvement,
        "metric_s": metric_s_float,
    }


def run_worker_loop(
    config: WorkerConfig,
    max_cycles: Optional[int] = None,
    stop_event: Optional[threading.Event] = None,
    solver_fn: Optional[Callable] = None,
    request_fn: Optional[Callable] = None,
) -> List[Dict[str, Any]]:
    """Execute continuous bounded or unbounded work cycles with error recovery and 204 backoff."""
    global _SHUTDOWN
    ev = stop_event or _GLOBAL_STOP_EVENT
    req = request_fn or send_request

    history: List[Dict[str, Any]] = []
    consecutive_errors = 0

    while not _SHUTDOWN and not ev.is_set():
        if max_cycles is not None and len(history) >= max_cycles:
            break

        try:
            cycle_result = run_worker_cycle(
                config=config,
                solver_fn=solver_fn,
                stop_event=ev,
                request_fn=req,
                max_cycles=1,
            )
            consecutive_errors = 0
            history.append(cycle_result)

            if cycle_result.get("status") == "idle":
                if _SHUTDOWN or ev.is_set():
                    break
                if ev.wait(timeout=config.poll_interval):
                    break

        except Exception as e:
            consecutive_errors += 1
            if _SHUTDOWN or ev.is_set():
                break
            sleep_time = min(config.max_backoff, 5.0 * consecutive_errors)
            if ev.wait(timeout=sleep_time):
                break

    return history


def main(argv: Optional[List[str]] = None) -> None:
    """CLI entrypoint for the Native Worker Client Daemon."""
    parser = argparse.ArgumentParser(
        description="Distributed Shape Packing Native Worker Daemon"
    )
    parser.add_argument(
        "--server", default="https://shape-packing-ggd4d5e8c2ctggam.eastus-01.azurewebsites.net", help="Coordinator URL"
    )
    parser.add_argument(
        "--username", default="anonymous", help="Volunteer handle username"
    )
    parser.add_argument(
        "--cores", type=int, default=1, help="CPU cores allocated for optimization"
    )
    parser.add_argument(
        "--worker-id", default=None, help="Assigned worker ID (optional)"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Poll interval for idle queue in seconds",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Maximum work cycles to execute before exiting",
    )
    args = parser.parse_args(argv)

    # Set background idle priority
    set_process_idle_priority()

    # Register signal handlers
    setup_signal_handlers()

    # Register with coordinator (using persisted worker_id & secret if available)
    target_worker_id = args.worker_id or load_cached_worker_id(args.username)
    cached_secret = load_cached_worker_secret(args.username)
    try:
        worker_id = register_with_server(
            args.server,
            args.username,
            worker_id=target_worker_id,
            worker_secret=cached_secret,
        )
        resolved_secret = _WORKER_SECRETS.get(worker_id) or cached_secret
        save_cached_worker_id(args.username, worker_id, worker_secret=resolved_secret)
    except Exception as e:
        print(
            f"[Worker] Failed to register with coordinator at {args.server}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    config = WorkerConfig(
        server_url=args.server,
        username=args.username,
        worker_id=worker_id,
        worker_secret=resolved_secret,
        cores=args.cores,
        poll_interval=args.poll_interval,
    )
    print(
        f"[Worker] Successfully registered as '{args.username}' ({worker_id}). Starting optimization loop..."
    )

    try:
        run_worker_loop(config, max_cycles=args.max_cycles)
    finally:
        flush_in_flight_heartbeat(config)
        deregister_with_server(config)
        print("[Worker] Exited cleanly.")


if __name__ == "__main__":
    main()
