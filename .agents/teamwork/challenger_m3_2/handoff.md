# Empirical Challenge Report: Coordinator REST API & Verifier Concurrency (Milestone 3)

**Author:** challenger_m3_2  
**Target:** parent (`86ab9594-ed5d-48cc-9be1-f2844355b5e4`)  
**Verdict:** **APPROVE**  
**Date:** 2026-11-21T00:36:00Z  

---

## 1. Observation

1. **Requested Verification Command & Results**:
   Executed the full test suite specified in dispatch item 5:
   ```bash
   pytest tests/test_server_api.py tests/test_server_scheduler_concurrency.py tests/test_server_database_concurrency.py -v
   ```
   Output:
   ```text
   ======================== 50 passed, 1 warning in 7.07s =========================
   ```
   All 50 tests passed with zero failures.

2. **Full Server Test Suite Execution**:
   Executed the complete server test suite across API, Database, Scheduler, Stress, and Concurrency suites:
   ```bash
   pytest tests/test_server_api.py tests/test_server_scheduler_concurrency.py tests/test_server_database_concurrency.py tests/test_server_api_concurrency.py tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_database_stress.py -v
   ```
   Output:
   ```text
   ======================= 207 passed, 1 warning in 14.58s ========================
   ```
   207 out of 207 tests passed with zero failures.

3. **Empirical Challenge Test Suite (`tests/test_server_api_concurrency.py`)**:
   Designed, implemented, and executed an 11-test adversarial stress harness targeting `src/shape_packing/server/app.py` under multi-threaded concurrency and lock contention:
   - `test_concurrent_worker_registrations`: 50 concurrent worker registrations followed by 50 concurrent re-registrations updating usernames under race conditions. Result: 100% 200 OK, exactly 50 rows in DB, last_seen_at updated, 0 deadlocks.
   - `test_concurrent_work_requests_with_shared_leasing`: 30 concurrent workers requesting work leases against 5 catalog problems. Result: 100% 200 OK, all obtain valid leases (unleased + fallback shared leasing), 30 active leases in DB, 0 deadlocks.
   - `test_concurrent_work_requests_empty_catalog_returns_204`: 24 concurrent requests against an empty catalog. Result: 100% 204 No Content, empty body, 0 exceptions.
   - `test_concurrent_heartbeats_under_wal_no_deadlocks`: 5 active leases, 150 concurrent heartbeat requests (30 per lease) reporting 25 attempts each (3,750 attempts total). Result: 100% 200 OK, `problems.total_attempts` and `workers.total_attempts` match exact mathematical expectation (3,750), zero dropped increments.
   - `test_concurrent_heartbeats_single_lease_heavy_contention`: 25 threads simultaneously updating the same lease with 100 attempts each. Result: 100% 200 OK, exact 2,500 attempts accumulated in both tables.
   - `test_concurrent_solutions_atomic_highest_metric_wins`: 16 workers concurrently submitting valid solutions for `3_3_in_circle` (initial `best_s = 3.0`) with metrics ranging from 2.95 down to 2.10. Result: all return 200 OK (verified=True); final `problems.best_s` in DB is exactly 2.10 (the lowest / winning metric); exactly 1 record in `solutions` table has `is_current_record = 1` with `metric_s = 2.10`; all intermediate records have `is_current_record = 0`; `records_broken` across workers equals the number of accepted record improvements.
   - `test_concurrent_solutions_mixed_valid_and_invalid`: 20 concurrent threads mixing valid improvements with invalid submissions (overlapping polygons failing SAT, out-of-bounds coords, coordinate vector length mismatches). Result: all invalid submissions rejected with HTTP 400 Bad Request (`verified = False`, `status = "rejected"`), valid submissions accepted with HTTP 200, zero state corruption, zero temp file leaks.
   - `test_full_cluster_heavy_traffic_stress`: 15 simulated volunteer nodes running 450+ concurrent requests across registration, work leasing, heartbeats, solution submissions, cluster stats, and leaderboard queries. Result: zero 500 errors, `PRAGMA integrity_check` returns `ok`, zero duplicate active records per problem.
   - `test_concurrent_wal_checkpoint_under_api_load`: Concurrent `PRAGMA wal_checkpoint(PASSIVE)` execution during active API worker read/write traffic. Result: zero locking errors, database integrity verified `ok`.
   - `test_concurrent_solutions_identical_metrics_single_winner`: 10 threads concurrently submitting the exact same metric (2.05). Result: exactly 1 accepted as new record (`is_new_record = True`), exactly 9 marked duplicate (`is_new_record = False`), exactly 1 active record in `solutions`, database `best_s = 2.05`.
   - `test_concurrent_solutions_sub_epsilon_improvements_rejected`: 8 concurrent threads submitting metrics `current_best - 1e-6` (< 1e-5 delta). Result: all 8 rejected as duplicates (`is_new_record = False`), `problems.best_s` unmodified.

