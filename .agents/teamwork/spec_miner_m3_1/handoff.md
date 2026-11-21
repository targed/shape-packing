# Milestone 3 Specification Mining Report: Coordinator REST API & In-Process Verifier

## 1. Observation

Authoritative project sources were inspected directly:
- **`ORIGINAL_REQUEST.md`** (§R3, lines 21–23):
  > "Build FastAPI coordinator endpoints in `src/shape_packing/server/app.py` (`/api/v1/workers/register`, `/api/v1/work`, `/api/v1/solutions`, `/api/v1/heartbeat`, `/api/v1/leaderboard`, `/api/v1/stats`). Every submitted solution must be strictly verified in-process using `src/shape_packing/solution_tools.py:verify_solution` (pairwise Separating Axis Theorem non-overlap and container confinement checks) before atomically committing a new record."
- **`ORIGINAL_REQUEST.md`** (Acceptance Criteria lines 38–40):
  > "- `/api/v1/solutions` validates coordinate vector length (3*N), runs pairwise SAT collision checks, and verifies container boundary containment.\n- Submissions with overlapping polygons or boundary penetrations are rejected with a 400 error.\n- Verified improvements atomically update the best record and increment the finder's leaderboard score."
- **`docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md`** (§4 REST API Contract, lines 119–212):
  Specifies the REST contract for:
  - `POST /api/v1/workers/register`
  - `GET /api/v1/work?worker_id={worker_id}&cores={cores}`
  - `POST /api/v1/solutions`
  - `POST /api/v1/heartbeat`
  - `GET /api/v1/leaderboard`
  - `GET /api/v1/stats`
  - `GET /api/v1/problems/{id}` (Discovered endpoint)
- **`docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md`** (§6 Geometric Verification Pipeline, lines 232–242):
  1. Dimension Check: `len(coordinates) == 3 * N`.
  2. Containment Check: Reconstructs each polygon and validates that all vertices lie inside container boundary with tolerance $\le 10^{-6}$.
  3. Pairwise SAT Collision Check: Evaluates SAT between all $N(N-1)/2$ polygon pairs with penetration $\le 10^{-6}$.
  4. Metric Verification: Recalculates $s$ directly from coordinates and verifies $s_{\text{submitted}} < s_{\text{best}} - 10^{-5}$.
  5. Atomic Commit: `BEGIN IMMEDIATE` transaction, demotes previous records (`is_current_record = 0`), inserts new solution, updates `problems.best_s`, and increments worker's `records_broken`.
- **`docs/superpowers/plans/2026-11-20-distributed-shape-packing.md`** (Task 3 lines 521–806):
  Specifies module `src/shape_packing/server/app.py`, factory `create_app(db_path: str = "data/distributed.db") -> FastAPI`, Pydantic models (`WorkerRegisterRequest`, `SolutionSubmitRequest`, `HeartbeatRequest`), and the initial test structure in `tests/test_server_api.py`.
- **Existing Components**:
  - `src/shape_packing/server/database.py`: Implements `init_db`, `register_worker`, `get_problem`, `update_solution_record` (`BEGIN IMMEDIATE`, atomic commit, `RECORD_MIN_IMPROVEMENT = 1e-5`), `seed_problems_from_verification`.
  - `src/shape_packing/server/scheduler.py`: Implements `assign_work`, `record_heartbeat`, `expire_stale_leases`.
  - `src/shape_packing/solution_tools.py`: Implements `verify_solution`, `compute_friedman_metric`, `build_polygons`, `_verify_container_bounds`, `_verify_overlap`, returning `VerifyResult(valid: bool, metric: float, errors: List[str], new_record: bool, message: str)`.
  - Test suites `tests/test_server_database*.py` and `tests/test_server_scheduler*.py` currently pass 165/165 tests in 10.16s.

---

## 2. Logic Chain

1. **Endpoint Topology**:
   - The original request (§R3) requires 6 core coordinator endpoints (`/api/v1/workers/register`, `/api/v1/work`, `/api/v1/solutions`, `/api/v1/heartbeat`, `/api/v1/leaderboard`, `/api/v1/stats`).
   - The design spec (§4.5) also defines `GET /api/v1/problems/{id}` to view individual problem configurations and records. Per specification miner rules, this discovered endpoint is fully specified.

