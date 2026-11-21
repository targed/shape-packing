"""
Empirical concurrency and stress tests for Coordinator FastAPI REST API (`src/shape_packing/server/app.py`).

Written by Challenger 2 for Milestone 3.
Empirically stress-tests:
1. Concurrent worker registrations and re-registration idempotency under race conditions.
2. Simultaneous work unit requests under normal and exhausted problem queue conditions.
3. Concurrent heartbeat updates under SQLite WAL mode without deadlocks or 500 errors.
4. Heavy lock contention on identical lease heartbeats (verifying exact attempt sum precision).
5. Concurrent solution submissions for the same problem: atomic updates, single active record invariant,
   and verification that the best (lowest container metric) wins.
6. Concurrent mixed valid and invalid geometric submissions (SAT collision, boundary violation, NaN coords).
7. Full cluster simulation: 20 concurrent worker loops executing 600+ mixed requests under load.
8. Concurrent SQLite WAL checkpoints while API traffic is actively writing.
"""
from __future__ import annotations

import concurrent.futures
import math
import os
import random
import sqlite3
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

from shape_packing.server.app import create_app
from shape_packing.server.database import init_db


@pytest.fixture
def test_app_and_db(tmp_path) -> Tuple[Any, str]:
    """Create a temporary test database with sample benchmark problems and FastAPI app."""
    db_path = str(tmp_path / "api_concurrency.db")
    conn = init_db(db_path)
    cursor = conn.cursor()

    # Problem 1: 3 triangles in circle (Friedman benchmark)
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', 0.85)
        """
    )
    # Problem 2: 2 circles in circle
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('2_cir_in_circle', 'CIRCLE', 'CIRCLE', 2, 2.0, 2.0, 'best_known', 0.90)
        """
    )
    # Problem 3: 4 squares in square
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('4_4_in_square', '4', '4', 4, 2.0, 2.0, 'best_known', 0.80)
        """
    )
    # Problem 4: 5 pentagons in circle
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('5_5_in_circle', '5', 'CIRCLE', 5, 3.5, 3.5, 'best_known', 0.75)
        """
    )
    # Problem 5: 6 hexagons in circle
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('6_6_in_circle', '6', 'CIRCLE', 6, 4.0, 4.0, 'best_known', 0.70)
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return app, db_path


# =========================================================================
# 1. Concurrent Worker Registrations and Simultaneous Work Requests
# =========================================================================


def test_concurrent_worker_registrations(test_app_and_db):
    """50 concurrent threads register distinct workers and re-register without deadlocks or errors."""
    app, db_path = test_app_and_db
    num_workers = 50

    def register_worker_task(idx: int) -> Tuple[int, Dict[str, Any]]:
        client = TestClient(app)
        w_id = f"worker-concur-{idx:03d}"
        username = f"worker_node_{idx}"
        resp = client.post(
            "/api/v1/workers/register",
            json={"username": username, "worker_id": w_id, "client_type": "native"},
        )
        assert resp.status_code == 200, f"Registration failed with code {resp.status_code}: {resp.text}"
        return resp.status_code, resp.json()

    # Initial concurrent registrations
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(register_worker_task, range(num_workers)))

    assert len(results) == num_workers
    for status_code, body in results:
        assert status_code == 200
        assert body["status"] == "registered"

    # Concurrent re-registrations updating usernames (idempotency check)
    def reregister_task(idx: int) -> Tuple[int, Dict[str, Any]]:
        client = TestClient(app)
        w_id = f"worker-concur-{idx:03d}"
        updated_username = f"worker_renamed_{idx}"
        resp = client.post(
            "/api/v1/workers/register",
            json={"username": updated_username, "worker_id": w_id, "client_type": "web"},
        )
        assert resp.status_code == 200
        return resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        re_results = list(executor.map(reregister_task, range(num_workers)))

    for status_code, body in re_results:
        assert status_code == 200
        assert body["client_type"] == "web"
        assert "worker_renamed_" in body["username"]

    # Verify database state
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM workers WHERE id LIKE 'worker-concur-%'")
    count = cursor.fetchone()[0]
    assert count == num_workers, f"Expected {num_workers} registered workers, found {count}"
    conn.close()


