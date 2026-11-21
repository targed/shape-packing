# Handoff Report — Milestone 2 Iteration 2: Scheduler Concurrency and Robustness Fix

**Agent**: `worker_m2_it2`  
**Milestone**: Milestone 2: Work Scheduler and Priority Allocator (Iteration 2)  
**Date**: 2026-11-20T18:02:30Z  
**Modified File**: `src/shape_packing/server/scheduler.py`  
**Status**: Completed — All 147 Regression Tests Passing (100% Pass Rate)  

---

## 1. Observation

### 1.1 Initial Test Failure
Running the baseline test suite prior to changes:
```bash
pytest tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py tests/test_server_database.py -v
```
Resulted in 2 failures out of 147 tests:
```text
FAILED tests/test_server_scheduler_concurrency.py::test_concurrent_assign_work_distinct_problems - AssertionError: Duplicate leases detected! 30 assigned vs 27 unique
FAILED tests/test_server_scheduler_concurrency.py::test_exploration_does_not_duplicate_lease_when_unleased_problems_exist - AssertionError: Exploration created duplicate lease on 'prob_unattempted' even though 5 unleased problems exist in catalog!
======================== 2 failed, 145 passed in 7.04s =========================
```

### 1.2 Root Cause Locations in `src/shape_packing/server/scheduler.py`
1. **Premature Fallback in Exploration Query (lines 123-136)**:
   In `assign_work`:
   ```python
   # 10% Probability exploration stage over unattempted shape configurations
   if random.random() < 0.10:
       # First attempt unleased unattempted candidates
       cursor.execute(...)
       prob = cursor.fetchone()
       if prob is None:
           # Fall back to leased unattempted candidates
           cursor.execute(
               """
               SELECT p.*
               FROM problems p
               WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'
                 AND (p.status = 'unattempted' OR p.total_attempts = 0)
               ORDER BY RANDOM()
               LIMIT 1
               """
           )
           prob = cursor.fetchone()
   ```
   When all unattempted problems were in-flight, this inner fallback immediately re-selected already-leased unattempted problems instead of letting `prob` remain `None` to fall through to the exploitation query.

2. **Parameter Casting and Overflow Vulnerabilities (lines 69-86, 219, 274-284)**:
   - `int(float('inf'))` or `int(float('-inf'))` raised `OverflowError: cannot convert float infinity to integer`, bypassing the `(ValueError, TypeError)` exception handler.
   - Large integer or float values (such as `lease_seconds = 1e308` or `10**20`) bypassed `int` exceptions but subsequently broke `datetime.timedelta(seconds=ls)` with `OverflowError: Python int too large to convert to C int` or `OverflowError: date value out of range`.
   - In `record_heartbeat`, `attempts > 2**63 - 1` raised SQLite parameter binding `OverflowError: Python int too large to convert to SQLite INTEGER`.
   - In `record_heartbeat`, `best_s > 1e308` or huge integer metrics (e.g. `10**400`) raised `OverflowError: int too large to convert to float` when checked via `math.isnan(best_s)`.

---

## 2. Logic Chain

1. **Exploration Fall-Through Fix**:
   - In `assign_work`, the inner fallback query (previously lines 123-136) was deleted.
   - Now, when `random.random() < 0.10` triggers exploration:
     - If an unleased unattempted problem exists, Query 1 selects it.
     - If all unattempted problems are already leased (or none exist), Query 1 returns `None`, and `prob` remains `None`.
     - Execution seamlessly falls through to line 127 (`if prob is None:`), which triggers the 90% exploitation query.
     - The exploitation query selects an unleased candidate from across the catalog using the multi-armed bandit tier ranking.
     - Only if the *entire non-optimal catalog is leased* does execution fall through to shared leasing (lines 161-184).
   - This eliminates premature duplicate leasing and resolves both `test_concurrent_assign_work_distinct_problems` and `test_exploration_does_not_duplicate_lease_when_unleased_problems_exist`.

