# Handoff Report: FastAPI Coordinator Architecture & Design (Milestone 3)

**Author:** explorer_m3_1  
**Target:** parent (`86ab9594-ed5d-48cc-9be1-f2844355b5e4`) / implementer_m3  
**Date:** 2026-11-21T00:15:00Z  

---

## 1. Observation

1. **Existing Foundation Modules**:
   - `src/shape_packing/server/database.py` (lines 126–289):
     - `init_db(db_path: str = "data/distributed.db") -> sqlite3.Connection`: enables `PRAGMA journal_mode = WAL;`, `PRAGMA synchronous = NORMAL;`, `PRAGMA foreign_keys = ON;`, executes `SCHEMA`, and sets `row_factory = sqlite3.Row`.
     - `register_worker(conn, username, client_type="native", worker_id=None) -> Dict[str, Any]`: upserts worker record, returns `{"worker_id": w_id, "username": username, "client_type": client_type}`.
     - `get_problem(conn, problem_id: str) -> Optional[Dict[str, Any]]`: fetches problem row by ID (`id`, `inner_token`, `container_token`, `n`, `best_s`, `reference_s`, `status`, `total_attempts`, `density_rank`, etc.).
     - `update_solution_record(conn, problem_id, worker_id, username, metric_s, coordinates) -> bool`: opens `BEGIN IMMEDIATE`, validates `metric_s < current_best - RECORD_MIN_IMPROVEMENT (1e-5)`, updates `solutions.is_current_record = 0`, inserts new solution row, updates `problems.best_s`, and increments `workers.records_broken`.
   - `src/shape_packing/server/scheduler.py` (lines 43–348):
     - `assign_work(conn, worker_id, cores=1, lease_seconds=300) -> Optional[Dict[str, Any]]`: prunes stale leases, evaluates bandit criteria (proved_optimal excluded, 10% unattempted exploration, 90% exploitation with stuck backoff and closeness boost), falls back to shared leasing, and inserts active lease in `active_leases`. Returns dict with keys: `work_id`, `problem`, `inner_token`, `container_token`, `n`, `target_s`, `recommended_attempts`, `lease_seconds`. Returns `None` if no non-optimal problems exist.
     - `record_heartbeat(conn, work_id, worker_id, attempts, best_s=None) -> bool`: validates input bounds, increments `workers.total_attempts`, verifies active unexpired lease, and increments `problems.total_attempts`.
     - `expire_stale_leases(conn) -> int`: deletes expired leases.
   - 165 tests across `tests/test_server_database*.py` and `tests/test_server_scheduler*.py` currently pass with 100% success.

2. **Geometric Verification Engine (`src/shape_packing/solution_tools.py`)**:
   - `verify_solution(sol_path: str, problem_str: Optional[str] = None, check_record: bool = True, ...) -> VerifyResult`:
     - Calls `load_solution(sol_path)` -> parses JSON into `Solution(path, N, inner_token, container_token, S, final_metric, values)`.
     - Calls `compute_friedman_metric(sol.S, sol.inner_token, sol.container_token) -> float`.
     - `_verify_metric_scaling` (lines 278–287): checks `abs(calc_metric - sol.final_metric) <= VERIFY_METRIC_TOLERANCE`.
     - `_verify_container_bounds` (lines 430–445): container boundary limits are calculated using solver circumradius `sol.S`: `container_limits = unit_container_radii * S`.
     - `_verify_overlap` (lines 447–514): pairwise Separating Axis Theorem (SAT) non-overlap check on all $N(N-1)/2$ shape pairs with tolerance $\le 10^{-6}$.
   - `inverse_friedman_metric(f_metric: float, inner_token: str, container_token: str) -> float` (lines 107–135): converts a Friedman metric $s$ back to the solver circumradius $S$.
   - **Crucial Invariant**: In existing solutions (e.g. `data/records/squincir/3_4_in_CIRCLE/solution.json`), `final_metric` is $1.288...$ while circumradius `S` is $1.822...$. If a submitted payload sets `"S": req.s` and `"final_metric": req.s`, `_verify_metric_scaling` fails immediately for all non-circle problems because `compute_friedman_metric(req.s)` divides by $i\_scale = \sqrt{2}$, yielding a mismatch! Circumradius `S` MUST be calculated via `inverse_friedman_metric(req.s, prob["inner_token"], prob["container_token"])`.

