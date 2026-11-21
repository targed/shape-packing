"""
Adversarial and stress test harness for Coordinator REST API and SAT verifier.

Empirical Challenger verification suite testing:
1. Adversarial and corrupt payloads (malformed JSON, invalid data types, extreme strings, SQL injection).
2. Negative numbers, zero, extreme values, NaN, and Inf.
3. Geometric SAT verification strict rejections (overlapping polygons, container boundary
   penetration, reflex cutout intrusion in L-containers, coordinate count mismatches).
4. Strict database immutability: invalid solutions NEVER update database solution records,
   best_s, or worker records_broken.
5. Concurrent stress and race conditions with adversarial interference.
"""

import json
import math
import sqlite3
import pytest
from fastapi.testclient import TestClient

from shape_packing.server.app import create_app
from shape_packing.server.database import init_db


@pytest.fixture
def adv_env(tmp_path):
    """
    Sets up an isolated test database with multiple container and problem types:
    - 3_3_in_circle: 3 triangles in circle container (baseline s = 3.0)
    - 2_cir_in_circle: 2 circles in circle container (baseline s = 2.0)
    - 2_4_in_4: 2 squares in square container (baseline s = 2.0)
    - 1_cir_in_L: 1 circle in L container (baseline s = 3.0)
    """
    db_path = str(tmp_path / "adversarial_test.db")
    conn = init_db(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES
        ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', 0.80),
        ('2_cir_in_circle', 'CIRCLE', 'CIRCLE', 2, 2.0, 2.0, 'best_known', 0.85),
        ('2_4_in_4', '4', '4', 2, 2.0, 2.0, 'best_known', 0.75),
        ('1_cir_in_L', 'CIRCLE', 'L', 1, 3.0, 3.0, 'best_known', 0.70)
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    client = TestClient(app)
    return client, db_path


# =========================================================================
# Helper: Verify Database Immutability
# =========================================================================

def assert_problem_unmodified(db_path: str, problem_id: str, expected_best_s: float):
    """Assert problem best_s is unchanged and no solutions were committed."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT best_s FROM problems WHERE id = ?", (problem_id,))
    row = cur.fetchone()
    assert row is not None
    assert abs(row["best_s"] - expected_best_s) < 1e-9

    cur.execute("SELECT COUNT(*) FROM solutions WHERE problem_id = ?", (problem_id,))
    sol_count = cur.fetchone()[0]
    assert sol_count == 0, f"Expected 0 solution records for {problem_id}, found {sol_count}"
    conn.close()


# =========================================================================
# 1. Corrupt and Malformed Payloads Against All Endpoints
# =========================================================================

def test_malformed_json_on_all_post_endpoints(adv_env):
    """Sending unparseable / truncated JSON to POST endpoints returns 422 without 500 crashes."""
    client, db_path = adv_env
    corrupt_bodies = [
        b"{",
        b'{"username": "incomplete',
        b"not a json at all",
        b"",
        b"\x00\x01\x02\x03",
    ]

    for body in corrupt_bodies:
        # Register
        r1 = client.post("/api/v1/workers/register", content=body, headers={"Content-Type": "application/json"})
        assert r1.status_code == 422

        # Solutions
        r2 = client.post("/api/v1/solutions", content=body, headers={"Content-Type": "application/json"})
        assert r2.status_code == 422

        # Heartbeat
        r3 = client.post("/api/v1/heartbeat", content=body, headers={"Content-Type": "application/json"})
        assert r3.status_code == 422


def test_invalid_data_types_on_endpoints(adv_env):
    """Sending invalid data types (arrays instead of dicts, strings instead of floats) returns 422."""
    client, db_path = adv_env

    # solutions: s as string
    r = client.post(
        "/api/v1/solutions",
        json={
            "worker_id": "w1",
            "problem": "3_3_in_circle",
            "s": "not-a-float",
            "coordinates": [0.0] * 9,
        },
    )
    assert r.status_code == 422

    # solutions: coordinates as string
    r = client.post(
        "/api/v1/solutions",
        json={
            "worker_id": "w1",
            "problem": "3_3_in_circle",
            "s": 2.5,
            "coordinates": "not-a-list",
        },
    )
    assert r.status_code == 422

    # solutions: coordinates as list of non-floats
    r = client.post(
        "/api/v1/solutions",
        json={
            "worker_id": "w1",
            "problem": "3_3_in_circle",
            "s": 2.5,
            "coordinates": ["a", "b", "c", 1, 2, 3, 4, 5, 6],
        },
    )
    assert r.status_code == 422

    # heartbeat: attempts as string
    r = client.post(
        "/api/v1/heartbeat",
        json={
            "worker_id": "w1",
            "work_id": "lease1",
            "attempts_completed": "ten_thousand",
        },
    )
    assert r.status_code == 422


def test_sql_injection_and_fuzzing_safety(adv_env):
    """SQL injection payloads in string fields are safely escaped and do not corrupt SQLite."""
    client, db_path = adv_env
    sqli_payloads = [
        "' OR '1'='1",
        "admin'; DROP TABLE workers; --",
        "'; DELETE FROM problems; --",
        "\" UNION SELECT * FROM problems --",
    ]

    for sqli in sqli_payloads:
        # Register worker with SQLi username
        reg = client.post("/api/v1/workers/register", json={"username": sqli})
        assert reg.status_code == 200

        # Query problem with SQLi problem_id
        prob = client.get(f"/api/v1/problems/{sqli}")
        assert prob.status_code == 404

        # Work leasing with SQLi worker_id
        work = client.get(f"/api/v1/work?worker_id={sqli}")
        assert work.status_code in (200, 204)

    # Verify tables still exist and are intact
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM problems")
    assert cur.fetchone()[0] == 4
    cur.execute("SELECT COUNT(*) FROM workers")
    assert cur.fetchone()[0] >= 4
    conn.close()


def test_extreme_size_payloads(adv_env):
    """Oversized inputs are safely rejected or handled without crashing the server."""
    client, db_path = adv_env
    reg = client.post("/api/v1/workers/register", json={"username": "size_tester"}).json()
    w_id = reg["worker_id"]

    # Massive coordinate array (10,000 floats for a problem requiring 9)
    huge_coords = [0.0] * 10000
    r = client.post(
        "/api/v1/solutions",
        json={
            "worker_id": w_id,
            "problem": "3_3_in_circle",
            "s": 2.5,
            "coordinates": huge_coords,
        },
    )
    assert r.status_code == 400
    assert r.json()["verified"] is False
    assert_problem_unmodified(db_path, "3_3_in_circle", 3.0)

    # Massive username
    huge_username = "X" * 100000
    r_huge_user = client.post("/api/v1/workers/register", json={"username": huge_username})
    assert r_huge_user.status_code == 200


# =========================================================================
# 2. Negative Numbers, Zero, and NaN/Inf Testing
# =========================================================================

def test_negative_and_zero_metric_s_rejections(adv_env):
    """Negative and zero values for s are strictly rejected with HTTP 400 and verified: False."""
    client, db_path = adv_env
    reg = client.post("/api/v1/workers/register", json={"username": "neg_tester"}).json()
    w_id = reg["worker_id"]
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    for bad_s in [0.0, -0.00001, -1.0, -1000.0]:
        resp = client.post(
            "/api/v1/solutions",
            json={
                "worker_id": w_id,
                "problem": "3_3_in_circle",
                "s": bad_s,
                "coordinates": valid_coords,
            },
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["verified"] is False
        assert data["status"] == "rejected"
        assert "positive" in data["message"].lower() or "finite" in data["message"].lower()
        assert_problem_unmodified(db_path, "3_3_in_circle", 3.0)


def test_nan_and_inf_metric_s_rejections(adv_env):
    """NaN and Inf for s are strictly rejected with HTTP 400 and verified: False."""
    client, db_path = adv_env
    reg = client.post("/api/v1/workers/register", json={"username": "nan_s_tester"}).json()
    w_id = reg["worker_id"]
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    for val in [float("nan"), float("inf"), float("-inf")]:
        content = json.dumps(
            {
                "worker_id": w_id,
                "problem": "3_3_in_circle",
                "s": val,
                "coordinates": valid_coords,
            },
            allow_nan=True,
        )
        resp = client.post(
            "/api/v1/solutions",
            content=content,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["verified"] is False
        assert data["status"] == "rejected"
        assert_problem_unmodified(db_path, "3_3_in_circle", 3.0)


def test_nan_and_inf_in_coordinates_rejections(adv_env):
    """NaN or Inf at any coordinate index is strictly rejected with HTTP 400."""
    client, db_path = adv_env
    reg = client.post("/api/v1/workers/register", json={"username": "coord_nan_tester"}).json()
    w_id = reg["worker_id"]

    for bad_idx in [0, 4, 8]:  # start, middle, end of 9 coords
        for bad_val in [float("nan"), float("inf"), float("-inf")]:
            coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]
            coords[bad_idx] = bad_val
            content = json.dumps(
                {
                    "worker_id": w_id,
                    "problem": "3_3_in_circle",
                    "s": 2.5,
                    "coordinates": coords,
                },
                allow_nan=True,
            )
            resp = client.post(
                "/api/v1/solutions",
                content=content,
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code == 400
            data = resp.json()
            assert data["verified"] is False
            assert "NaN or Inf" in data["message"]
            assert_problem_unmodified(db_path, "3_3_in_circle", 3.0)


def test_negative_cores_and_attempts(adv_env):
    """Negative cores and negative heartbeat attempts return HTTP 400."""
    client, db_path = adv_env
    reg = client.post("/api/v1/workers/register", json={"username": "neg_worker"}).json()
    w_id = reg["worker_id"]

    # Negative cores
    r_cores = client.get(f"/api/v1/work?worker_id={w_id}&cores=-5")
    assert r_cores.status_code == 400

    r_cores0 = client.get(f"/api/v1/work?worker_id={w_id}&cores=0")
    assert r_cores0.status_code == 400

    # Negative heartbeat attempts
    r_hb = client.post(
        "/api/v1/heartbeat",
        json={
            "worker_id": w_id,
            "work_id": "any_work",
            "attempts_completed": -1,
        },
    )
    assert r_hb.status_code == 400


# =========================================================================
# 3. Geometric SAT Verification Rejections (Overlap & Out of Bounds)
# =========================================================================

def test_sat_rejection_circle_container_complete_overlap(adv_env):
    """3 triangles placed on top of each other in circle container fail SAT and return 400."""
    client, db_path = adv_env
    reg = client.post("/api/v1/workers/register", json={"username": "sat_overlap_1"}).json()
    w_id = reg["worker_id"]

    # All triangles centered at origin
    overlap_coords = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    resp = client.post(
        "/api/v1/solutions",
        json={
            "worker_id": w_id,
            "problem": "3_3_in_circle",
            "s": 2.5,
            "coordinates": overlap_coords,
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["verified"] is False
    assert "overlap" in data["message"].lower()
    assert_problem_unmodified(db_path, "3_3_in_circle", 3.0)


def test_sat_rejection_square_container_partial_overlap(adv_env):
    """2 squares penetrating each other in square container fail SAT and return 400."""
    client, db_path = adv_env
    reg = client.post("/api/v1/workers/register", json={"username": "sat_overlap_sq"}).json()
    w_id = reg["worker_id"]

    # 2 squares at (-0.5, 0, 0) and (0.5, 0, 0) overlap by depth 0.707
    overlap_sq_coords = [-0.5, 0.0, 0.0, 0.5, 0.0, 0.0]
    resp = client.post(
        "/api/v1/solutions",
        json={
            "worker_id": w_id,
            "problem": "2_4_in_4",
            "s": 1.9,
            "coordinates": overlap_sq_coords,
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["verified"] is False
    assert "overlap" in data["message"].lower()
    assert_problem_unmodified(db_path, "2_4_in_4", 2.0)


def test_sat_rejection_circles_overlap(adv_env):
    """2 circles intersecting (center distance < 2.0) fail non-overlap and return 400."""
    client, db_path = adv_env
    reg = client.post("/api/v1/workers/register", json={"username": "circle_overlap"}).json()
    w_id = reg["worker_id"]

    # Circles placed at (0, 0) and (1.0, 0). Distance = 1.0 < 2.0 -> overlap!
    colliding_circles = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    resp = client.post(
        "/api/v1/solutions",
        json={
            "worker_id": w_id,
            "problem": "2_cir_in_circle",
            "s": 1.8,
            "coordinates": colliding_circles,
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["verified"] is False
    assert "overlap" in data["message"].lower()
    assert_problem_unmodified(db_path, "2_cir_in_circle", 2.0)


def test_boundary_rejection_radial_circle_container(adv_env):
    """Triangles outside circular container radius are rejected with HTTP 400."""
    client, db_path = adv_env
    reg = client.post("/api/v1/workers/register", json={"username": "radial_oob"}).json()
    w_id = reg["worker_id"]

    # Triangle 0 placed at (50.0, 50.0), far beyond S = 2.5
    oob_coords = [50.0, 50.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]
    resp = client.post(
        "/api/v1/solutions",
        json={
            "worker_id": w_id,
            "problem": "3_3_in_circle",
            "s": 2.5,
            "coordinates": oob_coords,
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["verified"] is False
    assert "bounds" in data["message"].lower()
    assert_problem_unmodified(db_path, "3_3_in_circle", 3.0)


def test_boundary_rejection_polygonal_square_container(adv_env):
    """Square placed outside polygonal container half-planes is rejected with HTTP 400."""
    client, db_path = adv_env
    reg = client.post("/api/v1/workers/register", json={"username": "poly_oob"}).json()
    w_id = reg["worker_id"]

    # S = 1.9, container limit is ~ 1.9. Square 0 at (10.0, 0.0) violates half-plane normals
    oob_sq_coords = [10.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    resp = client.post(
        "/api/v1/solutions",
        json={
            "worker_id": w_id,
            "problem": "2_4_in_4",
            "s": 1.9,
            "coordinates": oob_sq_coords,
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["verified"] is False
    assert "bounds" in data["message"].lower() or "violation" in data["message"].lower()
    assert_problem_unmodified(db_path, "2_4_in_4", 2.0)


def test_boundary_rejection_l_container_reflex_cutout(adv_env):
    """Shape placed inside L-container reflex cutout obstacle is rejected with HTTP 400."""
    client, db_path = adv_env
    reg = client.post("/api/v1/workers/register", json={"username": "l_cutout_tester"}).json()
    w_id = reg["worker_id"]

    # 1_cir_in_L: circle placed at (1.5, 1.5, 0.0) penetrates L-container reflex cut-out
    cutout_coords = [1.5, 1.5, 0.0]
    resp = client.post(
        "/api/v1/solutions",
        json={
            "worker_id": w_id,
            "problem": "1_cir_in_L",
            "s": 2.5,
            "coordinates": cutout_coords,
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["verified"] is False
    assert "cut-out" in data["message"].lower() or "bounds" in data["message"].lower()
    assert_problem_unmodified(db_path, "1_cir_in_L", 3.0)


def test_coordinate_count_mismatches_all_rejected(adv_env):
    """Submissions with len(coordinates) != 3*N are all rejected with HTTP 400."""
    client, db_path = adv_env
    reg = client.post("/api/v1/workers/register", json={"username": "dim_tester"}).json()
    w_id = reg["worker_id"]

    # Problem 3_3_in_circle has N = 3, expects 9 coordinates
    mismatched_lengths = [
        [],                   # 0 coords
        [1.0],                # 1 coord
        [0.0] * 8,            # 8 coords (3N - 1)
        [0.0] * 10,           # 10 coords (3N + 1)
        [0.0] * 27,           # 27 coords (3 * 9)
    ]

    for coords in mismatched_lengths:
        resp = client.post(
            "/api/v1/solutions",
            json={
                "worker_id": w_id,
                "problem": "3_3_in_circle",
                "s": 2.5,
                "coordinates": coords,
            },
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["status"] == "rejected"
        assert data["verified"] is False
        assert "Expected 9 coordinates" in data["message"]
        assert_problem_unmodified(db_path, "3_3_in_circle", 3.0)


# =========================================================================
# 4. Strict Database Immutability Check
# =========================================================================

def test_database_strictly_unmodified_after_barrage_of_invalid_solutions(adv_env):
    """
    Fire a barrage of corrupt, invalid, and out-of-bounds requests.
    Verify that SQLite database remains in pristine state:
    - best_s unchanged
    - solutions table has 0 rows
    - workers records_broken is 0
    - stats endpoint reports 0 verified solutions and 0 records broken
    """
    client, db_path = adv_env
    reg = client.post("/api/v1/workers/register", json={"username": "barrage_worker"}).json()
    w_id = reg["worker_id"]

    barrage_payloads = [
        # Wrong length
        {"worker_id": w_id, "problem": "3_3_in_circle", "s": 1.0, "coordinates": [0.0]},
        # Negative s
        {"worker_id": w_id, "problem": "3_3_in_circle", "s": -5.0, "coordinates": [0.0] * 9},
        # Massive overlap
        {"worker_id": w_id, "problem": "3_3_in_circle", "s": 2.0, "coordinates": [0.0] * 9},
        # Out of bounds
        {"worker_id": w_id, "problem": "3_3_in_circle", "s": 2.0, "coordinates": [1000.0] * 9},
        # Square overlap
        {"worker_id": w_id, "problem": "2_4_in_4", "s": 1.5, "coordinates": [0.0] * 6},
        # L reflex cutout
        {"worker_id": w_id, "problem": "1_cir_in_L", "s": 2.0, "coordinates": [1.5, 1.5, 0.0]},
    ]

    for p in barrage_payloads:
        resp = client.post("/api/v1/solutions", json=p)
        assert resp.status_code == 400
        assert resp.json()["verified"] is False

    # Check database tables directly
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Solutions table must be empty
    cur.execute("SELECT COUNT(*) FROM solutions")
    assert cur.fetchone()[0] == 0

    # Problems best_s must be original baselines
    cur.execute("SELECT id, best_s FROM problems")
    probs = dict(cur.fetchall())
    assert abs(probs["3_3_in_circle"] - 3.0) < 1e-9
    assert abs(probs["2_cir_in_circle"] - 2.0) < 1e-9
    assert abs(probs["2_4_in_4"] - 2.0) < 1e-9
    assert abs(probs["1_cir_in_L"] - 3.0) < 1e-9

    # Worker records_broken must be 0
    cur.execute("SELECT records_broken FROM workers WHERE id = ?", (w_id,))
    assert cur.fetchone()[0] == 0
    conn.close()

    # Cluster stats must reflect 0 verified solutions and 0 records broken
    stats = client.get("/api/v1/stats").json()
    assert stats["verified_solutions"] == 0
    assert stats["records_broken"] == 0


# =========================================================================
# 5. Concurrent Mixed Submissions (Adversarial + Honest)
# =========================================================================

def test_concurrent_adversarial_and_honest_submissions(adv_env):
    """
    Run concurrent submissions where one worker submits an invalid overlapping payload
    and another worker submits a valid improving solution.
    The invalid submission must be rejected (400), while the valid submission succeeds (200).
    The database must reflect ONLY the valid submission.
    """
    import concurrent.futures

    client, db_path = adv_env
    r_bad = client.post("/api/v1/workers/register", json={"username": "malicious"}).json()
    r_good = client.post("/api/v1/workers/register", json={"username": "honest"}).json()

    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]
    overlap_coords = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    def submit_bad():
        return client.post(
            "/api/v1/solutions",
            json={
                "worker_id": r_bad["worker_id"],
                "problem": "3_3_in_circle",
                "s": 1.0,  # Falsely claims s = 1.0, but geometry is overlapping!
                "coordinates": overlap_coords,
            },
        )

    def submit_good():
        return client.post(
            "/api/v1/solutions",
            json={
                "worker_id": r_good["worker_id"],
                "problem": "3_3_in_circle",
                "s": 2.5,  # Valid improvement over 3.0
                "coordinates": valid_coords,
            },
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_bad = executor.submit(submit_bad)
        f_good = executor.submit(submit_good)
        res_bad = f_bad.result()
        res_good = f_good.result()

    # Verify bad was strictly rejected
    assert res_bad.status_code == 400
    assert res_bad.json()["verified"] is False
    assert res_bad.json()["status"] == "rejected"

    # Verify good was accepted
    assert res_good.status_code == 200
    assert res_good.json()["verified"] is True
    assert res_good.json()["is_new_record"] is True
    assert abs(res_good.json()["metric_s"] - 2.5) < 1e-6

    # Verify database state
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Exactly 1 solution record in DB (from honest worker)
    cur.execute("SELECT worker_id, metric_s, is_current_record FROM solutions")
    sols = cur.fetchall()
    assert len(sols) == 1
    assert sols[0]["worker_id"] == r_good["worker_id"]
    assert abs(sols[0]["metric_s"] - 2.5) < 1e-6

    # Malicious worker has 0 records broken, honest has 1
    cur.execute("SELECT records_broken FROM workers WHERE id = ?", (r_bad["worker_id"],))
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT records_broken FROM workers WHERE id = ?", (r_good["worker_id"],))
    assert cur.fetchone()[0] == 1

    # Problem best_s is 2.5
    cur.execute("SELECT best_s FROM problems WHERE id = '3_3_in_circle'")
    assert abs(cur.fetchone()[0] - 2.5) < 1e-6
    conn.close()


def test_fraudulent_metric_spoofing_rejected(adv_env):
    """
    Worker claims an impossible metric (e.g. s = 0.1) using valid coordinates
    that only fit inside a larger container (s = 2.5).
    The verifier scales container limits by inverse_friedman_metric(0.1),
    causing the coordinates to violate container boundaries and returning HTTP 400.
    """
    client, db_path = adv_env
    reg = client.post("/api/v1/workers/register", json={"username": "cheater"}).json()
    w_id = reg["worker_id"]

    # These coordinates are valid for s = 2.5, but exceed bounds if container is shrunk to s = 0.5
    coords_for_2_5 = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    resp = client.post(
        "/api/v1/solutions",
        json={
            "worker_id": w_id,
            "problem": "3_3_in_circle",
            "s": 0.5,  # Fraudulent claim
            "coordinates": coords_for_2_5,
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["verified"] is False
    assert "bounds" in data["message"].lower()
    assert_problem_unmodified(db_path, "3_3_in_circle", 3.0)


def test_concurrent_leases_and_staleness(adv_env):
    """
    Multiple workers concurrently lease work.
    Scheduler allocates without race conditions, and returns 204 when queue is exhausted.
    """
    import concurrent.futures

    client, db_path = adv_env
    # Register 10 workers
    workers = [
        client.post("/api/v1/workers/register", json={"username": f"worker_{i}"}).json()["worker_id"]
        for i in range(10)
    ]

    def get_lease(wid):
        return client.get(f"/api/v1/work?worker_id={wid}&lease_seconds=300")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(get_lease, workers))

    # All requests succeeded without crash (either 200 with lease or 204 if all leased)
    status_codes = [r.status_code for r in results]
    assert all(c in (200, 204) for c in status_codes)
    leases = [r.json() for r in results if r.status_code == 200]
    # Each leased work_id must be unique
    work_ids = [l["work_id"] for l in leases]
    assert len(work_ids) == len(set(work_ids))

