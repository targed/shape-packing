# Specification Mining Report & Regression Test Suite Definition: Milestone 2 Iteration 2

**Author**: `spec_miner_m2_it2_1`  
**Date**: 2026-11-20T23:55:00Z  
**Target Workspace**: `/home/targed/Documents/Git/shape-packing`  
**Recipient**: `parent` (`86ab9594-ed5d-48cc-9be1-f2844355b5e4`)  
**Scope**: Work Scheduler & Priority Allocator (`src/shape_packing/server/scheduler.py`), Database Layer (`src/shape_packing/server/database.py`), and authoritative test suites (`tests/test_server_scheduler.py`, `tests/test_server_scheduler_stress.py`, `tests/test_server_scheduler_concurrency.py`, `tests/test_server_database.py`).

---

## 1. Observation

### 1.1 Test Suite Inventory & Current Execution Status
Running the authoritative pytest test collection:
- `tests/test_server_scheduler.py`: 70 tests collected.
- `tests/test_server_scheduler_stress.py`: 39 tests collected.
- `tests/test_server_scheduler_concurrency.py`: 9 tests collected.
- Total Scheduler Suites: **118 tests**.
- Additional Foundation Suite: `tests/test_server_database.py` (**29 tests**).
- Grand Total: **147 tests**.

Execution result of running all 118 scheduler tests:
```bash
pytest tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py
```
Output:
```
============================= test session starts ==============================
platform linux -- Python 3.14.10, pytest-9.2.0, pluggy-1.7.0
rootdir: /home/targed/Documents/Git/shape-packing
configfile: pyproject.toml
plugins: platformdirs-4.14.3
collected 118 items

tests/test_server_scheduler.py ......................................... [ 34%]
.............................                                            [ 59%]
tests/test_server_scheduler_stress.py .................................. [ 88%]
.....                                                                    [ 92%]
tests/test_server_scheduler_concurrency.py .F.......                     [100%]

=================================== FAILURES ===================================
____ test_exploration_does_not_duplicate_lease_when_unleased_problems_exist ____

conn = <sqlite3.Connection object at 0x7fdf8bdb6890>

    def test_exploration_does_not_duplicate_lease_when_unleased_problems_exist(conn: sqlite3.Connection):
...
>       assert w2["problem"] != "prob_unattempted", (
            "Exploration created duplicate lease on 'prob_unattempted' even though 5 unleased problems exist in catalog!"
        )
E       AssertionError: Exploration created duplicate lease on 'prob_unattempted' even though 5 unleased problems exist in catalog!
E       assert 'prob_unattempted' != 'prob_unattempted'

tests/test_server_scheduler_concurrency.py:160: AssertionError
======================== 1 failed, 117 passed in 7.32s =========================
```

Execution result of running the database test suite:
```bash
pytest tests/test_server_database.py
```
Output:
```
============================== 29 passed in 0.06s ==============================
```

### 1.2 Inspection of Source Code in `src/shape_packing/server/scheduler.py`
In `assign_work` (lines 107–136):
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
And lines 138–196:
```python
        # 90% Exploitation scoring stage (or fall-through if no unattempted candidates exist)
        if prob is None:
            # Primary: unleased non-proved_optimal candidates
            cursor.execute(
                """
                SELECT p.*
                FROM problems p
                LEFT JOIN active_leases l ON p.id = l.problem_id
                WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'
                  AND l.work_id IS NULL
                ORDER BY ...
```

---

## 2. Logic Chain

1. **Test Intent**:
   Challenger `challenger_m2_2` authored `tests/test_server_scheduler_concurrency.py` to stress scheduler concurrency and allocation invariants.
   Specifically, `test_exploration_does_not_duplicate_lease_when_unleased_problems_exist` verifies that when an unattempted problem is already leased by another worker, and 5 unleased candidates remain in the catalog, a new worker requesting work under exploration mode (`random.random() < 0.10`) must **not** duplicate the lease on the already-leased unattempted problem. Instead, the scheduler must fall through to exploitation to pick one of the available unleased candidates.
2. **Failure Analysis**:
   When `assign_work` executes exploration (lines 108–136):
   - The primary exploration query looks for an unattempted problem with `l.work_id IS NULL`. When `prob_unattempted` is already leased, this query returns `None`.
   - However, the code immediately falls back to querying `problems` *without* filtering out active leases (`l.work_id IS NULL`), immediately selecting the already-leased `prob_unattempted`.
   - Consequently, `prob` is assigned `prob_unattempted`, bypassing the 5 unleased problems in the catalog and creating a duplicate lease prematurely.
3. **Correct Behavior Required**:
   - If no *unleased* unattempted candidates exist, exploration should simply yield `prob = None`.
   - Execution then falls through to line 138 (`if prob is None:`), which queries unleased candidates across the rest of the catalog (`l.work_id IS NULL`).
   - Only when **all** eligible candidates across the entire catalog are leased does the scheduler fall back to shared leasing (lines 172–195).
