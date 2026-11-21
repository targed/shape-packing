# Milestone 4 Iteration 2 Review Report: Native Worker Client Daemon Remediation

**Reviewer**: `reviewer_m4_it2_2`  
**Milestone**: Milestone 4 Iteration 2 (Native Worker Client Daemon Remediation)  
**Verdict**: **APPROVE**  
**Overall Risk Assessment**: **LOW**  

---

## Review Summary

**Verdict**: **APPROVE**

All four findings from the previous review cycle (`reviewer_m4_2/handoff.md`) have been verified as **100% resolved** with high engineering quality and zero regressions:

1. **Critical Finding (Integrity Violation - Mock Sniffing) - RESOLVED**:
   `mock_calls` and all runtime mock sniffing logic have been completely excised from `src/shape_packing/client/native_worker.py`. A clean request dispatch mechanism (`_get_opener` with loopback bypass and optional caller-injected `opener`) replaced the ad-hoc mock detection. Tests configure mock doubles properly (`make_mock_response`), and an automated AST walk permanently prohibits test framework attribute sniffing.
2. **Major Finding (Signal-Hanging `time.sleep`) - RESOLVED**:
   `time.sleep()` in `run_worker_loop` (formerly lines 622, 629) was replaced by `if ev.wait(timeout=config.poll_interval): break` (line 614) and `if ev.wait(timeout=sleep_time): break` (line 622). Handled signals (`SIGINT`, `SIGTERM`) set `ev` and unblock idle/backoff waits instantaneously (< 0.1s) without PEP 475 syscall restart delays.
3. **Major Finding (Compute Attempt Telemetry Loss on Rejection) - RESOLVED**:
   In `run_worker_cycle`, `reporter.record_attempts(attempts, ...)` was moved to execute immediately following solver completion (lines 540–547), prior to candidate evaluation and POST submission. If `/api/v1/solutions` returns HTTP 400 (geometric verification rejection) or fails with network timeout, the outer `finally: reporter.stop()` guarantees that completed attempts are flushed to the coordinator heartbeat endpoint.
4. **Minor Finding (In-Flight State Synchronization on Retry) - RESOLVED**:
   In `HeartbeatReporter.flush`, on network exception, the current accumulated `self._unreported_attempts` is read inside `with self._lock:` before calling `set_in_flight_work` (lines 361–365), preventing concurrent solve attempts from being overwritten by stale values.

---

## 1. Observation

### 1.1 Complete Eradication of Test-Sniffing Mock Attributes
- Exact command:
  ```bash
  grep -n "mock" src/shape_packing/client/native_worker.py
  ```
  Result: Exit code 1 (0 matches).
- In `src/shape_packing/client/native_worker.py`, lines 145–153:
  ```python
  145:     try:
  146:         active_opener = opener or _get_opener(url)
  147:         if active_opener is not None:
  148:             resp_ctx = active_opener.open(req, timeout=timeout)
  149:         else:
  150:             resp_ctx = urllib.request.urlopen(req, timeout=timeout)
  151: 
  152:         cm = resp_ctx if hasattr(resp_ctx, "__enter__") else nullcontext(resp_ctx)
  153: 
  154:         with cm as resp:
  ```
- No mutation of `resp_ctx.__enter__.return_value` or checks for `hasattr(..., "mock_calls")` exist in production code.
- Automated AST enforcement in `tests/test_native_worker.py` (lines 882–909, `test_zero_mock_sniffing_in_production`) scans the parsed AST of `native_worker.py` and verifies that no `mock_calls` attribute accesses or string literals exist.

### 1.2 Signal-Responsive Event Wait in Worker Loop
- Exact command:
  ```bash
  grep -n "time.sleep" src/shape_packing/client/native_worker.py
  ```
  Result: Exit code 1 (0 matches).
- In `src/shape_packing/client/native_worker.py`, lines 611–624:
  ```python
  611:             if cycle_result.get("status") == "idle":
  612:                 if _SHUTDOWN or ev.is_set():
  613:                     break
  614:                 if ev.wait(timeout=config.poll_interval):
  615:                     break
  616: 
  617:         except Exception as e:
  618:             consecutive_errors += 1
  619:             if _SHUTDOWN or ev.is_set():
  620:                 break
  621:             sleep_time = min(config.max_backoff, 5.0 * consecutive_errors)
  622:             if ev.wait(timeout=sleep_time):
  623:                 break
  ```
- Signal unblocking speed test: `test_sigint_unblocks_idle_wait_immediately` in `tests/test_native_worker.py` executes `run_worker_loop` with a 10.0s poll interval and a 0.05s timer setting `ev.set()`. The loop unblocks and returns in < 0.1s (well under the 1.0s assertion bound).

