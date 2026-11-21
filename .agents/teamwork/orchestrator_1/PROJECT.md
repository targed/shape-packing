# Project: Distributed Shape Packing

## Architecture
Centralized coordinator REST service (FastAPI) backed by SQLite WAL mode storage. Workers request problem leases via an adaptive multi-armed bandit scheduler, run local continuous geometric optimization, and submit candidate packing improvements. The coordinator verifies candidates in-process using exact Separating Axis Theorem (SAT) non-overlap and container confinement checks before atomically committing record improvements.

### Data Flow
1. Worker registers via `POST /api/v1/workers/register` -> stored in `workers` table.
2. Worker requests lease via `GET /api/v1/work` -> scheduler assigns problem from `problems` table, creates record in `active_leases`.
3. Worker runs search batches locally, sends `POST /api/v1/heartbeat` with attempt counts -> updates `problems.total_attempts` and `workers.total_attempts`.
4. Worker finds candidate improvement, submits via `POST /api/v1/solutions` -> coordinator runs `verify_solution` (containment + SAT non-overlap + metric check). If valid and strictly better, commits atomic update in `solutions` and `problems.best_s`, and increments `workers.records_broken`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | SQLite WAL DB Schema | Initialize problems, solutions, workers, active_leases tables with WAL mode | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Worker Registration DB | Record worker username, client_type, UUID, and update last_seen_at | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Solution Record DB | Atomic update of solution records, record breaking flag, worker counter | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Problem Verification Seeding | Ingest baseline problems from data/packingVerification/*.json | M1 | ORIGINAL_REQUEST §R1 |
| 5 | Multi-Armed Bandit Scheduler | Assign problems by void space / density rank, gap to records, attempt count | M2 | ORIGINAL_REQUEST §R2 |
| 6 | Proved Optimal Exclusion | Strictly exclude instances marked proved_optimal from work allocation | M2 | ORIGINAL_REQUEST §R2 |
| 7 | Lease Expiry Management | Automatic expiration of stale leases and re-assignment | M2 | ORIGINAL_REQUEST §R2 |
| 8 | Heartbeat & Attempt Accounting | Record worker and problem attempt counters via heartbeat | M2 | ORIGINAL_REQUEST §R2 |
| 9 | FastAPI Coordinator API | REST endpoints /workers/register, /work, /solutions, /heartbeat, /leaderboard, /stats | M3 | ORIGINAL_REQUEST §R3 |
| 10 | In-Process SAT Geometric Verifier | Verify coordinates length (3*N), container confinement, and pairwise SAT non-overlap | M3 | ORIGINAL_REQUEST §R3 |
| 11 | Solution Commit / Reject | Accept valid improvements (200), reject overlaps/out-of-bounds (400), handle duplicates | M3 | ORIGINAL_REQUEST §R3 |
| 12 | Leaderboard & Stats Endpoints | Provide global stats and top contributor ranking | M3 | ORIGINAL_REQUEST §R3 |
| 13 | Native Worker Client Daemon | Python client using stdlib urllib, runs optimization batches at idle OS priority | M4 | ORIGINAL_REQUEST §R4 |
| 14 | Graceful Signal Handling | Catch SIGINT/SIGTERM, flush attempts to heartbeat, shutdown cleanly | M4 | ORIGINAL_REQUEST §R4 |
| 15 | Solver Interface Integration | Worker executes packer_rs solver batches via solver_interface | M4 | ORIGINAL_REQUEST §R4 |
| 16 | Comprehensive Test Suite | Pytest tests for database, scheduler, api, native worker, and e2e integration | M5 | ORIGINAL_REQUEST §R5 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Coordinator Database Layer | database.py: schema, WAL mode, worker reg, solution records, seeding | none | DONE |
| M2 | Work Scheduler & Priority Allocator | scheduler.py: bandit allocation, lease expiry, heartbeat accounting | M1 | DONE |
| M3 | Coordinator REST API & Verifier | app.py: FastAPI endpoints, in-process SAT verification, atomic commit | M1, M2 | DONE |
| M4 | Native Worker Client Daemon | native_worker.py: urllib networking, idle priority, signal handling | M3 | DONE |
| M5 | Integrated Verification & E2E Testing | test suites, e2e integration test, adversarial verification | M1, M2, M3, M4 | DONE |

## Interface Contracts
### database.py ↔ scheduler.py
- `init_db(db_path: str) -> sqlite3.Connection`
- `register_worker(conn: sqlite3.Connection, username: str, client_type: str, worker_id: Optional[str]) -> Dict[str, Any]`
- `get_problem(conn: sqlite3.Connection, problem_id: str) -> Optional[Dict[str, Any]]`
- `update_solution_record(conn: sqlite3.Connection, problem_id: str, worker_id: str, username: str, metric_s: float, coordinates: List[float]) -> bool`

### scheduler.py ↔ app.py
- `assign_work(conn: sqlite3.Connection, worker_id: str, cores: int, lease_seconds: int) -> Optional[Dict[str, Any]]`
- `record_heartbeat(conn: sqlite3.Connection, work_id: str, worker_id: str, attempts: int, best_s: Optional[float]) -> bool`
- `expire_stale_leases(conn: sqlite3.Connection) -> int`

### app.py ↔ native_worker.py
- HTTP REST API over JSON:
  - `POST /api/v1/workers/register` -> `{"worker_id": str, "username": str, "client_type": str}`
  - `GET /api/v1/work?worker_id={id}&cores={cores}` -> `{"work_id": str, "problem": str, "inner_token": str, "container_token": str, "n": int, "target_s": float, "recommended_attempts": int, "lease_seconds": int}`
  - `POST /api/v1/solutions` -> `{"status": str, "verified": bool, "is_new_record": bool, "metric_s": float, "message": str}`
  - `POST /api/v1/heartbeat` -> `{"status": str}`
  - `GET /api/v1/stats` -> `{"total_problems": int, "active_workers": int, "total_attempts": int, "verified_solutions": int}`
  - `GET /api/v1/leaderboard` -> `List[{"username": str, "total_attempts": int, "records_broken": int}]`

## Code Layout
- `src/shape_packing/server/__init__.py`: Server package init
- `src/shape_packing/server/database.py`: Database operations and table schema
- `src/shape_packing/server/scheduler.py`: Work scheduling and lease management
- `src/shape_packing/server/app.py`: FastAPI server application and verification
- `src/shape_packing/client/__init__.py`: Client package init
- `src/shape_packing/client/native_worker.py`: Native worker daemon
- `tests/test_server_database.py`: Database tests
- `tests/test_server_scheduler.py`: Scheduler tests
- `tests/test_server_api.py`: REST API tests
- `tests/test_native_worker.py`: Native worker daemon tests
- `tests/test_distributed_e2e.py`: End-to-end integration test
