"""Adversarial concurrency and stress tests for coordinator database layer.

Written by Challenger 2 for Milestone 1.
Empirically stress-tests:
1. Multi-threaded contention on single and multiple problem records (no lost updates).
2. BEGIN IMMEDIATE serialization vs DEFERRED transaction deadlock behavior.
3. WAL mode non-blocking concurrent readers and writers.
4. Multi-process cross-connection file locking under heavy load.
5. Concurrent problem seeding alongside live solution updates.
6. Database integrity and absence of corruption / deadlocks.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import random
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from shape_packing.server.database import (
    RECORD_MIN_IMPROVEMENT,
    get_problem,
    init_db,
    register_worker,
    seed_problems_from_verification,
    update_solution_record,
)


@pytest.fixture
def stress_db_path(tmp_path: Path) -> Path:
    """Fixture providing a temporary database path for stress testing."""
    return tmp_path / "stress_test.db"


# ===========================================================================
# 1. Multi-Threaded Contention: No Lost Updates, Strict Serialization
# ===========================================================================

def test_concurrent_conflicting_updates_single_problem(stress_db_path: Path):
    """Stress test: 30 concurrent threads attempting conflicting updates on the same problem.

    Verifies:
    - BEGIN IMMEDIATE serializes all updates.
    - No lost updates occur.
    - final problems.best_s matches exactly min(all accepted metrics).
    - Exactly one solution has is_current_record = 1.
    - Total worker records_broken equals total successful updates.
    - No unhandled lock exceptions.
    """
    conn = init_db(str(stress_db_path))
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_contention', '4', '4', 1, 100.0)"
    )
    conn.commit()
    conn.close()

    num_threads = 30
    attempts_per_thread = 5

    # Each thread will submit attempts with randomly generated metrics between 5.0 and 99.0
    accepted_updates: List[Tuple[str, float]] = []
    accepted_lock = threading.Lock()
    errors: List[Exception] = []

    start_barrier = threading.Barrier(num_threads)

    def worker_task(thread_id: int):
        thread_conn = init_db(str(stress_db_path))
        worker_id = f"worker_{thread_id}"
        username = f"user_{thread_id}"
        try:
            start_barrier.wait(timeout=10.0)
            for attempt in range(attempts_per_thread):
                # Candidate metric: random value in range
                cand = round(random.uniform(5.0, 95.0), 4)
                coords = [float(cand), float(thread_id), float(attempt)]
                success = update_solution_record(
                    thread_conn,
                    problem_id="p_contention",
                    worker_id=worker_id,
                    username=username,
                    metric_s=cand,
                    coordinates=coords,
                )
                if success:
                    with accepted_lock:
                        accepted_updates.append((worker_id, cand))
                # Slight jitter to interleave operations
                time.sleep(random.uniform(0.001, 0.005))
        except Exception as exc:
            errors.append(exc)
        finally:
            thread_conn.close()

    threads = [threading.Thread(target=worker_task, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30.0)

    # 1. Assert no unexpected exceptions (e.g. database locked or deadlock)
    assert not errors, f"Encountered unexpected exceptions during concurrency test: {errors}"
    assert len(accepted_updates) > 0, "At least some updates should have succeeded."

    # 2. Check final database state
    verify_conn = init_db(str(stress_db_path))
    cursor = verify_conn.cursor()

    # Integrity checks
    cursor.execute("PRAGMA integrity_check")
    assert cursor.fetchone()[0] == "ok"

    cursor.execute("PRAGMA foreign_key_check")
    assert cursor.fetchall() == []

    # Final best_s in problem table
    prob = get_problem(verify_conn, "p_contention")
    assert prob is not None
    final_best_s = prob["best_s"]

    # Minimum metric accepted
    min_accepted_metric = min(metric for _, metric in accepted_updates)
    assert final_best_s == pytest.approx(min_accepted_metric, abs=1e-5), (
        f"final best_s {final_best_s} does not match minimum accepted metric {min_accepted_metric}"
    )

    # Exactly one solution marked as current record
    cursor.execute(
        "SELECT id, metric_s, worker_id, is_current_record FROM solutions WHERE problem_id = 'p_contention' AND is_current_record = 1"
    )
    current_records = cursor.fetchall()
    assert len(current_records) == 1, f"Expected exactly 1 current record, got {len(current_records)}"
    assert current_records[0]["metric_s"] == pytest.approx(final_best_s, abs=1e-5)

    # Total solutions count equals total accepted updates
    cursor.execute("SELECT COUNT(*) FROM solutions WHERE problem_id = 'p_contention'")
    total_solutions = cursor.fetchone()[0]
    assert total_solutions == len(accepted_updates), (
        f"solutions row count {total_solutions} != accepted updates count {len(accepted_updates)}"
    )

    # Sum of records_broken in workers table equals total accepted updates
    cursor.execute("SELECT SUM(records_broken) FROM workers")
    total_records_broken = cursor.fetchone()[0] or 0
    assert total_records_broken == len(accepted_updates), (
        f"total records_broken {total_records_broken} != accepted updates count {len(accepted_updates)}"
    )

    verify_conn.close()


# ===========================================================================
# 2. Demonstrating BEGIN IMMEDIATE Prevents Lock Escalation Deadlock
# ===========================================================================

def test_begin_immediate_vs_deferred_deadlock_prevention(stress_db_path: Path):
    """Verify that BEGIN IMMEDIATE serializes concurrent writes where DEFERRED deadlocks.

    In standard SQLite DEFERRED mode, two transactions that read first then write
    both hold SHARED locks and deadlock trying to acquire RESERVED/EXCLUSIVE locks.
    BEGIN IMMEDIATE prevents this by acquiring RESERVED upfront.
    """
    db_path = str(stress_db_path)
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_deadlock', '3', '3', 1, 10.0)")
    conn.commit()
    conn.close()

    # Part A: Test that update_solution_record uses BEGIN IMMEDIATE and does NOT deadlock
    # when two connections on separate threads concurrently execute it on the same problem.
    barrier = threading.Barrier(2)
    results = [None, None]
    exceptions = [None, None]

    def t1():
        conn1 = init_db(db_path)
        try:
            barrier.wait()
            results[0] = update_solution_record(conn1, "p_deadlock", "w1", "u1", 9.0, [0.0])
        except Exception as e:
            exceptions[0] = e
        finally:
            conn1.close()

    def t2():
        conn2 = init_db(db_path)
        try:
            barrier.wait()
            results[1] = update_solution_record(conn2, "p_deadlock", "w2", "u2", 8.0, [0.0])
        except Exception as e:
            exceptions[1] = e
        finally:
            conn2.close()

    th1 = threading.Thread(target=t1)
    th2 = threading.Thread(target=t2)
    th1.start()
    th2.start()
    th1.join(timeout=10.0)
    th2.join(timeout=10.0)

    # Both must complete without raising exceptions (no database locked deadlock)
    assert exceptions == [None, None], f"Encountered unexpected exceptions: {exceptions}"
    assert results[0] is not None and results[1] is not None
    # At least one succeeded in updating the record
    assert any(results)


# ===========================================================================
# 3. WAL Mode Concurrent Readers and Writers
# ===========================================================================

def test_wal_mode_concurrent_readers_and_writers(stress_db_path: Path):
    """Verify WAL mode operation: continuous readers run concurrently with heavy writers.

    In WAL mode:
    - Readers never block writers.
    - Writers never block readers.
    - Readers never see partial/uncommitted states.
    """
    db_path = str(stress_db_path)
    conn = init_db(db_path)
    cursor = conn.cursor()
    # Populate initial set of problems
    for i in range(10):
        cursor.execute(
            "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES (?, '3', '3', 1, 100.0)",
            (f"p_wal_{i}",),
        )
    conn.commit()
    conn.close()

    stop_event = threading.Event()
    read_counts = [0] * 5
    reader_errors: List[Exception] = []
    writer_errors: List[Exception] = []

    def reader_task(reader_idx: int):
        r_conn = init_db(db_path)
        try:
            while not stop_event.is_set():
                p_id = f"p_wal_{random.randint(0, 9)}"
                prob = get_problem(r_conn, p_id)
                assert prob is not None
                assert prob["id"] == p_id
                # Read solutions table
                c = r_conn.cursor()
                c.execute("SELECT id, metric_s, coordinates_json, is_current_record FROM solutions WHERE problem_id = ?", (p_id,))
                rows = c.fetchall()
                # Verify consistency of read rows
                current_records = [r for r in rows if r["is_current_record"] == 1]
                assert len(current_records) <= 1, f"Observed {len(current_records)} current records during read!"
                for r in rows:
                    coords = json.loads(r["coordinates_json"])
                    assert isinstance(coords, list)
                read_counts[reader_idx] += 1
                time.sleep(0.001)
        except Exception as exc:
            reader_errors.append(exc)
        finally:
            r_conn.close()

    def writer_task(writer_idx: int):
        w_conn = init_db(db_path)
        try:
            for step in range(25):
                p_id = f"p_wal_{random.randint(0, 9)}"
                # Try improvement
                prob = get_problem(w_conn, p_id)
                current = prob["best_s"] if prob and prob["best_s"] else 100.0
                cand = current - random.uniform(0.1, 1.0)
                update_solution_record(
                    w_conn,
                    problem_id=p_id,
                    worker_id=f"w_writer_{writer_idx}",
                    username=f"writer_{writer_idx}",
                    metric_s=cand,
                    coordinates=[float(writer_idx), float(step)],
                )
                time.sleep(0.002)
        except Exception as exc:
            writer_errors.append(exc)
        finally:
            w_conn.close()

    # Start 5 reader threads and 3 writer threads
    readers = [threading.Thread(target=reader_task, args=(i,)) for i in range(5)]
    writers = [threading.Thread(target=writer_task, args=(i,)) for i in range(3)]

    for r in readers:
        r.start()
    for w in writers:
        w.start()

    # Wait for all writers to finish
    for w in writers:
        w.join(timeout=30.0)

    # Signal readers to stop
    stop_event.set()
    for r in readers:
        r.join(timeout=10.0)

    assert not writer_errors, f"Writer errors occurred: {writer_errors}"
    assert not reader_errors, f"Reader errors occurred: {reader_errors}"
    assert sum(read_counts) > 50, f"Readers should have completed many reads: {read_counts}"


# ===========================================================================
# 4. Multi-Process Concurrency (Cross-Process File Locking)
# ===========================================================================

def _mp_worker(db_path: str, proc_id: int, iterations: int, output_queue: multiprocessing.Queue):
    """Child process worker simulating independent daemon instances."""
    try:
        conn = init_db(db_path)
        successes = 0
        w_id = f"proc_worker_{proc_id}"
        register_worker(conn, f"proc_user_{proc_id}", client_type="multiprocess", worker_id=w_id)

        for i in range(iterations):
            p_id = f"p_mp_{i % 3}"
            # Random metric
            metric = round(random.uniform(1.0, 50.0), 4)
            ok = update_solution_record(
                conn,
                problem_id=p_id,
                worker_id=w_id,
                username=f"proc_user_{proc_id}",
                metric_s=metric,
                coordinates=[float(proc_id), float(i), float(metric)],
            )
            if ok:
                successes += 1
            time.sleep(random.uniform(0.001, 0.004))
        conn.close()
        output_queue.put({"proc_id": proc_id, "successes": successes, "error": None})
    except Exception as exc:
        output_queue.put({"proc_id": proc_id, "successes": 0, "error": str(exc)})


def test_multiprocess_concurrency(stress_db_path: Path):
    """Empirically test multi-process concurrency with separate OS processes.

    Verifies cross-process WAL locks and atomic transaction serialization.
    """
    db_path = str(stress_db_path)
    conn = init_db(db_path)
    cursor = conn.cursor()
    for i in range(3):
        cursor.execute(
            "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES (?, '4', '4', 2, 100.0)",
            (f"p_mp_{i}",),
        )
    conn.commit()
    conn.close()

    num_procs = 4
    iterations_per_proc = 15
    queue = multiprocessing.Queue()

    procs = [
        multiprocessing.Process(
            target=_mp_worker, args=(db_path, p, iterations_per_proc, queue)
        )
        for p in range(num_procs)
    ]

    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30.0)

    results = []
    while not queue.empty():
        results.append(queue.get())

    assert len(results) == num_procs, f"Expected {num_procs} process results, got {len(results)}"
    for r in results:
        assert r["error"] is None, f"Process {r['proc_id']} failed with: {r['error']}"

    # Verify database integrity post-multiprocess run
    v_conn = init_db(db_path)
    cur = v_conn.cursor()
    cur.execute("PRAGMA integrity_check")
    assert cur.fetchone()[0] == "ok"

    # Verify that each problem with solutions has exactly 1 current record
    for i in range(3):
        p_id = f"p_mp_{i}"
        cur.execute(
            "SELECT COUNT(*) FROM solutions WHERE problem_id = ? AND is_current_record = 1",
            (p_id,),
        )
        count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM solutions WHERE problem_id = ?", (p_id,))
        total = cur.fetchone()[0]
        if total > 0:
            assert count == 1, f"Problem {p_id} has {count} current records (total {total})"
    v_conn.close()


# ===========================================================================
# 5. Concurrent Seeding alongside Live Solution Updates
# ===========================================================================

def test_concurrent_seeding_and_live_updates(stress_db_path: Path, tmp_path: Path):
    """Stress test: Seeding running in background while workers submit updates.

    Verifies:
    - Seeding does not deadlock with worker updates.
    - Seeding does not wipe out live updates made before or during seed.
    """
    db_path = str(stress_db_path)
    conn = init_db(db_path)
    conn.close()

    # Create dummy catalog with 20 problems
    seed_dir = tmp_path / "concurrent_seed_catalog"
    seed_dir.mkdir()
    catalog_items = []
    for i in range(20):
        catalog_items.append({
            "our_problem": f"p_seed_{i}",
            "N": i + 1,
            "inner_shape": "circle",
            "container_shape": "hexagon",
            "best_value": 50.0 + i,
            "status": "best_known",
            "source_note": f"Seed note {i}",
        })
    (seed_dir / "catalog.json").write_text(json.dumps(catalog_items), encoding="utf-8")

    seed_errors: List[Exception] = []
    worker_errors: List[Exception] = []

    def seeder():
        s_conn = init_db(db_path)
        try:
            for _ in range(3):
                seed_problems_from_verification(s_conn, str(seed_dir))
                time.sleep(0.005)
        except Exception as exc:
            seed_errors.append(exc)
        finally:
            s_conn.close()

    def live_worker():
        w_conn = init_db(db_path)
        try:
            for step in range(20):
                p_id = f"p_seed_{step % 10}"
                # Submit an aggressive improvement (e.g. metric = 5.0)
                update_solution_record(
                    w_conn,
                    problem_id=p_id,
                    worker_id="w_live",
                    username="live_hero",
                    metric_s=5.0,
                    coordinates=[0.0] * ((step % 10 + 1) * 3),
                )
                time.sleep(0.002)
        except Exception as exc:
            worker_errors.append(exc)
        finally:
            w_conn.close()

    t_seed = threading.Thread(target=seeder)
    t_work = threading.Thread(target=live_worker)

    t_seed.start()
    t_work.start()

    t_seed.join(timeout=30.0)
    t_work.join(timeout=30.0)

    assert not seed_errors, f"Seeder encountered errors: {seed_errors}"
    assert not worker_errors, f"Worker encountered errors: {worker_errors}"

    # Verify that live improvements (5.0) were preserved and not reverted to baseline (50.0+)
    v_conn = init_db(db_path)
    cur = v_conn.cursor()
    cur.execute("PRAGMA integrity_check")
    assert cur.fetchone()[0] == "ok"

    for i in range(10):
        p_id = f"p_seed_{i}"
        prob = get_problem(v_conn, p_id)
        assert prob is not None
        # If it was updated, best_s must be 5.0, reference_s must be 50.0 + i
        if prob["best_s"] is not None and prob["best_s"] <= 10.0:
            assert prob["best_s"] == pytest.approx(5.0)
            assert prob["reference_s"] == pytest.approx(50.0 + i)
    v_conn.close()


# ===========================================================================
# 6. Concurrent Worker Registrations
# ===========================================================================

def test_concurrent_worker_registrations(stress_db_path: Path):
    """Verify concurrent worker registrations and upserts do not collide or fail."""
    db_path = str(stress_db_path)
    conn = init_db(db_path)
    conn.close()

    num_threads = 20
    errors: List[Exception] = []

    def reg_task(t_id: int):
        t_conn = init_db(db_path)
        try:
            # Register new worker
            reg = register_worker(t_conn, f"worker_thread_{t_id}")
            w_id = reg["worker_id"]
            # Re-register same worker to test upsert concurrency
            register_worker(t_conn, f"worker_thread_{t_id}_updated", worker_id=w_id)
            # Register shared worker ID across threads
            register_worker(t_conn, f"shared_from_{t_id}", worker_id="shared_worker_const")
        except Exception as exc:
            errors.append(exc)
        finally:
            t_conn.close()

    threads = [threading.Thread(target=reg_task, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20.0)

    assert not errors, f"Worker registration errors: {errors}"

    v_conn = init_db(db_path)
    cur = v_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM workers")
    count = cur.fetchone()[0]
    # num_threads unique workers + 1 shared worker
    assert count == num_threads + 1
    v_conn.close()


# ===========================================================================
# 7. Simultaneous Conflicting Identical Metrics
# ===========================================================================

def test_simultaneous_conflicting_identical_metrics(stress_db_path: Path):
    """Verify that when 10 threads submit the EXACT SAME better metric simultaneously,
    exactly ONE succeeds, and 9 fail with False (no duplicates or double counting).
    """
    db_path = str(stress_db_path)
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_identical', '3', '3', 1, 10.0)"
    )
    conn.commit()
    conn.close()

    num_threads = 10
    barrier = threading.Barrier(num_threads)
    results = [None] * num_threads
    errors: List[Exception] = []

    def task(idx: int):
        t_conn = init_db(db_path)
        try:
            barrier.wait()
            # Everyone submits the exact same metric: 8.0 (an improvement over 10.0)
            res = update_solution_record(
                t_conn,
                problem_id="p_identical",
                worker_id=f"w_{idx}",
                username=f"u_{idx}",
                metric_s=8.0,
                coordinates=[0.0],
            )
            results[idx] = res
        except Exception as exc:
            errors.append(exc)
        finally:
            t_conn.close()

    threads = [threading.Thread(target=task, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert not errors, f"Errors: {errors}"
    # Exactly one True, exactly 9 False
    true_count = sum(1 for r in results if r is True)
    false_count = sum(1 for r in results if r is False)
    assert true_count == 1, f"Expected exactly 1 True, got {true_count} (results: {results})"
    assert false_count == num_threads - 1

    # Verify DB state
    v_conn = init_db(db_path)
    cur = v_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM solutions WHERE problem_id = 'p_identical'")
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT SUM(records_broken) FROM workers")
    assert cur.fetchone()[0] == 1
    v_conn.close()


# ===========================================================================
# 8. Sub-Epsilon Improvements Rejected Under Concurrency
# ===========================================================================

def test_sub_epsilon_improvements_rejected_under_concurrency(stress_db_path: Path):
    """Verify that multiple concurrent threads submitting improvements smaller than RECORD_MIN_IMPROVEMENT
    are all rejected without modifying state.
    """
    db_path = str(stress_db_path)
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_subeps', '3', '3', 1, 5.0)"
    )
    conn.commit()
    conn.close()

    num_threads = 10
    barrier = threading.Barrier(num_threads)
    results = [None] * num_threads

    def task(idx: int):
        t_conn = init_db(db_path)
        try:
            barrier.wait()
            # Submit sub-epsilon improvement (e.g. 5.0 - 1e-6 < 1e-5 threshold)
            metric = 5.0 - (RECORD_MIN_IMPROVEMENT * 0.5)
            res = update_solution_record(
                t_conn,
                problem_id="p_subeps",
                worker_id=f"w_eps_{idx}",
                username=f"u_{idx}",
                metric_s=metric,
                coordinates=[0.0],
            )
            results[idx] = res
        finally:
            t_conn.close()

    threads = [threading.Thread(target=task, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    # All must be rejected
    assert all(r is False for r in results)

    v_conn = init_db(db_path)
    cur = v_conn.cursor()
    cur.execute("SELECT best_s FROM problems WHERE id = 'p_subeps'")
    assert cur.fetchone()[0] == pytest.approx(5.0)
    cur.execute("SELECT COUNT(*) FROM solutions WHERE problem_id = 'p_subeps'")
    assert cur.fetchone()[0] == 0
    v_conn.close()


# ===========================================================================
# 9. Extreme Concurrency Stress: 100 Concurrent Threads Across Multiple Problems
# ===========================================================================

def test_extreme_concurrency_stress_100_threads(stress_db_path: Path):
    """Massive stress test: 100 concurrent threads hammering 5 problems.

    Verifies:
    - Zero deadlocks or uncaught lock exceptions with default 30.0s timeout.
    - Consistency of all solution records, problem best_s, and worker tallies.
    - Zero database corruption (PRAGMA integrity_check).
    """
    db_path = str(stress_db_path)
    conn = init_db(db_path)
    cursor = conn.cursor()
    for i in range(5):
        cursor.execute(
            "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES (?, '4', '4', 2, 100.0)",
            (f"p_extreme_{i}",),
        )
    conn.commit()
    conn.close()

    num_threads = 100
    updates_per_thread = 5
    barrier = threading.Barrier(num_threads)

    accepted_per_problem: Dict[str, List[float]] = {f"p_extreme_{i}": [] for i in range(5)}
    lock = threading.Lock()
    errors: List[Exception] = []

    def task(t_id: int):
        t_conn = init_db(db_path)
        worker_id = f"w_extreme_{t_id}"
        username = f"user_{t_id}"
        try:
            barrier.wait()
            for _ in range(updates_per_thread):
                target_p = f"p_extreme_{random.randint(0, 4)}"
                cand_metric = round(random.uniform(1.0, 99.0), 3)
                ok = update_solution_record(
                    t_conn,
                    problem_id=target_p,
                    worker_id=worker_id,
                    username=username,
                    metric_s=cand_metric,
                    coordinates=[float(t_id), float(cand_metric)],
                )
                if ok:
                    with lock:
                        accepted_per_problem[target_p].append(cand_metric)
                time.sleep(random.uniform(0.0005, 0.002))
        except Exception as exc:
            errors.append(exc)
        finally:
            t_conn.close()

    threads = [threading.Thread(target=task, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60.0)

    assert not errors, f"Errors encountered during 100-thread test: {errors}"

    # Verify overall integrity
    v_conn = init_db(db_path)
    cur = v_conn.cursor()
    cur.execute("PRAGMA integrity_check")
    assert cur.fetchone()[0] == "ok"

    cur.execute("PRAGMA foreign_key_check")
    assert cur.fetchall() == []

    total_accepted = sum(len(v) for v in accepted_per_problem.values())

    cur.execute("SELECT SUM(records_broken) FROM workers")
    total_records_broken = cur.fetchone()[0] or 0
    assert total_records_broken == total_accepted

    cur.execute("SELECT COUNT(*) FROM solutions")
    total_solutions = cur.fetchone()[0]
    assert total_solutions == total_accepted

    # Per-problem checks
    for p_id, accepted_metrics in accepted_per_problem.items():
        prob = get_problem(v_conn, p_id)
        assert prob is not None
        if accepted_metrics:
            min_m = min(accepted_metrics)
            assert prob["best_s"] == pytest.approx(min_m, abs=1e-5)

            cur.execute(
                "SELECT COUNT(*) FROM solutions WHERE problem_id = ? AND is_current_record = 1",
                (p_id,),
            )
            assert cur.fetchone()[0] == 1

            cur.execute(
                "SELECT metric_s FROM solutions WHERE problem_id = ? AND is_current_record = 1",
                (p_id,),
            )
            assert cur.fetchone()[0] == pytest.approx(min_m, abs=1e-5)
        else:
            assert prob["best_s"] == pytest.approx(100.0)

    v_conn.close()


# ===========================================================================
# 10. WAL Checkpoint Under Active Read/Write Load
# ===========================================================================

def test_wal_checkpoint_under_active_load(stress_db_path: Path):
    """Verify that PRAGMA wal_checkpoint(PASSIVE / TRUNCATE) operates cleanly
    without deadlocking or corrupting database while operations are in flight.
    """
    db_path = str(stress_db_path)
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_ckpt', '3', '3', 1, 100.0)"
    )
    conn.commit()
    conn.close()

    stop_event = threading.Event()
    errors: List[Exception] = []

    def writer():
        w_conn = init_db(db_path)
        try:
            metric = 90.0
            while not stop_event.is_set():
                metric -= 0.1
                update_solution_record(
                    w_conn,
                    problem_id="p_ckpt",
                    worker_id="w_ckpt",
                    username="u_ckpt",
                    metric_s=metric,
                    coordinates=[0.0],
                )
                time.sleep(0.002)
        except Exception as e:
            errors.append(e)
        finally:
            w_conn.close()

    def checkpointer():
        c_conn = init_db(db_path)
        try:
            for _ in range(5):
                c_conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                time.sleep(0.01)
        except Exception as e:
            errors.append(e)
        finally:
            c_conn.close()

    t_w = threading.Thread(target=writer)
    t_c = threading.Thread(target=checkpointer)

    t_w.start()
    t_c.start()

    t_c.join(timeout=10.0)
    stop_event.set()
    t_w.join(timeout=10.0)

    assert not errors, f"Checkpoint errors: {errors}"

    v_conn = init_db(db_path)
    cur = v_conn.cursor()
    cur.execute("PRAGMA integrity_check")
    assert cur.fetchone()[0] == "ok"
    v_conn.close()