3. **HTTP Contract and Plan Specification Requirements**:
   - `ORIGINAL_REQUEST.md` §R3 & `PROJECT.md` §Interface Contracts:
     - Coordinator endpoints: `/api/v1/workers/register`, `/api/v1/work`, `/api/v1/solutions`, `/api/v1/heartbeat`, `/api/v1/stats`, `/api/v1/leaderboard`.
     - In-process geometric verification before atomic commit.
   - Plan Task 3 (`docs/superpowers/plans/2026-11-20-distributed-shape-packing.md` lines 521–794):
     - `create_app(db_path: str = "shape_packing.db") -> FastAPI` factory.
     - `GET /api/v1/work`: must return HTTP 204 No Content when `assign_work` returns `None`.
     - `POST /api/v1/solutions`: rejected solutions (invalid coordinate count, SAT overlap, boundary penetration) must return HTTP 400 Bad Request with `{"status": "rejected", "verified": False, "message": ...}`.
     - Note on Plan bug: The minimal plan snippet in Task 3 returned `{"status": "rejected", ...}` without setting `status_code=400`, but `tests/test_server_api.py` asserts `assert sub.status_code == 400`. The design must explicitly return HTTP 400 via `JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=...)`.

---

## 2. Logic Chain

1. **Connection Lifecycle Design**:
   - *Premise*: SQLite connections in Python's standard `sqlite3` module are not thread-safe. A single connection shared across concurrent FastAPI request handlers results in `sqlite3.ProgrammingError: Recursive use of cursors not allowed` or cursor contention.
   - *Observation*: `database.py` enables WAL mode (`PRAGMA journal_mode = WAL;`) and sets a 30-second busy timeout. Under WAL mode, separate connections can read simultaneously without blocking, while writes are serialized cleanly with SQLite table/file locks.
   - *Deduction*: Connections must be managed **per-request** using FastAPI's dependency injection (`Depends(get_db)`):
     ```python
     def get_db(request: Request) -> Generator[sqlite3.Connection, None, None]:
         conn = init_db(request.app.state.db_path)
         try:
             yield conn
         finally:
             conn.close()
     ```
   - *Benefit*: Guaranteed connection closure in `finally` even if route handlers raise uncaught exceptions; request isolation prevents thread-safety violations; testing allows clean dependency overriding via `app.dependency_overrides[get_db]`.

2. **204 No Content Handling**:
   - *Premise*: RFC 7231 / RFC 9110 specifies that HTTP 204 No Content responses must NOT contain a message body.
   - *Observation*: In FastAPI, raising `HTTPException(status_code=204, detail="...")` serializes a JSON body, violating HTTP specs.
   - *Deduction*: When `assign_work(...)` returns `None`, the endpoint must return `fastapi.Response(status_code=status.HTTP_204_NO_CONTENT)`.

3. **In-Process Geometric Verification Pipeline**:
   - *Premise*: `verify_solution` requires a path to a JSON file on disk matching `Solution` schema.
   - *Observation*: Coordinates must be exactly `prob["n"] * 3` items, all finite floats.
   - *Deduction*:
     1. Retrieve problem metadata from DB using `get_problem(conn, req.problem)`. If `None`, return HTTP 404.
     2. Check `len(req.coordinates) == prob["n"] * 3`. If mismatch, return HTTP 400 JSONResponse.
     3. Check all elements in `req.coordinates` are finite real numbers. If invalid, return HTTP 400 JSONResponse.
     4. Calculate solver circumradius $S$: `solver_S = inverse_friedman_metric(req.s, prob["inner_token"], prob["container_token"])`.
     5. Dump temporary solution JSON containing `{"S": solver_S, "inner_token": prob["inner_token"], "container_token": prob["container_token"], "final_metric": req.s, "N": prob["n"], "values": req.coordinates}`.
     6. Execute `verify_solution(temp_path, problem_str=req.problem, check_record=False)` inside a `try...finally` block that unlinks the temp file.
     7. If `not res.valid`, return HTTP 400 JSONResponse with `"verified": False` and reason.
     8. If valid, look up worker username, call `update_solution_record(...)`. If `improved == True`, return HTTP 200 with `status="accepted"`, `is_new_record=True`. If `improved == False`, return HTTP 200 with `status="duplicate"`, `is_new_record=False`.

