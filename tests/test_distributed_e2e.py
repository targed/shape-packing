"""End-to-End Distributed Cluster Verification Test Suite.

Verifies complete integration across:
1. Coordinator SQLite WAL database & problem catalog seeding
2. Multi-armed bandit scheduler & work leasing
3. Native worker daemon standard library urllib client
4. In-process geometric Separating Axis Theorem (SAT) verification
5. Atomic world record commits, leaderboards, and cluster statistics
6. Multi-worker fleet concurrency and fair attempt balancing
7. Competing worker races and atomic solution demotion
8. Starvation handling (HTTP 204 No Content), poll_interval backoff, and recovery
9. Signal interruption (SIGINT) and graceful heartbeat flushing (in-process & OS subprocess)
10. Adversarial invalid geometry rejection with telemetry preservation
11. Real verification catalog ingestion (>2,200 problems) and lease allocation
"""

from __future__ import annotations

import concurrent.futures
import io
import json
import math
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional
from unittest import mock
from urllib.parse import urlparse
import urllib.error

import pytest
from fastapi.testclient import TestClient

import shape_packing.client.native_worker as nw
from shape_packing.client.native_worker import (
    WorkerConfig,
    flush_in_flight_heartbeat,
    handle_signal,
    register_with_server,
    run_worker_cycle,
    run_worker_loop,
    send_request,
    set_in_flight_work,
)
from shape_packing.server.app import create_app, get_db
from shape_packing.server.database import (
    get_problem,
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
    with nw._IN_FLIGHT_STATE["lock"]:
        nw._IN_FLIGHT_STATE["work_id"] = None
        nw._IN_FLIGHT_STATE["attempts"] = 0
        nw._IN_FLIGHT_STATE["best_s"] = None


def make_testclient_transport(client: TestClient):
    """Bridge routing native worker urllib requests to in-process FastAPI TestClient."""
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


def make_thread_local_transport(app: Any):
    """Thread-safe transport bridge creating an isolated TestClient per OS thread."""
    thread_local = threading.local()

    def transport_send(
        url: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if not hasattr(thread_local, "client"):
            thread_local.client = TestClient(app)
        client = thread_local.client

        parsed = urlparse(url)
        path = parsed.path
        if parsed.query:
            path = f"{path}?{parsed.query}"
        body = payload if payload is not None else data

        if method.upper() == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path, json=body)

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
    port: Optional[int] = None,
    host: str = "127.0.0.1",
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


def test_e2e_single_worker_lifecycle_fastapi_testclient(tmp_path: Path):
    """Full single-worker cycle:
    1. Seed catalog with benchmark problems.
    2. Register worker with coordinator.
    3. Lease work unit via multi-armed bandit scheduler.
    4. Discover candidate improvement and verify through SAT verifier.
    5. Atomic commit of new record in SQLite WAL.
    6. Heartbeat credits completed attempts.
    7. Leaderboard reflects worker ranking and records broken.
    8. Global stats aggregate cluster compute effort.
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

    with mock.patch.object(nw, "send_request", side_effect=transport_send):
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
# Workflow 2: Single Worker Lifecycle End-to-End (Live Uvicorn Socket Server)
# ============================================================================


def test_e2e_single_worker_lifecycle_live_uvicorn_socket(tmp_path: Path):
    """Real OS network loopback with standard library urllib:
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
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('4_4_in_4', '4', '4', 4, 5.0, 5.0, 'best_known', 0.99)
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
    wait_for_server_ready(server, port=port)

    server_url = f"http://127.0.0.1:{port}"
    valid_square_coords = [
        -1.3, -1.3, 0.0,
        -1.3,  1.3, 0.0,
         1.3, -1.3, 0.0,
         1.3,  1.3, 0.0,
    ]

    try:
        # 1. Register with real HTTP coordinator over socket loopback
        w_id = register_with_server(server_url, username="socket_bob")
        assert len(w_id) >= 10

        cfg = WorkerConfig(worker_id=w_id, server_url=server_url, cores=1)

        def mock_solver(**kwargs: Any) -> Dict[str, Any]:
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
# Workflow 3: Multi-Worker Cluster Fleet
# ============================================================================


def test_e2e_multi_worker_cluster_fleet(tmp_path: Path):
    """6 worker daemons concurrently leasing work, reporting heartbeats, and submitting
    solutions against coordinator with SQLite WAL mode; verifying 0 deadlocks, fair attempt
    balancing, and accurate cluster stats.
    """
    db_path = str(tmp_path / "fleet_cluster.db")
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', 0.95)
        """
    )
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('4_4_in_square', '4', '4', 4, 5.0, 5.0, 'best_known', 0.90)
        """
    )
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('prob_tri_3', '3', 'CIRCLE', 3, 3.2, 3.2, 'best_known', 0.85)
        """
    )
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('prob_tri_4', '3', 'CIRCLE', 3, 3.4, 3.4, 'best_known', 0.80)
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    transport_send = make_thread_local_transport(app)

    valid_tri = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]
    valid_sq = [-1.3, -1.3, 0.0, -1.3, 1.3, 0.0, 1.3, -1.3, 0.0, 1.3, 1.3, 0.0]

    num_improvements = 0
    imp_lock = threading.Lock()

    def fleet_solver(**kwargs: Any) -> Dict[str, Any]:
        nonlocal num_improvements
        inner_shape = str(kwargs.get("inner_shape", ""))
        with imp_lock:
            if num_improvements < 2:
                num_improvements += 1
                if inner_shape == "4":
                    return {"success": True, "best_s": 4.5, "values": valid_sq}
                else:
                    return {"success": True, "best_s": 2.5, "values": valid_tri}
        return {"success": False, "score": 99.0, "values": []}

    with mock.patch.object(nw, "send_request", side_effect=transport_send):
        # Register 6 worker daemons
        configs = []
        for i in range(6):
            wid = register_with_server("http://localhost:8000", f"fleet_vol_{i}")
            configs.append(WorkerConfig(worker_id=wid, server_url="http://localhost:8000", cores=1))

        # Round 1: 6 workers concurrently lease work (4 unique + 2 shared fallback)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            r1 = list(executor.map(lambda cfg: run_worker_cycle(cfg, solver_fn=fleet_solver), configs))

        assert len(r1) == 6
        assert all(res["status"] == "completed" for res in r1)
        assert all(res["attempts_completed"] == 1000 for res in r1)

        # Round 2: 6 workers lease again, bandit scheduler balances compute on lower attempt problems
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            r2 = list(executor.map(lambda cfg: run_worker_cycle(cfg, solver_fn=fleet_solver), configs))

        assert len(r2) == 6
        assert all(res["status"] == "completed" for res in r2)
        assert all(res["attempts_completed"] == 1000 for res in r2)

    # Verify cluster global stats
    main_client = TestClient(app)
    stats = main_client.get("/api/v1/stats").json()
    assert stats["total_problems"] == 4
    assert stats["active_workers"] == 6
    assert stats["total_attempts"] == 12000  # 6 workers * 1000 * 2 cycles
    assert stats["records_broken"] == 2
    assert stats["verified_solutions"] == 2

    # Verify leaderboard ranking and record distribution
    lb = main_client.get("/api/v1/leaderboard").json()
    assert len(lb) == 6
    records_tally = sum(w["records_broken"] for w in lb)
    attempts_tally = sum(w["total_attempts"] for w in lb)
    assert records_tally == 2
    assert attempts_tally == 12000
    assert lb[0]["records_broken"] == 1
    assert lb[1]["records_broken"] == 1

    # Verify SQLite WAL database consistency
    db_conn = sqlite3.connect(db_path)
    db_conn.row_factory = sqlite3.Row
    c = db_conn.cursor()
    c.execute("SELECT COUNT(*) FROM solutions WHERE is_current_record = 1")
    assert c.fetchone()[0] == 2
    c.execute("SELECT SUM(total_attempts) FROM problems")
    assert c.fetchone()[0] == 12000
    db_conn.close()


# ============================================================================
# Workflow 4: Concurrent Improvement Race
# ============================================================================


def test_e2e_concurrent_improvement_race(tmp_path: Path):
    """Workers race on the same problem:
    - Alice (s=2.90) accepted as new record.
    - Bob (s=2.95) rejected as duplicate (worse than current best).
    - Charlie (s=2.85) accepted as new record.
    Verifies atomic demotion, zero duplicates inserted, and leaderboard ranking.
    """
    db_path = str(tmp_path / "e2e_race.db")
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', 0.95)
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    client = TestClient(app)

    # 1. Register Alice, Bob, and Charlie
    alice_id = client.post("/api/v1/workers/register", json={"username": "race_alice"}).json()["worker_id"]
    bob_id = client.post("/api/v1/workers/register", json={"username": "race_bob"}).json()["worker_id"]
    charlie_id = client.post("/api/v1/workers/register", json={"username": "race_charlie"}).json()["worker_id"]

    # 2. All 3 lease work on 3_3_in_circle
    w_alice = client.get(f"/api/v1/work?worker_id={alice_id}").json()
    w_bob = client.get(f"/api/v1/work?worker_id={bob_id}").json()
    w_charlie = client.get(f"/api/v1/work?worker_id={charlie_id}").json()

    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    # 3. Alice submits s=2.90 -> Accepted, new record!
    r_alice = client.post(
        "/api/v1/solutions",
        json={
            "work_id": w_alice["work_id"],
            "worker_id": alice_id,
            "problem": "3_3_in_circle",
            "s": 2.90,
            "coordinates": valid_coords,
        },
    )
    assert r_alice.status_code == 200
    data_alice = r_alice.json()
    assert data_alice["status"] == "accepted"
    assert data_alice["verified"] is True
    assert data_alice["is_new_record"] is True
    assert abs(data_alice["metric_s"] - 2.90) < 1e-6

    # 4. Bob submits s=2.95 -> Duplicate (2.95 >= 2.90 - 1e-5), rejected as new record
    r_bob = client.post(
        "/api/v1/solutions",
        json={
            "work_id": w_bob["work_id"],
            "worker_id": bob_id,
            "problem": "3_3_in_circle",
            "s": 2.95,
            "coordinates": valid_coords,
        },
    )
    assert r_bob.status_code == 200
    data_bob = r_bob.json()
    assert data_bob["status"] == "duplicate"
    assert data_bob["verified"] is True
    assert data_bob["is_new_record"] is False

    # 5. Charlie submits s=2.85 -> Accepted, new record (2.85 < 2.90 - 1e-5)!
    r_charlie = client.post(
        "/api/v1/solutions",
        json={
            "work_id": w_charlie["work_id"],
            "worker_id": charlie_id,
            "problem": "3_3_in_circle",
            "s": 2.85,
            "coordinates": valid_coords,
        },
    )
    assert r_charlie.status_code == 200
    data_charlie = r_charlie.json()
    assert data_charlie["status"] == "accepted"
    assert data_charlie["verified"] is True
    assert data_charlie["is_new_record"] is True
    assert abs(data_charlie["metric_s"] - 2.85) < 1e-6

    # 6. Verify SQLite database:
    # - exactly 2 solutions inserted (Alice and Charlie, zero for Bob)
    # - Alice's solution demoted (is_current_record = 0)
    # - Charlie's solution active (is_current_record = 1)
    # - problems.best_s == 2.85
    db_conn = sqlite3.connect(db_path)
    db_conn.row_factory = sqlite3.Row
    c = db_conn.cursor()

    c.execute("SELECT best_s FROM problems WHERE id = '3_3_in_circle'")
    assert abs(c.fetchone()["best_s"] - 2.85) < 1e-6

    c.execute("SELECT worker_id, is_current_record, metric_s FROM solutions WHERE problem_id = '3_3_in_circle' ORDER BY id ASC")
    rows = c.fetchall()
    assert len(rows) == 2
    assert rows[0]["worker_id"] == alice_id
    assert rows[0]["is_current_record"] == 0
    assert abs(rows[0]["metric_s"] - 2.90) < 1e-6

    assert rows[1]["worker_id"] == charlie_id
    assert rows[1]["is_current_record"] == 1
    assert abs(rows[1]["metric_s"] - 2.85) < 1e-6

    # 7. Verify leaderboard ranking
    lb = client.get("/api/v1/leaderboard").json()
    assert len(lb) == 3
    worker_ranks = {w["username"]: w["records_broken"] for w in lb}
    assert worker_ranks["race_alice"] == 1
    assert worker_ranks["race_charlie"] == 1
    assert worker_ranks["race_bob"] == 0

    # 8. Verify Problem Detail endpoint
    p_detail = client.get("/api/v1/problems/3_3_in_circle").json()
    assert abs(p_detail["best_s"] - 2.85) < 1e-6
    assert p_detail["coordinates"] == valid_coords
    db_conn.close()


# ============================================================================
# Workflow 5: Starvation & Backoff Recovery
# ============================================================================


def test_e2e_starvation_and_backoff_recovery(tmp_path: Path):
    """Catalog with only proved_optimal problems returns HTTP 204 No Content;
    worker enters idle backoff sleep; delayed release of non-optimal problem allows seamless recovery.
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
    conn.close()

    app = create_app(db_path=db_path)
    client = TestClient(app)
    transport_send = make_testclient_transport(client)

    # Background thread to release eligible non-optimal work after brief starvation interval
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

    with mock.patch.object(nw, "send_request", side_effect=transport_send):
        w_id = register_with_server("http://localhost:8000", username="starved_worker")
        cfg = WorkerConfig(worker_id=w_id, server_url="http://localhost:8000", poll_interval=0.15)

        # Run multi-cycle loop: Cycle 1 must starve (idle), Cycle 2 must recover (completed)
        history = run_worker_loop(
            cfg,
            max_cycles=2,
            solver_fn=lambda **kw: {"success": True, "best_s": 2.5, "values": valid_coords},
        )

    release_thread.join(timeout=2.0)

    assert len(history) == 2
    assert history[0]["status"] == "idle"
    assert history[0]["attempts_completed"] == 0
    assert history[0]["found_improvement"] is False

    assert history[1]["status"] == "completed"
    assert history[1]["attempts_completed"] == 1000
    assert history[1]["found_improvement"] is True