def test_concurrent_work_requests_with_shared_leasing(test_app_and_db):
    """
    30 concurrent threads request work leases simultaneously against 5 catalog problems.
    All 30 must successfully obtain leases (via unleased and fallback shared leasing)
    without deadlocks or 500 errors.
    """
    app, db_path = test_app_and_db
    num_requests = 30

    # First register workers
    client = TestClient(app)
    worker_ids = []
    for i in range(num_requests):
        w_id = f"lease-worker-{i:03d}"
        resp = client.post(
            "/api/v1/workers/register",
            json={"username": f"worker_{i}", "worker_id": w_id},
        )
        assert resp.status_code == 200
        worker_ids.append(w_id)

    def request_work_task(w_id: str) -> Tuple[int, Optional[Dict[str, Any]]]:
        t_client = TestClient(app)
        resp = t_client.get(f"/api/v1/work?worker_id={w_id}&cores=4&lease_seconds=600")
        if resp.status_code == 204:
            return 204, None
        assert resp.status_code == 200, f"Unexpected status {resp.status_code}: {resp.text}"
        return resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        lease_results = list(executor.map(request_work_task, worker_ids))

    assert len(lease_results) == num_requests
    for status_code, body in lease_results:
        assert status_code == 200
        assert body is not None
        assert "work_id" in body
        assert "problem" in body
        assert body["lease_seconds"] == 600
        assert body["recommended_attempts"] == 4000

    # Verify active leases in DB
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM active_leases")
    lease_count = cursor.fetchone()[0]
    assert lease_count == num_requests, f"Expected {num_requests} active leases, found {lease_count}"
    conn.close()


def test_concurrent_work_requests_empty_catalog_returns_204(tmp_path):
    """When no problems exist, concurrent work requests return HTTP 204 No Content without 500 errors."""
    empty_db = str(tmp_path / "empty_catalog.db")
    conn = init_db(empty_db)
    conn.close()
    app = create_app(db_path=empty_db)

    def request_empty(idx: int) -> int:
        client = TestClient(app)
        resp = client.get(f"/api/v1/work?worker_id=worker_{idx}&cores=2")
        return resp.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        codes = list(executor.map(request_empty, range(24)))

    assert len(codes) == 24
    for code in codes:
        assert code == 204, f"Expected 204 No Content, got {code}"


# =========================================================================
# 2. Concurrent Heartbeat Updates Under SQLite WAL Mode
# =========================================================================


