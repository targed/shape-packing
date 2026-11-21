# Milestone 4 Specification Handoff Report: Native Worker Client Daemon

**Author**: `spec_miner_m4_1`  
**Target Milestone**: Milestone 4 (Native Worker Client Daemon)  
**Target Files**:
- `src/shape_packing/client/__init__.py`
- `src/shape_packing/client/native_worker.py`
- `tests/test_native_worker.py`

---

## 1. Observations

### 1.1 Requirements & Specifications
1. **ORIGINAL_REQUEST.md (§R4 & Acceptance Criteria)**:
   - Line 24-26:
     > "Build a Python worker client in `src/shape_packing/client/native_worker.py` that connects to the coordinator using Python's standard library `urllib`, runs search batches at idle OS priority using `packer_rs` via `solver_interface`, immediately submits improved configurations, and flushes heartbeats gracefully on SIGINT/SIGTERM."
   - Line 43-45:
     > "- [ ] Worker runs without third-party networking dependencies using standard library `urllib`.  
     > - [ ] Handles SIGINT/SIGTERM gracefully by reporting in-flight attempts before terminating."
   - Line 47:
     > "`pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_api.py tests/test_native_worker.py tests/test_distributed_e2e.py` passes with 0 failures."

2. **Architecture Spec (`docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md`)**:
   - Section 4 (REST API Contract):
     - `POST /api/v1/workers/register`: Worker registration (`{"username": "...", "client_type": "native", "worker_id": "..."}`) returning 200 OK with `{"worker_id": "...", "username": "...", "status": "registered"}`.
     - `GET /api/v1/work?worker_id={worker_id}&cores={cores}`: Work lease assignment returning 200 OK with work unit JSON (`work_id`, `problem`, `inner_token`, `container_token`, `n`, `target_s`, `recommended_attempts`, `timeout_seconds`), or HTTP 204 No Content with empty body when no problems are available.
     - `POST /api/v1/solutions`: Solution submission (`{"work_id": "...", "worker_id": "...", "problem": "...", "s": ..., "coordinates": [...]}`) returning 200 OK (`status: accepted`, `is_new_record: true`) or 400 Bad Request (`status: rejected`, `verified: false`).
     - `POST /api/v1/heartbeat`: Heartbeat and attempt telemetry (`{"worker_id": "...", "work_id": "...", "attempts_completed": ..., "best_local_s": ...}`) returning 200 OK (`status: recorded`).
   - Section 8 (Native Worker Daemon):
     - Python process running at OS idle priority (`nice` on POSIX or safe fallback).
     - Configurable via CLI flags: `--server`, `--username`, `--cores`.
     - Graceful shutdown capturing `SIGINT` / `SIGTERM`, completing the current batch, flushing completed attempts via `/api/v1/heartbeat`, and exiting.

3. **Plan Spec (`docs/superpowers/plans/2026-11-20-distributed-shape-packing.md` Task 4 & Task 5)**:
   - Task 4 specifies:
     - `WorkerConfig` dataclass: `server_url`, `username`, `worker_id`, `cores`.
     - `send_request(url: str, method: str = "GET", payload: Optional[Dict] = None) -> Dict[str, Any]`
     - `register_with_server(server_url: str, username: str, worker_id: Optional[str] = None) -> str`
     - `run_worker_cycle(config: WorkerConfig, solver_fn: Optional[Callable] = None) -> Dict[str, Any]`
     - `main()` CLI entrypoint with `argparse`, `os.nice(19)`, signal handlers, and execution loop.
   - Task 5 demonstrates end-to-end integration:
     - Worker client retrieves work assignment from coordinator, executes solver, submits valid improvement to `/api/v1/solutions`, reports heartbeat to `/api/v1/heartbeat`, and verifies leaderboard updates.

