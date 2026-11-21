# Handoff Report: Milestone 5 — Multi-Worker Concurrency & Adversarial E2E Edge Cases

**Author**: `explorer_m5_2`
**Date**: 2026-11-21T04:36:00Z
**Mission**: Design multi-worker and adversarial edge-case integration scenarios for `tests/test_distributed_e2e.py`.

---

## 1. Observation

### 1.1 Coordinator Database Layer & Transaction Serialization
- In `src/shape_packing/server/database.py:62-115`, SQLite is configured with:
  ```sql
  PRAGMA journal_mode = WAL;
  PRAGMA synchronous = NORMAL;
  PRAGMA foreign_keys = ON;
  ```
- Connection initialization in `database.py:137`:
  ```python
  conn = sqlite3.connect(db_path, timeout=30.0)
  ```
- Solution commit atomicity in `database.py:235-285`:
  Write transactions strictly use `cursor.execute("BEGIN IMMEDIATE")` to prevent deadlocks and enforce serializable updates.
  A submission only breaks an existing record if:
  ```python
  if current_best is not None and metric_s >= (current_best - RECORD_MIN_IMPROVEMENT):
      conn.rollback()
      return False
  ```
  where `RECORD_MIN_IMPROVEMENT = 1e-5`.
  When accepted:
  1. Older records for that problem are demoted: `UPDATE solutions SET is_current_record = 0 WHERE problem_id = ?`.
  2. New solution row inserted: `INSERT INTO solutions (..., is_current_record) VALUES (..., 1)`.
  3. Problem metric updated: `UPDATE problems SET best_s = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?`.
  4. Worker record tally updated: `ON CONFLICT(id) DO UPDATE SET records_broken = workers.records_broken + 1`.

### 1.2 Multi-Armed Bandit Scheduler & Fair Allocation
- In `src/shape_packing/server/scheduler.py:43-233`:
  `assign_work` executes under `BEGIN IMMEDIATE` and runs in two stages:
  1. **Exploration (10% random probability)**: selects unattempted, unleased candidates (`ORDER BY RANDOM() LIMIT 1`).
  2. **Exploitation (90% probability)**: orders unleased problems by:
     - Tier 1: Stuck problem backoff (`total_attempts > 50000`).
     - Tier 2: Closeness boost (`abs(best_s - ref_s) / ref_s <= 0.01`).
     - **Tier 3: Attempt count fair balancing (`p.total_attempts ASC`)**.
     - Tier 4: Density rank void space (`p.density_rank DESC`).
  3. **Shared Leasing Fallback**: If all eligible problems are already leased by workers, the scheduler falls back to assigning already-leased problems, preserving the same prioritization tiers.
  This guarantees:
  - 100% of workers receive valid leases even when `workers > catalog_problems`.
  - Problems with fewer attempts (`total_attempts ASC`) are prioritized in subsequent lease rounds, ensuring fair distribution of volunteer compute.

### 1.3 In-Process Geometric SAT Verifier
- In `src/shape_packing/server/app.py:154-285`:
  `POST /api/v1/solutions` reconstructs shape polygons and invokes:
  ```python
  res = verify_solution(temp_path, problem_str=req.problem, check_record=False)
  ```
  If `not res.valid`:
  Returns HTTP 400 with:
  ```json
  {"status": "rejected", "verified": false, "message": "Geometric verification failed: <detail>"}
  ```
  Database records are untouched when verification fails.

### 1.4 Native Worker Daemon Telemetry Resilience
- In `src/shape_packing/client/native_worker.py:538-571`:
  ```python
  reporter.record_attempts(
      attempts,
      best_s=(
          metric_s_float
          if (metric_s_float is not None and metric_s_float > 0)
          else None
      ),
  )

  if (
      success
      and metric_s_float is not None
      and not math.isnan(metric_s_float)
      and not math.isinf(metric_s_float)
  ):
      if target_s_float is None or metric_s_float < target_s_float:
          found_improvement = True
          sol_url = f"{config.server_url.rstrip('/')}/api/v1/solutions"
          req(
              sol_url,
              method="POST",
              payload={
                  "work_id": work_id,
                  "worker_id": config.worker_id,
                  "problem": problem,
                  "s": metric_s_float,
                  "coordinates": [float(c) for c in coords],
              },
          )
  finally:
      reporter.stop()
  ```
  Crucial observation: `reporter.record_attempts(...)` is invoked **before** candidate solution submission.
  If `/api/v1/solutions` rejects an invalid submission with HTTP 400 (raising `urllib.error.HTTPError`), the `finally: reporter.stop()` block **guarantees** `flush(force=True)` is called.
  Therefore, volunteer attempt telemetry is sent to `/api/v1/heartbeat` and credited on the coordinator even when candidate coordinates fail geometric verification.

### 1.5 Empirical Test Execution Results
- Ran full existing concurrency suite:
  `pytest tests/test_server_database_concurrency.py tests/test_server_scheduler_concurrency.py tests/test_server_api_concurrency.py tests/test_native_worker_concurrency.py`
  Result: **38 passed in 11.45s** with 0 deadlocks and 0 locking conflicts.
