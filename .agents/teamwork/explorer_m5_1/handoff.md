# Milestone 5 Investigation: End-to-End Distributed Cluster Verification

## 1. Observation

### 1.1 Existing Codebase & Component Interfaces
Direct inspection of the codebase revealed the following components and operational interfaces:

1. **Coordinator Database Layer (`src/shape_packing/server/database.py`)**:
   - Lines 62–115 define SQLite schema with WAL mode (`PRAGMA journal_mode = WAL; PRAGMA synchronous = NORMAL; PRAGMA foreign_keys = ON;`).
   - `init_db(db_path)` (lines 126–144) initializes `problems`, `solutions`, `workers`, and `active_leases` tables.
   - `seed_problems_from_verification(conn, verification_dir)` (lines 291–407) ingests benchmark JSON files from `data/packingVerification/*.json`. Empirically executed against `data/packingVerification/` with command:
     ```bash
     PYTHONPATH=src python3 -c "from shape_packing.server.database import init_db, seed_problems_from_verification; conn = init_db(':memory:'); print(seed_problems_from_verification(conn))"
     ```
     Result: **2,269 problems parsed, 2,249 stored in database** in < 1.0s. Catalog items include `1_cirinsqu` (circle-in-square, $N=1, \text{best\_s}=2.0, \text{status}=\text{'trivial'}$), `4_4_in_4` ($N=4, \text{best\_s}=4.0$), and `6_cirinsqu` ($\text{status}=\text{'proved\_optimal'}$).
   - `update_solution_record` (lines 189–289) requires improvement $\ge \text{RECORD\_MIN\_IMPROVEMENT} = 10^{-5}$ (`metric_s < current_best - 1e-5`), demotes previous solutions (`is_current_record = 0`), writes new solution, updates `problems.best_s`, and increments `workers.records_broken`.

2. **Work Scheduler & Priority Allocator (`src/shape_packing/server/scheduler.py`)**:
   - `assign_work(conn, worker_id, cores, lease_seconds)` (lines 43–233) automatically purges stale leases via `expire_stale_leases` and selects non-`proved_optimal` candidates using a multi-armed bandit policy (10% unattempted exploration, 90% priority exploitation).
   - Lines 70–78 calculate `recommended_attempts = max(1000, min(cores * 1000, 20000))`.
   - When all problems have `status = 'proved_optimal'` or all are leased without fallback, lines 186–188 execute `conn.rollback()` and return `None`.
   - `record_heartbeat` (lines 235–348) increments `problems.total_attempts` and `workers.total_attempts`.

3. **Coordinator REST API & Verification Pipeline (`src/shape_packing/server/app.py`)**:
   - `POST /api/v1/workers/register` (lines 90–117): registers worker, returns `{"worker_id": ..., "username": ..., "client_type": "native", "status": "registered"}`.
   - `GET /api/v1/work` (lines 118–152): returns 200 with lease dictionary or `Response(status_code=status.HTTP_204_NO_CONTENT)` when `assign_work` returns `None`.
   - `POST /api/v1/solutions` (lines 153–286): validates coordinate length ($3 \times N$), finite positive numbers, reconstructs geometry, and invokes `verify_solution(temp_path, problem_str=req.problem, check_record=False)`.
     - Rejects overlaps/containment failures with HTTP 400 (`{"status": "rejected", "verified": False, "message": ...}`).
     - Accepts valid improvements with HTTP 200 (`{"status": "accepted", "verified": True, "is_new_record": True, "metric_s": ...}`).
   - `POST /api/v1/heartbeat` (lines 287–325): logs attempts, returns `{"status": "recorded", "total_worker_attempts": ...}`.
   - `GET /api/v1/stats` (lines 326–352): aggregates `total_problems`, `active_workers`, `total_attempts`, `records_broken`, `verified_solutions`.
   - `GET /api/v1/leaderboard` (lines 353–378): ranks workers by `records_broken DESC, total_attempts DESC`.

