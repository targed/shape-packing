# Specification Mining & Remediation Report: End-to-End Integration Suite

**Miner**: `spec_miner_m5_it2_1` (E2E Remediation Spec Miner)  
**Parent**: Orchestrator conversation ID `86ab9594-ed5d-48cc-9be1-f2844355b5e4`  
**Target File**: `tests/test_distributed_e2e.py`  
**Date**: 2026-11-21T05:05:30Z  

---

## Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Scheduler | MAB Exploration Problem Selection | 10% probability query selecting unattempted problems (`total_attempts = 0` or `status = 'unattempted'`) excluding `status = 'proved_optimal'` | Worker request at `/api/v1/work` | Leased Problem dictionary | Returns 204 No Content if no unleased non-optimal problems exist | `src/shape_packing/server/scheduler.py:109-125` |
| 2 | Coordinator API | Geometric Coordinate Length Validation | Validates submission coordinates vector has length `3 * n` before executing SAT verifier | POST `/api/v1/solutions` with coordinate list | HTTP 200 on success | HTTP 400 Bad Request with error detail if `len != 3*n` | `src/shape_packing/server/app.py:192-198` |
| 3 | Worker Client | Multi-signature Solver Invocation | Passes problem parameters (`n`, `n_shapes`, `inner_shape`, `container_shape`, `attempts`, `target_s`) to solver callback | WorkerConfig, solver_fn | Result dictionary with `values` and `best_s` | Fallback signature retry on `TypeError` | `src/shape_packing/client/native_worker.py:415-442` |
| 4 | Test Harness | Background Live Server Readiness | Asynchronous startup of Uvicorn ASGI server with socket port binding | `uvicorn.Server(config)` in `threading.Thread` | `server.started == True` and open TCP socket | Connection refused if client connects before server binds | `tests/test_distributed_e2e.py:313-318, 777-782` |
| 5 | Test Harness | Subprocess OS Signal Interruption & Cleanup | Spawns native worker CLI as OS subprocess and signals SIGINT | CLI arguments via `subprocess.Popen` | Exit code 0 and stdout "[Worker] Exited cleanly." | Orphaned background process if unhandled timeout or assertion failure occurs | `tests/test_distributed_e2e.py:786-827` |

---

## Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | MAB Exploration Lease | Two unattempted problems (`3_3_in_circle`, $N=3$; `4_4_in_4`, $N=4$) with single-problem mock returning 9 coordinates | ~5% chance of selecting `4_4_in_4`, triggering HTTP 400 Bad Request ("Coordinate count (9) must be 3*N (12)") and failing test. |
| 2 | Subprocess Termination | Timeout or assertion failure during CLI daemon test | Worker daemon process remains alive in background without `proc.kill()` in `finally:` block. |
| 3 | Server Startup Timing | Uvicorn server started with fixed `time.sleep(0.4)` under high load or CI congestion | Socket connection fails if startup exceeds 400ms, or wastes idle time if startup takes ~11ms. |

---

## 1. Observation

### 1.1 Flakiness Reproduction in `test_e2e_single_worker_lifecycle_fastapi_testclient`
- **Location**: `tests/test_distributed_e2e.py:197–263`
- **Empirical Measurement**:
  - Running 50 iterations of `test_e2e_single_worker_lifecycle_fastapi_testclient` in isolation resulted in **2 failures out of 50 runs (4.0% failure rate)**.
  - Verbatim Failure Trace:
    ```
    url = 'http://localhost:8000/api/v1/solutions', method = 'POST'
    payload = {'work_id': '...', 'worker_id': '...', 'problem': '4_4_in_4', 's': 2.5, ...}
    >           raise err
    E           urllib.error.HTTPError: HTTP Error 400: HTTP Error 400
    tests/test_distributed_e2e.py:119: HTTPError
    ```
- **Context in Code**:
  - In `tests/test_distributed_e2e.py:197–208`, two problems are seeded: `3_3_in_circle` ($N=3$) and `4_4_in_4` ($N=4$), both with `status = 'best_known'` and default `total_attempts = 0`.
  - In `src/shape_packing/server/scheduler.py:109–125`, a 10% exploration branch executes:
    `WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal' AND (p.status = 'unattempted' OR p.total_attempts = 0) ORDER BY RANDOM() LIMIT 1`
  - With ~5% probability ($0.10 \times 0.50$), `4_4_in_4` is leased instead of `3_3_in_circle`.
  - In `tests/test_distributed_e2e.py:217–220`, `mock_solver` unconditionally returned 9 coordinates (`valid_coords`). For $N=4$, `/api/v1/solutions` requires $3 \times 4 = 12$ coordinates, rejecting the submission with HTTP 400.

