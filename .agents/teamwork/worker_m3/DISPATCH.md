## 2026-11-21T00:19:10Z
You are worker_m3.
Working directory: /home/targed/Documents/Git/shape-packing/.agents/teamwork/worker_m3
Exclusively owned files:
- `src/shape_packing/server/app.py`
- `tests/test_server_api.py`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Context & Inputs:
- Read /home/targed/Documents/Git/shape-packing/.agents/teamwork/ORIGINAL_REQUEST.md (§R3)
- Read /home/targed/Documents/Git/shape-packing/.agents/teamwork/orchestrator_1/PROJECT.md
- Read docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md
- Read docs/superpowers/plans/2026-11-20-distributed-shape-packing.md (Task 3)
- Read /home/targed/Documents/Git/shape-packing/.agents/teamwork/explorer_m3_1/handoff.md
- Read /home/targed/Documents/Git/shape-packing/.agents/teamwork/explorer_m3_2/handoff.md
- Read /home/targed/Documents/Git/shape-packing/.agents/teamwork/spec_miner_m3_1/handoff.md

Your Task:
1. Implement the Coordinator REST API in `src/shape_packing/server/app.py`:
   - Factory `create_app(db_path: str = "shape_packing.db") -> FastAPI`
   - DB connection dependency `get_db(request: Request)` yielding a connection per request and closing safely in `finally`.
   - Endpoints:
     - `POST /api/v1/workers/register`: Register worker with username & client_type.
     - `GET /api/v1/work`: Call `assign_work(conn, worker_id, cores, lease_seconds)`. Return HTTP 204 No Content with empty body when `assign_work` returns None; return HTTP 200 with work dict when work is leased.
     - `POST /api/v1/solutions`: In-process geometric SAT verification.
       - Validate `len(coordinates) == 3 * n`.
       - Compute circumradius $S$ via `inverse_friedman_metric(metric_s, inner_token, container_token)`.
       - Write temporary values-style JSON file and call `solution_tools.verify_solution(temp_path, problem_id, check_record=False)`.
       - If invalid (overlap, boundary violation), return HTTP 400 Bad Request with `{"status": "rejected", "verified": False, "message": str}`.
       - If valid, invoke `update_solution_record(...)`. Return HTTP 200 OK with `{"status": "accepted"|"duplicate", "verified": True, "is_new_record": bool, "metric_s": float, "message": str}`.
     - `POST /api/v1/heartbeat`: Call `record_heartbeat`. Return HTTP 200 OK with `{"status": "recorded"|"ignored"}`.
     - `GET /api/v1/stats`: Return cluster stats (total_problems, active_workers, total_attempts, records_broken).
     - `GET /api/v1/leaderboard`: Return top workers by records broken and total attempts.
     - `GET /api/v1/problems/{problem_id}`: Retrieve problem metadata.
2. Implement comprehensive tests in `tests/test_server_api.py`:
   - Use `fastapi.testclient.TestClient`.
   - Test worker registration (happy path, empty username, duplicate username).
   - Test work leasing (happy path, 204 when no work available, invalid cores, invalid worker).
   - Test solution verification (valid solution accepting new record, valid duplicate, overlapping shapes rejected with 400, shapes outside boundary rejected with 400, mismatched coordinate count rejected with 400).
   - Test heartbeat reporting (valid active lease, zero keepalive, expired lease).
   - Test stats and leaderboard endpoints.
   - Test problem lookup endpoint.
3. Run the full server test suite:
   ```bash
   pytest tests/test_server_api.py tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py -v
   ```
   Ensure 100% of tests pass with 0 failures.
4. Document all changes, files touched, and verification command output in `/home/targed/Documents/Git/shape-packing/.agents/teamwork/worker_m3/handoff.md`.
5. Send a message to parent upon completion.
