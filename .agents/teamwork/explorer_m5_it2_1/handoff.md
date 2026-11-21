# Investigation Report: Root Cause and Remediation for Flaky E2E Test `test_e2e_single_worker_lifecycle_fastapi_testclient`

**Author**: `explorer_m5_it2_1` (E2E Test Flake & Scheduler Investigation Explorer)  
**Parent**: Orchestrator conversation ID `86ab9594-ed5d-48cc-9be1-f2844355b5e4`  
**Target Files**:
- `tests/test_distributed_e2e.py` (lines 190–263)
- `src/shape_packing/server/scheduler.py` (lines 108–188)
- `src/shape_packing/server/app.py` (lines 193–203, 326–351)
- `src/shape_packing/server/database.py` (lines 67–79)
- `src/shape_packing/client/native_worker.py` (lines 416–442, 550–570)
**Date**: 2026-11-21T05:05:00Z  

---

## 1. Observation

### 1.1 Verbatim Failure and Empirical Reproduction
Running `test_e2e_single_worker_lifecycle_fastapi_testclient` repeatedly reproduces an intermittent failure with an uncaught `urllib.error.HTTPError: HTTP Error 400`:
- **Empirical test execution**:
  ```bash
  python3 -c "
  import subprocess, sys
  failed = 0
  for i in range(30):
      res = subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_distributed_e2e.py::test_e2e_single_worker_lifecycle_fastapi_testclient', '-q'], capture_output=True, text=True)
      if res.returncode != 0:
          failed += 1
          print(f'Run {i} failed!')
  print(f'Total failures out of 30: {failed}')
  "
  ```
- **Observed output**:
  ```
  Run 8 failed!
  Run 12 failed!
  Total failures out of 30: 2
  ```
- **Observed error stack**:
  ```
  FAILED tests/test_distributed_e2e.py::test_e2e_single_worker_lifecycle_fastapi_testclient
  cycle_res = run_worker_cycle(cfg, solver_fn=mock_solver)
  ...
  urllib.error.HTTPError: HTTP Error 400: HTTP Error 400
  tests/test_distributed_e2e.py:119: HTTPError
  ```

### 1.2 Database Schema and Test Setup
1. In `src/shape_packing/server/database.py` lines 67–79:
   ```sql
   CREATE TABLE IF NOT EXISTS problems (
       id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
       inner_token TEXT NOT NULL,
       container_token TEXT NOT NULL,
       n INTEGER NOT NULL CHECK (n > 0),
       best_s REAL CHECK (best_s IS NULL OR (best_s > 0 AND best_s < 1e999)),
       reference_s REAL CHECK (reference_s IS NULL OR (reference_s > 0 AND reference_s < 1e999)),
       status TEXT NOT NULL DEFAULT 'unattempted',
       total_attempts INTEGER DEFAULT 0,
       density_rank REAL DEFAULT 0.0,
       source_attribution TEXT,
       updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```
2. In `tests/test_distributed_e2e.py` lines 197–208:
   ```python
   cursor.execute(
       """
       INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
       VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', 0.85)
       """
   )
   cursor.execute(
       """
       INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
       VALUES ('4_4_in_4', '4', '4', 4, 5.0, 5.0, 'best_known', 0.75)
       """
   )
   ```
   Both rows specify `status = 'best_known'` and omit `total_attempts`, so both rows default to `total_attempts = 0`.