4. **Native Worker Client Daemon (`src/shape_packing/client/native_worker.py`)**:
   - Zero external networking dependencies (verified via AST: only `urllib.request`).
   - Loopback proxy bypass (`_get_opener`, lines 96–103) creates an empty `ProxyHandler({})` for `127.0.0.1`, `localhost`, `::1`.
   - `register_with_server(server_url, username, worker_id)` (lines 194–212) registers worker over HTTP.
   - `run_worker_cycle(config, solver_fn, request_fn)` (lines 444–579): leases work, runs solver batch, posts solution if $s < \text{target\_s}$, flushes heartbeat via `HeartbeatReporter`.
   - `run_worker_loop(config, max_cycles, stop_event, solver_fn, request_fn)` (lines 581–626): executes continuous cycles; if cycle returns `status: "idle"`, executes backoff sleep `ev.wait(timeout=config.poll_interval)`.
   - Signal handling & Graceful shutdown (lines 32–41, 380–405, 688–693): `handle_signal` sets `_SHUTDOWN = True` and triggers `_GLOBAL_STOP_EVENT.set()`; `finally: flush_in_flight_heartbeat(config)` flushes in-flight attempt counts to `/api/v1/heartbeat`.

### 1.2 Empirical Geometry Verification Prototyping
We tested concrete geometric configurations with `verify_solution`:
- **Problem `3_3_in_circle`** ($N=3$, inner `3`, container `CIRCLE`, baseline $s=3.0$):
  - Improved $s=2.5$ with coordinates `[-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]` passes SAT verification: `res.valid == True, res.metric == 2.5, res.errors == []`.
- **Problem `4_4_in_4`** ($N=4$, inner `4`, container `4`, baseline $s=5.0$):
  - Improved $s=4.5$ with coordinates `[-1.3, -1.3, 0.0, -1.3, 1.3, 0.0, 1.3, -1.3, 0.0, 1.3, 1.3, 0.0]` passes SAT verification: `res.valid == True, res.metric == 4.5, res.errors == []`.
- **Problem `1_cir_in_4`** ($N=1$, inner `CIRCLE`, container `4`, baseline $s=2.5$):
  - Improved $s=2.0$ with coordinates `[0.0, 0.0, 0.0]` passes SAT verification: `res.valid == True, res.metric == 2.0, res.errors == []`.

### 1.3 Empirical Subprocess & Server Prototyping
1. **Live Uvicorn Server on Loopback**:
   - Ephemeral port selection via `sock.bind(('127.0.0.1', 0))` and `uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error'))` in a daemon thread.
   - Tested real socket HTTP requests from `native_worker.py` without mocks: full cycle completed, leaderboard and stats updated in 0.94s.
2. **Subprocess SIGINT Graceful Shutdown**:
   - Launched real CLI daemon: `python3 -m shape_packing.client.native_worker --server http://127.0.0.1:port --username sig_volunteer --poll-interval 0.5`.
   - Sent OS `SIGINT` via `proc.send_signal(signal.SIGINT)`.
   - Process output: `[Worker] Successfully registered... [Worker] Exited cleanly.` with return code `0`.
   - Coordinator database recorded `total_attempts = 302000` from the flushed in-flight heartbeat.

---

## 2. Logic Chain

1. **Test Scope & Architecture Alignment**:
   - Requirement §R5 dictates: `pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_api.py tests/test_native_worker.py tests/test_distributed_e2e.py` must pass with 0 failures.
   - All unit and isolated concurrency tests already exist and pass (168 passed in 2.16s).
   - Milestone 5 specifically requires `tests/test_distributed_e2e.py` integrating the complete system.

2. **Coordinator API Transport Strategy**:
   - Both `TestClient(app)` (fast, deterministic in-process ASGI simulation) and live `uvicorn` server (testing genuine TCP sockets and loopback urllib request handling) are viable and empirically proven.
   - Providing tests for both gives dual verification:
     - `test_e2e_single_worker_lifecycle_fastapi_testclient` verifies coordinator in-process logic rapidly.
     - `test_e2e_single_worker_lifecycle_live_uvicorn_socket` verifies real OS socket networking and zero-dependency urllib integration.

