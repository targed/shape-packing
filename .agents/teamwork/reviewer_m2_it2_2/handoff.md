# Handoff Report — Milestone 2 Iteration 2 Code Review & Adversarial Stress Test

**Agent**: `reviewer_m2_it2_2`  
**Roles**: Reviewer, Adversarial Critic  
**Date**: 2026-11-21T00:08:00Z  
**Verdict**: **APPROVE**  
**Integrity Attestation**: Pass — Zero integrity violations detected (no hardcoding, no facades, no shortcuts, no fabricated verifications).

---

## 1. Observation

### 1.1 Code and Test Inspection
- **Reviewed File**: `src/shape_packing/server/scheduler.py` (348 lines).
- **Core Functions Inspected**:
  - `expire_stale_leases(conn: sqlite3.Connection) -> int` (lines 19-41)
  - `assign_work(conn: sqlite3.Connection, worker_id: str, cores: int = 1, lease_seconds: int = 300) -> Optional[Dict[str, Any]]` (lines 43-233)
  - `record_heartbeat(conn: sqlite3.Connection, work_id: str, worker_id: str, attempts: int, best_s: Optional[float] = None) -> bool` (lines 235-348)
- **Database Schema & Foreign Keys**: `src/shape_packing/server/database.py` (407 lines) enforcing `PRAGMA foreign_keys = ON`, `PRAGMA journal_mode = WAL`, and table constraints on `problems`, `solutions`, `workers`, and `active_leases`.

### 1.2 Regression Test Execution
- Executed specified test command:
  ```bash
  pytest tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py tests/test_server_database.py -v
  ```
  **Result**: 147 passed in 7.29s (exit code 0).
- Executed full server test suite:
  ```bash
  pytest tests/test_server_*.py -v
  ```
  **Result**: 165 passed in 10.36s (exit code 0).

### 1.3 Concrete Code Behaviors Observed in `src/shape_packing/server/scheduler.py`
1. **Multi-Armed Bandit Tier Ranking (lines 136-155, 167-182)**:
   - Tier 1: Stuck backoff (`CASE WHEN p.total_attempts > 50000 AND (p.updated_at IS NULL OR p.updated_at < datetime('now', '-1 day')) THEN 1 ELSE 0 END ASC`)
   - Tier 2: Closeness boost (`CASE WHEN p.reference_s IS NOT NULL AND p.best_s IS NOT NULL AND p.reference_s > 0 AND (abs(p.best_s - p.reference_s) / p.reference_s) <= 0.01 THEN 0 ELSE 1 END ASC`)
   - Tier 3: Fair attempt balancing (`p.total_attempts ASC`)
   - Tier 4: Void space density rank (`p.density_rank DESC`)
   - Tier 5: Random tie-breaker (`RANDOM()`)
2. **Proved Optimal Exclusion (lines 117, 134, 166)**:
   - Present across all 3 problem selection query paths: exploration, exploitation, and fallback shared leasing.
   - Evaluated as `WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'`, which safely handles all casing variations (`proved_optimal`, `PROVED_OPTIMAL`, `Proved_Optimal`) and NULL values.
3. **Exploration Fall-Through (lines 109-127)**:
   - 10% unattempted exploration query only queries unleased unattempted candidates (`(p.status = 'unattempted' OR p.total_attempts = 0) AND l.work_id IS NULL`).
   - If no unleased unattempted candidate exists, `prob` remains `None`, seamlessly falling through to the 90% exploitation query. It does not create premature duplicate leases.
4. **Transaction & WAL Concurrency (lines 32, 96, 290)**:
   - Explicit `BEGIN IMMEDIATE` transaction serialization protects write queries from concurrency deadlocks and race conditions.
   - Guarded by `if conn.in_transaction: conn.commit()` to prevent SQLite `OperationalError: cannot start a transaction within a transaction`.
   - Comprehensive `try...except Exception: conn.rollback(); raise` ensures no dangling uncommitted transactions.
5. **Row Factory Agnosticism (lines 191-195, 331)**:
   - Checks `hasattr(row, "keys")` before dictionary indexing; falls back to `cursor.description` column mapping for raw tuple connections.
6. **Defensive Input Validation & Exception Handling**:
   - `cores`: Normalizes non-integer, bool, float, and strings; catches `(ValueError, TypeError, OverflowError)` to protect against `float('inf')` and huge exponents; clamps recommended attempts to `[1000, 20000]`.
   - `lease_seconds`: Catches `(ValueError, TypeError, OverflowError)`; clamps lease duration to `[1, 604800]` (1s to 7 days), preventing `datetime.timedelta` C-level integer overflow.
   - `attempts`: Rejects negative, boolean, and values `> 2**63 - 1` (preventing SQLite integer parameter binding overflow).
   - `best_s`: Validates finite positive float, catches `OverflowError`, rejects NaN, Inf, non-positive, and values `> 1e308`. Telemetry boundary strictly observed: `best_s` in `record_heartbeat` NEVER modifies `problems.best_s`.

---

## 2. Logic Chain