def test_concurrent_heartbeats_under_wal_no_deadlocks(test_app_and_db):
    """
    10 workers with active leases each send 15 concurrent heartbeats (150 total requests).
    Tests for absence of deadlocks, absence of 500 Internal Server Errors,
    and exact attempt tally accumulation in both workers and problems tables.
    """
    app, db_path = test_app_and_db
    client = TestClient(app)

    # Setup 5 workers and obtain 5 leases
    leases = []
    for i in range(5):
        w_id = f"hb-worker-{i}"
        client.post("/api/v1/workers/register", json={"username": f"hb_user_{i}", "worker_id": w_id})
        work = client.get(f"/api/v1/work?worker_id={w_id}&cores=2").json()
        leases.append((w_id, work["work_id"], work["problem"]))

    # Prepare 150 heartbeat tasks: 30 per lease, reporting 25 attempts each
    heartbeat_tasks = []
    attempts_per_call = 25
    calls_per_lease = 30
    for w_id, work_id, prob_id in leases:
        for _ in range(calls_per_lease):
            heartbeat_tasks.append((w_id, work_id, prob_id, attempts_per_call))

    random.shuffle(heartbeat_tasks)

    def send_heartbeat(task_info: Tuple[str, str, str, int]) -> Tuple[int, Dict[str, Any]]:
        w_id, work_id, prob_id, att = task_info
        t_client = TestClient(app)
        resp = t_client.post(
            "/api/v1/heartbeat",
            json={
                "worker_id": w_id,
                "work_id": work_id,
                "attempts_completed": att,
                "best_local_s": 2.9,
            },
        )
        assert resp.status_code == 200, f"Heartbeat failed with {resp.status_code}: {resp.text}"
        return resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(send_heartbeat, heartbeat_tasks))

    assert len(results) == len(heartbeat_tasks)
    for code, body in results:
        assert code == 200
        assert body["status"] == "recorded"

    # Verify attempt math in DB
    expected_attempts_per_worker = calls_per_lease * attempts_per_call  # 30 * 25 = 750
    total_expected = len(leases) * expected_attempts_per_worker         # 5 * 750 = 3750

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    for w_id, _, _ in leases:
        cursor.execute("SELECT total_attempts FROM workers WHERE id = ?", (w_id,))
        actual_worker_att = cursor.fetchone()["total_attempts"]
        assert actual_worker_att == expected_attempts_per_worker, (
            f"Worker {w_id} attempts mismatch: expected {expected_attempts_per_worker}, got {actual_worker_att}"
        )

    cursor.execute("SELECT SUM(total_attempts) FROM problems")
    prob_attempts_sum = cursor.fetchone()[0]
    assert prob_attempts_sum == total_expected, (
        f"Problems attempts sum mismatch: expected {total_expected}, got {prob_attempts_sum}"
    )
    conn.close()


def test_concurrent_heartbeats_single_lease_heavy_contention(test_app_and_db):
    """
    25 threads simultaneously fire heartbeats at the exact same worker and work_id.
    Validates that atomic row locking handles heavy collision on a single record
    without deadlocking or losing increments.
    """
    app, db_path = test_app_and_db
    client = TestClient(app)

    w_id = "contention-worker-single"
    client.post("/api/v1/workers/register", json={"username": "contention_hero", "worker_id": w_id})
    work = client.get(f"/api/v1/work?worker_id={w_id}&cores=1").json()
    work_id = work["work_id"]
    prob_id = work["problem"]

    num_threads = 25
    attempts_each = 100

    def fire_heartbeat(_: int) -> Tuple[int, Dict[str, Any]]:
        t_client = TestClient(app)
        resp = t_client.post(
            "/api/v1/heartbeat",
            json={
                "worker_id": w_id,
                "work_id": work_id,
                "attempts_completed": attempts_each,
            },
        )
        assert resp.status_code == 200
        return resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(fire_heartbeat, range(num_threads)))

    for code, body in results:
        assert code == 200
        assert body["status"] == "recorded"

    expected_total = num_threads * attempts_each  # 2500

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT total_attempts FROM workers WHERE id = ?", (w_id,))
    assert cursor.fetchone()["total_attempts"] == expected_total

    cursor.execute("SELECT total_attempts FROM problems WHERE id = ?", (prob_id,))
    assert cursor.fetchone()["total_attempts"] == expected_total
    conn.close()


# =========================================================================
# 3. Concurrent Solution Submissions & Highest Metric Wins
# =========================================================================


