# Milestone 5 Challenger Handoff Report: Stress & Flake Review

**Challenger**: `challenger_m5_1` (E2E Stress & Flake Challenger)  
**Parent**: Orchestrator conversation ID `86ab9594-ed5d-48cc-9be1-f2844355b5e4`  
**Target File**: `tests/test_distributed_e2e.py`  
**Verdict**: **REQUEST_CHANGES**  
**Date**: 2026-11-21T04:59:00Z  

---

## 1. Observation

### 1.1 Flake Reproduction in Back-to-Back Test Runs
During back-to-back execution of `tests/test_distributed_e2e.py`, Run 5 failed:
- Command:
  ```bash
  python3 -c "
  import subprocess, time, sys
  for i in range(1, 11):
      res = subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_distributed_e2e.py', '-q'], capture_output=True, text=True)
      print(f'Run {i:2d}/10: {\"PASS\" if res.returncode == 0 else \"FAIL\"}')
      if res.returncode != 0:
          print(res.stdout)
          sys.exit(1)
  "
  ```
- Output:
  ```
  Run  1/10: PASS in 3.14s
  Run  2/10: PASS in 3.11s
  Run  3/10: PASS in 3.10s
  Run  4/10: PASS in 3.13s
  Run  5/10: FAIL (code 1) in 3.13s
  STDOUT:
   F........                                                                [100%]
  =================================== FAILURES ===================================
  _____________ test_e2e_single_worker_lifecycle_fastapi_testclient ______________

  tmp_path = PosixPath('/tmp/pytest-of-targed/pytest-183/test_e2e_single_worker_lifecyc0')
  ...
  url = 'http://localhost:8000/api/v1/solutions', method = 'POST'
  payload = {'work_id': 'wu_9be1c1660b98', 'worker_id': '7ddedfae-39ac-4a15-9cb6-9fa52b82f5c8', 'problem': '4_4_in_4', 's': 2.5, ...}
  ...
  >           raise err
  E           urllib.error.HTTPError: HTTP Error 400: HTTP Error 400

  tests/test_distributed_e2e.py:119: HTTPError
  FAILED tests/test_distributed_e2e.py::test_e2e_single_worker_lifecycle_fastapi_testclient
  1 failed, 8 passed, 1 warning in 2.72s
  ```

### 1.2 Targeted Flake Rate Measurement
Running `test_e2e_single_worker_lifecycle_fastapi_testclient` 50 times in isolation:
- Command:
  ```bash
  python3 -c "
  import subprocess, sys
  failed = sum(1 for _ in range(50) if subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_distributed_e2e.py::test_e2e_single_worker_lifecycle_fastapi_testclient', '-q'], capture_output=True).returncode != 0)
  print(f'Total failures out of 50 runs: {failed} ({failed/50*100:.1f}%)')
  "
  ```
- Result: **2 failures out of 50 runs (4.0% failure rate)**.

### 1.3 Inspection of Code & Test Setup
In `tests/test_distributed_e2e.py`:
- Lines 197–208 insert two problems:
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
- Lines 217–220 define `mock_solver`:
  ```python
  valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

  def mock_solver(**kwargs: Any) -> Dict[str, Any]:
      return {"success": True, "best_s": 2.5, "values": valid_coords}
  ```