- Ran standalone empirical verification scripts reproducing:
  - 6 concurrent worker daemons leasing and computing under SQLite WAL.
  - Concurrent improvement race on `3_3_in_circle` (Alice s=2.90 accepted; Bob s=2.95 rejected; Charlie s=2.85 accepted).
  - Invalid colliding geometry rejection (HTTP 400, telemetry credited, zero corruption).

---

## 2. Logic Chain

1. **Premise 1 (SQLite WAL Concurrency)**: SQLite with `journal_mode = WAL`, `synchronous = NORMAL`, and `timeout = 30.0` allows concurrent readers to read without blocking writers, while writers serialize via `BEGIN IMMEDIATE`.
2. **Premise 2 (Zero Deadlock Guarantee)**: Because all transactional endpoints (`assign_work`, `update_solution_record`, `record_heartbeat`) acquire immediate write locks at the start of transactions rather than upgrading deferred read locks mid-transaction, deadlock loops cannot form.
3. **Premise 3 (Fair Bandit Scheduling)**: When multiple workers lease problems concurrently:
   - If `workers <= catalog_problems`, each worker receives a distinct unleased problem.
   - If `workers > catalog_problems`, excess workers receive shared leases via the fallback branch.
   - In subsequent rounds, the scheduler sorts candidate problems by `p.total_attempts ASC`. The problems with lower attempt counts are prioritized, balancing search effort across the catalog.
4. **Premise 4 (Improvement Race Consistency)**:
   - When Worker A submits `s = 2.90`, `current_best` (3.0) is improved by `>= 1e-5`, so Worker A's solution is committed (`is_current_record = 1`, `best_s = 2.90`, Alice `records_broken = 1`).
   - When Worker B submits `s = 2.95`, `2.95 >= 2.90 - 1e-5`, so `update_solution_record` returns `False`. The coordinator returns HTTP 200 with status `"duplicate"`. No record is inserted for Bob; Bob's `records_broken` remains 0; `problems.best_s` remains 2.90.
   - When Worker C submits `s = 2.85`, `2.85 < 2.90 - 1e-5`. Alice's record is demoted (`is_current_record = 0`), Charlie's record is marked active (`is_current_record = 1`), Charlie's `records_broken` becomes 1, and `problems.best_s` becomes 2.85.
   - Leaderboard accurately ranks Charlie and Alice with 1 record broken each, and ranks Bob below them with 0 records broken.
5. **Premise 5 (Adversarial Geometric Collision Rejection)**:
   - When an adversarial or buggy worker generates overlapping coordinates (`[0.0, 0.0, 0.0, ...]`), `verify_solution` detects SAT collision and returns `valid = False`.
   - The coordinator returns HTTP 400 `{"status": "rejected", "verified": false}`.
   - The worker client raises `urllib.error.HTTPError(400)`.
   - The `finally:` block of `run_worker_cycle` executes `reporter.stop()`, successfully flushing accumulated attempts to `/api/v1/heartbeat`.
   - Database integrity check confirms: `problems.best_s` is unmodified, `solutions` table has 0 rows, and worker `records_broken == 0` while `total_attempts` reflects search effort.

---

## 3. Caveats

1. **TestClient Concurrency & Thread Isolation**:
   In `fastapi.testclient.TestClient`, sharing a single `TestClient` instance across multiple concurrent threads can cause httpx transport state race conditions. Creating a `TestClient(app)` per thread (or using `threading.local()`) completely eliminates transport contention and allows true concurrent execution against the SQLite database in WAL mode.
2. **Worker Loop Exponential Backoff on 400**:
   In `native_worker.run_worker_loop`, if a cycle raises an exception (e.g., HTTP 400 from invalid geometry), the worker enters exponential error backoff (`min(max_backoff, 5.0 * errors)`). To keep E2E tests sub-second, test scenarios should test `run_worker_cycle` directly or supply a `stop_event` that exits the loop cleanly.
3. **Float Delta Comparison**:
   Floating-point equality comparisons must use `abs(a - b) < 1e-6` to avoid platform float representation discrepancies.

---

## 4. Conclusion & Test Blueprint

To fulfill Milestone 5, the following three test scenarios must be implemented in `tests/test_distributed_e2e.py` alongside the single-worker scenarios designed by `explorer_m5_1`.