2. **Status Code and Error Response Semantics**:
   - FastAPIs default Pydantic model validation on malformed request bodies or missing required fields returns `422 Unprocessable Entity` with `{"detail": [...]}`.
   - Missing query parameters on GET endpoints (e.g. missing `worker_id` on `/api/v1/work`) returns `422 Unprocessable Entity`.
   - Empty work queues when all available problems are optimal or none exist return `204 No Content` with an empty response body (per design doc §4.2).
   - Solution rejection (`POST /api/v1/solutions`) due to geometric errors (penetration, container violation, coordinate count mismatch) must return `400 Bad Request` with payload `{"status": "rejected", "verified": false, "message": str}` (per acceptance criteria line 39 and design doc §4.3). To achieve this in FastAPI while preserving the JSON body format expected by clients, the endpoint should return `JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"status": "rejected", "verified": False, "message": msg})`.
   - Missing resources (e.g. submitting a solution for an unknown problem ID, or querying `/api/v1/problems/{id}` for a nonexistent ID) return `404 Not Found` with `{"detail": "Problem not found"}`.
   - Non-geometric bad parameters (such as empty whitespace `username=""`, negative attempt counts, or NaN/Inf coordinates) return `400 Bad Request` with `{"detail": str}` or `{"status": "rejected", ...}`.

3. **In-Process Geometric Verification Flow**:
   - Step 1: Look up problem in database via `get_problem(conn, req.problem)`. If `None`, return 404/400.
   - Step 2: Validate coordinate vector size: `expected = 3 * prob["n"]`. If `len(req.coordinates) != expected`, immediately reject with 400 Bad Request: `{"status": "rejected", "verified": False, "message": f"Expected {expected} coordinates, received {len(req.coordinates)}"}`.
   - Step 3: Compute Friedman metric: `calc_metric = compute_friedman_metric(req.s, prob["inner_token"], prob["container_token"])`. Assemble solution JSON payload with `{"N": prob["n"], "inner_token": prob["inner_token"], "container_token": prob["container_token"], "S": req.s, "final_metric": calc_metric, "values": req.coordinates}`.
   - Step 4: Write to a secure temporary file (`tempfile.NamedTemporaryFile`) and invoke `verify_solution(temp_path, problem_str=req.problem, check_record=False)`. Always clean up temporary file in a `finally:` block.
   - Step 5: If `not res.valid`, return 400 Bad Request with `{"status": "rejected", "verified": False, "message": f"Geometric verification failed: {res.message}"}`.
   - Step 6: If `res.valid`, attempt atomic database update via `update_solution_record(conn, problem_id=req.problem, worker_id=req.worker_id, username=username, metric_s=res.metric, coordinates=req.coordinates)`.
     - If `improved == True`: Return `200 OK` with `{"status": "accepted", "verified": True, "is_new_record": True, "metric_s": res.metric, "previous_best_s": prob["best_s"], "message": "New world record registered! Rank updated."}`.
     - If `improved == False`: Return `200 OK` with `{"status": "duplicate", "verified": True, "is_new_record": False, "metric_s": res.metric, "message": "Valid configuration, but not lower than current best"}`.

4. **Concurrency and State Isolation**:
   - Concurrency is managed at the SQLite WAL level using `BEGIN IMMEDIATE` in `update_solution_record`, `assign_work`, and `record_heartbeat`. FastAPI handlers must obtain independent SQLite connections per request (or via dependency injection) and close them in `finally:`.

---

## 3. Comprehensive REST API Interface Specifications

### Endpoint 1: Register Worker
- **Route**: `POST /api/v1/workers/register`
- **Request Body (JSON)**:
  ```json
  {
    "username": "targed",
    "client_type": "native",
    "worker_id": "a1b2c3d4-e5f6-7890"
  }
  ```
  - `username` (string, required): Contributor handle. Must be non-empty.
  - `client_type` (string, optional, default `"native"`): Client type (`"native"` or `"web"`).
  - `worker_id` (string, optional, nullable, default `null`): Client-provided UUID. If omitted or null, coordinator generates a UUID4 string.
- **Success Response (`200 OK`)**:
  ```json
  {
    "worker_id": "a1b2c3d4-e5f6-7890",
    "username": "targed",
    "client_type": "native",
    "status": "registered"
  }
  ```
