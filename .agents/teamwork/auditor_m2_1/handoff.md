# Forensic Audit Report: Milestone 2 Work Scheduler and Priority Allocator

**Auditor Agent**: `auditor_m2_1`  
**Target Milestone**: Milestone 2: Work Scheduler and Priority Allocator  
**Audit Date**: 2026-11-20T23:45:30Z  
**Integrity Mode**: Development (per `ORIGINAL_REQUEST.md` line 8)  
**Verdict**: **CLEAN**

---

## Forensic Audit Report

**Work Product**: `src/shape_packing/server/scheduler.py`, `tests/test_server_scheduler.py`  
**Profile**: General Project (Development Mode)  
**Verdict**: **CLEAN**

### Phase Results
- **Hardcoded Test Results / Facades**: PASS — No hardcoded return values, dummy stubs, or mock facades detected.
- **Proved Optimal Exclusion**: PASS — `COALESCE(LOWER(p.status), '') != 'proved_optimal'` is strictly enforced in all SQL selection queries across exploration, exploitation, and shared fallback.
- **Lease Expiration & Lifecycle Accounting**: PASS — Stale leases are purged automatically via `DELETE FROM active_leases WHERE expires_at <= CURRENT_TIMESTAMP`; expired leases reject problem attempt updates while crediting worker compute.
- **Heartbeat Telemetry Security / Backdoor Protection**: PASS — `record_heartbeat` NEVER touches `problems.best_s` or inserts records into `solutions`; `best_s` is used strictly as an ephemeral telemetry argument.
- **Pre-populated Artifact Detection**: PASS — Zero pre-existing logs, result artifacts, or dummy output files detected.
- **Empirical Test Suite Execution**: PASS — 70 of 70 scheduler tests passed in 1.31s; full database regression suite passed (117/117 in 4.28s).

---

## 1. Observation

### 1.1 Requirements & Interface Contracts
- **`ORIGINAL_REQUEST.md` §R2**:
  > "Implement a multi-armed bandit scheduler in `src/shape_packing/server/scheduler.py` that leases problems to workers based on geometric void space (packing density), gap to records, and stuck problem backoff, while strictly excluding `proved_optimal` instances. Handle lease expiry and heartbeat accounting."
- **Integrity Level**: Development Mode (`ORIGINAL_REQUEST.md` line 8: `Integrity mode: development`).

### 1.2 Source Code Inspection: `src/shape_packing/server/scheduler.py`
1. **Lease Pruning (`expire_stale_leases`, lines 19–41)**:
   ```python
   cursor.execute("BEGIN IMMEDIATE")
   try:
       cursor.execute("DELETE FROM active_leases WHERE expires_at <= CURRENT_TIMESTAMP")
       deleted = cursor.rowcount
       conn.commit()
       return max(0, deleted)
   ```
2. **Work Assignment (`assign_work`, lines 43–244)**:
   - Purges expired leases prior to selection: line 88 (`expire_stale_leases(conn)`).
   - Enforces foreign keys and auto-registers workers: lines 97–104 (`INSERT INTO workers ... ON CONFLICT(id) DO UPDATE SET last_seen_at = CURRENT_TIMESTAMP`).
   - Normalizes hardware cores and attempts: line 76 (`recommended_attempts = max(1000, min(c * 1000, 20000))`).
   - Strict `proved_optimal` exclusion across all query branches:
     - Exploration unleased (line 115): `WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal' AND (p.status = 'unattempted' OR p.total_attempts = 0) AND l.work_id IS NULL`
     - Exploration fallback (line 129): `WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal' AND (p.status = 'unattempted' OR p.total_attempts = 0)`
     - Exploitation unleased (line 145): `WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal' AND l.work_id IS NULL`
     - Shared fallback (line 177): `WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'`
   - Exploitation priority ordering:
     - Tier 1: Stuck backoff (`total_attempts > 50000 AND (p.updated_at IS NULL OR p.updated_at < datetime('now', '-1 day'))`)
     - Tier 2: Closeness boost (`(abs(p.best_s - p.reference_s) / p.reference_s) <= 0.01`)
     - Tier 3: Attempt balance (`p.total_attempts ASC`)
     - Tier 4: Void space (`p.density_rank DESC`)
     - Tier 5: Random tie-breaker (`RANDOM()`)
   - Schema conformance: returns dictionary with 8 keys (`work_id`, `problem`, `inner_token`, `container_token`, `n`, `target_s`, `recommended_attempts`, `lease_seconds`).