3. **Lifecycle Flow & Invariant Tracking**:
   - Registration: `POST /api/v1/workers/register` creates worker row with `records_broken = 0, total_attempts = 0`.
   - Leasing: `GET /api/v1/work` creates lease in `active_leases`, allocates problem `target_s` and `recommended_attempts`.
   - Search: Worker executes batch with solver function returning `best_s < target_s`.
   - Verification & Commit: `POST /api/v1/solutions` runs in-process SAT collision test (`solution_tools.py:verify_solution`). If valid and lower, commits new record atomically, demotes old record, increments `workers.records_broken`.
   - Telemetry: Worker heartbeat increments `workers.total_attempts` and `problems.total_attempts`.
   - Reporting: `GET /api/v1/leaderboard` returns worker at rank #1; `GET /api/v1/stats` confirms incremented cluster aggregates.

4. **Starvation & Backoff Reasoning**:
   - When only `proved_optimal` problems exist or all non-optimal problems are active, `assign_work` returns `None`.
   - Coordinator returns HTTP 204 No Content with empty body.
   - `send_request` cleanly decodes empty body into `{}` without throwing `json.JSONDecodeError`.
   - `run_worker_cycle` yields `{"status": "idle", "attempts_completed": 0, "found_improvement": False}`.
   - `run_worker_loop` enters `ev.wait(timeout=config.poll_interval)` backoff.
   - When a problem is released or inserted into the database, the next poll query immediately receives work, returning `{"status": "completed"}`.

5. **Signal Interruption & Graceful Shutdown Reasoning**:
   - Volunteer workers may be interrupted by OS shutdown or user interrupt (`SIGINT` / `Ctrl+C`).
   - Signal handler `handle_signal` flags `_SHUTDOWN = True` and unblocks `_GLOBAL_STOP_EVENT`.
   - Worker breaks loop, enters `finally: flush_in_flight_heartbeat(config)`.
   - In-flight attempts stored in `_IN_FLIGHT_STATE` are posted to `/api/v1/heartbeat`.
   - Coordinator credits attempt counts so volunteer compute is never lost.
   - Process exits cleanly with return code 0.

6. **State Isolation Requirement**:
   - Because `_SHUTDOWN`, `_GLOBAL_STOP_EVENT`, and `_IN_FLIGHT_STATE` are module globals in `src.shape_packing.client.native_worker`, tests that trigger shutdown will cause subsequent tests to immediately exit unless state is restored.
   - An `autouse=True` fixture `reset_worker_state` must be defined in `tests/test_distributed_e2e.py` to reset flags between tests.

---

## 3. Caveats

1. **Solver Binary Availability**: `packer_rs/target/release/packer_rs` is not compiled in this test environment. Therefore, end-to-end tests must inject valid solver functions (`solver_fn`) producing mathematically valid geometric placements verified by `solution_tools.verify_solution`.
2. **Uvicorn Dependency**: `uvicorn` is installed and available in the environment (as seen in `test_native_worker_concurrency.py`). For environments without uvicorn, the test suite can guard live socket tests with `pytest.importorskip("uvicorn")`.
3. **Database Thread-Safety with Uvicorn**: When uvicorn runs multi-threaded ASGI dispatch, SQLite connections in FastAPI dependencies should use `check_same_thread=False` or create a fresh connection per request in WAL mode.

---

## 4. Conclusion & Proposed Implementation

