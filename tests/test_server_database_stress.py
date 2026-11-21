"""Empirical stress tests and adversarial edge cases for coordinator database layer.

Authored by Challenger 1 for Milestone 1.
Validates:
1. High-throughput concurrent worker registration and solution updates under WAL mode.
2. Boundary condition metrics (epsilon delta, zero values, negative numbers, NaN/Inf).
3. Seeding behavior under corrupt and extreme benchmark data.
4. Database integrity invariants.
"""
from __future__ import annotations

import concurrent.futures
import json
import math
import os
import random
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List

import pytest

from shape_packing.server.database import (
    RECORD_MIN_IMPROVEMENT,
    get_problem,
    init_db,
    register_worker,
    seed_problems_from_verification,
    update_solution_record,
)


# ===========================================================================
# 1. High-Throughput Concurrency Tests
# ===========================================================================

def test_concurrent_worker_registration_high_throughput(tmp_path: Path):
    """Stress test 50 concurrent threads registering and re-registering workers."""
    db_path = str(tmp_path / "concurrent_reg.db")
    init_db(db_path).close()

    errors: List[str] = []

    def reg_task(thread_id: int):
        conn = init_db(db_path)
        try:
            for i in range(25):
                # Mixture of new worker IDs and re-registrations
                w_id = f"worker_{thread_id}_{i % 5}"
                username = f"user_{thread_id}_v{i}"
                res = register_worker(conn, username, client_type="native", worker_id=w_id)
                assert res["worker_id"] == w_id
        except Exception as exc:
            errors.append(f"Thread {thread_id}: {type(exc).__name__}: {exc}")
        finally:
            conn.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(reg_task, t) for t in range(50)]
        concurrent.futures.wait(futures)

    assert not errors, f"Errors encountered during concurrent registration: {errors[:5]}"

    # Verify database integrity and record counts
    conn = init_db(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check")
    assert cur.fetchone()[0] == "ok"

    cur.execute("SELECT COUNT(*) FROM workers")
    count = cur.fetchone()[0]
    # 50 threads * 5 unique worker_ids = 250 workers
    assert count == 250
    conn.close()


def test_concurrent_solution_updates_hotspot(tmp_path: Path):
    """Stress test 50 threads racing to update records on the EXACT same hotspot problem."""
    db_path = str(tmp_path / "hotspot.db")
    setup_conn = init_db(db_path)
    setup_cur = setup_conn.cursor()
    setup_cur.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_hotspot', '3', '3', 1, 10000.0)"
    )
    setup_conn.commit()
    setup_conn.close()

    errors: List[str] = []
    success_count = [0]
    lock = threading.Lock()

    def racer_task(thread_id: int):
        conn = init_db(db_path)
        try:
            for step in range(30):
                p = get_problem(conn, "p_hotspot")
                if p and p["best_s"] is not None:
                    # Attempt a valid improvement
                    metric = p["best_s"] - 0.05
                    ok = update_solution_record(
                        conn, "p_hotspot", f"worker_{thread_id}", f"user_{thread_id}", metric, [float(step)]
                    )
                    if ok:
                        with lock:
                            success_count[0] += 1
        except Exception as exc:
            with lock:
                errors.append(f"Thread {thread_id}: {type(exc).__name__}: {exc}")
        finally:
            conn.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(racer_task, t) for t in range(50)]
        concurrent.futures.wait(futures)

    assert not errors, f"Errors encountered during hotspot race: {errors[:5]}"
    assert success_count[0] > 0, "Expected at least some successful updates"

    # Invariant verification
    verify_conn = init_db(db_path)
    cur = verify_conn.cursor()
    cur.execute("PRAGMA integrity_check")
    assert cur.fetchone()[0] == "ok"

    cur.execute("PRAGMA foreign_key_check")
    assert cur.fetchall() == []

    # Invariant 1: Exactly one is_current_record = 1 for the problem
    cur.execute("SELECT COUNT(*) FROM solutions WHERE problem_id = 'p_hotspot' AND is_current_record = 1")
    assert cur.fetchone()[0] == 1

    # Invariant 2: Problem best_s equals the metric_s of the current record
    cur.execute("SELECT metric_s FROM solutions WHERE problem_id = 'p_hotspot' AND is_current_record = 1")
    best_record_s = cur.fetchone()[0]
    p_final = get_problem(verify_conn, "p_hotspot")
    assert p_final["best_s"] == pytest.approx(best_record_s)

    # Invariant 3: Sum of workers.records_broken matches total successful solution rows
    cur.execute("SELECT COUNT(*) FROM solutions WHERE problem_id = 'p_hotspot'")
    total_solutions = cur.fetchone()[0]
    cur.execute("SELECT SUM(records_broken) FROM workers")
    total_records_broken = cur.fetchone()[0]
    assert total_solutions == total_records_broken
    assert total_solutions == success_count[0]

    verify_conn.close()