- **Error Responses**:
  - `400 Bad Request`: `username` is empty or whitespace-only (`{"detail": "Username cannot be empty"}`).
  - `422 Unprocessable Entity`: Body is malformed or missing `username` (`{"detail": [...]}`).

### Endpoint 2: Request Work Assignment
- **Route**: `GET /api/v1/work`
- **Query Parameters**:
  - `worker_id` (string, required): Identifier of requesting worker node.
  - `cores` (integer, optional, default `1`, ge=1): CPU cores available on worker.
  - `lease_seconds` (integer, optional, default `300`, ge=1, le=604800): Lease duration.
- **Success Response (`200 OK`)**:
  ```json
  {
    "work_id": "wu_a1b2c3d4e5f6",
    "problem": "14_TAN_in_circle",
    "inner_token": "TAN",
    "container_token": "CIRCLE",
    "n": 14,
    "target_s": 2.8451203,
    "recommended_attempts": 4000,
    "lease_seconds": 300
  }
  ```
  *(Note: `timeout_seconds` should be mirrored or aliased to `lease_seconds` for client compatibility).*
- **Error Responses**:
  - `204 No Content`: Returned when work queue is exhausted or all non-optimal problems are completed. Body is empty.
  - `400 Bad Request`: `worker_id` is empty or whitespace (`{"detail": "worker_id cannot be empty"}`).
  - `422 Unprocessable Entity`: Missing `worker_id` query param or non-integer `cores` (`{"detail": [...]}`).

### Endpoint 3: Submit Solution
- **Route**: `POST /api/v1/solutions`
- **Request Body (JSON)**:
  ```json
  {
    "work_id": "wu_a1b2c3d4e5f6",
    "worker_id": "a1b2c3d4-e5f6-7890",
    "problem": "14_TAN_in_circle",
    "s": 2.8449112,
    "coordinates": [0.12, -0.45, 1.57, 0.33, 0.21, 0.0]
  }
  ```
  - `work_id` (string, required): Active lease ID.
  - `worker_id` (string, required): Worker ID.
  - `problem` (string, required): Canonical problem ID.
  - `s` (number, required): Candidate container scale parameter ($S > 0$).
  - `coordinates` (array of numbers, required): Flat vector of $3 \times N$ values $[x_1, y_1, \theta_1, \dots, x_N, y_N, \theta_N]$.
- **Success Response (Verified New Record) (`200 OK`)**:
  ```json
  {
    "status": "accepted",
    "verified": true,
    "is_new_record": true,
    "metric_s": 2.8449112,
    "previous_best_s": 2.8451203,
    "message": "New world record registered! Rank updated."
  }
  ```
- **Success Response (Verified Duplicate / Non-Improving) (`200 OK`)**:
  ```json
  {
    "status": "duplicate",
    "verified": true,
    "is_new_record": false,
    "metric_s": 2.8451203,
    "message": "Valid configuration, but not lower than current best"
  }
  ```
- **Error Responses**:
  - `400 Bad Request`:
    - Overlapping polygons / SAT failure: `{"status": "rejected", "verified": false, "message": "SAT overlap detected between shape 2 and shape 7 (penetration = 0.0021)."}`
    - Container boundary penetration: `{"status": "rejected", "verified": false, "message": "Shape 0 is out of bounds! Violation margin: 0.15"}`
    - Non-convex reflex cutout violation: `{"status": "rejected", "verified": false, "message": "Shape 0 intersects L-container reflex cut-out!"}`
    - Coordinate length mismatch: `{"status": "rejected", "verified": false, "message": "Expected 42 coordinates, received 6"}`
    - Non-numeric / NaN / Inf coordinate values: `{"status": "rejected", "verified": false, "message": "Coordinates must contain finite numeric values"}`
    - Problem not found: `{"detail": "Problem not found"}` (or `404 Not Found`)
  - `422 Unprocessable Entity`: Body missing required fields or invalid schema types (`{"detail": [...]}`).