### 1.2 Existing Codebase Observations & Discrepancies
1. **`src/shape_packing/solver_interface.py` Interface Details**:
   - Line 218:
     ```python
     def run_solver(
         n_shapes: int,
         inner_shape: str,
         container_shape: str,
         attempts: int = 1000,
         ...
         target_s: Optional[float] = None,
     ) -> Dict[str, Any]:
     ```
     *Discrepancy*: `solver_interface.run_solver` parameter is named `n_shapes`, NOT `n`. In `plan.md` Task 4 line 970, the plan draft passed `n=work["n"]`. That would raise `TypeError: run_solver() got an unexpected keyword argument 'n'`. The worker implementation must pass `n_shapes=work["n"]` (or pass `work["n"]` positionally).
   - Lines 91-98 and 198-203:
     ```python
     return {
         "success": True,
         "score": final_metric,  # or "score": score
         "S": S,
         "values": values,
         "backend": "...",
         "output": ...
     }
     ```
     *Discrepancy*: `run_solver` returns `"score"` (float) and `"values"` (list of coordinates), NOT `"best_s"`. In `plan.md` line 976, the draft checked `result.get("best_s")`. If only `best_s` is checked, it evaluates to None or `inf`, so no improvement is ever submitted! The worker client must check:
     `metric_s = result.get("best_s") if "best_s" in result else result.get("score")`
     and coordinates:
     `coordinates = result.get("values") or result.get("coordinates") or []`.

2. **Standard Library `urllib` Observable Behavior**:
   - `urllib.request.urlopen` returns an HTTPResponse object for status 200 and 204.
   - On HTTP 204: `resp.read()` returns `b""`. Decoding to utf-8 gives `""`. `json.loads("")` raises `json.JSONDecodeError` unless checked before parsing.
   - On HTTP 400, 404, 500: `urlopen` raises `urllib.error.HTTPError`.
   - `HTTPError` wraps the underlying socket stream in `fp`. Calling `err.read()` reads the stream once. Subsequent calls to `err.read()` return `b""`.
   - On timeout: raises `urllib.error.URLError` wrapping `socket.timeout` or `TimeoutError`.
   - On connection refused: raises `urllib.error.URLError` wrapping `ConnectionRefusedError`.

3. **Operating System Priority (`os.nice`)**:
   - `hasattr(os, "nice")` is `True` on Linux/POSIX, but `False` on Windows.
   - On POSIX, calling `os.nice(19)` succeeds for non-root users increasing niceness to idle priority.
   - If permissions fail or `os.nice` raises `OSError` / `AttributeError`, worker must not crash; it should log a warning or gracefully pass.

---

## 2. Logic Chain

1. **Zero External Network Dependencies**:
   - R4 and Acceptance Criteria mandate: no `requests`, no `httpx`, stdlib `urllib` only.
   - `send_request` must use `urllib.request.Request`, encode payloads to UTF-8 JSON bytes, set `Content-Type: application/json` and `Accept: application/json`, and handle empty 204 responses by returning an empty dict `{}`.
   - To make `send_request` robust for both API queries and error handling, `send_request` should read and parse JSON responses, and when `HTTPError` occurs, read the error response body and raise `HTTPError` (or a worker network error) with the body attached.

2. **Worker Configuration Flexibility**:
   - Workers must be configurable via defaults, environment variables (`SHAPE_PACKING_SERVER_URL`, `SHAPE_PACKING_USERNAME`, `SHAPE_PACKING_CORES`, `SHAPE_PACKING_WORKER_ID`), and CLI arguments / programmatic overrides.
   - Server URLs with trailing slashes must be stripped to prevent double-slash path routing errors (`http://localhost:8000//api/v1/work`).
   - Cores must be validated (`cores >= 1`).

3. **Worker Lifecycle & Coordination**:
   - Worker registers handle via `POST /api/v1/workers/register` and receives persistent `worker_id`.
   - Polling loop queries `GET /api/v1/work?worker_id={worker_id}&cores={cores}`.
   - If coordinator returns HTTP 204 No Content, worker enters idle backoff (sleeps `poll_interval`, default 5.0s) and does not invoke the solver.
   - If work is received, worker executes solver batch using `solver_fn` (or `solver_interface.run_solver`).
   - If solver discovers a metric better than `target_s` (or when `target_s` is None for new problems), worker immediately submits solution via `POST /api/v1/solutions`.
   - Worker always reports completed attempts and local best metric via `POST /api/v1/heartbeat`.

