# Milestone 5 Review & Adversarial Challenge Report: End-to-End Integration Test Suite

**Reviewer**: `reviewer_m5_2` (E2E Test Suite Reviewer 2)  
**Parent**: Orchestrator conversation ID `86ab9594-ed5d-48cc-9be1-f2844355b5e4`  
**Target File Reviewed**: `tests/test_distributed_e2e.py`  
**Date**: 2026-11-21T04:54:30Z  
**Verdict**: **REQUEST_CHANGES**

---

## 1. Observation

### 1.1 Direct Test Suite Observations
- Target test file `tests/test_distributed_e2e.py` comprises 990 lines and 9 test workflows.
- Single-run execution of `pytest tests/test_distributed_e2e.py -v`:
  - Result: 9 passed, 1 warning in 2.69s.
- Combined acceptance suite `pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_api.py tests/test_native_worker.py tests/test_distributed_e2e.py -v`:
  - Result: 177 passed, 1 warning in 4.69s.
- Concurrency test suite: 38 passed in 11.40s.
- Integrity check:
  - Zero mock-sniffing or test-framework inspections in production `src/shape_packing/`.
  - The geometric SAT verifier (`src/shape_packing/solution_tools.py:verify_solution`) is genuinely executed in-process on real temporary JSON solution payloads. When tested directly against `valid_coords` (`[-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]`) and `overlapping_coords` (`[0.0] * 9`), the verifier returns `Valid: True` and `Valid: False (Shapes 0 and 1 overlap! Depth: 1.5)` respectively.

### 1.2 Flakiness Failure Observed Under Adversarial Stress Testing
During multi-iteration repeatability stress-testing (`for i in {1..5}; do pytest tests/test_distributed_e2e.py -q || exit 1; done`), iteration 2 failed with an uncaught `urllib.error.HTTPError: HTTP Error 400`:

```
=================================== FAILURES ===================================
_____________ test_e2e_single_worker_lifecycle_fastapi_testclient ______________

tmp_path = PosixPath('/tmp/pytest-of-targed/pytest-287/test_e2e_single_worker_lifecyc0')

    def test_e2e_single_worker_lifecycle_fastapi_testclient(tmp_path: Path):
...
>           cycle_res = run_worker_cycle(cfg, solver_fn=mock_solver)
...
url = 'http://localhost:8000/api/v1/solutions', method = 'POST'
payload = {'work_id': 'wu_ddce93e7cec2', 'worker_id': '6d9ab0c9-5445-494c-8c4e-76e7625e605b', 'problem': '4_4_in_4', 's': 2.5, ...}
...
>           raise err
E           urllib.error.HTTPError: HTTP Error 400: HTTP Error 400

tests/test_distributed_e2e.py:119: HTTPError
=========================== short test summary info ============================
FAILED tests/test_distributed_e2e.py::test_e2e_single_worker_lifecycle_fastapi_testclient
1 failed, 8 passed, 1 warning in 2.73s
```

### 1.3 Subprocess and Socket Lifecycle Observations
- In `tests/test_distributed_e2e.py` lines 786–827 (`test_e2e_signal_interruption_subprocess_cli_daemon`):
  `subprocess.Popen` is launched to execute `python -m shape_packing.client.native_worker`.
  In the `finally:` block (lines 824–827), only the uvicorn server is shut down (`server.should_exit = True; server_thread.join(timeout=2.0)`). `proc.kill()` is not called if `proc.communicate(timeout=5.0)` raises `TimeoutExpired` or if an assertion fails before process termination.
- In `tests/test_distributed_e2e.py` lines 317 and 781:
  Fixed `time.sleep(0.4)` is used to wait for uvicorn to bind rather than checking `server.started`.
- In `tests/test_distributed_e2e.py` lines 280–284 and 745–749:
  Ephemeral port allocation binds to `("127.0.0.1", 0)`, queries `port`, and immediately closes the socket before passing `port` to `uvicorn.Config`.

---

## 2. Logic Chain