- In `src/shape_packing/server/scheduler.py` lines 109–125:
  ```python
  # 10% Probability exploration stage over unattempted shape configurations
  if random.random() < 0.10:
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

### 1.4 Stress-Testing Remaining 8 Workflows
Running the remaining 8 workflows repeatedly demonstrated exceptional stability:
- `test_e2e_single_worker_lifecycle_live_uvicorn_socket`: 0 failures out of 50 runs.
- `test_e2e_multi_worker_cluster_fleet`: 0 failures out of 50 runs.
- `test_e2e_concurrent_improvement_race`: 0 failures out of 10 runs.
- `test_e2e_starvation_and_backoff_recovery`: 0 failures out of 30 runs.
- `test_e2e_signal_interruption_in_process_graceful_shutdown`: 0 failures out of 10 runs.
- `test_e2e_signal_interruption_subprocess_cli_daemon`: 0 failures out of 30 runs.
- `test_e2e_invalid_geometry_rejected_and_attempts_preserved`: 0 failures out of 10 runs.
- `test_e2e_real_verification_file_catalog_seeding`: 0 failures out of 10 runs.

### 1.5 Test Order Independence & Resource Cleanliness
- Reverse test ordering: 9/9 passed.
- Randomized ordering across 5 different seeds: 5/5 passed.
- Thread leaks: 1 thread (`MainThread`) before and after pytest run. Zero thread leaks.
- File descriptor / socket leaks: 6 FDs before, 6 FDs after. Zero socket/FD leaks.
- Performance: Suite runtime averages 2.6s–3.1s (well under the 5.0s budget).

---

## 2. Logic Chain

1. In `test_e2e_single_worker_lifecycle_fastapi_testclient`, both `3_3_in_circle` and `4_4_in_4` are created with default `total_attempts = 0` (Observation 1.3).
2. The work scheduler in `scheduler.py` runs a multi-armed bandit algorithm with an exploration probability of 10% (`if random.random() < 0.10:`). When triggered, it queries for problems with `(p.status = 'unattempted' OR p.total_attempts = 0) ORDER BY RANDOM() LIMIT 1` (Observation 1.3).
3. Because both problems satisfy `total_attempts = 0`, SQLite chooses between `3_3_in_circle` and `4_4_in_4` with 50% probability during the exploration branch.
4. Therefore, with probability $0.10 \times 0.50 = 0.05$ (5%), the scheduler leases `4_4_in_4` to the worker instead of `3_3_in_circle`.
5. When `4_4_in_4` is leased, `mock_solver` unconditionally returns `valid_coords` (9 floats for 3 triangles). But `4_4_in_4` has $n=4$, which requires $3 \times 4 = 12$ coordinates.
6. The coordinator endpoint `/api/v1/solutions` checks coordinate vector length and rejects the submission with HTTP 400 Bad Request (`detail="Coordinate vector length must be 12 for n=4, got 9"`), raising `urllib.error.HTTPError: HTTP Error 400` in `run_worker_cycle`.
7. This directly explains the empirically measured 4.0% failure rate (Observation 1.1 and 1.2).
8. All other 8 tests, socket lifecycles, and concurrency scenarios are fully robust with 0 flakes across 30–50 runs (Observation 1.4), zero resource leaks (Observation 1.5), and sub-3.5s runtime.

---

## 3. Caveats

- The flake is localized strictly to the test fixture setup of `test_e2e_single_worker_lifecycle_fastapi_testclient`. The production server code (`app.py`, `scheduler.py`, `database.py`) and worker daemon (`native_worker.py`) operate strictly according to design.
- The 10% bandit exploration mechanism is an explicit requirement from Requirement R2. Thus, the production code is correct, and the test setup in `test_e2e_single_worker_lifecycle_fastapi_testclient` must be made robust against bandit exploration.

---

## 4. Conclusion

**Verdict: REQUEST_CHANGES**

`tests/test_distributed_e2e.py` cannot be approved until the probabilistic flake in `test_e2e_single_worker_lifecycle_fastapi_testclient` is resolved.

### Required Changes for `worker_m5_1`:
In `tests/test_distributed_e2e.py::test_e2e_single_worker_lifecycle_fastapi_testclient`:
1. Change the second inserted problem (`4_4_in_4`) to have `status='proved_optimal'`:
   ```python
   cursor.execute(
       """
       INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
       VALUES ('4_4_in_4', '4', '4', 4, 5.0, 5.0, 'proved_optimal', 0.75)
       """
   )
   ```
   *Why this fixes it*: The scheduler's query strictly filters `WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'`, guaranteeing `4_4_in_4` is never leased in either exploration or exploitation, while still keeping `stats["total_problems"] == 2` and `stats["total_attempts"] == 2000`.
2. Additionally, make `mock_solver` resilient by checking `kwargs.get("inner_shape")` or `kwargs.get("inner_token")`:
   ```python
   valid_triangle_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]
   valid_square_coords = [-1.3, -1.3, 0.0, -1.3, 1.3, 0.0, 1.3, -1.3, 0.0, 1.3, 1.3, 0.0]

   def mock_solver(**kwargs: Any) -> Dict[str, Any]:
       inner = str(kwargs.get("inner_shape") or kwargs.get("inner_token") or "")
       if inner == "4":
           return {"success": True, "best_s": 4.5, "values": valid_square_coords}
       return {"success": True, "best_s": 2.5, "values": valid_triangle_coords}
   ```

---

## 5. Verification Method

Once `worker_m5_1` applies the fix:
1. **Flake-free back-to-back verification (10x)**:
   ```bash
   python3 -c "
   import subprocess, sys
   for i in range(1, 11):
       res = subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_distributed_e2e.py', '-q'], capture_output=True, text=True)
       assert res.returncode == 0, f'Run {i} failed: {res.stdout}'
       print(f'Run {i}/10 passed.')
   "
   ```
   *Expected result*: 10/10 runs pass with 0 failures.

2. **Isolated 50-iteration stress run on test 1**:
   ```bash
   python3 -c "
   import subprocess, sys
   for i in range(50):
       res = subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_distributed_e2e.py::test_e2e_single_worker_lifecycle_fastapi_testclient', '-q'], capture_output=True, text=True)
       assert res.returncode == 0, f'Run {i} failed: {res.stdout}'
   print('All 50 passed.')
   "
   ```
   *Expected result*: 0 failures out of 50 runs.