def test_mixed_concurrent_workload(tmp_path: Path):
    """Stress test with mixed concurrent operations: registration, updates, reads across 20 problems."""
    db_path = str(tmp_path / "mixed.db")
    setup_conn = init_db(db_path)
    cur = setup_conn.cursor()
    for i in range(20):
        cur.execute(
            "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES (?, '3', '3', 1, 500.0)",
            (f"p_{i}",),
        )
    setup_conn.commit()
    setup_conn.close()

    errors: List[str] = []

    def mixed_worker(thread_id: int):
        conn = init_db(db_path)
        try:
            for step in range(20):
                op = step % 3
                prob_id = f"p_{random.randint(0, 19)}"
                if op == 0:
                    # Register
                    register_worker(conn, f"user_{thread_id}", worker_id=f"w_{thread_id}")
                elif op == 1:
                    # Update solution
                    p = get_problem(conn, prob_id)
                    if p and p["best_s"] is not None:
                        update_solution_record(
                            conn, prob_id, f"w_{thread_id}", f"user_{thread_id}", p["best_s"] - 0.1, [0.0]
                        )
                else:
                    # Read
                    get_problem(conn, prob_id)
        except Exception as exc:
            errors.append(f"Thread {thread_id}: {type(exc).__name__}: {exc}")
        finally:
            conn.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=40) as executor:
        futures = [executor.submit(mixed_worker, t) for t in range(40)]
        concurrent.futures.wait(futures)

    assert not errors, f"Errors encountered during mixed workload: {errors[:5]}"

    check_conn = init_db(db_path)
    cur = check_conn.cursor()
    cur.execute("PRAGMA integrity_check")
    assert cur.fetchone()[0] == "ok"
    check_conn.close()


# ===========================================================================
# 2. Boundary Condition Metrics (Epsilon, Zero, Negative, Non-Finite)
# ===========================================================================

def test_epsilon_boundary_precision():
    """Verify exact delta behavior near RECORD_MIN_IMPROVEMENT (1e-5)."""
    conn = init_db(":memory:")
    cur = conn.cursor()
    cur.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_eps', '3', '3', 1, 5.0)")
    conn.commit()

    # 1. Delta = 1.0000000000000000e-5 (Exact boundary: 5.0 - 1e-5 = 4.99999)
    # Since metric_s >= current_best - 1e-5 (4.99999 >= 4.99999), it is REJECTED.
    exact_delta_metric = 5.0 - RECORD_MIN_IMPROVEMENT
    assert not update_solution_record(conn, "p_eps", "w1", "user", exact_delta_metric, [0.0])

    # 2. Delta slightly smaller than 1e-5 (4.999990001) -> REJECTED
    smaller_delta_metric = 5.0 - (RECORD_MIN_IMPROVEMENT - 1e-9)
    assert not update_solution_record(conn, "p_eps", "w1", "user", smaller_delta_metric, [0.0])

    # 3. Delta strictly larger than 1e-5 (4.999989999) -> ACCEPTED
    larger_delta_metric = 5.0 - (RECORD_MIN_IMPROVEMENT + 1e-9)
    assert update_solution_record(conn, "p_eps", "w1", "user", larger_delta_metric, [0.0])
    p = get_problem(conn, "p_eps")
    assert p["best_s"] == pytest.approx(larger_delta_metric)
    conn.close()


