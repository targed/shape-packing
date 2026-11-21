# Handoff Report — Milestone 2 Iteration 2: Scheduler Review & Adversarial Verification

**Agent**: `reviewer_m2_it2_1`  
**Roles**: Reviewer, Critic  
**Date**: 2026-11-21T00:06:00Z  
**Target File**: `src/shape_packing/server/scheduler.py`  
**Verdict**: **APPROVE**  

---

## 1. Observation

### 1.1 Code Inspection of `src/shape_packing/server/scheduler.py`
1. **Exploration Fall-Through Fix (lines 108–160)**:
   - In lines 109–125:
     ```python
     prob = None
     # 10% Probability exploration stage over unattempted shape configurations
     if random.random() < 0.10:
         # First attempt unleased unattempted candidates
         cursor.execute(
             """
             SELECT p.*
             FROM problems p
             LEFT JOIN active_leases l ON p.id = l.problem_id
             WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'
               AND (p.status = 'unattempted' OR p.total_attempts = 0)
               AND l.work_id IS NULL
             ORDER BY RANDOM()
             LIMIT 1
             """
         )
         prob = cursor.fetchone()
     ```
   - Lines 123–136 from the prior iteration (which had an inner fallback that re-selected leased unattempted problems) have been completely removed.
   - When all unattempted problems are already leased, `prob` remains `None`, seamlessly falling through to line 127 (`if prob is None:`), which executes the exploitation query to select an unleased candidate from across the non-optimal catalog.
   - Only if all non-optimal problems in the catalog are currently leased does it reach the shared leasing fallback at line 161.

2. **Input Normalization & Exception Handling for `cores` and `lease_seconds` (lines 70–87)**:
   - `cores`:
     ```python
     if isinstance(cores, bool) or not isinstance(cores, int):
         try:
             c = max(1, int(cores))
         except (ValueError, TypeError, OverflowError):
             c = 1
     else:
         c = max(1, cores)
     recommended_attempts = max(1000, min(c * 1000, 20000))
     ```
   - `lease_seconds`:
     ```python
     MAX_LEASE_SECONDS = 604800  # 7 days max lease duration
     ...
     if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int):
         try:
             ls = min(max(1, int(lease_seconds)), MAX_LEASE_SECONDS)
         except (ValueError, TypeError, OverflowError):
             ls = 300
     else:
         ls = min(max(1, lease_seconds), MAX_LEASE_SECONDS)
     ```
   - Catches `(ValueError, TypeError, OverflowError)` preventing crashes from `float('inf')`, `float('-inf')`, `float('nan')`, or arbitrarily large ints.
   - Enforces clamp `[1, 604800]` on `ls`, preventing C int overflows or `datetime` out-of-range errors in `datetime.timedelta(seconds=ls)`.

3. **`record_heartbeat` Guards (lines 263–282)**:
   - Rejects boolean `attempts` and bounds integer:
     ```python
     if (
         isinstance(attempts, bool)
         or not isinstance(attempts, int)
         or attempts < 0
         or attempts > 2**63 - 1
     ):
         return False
     ```
   - `best_s` validation:
     ```python
     if best_s is not None:
         if isinstance(best_s, bool) or not isinstance(best_s, (int, float)):
             return False
         try:
             f_best_s = float(best_s)
         except (ValueError, TypeError, OverflowError):
             return False
         if math.isnan(f_best_s) or math.isinf(f_best_s) or f_best_s <= 0.0 or f_best_s > 1e308:
             return False
     ```
   - Guarantees SQLite binding will never raise an `OverflowError` and rejects non-finite/negative/non-positive floats.
   - Verified that `best_s` is treated solely as telemetry and is NEVER written into `problems.best_s` (lines 332–341 only update `total_attempts`).

4. **`expire_stale_leases` Logic (lines 19–41)**:
   - Validates `isinstance(conn, sqlite3.Connection)`.
   - Uses `BEGIN IMMEDIATE` to prevent deadlock/race conditions.
   - Deletes `expires_at <= CURRENT_TIMESTAMP`.
   - Returns `max(0, deleted or 0)` defensively handling `None` rowcounts.

### 1.2 Automated Test Execution
Running the full regression suite:
```bash
pytest tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py tests/test_server_database.py -v
```
Output:
```text
============================= 147 passed in 8.12s ==============================
```
Specifically, both tests that previously failed now pass cleanly:
- `tests/test_server_scheduler_concurrency.py::test_concurrent_assign_work_distinct_problems PASSED`
- `tests/test_server_scheduler_concurrency.py::test_exploration_does_not_duplicate_lease_when_unleased_problems_exist PASSED`