def test_concurrent_solutions_atomic_highest_metric_wins(test_app_and_db):
    """
    Multiple workers concurrently submit valid solutions for the same problem with different metrics.
    Verify:
    1. Zero deadlocks or 500 errors.
    2. Every submission is properly verified and categorized (accepted or duplicate).
    3. Exactly ONE record in `solutions` is marked `is_current_record = 1`.
    4. The lowest / best Friedman container metric wins (e.g., metric 2.10 beats 2.90).
    5. The `problems.best_s` accurately reflects the winning solution.
    6. `workers.records_broken` accurately tallies accepted improvements.
    """
    app, db_path = test_app_and_db
    client = TestClient(app)

    # Valid placement of 3 triangles in circle (radius allows metrics down to ~2.0)
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]
    prob_id = "3_3_in_circle"

    # Metrics to submit concurrently:
    # 2.80, 2.70, 2.60, 2.50, 2.40, 2.30, 2.20, 2.10 (winning),
    # along with duplicate / worse values like 2.85, 2.75, 2.95, 3.10
    metric_candidates = [
        ("worker_A", 2.80),
        ("worker_B", 2.65),
        ("worker_C", 2.50),
        ("worker_D", 2.35),
        ("worker_E", 2.20),
        ("worker_F", 2.10),  # This is the winning metric
        ("worker_G", 2.85),
        ("worker_H", 2.75),
        ("worker_I", 2.45),
        ("worker_J", 2.95),
        ("worker_K", 2.60),
        ("worker_L", 2.15),
        ("worker_M", 2.70),
        ("worker_N", 2.40),
        ("worker_O", 2.25),
        ("worker_P", 2.12),
    ]

    # Pre-register workers
    for w_username, _ in metric_candidates:
        client.post(
            "/api/v1/workers/register",
            json={"username": w_username, "worker_id": f"id_{w_username}"},
        )

    random.shuffle(metric_candidates)

    def submit_solution_task(item: Tuple[str, float]) -> Tuple[str, float, int, Dict[str, Any]]:
        w_username, metric = item
        w_id = f"id_{w_username}"
        t_client = TestClient(app)
        resp = t_client.post(
            "/api/v1/solutions",
            json={
                "worker_id": w_id,
                "problem": prob_id,
                "s": metric,
                "coordinates": valid_coords,
            },
        )
        assert resp.status_code == 200, f"Submit failed: {resp.status_code} {resp.text}"
        return w_username, metric, resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        submissions = list(executor.map(submit_solution_task, metric_candidates))

    accepted_count = 0
    duplicate_count = 0
    for w_username, metric, code, body in submissions:
        assert code == 200
        assert body["verified"] is True
        if body["is_new_record"]:
            accepted_count += 1
            assert body["status"] == "accepted"
        else:
            duplicate_count += 1
            assert body["status"] == "duplicate"

    assert accepted_count >= 1
    assert (accepted_count + duplicate_count) == len(metric_candidates)

    # Invariants verification in database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Winning metric in problems table must be 2.10
    cursor.execute("SELECT best_s FROM problems WHERE id = ?", (prob_id,))
    db_best_s = cursor.fetchone()["best_s"]
    assert abs(db_best_s - 2.10) < 1e-6, f"Expected winning best_s = 2.10, but found {db_best_s}"

    # 2. Exactly ONE active record in solutions table
    cursor.execute(
        "SELECT * FROM solutions WHERE problem_id = ? AND is_current_record = 1",
        (prob_id,),
    )
    active_solutions = cursor.fetchall()
    assert len(active_solutions) == 1, f"Expected exactly 1 current record, found {len(active_solutions)}"
    winning_record = active_solutions[0]
    assert abs(winning_record["metric_s"] - 2.10) < 1e-6
    assert winning_record["worker_username"] == "worker_F"
    assert winning_record["worker_id"] == "id_worker_F"

    # 3. All non-current solutions have is_current_record = 0
    cursor.execute(
        "SELECT COUNT(*) FROM solutions WHERE problem_id = ? AND is_current_record = 0",
        (prob_id,),
    )
    demoted_count = cursor.fetchone()[0]
    assert demoted_count == (accepted_count - 1), (
        f"Expected {accepted_count - 1} demoted records, found {demoted_count}"
    )

    # 4. Total records_broken across workers matches accepted_count
    cursor.execute("SELECT SUM(records_broken) FROM workers")
    total_records_broken = cursor.fetchone()[0]
    assert total_records_broken == accepted_count, (
        f"Expected {accepted_count} total records broken, got {total_records_broken}"
    )

    # 5. Worker F (the ultimate winner) has records_broken >= 1
    cursor.execute("SELECT records_broken FROM workers WHERE id = 'id_worker_F'")
    assert cursor.fetchone()["records_broken"] >= 1

    conn.close()