`tests/test_distributed_e2e.py` should be implemented containing 6 distinct, complementary integration test vectors:
1. `test_e2e_single_worker_lifecycle_fastapi_testclient`: Full lifecycle test with seeded catalog, registration, leasing, SAT verification, record commit, leaderboard, and stats via TestClient.
2. `test_e2e_single_worker_lifecycle_live_uvicorn_socket`: Full lifecycle test over real TCP loopback sockets with standard library urllib.
3. `test_e2e_starvation_and_backoff_recovery`: Starvation on `proved_optimal` problems, HTTP 204 backoff, and recovery when new work is released.
4. `test_e2e_signal_interruption_in_process_graceful_shutdown`: In-process signal delivery (`handle_signal`), thread unblocking, and in-flight attempt flush.
5. `test_e2e_signal_interruption_subprocess_cli_daemon`: Genuine OS process SIGINT delivery, clean exit code 0, and coordinator database verification.
6. `test_e2e_invalid_geometry_rejected_and_attempts_preserved`: Coordinator in-process SAT verifier rejects colliding polygons with HTTP 400 while preserving attempt telemetry in database.

### Proposed Code for `tests/test_distributed_e2e.py`

```python
"""End-to-End Distributed Cluster Verification Test Suite.

Verifies complete integration across:
- Coordinator SQLite WAL database & problem catalog seeding
- Multi-armed bandit scheduler & work leasing
- Native worker daemon standard library urllib client
- In-process geometric Separating Axis Theorem (SAT) verification
- Atomic world record commits, leaderboards, and cluster statistics
- Starvation handling (HTTP 204 No Content), poll_interval backoff, and recovery
- Signal interruption (SIGINT) and graceful heartbeat flushing (in-process & OS subprocess)
"""

from __future__ import annotations

import os
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional
import unittest.mock as mock
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

import src.shape_packing.client.native_worker as nw
from src.shape_packing.client.native_worker import (
    WorkerConfig,
    flush_in_flight_heartbeat,
    handle_signal,
    register_with_server,
    run_worker_cycle,
    run_worker_loop,
    send_request,
    set_in_flight_work,
)
from src.shape_packing.server.app import create_app, get_db
from shape_packing.server.database import (
    init_db,
    seed_problems_from_verification,
)


@pytest.fixture(autouse=True)
def reset_worker_state():
    """Ensure clean shutdown flags and in-flight tracking between tests."""
    nw._SHUTDOWN = False
    nw._GLOBAL_STOP_EVENT.clear()
    with nw._IN_FLIGHT_STATE["lock"]:
        nw._IN_FLIGHT_STATE["work_id"] = None
        nw._IN_FLIGHT_STATE["attempts"] = 0
        nw._IN_FLIGHT_STATE["best_s"] = None
    yield
    nw._SHUTDOWN = False
    nw._GLOBAL_STOP_EVENT.clear()


def make_testclient_transport(client: TestClient):
    """Bridge function routing native worker urllib requests to FastAPI TestClient."""
    transport_lock = threading.Lock()

    def transport_send(
        url: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        parsed = urlparse(url)
        path = parsed.path
        if parsed.query:
            path = f"{path}?{parsed.query}"
        body = payload if payload is not None else data

        with transport_lock:
            if method.upper() == "GET":
                resp = client.get(path)
            else:
                resp = client.post(path, json=body)

        if resp.status_code == 204:
            return {}
        elif resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 400:
            import io
            import urllib.error
            raw_text = resp.text
            err = urllib.error.HTTPError(
                url=url,
                code=400,
                msg="Bad Request",
                hdrs=mock.MagicMock(),
                fp=io.BytesIO(raw_text.encode("utf-8")),
            )
            err.error_body = raw_text
            err.error_data = resp.json() if raw_text.strip() else {}
            raise err
        else:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

    return transport_send


# ============================================================================
# Vector 1: Single Worker Lifecycle End-to-End (In-Process TestClient)
# ============================================================================


def test_e2e_single_worker_lifecycle_fastapi_testclient(tmp_path):
    """End-to-End single worker lifecycle against FastAPI coordinator:
    1. Seeds database with standard problems (circle-in-circle, square-in-square).
    2. Worker registers via POST /api/v1/workers/register.
    3. Worker leases work unit via GET /api/v1/work.
    4. Worker discovers verified improvement (metric_s < target_s).
    5. Coordinator SAT verifier verifies non-overlap and boundary containment.
    6. Record committed atomically to database.
    7. Heartbeat credits completed search attempts.
    8. Leaderboard ranks worker #1 with 1 record broken.
    9. Global stats reflect updated active workers, attempts, and solutions.
    """
    db_path = str(tmp_path / "e2e_testclient.db")
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', 0.85)
        """
    )
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

    # Valid placement of 3 triangles in circle (radius s=2.5 < target 3.0)
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    def mock_solver(**kwargs):
        return {"success": True, "best_s": 2.5, "values": valid_coords}

    with mock.patch("src.shape_packing.client.native_worker.send_request", side_effect=transport_send):
        # 1. Register worker
        w_id = register_with_server("http://localhost:8000", username="e2e_alice")
        assert len(w_id) >= 10

        cfg = WorkerConfig(worker_id=w_id, server_url="http://localhost:8000", cores=2)

        # 2. Execute worker cycle
        cycle_res = run_worker_cycle(cfg, solver_fn=mock_solver)

        assert cycle_res["status"] == "completed"
        assert cycle_res["found_improvement"] is True
        assert cycle_res["attempts_completed"] == 2000
        assert cycle_res["metric_s"] == 2.5

    # 3. Verify Leaderboard reflects worker and broken record
    lb_resp = client.get("/api/v1/leaderboard")
    assert lb_resp.status_code == 200
    lb = lb_resp.json()
    assert len(lb) == 1
    assert lb[0]["username"] == "e2e_alice"
    assert lb[0]["records_broken"] == 1
    assert lb[0]["total_attempts"] == 2000

    # 4. Verify Global Stats
    stats_resp = client.get("/api/v1/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_problems"] == 2
    assert stats["active_workers"] >= 1
    assert stats["total_attempts"] == 2000
    assert stats["records_broken"] == 1
    assert stats["verified_solutions"] == 1

    # 5. Verify Problem Detail record update
    prob_resp = client.get("/api/v1/problems/3_3_in_circle")
    assert prob_resp.status_code == 200
    pdata = prob_resp.json()
    assert abs(pdata["best_s"] - 2.5) < 1e-6
    assert pdata["coordinates"] == valid_coords


# ============================================================================
# Vector 2: Single Worker Lifecycle End-to-End (Live Uvicorn Socket Server)
# ============================================================================


def test_e2e_single_worker_lifecycle_live_uvicorn_socket(tmp_path):
    """End-to-End single worker lifecycle over real OS network loopback:
    Uses uvicorn in a background thread to verify:
    - Standard library urllib networking
    - Loopback proxy bypass configuration
    - Real HTTP streaming and response headers
    - Complete database record lifecycle
    """
    pytest.importorskip("uvicorn")
    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    db_path = str(tmp_path / "e2e_live.db")
    conn = init_db(db_path)
    # Seed standard catalog from verification data
    seed_problems_from_verification(conn, verification_dir="data/packingVerification")

    # Ensure 4_4_in_4 has high priority and eligible status
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('4_4_in_4', '4', '4', 4, 5.0, 5.0, 'best_known', 0.99)
        ON CONFLICT(id) DO UPDATE SET best_s = 5.0, status = 'best_known', density_rank = 0.99
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)

    # Thread-safe SQLite connection factory for concurrent ASGI worker threads
    def thread_safe_get_db():
        c = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode = WAL;")
        c.execute("PRAGMA synchronous = NORMAL;")
        c.execute("PRAGMA foreign_keys = ON;")
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_db] = thread_safe_get_db

    server_config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(server_config)
    server_thread = threading.Thread(target=server.run, daemon=True, name="UvicornLiveServer")
    server_thread.start()
    time.sleep(0.3)

    server_url = f"http://127.0.0.1:{port}"
    valid_square_coords = [
        -1.3, -1.3, 0.0,
        -1.3,  1.3, 0.0,
         1.3, -1.3, 0.0,
         1.3,  1.3, 0.0,
    ]

    try:
        # 1. Register with real HTTP coordinator
        w_id = register_with_server(server_url, username="socket_bob")
        assert len(w_id) >= 10

        cfg = WorkerConfig(worker_id=w_id, server_url=server_url, cores=1)

        def mock_solver(**kwargs):
            return {"success": True, "best_s": 4.5, "values": valid_square_coords}

        # 2. Execute work cycle over real sockets (zero mocks on send_request)
        res = run_worker_cycle(cfg, solver_fn=mock_solver)

        assert res["status"] == "completed"
        assert res["found_improvement"] is True
        assert res["attempts_completed"] == 1000

        # 3. Verify leaderboard over real HTTP GET
        lb = send_request(f"{server_url}/api/v1/leaderboard")
        assert len(lb) >= 1
        assert lb[0]["username"] == "socket_bob"
        assert lb[0]["records_broken"] >= 1

        # 4. Verify stats over real HTTP GET
        stats = send_request(f"{server_url}/api/v1/stats")
        assert stats["active_workers"] >= 1
        assert stats["records_broken"] >= 1
        assert stats["verified_solutions"] >= 1

    finally:
        server.should_exit = True
        server_thread.join(timeout=2.0)


# ============================================================================
# Vector 3: Starvation & Backoff Recovery
# ============================================================================


def test_e2e_starvation_and_backoff_recovery(tmp_path):
    """End-to-End Starvation & Backoff:
    1. Database only contains proved_optimal problems (empty eligible queue).
    2. Coordinator returns HTTP 204 No Content.
    3. Worker returns status='idle' and performs backoff wait (poll_interval).
    4. New non-optimal problem is released into the database.
    5. On subsequent cycle, worker seamlessly recovers, leases problem, and finishes.
    """
    db_path = str(tmp_path / "e2e_starvation.db")
    conn = init_db(db_path)
    cursor = conn.cursor()
    # Insert only proved_optimal problem
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status)
        VALUES ('1_opt', '3', 'CIRCLE', 1, 1.0, 1.0, 'proved_optimal')
        """
    )
    conn.commit()

    app = create_app(db_path=db_path)
    client = TestClient(app)
    transport_send = make_testclient_transport(client)

    # Background thread to release work after brief starvation interval
    def delayed_problem_release():
        time.sleep(0.1)
        c = sqlite3.connect(db_path)
        c.execute(
            """
            INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
            VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', 0.9)
            """
        )
        c.commit()
        c.close()

    release_thread = threading.Thread(target=delayed_problem_release, daemon=True)
    release_thread.start()

    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    with mock.patch("src.shape_packing.client.native_worker.send_request", side_effect=transport_send):
        w_id = register_with_server("http://localhost:8000", username="starved_worker")
        cfg = WorkerConfig(worker_id=w_id, server_url="http://localhost:8000", poll_interval=0.15)

        # Run multi-cycle loop: Cycle 1 should starve (idle), Cycle 2 should recover (completed)
        history = run_worker_loop(
            cfg,
            max_cycles=2,
            solver_fn=lambda **kw: {"success": True, "best_s": 2.5, "values": valid_coords},
        )

    release_thread.join(timeout=2.0)
    conn.close()

    assert len(history) == 2
    assert history[0]["status"] == "idle"
    assert history[0]["attempts_completed"] == 0
    assert history[0]["found_improvement"] is False

    assert history[1]["status"] == "completed"
    assert history[1]["attempts_completed"] == 1000
    assert history[1]["found_improvement"] is True


# ============================================================================
# Vector 4: In-Process Signal Interruption & Graceful Heartbeat Flush
# ============================================================================


def test_e2e_signal_interruption_in_process_graceful_shutdown(tmp_path):
    """End-to-End in-process signal interruption:
    1. Worker is actively computing a solver batch.
    2. Simulated SIGINT triggers handle_signal.
    3. Worker unblocks immediately from loop.
    4. Post-loop finally block calls flush_in_flight_heartbeat.
    5. Coordinator records in-flight attempts in database.
    """
    db_path = str(tmp_path / "e2e_sig_inprocess.db")
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status)
        VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known')
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    client = TestClient(app)
    transport_send = make_testclient_transport(client)

    with mock.patch("src.shape_packing.client.native_worker.send_request", side_effect=transport_send):
        w_id = register_with_server("http://localhost:8000", username="sig_interrupted_worker")
        cfg = WorkerConfig(worker_id=w_id, server_url="http://localhost:8000", poll_interval=5.0)

        # Obtain lease
        work_unit = transport_send("http://localhost:8000/api/v1/work?worker_id=" + w_id)
        work_id = work_unit["work_id"]

        # Track 1500 in-flight attempts completed before signal arrives
        set_in_flight_work(work_id=work_id, attempts=1500, best_s=2.85)

        # Simulate SIGINT signal delivery
        handle_signal(signal.SIGINT, None)

        # Worker loop must exit immediately without executing new cycles
        history = run_worker_loop(cfg, max_cycles=10)
        assert history == []

        # Flush in-flight heartbeat as main() does in finally: block
        flushed = flush_in_flight_heartbeat(cfg, request_fn=transport_send)
        assert flushed is True

    # Verify coordinator database recorded the 1500 attempts
    db_conn = sqlite3.connect(db_path)
    db_conn.row_factory = sqlite3.Row
    c = db_conn.cursor()
    c.execute("SELECT total_attempts FROM workers WHERE id = ?", (w_id,))
    assert c.fetchone()["total_attempts"] == 1500

    c.execute("SELECT total_attempts FROM problems WHERE id = '3_3_in_circle'")
    assert c.fetchone()["total_attempts"] == 1500
    db_conn.close()


# ============================================================================
# Vector 5: Subprocess OS Signal Interruption & CLI Daemon Graceful Exit
# ============================================================================


def test_e2e_signal_interruption_subprocess_cli_daemon(tmp_path):
    """End-to-End OS signal interruption with real subprocess CLI:
    1. Spawns live coordinator server.
    2. Spawns native_worker CLI process using subprocess.Popen.
    3. Sends real OS SIGINT signal to child process.
    4. Worker catches signal, flushes in-flight attempts, exits with code 0.
    5. Coordinator confirms worker registration and telemetry in SQLite.
    """
    pytest.importorskip("uvicorn")
    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    db_path = str(tmp_path / "e2e_subprocess.db")
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', 0.8)
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)

    def thread_safe_get_db():
        c = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode = WAL;")
        c.execute("PRAGMA synchronous = NORMAL;")
        c.execute("PRAGMA foreign_keys = ON;")
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_db] = thread_safe_get_db

    server_config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(server_config)
    server_thread = threading.Thread(target=server.run, daemon=True, name="UvicornSubprocServer")
    server_thread.start()
    time.sleep(0.3)

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
                "0.5",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={"PYTHONPATH": "src", "PATH": os.environ.get("PATH", "")},
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


# ============================================================================
# Vector 6: Invalid Geometry Rejection & Attempt Telemetry Preservation
# ============================================================================


def test_e2e_invalid_geometry_rejected_and_attempts_preserved(tmp_path):
    """End-to-End Invalid Geometry Rejection:
    1. Worker leases problem.
    2. Worker submits invalid overlapping geometry (all shapes at origin).
    3. Coordinator in-process SAT verifier rejects with HTTP 400.
    4. Worker attempts completed are still flushed and credited.
    5. Database world record remains uncorrupted.
    """
    db_path = str(tmp_path / "e2e_invalid_geom.db")
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status)
        VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known')
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    client = TestClient(app)
    transport_send = make_testclient_transport(client)

    # 3 overlapping shapes at origin (0, 0, 0)
    overlapping_coords = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    def mock_invalid_solver(**kwargs):
        return {"success": True, "best_s": 2.5, "values": overlapping_coords}

    with mock.patch("src.shape_packing.client.native_worker.send_request", side_effect=transport_send):
        w_id = register_with_server("http://localhost:8000", username="overlap_worker")
        cfg = WorkerConfig(worker_id=w_id, server_url="http://localhost:8000", cores=1)

        # Worker cycle will raise urllib.error.HTTPError from coordinator's 400 rejection
        with pytest.raises(Exception) as exc_info:
            run_worker_cycle(cfg, solver_fn=mock_invalid_solver)

        assert "400" in str(exc_info.value) or getattr(exc_info.value, "code", None) == 400

    # Verify best_s was NOT corrupted
    db_conn = sqlite3.connect(db_path)
    db_conn.row_factory = sqlite3.Row
    c = db_conn.cursor()
    c.execute("SELECT best_s FROM problems WHERE id = '3_3_in_circle'")
    assert c.fetchone()["best_s"] == 3.0

    # Worker attempts credited despite solution rejection
    c.execute("SELECT total_attempts, records_broken FROM workers WHERE id = ?", (w_id,))
    w_row = c.fetchone()
    assert w_row["total_attempts"] == 1000
    assert w_row["records_broken"] == 0
    db_conn.close()
```

