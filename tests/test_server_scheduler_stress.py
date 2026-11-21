"""Adversarial stress tests and boundary verification for work scheduler.

Designed by Challenger 1 (Milestone 2) to empirically challenge:
1. Proved optimal problem extraction prevention under all conditions.
2. Extreme and corrupt inputs (negative/non-integer/huge cores, invalid worker_id, extreme lease_seconds).
3. Catalog boundary states (empty, only proved_optimal, all leased, fallback shared leasing).
4. Stuck backoff and closeness boost ordering under adversarial edge cases.
5. Heartbeat accounting security and boundary conditions.
"""
from __future__ import annotations

import datetime
import math
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from shape_packing.server.database import init_db, register_worker, update_solution_record
from shape_packing.server.scheduler import (
    assign_work,
    expire_stale_leases,
    record_heartbeat,
)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    """Fixture providing a fresh SQLite WAL connection."""
    db_file = tmp_path / "scheduler_stress.db"
    c = init_db(str(db_file))
    yield c
    c.close()


def _insert_problem(
    conn: sqlite3.Connection,
    problem_id: str,
    inner: str = "4",
    container: str = "4",
    n: int = 1,
    best_s: Optional[float] = None,
    reference_s: Optional[float] = None,
    status: str = "unattempted",
    total_attempts: int = 0,
    density_rank: float = 0.0,
    updated_at: Optional[str] = None,
) -> None:
    """Helper to insert a problem directly into the problems table."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO problems (
            id, inner_token, container_token, n, best_s, reference_s, status, total_attempts, density_rank, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            problem_id,
            inner,
            container,
            n,
            best_s,
            reference_s,
            status,
            total_attempts,
            density_rank,
            updated_at,
        ),
    )
    conn.commit()


# ===========================================================================
# 1. Proved Optimal Problem Extraction Invariants
# ===========================================================================


def test_adversarial_proved_optimal_extraction_exhaustive(conn: sqlite3.Connection):
    """Stress test: 1,000 attempts under mixed exploration & exploitation MUST NEVER return proved_optimal."""
    # Insert multiple variations of proved_optimal problems (varied casings, attempts, ranks)
    _insert_problem(conn, "opt_lower", status="proved_optimal", total_attempts=0, density_rank=0.9)
    _insert_problem(conn, "opt_upper", status="PROVED_OPTIMAL", total_attempts=0, density_rank=1.0)
    _insert_problem(conn, "opt_mixed", status="Proved_Optimal", total_attempts=0, density_rank=0.8)
    _insert_problem(conn, "opt_many_attempts", status="proved_optimal", total_attempts=100000, density_rank=0.5)

    # Insert only 2 legitimate candidates
    _insert_problem(conn, "valid_cand_1", status="unattempted", total_attempts=0, density_rank=0.1)
    _insert_problem(conn, "valid_cand_2", status="best_known", total_attempts=500, density_rank=0.2)

    extracted_problems = set()
    for i in range(1000):
        # We periodically clear active leases to trigger all 4 query branches
        if i % 3 == 0:
            conn.execute("DELETE FROM active_leases")
            conn.commit()

        work = assign_work(conn, worker_id=f"worker_{i}")
        assert work is not None
        assert work["problem"] not in ("opt_lower", "opt_upper", "opt_mixed", "opt_many_attempts")
        assert work["problem"] in ("valid_cand_1", "valid_cand_2")
        extracted_problems.add(work["problem"])

    assert extracted_problems == {"valid_cand_1", "valid_cand_2"}


def test_fallback_shared_leasing_excludes_proved_optimal(conn: sqlite3.Connection):
    """When all non-optimal problems are actively leased, fallback shared leasing still excludes proved_optimal."""
    _insert_problem(conn, "opt_1", status="proved_optimal")
    _insert_problem(conn, "valid_1", status="best_known", total_attempts=100)

    # Worker 1 leases the only valid problem
    w1 = assign_work(conn, worker_id="w1")
    assert w1 is not None and w1["problem"] == "valid_1"

    # Now valid_1 is leased. Worker 2 requests work.
    # Fallback shared leasing must assign valid_1, NOT opt_1.
    w2 = assign_work(conn, worker_id="w2")
    assert w2 is not None
    assert w2["problem"] == "valid_1"
    assert w2["problem"] != "opt_1"


# ===========================================================================
# 2. Extreme and Corrupt Inputs
# ===========================================================================


@pytest.mark.parametrize(
    "extreme_cores, expected_attempts",
    [
        (-1, 1000),
        (-1000000, 1000),
        (0, 1000),
        (1, 1000),
        (4, 4000),
        (20, 20000),
        (100, 20000),
        (999999999, 20000),
        ("8", 8000),
        ("not_a_number", 1000),
        (None, 1000),
        (True, 1000),
        (False, 1000),
        ([], 1000),
        ({}, 1000),
        (3.7, 3000),
        (0.2, 1000),
    ],
)
def test_extreme_and_corrupt_cores_normalization(
    conn: sqlite3.Connection, extreme_cores: Any, expected_attempts: int
):
    """Verify extreme, negative, and corrupt cores are normalized cleanly."""
    _insert_problem(conn, "prob_cores", n=1)
    work = assign_work(conn, worker_id="worker_test", cores=extreme_cores)
    assert work is not None
    assert work["recommended_attempts"] == expected_attempts


def test_overflow_cores_and_lease_seconds_behavior(conn: sqlite3.Connection):
    """Check behavior when cores or lease_seconds is float('inf') or float('nan')."""
    _insert_problem(conn, "prob_overflow", n=1)

    # float('nan') can be converted to int? No, ValueError. Caught by assign_work:
    work_nan = assign_work(conn, worker_id="w_nan", cores=float("nan"))
    assert work_nan is not None
    assert work_nan["recommended_attempts"] == 1000

    work_nan_ls = assign_work(conn, worker_id="w_nan_ls", lease_seconds=float("nan"))
    assert work_nan_ls is not None
    assert work_nan_ls["lease_seconds"] == 300


@pytest.mark.parametrize(
    "corrupt_worker_id",
    [
        None,
        "",
        "   ",
        "\t\r\n",
        12345,
        ["worker_list"],
        {"id": "worker"},
        True,
        False,
    ],
)
def test_corrupt_worker_ids_rejected(conn: sqlite3.Connection, corrupt_worker_id: Any):
    """Verify non-string or blank worker_ids are rejected with None."""
    _insert_problem(conn, "p1")
    assert assign_work(conn, worker_id=corrupt_worker_id) is None


def test_adversarial_worker_ids_sql_injection_and_unicode(conn: sqlite3.Connection):
    """Verify SQL injection strings and unicode/emoji worker IDs are safely handled."""
    _insert_problem(conn, "p1")

    injection_id = "worker'; DROP TABLE problems; --"
    work = assign_work(conn, worker_id=injection_id)
    assert work is not None
    assert work["problem"] == "p1"

    # Verify problems table was NOT dropped!
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM problems")
    assert cursor.fetchone()[0] == 1

    # Verify unicode / emoji worker ID
    emoji_id = "🤖_worker_42_🚀"
    work2 = assign_work(conn, worker_id=emoji_id)
    assert work2 is not None


# ===========================================================================
# 3. Catalog Boundary States
# ===========================================================================


def test_boundary_empty_catalog(conn: sqlite3.Connection):
    """Catalog with 0 problems returns None."""
    assert assign_work(conn, worker_id="w1") is None


def test_boundary_only_proved_optimal_in_catalog(conn: sqlite3.Connection):
    """Catalog with only proved_optimal returns None across all attempts."""
    for i in range(5):
        _insert_problem(conn, f"opt_{i}", status="proved_optimal")

    for _ in range(50):
        assert assign_work(conn, worker_id="w1") is None


def test_boundary_target_s_defaults(conn: sqlite3.Connection):
    """When best_s and reference_s are None, target_s defaults to 10.0."""
    _insert_problem(conn, "p_no_metric", best_s=None, reference_s=None)
    work = assign_work(conn, worker_id="w1")
    assert work is not None
    assert work["target_s"] == 10.0


# ===========================================================================
# 4. Stuck Backoff and Closeness Boost Ordering Under Adversarial Edge Cases
# ===========================================================================


def test_stuck_backoff_threshold_boundaries(conn: sqlite3.Connection):
    """Verify boundary conditions for stuck backoff (>50k attempts and updated_at < now - 1 day)."""
    yesterday_str = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Problem 1: exactly 50,000 attempts, updated 2 days ago -> NOT stuck (condition is > 50000)
    _insert_problem(
        conn,
        "p_50000",
        total_attempts=50000,
        updated_at=yesterday_str,
        density_rank=0.1,
    )
    # Problem 2: 50,001 attempts, updated 2 days ago -> STUCK
    _insert_problem(
        conn,
        "p_50001",
        total_attempts=50001,
        updated_at=yesterday_str,
        density_rank=0.9,
    )

    with patch("random.random", return_value=0.5):
        work = assign_work(conn, worker_id="w1")
        assert work is not None
        # p_50000 is NOT stuck (Tier 1 = 0), p_50001 IS stuck (Tier 1 = 1).
        # Even though p_50001 has higher density_rank (0.9 vs 0.1), p_50000 wins!
        assert work["problem"] == "p_50000"


def test_stuck_backoff_overrides_closeness_boost(conn: sqlite3.Connection):
    """Verify Tier 1 (Stuck backoff) strictly overrides Tier 2 (Closeness boost)."""
    old_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Problem A: Stuck (60k attempts, old update) BUT has closeness boost (delta = 0.1%)
    _insert_problem(
        conn,
        "p_stuck_but_close",
        best_s=9.99,
        reference_s=10.0,
        total_attempts=60000,
        updated_at=old_time,
        density_rank=0.9,
    )
    # Problem B: Not stuck (10k attempts) BUT FAR from record (delta = 50%)
    _insert_problem(
        conn,
        "p_not_stuck_far",
        best_s=5.0,
        reference_s=10.0,
        total_attempts=10000,
        updated_at=old_time,
        density_rank=0.1,
    )

    with patch("random.random", return_value=0.5):
        work = assign_work(conn, worker_id="w1")
        assert work is not None
        # Not-stuck problem must win over stuck problem despite closeness boost!
        assert work["problem"] == "p_not_stuck_far"


def test_closeness_boost_exact_boundary(conn: sqlite3.Connection):
    """Verify closeness boost threshold boundary: abs(best_s - ref_s)/ref_s <= 0.01."""
    # Reference is 100.0
    # Problem A: delta is exactly 1.0000 -> 1.0 / 100.0 = 0.0100 (qualifies for boost)
    _insert_problem(
        conn,
        "p_exact_boost",
        best_s=99.0,
        reference_s=100.0,
        total_attempts=2000,
        density_rank=0.1,
    )
    # Problem B: delta is 1.0200 -> 1.02 / 100.0 = 0.0102 (does not qualify)
    _insert_problem(
        conn,
        "p_no_boost",
        best_s=98.98,
        reference_s=100.0,
        total_attempts=100,  # Far fewer attempts!
        density_rank=0.9,
    )

    with patch("random.random", return_value=0.5):
        work = assign_work(conn, worker_id="w1")
        assert work is not None
        # p_exact_boost qualifies for Tier 2 boost (Tier 2 = 0) vs p_no_boost (Tier 2 = 1).
        # Even though p_no_boost has only 100 attempts vs 2000 attempts, p_exact_boost wins!
        assert work["problem"] == "p_exact_boost"


def test_concurrent_fallback_sharing_single_problem(tmp_path: Path):
    """Verify that when only 1 problem exists, 10 concurrent threads all receive valid leases via shared leasing."""
    db_file = tmp_path / "single_prob_concurrent.db"
    conn = init_db(str(db_file))
    _insert_problem(conn, "only_one_problem", total_attempts=50)
    conn.close()

    num_threads = 10
    leases: List[Dict[str, Any]] = []
    errors: List[Exception] = []
    lock = threading.Lock()
    barrier = threading.Barrier(num_threads)

    def worker_thread(idx: int):
        t_conn = init_db(str(db_file))
        try:
            barrier.wait(timeout=10.0)
            work = assign_work(t_conn, worker_id=f"worker_{idx}")
            if work:
                with lock:
                    leases.append(work)
        except Exception as exc:
            with lock:
                errors.append(exc)
        finally:
            t_conn.close()

    threads = [threading.Thread(target=worker_thread, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)

    assert len(errors) == 0, f"Encountered errors: {errors}"
    assert len(leases) == num_threads
    for item in leases:
        assert item["problem"] == "only_one_problem"

    # Verify active_leases table in db contains all 10 leases
    check_conn = init_db(str(db_file))
    cursor = check_conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM active_leases WHERE problem_id = 'only_one_problem'")
    assert cursor.fetchone()[0] == num_threads
    check_conn.close()




# ===========================================================================
# 5. Heartbeat Accounting and Security Stress
# ===========================================================================


def test_record_heartbeat_cross_worker_rejection(conn: sqlite3.Connection):
    """Worker B cannot update Worker A's active lease."""
    _insert_problem(conn, "p_secure")
    work_a = assign_work(conn, worker_id="worker_alice")
    assert work_a is not None

    # Worker Bob attempts to heartbeat on Alice's work_id
    success = record_heartbeat(
        conn,
        work_id=work_a["work_id"],
        worker_id="worker_bob",
        attempts=500,
    )
    # Must fail because lease belongs to Alice
    assert success is False

    # Alice's problem must not have received Bob's attempts
    cursor = conn.cursor()
    cursor.execute("SELECT total_attempts FROM problems WHERE id = 'p_secure'")
    assert cursor.fetchone()[0] == 0


def test_record_heartbeat_large_attempt_increments(conn: sqlite3.Connection):
    """Large attempt counts are properly accounted without integer overflow."""
    _insert_problem(conn, "p_big", total_attempts=0)
    work = assign_work(conn, worker_id="w_big")
    assert work is not None

    large_attempts = 10**9
    assert record_heartbeat(conn, work["work_id"], "w_big", attempts=large_attempts) is True

    cursor = conn.cursor()
    cursor.execute("SELECT total_attempts FROM problems WHERE id = 'p_big'")
    assert cursor.fetchone()[0] == large_attempts
