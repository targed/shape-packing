# Challenger 2 Report — Milestone 2: Work Scheduler and Priority Allocator

**Agent**: `challenger_m2_2`  
**Milestone**: Milestone 2: Work Scheduler and Priority Allocator  
**Date**: 2026-11-20T23:50:00Z  
**Verdict**: **REQUEST_CHANGES**

---

## 1. Observation

### 1.1 Baseline Scheduler Test Suite
Running `pytest tests/test_server_scheduler.py -v`:
```text
============================= test session starts ==============================
platform linux -- Python 3.14.10, pytest-9.2.0, pluggy-1.7.0 -- /usr/bin/python
collected 70 items

tests/test_server_scheduler.py::test_assign_work_schema_compliance PASSED [  1%]
...
tests/test_server_scheduler.py::test_concurrent_work_assignment_no_duplicates PASSED [ 97%]
tests/test_server_scheduler.py::test_concurrent_heartbeats_no_lost_updates PASSED [ 98%]
tests/test_server_scheduler.py::test_concurrent_expire_and_assign PASSED [100%]
============================== 70 passed in 1.35s ==============================
```

### 1.2 Empirical Concurrency & Stress Challenge Suite
Created `tests/test_server_scheduler_concurrency.py` with 9 empirical stress tests:
1. `test_concurrent_assign_work_distinct_problems`: 30 concurrent threads requesting work on 30 catalog problems (1 unattempted, 29 attempted).
2. `test_exploration_does_not_duplicate_lease_when_unleased_problems_exist`: Deterministic unit reproducer of the exploration fallback bug.
3. `test_concurrent_assign_work_exceeding_catalog_shared_leases`: 30 concurrent threads requesting work on 10 catalog problems (verifying graceful shared fallback when catalog is saturated).
4. `test_concurrent_heartbeats_during_lease_expiration_race`: Race condition where active lease expires while 10 concurrent threads submit heartbeats.
5. `test_wal_mode_concurrent_readers_and_writers`: 6 reader threads and 4 writer threads running sustained queries under SQLite WAL mode.
6. `test_heavy_mixed_contention_stress`: 20 concurrent threads running randomized operations across `assign_work`, `record_heartbeat`, `expire_stale_leases`, `update_solution_record`, and `register_worker`.
7. `test_multiprocess_scheduler_concurrency`: 4 native OS processes (`multiprocessing.Process`) verifying cross-process WAL mode locking.
8. `test_rapid_lease_and_expiration_churn`: 50 rapid lease creation and expiration cycles.
9. `test_complete_state_integrity_and_invariants`: Database integrity check, foreign key checks, and attempt non-negativity invariant.

Running `pytest tests/test_server_scheduler_concurrency.py -v`:
```text
============================= test session starts ==============================
platform linux -- Python 3.14.10, pytest-9.2.0, pluggy-1.7.0 -- /usr/bin/python
collected 9 items

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
>       assert len(set(assigned_problems)) == num_threads, (
            f"Duplicate leases detected! {len(assigned_problems)} assigned vs {len(set(assigned_problems))} unique"
        )
E       AssertionError: Duplicate leases detected! 30 assigned vs 25 unique
E       assert 25 == 30
E        +  where 25 = len({'prob_000', 'prob_001', 'prob_002', 'prob_003', 'prob_004', 'prob_005', ...})

____ test_exploration_does_not_duplicate_lease_when_unleased_problems_exist ____
>       assert w2["problem"] != "prob_unattempted", (
            "Exploration created duplicate lease on 'prob_unattempted' even though 5 unleased problems exist in catalog!"
        )
E       AssertionError: Exploration created duplicate lease on 'prob_unattempted' even though 5 unleased problems exist in catalog!
E       assert 'prob_unattempted' != 'prob_unattempted'
========================= 2 failed, 7 passed in 6.08s ==========================
```