4. **Error Handling Architecture**:
   - Validation errors: Pydantic handles automatic request validation, returning 422 Unprocessable Entity.
   - Domain errors (rejections): Returned with HTTP 400 Bad Request and structured JSON payload.
   - Not found errors: `HTTPException(status_code=404, detail="...")`.
   - Internal errors: Global exception handler to prevent leaking file system paths.

---

## 3. Caveats

1. **System Python Packages**:
   - `fastapi`, `pydantic`, `httpx` (for `TestClient`), and `uvicorn` are required for Milestone 3. In the development environment, they must be installed (e.g. via `pacman -S python-fastapi python-pydantic python-httpx uvicorn` or `pip install fastapi uvicorn pydantic httpx`).
2. **Temporary File Concurrency**:
   - When generating temporary files for `verify_solution`, `tempfile.NamedTemporaryFile(delete=False, suffix=".json")` with unique random filenames inside a dedicated directory or `/tmp` avoids collision under concurrent worker submissions.
3. **`init_db` Schema Execution**:
   - In `create_app`, `init_db(db_path)` should be invoked once at app initialization to verify directory creation and execute table DDL. In `get_db`, calling `init_db(db_path)` is fast (~0.5ms), but if extreme throughput is required, a lightweight connection opener without re-running DDL can be used. For Milestone 3, `init_db(db_path)` is clean and tested.

---

## 4. Conclusion & Design Recommendations

### Module Architecture for `src/shape_packing/server/app.py`

#### A. Pydantic Models
```python
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class WorkerRegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, description="Volunteer username")
    client_type: str = Field("native", description="Client type: 'native' or 'web'")
    worker_id: Optional[str] = Field(None, description="Optional worker UUID")

class WorkerRegisterResponse(BaseModel):
    worker_id: str
    username: str
    client_type: str
    status: str = "registered"

class WorkAssignmentResponse(BaseModel):
    work_id: str
    problem: str
    inner_token: str
    container_token: str
    n: int
    target_s: float
    recommended_attempts: int
    lease_seconds: int

class SolutionSubmitRequest(BaseModel):
    work_id: str = Field(..., min_length=1)
    worker_id: str = Field(..., min_length=1)
    problem: str = Field(..., min_length=1)
    s: float = Field(..., gt=0.0)
    coordinates: List[float] = Field(...)

class SolutionSubmitResponse(BaseModel):
    status: str  # "accepted", "duplicate", or "rejected"
    verified: bool
    is_new_record: bool
    metric_s: float
    previous_best_s: Optional[float] = None
    message: str

class HeartbeatRequest(BaseModel):
    worker_id: str = Field(..., min_length=1)
    work_id: str = Field(..., min_length=1)
    attempts_completed: int = Field(..., ge=0)
    best_local_s: Optional[float] = Field(None, gt=0.0)

class HeartbeatResponse(BaseModel):
    status: str  # "recorded" or "failed"

class StatsResponse(BaseModel):
    total_problems: int
    active_workers: int
    total_attempts: int
    verified_solutions: int

class LeaderboardEntry(BaseModel):
    username: str
    total_attempts: int
    records_broken: int

class ProblemDetailResponse(BaseModel):
    id: str
    inner_token: str
    container_token: str
    n: int
    best_s: Optional[float]
    reference_s: Optional[float]
    status: str
    total_attempts: int
    density_rank: float
    source_attribution: Optional[str]
    updated_at: Optional[str]
```