def test_zero_and_negative_metrics_empirical_behavior():
    """
    CRITICAL INVARIANT:
    Verify that update_solution_record strictly rejects metric_s <= 0.
    In 2D packing, container scale s must be strictly positive (s > 0).
    Non-positive metrics return False and do NOT corrupt problems.best_s.
    """
    conn = init_db(":memory:")
    cur = conn.cursor()
    cur.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_zero', '3', '3', 1, 2.0)")
    cur.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_neg', '3', '3', 1, 2.0)")
    conn.commit()

    # Rejection of zero metric
    zero_accepted = update_solution_record(conn, "p_zero", "w1", "user", 0.0, [0.0])
    p_zero = get_problem(conn, "p_zero")

    # Rejection of negative metric
    neg_accepted = update_solution_record(conn, "p_neg", "w1", "user", -5.0, [0.0])
    p_neg = get_problem(conn, "p_neg")

    assert zero_accepted is False, "Zero metric must be rejected"
    assert p_zero["best_s"] == 2.0, "best_s must not be corrupted by zero metric"
    assert neg_accepted is False, "Negative metric must be rejected"
    assert p_neg["best_s"] == 2.0, "best_s must not be corrupted by negative metric"

    # Verify problem remains unpoisoned and solvable by subsequent legitimate improvement
    valid_accepted = update_solution_record(conn, "p_zero", "w1", "user", 1.5, [0.0])
    assert valid_accepted is True
    assert get_problem(conn, "p_zero")["best_s"] == 1.5

    conn.close()


def test_non_numeric_and_none_metric_type_errors():
    """
    INVARIANT:
    Verify that update_solution_record safely returns False without raising TypeError
    when provided with None, non-numeric types, or malformed arguments.
    """
    conn = init_db(":memory:")
    cur = conn.cursor()
    cur.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_types', '3', '3', 1, 2.0)")
    conn.commit()

    # metric_s = None, str, bool, list -> return False cleanly without raising TypeError
    assert update_solution_record(conn, "p_types", "w1", "user", None, [0.0]) is False
    assert update_solution_record(conn, "p_types", "w1", "user", "1.5", [0.0]) is False
    assert update_solution_record(conn, "p_types", "w1", "user", True, [0.0]) is False
    assert update_solution_record(conn, "p_types", "w1", "user", [1.0], [0.0]) is False

    # coordinates = None, str, empty list, list with invalid elements -> return False cleanly
    assert update_solution_record(conn, "p_types", "w1", "user", 1.5, None) is False
    assert update_solution_record(conn, "p_types", "w1", "user", 1.5, "0.0") is False
    assert update_solution_record(conn, "p_types", "w1", "user", 1.5, []) is False
    assert update_solution_record(conn, "p_types", "w1", "user", 1.5, [None]) is False
    assert update_solution_record(conn, "p_types", "w1", "user", 1.5, ["str"]) is False
    assert update_solution_record(conn, "p_types", "w1", "user", 1.5, [True]) is False

    # Empty or whitespace identifiers must return False cleanly
    assert update_solution_record(conn, "", "w1", "user", 1.5, [0.0]) is False
    assert update_solution_record(conn, "   ", "w1", "user", 1.5, [0.0]) is False
    assert update_solution_record(conn, "p_types", "", "user", 1.5, [0.0]) is False
    assert update_solution_record(conn, "p_types", "   ", "user", 1.5, [0.0]) is False
    assert update_solution_record(conn, "p_types", "w1", "", 1.5, [0.0]) is False
    assert update_solution_record(conn, "p_types", "w1", "   ", 1.5, [0.0]) is False

    # Verify best_s was never corrupted
    p = get_problem(conn, "p_types")
    assert p["best_s"] == 2.0

    conn.close()


def test_nan_in_coordinates_rfc8259():
    """
    INVARIANT:
    Verify that update_solution_record rejects coordinates containing NaN or Inf
    to guarantee strict RFC 8259 JSON compliance.
    """
    conn = init_db(":memory:")
    cur = conn.cursor()
    cur.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_nan_coord', '3', '3', 1, 5.0)")
    conn.commit()

    assert update_solution_record(conn, "p_nan_coord", "w1", "user", 3.0, [float("nan")]) is False
    assert update_solution_record(conn, "p_nan_coord", "w1", "user", 3.0, [float("inf")]) is False
    assert update_solution_record(conn, "p_nan_coord", "w1", "user", 3.0, [float("-inf")]) is False
    assert update_solution_record(conn, "p_nan_coord", "w1", "user", 3.0, [1.0, float("nan")]) is False

    # Verify no invalid solution was recorded
    cur.execute("SELECT COUNT(*) FROM solutions WHERE problem_id = 'p_nan_coord'")
    assert cur.fetchone()[0] == 0

    p = get_problem(conn, "p_nan_coord")
    assert p["best_s"] == 5.0

    conn.close()