### 1.3 Exact Code Location of Root Cause
In `src/shape_packing/server/scheduler.py`, lines 107–136:
```python
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

---

## 2. Logic Chain

1. **Premature Fallback in Exploration Stage**:
   - In `scheduler.py` lines 108–136, when `random.random() < 0.10` triggers the exploration branch, the scheduler queries for unleased unattempted candidates (`l.work_id IS NULL`).
   - If all unattempted candidates are currently in flight (or if only 1 unattempted problem exists and is already leased), `prob` is initially `None`.
   - Instead of falling through to the exploitation stage (`if prob is None:` at line 138) to lease an unleased candidate, lines 123–136 immediately query for *already-leased* unattempted candidates:
     `SELECT p.* FROM problems p WHERE ... (p.status = 'unattempted' OR p.total_attempts = 0) ORDER BY RANDOM() LIMIT 1`.
   - As a direct result, the scheduler leases the *same* in-flight problem again, creating duplicate leases.

2. **Violation of Dispatch Challenge 1 and Architectural Invariants**:
   - Dispatch Requirement 1: *"Multi-threaded concurrent assign_work calls (verify no duplicate leases on distinct problems, verify clean serialization via BEGIN IMMEDIATE)."*
   - `PROJECT.md` & `worker_m2/handoff.md`:
     > "Stochastic Search Sharing Fallback: If all eligible non-optimal candidates are currently leased, assign_work falls back to shared leasing following bandit scoring, preventing volunteer idle starvation."
   - Shared leasing (duplicate leasing) is strictly a fallback when the *entire eligible catalog* is saturated. It must NEVER occur when unleased problems remain in the catalog.
   - In `test_concurrent_assign_work_distinct_problems`, 30 concurrent workers requested work on 30 problems. `prob_000` was assigned 6 times, while 5 catalog problems were completely starved of compute despite 30 workers being available.

3. **Why `test_concurrent_work_assignment_no_duplicates` in `worker_m2` Did Not Catch This**:
   - In `worker_m2`'s test (lines 792–798 of `tests/test_server_scheduler.py`), all 10 problems were inserted with `total_attempts = 0`.
   - Because all 10 problems were unattempted, each exploration roll picked one of the remaining unleased unattempted problems.
   - When a realistic mix exists (e.g., 1 unattempted problem and 29 attempted problems), any worker rolling exploration after problem 0 is leased immediately hits lines 123–136 and duplicates problem 0.

4. **Verification of the Surgical Fix**:
   - The required fix is simply to delete lines 123–136 from `src/shape_packing/server/scheduler.py`:
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
   - When lines 123–136 are removed:
     1. If an unleased unattempted problem exists, exploration selects it.
     2. If all unattempted problems are in flight, `prob` remains `None`, seamlessly falling through to the exploitation stage (`if prob is None:` at line 138), which selects an unleased candidate.
     3. If and only if *all* eligible catalog problems are leased, lines 172–195 execute shared leasing.
   - When tested against the patched logic:
     - `tests/test_server_scheduler.py`: **70 passed in 1.32s**.
     - `tests/test_server_scheduler_concurrency.py`: **9 passed in 6.78s** (all 9 pass, 0 failures).

5. **Concurrency, Deadlock Freedom, and State Integrity Verified**:
   - Concurrency tests 3–9 in `test_server_scheduler_concurrency.py` demonstrated:
     - Zero deadlocks under heavy mixed contention (20 threads, 500 operations).
     - Clean reader/writer isolation under SQLite WAL mode (6 readers and 4 writers with 0 lock errors).
     - Multi-process concurrency safety across separate OS processes (`multiprocessing.Process`).
     - Perfect attempt accounting and status reporting during lease expiration races (`problems.total_attempts <= workers.total_attempts`).
     - `PRAGMA integrity_check` returned `"ok"`.
     - `PRAGMA foreign_key_check` returned 0 violations.

---

## 3. Caveats

- **No Caveats**: The bug was deterministically reproduced in both multi-threaded and single-threaded environments. The fix is minimal and has been tested to not break any existing tests.
- **Review-Only Constraint Honored**: In accordance with the Challenger protocol ("Review-only — do NOT modify implementation code"), `src/shape_packing/server/scheduler.py` was NOT modified by Challenger 2. The fix is handed back to `worker_m2` to apply.

---

## 4. Conclusion

The scheduler implementation is structurally sound, deadlock-free, and handles SQLite WAL mode and lease expiration races cleanly. However, it contains a critical bug in `assign_work` (lines 123–136 of `src/shape_packing/server/scheduler.py`) where exploration prematurely duplicates leases on in-flight unattempted configurations while unleased catalog problems are available.

**Verdict**: **REQUEST_CHANGES**

**Action Required from `worker_m2`**:
1. Remove lines 123–136 of `src/shape_packing/server/scheduler.py`.
2. Run `pytest tests/test_server_scheduler.py tests/test_server_scheduler_concurrency.py -v` to confirm all 79 tests pass.

---

## 5. Verification Method

To reproduce the bug and verify the fix:

1. **Reproduce Failure on Current Codebase**:
   ```bash
   pytest tests/test_server_scheduler_concurrency.py::test_exploration_does_not_duplicate_lease_when_unleased_problems_exist tests/test_server_scheduler_concurrency.py::test_concurrent_assign_work_distinct_problems -v
   ```
   *Result*: Fails with `AssertionError: Exploration created duplicate lease on 'prob_unattempted' even though 5 unleased problems exist in catalog!`

2. **Verify That Removing Lines 123–136 Passes All 79 Tests**:
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
   patched = code.replace(target, '')
   import types, sys, pytest, shape_packing.server.scheduler as s
   m = types.ModuleType('temp')
   exec(patched, m.__dict__)
   s.assign_work = m.assign_work
   res = pytest.main(['tests/test_server_scheduler.py', 'tests/test_server_scheduler_concurrency.py', '-v'])
   assert res == 0
   print('ALL 79 TESTS PASSED')
   "
   ```