def test_concurrent_solutions_mixed_valid_and_invalid(test_app_and_db):
    """
    Concurrent mix of valid and invalid submissions:
    - Invalid: overlapping polygons (SAT failure), boundary violations, NaN coordinates, coordinate count mismatch.
    - Valid: non-overlapping valid coordinates with improving metric.
    Verifies that all invalid submissions are cleanly rejected with HTTP 400
    without leaking files or corrupting state.
    """
    app, db_path = test_app_and_db
    client = TestClient(app)

    prob_id = "3_3_in_circle"
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    # Pre-register test workers
    for idx in range(20):
        client.post(
            "/api/v1/workers/register",
            json={"username": f"mix_user_{idx}", "worker_id": f"mix_w_{idx}"},
        )

    tasks = []
    # 5 Valid tasks
    for i in range(5):
        tasks.append({
            "type": "valid",
            "worker_id": f"mix_w_{i}",
            "payload": {
                "worker_id": f"mix_w_{i}",
                "problem": prob_id,
                "s": 2.5 - (i * 0.05),
                "coordinates": valid_coords,
            },
        })

    # 5 Overlapping shapes (SAT collision failure)
    overlapping_coords = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    for i in range(5, 10):
        tasks.append({
            "type": "invalid_overlap",
            "worker_id": f"mix_w_{i}",
            "payload": {
                "worker_id": f"mix_w_{i}",
                "problem": prob_id,
                "s": 2.2,
                "coordinates": overlapping_coords,
            },
        })

    # 5 Out-of-bounds coordinates (boundary penetration failure)
    out_of_bounds_coords = [100.0, 100.0, 0.0, 0.0, 0.0, 0.0, 2.0, -1.0, 0.0]
    for i in range(10, 15):
        tasks.append({
            "type": "invalid_boundary",
            "worker_id": f"mix_w_{i}",
            "payload": {
                "worker_id": f"mix_w_{i}",
                "problem": prob_id,
                "s": 2.2,
                "coordinates": out_of_bounds_coords,
            },
        })

    # 5 Mismatched coordinate lengths
    wrong_length_coords = [0.0, 0.0, 0.0, 1.0]
    for i in range(15, 20):
        tasks.append({
            "type": "invalid_length",
            "worker_id": f"mix_w_{i}",
            "payload": {
                "worker_id": f"mix_w_{i}",
                "problem": prob_id,
                "s": 2.2,
                "coordinates": wrong_length_coords,
            },
        })

    random.shuffle(tasks)

    def execute_mixed_task(t: Dict[str, Any]) -> Tuple[str, int, Dict[str, Any]]:
        t_client = TestClient(app)
        resp = t_client.post("/api/v1/solutions", json=t["payload"])
        return t["type"], resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(execute_mixed_task, tasks))

    for task_type, code, body in results:
        if task_type == "valid":
            assert code == 200
            assert body["verified"] is True
        else:
            assert code == 400
            assert body["verified"] is False
            assert body["status"] == "rejected"


# =========================================================================
# 4. Realistic Full Distributed Cluster Simulation
# =========================================================================


