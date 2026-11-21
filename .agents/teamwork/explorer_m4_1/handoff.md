# Milestone 4 Investigation & Networking Architecture: Native Worker Client

**Investigator**: `explorer_m4_1`  
**Milestone**: M4 — Native Worker Client Daemon  
**Scope**: Client Networking Architecture using Python standard library `urllib` only  
**Status**: COMPLETE (Hard Handoff)

---

## 1. Observation

### 1.1 Existing System Contracts & Endpoints
Inspection of coordinator implementation in `src/shape_packing/server/app.py` reveals the following exact endpoint contracts and status codes:
1. `POST /api/v1/workers/register` (lines 90–117):
   - Accepts JSON `WorkerRegisterRequest`: `{"username": str, "client_type": str = "native", "worker_id": Optional[str] = None}`.
   - Returns `200 OK`: `{"worker_id": str, "username": str, "client_type": str, "status": "registered"}`.
   - Returns `400 Bad Request` if `username` is empty: `{"detail": "Username cannot be empty"}`.
2. `GET /api/v1/work?worker_id={id}&cores={cores}&lease_seconds={lease}` (lines 118–152):
   - Returns `200 OK` when work is available: JSON payload with `work_id`, `problem`, `inner_token`, `container_token`, `n`, `target_s`, `recommended_attempts`, `lease_seconds`, `timeout_seconds`.
   - Returns `204 No Content` with an empty HTTP response body (`b""`) when no non-optimal problems are available or all problems are leased.
   - Returns `400 Bad Request` if `worker_id` is empty or `cores < 1`.
3. `POST /api/v1/solutions` (lines 153–286):
   - Accepts JSON `SolutionSubmitRequest`: `{"work_id": Optional[str], "worker_id": str, "problem": str, "s": float, "coordinates": List[float]}`.
   - Returns `200 OK`: `{"status": "accepted"|"duplicate", "verified": True, "is_new_record": bool, "metric_s": float, "previous_best_s": float, "message": str}`.
   - Returns `400 Bad Request` if coordinate length != 3*N, if coordinate contains NaN/Inf, or if in-process SAT non-overlap / container boundary check fails: `{"status": "rejected", "verified": False, "message": "Geometric verification failed: ..."}`.
4. `POST /api/v1/heartbeat` (lines 287–325):
   - Accepts JSON `HeartbeatRequest`: `{"worker_id": str, "work_id": str, "attempts_completed": int, "best_local_s": Optional[float]}`.
   - Returns `200 OK`: `{"status": "recorded"|"ignored", "total_worker_attempts": int}`.
   - Returns `400 Bad Request` if identifiers empty or attempts < 0.
5. `GET /api/v1/stats` (lines 326–352) & `GET /api/v1/leaderboard` (lines 353–378):
   - Return cluster statistics and top contributor rankings over `200 OK`.

### 1.2 Dependency & Packaging Constraints
Inspection of `pyproject.toml` (lines 11–18):
```toml
dependencies = [
    "numpy>=1.24.0",
    "scipy>=1.10.0",
    "matplotlib>=3.7.0",
    "numba>=0.58.0",
    "joblib>=1.3.0",
    "pillow>=9.5.0",
]
```
Neither `requests`, `httpx`, `aiohttp`, nor `urllib3` are permitted or listed as dependencies. Requirement §R4 of `ORIGINAL_REQUEST.md` mandates standard library `urllib` exclusively.

### 1.3 Python Standard Library `urllib` Mechanics & Environment Proxy Trap
Execution of real Python runtime tests against standard library `urllib.request` revealed two critical behavioral facts:
1. **Exception Raising on Non-2xx Responses**:
   `urllib.request.urlopen` does not return response objects for 4xx or 5xx status codes; instead, it raises `urllib.error.HTTPError`. However, `HTTPError` implements the `io.BufferedIOBase` protocol: calling `exc.read().decode("utf-8")` extracts the server's JSON error response payload (e.g. rejection messages from `/api/v1/solutions`).
2. **Environment Proxy Interception (`http_proxy` / `HTTP_PROXY`)**:
   In environments where corporate, development, or container proxies are exported (such as `http_proxy=http://127.0.0.1:40167`), standard `urllib.request.urlopen` routes `127.0.0.1` and `localhost` through the proxy unless loopback bypass is configured. This resulted in `Direct IP access is not allowed` (HTTP 400).
   Configuring `urllib.request.ProxyHandler({})` for loopback addresses completely resolves this trap.