3. **Heartbeat Accounting & Telemetry Boundary (`record_heartbeat`, lines 246–350)**:
   - Validates attempts: line 275 (`if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0: return False`).
   - Validates telemetry `best_s`: lines 279–283 (must be positive, finite float or int, not boolean).
   - Credits worker compute: lines 306–315 (`INSERT INTO workers ... ON CONFLICT(id) DO UPDATE SET total_attempts = workers.total_attempts + excluded.total_attempts, last_seen_at = CURRENT_TIMESTAMP`).
   - Verifies active lease: lines 322–330 (`SELECT 1 FROM active_leases WHERE work_id = ? AND worker_id = ? AND expires_at > CURRENT_TIMESTAMP`).
   - Atomically updates problem attempts: lines 334–342 (`UPDATE problems SET total_attempts = total_attempts + ? WHERE id = ?`).
   - **Crucial Security Finding**: Lines 246–350 contain NO references to modifying `problems.best_s` or inserting into `solutions`.

### 1.3 Pre-populated Artifact Inspection
- Command: `find tests/ .agents/ -name '*.log' -o -name '*result*' -o -name '*output*'`
- Output:
  ```text
  tests/test_compare_results.py
  tests/__pycache__/test_compare_results.cpython-314-pytest-9.2.0.pyc
  ```
  No pre-populated test output logs or fabricated artifact files exist.