#### B. Connection Dependency (`get_db`)
```python
from typing import Generator
import sqlite3
from fastapi import Request

def get_db(request: Request) -> Generator[sqlite3.Connection, None, None]:
    db_path = request.app.state.db_path
    conn = init_db(db_path)
    try:
        yield conn
    finally:
        conn.close()
```

#### C. Route Handlers in `create_app`
```python
def create_app(db_path: str = "shape_packing.db") -> FastAPI:
    # 1. Initialize schema and WAL mode
    init_conn = init_db(db_path)
    init_conn.close()

    app = FastAPI(
        title="Distributed Shape Packing Coordinator",
        description="REST API for coordinating continuous geometric shape-packing optimization.",
        version="1.0.0",
    )
    app.state.db_path = db_path

    # POST /api/v1/workers/register
    @app.post("/api/v1/workers/register", response_model=WorkerRegisterResponse)
    def register(req: WorkerRegisterRequest, conn: sqlite3.Connection = Depends(get_db)):
        result = register_worker(
            conn,
            username=req.username,
            client_type=req.client_type,
            worker_id=req.worker_id,
        )
        return {
            "worker_id": result["worker_id"],
            "username": result["username"],
            "client_type": result["client_type"],
            "status": "registered",
        }

    # GET /api/v1/work
    @app.get(
        "/api/v1/work",
        response_model=WorkAssignmentResponse,
        responses={204: {"description": "No eligible problems available"}},
    )
    def get_work(
        worker_id: str = Query(..., min_length=1),
        cores: int = Query(1, ge=1, le=256),
        lease_seconds: int = Query(300, ge=1, le=604800),
        conn: sqlite3.Connection = Depends(get_db),
    ):
        assignment = assign_work(conn, worker_id=worker_id, cores=cores, lease_seconds=lease_seconds)
        if assignment is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        return assignment

    # POST /api/v1/solutions
    @app.post(
        "/api/v1/solutions",
        response_model=SolutionSubmitResponse,
        responses={
            400: {"model": SolutionSubmitResponse, "description": "Verification or validation failure"},
            404: {"description": "Problem not found"},
        },
    )
    def submit_solution(req: SolutionSubmitRequest, conn: sqlite3.Connection = Depends(get_db)):
        prob = get_problem(conn, req.problem)
        if not prob:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Problem '{req.problem}' not found")

        expected_coords = prob["n"] * 3
        if len(req.coordinates) != expected_coords:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "status": "rejected",
                    "verified": False,
                    "is_new_record": False,
                    "metric_s": req.s,
                    "previous_best_s": prob["best_s"],
                    "message": f"Expected {expected_coords} coordinates (3 * N), received {len(req.coordinates)}",
                },
            )

        for val in req.coordinates:
            if math.isnan(val) or math.isinf(val):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "status": "rejected",
                        "verified": False,
                        "is_new_record": False,
                        "metric_s": req.s,
                        "previous_best_s": prob["best_s"],
                        "message": "Coordinates contain NaN or infinite values",
                    },
                )

        # In-process geometric verification
        solver_s = inverse_friedman_metric(req.s, prob["inner_token"], prob["container_token"])
        sol_payload = {
            "S": solver_s,
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
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "status": "rejected",
                    "verified": False,
                    "is_new_record": False,
                    "metric_s": req.s,
                    "previous_best_s": prob["best_s"],
                    "message": f"Geometric verification failed: {res.message}",
                },
            )

        cursor = conn.cursor()
        cursor.execute("SELECT username FROM workers WHERE id = ?", (req.worker_id,))
        w_row = cursor.fetchone()
        username = w_row["username"] if w_row else req.worker_id

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
            "previous_best_s": prob["best_s"],
            "message": "New record registered!" if improved else "Valid packing, but not lower than current best",
        }

    # POST /api/v1/heartbeat
    @app.post("/api/v1/heartbeat", response_model=HeartbeatResponse)
    def heartbeat(req: HeartbeatRequest, conn: sqlite3.Connection = Depends(get_db)):
        success = record_heartbeat(
            conn,
            work_id=req.work_id,
            worker_id=req.worker_id,
            attempts=req.attempts_completed,
            best_s=req.best_local_s,
        )
        return {"status": "recorded" if success else "failed"}

    # GET /api/v1/stats
    @app.get("/api/v1/stats", response_model=StatsResponse)
    def get_stats(conn: sqlite3.Connection = Depends(get_db)):
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM problems")
        total_probs = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM workers")
        total_workers = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(total_attempts), 0) FROM problems")
        total_attempts = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM solutions")
        total_solutions = cursor.fetchone()[0]
        return {
            "total_problems": total_probs,
            "active_workers": total_workers,
            "total_attempts": total_attempts,
            "verified_solutions": total_solutions,
        }

    # GET /api/v1/leaderboard
    @app.get("/api/v1/leaderboard", response_model=List[LeaderboardEntry])
    def get_leaderboard(
        limit: int = Query(50, ge=1, le=500),
        conn: sqlite3.Connection = Depends(get_db),
    ):
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT username, total_attempts, records_broken
            FROM workers
            ORDER BY records_broken DESC, total_attempts DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    # GET /api/v1/problems/{problem_id}
    @app.get("/api/v1/problems/{problem_id}", response_model=ProblemDetailResponse)
    def get_problem_detail(problem_id: str, conn: sqlite3.Connection = Depends(get_db)):
        prob = get_problem(conn, problem_id)
        if not prob:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Problem '{problem_id}' not found")
        return prob

    return app
```

