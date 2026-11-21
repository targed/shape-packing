"""Adversarial concurrency, signal lifecycle, and multi-worker stress test suite.

Empirically tests:
1. Multi-threaded HeartbeatReporter stress under high concurrency (10 threads, record + flush, transient network drops).
2. SIGINT and SIGTERM simulated interruption during active solve batch (signal catching, stop event set, prompt termination, in-flight flush behavior).
3. Multi-worker simulated fleet (4 workers leasing work and reporting heartbeats concurrently against coordinator, 0 deadlocks, 0 unexpected errors).
"""

from __future__ import annotations

import os
import random
import signal
import socket
import sqlite3
import sys
import threading
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import src.shape_packing.client.native_worker as nw
from src.shape_packing.client.native_worker import (
    HeartbeatReporter,
    WorkerConfig,
    flush_in_flight_heartbeat,
    handle_signal,
    register_with_server,
    run_worker_cycle,
    run_worker_loop,
    send_request,
    set_in_flight_work,
    setup_signal_handlers,
)
from shape_packing.server.app import create_app, get_db
from shape_packing.server.database import init_db


@pytest.fixture(autouse=True)
def clean_worker_global_state():
    """Reset worker global state before and after every test."""
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


# ============================================================================
# Vector 1: Multi-Threaded HeartbeatReporter Stress (10 Concurrent Threads)
# ============================================================================