4. **Impact of Fix**:
   Removing lines 123–135 in `scheduler.py` allows exploration to seamlessly fall through to unleased candidates in the catalog. All 118 scheduler tests and 29 database tests will pass cleanly.

---

## 3. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Allocation | `assign_work` Schema Compliance | Returns 8-key work dictionary | `conn`, `worker_id`, `cores`, `lease_seconds` | Dict with keys: `work_id`, `problem`, `inner_token`, `container_token`, `n`, `target_s`, `recommended_attempts`, `lease_seconds` | Returns `None` on invalid worker or empty catalog | `test_server_scheduler.py:133` |
| 2 | Allocation | Core Attempt Scaling | Scales batch attempts by hardware cores: `max(1000, min(cores * 1000, 20000))` | `cores: int` (1, 4, 8, 20, 64) | `recommended_attempts: int` in [1000, 20000] | Clamps negative/zero/corrupt/float to 1000 | `test_server_scheduler.py:172` |
| 3 | Allocation | Target Metric Fallback | Hierarchical metric selection: `best_s -> reference_s -> 10.0` | Problem records in DB | `target_s: float` | Defaults to `10.0` if metrics are null | `test_server_scheduler.py:200` |
| 4 | Policy | Proved Optimal Exclusion | Strict exclusion of problems marked `proved_optimal` (case-insensitive) | Catalog with mixed statuses | Work unit of non-optimal problem, or `None` if only proved_optimal | Returns `None` when catalog contains only proved_optimal | `test_server_scheduler.py:249`, `test_server_scheduler_stress.py:82` |
| 5 | Policy | Tier 1: Stuck Backoff | Deprioritizes problems with >50k attempts and `updated_at < now - 1 day` | `total_attempts > 50000`, `updated_at` | Problem placed in Tier 1 penalty category (CASE = 1) | Solution update resets `updated_at`, clearing stuck status | `test_server_scheduler.py:369`, `test_server_scheduler_stress.py:250` |
| 6 | Policy | Tier 2: Closeness Boost | Prioritizes problems within 1% of reference record (`abs(best_s - ref_s)/ref_s <= 0.01`) | `best_s`, `reference_s` | Problem placed in boosted Tier 2 category (CASE = 0) | Overridden by Tier 1 stuck backoff | `test_server_scheduler.py:342`, `test_server_scheduler_stress.py:281` |
| 7 | Policy | Tier 3 & 4: Balancing & Void Space | Fair attempt balancing (`total_attempts ASC`), void space priority (`density_rank DESC`) | Problem metadata | Prioritized problem selection | Tie broken by `RANDOM()` | `test_server_scheduler.py:320`, `test_server_scheduler.py:331` |
| 8 | Allocation | Exploration vs Exploitation | 10% chance to target unattempted problems (`status = 'unattempted' OR total_attempts = 0`) | `random.random() < 0.10` | Unleased unattempted problem, or falls through to unleased exploitation | Must NOT create duplicate lease if unleased problems exist | `test_server_scheduler.py:443`, `test_server_scheduler_concurrency.py:137` |
| 9 | Allocation | Fallback Shared Leasing | If ALL eligible problems are leased, stochastically leases active problems | All problems actively leased | Active problem leased shared across multiple workers | Excludes proved_optimal instances even during shared fallback | `test_server_scheduler.py:298`, `test_server_scheduler_stress.py:110` |
| 10 | Allocation | Worker Auto-Registration | Automatically creates worker record with `client_type='native'` if unknown | Unregistered `worker_id` | Worker row upserted into `workers` | Preserves existing worker username | `test_server_scheduler.py:708`, `test_server_scheduler.py:724` |
| 11 | Lifecycle | Lease Expiration Management | Deletes expired leases (`expires_at <= CURRENT_TIMESTAMP`) | Active leases in SQLite | Count of pruned stale leases | Safe on empty table; live leases preserved | `test_server_scheduler.py:472`, `test_server_scheduler.py:495` |
| 12 | Lifecycle | Auto-Expiry in `assign_work` | Purges stale leases automatically before evaluating problem availability | Expired lease in DB | Reclaims problem as unleased | Prunes stale rows atomically | `test_server_scheduler.py:521` |
| 13 | Accounting | Heartbeat Attempt Accounting | Increments `problem.total_attempts` and `worker.total_attempts` | `work_id`, `worker_id`, `attempts: int` | Returns `True` if active lease; `False` if expired/unknown | Rejects negative/bool/float/string attempts | `test_server_scheduler.py:552`, `test_server_scheduler.py:737` |
| 14 | Accounting | Worker Liveness Tracking | Updates worker `last_seen_at` timestamp on heartbeat | Heartbeat call | `workers.last_seen_at` refreshed | Non-existent work credits worker liveness only | `test_server_scheduler.py:573` |
| 15 | Accounting | Zero-Attempt Liveness Keepalive | Accepts `attempts=0` as heartbeat keepalive without altering attempt counters | `attempts=0` | Returns `True`, updates `last_seen_at` | Attempt totals remain unchanged | `test_server_scheduler.py:611` |
| 16 | Accounting | Expired/Unknown Lease Handling | If lease expired or work_id unknown, credits worker compute only and returns `False` | Expired `work_id` | Returns `False`, increments worker attempts only | Problem attempts NOT incremented | `test_server_scheduler.py:630`, `test_server_scheduler.py:659` |
| 17 | Accounting | Telemetry Boundary Invariant | Heartbeat telemetry NEVER updates `problems.best_s` | `best_s: float` passed to heartbeat | Returns `True` | `problems.best_s` strictly unmodified | `test_server_scheduler.py:672` |
| 18 | Security | Cross-Worker Lease Rejection | Rejects heartbeat on lease owned by another worker | Worker B sends heartbeat on Worker A's `work_id` | Returns `False` | Problem total attempts uncredited | `test_server_scheduler_stress.py:398` |
| 19 | Concurrency | `BEGIN IMMEDIATE` Serialization | Prevents duplicate leases on unleased problems under multi-threaded contention | Concurrent threads calling `assign_work` | Distinct problem per worker | No deadlocks, no duplicate leases | `test_server_scheduler.py:792`, `test_server_scheduler_concurrency.py:83` |
| 20 | Concurrency | Concurrent Heartbeats Without Lost Updates | Concurrent heartbeats on same problem/worker accumulate without loss | Concurrent threads calling `record_heartbeat` | Cumulative attempts match sum of all calls | No database lock errors | `test_server_scheduler.py:830`, `test_server_scheduler_concurrency.py:226` |
| 21 | Concurrency | SQLite WAL Reader/Writer Concurrency | Readers and writers execute concurrently without blocking | 6 readers, 4 writers under WAL mode | High throughput, snapshot isolation | 0 lock escalation or busy errors | `test_server_scheduler_concurrency.py:330` |
| 22 | Concurrency | Multi-Process OS Concurrency | Independent OS processes access shared DB via WAL mode | Separate `multiprocessing.Process` workers | Work assigned, heartbeats recorded | Clean IPC locking | `test_server_scheduler_concurrency.py:525` |
| 23 | Concurrency | Rapid Lease Churn & State Integrity | 50 churn cycles leave 0 orphan leases; PRAGMA integrity and FK checks pass | Rapid assign/expire cycles | 0 orphan leases, valid relational integrity | `PRAGMA integrity_check == 'ok'` | `test_server_scheduler_concurrency.py:569`, `test_server_scheduler_concurrency.py:600` |

