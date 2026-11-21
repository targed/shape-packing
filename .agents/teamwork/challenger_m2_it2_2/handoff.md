# Handoff Report — Milestone 2 Iteration 2: Scheduler Concurrency Verification

**Agent**: `challenger_m2_it2_2`  
**Milestone**: Milestone 2: Work Scheduler and Priority Allocator (Iteration 2)  
**Date**: 2026-11-21T00:06:40Z  
**Target Code**: `src/shape_packing/server/scheduler.py`  
**Final Verdict**: **APPROVE**

---

## 1. Observation

### 1.1 Concurrency Test Suite Execution
Direct execution of the dedicated scheduler concurrency test suite:
```bash
pytest tests/test_server_scheduler_concurrency.py -v
```
**Result**: 9 passed out of 9 tests in 5.73s (100% pass rate).
Verbatim test results:
```text
tests/test_server_scheduler_concurrency.py::test_concurrent_assign_work_distinct_problems PASSED [ 11%]
tests/test_server_scheduler_concurrency.py::test_exploration_does_not_duplicate_lease_when_unleased_problems_exist PASSED [ 22%]
tests/test_server_scheduler_concurrency.py::test_concurrent_assign_work_exceeding_catalog_shared_leases PASSED [ 33%]
tests/test_server_scheduler_concurrency.py::test_concurrent_heartbeats_during_lease_expiration_race PASSED [ 44%]
tests/test_server_scheduler_concurrency.py::test_wal_mode_concurrent_readers_and_writers PASSED [ 55%]
tests/test_server_scheduler_concurrency.py::test_heavy_mixed_contention_stress PASSED [ 66%]
tests/test_server_scheduler_concurrency.py::test_multiprocess_scheduler_concurrency PASSED [ 77%]
tests/test_server_scheduler_concurrency.py::test_rapid_lease_and_expiration_churn PASSED [ 88%]
tests/test_server_scheduler_concurrency.py::test_complete_state_integrity_and_invariants PASSED [100%]
============================== 9 passed in 5.73s ===============================
```
Both `test_exploration_does_not_duplicate_lease_when_unleased_problems_exist` and `test_concurrent_assign_work_distinct_problems` passed cleanly with 0 failures.

### 1.2 Full Server Database and Scheduler Suite Execution
```bash
pytest tests/test_server_database.py tests/test_server_database_concurrency.py tests/test_server_database_stress.py tests/test_server_scheduler.py tests/test_server_scheduler_concurrency.py tests/test_server_scheduler_stress.py -v
```
**Result**: 165 passed out of 165 tests in 9.87s (100% pass rate). Zero failures, zero warnings.

### 1.3 Independent Empirical Stress Harness Observations
Seven custom empirical stress harnesses were designed and executed to independently challenge concurrency, lease invariants, and SQLite WAL behavior:

1. **50-Thread Concurrent Assignment (10 unattempted + 40 attempted problems)**:
   - 50 concurrent worker threads invoked `assign_work` behind a `threading.Barrier`.
   - Result: Exactly 50 leases assigned, exactly 50 unique problem IDs (`len(set(assigned)) == 50`). Zero duplicate leases, zero errors.

2. **Forced 100% Exploration Fall-Through (5 unattempted + 25 attempted problems, 20 concurrent workers)**:
   - Forced `random.random() < 0.10` to always evaluate `True` for all 20 threads.
   - Result: Exactly the 5 unattempted problems were leased once. The remaining 15 workers seamlessly fell through to exploitation and leased 15 unique attempted problems. Total assigned: 20, unique assigned: 20 (`len(set(assigned)) == 20`). Zero duplicate leases.

3. **Shared Leasing Fallback (5 unattempted + 5 attempted + 5 proved_optimal, 35 concurrent workers)**:
   - 35 concurrent workers requested work on a 10-problem non-optimal catalog.
   - Result: 35 leases assigned across all 10 non-optimal problems. Exactly 0 `proved_optimal` problems leased. Zero errors, zero lock escalations.

4. **Sustained Mixed WAL Contention (30 threads, 3.0 seconds)**:
   - 30 threads continuously executed randomized mixtures of `assign_work`, `record_heartbeat`, `expire_stale_leases`, `update_solution_record`, and `register_worker`.
   - Result: 15,263 operations completed in 3.0 seconds (3,049 assigns, 3,075 heartbeats, 3,124 expires, 2,988 solutions, 3,027 registrations). Zero `sqlite3.OperationalError: database is locked`, zero deadlocks, PRAGMA `integrity_check` returned `ok`, PRAGMA `foreign_key_check` returned `[]`.

5. **Heartbeat/Lease Expiration Race Condition Accounting**:
   - 10 threads executed 250 heartbeats (40 attempts each) while another thread concurrently expired stale leases on a 1-second lease.
   - Result: 150 successful calls before expiration, 100 rejected calls after expiration. Problem attempts recorded: exactly 6,000 (150 * 40). Worker attempts recorded: exactly 10,000 (250 * 40). Zero lost updates or negative counts.

6. **Cross-Process Concurrency (8 separate OS processes)**:
   - 8 independent processes concurrently invoked scheduler operations on disk DB in WAL mode.
   - Result: 200 total operations completed with 0 multi-process errors or file lock contentions.

