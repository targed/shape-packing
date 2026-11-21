## 2026-11-20T23:25:55Z
You are a Spec Miner for Milestone 2: Work Scheduler and Priority Allocator.

Your working directory is: /home/targed/Documents/Git/shape-packing/.agents/teamwork/spec_miner_m2_1

You MUST read the following authoritative sources:
- /home/targed/Documents/Git/shape-packing/.agents/teamwork/ORIGINAL_REQUEST.md
- /home/targed/Documents/Git/shape-packing/.agents/teamwork/orchestrator_1/PROJECT.md
- /home/targed/Documents/Git/shape-packing/docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md
- /home/targed/Documents/Git/shape-packing/docs/superpowers/plans/2026-11-20-distributed-shape-packing.md
- /home/targed/Documents/Git/shape-packing/src/shape_packing/server/database.py

Mine and document:
1. Exact functional requirements and interfaces for Task 2 / Milestone 2:
   - assign_work(conn: sqlite3.Connection, worker_id: str, cores: int = 1, lease_seconds: int = 300) -> Optional[Dict[str, Any]]
   - record_heartbeat(conn: sqlite3.Connection, work_id: str, worker_id: str, attempts: int, best_s: Optional[float] = None) -> bool
   - expire_stale_leases(conn: sqlite3.Connection) -> int
2. Return dictionary schema for assign_work (work_id, problem, inner_token, container_token, n, target_s, recommended_attempts, lease_seconds).
3. Required unit and integration tests for tests/test_server_scheduler.py.
4. Input validation and edge case specifications.

Write your specification report to:
/home/targed/Documents/Git/shape-packing/.agents/teamwork/spec_miner_m2_1/handoff.md
Send a completion message back to your caller when done.