---

## 2. Logic Chain

1. **Resolution of Duplicate Leases (Referencing Observation 1.1.1 & 1.2)**:
   - In iteration 1, when `random.random() < 0.10` selected exploration, an inner fallback query directly queried already-leased unattempted problems if no unleased unattempted problem existed. This caused duplicate leases while unleased attempted problems were waiting in the catalog.
   - With the deletion of that inner fallback, `prob` remains `None` when all unattempted problems are in-flight, which smoothly enters `if prob is None:` (exploitation).
   - Exploitation filters with `l.work_id IS NULL`, so it exclusively picks unleased problems across the rest of the catalog.
   - In an adversarial test where 1 unattempted problem was leased by Worker 1, and exploration was forced for Worker 2, Worker 2 received an unleased attempted problem with zero duplicate leases.

2. **Resolution of Overflow & Value Errors (Referencing Observation 1.1.2, 1.1.3 & 1.2)**:
   - Casting floats like `float('inf')` or `float('nan')` to `int` raises `OverflowError` or `ValueError`. Catching `(ValueError, TypeError, OverflowError)` safely sets default fallback values.
   - Clamping `lease_seconds` to `[1, 604800]` ensures `datetime.timedelta(seconds=ls)` is bounded to at most 7 days, avoiding any date overflow.
   - SQLite signed 64-bit integers cannot exceed `2**63 - 1`. Enforcing `attempts > 2**63 - 1` prevents database serialization crashes.
   - Guarding `f_best_s > 1e308` and catching `OverflowError` during `float(best_s)` prevents floating point overflows from corrupting telemetry.

3. **Integrity & Concurrency Robustness**:
   - Zero hardcoded test names, fake return values, or shortcuts exist in `src/shape_packing/server/scheduler.py`.
   - Multi-process and multi-threaded concurrency suites (30 threads, 8 processes) run under WAL mode with zero deadlocks and zero invariant violations.

---

## 3. Caveats

- **No Caveats**: All 4 specific verification areas requested in the dispatch instructions were reviewed, tested across boundary values, and confirmed. Zero regressions were detected across the entire test suite.

---

## 4. Conclusion

- **Verdict**: **APPROVE**
- `src/shape_packing/server/scheduler.py` is fully verified, mathematically sound, defensively bounded against all numerical/type anomalies, and concurrency-safe under high contention.
- Milestone 2 is complete and ready to advance to Milestone 3 (FastAPI Coordinator REST API & In-Process Geometric Verifier).

---

## 5. Verification Method

To independently reproduce the complete verification:

### 5.1 Full Regression Test Command
```bash
pytest tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py tests/test_server_database.py -v
```
Expected output:
```text
============================= 147 passed in ~8s ==============================
```

### 5.2 Direct Adversarial Exploration & Overflow Verification
```bash
PYTHONPATH=src python3 -c "
import sqlite3
from unittest.mock import patch
from shape_packing.server.database import init_db
from shape_packing.server.scheduler import assign_work, record_heartbeat, expire_stale_leases

conn = init_db(':memory:')
conn.execute(\"INSERT INTO problems (id, inner_token, container_token, n, status, total_attempts) VALUES ('p_unatt', 'c', 's', 1, 'unattempted', 0)\")
conn.execute(\"INSERT INTO problems (id, inner_token, container_token, n, status, total_attempts) VALUES ('p_att1', 'c', 's', 1, 'in_progress', 100)\")
conn.commit()

# 1. Force exploration: Worker 1 gets p_unatt
with patch('random.random', return_value=0.01):
    w1 = assign_work(conn, 'w1')
assert w1['problem'] == 'p_unatt'

# 2. Force exploration again: Worker 2 MUST get p_att1, NOT p_unatt
with patch('random.random', return_value=0.01):
    w2 = assign_work(conn, 'w2')
assert w2['problem'] == 'p_att1'

# 3. Direct overflow boundaries
assert assign_work(conn, 'w_test', cores=float('inf'))['recommended_attempts'] == 1000
assert assign_work(conn, 'w_test', lease_seconds=10**20)['lease_seconds'] == 604800
assert record_heartbeat(conn, w1['work_id'], 'w1', attempts=2**63) is False
assert record_heartbeat(conn, w1['work_id'], 'w1', attempts=10, best_s=1e309) is False
assert record_heartbeat(conn, w1['work_id'], 'w1', attempts=2**63 - 1, best_s=1e308) is True
print('ALL INDEPENDENT VERIFICATIONS PASSED!')
"
```
Expected output:
```text
ALL INDEPENDENT VERIFICATIONS PASSED!
```