---

## 4. Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | `assign_work` | `worker_id` in `[None, "", "   ", "\t\r\n", 12345, True, False, [], {}]` | Safely returns `None` without DB error. |
| 2 | `assign_work` | `worker_id="worker'; DROP TABLE problems; --"` | SQL injection prevented; table intact; worker registered safely. |
| 3 | `assign_work` | `worker_id="🤖_worker_42_🚀"` | Unicode / emoji strings handled cleanly. |
| 4 | `assign_work` | `cores` in `[-1, -1000000, 0, None, True, False, "not_a_number", [], {}]` | Normalized to 1 core -> `recommended_attempts = 1000`. |
| 5 | `assign_work` | `cores` in `[20, 100, 999999999]` | Clamped to ceiling -> `recommended_attempts = 20000`. |
| 6 | `assign_work` | `cores=float("nan")`, `lease_seconds=float("nan")` | Handled via exception fallback to defaults (1000 attempts, 300s lease). |
| 7 | `assign_work` | Empty catalog or only `proved_optimal` problems in catalog | Safely returns `None` across repeated attempts. |
| 8 | `assign_work` | All catalog problems unattempted and already leased, unleased attempted problems exist | **BUG DETECTED**: Currently duplicates leased unattempted problem instead of falling through to unleased attempted candidates. |
| 9 | `assign_work` | Only 1 problem in catalog, 10 concurrent workers request leases | All 10 workers receive valid shared leases on the single problem. |
| 10 | `record_heartbeat` | `attempts` in `[-1, -100, True, False, "100", 12.5, None, [10]]` | Rejected immediately with `False`. |
| 11 | `record_heartbeat` | `work_id` or `worker_id` in `[None, "", "   ", 123, []]` | Rejected immediately with `False`. |
| 12 | `record_heartbeat` | `best_s` in `[-1.0, 0.0, float("nan"), float("inf"), True, "1.5"]` | Rejected immediately with `False`. |
| 13 | `record_heartbeat` | `attempts = 10**9` (1 billion) | Correctly increments attempts without 64-bit integer overflow. |
| 14 | `record_heartbeat` | Heartbeat sent after lease expiration | Returns `False`; worker credited; problem uncredited. |
| 15 | `expire_stale_leases` | Database connection is `None` or invalid type | Safely returns `0` without throwing uncaught exceptions. |
| 16 | `assign_work` | Stale lease exists for only candidate problem | Automatically purges stale lease and reclaims candidate as unleased. |