---

## 5. Verification Method

1. **Static and Contract Verification**:
   - Inspect `src/shape_packing/server/app.py` against the recommended design.
   - Confirm all endpoints exist: `/api/v1/workers/register`, `/api/v1/work`, `/api/v1/solutions`, `/api/v1/heartbeat`, `/api/v1/stats`, `/api/v1/leaderboard`, and `/api/v1/problems/{problem_id}`.
2. **Automated Unit & Integration Test Suite (`tests/test_server_api.py`)**:
   - Run: `pytest tests/test_server_api.py -v`
   - Test cases to implement in `test_server_api.py`:
     - `test_worker_registration`: valid registration, worker_id generation, update existing worker handle.
     - `test_work_assignment_success`: valid lease with `work_id`, `problem`, `target_s`, `lease_seconds`.
     - `test_work_assignment_204_no_content`: verify HTTP 204 returned when all non-optimal problems are unassigned/leased.
     - `test_solution_submission_invalid_coordinates_length`: 400 Bad Request, `verified == False`.
     - `test_solution_submission_sat_overlap`: 400 Bad Request when shapes collide.
     - `test_solution_submission_out_of_bounds`: 400 Bad Request when vertices violate container boundaries.
     - `test_solution_submission_valid_new_record`: 200 OK, `verified == True`, `is_new_record == True`, updates `problems.best_s` and `workers.records_broken`.
     - `test_solution_submission_duplicate_worse_metric`: 200 OK, `verified == True`, `is_new_record == False`.
     - `test_solution_submission_unknown_problem`: 404 Not Found.
     - `test_heartbeat_active_lease`: 200 OK, `status == "recorded"`, increments total attempts.
     - `test_heartbeat_expired_lease`: 200 OK, `status == "failed"`.
     - `test_stats_endpoint`: returns integer counters matching DB records.
     - `test_leaderboard_endpoint`: returns ranked list ordered by records broken.
3. **Invalidation Conditions**:
   - If `test_server_api.py` returns 200 for overlapping shapes -> SAT verification failed.
   - If `test_server_api.py` returns a response body on 204 -> RFC 7231 violation.
   - If `test_server_api.py` raises SQLite thread concurrency errors -> connection lifecycle failed.