---

## 2. Logic Chain

1. **Premise 1**: The worker daemon must operate without third-party networking dependencies in Python 3.10+.
2. **Premise 2**: The coordinator REST service returns specific HTTP status codes with semantic meaning: `200` (success with data), `204` (queue starvation/no content), `400` (bad request or geometric verification rejection), `5xx` (transient server fault), and connection drops/timeouts (`0`).
3. **Reasoning from Premise 1 & 2 to `send_request` Signature**:
   A function returning only `dict` cannot distinguish `204 No Content` (valid empty queue) from an empty response, nor can it inspect HTTP status codes without raising uncaught exceptions on 400 or 500.
   Therefore, the signature:
   `send_request(url: str, method: str = "GET", data: Optional[Dict] = None, headers: Optional[Dict] = None, timeout: float = 10.0) -> Tuple[int, Dict[str, Any], str]`
   provides an explicit 3-tuple `(status_code, response_dict, raw_text)`:
   - For `200 OK`: `(200, parsed_json, raw_text)`
   - For `204 No Content`: `(204, {}, "")`
   - For `400 Bad Request`: `(400, parsed_error_json, raw_text)`
   - For `5xx Server Error`: `(500, parsed_json_or_empty, raw_text)`
   - For Transport / Network / Timeout Failure: `(0, {}, error_message)`
4. **Reasoning to `WorkerConfig` Structure**:
   The worker requires coordination parameters (`coordinator_url`/`server_url`, `username`, `client_type`, `cores`, `worker_id`) alongside operational telemetry (`poll_interval`, `heartbeat_interval`, `max_consecutive_errors`, `timeout`, `max_backoff`).
   Implementing URL normalization and alias bridging (`server_url` <-> `coordinator_url`) in `__post_init__` ensures compatibility with CLI argument conventions, test suites, and internal callers.
5. **Reasoning to Status Code State Machine**:
   - `200 OK`: Reset consecutive error count to 0; process payload.
   - `204 No Content`: Work queue temporarily starved; sleep for `poll_interval` (default 5.0s) without increasing error counter.
   - `400 Bad Request`: Permanent input invalidity or SAT verification rejection; do not retry identical submission; log diagnostic reason from `message`. If occurred during work request, re-register worker.
   - `5xx / 0`: Transient network failure or coordinator restart; increment `consecutive_errors`; apply exponential backoff `min(max_backoff, 2 ** errors + uniform(0, 0.5))`; if errors exceed `max_consecutive_errors`, log critical alert.
6. **Reasoning to AST Verification**:
   To guarantee zero third-party networking imports across the client module, an automated AST parser can traverse all `Import` and `ImportFrom` nodes in `native_worker.py` and assert disjointness with `{'requests', 'httpx', 'aiohttp', 'urllib3'}`.

---

## 3. Caveats

1. **Proxy Environment Traversal**:
   `ProxyHandler({})` is selectively applied to loopback hosts (`127.0.0.1`, `localhost`). If a user deploys the worker in an enterprise network targeting a remote coordinator URL via an authentic corporate HTTP proxy, urllib's default environment proxy handling will properly engage.
2. **Test Mock Flexibility**:
   Early draft plan notes sketched `send_request` returning `Dict`. Client helper methods (`register_with_server`, `run_worker_cycle`) should unpack tuples when present (`if isinstance(resp, tuple): (code, data, raw) = resp else: code, data, raw = 200, resp, ""`), ensuring 100% interoperability with both 3-tuple callers and simplified unit test mocks.
3. **OS Priority Portability**:
   `os.nice(19)` is standard POSIX. On Windows or environments without permission to adjust process priority, calls must be safely wrapped in a try/except block to ensure zero-crash execution.
4. **Heartbeat Thread Safety**:
   Standard library `urllib.request.urlopen` requests create independent TCP sockets. When a background heartbeat thread emits periodic progress while the main thread executes an optimization batch, requests do not conflict.

---

## 4. Conclusion & Architecture Blueprint

### 4.1 `WorkerConfig` Dataclass Specification