### 1.3 Pre-Submission Attempt Telemetry Recording
- In `src/shape_packing/client/native_worker.py`, lines 538–572:
  ```python
  538:         # Record attempts immediately upon solver batch completion so volunteer compute
  539:         # is credited even if candidate solution submission fails or is rejected by coordinator
  540:         reporter.record_attempts(
  541:             attempts,
  542:             best_s=(
  543:                 metric_s_float
  544:                 if (metric_s_float is not None and metric_s_float > 0)
  545:                 else None
  546:             ),
  547:         )
  548: 
  549:         if (
  550:             success
  551:             and metric_s_float is not None
  552:             and not math.isnan(metric_s_float)
  553:             and not math.isinf(metric_s_float)
  554:         ):
  555:             if target_s_float is None or metric_s_float < target_s_float:
  556:                 found_improvement = True
  557:                 sol_url = f"{config.server_url.rstrip('/')}/api/v1/solutions"
  558:                 req(
  559:                     sol_url,
  560:                     method="POST",
  561:                     payload={
  562:                         "work_id": work_id,
  563:                         "worker_id": config.worker_id,
  564:                         "problem": problem,
  565:                         "s": metric_s_float,
  566:                         "coordinates": [float(c) for c in coords],
  567:                     },
  568:                 )
  569: 
  570:     finally:
  571:         reporter.stop()
  ```
- In `test_attempts_preserved_on_solution_400_rejection`, when `/api/v1/solutions` raises an HTTP 400 rejection (simulating geometric SAT overlap), `reporter.stop()` flushes 500 attempts to `/api/v1/heartbeat`.

### 1.4 Flush Retry In-Flight State Synchronization
- In `src/shape_packing/client/native_worker.py`, lines 356–366:
  ```python
  356:         try:
  357:             self.request_fn(url, method="POST", payload=payload)
  358:             return True
  359:         except Exception:
  360:             # Re-credit attempts if network call failed so they can be retried on next flush
  361:             with self._lock:
  362:                 self._unreported_attempts += attempts_to_send
  363:                 current_unreported = self._unreported_attempts
  364:                 current_best_s = self._best_local_s
  365:             set_in_flight_work(self.work_id, current_unreported, current_best_s)
  366:             return False
  ```
- Concurrency test `test_heartbeat_flush_retry_preserves_concurrent_in_flight_attempts` proves that attempts added concurrently during the network call (50 attempts added while 100 were in flight) yield exactly 150 attempts restored in both `reporter._unreported_attempts` and `_IN_FLIGHT_STATE["attempts"]`.

### 1.5 Diagnostic Error Body Retention
- In `src/shape_packing/client/native_worker.py`, lines 174–191:
  ```python
  174:     except urllib.error.HTTPError as exc:
  175:         try:
  176:             err_bytes = exc.read()
  177:             exc.fp = io.BytesIO(err_bytes)
  178:             exc.read = exc.fp.read
  179:             err_text = err_bytes.decode("utf-8", errors="replace")
  180:             exc.error_body = err_text
  181:             try:
  182:                 err_json = json.loads(err_text) if err_text.strip() else {}
  183:             except Exception:
  184:                 err_json = {}
  185:             exc.error_data = err_json
  186:         except Exception:
  187:             if not hasattr(exc, "error_body"):
  188:                 exc.error_body = ""
  189:             if not hasattr(exc, "error_data"):
  190:                 exc.error_data = {}
  191:         raise exc
  ```
- Validated with plaintext bodies in `test_400_with_plaintext_non_json_body` and JSON bodies in `test_send_request_400_bad_request`.

### 1.6 Independent Test Suite Execution Results
- Command:
  ```bash
  pytest tests/test_native_worker.py tests/test_server_api.py -v
  ```
  Result: **69 passed, 0 failures** in 0.75s.
- Command:
  ```bash
  pytest tests/test_native_worker_concurrency.py tests/test_native_worker_stress.py -v
  ```
  Result: **27 passed, 0 failures** in 2.88s.
- Command:
  ```bash
  pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_api.py tests/test_native_worker.py tests/test_native_worker_stress.py tests/test_native_worker_concurrency.py -v
  ```
  Result: **195 passed, 0 failures** in 4.92s.

---

## 2. Logic Chain

1. **Resolution of Critical Integrity Violation**:
   - Upstream previously used `hasattr(..., "mock_calls")` to alter execution paths and fix unconfigured MagicMock doubles from inside production code.
   - The remediation removed all 4 call sites and any mock sniffing. `send_request` cleanly relies on `active_opener = opener or _get_opener(url)` and `urllib.request.urlopen`.
   - Test doubles were updated to properly emulate readable streams and context managers using `make_mock_response`.
   - The AST test permanently ensures no future regressions or mock detection logic can be reintroduced.
   - Result: Finding 1 is 100% resolved and genuine.

2. **Resolution of Signal-Hanging Loops**:
   - Under Python 3.5+ (PEP 475), `time.sleep` restarts when signals are handled without raising exceptions.
   - `threading.Event.wait(timeout)` relies on condition variables and immediately wakes up and returns `True` when `ev.set()` is called from a signal handler.
   - Replacing `time.sleep` with `if ev.wait(timeout=...): break` ensures both idle polling and error backoff immediately terminate upon signal reception without blocking.
   - Result: Finding 2 is 100% resolved and verified.