### Endpoint 4: Heartbeat & Attempt Logging
- **Route**: `POST /api/v1/heartbeat`
- **Request Body (JSON)**:
  ```json
  {
    "worker_id": "a1b2c3d4-e5f6-7890",
    "work_id": "wu_a1b2c3d4e5f6",
    "attempts_completed": 4000,
    "best_local_s": 2.849102
  }
  ```
  - `worker_id` (string, required): Worker ID.
  - `work_id` (string, required): Work lease ID.
  - `attempts_completed` (integer, required, ge=0): Attempts executed.
  - `best_local_s` (number, optional, nullable, default `null`): Local telemetry.
- **Success Response (`200 OK`)**:
  ```json
  {
    "status": "recorded",
    "total_worker_attempts": 124000
  }
  ```
- **Error Responses**:
  - `400 Bad Request`: `attempts_completed < 0` or blank IDs (`{"detail": "Invalid attempts or identifiers"}`).
  - `422 Unprocessable Entity`: Missing fields or non-integer attempts (`{"detail": [...]}`).

### Endpoint 5: Leaderboard
- **Route**: `GET /api/v1/leaderboard`
- **Query Parameters**:
  - `limit` (integer, optional, default `50`, ge=1, le=500): Maximum rows to return.
- **Success Response (`200 OK`)**:
  ```json
  [
    {
      "username": "targed",
      "total_attempts": 124000,
      "records_broken": 5
    }
  ]
  ```
  *(Sorted by `records_broken DESC, total_attempts DESC LIMIT :limit`)*
- **Error Responses**:
  - `422 Unprocessable Entity`: Invalid limit parameter (`limit <= 0`).

### Endpoint 6: Global Network Statistics
- **Route**: `GET /api/v1/stats`
- **Success Response (`200 OK`)**:
  ```json
  {
    "total_problems": 2242,
    "active_workers": 18,
    "total_attempts": 45120300,
    "verified_solutions": 890
  }
  ```
- **Error Responses**:
  - None under normal operation.

### Discovered Endpoint: Problem Details & Solution Coordinates
- **Route**: `GET /api/v1/problems/{id}`
- **Path Parameters**: `id` (string, required): Canonical problem ID (e.g. `"14_TAN_in_circle"`).
- **Success Response (`200 OK`)**:
  ```json
  {
    "id": "14_TAN_in_circle",
    "inner_token": "TAN",
    "container_token": "CIRCLE",
    "n": 14,
    "best_s": 2.8449112,
    "reference_s": 2.8451203,
    "status": "best_known",
    "total_attempts": 124000,
    "coordinates": [0.12, -0.45, 1.57, 0.33, 0.21, 0.0]
  }
  ```
- **Error Responses**:
  - `404 Not Found`: Problem ID not in catalog (`{"detail": "Problem not found"}`).

---