### 1.2 Subprocess Lifecycle in `test_e2e_signal_interruption_subprocess_cli_daemon`
- **Location**: `tests/test_distributed_e2e.py:786–827`
- `subprocess.Popen` is executed without pre-initializing `proc = None` or terminating `proc` in `finally:`.
- If `proc.communicate(timeout=5.0)` raises `TimeoutExpired` or any assertion fails, `proc.kill()` is not called, potentially leaking background processes.

### 1.3 Server Startup Delays in Live Server Tests
- **Locations**: `tests/test_distributed_e2e.py:317` and `tests/test_distributed_e2e.py:781`
- Fixed `time.sleep(0.4)` is used to wait for uvicorn binding.
- Direct measurement shows uvicorn startup completes in ~11ms. Fixed sleep wastes ~380ms per live test and risks `ConnectionRefusedError` if host system load delays startup past 400ms.

---

## 2. Logic Chain

1. **Exclusion of `proved_optimal` in Work Scheduler**:
   - Both the exploration query (`scheduler.py:114`) and exploitation query (`scheduler.py:132`) strictly filter:
     `WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'`
   - Setting `status = 'proved_optimal'` on `4_4_in_4` in `test_e2e_single_worker_lifecycle_fastapi_testclient` guarantees that `4_4_in_4` is never leased to workers.
   - Global problem count query (`SELECT COUNT(*) FROM problems` in `app.py:314`) counts all rows regardless of status, preserving `stats["total_problems"] == 2`.
   - Therefore, `3_3_in_circle` is deterministically leased 100% of the time, updating its record to $s=2.5$ and satisfying assertions at lines 257–261.

2. **Defense-in-Depth via Shape-Aware `mock_solver`**:
   - `native_worker.py:415–442` passes `n`, `n_shapes`, and `inner_shape` into `solver_fn`.
   - By checking `n == 4` or `inner == "4"`, `mock_solver` can return `valid_square_coords` (12 floats, $s=4.5$) for $N=4$, and `valid_coords` (9 floats, $s=2.5$) for $N=3$.
   - Even under adversarial scheduler conditions, the solver submission will strictly pass coordinate length validation and in-process SAT verification.

3. **Subprocess Cleanup Guarantee**:
   - Setting `proc: Optional[subprocess.Popen] = None` before `try:`, and checking `if proc is not None and proc.poll() is None:` in `finally:` ensures that if the process was created and is still running, `proc.kill()` sends SIGKILL and `proc.communicate(timeout=2.0)` reaps the exit status, closing all stdout/stderr pipes.

4. **Deterministic Readiness Polling**:
   - `uvicorn.Server` sets `server.started = True` after the event loop initializes and binds socket listeners.
   - Polling `getattr(server, "started", False)` along with active connection check via `socket.create_connection((host, port))` provides a timeout-guarded (5.0s) readiness barrier that unblocks immediately (~11ms) without race conditions.

---

## 3. Caveats

- **Scope**: Production code in `src/shape_packing/` is fully compliant with R1–R5 and remains unchanged. All remediation is strictly confined to `tests/test_distributed_e2e.py`.
- **Bandit Exploration Logic**: The 10% bandit exploration mechanism is an explicit requirement from R2 and operates as intended. The remediation adapts the test fixture to comply with the scheduler's exclusion rules.
- **Other Tests**: All other 8 workflows in `tests/test_distributed_e2e.py` were verified clean with 0 failures over 50 iterations.

---

## 4. Conclusion & Ready-to-Implement Modifications

The remediation plan consists of four distinct, self-contained modifications to `tests/test_distributed_e2e.py`.

### Modification 1: Add `wait_for_server_ready` Helper
Add the readiness polling function right after `make_thread_local_transport` (around line 177).