---

## 5. Precise Regression Test Suite and Verification Commands

Worker M2 it2 must execute and pass the following regression suites:

### 5.1 Primary Milestone 2 Scheduler Concurrency & Unit Suites (118 Tests)
```bash
pytest -v tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py
```
Breakdown:
1. `tests/test_server_scheduler.py` (70 tests)
   - Interface schema compliance
   - Hardware attempt scaling bounds (1 to 128 cores)
   - Target metric fallback hierarchy
   - Proved optimal exclusion
   - Multi-armed bandit tier ranking (stuck backoff, closeness boost, attempts, density rank)
   - Exploration branch handling
   - Stale lease expiration and auto-purging
   - Heartbeat telemetry and cumulative accounting
   - Defensive input validation (invalid types, booleans, whitespace, corrupt best_s)
   - Concurrency serialization with `BEGIN IMMEDIATE`
2. `tests/test_server_scheduler_stress.py` (39 tests)
   - Adversarial proved optimal extraction prevention (1,000 iterations)
   - Corrupt & extreme core normalization
   - SQL injection & Unicode worker IDs
   - Catalog boundary conditions
   - Stuck backoff & closeness boost boundary cases
   - Fallback shared leasing invariants
   - Large attempt count handling ($10^9$)
   - Cross-worker heartbeat rejection
3. `tests/test_server_scheduler_concurrency.py` (9 tests)
   - `test_concurrent_assign_work_distinct_problems` (30 threads, 30 distinct problems)
   - `test_exploration_does_not_duplicate_lease_when_unleased_problems_exist` (**TARGET FIX**)
   - `test_concurrent_assign_work_exceeding_catalog_shared_leases` (30 threads, 10 problems)
   - `test_concurrent_heartbeats_during_lease_expiration_race` (10 threads, race condition accounting)
   - `test_wal_mode_concurrent_readers_and_writers` (6 readers, 4 writers, zero blocking)
   - `test_heavy_mixed_contention_stress` (20 threads, 500 mixed operations, zero deadlocks)
   - `test_multiprocess_scheduler_concurrency` (4 separate OS processes)
   - `test_rapid_lease_and_expiration_churn` (50 rapid churn cycles, 0 leaks)
   - `test_complete_state_integrity_and_invariants` (PRAGMA integrity and FK checks)

### 5.2 Full Foundation Regression Command (147 Tests)
To guarantee zero regression across the database layer as well:
```bash
pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py
```
Success Criteria:
- `147 passed in ~7.5s`
- Exit code: `0`

---

## 6. Caveats
- No code was modified in `src/shape_packing/server/scheduler.py` during this investigation, as this role is strictly read-only specification mining.
- The identified fix (removing lines 123–135 in `src/shape_packing/server/scheduler.py`) has been verified via code review and query tracing against all test scenarios, but must be applied and tested by Worker M2 it2.

---

## 7. Conclusion
1. The specification across `tests/test_server_scheduler.py` (70 tests), `tests/test_server_scheduler_stress.py` (39 tests), and `tests/test_server_scheduler_concurrency.py` (9 tests) defines a robust multi-armed bandit scheduler under SQLite WAL mode.
2. Currently, **117 out of 118** scheduler tests pass. Exactly 1 test fails: `tests/test_server_scheduler_concurrency.py::test_exploration_does_not_duplicate_lease_when_unleased_problems_exist`.
3. The root cause is lines 123–135 in `src/shape_packing/server/scheduler.py`, which immediately fall back to already-leased unattempted problems during exploration instead of falling through to unleased exploitation candidates.
4. Once Worker M2 it2 removes this inner fallback, all 118 scheduler tests and 29 database tests (147 total tests) will pass with 0 failures.

---

## 8. Verification Method

To verify these findings:
```bash
# 1. Reproduce the single failing test:
pytest tests/test_server_scheduler_concurrency.py -k test_exploration_does_not_duplicate_lease_when_unleased_problems_exist

# 2. Run all other 117 scheduler tests to confirm they are passing:
pytest tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py -k "not test_exploration_does_not_duplicate_lease_when_unleased_problems_exist"

# 3. Verify database suite passes:
pytest tests/test_server_database.py

# 4. Verify post-fix behavior once Worker M2 it2 applies the change:
pytest tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py tests/test_server_database.py
```