4. **Graceful Shutdown & Signal Handling**:
   - Long-running daemons receive `SIGINT` (Ctrl+C) or `SIGTERM` (systemd/container stop).
   - Signal handler sets `_SHUTDOWN = True`.
   - The worker loop detects `_SHUTDOWN`, completes or flushes in-flight attempt progress via `POST /api/v1/heartbeat`, and terminates with exit code 0.
   - A dedicated `flush_in_flight_heartbeat(config)` helper ensures that pending attempts are never lost upon shutdown.

---

## 3. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Configuration | Default Configuration | Default config with standard local coordinator and 1 core | None | `WorkerConfig(server_url="http://localhost:8000", username="anonymous", worker_id=None, cores=1, poll_interval=5.0)` | None | Design Spec §8, Plan Task 4 |
| 2 | Configuration | Environment Variable Ingestion | Load config from environment variables | `SHAPE_PACKING_SERVER_URL`, `SHAPE_PACKING_USERNAME`, `SHAPE_PACKING_CORES`, `SHAPE_PACKING_WORKER_ID` | Updated `WorkerConfig` | Invalid numeric cores falls back or raises ValueError | R4, Spec Miner Probing |
| 3 | Configuration | Argument & Param Overrides | Constructor / CLI arguments take precedence over env and defaults | CLI args (`--server`, `--username`, `--cores`, `--worker-id`, `--max-cycles`) | Overridden `WorkerConfig` | `cores < 1` raises ValueError | Plan Task 4 |
| 4 | Configuration | Server URL Normalization | Strip trailing slashes from server URL to prevent malformed endpoints | URL with trailing `/` (e.g. `http://localhost:8000///`) | Clean URL `http://localhost:8000` | Empty string raises ValueError | Spec Miner Probing |
| 5 | Networking | Stdlib `send_request` GET | Issues HTTP GET via `urllib.request` with `Accept: application/json` | URL, headers, timeout | Parsed JSON dict | Network errors raise `urllib.error.URLError` | R4, Plan Task 4 |
| 6 | Networking | Stdlib `send_request` POST | Issues HTTP POST with JSON body encoded as UTF-8 | URL, payload dict, headers, timeout | Parsed JSON dict | Serialized payload, raises `URLError` on failure | R4, Plan Task 4 |
| 7 | Networking | HTTP 204 Empty Body Handling | Correctly parses HTTP 204 No Content without JSONDecodeError | Response status 204, empty byte body `b""` | `{}` (empty dict) | Does not raise `json.JSONDecodeError` | Coordinator `app.py:148` |
| 8 | Networking | HTTP 400 Bad Request Handling | Traps `urllib.error.HTTPError`, exposes status code and error body | Coordinator 400 response with JSON message | Raises `HTTPError` with readable body or returns error dict | Trapped and parsed | Coordinator `app.py:168` |
| 9 | Networking | Network Timeout & Connection Refused | Handles socket timeout and unreachable coordinator | Unreachable server or delay > timeout | Raises `urllib.error.URLError` or `TimeoutError` | Caught by worker loop; backs off and retries | Plan Task 4, Dispatch |
| 10 | Registration | Worker Registration | Registers worker node and receives or confirms `worker_id` | `server_url`, `username`, optional `worker_id` | Registered `worker_id` string | Coordinator 400 if username empty; URLError if offline | Coordinator `app.py:90` |
| 11 | Polling | Work Unit Polling | Leases work unit matching worker ID and cores count | `GET /api/v1/work?worker_id=...&cores=...` | Work dictionary or empty on 204 | Raises if worker_id empty or cores < 1 | Coordinator `app.py:118` |
| 12 | Polling | 204 Backoff Sleep | Sleeps `poll_interval` when server returns 204 to prevent tight-looping | Empty work response | Sleep duration elapsed, loop resumes | Interrupted cleanly by `_SHUTDOWN` | Design Spec §4, Dispatch |
| 13 | Solver Execution | Solver Execution Bridge | Invokes solver with problem tokens, piece count $N$, attempts, target | `inner_token`, `container_token`, `n`, `attempts`, `target_s` | `{"success": bool, "score": float, "values": [...]}` | Handles both `n_shapes` and `n`, both `score` and `best_s` | `solver_interface.py:218` |
| 14 | Solution Submission | Improvement Submission | Submits coordinates to `/api/v1/solutions` if metric beats target | `work_id`, `worker_id`, `problem`, `s`, `coordinates` | Server verification result (accepted/rejected) | Rejected if SAT overlap or out-of-bounds | Coordinator `app.py:153` |
| 15 | Solution Submission | Non-Improvement Filter | Skips `/api/v1/solutions` if metric does not improve target | `s >= target_s` or solver failed | No POST to solutions, cycle continues | None | Plan Task 4 |
| 16 | Telemetry | Heartbeat Emission | Emits attempt tally and local best metric to `/api/v1/heartbeat` | `worker_id`, `work_id`, `attempts_completed`, `best_local_s` | `{"status": "recorded"}` | Coordinator 400 if attempts < 0 | Coordinator `app.py:287` |
| 17 | Process Priority | Idle OS Priority (`os.nice`) | Sets process nice level to 19 on Linux/POSIX | None | Returns `True` on success, `False` on fallback | Catches `OSError`, `AttributeError` (Windows) | R4, Design Spec §8 |
| 18 | Signal Handling | SIGINT/SIGTERM Graceful Shutdown | Catches signals, sets `_SHUTDOWN = True`, flushes in-flight progress | `signal.SIGINT` or `signal.SIGTERM` | `_SHUTDOWN = True`, heartbeat flushed | Process exits cleanly without data loss | R4, Design Spec §8 |
| 19 | Execution Loop | Single-Cycle Execution | Executes exactly one work lease cycle | `WorkerConfig`, optional `solver_fn` | Cycle summary dict (`attempts_completed`, `found_improvement`) | Traps cycle errors | Plan Task 4 |
| 20 | Execution Loop | Multi-Cycle Bounded Execution | Runs up to `max_cycles` cycles or until `_SHUTDOWN` | `WorkerConfig(max_cycles=N)` | List of cycle summary dicts | Handles transient network errors with 5s backoff | Plan Task 4, Dispatch |

