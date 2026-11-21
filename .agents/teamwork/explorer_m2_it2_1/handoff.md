# Investigation Report: Scheduler Duplicate Lease Concurrency Bug and Resolution

**Agent**: `explorer_m2_it2_1`  
**Milestone**: Milestone 2: Work Scheduler and Priority Allocator (Iteration 2)  
**Date**: 2026-11-20T23:55:00Z  
**Target File**: `src/shape_packing/server/scheduler.py` (lines 107–140)  
**Status**: Investigation Complete — Root Cause Verified, Resolution Validated  

---

## 1. Observation

### 1.1 Verbatim Code in `src/shape_packing/server/scheduler.py`
In `src/shape_packing/server/scheduler.py` (lines 106–140):
```python
106:         prob = None
107:         # 10% Probability exploration stage over unattempted shape configurations
108:         if random.random() < 0.10:
109:             # First attempt unleased unattempted candidates
110:             cursor.execute(
111:                 """
112:                 SELECT p.*
113:                 FROM problems p
114:                 LEFT JOIN active_leases l ON p.id = l.problem_id
115:                 WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'
116:                   AND (p.status = 'unattempted' OR p.total_attempts = 0)
117:                   AND l.work_id IS NULL
118:                 ORDER BY RANDOM()
119:                 LIMIT 1
120:                 """
121:             )
122:             prob = cursor.fetchone()
123:             if prob is None:
124:                 # Fall back to leased unattempted candidates
125:                 cursor.execute(
126:                     """
127:                     SELECT p.*
128:                     FROM problems p
129:                     WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'
130:                       AND (p.status = 'unattempted' OR p.total_attempts = 0)
131:                     ORDER BY RANDOM()
132:                     LIMIT 1
133:                     """
134:                 )
135:                 prob = cursor.fetchone()
136: 
137:         # 90% Exploitation scoring stage (or fall-through if no unattempted candidates exist)
138:         if prob is None:
139:             # Primary: unleased non-proved_optimal candidates
140:             cursor.execute(
...
```

### 1.2 Test Failure Reproductions
Running `pytest tests/test_server_scheduler_concurrency.py -v`:
```text
tests/test_server_scheduler_concurrency.py::test_concurrent_assign_work_distinct_problems FAILED [ 11%]
tests/test_server_scheduler_concurrency.py::test_exploration_does_not_duplicate_lease_when_unleased_problems_exist FAILED [ 22%]
tests/test_server_scheduler_concurrency.py::test_concurrent_assign_work_exceeding_catalog_shared_leases PASSED [ 33%]
tests/test_server_scheduler_concurrency.py::test_concurrent_heartbeats_during_lease_expiration_race PASSED [ 44%]
tests/test_server_scheduler_concurrency.py::test_wal_mode_concurrent_readers_and_writers PASSED [ 55%]
tests/test_server_scheduler_concurrency.py::test_heavy_mixed_contention_stress PASSED [ 66%]
tests/test_server_scheduler_concurrency.py::test_multiprocess_scheduler_concurrency PASSED [ 77%]
tests/test_server_scheduler_concurrency.py::test_rapid_lease_and_expiration_churn PASSED [ 88%]
tests/test_server_scheduler_concurrency.py::test_complete_state_integrity_and_invariants PASSED [100%]

=================================== FAILURES ===================================
________________ test_concurrent_assign_work_distinct_problems _________________
E       AssertionError: Duplicate leases detected! 30 assigned vs 28 unique
E       assert 28 == 30

____ test_exploration_does_not_duplicate_lease_when_unleased_problems_exist ____
E       AssertionError: Exploration created duplicate lease on 'prob_unattempted' even though 5 unleased problems exist in catalog!
E       assert 'prob_unattempted' != 'prob_unattempted'
```

---

## 2. Logic Chain

### 2.1 The Premature Fallback Mechanism in Exploration
1. When `assign_work` runs, it enters a `BEGIN IMMEDIATE` transaction, serializing write access.
2. At line 108, exploration triggers with 10% probability (`random.random() < 0.10`).
3. Query 1 (lines 110–121) looks for unleased unattempted problems using `LEFT JOIN active_leases l ON p.id = l.problem_id WHERE ... AND l.work_id IS NULL`.
4. If an unattempted problem exists but is *already leased* to another worker (in flight), Query 1 returns `None`.
5. Lines 123–136 (`if prob is None:`) immediately query the `problems` table directly without filtering on `l.work_id IS NULL`.
6. This second query picks the *already-leased* unattempted problem and populates `prob`.
7. Because `prob` is now not `None`, line 138 (`if prob is None:`) evaluates to `False`.
8. The entire exploitation block (lines 138–195)—which is specifically responsible for finding unleased candidates among the rest of the catalog—is completely bypassed.
9. Line 224 inserts a duplicate lease into `active_leases` for this already-leased problem, even though dozens of other unleased problems are waiting in the catalog.

