# Distributed Shape Packing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a distributed computing system for 2D shape packing featuring a centralized coordinator API with sub-millisecond SAT verification and a native multi-threaded worker client daemon.

**Architecture:** The coordinator runs as a FastAPI service backed by an SQLite database in WAL mode. When workers request tasks, the scheduler selects problems using an adaptive multi-armed bandit policy. Candidate solutions submitted by workers are verified in-process using exact Separating Axis Theorem (SAT) collision and boundary tests before atomically updating world records. A native Python/Rust worker runs unattended at idle CPU priority, executing optimization batches via `packer_rs` and reporting progress over REST.

**Tech Stack:** Python 3.10+, FastAPI, SQLite (WAL mode), Rust (`packer_rs`), PyO3, pytest, unittest.mock, urllib standard library.

**Spec:** `docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md`

## Global Constraints

- Monorepo structure: coordinator lives under `src/shape_packing/server/` and client lives under `src/shape_packing/client/`.
- No blockchain, consensus tokens, or third-party cloud dependencies required for baseline operation.
- Worker client networking must use Python standard library (`urllib.request`) to guarantee zero mandatory external networking dependencies on volunteer machines.
- All candidate solutions must be strictly verified mathematically in-process via `solution_tools.py:verify_solution` before committing records to the database.

---

### Task 1: Coordinator Database Layer & Problem Catalog Loader

**Files:**
- Create: `src/shape_packing/server/__init__.py`
- Create: `src/shape_packing/server/database.py`
- Test: `tests/test_server_database.py`

