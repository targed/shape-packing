# Security Best Practices & Code Review Report

Audit of the `shape-packing` coordinator server, verification core, worker clients, Astro frontend, and CI/CD workflows using `/security-review`, `/security-threat-model`, and `/security-best-practices`.

## Executive Summary
The most urgent gaps before public launch are:
1. Unauthenticated endpoints on Azure App Service Free F1 (including fail-open `/api/v1/export/db`, worker impersonation via `/register`/`/deregister`, fake attempt inflation via `/heartbeat`, and unbounded `/solutions` payloads).
2. A confirmed DOM XSS sink in `site/src/pages/contribute.astro:374` paired with an unvalidated `?coordinator=` query override in `site/src/lib/api.ts:40-44`.
3. Missing body size caps, per-request `init_db()` overhead, permissive CORS (`allow_credentials=True` + `allow_private_network=True`), and CI supply-chain pinning gaps.

---

## Findings by Severity

### High Severity

- **SEC-01: DOM XSS via Untrusted `data.problem` in `addCalculationLog`**
  - **Location:** `site/src/pages/contribute.astro:374`, fed by `site/src/lib/workers/wasm_packer_worker.ts:39, 48, 68`
  - **Impact:** A malicious or compromised coordinator URL returns HTML/JS in `work.problem`, executing arbitrary JavaScript inside the GitHub Pages origin.
  - **Remediation:** Construct log elements with `document.createElement` and `.textContent` instead of `left.innerHTML`, and reject non-string or oversized `work` fields in `wasm_packer_worker.ts`.

- **SEC-02: Unvalidated `?coordinator=` URL Query Override**
  - **Location:** `site/src/lib/api.ts:40-48` and `site/src/pages/contribute.astro:414, 420`
  - **Impact:** Crafted links (`?coordinator=https://evil.example` or `?coordinator=http://127.0.0.1:...`) hijack dashboard fetches, spoof cluster/leaderboard data, or probe loopback ports.
  - **Remediation:** Enforce a strict `validateCoordinatorUrl()` helper. On public read-only pages (`index`, `leaderboard`, `results`), restrict `?coordinator=` to allowlisted official origins (`https://shape-packing-ggd4d5e8c2ctggam.eastus-01.azurewebsites.net`, `http://localhost:8000`, `http://127.0.0.1:8000`). In `contribute.astro`, allow `https://` or loopback `http://(localhost|127.0.0.1)` origins only.

- **SEC-03: Fail-Open Database Export & Full-File Memory Buffering**
  - **Location:** `src/shape_packing/server/app.py:603-632`, `.github/workflows/sync-azure-db.yml:20`
  - **Impact:** Anyone can download the entire live SQLite database while `SHAPE_PACKING_BACKUP_TOKEN` is unset, and concurrent calls read the entire DB into Azure Free F1's 1 GB RAM at once.
  - **Remediation:** Fail closed (HTTP 503 if `SHAPE_PACKING_BACKUP_TOKEN` is unset unless explicit dev opt-out, HTTP 401 on invalid `Bearer ` token using `hmac.compare_digest`), stream in chunks from temp file cleanup, rate-limit strictly, and pass `secrets.BACKUP_TOKEN` from `sync-azure-db.yml`.