### 2.2 Impact on Work Distribution & Volunteer Compute
- In a realistic scenario with 1 unattempted problem and 29 attempted (unleased) problems:
  - The first worker leases the unattempted problem.
  - Subsequent workers rolling exploration (~10% of requests) trigger lines 123–136, receiving duplicate leases on problem 0.
  - Multiple workers duplicate work on the same problem while other catalog problems starve.
- Deterministic reproduction (`test_exploration_does_not_duplicate_lease_when_unleased_problems_exist`):
  - Catalog has 1 unattempted problem (leased by Worker 1) and 5 attempted problems (all unleased).
  - Worker 2 rolls exploration (mocked `random.random() = 0.05`).
  - Worker 2 receives `prob_unattempted` instead of one of the 5 unleased problems.

### 2.3 Verification of Deleting Lines 123–136
Deleting lines 123–136:
```python
<<<<
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
====
>>>>
```
Trace of the execution flow after deletion:
1. **Exploration rolled (`p < 0.10`) & unleased unattempted problem exists**:
   - Query 1 finds it. `prob` is set. Line 138 (`if prob is None:`) is `False`. The unleased problem is leased. (0 duplicates).
2. **Exploration rolled (`p < 0.10`) & unattempted problem already leased (or none exist)**:
   - Query 1 returns `None`.
   - `prob` remains `None`.
   - Line 138 (`if prob is None:`) evaluates to `True`.
   - The scheduler falls through seamlessly into the 90% exploitation block (lines 138–170).
   - Primary exploitation query (`SELECT p.* FROM problems p LEFT JOIN active_leases l ... WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal' AND l.work_id IS NULL ORDER BY ... LIMIT 1`) searches all unleased eligible catalog problems using the 5-tier bandit priority ranking.
   - An unleased problem is selected. `prob` is set. Line 172 (`if prob is None:`) is `False`. The unleased problem is leased. (0 duplicates).
3. **Entire catalog saturated (every non-proved_optimal problem has an active lease)**:
   - Primary exploitation query returns `None`.
   - Line 172 (`if prob is None:`) evaluates to `True`.
   - Shared leasing query (lines 173–195) runs as the *sole* duplicate leasing fallback, selecting the highest-priority problem across the catalog based on bandit ranking.
4. **Empty catalog or only `proved_optimal` problems**:
   - Shared leasing returns `None`.
   - Line 197 (`if prob is None:`) triggers rollback and returns `None`.

### 2.4 Analysis of Other Potential Duplicate Leasing Branches
We audited every query and branch in `scheduler.py` and `database.py`:
1. **Exploitation primary query (lines 140–169)**:
   - Contains `WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal' AND l.work_id IS NULL`.
   - Because `l.work_id` is a non-null primary key in `active_leases`, `l.work_id IS NULL` matches if and only if `p.id` has 0 active leases.
   - It cannot select an already-leased problem.
2. **Shared leasing query (lines 172–195)**:
   - Strictly nested inside `if prob is None:` under line 138.
   - It executes if and only if the primary query returned `None`.
   - Because the primary query considers *all* non-optimal problems in the catalog without attempt count restrictions, returning `None` mathematically guarantees that 100% of non-optimal catalog problems have active leases.
   - Therefore, shared leasing cannot execute while any unleased problem exists.
3. **Concurrency and Serialization**:
   - Every assignment is wrapped in `BEGIN IMMEDIATE` (line 94).
   - In SQLite WAL mode, `BEGIN IMMEDIATE` serializes write transactions across all threads and processes.
   - Two concurrent workers cannot both observe the same problem as unleased simultaneously.
4. **No other branches exist**:
   - `active_leases` is referenced only in `assign_work`, `expire_stale_leases`, and `record_heartbeat`.
   - No other code path creates leases or bypasses the `l.work_id IS NULL` check.