# ===========================================================================
# 3. Benchmark Seeding with Corrupt and Extreme Data
# ===========================================================================

def test_seed_problems_corrupt_files_and_extreme_items(tmp_path: Path):
    """
    INVARIANT:
    Test seed_problems_from_verification under extreme data and corrupt files.
    Whitespace IDs are discarded; non-positive/infinite best_values are sanitized to None.
    """
    seed_dir = tmp_path / "extreme_catalog"
    seed_dir.mkdir()

    # 1. Corrupt files (unparseable, empty, HTML)
    (seed_dir / "bad.json").write_text("not json content {")
    (seed_dir / "empty.json").write_text("")
    (seed_dir / "html.json").write_text("<html>404</html>")
    (seed_dir / "non_list.json").write_text(json.dumps({"key": "val"}))
    (seed_dir / "primitives_list.json").write_text(json.dumps([1, 2, "str", None]))

    # 2. Extreme items
    extreme_items = [
        # Whitespace ID (must be rejected)
        {"our_problem": "   ", "N": 1, "best_value": 1.0, "inner_shape": "3", "container_shape": "3"},
        # Zero N (filtered out by n <= 0)
        {"our_problem": "p_zero_n", "N": 0, "best_value": 1.0},
        # Negative N (filtered out by n <= 0)
        {"our_problem": "p_neg_n", "N": -5, "best_value": 1.0},
        # Zero best_value (best_val normalized to None)
        {"our_problem": "p_zero_val", "N": 1, "best_value": 0.0, "inner_shape": "3", "container_shape": "3"},
        # Negative best_value (best_val normalized to None)
        {"our_problem": "p_neg_val", "N": 1, "best_value": -3.5, "inner_shape": "3", "container_shape": "3"},
        # Infinite best_value (best_val normalized to None)
        {"our_problem": "p_inf_val", "N": 1, "best_value": "Infinity", "inner_shape": "3", "container_shape": "3"},
        # SQL injection ID (handled safely via parameterized query)
        {"our_problem": "p_safe'; DROP TABLE problems; --", "N": 1, "best_value": 2.0, "inner_shape": "3", "container_shape": "3"},
        # Float N (truncated to int 2)
        {"our_problem": "p_float_n", "N": 2.9, "best_value": 2.0, "inner_shape": "3", "container_shape": "3"},
        # Proved optimal status
        {"our_problem": "p_optimal", "N": 1, "best_value": 1.0, "inner_shape": "3", "container_shape": "3", "status": "proved_optimal"},
    ]
    (seed_dir / "extreme_data.json").write_text(json.dumps(extreme_items), encoding="utf-8")

    conn = init_db(":memory:")
    seeded_count = seed_problems_from_verification(conn, str(seed_dir))

    # Items that passed:
    # p_zero_val, p_neg_val, p_inf_val, p_safe'..., p_float_n, p_optimal = 6 items
    assert seeded_count == 6

    # Whitespace problem ID must not exist
    assert get_problem(conn, "   ") is None
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM problems WHERE trim(id) = ''")
    assert cur.fetchone()[0] == 0

    # Check zero, negative, and inf values are sanitized to None (NULL)
    p_zero = get_problem(conn, "p_zero_val")
    assert p_zero["best_s"] is None
    assert p_zero["reference_s"] is None
    assert p_zero["status"] == "unattempted"

    p_neg = get_problem(conn, "p_neg_val")
    assert p_neg["best_s"] is None
    assert p_neg["reference_s"] is None
    assert p_neg["status"] == "unattempted"

    p_inf = get_problem(conn, "p_inf_val")
    assert p_inf["best_s"] is None
    assert p_inf["reference_s"] is None
    assert p_inf["status"] == "unattempted"

    # Check SQL injection didn't drop tables
    cur.execute("SELECT COUNT(*) FROM problems")
    assert cur.fetchone()[0] == 6

    conn.close()