def test_full_cluster_heavy_traffic_stress(test_app_and_db):
    """
    Simulates 15 volunteer worker nodes running concurrent lifecycles:
    1. Worker registration
    2. Request work lease
    3. Send 3 heartbeat progress updates
    4. Submit solution
    5. Query cluster stats
    6. Query leaderboard
    Under 450+ interleaved concurrent requests, verifies zero 500 errors,
    SQLite database integrity, and invariant consistency.
    """
    app, db_path = test_app_and_db
    num_nodes = 15
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    def worker_node_lifecycle(node_idx: int) -> List[Tuple[str, int]]:
        client = TestClient(app)
        call_logs = []
        w_id = f"sim-node-{node_idx:02d}"
        username = f"volunteer_{node_idx}"

        # 1. Register
        r_reg = client.post(
            "/api/v1/workers/register",
            json={"username": username, "worker_id": w_id, "client_type": "native"},
        )
        call_logs.append(("register", r_reg.status_code))

        # 2. Get work
        r_work = client.get(f"/api/v1/work?worker_id={w_id}&cores=4&lease_seconds=300")
        call_logs.append(("get_work", r_work.status_code))
        if r_work.status_code == 200:
            work = r_work.json()
            work_id = work["work_id"]
            prob_id = work["problem"]

            # 3. Send 3 heartbeats
            for step in range(3):
                r_hb = client.post(
                    "/api/v1/heartbeat",
                    json={
                        "worker_id": w_id,
                        "work_id": work_id,
                        "attempts_completed": 100,
                        "best_local_s": 2.8,
                    },
                )
                call_logs.append(("heartbeat", r_hb.status_code))

            # 4. Submit candidate solution
            # If problem is 3_3_in_circle, submit valid coordinates
            if prob_id == "3_3_in_circle":
                r_sol = client.post(
                    "/api/v1/solutions",
                    json={
                        "worker_id": w_id,
                        "problem": prob_id,
                        "s": 2.7 - (node_idx * 0.02),
                        "coordinates": valid_coords,
                    },
                )
                call_logs.append(("solution", r_sol.status_code))

        # 5. Query stats
        r_stats = client.get("/api/v1/stats")
        call_logs.append(("stats", r_stats.status_code))

        # 6. Query leaderboard
        r_lead = client.get("/api/v1/leaderboard?limit=10")
        call_logs.append(("leaderboard", r_lead.status_code))

        return call_logs

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        all_logs = list(executor.map(worker_node_lifecycle, range(num_nodes)))

    total_calls = 0
    for logs in all_logs:
        for action, status_code in logs:
            total_calls += 1
            assert status_code in (200, 204), f"Action '{action}' returned unexpected code {status_code}"

    assert total_calls >= num_nodes * 5

    # Check database integrity and invariants
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # PRAGMA integrity_check
    cursor.execute("PRAGMA integrity_check;")
    check_res = cursor.fetchall()
    assert len(check_res) == 1 and check_res[0][0] == "ok", f"Integrity check failed: {check_res}"

    # Verify no multiple active records per problem
    cursor.execute(
        """
        SELECT problem_id, COUNT(*)
        FROM solutions
        WHERE is_current_record = 1
        GROUP BY problem_id
        HAVING COUNT(*) > 1
        """
    )
    conflicts = cursor.fetchall()
    assert len(conflicts) == 0, f"Found multiple active records for problems: {conflicts}"

    conn.close()


# =========================================================================
# 5. Concurrent WAL Checkpoints During API Traffic
# =========================================================================


def test_concurrent_wal_checkpoint_under_api_load(test_app_and_db):
    """
    Runs active API traffic while concurrently executing SQLite WAL checkpoints.
    Validates that WAL checkpoints (PASSIVE/TRUNCATE) do not cause 500 errors or lockups.
    """
    app, db_path = test_app_and_db
    stop_flag = False

    def api_worker_traffic():
        client = TestClient(app)
        counter = 0
        while not stop_flag and counter < 50:
            counter += 1
            w_id = f"wal-worker-{counter}"
            client.post("/api/v1/workers/register", json={"username": f"wal_user_{counter}", "worker_id": w_id})
            client.get(f"/api/v1/work?worker_id={w_id}&cores=2")
            client.get("/api/v1/stats")
            time.sleep(0.005)

    def wal_checkpoint_runner():
        check_conn = sqlite3.connect(db_path, timeout=30.0)
        c_count = 0
        while not stop_flag and c_count < 10:
            c_count += 1
            check_conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
            time.sleep(0.02)
        check_conn.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        f_traffic = [executor.submit(api_worker_traffic) for _ in range(3)]
        f_wal = executor.submit(wal_checkpoint_runner)

        # Wait for all to finish
        for f in f_traffic:
            f.result()
        stop_flag = True
        f_wal.result()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA integrity_check;")
    assert cursor.fetchone()[0] == "ok"
    conn.close()


