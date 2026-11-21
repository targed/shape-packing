"""
Comprehensive test suite for Coordinator FastAPI REST API and verification pipeline.

Tests:
1. Worker node registration (happy path, default native, web client, re-registration, validations)
2. Work unit leasing (bandit scheduling, cores scaling, proved_optimal exclusion, 204 on empty)
3. In-process geometric SAT solution verification:
   - Valid solution accepting new record
   - Valid duplicate / non-improving solution
   - Overlapping shapes rejected with HTTP 400
   - Out of bounds vertices rejected with HTTP 400
   - Coordinate vector length mismatch rejected with HTTP 400
   - NaN / Inf coordinates rejected with HTTP 400
   - Unknown problem rejected with HTTP 404
4. Heartbeat telemetry (active lease, zero keepalive, expired lease, negative attempts)
5. Global stats aggregation
6. Contributor leaderboard ranking
7. Problem detail and record coordinates lookup
8. Concurrency: atomic simultaneous solution submissions
"""

import math
import sqlite3
from typing import Tuple

import pytest
from fastapi.testclient import TestClient

from shape_packing.server.app import create_app
from shape_packing.server.database import init_db
from shape_packing.solution_tools import inverse_friedman_metric


@pytest.fixture
def app_client(tmp_path) -> Tuple[TestClient, str]:
    """Create a temporary test database and FastAPI TestClient."""
    db_path = str(tmp_path / "api_test.db")
    conn = init_db(db_path)
    cursor = conn.cursor()
    # Insert a standard benchmark test problem: 3 triangles in circle
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', 0.85)
        """
    )
    # Insert another problem: 2 circles in circle
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('2_cir_in_circle', 'CIRCLE', 'CIRCLE', 2, 2.0, 2.0, 'best_known', 0.90)
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    client = TestClient(app)
    return client, db_path


# =========================================================================
# 1. Worker Registration Tests
# =========================================================================


def test_register_worker_default_native(app_client):
    """Register worker with default native client type."""
    client, _ = app_client
    resp = client.post("/api/v1/workers/register", json={"username": "alice"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "alice"
    assert data["client_type"] == "native"
    assert data["status"] == "registered"
    assert len(data["worker_id"]) >= 10


def test_register_worker_custom_id_and_web_client(app_client):
    """Register worker with custom UUID and web client type."""
    client, _ = app_client
    custom_uuid = "custom-worker-uuid-1234"
    resp = client.post(
        "/api/v1/workers/register",
        json={"username": "bob", "client_type": "web", "worker_id": custom_uuid},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["worker_id"] == custom_uuid
    assert data["username"] == "bob"
    assert data["client_type"] == "web"


def test_register_worker_idempotent_re_registration(app_client):
    """Re-registering an existing worker_id updates the username and preserves ID."""
    client, _ = app_client
    w_id = "re-reg-id-999"
    resp1 = client.post(
        "/api/v1/workers/register",
        json={"username": "original_name", "worker_id": w_id},
    )
    assert resp1.status_code == 200

    resp2 = client.post(
        "/api/v1/workers/register",
        json={"username": "updated_name", "worker_id": w_id},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["worker_id"] == w_id
    assert data2["username"] == "updated_name"


def test_register_worker_empty_username_returns_400(app_client):
    """Empty or whitespace-only username is rejected with HTTP 400."""
    client, _ = app_client
    resp = client.post("/api/v1/workers/register", json={"username": ""})
    assert resp.status_code == 400
    assert "cannot be empty" in resp.json()["detail"]

    resp_ws = client.post("/api/v1/workers/register", json={"username": "   "})
    assert resp_ws.status_code == 400


def test_register_worker_missing_username_returns_422(app_client):
    """Payload missing required username field returns 422 Unprocessable Entity."""
    client, _ = app_client
    resp = client.post("/api/v1/workers/register", json={})
    assert resp.status_code == 422


# =========================================================================
# 2. Work Leasing Tests
# =========================================================================


def test_get_work_success(app_client):
    """Leasing work returns active work unit with all required fields."""
    client, _ = app_client
    reg = client.post("/api/v1/workers/register", json={"username": "miner_1"})
    w_id = reg.json()["worker_id"]

    resp = client.get(f"/api/v1/work?worker_id={w_id}&cores=2")
    assert resp.status_code == 200
    work = resp.json()
    assert "work_id" in work
    assert work["problem"] in ("3_3_in_circle", "2_cir_in_circle")
    assert "inner_token" in work
    assert "container_token" in work
    assert "target_s" in work
    assert work["recommended_attempts"] == 2000
    assert work["lease_seconds"] == 300
    assert work["timeout_seconds"] == 300


def test_get_work_empty_queue_returns_204(tmp_path):
    """When only proved_optimal problems exist or queue is empty, returns 204 No Content."""
    db_path = str(tmp_path / "optimal_only.db")
    conn = init_db(db_path)
    cursor = conn.cursor()
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

    reg = client.post("/api/v1/workers/register", json={"username": "worker_opt"})
    w_id = reg.json()["worker_id"]

    resp = client.get(f"/api/v1/work?worker_id={w_id}")
    assert resp.status_code == 204
    assert len(resp.content) == 0


def test_get_work_invalid_cores_returns_400(app_client):
    """cores < 1 is rejected with HTTP 400."""
    client, _ = app_client
    resp = client.get("/api/v1/work?worker_id=valid_id&cores=0")
    assert resp.status_code == 400
    assert "cores must be >= 1" in resp.json()["detail"]

    resp_neg = client.get("/api/v1/work?worker_id=valid_id&cores=-3")
    assert resp_neg.status_code == 400


def test_get_work_invalid_worker_id(app_client):
    """Empty or whitespace worker_id returns 400; missing returns 422."""
    client, _ = app_client
    resp_empty = client.get("/api/v1/work?worker_id=")
    assert resp_empty.status_code == 400

    resp_ws = client.get("/api/v1/work?worker_id=   ")
    assert resp_ws.status_code == 400

    resp_missing = client.get("/api/v1/work")
    assert resp_missing.status_code == 422


def test_get_work_cores_scaling(app_client):
    """Recommended attempts scale with core count, capped at 20000."""
    client, _ = app_client
    reg = client.post("/api/v1/workers/register", json={"username": "scaler"})
    w_id = reg.json()["worker_id"]

    work_8 = client.get(f"/api/v1/work?worker_id={w_id}&cores=8").json()
    assert work_8["recommended_attempts"] == 8000

    work_64 = client.get(f"/api/v1/work?worker_id={w_id}&cores=64").json()
    assert work_64["recommended_attempts"] == 20000


# =========================================================================
# 3. Geometric SAT Solution Verification Tests
# =========================================================================


def test_submit_valid_new_record_accepted(app_client):
    """Valid non-overlapping configuration strictly beating current best is accepted as new record."""
    client, db_path = app_client
    reg = client.post("/api/v1/workers/register", json={"username": "solver_hero"})
    w_id = reg.json()["worker_id"]

    work = client.get(f"/api/v1/work?worker_id={w_id}").json()

    # Valid placement of 3 triangles in circle with metric s = 2.5 (better than initial 3.0)
    # Triangles placed well within circle of radius 2.5
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]
    payload = {
        "work_id": work["work_id"],
        "worker_id": w_id,
        "problem": "3_3_in_circle",
        "s": 2.5,
        "coordinates": valid_coords,
    }
    resp = client.post("/api/v1/solutions", json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "accepted"
    assert res_data["verified"] is True
    assert res_data["is_new_record"] is True
    assert abs(res_data["metric_s"] - 2.5) < 1e-6

    # Verify database was updated
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT best_s FROM problems WHERE id = '3_3_in_circle'")
    assert abs(cursor.fetchone()["best_s"] - 2.5) < 1e-6

    cursor.execute("SELECT records_broken FROM workers WHERE id = ?", (w_id,))
    assert cursor.fetchone()["records_broken"] == 1
    conn.close()


def test_submit_valid_duplicate_solution(app_client):
    """Valid non-overlapping configuration that does not improve current best is accepted as duplicate."""
    client, db_path = app_client
    reg = client.post("/api/v1/workers/register", json={"username": "solver_dup"})
    w_id = reg.json()["worker_id"]

    # Problem best_s is 3.0; submit valid packing with s = 3.2 (worse than best_s)
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]
    payload = {
        "worker_id": w_id,
        "problem": "3_3_in_circle",
        "s": 3.2,
        "coordinates": valid_coords,
    }
    resp = client.post("/api/v1/solutions", json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "duplicate"
    assert res_data["verified"] is True
    assert res_data["is_new_record"] is False

    # Check best_s was NOT overwritten
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT best_s FROM problems WHERE id = '3_3_in_circle'")
    assert cursor.fetchone()["best_s"] == 3.0
    conn.close()


def test_submit_overlapping_shapes_rejected_with_400(app_client):
    """Submissions with overlapping polygons fail SAT and are rejected with HTTP 400."""
    client, _ = app_client
    reg = client.post("/api/v1/workers/register", json={"username": "overlap_tester"})
    w_id = reg.json()["worker_id"]

    # All 3 triangles placed at origin (0, 0, 0), creating massive collision
    overlap_coords = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    payload = {
        "worker_id": w_id,
        "problem": "3_3_in_circle",
        "s": 2.5,
        "coordinates": overlap_coords,
    }
    resp = client.post("/api/v1/solutions", json=payload)
    assert resp.status_code == 400
    res_data = resp.json()
    assert res_data["status"] == "rejected"
    assert res_data["verified"] is False
    assert "overlap" in res_data["message"].lower()


def test_submit_shapes_outside_boundary_rejected_with_400(app_client):
    """Submissions penetrating or outside the container boundary are rejected with HTTP 400."""
    client, _ = app_client
    reg = client.post("/api/v1/workers/register", json={"username": "boundary_tester"})
    w_id = reg.json()["worker_id"]

    # Shape 0 placed at (100.0, 100.0), far outside container radius 2.5
    oob_coords = [100.0, 100.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]
    payload = {
        "worker_id": w_id,
        "problem": "3_3_in_circle",
        "s": 2.5,
        "coordinates": oob_coords,
    }
    resp = client.post("/api/v1/solutions", json=payload)
    assert resp.status_code == 400
    res_data = resp.json()
    assert res_data["status"] == "rejected"
    assert res_data["verified"] is False
    assert "bounds" in res_data["message"].lower()


def test_submit_mismatched_coordinate_count_rejected_with_400(app_client):
    """Submissions where coordinate count != 3 * N are rejected with HTTP 400."""
    client, _ = app_client
    reg = client.post("/api/v1/workers/register", json={"username": "count_tester"})
    w_id = reg.json()["worker_id"]

    # 3_3_in_circle expects 3 * 3 = 9 coordinates. Send 5.
    payload = {
        "worker_id": w_id,
        "problem": "3_3_in_circle",
        "s": 2.5,
        "coordinates": [0.0, 0.0, 0.0, 1.0, 1.0],
    }
    resp = client.post("/api/v1/solutions", json=payload)
    assert resp.status_code == 400
    res_data = resp.json()
    assert res_data["status"] == "rejected"
    assert res_data["verified"] is False
    assert "Expected 9 coordinates" in res_data["message"]


def test_submit_nan_inf_coordinates_rejected_with_400(app_client):
    """Coordinates containing NaN or Infinity are rejected with HTTP 400."""
    client, _ = app_client
    reg = client.post("/api/v1/workers/register", json={"username": "nan_tester"})
    w_id = reg.json()["worker_id"]

    import json

    content_nan = json.dumps(
        {
            "worker_id": w_id,
            "problem": "3_3_in_circle",
            "s": 2.5,
            "coordinates": [float("nan"), 0.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0],
        },
        allow_nan=True,
    )
    resp = client.post(
        "/api/v1/solutions",
        content=content_nan,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert resp.json()["verified"] is False

    content_inf = json.dumps(
        {
            "worker_id": w_id,
            "problem": "3_3_in_circle",
            "s": 2.5,
            "coordinates": [float("inf"), 0.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0],
        },
        allow_nan=True,
    )
    resp_inf = client.post(
        "/api/v1/solutions",
        content=content_inf,
        headers={"Content-Type": "application/json"},
    )
    assert resp_inf.status_code == 400
    assert resp_inf.json()["verified"] is False


def test_submit_unknown_problem_returns_404(app_client):
    """Submitting solution for nonexistent problem returns HTTP 404."""
    client, _ = app_client
    reg = client.post("/api/v1/workers/register", json={"username": "unknown_tester"})
    w_id = reg.json()["worker_id"]

    payload = {
        "worker_id": w_id,
        "problem": "999_nonexistent_problem",
        "s": 2.5,
        "coordinates": [0.0, 0.0, 0.0],
    }
    resp = client.post("/api/v1/solutions", json=payload)
    assert resp.status_code == 404


# =========================================================================
# 4. Heartbeat Reporting Tests
# =========================================================================


def test_heartbeat_valid_active_lease(app_client):
    """Heartbeat on active lease updates both worker and problem attempt counters."""
    client, db_path = app_client
    reg = client.post("/api/v1/workers/register", json={"username": "hb_worker"})
    w_id = reg.json()["worker_id"]

    work = client.get(f"/api/v1/work?worker_id={w_id}").json()

    hb_resp = client.post(
        "/api/v1/heartbeat",
        json={
            "worker_id": w_id,
            "work_id": work["work_id"],
            "attempts_completed": 5000,
            "best_local_s": 2.8,
        },
    )
    assert hb_resp.status_code == 200
    assert hb_resp.json()["status"] == "recorded"
    assert hb_resp.json()["total_worker_attempts"] == 5000

    # Verify problem attempts also increased
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT total_attempts FROM problems WHERE id = ?", (work["problem"],))
    assert cursor.fetchone()["total_attempts"] == 5000
    conn.close()


def test_heartbeat_zero_keepalive(app_client):
    """Heartbeat with 0 attempts completed is a valid keepalive."""
    client, _ = app_client
    reg = client.post("/api/v1/workers/register", json={"username": "keepalive_w"})
    w_id = reg.json()["worker_id"]
    work = client.get(f"/api/v1/work?worker_id={w_id}").json()

    hb = client.post(
        "/api/v1/heartbeat",
        json={
            "worker_id": w_id,
            "work_id": work["work_id"],
            "attempts_completed": 0,
        },
    )
    assert hb.status_code == 200
    assert hb.json()["status"] == "recorded"


def test_heartbeat_expired_lease(app_client):
    """Heartbeat on expired lease returns 200 with ignored status, crediting worker only."""
    client, db_path = app_client
    reg = client.post("/api/v1/workers/register", json={"username": "expired_w"})
    w_id = reg.json()["worker_id"]
    work = client.get(f"/api/v1/work?worker_id={w_id}").json()

    # Artificially expire the lease in SQLite
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE active_leases SET expires_at = '2000-01-01 00:00:00' WHERE work_id = ?",
        (work["work_id"],),
    )
    conn.commit()
    conn.close()

    hb = client.post(
        "/api/v1/heartbeat",
        json={
            "worker_id": w_id,
            "work_id": work["work_id"],
            "attempts_completed": 3000,
        },
    )
    assert hb.status_code == 200
    assert hb.json()["status"] == "ignored"

    # Worker attempts credited, problem attempts not credited
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT total_attempts FROM workers WHERE id = ?", (w_id,))
    assert cursor.fetchone()["total_attempts"] == 3000

    cursor.execute("SELECT total_attempts FROM problems WHERE id = ?", (work["problem"],))
    assert cursor.fetchone()["total_attempts"] == 0
    conn.close()


def test_heartbeat_negative_attempts_returns_400(app_client):
    """Negative attempt counts are rejected with HTTP 400."""
    client, _ = app_client
    resp = client.post(
        "/api/v1/heartbeat",
        json={
            "worker_id": "wid",
            "work_id": "wuid",
            "attempts_completed": -10,
        },
    )
    assert resp.status_code == 400


# =========================================================================
# 5. Cluster Stats & Leaderboard Tests
# =========================================================================


def test_stats_and_leaderboard_endpoints(app_client):
    """Test global stats and contributor leaderboard reflect activity."""
    client, _ = app_client
    # Initial stats
    s0 = client.get("/api/v1/stats").json()
    assert s0["total_problems"] >= 2
    assert s0["active_workers"] == 0
    assert s0["total_attempts"] == 0

    # Initial leaderboard empty
    lb0 = client.get("/api/v1/leaderboard").json()
    assert isinstance(lb0, list)
    assert len(lb0) == 0

    # Register 2 workers
    r1 = client.post("/api/v1/workers/register", json={"username": "champion"}).json()
    r2 = client.post("/api/v1/workers/register", json={"username": "grinder"}).json()

    # Champion breaks record
    client.post(
        "/api/v1/solutions",
        json={
            "worker_id": r1["worker_id"],
            "problem": "3_3_in_circle",
            "s": 2.5,
            "coordinates": [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0],
        },
    )

    # Grinder does 50000 attempts
    w_grinder = client.get(f"/api/v1/work?worker_id={r2['worker_id']}").json()
    client.post(
        "/api/v1/heartbeat",
        json={
            "worker_id": r2["worker_id"],
            "work_id": w_grinder["work_id"],
            "attempts_completed": 50000,
        },
    )

    # Check updated stats
    s1 = client.get("/api/v1/stats").json()
    assert s1["active_workers"] >= 2
    assert s1["total_attempts"] == 50000
    assert s1["records_broken"] == 1

    # Check leaderboard ordering (champion with 1 record broken ranks first)
    lb1 = client.get("/api/v1/leaderboard").json()
    assert len(lb1) == 2
    assert lb1[0]["username"] == "champion"
    assert lb1[0]["records_broken"] == 1
    assert lb1[1]["username"] == "grinder"
    assert lb1[1]["total_attempts"] == 50000


def test_leaderboard_limit_query(app_client):
    """Leaderboard limit query parameter caps returned list."""
    client, _ = app_client
    for i in range(5):
        client.post("/api/v1/workers/register", json={"username": f"user_{i}"})

    resp = client.get("/api/v1/leaderboard?limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


# =========================================================================
# 6. Problem Detail Endpoint Tests
# =========================================================================


def test_problem_detail_endpoint(app_client):
    """Problem lookup returns metadata and record coordinates."""
    client, _ = app_client
    # Lookup existing problem before record submission
    resp = client.get("/api/v1/problems/3_3_in_circle")
    assert resp.status_code == 200
    pdata = resp.json()
    assert pdata["id"] == "3_3_in_circle"
    assert pdata["n"] == 3
    assert pdata["inner_token"] == "3"
    assert pdata["container_token"] == "CIRCLE"
    assert pdata["best_s"] == 3.0
    assert pdata["coordinates"] is None

    # Submit solution
    reg = client.post("/api/v1/workers/register", json={"username": "detail_tester"}).json()
    coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]
    client.post(
        "/api/v1/solutions",
        json={
            "worker_id": reg["worker_id"],
            "problem": "3_3_in_circle",
            "s": 2.5,
            "coordinates": coords,
        },
    )

    # Lookup problem again: coordinates now populated
    resp2 = client.get("/api/v1/problems/3_3_in_circle")
    assert resp2.status_code == 200
    pdata2 = resp2.json()
    assert abs(pdata2["best_s"] - 2.5) < 1e-6
    assert pdata2["coordinates"] is not None
    assert len(pdata2["coordinates"]) == 9


def test_problem_detail_not_found(app_client):
    """Nonexistent problem returns 404."""
    client, _ = app_client
    resp = client.get("/api/v1/problems/does_not_exist")
    assert resp.status_code == 404


def test_register_worker_duplicate_username(app_client):
    """Multiple workers registering with the same username succeed and receive unique worker IDs."""
    client, _ = app_client
    r1 = client.post("/api/v1/workers/register", json={"username": "common_name"})
    assert r1.status_code == 200
    r2 = client.post("/api/v1/workers/register", json={"username": "common_name"})
    assert r2.status_code == 200
    assert r1.json()["worker_id"] != r2.json()["worker_id"]
    assert r1.json()["username"] == r2.json()["username"] == "common_name"


def test_submit_invalid_metric_s_rejected(app_client):
    """Submissions with non-positive metric s are rejected with HTTP 400."""
    client, _ = app_client
    reg = client.post("/api/v1/workers/register", json={"username": "metric_tester"}).json()
    coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    resp_neg = client.post(
        "/api/v1/solutions",
        json={
            "worker_id": reg["worker_id"],
            "problem": "3_3_in_circle",
            "s": -1.0,
            "coordinates": coords,
        },
    )
    assert resp_neg.status_code == 400
    assert resp_neg.json()["verified"] is False

    resp_zero = client.post(
        "/api/v1/solutions",
        json={
            "worker_id": reg["worker_id"],
            "problem": "3_3_in_circle",
            "s": 0.0,
            "coordinates": coords,
        },
    )
    assert resp_zero.status_code == 400
    assert resp_zero.json()["verified"] is False


def test_submit_solution_empty_worker_id_rejected(app_client):
    """Submissions with empty worker_id are rejected with HTTP 400."""
    client, _ = app_client
    coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]
    resp = client.post(
        "/api/v1/solutions",
        json={
            "worker_id": "",
            "problem": "3_3_in_circle",
            "s": 2.5,
            "coordinates": coords,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["verified"] is False


def test_heartbeat_empty_identifiers_rejected(app_client):
    """Heartbeat with empty worker_id or work_id is rejected with HTTP 400."""
    client, _ = app_client
    resp1 = client.post(
        "/api/v1/heartbeat",
        json={"worker_id": "", "work_id": "valid_work", "attempts_completed": 10},
    )
    assert resp1.status_code == 400

    resp2 = client.post(
        "/api/v1/heartbeat",
        json={"worker_id": "valid_worker", "work_id": "   ", "attempts_completed": 10},
    )
    assert resp2.status_code == 400


def test_submit_concurrent_solutions_race(app_client):
    """Simultaneous solution submissions execute safely under WAL mode without locking errors."""
    import concurrent.futures

    client, db_path = app_client
    r1 = client.post("/api/v1/workers/register", json={"username": "racer_1"}).json()
    r2 = client.post("/api/v1/workers/register", json={"username": "racer_2"}).json()

    coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    def submit(worker_id, metric):
        return client.post(
            "/api/v1/solutions",
            json={
                "worker_id": worker_id,
                "problem": "3_3_in_circle",
                "s": metric,
                "coordinates": coords,
            },
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(submit, r1["worker_id"], 2.5)
        f2 = executor.submit(submit, r2["worker_id"], 2.4)
        res1 = f1.result()
        res2 = f2.result()

    assert res1.status_code == 200
    assert res2.status_code == 200
    # Both verified as valid geometry
    assert res1.json()["verified"] is True
    assert res2.json()["verified"] is True

    # Best metric in DB must be 2.4
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT best_s FROM problems WHERE id = '3_3_in_circle'")
    assert abs(cursor.fetchone()["best_s"] - 2.4) < 1e-6
    conn.close()


def test_get_db_dependency_override(tmp_path):
    """FastAPI get_db dependency can be cleanly overridden for testing isolation."""
    from shape_packing.server.app import get_db

    db_path = str(tmp_path / "custom_override.db")
    custom_conn = init_db(db_path)
    cursor = custom_conn.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status) "
        "VALUES ('override_prob', '3', 'CIRCLE', 3, 4.0, 4.0, 'best_known')"
    )
    custom_conn.commit()

    app = create_app(db_path=db_path)

    def override_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    resp = client.get("/api/v1/problems/override_prob")
    assert resp.status_code == 200
    assert resp.json()["id"] == "override_prob"
    custom_conn.close()
