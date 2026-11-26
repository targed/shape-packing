# Security Hardening Implementation Plan

> **For agentic workers:** Execute task-by-task using TDD (`test -> fail -> fix -> pass -> commit`). Report verified outputs cleanly before completing each task.

**Goal:** Harden the Azure coordinator API, geometric verification core, Python/Rust/WASM worker clients, Astro frontend, and GitHub Actions workflows against DoS, XSS, data poisoning, and spoofing without hindering legitimate multi-core or NAT-shared compute donors.

**Architecture:** Use zero-dependency in-process security controls tuned for single-process Azure App Service Free F1 (LRU token buckets, short TTL read caching, SHA-256 `worker_secret` bearer auth, strict size/type bounds, fast-fail in-memory SAT verification), strict DOM/URL/CSP hardening in Astro, and lockfile/permission hardening in GitHub Actions.

**Tech Stack:** Python 3.12+ (FastAPI, Starlette ASGI, SQLite WAL, NumPy), Rust (`packer_rs`, `ureq`, `wasm-bindgen`), Astro / TypeScript, GitHub Actions.

## Global Constraints
- Zero emojis and zero em dashes across all modified source, docs, and site files.
- Keep existing local `http://localhost:8000` mock tests working while tightening defaults and input boundaries.
- Preserve existing 88 solutions in `shape_packing.db` and keep heavy compute donors (16-thread WASM tabs, multi-core CLI workers behind NAT) unthrottled under normal operation.

---

### Task 1: Fail-Closed Backup Export & Sync Workflow Security (`SEC-03`, `TM-01`)

**Files:**
- Modify: `src/shape_packing/server/app.py` (`export_database_snapshot`)
- Modify: `.github/workflows/sync-azure-db.yml`
- Test: `tests/test_security_api.py` (new ASGI + unit security test suite)

- [ ] **Step 1: Write failing tests for fail-closed `/api/v1/export/db` auth, `Bearer ` enforcement, `Cache-Control: no-store`, and invalid token rejection**
- [ ] **Step 2: Run `pytest tests/test_security_api.py -p no:cacheprovider -q` to confirm tests fail**
- [ ] **Step 3: Implement fail-closed `SHAPE_PACKING_BACKUP_TOKEN` check (HTTP 503 when unset unless `SHAPE_PACKING_ALLOW_UNAUTH_EXPORT=1` for local tests, exact `Bearer ` + `hmac.compare_digest`), chunked `StreamingResponse` with temp cleanup in `finally:`, `Cache-Control: no-store`, and 1/min rate limit in `app.py`; update `sync-azure-db.yml` to send `Authorization: Bearer ${{ secrets.BACKUP_TOKEN }}`, `--max-filesize 52428800`, and no `-L` redirect following**
- [ ] **Step 4: Re-run `pytest tests/test_security_api.py tests/test_package_imports.py -p no:cacheprovider -q` and confirm PASS**
- [ ] **Step 5: Commit Task 1**

---

### Task 2: Per-Worker Auth (`worker_secret`), Lease Integrity, & Heartbeat/Register Bounds (`SEC-04`, `TM-04`)

**Files:**
- Modify: `src/shape_packing/server/database.py` (`workers.secret_hash` schema + migration, `register_worker`, `verify_worker_secret`, `deregister_worker`)
- Modify: `src/shape_packing/server/scheduler.py` (`MAX_LEASE_SECONDS = 1800`, `MAX_HEARTBEAT_ATTEMPTS = 50_000`, `MAX_ACTIVE_LEASES_PER_WORKER = 4`, require active matching lease before crediting attempts)
- Modify: `src/shape_packing/server/app.py` (Pydantic length/charset bounds, `Literal["native", "wasm", "python"]`, Bearer `worker_secret` dependency on `/work`, `/heartbeat`, `/solutions`, `/workers/deregister`)
- Test: `tests/test_security_api.py`, `tests/test_server_database.py`, `tests/test_server_scheduler.py`