```python
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class WorkerConfig:
    """Configuration parameters for distributed native worker daemon."""
    server_url: str = "http://localhost:8000"
    username: str = "anonymous"
    client_type: str = "native"
    worker_id: Optional[str] = None
    cores: int = 1
    poll_interval: float = 5.0
    heartbeat_interval: float = 30.0
    max_consecutive_errors: int = 5
    timeout: float = 10.0
    max_backoff: float = 60.0
    coordinator_url: Optional[str] = None

    def __post_init__(self) -> None:
        if self.coordinator_url is not None:
            self.server_url = self.coordinator_url
        self.server_url = self.server_url.rstrip("/")
        self.coordinator_url = self.server_url
        if self.cores < 1:
            self.cores = os.cpu_count() or 1
```

### 4.2 Standard Library `send_request` Architecture

```python
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

def send_request(
    url: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
) -> Tuple[int, Dict[str, Any], str]:
    """
    Execute HTTP request using Python standard library urllib only.

    Returns:
        Tuple of (status_code: int, response_dict: Dict, raw_text: str)
        On network/transport failure, returns (0, {}, error_message).
    """
    req_headers = {
        "Accept": "application/json",
        "User-Agent": "shape-packing-worker/1.0",
    }
    encoded_body = None
    if data is not None:
        req_headers["Content-Type"] = "application/json"
        encoded_body = json.dumps(data).encode("utf-8")

    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(
        url,
        data=encoded_body,
        headers=req_headers,
        method=method.upper(),
    )

    # Bypass environment proxies for loopback destinations to avoid interception traps
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname in ("127.0.0.1", "localhost", "::1"):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    else:
        opener = urllib.request.build_opener()

    try:
        with opener.open(req, timeout=timeout) as resp:
            status_code = getattr(resp, "status", resp.getcode())
            raw_bytes = resp.read()
            raw_text = raw_bytes.decode("utf-8", errors="replace")
            json_dict: Dict[str, Any] = {}
            if raw_text.strip():
                try:
                    json_dict = json.loads(raw_text)
                except Exception:
                    json_dict = {}
            return (status_code, json_dict, raw_text)

    except urllib.error.HTTPError as exc:
        status_code = exc.code
        try:
            raw_bytes = exc.read()
            raw_text = raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            raw_text = ""
        json_dict = {}
        if raw_text.strip():
            try:
                json_dict = json.loads(raw_text)
            except Exception:
                json_dict = {}
        return (status_code, json_dict, raw_text)

    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return (0, {}, str(exc))
```

### 4.3 Client Endpoint Handlers & Resilience State Machine

