"""Unit and integration tests for the coordinator database layer."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List

import pytest

from shape_packing.server.database import (
    CANONICAL_SHAPE_TOKENS,
    RECORD_MIN_IMPROVEMENT,
    get_problem,
    init_db,
    normalize_shape_token,
    register_worker,
    seed_problems_from_verification,
    update_solution_record,
)


@pytest.fixture
def mem_db() -> sqlite3.Connection:
    """Fixture providing an in-memory database with initialized schema."""
    conn = init_db(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def file_db_path(tmp_path: Path) -> Path:
    """Fixture providing a temporary file path for a file-backed SQLite database."""
    return tmp_path / "coordinator_test.db"


@pytest.fixture
def file_db(file_db_path: Path) -> sqlite3.Connection:
    """Fixture providing a file-backed SQLite database connection."""
    conn = init_db(str(file_db_path))
    yield conn
    conn.close()


# ===========================================================================
# 1. Database Initialization, WAL Mode, and Schema
# ===========================================================================

def test_init_db_creates_tables_and_indexes(mem_db: sqlite3.Connection):
    """Verify that all core tables and secondary indexes are created."""
    cursor = mem_db.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    expected_tables = {"problems", "solutions", "workers", "active_leases"}
    assert expected_tables.issubset(tables)

    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {row[0] for row in cursor.fetchall()}
    expected_indexes = {
        "idx_active_leases_problem",
        "idx_active_leases_expires",
        "idx_solutions_problem_record",
        "idx_problems_status_attempts",
        "idx_workers_records_broken",
    }
    assert expected_indexes.issubset(indexes)


def test_init_db_enables_wal_mode_on_disk(file_db: sqlite3.Connection):
    """Verify that file-backed databases enable WAL mode and foreign keys."""
    cursor = file_db.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal"

    cursor.execute("PRAGMA foreign_keys")
    fk = cursor.fetchone()[0]
    assert fk == 1


def test_init_db_supports_in_memory_without_crash():
    """Verify that :memory: databases initialize cleanly even though WAL returns 'memory'."""
    conn = init_db(":memory:")
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    assert mode.lower() in ("memory", "wal")
    conn.close()


def test_init_db_creates_nested_directories(tmp_path: Path):
    """Verify that init_db automatically creates non-existent parent directories."""
    nested_path = tmp_path / "deep" / "nested" / "dir" / "test.db"
    assert not nested_path.parent.exists()
    conn = init_db(str(nested_path))
    assert nested_path.parent.exists()
    assert nested_path.exists()
    conn.close()


def test_init_db_is_idempotent(file_db_path: Path):
    """Verify that calling init_db repeatedly does not wipe or corrupt existing data."""
    conn1 = init_db(str(file_db_path))
    register_worker(conn1, "worker1", worker_id="w-123")
    conn1.close()

    conn2 = init_db(str(file_db_path))
    cursor = conn2.cursor()
    cursor.execute("SELECT username FROM workers WHERE id = 'w-123'")
    row = cursor.fetchone()
    assert row is not None
    assert row["username"] == "worker1"
    conn2.close()


def test_foreign_keys_enforced(file_db: sqlite3.Connection):
    """Verify foreign key enforcement rejects orphaned solutions or leases."""
    cursor = file_db.cursor()
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            "INSERT INTO solutions (problem_id, metric_s, worker_username, worker_id, coordinates_json) "
            "VALUES ('nonexistent_p', 2.5, 'user', 'w1', '[]')"
        )
        file_db.commit()


# ===========================================================================
# 2. Worker Identity and Registration
# ===========================================================================

def test_register_worker_generates_uuid_when_omitted(mem_db: sqlite3.Connection):
    """Verify worker registration generates a valid UUID when worker_id is omitted."""
    info = register_worker(mem_db, "alice")
    assert "worker_id" in info
    assert len(info["worker_id"]) > 10
    assert info["username"] == "alice"
    assert info["client_type"] == "native"

    cursor = mem_db.cursor()
    cursor.execute("SELECT * FROM workers WHERE id = ?", (info["worker_id"],))
    row = cursor.fetchone()
    assert row is not None
    assert row["username"] == "alice"
    assert row["records_broken"] == 0
    assert row["total_attempts"] == 0


def test_register_worker_with_custom_id(mem_db: sqlite3.Connection):
    """Verify worker registration reuses a client-specified worker_id."""
    info = register_worker(mem_db, "bob", client_type="cluster", worker_id="custom-bob-99")
    assert info["worker_id"] == "custom-bob-99"
    assert info["username"] == "bob"
    assert info["client_type"] == "cluster"


def test_register_worker_idempotent_updates_fields(mem_db: sqlite3.Connection):
    """Verify calling register_worker with the same worker_id updates existing record without duplicate."""
    w_id = "worker-unique-1"
    info1 = register_worker(mem_db, "carol", worker_id=w_id)
    assert info1["username"] == "carol"

    # Re-register with updated username and client_type
    info2 = register_worker(mem_db, "carol_renamed", client_type="web", worker_id=w_id)
    assert info2["worker_id"] == w_id
    assert info2["username"] == "carol_renamed"
    assert info2["client_type"] == "web"

    cursor = mem_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM workers WHERE id = ?", (w_id,))
    assert cursor.fetchone()[0] == 1


# ===========================================================================
# 3. Problem Retrieval and SQL Injection Safety
# ===========================================================================

def test_get_problem_existing(mem_db: sqlite3.Connection):
    """Verify retrieving an existing problem returns a complete dictionary."""
    cursor = mem_db.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status) "
        "VALUES ('problem_1', '3', '5', 8, 2.5, 2.6, 'best_known')"
    )
    mem_db.commit()

    prob = get_problem(mem_db, "problem_1")
    assert prob is not None
    assert prob["id"] == "problem_1"
    assert prob["inner_token"] == "3"
    assert prob["container_token"] == "5"
    assert prob["n"] == 8
    assert prob["best_s"] == 2.5
    assert prob["reference_s"] == 2.6
    assert prob["status"] == "best_known"


def test_get_problem_missing_returns_none(mem_db: sqlite3.Connection):
    """Verify retrieving a non-existent problem returns None."""
    assert get_problem(mem_db, "non_existent_problem_xyz") is None


def test_get_problem_sql_injection_safe(mem_db: sqlite3.Connection):
    """Verify SQL injection strings do not compromise lookup or bypass queries."""
    cursor = mem_db.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n) VALUES ('valid_p', '4', '4', 2)"
    )
    mem_db.commit()

    injection_attempt = "' OR 1=1; --"
    assert get_problem(mem_db, injection_attempt) is None


# ===========================================================================
# 4. Atomic Record Updates and Improvement Threshold
# ===========================================================================

def test_update_solution_record_missing_problem_returns_false(mem_db: sqlite3.Connection):
    """Verify update_solution_record fails and rolls back when problem does not exist."""
    res = update_solution_record(
        mem_db,
        problem_id="unknown_p",
        worker_id="w1",
        username="alice",
        metric_s=1.5,
        coordinates=[0.0, 0.0, 0.0],
    )
    assert res is False


def test_update_solution_record_unattempted_problem(mem_db: sqlite3.Connection):
    """Verify any valid metric is accepted when best_s is None (unattempted problem)."""
    cursor = mem_db.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_init', '3', '3', 1, NULL)"
    )
    mem_db.commit()

    coords = [0.1, 0.2, 0.0]
    res = update_solution_record(
        mem_db,
        problem_id="p_init",
        worker_id="w_init",
        username="init_user",
        metric_s=3.14159,
        coordinates=coords,
    )
    assert res is True

    prob = get_problem(mem_db, "p_init")
    assert prob["best_s"] == pytest.approx(3.14159)

    cursor.execute("SELECT * FROM solutions WHERE problem_id = 'p_init'")
    sol = cursor.fetchone()
    assert sol is not None
    assert sol["is_current_record"] == 1
    assert json.loads(sol["coordinates_json"]) == coords

    cursor.execute("SELECT records_broken FROM workers WHERE id = 'w_init'")
    worker_row = cursor.fetchone()
    assert worker_row["records_broken"] == 1


def test_update_solution_record_strictly_better_metric(mem_db: sqlite3.Connection):
    """Verify that an improvement exceeding RECORD_MIN_IMPROVEMENT is accepted."""
    cursor = mem_db.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_test', '3', '3', 1, 2.00000)"
    )
    mem_db.commit()

    # Improvement of 0.00002 >= 1e-5
    new_metric = 2.00000 - 0.00002
    res = update_solution_record(
        mem_db,
        problem_id="p_test",
        worker_id="w1",
        username="alice",
        metric_s=new_metric,
        coordinates=[0.0, 0.0, 0.0],
    )
    assert res is True
    prob = get_problem(mem_db, "p_test")
    assert prob["best_s"] == pytest.approx(new_metric)


def test_update_solution_record_insufficient_improvement_rejected(mem_db: sqlite3.Connection):
    """Verify that an improvement of less than 1e-5 (e.g. 1e-6, 0, or worse) is rejected."""
    cursor = mem_db.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_thresh', '3', '3', 1, 5.0)"
    )
    mem_db.commit()

    # 1. Worse metric (> 5.0)
    assert not update_solution_record(
        mem_db, "p_thresh", "w1", "alice", metric_s=5.1, coordinates=[0.0]
    )

    # 2. Equal metric (== 5.0)
    assert not update_solution_record(
        mem_db, "p_thresh", "w1", "alice", metric_s=5.0, coordinates=[0.0]
    )

    # 3. Insufficient improvement (delta = 1e-6 < 1e-5)
    insufficient = 5.0 - (RECORD_MIN_IMPROVEMENT / 10.0)
    assert not update_solution_record(
        mem_db, "p_thresh", "w1", "alice", metric_s=insufficient, coordinates=[0.0]
    )

    # Verify best_s was untouched and no solution was committed
    prob = get_problem(mem_db, "p_thresh")
    assert prob["best_s"] == pytest.approx(5.0)

    cursor.execute("SELECT COUNT(*) FROM solutions WHERE problem_id = 'p_thresh'")
    assert cursor.fetchone()[0] == 0


def test_update_solution_record_demotes_previous_record(mem_db: sqlite3.Connection):
    """Verify that multiple consecutive record improvements leave only the latest as is_current_record=1."""
    cursor = mem_db.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_multi', '3', '3', 1, 10.0)"
    )
    mem_db.commit()

    # First improvement: 9.0
    res1 = update_solution_record(mem_db, "p_multi", "w1", "alice", 9.0, [1.0])
    assert res1 is True

    # Second improvement: 8.0
    res2 = update_solution_record(mem_db, "p_multi", "w2", "bob", 8.0, [2.0])
    assert res2 is True

    # Third improvement: 7.0
    res3 = update_solution_record(mem_db, "p_multi", "w1", "alice", 7.0, [3.0])
    assert res3 is True

    cursor.execute(
        "SELECT id, metric_s, worker_username, is_current_record FROM solutions WHERE problem_id = 'p_multi' ORDER BY id ASC"
    )
    rows = cursor.fetchall()
    assert len(rows) == 3
    assert [r["is_current_record"] for r in rows] == [0, 0, 1]
    assert rows[2]["worker_username"] == "alice"
    assert rows[2]["metric_s"] == pytest.approx(7.0)

    # Check worker leaderboard counts: alice=2, bob=1
    cursor.execute("SELECT id, records_broken FROM workers ORDER BY id ASC")
    w_rows = {r["id"]: r["records_broken"] for r in cursor.fetchall()}
    assert w_rows["w1"] == 2
    assert w_rows["w2"] == 1


def test_update_solution_record_rejects_nan_and_inf(mem_db: sqlite3.Connection):
    """Verify that NaN and Inf metrics are rejected cleanly without breaking the database."""
    cursor = mem_db.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_nan', '3', '3', 1, 5.0)"
    )
    mem_db.commit()

    assert not update_solution_record(mem_db, "p_nan", "w1", "alice", float("nan"), [0.0])
    assert not update_solution_record(mem_db, "p_nan", "w1", "alice", float("inf"), [0.0])
    assert not update_solution_record(mem_db, "p_nan", "w1", "alice", float("-inf"), [0.0])


# ===========================================================================
# 5. Concurrency Serialization with Multiple Threads
# ===========================================================================

def test_update_solution_record_concurrency_serialization(file_db_path: Path):
    """Verify that multiple concurrent threads attempting to update the same record serialize correctly."""
    conn_setup = init_db(str(file_db_path))
    cursor = conn_setup.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_race', '3', '3', 1, 10.0)"
    )
    conn_setup.commit()
    conn_setup.close()

    results: List[Dict[str, Any]] = []
    results_lock = threading.Lock()

    def worker_submission(worker_idx: int, target_metric: float):
        thread_conn = init_db(str(file_db_path))
        try:
            success = update_solution_record(
                thread_conn,
                problem_id="p_race",
                worker_id=f"w_thread_{worker_idx}",
                username=f"user_{worker_idx}",
                metric_s=target_metric,
                coordinates=[float(worker_idx)],
            )
            with results_lock:
                results.append({"worker": worker_idx, "metric": target_metric, "success": success})
        finally:
            thread_conn.close()

    # Launch 6 concurrent workers with descending candidate metrics:
    # 9.0, 8.5, 8.499995 (insufficient over 8.5), 8.0, 7.5, 7.5 (duplicate of 7.5)
    metrics = [9.0, 8.5, 8.499995, 8.0, 7.5, 7.5]
    threads = [
        threading.Thread(target=worker_submission, args=(idx, m))
        for idx, m in enumerate(metrics)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Re-open and verify final state
    verify_conn = init_db(str(file_db_path))
    prob = get_problem(verify_conn, "p_race")
    assert prob is not None
    # The lowest valid submitted metric was 7.5
    assert prob["best_s"] == pytest.approx(7.5)

    cursor = verify_conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM solutions WHERE problem_id = 'p_race' AND is_current_record = 1")
    assert cursor.fetchone()[0] == 1

    verify_conn.close()


# ===========================================================================
# 6. Shape Token Normalization and Benchmark Seeding
# ===========================================================================

def test_normalize_shape_token():
    """Verify that shape tokens are normalized to canonical solver/verifier formats."""
    # Polygons map to side numbers as strings
    assert normalize_shape_token("3") == "3"
    assert normalize_shape_token("triangle") == "3"
    assert normalize_shape_token("TRI") == "3"
    assert normalize_shape_token("4") == "4"
    assert normalize_shape_token("square") == "4"
    assert normalize_shape_token("SQU") == "4"
    assert normalize_shape_token("5") == "5"
    assert normalize_shape_token("pentagon") == "5"
    assert normalize_shape_token("6") == "6"
    assert normalize_shape_token("HEXAGON") == "6"
    assert normalize_shape_token("8") == "8"
    assert normalize_shape_token("octagon") == "8"

    # Non-polygonal shapes
    assert normalize_shape_token("circle") == "CIRCLE"
    assert normalize_shape_token("cir") == "CIRCLE"
    assert normalize_shape_token("domino") == "DOMINO"
    assert normalize_shape_token("tan") == "TAN"
    assert normalize_shape_token("l") == "L"
    assert normalize_shape_token("L-TROMINO") == "L"

    # Edge cases
    assert normalize_shape_token(None) == ""
    assert normalize_shape_token("unknown_custom") == "UNKNOWN_CUSTOM"


def test_seed_problems_missing_directory_returns_zero(mem_db: sqlite3.Connection):
    """Verify seeding handles a non-existent directory gracefully by returning 0."""
    count = seed_problems_from_verification(mem_db, "non_existent_verification_dir_123")
    assert count == 0


def test_seed_problems_tolerates_corrupt_and_non_list_files(mem_db: sqlite3.Connection, tmp_path: Path):
    """Verify seeding skips corrupt files or non-list JSON roots without halting remaining imports."""
    seed_dir = tmp_path / "packing_test_seed"
    seed_dir.mkdir()

    # 1. Valid file
    valid_data = [
        {
            "our_problem": "1_cirincir",
            "N": 1,
            "inner_shape": "circle",
            "container_shape": "circle",
            "best_value": 1.0,
            "status": "trivial",
            "source_note": "Trivial single circle",
        }
    ]
    (seed_dir / "valid.json").write_text(json.dumps(valid_data), encoding="utf-8")

    # 2. Corrupt JSON syntax
    (seed_dir / "corrupt.json").write_text("{ incomplete json syntax", encoding="utf-8")

    # 3. Non-list JSON object
    (seed_dir / "dict_root.json").write_text(json.dumps({"key": "value"}), encoding="utf-8")

    # 4. Another valid file
    valid_data2 = [
        {
            "our_problem": "2_squintan",
            "N": 2,
            "inner_shape": "square",
            "container_shape": "tan",
            "best_value": 2.414,
            "status": "best_known",
            "source_note": "Friedman benchmark",
        }
    ]
    (seed_dir / "valid2.json").write_text(json.dumps(valid_data2), encoding="utf-8")

    count = seed_problems_from_verification(mem_db, str(seed_dir))
    assert count == 2

    p1 = get_problem(mem_db, "1_CIRCLE_in_CIRCLE")
    assert p1 is not None
    assert p1["inner_token"] == "CIRCLE"
    assert p1["container_token"] == "CIRCLE"
    assert p1["best_s"] == 1.0

    p2 = get_problem(mem_db, "2_4_in_TAN")
    assert p2 is not None
    assert p2["inner_token"] == "4"
    assert p2["container_token"] == "TAN"
    assert p2["best_s"] == 2.414


def test_seed_problems_from_real_verification_catalog(mem_db: sqlite3.Connection):
    """Verify seeding the complete repository data/packingVerification catalog."""
    catalog_path = "data/packingVerification"
    if not Path(catalog_path).exists():
        pytest.skip(f"Benchmark catalog {catalog_path} not found.")

    count = seed_problems_from_verification(mem_db, catalog_path)
    assert count == 2543

    cursor = mem_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM problems")
    unique_count = cursor.fetchone()[0]
    assert unique_count == 2543

    # Verify status distribution
    cursor.execute("SELECT COUNT(*) FROM problems WHERE status = 'proved_optimal'")
    optimal_count = cursor.fetchone()[0]
    assert optimal_count == 49

    # Verify token normalization on real problem: 1_CIRCLE_in_6 has hexagon container -> normalized to '6'
    p = get_problem(mem_db, "1_CIRCLE_in_6")
    assert p is not None
    assert p["inner_token"] == "CIRCLE"
    assert p["container_token"] == "6"

    # Verify square in triangle: 3_in_4 -> '3' and '4'
    p_squ = get_problem(mem_db, "1_3_in_4")
    assert p_squ is not None
    assert p_squ["inner_token"] == "3"
    assert p_squ["container_token"] == "4"


def test_seed_preserves_improved_live_best_s(mem_db: sqlite3.Connection, tmp_path: Path):
    """Verify re-seeding updates reference_s but preserves better live best_s found by workers."""
    seed_dir = tmp_path / "live_seed_test"
    seed_dir.mkdir()

    baseline_data = [
        {
            "our_problem": "10_6_in_4",
            "N": 10,
            "inner_shape": "6",
            "container_shape": "4",
            "best_value": 3.84491,
            "status": "best_known",
            "source_note": "Initial baseline",
        }
    ]
    (seed_dir / "test.json").write_text(json.dumps(baseline_data), encoding="utf-8")

    # Initial seed
    seed_problems_from_verification(mem_db, str(seed_dir))
    p_before = get_problem(mem_db, "10_6_in_4")
    assert p_before["best_s"] == pytest.approx(3.84491)
    assert p_before["reference_s"] == pytest.approx(3.84491)

    # Live worker finds an improved solution: 3.50000
    improved = update_solution_record(
        mem_db, "10_6_in_4", "worker_hero", "hero", 3.50000, [0.0] * 30
    )
    assert improved is True
    p_improved = get_problem(mem_db, "10_6_in_4")
    assert p_improved["best_s"] == pytest.approx(3.50000)

    # Coordinator restarts and re-runs problem seeding from disk
    seed_problems_from_verification(mem_db, str(seed_dir))
    p_after_reseed = get_problem(mem_db, "10_6_in_4")

    # best_s must stay at the improved 3.50000, NOT revert to 3.84491
    assert p_after_reseed["best_s"] == pytest.approx(3.50000)
    assert p_after_reseed["reference_s"] == pytest.approx(3.84491)


# ===========================================================================
# 6. Remediation Unit Tests: Input Validation & Schema CHECK Constraints
# ===========================================================================

def test_update_solution_record_rejects_non_positive_metrics(mem_db: sqlite3.Connection):
    """Verify update_solution_record rejects non-positive metrics (s <= 0)."""
    mem_db.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_test_pos', '3', '3', 1, 5.0)"
    )
    mem_db.commit()

    for invalid_metric in [0.0, -0.0, -1.0, -1e-5, -100.0]:
        res = update_solution_record(mem_db, "p_test_pos", "w1", "user", invalid_metric, [0.0])
        assert res is False, f"metric_s={invalid_metric} should be rejected"

    # Verify best_s was not modified
    p = get_problem(mem_db, "p_test_pos")
    assert p["best_s"] == 5.0

    # Verify valid improvement still succeeds (no database poisoning)
    res_valid = update_solution_record(mem_db, "p_test_pos", "w1", "user", 4.0, [0.0])
    assert res_valid is True
    assert get_problem(mem_db, "p_test_pos")["best_s"] == 4.0


def test_update_solution_record_rejects_non_numeric_and_bool_metrics(mem_db: sqlite3.Connection):
    """Verify update_solution_record rejects non-numeric and boolean metrics without raising TypeError."""
    mem_db.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_test_types', '3', '3', 1, 5.0)"
    )
    mem_db.commit()

    for invalid_type in [None, "3.0", True, False, [1.0], {"s": 1.0}]:
        res = update_solution_record(mem_db, "p_test_types", "w1", "user", invalid_type, [0.0])
        assert res is False, f"metric_s={invalid_type!r} should be rejected"

    p = get_problem(mem_db, "p_test_types")
    assert p["best_s"] == 5.0


def test_update_solution_record_rejects_invalid_coordinates(mem_db: sqlite3.Connection):
    """Verify update_solution_record rejects coordinates containing NaN, Inf, bool, non-numeric, or non-sequences."""
    mem_db.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_test_coords', '3', '3', 1, 5.0)"
    )
    mem_db.commit()

    invalid_coords = [
        None,
        "not_a_list",
        123,
        [],
        [float("nan")],
        [float("inf")],
        [float("-inf")],
        [1.0, float("nan")],
        [1.0, float("inf")],
        [1.0, True],
        [False, 2.0],
        [1.0, "string_coord"],
        [1.0, None],
    ]
    for coords in invalid_coords:
        res = update_solution_record(mem_db, "p_test_coords", "w1", "user", 4.0, coords)
        assert res is False, f"coordinates={coords!r} should be rejected"

    # Verify 0 rows inserted in solutions
    cur = mem_db.cursor()
    cur.execute("SELECT COUNT(*) FROM solutions WHERE problem_id = 'p_test_coords'")
    assert cur.fetchone()[0] == 0
    assert get_problem(mem_db, "p_test_coords")["best_s"] == 5.0


def test_seed_problems_rejects_whitespace_ids_and_sanitizes_metrics(mem_db: sqlite3.Connection, tmp_path: Path):
    """Verify seed_problems_from_verification rejects whitespace/empty IDs and normalizes non-positive metrics."""
    seed_dir = tmp_path / "whitespace_seed_test"
    seed_dir.mkdir()

    seed_data = [
        # Whitespace problem IDs (must be skipped)
        {"our_problem": "   ", "N": 1, "inner_shape": "3", "container_shape": "3", "best_value": 1.0},
        {"our_problem": "\t  \n ", "N": 1, "inner_shape": "3", "container_shape": "3", "best_value": 1.0},
        {"our_problem": "", "N": 1, "inner_shape": "3", "container_shape": "3", "best_value": 1.0},
        # Valid ID but boolean N (must be skipped)
        {"our_problem": "p_bool_n", "N": True, "inner_shape": "3", "container_shape": "3", "best_value": 1.0},
        # Valid ID with surrounding whitespace (must be stripped)
        {"our_problem": "  p_stripped  ", "N": 1, "inner_shape": "3", "container_shape": "3", "best_value": 2.5},
        # Valid ID with zero metric (best_val normalized to None)
        {"our_problem": "p_zero_s", "N": 2, "inner_shape": "4", "container_shape": "4", "best_value": 0.0},
        # Valid ID with negative metric (best_val normalized to None)
        {"our_problem": "p_neg_s", "N": 3, "inner_shape": "4", "container_shape": "4", "best_value": -1.5},
        # Valid ID with infinite metric (best_val normalized to None)
        {"our_problem": "p_inf_s", "N": 4, "inner_shape": "4", "container_shape": "4", "best_value": "Infinity"},
        # Valid ID with boolean metric (best_val normalized to None)
        {"our_problem": "p_bool_s", "N": 5, "inner_shape": "4", "container_shape": "4", "best_value": True},
    ]
    (seed_dir / "catalog.json").write_text(json.dumps(seed_data), encoding="utf-8")

    count = seed_problems_from_verification(mem_db, str(seed_dir))
    # 5 valid problems ingested as canonical IDs: 1_3_in_3, 2_4_in_4..5_4_in_4
    assert count == 5

    # Whitespace IDs not present
    assert get_problem(mem_db, "   ") is None
    assert get_problem(mem_db, "") is None
    assert get_problem(mem_db, "p_bool_n") is None

    # Canonical ID exists
    p_stripped = get_problem(mem_db, "1_3_in_3")
    assert p_stripped is not None
    assert p_stripped["best_s"] == pytest.approx(2.5)

    # Normalized metrics are None
    for pid in ["2_4_in_4", "3_4_in_4", "4_4_in_4", "5_4_in_4"]:
        p = get_problem(mem_db, pid)
        assert p is not None
        assert p["best_s"] is None
        assert p["reference_s"] is None
        assert p["status"] == "unattempted"


def test_schema_check_constraints_enforced(mem_db: sqlite3.Connection):
    """Verify SQLite table DDL CHECK constraints reject invalid raw SQL writes."""
    # 1. problems.best_s must be > 0 and < 1e999 (or NULL)
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute(
            "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('bad_s0', '3', '3', 1, 0.0)"
        )
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute(
            "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('bad_neg', '3', '3', 1, -1.0)"
        )
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute(
            "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('bad_inf', '3', '3', 1, 1e999)"
        )

    # 2. problems.id must not be empty or whitespace-only
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute(
            "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('   ', '3', '3', 1, 1.0)"
        )

    # 3. problems.n must be > 0
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute(
            "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('bad_n', '3', '3', 0, 1.0)"
        )

    # 4. solutions.metric_s must be > 0 and < 1e999
    mem_db.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_schema_test', '3', '3', 1, 2.0)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute(
            "INSERT INTO solutions (problem_id, metric_s, worker_username, worker_id, coordinates_json) "
            "VALUES ('p_schema_test', 0.0, 'u', 'w', '[0.0]')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute(
            "INSERT INTO solutions (problem_id, metric_s, worker_username, worker_id, coordinates_json) "
            "VALUES ('p_schema_test', -2.0, 'u', 'w', '[0.0]')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute(
            "INSERT INTO solutions (problem_id, metric_s, worker_username, worker_id, coordinates_json) "
            "VALUES ('p_schema_test', 1e999, 'u', 'w', '[0.0]')"
        )


def test_init_db_migrates_missing_tier_column(tmp_path):
    """Verify init_db safely adds tier column to legacy databases missing it."""
    legacy_db = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(legacy_db)
    conn.execute(
        """
        CREATE TABLE problems (
            id TEXT PRIMARY KEY,
            inner_token TEXT NOT NULL,
            container_token TEXT NOT NULL,
            n INTEGER NOT NULL,
            best_s REAL,
            reference_s REAL,
            status TEXT NOT NULL DEFAULT 'unattempted',
            total_attempts INTEGER DEFAULT 0,
            density_rank REAL DEFAULT 0.0,
            source_attribution TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("INSERT INTO problems (id, inner_token, container_token, n) VALUES ('1_3_in_4', '3', '4', 1)")
    conn.commit()
    conn.close()

    migrated = init_db(legacy_db)
    row = get_problem(migrated, "1_3_in_4")
    assert row is not None
    assert row["tier"] == "benchmark"
    migrated.close()


def test_seed_problems_asymmetric_capabilities_and_frontier(mem_db: sqlite3.Connection, tmp_path):
    """Verify supported curved circle pairs are benchmark-seeded, invalid pairs are unsupported, and Frontier quads seed cleanly."""
    from shape_packing.server.database import seed_frontier_problems

    pv_dir = tmp_path / "pv"
    pv_dir.mkdir()
    (pv_dir / "mixed.json").write_text(
        json.dumps([
            {
                "our_problem": "1_cirinsemi",
                "N": 1,
                "inner_shape": "circle",
                "container_shape": "semicircle",
                "best_value": 2.0,
                "status": "trivial",
            },
            {
                "our_problem": "1_4_in_SEMICIRCLE",
                "N": 1,
                "inner_shape": "4",
                "container_shape": "semicircle",
                "best_value": 3.0,
                "status": "best_known",
            },
        ])
    )

    seed_problems_from_verification(mem_db, str(pv_dir))
    semi_ok = get_problem(mem_db, "1_CIRCLE_in_SEMICIRCLE")
    semi_bad = get_problem(mem_db, "1_4_in_SEMICIRCLE")
    assert semi_ok is not None and semi_ok["status"] != "unsupported" and semi_ok["tier"] == "benchmark"
    assert semi_bad is not None and semi_bad["status"] == "unsupported"

    from shape_packing.catalog import list_frontier_families

    expected_frontier = len(list_frontier_families()) * 5
    inserted = seed_frontier_problems(mem_db, max_n=5)
    assert inserted == expected_frontier
    p_front = get_problem(mem_db, "3_RHOMBUS_in_4")
    assert p_front is not None
    assert p_front["tier"] == "frontier"
    assert p_front["reference_s"] is None
    assert p_front["status"] == "unattempted"

    # Idempotent re-seed keeps count unchanged
    assert seed_frontier_problems(mem_db, max_n=5) == expected_frontier
    cur = mem_db.cursor()
    cur.execute("SELECT COUNT(*) FROM problems WHERE tier = 'frontier'")
    assert cur.fetchone()[0] == expected_frontier


def test_migrate_legacy_problem_ids_preserves_solutions_and_leases(mem_db: sqlite3.Connection):
    """Legacy IDs like 2_dominhex migrate to 2_DOMINO_in_6 without losing solutions or active leases."""
    from shape_packing.server.database import migrate_legacy_problem_ids

    mem_db.execute(
        "INSERT INTO workers (id, username, client_type) VALUES ('w1', 'alice', 'native')"
    )
    mem_db.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, tier) "
        "VALUES ('2_dominhex', 'DOMINO', '6', 2, 1.85, 1.90, 'best_known', 'benchmark')"
    )
    mem_db.execute(
        "INSERT INTO solutions (problem_id, metric_s, worker_username, worker_id, coordinates_json, is_current_record) "
        "VALUES ('2_dominhex', 1.85, 'alice', 'w1', '[0,0,0,1,0,0]', 1)"
    )
    mem_db.execute(
        "INSERT INTO active_leases (work_id, problem_id, worker_id, expires_at) "
        "VALUES ('wu_1', '2_dominhex', 'w1', datetime('now', '+5 minutes'))"
    )
    mem_db.commit()

    migrated = migrate_legacy_problem_ids(mem_db)
    assert migrated == 1
    assert get_problem(mem_db, "2_dominhex") is None
    canon = get_problem(mem_db, "2_DOMINO_in_6")
    assert canon is not None and canon["best_s"] == pytest.approx(1.85)
    sol_pid = mem_db.execute("SELECT problem_id FROM solutions WHERE worker_id = 'w1'").fetchone()[0]
    lease_pid = mem_db.execute("SELECT problem_id FROM active_leases WHERE work_id = 'wu_1'").fetchone()[0]
    assert sol_pid == "2_DOMINO_in_6"
    assert lease_pid == "2_DOMINO_in_6"

