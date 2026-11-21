# Milestone 2 Handoff Report: Work Scheduler and Priority Allocator

**Agent**: `worker_m2`  
**Milestone**: Milestone 2: Work Scheduler and Priority Allocator  
**Date**: 2026-11-20T23:41:45Z  
**Target Files Modified**:
- `src/shape_packing/server/scheduler.py`
- `tests/test_server_scheduler.py`

---

## 1. Observation

### 1.1 Requirements & Interface Contracts
- **`ORIGINAL_REQUEST.md` §R2**:
  > "Implement a multi-armed bandit scheduler in `src/shape_packing/server/scheduler.py` that leases problems to workers based on geometric void space (packing density), gap to records, and stuck problem backoff, while strictly excluding `proved_optimal` instances. Handle lease expiry and heartbeat accounting."
- **`PROJECT.md` § Interface Contracts (scheduler.py ↔ app.py)**:
  - `assign_work(conn: sqlite3.Connection, worker_id: str, cores: int = 1, lease_seconds: int = 300) -> Optional[Dict[str, Any]]`
  - `record_heartbeat(conn: sqlite3.Connection, work_id: str, worker_id: str, attempts: int, best_s: Optional[float] = None) -> bool`
  - `expire_stale_leases(conn: sqlite3.Connection) -> int`
- **Return Dictionary Schema from `assign_work`**:
  ```python
  {
      "work_id": str,
      "problem": str,
      "inner_token": str,
      "container_token": str,
      "n": int,
      "target_s": float,
      "recommended_attempts": int,
      "lease_seconds": int,
  }
  ```

### 1.2 Execution Results
- **Test Command**: `pytest tests/test_server_scheduler.py -v`
- **Output**:
  ```text
  ============================= test session starts ==============================
  platform linux -- Python 3.14.10, pytest-9.2.0, pluggy-1.7.0 -- /usr/bin/python
  rootdir: /home/targed/Documents/Git/shape-packing
  collected 70 items

  tests/test_server_scheduler.py::test_assign_work_schema_compliance PASSED [  1%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[1-1000] PASSED [  2%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[4-4000] PASSED [  5%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[16-16000] PASSED [  8%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[64-20000] PASSED [ 12%]
  tests/test_server_scheduler.py::test_assign_work_skips_proved_optimal PASSED [ 24%]
  tests/test_server_scheduler.py::test_assign_work_priority_least_attempts_first PASSED [ 31%]
  tests/test_server_scheduler.py::test_assign_work_priority_density_rank PASSED [ 32%]
  tests/test_server_scheduler.py::test_assign_work_priority_closeness_boost PASSED [ 34%]
  tests/test_server_scheduler.py::test_assign_work_stuck_backoff PASSED    [ 35%]
  tests/test_server_scheduler.py::test_assign_work_stuck_backoff_cleared_by_solution_update PASSED [ 37%]
  tests/test_server_scheduler.py::test_assign_work_exploration_unattempted_selection PASSED [ 38%]
  tests/test_server_scheduler.py::test_expire_stale_leases_past_deleted PASSED [ 44%]
  tests/test_server_scheduler.py::test_record_heartbeat_updates_problem_and_worker_attempts PASSED [ 47%]
  tests/test_server_scheduler.py::test_record_heartbeat_after_lease_expired PASSED [ 52%]
  tests/test_server_scheduler.py::test_record_heartbeat_does_not_modify_best_s PASSED [ 55%]
  tests/test_server_scheduler.py::test_concurrent_work_assignment_no_duplicates PASSED [ 97%]
  tests/test_server_scheduler.py::test_concurrent_heartbeats_no_lost_updates PASSED [ 98%]
  tests/test_server_scheduler.py::test_concurrent_expire_and_assign PASSED [100%]
  ============================== 70 passed in 1.31s ==============================
  ```
- **Server Suite Regression Test**: `pytest tests/test_server_database.py tests/test_server_database_concurrency.py tests/test_server_database_stress.py tests/test_server_scheduler.py -v`
  - Result: `117 passed in 4.11s` with 0 failures.
- **Syntax and Bytecode Verification**: `python3 -m py_compile src/shape_packing/server/scheduler.py tests/test_server_scheduler.py`
  - Result: Clean compile, exit code 0.

---

## 2. Logic Chain

1. **Lease Lifecycle & Expiration**:
   - *Observation*: SQLite evaluates `CURRENT_TIMESTAMP` in UTC space-separated format `'YYYY-MM-DD HH:MM:SS'`.
   - *Implementation*: `expire_stale_leases` deletes rows from `active_leases WHERE expires_at <= CURRENT_TIMESTAMP` and returns `cursor.rowcount`.
   - *Integration*: `assign_work` invokes `expire_stale_leases(conn)` before querying candidate problems, immediately recovering expired leases for reassignment.

