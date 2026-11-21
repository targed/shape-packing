# Project Orchestration Plan: Distributed Shape Packing

## Objective
Deliver a production-ready distributed computing system for 2D shape packing meeting all requirements R1-R5 and acceptance criteria in ORIGINAL_REQUEST.md.

## Architectural Structure & Modules
- `src/shape_packing/server/database.py` (Database, WAL mode, worker registration, solution storage, problem seeding)
- `src/shape_packing/server/scheduler.py` (Work assignment, multi-armed bandit, lease recovery, heartbeat accounting)
- `src/shape_packing/server/app.py` (FastAPI REST API, endpoints `/api/v1/*`, in-process SAT geometric verification)
- `src/shape_packing/client/native_worker.py` (Client daemon, urllib networking, idle priority, graceful signal handling)
- `tests/test_server_database.py`, `tests/test_server_scheduler.py`, `tests/test_server_api.py`, `tests/test_native_worker.py`, `tests/test_distributed_e2e.py` (Comprehensive test coverage)

## Execution Milestones
1. **Milestone 1: Coordinator Database Layer & Ingestion (R1)**
   - Implement `src/shape_packing/server/database.py` and `tests/test_server_database.py`.
   - Gate: build & tests pass, review approve, challenge approve, clean audit.
2. **Milestone 2: Work Scheduler & Priority Allocator (R2)**
   - Implement `src/shape_packing/server/scheduler.py` and `tests/test_server_scheduler.py`.
   - Gate: build & tests pass, review approve, challenge approve, clean audit.
3. **Milestone 3: REST API & In-Process Verifier (R3)**
   - Implement `src/shape_packing/server/app.py` and `tests/test_server_api.py`.
   - Gate: build & tests pass, review approve, challenge approve, clean audit.
4. **Milestone 4: Native Worker Daemon (R4)**
   - Implement `src/shape_packing/client/native_worker.py` and `tests/test_native_worker.py`.
   - Gate: build & tests pass, review approve, challenge approve, clean audit.
5. **Milestone 5: Integrated Verification & E2E Testing (R5)**
   - Implement `tests/test_distributed_e2e.py` and verify all test suites together.
   - Run adversarial coverage and final acceptance checks.
