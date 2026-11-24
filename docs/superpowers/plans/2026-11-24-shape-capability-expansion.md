# Shape Capability Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand supported shapes selectively (`7/9/10` polygons, closed-form `SEMICIRCLE`/`QUADRANT` circle containers, canonical fixed `RHOMBUS`/`PARALLELOGRAM`/`TRAPEZOID` Frontier quads) on top of a unified declarative shape catalog, while fixing existing metric/gradient/normalization bugs across Python, Rust, SQLite, and Astro/TS.

**Architecture:** A shared `src/shape_packing/shape_catalog.json` defines canonical tokens, aliases, geometry categories, scaling formulas, area coefficients, and asymmetric pair capabilities (`is_pair_supported`). Python and TypeScript load this catalog directly while Rust (`packer_rs`) mirrors and cross-validates identical unit geometries and SDFs via unit tests. A new Packomania importer normalizes Packomania `circle_in_*` benchmarks (`cirinoct`, `cirindom`, `cirin7`, `cirin9`, `cirin10`, `cirinsemi`, `cirinquad`), and a two-tier scheduler prioritizes `'benchmark'` problems ahead of `'frontier'` quad families.

**Tech Stack:** Python 3.x (NumPy, SciPy, SQLite, FastAPI, Pytest), Rust (PyO3/WASM/CLI `packer_rs`, Cargo test), Astro 5 + TypeScript + TailwindCSS (`node --test`).

## Global Constraints

- Exact closed-form SDFs for `CIRCLE`, `SEMICIRCLE`, and `QUADRANT` (never use polygon approximations in containment/overlap verification or circle-container checks).
- Strictly forbid non-`CIRCLE` items inside `SEMICIRCLE` and `QUADRANT` containers (`ValueError` / explicit rejection).
- Fail loudly (`ValueError` / explicit error) on unknown shape tokens instead of falling back silently to triangle `sides = 3`.
- Zero emojis and zero em dashes anywhere in UI copy, generated markdown, logs, and comments.
- TDD required for every code change: write failing test, verify failure, implement minimal fix, verify pass, commit cleanly.

---

### Task 1: Shared Declarative Shape Catalog & Registry (`shape_catalog.json`, `problems.py`, `packing_config.py`)

**Files:**
- Create: `src/shape_packing/shape_catalog.json`
- Create: `src/shape_packing/catalog.py`
- Modify: `src/shape_packing/packing_config.py:98-135, 868-965`
- Modify: `src/shape_packing/problems.py:30-165`
- Test: `tests/test_problems.py`, `tests/test_packing_config.py`

**Interfaces:**
- Produces in `src/shape_packing/catalog.py`:
  - `load_catalog() -> Dict[str, Any]`
  - `normalize_token(token: Any) -> str`
  - `is_pair_supported(inner_token: str, container_token: str) -> bool`
  - `get_shape_spec(token: str) -> Dict[str, Any]`
  - `list_frontier_families() -> List[Tuple[str, str, str]]` (`(family_id, inner_token, container_token)`)
- Consumed by `problems.py`, `packing_config.py`, `geometry.py`, `solution_tools.py`, `agent_loop.py`, `ranker.py`, `database.py`, `build_site_data.py`, `shape_badge.ts`.

- [ ] **Step 1: Write failing tests for catalog normalization, asymmetric pairing rules, and case-insensitive `_validate_token`**
  - Verify `normalize_token("heptagon") == "7"`, `normalize_token("enneagon") == "9"`, `normalize_token("semi") == "SEMICIRCLE"`, `normalize_token("quad") == "QUADRANT"`, `normalize_token("diamond")` / `"rhombus"` -> `"RHOMBUS"`.
  - Verify `is_pair_supported("CIRCLE", "SEMICIRCLE") is True` and `is_pair_supported("4", "SEMICIRCLE") is False`.
  - Verify `validate_problem(parse_problem("3_circle_in_square"))` succeeds (regression for case-sensitive `_validate_token` bug at `problems.py:150`).
  - Verify `list_frontier_families()` yields all 45 canonical quad pairs (`3x3` quad-in-quad + `3x6x2` quad paired with `{3,4,5,6,8,CIRCLE}`).