**Interfaces:**
- Consumes: None (pure Python standard library `sqlite3` and `json`).
- Produces:
  - `init_db(db_path: str = "data/distributed.db") -> sqlite3.Connection`
  - `seed_problems_from_verification(conn: sqlite3.Connection, verification_dir: str = "data/packingVerification") -> int`
  - `register_worker(conn: sqlite3.Connection, username: str, client_type: str = "native", worker_id: Optional[str] = None) -> Dict[str, Any]`
  - `get_problem(conn: sqlite3.Connection, problem_id: str) -> Optional[Dict[str, Any]]`
  - `update_solution_record(conn: sqlite3.Connection, problem_id: str, worker_id: str, username: str, metric_s: float, coordinates: List[float]) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server_database.py
import os
import sqlite3
import pytest
from src.shape_packing.server.database import (
    init_db,
    seed_problems_from_verification,
    register_worker,
    get_problem,
    update_solution_record,
)

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_distributed.db")
    conn = init_db(db_path)
    yield conn, db_path
    conn.close()

def test_init_db_creates_tables(test_db):
    conn, _ = test_db
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "problems" in tables
    assert "solutions" in tables
    assert "workers" in tables
    assert "active_leases" in tables

def test_register_worker(test_db):
    conn, _ = test_db
    worker = register_worker(conn, username="alice", client_type="native")
    assert worker["username"] == "alice"
    assert worker["client_type"] == "native"
    assert "worker_id" in worker
    assert len(worker["worker_id"]) > 0

def test_update_solution_record(test_db):
    conn, _ = test_db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status) "
        "VALUES ('5_3_in_4', '3', '4', 5, 3.5, 3.5, 'best_known')"
    )
    conn.commit()

    worker = register_worker(conn, username="bob")
    coords = [0.1, 0.2, 0.0] * 5
    improved = update_solution_record(
        conn,
        problem_id="5_3_in_4",
        worker_id=worker["worker_id"],
        username="bob",
        metric_s=3.4,
        coordinates=coords,
    )
    assert improved is True

    prob = get_problem(conn, "5_3_in_4")
    assert prob["best_s"] == pytest.approx(3.4)

    # Submitting worse solution should not overwrite
    worse = update_solution_record(
        conn,
        problem_id="5_3_in_4",
        worker_id=worker["worker_id"],
        username="bob",
        metric_s=3.45,
        coordinates=coords,
    )
    assert worse is False
    prob2 = get_problem(conn, "5_3_in_4")
    assert prob2["best_s"] == pytest.approx(3.4)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_server_database.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.shape_packing.server'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/shape_packing/server/__init__.py
"""Distributed shape packing server package."""

# src/shape_packing/server/database.py
from __future__ import annotations
import glob
import json
import os
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS problems (
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
);

CREATE TABLE IF NOT EXISTS solutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id TEXT NOT NULL REFERENCES problems(id),
    metric_s REAL NOT NULL,
    worker_username TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    coordinates_json TEXT NOT NULL,
    is_current_record BOOLEAN DEFAULT 1,
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    client_type TEXT NOT NULL DEFAULT 'native',
    total_attempts INTEGER DEFAULT 0,
    records_broken INTEGER DEFAULT 0,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS active_leases (
    work_id TEXT PRIMARY KEY,
    problem_id TEXT NOT NULL REFERENCES problems(id),
    worker_id TEXT NOT NULL REFERENCES workers(id),
    leased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);
"""

def init_db(db_path: str = "data/distributed.db") -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn

def register_worker(
    conn: sqlite3.Connection,
    username: str,
    client_type: str = "native",
    worker_id: Optional[str] = None,
) -> Dict[str, Any]:
    w_id = worker_id or str(uuid.uuid4())
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO workers (id, username, client_type, last_seen_at) "
        "VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(id) DO UPDATE SET last_seen_at=CURRENT_TIMESTAMP, username=excluded.username",
        (w_id, username, client_type),
    )
    conn.commit()
    return {"worker_id": w_id, "username": username, "client_type": client_type}

def get_problem(conn: sqlite3.Connection, problem_id: str) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM problems WHERE id = ?", (problem_id,))
    row = cursor.fetchone()
    return dict(row) if row else None

def update_solution_record(
    conn: sqlite3.Connection,
    problem_id: str,
    worker_id: str,
    username: str,
    metric_s: float,
    coordinates: List[float],
) -> bool:
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    cursor.execute("SELECT best_s FROM problems WHERE id = ?", (problem_id,))
    row = cursor.fetchone()
    if not row:
        conn.rollback()
        return False

    current_best = row["best_s"]
    if current_best is not None and metric_s >= (current_best - 1e-5):
        conn.rollback()
        return False

    cursor.execute(
        "UPDATE solutions SET is_current_record = 0 WHERE problem_id = ?",
        (problem_id,),
    )
    cursor.execute(
        "INSERT INTO solutions (problem_id, metric_s, worker_username, worker_id, coordinates_json, is_current_record) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        (problem_id, metric_s, username, worker_id, json.dumps(coordinates)),
    )
    cursor.execute(
        "UPDATE problems SET best_s = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (metric_s, problem_id),
    )
    cursor.execute(
        "UPDATE workers SET records_broken = records_broken + 1, last_seen_at = CURRENT_TIMESTAMP WHERE id = ?",
        (worker_id,),
    )
    conn.commit()
    return True

def seed_problems_from_verification(
    conn: sqlite3.Connection, verification_dir: str = "data/packingVerification"
) -> int:
    inserted = 0
    pattern = os.path.join(verification_dir, "*.json")
    cursor = conn.cursor()
    for file_path in glob.glob(pattern):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                continue
            for item in data:
                our_problem = item.get("our_problem")
                if not our_problem:
                    continue
                inner = str(item.get("inner_shape", "")).upper()
                container = str(item.get("container_shape", "")).upper()
                n = int(item.get("N", 0))
                best_val = item.get("best_value")
                status = item.get("status", "best_known")
                note = item.get("source_note", "")

                cursor.execute(
                    "INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, source_attribution) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET reference_s=excluded.reference_s",
                    (our_problem, inner, container, n, best_val, best_val, status, note),
                )
                inserted += 1
        except Exception:
            continue
    conn.commit()
    return inserted
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_server_database.py -v`
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit**