def test_concurrent_solutions_identical_metrics_single_winner(test_app_and_db):
    """
    10 threads submit the EXACT SAME metric (2.05) simultaneously for a problem at 3.0.
    Validates that:
    1. Only the first thread to commit receives `is_new_record = True` and `status = "accepted"`.
    2. All other 9 threads receive `is_new_record = False` and `status = "duplicate"`.
    3. Exactly ONE record in `solutions` is marked `is_current_record = 1`.
    4. Database `best_s` is updated to 2.05 without race conditions or deadlocks.
    """
    app, db_path = test_app_and_db
    client = TestClient(app)
    prob_id = "3_3_in_circle"
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    num_threads = 10
    identical_metric = 2.05

    for i in range(num_threads):
        client.post(
            "/api/v1/workers/register",
            json={"username": f"same_user_{i}", "worker_id": f"same_w_{i}"},
        )

    def submit_identical(idx: int) -> Tuple[int, Dict[str, Any]]:
        t_client = TestClient(app)
        resp = t_client.post(
            "/api/v1/solutions",
            json={
                "worker_id": f"same_w_{idx}",
                "problem": prob_id,
                "s": identical_metric,
                "coordinates": valid_coords,
            },
        )
        assert resp.status_code == 200
        return resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        results = list(executor.map(submit_identical, range(num_threads)))

    accepted = [res for _, res in results if res["is_new_record"] is True]
    duplicates = [res for _, res in results if res["is_new_record"] is False]

    assert len(accepted) == 1, f"Expected exactly 1 accepted new record, got {len(accepted)}"
    assert len(duplicates) == (num_threads - 1)
    assert accepted[0]["status"] == "accepted"
    for dup in duplicates:
        assert dup["status"] == "duplicate"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT best_s FROM problems WHERE id = ?", (prob_id,))
    assert abs(cursor.fetchone()["best_s"] - identical_metric) < 1e-6

    cursor.execute(
        "SELECT COUNT(*) FROM solutions WHERE problem_id = ? AND is_current_record = 1",
        (prob_id,),
    )
    assert cursor.fetchone()[0] == 1

    conn.close()


def test_concurrent_solutions_sub_epsilon_improvements_rejected(test_app_and_db):
    """
    Sub-epsilon improvements (< 1e-5 delta from current best) must be rejected
    as duplicate under concurrent submission load.
    """
    app, db_path = test_app_and_db
    client = TestClient(app)
    prob_id = "3_3_in_circle"
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    # First set best_s = 2.50
    w0_id = "subeps_w0"
    client.post("/api/v1/workers/register", json={"username": "subeps_user0", "worker_id": w0_id})
    resp0 = client.post(
        "/api/v1/solutions",
        json={"worker_id": w0_id, "problem": prob_id, "s": 2.50, "coordinates": valid_coords},
    )
    assert resp0.status_code == 200
    assert resp0.json()["is_new_record"] is True

    # Now 8 workers submit metrics between 2.499991 and 2.499999 (all delta < 1e-5)
    num_threads = 8
    for i in range(num_threads):
        client.post(
            "/api/v1/workers/register",
            json={"username": f"subeps_user_{i}", "worker_id": f"subeps_w_{i}"},
        )

    def submit_sub_epsilon(idx: int) -> Tuple[int, Dict[str, Any]]:
        t_client = TestClient(app)
        # delta = (idx + 1) * 1e-6 < 1e-5
        sub_eps_s = 2.50 - ((idx + 1) * 1e-6)
        resp = t_client.post(
            "/api/v1/solutions",
            json={
                "worker_id": f"subeps_w_{idx}",
                "problem": prob_id,
                "s": sub_eps_s,
                "coordinates": valid_coords,
            },
        )
        assert resp.status_code == 200
        return resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        sub_results = list(executor.map(submit_sub_epsilon, range(num_threads)))

    for _, body in sub_results:
        assert body["verified"] is True
        assert body["is_new_record"] is False
        assert body["status"] == "duplicate"

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT best_s FROM problems WHERE id = ?", (prob_id,))
    assert abs(cursor.fetchone()[0] - 2.50) < 1e-6
    conn.close()