3. **Resolution of Volunteer Attempt Loss**:
   - When a volunteer worker computes thousands of solver iterations, that compute must be credited regardless of whether the candidate solution is rejected (e.g. geometric overlap) or accepted.
   - Calling `reporter.record_attempts` before solution POST guarantees that attempts are tracked. The enclosing `try...finally: reporter.stop()` ensures that `self.flush(force=True)` runs even if an unhandled `HTTPError` occurs.
   - Result: Finding 3 is 100% resolved and verified.

4. **Resolution of In-Flight State Overwriting**:
   - When `flush` fails due to network outage, attempts are re-credited to `self._unreported_attempts`.
   - Concurrently, other threads may have recorded additional attempts.
   - By reading `self._unreported_attempts` under `self._lock` after adding `attempts_to_send`, `set_in_flight_work` receives the exact current total rather than the stale pre-flush snapshot.
   - Result: Finding 4 is 100% resolved and verified.

---

## 3. Findings Status Matrix

| Prior Finding | Severity | Category | Status | Verification Evidence |
|---|---|---|---|---|
| Finding 1: Mock-sniffing `mock_calls` in production | Critical | Integrity Violation | **RESOLVED** | Grep returns 0 matches; AST scan passes in `test_zero_mock_sniffing_in_production`. |
| Finding 2: Blocking `time.sleep` in worker loop | Major | Concurrency / Signals | **RESOLVED** | `time.sleep` eliminated; `ev.wait` unblocks in < 0.1s in `test_sigint_unblocks_idle_wait_immediately`. |
| Finding 3: Attempt loss on solution 400 rejection | Major | Business Logic / Telemetry | **RESOLVED** | `record_attempts` moved prior to POST; verified in `test_attempts_preserved_on_solution_400_rejection`. |
| Finding 4: In-flight state clobbering on flush retry | Minor | Thread Safety / Concurrency | **RESOLVED** | Read under lock; verified in `test_heartbeat_flush_retry_preserves_concurrent_in_flight_attempts`. |

---

## 4. Integrity Audit

- **Hardcoded test results embedded in source**: NONE. Verified through static inspection of `native_worker.py`.
- **Dummy or facade implementations**: NONE. Real urllib networking, real OS nice/ctypes priority calls, real threading primitives.
- **Shortcuts bypassing intended task**: NONE. Uses standard library `urllib` exclusively (no `requests`/`httpx` in client).
- **Fabricated verification outputs or logs**: NONE. All test commands executed live in subshell with 195/195 real passing tests.
- **Self-certifying work**: NONE. Independently reproduced and verified with separate test executions and AST checks.

---

## 5. Caveats

- **Windows Priority Verification**: As the test host is Linux, Windows `SetPriorityClass` was verified via unit test mocking and ctypes static structure analysis. On POSIX, `os.nice(19)` was directly tested and verified.
- **No external networking packages allowed**: Adhering strictly to Requirement R4, the client uses only Python standard library networking modules (`urllib.request`, `urllib.parse`, `urllib.error`). Zero third-party networking dependencies exist.

---

## 6. Conclusion

Milestone 4 Iteration 2 Remediation satisfies all functional and non-functional requirements. The critical integrity violation and all operational issues have been completely resolved. The implementation is robust, clean, and fully tested.

**Verdict**: **APPROVE**

---

## 7. Verification Method

To independently reproduce and verify this review:

1. **Verify Complete Absence of Mock Attributes in Production**:
   ```bash
   grep -n "mock" src/shape_packing/client/native_worker.py
   # Expected: Exit code 1 (0 matches)
   ```

2. **Verify AST Guard Against Mock Sniffing**:
   ```bash
   pytest tests/test_native_worker.py -k test_zero_mock_sniffing_in_production -v
   # Expected: 1 passed
   ```

3. **Verify Signal Responsive Unblocking (< 0.1s)**:
   ```bash
   pytest tests/test_native_worker.py -k test_sigint_unblocks_idle_wait_immediately -v
   # Expected: 1 passed
   ```

4. **Verify Attempt Telemetry Preservation on 400 Rejection**:
   ```bash
   pytest tests/test_native_worker.py -k test_attempts_preserved_on_solution_400_rejection -v
   # Expected: 1 passed
   ```

5. **Verify Flush Retry In-Flight State Synchronization**:
   ```bash
   pytest tests/test_native_worker.py -k test_heartbeat_flush_retry_preserves_concurrent_in_flight_attempts -v
   # Expected: 1 passed
   ```

6. **Run Client & Server Test Suites**:
   ```bash
   pytest tests/test_native_worker.py tests/test_server_api.py -v
   # Expected: 69 passed, 0 failures
   ```

7. **Run Full Distributed Test Suite**:
   ```bash
   pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_api.py tests/test_native_worker.py tests/test_native_worker_stress.py tests/test_native_worker_concurrency.py -v
   # Expected: 195 passed, 0 failures
   ```
