# Milestone 2 Review and Adversarial Challenge Report

**Reviewer**: `reviewer_m2_2` (Reviewer 2)  
**Milestone**: Milestone 2: Work Scheduler and Priority Allocator  
**Date**: 2026-11-20T23:46:30Z  
**Target Files Reviewed**:
- `src/shape_packing/server/scheduler.py`
- `tests/test_server_scheduler.py`
- Relevant schema in `src/shape_packing/server/database.py`

---

## Review Summary

**Verdict**: **APPROVE**

The implementation of `src/shape_packing/server/scheduler.py` and its comprehensive test suite `tests/test_server_scheduler.py` satisfies all requirements from `ORIGINAL_REQUEST.md` (§R2) and `PROJECT.md` (§ Interface Contracts). The multi-armed bandit allocation policy, lease expiration mechanics, timestamp handling, foreign key consistency, and telemetry boundary protections are fully realized without shortcuts or facades.

---

## 1. Observation

### 1.1 Requirements & Interface Compliance
- **`ORIGINAL_REQUEST.md` §R2**:
  > "Implement a multi-armed bandit scheduler in `src/shape_packing/server/scheduler.py` that leases problems to workers based on geometric void space (packing density), gap to records, and stuck problem backoff, while strictly excluding `proved_optimal` instances. Handle lease expiry and heartbeat accounting."
- **`PROJECT.md` Interface Contracts**:
  - `assign_work(conn: sqlite3.Connection, worker_id: str, cores: int = 1, lease_seconds: int = 300) -> Optional[Dict[str, Any]]`:
    - Exactly outputs dictionary with keys: `work_id`, `problem`, `inner_token`, `container_token`, `n`, `target_s`, `recommended_attempts`, `lease_seconds`.
    - Verified: `test_assign_work_schema_compliance` directly validates schema and data types.
  - `record_heartbeat(conn: sqlite3.Connection, work_id: str, worker_id: str, attempts: int, best_s: Optional[float] = None) -> bool`:
    - Returns `True` if recorded against active lease, `False` if lease expired or invalid.
  - `expire_stale_leases(conn: sqlite3.Connection) -> int`:
    - Prunes expired rows from `active_leases WHERE expires_at <= CURRENT_TIMESTAMP` and returns deleted rowcount.

### 1.2 Lease Expiration Mechanics & UTC Timestamp Formatting
- **UTC Timestamp Generation**:
  `assign_work` computes:
  ```python
  now_utc = datetime.datetime.now(datetime.timezone.utc)
  expires_at_dt = now_utc + datetime.timedelta(seconds=ls)
  expires_at_str = expires_at_dt.strftime("%Y-%m-%d %H:%M:%S")
  ```
  This creates a space-separated UTC timestamp matching SQLite's `CURRENT_TIMESTAMP` and `datetime('now')` verbatim.
- **Lease Expiration Pruning**:
  In `expire_stale_leases`:
  ```sql
  DELETE FROM active_leases WHERE expires_at <= CURRENT_TIMESTAMP
  ```
  Query plan inspection via `EXPLAIN QUERY PLAN` confirms SQLite uses the covering index:
  `SEARCH active_leases USING COVERING INDEX idx_active_leases_expires (expires_at<?)`
- **Auto-Prune on Assignment**:
  `assign_work` immediately triggers `expire_stale_leases(conn)` before evaluating unleased problem availability, guaranteeing expired leases are recovered instantly.

### 1.3 Heartbeat Telemetry Isolation (IRON RULE)
- **Zero Modifications to `problems.best_s`**:
  Inspected all SQL queries within `record_heartbeat` (`scheduler.py` lines 246–350). The only mutation performed on `problems` is:
  ```sql
  UPDATE problems
  SET total_attempts = total_attempts + ?
  WHERE id = ?
  ```
  `problems.best_s` is never referenced in any `UPDATE` or `INSERT` query. Candidate metrics submitted via `best_s` parameter are treated strictly as read-only telemetry. Updating records is exclusively delegated to in-process Separating Axis Theorem (SAT) verified commits in Milestone 3.
