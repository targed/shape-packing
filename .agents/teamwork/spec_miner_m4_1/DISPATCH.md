## 2026-11-21T00:37:48Z
You are spec_miner_m4_1.
Working directory: /home/targed/Documents/Git/shape-packing/.agents/teamwork/spec_miner_m4_1

Your task:
1. Read /home/targed/Documents/Git/shape-packing/.agents/teamwork/ORIGINAL_REQUEST.md (§R4)
2. Read docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md (§4)
3. Read docs/superpowers/plans/2026-11-20-distributed-shape-packing.md (Task 4)
4. Mine and enumerate all functional features, constraints, error conditions, and test cases for Milestone 4 (Native Worker Client Daemon):
   - Constraints: zero external network dependencies (stdlib `urllib` only), idle priority (`os.nice(19)`), clean SIGINT/SIGTERM shutdown.
   - Enumerate all test cases required for `tests/test_native_worker.py`:
     - Config initialization (defaults, env vars, overrides)
     - `send_request` with `urllib` (GET, POST, 200, 204, 400, timeout, connection refused)
     - Worker registration flow
     - Work polling loop with 204 backoff
     - Heartbeat emission during execution
     - Solution submission on improvement
     - Idle priority setting (`os.nice` verification and mock fallback)
     - Signal handling and graceful shutdown (SIGINT/SIGTERM flush)
     - Single-cycle and multi-cycle execution
5. Write your detailed specification to `/home/targed/Documents/Git/shape-packing/.agents/teamwork/spec_miner_m4_1/handoff.md` and notify parent.