### 2.1 Root Cause Analysis of Flaky Test Failure (Finding 1)
1. **Observation**: In `test_e2e_single_worker_lifecycle_fastapi_testclient` (lines 197–208), two problems are inserted:
   - `3_3_in_circle` (inner '3', container 'CIRCLE', $N=3$, best_s=3.0, total_attempts=0)
   - `4_4_in_4` (inner '4', container '4', $N=4$, best_s=5.0, total_attempts=0)
2. **Observation**: In `src/shape_packing/server/scheduler.py` line 110:
   `if random.random() < 0.10:`
   With 10% probability, the scheduler selects an unattempted problem via:
   `SELECT p.* FROM problems p ... WHERE (p.status = 'unattempted' OR p.total_attempts = 0) ... ORDER BY RANDOM() LIMIT 1`
3. **Logic**: Because both problems have `total_attempts = 0`, both qualify for the exploration query. `ORDER BY RANDOM()` selects `4_4_in_4` approximately 50% of the time that exploration triggers (overall ~5% probability on any call to `/api/v1/work`).
4. **Observation**: `mock_solver` in `test_e2e_single_worker_lifecycle_fastapi_testclient` (lines 217–220) is defined as:
   ```python
   valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

   def mock_solver(**kwargs: Any) -> Dict[str, Any]:
       return {"success": True, "best_s": 2.5, "values": valid_coords}
   ```
   `valid_coords` contains exactly 9 coordinates (3 vertices for $N=3$ shapes).
5. **Logic**: When `4_4_in_4` is leased, `mock_solver` returns 9 coordinates for a problem requiring $N=4$ (which requires $3 \times 4 = 12$ coordinates).
6. **Observation**: `/api/v1/solutions` checks coordinate vector length:
   `if len(req.coordinates) != 3 * n_shapes:`
   Since $9 \neq 12$, `/api/v1/solutions` returns `HTTP 400 Bad Request: "Coordinate count (9) must be 3*N (12)"`.
7. **Logic**: `run_worker_cycle` raises `urllib.error.HTTPError: HTTP Error 400`, crashing the test.
8. **Logic**: Furthermore, lines 257–261 assert:
   ```python
   prob_resp = client.get("/api/v1/problems/3_3_in_circle")
   assert prob_resp.status_code == 200
   pdata = prob_resp.json()
   assert abs(pdata["best_s"] - 2.5) < 1e-6
   ```
   Even if `mock_solver` returned 12 coordinates, `3_3_in_circle` would never have its `best_s` updated because `4_4_in_4` was leased, causing lines 257–261 to fail.
9. **Conclusion**: `test_e2e_single_worker_lifecycle_fastapi_testclient` is non-deterministic and flaky.

### 2.2 Subprocess Cleanup Risk (Finding 2)
1. **Observation**: `test_e2e_signal_interruption_subprocess_cli_daemon` starts an external OS process using `subprocess.Popen`.
2. **Logic**: If `proc.communicate(timeout=5.0)` times out or an assertion fails, execution jumps directly to `finally:` without terminating `proc`. The child worker daemon remains running in the background, consuming CPU and system resources.
3. **Conclusion**: The `finally:` block must ensure `if proc.poll() is None: proc.kill(); proc.wait()`.

### 2.3 Verified Robust Capabilities
1. **Test Isolation**: The `reset_worker_state` fixture cleanly resets `_SHUTDOWN`, `_GLOBAL_STOP_EVENT`, and `_IN_FLIGHT_STATE` under lock both before and after each test. All databases are placed in unique `tmp_path` files.
2. **Concurrency Safety**: In `test_e2e_multi_worker_cluster_fleet`, 6 workers execute concurrent cycles across 4 problems with shared lease fallbacks; 12,000 attempts and 2 broken records are aggregated without SQLite deadlocks or lost updates.
3. **Atomic Demotion**: In `test_e2e_concurrent_improvement_race`, racing workers submit $s=2.90$, $s=2.95$, and $s=2.85$; Charlie's record demotes Alice's while Bob's duplicate is rejected with 0 database rows inserted.
4. **SAT Verifier Integration**: Verifier actively runs pairwise SAT collision checks and boundary checks on real temporary files. Invalid geometry is rejected with HTTP 400 while preserving worker and problem attempt counts.