### Blueprint 1: Multi-Worker Cluster Fleet
```python
def test_e2e_multi_worker_cluster_fleet(tmp_path):
    """
    E2E Scenario: 6 worker daemons concurrently leasing work, reporting heartbeats,
    and submitting solutions against coordinator with SQLite WAL mode.
    
    Verifies:
    1. Zero deadlocks or database locked errors under concurrent load.
    2. Multi-armed bandit scheduler allocates problems across workers (unleased + shared fallback).
    3. Attempts are precisely accumulated on problems and workers.
    4. Records broken are properly credited to winning workers.
    5. Cluster stats and leaderboard reflect consistent global state.
    """
```
**Key Steps**:
1. Seed 4 benchmark problems (`3_3_in_circle`, `4_4_in_square`, `2_cir_in_circle`, `5_5_in_circle`) with distinct density ranks.
2. Register 6 workers: `fleet_vol_0` through `fleet_vol_5`.
3. Concurrently execute `run_worker_cycle` across 6 worker threads using `concurrent.futures.ThreadPoolExecutor(max_workers=6)`.
4. Configure solver: Workers 0 and 1 find genuine improvements; Workers 2-5 complete standard attempt batches without improvements.
5. In second round of leasing, verify scheduler prioritizes problems with fewer attempts (`p.total_attempts ASC`).
6. Assert database state:
   - `COUNT(*) FROM solutions WHERE is_current_record = 1` == 2
   - `SUM(records_broken) FROM workers` == 2
   - `GET /api/v1/stats` returns `active_workers == 6`, `verified_solutions >= 2`, and matching `total_attempts`.

### Blueprint 2: Concurrent Improvement Race
```python
def test_e2e_concurrent_improvement_race(tmp_path):
    """
    E2E Scenario: Competing workers race on the same problem with different metrics.
    
    Sequence:
    - Problem baseline: s = 3.0 ('3_3_in_circle')
    - Worker A (Alice) submits s = 2.90 -> Accepted, new record!
    - Worker B (Bob) submits s = 2.95 -> Duplicate, rejected (not lower than 2.90)!
    - Worker C (Charlie) submits s = 2.85 -> Accepted, new record!
    
    Verifies:
    1. Atomic record demotion: Alice's solution demoted (is_current_record = 0).
    2. Charlie's solution active (is_current_record = 1).
    3. Zero solutions inserted for Bob.
    4. problems.best_s == 2.85.
    5. Leaderboard ranks Charlie (#1) and Alice (#2) with 1 record each, Bob (#3) with 0.
    """
```
**Key Steps**:
1. Seed `3_3_in_circle` with `best_s = 3.0`.
2. Register Alice, Bob, and Charlie.
3. All three obtain leases on `3_3_in_circle`.
4. Submit solutions in order: Alice (2.90), Bob (2.95), Charlie (2.85).
5. Verify response bodies: Alice accepted, Bob duplicate, Charlie accepted.
6. Verify database records: exactly 2 solutions in DB; problems.best_s == 2.85.
7. Verify leaderboard: Alice (1 record), Charlie (1 record), Bob (0 records).
8. Verify `GET /api/v1/problems/3_3_in_circle` returns Charlie's coordinates.

### Blueprint 3: Invalid / Colliding Geometry Rejection
```python
def test_e2e_invalid_colliding_geometry_rejection(tmp_path):
    """
    E2E Scenario: Worker submits overlapping polygons that violate SAT.
    
    Verifies:
    1. Coordinator in-process SAT verifier detects collision and returns HTTP 400.
    2. Worker catches HTTP 400 with diagnostic message detailing polygon overlap.
    3. Attempt telemetry is preserved and flushed via HeartbeatReporter.stop() in finally block.
    4. Database remains uncorrupted: best_s unchanged, 0 solution rows inserted.
    5. Worker recovers and successfully submits valid packing in subsequent cycle.
    """
```
**Key Steps**:
1. Seed `3_3_in_circle` with `best_s = 3.5`.
2. Register worker `adversarial_alice`.
3. Worker runs cycle with buggy solver returning overlapping coordinates `[0.0, 0.0, 0.0, ...]`.
4. Catch `urllib.error.HTTPError(400)`; verify error message indicates `"overlap"`.
5. Verify coordinator database:
   - `problems.best_s == 3.5` (uncorrupted).
   - `problems.total_attempts >= 1000` (telemetry preserved).
   - `COUNT(*) FROM solutions == 0`.
   - `workers.records_broken == 0`.
6. Run second cycle with valid coordinates `[-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]` and `s = 2.90`.
7. Verify successful recovery: HTTP 200 accepted, `best_s == 2.90`, `records_broken == 1`.

---

## 5. Verification Method

### 5.1 Test Execution Commands
Once `tests/test_distributed_e2e.py` is implemented:
```bash
# Run the complete distributed end-to-end suite
pytest tests/test_distributed_e2e.py -v

# Run the complete test suite across all milestones
pytest tests/test_server_database.py \
       tests/test_server_scheduler.py \
       tests/test_server_api.py \
       tests/test_native_worker.py \
       tests/test_distributed_e2e.py -v
```

### 5.2 Inspection Checklist
- Check `active_leases` table during and after test runs.
- Check `sqlite3.Row` dictionaries for column key consistency.
- Verify `is_current_record` invariant: for any problem, `COUNT(is_current_record = 1) <= 1`.

### 5.3 Invalidation Conditions
- Any occurrence of `sqlite3.OperationalError: database is locked`.
- Any HTTP 500 Internal Server Error during concurrent leasing or heartbeats.
- Overwriting `best_s` when a worse metric is submitted.
- Loss of worker attempt counts upon solution submission failure.
