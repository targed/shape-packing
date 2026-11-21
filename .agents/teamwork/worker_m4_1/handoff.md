# Milestone 4 Handoff Report: Native Worker Client Daemon

**Worker**: `worker_m4_1`  
**Milestone**: Milestone 4 (Native Worker Client Daemon)  
**Status**: COMPLETE (Hard Handoff)  
**Files Created/Owned**:
- `src/shape_packing/client/__init__.py`
- `src/shape_packing/client/native_worker.py`
- `tests/test_native_worker.py`

---

## 1. Observation

1. **System & Spec Contracts**:
   - `ORIGINAL_REQUEST.md` (§R4): Mandated a Python worker client in `src/shape_packing/client/native_worker.py` that connects to the coordinator using Python standard library `urllib` exclusively (no `requests`, `httpx`, `aiohttp`, `urllib3`), executes search batches at idle OS priority, immediately submits improved configurations, and flushes heartbeats gracefully on SIGINT/SIGTERM.
   - `spec_miner_m4_1/handoff.md`: Specified 29 required tests across 9 categories covering configuration, stdlib networking (GET, POST, 204 empty body, 400 Bad Request error payload extraction, timeout, connection refused), worker registration, 204 polling backoff, heartbeat reporting, solution submission, cross-platform idle priority (`nice(19)`), signal graceful shutdown, and single/multi-cycle execution.
   - `explorer_m4_1/handoff.md`: Observed that `urllib.request.urlopen` routes `127.0.0.1` and `localhost` through proxies in environments exporting `http_proxy` unless loopback proxy bypass (`urllib.request.ProxyHandler({})`) is configured.
   - `explorer_m4_2/handoff.md`: Observed that `solver_interface.run_solver` uses argument `n_shapes` (not `n`) and returns metric under key `"score"` (or `"best_s"`, `"final_metric"`, `"S"`), and coordinates under `"values"` or `"coordinates"`.

2. **Test & Runtime Execution**:
   - Running `pytest tests/test_native_worker.py tests/test_server_api.py -v`:
     ```
     ======================== 63 passed, 1 warning in 0.68s =========================
     ```
   - Running full distributed server and worker test suite (`pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_api.py tests/test_native_worker.py -v`):
     ```
     ======================== 162 passed, 1 warning in 2.12s ========================
     ```
   - AST inspection test `test_zero_external_networking_dependencies`: Passed, confirming zero imports of `requests`, `httpx`, `aiohttp`, or `urllib3` in `src/shape_packing/client/native_worker.py`.
   - `python3 -m py_compile src/shape_packing/client/__init__.py src/shape_packing/client/native_worker.py tests/test_native_worker.py`: Exited 0 with no errors.

---

## 2. Logic Chain

1. **Zero External Networking Dependencies**:
   - Derived directly from Requirement R4 and pyproject.toml inspection.
   - Built `send_request` utilizing `urllib.request.Request`, UTF-8 JSON encoding, and automatic `ProxyHandler({})` for loopback addresses (`127.0.0.1`, `localhost`, `::1`).
   - Implemented HTTP status handling: HTTP 200 returns parsed JSON; HTTP 204 returns `{}` without raising `JSONDecodeError`; HTTP 400 extracts server JSON error payload into `exc.error_data` and restores `exc.fp` / `exc.read` so callers can inspect diagnostics; network drops and timeouts raise `urllib.error.URLError`.

2. **Configuration Normalization & Environment Ingestion**:
   - Created `WorkerConfig` dataclass with all required fields: `server_url`, `username`, `client_type`, `worker_id`, `cores`, `poll_interval`, `heartbeat_interval`, `timeout`, `max_backoff`, `coordinator_url`.
   - Implemented `__post_init__` to strip trailing slashes (`.rstrip('/')`), synchronize `server_url` with `coordinator_url`, and validate `cores >= 1`.
   - Implemented `WorkerConfig.from_env(**overrides)` reading `SHAPE_PACKING_SERVER_URL`, `SHAPE_PACKING_USERNAME`, `SHAPE_PACKING_CORES`, and `SHAPE_PACKING_WORKER_ID`.

