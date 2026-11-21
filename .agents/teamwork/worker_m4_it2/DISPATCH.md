## 2026-11-21T04:08:27Z
You are worker_m4_it2, a teamwork_preview_worker executing Milestone 4 Iteration 2 Remediation for the Native Worker Client Daemon.

Working Directory: /home/targed/Documents/Git/shape-packing/.agents/teamwork/worker_m4_it2
Workspace Root: /home/targed/Documents/Git/shape-packing

MANDATORY FIRST ACTIONS:
1. Initialize your BRIEFING.md, DISPATCH.md, and progress.md in your working directory.
2. Read ORIGINAL_REQUEST.md:
   /home/targed/Documents/Git/shape-packing/.agents/teamwork/ORIGINAL_REQUEST.md
3. Read the Iteration 2 remediation blueprints:
   - /home/targed/Documents/Git/shape-packing/.agents/teamwork/spec_miner_m4_it2_1/handoff.md
   - /home/targed/Documents/Git/shape-packing/.agents/teamwork/explorer_m4_it2_1/handoff.md
   - /home/targed/Documents/Git/shape-packing/.agents/teamwork/explorer_m4_it2_2/handoff.md
   - /home/targed/Documents/Git/shape-packing/.agents/teamwork/reviewer_m4_2/handoff.md

EXCLUSIVE FILE WRITE OWNERSHIP:
- src/shape_packing/client/native_worker.py
- tests/test_native_worker.py
- tests/test_native_worker_stress.py

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

REMEDIATION TASKS:
1. Complete Elimination of Test-Sniffing `mock_calls`:
   - In `src/shape_packing/client/native_worker.py`: Remove all 4 occurrences of `mock_calls` (lines 148, 151, 161, 177). Production code must NEVER inspect mock framework internals.
   - Cleanly delegate opener requests:
     `active_opener = opener or _get_opener(url)`
     `if active_opener is not None: resp_ctx = active_opener.open(req, timeout=timeout)`
     `else: resp_ctx = urllib.request.urlopen(req, timeout=timeout)`
   - Add `test_zero_mock_sniffing_in_production` to `tests/test_native_worker.py` with an AST walk asserting zero `.mock_calls` attribute checks and string literals.
2. Signal-Responsive Sleep (`ev.wait`):
   - In `run_worker_loop`: Replace `time.sleep(config.poll_interval)` and `time.sleep(sleep_time)` with `if ev.wait(timeout=...): break`. This ensures immediate sub-millisecond signal unblocking under PEP 475.
   - Add `test_sigint_unblocks_idle_wait_immediately` to `tests/test_native_worker.py`.
3. Compute Attempt Telemetry Preservation:
   - In `run_worker_cycle`: Advance `reporter.record_attempts(attempts, best_s)` before candidate solution submission, so completed volunteer compute is flushed in `finally: reporter.stop()` even if the coordinator rejects a solution with HTTP 400 or network drops occur.
   - Add `test_attempts_preserved_on_solution_400_rejection` to `tests/test_native_worker.py`.
4. Diagnostic Error Body Retention:
   - In `send_request`: Set `exc.error_body = err_text` before attempting `json.loads(err_text)` on HTTP 400 responses, ensuring plaintext/HTML error bodies are preserved.
5. In-Flight Attempt Synchronization:
   - In `HeartbeatReporter.flush`: Under network exception, update `set_in_flight_work` with current `self._unreported_attempts` and `self._best_local_s` inside `self._lock`.
6. Test Suite Alignment:
   - Update `tests/test_native_worker.py` and `tests/test_native_worker_stress.py` per the exact test matrix in `spec_miner_m4_it2_1/handoff.md §5.5`:
     - Configure unit test mock responses with `mock_resp.__enter__.return_value = mock_resp`.
     - In tests intercepting sleep/wait, patch `nw._GLOBAL_STOP_EVENT.wait` or `stop_event.wait` instead of `time.sleep`.
     - Ensure all 32+ unit tests, 19 stress tests, and 8 concurrency tests pass.

VERIFICATION:
Run pytest to verify all suites pass 100%:
`pytest tests/test_native_worker.py tests/test_native_worker_stress.py tests/test_native_worker_concurrency.py tests/test_server_api.py -v`
`pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_api.py tests/test_native_worker.py -v`

DELIVERABLE:
Write your complete handoff report to `/home/targed/Documents/Git/shape-packing/.agents/teamwork/worker_m4_it2/handoff.md` following the 5-component format.
Then notify parent with `send_message`.