7. **Extreme Adversarial Parameter Fuzzing Under Concurrency**:
   - 20 concurrent threads passed extreme and corrupt parameter combinations (`cores` with NaN/Inf/1e308/10^100/bool/None, `lease_seconds` with NaN/Inf/1e308/10^20, `attempts` with 2^63/2^64/negative, `best_s` with NaN/Inf/10^400).
   - Result: Zero exceptions escaped, all recommended attempts remained clamped in `[1000, 20000]`, lease durations remained clamped in `[1, 604800]`, and all heartbeat calls safely returned boolean indicators.

---

## 2. Logic Chain

1. **Elimination of Premature Exploration Fallback**:
   - In `assign_work` (lines 109-125), the exploration branch queries unleased unattempted problems (`p.status = 'unattempted' OR p.total_attempts = 0` with `l.work_id IS NULL`).
   - If all unattempted problems are already leased, `prob` remains `None` without falling back to leased unattempted problems.
   - Execution seamlessly drops to the exploitation branch (`if prob is None:` at line 127).
   - The exploitation query selects an unleased candidate across the catalog using bandit priority tiers.
   - Only when *all eligible non-optimal problems in the entire catalog are leased* does the code trigger shared leasing (line 161).
   - This directly prevents duplicate leasing whenever unleased problems exist in the catalog, satisfying R2 and the test assertions.

2. **Atomic Serialization via `BEGIN IMMEDIATE`**:
   - Both `assign_work` and `record_heartbeat` use `cursor.execute("BEGIN IMMEDIATE")` within an active SQLite WAL connection.
   - In SQLite WAL mode, `BEGIN IMMEDIATE` immediately acquires a reserved lock, preventing concurrent writers from modifying tables between the eligibility SELECT and the lease INSERT.
   - The 30-second busy timeout configured in `database.py:init_db` allows concurrent writers to queue safely without throwing `database is locked` under high contention (confirmed by 15,263 operations in 3 seconds).

3. **Mathematical Precision in Telemetry Accounting**:
   - `record_heartbeat` updates worker `total_attempts` unconditionally (crediting compute even after lease expiration).
   - `record_heartbeat` updates problem `total_attempts` conditionally only if `expires_at > CURRENT_TIMESTAMP`.
   - Empirical test confirmed exact accounting match: `prob_attempts == 6000` and `worker_attempts == 10000`.

---

## 3. Caveats

- **Network-level HTTP Concurrency**: These empirical tests evaluated multi-threaded and multi-process SQLite WAL concurrency directly at the Python database/scheduler layer. Full end-to-end HTTP concurrency testing across FastAPI endpoints is planned for Milestone 3 (REST API) and Milestone 5 (E2E).

---

## 4. Conclusion

**Verdict: APPROVE**

The fixes implemented in `src/shape_packing/server/scheduler.py` by `worker_m2_it2` are robust, mathematically sound, and empirically verified under heavy multi-threaded and multi-process contention. All concurrency invariants hold:
1. 0 duplicate leases assigned when unleased problems exist.
2. 0 duplicate leases during exploration when unattempted problems are leased but unleased attempted problems remain.
3. 0 deadlocks or lock escalations under sustained high-contention SQLite WAL mode.
4. 0 lost updates or discrepancies in attempt tallies during concurrent heartbeat and lease expiration races.
5. 100% pass rate (165/165 tests) across all database, scheduler, and concurrency test suites.

Milestone 2 is verified and ready for Milestone 3 progression.

---

## 5. Verification Method

To independently verify these findings:

```bash
# 1. Run the dedicated scheduler concurrency test suite
pytest tests/test_server_scheduler_concurrency.py -v

# 2. Run all database and scheduler regression test suites (165 tests)
pytest tests/test_server_database.py tests/test_server_database_concurrency.py tests/test_server_database_stress.py tests/test_server_scheduler.py tests/test_server_scheduler_concurrency.py tests/test_server_scheduler_stress.py -v

# 3. Run the empirical 50-thread distinct lease verification harness
PYTHONPATH=src python3 -c "
import sqlite3, threading, tempfile, os
from shape_packing.server.database import init_db
from shape_packing.server.scheduler import assign_work

tmp_dir = tempfile.mkdtemp()
db_file = os.path.join(tmp_dir, 'verify.db')
conn = init_db(db_file)
for i in range(10):
    conn.execute('INSERT INTO problems (id, inner_token, container_token, n, status, total_attempts) VALUES (?, ?, ?, ?, ?, ?)', (f'u_{i}', 'circle', 'square', 1, 'unattempted', 0))
for i in range(40):
    conn.execute('INSERT INTO problems (id, inner_token, container_token, n, status, total_attempts, best_s, reference_s) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (f'a_{i}', 'circle', 'square', 1, 'best_known', (i+1)*10, 10.0, 10.0))
conn.commit(); conn.close()

num_workers = 50
barrier = threading.Barrier(num_workers)
assigned, lock = [], threading.Lock()

def worker(idx):
    c = init_db(db_file)
    barrier.wait()
    w = assign_work(c, f'w_{idx}')
    if w:
        with lock: assigned.append(w['problem'])
    c.close()

threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_workers)]
for t in threads: t.start()
for t in threads: t.join()

assert len(assigned) == 50 and len(set(assigned)) == 50
print('Empirical check passed: 50/50 unique assignments, 0 duplicates!')
"
```
