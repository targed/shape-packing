## 2026-11-20T23:57:44Z
You are worker_m2_it2.
Working directory: /home/targed/Documents/Git/shape-packing/.agents/teamwork/worker_m2_it2
Exclusively owned file: `src/shape_packing/server/scheduler.py`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Context & Inputs:
- Read /home/targed/Documents/Git/shape-packing/.agents/teamwork/ORIGINAL_REQUEST.md
- Read /home/targed/Documents/Git/shape-packing/.agents/teamwork/orchestrator_1/PROJECT.md
- Read /home/targed/Documents/Git/shape-packing/.agents/teamwork/challenger_m2_2/handoff.md
- Read /home/targed/Documents/Git/shape-packing/.agents/teamwork/explorer_m2_it2_1/handoff.md
- Read /home/targed/Documents/Git/shape-packing/.agents/teamwork/explorer_m2_it2_2/handoff.md
- Read /home/targed/Documents/Git/shape-packing/.agents/teamwork/spec_miner_m2_it2_1/handoff.md

Your Task:
1. Apply the verified surgical fix to `src/shape_packing/server/scheduler.py`:
   - In `assign_work`: Remove lines 123-136 (the inner fallback query during exploration that re-selects already-leased unattempted problems). When Query 1 finds no unleased unattempted problems, `prob` must remain `None`, seamlessly falling through to line 138 (exploitation query for unleased candidates across the catalog).
   - In `assign_work`: Expand exception handlers when casting `cores` and `lease_seconds` to catch `(ValueError, TypeError, OverflowError)`. Clamp `lease_seconds` to an upper bound (e.g. `min(max(1, ls), 604800)`) so large/infinite values don't break `datetime.timedelta`.
   - In `record_heartbeat`: Guard against integer overflow where `attempts > 2**63 - 1` or `best_s > 1e308` (return `False` if out of bounds).
2. Run the full regression test suite:
   ```bash
   pytest tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py tests/test_server_database.py -v
   ```
   Verify 100% of tests pass (147 tests, 0 failures).
3. Document what changed, verification commands and output in `/home/targed/Documents/Git/shape-packing/.agents/teamwork/worker_m2_it2/handoff.md`.
4. Send a message to parent upon completion.