2. **Foreign Key Integrity & Worker Auto-Registration**:
   - *Observation*: The database schema enforces `PRAGMA foreign_keys = ON;`, requiring that `active_leases.worker_id` exist in `workers.id`.
   - *Implementation*: Before inserting leases or updating heartbeats, the worker is registered using:
     `INSERT INTO workers (id, username, client_type, last_seen_at) VALUES (?, ?, 'native', CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET last_seen_at = CURRENT_TIMESTAMP`
     This prevents `sqlite3.IntegrityError` without overwriting existing usernames.

3. **Multi-Armed Bandit Scheduling**:
   - *Exclusion*: `COALESCE(LOWER(p.status), '') != 'proved_optimal'` is applied across all exploration, exploitation, and fallback shared leasing queries.
   - *10% Exploration*: With $p < 0.10$, selects uniformly at random from unattempted configurations (`status = 'unattempted' OR total_attempts = 0`), prioritizing unleased configurations first. If no unattempted problems exist, falls through to exploitation.
   - *90% Exploitation Scoring*:
     - Tier 1: Stuck backoff (`total_attempts > 50000 AND (updated_at IS NULL OR updated_at < datetime('now', '-1 day'))` pushed behind non-stuck problems).
     - Tier 2: Closeness boost (`abs(best_s - ref_s) / ref_s <= 0.01` prioritized).
     - Tier 3: Fairness attempt balancing (`total_attempts ASC`).
     - Tier 4: Geometric void space (`density_rank DESC`).
     - Tier 5: Random tie-breaker (`RANDOM()`).
   - *Stochastic Search Sharing Fallback*: If all eligible non-optimal candidates are currently leased, `assign_work` falls back to shared leasing following bandit scoring, preventing volunteer idle starvation.

4. **Attempt Normalization by Hardware Cores**:
   - *Implementation*: Formula `recommended_attempts = max(1000, min(max(1, int(cores)) * 1000, 20000))` normalizes batch completion times to ~5–15s while clamping hardware bounds (1 core $\to$ 1,000, 4 cores $\to$ 4,000, 16 cores $\to$ 16,000, 64 cores $\to$ 20,000).

5. **Heartbeat Progress & Telemetry Protection**:
   - *Validation*: Rejects boolean types (`isinstance(attempts, bool)`), negative counts (`attempts < 0`), non-int values, and non-positive/non-finite `best_s`.
   - *Accounting*: Atomically increments `problems.total_attempts += attempts` (only if lease is active) and `workers.total_attempts += attempts`.
   - *Telemetry Boundary*: `problems.best_s` is never modified by `record_heartbeat`. Solutions must be verified in-process via Separating Axis Theorem (SAT) in Milestone 3 before updating records.
   - *Status Signal*: Returns `True` if recorded against an active lease; returns `False` if lease is expired/not found (while still crediting worker compute) or inputs are invalid.

6. **ACID Concurrency Serialization**:
   - *Implementation*: Both `assign_work` and `record_heartbeat` wrap their critical sections inside `BEGIN IMMEDIATE` transactions in SQLite WAL mode.
   - *Verification*: `test_concurrent_work_assignment_no_duplicates` demonstrated that 10 simultaneous threads requesting work on 10 unleased problems receive 10 distinct problems with 0 duplicate leases.

---

## 3. Caveats

- **No Caveats**: All requirements from `ORIGINAL_REQUEST.md`, `PROJECT.md`, and the dispatch instructions have been completely satisfied.
- **Downstream Dependency Note for Milestone 3**: The coordinator REST API in `src/shape_packing/server/app.py` should map `assign_work` returning `None` to HTTP `204 No Content`, and invoke `record_heartbeat` inside the `POST /api/v1/heartbeat` endpoint.

---

## 4. Conclusion

Milestone 2 is complete. `src/shape_packing/server/scheduler.py` provides complete, non-dummy implementations of `expire_stale_leases`, `assign_work`, and `record_heartbeat`. The comprehensive test suite `tests/test_server_scheduler.py` verifies all 70 test scenarios with 100% pass rate.

---

## 5. Verification Method

To independently verify the implementation:

1. **Run the Scheduler Test Suite**:
   ```bash
   pytest tests/test_server_scheduler.py -v
   ```
   *Expected outcome*: 70 passed in ~1.3 seconds with 0 failures.

2. **Run Full Server Regression Test Suite**:
   ```bash
   pytest tests/test_server_database.py tests/test_server_database_concurrency.py tests/test_server_database_stress.py tests/test_server_scheduler.py -v
   ```
   *Expected outcome*: 117 passed in ~4.1 seconds with 0 failures.

3. **Verify Python Syntax and Imports**:
   ```bash
   python3 -c "import shape_packing.server.scheduler as s; print(dir(s))"
   ```
   *Expected outcome*: Module imports cleanly and exposes `['assign_work', 'expire_stale_leases', 'record_heartbeat', ...]`.
