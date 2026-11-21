# BRIEFING — 2026-11-21T04:06:00Z

## Mission
Mine complete specification diff and test matrix needed for Milestone 4 Iteration 2 remediation on native worker client.

## 🔒 My Identity
- Archetype: teamwork_preview_spec_miner
- Roles: Specification Miner
- Working directory: /home/targed/Documents/Git/shape-packing/.agents/teamwork/spec_miner_m4_it2_1
- Original parent: 86ab9594-ed5d-48cc-9be1-f2844355b5e4
- Milestone: Milestone 4 Iteration 2

## 🔒 Key Constraints
- Zero mock_calls in production code. Provide exact AST check or grep assertion to guarantee no test framework sniffing.
- Signal-responsive sleep specification: ev.wait(timeout) instead of time.sleep().
- Compute attempt telemetry preservation: ensure attempts are recorded before solution submission or inside try...finally.
- Non-JSON HTTP 400 response body preservation: ensure exc.error_body = err_text is set before attempting JSON parse.
- Identify all tests across unit, stress, and concurrency suites that will be impacted or need adjustment.
- Do NOT implement anything — read-only specification mining and analysis.
- Write report to /home/targed/Documents/Git/shape-packing/.agents/teamwork/spec_miner_m4_it2_1/handoff.md.

## Current Parent
- Conversation ID: 86ab9594-ed5d-48cc-9be1-f2844355b5e4
- Updated: 2026-11-21T04:00:00Z

## Task Summary
- **What to build**: Specification report detailing the exact requirements, edge cases, error behaviors, AST assertions, code diff specifications, and impacted test matrix for Iteration 2 remediation.
- **Success criteria**: Comprehensive specification covering all 5 investigation points with exact behavioral definitions, test impacts, and verification methods.
- **Interface contracts**: /home/targed/Documents/Git/shape-packing/.agents/teamwork/ORIGINAL_REQUEST.md
- **Code layout**: src/shape_packing/client/native_worker.py, tests/test_native_worker*.py

## Key Decisions Made
- [Initial]: Established baseline briefing for M4 It2 specification mining.
- [Mined Root Cause]: Discovered that `mock_calls` was introduced due to unit tests passing `http://localhost:8000/...` to `send_request` while patching `urllib.request.urlopen`, colliding with loopback proxy bypass that used `build_opener()`.
- [Mined Context Manager Root Cause]: Discovered `resp_ctx.__enter__.return_value = resp_ctx` in production was compensating for tests using `MagicMock()` without configuring `mock_resp.__enter__.return_value = mock_resp`.
- [Mined Sleep Blocking]: Verified Python PEP 475 causes `time.sleep` to restart on handled signals, whereas `ev.wait(timeout)` wakes up in < 0.001s when signaled.
- [Mined Test Impact Matrix]: Identified 11 tests in `test_native_worker_stress.py` and 2 tests in `test_native_worker.py` that currently mock `time.sleep` and must be adjusted to mock/intercept `ev.wait`.
- [Mined Attempt Loss]: Verified that moving `reporter.record_attempts` before solution POST guarantees completed compute attempts are flushed on HTTP 400 or network timeout via `finally: reporter.stop()`.
- [Mined Error Body Wipeout]: Verified setting `exc.error_body = err_text` before `json.loads` preserves plaintext/HTML 400 error payloads.

## Artifact Index
- DISPATCH.md — Dispatch instructions
- BRIEFING.md — Situational awareness
- progress.md — Liveness heartbeat and milestone tracking
- handoff.md — Complete specification mining deliverable