#### Before:
```python
        if resp.status_code == 204:
            return {}
        elif resp.status_code == 200:
            return resp.json()
        elif resp.status_code >= 400:
            raw_text = resp.text
            err = urllib.error.HTTPError(
                url=url,
                code=resp.status_code,
                msg=f"HTTP Error {resp.status_code}",
                hdrs=mock.MagicMock(),
                fp=io.BytesIO(raw_text.encode("utf-8")),
            )
            err.error_body = raw_text
            try:
                err.error_data = resp.json() if raw_text.strip() else {}
            except Exception:
                err.error_data = {}
            raise err
        else:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

    return transport_send


# ============================================================================
# Workflow 1: Single Worker Lifecycle End-to-End (In-Process TestClient)
# ============================================================================
```

#### After:
```python
        if resp.status_code == 204:
            return {}
        elif resp.status_code == 200:
            return resp.json()
        elif resp.status_code >= 400:
            raw_text = resp.text
            err = urllib.error.HTTPError(
                url=url,
                code=resp.status_code,
                msg=f"HTTP Error {resp.status_code}",
                hdrs=mock.MagicMock(),
                fp=io.BytesIO(raw_text.encode("utf-8")),
            )
            err.error_body = raw_text
            try:
                err.error_data = resp.json() if raw_text.strip() else {}
            except Exception:
                err.error_data = {}
            raise err
        else:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

    return transport_send


def wait_for_server_ready(
    server: Any,
    host: str = "127.0.0.1",
    port: Optional[int] = None,
    timeout: float = 5.0,
) -> None:
    """Poll until background uvicorn server is running and actively accepting connections."""
    deadline = time.time() + timeout
    while not getattr(server, "started", False) and time.time() < deadline:
        time.sleep(0.01)
    if not getattr(server, "started", False):
        raise TimeoutError(f"Uvicorn server failed to start within {timeout}s")
    if port is not None:
        while time.time() < deadline:
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.01)
        raise TimeoutError(f"Uvicorn server port {port} not accepting connections within {timeout}s")


# ============================================================================
# Workflow 1: Single Worker Lifecycle End-to-End (In-Process TestClient)
# ============================================================================
```

---

### Modification 2: Status `proved_optimal` and Shape-Aware Mock Solver in Workflow 1
In `test_e2e_single_worker_lifecycle_fastapi_testclient` (around lines 203–221):

#### Before:
```python
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('4_4_in_4', '4', '4', 4, 5.0, 5.0, 'best_known', 0.75)
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    client = TestClient(app)
    transport_send = make_testclient_transport(client)

    # Valid placement of 3 triangles in circle (s=2.5 < target 3.0)
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    def mock_solver(**kwargs: Any) -> Dict[str, Any]:
        return {"success": True, "best_s": 2.5, "values": valid_coords}
```

#### After:
```python
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('4_4_in_4', '4', '4', 4, 5.0, 5.0, 'proved_optimal', 0.75)
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    client = TestClient(app)
    transport_send = make_testclient_transport(client)

    # Valid placement of 3 triangles in circle (s=2.5 < target 3.0)
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]
    valid_square_coords = [
        -1.3, -1.3, 0.0,
        -1.3,  1.3, 0.0,
         1.3, -1.3, 0.0,
         1.3,  1.3, 0.0,
    ]

    def mock_solver(**kwargs: Any) -> Dict[str, Any]:
        n = kwargs.get("n") or kwargs.get("n_shapes")
        inner = str(kwargs.get("inner_shape") or kwargs.get("inner_token") or "")
        if n == 4 or inner == "4":
            return {"success": True, "best_s": 4.5, "values": valid_square_coords}
        return {"success": True, "best_s": 2.5, "values": valid_coords}
```

---

### Modification 3: Server Startup Readiness Polling in Workflow 2
In `test_e2e_single_worker_lifecycle_live_uvicorn_socket` (around lines 313–318):

#### Before:
```python
    server_config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(server_config)
    server_thread = threading.Thread(target=server.run, daemon=True, name="UvicornLiveServer")
    server_thread.start()
    time.sleep(0.4)
```

#### After:
```python
    server_config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(server_config)
    server_thread = threading.Thread(target=server.run, daemon=True, name="UvicornLiveServer")
    server_thread.start()
    wait_for_server_ready(server, port=port)
```

---

### Modification 4: Server Readiness & Subprocess Cleanup in Workflow 7
In `test_e2e_signal_interruption_subprocess_cli_daemon` (around lines 777–827):

