## 2026-11-21T03:38:54Z

You are worker_m4_1, a teamwork_preview_worker responsible for implementing Milestone 4: Native Worker Client Daemon in the shape-packing distributed system.

Working Directory: /home/targed/Documents/Git/shape-packing/.agents/teamwork/worker_m4_1
Workspace Root: /home/targed/Documents/Git/shape-packing

MANDATORY FIRST ACTIONS:
1. Initialize your BRIEFING.md, DISPATCH.md, and progress.md in your working directory.
2. Read ORIGINAL_REQUEST.md:
   /home/targed/Documents/Git/shape-packing/.agents/teamwork/ORIGINAL_REQUEST.md
3. Read the three exploration and specification handoff reports:
   - /home/targed/Documents/Git/shape-packing/.agents/teamwork/explorer_m4_1/handoff.md
   - /home/targed/Documents/Git/shape-packing/.agents/teamwork/explorer_m4_2/handoff.md
   - /home/targed/Documents/Git/shape-packing/.agents/teamwork/spec_miner_m4_1/handoff.md

EXCLUSIVE FILE WRITE OWNERSHIP:
- src/shape_packing/client/__init__.py
- src/shape_packing/client/native_worker.py
- tests/test_native_worker.py

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

SPECIFICATION REQUIREMENTS (R4):
1. Client Networking (stdlib urllib ONLY):
   - Zero third-party networking dependencies (forbidden: `requests`, `httpx`, `aiohttp`, `urllib3`).
   - Implement `send_request(url, method="GET", payload=None, timeout=10.0)` using `urllib.request`.
   - Configure proxy bypass for loopback addresses (`127.0.0.1`, `localhost`, `::1`) using `urllib.request.ProxyHandler({})` so environment proxies don't intercept local requests.
   - Correctly handle HTTP 200 (parse JSON), HTTP 204 No Content (return empty dict `{}` without raising JSONDecodeError), HTTP 400 Bad Request (extract server error JSON message), timeouts, and connection errors.
2. Worker Configuration (`WorkerConfig` dataclass):
   - Fields: `server_url`, `username`, `client_type="native"`, `worker_id=None`, `cores=1`, `poll_interval=5.0`, `heartbeat_interval=30.0`, `timeout=10.0`, `max_backoff=60.0`, `coordinator_url=None`.
   - Strip trailing slashes on URLs (`.rstrip('/')`). Support `.from_env()` ingesting `SHAPE_PACKING_SERVER_URL`, `SHAPE_PACKING_USERNAME`, `SHAPE_PACKING_CORES`, `SHAPE_PACKING_WORKER_ID`. Validate `cores >= 1`.
3. Worker Registration & Helpers:
   - `register_with_server(server_url: str, username: str, worker_id: Optional[str] = None) -> str`
4. OS Priority Scheduling:
   - `set_process_idle_priority() -> bool`: sets idle OS priority via `os.setpriority(os.PRIO_PROCESS, 0, 19)` / `os.nice(19)` on POSIX, `ctypes.windll.kernel32.SetPriorityClass` on Windows, safely wrapped in try/except returning boolean.
5. Heartbeat Daemon (`HeartbeatReporter`):
   - Thread-safe background reporter that flushes completed attempts incrementally to `/api/v1/heartbeat`. On shutdown or cycle end, performs a final flush.
6. Solver Execution Bridge:
   - Interfaces with `solver_interface.run_solver(n_shapes=..., inner_shape=..., container_shape=..., attempts=..., target_s=...)`.
   - Normalizes return fields: metric from `best_s`, `score`, or `final_metric`; coordinates from `values` or `coordinates`.
   - If improvement found (`metric_s < target_s` and `success`), immediately submits candidate to `/api/v1/solutions`.
7. Signal Handling & Graceful Shutdown:
   - Intercepts SIGINT and SIGTERM, sets `stop_event`, finishes active compute, flushes completed attempts to `/api/v1/heartbeat`, and exits cleanly.
8. Execution Cycles:
   - `run_worker_cycle(config, stop_event=None, max_cycles=1, solver_fn=None, request_fn=None)` supporting both single-cycle unit execution and continuous bounded/unbounded loops with 204 backoff sleep.
   - `main()` CLI entrypoint with `argparse`.
9. Comprehensive Test Suite (`tests/test_native_worker.py`):
   - Implement all 29 tests specified in `spec_miner_m4_1/handoff.md` across all 9 categories.
   - Must include an AST inspection test verifying zero imports of `requests`, `httpx`, `aiohttp`, or `urllib3` in `native_worker.py`.

VERIFICATION:
Run pytest to verify your tests pass:
`pytest tests/test_native_worker.py tests/test_server_api.py -v`
Ensure all tests pass 100% with 0 failures.

DELIVERABLE:
Write your complete handoff report to `/home/targed/Documents/Git/shape-packing/.agents/teamwork/worker_m4_1/handoff.md` following the 5-component format (Observation, Logic Chain, Caveats, Conclusion, Verification Method).
Then notify parent with `send_message`.