# ============================================================================
# Workflow 6: In-Process Signal Interruption & Graceful Heartbeat Flush
# ============================================================================


def test_e2e_signal_interruption_in_process_graceful_shutdown(tmp_path: Path):
    """In-process signal delivery (handle_signal), thread unblocking,
    and in-flight attempt flush to coordinator database.
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

    with mock.patch.object(nw, "send_request", side_effect=transport_send):
        w_id = register_with_server("http://localhost:8000", username="sig_interrupted_worker")
        cfg = WorkerConfig(worker_id=w_id, server_url="http://localhost:8000", poll_interval=5.0)

        # Obtain lease
        work_unit = transport_send("http://localhost:8000/api/v1/work?worker_id=" + w_id)
        work_id = work_unit["work_id"]

        # Track 1500 in-flight attempts completed before signal arrives
        set_in_flight_work(work_id=work_id, attempts=1500, best_s=2.85)

        # Simulate SIGINT signal delivery
        handle_signal(signal.SIGINT, None)
        assert nw._SHUTDOWN is True
        assert nw._GLOBAL_STOP_EVENT.is_set()

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
# Workflow 7: Subprocess OS Signal Interruption & CLI Daemon Graceful Exit
# ============================================================================


def test_e2e_signal_interruption_subprocess_cli_daemon(tmp_path: Path):
    """Genuine OS process SIGINT delivery to subprocess.Popen running
    shape_packing.client.native_worker, clean exit code 0, and coordinator database verification.
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
    wait_for_server_ready(server, port=port)

    server_url = f"http://127.0.0.1:{port}"

    proc: Optional[subprocess.Popen] = None
    try:
        proc_kwargs: Dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "env": {**os.environ, "PYTHONPATH": "src"},
        }
        if sys.platform == "win32":
            proc_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

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
            **proc_kwargs,
        )

        # Allow worker daemon to register and begin loop
        time.sleep(0.8)

        # Deliver real OS SIGINT / CTRL_BREAK
        if sys.platform == "win32":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
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
                proc.wait(timeout=2.0)
            except Exception:
                pass
        server.should_exit = True
        server_thread.join(timeout=2.0)


