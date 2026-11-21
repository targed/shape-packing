## 2026-11-21T03:49:21Z
You are challenger_m4_1, a teamwork_preview_challenger challenging Milestone 4: Native Worker Client Daemon.

Working Directory: /home/targed/Documents/Git/shape-packing/.agents/teamwork/challenger_m4_1
Workspace Root: /home/targed/Documents/Git/shape-packing

MANDATORY FIRST ACTIONS:
1. Initialize BRIEFING.md, DISPATCH.md, and progress.md in your working directory.
2. Read ORIGINAL_REQUEST.md:
   /home/targed/Documents/Git/shape-packing/.agents/teamwork/ORIGINAL_REQUEST.md
3. Read worker handoff:
   /home/targed/Documents/Git/shape-packing/.agents/teamwork/worker_m4_1/handoff.md

CHALLENGE MISSION:
Empirically stress-test the networking and resilience of `src/shape_packing/client/native_worker.py`.
Write and execute an adversarial stress test script (e.g. `tests/test_native_worker_stress.py`).

TEST VECTORS TO ADVERSARIALLY EXECUTE:
1. Transient network drop simulation: mock `send_request` or `urllib.request.urlopen` dropping 1, 2, 3 packets with 500/503 errors and verify exponential backoff and recovery.
2. HTTP 204 starve-to-work transition: verify that worker properly sleeps `poll_interval` during 204 starvation without CPU spinning or memory leakage, and immediately picks up work when it appears.
3. Malformed coordinator responses: simulate truncated JSON, corrupted headers, HTTP 400 rejection responses with custom JSON errors, verify client does not crash and logs/surfaces error diagnostics.
4. Loopback proxy pollution: test with `http_proxy=http://127.0.0.1:9999` in `os.environ` and verify loopback requests to `127.0.0.1` and `localhost` bypass the invalid proxy and succeed.

DELIVERABLE:
Write your challenge report to `/home/targed/Documents/Git/shape-packing/.agents/teamwork/challenger_m4_1/handoff.md` with explicit verdict: **APPROVE** or **REQUEST_CHANGES**.
Then notify parent with `send_message`.