- **SEC-04: Worker Impersonation, Leaderboard/Attempt Spoofing, & 7-Day Lease Hoarding**
  - **Location:** `src/shape_packing/server/app.py:46-68, 129-212, 359-397`, `database.py:189-200`, `scheduler.py:69, 288, 323-333`
  - **Impact:** Unauthenticated callers can overwrite any existing `worker_id` username, delete active leases via `/deregister`, lock problems for 7 days (`lease_seconds=604800`), and send `attempts_completed = 2**62` (triggering SQLite 64-bit integer overflow and hijacking #1 on `/leaderboard`).
  - **Remediation:** Generate a per-worker `worker_secret` (`secrets.token_urlsafe(32)`, stored hashed with SHA-256 in `workers.secret_hash`) on `/workers/register` and require `Authorization: Bearer <worker_secret>` on `/work`, `/heartbeat`, `/solutions`, and `/deregister`. Enforce `username` length `1..64`, `client_type` allowlist, `lease_seconds <= 1800`, max active leases per worker (`<= 4`), `attempts_completed <= 50_000` per heartbeat, and require a valid matching active lease before crediting attempts.

- **SEC-05: Unbounded Payloads, Missing Rate Limits, Temp-File I/O, & Pre-SAT DoS on `/api/v1/solutions`**
  - **Location:** `src/shape_packing/server/app.py:56-61, 214-357`, `src/shape_packing/solution_tools.py:541-606`, `src/shape_packing/catalog.py:286`
  - **Impact:** Attackers can exhaust Azure F1's 60 CPU-min/day quota or 1 GB RAM by flooding oversized JSON bodies, `req.s = 1.5e308`, or invalid `N=54` arrays forcing full `O(N^2)` SAT verification and temp-file writes. `submit_solution` also fails to reject `proved_optimal` / `unsupported` / disabled problems and leaks `str(exc)` on errors.
  - **Remediation:** Add ASGI body size caps (`64 KB` on `/solutions`, `8 KB` on `/register` & `/heartbeat`), bounded LRU in-memory rate limits tuned to allow legitimate high-core/NAT compute donors, 10s read-cache on `/stats`/`/leaderboard`/`/recent_solutions`/`/problems`, in-memory fast-fail SAT verification without temp files, cheap pre-SAT rejection (`proved_optimal`/`unsupported`/disabled/non-improving `s`, `s <= 1e12`), and generic client error messages.

### Medium Severity

- **SEC-06: CORS Wildcard + Credentials + Private Network Access & Per-Request `init_db()`**
  - **Location:** `src/shape_packing/server/app.py:75-127`
  - **Remediation:** Set `allow_credentials=False`, remove `allow_private_network=True`, restrict `allow_origins` to GitHub Pages (`https://targed.github.io`, `https://erich-friedman.github.io`) + dev origins (`SHAPE_PACKING_ALLOWED_ORIGINS`), move `init_db()` / migrations to FastAPI `lifespan` startup, disable `/docs`/`/redoc` in production unless `SHAPE_PACKING_ENABLE_DOCS=1`, and add `X-Content-Type-Options: nosniff` + `X-Frame-Options: DENY`.

- **SEC-07: Missing CSP, Referrer Policy, & Inline Scripts in `BaseLayout.astro`**
  - **Location:** `site/src/layouts/BaseLayout.astro:22-24`, `site/src/pages/results.astro:264`, `site/src/pages/family/index.astro:131`
  - **Remediation:** Remove `is:inline` from `<script>` tags so Astro bundles them, add `<meta name="referrer" content="strict-origin-when-cross-origin">` and a `<meta http-equiv="Content-Security-Policy" ...>` header policy in `BaseLayout.astro` (note: self-hosting fonts removes external `fonts.googleapis.com` / `fonts.gstatic.com` dependencies cleanly).

- **SEC-08: `verify_solution` Allows `N <= 0` / `NaN`, Tolerance Gap, & `cli.py` Ignores Verification**
  - **Location:** `src/shape_packing/solution_tools.py:88-151, 541-606`, `packing_config.py:46-48`, `cli.py:193-205`
  - **Remediation:** Enforce `N > 0`, `len(values) == 3 * N`, finite positive `S`/`final_metric`/`values`, normalize `CIRCLE` via `normalize_token`, tighten `VERIFY_SAT_TOLERANCE` to `1e-7`, and abort `cli.py` before logging/committing if `not v_res.valid`.

- **SEC-09: Python/Rust Client & Solver Edge Cases**
  - **Location:** `packer_rs/src/solver.rs:87`, `packer_rs/src/bin/worker.rs:141-143`, `packer_rs/src/main.rs:68-80`, `packer_rs/src/wasm.rs:18-30`, `src/shape_packing/client/native_worker.py:149-165, 249, 536`, `autostart.py:30, 128-131`
  - **Remediation:** Guard `time_limit.is_finite() && time_limit > 0.0` in `solver.rs` and avoid sleeping leftover threads, bound `n` and `attempts` in `worker.rs` and `wasm.rs`, replace `cmd /c start` shell invocation and serialize `main.rs` via `serde_json`, validate `http`/`https` schemes + `urllib.parse.quote` + `MAX_RESPONSE_BYTES` + `0o600` permissions in `native_worker.py`, and fix `shape_packing.client.gui` + `xml.sax.saxutils.escape` in `autostart.py`.

- **SEC-10: GitHub Actions Least Privilege, Lockfiles, & Action Pinning**
  - **Location:** `.github/workflows/{main_shape-packing,sync-azure-db,deploy-astro,release}.yml`
  - **Remediation:** Move `permissions:` from workflow-level to job-level in `deploy-astro.yml` and `release.yml`, replace `npm ci || npm install` with strict `npm ci`, add `--locked` to `cargo build` in `release.yml` + `actions/attest-build-provenance`, add `--max-filesize` and token auth to `sync-azure-db.yml`, and pin Actions versions to commit SHAs.