---

## 4. Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | `send_request` | HTTP 204 with 0-byte body `b""` | Must return `{}` without raising `json.JSONDecodeError`. |
| 2 | `send_request` | HTTP 400 with JSON error body | `urllib.error.HTTPError` is raised. Note: `err.read()` must be read carefully because the file pointer is consumed after first read. |
| 3 | `send_request` | Unreachable coordinator (connection refused) | Raises `urllib.error.URLError` wrapping `ConnectionRefusedError`. Worker loop catches and sleeps 5s before retrying. |
| 4 | `send_request` | Request socket timeout | Raises `urllib.error.URLError` wrapping `socket.timeout` or `TimeoutError`. Worker loop catches and retries. |
| 5 | `WorkerConfig` | `server_url` with trailing slashes (`"http://localhost:8000///"`) | Stripped cleanly to `"http://localhost:8000"`, preventing double-slashed URLs like `http://localhost:8000///api/v1/work`. |
| 6 | `WorkerConfig` | `cores=0` or `cores=-1` | Raises `ValueError("cores must be >= 1")`. |
| 7 | `WorkerConfig` | Missing environment variables | Falls back to sensible defaults (`http://localhost:8000`, `anonymous`, 1 core). |
| 8 | `set_idle_priority` | Execution on Windows (`hasattr(os, "nice") == False`) | Safely returns `False` without raising `AttributeError`. |
| 9 | `set_idle_priority` | Execution in restricted container where `os.nice(19)` raises `PermissionError` / `OSError(EPERM)` | Safely catches exception, logs warning, and returns `False`. |
| 10 | `run_worker_cycle` | Work unit missing `recommended_attempts` | Falls back to default `2000` attempts. |
| 11 | `run_worker_cycle` | Problem has `target_s = None` (unattempted problem) | Any successful packing is considered an improvement and submitted. |
| 12 | `run_worker_cycle` | Solver returns `score` instead of `best_s` | Correctly extracts metric from `score` key to prevent improvement drop. |
| 13 | `run_worker_cycle` | Solver returns `values` instead of `coordinates` | Correctly extracts coordinates vector from `values` key. |
| 14 | `run_worker_cycle` | Solver fails (`success=False`) | `found_improvement=False`, solution is NOT submitted, but attempts are still reported via heartbeat. |
| 15 | `handle_signal` | Signal received while worker is idling between cycles | Sets `_SHUTDOWN=True`, polling loop terminates immediately without starting new work. |
| 16 | `handle_signal` | Signal received with in-flight work | Sets `_SHUTDOWN=True`, flushes in-flight completed attempts to `/api/v1/heartbeat`, then exits cleanly. |