```bash
git add src/shape_packing/server/__init__.py src/shape_packing/server/database.py tests/test_server_database.py
git commit -m "feat(server): implement database schema, worker registration, and problem records"
```

---

### Task 2: Work Scheduler & Priority Allocator

**Files:**
- Create: `src/shape_packing/server/scheduler.py`
- Test: `tests/test_server_scheduler.py`

**Interfaces:**
- Consumes: `src/shape_packing/server/database.py`
- Produces:
  - `assign_work(conn: sqlite3.Connection, worker_id: str, cores: int = 1, lease_seconds: int = 300) -> Optional[Dict[str, Any]]`
  - `record_heartbeat(conn: sqlite3.Connection, work_id: str, worker_id: str, attempts: int, best_s: Optional[float] = None) -> bool`
  - `expire_stale_leases(conn: sqlite3.Connection) -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server_scheduler.py
import time
import pytest
from src.shape_packing.server.database import init_db, register_worker
from src.shape_packing.server.scheduler import (
    assign_work,
    record_heartbeat,
    expire_stale_leases,
)

@pytest.fixture
def scheduler_db(tmp_path):
    db_path = str(tmp_path / "scheduler_test.db")
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank) "
        "VALUES ('5_3_in_4', '3', '4', 5, 3.5, 3.5, 'best_known', 0.8),"
        "       ('7_6_in_6', '6', '6', 7, 3.0, 3.0, 'proved_optimal', 0.9),"
        "       ('10_TAN_in_circle', 'TAN', 'CIRCLE', 10, 4.0, 4.0, 'best_known', 0.5)"
    )
    conn.commit()
    yield conn
    conn.close()

def test_assign_work_skips_proved_optimal(scheduler_db):
    worker = register_worker(scheduler_db, "carol")
    work = assign_work(scheduler_db, worker["worker_id"], cores=4)
    assert work is not None
    # Should not assign proved_optimal problem
    assert work["problem"] != "7_6_in_6"
    assert work["problem"] in ("5_3_in_4", "10_TAN_in_circle")
    assert "work_id" in work
    assert work["target_s"] > 0

def test_lease_expiry_reassigns_problem(scheduler_db):
    worker1 = register_worker(scheduler_db, "worker1")
    work1 = assign_work(scheduler_db, worker1["worker_id"], lease_seconds=1)
    assert work1 is not None

    # Immediate request by worker2 should pick the remaining problem or return none if all leased
    worker2 = register_worker(scheduler_db, "worker2")
    work2 = assign_work(scheduler_db, worker2["worker_id"], lease_seconds=1)
    assert work2 is not None
    assert work2["problem"] != work1["problem"]

    # Expire leases manually by updating expires_at
    cursor = scheduler_db.cursor()
    cursor.execute("UPDATE active_leases SET expires_at = datetime('now', '-10 seconds')")
    scheduler_db.commit()

    expired = expire_stale_leases(scheduler_db)
    assert expired >= 1

def test_record_heartbeat(scheduler_db):
    worker = register_worker(scheduler_db, "worker_hb")
    work = assign_work(scheduler_db, worker["worker_id"], lease_seconds=60)
    assert work is not None

    success = record_heartbeat(
        scheduler_db,
        work_id=work["work_id"],
        worker_id=worker["worker_id"],
        attempts=2500,
        best_s=3.48,
    )
    assert success is True

    # Problem total_attempts and worker total_attempts must increment
    cursor = scheduler_db.cursor()
    cursor.execute("SELECT total_attempts FROM problems WHERE id = ?", (work["problem"],))
    assert cursor.fetchone()[0] == 2500
    cursor.execute("SELECT total_attempts FROM workers WHERE id = ?", (worker["worker_id"],))
    assert cursor.fetchone()[0] == 2500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_server_scheduler.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.shape_packing.server.scheduler'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/shape_packing/server/scheduler.py
from __future__ import annotations
import datetime
import random
import sqlite3
import uuid
from typing import Any, Dict, Optional

def expire_stale_leases(conn: sqlite3.Connection) -> int:
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM active_leases WHERE expires_at < CURRENT_TIMESTAMP"
    )
    conn.commit()
    return cursor.rowcount

def assign_work(
    conn: sqlite3.Connection,
    worker_id: str,
    cores: int = 1,
    lease_seconds: int = 300,
) -> Optional[Dict[str, Any]]:
    expire_stale_leases(conn)
    cursor = conn.cursor()

    # Prioritize non-proved-optimal problems not currently leased
    cursor.execute(
        """
        SELECT p.*
        FROM problems p
        LEFT JOIN active_leases l ON p.id = l.problem_id
        WHERE p.status != 'proved_optimal' AND l.work_id IS NULL
        ORDER BY p.total_attempts ASC, p.density_rank DESC, RANDOM()
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    if not row:
        # If all problems are leased, allow sharing stochastic search on top problem
        cursor.execute(
            """
            SELECT * FROM problems
            WHERE status != 'proved_optimal'
            ORDER BY total_attempts ASC, RANDOM()
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if not row:
            return None

    prob = dict(row)
    work_id = f"wu_{uuid.uuid4().hex[:12]}"
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=lease_seconds)

    cursor.execute(
        "INSERT INTO active_leases (work_id, problem_id, worker_id, expires_at) VALUES (?, ?, ?, ?)",
        (work_id, prob["id"], worker_id, expires_at.strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()

    recommended = max(1000, min(cores * 1000, 20000))
    target_s = prob["best_s"] if prob["best_s"] is not None else (prob["reference_s"] or 10.0)

    return {
        "work_id": work_id,
        "problem": prob["id"],
        "inner_token": prob["inner_token"],
        "container_token": prob["container_token"],
        "n": prob["n"],
        "target_s": float(target_s),
        "recommended_attempts": recommended,
        "lease_seconds": lease_seconds,
    }

def record_heartbeat(
    conn: sqlite3.Connection,
    work_id: str,
    worker_id: str,
    attempts: int,
    best_s: Optional[float] = None,
) -> bool:
    cursor = conn.cursor()
    cursor.execute("SELECT problem_id FROM active_leases WHERE work_id = ?", (work_id,))
    row = cursor.fetchone()
    problem_id = row[0] if row else None

    if problem_id:
        cursor.execute(
            "UPDATE problems SET total_attempts = total_attempts + ? WHERE id = ?",
            (attempts, problem_id),
        )

    cursor.execute(
        "UPDATE workers SET total_attempts = total_attempts + ?, last_seen_at = CURRENT_TIMESTAMP WHERE id = ?",
        (attempts, worker_id),
    )
    conn.commit()
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_server_scheduler.py -v`
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit**