- [ ] **Step 2: Run `.venv\Scripts\pytest.exe tests/test_problems.py tests/test_packing_config.py -p no:cacheprovider -q` and confirm failure**
- [ ] **Step 3: Create `src/shape_packing/shape_catalog.json` and `src/shape_packing/catalog.py`; update `packing_config.py` and `problems.py`**
  - Ensure `SHAPE_TO_SIDES` includes `"7"`, `"9"`, `"10"` and `"NONAGON": 9`.
  - Add `CURVED_CIRCLE_CONTAINERS = {"SEMICIRCLE", "QUADRANT"}` and `QUAD_SHAPES = {"RHOMBUS", "PARALLELOGRAM", "TRAPEZOID"}` exported from `packing_config.py`.
  - Fix `_validate_token` in `problems.py` to normalize uppercase before lookup and raise `ValueError` on unknown tokens or invalid pairings.
- [ ] **Step 4: Run tests to verify pass**
  - `.venv\Scripts\pytest.exe tests/test_problems.py tests/test_packing_config.py -p no:cacheprovider -q` -> Expected: all pass.
- [ ] **Step 5: Commit Task 1**

---

### Task 2: Python Geometry, Exact Verifier, & Optimizer Fixes (`geometry.py`, `solution_tools.py`, `optimization.py`, `agent_loop.py`)

**Files:**
- Modify: `src/shape_packing/geometry.py:67-175, 267-410`
- Modify: `src/shape_packing/solution_tools.py:80-170, 395-545, 620-660`
- Modify: `src/shape_packing/optimization.py:225-240`
- Modify: `src/shape_packing/agent_loop.py:230-275, 355-430`
- Modify: `tests/test_solution_tools.py:521-537`
- Test: `tests/test_geometry.py`, `tests/test_geometry_extra.py`, `tests/test_solution_tools.py`

**Interfaces:**
- `get_shape_geometry(token: str)` supports `RHOMBUS`, `PARALLELOGRAM`, `TRAPEZOID`, raises `ValueError` on `SEMICIRCLE`/`QUADRANT` or unknown tokens.
- Exact closed-form bounds for `SEMICIRCLE` ($y_i \ge 1, \|c_i\| \le S-1$) and `QUADRANT` ($x_i \ge 1, y_i \ge 1, \|c_i\| \le S-1$) in `geometry.py` (`bh_objective` / `_poking_penalty_nb`) and `solution_tools.py` (`_verify_container_bounds`), guarded by explicit inner-is-circle checks.
- `_get_inner_shape_area` / `_get_container_shape_area` in `agent_loop.py` support `7, 9, 10, SEMICIRCLE, QUADRANT, RHOMBUS, PARALLELOGRAM, TRAPEZOID`.

- [ ] **Step 1: Write failing tests**
  - Analytical $N=1$ exact verification tests in `tests/test_solution_tools.py`:
    - `1_CIRCLE_in_SEMICIRCLE` passes at $(0, 1.0)$ with $S = 2.0$ and fails at $(0, 0.9999)$.
    - `1_CIRCLE_in_QUADRANT` passes at $(1.0, 1.0)$ with $S = 1 + \sqrt{2}$ and fails when $x < 1.0$ or $y < 1.0$.
    - `1_CIRCLE_in_RHOMBUS` ($S = 4/\sqrt{3}$), `1_CIRCLE_in_PARALLELOGRAM` ($S = 2\sqrt{2}$), `1_CIRCLE_in_TRAPEZOID` ($S = 4/\sqrt{3}$), `1_4_in_7` / `9` / `10`.
    - `verify_solution` rejects `1_4_in_SEMICIRCLE` and raises/rejects unknown `"ELLIPSE"` instead of falling back to `3`.
  - Verify `optimization.py` shrink step preserves `theta` values while scaling `(x, y)` coordinates.
  - Fix `TestRenderSolution.test_render_basic` & `test_render_with_flags` to `monkeypatch.chdir(tmp_path)`.
- [ ] **Step 2: Run pytest on `tests/test_geometry.py tests/test_geometry_extra.py tests/test_solution_tools.py` and confirm new tests fail**
- [ ] **Step 3: Implement geometry, bounds, metric, area, and optimizer shrink fixes across `geometry.py`, `solution_tools.py`, `optimization.py`, `agent_loop.py`**
- [ ] **Step 4: Run pytest to verify all geometry & solution tests pass**
- [ ] **Step 5: Commit Task 2**