## 4. Features Discovered Table

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Worker Auth & Registration | Worker Registration | Registers worker node, issues/records worker_id, sets client type, records last seen | `username` (str), `client_type` (str="native"), `worker_id` (str=None) | `{"worker_id": str, "username": str, "client_type": str, "status": "registered"}` | Empty username -> 400 Bad Request; Missing field -> 422 Unprocessable Entity | Spec §4.1, Plan Task 3, ORIGINAL_REQUEST §R3 |
| 2 | Worker Auth & Registration | Worker Idempotent Update | Re-registration with existing worker_id updates username and last_seen_at without duplicate key error | `worker_id` (existing str), `username` (new str) | `200 OK` with updated profile | Invalid types -> 422 | `database.py:register_worker`, Plan Task 1 |
| 3 | Work Scheduler API | Work Unit Leasing | Leases problem using multi-armed bandit, balancing density rank, closeness boost, and 10% exploration | `worker_id` (str), `cores` (int=1), `lease_seconds` (int=300) | `{"work_id": str, "problem": str, "inner_token": str, "container_token": str, "n": int, "target_s": float, "recommended_attempts": int, "lease_seconds": int}` | No work available -> 204 No Content; missing worker_id -> 422; blank worker_id -> 400 | Spec §4.2, Plan Task 2 & 3, `scheduler.py` |
| 4 | Work Scheduler API | Automatic Stale Lease Expiry | Purges expired leases prior to assigning work, reclaiming abandoned problems | None (triggered on `assign_work`) | Expired leases pruned from `active_leases` table | None (silent recovery) | Spec §5, `scheduler.py:expire_stale_leases` |
| 5 | Work Scheduler API | Cores Scaling | Computes `recommended_attempts = max(1000, min(cores * 1000, 20000))` | `cores` (int) | Scaled attempt recommendation | Negative/corrupt cores normalized to 1000 | `scheduler.py:assign_work`, Spec §4.2 |
| 6 | Work Scheduler API | Proved-Optimal Exclusion | Strictly skips problems where `status == 'proved_optimal'` during work allocation | Catalog with proved_optimal problems | Leased problem is guaranteed non-proved_optimal | If only proved_optimal exist -> 204 No Content | ORIGINAL_REQUEST §R2, Spec §5.1 |
| 7 | Solution Verification API | In-Process SAT Collision Verification | Reconstructs polygons and validates Separating Axis Theorem non-overlap between all $N(N-1)/2$ pairs | `work_id`, `worker_id`, `problem`, `s`, `coordinates` (len 3*N) | `res.valid == True` or error message detailing overlapping pair & depth | Penetration > 1e-6 -> 400 Bad Request `{"status": "rejected", "verified": false, "message": "..."}` | ORIGINAL_REQUEST §R3, Spec §6, `solution_tools.py` |
| 8 | Solution Verification API | Container Boundary Verification | Tests that all polygon vertices lie within container apothem/boundary with tolerance $\le 10^{-6}$ | `coordinates`, container geometry | Boundary pass/fail | Out-of-bounds vertex -> 400 Bad Request `{"status": "rejected", "verified": false, "message": "..."}` | Spec §6.2, `solution_tools.py:_verify_container_bounds` |
| 9 | Solution Verification API | Non-Convex Reflex Cutout Check | For non-convex containers (e.g. L-tromino "L"), verifies shapes do not penetrate reflex corner obstacle | L-container coordinates | Reflex cutout pass/fail | Intersection -> 400 Bad Request `{"status": "rejected", "verified": false, "message": "..."}` | `solution_tools.py:_verify_l_container_bounds` |
| 10 | Solution Verification API | Coordinate Vector Dimension Check | Checks that coordinates array length exactly equals $3 \times N$ | `coordinates` (list), problem $N$ | Passes to verifier if match | Length mismatch -> 400 Bad Request `{"status": "rejected", "verified": false, "message": "Expected ... coordinates, received ..."}` | ORIGINAL_REQUEST §R3, Spec §6.1 |
| 11 | Solution Verification API | Record Improvement Determination | Compares verified metric $s$ to existing best: $s < s_{\text{best}} - 10^{-5}$ | `s`, `coordinates` | `is_new_record: True` | If valid but $s \ge s_{\text{best}} - 10^{-5}$ -> 200 OK `status: "duplicate"`, `is_new_record: False` | `database.py:update_solution_record`, Spec §6.4 |
| 12 | Solution Verification API | Atomic Record Commit | Atomically updates `problems.best_s`, marks old records `is_current_record = 0`, inserts new solution, increments `workers.records_broken` | Verified improvement | Record stored atomically in SQLite WAL via `BEGIN IMMEDIATE` | Race conditions serialized; concurrent inferior submission rolled back | ORIGINAL_REQUEST §R3, Spec §6.5, `database.py` |
| 13 | Telemetry & Heartbeat API | Heartbeat Logging | Records search attempt counts and refreshes worker liveness timestamp | `worker_id`, `work_id`, `attempts_completed`, `best_local_s` | `{"status": "recorded", "total_worker_attempts": int}` | Negative attempts -> 400 Bad Request; missing fields -> 422 | Spec §4.4, Plan Task 2 & 3, `scheduler.py` |
| 14 | Telemetry & Heartbeat API | Expired Lease Compute Crediting | If worker submits heartbeat on an expired lease, worker attempts are credited, but problem attempts are not | Expired `work_id` | `200 OK` status recorded | None | `scheduler.py:record_heartbeat` |
| 15 | Telemetry & Heartbeat API | Telemetry Best S Isolation | Ensures candidate `best_local_s` in heartbeat is recorded for telemetry only and never mutates `problems.best_s` | `best_local_s` float | `200 OK` | Invalid float -> 400 Bad Request | `scheduler.py:record_heartbeat` |
| 16 | Analytics & Dashboard API | Contributor Leaderboard | Ranks contributors by `records_broken DESC, total_attempts DESC` | `limit` (int=50) | List of `{"username": str, "total_attempts": int, "records_broken": int}` | `limit <= 0` -> 422 Unprocessable Entity | Spec §4.5, Plan Task 3, `database.py` |
| 17 | Analytics & Dashboard API | Global Summary Statistics | Aggregates `total_problems`, `active_workers`, `total_attempts`, and `verified_solutions` | None | `{"total_problems": int, "active_workers": int, "total_attempts": int, "verified_solutions": int}` | None | Spec §4.5, Plan Task 3 |
| 18 | Problem Catalog API (Discovered) | Problem Detail & Coordinates | Retrieves problem metadata, status, reference metric, best metric, and active solution coordinates | `id` (str path param) | `{"id": str, "inner_token": str, "container_token": str, "n": int, "best_s": float, "reference_s": float, "status": str, "coordinates": list}` | Problem ID not found -> 404 Not Found | Spec §4.5 line 210 |