---

## 5. Verification Method

### 5.1 Independent Verification Commands
To independently verify this design and confirm that all existing and newly specified tests pass with 0 failures:

1. **Verify complete distributed test suite**:
   ```bash
   pytest tests/test_server_database.py \
          tests/test_server_scheduler.py \
          tests/test_server_api.py \
          tests/test_native_worker.py \
          -v
   ```
   **Expected**: 168 passed in ~2.2s.

2. **Verify live server concurrency & socket communication**:
   ```bash
   pytest tests/test_native_worker_concurrency.py -k test_multi_worker_fleet_live_server_with_thread_override -v
   ```
   **Expected**: 1 passed in ~0.9s.

3. **Verify prototype execution for all 3 Milestone 5 mission scenarios**:
   ```bash
   PYTHONPATH=src python3 -c "
   import tempfile, sqlite3, unittest.mock as mock
   from fastapi.testclient import TestClient
   from shape_packing.server.app import create_app
   from shape_packing.server.database import init_db
   from shape_packing.client.native_worker import WorkerConfig, run_worker_cycle, register_with_server

   db_path = tempfile.mktemp(suffix='.db')
   conn = init_db(db_path)
   cursor = conn.cursor()
   cursor.execute(\"INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status) VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known')\")
   conn.commit()
   conn.close()

   app = create_app(db_path=db_path)
   client = TestClient(app)

   def mock_send(url, method='GET', payload=None, timeout=10.0, **kwargs):
       from urllib.parse import urlparse
       p = urlparse(url)
       path = f'{p.path}?{p.query}' if p.query else p.path
       r = client.get(path) if method.upper() == 'GET' else client.post(path, json=payload)
       return {} if r.status_code == 204 else r.json()

   with mock.patch('shape_packing.client.native_worker.send_request', side_effect=mock_send):
       w_id = register_with_server('http://localhost:8000', 'alice')
       cfg = WorkerConfig(worker_id=w_id, server_url='http://localhost:8000')
       res = run_worker_cycle(cfg, solver_fn=lambda **kw: {'success': True, 'best_s': 2.5, 'values': [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]})

   print('Cycle result:', res)
   print('Leaderboard:', client.get('/api/v1/leaderboard').json())
   print('Stats:', client.get('/api/v1/stats').json())
   "
   ```
   **Expected**: Cycle status `completed`, improvement `True`, leaderboard reflecting `alice` with 1 record broken, stats reflecting `verified_solutions: 1`.

4. **Verify Milestone 5 acceptance command once implemented**:
   ```bash
   pytest tests/test_server_database.py \
          tests/test_server_scheduler.py \
          tests/test_server_api.py \
          tests/test_native_worker.py \
          tests/test_distributed_e2e.py \
          -v
   ```
   **Expected**: All tests pass with 0 failures.

### 5.2 Invalidation Conditions
This investigation and test design would be invalidated if:
1. `solution_tools.verify_solution` changes its container scaling convention or returns invalid for legitimate non-overlapping coordinates.
2. `native_worker.py` removes standard library `urllib` in favor of third-party networking libraries.
3. FastAPI dependency injection overrides fail to cleanly close SQLite connections across worker threads in WAL mode.