2. **Cores & Lease Seconds Exception Handling & Clamping**:
   - In `assign_work`, exception handlers for `cores` and `lease_seconds` casting were expanded to catch `(ValueError, TypeError, OverflowError)`.
   - `lease_seconds` is clamped to `[1, 604800]` (7 days maximum) via `min(max(1, ls), MAX_LEASE_SECONDS)` across both branches.
   - This guarantees `datetime.timedelta(seconds=ls)` can never overflow C-level integers or exceed `datetime.MAXYEAR`.

3. **`record_heartbeat` Parameter Bounds**:
   - Added guard `attempts > 2**63 - 1` to reject inputs exceeding signed 64-bit integer capacity, preventing SQLite binding errors.
   - Wrapped `best_s` in `try: f_best_s = float(best_s) except (ValueError, TypeError, OverflowError): return False`.
   - Added guard `f_best_s > 1e308` alongside `math.isnan(f_best_s)`, `math.isinf(f_best_s)`, and `f_best_s <= 0.0`.

4. **Defensive Rowcount in `expire_stale_leases`**:
   - Replaced `return max(0, deleted)` with `return max(0, deleted or 0)` to guarantee safe integer return if `cursor.rowcount` is `None`.

---

## 3. Caveats

- **No Caveats**: The fixes are strictly surgical, contained within `src/shape_packing/server/scheduler.py`, and verified to introduce zero regressions across the entire server database and scheduler test suite.

---

## 4. Conclusion

All reported defects and potential overflow vulnerabilities in `src/shape_packing/server/scheduler.py` have been resolved:
- Exploration now prioritizes unleased catalog problems instead of duplicating in-flight unattempted configurations.
- Cores and lease duration handling are immune to `OverflowError`, `ValueError`, and out-of-range `timedelta` errors.
- Telemetry recording in `record_heartbeat` safely rejects out-of-bound 64-bit integers and float overflow metrics.
- 100% of tests in the full test suite (147 tests) pass cleanly.

---

## 5. Verification Method

To independently reproduce the complete verification:

### 5.1 Full Regression Test Command (147 Tests)
```bash
pytest tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py tests/test_server_database.py -v
```
**Observed Output**:
```text
============================= 147 passed in 7.72s ==============================
```

### 5.2 Direct Overflow Boundary Verification
```bash
PYTHONPATH=src python3 -c "
import sqlite3, math, datetime
from shape_packing.server.database import init_db
from shape_packing.server.scheduler import assign_work, record_heartbeat

conn = init_db(':memory:')
conn.execute('''INSERT INTO problems (id, inner_token, container_token, n, status) VALUES ('p1', 'circle', 'square', 1, 'unattempted')''')
conn.commit()

# 1. Extreme and infinite cores
for c in [float('inf'), float('-inf'), float('nan'), 1e308, -1e308, 10**100, -5, 0, None, True, False]:
    w = assign_work(conn, 'w_test', cores=c)
    assert w is not None
    assert 1000 <= w['recommended_attempts'] <= 20000

# 2. Extreme and infinite lease_seconds
for ls in [float('inf'), float('-inf'), float('nan'), 1e308, -1e308, 10**20, 10**12, -5, 0, None, True, False]:
    w = assign_work(conn, 'w_test', lease_seconds=ls)
    assert w is not None
    assert 1 <= w['lease_seconds'] <= 604800

# 3. Extreme and infinite heartbeat parameters
w = assign_work(conn, 'w_test')
work_id = w['work_id']
for att in [-1, True, False, 10**20, 2**63, 2**64]:
    assert record_heartbeat(conn, work_id, 'w_test', attempts=att) is False

for bs in [float('nan'), float('inf'), float('-inf'), -1.0, 0.0, 10**400, 2**1024, 1e309, 1.5e308, True, False]:
    assert record_heartbeat(conn, work_id, 'w_test', attempts=10, best_s=bs) is False

assert record_heartbeat(conn, work_id, 'w_test', attempts=10, best_s=1e308) is True
assert record_heartbeat(conn, work_id, 'w_test', attempts=2**63 - 1) is True

print('ALL DIRECT OVERFLOW VERIFICATIONS PASSED!')
"
```
**Observed Output**:
```text
ALL DIRECT OVERFLOW VERIFICATIONS PASSED!
```