4. **Implementation Inspection**:
   - `src/shape_packing/server/app.py`:
     - Line 61: `get_db(request: Request)` yields a thread-isolated SQLite connection per request with WAL mode and `timeout=30.0`, safely closing connections in a `finally:` block.
     - Line 229: `tempfile.NamedTemporaryFile` creates isolated JSON payloads for `verify_solution`, cleanly unlinked in `finally:`.
     - Line 269: Delegates atomic commits to `database.py:update_solution_record`.
   - `src/shape_packing/server/database.py`:
     - Line 235: `cursor.execute("BEGIN IMMEDIATE")` guarantees write serialization and eliminates race conditions.
     - Line 244: `if current_best is not None and metric_s >= (current_best - RECORD_MIN_IMPROVEMENT): conn.rollback(); return False` enforces strict improvement threshold.
     - Line 249: Atomically demotes previous records (`UPDATE solutions SET is_current_record = 0 WHERE problem_id = ?`) before inserting the winning record with `is_current_record = 1`.
   - `src/shape_packing/server/scheduler.py`:
     - Line 96: `assign_work` uses `BEGIN IMMEDIATE` to prevent race conditions during lease allocation.
     - Line 290: `record_heartbeat` uses `BEGIN IMMEDIATE` and safely increments attempts on worker and problem records.

---

## 2. Logic Chain

1. **Transaction Isolation and Deadlock Freedom**:
   - Observations 1, 2, 3, and 4 demonstrate that under heavy concurrent load (up to 50 threads and 450+ interleaved requests), zero `sqlite3.OperationalError: database is locked` errors occur.
   - This directly stems from `init_db` setting `timeout=30.0` and `PRAGMA journal_mode = WAL`, combined with every write operation explicitly acquiring `BEGIN IMMEDIATE` locks at the start of transactions rather than upgrading deferred read locks mid-transaction.

2. **Atomic Record Commits and Highest Metric Wins**:
   - Observation 3 (`test_concurrent_solutions_atomic_highest_metric_wins`, `test_concurrent_solutions_identical_metrics_single_winner`, `test_concurrent_solutions_sub_epsilon_improvements_rejected`) shows that when multiple candidates compete concurrently for the same problem:
     - The candidate with the best (lowest container metric $s$) wins.
     - If multiple candidates submit identical winning metrics simultaneously, exactly one is accepted as the new record and the remaining are categorized as duplicates.
     - At all times, the invariant $\text{COUNT}(is\_current\_record = 1) = 1$ is preserved per problem.
     - Sub-epsilon improvements below `RECORD_MIN_IMPROVEMENT` ($10^{-5}$) are safely treated as duplicates.

3. **In-Process Geometric SAT Verification Concurrency**:
   - Observation 3 (`test_concurrent_solutions_mixed_valid_and_invalid`) proves that in-process SAT collision checks, boundary containment checks, and temp file serialization operate safely in parallel across threads without file collision or state leakage. All invalid solutions return HTTP 400 Bad Request, leaving the database state completely unaffected.

4. **Attempt Tally Precision**:
   - Observation 3 (`test_concurrent_heartbeats_under_wal_no_deadlocks` and `test_concurrent_heartbeats_single_lease_heavy_contention`) verifies that 3,750 concurrent attempts across 150 requests and 2,500 attempts on a single contended lease were accumulated with 100% precision with zero lost updates.

---

## 3. Caveats

1. **Starlette Deprecation Warning**:
   - Python 3.14 emits `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.` This is an upstream Starlette/FastAPI warning and has zero impact on functionality or test reliability.
2. **Network Layer Scope**:
   - These empirical stress tests evaluated the FastAPI application and SQLite WAL persistence layer in-process via multi-threaded ASGI clients. Multi-process socket networking will be exercised in Milestone 4 and Milestone 5 when the standalone `native_worker.py` daemon is integrated.

---

## 4. Conclusion

**Verdict: APPROVE**

The Coordinator REST API (`src/shape_packing/server/app.py`) and its supporting database and scheduler modules satisfy all concurrency, integrity, and performance requirements for Milestone 3:
- Concurrent worker registrations and simultaneous work requests execute reliably without 500 errors.
- Concurrent heartbeat updates under SQLite WAL mode process cleanly with zero deadlocks and 100% attempt counting precision.
- Concurrent solution submissions update records atomically, maintain a single active record invariant, and ensure the best (lowest metric) solution wins.
- 50/50 tests pass in the required test suite; 11/11 tests pass in the new concurrency stress suite; 207/207 tests pass across the entire server test suite.

---

## 5. Verification Method

To independently reproduce and verify these findings, run the following automated commands:

```bash
# 1. Run the required concurrency test suite (item 5)
pytest tests/test_server_api.py tests/test_server_scheduler_concurrency.py tests/test_server_database_concurrency.py -v

# 2. Run the newly created empirical API concurrency and stress test suite
pytest tests/test_server_api_concurrency.py -v

# 3. Run all server test suites
pytest tests/test_server_api.py tests/test_server_scheduler_concurrency.py tests/test_server_database_concurrency.py tests/test_server_api_concurrency.py tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_database_stress.py -v
```

Expected result: 100% pass rate with zero failures.
