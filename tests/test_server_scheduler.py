"""Unit and integration tests for work scheduler and priority allocator.

Tests:
1. Interface & schema compliance: return dictionary structure and keys.
2. Hardware attempt scaling across cores (1, 4, 8, 16, 20, 64, floored, clamped).
3. Target metric fallback hierarchy (best_s -> reference_s -> 10.0).
4. Strict exclusion of 'proved_optimal' configurations under all conditions.
5. Multi-armed bandit prioritization:
   - Closeness boost (within 1% of baseline record).
   - Stuck problem backoff (>50k attempts without improvement decays priority).
   - Attempt count fair balancing (total_attempts ASC).
   - Density rank void space (density_rank DESC).
   - 10% unattempted family exploration.
6. Fallback shared leasing when all eligible candidates are leased.
7. Active lease expiration (expire_stale_leases) and automatic re-leasing.
8. Heartbeat telemetry and attempt accounting:
   - Atomically updates problem and worker attempt tallies.
   - Updates worker last_seen_at.
   - Cumulative successive increments.
   - Zero-attempt keepalive pings.
   - Stale lease handling (credit worker, reject problem, return False).
   - Telemetry boundary: NEVER updates problems.best_s.
9. Input validation and edge cases (invalid types, booleans, whitespace, negative attempts).
10. Multi-threaded concurrency:
    - Serialization with BEGIN IMMEDIATE prevents duplicate leasing of unleased problems.
    - Concurrent heartbeat updates without lost updates.
    - Concurrent lease expiration and assignment without deadlock.
"""
from __future__ import annotations

import datetime
import math
import random
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest

from shape_packing.server.database import (
    init_db,
    register_worker,
    update_solution_record,
)
from shape_packing.server.scheduler import (
    assign_work,
    expire_stale_leases,
    record_heartbeat,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Fixture providing a temporary database file path."""
    return tmp_path / "scheduler_test.db"


@pytest.fixture
def conn(db_path: Path) -> sqlite3.Connection:
    """Fixture providing an initialized SQLite connection with WAL mode."""
    c = init_db(str(db_path))
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
    if updated_at is not None:
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
    else:
        cursor.execute(
            """
            INSERT INTO problems (
                id, inner_token, container_token, n, best_s, reference_s, status, total_attempts, density_rank
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
    conn.commit()


# ===========================================================================
# 1. Interface & Schema Conformance
# ===========================================================================


def test_assign_work_schema_compliance(conn: sqlite3.Connection):
    """Verify returned work unit dictionary contains exactly the 8 expected keys and types."""
    _insert_problem(
        conn,
        "14_TAN_in_circle",
        inner="TAN",
        container="CIRCLE",
        n=14,
        best_s=2.8451,
        reference_s=2.8500,
        status="best_known",
    )
    register_worker(conn, "alice", worker_id="w_alice")

    work = assign_work(conn, worker_id="w_alice", cores=4, lease_seconds=300)
    assert work is not None
    assert set(work.keys()) == {
        "work_id",
        "problem",
        "inner_token",
        "container_token",
        "n",
        "target_s",
        "recommended_attempts",
        "lease_seconds",
    }
    assert isinstance(work["work_id"], str)
    assert work["work_id"].startswith("wu_")
    assert work["problem"] == "14_TAN_in_circle"
    assert work["inner_token"] == "TAN"
    assert work["container_token"] == "CIRCLE"
    assert work["n"] == 14
    assert isinstance(work["n"], int)
    assert isinstance(work["target_s"], float)
    assert work["target_s"] == pytest.approx(2.8451)
    assert work["recommended_attempts"] == 4000
    assert work["lease_seconds"] == 300


@pytest.mark.parametrize(
    "cores, expected_attempts",
    [
        (1, 1000),
        (2, 2000),
        (4, 4000),
        (8, 8000),
        (16, 16000),
        (20, 20000),
        (32, 20000),
        (64, 20000),
        (128, 20000),
        (0, 1000),
        (-3, 1000),
        (True, 1000),  # bool clamped/normalized
        (False, 1000),
    ],
)
def test_assign_work_recommended_attempts_bounds(
    conn: sqlite3.Connection, cores: Any, expected_attempts: int
):
    """Verify attempt scaling formula max(1000, min(cores * 1000, 20000))."""
    _insert_problem(conn, "p_scale", n=1)
    work = assign_work(conn, worker_id="w_tester", cores=cores)
    assert work is not None
    assert work["recommended_attempts"] == expected_attempts


def test_assign_work_target_s_fallback(conn: sqlite3.Connection):
    """Verify target_s falls back from best_s to reference_s to default 10.0."""
    # Problem 1: has best_s
    _insert_problem(conn, "p_best", best_s=3.14, reference_s=3.20, total_attempts=10)
    # Problem 2: has only reference_s
    _insert_problem(conn, "p_ref", best_s=None, reference_s=5.50, total_attempts=20)
    # Problem 3: has neither
    _insert_problem(conn, "p_none", best_s=None, reference_s=None, total_attempts=30)

    # Disable exploration to test deterministic problem order
    with patch("random.random", return_value=0.5):
        w1 = assign_work(conn, worker_id="w1")
        assert w1 is not None and w1["problem"] == "p_best"
        assert w1["target_s"] == pytest.approx(3.14)

        w2 = assign_work(conn, worker_id="w2")
        assert w2 is not None and w2["problem"] == "p_ref"
        assert w2["target_s"] == pytest.approx(5.50)

        w3 = assign_work(conn, worker_id="w3")
        assert w3 is not None and w3["problem"] == "p_none"
        assert w3["target_s"] == pytest.approx(10.0)


def test_assign_work_custom_lease_seconds(conn: sqlite3.Connection):
    """Verify custom lease_seconds is stored and reflected in the active lease expires_at."""
    _insert_problem(conn, "p_lease", n=1)
    work = assign_work(conn, worker_id="w1", lease_seconds=600)
    assert work is not None
    assert work["lease_seconds"] == 600

    cursor = conn.cursor()
    cursor.execute("SELECT expires_at, leased_at FROM active_leases WHERE work_id = ?", (work["work_id"],))
    row = cursor.fetchone()
    assert row is not None
    # Verify expires_at is approximately 600 seconds after leased_at
    cursor.execute(
        "SELECT strftime('%s', expires_at) - strftime('%s', leased_at) FROM active_leases WHERE work_id = ?",
        (work["work_id"],),
    )
    diff = cursor.fetchone()[0]
    assert diff == pytest.approx(600, abs=2)


# ===========================================================================
# 2. Constraint & Allocation Policies
# ===========================================================================


def test_assign_work_skips_proved_optimal(conn: sqlite3.Connection):
    """Verify proved_optimal problems are strictly excluded under all allocation paths."""
    _insert_problem(conn, "opt_1", status="proved_optimal", total_attempts=0)
    _insert_problem(conn, "opt_2", status="PROVED_OPTIMAL", total_attempts=0)
    _insert_problem(conn, "cand_1", status="unattempted", total_attempts=0)

    # Across 20 assignments (exploration and exploitation), opt_1 and opt_2 must never be assigned
    for i in range(20):
        # Clear leases so cand_1 can be re-assigned
        conn.execute("DELETE FROM active_leases")
        conn.commit()
        work = assign_work(conn, worker_id=f"w_{i}")
        assert work is not None
        assert work["problem"] == "cand_1"
        assert work["problem"] not in ("opt_1", "opt_2")


def test_assign_work_returns_none_when_only_proved_optimal(conn: sqlite3.Connection):
    """Verify assign_work returns None cleanly when catalog contains only proved_optimal."""
    _insert_problem(conn, "opt_1", status="proved_optimal")
    _insert_problem(conn, "opt_2", status="proved_optimal")
    work = assign_work(conn, worker_id="w1")
    assert work is None


def test_assign_work_skips_unsupported(conn: sqlite3.Connection):
    """Verify unsupported problems are strictly excluded under all allocation paths."""
    _insert_problem(conn, "unsup_1", status="unsupported", total_attempts=0)
    _insert_problem(conn, "unsup_2", status="UNSUPPORTED", total_attempts=0)
    _insert_problem(conn, "cand_1", status="unattempted", total_attempts=0)

    # Across 20 assignments (exploration and exploitation), unsupported problems must never be assigned
    for i in range(20):
        conn.execute("DELETE FROM active_leases")
        conn.commit()
        work = assign_work(conn, worker_id=f"w_{i}")
        assert work is not None
        assert work["problem"] == "cand_1"
        assert work["problem"] not in ("unsup_1", "unsup_2")


def test_assign_work_returns_none_when_only_unsupported(conn: sqlite3.Connection):
    """Verify assign_work returns None cleanly when catalog contains only unsupported problems."""
    _insert_problem(conn, "unsup_1", status="unsupported")
    _insert_problem(conn, "unsup_2", status="UNSUPPORTED")
    work = assign_work(conn, worker_id="w1")
    assert work is None


def test_assign_work_returns_none_when_db_empty(conn: sqlite3.Connection):
    """Verify assign_work returns None cleanly when database is empty."""
    work = assign_work(conn, worker_id="w1")
    assert work is None


def test_assign_work_excludes_currently_leased(conn: sqlite3.Connection):
    """Verify currently leased problems are excluded while unleased problems remain."""
    _insert_problem(conn, "prob_a", total_attempts=0)
    _insert_problem(conn, "prob_b", total_attempts=0)

    with patch("random.random", return_value=0.5):
        w1 = assign_work(conn, worker_id="worker_1")
        assert w1 is not None

        w2 = assign_work(conn, worker_id="worker_2")
        assert w2 is not None

        # worker_1 and worker_2 must receive different problems
        assert w1["problem"] != w2["problem"]
        assigned_problems = {w1["problem"], w2["problem"]}
        assert assigned_problems == {"prob_a", "prob_b"}


def test_assign_work_fallback_sharing_when_all_leased(conn: sqlite3.Connection):
    """Verify fallback to shared stochastic leasing when all eligible candidates are leased."""
    _insert_problem(conn, "prob_1", total_attempts=100)
    _insert_problem(conn, "prob_2", total_attempts=200)

    with patch("random.random", return_value=0.5):
        w1 = assign_work(conn, worker_id="worker_1")
        w2 = assign_work(conn, worker_id="worker_2")
        assert w1 is not None and w2 is not None

        # Both problems are now actively leased. Worker 3 requests work:
        w3 = assign_work(conn, worker_id="worker_3")
        assert w3 is not None
        # Must be assigned to one of the eligible problems via shared leasing
        assert w3["problem"] in ("prob_1", "prob_2")

        # active_leases should now have 3 leases across the 2 problems
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM active_leases")
        assert cursor.fetchone()[0] == 3


def test_assign_work_priority_least_attempts_first(conn: sqlite3.Connection):
    """Verify attempt balancing: problem with fewer cumulative attempts is prioritized."""
    _insert_problem(conn, "p_busy", total_attempts=5000, density_rank=0.5)
    _insert_problem(conn, "p_fresh", total_attempts=10, density_rank=0.5)

    with patch("random.random", return_value=0.5):
        work = assign_work(conn, worker_id="w1")
        assert work is not None
        assert work["problem"] == "p_fresh"


def test_assign_work_priority_density_rank(conn: sqlite3.Connection):
    """Verify void space priority: higher density_rank is prioritized when attempts are equal."""
    _insert_problem(conn, "p_dense", total_attempts=100, density_rank=0.2)
    _insert_problem(conn, "p_sparse", total_attempts=100, density_rank=0.9)

    with patch("random.random", return_value=0.5):
        work = assign_work(conn, worker_id="w1")
        assert work is not None
        assert work["problem"] == "p_sparse"


def test_assign_work_priority_closeness_boost(conn: sqlite3.Connection):
    """Verify closeness boost: problems within 1% of baseline record are prioritized."""
    # Problem A: within 0.5% of reference record (closeness boost)
    _insert_problem(
        conn,
        "p_close",
        best_s=9.95,
        reference_s=10.0,
        total_attempts=500,
        density_rank=0.1,
    )
    # Problem B: 5.0% away from reference record
    _insert_problem(
        conn,
        "p_far",
        best_s=9.50,
        reference_s=10.0,
        total_attempts=100,
        density_rank=0.9,
    )

    with patch("random.random", return_value=0.5):
        work = assign_work(conn, worker_id="w1")
        assert work is not None
        assert work["problem"] == "p_close"


def test_assign_work_stuck_backoff(conn: sqlite3.Connection):
    """Verify stuck problem backoff (>50k attempts without improvement in 24h decays priority)."""
    # Problem A: stuck (>50k attempts, updated 2 days ago)
    _insert_problem(
        conn,
        "p_stuck",
        total_attempts=60000,
        updated_at="2026-01-01 00:00:00",
        density_rank=0.9,
    )
    # Problem B: normal problem (10k attempts, updated 2 days ago)
    _insert_problem(
        conn,
        "p_active",
        total_attempts=10000,
        updated_at="2026-01-01 00:00:00",
        density_rank=0.1,
    )

    with patch("random.random", return_value=0.5):
        work = assign_work(conn, worker_id="w1")
        assert work is not None
        assert work["problem"] == "p_active"


def test_assign_work_stuck_backoff_cleared_by_solution_update(conn: sqlite3.Connection):
    """Verify that updating a solution record refreshes updated_at and clears stuck status."""
    _insert_problem(
        conn,
        "p_was_stuck",
        best_s=5.0,
        reference_s=10.0,
        total_attempts=60000,
        updated_at="2026-01-01 00:00:00",
        density_rank=0.9,
    )
    _insert_problem(
        conn,
        "p_other",
        best_s=5.0,
        reference_s=10.0,
        total_attempts=60000,
        updated_at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        density_rank=0.1,
    )

    # Initially, p_other is preferred because p_was_stuck is stuck in Tier 1
    with patch("random.random", return_value=0.5):
        w1 = assign_work(conn, worker_id="w1")
        assert w1 is not None and w1["problem"] == "p_other"

    # Now an improvement is recorded for p_was_stuck
    register_worker(conn, "bob", worker_id="w_bob")
    assert update_solution_record(
        conn,
        problem_id="p_was_stuck",
        worker_id="w_bob",
        username="bob",
        metric_s=4.5,
        coordinates=[1.0, 2.0, 3.0],
    )

    # Clear active leases
    conn.execute("DELETE FROM active_leases")
    conn.commit()

    # Now p_was_stuck has updated_at = CURRENT_TIMESTAMP, so it is no longer stuck!
    # With equal total_attempts and density_rank 0.9 vs 0.1, p_was_stuck should now win!
    with patch("random.random", return_value=0.5):
        w2 = assign_work(conn, worker_id="w2")
        assert w2 is not None
        assert w2["problem"] == "p_was_stuck"


def test_assign_work_exploration_unattempted_selection(conn: sqlite3.Connection):
    """Verify 10% exploration stage targets unattempted configurations."""
    _insert_problem(conn, "p_explored", status="best_known", total_attempts=5000)
    _insert_problem(conn, "p_new", status="unattempted", total_attempts=0)

    # Force exploration branch with random value < 0.10
    with patch("random.random", return_value=0.05):
        work = assign_work(conn, worker_id="w1")
        assert work is not None
        assert work["problem"] == "p_new"


def test_assign_work_exploration_falls_back_when_no_unattempted(conn: sqlite3.Connection):
    """Verify exploration seamlessly falls back to exploitation if no unattempted problems exist."""
    _insert_problem(conn, "p_a", status="best_known", total_attempts=100)
    _insert_problem(conn, "p_b", status="best_known", total_attempts=200)

    # Force exploration branch, but no unattempted problems exist
    with patch("random.random", return_value=0.02):
        work = assign_work(conn, worker_id="w1")
        assert work is not None
        assert work["problem"] == "p_a"


# ===========================================================================
# 3. Lease Expiration & Lifecycle
# ===========================================================================


def test_expire_stale_leases_empty(conn: sqlite3.Connection):
    """Verify expire_stale_leases returns 0 safely on empty active_leases table."""
    assert expire_stale_leases(conn) == 0


def test_expire_stale_leases_future_intact(conn: sqlite3.Connection):
    """Verify active leases with future expires_at are preserved and not deleted."""
    _insert_problem(conn, "p1")
    register_worker(conn, "alice", worker_id="w1")
    conn.execute(
        """
        INSERT INTO active_leases (work_id, problem_id, worker_id, leased_at, expires_at)
        VALUES ('wu_future', 'p1', 'w1', CURRENT_TIMESTAMP, datetime('now', '+300 seconds'))
        """
    )
    conn.commit()

    assert expire_stale_leases(conn) == 0
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM active_leases")
    assert cursor.fetchone()[0] == 1


def test_expire_stale_leases_past_deleted(conn: sqlite3.Connection):
    """Verify stale leases in the past are deleted and exact count is returned."""
    _insert_problem(conn, "p1")
    _insert_problem(conn, "p2")
    register_worker(conn, "alice", worker_id="w1")
    conn.execute(
        """
        INSERT INTO active_leases (work_id, problem_id, worker_id, leased_at, expires_at)
        VALUES
            ('wu_stale1', 'p1', 'w1', CURRENT_TIMESTAMP, datetime('now', '-50 seconds')),
            ('wu_stale2', 'p2', 'w1', CURRENT_TIMESTAMP, datetime('now', '-10 seconds')),
            ('wu_live', 'p1', 'w1', CURRENT_TIMESTAMP, datetime('now', '+300 seconds'))
        """
    )
    conn.commit()

    deleted = expire_stale_leases(conn)
    assert deleted == 2

    cursor = conn.cursor()
    cursor.execute("SELECT work_id FROM active_leases")
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "wu_live"


def test_assign_work_auto_expires_stale_leases(conn: sqlite3.Connection):
    """Verify assign_work automatically calls expire_stale_leases and reclaims stale problems."""
    _insert_problem(conn, "p_only_one", total_attempts=0)
    register_worker(conn, "alice", worker_id="w1")

    # Insert an expired lease for the only problem
    conn.execute(
        """
        INSERT INTO active_leases (work_id, problem_id, worker_id, leased_at, expires_at)
        VALUES ('wu_expired', 'p_only_one', 'w1', CURRENT_TIMESTAMP, datetime('now', '-30 seconds'))
        """
    )
    conn.commit()

    # Calling assign_work should purge wu_expired and assign p_only_one as unleased
    work = assign_work(conn, worker_id="w2")
    assert work is not None
    assert work["problem"] == "p_only_one"
    assert work["work_id"] != "wu_expired"

    # Confirm wu_expired is no longer in active_leases
    cursor = conn.cursor()
    cursor.execute("SELECT work_id FROM active_leases WHERE work_id = 'wu_expired'")
    assert cursor.fetchone() is None


# ===========================================================================
# 4. Heartbeat Telemetry & Attempt Accounting
# ===========================================================================


def test_record_heartbeat_updates_problem_and_worker_attempts(conn: sqlite3.Connection):
    """Verify heartbeat increments problem.total_attempts, worker.total_attempts, and updates last_seen_at."""
    _insert_problem(conn, "p1", total_attempts=50)
    register_worker(conn, "alice", worker_id="w_alice")

    work = assign_work(conn, worker_id="w_alice")
    assert work is not None

    success = record_heartbeat(conn, work_id=work["work_id"], worker_id="w_alice", attempts=2500)
    assert success is True

    # Verify problem attempts
    cursor = conn.cursor()
    cursor.execute("SELECT total_attempts FROM problems WHERE id = 'p1'")
    assert cursor.fetchone()[0] == 2550

    # Verify worker attempts
    cursor.execute("SELECT total_attempts FROM workers WHERE id = 'w_alice'")
    assert cursor.fetchone()[0] == 2500


def test_record_heartbeat_updates_worker_last_seen(conn: sqlite3.Connection):
    """Verify heartbeat updates worker last_seen_at timestamp."""
    _insert_problem(conn, "p1")
    register_worker(conn, "alice", worker_id="w_alice")
    # Set last_seen_at in past
    conn.execute("UPDATE workers SET last_seen_at = '2026-01-01 00:00:00' WHERE id = 'w_alice'")
    conn.commit()

    work = assign_work(conn, worker_id="w_alice")
    assert work is not None

    assert record_heartbeat(conn, work_id=work["work_id"], worker_id="w_alice", attempts=100) is True

    cursor = conn.cursor()
    cursor.execute("SELECT last_seen_at FROM workers WHERE id = 'w_alice'")
    last_seen = cursor.fetchone()[0]
    assert last_seen > "2026-01-01 00:00:00"


def test_record_heartbeat_multiple_cumulative(conn: sqlite3.Connection):
    """Verify successive heartbeats accumulate attempts monotonically."""
    _insert_problem(conn, "p1", total_attempts=0)
    register_worker(conn, "bob", worker_id="w_bob")

    work = assign_work(conn, worker_id="w_bob")
    assert work is not None

    assert record_heartbeat(conn, work_id=work["work_id"], worker_id="w_bob", attempts=1000) is True
    assert record_heartbeat(conn, work_id=work["work_id"], worker_id="w_bob", attempts=2500) is True

    cursor = conn.cursor()
    cursor.execute("SELECT total_attempts FROM problems WHERE id = 'p1'")
    assert cursor.fetchone()[0] == 3500

    cursor.execute("SELECT total_attempts FROM workers WHERE id = 'w_bob'")
    assert cursor.fetchone()[0] == 3500


def test_record_heartbeat_zero_attempts_liveness(conn: sqlite3.Connection):
    """Verify attempts=0 functions as a valid liveness ping without modifying attempts."""
    _insert_problem(conn, "p1", total_attempts=123)
    register_worker(conn, "charlie", worker_id="w_charlie")
    conn.execute("UPDATE workers SET total_attempts = 456 WHERE id = 'w_charlie'")
    conn.commit()

    work = assign_work(conn, worker_id="w_charlie")
    assert work is not None

    assert record_heartbeat(conn, work_id=work["work_id"], worker_id="w_charlie", attempts=0) is True

    cursor = conn.cursor()
    cursor.execute("SELECT total_attempts FROM problems WHERE id = 'p1'")
    assert cursor.fetchone()[0] == 123
    cursor.execute("SELECT total_attempts FROM workers WHERE id = 'w_charlie'")
    assert cursor.fetchone()[0] == 456


def test_record_heartbeat_after_lease_expired(conn: sqlite3.Connection):
    """Verify that after lease expiration, worker attempts are credited but problem is not, returning False."""
    _insert_problem(conn, "p1", total_attempts=100)
    register_worker(conn, "dave", worker_id="w_dave")

    # Insert an expired lease
    conn.execute(
        """
        INSERT INTO active_leases (work_id, problem_id, worker_id, leased_at, expires_at)
        VALUES ('wu_expired_hb', 'p1', 'w_dave', CURRENT_TIMESTAMP, datetime('now', '-10 seconds'))
        """
    )
    conn.commit()

    # Worker reports heartbeat on expired lease
    success = record_heartbeat(conn, work_id="wu_expired_hb", worker_id="w_dave", attempts=500)
    # Returns False to signal to worker that lease has lapsed
    assert success is False

    # Worker compute was still credited
    cursor = conn.cursor()
    cursor.execute("SELECT total_attempts FROM workers WHERE id = 'w_dave'")
    assert cursor.fetchone()[0] == 500

    # Problem total_attempts was NOT credited
    cursor.execute("SELECT total_attempts FROM problems WHERE id = 'p1'")
    assert cursor.fetchone()[0] == 100


def test_record_heartbeat_unknown_work_id(conn: sqlite3.Connection):
    """Verify unknown work_id credits worker compute but returns False without updating problem."""
    _insert_problem(conn, "p1", total_attempts=100)
    register_worker(conn, "eve", worker_id="w_eve")

    success = record_heartbeat(conn, work_id="wu_nonexistent", worker_id="w_eve", attempts=700)
    assert success is False

    cursor = conn.cursor()
    cursor.execute("SELECT total_attempts FROM workers WHERE id = 'w_eve'")
    assert cursor.fetchone()[0] == 700


def test_record_heartbeat_does_not_modify_best_s(conn: sqlite3.Connection):
    """IRON RULE: verify heartbeat NEVER updates problems.best_s even if best_s is reported."""
    _insert_problem(conn, "p1", best_s=5.0)
    register_worker(conn, "frank", worker_id="w_frank")

    work = assign_work(conn, worker_id="w_frank")
    assert work is not None

    # Heartbeat reports a lower metric (e.g. 2.0)
    success = record_heartbeat(
        conn,
        work_id=work["work_id"],
        worker_id="w_frank",
        attempts=1000,
        best_s=2.0,
    )
    assert success is True

    # problems.best_s must remain 5.0
    cursor = conn.cursor()
    cursor.execute("SELECT best_s FROM problems WHERE id = 'p1'")
    assert cursor.fetchone()[0] == pytest.approx(5.0)


# ===========================================================================
# 5. Input Validation & Defensive Edge Cases
# ===========================================================================


@pytest.mark.parametrize("invalid_id", [None, "", "   ", 123, [], {}])
def test_assign_work_invalid_worker_id(conn: sqlite3.Connection, invalid_id: Any):
    """Verify assign_work rejects non-string or whitespace worker_id."""
    _insert_problem(conn, "p1")
    assert assign_work(conn, worker_id=invalid_id) is None


def test_assign_work_unregistered_worker_auto_registration(conn: sqlite3.Connection):
    """Verify assign_work auto-registers unknown worker to avoid foreign key violations."""
    _insert_problem(conn, "p1")
    work = assign_work(conn, worker_id="w_brand_new_worker")
    assert work is not None
    assert work["work_id"] is not None

    # Verify worker was registered in workers table
    cursor = conn.cursor()
    cursor.execute("SELECT id, client_type FROM workers WHERE id = 'w_brand_new_worker'")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "w_brand_new_worker"
    assert row[1] == "native"


def test_assign_work_preserves_existing_username(conn: sqlite3.Connection):
    """Verify assign_work does not overwrite existing worker username during auto-upsert."""
    _insert_problem(conn, "p1")
    register_worker(conn, username="special_agent", worker_id="w_agent")

    work = assign_work(conn, worker_id="w_agent")
    assert work is not None

    cursor = conn.cursor()
    cursor.execute("SELECT username FROM workers WHERE id = 'w_agent'")
    assert cursor.fetchone()[0] == "special_agent"


@pytest.mark.parametrize(
    "invalid_attempts",
    [-1, -100, True, False, "100", 12.5, None, [10]],
)
def test_record_heartbeat_invalid_attempts(conn: sqlite3.Connection, invalid_attempts: Any):
    """Verify record_heartbeat strictly rejects negative, non-int, and boolean attempts."""
    _insert_problem(conn, "p1")
    register_worker(conn, "grace", worker_id="w_grace")
    work = assign_work(conn, worker_id="w_grace")
    assert work is not None

    assert record_heartbeat(
        conn,
        work_id=work["work_id"],
        worker_id="w_grace",
        attempts=invalid_attempts,
    ) is False


@pytest.mark.parametrize("invalid_id", [None, "", "   ", 123, []])
def test_record_heartbeat_invalid_identifiers(conn: sqlite3.Connection, invalid_id: Any):
    """Verify record_heartbeat rejects empty or non-string work_id and worker_id."""
    assert record_heartbeat(conn, work_id=invalid_id, worker_id="w1", attempts=10) is False
    assert record_heartbeat(conn, work_id="wu_valid", worker_id=invalid_id, attempts=10) is False


@pytest.mark.parametrize("invalid_best_s", [-1.0, 0.0, float("nan"), float("inf"), True, "1.5"])
def test_record_heartbeat_invalid_best_s(conn: sqlite3.Connection, invalid_best_s: Any):
    """Verify record_heartbeat rejects non-positive or non-finite best_s values."""
    _insert_problem(conn, "p1")
    register_worker(conn, "heidi", worker_id="w_heidi")
    work = assign_work(conn, worker_id="w_heidi")
    assert work is not None

    assert record_heartbeat(
        conn,
        work_id=work["work_id"],
        worker_id="w_heidi",
        attempts=10,
        best_s=invalid_best_s,
    ) is False


def test_functions_handle_invalid_connections():
    """Verify scheduler functions reject non-connection objects gracefully."""
    assert expire_stale_leases(None) == 0  # type: ignore
    assert assign_work(None, "w1") is None  # type: ignore
    assert record_heartbeat(None, "wu1", "w1", 10) is False  # type: ignore


# ===========================================================================
# 6. Concurrency & Multi-Threading
# ===========================================================================


def test_concurrent_work_assignment_no_duplicates(db_path: Path):
    """Verify BEGIN IMMEDIATE serialization: 10 concurrent threads leasing 10 problems get distinct tasks."""
    conn = init_db(str(db_path))
    num_problems = 10
    for i in range(num_problems):
        _insert_problem(conn, f"prob_{i:02d}", total_attempts=0)
    conn.close()

    assigned: List[str] = []
    assigned_lock = threading.Lock()
    errors: List[Exception] = []
    start_barrier = threading.Barrier(num_problems)

    def worker_thread(idx: int):
        thread_conn = init_db(str(db_path))
        try:
            start_barrier.wait(timeout=10.0)
            work = assign_work(thread_conn, worker_id=f"worker_{idx}", cores=2)
            if work:
                with assigned_lock:
                    assigned.append(work["problem"])
        except Exception as exc:
            errors.append(exc)
        finally:
            thread_conn.close()

    threads = [threading.Thread(target=worker_thread, args=(i,)) for i in range(num_problems)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)

    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"
    assert len(assigned) == num_problems
    # Each thread must have received a distinct problem without duplicate leases
    assert len(set(assigned)) == num_problems


def test_concurrent_heartbeats_no_lost_updates(db_path: Path):
    """Verify concurrent heartbeats on the same problem and worker: no lost updates."""
    conn = init_db(str(db_path))
    _insert_problem(conn, "prob_hotspot", total_attempts=0)
    register_worker(conn, "shared_worker", worker_id="w_shared")
    work = assign_work(conn, worker_id="w_shared")
    assert work is not None
    work_id = work["work_id"]
    conn.close()

    num_threads = 10
    attempts_per_call = 100
    errors: List[Exception] = []
    start_barrier = threading.Barrier(num_threads)

    def heartbeat_thread(idx: int):
        thread_conn = init_db(str(db_path))
        try:
            start_barrier.wait(timeout=10.0)
            success = record_heartbeat(
                thread_conn,
                work_id=work_id,
                worker_id="w_shared",
                attempts=attempts_per_call,
            )
            if not success:
                errors.append(RuntimeError(f"Heartbeat failed on thread {idx}"))
        except Exception as exc:
            errors.append(exc)
        finally:
            thread_conn.close()

    threads = [threading.Thread(target=heartbeat_thread, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)

    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"

    # Verify final counts in database
    verify_conn = init_db(str(db_path))
    cursor = verify_conn.cursor()
    cursor.execute("SELECT total_attempts FROM problems WHERE id = 'prob_hotspot'")
    assert cursor.fetchone()[0] == num_threads * attempts_per_call

    cursor.execute("SELECT total_attempts FROM workers WHERE id = 'w_shared'")
    assert cursor.fetchone()[0] == num_threads * attempts_per_call
    verify_conn.close()


def test_concurrent_expire_and_assign(db_path: Path):
    """Verify concurrent assign_work and expire_stale_leases execute without deadlocks."""
    conn = init_db(str(db_path))
    for i in range(5):
        _insert_problem(conn, f"prob_mix_{i}", total_attempts=i * 10)
    conn.close()

    stop_event = threading.Event()
    errors: List[Exception] = []

    def assigner(idx: int):
        thread_conn = init_db(str(db_path))
        try:
            while not stop_event.is_set():
                assign_work(thread_conn, worker_id=f"worker_{idx}", lease_seconds=1)
                time.sleep(0.005)
        except Exception as exc:
            errors.append(exc)
        finally:
            thread_conn.close()

    def expirer():
        thread_conn = init_db(str(db_path))
        try:
            while not stop_event.is_set():
                expire_stale_leases(thread_conn)
                time.sleep(0.005)
        except Exception as exc:
            errors.append(exc)
        finally:
            thread_conn.close()

    assign_threads = [threading.Thread(target=assigner, args=(i,)) for i in range(4)]
    expire_threads = [threading.Thread(target=expirer) for _ in range(2)]

    all_threads = assign_threads + expire_threads
    for t in all_threads:
        t.start()

    time.sleep(1.0)
    stop_event.set()

    for t in all_threads:
        t.join(timeout=5.0)

    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"


def test_assign_work_prioritizes_benchmark_over_frontier(conn: sqlite3.Connection):
    """Benchmark tier must always be leased ahead of frontier tier in both exploration and exploitation."""
    conn.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, reference_s, status, total_attempts, density_rank, tier) "
        "VALUES ('1_RHOMBUS_in_4', 'RHOMBUS', '4', 1, NULL, 'unattempted', 0, 0.0, 'frontier')"
    )
    conn.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, reference_s, status, total_attempts, density_rank, tier) "
        "VALUES ('5_CIRCLE_in_SEMICIRCLE', 'CIRCLE', 'SEMICIRCLE', 5, 3.8284, 'best_known', 100, 0.75, 'benchmark')"
    )
    conn.commit()

    # Even during 10% exploration (random=0.01) or 90% exploitation (random=0.5), benchmark wins first
    with patch("random.random", return_value=0.01):
        w1 = assign_work(conn, worker_id="w_bench_first")
        assert w1 is not None and w1["problem"] == "5_CIRCLE_in_SEMICIRCLE"

    # Once benchmark is leased, next worker falls through cleanly to frontier
    with patch("random.random", return_value=0.5):
        w2 = assign_work(conn, worker_id="w_frontier_fallback")
        assert w2 is not None and w2["problem"] == "1_RHOMBUS_in_4"
        assert w2["target_s"] == pytest.approx(10.0)


def test_assign_work_tier_filter_opt_in(conn: sqlite3.Connection):
    """Workers explicitly requesting tier_filter='frontier' receive frontier problems immediately."""
    conn.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, reference_s, status, total_attempts, tier) "
        "VALUES ('1_TRAPEZOID_in_6', 'TRAPEZOID', '6', 1, NULL, 'unattempted', 0, 'frontier')"
    )
    conn.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, reference_s, status, total_attempts, tier) "
        "VALUES ('5_3_in_4', '3', '4', 5, 2.5, 'best_known', 0, 'benchmark')"
    )
    conn.commit()

    w = assign_work(conn, worker_id="w_frontier_only", tier_filter="frontier")
    assert w is not None and w["problem"] == "1_TRAPEZOID_in_6"