---

## 3. Findings

### [Major] Finding 1: Flaky Test Failure in `test_e2e_single_worker_lifecycle_fastapi_testclient`
- **Location**: `tests/test_distributed_e2e.py:183–263`
- **Issue**: Inserting two unattempted problems (`3_3_in_circle` and `4_4_in_4`) triggers the bandit scheduler's exploration query (`random.random() < 0.10`) with ~5% probability. When `4_4_in_4` is leased, `mock_solver` returns 9 coordinates instead of 12, causing HTTP 400 rejection and test failure.
- **Why**: Flaky tests violate CI reliability and can randomly fail automated PR and regression checks.
- **Suggested Fix**: In `test_e2e_single_worker_lifecycle_fastapi_testclient`, set the second problem (`4_4_in_4`) status to `'proved_optimal'`:
  ```python
  cursor.execute(
      """
      INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
      VALUES ('4_4_in_4', '4', '4', 4, 5.0, 5.0, 'proved_optimal', 0.75)
      """
  )
  ```
  This preserves `stats["total_problems"] == 2`, adheres strictly to Requirement R2 ("strictly excluding proved_optimal instances"), and guarantees deterministic leasing of `3_3_in_circle` 100% of the time.

### [Minor] Finding 2: Subprocess Process Leak Risk in `test_e2e_signal_interruption_subprocess_cli_daemon`
- **Location**: `tests/test_distributed_e2e.py:786–827`
- **Issue**: If `proc.communicate()` raises `TimeoutExpired` or if an assertion fails, the worker subprocess is never killed.
- **Suggested Fix**: Add process cleanup to the `finally:` block:
  ```python
  finally:
      if proc.poll() is None:
          proc.kill()
          try:
              proc.wait(timeout=2.0)
          except Exception:
              pass
      server.should_exit = True
      server_thread.join(timeout=2.0)
  ```

### [Minor] Finding 3: Arbitrary Sleep for Uvicorn Server Startup
- **Location**: `tests/test_distributed_e2e.py:317` and `781`
- **Issue**: `time.sleep(0.4)` assumes the server binds within 400ms. On slow or congested CI runners, this can lead to connection refused errors.
- **Suggested Fix**: Use an active polling loop on `getattr(server, "started", False)` with a 5.0s timeout.

---

## 4. Caveats

- **Integrity**: No cheating, hardcoded verification bypasses, or facade implementations were detected. All components interact through genuine HTTP, SQLite, and geometric verification layers.
- **Scope**: Production code in `src/shape_packing/` was preserved unchanged. All findings are contained within `tests/test_distributed_e2e.py`.

---

## 5. Conclusion

**Verdict: REQUEST_CHANGES**

While the test suite demonstrates excellent coverage of the distributed architecture (including real SAT verification, graceful signal flushing, and SQLite WAL concurrency), `test_e2e_single_worker_lifecycle_fastapi_testclient` suffers from a reproducible ~5% flakiness failure due to bandit exploration problem selection.

Once Finding 1 (and preferably Minor Findings 2 and 3) are addressed by the test worker, the test suite will be 100% deterministic and ready for approval.

---

## 6. Verification Method

To reproduce the findings:
1. **Demonstrate Flakiness in `test_e2e_single_worker_lifecycle_fastapi_testclient`**:
   ```bash
   for i in {1..25}; do pytest tests/test_distributed_e2e.py::test_e2e_single_worker_lifecycle_fastapi_testclient -q || break; done
   ```
   *Result*: Will fail with `urllib.error.HTTPError: HTTP Error 400` once the 10% exploration branch selects `4_4_in_4`.

2. **Verify Full Acceptance Test Suite Passing**:
   ```bash
   pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_api.py tests/test_native_worker.py tests/test_distributed_e2e.py -v
   ```
   *Result*: 177 passed.