---

## 5. Test Suite Specification (`tests/test_native_worker.py`)

The test suite must cover all 9 areas with isolated unit tests using mocks and no real external network requests:

### Group 1: Configuration Initialization (`WorkerConfig`)
1. `test_config_defaults`:
   - Initialize `WorkerConfig()` with no args.
   - Assert `server_url == "http://localhost:8000"`, `username == "anonymous"`, `worker_id is None`, `cores == 1`, `poll_interval == 5.0`.
2. `test_config_from_env`:
   - Mock `os.environ` with `SHAPE_PACKING_SERVER_URL="http://coord:9000"`, `SHAPE_PACKING_USERNAME="volunteer1"`, `SHAPE_PACKING_CORES="8"`, `SHAPE_PACKING_WORKER_ID="worker-uuid-42"`.
   - Call `WorkerConfig.from_env()`.
   - Assert all fields match environment variables.
3. `test_config_overrides`:
   - Pass explicit overrides (`cores=4`, `username="custom"`) to `WorkerConfig`.
   - Assert explicit arguments override defaults and env vars.
4. `test_config_normalization`:
   - Pass `server_url="http://localhost:8000///"`.
   - Assert `config.server_url == "http://localhost:8000"`.
5. `test_config_validation_cores`:
   - Pass `cores=0` or `cores=-2`.
   - Assert `ValueError` is raised.

### Group 2: `send_request` with stdlib `urllib`
6. `test_send_request_get_200`:
   - Mock `urllib.request.urlopen` returning HTTP 200 with JSON bytes `b'{"status": "ok"}'`.
   - Call `send_request("http://localhost:8000/test", method="GET")`.
   - Assert returns `{"status": "ok"}`. Assert request method is GET, headers contain `Accept: application/json`.
7. `test_send_request_post_200`:
   - Mock `urlopen` returning 200 with JSON response for POST with body `{"k": "v"}`.
   - Call `send_request("http://localhost:8000/test", method="POST", payload={"k": "v"})`.
   - Assert payload is UTF-8 JSON encoded and request method is POST.
8. `test_send_request_204_no_content`:
   - Mock `urlopen` returning response with status 204 and empty read `b""`.
   - Call `send_request(...)`.
   - Assert returns `{}` and no JSONDecodeError is raised.
9. `test_send_request_400_bad_request`:
   - Mock `urlopen` raising `urllib.error.HTTPError(..., 400, "Bad Request", ..., fp=io.BytesIO(b'{"message": "invalid"}'))`.
   - Call `send_request(...)`.
   - Assert raises `urllib.error.HTTPError` with `code == 400` (or returns handled error dict).
10. `test_send_request_timeout`:
    - Mock `urlopen` raising `urllib.error.URLError("timed out")` or `TimeoutError()`.
    - Call `send_request(...)`.
    - Assert `urllib.error.URLError` (or `TimeoutError`) is raised.