#### Before:
```python
    server_config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(server_config)
    server_thread = threading.Thread(target=server.run, daemon=True, name="UvicornSubprocServer")
    server_thread.start()
    time.sleep(0.4)

    server_url = f"http://127.0.0.1:{port}"

    try:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "shape_packing.client.native_worker",
                "--server",
                server_url,
                "--username",
                "daemon_cli_worker",
                "--poll-interval",
                "0.2",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONPATH": "src"},
        )

        # Allow worker daemon to register and begin loop
        time.sleep(0.8)

        # Deliver real OS SIGINT
        proc.send_signal(signal.SIGINT)
        stdout, stderr = proc.communicate(timeout=5.0)

        assert proc.returncode == 0, f"Worker process failed with code {proc.returncode}. Stderr: {stderr}"
        assert "[Worker] Exited cleanly." in stdout

        # Verify database registered worker
        db_conn = sqlite3.connect(db_path)
        db_conn.row_factory = sqlite3.Row
        c = db_conn.cursor()
        c.execute("SELECT username, total_attempts FROM workers WHERE username = 'daemon_cli_worker'")
        w_row = c.fetchone()
        assert w_row is not None
        assert w_row["username"] == "daemon_cli_worker"
        db_conn.close()

    finally:
        server.should_exit = True
        server_thread.join(timeout=2.0)
```

#### After:
```python
    server_config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(server_config)
    server_thread = threading.Thread(target=server.run, daemon=True, name="UvicornSubprocServer")
    server_thread.start()
    wait_for_server_ready(server, port=port)

    server_url = f"http://127.0.0.1:{port}"

    proc: Optional[subprocess.Popen] = None
    try:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "shape_packing.client.native_worker",
                "--server",
                server_url,
                "--username",
                "daemon_cli_worker",
                "--poll-interval",
                "0.2",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONPATH": "src"},
        )

        # Allow worker daemon to register and begin loop
        time.sleep(0.8)

        # Deliver real OS SIGINT
        proc.send_signal(signal.SIGINT)
        stdout, stderr = proc.communicate(timeout=5.0)

        assert proc.returncode == 0, f"Worker process failed with code {proc.returncode}. Stderr: {stderr}"
        assert "[Worker] Exited cleanly." in stdout

        # Verify database registered worker
        db_conn = sqlite3.connect(db_path)
        db_conn.row_factory = sqlite3.Row
        c = db_conn.cursor()
        c.execute("SELECT username, total_attempts FROM workers WHERE username = 'daemon_cli_worker'")
        w_row = c.fetchone()
        assert w_row is not None
        assert w_row["username"] == "daemon_cli_worker"
        db_conn.close()

    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
                proc.communicate(timeout=2.0)
            except Exception:
                pass
        server.should_exit = True
        server_thread.join(timeout=2.0)
```

---

## 5. Verification Method

To independently verify this remediation:

1. **Verify 0 Flakes over 50 Iterations**:
   ```bash
   python3 -c "
   import subprocess, sys
   for i in range(50):
       res = subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_distributed_e2e.py::test_e2e_single_worker_lifecycle_fastapi_testclient', '-q'], capture_output=True, text=True)
       assert res.returncode == 0, f'Run {i} failed: {res.stdout}'
   print('All 50 passed with 0 failures.')
   "
   ```
   *Expected Outcome*: 50/50 runs pass with 0 failures (0.0% failure rate).

2. **Verify Full E2E Test Suite Execution**:
   ```bash
   pytest tests/test_distributed_e2e.py -v
   ```
   *Expected Outcome*: 9 passed in < 2.0s.

3. **Verify Full Distributed Cluster Acceptance Suite**:
   ```bash
   pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_api.py tests/test_native_worker.py tests/test_distributed_e2e.py -v
   ```
   *Expected Outcome*: 177 passed in < 4.5s.

4. **Verify No Subprocess or Socket Leaks**:
   ```bash
   python3 -c "
   import psutil, os
   p = psutil.Process()
   fds_before = len(p.open_files()) + len(p.connections())
   import pytest
   pytest.main(['tests/test_distributed_e2e.py', '-q'])
   fds_after = len(p.open_files()) + len(p.connections())
   print(f'FDs before: {fds_before}, FDs after: {fds_after}')
   assert fds_after <= fds_before + 2
   "
   ```
   *Expected Outcome*: 0 leaked subprocesses or dangling sockets.