- **Worker Compute Accounting**:
  Even if a lease has expired or is invalid, the reporting volunteer's `total_attempts` and `last_seen_at` are faithfully credited in the `workers` table, while the `problems` table is protected.

### 1.4 Test Suite Execution
- **Scheduler Test Suite**:
  `pytest tests/test_server_scheduler.py -v`
  Result: **70 passed in 1.39s** with 0 failures, 0 errors, 0 warnings.
- **Full Server Regression Suite**:
  `pytest tests/test_server_database.py tests/test_server_database_concurrency.py tests/test_server_database_stress.py tests/test_server_scheduler.py -v`
  Result: **117 passed in 4.23s** with 0 failures.

---

## 2. Logic Chain

1. **Integrity Audit**:
   - Source code inspection confirms no hardcoded test values, no fake stub branches (e.g. `if worker_id == "alice"`), and no dummy facades.
   - All logic relies on generic SQL queries and parameter bindings executed against SQLite WAL mode tables.
   - Tests execute against live SQLite memory and temporary file databases, exercising real concurrency via threading barriers.

2. **Bandit Policy Correctness**:
   - **Proved Optimal Exclusion**: All exploration (`random.random() < 0.10`), exploitation, and fallback shared leasing queries apply `COALESCE(LOWER(p.status), '') != 'proved_optimal'`. Case-insensitivity ensures variants like `'PROVED_OPTIMAL'` and `'proved_optimal'` are never scheduled.
   - **Exploration (10%)**: Selects uniformly at random among unattempted configurations (`status = 'unattempted' OR total_attempts = 0`), prioritizing unleased configurations first. Falls back seamlessly to exploitation if no unattempted candidates exist.
   - **Exploitation Scoring (5 Tiers)**:
     - Tier 1: Stuck backoff (`total_attempts > 50000 AND (updated_at IS NULL OR updated_at < datetime('now', '-1 day'))`) derates stalled problems. When a solution record is committed, `updated_at` refreshes to `CURRENT_TIMESTAMP`, instantly clearing stuck status.
     - Tier 2: Closeness boost (`abs(best_s - ref_s) / ref_s <= 0.01`) prioritizes near-record opportunities.
     - Tier 3: Fairness attempt balancing (`total_attempts ASC`).
     - Tier 4: Geometric void space (`density_rank DESC`).
     - Tier 5: Random tie-breaker (`RANDOM()`).
   - **Shared Leasing Fallback**: If all eligible non-optimal candidates are actively leased, `assign_work` falls back to shared stochastic leasing, preventing volunteer compute starvation.

3. **Concurrency Serialization**:
   - `assign_work`, `expire_stale_leases`, and `record_heartbeat` wrap critical sections in `BEGIN IMMEDIATE` transactions.
   - Pre-commit check `if conn.in_transaction: conn.commit()` avoids `sqlite3.OperationalError: cannot start a transaction within a transaction`.
   - Threading stress tests (`test_concurrent_work_assignment_no_duplicates`, `test_concurrent_heartbeats_no_lost_updates`, `test_concurrent_expire_and_assign`) prove that 10 concurrent threads acquire distinct leases and update heartbeats without deadlocks or lost updates.

---

## 3. Findings

### [Minor] Finding 1: Unhandled `OverflowError` on `float('inf')` for `cores` and `lease_seconds`
- **What**: Passing `float('inf')` or `float('-inf')` as `cores` or `lease_seconds` raises an unhandled `OverflowError: cannot convert float infinity to integer` during `int(cores)`.
- **Where**: `src/shape_packing/server/scheduler.py`, line 72 and line 82:
  ```python
  try:
      c = max(1, int(cores))
  except (ValueError, TypeError):
      c = 1
  ```
- **Why**: In Python, `int(float('inf'))` raises `OverflowError`, which inherits from `ArithmeticError`, not `ValueError` or `TypeError`.
- **Impact / Risk**: **Low**. In the FastAPI REST API (Milestone 3), query parameters are parsed by Pydantic as `int`, which rejects non-integer strings with HTTP 422 before calling `assign_work`. However, for direct Python library invocations, passing `cores=float('inf')` causes an unhandled exception.
- **Suggestion**: Expand the exception tuple to `except (ValueError, TypeError, OverflowError):` in `scheduler.py` when touching this file in future milestones.

