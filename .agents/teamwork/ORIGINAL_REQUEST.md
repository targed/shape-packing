# Original User Request

## 2026-11-20T22:34:51Z

Build a distributed computing system for 2D shape packing featuring a centralized coordinator REST API with in-process geometric SAT verification and a native multi-threaded worker client daemon.

Working directory: /home/targed/Documents/Git/shape-packing
Integrity mode: development

Reference spec: docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md
Implementation plan: docs/superpowers/plans/2026-11-20-distributed-shape-packing.md

## Requirements

### R1. Coordinator Database Layer and Problem Ingestion
Implement an SQLite database in WAL mode storing problems, solution records, registered workers, and active work leases in `src/shape_packing/server/database.py`. Support seeding baseline benchmark problems from `data/packingVerification/*.json`.

### R2. Work Scheduler and Priority Allocator
Implement a multi-armed bandit scheduler in `src/shape_packing/server/scheduler.py` that leases problems to workers based on geometric void space (packing density), gap to records, and stuck problem backoff, while strictly excluding `proved_optimal` instances. Handle lease expiry and heartbeat accounting.

### R3. Coordinator REST API and In-Process Geometric Verifier
Build FastAPI coordinator endpoints in `src/shape_packing/server/app.py` (`/api/v1/workers/register`, `/api/v1/work`, `/api/v1/solutions`, `/api/v1/heartbeat`, `/api/v1/leaderboard`, `/api/v1/stats`). Every submitted solution must be strictly verified in-process using `src/shape_packing/solution_tools.py:verify_solution` (pairwise Separating Axis Theorem non-overlap and container confinement checks) before atomically committing a new record.

### R4. Native Worker Client Daemon
Build a Python worker client in `src/shape_packing/client/native_worker.py` that connects to the coordinator using Python's standard library `urllib`, runs search batches at idle OS priority using `packer_rs` via `solver_interface`, immediately submits improved configurations, and flushes heartbeats gracefully on SIGINT/SIGTERM.

### R5. Verification and End-to-End Testing
Provide comprehensive automated pytest test suites covering database operations, scheduler leasing, API endpoints (valid vs invalid geometric submissions), worker loop cycles, and an integrated end-to-end workflow test.

## Acceptance Criteria

### Database and Scheduler
- [ ] SQLite database initializes tables with WAL mode enabled.
- [ ] Work scheduler assigns non-optimal problems and recovers expired leases.
- [ ] Heartbeat endpoint updates attempt tallies on both problem and worker records.

### Geometric Verification and API
- [ ] `/api/v1/solutions` validates coordinate vector length (3*N), runs pairwise SAT collision checks, and verifies container boundary containment.
- [ ] Submissions with overlapping polygons or boundary penetrations are rejected with a 400 error.
- [ ] Verified improvements atomically update the best record and increment the finder's leaderboard score.

### Client Daemon
- [ ] Worker runs without third-party networking dependencies using standard library `urllib`.
- [ ] Handles SIGINT/SIGTERM gracefully by reporting in-flight attempts before terminating.

### Test Suite
- [ ] `pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_api.py tests/test_native_worker.py tests/test_distributed_e2e.py` passes with 0 failures.