---

### Task 3: Rust Solver & WASM Parity (`packer_rs/src/solver.rs`, `packer_rs/src/wasm.rs`)

**Files:**
- Modify: `packer_rs/src/solver.rs:100-145, 200-350, 485-535, 960-1010, 1190-1230, 1415-1465`
- Modify: `packer_rs/src/wasm.rs:14-48`

**Interfaces:**
- `parse_polygon_sides`, `compute_friedman_metric`, `inverse_friedman_metric`, `get_shape_geometry` mirror Python catalog exactly for `RHOMBUS`, `PARALLELOGRAM`, `TRAPEZOID`, `SEMICIRCLE`, `QUADRANT`, `7`, `9`, `10`.
- Unsupported pair check in `solve()` returns `SolveResult { success: false, ... }` cleanly if `is_container_semicircle || is_container_quadrant` and `!is_inner_circle`.

- [ ] **Step 1: Write failing Rust unit tests in `packer_rs/src/solver.rs`**
  - Metric roundtrip tests for `RHOMBUS`, `PARALLELOGRAM`, `TRAPEZOID`, `SEMICIRCLE`, `QUADRANT`, `7`, `9`, `10`.
  - Analytical gradient vs. central finite-difference parity tests for:
    - `CIRCLE` in `SEMICIRCLE` and `CIRCLE` in `QUADRANT` boundaries.
    - `L` cutout SAT & `L` 2x2 SAT (exposing missing `d_axis / d_rot` gradient!).
  - Solver convergence test for `1_CIRCLE_in_SEMICIRCLE` ($s \to 2.0$), `1_CIRCLE_in_QUADRANT` ($s \to 1 + \sqrt{2}$), and `2_RHOMBUS_in_4`.
- [ ] **Step 2: Run `cargo test --manifest-path packer_rs\Cargo.toml` and confirm failures**
- [ ] **Step 3: Implement exact quad geometries, `SEMICIRCLE`/`QUADRANT` SDFs, rotation-preserving `shrink_multiplier` (`idx % 3 != 2`), and restored `d_axis / d_rot` gradient on `L` shapes in `solver.rs`**
- [ ] **Step 4: Run `cargo test --manifest-path packer_rs\Cargo.toml` and verify 100% pass**
- [ ] **Step 5: Commit Task 3**

---

### Task 4: Packomania Benchmark Repair, Importer, & Priority Queue (`scripts/import_packomania.py`, `data/packingVerification/`, `ranker.py`)

**Files:**
- Create: `scripts/import_packomania.py`
- Modify: `data/packingVerification/cirinoct.json` (re-normalize from Packomania raw $r$ to octagon side $s = 2\sin(\pi/8)/r$)
- Repair/Create: `data/packingVerification/cirin7.json`, `cirin9.json`, `cirin10.json`, `cirinsemi.json`, `cirinquad.json` (`N = 1..50`) and inspect/fix `cirindom.json`
- Modify: `src/shape_packing/ranker.py:14-140`
- Test: `tests/test_ranker.py`, `tests/test_packomania_importer.py`

**Interfaces:**
- `convert_packomania_value(raw_val: float, container_token: str, raw_basis: str) -> float`
- `ranker.get_shape_area(shape_token: str, size: float) -> Optional[float]` supports all catalog tokens.
- `ranker.generate_queue(...)` emits clean densities `< 1.0` (never `2097.0`!) for `cirinoct` and includes `'frontier'` tail items after `'benchmark'` items.

- [ ] **Step 1: Write failing tests for Packomania normalization conversions (`N=1` octagon `2*(sqrt(2)-1)`, heptagon, semicircle, quadrant) and `ranker.py` area/queue logic**
- [ ] **Step 2: Run pytest on `tests/test_ranker.py tests/test_packomania_importer.py` and confirm failure**
- [ ] **Step 3: Implement `scripts/import_packomania.py`, re-normalize `cirinoct.json`, import/verify `cirin7`/`cirin9`/`cirin10`/`cirinsemi`/`cirinquad` + `cirindom`, update `ranker.py`, and regenerate `data/priority_queue.json`**
- [ ] **Step 4: Run tests and verify `data/priority_queue.json` has realistic `cirinoct` densities (< 1.0)**
- [ ] **Step 5: Commit Task 4**