# ============================================================================
# Workflow 8: Invalid Geometry Rejection & Attempt Telemetry Preservation
# ============================================================================


def test_e2e_invalid_geometry_rejected_and_attempts_preserved(tmp_path: Path):
    """In-process SAT verifier detects overlapping polygons and returns HTTP 400;
    database remains uncorrupted while attempt telemetry is preserved and credited.
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

    def mock_invalid_solver(**kwargs: Any) -> Dict[str, Any]:
        return {"success": True, "best_s": 2.5, "values": overlapping_coords}

    with mock.patch.object(nw, "send_request", side_effect=transport_send):
        w_id = register_with_server("http://localhost:8000", username="overlap_worker")
        cfg = WorkerConfig(worker_id=w_id, server_url="http://localhost:8000", cores=1)

        # Worker cycle will raise urllib.error.HTTPError from coordinator's 400 rejection
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            run_worker_cycle(cfg, solver_fn=mock_invalid_solver)

        assert exc_info.value.code == 400
        assert "overlap" in getattr(exc_info.value, "error_body", "").lower()

    # Verify best_s was NOT corrupted in coordinator database
    db_conn = sqlite3.connect(db_path)
    db_conn.row_factory = sqlite3.Row
    c = db_conn.cursor()
    c.execute("SELECT best_s, total_attempts FROM problems WHERE id = '3_3_in_circle'")
    prob_row = c.fetchone()
    assert prob_row["best_s"] == 3.0
    # Telemetry credited: 1000 attempts completed during batch
    assert prob_row["total_attempts"] == 1000

    # Worker attempts credited despite solution rejection
    c.execute("SELECT total_attempts, records_broken FROM workers WHERE id = ?", (w_id,))
    w_row = c.fetchone()
    assert w_row["total_attempts"] == 1000
    assert w_row["records_broken"] == 0

    # Zero solutions inserted into database
    c.execute("SELECT COUNT(*) FROM solutions")
    assert c.fetchone()[0] == 0

    # Subsequent valid solution succeeds and updates database cleanly
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    def mock_valid_solver(**kwargs: Any) -> Dict[str, Any]:
        return {"success": True, "best_s": 2.5, "values": valid_coords}

    with mock.patch.object(nw, "send_request", side_effect=transport_send):
        res2 = run_worker_cycle(cfg, solver_fn=mock_valid_solver)
        assert res2["status"] == "completed"
        assert res2["found_improvement"] is True
        assert res2["metric_s"] == 2.5

    c.execute("SELECT best_s, total_attempts FROM problems WHERE id = '3_3_in_circle'")
    prob_row2 = c.fetchone()
    assert abs(prob_row2["best_s"] - 2.5) < 1e-6
    assert prob_row2["total_attempts"] == 2000

    c.execute("SELECT total_attempts, records_broken FROM workers WHERE id = ?", (w_id,))
    w_row2 = c.fetchone()
    assert w_row2["total_attempts"] == 2000
    assert w_row2["records_broken"] == 1
    db_conn.close()


# ============================================================================
# Workflow 9: Real Benchmark Catalog File Ingestion & Leasing
# ============================================================================


def test_e2e_real_verification_file_catalog_seeding(tmp_path: Path):
    """Ingestion of real benchmark files from data/packingVerification/*.json,
    seeding >2,200 problems into SQLite WAL, and leasing an unattempted problem to worker.
    """
    catalog_path = "data/packingVerification"
    if not Path(catalog_path).exists():
        pytest.skip(f"Benchmark catalog {catalog_path} not found.")

    db_path = str(tmp_path / "e2e_real_catalog.db")
    conn = init_db(db_path)

    # 1. Verify SQLite WAL mode
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    assert cursor.fetchone()[0].lower() == "wal"

    # 2. Seed real benchmark catalog
    parsed_count = seed_problems_from_verification(conn, catalog_path)
    assert parsed_count > 2200

    cursor.execute("SELECT COUNT(*) FROM problems")
    stored_count = cursor.fetchone()[0]
    assert stored_count > 2200

    # 3. Verify unattempted problems exist
    cursor.execute("SELECT COUNT(*) FROM problems WHERE total_attempts = 0")
    unattempted_count = cursor.fetchone()[0]
    assert unattempted_count > 2000
    conn.close()

    # 4. Coordinator app leasing an unattempted benchmark problem
    app = create_app(db_path=db_path)
    client = TestClient(app)

    reg_resp = client.post("/api/v1/workers/register", json={"username": "real_catalog_worker"})
    assert reg_resp.status_code == 200
    w_id = reg_resp.json()["worker_id"]

    work_resp = client.get(f"/api/v1/work?worker_id={w_id}&cores=2")
    assert work_resp.status_code == 200
    work = work_resp.json()

    assert work["work_id"] is not None
    assert work["problem"] is not None
    assert work["inner_token"] is not None
    assert work["container_token"] is not None
    assert work["recommended_attempts"] == 2000

    # 5. Report attempt telemetry via heartbeat
    hb_resp = client.post(
        "/api/v1/heartbeat",
        json={
            "work_id": work["work_id"],
            "worker_id": w_id,
            "attempts_completed": 2000,
        },
    )
    assert hb_resp.status_code == 200
    assert hb_resp.json()["status"] == "recorded"

    # 6. Verify coordinator database recorded attempts
    db_conn = sqlite3.connect(db_path)
    db_conn.row_factory = sqlite3.Row
    c = db_conn.cursor()
    c.execute("SELECT total_attempts FROM workers WHERE id = ?", (w_id,))
    assert c.fetchone()["total_attempts"] == 2000

    c.execute("SELECT total_attempts FROM problems WHERE id = ?", (work["problem"],))
    assert c.fetchone()["total_attempts"] == 2000
    db_conn.close()
