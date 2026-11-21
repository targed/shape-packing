## 2026-11-20T23:25:55Z
You are an Explorer for Milestone 2: Work Scheduler and Priority Allocator.

Your working directory is: /home/targed/Documents/Git/shape-packing/.agents/teamwork/explorer_m2_1

You MUST read the following authoritative sources:
- /home/targed/Documents/Git/shape-packing/.agents/teamwork/ORIGINAL_REQUEST.md
- /home/targed/Documents/Git/shape-packing/.agents/teamwork/orchestrator_1/PROJECT.md
- /home/targed/Documents/Git/shape-packing/docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md
- /home/targed/Documents/Git/shape-packing/docs/superpowers/plans/2026-11-20-distributed-shape-packing.md
- /home/targed/Documents/Git/shape-packing/src/shape_packing/server/database.py

Investigate:
1. The multi-armed bandit scheduling policy in design spec §5:
   - Exclusion: strictly exclude configurations marked proved_optimal.
   - Exclusion of currently leased problems (active_leases), with fallback to sharing if all problems leased.
   - Exploitation: ranking by geometric void space / density rank (rho = N * A_inner / A_container(s)), closeness to baseline record, attempt count.
   - Exploration and stuck backoff (>50k attempts without improvement decays priority weight, 10% uniform random selection).
2. Recommended algorithm and SQL query structure for assign_work(conn, worker_id, cores, lease_seconds).
3. Recommended attempts calculation based on cores (e.g. max(1000, min(cores * 1000, 20000))).

Write your findings report to:
/home/targed/Documents/Git/shape-packing/.agents/teamwork/explorer_m2_1/handoff.md
Send a completion message back to your caller when done.