---

### Task 5: Two-Tier Coordinator Database, Scheduler, & FastAPI Validation (`database.py`, `scheduler.py`, `app.py`)

**Files:**
- Modify: `src/shape_packing/server/database.py:24-125, 310-420`
- Modify: `src/shape_packing/server/scheduler.py:43-220`
- Modify: `src/shape_packing/server/app.py:255-340`
- Test: `tests/test_server_database.py`, `tests/test_server_scheduler.py`

**Interfaces:**
- `problems.tier TEXT NOT NULL DEFAULT 'benchmark'` added in `SCHEMA` + idempotent `ALTER TABLE` migration in `init_db`.
- `seed_frontier_problems(conn, max_n=20) -> int` seeds the 45 canonical Frontier families cleanly with `tier = 'frontier'`.
- `assign_work(conn, worker_id, cores=1, lease_seconds=300, tier_filter=None)` orders `'benchmark'` before `'frontier'`.

- [ ] **Step 1: Write failing tests in `tests/test_server_database.py` and `tests/test_server_scheduler.py`**
  - Verify `init_db` migrates existing DB without `tier` column cleanly.
  - Verify `seed_problems` marks `CIRCLE in SEMICIRCLE` as supported (`tier='benchmark'`) and marks invalid pairs like `4 in SEMICIRCLE` as `'unsupported'`.
  - Verify `assign_work` hands out `'benchmark'` work before `'frontier'` work when both exist, and hands out `'frontier'` work once open benchmarks are leased/exhausted.
- [ ] **Step 2: Run pytest on database & scheduler tests and confirm failure**
- [ ] **Step 3: Implement `tier` migration, `is_pair_supported` checks in `database.py` & `app.py`, `seed_frontier_problems`, and two-tier bandit ordering in `scheduler.py`**
- [ ] **Step 4: Run pytest to verify pass**
- [ ] **Step 5: Commit Task 5**

---

### Task 6: Site Data Builder Fixes & Frontend Arc/Quad/Frontier Explorer (`build_site_data.py`, `site/src/`)

**Files:**
- Modify: `scripts/build_site_data.py:40-310, 515-560`
- Modify: `site/src/lib/visualization/render_packing.ts:55-330`
- Modify: `site/src/lib/visualization/shape_badge.ts:1-159`
- Modify: `site/src/components/PackingVisual.astro`
- Modify: `site/src/components/ResultsTable.astro`, `site/src/pages/results.astro`, `site/src/pages/family/index.astro`, `site/src/pages/family/[slug].astro`
- Test: `site/tests/` (`packing_visual.test.mjs`, `shape_badge.test.mjs`, `results_table.test.mjs`, `family_pages.test.mjs`, `global_quality_audit.test.mjs`)

- [ ] **Step 1: Write failing frontend/build tests**
  - `render_packing.ts` produces arc path specs for `SEMICIRCLE` and `QUADRANT`, quad polygons for `RHOMBUS`/`PARALLELOGRAM`/`TRAPEZOID`, and centers viewBox on `(vbCx, vbCy)` so `SEMICIRCLE` bottom chord sits visibly inside the upper/middle frame.
  - `shape_badge.ts` returns valid SVG badges (non-fallback) for `7`, `9`, `10`, `semicircle`, `quadrant`, `rhombus`, `parallelogram`, `trapezoid`.
  - Zero-emoji and zero-em-dash checks pass across all updated templates.
- [ ] **Step 2: Run `npm test --prefix site` and confirm new tests fail**
- [ ] **Step 3: Fix `build_site_data.py` (`L` metric parity, `lincir`/`linsqu` -> `L_in_*`, `cirinttt` handling, catalog lookup, `tier` export), regenerate `site/src/data/site_data.json`, and update TS/Astro visualization + Frontier UI filters**
- [ ] **Step 4: Run `npm test --prefix site` and `npm run build --prefix site` cleanly; rebuild Rust binary if needed and re-verify full Python & Rust suites**
- [ ] **Step 5: Commit Task 6**