### 1.4 Test Suite Execution
- **Command**: `pytest tests/test_server_scheduler.py -v`
- **Output**:
  ```text
  ============================= test session starts ==============================
  platform linux -- Python 3.14.10, pytest-9.2.0, pluggy-1.7.0 -- /usr/bin/python
  rootdir: /home/targed/Documents/Git/shape-packing
  collected 70 items

  tests/test_server_scheduler.py::test_assign_work_schema_compliance PASSED [  1%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[1-1000] PASSED [  2%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[2-2000] PASSED [  4%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[4-4000] PASSED [  5%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[8-8000] PASSED [  7%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[16-16000] PASSED [  8%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[20-20000] PASSED [ 10%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[32-20000] PASSED [ 11%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[64-20000] PASSED [ 12%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[128-20000] PASSED [ 14%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[0-1000] PASSED [ 15%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[-3-1000] PASSED [ 17%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[True-1000] PASSED [ 18%]
  tests/test_server_scheduler.py::test_assign_work_recommended_attempts_bounds[False-1000] PASSED [ 20%]
  tests/test_server_scheduler.py::test_assign_work_target_s_fallback PASSED [ 21%]
  tests/test_server_scheduler.py::test_assign_work_custom_lease_seconds PASSED [ 22%]
  tests/test_server_scheduler.py::test_assign_work_skips_proved_optimal PASSED [ 24%]
  tests/test_server_scheduler.py::test_assign_work_returns_none_when_only_proved_optimal PASSED [ 25%]
  tests/test_server_scheduler.py::test_assign_work_returns_none_when_db_empty PASSED [ 27%]
  tests/test_server_scheduler.py::test_assign_work_excludes_currently_leased PASSED [ 28%]
  tests/test_server_scheduler.py::test_assign_work_fallback_sharing_when_all_leased PASSED [ 30%]
  tests/test_server_scheduler.py::test_assign_work_priority_least_attempts_first PASSED [ 31%]
  tests/test_server_scheduler.py::test_assign_work_priority_density_rank PASSED [ 32%]
  tests/test_server_scheduler.py::test_assign_work_priority_closeness_boost PASSED [ 34%]
  tests/test_server_scheduler.py::test_assign_work_stuck_backoff PASSED    [ 35%]
  tests/test_server_scheduler.py::test_assign_work_stuck_backoff_cleared_by_solution_update PASSED [ 37%]
  tests/test_server_scheduler.py::test_assign_work_exploration_unattempted_selection PASSED [ 38%]
  tests/test_server_scheduler.py::test_assign_work_exploration_falls_back_when_no_unattempted PASSED [ 40%]
  tests/test_server_scheduler.py::test_expire_stale_leases_empty PASSED    [ 41%]
  tests/test_server_scheduler.py::test_expire_stale_leases_future_intact PASSED [ 42%]
  tests/test_server_scheduler.py::test_expire_stale_leases_past_deleted PASSED [ 44%]
  tests/test_server_scheduler.py::test_assign_work_auto_expires_stale_leases PASSED [ 45%]
  tests/test_server_scheduler.py::test_record_heartbeat_updates_problem_and_worker_attempts PASSED [ 47%]
  tests/test_server_scheduler.py::test_record_heartbeat_updates_worker_last_seen PASSED [ 48%]
  tests/test_server_scheduler.py::test_record_heartbeat_multiple_cumulative PASSED [ 50%]
  tests/test_server_scheduler.py::test_record_heartbeat_zero_attempts_liveness PASSED [ 51%]
  tests/test_server_scheduler.py::test_record_heartbeat_after_lease_expired PASSED [ 52%]
  tests/test_server_scheduler.py::test_record_heartbeat_unknown_work_id PASSED [ 54%]
  tests/test_server_scheduler.py::test_record_heartbeat_does_not_modify_best_s PASSED [ 55%]
  tests/test_server_scheduler.py::test_assign_work_invalid_worker_id[None] PASSED [ 57%]
  tests/test_server_scheduler.py::test_assign_work_invalid_worker_id[] PASSED [ 58%]
  tests/test_server_scheduler.py::test_assign_work_invalid_worker_id[   ] PASSED [ 60%]
  tests/test_server_scheduler.py::test_assign_work_invalid_worker_id[123] PASSED [ 61%]
  tests/test_server_scheduler.py::test_assign_work_invalid_worker_id[invalid_id4] PASSED [ 62%]
  tests/test_server_scheduler.py::test_assign_work_invalid_worker_id[invalid_id5] PASSED [ 64%]
  tests/test_server_scheduler.py::test_assign_work_unregistered_worker_auto_registration PASSED [ 65%]
  tests/test_server_scheduler.py::test_assign_work_preserves_existing_username PASSED [ 67%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_attempts[-1] PASSED [ 68%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_attempts[-100] PASSED [ 70%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_attempts[True] PASSED [ 71%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_attempts[False] PASSED [ 72%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_attempts[100] PASSED [ 74%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_attempts[12.5] PASSED [ 75%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_attempts[None] PASSED [ 77%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_attempts[invalid_attempts7] PASSED [ 78%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_identifiers[None] PASSED [ 80%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_identifiers[] PASSED [ 81%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_identifiers[   ] PASSED [ 82%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_identifiers[123] PASSED [ 84%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_identifiers[invalid_id4] PASSED [ 85%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_best_s[-1.0] PASSED [ 87%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_best_s[0.0] PASSED [ 88%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_best_s[nan] PASSED [ 90%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_best_s[inf] PASSED [ 91%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_best_s[True] PASSED [ 92%]
  tests/test_server_scheduler.py::test_record_heartbeat_invalid_best_s[1.5] PASSED [ 94%]
  tests/test_server_scheduler.py::test_functions_handle_invalid_connections PASSED [ 95%]
  tests/test_server_scheduler.py::test_concurrent_work_assignment_no_duplicates PASSED [ 97%]
  tests/test_server_scheduler.py::test_concurrent_heartbeats_no_lost_updates PASSED [ 98%]
  tests/test_server_scheduler.py::test_concurrent_expire_and_assign PASSED [100%]
  ============================== 70 passed in 1.31s ==============================
  ```
- **Regression Test Command**: `pytest tests/test_server_database.py tests/test_server_database_concurrency.py tests/test_server_database_stress.py -v`
- **Output**: `47 passed in 2.97s`. Combined server test suite: 117 tests passing with 0 failures.

### 1.5 Adversarial Empirical Probes
1. **Heartbeat Backdoor Probe**:
   - Injected problem with `best_s = 10.0`. Worker reported heartbeat with `best_s = 1.0` and `attempts = 1000`.
   - Result: Verified `problems.best_s` remained untouched at `10.0`, and `solutions` table remained completely empty (0 rows).
2. **Proved Optimal Exclusion Probe**:
   - Tested status strings `['proved_optimal', 'PROVED_OPTIMAL', 'Proved_Optimal', 'proved_OPTIMAL']` under 100% exploration mode, 100% exploitation mode, and leased shared fallback.
   - Result: Returned `None` in all cases; proved optimal problems were strictly never allocated.
3. **Lease Expiration Probe**:
   - Leased problem with 1-second expiration. Reported heartbeat at $t = 0.1\text{s}$ (returned `True`, updated problem attempts and worker attempts).
   - Waited 1.5s until expired. Reported heartbeat at $t = 1.6\text{s}$ (returned `False`, updated worker attempts, preserved problem attempts without alteration).
   - Called `expire_stale_leases` (returned `1`, pruned expired lease from `active_leases`).