- [ ] **Step 1: Write failing tests covering: oversized username rejection, `worker_id` hijack attempt without matching `worker_secret`, unauthenticated `/work`/`/heartbeat`/`/solutions`/`/deregister` HTTP 401, fake `2**62` `attempts_completed` rejection, expired/nonexistent lease heartbeat NOT crediting attempts, and lease hoarding (>4 active leases)**
- [ ] **Step 2: Run tests to verify failure**
- [ ] **Step 3: Implement `secret_hash` migration, `secrets.token_urlsafe(32)` issuance, `hmac.compare_digest` verification, bounded Pydantic models, active lease enforcement, and cap adjustments**
- [ ] **Step 4: Run `pytest tests/test_security_api.py tests/test_server_database.py tests/test_server_scheduler.py tests/test_package_imports.py -p no:cacheprovider -q` and confirm all pass**
- [ ] **Step 5: Commit Task 2**

---

### Task 3: Donor-Friendly Rate Limiting, Body Size Middleware, TTL Read Cache, Pre-SAT Filter, & App Lifespan (`SEC-05`, `SEC-06`, `TM-03`)

**Files:**
- Create: `src/shape_packing/server/security.py` (small focused module: bounded `OrderedDict` LRU token bucket, Azure proxy IP resolver, TTL read cache, ASGI body size cap middleware, security headers middleware)
- Modify: `src/shape_packing/server/app.py` (lifespan DB init removing per-request `init_db`, tightened CORS without `allow_credentials`/`allow_private_network`, pre-SAT validation & in-memory `verify_solution` without temp files, disabled prod `/docs` by default)
- Modify: `src/shape_packing/solution_tools.py` (`N > 0`, finite floats, `normalize_token` circle check, `fast_fail` verification parameter, `verify_solution_obj`), `src/shape_packing/packing_config.py` (`VERIFY_SAT_TOLERANCE = 1e-7`), `src/shape_packing/cli.py` (check `res.valid` before logging/committing)
- Test: `tests/test_security_api.py`, `tests/test_solution_tools.py`

- [ ] **Step 1: Write failing tests for: HTTP 413 oversized `/solutions` body (>64 KB), HTTP 429 burst enforcement while allowing 16 concurrent WASM thread registrations + high NAT `/work`, TTL cache hit on `/stats` & `/leaderboard`, `N <= 0` and `NaN` solution rejection in `verify_solution`, fast-fail SAT on `[0.0]*150`, rejecting `proved_optimal` / `unsupported` / `1.5e308` before SAT, and CORS headers**
- [ ] **Step 2: Run tests to confirm failures**
- [ ] **Step 3: Implement `security.py`, wire into `app.py` lifespan + endpoints, and harden `solution_tools.py` & `cli.py`**
- [ ] **Step 4: Run `pytest` across all core, DB, scheduler, solution_tools, and security suites**
- [ ] **Step 5: Commit Task 3**

---

### Task 4: Client Auth Propagation & Safety Fixes (`SEC-09`, `TM-07`)

**Files:**
- Modify: `packer_rs/src/worker/config.rs`, `packer_rs/src/worker/client.rs`, `packer_rs/src/bin/worker.rs` (`worker_secret` persistence + `Authorization: Bearer` header, `n <= 200` / `attempts <= 100_000` clamp, remove `cmd /c start` shell risk)
- Modify: `packer_rs/src/solver.rs`, `packer_rs/src/wasm.rs`, `packer_rs/src/main.rs` (`time_limit.is_finite() && > 0.0` + cancellable timer condvar, `serde_json` CLI output, WASM input bounds)
- Modify: `src/shape_packing/client/native_worker.py`, `src/shape_packing/client/gui.py`, `src/shape_packing/client/autostart.py` (`worker_secret` storage/Bearer header, `http`/`https` scheme validation, `urllib.parse.quote`, bounded `resp.read()`, `0o600` POSIX permissions, `shape_packing.client.gui` autostart path, XML escape)
- Test: `cargo test --manifest-path packer_rs\Cargo.toml`, `pytest tests/test_native_worker.py tests/test_client_autostart.py tests/test_client_gui.py -p no:cacheprovider -q`

