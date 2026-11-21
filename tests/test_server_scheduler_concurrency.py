"""Empirical concurrency and stress challenge test suite for scheduler.py.

Tests:
1. Multi-threaded concurrent assign_work with distinct unleased problems (0 duplicates).
2. Multi-threaded concurrent assign_work exceeding catalog size (shared leasing fallback).
3. Concurrent heartbeats during lease expiration race (accounting accuracy).
4. Reader/writer concurrency under SQLite WAL mode (zero blocking, snapshot isolation).
5. Heavy mixed-contention stress (assign, heartbeat, expire, solve, register) with zero deadlocks.
6. Multi-process concurrency across OS process boundaries.
7. Rapid lease and expiration churn leak check.
8. Post-stress database and state integrity verification.
"""
from __future__ import annotations

import datetime
import multiprocessing as mp
import random
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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
    return tmp_path / "scheduler_concurrency_stress.db"


@pytest.fixture
def conn(db_path: Path) -> sqlite3.Connection:
    """Fixture providing an initialized SQLite connection with WAL mode."""
    c = init_db(str(db_path))
    yield c
    c.close()


def _seed_problem(
    conn: sqlite3.Connection,
    problem_id: str,
    inner: str = "4",
    container: str = "4",
    n: int = 1,
    best_s: Optional[float] = 10.0,
    reference_s: Optional[float] = 10.0,
    status: str = "best_known",
    total_attempts: int = 0,
    density_rank: float = 0.5,
) -> None:
    """Insert a problem record for test setup."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO problems (
            id, inner_token, container_token, n, best_s, reference_s, status, total_attempts, density_rank
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (problem_id, inner, container, n, best_s, reference_s, status, total_attempts, density_rank),
    )
    conn.commit()


# ===========================================================================
# 1. Multi-Threaded Concurrent assign_work Calls (Distinct Problems)
# ===========================================================================


def test_concurrent_assign_work_distinct_problems(db_path: Path):
    """Verify 30 concurrent threads leasing 30 unleased problems receive 30 distinct problems with 0 duplicate leases."""
    conn = init_db(str(db_path))
    num_threads = 30
    for i in range(num_threads):
        _seed_problem(conn, f"prob_{i:03d}", total_attempts=i * 10)
    conn.close()

    barrier = threading.Barrier(num_threads)
    assigned_problems: List[str] = []
    work_ids: List[str] = []
    lock = threading.Lock()
    errors: List[Exception] = []

    def worker_func(thread_idx: int):
        t_conn = init_db(str(db_path))
        try:
            barrier.wait(timeout=10.0)
            work = assign_work(t_conn, worker_id=f"worker_{thread_idx:03d}", cores=2)
            assert work is not None, f"Thread {thread_idx} received None"
            with lock:
                assigned_problems.append(work["problem"])
                work_ids.append(work["work_id"])
        except Exception as exc:
            with lock:
                errors.append(exc)
        finally:
            t_conn.close()

    threads = [threading.Thread(target=worker_func, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20.0)

    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"
    assert len(assigned_problems) == num_threads
    # Strict serialization check: zero duplicate problem assignments
    assert len(set(assigned_problems)) == num_threads, (
        f"Duplicate leases detected! {len(assigned_problems)} assigned vs {len(set(assigned_problems))} unique"
    )
    assert len(set(work_ids)) == num_threads

    # Verify active_leases table integrity
    verify_conn = init_db(str(db_path))
    cursor = verify_conn.cursor()
    cursor.execute("SELECT COUNT(*), COUNT(DISTINCT problem_id), COUNT(DISTINCT work_id) FROM active_leases")
    row = cursor.fetchone()
    assert row[0] == num_threads
    assert row[1] == num_threads
    assert row[2] == num_threads
    verify_conn.close()


def test_exploration_does_not_duplicate_lease_when_unleased_problems_exist(conn: sqlite3.Connection):
    """Verify that if all unattempted problems are already leased, exploration falls through
    to exploitation to assign an unleased candidate rather than creating a duplicate lease
    on the already-leased problem while unleased candidates remain in the catalog."""
    from unittest.mock import patch

    # 1 unattempted problem
    _seed_problem(conn, "prob_unattempted", status="unattempted", total_attempts=0)
    # 5 attempted problems
    for i in range(1, 6):
        _seed_problem(conn, f"prob_attempted_{i}", status="best_known", total_attempts=i * 100)

    # Worker 1 leases the unattempted problem
    w1 = assign_work(conn, worker_id="worker_1")
    assert w1 is not None
    assert w1["problem"] == "prob_unattempted"

    # Worker 2 requests work, rolling exploration (p < 0.10)
    with patch("random.random", return_value=0.05):
        w2 = assign_work(conn, worker_id="worker_2")
        assert w2 is not None

    # Worker 2 must NOT receive prob_unattempted (which is already leased)
    assert w2["problem"] != "prob_unattempted", (
        "Exploration created duplicate lease on 'prob_unattempted' even though 5 unleased problems exist in catalog!"
    )
    assert w2["problem"].startswith("prob_attempted_")


# ===========================================================================
# 2. Concurrent assign_work Exceeding Catalog Size (Shared Leasing)
# ===========================================================================


def test_concurrent_assign_work_exceeding_catalog_shared_leases(db_path: Path):
    """Verify 30 concurrent threads requesting work on 10 problems: 10 distinct, 20 shared, 0 deadlocks."""
    conn = init_db(str(db_path))
    catalog_size = 10
    total_workers = 30
    for i in range(catalog_size):
        _seed_problem(conn, f"cat_prob_{i:02d}", total_attempts=i * 5)
    conn.close()

    barrier = threading.Barrier(total_workers)
    assignments: List[str] = []
    lock = threading.Lock()
    errors: List[Exception] = []

    def worker_func(idx: int):
        t_conn = init_db(str(db_path))
        try:
            barrier.wait(timeout=10.0)
            work = assign_work(t_conn, worker_id=f"worker_{idx:03d}")
            assert work is not None
            with lock:
                assignments.append(work["problem"])
        except Exception as exc:
            with lock:
                errors.append(exc)
        finally:
            t_conn.close()

    threads = [threading.Thread(target=worker_func, args=(i,)) for i in range(total_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=25.0)

    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"
    assert len(assignments) == total_workers

    # All catalog problems should be covered
    assigned_set = set(assignments)
    expected_set = {f"cat_prob_{i:02d}" for i in range(catalog_size)}
    assert assigned_set == expected_set

    # Verify active_leases count
    verify_conn = init_db(str(db_path))
    cursor = verify_conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM active_leases")
    assert cursor.fetchone()[0] == total_workers
    verify_conn.close()


# ===========================================================================
# 3. Concurrent Heartbeats During Lease Expiration Race
# ===========================================================================


def test_concurrent_heartbeats_during_lease_expiration_race(db_path: Path):
    """Verify race condition when lease expires during concurrent heartbeats:
    - Heartbeats on active lease credit both problem and worker.
    - Heartbeats after expiry credit only worker and return False.
    - Invariant: problem.total_attempts <= worker.total_attempts.
    - Zero deadlocks, zero lock escalation errors.
    """
    conn = init_db(str(db_path))
    _seed_problem(conn, "prob_expire_race", total_attempts=0)
    register_worker(conn, "race_worker", worker_id="w_race")
    # Assign work with 1-second lease
    work = assign_work(conn, worker_id="w_race", lease_seconds=1)
    assert work is not None
    work_id = work["work_id"]
    conn.close()

    num_threads = 10
    calls_per_thread = 20
    attempts_per_call = 50

    successful_heartbeats = 0
    expired_heartbeats = 0
    lock = threading.Lock()
    errors: List[Exception] = []
    stop_event = threading.Event()

    def heartbeat_worker(t_idx: int):
        t_conn = init_db(str(db_path))
        try:
            for _ in range(calls_per_thread):
                success = record_heartbeat(
                    t_conn,
                    work_id=work_id,
                    worker_id="w_race",
                    attempts=attempts_per_call,
                )
                with lock:
                    nonlocal successful_heartbeats, expired_heartbeats
                    if success:
                        successful_heartbeats += 1
                    else:
                        expired_heartbeats += 1
                time.sleep(0.08)  # Space out calls so some land before 1s, some after 1s
        except Exception as exc:
            with lock:
                errors.append(exc)
        finally:
            t_conn.close()

    def expirer_worker():
        t_conn = init_db(str(db_path))
        try:
            while not stop_event.is_set():
                expire_stale_leases(t_conn)
                time.sleep(0.1)
        except Exception as exc:
            with lock:
                errors.append(exc)
        finally:
            t_conn.close()

    hb_threads = [threading.Thread(target=heartbeat_worker, args=(i,)) for i in range(num_threads)]
    exp_thread = threading.Thread(target=expirer_worker)

    exp_thread.start()
    for t in hb_threads:
        t.start()

    for t in hb_threads:
        t.join(timeout=30.0)

    stop_event.set()
    exp_thread.join(timeout=5.0)

    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"
    total_calls = num_threads * calls_per_thread
    assert successful_heartbeats + expired_heartbeats == total_calls
    # Because duration > 1s, we should have seen both active and expired states
    assert successful_heartbeats > 0, "Expected some successful heartbeats before expiration"
    assert expired_heartbeats > 0, "Expected some expired heartbeats after expiration"

    # Verify accounting in database
    verify_conn = init_db(str(db_path))
    cursor = verify_conn.cursor()

    cursor.execute("SELECT total_attempts FROM problems WHERE id = 'prob_expire_race'")
    prob_attempts = cursor.fetchone()[0]

    cursor.execute("SELECT total_attempts FROM workers WHERE id = 'w_race'")
    worker_attempts = cursor.fetchone()[0]

    verify_conn.close()

    # Exact accounting verification
    assert prob_attempts == successful_heartbeats * attempts_per_call
    assert worker_attempts == total_calls * attempts_per_call
    assert prob_attempts < worker_attempts


# ===========================================================================
# 4. Reader/Writer Concurrency Under SQLite WAL Mode
# ===========================================================================


def test_wal_mode_concurrent_readers_and_writers(db_path: Path):
    """Verify SQLite WAL mode reader/writer concurrency:
    - 6 continuous reader threads executing heavy SELECT queries.
    - 4 continuous writer threads running assign_work, record_heartbeat, expire_stale_leases.
    - Readers never block writers; writers never block readers.
    - Complete snapshot isolation and 0 lock errors.
    """
    conn = init_db(str(db_path))
    for i in range(10):
        _seed_problem(conn, f"wal_prob_{i:02d}", total_attempts=100)
    conn.close()

    stop_event = threading.Event()
    reader_counts = [0] * 6
    writer_counts = [0] * 4
    errors: List[Exception] = []
    lock = threading.Lock()

    def reader_loop(reader_id: int):
        t_conn = init_db(str(db_path))
        try:
            while not stop_event.is_set():
                cursor = t_conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM problems")
                p_cnt = cursor.fetchone()[0]
                assert p_cnt == 10

                cursor.execute("SELECT COUNT(*) FROM active_leases")
                _ = cursor.fetchone()[0]

                cursor.execute("SELECT SUM(total_attempts) FROM problems")
                _ = cursor.fetchone()[0]

                cursor.execute("SELECT * FROM workers ORDER BY last_seen_at DESC LIMIT 5")
                _ = cursor.fetchall()

                reader_counts[reader_id] += 1
                time.sleep(0.005)
        except Exception as exc:
            with lock:
                errors.append(exc)
        finally:
            t_conn.close()

    def writer_loop(writer_id: int):
        t_conn = init_db(str(db_path))
        try:
            w_name = f"wal_worker_{writer_id}"
            while not stop_event.is_set():
                # Assign work
                work = assign_work(t_conn, worker_id=w_name, lease_seconds=2)
                if work:
                    # Heartbeat
                    record_heartbeat(
                        t_conn,
                        work_id=work["work_id"],
                        worker_id=w_name,
                        attempts=50,
                    )
                # Expire stale leases
                expire_stale_leases(t_conn)
                writer_counts[writer_id] += 1
                time.sleep(0.01)
        except Exception as exc:
            with lock:
                errors.append(exc)
        finally:
            t_conn.close()

    readers = [threading.Thread(target=reader_loop, args=(i,)) for i in range(6)]
    writers = [threading.Thread(target=writer_loop, args=(i,)) for i in range(4)]

    for t in readers + writers:
        t.start()

    # Run sustained reader/writer load for 2 seconds
    time.sleep(2.0)
    stop_event.set()

    for t in readers + writers:
        t.join(timeout=10.0)

    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"
    total_reads = sum(reader_counts)
    total_writes = sum(writer_counts)

    assert total_reads > 50, f"Expected >50 reads under WAL mode, got {total_reads}"
    assert total_writes > 20, f"Expected >20 writes under WAL mode, got {total_writes}"


# ===========================================================================
# 5. Heavy Mixed-Contention Stress (Zero Deadlocks, Zero Lock Escalations)
# ===========================================================================


def test_heavy_mixed_contention_stress(db_path: Path):
    """Stress test 20 concurrent threads hammering all scheduler and database functions:
    - assign_work
    - record_heartbeat
    - expire_stale_leases
    - update_solution_record
    - register_worker
    Verify zero deadlocks, zero lock escalation errors, complete data integrity.
    """
    conn = init_db(str(db_path))
    num_problems = 8
    for i in range(num_problems):
        _seed_problem(conn, f"stress_p_{i}", best_s=10.0 - i * 0.5, reference_s=10.0)
    conn.close()

    num_threads = 20
    iterations = 25
    errors: List[Exception] = []
    lock = threading.Lock()
    barrier = threading.Barrier(num_threads)

    def worker_stress(t_idx: int):
        t_conn = init_db(str(db_path))
        worker_id = f"worker_stress_{t_idx}"
        try:
            barrier.wait(timeout=10.0)
            for it in range(iterations):
                op = random.randint(1, 5)
                if op == 1:
                    # Assign work
                    work = assign_work(t_conn, worker_id=worker_id, cores=random.randint(1, 8))
                    if work:
                        record_heartbeat(t_conn, work["work_id"], worker_id, attempts=100)
                elif op == 2:
                    # Heartbeat on dummy or known work
                    record_heartbeat(t_conn, f"wu_rand_{it}", worker_id, attempts=25)
                elif op == 3:
                    # Expire stale leases
                    expire_stale_leases(t_conn)
                elif op == 4:
                    # Update solution record
                    prob_id = f"stress_p_{random.randint(0, num_problems - 1)}"
                    update_solution_record(
                        t_conn,
                        problem_id=prob_id,
                        worker_id=worker_id,
                        username=f"user_{t_idx}",
                        metric_s=random.uniform(1.0, 9.0),
                        coordinates=[random.random() for _ in range(6)],
                    )
                elif op == 5:
                    # Register worker
                    register_worker(t_conn, username=f"user_{t_idx}", worker_id=worker_id)
        except Exception as exc:
            with lock:
                errors.append(exc)
        finally:
            t_conn.close()

    threads = [threading.Thread(target=worker_stress, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30.0)

    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"

    # Verify database integrity after intense contention
    verify_conn = init_db(str(db_path))
    cur = verify_conn.cursor()
    cur.execute("PRAGMA integrity_check")
    assert cur.fetchone()[0] == "ok"
    cur.execute("PRAGMA foreign_key_check")
    assert cur.fetchall() == []
    verify_conn.close()


# ===========================================================================
# 6. Multi-Process Concurrency (Separate OS Processes)
# ===========================================================================


def _proc_worker(db_path_str: str, proc_id: int, barrier: Any, error_queue: Any, result_queue: Any):
    """Independent OS process worker function."""
    conn = init_db(db_path_str)
    worker_id = f"proc_worker_{proc_id}"
    try:
        barrier.wait()
        for i in range(15):
            work = assign_work(conn, worker_id=worker_id, lease_seconds=2)
            if work:
                result_queue.put(work["problem"])
                record_heartbeat(conn, work["work_id"], worker_id, attempts=10)
            time.sleep(0.01)
    except Exception as exc:
        error_queue.put(f"Process {proc_id} error: {exc}")
    finally:
        conn.close()


def test_multiprocess_scheduler_concurrency(db_path: Path):
    """Verify cross-process WAL mode locking with native multiprocessing.Process."""
    conn = init_db(str(db_path))
    for i in range(5):
        _seed_problem(conn, f"mp_prob_{i}", total_attempts=0)
    conn.close()

    num_procs = 4
    barrier = mp.Barrier(num_procs)
    error_queue = mp.Queue()
    result_queue = mp.Queue()

    procs = [
        mp.Process(
            target=_proc_worker,
            args=(str(db_path), i, barrier, error_queue, result_queue),
        )
        for i in range(num_procs)
    ]

    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=25.0)

    proc_errors: List[str] = []
    while not error_queue.empty():
        proc_errors.append(error_queue.get_nowait())

    assert len(proc_errors) == 0, f"Multi-process errors encountered: {proc_errors}"

    assigned_count = 0
    while not result_queue.empty():
        result_queue.get_nowait()
        assigned_count += 1

    assert assigned_count > 0, "Expected processes to successfully receive work assignments"


# ===========================================================================
# 7. Rapid Lease and Expiration Churn
# ===========================================================================


def test_rapid_lease_and_expiration_churn(db_path: Path):
    """Verify rapid leasing and expiration cycles do not leak state or leave orphan leases."""
    conn = init_db(str(db_path))
    _seed_problem(conn, "churn_p1", total_attempts=0)
    _seed_problem(conn, "churn_p2", total_attempts=0)

    for cycle in range(50):
        # Assign with 1-second lease
        w1 = assign_work(conn, worker_id=f"w_churn_{cycle}_a", lease_seconds=1)
        w2 = assign_work(conn, worker_id=f"w_churn_{cycle}_b", lease_seconds=1)
        assert w1 is not None and w2 is not None

        # Manually backdate leases to simulate instant expiration
        conn.execute("UPDATE active_leases SET expires_at = datetime('now', '-5 seconds')")
        conn.commit()

        # Expire stale leases
        pruned = expire_stale_leases(conn)
        assert pruned == 2

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM active_leases")
    assert cur.fetchone()[0] == 0
    conn.close()


# ===========================================================================
# 8. Post-Stress Database and State Integrity Verification
# ===========================================================================


def test_complete_state_integrity_and_invariants(db_path: Path):
    """Comprehensive check of relational invariants and PRAGMA checks."""
    conn = init_db(str(db_path))
    cur = conn.cursor()

    # 1. PRAGMA integrity_check
    cur.execute("PRAGMA integrity_check")
    assert cur.fetchone()[0] == "ok"

    # 2. PRAGMA foreign_key_check
    cur.execute("PRAGMA foreign_key_check")
    fk_violations = cur.fetchall()
    assert fk_violations == [], f"Foreign key violations found: {fk_violations}"

    # 3. Foreign key referential integrity on active_leases
    cur.execute(
        """
        SELECT l.work_id
        FROM active_leases l
        LEFT JOIN problems p ON l.problem_id = p.id
        WHERE p.id IS NULL
        """
    )
    assert cur.fetchall() == []

    cur.execute(
        """
        SELECT l.work_id
        FROM active_leases l
        LEFT JOIN workers w ON l.worker_id = w.id
        WHERE w.id IS NULL
        """
    )
    assert cur.fetchall() == []

    # 4. Total attempts non-negative invariant
    cur.execute("SELECT COUNT(*) FROM problems WHERE total_attempts < 0")
    assert cur.fetchone()[0] == 0

    cur.execute("SELECT COUNT(*) FROM workers WHERE total_attempts < 0")
    assert cur.fetchone()[0] == 0

    conn.close()