---

## 5. Edge Cases Table

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | `/api/v1/work` | Work requested when catalog only contains `proved_optimal` problems | Returns `204 No Content` with empty body; worker does not crash |
| 2 | `/api/v1/work` | `cores=0` or `cores=-5` | Normalized to `recommended_attempts = 1000` |
| 3 | `/api/v1/work` | `cores=128` | Capped at `recommended_attempts = 20000` |
| 4 | `/api/v1/work` | `worker_id="   "` (whitespace) | Returns `400 Bad Request` (`{"detail": "worker_id cannot be empty"}`) |
| 5 | `/api/v1/solutions` | Coordinates array has $M \ne 3N$ numbers (e.g. 5 instead of 6 for $N=2$) | Returns `400 Bad Request` with `{"status": "rejected", "verified": false, "message": "Expected 6 coordinates, received 5"}` |
| 6 | `/api/v1/solutions` | Two shapes positioned at identical coordinates $[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]$ | Returns `400 Bad Request` with `{"status": "rejected", "verified": false, "message": "SAT overlap detected between shape 0 and shape 1..."}` |
| 7 | `/api/v1/solutions` | Single shape vertex placed outside container radius ($x=100.0, y=100.0$) | Returns `400 Bad Request` with `{"status": "rejected", "verified": false, "message": "Shape 0 is out of bounds..."}` |
| 8 | `/api/v1/solutions` | Shape placed inside the reflex cutout of an L-tromino container | Returns `400 Bad Request` with `{"status": "rejected", "verified": false, "message": "Shape 0 intersects L-container reflex cut-out!"}` |
| 9 | `/api/v1/solutions` | Coordinates containing `NaN` or `Infinity` | Rejected with `400 Bad Request` or `422 Unprocessable Entity` |
| 10 | `/api/v1/solutions` | Metric $s$ matches valid configuration, but $s \ge s_{\text{best}} - 10^{-5}$ | Returns `200 OK` with `status="duplicate"`, `verified=true`, `is_new_record=false`. Database record is untouched |
| 11 | `/api/v1/solutions` | Two workers submit improvements simultaneously for the same problem | SQLite `BEGIN IMMEDIATE` serializes execution; first commit wins, second commit is evaluated against the new best; no database locking errors or data loss |
| 12 | `/api/v1/solutions` | Solution submitted for nonexistent `problem="99_UNKNOWN"` | Returns `404 Not Found` (or `400 Bad Request`) with `{"detail": "Problem not found"}` |
| 13 | `/api/v1/heartbeat` | `attempts_completed = -100` | Returns `400 Bad Request` or `422 Unprocessable Entity` |
| 14 | `/api/v1/heartbeat` | Heartbeat sent for expired lease | Returns `200 OK` with `status="recorded"`. Increments `workers.total_attempts`, does NOT increment `problems.total_attempts` |
| 15 | `/api/v1/leaderboard` | Empty database (no workers registered yet) | Returns `200 OK` with empty list `[]` |
| 16 | `/api/v1/leaderboard` | `limit=0` or `limit=-10` | Returns `422 Unprocessable Entity` validation error |
| 17 | `/api/v1/workers/register`| Empty string `username=""` or whitespace `username="   "` | Returns `400 Bad Request` (`{"detail": "Username cannot be empty"}`) |

---

## 6. Complete Test Suite Enumeration for `tests/test_server_api.py`

A total of 36 distinct test cases are specified across 7 logical groups:

### Group 1: Worker Registration (`/api/v1/workers/register`)
1. `test_register_worker_default_native`: Register with `{"username": "alice"}`. Assert status 200, valid UUID `worker_id`, `client_type="native"`, `status="registered"`.
2. `test_register_worker_custom_id_and_web_client`: Register with `{"username": "bob", "client_type": "web", "worker_id": "custom-uuid"}`. Assert status 200, echoes provided `worker_id` and `client_type`.
3. `test_register_worker_idempotent_re_registration`: Re-register same `worker_id` with new username. Assert status 200, updates worker record in DB.
4. `test_register_worker_missing_username_returns_422`: POST body `{}` without `username`. Assert 422 Unprocessable Entity.
5. `test_register_worker_empty_or_whitespace_username_returns_400`: POST `{"username": "   "}`. Assert 400 Bad Request.
6. `test_register_worker_malformed_json_returns_422`: POST invalid JSON payload. Assert 422.

### Group 2: Work Assignment Requests (`/api/v1/work`)
7. `test_get_work_success_single_core`: Request with `worker_id="w1"`, `cores=1`. Assert status 200, response contains all 8 required fields, `recommended_attempts == 1000`.
8. `test_get_work_cores_scaling`: Request with `cores=8`. Assert `recommended_attempts == 8000`. Request with `cores=64`. Assert capped at 20000.
9. `test_get_work_skips_proved_optimal`: Database with 1 `proved_optimal` and 1 `best_known`. Assert assigned problem is `best_known`.
10. `test_get_work_empty_queue_returns_204`: Database with only `proved_optimal` problems. Assert status 204 No Content, body empty.
11. `test_get_work_auto_recovers_expired_lease`: Lease problem with short duration, expire lease. Subsequent request re-leases the problem.
12. `test_get_work_missing_worker_id_returns_422`: GET `/api/v1/work` without `worker_id`. Assert 422 Unprocessable Entity.
13. `test_get_work_empty_worker_id_returns_400`: GET `/api/v1/work?worker_id=`. Assert 400 Bad Request.

### Group 3: Solution Submission (`/api/v1/solutions`)
14. `test_submit_valid_improving_solution_accepted`: Submit valid non-overlapping packing for `3_3_in_circle` with metric $s=3.0 < 3.5$. Assert 200 OK, `status="accepted"`, `verified=true`, `is_new_record=true`. Verify DB updated: `problems.best_s == 3.0`, `workers.records_broken == 1`.
15. `test_submit_valid_duplicate_solution`: Submit valid packing with $s=3.2 \ge 3.0$. Assert 200 OK, `status="duplicate"`, `verified=true`, `is_new_record=false`. Verify DB unchanged.
16. `test_submit_solution_coordinate_length_mismatch_returns_400`: Submit 3 coordinates for $N=3$ (expects 9). Assert 400 Bad Request, `verified=false`, message describes expected count.
17. `test_submit_solution_pairwise_sat_overlap_returns_400`: Submit coordinates where two shapes overlap at $[0, 0, 0]$. Assert 400 Bad Request, `verified=false`, message contains "SAT overlap detected".
18. `test_submit_solution_container_boundary_penetration_returns_400`: Submit shape at $x=100.0, y=100.0$. Assert 400 Bad Request, `verified=false`, message contains boundary violation.
19. `test_submit_solution_non_convex_reflex_cutout_violation_returns_400`: For L-tromino container, place shape in reflex cutout. Assert 400 Bad Request, `verified=false`, reflex cutout error.
20. `test_submit_solution_unknown_problem_returns_404_or_400`: Submit for nonexistent problem ID. Assert 404 or 400.
21. `test_submit_solution_nan_inf_coordinates_returns_400_or_422`: Submit coordinates with `float("nan")` or `float("inf")`. Assert 400 or 422.
22. `test_submit_solution_missing_fields_returns_422`: Submit payload missing `coordinates` or `work_id`. Assert 422.
23. `test_submit_solution_atomic_concurrency_race`: Spawn concurrent threads submitting solutions for same problem. Assert no lock error and only superior metric commits.