11. `test_send_request_connection_refused`:
    - Mock `urlopen` raising `urllib.error.URLError(ConnectionRefusedError("Connection refused"))`.
    - Call `send_request(...)`.
    - Assert `urllib.error.URLError` is raised.

### Group 3: Worker Registration Flow
12. `test_register_with_server_generates_id`:
    - Mock `send_request` returning `{"worker_id": "uuid-test-1", "username": "alice", "status": "registered"}`.
    - Call `register_with_server("http://localhost:8000", "alice")`.
    - Assert returns `"uuid-test-1"`.
13. `test_register_with_server_existing_id`:
    - Mock `send_request`. Pass `worker_id="fixed-uuid"`.
    - Verify payload sent to `/api/v1/workers/register` has `{"username": "bob", "client_type": "native", "worker_id": "fixed-uuid"}`.
14. `test_register_with_server_network_error`:
    - Mock `send_request` raising `URLError`.
    - Verify exception is raised to caller or handled cleanly.

### Group 4: Work Polling Loop with 204 Backoff
15. `test_run_worker_cycle_204_idle`:
    - Mock `send_request` returning `{}` (HTTP 204).
    - Call `run_worker_cycle(config)`.
    - Assert returns `{"status": "idle", "attempts_completed": 0, "found_improvement": False}`.
    - Assert no solver function was invoked.
16. `test_run_worker_loop_204_backoff_sleep`:
    - Mock `send_request` returning 204, mock `time.sleep`.
    - Run `run_worker_loop(config, max_cycles=1)`.
    - Assert `time.sleep` was called with `config.poll_interval`.

### Group 5: Heartbeat Emission
17. `test_heartbeat_emitted_after_solver_batch`:
    - Mock work unit and solver completing 1000 attempts.
    - Call `run_worker_cycle(config, solver_fn=...)`.
    - Inspect calls to `send_request`. Assert `/api/v1/heartbeat` was called with:
      - `worker_id == config.worker_id`
      - `work_id == "wu_1"`
      - `attempts_completed == 1000`
      - `best_local_s == 2.95`

### Group 6: Solution Submission on Improvement
18. `test_solution_submitted_on_improvement`:
    - Target $s = 3.0$. Mock solver returning `best_s = 2.90` (or `score = 2.90`).
    - Call `run_worker_cycle(config, solver_fn=...)`.
    - Assert `POST /api/v1/solutions` was called with `{"work_id": "...", "worker_id": "...", "problem": "...", "s": 2.90, "coordinates": [...]}`.
    - Assert cycle result has `found_improvement=True`.
19. `test_solution_not_submitted_when_no_improvement`:
    - Target $s = 3.0$. Mock solver returning `best_s = 3.10`.
    - Call `run_worker_cycle(config, solver_fn=...)`.
    - Assert `POST /api/v1/solutions` was NOT called.
    - Assert `POST /api/v1/heartbeat` WAS called with 1000 attempts.
    - Assert cycle result has `found_improvement=False`.
20. `test_solution_not_submitted_on_solver_failure`:
    - Mock solver returning `{"success": False}`.
    - Call `run_worker_cycle(config, solver_fn=...)`.
    - Assert `POST /api/v1/solutions` was NOT called.

### Group 7: Idle Priority Setting (`os.nice`)
21. `test_set_idle_priority_posix_success`:
    - Patch `os.nice` to return 19.
    - Call `set_idle_priority()`.
    - Assert returns `True` and `os.nice(19)` was called.
22. `test_set_idle_priority_permission_error_fallback`:
    - Patch `os.nice` to raise `PermissionError("Operation not permitted")`.
    - Call `set_idle_priority()`.
    - Assert returns `False` without raising an exception.
23. `test_set_idle_priority_windows_fallback`:
    - Patch `os` to not have `nice` attribute (`delattr(os, "nice")`).
    - Call `set_idle_priority()`.
    - Assert returns `False` without raising `AttributeError`.