### 2.5 Test Results After Deletion
Testing against the patched scheduler logic:
- `tests/test_server_scheduler.py`: **70 passed in 1.41s**
- `tests/test_server_scheduler_concurrency.py`: **9 passed in 5.69s** (both previously failing concurrency tests now pass)
- `tests/test_server_scheduler_stress.py`: **39 passed in 0.22s**
- **Total: 118 passed, 0 failures, 0 regressions.**

---

## 3. Caveats

1. **Stochastic Roll Behavior**: When all unattempted problems are leased, workers that roll exploration (`< 0.10`) will fall through to the exploitation bandit scoring. This is the desired behavior according to the project specification (compute is directed to unleased problems rather than idling or duplicating in-flight unattempted problems).
2. **Read-Only Investigation Compliance**: Per the teamwork protocol, this explorer agent did not modify `src/shape_packing/server/scheduler.py` on disk. The fix is ready for `worker_m2` to apply directly.

---

## 4. Conclusion

1. **Root Cause Confirmed**: Lines 123–136 of `src/shape_packing/server/scheduler.py` prematurely query for already-leased unattempted problems when Query 1 returns `None`, bypassing the exploitation stage and causing duplicate leases while unleased catalog problems exist.
2. **Seamless Fall-Through Verified**: Deleting lines 123–136 leaves `prob = None` when all unattempted candidates are leased, allowing clean fall-through to the primary exploitation query (line 138), which successfully leases an unleased problem from the rest of the catalog.
3. **Sole Fallback Preserved**: Shared leasing (lines 172–195) is confirmed to be the sole fallback for duplicate leasing, executing if and only if the entire non-optimal catalog is saturated.
4. **No Other Buggy Branches**: Exhaustive inspection confirms no other branch can create duplicate leases while unleased problems remain.

### Recommended Action for `worker_m2`:
Apply the following diff to `src/shape_packing/server/scheduler.py`:
```diff
--- a/src/shape_packing/server/scheduler.py
+++ b/src/shape_packing/server/scheduler.py
@@ -120,17 +120,6 @@ def assign_work(
                 LIMIT 1
                 """
             )
             prob = cursor.fetchone()
-            if prob is None:
-                # Fall back to leased unattempted candidates
-                cursor.execute(
-                    """
-                    SELECT p.*
-                    FROM problems p
-                    WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'
-                      AND (p.status = 'unattempted' OR p.total_attempts = 0)
-                    ORDER BY RANDOM()
-                    LIMIT 1
-                    """
-                )
-                prob = cursor.fetchone()
 
         # 90% Exploitation scoring stage (or fall-through if no unattempted candidates exist)
         if prob is None:
```

---

## 5. Verification Method

To independently reproduce the bug on current code and verify the fix:

### Step 1: Reproduce on Current Code
```bash
pytest tests/test_server_scheduler_concurrency.py::test_concurrent_assign_work_distinct_problems tests/test_server_scheduler_concurrency.py::test_exploration_does_not_duplicate_lease_when_unleased_problems_exist -v
```
*Expected Result*: Fails with `AssertionError: Duplicate leases detected!` and `AssertionError: Exploration created duplicate lease on 'prob_unattempted'`.

### Step 2: Verify All 118 Tests Pass with Fix
```bash
PYTHONPATH=src python3 -c "
with open('src/shape_packing/server/scheduler.py') as f:
    code = f.read()
target = '''            if prob is None:
                # Fall back to leased unattempted candidates
                cursor.execute(
                    \"\"\"
                    SELECT p.*
                    FROM problems p
                    WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'
                      AND (p.status = 'unattempted' OR p.total_attempts = 0)
                    ORDER BY RANDOM()
                    LIMIT 1
                    \"\"\"
                )
                prob = cursor.fetchone()'''
assert target in code, 'Target string not found'
patched = code.replace(target, '')
import types, sys, pytest, shape_packing.server.scheduler as s
m = types.ModuleType('temp')
exec(patched, m.__dict__)
s.assign_work = m.assign_work
res = pytest.main([
    'tests/test_server_scheduler.py',
    'tests/test_server_scheduler_concurrency.py',
    'tests/test_server_scheduler_stress.py',
    '-v'
])
assert res == 0
print('ALL 118 SCHEDULER TESTS PASSED')
"
```
*Expected Result*: All 118 tests across `test_server_scheduler.py`, `test_server_scheduler_concurrency.py`, and `test_server_scheduler_stress.py` pass with code 0.