### Group 4: Heartbeat Telemetry (`/api/v1/heartbeat`)
24. `test_heartbeat_active_lease_increments_both_counters`: Send heartbeat for active lease with 5000 attempts. Assert 200 OK, `status="recorded"`. Verify both problem and worker attempts increment by 5000.
25. `test_heartbeat_expired_lease_credits_worker_only`: Send heartbeat for expired lease. Assert 200 OK, worker attempts increment, problem attempts unchanged.
26. `test_heartbeat_telemetry_does_not_mutate_best_s`: Send `best_local_s=2.5`. Assert 200 OK, `problems.best_s` in DB unaffected.
27. `test_heartbeat_negative_attempts_returns_400_or_422`: Send `attempts_completed=-10`. Assert 400 or 422.
28. `test_heartbeat_missing_required_fields_returns_422`: Send body missing `worker_id` or `work_id`. Assert 422.

### Group 5: Contributor Leaderboard (`/api/v1/leaderboard`)
29. `test_leaderboard_empty_db`: Empty DB returns `[]` with status 200 OK.
30. `test_leaderboard_ranking_order`: Register multiple workers with varying `records_broken` and `total_attempts`. Assert returned order is `records_broken DESC, total_attempts DESC`.
31. `test_leaderboard_limit_parameter`: Query `?limit=2`. Assert length of result list is 2.
32. `test_leaderboard_invalid_limit_returns_422`: Query `?limit=0` or `?limit=-1`. Assert 422.

### Group 6: Network Statistics (`/api/v1/stats`)
33. `test_stats_initial_counts`: Seed DB with 3 problems. Assert 200 OK, `total_problems=3`, `active_workers=0`, `total_attempts=0`, `verified_solutions=0`.
34. `test_stats_updates_after_activity`: Register worker, submit solution, record heartbeat. Assert counts increment accurately.

### Group 7: Problem Detail Endpoint (`/api/v1/problems/{id}`)
35. `test_get_problem_by_id_success`: GET `/api/v1/problems/3_3_in_circle`. Assert 200 OK, returns metadata, tokens, $N$, reference metric, and record coordinates.
36. `test_get_problem_by_id_not_found`: GET `/api/v1/problems/non_existent`. Assert 404 Not Found.

---

## 7. Caveats

- **FastAPI / Pydantic Environment**: `fastapi`, `uvicorn`, `pydantic`, and `httpx` must be added to `pyproject.toml` dependencies and installed in the execution environment before running `tests/test_server_api.py`.
- **Response Format on 400 Geometric Rejection**: FastAPI's default `raise HTTPException(status_code=400, detail="...")` yields `{"detail": "..."}`. To return `{"status": "rejected", "verified": false, "message": "..."}` with status code 400 as demanded by the test suite and client daemon, `JSONResponse(status_code=400, content={"status": "rejected", "verified": False, "message": msg})` must be used.
- **Metric Scaling Check**: In `solution_tools.py:verify_solution`, `calc_metric` is compared against `sol.final_metric`. When creating the temporary JSON solution file in `api_submit_solution`, setting `final_metric` to `compute_friedman_metric(req.s, prob["inner_token"], prob["container_token"])` prevents spurious metric scaling errors.

---

## 8. Conclusion

The specification for Milestone 3 (Coordinator REST API & In-Process Verifier) is fully probed, verified against all authoritative specs, design documents, and the existing codebase. The specification covers:
- All 6 core endpoints + 1 discovered endpoint (`GET /api/v1/problems/{id}`).
- Full schemas, methods, query parameters, status codes (200, 204, 400, 422).
- Precise geometric verification integration with SAT tolerance $10^{-6}$ and record delta $10^{-5}$.
- A comprehensive 36-test suite covering happy paths, edge cases, schema validations, geometric rejections, and concurrency.

---

## 9. Verification Method

To verify the specification once implemented:
1. Ensure dependencies are installed: `pip install fastapi uvicorn pydantic httpx` (or via dev venv).
2. Run test suite:
   ```bash
   pytest tests/test_server_api.py -v
   ```
3. Run existing database and scheduler suites to confirm zero regressions:
   ```bash
   pytest tests/test_server_database*.py tests/test_server_scheduler*.py -v
   ```
4. Invalidation conditions: Any test failure in `tests/test_server_api.py`, failure to return 400 on overlapping coordinates, failure to return 204 on empty work queue, or mutation of `problems.best_s` from unverified heartbeats.