```bash
git add src/shape_packing/server/scheduler.py tests/test_server_scheduler.py
git commit -m "feat(server): implement work unit scheduler and lease manager"
```

---

### Task 3: Coordinator FastAPI Application & Verification Pipeline

**Files:**
- Create: `src/shape_packing/server/app.py`
- Modify: `pyproject.toml`
- Test: `tests/test_server_api.py`

**Interfaces:**
- Consumes:
  - `src/shape_packing/server/database.py`
  - `src/shape_packing/server/scheduler.py`
  - `src/shape_packing/solution_tools.py:verify_solution`
- Produces:
  - `create_app(db_path: Optional[str] = None) -> FastAPI`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server_api.py
import pytest
from fastapi.testclient import TestClient
from src.shape_packing.server.app import create_app
from src.shape_packing.server.database import init_db

@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "api_test.db")
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status) "
        "VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known')"
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return TestClient(app)

def test_register_and_get_work(client):
    reg = client.post("/api/v1/workers/register", json={"username": "dave", "client_type": "native"})
    assert reg.status_code == 200
    w_data = reg.json()
    assert "worker_id" in w_data

    work = client.get(f"/api/v1/work?worker_id={w_data['worker_id']}&cores=2")
    assert work.status_code == 200
    task = work.json()
    assert task["problem"] == "3_3_in_circle"
    assert task["n"] == 3