### Group 8: Signal Handling & Graceful Shutdown
24. `test_handle_signal_sets_shutdown_flag`:
    - Call `handle_signal(signal.SIGINT, None)`.
    - Assert `_SHUTDOWN` flag becomes `True`.
25. `test_graceful_shutdown_flushes_inflight_heartbeat`:
    - Simulate in-flight work with 500 completed attempts.
    - Trigger `flush_in_flight_heartbeat(config)`.
    - Assert `POST /api/v1/heartbeat` was called reporting in-flight attempts.
26. `test_loop_terminates_promptly_when_shutdown_requested`:
    - Set `_SHUTDOWN = True`.
    - Run `run_worker_loop(config)`.
    - Assert loop exits immediately without executing any work cycle.

### Group 9: Single-Cycle & Multi-Cycle Execution
27. `test_single_cycle_end_to_end`:
    - Run `run_worker_cycle(config, solver_fn=...)` end-to-end.
    - Verify complete return schema: `status`, `attempts_completed`, `found_improvement`.
28. `test_multi_cycle_max_cycles`:
    - Run `run_worker_loop(config, max_cycles=3, solver_fn=...)`.
    - Assert exactly 3 cycles executed and returned in history list.
29. `test_multi_cycle_error_recovery`:
    - Mock `send_request` raising `URLError` on cycle 1, succeeding on cycle 2.
    - Patch `time.sleep`.
    - Run `run_worker_loop(config, max_cycles=2)`.
    - Assert error was caught, backoff sleep occurred, cycle 2 completed, daemon did not crash.

---

## 6. Caveats

1. **Solver Interface Signature**:
   - `solver_interface.run_solver` uses `n_shapes` (not `n`). If `solver_fn` is injected in tests, tests may pass `n` or `n_shapes`. The native worker daemon should pass `n_shapes=work["n"]` to `run_solver`.
2. **Solver Output Keys**:
   - `solver_interface.run_solver` outputs `{"score": ..., "values": ...}`. The native worker should check both `best_s` and `score`, and both `coordinates` and `values`.
3. **Signal Handler Scope**:
   - Signal handlers in Python run on the main thread only. In a multi-threaded or sub-process worker context, signal registration must occur in the main execution thread.
4. **No External Network Dependencies**:
   - Standard library `urllib` must be strictly adhered to. Third-party packages (`requests`, `httpx`, `aiohttp`) must NOT be imported in `src/shape_packing/client/native_worker.py`.

---

## 7. Conclusion

Milestone 4 requires building the Native Worker Client Daemon in `src/shape_packing/client/native_worker.py` and its comprehensive test suite in `tests/test_native_worker.py`. The specification mined in this report covers all requirements of R4, the architecture specification §4/§8, and plan Task 4.

Key contracts identified:
1. `WorkerConfig` with defaults, environment variables (`SHAPE_PACKING_*`), argument overrides, URL normalization, and core validation.
2. `send_request` standard library `urllib` implementation handling GET/POST, 200, 204 (empty body dict return), 400 error bodies, timeouts, and connection refused errors.
3. Worker registration flow (`/api/v1/workers/register`).
4. Polling loop with 204 backoff sleep.
5. In-flight heartbeat emission and flush on SIGINT/SIGTERM (`/api/v1/heartbeat`).
6. Solution submission on verified improvement (`/api/v1/solutions`).
7. Cross-platform idle priority (`os.nice(19)` with graceful Windows/permission fallback).
8. Bounded multi-cycle execution (`max_cycles`) with error recovery.

---

## 8. Verification Method

To independently verify the completeness and compliance of this specification:
1. Review `ORIGINAL_REQUEST.md` (§R4 and Client Daemon criteria) against Section 1 of this report.
2. Verify that all 29 test cases in Section 5 correspond to the required functional areas.
3. When Milestone 4 implementation is written, execute:
   ```bash
   pytest tests/test_native_worker.py -v
   ```
4. Verify end-to-end integration with the coordinator:
   ```bash
   pytest tests/test_distributed_e2e.py -v
   ```
