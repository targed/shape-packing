## 2026-11-20T23:33:25Z
You are the Worker for Milestone 2: Work Scheduler and Priority Allocator.

Your working directory is: /home/targed/Documents/Git/shape-packing/.agents/teamwork/worker_m2

You MUST read the following authoritative sources before starting work:
- /home/targed/Documents/Git/shape-packing/.agents/teamwork/ORIGINAL_REQUEST.md
- /home/targed/Documents/Git/shape-packing/.agents/teamwork/orchestrator_1/PROJECT.md
- /home/targed/Documents/Git/shape-packing/.agents/teamwork/explorer_m2_1/handoff.md
- /home/targed/Documents/Git/shape-packing/.agents/teamwork/explorer_m2_2/handoff.md
- /home/targed/Documents/Git/shape-packing/.agents/teamwork/spec_miner_m2_1/handoff.md

Domain skill:
Please read and follow /home/targed/.gemini/config/skills/python-testing-patterns/SKILL.md

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

File write ownership:
You exclusively own and may edit:
- src/shape_packing/server/scheduler.py
- tests/test_server_scheduler.py

Key implementation requirements:
1. In src/shape_packing/server/scheduler.py:
   - expire_stale_leases(conn: sqlite3.Connection) -> int
     Deletes from active_leases where expires_at <= CURRENT_TIMESTAMP.
   - assign_work(conn: sqlite3.Connection, worker_id: str, cores: int = 1, lease_seconds: int = 300) -> Optional[Dict[str, Any]]
     - Auto-register worker or ensure worker_id exists in workers table before inserting lease (avoiding foreign key failure).
     - Call expire_stale_leases first.
     - Multi-armed bandit policy:
       - Strictly exclude LOWER(status) = 'proved_optimal'.
       - 10% probability exploration over unattempted candidates (status='unattempted' or total_attempts=0).
       - 90% exploitation: unleased candidates (l.work_id IS NULL), stuck backoff (>50k attempts without improvement decays priority), closeness boost (within 1% of baseline record prioritized), attempt count fair balancing (total_attempts ASC), density rank void space (density_rank DESC), random tie-breaker.
       - Fallback: if all eligible candidates are currently leased, fall back to shared leasing across non-proved_optimal candidates.
       - If no eligible problems exist, return None.
     - Calculate recommended_attempts = max(1000, min(max(1, int(cores)) * 1000, 20000)).
     - UTC expires_at formatted as '%Y-%m-%d %H:%M:%S' via datetime.datetime.now(datetime.timezone.utc).
     - Atomic BEGIN IMMEDIATE transaction for lease creation.
     - Return dict: {work_id, problem, inner_token, container_token, n, target_s, recommended_attempts, lease_seconds}.
   - record_heartbeat(conn: sqlite3.Connection, work_id: str, worker_id: str, attempts: int, best_s: Optional[float] = None) -> bool
     - Validate attempts >= 0 (reject negative).
     - BEGIN IMMEDIATE transaction.
     - Verify lease in active_leases. If active: increment problems.total_attempts += attempts.
     - Update workers: total_attempts += attempts, last_seen_at = CURRENT_TIMESTAMP.
     - Return True if recorded; if lease not found, credit worker attempts and return False.
     - NEVER update problems.best_s in heartbeat.
2. Comprehensive test suite in tests/test_server_scheduler.py:
   - Verify proved_optimal exclusion under all conditions.
   - Verify lease expiry reassigns problem.
   - Verify record_heartbeat updates problem and worker attempt tallies.
   - Verify closeness boost priority.
   - Verify stuck problem backoff.
   - Verify fallback shared assignment when all problems leased.
   - Verify empty catalog returns None.
   - Verify concurrent assign_work serialization (no duplicate leases on separate problems).
   - Verify attempt scaling across 1, 4, 16, 64 cores.
3. Run pytest tests/test_server_scheduler.py -v and ensure 100% pass with 0 failures.

Write your handoff report to:
/home/targed/Documents/Git/shape-packing/.agents/teamwork/worker_m2/handoff.md
Send a completion message back to your caller when done.