### 1.3 Scheduler Leasing Logic
In `src/shape_packing/server/scheduler.py` lines 108–158:
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
                ORDER BY
                    -- Tier 1: Stuck backoff (>50k attempts without improvement decays priority)
                    CASE
                        WHEN p.total_attempts > 50000
                             AND (p.updated_at IS NULL OR p.updated_at < datetime('now', '-1 day'))
                        THEN 1 ELSE 0
                    END ASC,
                    -- Tier 2: Closeness boost (within 1% of baseline record prioritized)
                    CASE
                        WHEN p.reference_s IS NOT NULL AND p.best_s IS NOT NULL AND p.reference_s > 0
                             AND (abs(p.best_s - p.reference_s) / p.reference_s) <= 0.01
                        THEN 0 ELSE 1
                    END ASC,
                    -- Tier 3: Attempt count fair balancing (total_attempts ASC)
                    p.total_attempts ASC,
                    -- Tier 4: Density rank void space (density_rank DESC)
                    p.density_rank DESC,
                    -- Tier 5: Random tie-breaker
                    RANDOM()
                LIMIT 1
                """
            )
            prob = cursor.fetchone()
```

### 1.4 Mock Solver and Server Verification Behavior
1. In `tests/test_distributed_e2e.py` lines 217–220:
   ```python
   # Valid placement of 3 triangles in circle (s=2.5 < target 3.0)
   valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

   def mock_solver(**kwargs: Any) -> Dict[str, Any]:
       return {"success": True, "best_s": 2.5, "values": valid_coords}
   ```
   `valid_coords` contains exactly 9 floating-point values ($3 \times 3$ coordinates for $N=3$).
2. In `src/shape_packing/server/app.py` lines 193–203:
   ```python
   n_shapes = int(prob["n"])
   expected_coords = n_shapes * 3
   if len(req.coordinates) != expected_coords:
       return JSONResponse(
           status_code=status.HTTP_400_BAD_REQUEST,
           content={
               "status": "rejected",
               "verified": False,
               "message": f"Expected {expected_coords} coordinates (3 * N), received {len(req.coordinates)}",
           },
       )
   ```
   For `4_4_in_4`, $N=4$, so `expected_coords = 12`. Because `len(req.coordinates) == 9 != 12`, the server returns `HTTP 400 Bad Request`.
3. In `tests/test_distributed_e2e.py` lines 105–119:
   `make_testclient_transport` translates any status code $\ge 400$ to `raise urllib.error.HTTPError(...)`.
4. In `tests/test_distributed_e2e.py` lines 257–261:
   ```python
   prob_resp = client.get("/api/v1/problems/3_3_in_circle")
   assert prob_resp.status_code == 200
   pdata = prob_resp.json()
   assert abs(pdata["best_s"] - 2.5) < 1e-6
   assert pdata["coordinates"] == valid_coords
   ```
   The test explicitly asserts that `3_3_in_circle` was the problem leased, improved, and updated.
5. In `src/shape_packing/server/app.py` lines 330–331:
   ```python
   cursor.execute("SELECT COUNT(*) FROM problems")
   total_probs = cursor.fetchone()[0]
   ```
   Global stats counts all rows in `problems` without filtering by status.

---

## 2. Logic Chain

1. **Why `4_4_in_4` is selected probabilistically**:
   - In the exploitation branch (`random.random() >= 0.10`, 90% probability), both problems tie on Tier 1 (attempts $\le 50000$), Tier 2 (both equal to reference record), and Tier 3 (`total_attempts = 0`). On Tier 4 (`density_rank DESC`), `3_3_in_circle` has `density_rank = 0.85` while `4_4_in_4` has `density_rank = 0.75`. Because $0.85 > 0.75$, `3_3_in_circle` is deterministically selected 100% of the time under exploitation.
   - However, in the exploration branch (`random.random() < 0.10`, 10% probability), the query filters on `(p.status = 'unattempted' OR p.total_attempts = 0)`. Both `3_3_in_circle` and `4_4_in_4` satisfy `p.total_attempts = 0`.
   - The exploration query specifies `ORDER BY RANDOM() LIMIT 1` with no density weighting. SQLite randomly selects between the two candidates with equal probability ($P = 0.50$).
   - Therefore, the probability of leasing `4_4_in_4` is $0.10 \times 0.50 = 0.05$ (5%).
2. **Why this crashes the test**:
   - When `4_4_in_4` is leased, `run_worker_cycle` calls `mock_solver`.
   - `mock_solver` unconditionally returns `valid_coords` (9 coordinates).
   - `/api/v1/solutions` checks whether `len(req.coordinates) == 3 * n`. For `4_4_in_4`, $n=4$, expecting 12 coordinates.
   - Coordinator returns `HTTP 400 Bad Request: Expected 12 coordinates (3 * N), received 9`.
   - `make_testclient_transport` raises `urllib.error.HTTPError`, terminating the test cycle before assertions run.
   - Even if `mock_solver` returned 12 coordinates, line 260 verifies that `3_3_in_circle`'s `best_s` was reduced to 2.5. If `4_4_in_4` were leased instead, `3_3_in_circle` would remain at 3.0, and line 260 would fail.
3. **Validation of Remediation Strategy 1 (`status = 'proved_optimal'`)**:
   - In `scheduler.py`, all queries (exploration line 117, exploitation line 134, and fallback line 166) contain `WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'`.
   - Marking `4_4_in_4` as `proved_optimal` strictly excludes it from all leasing paths, guaranteeing that `3_3_in_circle` is selected 100% of the time.
   - In `/api/v1/stats`, the query is `SELECT COUNT(*) FROM problems`, which does not filter out `proved_optimal`. Thus, `stats["total_problems"] == 2` is strictly preserved.
4. **Validation of Remediation Strategy 2 (dynamic `mock_solver`)**:
   - By inspecting `kwargs.get("inner_shape")` or `kwargs.get("inner_token")` in `mock_solver`, the solver can return valid coordinates for either $N=3$ (9 coordinates, $s=2.5$) or $N=4$ (12 coordinates, $s=4.5$).
   - Direct verification using `shape_packing.solution_tools:verify_solution` confirmed that `valid_square_coords = [-1.3, -1.3, 0.0, -1.3, 1.3, 0.0, 1.3, -1.3, 0.0, 1.3, 1.3, 0.0]` with $s=4.5$ is geometrically valid, non-overlapping (SAT verified), and contained within the container.
   - Testing 50 consecutive iterations with both remediations applied yielded 50/50 passes (0 failures).

---

## 3. Caveats

- **Production Code Status**: The production server code (`scheduler.py`, `app.py`, `database.py`) and worker daemon (`native_worker.py`) are fully compliant with Requirements R1–R5. The multi-armed bandit 10% exploration rule is an intentional design requirement. No modifications to production code in `src/shape_packing/` are needed or recommended.
- **Reviewer Minor Findings**: In addition to the flaky test finding, `reviewer_m5_2` noted two minor defensive improvements in `tests/test_distributed_e2e.py`:
  1. Adding `if proc.poll() is None: proc.kill(); proc.wait()` in `test_e2e_signal_interruption_subprocess_cli_daemon`'s `finally:` block to prevent orphaned worker daemon subprocesses on assertion failure.
  2. Active polling on `server.started` instead of fixed `time.sleep(0.4)` for Uvicorn startup.
  These can be included opportunistically by the implementation worker.

---

## 4. Conclusion

The root cause of the flaky test failure in `test_e2e_single_worker_lifecycle_fastapi_testclient` is confirmed beyond doubt:
1. `3_3_in_circle` and `4_4_in_4` both had `total_attempts = 0`, causing the 10% bandit exploration branch to randomly pick `4_4_in_4` ~50% of the time (~5% overall probability).
2. `mock_solver` returned 9 coordinates, violating the 12-coordinate expectation for $N=4$, resulting in HTTP 400 rejection.
3. The proposed dual remediation is 100% effective:
   - Primary: Set `status = 'proved_optimal'` on `4_4_in_4` in `test_e2e_single_worker_lifecycle_fastapi_testclient`.
   - Defense-in-depth: Make `mock_solver` dynamically return valid square coordinates if $N=4$ or triangle coordinates if $N=3$.

### Concrete Implementation Specification for `worker_m5_it2_1`

In `tests/test_distributed_e2e.py` lines 197–221:

```python
<<<<
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', 0.85)
        """
    )
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('4_4_in_4', '4', '4', 4, 5.0, 5.0, 'best_known', 0.75)
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    client = TestClient(app)
    transport_send = make_testclient_transport(client)

    # Valid placement of 3 triangles in circle (s=2.5 < target 3.0)
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    def mock_solver(**kwargs: Any) -> Dict[str, Any]:
        return {"success": True, "best_s": 2.5, "values": valid_coords}
