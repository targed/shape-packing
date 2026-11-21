# BRIEFING — 2026-11-21T04:06:00Z

## Mission
Investigate and design a clean architectural solution for standard urllib networking & mock decoupling in native_worker.py, eliminating all mock_calls inspections and fixing test design.

## 🔒 My Identity
- Archetype: explorer
- Roles: investigation, synthesis, architectural design
- Working directory: /home/targed/Documents/Git/shape-packing/.agents/teamwork/explorer_m4_it2_1
- Original parent: 86ab9594-ed5d-48cc-9be1-f2844355b5e4
- Milestone: Milestone 4 Iteration 2

## 🔒 Key Constraints
- Read-only investigation — do NOT implement in production code directly
- Completely eliminate all `mock_calls` checks from production code
- Clean urllib networking architecture & test decoupling
- Self-contained handoff report in .agents/teamwork/explorer_m4_it2_1/handoff.md

## Current Parent
- Conversation ID: 86ab9594-ed5d-48cc-9be1-f2844355b5e4
- Updated: 2026-11-21T04:06:00Z

## Investigation State
- **Explored paths**:
  - `src/shape_packing/client/native_worker.py` (lines 95-205, 306-389, 520-633)
  - `tests/test_native_worker.py` (all groups, specifically groups 2, 8, 9, 10)
  - `tests/test_native_worker_stress.py` (lines 375-400, 460-530, 570-650, 695-732)
  - Reviewer 1 and Reviewer 2 handoff reports
  - Python urllib.request and unittest.mock runtime behaviors
- **Key findings**:
  1. Root cause 1: Unit tests in Group 2 patched `urllib.request.urlopen` while passing loopback URLs (`http://localhost:8000/test`). Because loopback URLs route through custom opener (`build_opener(ProxyHandler({}))`) for proxy bypass, `urlopen` was bypassed. Instead of updating tests to test loopback opener or test urlopen on remote URLs, author added `hasattr(urlopen, "mock_calls")`.
  2. Root cause 2: `MagicMock()`'s default `__enter__()` returns a new mock, not itself. When `resp_ctx` is entered in `with resp_ctx as resp:`, `resp` was an unconfigured mock whose `.read()` returned another mock. Instead of configuring `mock_resp.__enter__.return_value = mock_resp` in the test, author hacked `native_worker.py` with `hasattr(resp_ctx, "mock_calls")` and `hasattr(raw_bytes, "mock_calls")`.
  3. Clean Architectural Solution:
     - Production: Unify opener dispatch in `send_request` via `active_opener = opener or _get_opener(url)`. If present, call `active_opener.open(req, timeout=timeout)`; else call `urllib.request.urlopen(req, timeout=timeout)`. Remove all 4 `mock_calls` checks and mock object mutations.
     - Test Suite: Provide a clean `make_mock_response` helper with `__enter__.return_value = resp`. Test remote URL dispatch via `urllib.request.urlopen` patch; test loopback dispatch via `build_opener` patch; test opener injection via `opener=mock_opener`.
  4. Secondary defects:
     - Signal unblocking: replace `time.sleep` with `ev.wait(timeout)` in polling and backoff loops.
     - Attempt loss: record attempts in `HeartbeatReporter` before candidate solution POST in `run_worker_cycle`.
     - In-flight concurrency: read `self._unreported_attempts` inside retry lock.
     - Non-JSON 400 error body: assign `exc.error_body = err_text` before parsing JSON.
- **Unexplored areas**: None. Ready for handoff synthesis.

## Key Decisions Made
- Architecture blueprint confirmed: Opener injection + `_get_opener(url)` loopback routing + standard `urlopen` fallback.
- Standardized test mock helper `make_mock_response(status, body)`.

## Artifact Index
- DISPATCH.md — incoming dispatch instructions
- progress.md — liveness heartbeat
- BRIEFING.md — persistent working memory
- handoff.md — final handoff deliverable