3. **Cross-Platform Idle Scheduling**:
   - Implemented `set_process_idle_priority()` (aliased to `set_idle_priority`).
   - On POSIX, sets niceness to 19 via `os.nice(19)` or `os.setpriority(os.PRIO_PROCESS, 0, 19)`. On Windows, calls `ctypes.windll.kernel32.SetPriorityClass` with `0x00000040` (`IDLE_PRIORITY_CLASS`).
   - Safely wrapped in `try/except (OSError, PermissionError, AttributeError)` returning a boolean, ensuring zero crashes on restricted containers or unprivileged runtimes.

4. **Thread-Safe Heartbeat Telemetry & In-Flight Flush**:
   - Implemented `HeartbeatReporter` running a background daemon thread that flushes accumulated attempts incrementally to `/api/v1/heartbeat`.
   - Implemented thread-safe atomic lock protection; on network errors, unacknowledged attempts are re-credited to `_unreported_attempts` to avoid compute tally loss.
   - Added `flush_in_flight_heartbeat(config)` to report in-flight attempts upon graceful shutdown.

5. **Solver Execution Bridge**:
   - Implemented `_invoke_solver` and `run_worker_cycle` interfacing with `solver_interface.run_solver(n_shapes=...)`.
   - Normalized metrics across `best_s`, `score`, `final_metric`, and `S`. Normalized coordinates across `values` and `coordinates`.
   - Verified that when `success` is True and `metric_s < target_s` (or when `target_s` is None), candidate solution coordinates are immediately submitted to `POST /api/v1/solutions`.

6. **Signal Handling & Execution Loops**:
   - Implemented `handle_signal` and `setup_signal_handlers` intercepting `SIGINT` and `SIGTERM`, setting `_SHUTDOWN = True` and unblocking `_GLOBAL_STOP_EVENT`.
   - Implemented `run_worker_cycle` for single-cycle execution and `run_worker_loop` for multi-cycle execution with 204 backoff sleep (`time.sleep(config.poll_interval)`) and exponential backoff retry on transient transport faults.
   - Implemented CLI `main()` entrypoint with `argparse`.

7. **Comprehensive Test Coverage**:
   - Built `tests/test_native_worker.py` containing 32 test cases (covering all 29 spec miner requirements plus AST inspection, loopback proxy bypass, and CLI entrypoint).

---

## 3. Caveats

1. **Proxy Traversal in Enterprise Networks**:
   - The empty `ProxyHandler({})` is explicitly restricted to loopback addresses (`127.0.0.1`, `localhost`, `::1`). If a remote coordinator URL is used, urllib uses standard system environment proxy configurations.
2. **Subprocess Signal Propagation**:
   - Signal handlers catch `SIGINT` and `SIGTERM` on Python's main thread. In environments where worker processes run as child processes, signals to the process group trigger the handler which unblocks the loop and performs a final heartbeat flush before exit.
3. **No Third-Party Networking Libraries**:
   - Verified strictly via AST inspection test (`test_zero_external_networking_dependencies`) that `requests`, `httpx`, `aiohttp`, and `urllib3` are nowhere imported.

---

## 4. Conclusion

Milestone 4 (Native Worker Client Daemon) is fully implemented, verified, and passing all tests without third-party networking dependencies. The implementation adheres strictly to the REST API contracts of the coordinator server, supports cross-platform idle CPU execution, performs incremental heartbeat reporting, submits candidate improvements, and shuts down gracefully with attempt flushing.

---

## 5. Verification Method

To independently verify this milestone:

1. **Run Native Worker and Server API Unit Tests**:
   ```bash
   pytest tests/test_native_worker.py tests/test_server_api.py -v
   ```
   *Expected output*: 63 passed, 0 failures.

2. **Run Full Server & Worker Distributed Suite**:
   ```bash
   pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_api.py tests/test_native_worker.py -v
   ```
   *Expected output*: 162 passed, 0 failures.

3. **Run AST Prohibited Dependency Inspection**:
   ```bash
   pytest tests/test_native_worker.py -k test_zero_external_networking_dependencies -v
   ```
   *Expected output*: PASSED (0 occurrences of `requests`, `httpx`, `aiohttp`, `urllib3`).

4. **Verify Syntax & Type Compilation**:
   ```bash
   python3 -m py_compile src/shape_packing/client/__init__.py src/shape_packing/client/native_worker.py tests/test_native_worker.py
   ```
   *Expected output*: Exit code 0, no warnings or syntax errors.