---

## 4. Adversarial Review & Stress Test Results

| # | Stress Test Scenario | Tested Condition | Predicted Behavior | Actual Behavior | Result |
|---|----------------------|------------------|--------------------|-----------------|--------|
| 1 | Clock string comparison | Space-separated UTC timestamp format vs SQLite `CURRENT_TIMESTAMP` | Chronological sort matches string sort | Identical format `'YYYY-MM-DD HH:MM:SS'`, query uses covering index | **PASS** |
| 2 | Heartbeat attempt overflow | `attempts = 2**62` | Large integer stored in 64-bit SQLite INTEGER | Successfully added and accumulated | **PASS** |
| 3 | Heartbeat metric tampering | `best_s = 2.0` on problem with `best_s = 5.0` | `problems.best_s` must remain 5.0 | `problems.best_s` remains 5.0; zero writes to column | **PASS** |
| 4 | Stale lease heartbeat rejection | Worker reports heartbeat after `expires_at` has passed | Worker credited, problem not credited, returns `False` | Worker compute recorded, problem unchanged, returned `False` | **PASS** |
| 5 | Proved optimal case variation | Status `'PROVED_OPTIMAL'` and `'proved_optimal'` | Never scheduled | Filter `COALESCE(LOWER(status), '') != 'proved_optimal'` excludes all | **PASS** |
| 6 | Extreme worker ID length | `worker_id` of 1,000 characters | Parameterized insert handles safely | Worker registered, lease assigned | **PASS** |
| 7 | Non-standard float parameter | `cores = float('inf')` | Handled gracefully or raises | Raises `OverflowError` (documented as Minor Finding 1) | **PASS (Documented)** |

---

## 5. Verified Claims & Integrity Confirmation

- **Hardcoded outputs**: **NONE DETECTED**. Verified that all outputs derive dynamically from database queries.
- **Facade implementations**: **NONE DETECTED**. Real bandit scheduling with 5-tier ordering and 10% exploration.
- **Shortcuts / Task Bypasses**: **NONE DETECTED**. Complete SQLite WAL transactions, lease tracking, and attempt scaling.
- **Fabricated verification artifacts**: **NONE DETECTED**. All 70 scheduler tests and 117 total server tests independently executed and verified.
- **Self-certifying work**: **NONE DETECTED**. Full multi-threaded concurrency tests independently validated with barrier synchronization.

---

## 6. Caveats

- **No Caveats**: The implementation satisfies all criteria specified in the design and original requirements.
- **Milestone 3 Coordination Note**: The REST API layer in `src/shape_packing/server/app.py` should map `assign_work` returning `None` to HTTP 204 No Content (or 404), and invoke `record_heartbeat` within the `POST /api/v1/heartbeat` endpoint.

---

## 7. Conclusion

Milestone 2 (Work Scheduler and Priority Allocator) is **APPROVED**. The code is well-architected, robust against concurrent multi-threaded contention, and enforces all required business and integrity boundaries.

---

## 8. Verification Method

To independently reproduce the verification:

1. **Run the Scheduler Test Suite**:
   ```bash
   pytest tests/test_server_scheduler.py -v
   ```
   *Expected outcome*: 70 passed in ~1.4 seconds with 0 failures.

2. **Run the Full Server Regression Suite**:
   ```bash
   pytest tests/test_server_database.py tests/test_server_database_concurrency.py tests/test_server_database_stress.py tests/test_server_scheduler.py -v
   ```
   *Expected outcome*: 117 passed in ~4.2 seconds with 0 failures.

3. **Verify Heartbeat Telemetry Protection**:
   ```bash
   pytest tests/test_server_scheduler.py -k "test_record_heartbeat_does_not_modify_best_s" -v
   ```
   *Expected outcome*: 1 passed.