- [ ] **Step 1: Add unit tests for Rust `worker_secret` Bearer header + `NaN` `time_limit` + `n` clamping, and Python client scheme rejection / `worker_secret` / XML escaping**
- [ ] **Step 2: Run Rust and Python tests to verify new tests fail before implementation**
- [ ] **Step 3: Implement Rust and Python client security updates cleanly**
- [ ] **Step 4: Run `cargo test` and `pytest` client tests and confirm 100% pass**
- [ ] **Step 5: Commit Task 4**

---

### Task 5: Frontend XSS Elimination, URL Validation, CSP, & WASM/Astro Rebuild (`SEC-01`, `SEC-02`, `SEC-07`, `TM-02`)

**Files:**
- Modify: `site/src/lib/api.ts`, `site/src/lib/api.js` (`validateCoordinatorUrl` allowlisting `?coordinator=` origins; pass `workerSecret` cleanly)
- Modify: `site/src/pages/contribute.astro` (replace `left.innerHTML` with `createElement`/`textContent`; store/send `workerSecret`; pass `client_type: "wasm"`; guard `target_s`; validate `serverUrl`)
- Modify: `site/src/lib/workers/wasm_packer_worker.ts` (validate `work` schema/bounds; pass `Authorization: Bearer <workerSecret>`; add `AbortController` timeouts; guard `work.target_s == null`)
- Modify: `site/src/components/LeaderboardTable.astro`, `site/src/components/RecentlyUpdated.astro` (build table rows via DOM APIs instead of `innerHTML`)
- Modify: `site/src/layouts/BaseLayout.astro`, `site/src/pages/results.astro`, `site/src/pages/family/index.astro` (remove `is:inline`, add `<meta name="referrer">` and `<meta http-equiv="Content-Security-Policy">`)
- Rebuild: `wasm-pack build` -> `site/public/wasm/`, `npm run build --prefix site` -> `site/dist/`
- Test: `site/tests/*.test.mjs`, `site/tests/api.test.js`

- [ ] **Step 1: Add failing frontend tests verifying `validateCoordinatorUrl` rejects `http://evil.com`, `javascript:...`, `http://127.0.0.1` query hijack on public pages, and `contribute.astro` no longer assigns `left.innerHTML`**
- [ ] **Step 2: Run `npm test --prefix site` to confirm new assertions fail**
- [ ] **Step 3: Apply frontend hardening edits, rebuild WASM + Astro static site**
- [ ] **Step 4: Run `npm test --prefix site` + WASM Node smoke check and confirm all pass**
- [ ] **Step 5: Commit Task 5**

---

### Task 6: GitHub Actions Supply-Chain & Red-Team Verification (`SEC-10`, `TM-05`, `TM-06`)

**Files:**
- Modify: `.github/workflows/deploy-astro.yml` (move `pages: write`/`id-token: write` to `deploy` job, enforce `npm ci` without fallback)
- Modify: `.github/workflows/release.yml` (move `contents: write` to `release` job, add `--locked` to `cargo build`, add `actions/attest-build-provenance`, reject empty `tag_name` on `main` dispatch)
- Modify: `.github/workflows/main_shape-packing.yml` (remove deprecated/unused artifact clutter cleanly if needed; pin GitHub Actions to commit SHAs across all 4 workflows)

- [ ] **Step 1: Update workflow permissions, `--locked`, `npm ci`, and SHA-pinned Actions**
- [ ] **Step 2: Launch an adversarial Red-Team subagent (read/probe tests against running `create_app()` + `tests/test_security_api.py` + AST checks) to attempt bypassing rate limits, worker auth, export token, SAT `NaN`/`1e308`, and `?coordinator=` XSS**
- [ ] **Step 3: Fix any finding surfaced by Red-Team testing and re-run full Rust, Python, and Site suites cleanly (`/verification-before-completion`)**
- [ ] **Step 4: Commit Task 6**