1. **Verification of MAB Tier Ranking Order**:
   - *Observation*: ORDER BY clause specifies Tier 1 (stuck backoff) first, Tier 2 (closeness boost) second, Tier 3 (attempts ASC) third, Tier 4 (density_rank DESC) fourth, and Tier 5 (RANDOM()) fifth.
   - *Empirical Test*: Directly simulated a 6-problem catalog with conflicting properties. Verified assignment sequence:
     1. `p_close_boost` (non-stuck, close)
     2. `p_low_attempts_high_density` (non-stuck, not close, attempts=100, density=0.9)
     3. `p_low_attempts_low_density` (non-stuck, not close, attempts=100, density=0.1)
     4. `p_regular_1000` (non-stuck, not close, attempts=1000)
     5. `p_stuck_close` (stuck backoff deprioritizes to back despite being close)
   - *Conclusion*: Multi-armed bandit tier ranking complies 100% with requirements: `stuck backoff > closeness boost > attempt balancing > density rank > random`.

2. **Verification of Proved Optimal Exclusion**:
   - *Observation*: Every SQL query selecting problems from `problems` table has `COALESCE(LOWER(p.status), '') != 'proved_optimal'`.
   - *Empirical Test*: `test_adversarial_proved_optimal_extraction_exhaustive` executed 1,000 extractions with mixed exploration/exploitation and lease resets, and `test_fallback_shared_leasing_excludes_proved_optimal` tested shared leasing fallback.
   - *Conclusion*: Proved optimal exclusion is enforced across all execution paths.

3. **Verification of SQLite WAL Transaction Safety**:
   - *Observation*: `BEGIN IMMEDIATE` is acquired before reading problem availability and writing leases.
   - *Empirical Test*: `test_concurrent_assign_work_distinct_problems` ran 30 concurrent threads leasing 30 problems; zero duplicate leases occurred. `test_concurrent_heartbeats_no_lost_updates` ran concurrent heartbeat updates; zero lost updates occurred.
   - *Conclusion*: Transaction safety in SQLite WAL mode is verified under high concurrency.

4. **Verification of Iteration 2 Defect Fixes**:
   - *Observation*: Previously, `test_concurrent_assign_work_distinct_problems` and `test_exploration_does_not_duplicate_lease_when_unleased_problems_exist` failed due to premature fallback within the exploration branch.
   - *Inspection*: Inner fallback query was eliminated, allowing unleased exploration to fall through to unleased exploitation.
   - *Empirical Test*: Both concurrency tests now pass consistently.

5. **Adversarial Integrity Audit**:
   - *Source Inspection*: Scanned `src/shape_packing/server/scheduler.py` for hardcoded constants, mock branches, test fixtures in production code, or shortcut bypasses.
   - *Result*: Zero integrity violations found. Real mathematical operations and real SQL queries are executed.

---

## 3. Caveats

- **No Caveats**: The implementation was tested under both standalone unit/stress tests and concurrent multi-threaded/multi-process loads. Zero regressions or design defects were identified.

---

## 4. Conclusion

**Verdict**: **APPROVE**

The work scheduler and priority allocator implementation in `src/shape_packing/server/scheduler.py` fully satisfies all architectural, functional, concurrency, and security requirements for Milestone 2:
- Multi-armed bandit tier ranking hierarchy operates strictly as specified.
- Proved optimal exclusion is watertight across exploration, exploitation, and shared fallback paths.
- SQLite WAL transaction safety is maintained via `BEGIN IMMEDIATE` and robust transaction cleanup.
- Defensive parameter guards protect against arithmetic overflow, boolean coercion, and out-of-range timestamps.
- All 147 regression tests pass with 100% success.

---

## 5. Verification Method

To independently reproduce the full verification:

```bash
# 1. Run all scheduler and database test suites (147 tests)
pytest tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py tests/test_server_database.py -v

# 2. Run all server test suites (165 tests)
pytest tests/test_server_*.py -v

# 3. Empirically verify MAB tier priority order
PYTHONPATH=src python3 -c "
import sqlite3, unittest.mock as mock
from shape_packing.server.database import init_db
from shape_packing.server.scheduler import assign_work

conn = init_db(':memory:')
c = conn.cursor()
c.execute(\"\"\"INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, total_attempts, density_rank, updated_at) VALUES
    ('p_stuck_close', '4', '4', 1, 1.005, 1.0, 'best_known', 60000, 0.5, '2020-01-01 00:00:00'),
    ('p_regular_1000', '4', '4', 1, 1.5, 1.0, 'best_known', 1000, 0.5, CURRENT_TIMESTAMP),
    ('p_close_boost', '4', '4', 1, 1.005, 1.0, 'best_known', 20000, 0.5, CURRENT_TIMESTAMP),
    ('p_low_attempts_low_density', '4', '4', 1, 1.5, 1.0, 'best_known', 100, 0.1, CURRENT_TIMESTAMP),
    ('p_low_attempts_high_density', '4', '4', 1, 1.5, 1.0, 'best_known', 100, 0.9, CURRENT_TIMESTAMP),
    ('p_proved_opt', '4', '4', 1, 1.0, 1.0, 'proved_optimal', 0, 1.0, CURRENT_TIMESTAMP)\"\"\")
conn.commit()

order = []
for i in range(5):
    with mock.patch('random.random', return_value=0.5):
        w = assign_work(conn, f'w_{i}')
        order.append(w['problem'])

assert order == ['p_close_boost', 'p_low_attempts_high_density', 'p_low_attempts_low_density', 'p_regular_1000', 'p_stuck_close']
print('VERIFIED: MAB tier precedence verified exactly!')
"
```