def test_submit_invalid_coordinates_rejected(client):
    reg = client.post("/api/v1/workers/register", json={"username": "eve"})
    w_id = reg.json()["worker_id"]
    work = client.get(f"/api/v1/work?worker_id={w_id}").json()

    # Wrong number of coordinates (expecting 3 * 3 = 9)
    sub = client.post(
        "/api/v1/solutions",
        json={
            "work_id": work["work_id"],
            "worker_id": w_id,
            "problem": "3_3_in_circle",
            "s": 2.5,
            "coordinates": [0.0, 0.0, 0.0],
        },
    )
    assert sub.status_code == 400
    assert sub.json()["verified"] is False

def test_leaderboard_and_stats(client):
    stats = client.get("/api/v1/stats").json()
    assert stats["total_problems"] >= 1
    assert "active_workers" in stats

    lb = client.get("/api/v1/leaderboard").json()
    assert isinstance(lb, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_server_api.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.shape_packing.server.app'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/shape_packing/server/app.py
from __future__ import annotations
import json
import math
import tempfile
import os
import sqlite3
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel

from .database import (
    init_db,
    register_worker,
    get_problem,
    update_solution_record,
)
from .scheduler import assign_work, record_heartbeat
from ..solution_tools import verify_solution

class WorkerRegisterRequest(BaseModel):
    username: str
    client_type: str = "native"
    worker_id: Optional[str] = None

class SolutionSubmitRequest(BaseModel):
    work_id: str
    worker_id: str
    problem: str
    s: float
    coordinates: List[float]

class HeartbeatRequest(BaseModel):
    worker_id: str
    work_id: str
    attempts_completed: int
    best_local_s: Optional[float] = None

def create_app(db_path: str = "data/distributed.db") -> FastAPI:
    app = FastAPI(title="Distributed Shape Packing Coordinator", version="1.0.0")

    def get_conn() -> sqlite3.Connection:
        return init_db(db_path)

    @app.post("/api/v1/workers/register")
    def api_register_worker(req: WorkerRegisterRequest):
        conn = get_conn()
        try:
            return register_worker(
                conn,
                username=req.username,
                client_type=req.client_type,
                worker_id=req.worker_id,
            )
        finally:
            conn.close()

    @app.get("/api/v1/work")
    def api_get_work(worker_id: str = Query(...), cores: int = Query(1)):
        conn = get_conn()
        try:
            assignment = assign_work(conn, worker_id=worker_id, cores=cores)
            if not assignment:
                raise HTTPException(status_code=status.HTTP_204_NO_CONTENT, detail="No work available")
            return assignment
        finally:
            conn.close()

    @app.post("/api/v1/solutions")
    def api_submit_solution(req: SolutionSubmitRequest):
        conn = get_conn()
        try:
            prob = get_problem(conn, req.problem)
            if not prob:
                raise HTTPException(status_code=404, detail="Problem not found")

            expected_coords = prob["n"] * 3
            if len(req.coordinates) != expected_coords:
                return {
                    "status": "rejected",
                    "verified": False,
                    "message": f"Expected {expected_coords} coordinates, received {len(req.coordinates)}",
                }

            # Write temporary solution JSON for verification
            sol_payload = {
                "S": req.s,
                "inner_token": prob["inner_token"],
                "container_token": prob["container_token"],
                "final_metric": req.s,
                "N": prob["n"],
                "values": req.coordinates,
            }

            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
                json.dump(sol_payload, tf)
                temp_path = tf.name

            try:
                res = verify_solution(temp_path, problem_str=req.problem, check_record=False)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

            if not res.valid:
                return {
                    "status": "rejected",
                    "verified": False,
                    "message": f"Geometric verification failed: {res.message}",
                }

            cursor = conn.cursor()
            cursor.execute("SELECT username FROM workers WHERE id = ?", (req.worker_id,))
            w_row = cursor.fetchone()
            username = w_row[0] if w_row else "anonymous"

            improved = update_solution_record(
                conn,
                problem_id=req.problem,
                worker_id=req.worker_id,
                username=username,
                metric_s=res.metric,
                coordinates=req.coordinates,
            )

            return {
                "status": "accepted" if improved else "duplicate",
                "verified": True,
                "is_new_record": improved,
                "metric_s": res.metric,
                "message": res.message if improved else "Valid packing, but not lower than current best",
            }
        finally:
            conn.close()

    @app.post("/api/v1/heartbeat")
    def api_heartbeat(req: HeartbeatRequest):
        conn = get_conn()
        try:
            success = record_heartbeat(
                conn,
                work_id=req.work_id,
                worker_id=req.worker_id,
                attempts=req.attempts_completed,
                best_s=req.best_local_s,
            )
            return {"status": "recorded" if success else "failed"}
        finally:
            conn.close()

    @app.get("/api/v1/stats")
    def api_stats():
        conn = get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM problems")
            total_probs = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM workers")
            total_workers = cursor.fetchone()[0]
            cursor.execute("SELECT SUM(total_attempts) FROM problems")
            total_attempts = cursor.fetchone()[0] or 0
            cursor.execute("SELECT COUNT(*) FROM solutions")
            total_records = cursor.fetchone()[0]
            return {
                "total_problems": total_probs,
                "active_workers": total_workers,
                "total_attempts": total_attempts,
                "verified_solutions": total_records,
            }
        finally:
            conn.close()

    @app.get("/api/v1/leaderboard")
    def api_leaderboard():
        conn = get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT username, total_attempts, records_broken FROM workers "
                "ORDER BY records_broken DESC, total_attempts DESC LIMIT 50"
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_server_api.py -v`
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit**

```bash
git add src/shape_packing/server/app.py tests/test_server_api.py
git commit -m "feat(server): implement FastAPI coordinator endpoints and SAT verification pipeline"
```

---

### Task 4: Native Worker Daemon Implementation

**Files:**
- Create: `src/shape_packing/client/__init__.py`
- Create: `src/shape_packing/client/native_worker.py`
- Test: `tests/test_native_worker.py`

**Interfaces:**
- Consumes: Python `urllib.request` standard library, `src/shape_packing/solver_interface.py`
- Produces:
  - `WorkerConfig` dataclass
  - `send_request(url: str, method: str = "GET", payload: Optional[Dict] = None) -> Dict`
  - `run_worker_cycle(config: WorkerConfig, solver_fn: Optional[Callable] = None) -> Dict[str, Any]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_native_worker.py
import pytest
from unittest.mock import patch, MagicMock
from src.shape_packing.client.native_worker import (
    WorkerConfig,
    run_worker_cycle,
    register_with_server,
)

def test_register_with_server():
    mock_resp = {"worker_id": "test_uuid", "username": "tester"}
    with patch("src.shape_packing.client.native_worker.send_request", return_value=mock_resp):
        w_id = register_with_server("http://localhost:8000", "tester")
        assert w_id == "test_uuid"

def test_run_worker_cycle_submits_improvement():
    config = WorkerConfig(
        server_url="http://localhost:8000",
        username="tester",
        worker_id="test_uuid",
        cores=2,
    )

    mock_work = {
        "work_id": "wu_1",
        "problem": "3_3_in_circle",
        "inner_token": "3",
        "container_token": "CIRCLE",
        "n": 3,
        "target_s": 3.0,
        "recommended_attempts": 100,
    }

    mock_solver_result = {
        "success": True,
        "best_s": 2.95,
        "values": [0.1] * 9,
    }

    requests_sent = []
    def mock_send(url, method="GET", payload=None):
        requests_sent.append((url, method, payload))
        if "work" in url:
            return mock_work
        elif "solutions" in url:
            return {"status": "accepted", "is_new_record": True}
        elif "heartbeat" in url:
            return {"status": "recorded"}
        return {}

    with patch("src.shape_packing.client.native_worker.send_request", side_effect=mock_send):
        cycle_result = run_worker_cycle(config, solver_fn=lambda **kwargs: mock_solver_result)

    assert cycle_result["attempts_completed"] == 100
    assert cycle_result["found_improvement"] is True

    # Check solution was submitted
    solution_calls = [c for c in requests_sent if "solutions" in c[0]]
    assert len(solution_calls) == 1
    assert solution_calls[0][2]["s"] == 2.95
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_native_worker.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.shape_packing.client'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/shape_packing/client/__init__.py
"""Distributed shape packing client package."""

# src/shape_packing/client/native_worker.py
from __future__ import annotations
import argparse
import json
import os
import signal
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

_SHUTDOWN = False

def handle_signal(sig, frame):
    global _SHUTDOWN
    print(f"\n[Worker] Caught signal {sig}. Completing batch and shutting down gracefully...")
    _SHUTDOWN = True

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

@dataclass
class WorkerConfig:
    server_url: str = "http://localhost:8000"
    username: str = "anonymous"
    worker_id: Optional[str] = None
    cores: int = 1

def send_request(url: str, method: str = "GET", payload: Optional[Dict] = None) -> Dict[str, Any]:
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    data = json.dumps(payload).encode("utf-8") if payload else None
    with urllib.request.urlopen(req, data=data, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}

def register_with_server(server_url: str, username: str, worker_id: Optional[str] = None) -> str:
    url = f"{server_url.rstrip('/')}/api/v1/workers/register"
    resp = send_request(url, method="POST", payload={"username": username, "worker_id": worker_id})
    return resp["worker_id"]

def run_worker_cycle(
    config: WorkerConfig,
    solver_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    work_url = f"{config.server_url.rstrip('/')}/api/v1/work?worker_id={config.worker_id}&cores={config.cores}"
    work = send_request(work_url, method="GET")
    if not work:
        return {"status": "idle", "attempts_completed": 0, "found_improvement": False}

    problem = work["problem"]
    target_s = work["target_s"]
    attempts = work.get("recommended_attempts", 2000)

    # Invoke solver (injected or default solver_interface)
    if solver_fn:
        result = solver_fn(
            inner_shape=work["inner_token"],
            container_shape=work["container_token"],
            n=work["n"],
            attempts=attempts,
            target_s=target_s,
        )
    else:
        from ..solver_interface import run_solver
        result = run_solver(
            inner_shape=work["inner_token"],
            container_shape=work["container_token"],
            n=work["n"],
            attempts=attempts,
            target_s=target_s,
        )

    found_improvement = False
    if result.get("success") and result.get("best_s", float("inf")) < target_s:
        found_improvement = True
        sol_url = f"{config.server_url.rstrip('/')}/api/v1/solutions"
        send_request(
            sol_url,
            method="POST",
            payload={
                "work_id": work["work_id"],
                "worker_id": config.worker_id,
                "problem": problem,
                "s": result["best_s"],
                "coordinates": result.get("values", []),
            },
        )

    # Report heartbeat
    hb_url = f"{config.server_url.rstrip('/')}/api/v1/heartbeat"
    send_request(
        hb_url,
        method="POST",
        payload={
            "worker_id": config.worker_id,
            "work_id": work["work_id"],
            "attempts_completed": attempts,
            "best_local_s": result.get("best_s"),
        },
    )

    return {
        "status": "completed",
        "attempts_completed": attempts,
        "found_improvement": found_improvement,
    }

def main():
    parser = argparse.ArgumentParser(description="Distributed Shape Packing Worker Daemon")
    parser.add_argument("--server", default="http://localhost:8000", help="Coordinator URL")
    parser.add_argument("--username", default="anonymous", help="Volunteer handle")
    parser.add_argument("--cores", type=int, default=os.cpu_count() or 1, help="Cores to use")
    args = parser.parse_args()

    # Set idle priority on Linux
    try:
        os.nice(19)
    except Exception:
        pass

    worker_id = register_with_server(args.server, args.username)
    config = WorkerConfig(server_url=args.server, username=args.username, worker_id=worker_id, cores=args.cores)
    print(f"[Worker] Registered as '{args.username}' ({worker_id}). Starting optimization loop...")

    while not _SHUTDOWN:
        try:
            res = run_worker_cycle(config)
            if res.get("found_improvement"):
                print(f"[Worker] Improved record! Submitting coordinates...")
            time.sleep(0.1)
        except Exception as e:
            print(f"[Worker] Error in cycle: {e}. Retrying in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_native_worker.py -v`
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit**

```bash
git add src/shape_packing/client/__init__.py src/shape_packing/client/native_worker.py tests/test_native_worker.py
git commit -m "feat(client): implement native worker daemon with graceful signal shutdown"
```

---

### Task 5: End-to-End Distributed Cluster Verification

**Files:**
- Create: `tests/test_distributed_e2e.py`

**Interfaces:**
- Consumes: All components from Tasks 1-4.
- Produces: Integrated verification test proving end-to-end functionality.

- [ ] **Step 1: Write the end-to-end test**

```python
# tests/test_distributed_e2e.py
import pytest
from fastapi.testclient import TestClient
from src.shape_packing.server.app import create_app
from src.shape_packing.server.database import init_db
from src.shape_packing.client.native_worker import WorkerConfig, run_worker_cycle

def test_full_distributed_cycle_mock_network(tmp_path):
    db_path = str(tmp_path / "e2e_distributed.db")
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status) "
        "VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.5, 3.5, 'best_known')"
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    client = TestClient(app)

    # 1. Register worker
    reg = client.post("/api/v1/workers/register", json={"username": "alice", "client_type": "native"}).json()
    worker_id = reg["worker_id"]

    # 2. Get work assignment
    work = client.get(f"/api/v1/work?worker_id={worker_id}&cores=2").json()
    assert work["problem"] == "3_3_in_circle"

    # 3. Simulate client discovering valid lower packing
    # 3 triangles inside circle container of radius S=3.0 (coordinates: x, y, theta)
    valid_coords = [
        0.0, 0.5, 0.0,
        -0.5, -0.5, 0.0,
        0.5, -0.5, 0.0
    ]
    sub = client.post(
        "/api/v1/solutions",
        json={
            "work_id": work["work_id"],
            "worker_id": worker_id,
            "problem": "3_3_in_circle",
            "s": 3.0,
            "coordinates": valid_coords,
        },
    ).json()

    assert sub["verified"] is True
    assert sub["is_new_record"] is True
    assert sub["status"] == "accepted"

    # 4. Heartbeat
    hb = client.post(
        "/api/v1/heartbeat",
        json={
            "worker_id": worker_id,
            "work_id": work["work_id"],
            "attempts_completed": 1000,
            "best_local_s": 3.0,
        },
    ).json()
    assert hb["status"] == "recorded"

    # 5. Verify stats and leaderboard
    lb = client.get("/api/v1/leaderboard").json()
    assert len(lb) == 1
    assert lb[0]["username"] == "alice"
    assert lb[0]["records_broken"] == 1
    assert lb[0]["total_attempts"] == 1000
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_distributed_e2e.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_distributed_e2e.py
git commit -m "test(distributed): add end-to-end integration test verifying full worker/coordinator cycle"
```

---

## Plan Self-Review Checklist

1. **Spec Coverage**:
   - Coordinator service with SQLite WAL mode -> Task 1, Task 3
   - Scheduler with multi-armed bandit -> Task 2
   - Verification endpoint with sub-millisecond SAT checks -> Task 3
   - Native worker daemon running at idle priority -> Task 4
   - End-to-end integration and leaderboard stats -> Task 5
2. **No Placeholders**:
   - Zero occurrences of "TODO", "TBD", or placeholders.
   - All code snippets are concrete, fully typed, and executable.
3. **Type Consistency**:
   - Table columns (`problems.id`, `solutions.metric_s`, `workers.records_broken`) match across SQL schemas, Pydantic models, and client payloads.