====
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', 0.85)
        """
    )
    cursor.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('4_4_in_4', '4', '4', 4, 5.0, 5.0, 'proved_optimal', 0.75)
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    client = TestClient(app)
    transport_send = make_testclient_transport(client)

    # Valid placement of 3 triangles in circle (s=2.5 < target 3.0)
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]
    valid_square_coords = [-1.3, -1.3, 0.0, -1.3, 1.3, 0.0, 1.3, -1.3, 0.0, 1.3, 1.3, 0.0]

    def mock_solver(**kwargs: Any) -> Dict[str, Any]:
        inner = str(kwargs.get("inner_shape") or kwargs.get("inner_token") or "")
        if inner == "4":
            return {"success": True, "best_s": 4.5, "values": valid_square_coords}
        return {"success": True, "best_s": 2.5, "values": valid_coords}
>>>>
```

---

## 5. Verification Method

Once implemented, verify independently using:
1. **Flake-free Stress Test (50 iterations)**:
   ```bash
   python3 -c "
   import subprocess, sys
   for i in range(50):
       res = subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_distributed_e2e.py::test_e2e_single_worker_lifecycle_fastapi_testclient', '-q'], capture_output=True, text=True)
       assert res.returncode == 0, f'Run {i} failed: {res.stdout}'
   print('All 50 passed with 0 failures.')
   "
   ```
   *Expected result*: `All 50 passed with 0 failures.`
2. **Back-to-Back Full E2E Test Runs (10 iterations)**:
   ```bash
   python3 -c "
   import subprocess, sys
   for i in range(1, 11):
       res = subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_distributed_e2e.py', '-q'], capture_output=True, text=True)
       assert res.returncode == 0, f'Run {i} failed: {res.stdout}'
       print(f'Run {i}/10 passed.')
   "
   ```
   *Expected result*: 10/10 runs pass.
3. **Full Acceptance Test Suite**:
   ```bash
   pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_api.py tests/test_native_worker.py tests/test_distributed_e2e.py -v
   ```
   *Expected result*: 177 passed.