```python
import random
import time
from typing import Any, Dict, List, Optional, Tuple

class CoordinatorClient:
    """Stateful networking coordinator client managing registration and error backoff."""

    def __init__(self, config: WorkerConfig):
        self.config = config
        self.consecutive_errors: int = 0

    def _apply_backoff(self) -> None:
        self.consecutive_errors += 1
        sleep_sec = min(
            self.config.max_backoff,
            (2 ** (min(self.consecutive_errors, 6) - 1)) + random.uniform(0.1, 0.5),
        )
        time.sleep(sleep_sec)

    def _reset_errors(self) -> None:
        self.consecutive_errors = 0

    def register(self) -> str:
        """Register worker node with coordinator, retrying on transient faults."""
        url = f"{self.config.server_url}/api/v1/workers/register"
        payload = {
            "username": self.config.username,
            "client_type": self.config.client_type,
            "worker_id": self.config.worker_id,
        }
        while self.consecutive_errors < self.config.max_consecutive_errors:
            code, data, raw = send_request(url, method="POST", data=payload, timeout=self.config.timeout)
            if code == 200 and "worker_id" in data:
                self._reset_errors()
                self.config.worker_id = data["worker_id"]
                return data["worker_id"]
            elif code == 400:
                raise ValueError(f"Registration rejected by coordinator: {data.get('detail') or raw}")
            else:
                self._apply_backoff()

        raise ConnectionError(f"Failed to register with coordinator at {self.config.server_url}")

    def fetch_work(self) -> Optional[Dict[str, Any]]:
        """
        Poll work lease from coordinator.
        Returns:
            Dict containing problem details if leased (200),
            None if queue empty (204) or on transient failure.
        """
        url = (
            f"{self.config.server_url}/api/v1/work"
            f"?worker_id={self.config.worker_id}&cores={self.config.cores}&lease_seconds=300"
        )
        code, data, raw = send_request(url, method="GET", timeout=self.config.timeout)
        if code == 200:
            self._reset_errors()
            return data
        elif code == 204:
            self._reset_errors()
            return None  # Caller sleeps for poll_interval
        elif code == 400:
            # Re-register if coordinator lost worker record
            self.register()
            return None
        else:
            self._apply_backoff()
            return None

    def submit_solution(
        self,
        work_id: str,
        problem: str,
        metric_s: float,
        coordinates: List[float],
    ) -> Tuple[bool, Dict[str, Any]]:
        """Submit candidate packing solution for in-process SAT verification."""
        url = f"{self.config.server_url}/api/v1/solutions"
        payload = {
            "work_id": work_id,
            "worker_id": self.config.worker_id,
            "problem": problem,
            "s": float(metric_s),
            "coordinates": coordinates,
        }
        for attempt in range(3):
            code, data, raw = send_request(url, method="POST", data=payload, timeout=self.config.timeout)
            if code == 200:
                self._reset_errors()
                return (True, data)
            elif code == 400:
                # Deterministic verification rejection
                return (False, data)
            else:
                time.sleep(1.0 + attempt)
        return (False, {"status": "error", "message": "Coordinator submission failed"})

    def send_heartbeat(
        self,
        work_id: str,
        attempts: int,
        best_local_s: Optional[float] = None,
    ) -> bool:
        """Report worker liveness and cumulative attempts."""
        url = f"{self.config.server_url}/api/v1/heartbeat"
        payload = {
            "worker_id": self.config.worker_id,
            "work_id": work_id,
            "attempts_completed": attempts,
            "best_local_s": best_local_s,
        }
        code, data, raw = send_request(url, method="POST", data=payload, timeout=self.config.timeout)
        if code == 200:
            self._reset_errors()
            return True
        return False
```

### 4.4 Backward-Compatible Standalone Functions

```python
def register_with_server(
    server_url: str,
    username: str,
    worker_id: Optional[str] = None,
    timeout: float = 10.0,
) -> str:
    """Standalone registration helper matching test fixtures."""
    url = f"{server_url.rstrip('/')}/api/v1/workers/register"
    payload = {"username": username, "client_type": "native", "worker_id": worker_id}
    resp = send_request(url, method="POST", data=payload, timeout=timeout)
    data = resp[1] if isinstance(resp, tuple) else resp
    return data["worker_id"]
```

---

## 5. Verification Method

### 5.1 AST Verification for Zero External Networking Libraries
Add this automated test to `tests/test_native_worker.py`:

```python
import ast
import os

def test_zero_external_networking_dependencies():
    """Verify native_worker.py imports zero third-party networking packages."""
    client_path = os.path.join("src", "shape_packing", "client", "native_worker.py")
    assert os.path.exists(client_path), f"File {client_path} does not exist"

    with open(client_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=client_path)

    forbidden = {"requests", "httpx", "aiohttp", "urllib3"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])

    violations = imported.intersection(forbidden)
    assert not violations, f"Forbidden networking libraries imported in native_worker.py: {violations}"
```

### 5.2 Unit Verification Suite for `send_request`
Test cases covering all status pathways with an in-process local HTTP server fixture:
1. `GET /ok` -> Expect status 200, parsed JSON dict, non-empty raw text.
2. `GET /empty` -> Expect status 204, empty dict `{}` and raw string `""`.
3. `POST /submit` (valid payload) -> Expect status 200, parsed JSON response.
4. `POST /submit` (invalid payload) -> Expect status 400, parsed rejection JSON with error message, no unhandled exception.
5. `GET /err500` -> Expect status 500, parsed error dict, no unhandled crash.
6. `GET /unreachable_port` -> Expect status 0, empty dict, raw text containing `Connection refused`.
7. `GET /timeout` -> Expect status 0, empty dict, raw text containing timeout information.

### 5.3 Automated Verification Commands
```bash
# 1. Run full server test suite to ensure API compliance
pytest tests/test_server_api.py -v

# 2. Run native worker tests once implemented
pytest tests/test_native_worker.py -v

# 3. Run distributed end-to-end integration test
pytest tests/test_distributed_e2e.py -v
```