def test_heartbeat_reporter_10_thread_stress_no_lost_attempts():
    """Vector 1: 10 concurrent threads simultaneously recording attempts and flushing.

    Asserts that total_attempts recorded equals exactly the sum of increments (0 lost attempts).
    """
    flushed_payloads: List[Dict[str, Any]] = []
    capture_lock = threading.Lock()

    def mock_request(url: str, method: str = "POST", payload: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        time.sleep(random.uniform(0.0001, 0.001))
        if payload and "attempts_completed" in payload:
            with capture_lock:
                flushed_payloads.append(payload)
        return {"status": "recorded"}

    reporter = HeartbeatReporter(
        server_url="http://localhost:8000",
        worker_id="w_stress_10",
        work_id="wu_stress_10",
        interval_seconds=60.0,
        request_fn=mock_request,
    )

    num_threads = 10
    increments_per_thread = 200
    thread_increments = [0] * num_threads

    def worker_action(thread_idx: int) -> None:
        local_sum = 0
        for _ in range(increments_per_thread):
            count = random.randint(1, 50)
            local_sum += count
            reporter.record_attempts(count, best_s=random.uniform(2.0, 10.0))
            if random.random() < 0.25:
                reporter.flush()
        thread_increments[thread_idx] = local_sum

    threads = [
        threading.Thread(target=worker_action, args=(i,), name=f"StressThread-{i}")
        for i in range(num_threads)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    # All threads must finish cleanly
    assert all(not t.is_alive() for t in threads), "Threads timed out or deadlocked"

    # Final force flush
    reporter.flush(force=True)

    expected_total = sum(thread_increments)
    actual_flushed = sum(p["attempts_completed"] for p in flushed_payloads)

    assert expected_total > 0
    assert actual_flushed == expected_total, (
        f"Mismatch in total attempts! Expected {expected_total}, got {actual_flushed} "
        f"(difference: {actual_flushed - expected_total})"
    )


def test_heartbeat_reporter_stress_with_transient_network_drops():
    """Vector 1: 10 concurrent threads with 15% random network drop rate.

    Verifies retry re-credit logic under concurrency: unacknowledged attempts must not be dropped.
    """
    flushed_payloads: List[Dict[str, Any]] = []
    capture_lock = threading.Lock()

    def unreliable_request(url: str, method: str = "POST", payload: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        time.sleep(random.uniform(0.0001, 0.0008))
        if random.random() < 0.15:
            raise ConnectionResetError("Simulated socket drop")
        if payload and "attempts_completed" in payload:
            with capture_lock:
                flushed_payloads.append(payload)
        return {"status": "recorded"}

    reporter = HeartbeatReporter(
        server_url="http://localhost:8000",
        worker_id="w_drop_10",
        work_id="wu_drop_10",
        interval_seconds=60.0,
        request_fn=unreliable_request,
    )

    num_threads = 10
    increments_per_thread = 150
    thread_increments = [0] * num_threads

    def worker_action(thread_idx: int) -> None:
        local_sum = 0
        for _ in range(increments_per_thread):
            count = random.randint(1, 30)
            local_sum += count
            reporter.record_attempts(count)
            if random.random() < 0.3:
                reporter.flush()
        thread_increments[thread_idx] = local_sum

    threads = [
        threading.Thread(target=worker_action, args=(i,))
        for i in range(num_threads)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    # Switch to reliable transport for final flush of retried attempts
    def reliable_request(url: str, method: str = "POST", payload: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        if payload and "attempts_completed" in payload:
            with capture_lock:
                flushed_payloads.append(payload)
        return {"status": "recorded"}

    reporter.request_fn = reliable_request
    reporter.flush(force=True)

    expected_total = sum(thread_increments)
    actual_flushed = sum(p["attempts_completed"] for p in flushed_payloads)

    assert actual_flushed == expected_total, (
        f"Transient drops caused lost attempts! Expected {expected_total}, got {actual_flushed}"
    )


def test_heartbeat_reporter_best_s_concurrent_min_tracking():
    """Vector 1: Concurrent best_s tracking must monotonically reflect the global minimum."""
    reporter = HeartbeatReporter(
        server_url="http://localhost:8000",
        worker_id="w_min",
        work_id="wu_min",
        request_fn=lambda *a, **k: {},
    )

    scores: List[float] = [random.uniform(1.0, 50.0) for _ in range(500)]
    threads = []

    def score_recorder(sub_scores: List[float]) -> None:
        for s in sub_scores:
            reporter.record_attempts(1, best_s=s)

    chunk_size = 50
    for i in range(10):
        chunk = scores[i * chunk_size : (i + 1) * chunk_size]
        t = threading.Thread(target=score_recorder, args=(chunk,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=5.0)

    expected_min = min(scores)
    assert reporter._best_local_s is not None
    assert abs(reporter._best_local_s - expected_min) < 1e-9


# ============================================================================
# Vector 2: SIGINT / SIGTERM Interruption During Active Solve Batch
# ============================================================================


def test_sigint_interruption_during_active_solve_batch():
    """Vector 2: Trigger SIGINT midway through active solve batch.

    Verifies:
    a. Signal is caught.
    b. _SHUTDOWN / _GLOBAL_STOP_EVENT is set.
    c. In-flight heartbeat is flushed with completed attempts.
    d. Worker terminates promptly without hanging (< 2.0s).
    """
    config = WorkerConfig(worker_id="w_sigint_test", server_url="http://coord:8000")
    flushed_heartbeats: List[Dict[str, Any]] = []

    def mock_request(url: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        if "work" in url:
            return {
                "work_id": "wu_sigint_active",
                "problem": "3_3_in_circle",
                "n": 3,
                "recommended_attempts": 2000,
                "target_s": 3.0,
            }
        elif "heartbeat" in url:
            if payload:
                flushed_heartbeats.append(payload)
            return {"status": "recorded"}
        return {}

    attempts_completed_before_signal = 0

    def active_solver(**kwargs) -> Dict[str, Any]:
        nonlocal attempts_completed_before_signal
        for i in range(20):
            if nw._SHUTDOWN or nw._GLOBAL_STOP_EVENT.is_set():
                break
            attempts_completed_before_signal += 50
            set_in_flight_work("wu_sigint_active", attempts_completed_before_signal, 3.25)
            time.sleep(0.04)
        return {"success": False, "score": 3.25}

    def trigger_sigint_after_delay() -> None:
        time.sleep(0.12)
        # Signal handler invocation
        handle_signal(signal.SIGINT, None)

    signal_thread = threading.Thread(target=trigger_sigint_after_delay, daemon=True)
    signal_thread.start()

    t_start = time.time()
    try:
        history = run_worker_loop(
            config,
            max_cycles=5,
            solver_fn=active_solver,
            request_fn=mock_request,
        )
    finally:
        flush_in_flight_heartbeat(config, request_fn=mock_request)
        signal_thread.join(timeout=2.0)
    elapsed = time.time() - t_start

    # (a) Signal is caught
    # (b) _SHUTDOWN / _GLOBAL_STOP_EVENT is set
    assert nw._SHUTDOWN is True, "Shutdown flag was not set"
    assert nw._GLOBAL_STOP_EVENT.is_set(), "Global stop event was not set"

    # (d) Worker terminates promptly without hanging (< 2.0s)
    assert elapsed < 2.0, f"Worker loop hung! Took {elapsed:.2f}s to terminate"

    # (c) In-flight heartbeat telemetry was emitted
    assert len(flushed_heartbeats) >= 1, "No heartbeat was emitted upon shutdown"
    total_flushed_attempts = sum(h["attempts_completed"] for h in flushed_heartbeats)
    assert total_flushed_attempts > 0, "Zero attempts were flushed"


def test_sigterm_interruption_during_active_solve_batch():
    """Vector 2: Trigger SIGTERM midway through active solve batch.

    Verifies prompt termination and clean shutdown on SIGTERM.
    """
    config = WorkerConfig(worker_id="w_sigterm_test", server_url="http://coord:8000")
    flushed_heartbeats: List[Dict[str, Any]] = []

    def mock_request(url: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        if "work" in url:
            return {
                "work_id": "wu_sigterm_active",
                "problem": "3_3_in_circle",
                "n": 3,
                "recommended_attempts": 3000,
                "target_s": 3.0,
            }
        elif "heartbeat" in url:
            if payload:
                flushed_heartbeats.append(payload)
            return {"status": "recorded"}
        return {}

    def active_solver(**kwargs) -> Dict[str, Any]:
        for i in range(25):
            if nw._SHUTDOWN or nw._GLOBAL_STOP_EVENT.is_set():
                break
            set_in_flight_work("wu_sigterm_active", (i + 1) * 40, 3.10)
            time.sleep(0.03)
        return {"success": False, "score": 3.10}

    def trigger_sigterm_after_delay() -> None:
        time.sleep(0.10)
        handle_signal(signal.SIGTERM, None)

    signal_thread = threading.Thread(target=trigger_sigterm_after_delay, daemon=True)
    signal_thread.start()

    t_start = time.time()
    try:
        run_worker_loop(
            config,
            max_cycles=5,
            solver_fn=active_solver,
            request_fn=mock_request,
        )
    finally:
        flush_in_flight_heartbeat(config, request_fn=mock_request)
        signal_thread.join(timeout=2.0)
    elapsed = time.time() - t_start

    assert nw._SHUTDOWN is True
    assert nw._GLOBAL_STOP_EVENT.is_set()
    assert elapsed < 2.0, f"Worker loop hung! Took {elapsed:.2f}s"
    assert len(flushed_heartbeats) >= 1


def test_interruption_with_exception_in_flight_flush_vulnerability():
    """Vector 2 (Adversarial Edge Case): Exposing in-flight attempt loss on exception.

    Empirically demonstrates:
    When a solve batch is interrupted by an exception (e.g. InterruptedError),
    HeartbeatReporter.stop() calls flush(force=True), which calls
    set_in_flight_work(self.work_id, 0, None) with 0 attempts, wiping out
    the completed in-flight progress stored in _IN_FLIGHT_STATE.
    """
    config = WorkerConfig(worker_id="w_vuln", server_url="http://coord:8000")
    flushed_heartbeats: List[Dict[str, Any]] = []

    def mock_request(url: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        if "work" in url:
            return {
                "work_id": "wu_vuln_batch",
                "problem": "3_3_in_circle",
                "n": 3,
                "recommended_attempts": 2000,
                "target_s": 3.0,
            }
        elif "heartbeat" in url:
            if payload:
                flushed_heartbeats.append(payload)
            return {"status": "recorded"}
        return {}

    def interrupting_solver(**kwargs) -> Dict[str, Any]:
        # Completed 350 attempts before being interrupted
        set_in_flight_work("wu_vuln_batch", 350, 2.95)
        handle_signal(signal.SIGINT, None)
        raise InterruptedError("Batch interrupted by OS signal")

    try:
        run_worker_loop(
            config,
            max_cycles=1,
            solver_fn=interrupting_solver,
            request_fn=mock_request,
        )
    finally:
        # main() calls flush_in_flight_heartbeat in finally block
        flush_in_flight_heartbeat(config, request_fn=mock_request)

    # Total attempts flushed across all heartbeats
    total_flushed = sum(h["attempts_completed"] for h in flushed_heartbeats)

    # Document the empirical finding:
    # Notice: HeartbeatReporter.stop() flushed 0 attempts and wiped out _IN_FLIGHT_STATE,
    # so the 350 completed attempts were not flushed.
    assert total_flushed == 0, (
        "Expected 0 due to in-flight wipeout bug in reporter.stop()"
    )


# ============================================================================
# Vector 3: Multi-Worker Simulated Fleet Against Coordinator (4 Workers)
# ============================================================================


def test_multi_worker_fleet_fastapi_testclient(tmp_path):
    """Vector 3: 4 worker daemons running concurrently against FastAPI TestClient.

    Verifies:
    - 0 deadlocks across workers
    - 0 duplicate unexpected errors
    - Multi-worker concurrent leasing and heartbeat emission
    """
    db_path = str(tmp_path / "fleet_tc.db")
    conn = init_db(db_path)
    cursor = conn.cursor()
    # Insert 10 benchmark problems
    for i in range(10):
        cursor.execute(
            """
            INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
            VALUES (?, '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', ?)
            """,
            (f"fleet_prob_{i}", 0.50 + i * 0.04),
        )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    client = TestClient(app)

    transport_lock = threading.Lock()

    def thread_safe_mock_send(url: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
        from urllib.parse import urlparse
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
        else:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

    num_workers = 4
    cycles_per_worker = 3
    worker_errors: List[Tuple[int, Exception]] = []
    worker_histories: Dict[int, List[Dict[str, Any]]] = {}

    with patch.object(nw, "send_request", side_effect=thread_safe_mock_send):
        configs = []
        for i in range(num_workers):
            wid = register_with_server("http://localhost:8000", username=f"fleet_vol_{i}")
            configs.append(WorkerConfig(worker_id=wid, server_url="http://localhost:8000", poll_interval=0.1))

        def worker_runner(w_idx: int, cfg: WorkerConfig) -> None:
            try:
                hist = run_worker_loop(
                    cfg,
                    max_cycles=cycles_per_worker,
                    solver_fn=lambda **kw: {"success": False, "score": 3.8, "values": []},
                    request_fn=thread_safe_mock_send,
                )
                worker_histories[w_idx] = hist
            except Exception as exc:
                worker_errors.append((w_idx, exc))

        threads = [
            threading.Thread(target=worker_runner, args=(i, configs[i]), name=f"WorkerThread-{i}")
            for i in range(num_workers)
        ]

        t0 = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)
        elapsed = time.time() - t0

    # 1. 0 Deadlocks
    assert all(not t.is_alive() for t in threads), "Deadlock detected: worker threads timed out"

    # 2. 0 Unexpected errors
    assert len(worker_errors) == 0, f"Worker fleet encountered errors: {worker_errors}"

    # 3. All cycles completed
    for i in range(num_workers):
        assert len(worker_histories.get(i, [])) == cycles_per_worker, (
            f"Worker {i} did not complete {cycles_per_worker} cycles"
        )


def test_multi_worker_fleet_live_server_with_thread_override(tmp_path):
    """Vector 3: 4 workers running against a live uvicorn HTTP server over real sockets.

    Uses dependency_override for get_db (check_same_thread=False) to test the native worker
    networking stack, socket requests, and multi-worker concurrent leasing over loopback.
    """
    import uvicorn

    # Ephemeral free port
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    db_path = str(tmp_path / "fleet_live.db")
    conn = init_db(db_path)
    cursor = conn.cursor()
    for i in range(12):
        cursor.execute(
            """
            INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
            VALUES (?, '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', ?)
            """,
            (f"live_prob_{i}", 0.50 + i * 0.03),
        )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)

    # Dependency override for thread-safe SQLite connection in WAL mode
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

    server_thread = threading.Thread(target=server.run, daemon=True, name="UvicornServer")
    server_thread.start()

    # Wait for server readiness
    time.sleep(0.5)

    base_url = f"http://127.0.0.1:{port}"
    num_workers = 4
    cycles_per_worker = 2
    worker_errors: List[Tuple[int, Exception]] = []
    worker_histories: Dict[int, List[Dict[str, Any]]] = {}

    try:
        configs = []
        for i in range(num_workers):
            wid = register_with_server(base_url, username=f"live_vol_{i}")
            configs.append(WorkerConfig(worker_id=wid, server_url=base_url, poll_interval=0.1))

        def worker_runner(w_idx: int, cfg: WorkerConfig) -> None:
            try:
                hist = run_worker_loop(
                    cfg,
                    max_cycles=cycles_per_worker,
                    solver_fn=lambda **kw: {"success": False, "score": 3.9, "values": []},
                )
                worker_histories[w_idx] = hist
            except Exception as exc:
                worker_errors.append((w_idx, exc))

        threads = [
            threading.Thread(target=worker_runner, args=(i, configs[i]), name=f"LiveWorker-{i}")
            for i in range(num_workers)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        # 0 deadlocks
        assert all(not t.is_alive() for t in threads), "Live workers deadlocked or timed out"

        # 0 unexpected errors
        assert len(worker_errors) == 0, f"Errors encountered: {worker_errors}"

        # All completed
        for i in range(num_workers):
            assert len(worker_histories.get(i, [])) == cycles_per_worker

    finally:
        server.should_exit = True
        server_thread.join(timeout=2.0)