---

## 2. Logic Chain

1. **Premise 1: Genuine Non-Facade Implementation**:
   - Direct inspection of `src/shape_packing/server/scheduler.py` reveals complete, substantive implementations of `expire_stale_leases`, `assign_work`, and `record_heartbeat`.
   - Functions perform dynamic SQL transactions in SQLite WAL mode using `BEGIN IMMEDIATE` for ACID isolation.
   - Return values are dynamically computed from database rows and runtime parameters (e.g. UUID generation, datetime calculations, core-scaled attempt normalization).
   - No hardcoded test responses or facade stubs exist.

2. **Premise 2: Proved Optimal Exclusion**:
   - `assign_work` filters problems using `WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'`.
   - This filter is applied uniformly in exploration (lines 115, 129), exploitation (line 145), and fallback shared leasing (line 177).
   - Empirical testing with 4 case variations confirmed zero leaks of proved optimal problems.

3. **Premise 3: SQLite Lease and Heartbeat Interaction**:
   - `expire_stale_leases` issues `DELETE FROM active_leases WHERE expires_at <= CURRENT_TIMESTAMP` inside an immediate transaction and inspects `cursor.rowcount`.
   - `assign_work` invokes `expire_stale_leases` upon every call, preventing zombie lease accumulation.
   - `record_heartbeat` verifies the lease status against SQLite `CURRENT_TIMESTAMP` before updating `problems.total_attempts`.

4. **Premise 4: Metric Security / Backdoor Immunity**:
   - `record_heartbeat` validates `best_s` as a finite positive number, but never executes any `UPDATE problems SET best_s` or `INSERT INTO solutions`.
   - Empirical probe confirmed that reporting arbitrary `best_s` values via heartbeat does not mutate the database record metric.
   - All record updates remain strictly confined to the solution verification pipeline (`update_solution_record`).

5. **Deductive Conclusion**:
   - All requirements of Milestone 2 from `ORIGINAL_REQUEST.md` §R2 and `PROJECT.md` are authentically implemented.
   - Every integrity forensic check passed with empirical proof.
   - Therefore, the verdict is **CLEAN**.

---

## 3. Caveats

- **No Caveats**: The audit found zero integrity violations, zero skipped tests, zero regressions, and zero security backdoors.
- **Milestone 3 Integration Note**: Downstream coordinator REST endpoints in `app.py` should map `assign_work -> None` to HTTP `204 No Content` and call `record_heartbeat` within `POST /api/v1/heartbeat`.

---

## 4. Conclusion

The Milestone 2 work product is **CLEAN**.
`src/shape_packing/server/scheduler.py` and `tests/test_server_scheduler.py` satisfy all behavioral, integrity, and interface specifications. The test suite exhibits 100% pass rate across 70 comprehensive test scenarios with full ACID concurrency safety.

---

## 5. Verification Method

To independently reproduce the forensic verification:

1. **Run the Scheduler Test Suite**:
   ```bash
   pytest tests/test_server_scheduler.py -v
   ```
   *Expected*: 70 passed in ~1.3s with 0 failures.

2. **Run Full Server Regression Test Suite**:
   ```bash
   pytest tests/test_server_database.py tests/test_server_database_concurrency.py tests/test_server_database_stress.py tests/test_server_scheduler.py -v
   ```
   *Expected*: 117 passed in ~4.3s with 0 failures.

3. **Run Heartbeat Telemetry & Proved Optimal Adversarial Probe**:
   ```bash
   PYTHONPATH=src python3 -c "
   import sqlite3
   from shape_packing.server.database import init_db
   from shape_packing.server.scheduler import assign_work, record_heartbeat

   conn = init_db(':memory:')
   conn.execute(\"INSERT INTO problems (id, inner_token, container_token, n, best_s, status) VALUES ('p1', '4', '4', 1, 10.0, 'best_known')\")
   conn.commit()
   w = assign_work(conn, worker_id='w1')
   assert record_heartbeat(conn, work_id=w['work_id'], worker_id='w1', attempts=1000, best_s=1.0) is True
   cur = conn.cursor()
   cur.execute('SELECT best_s FROM problems WHERE id = \"p1\"')
   assert cur.fetchone()[0] == 10.0, 'Backdoor vulnerability!'
   print('AUDIT VERIFIED CLEAN')
   "
   ```
   *Expected*: Prints `AUDIT VERIFIED CLEAN` and exits with code 0.
