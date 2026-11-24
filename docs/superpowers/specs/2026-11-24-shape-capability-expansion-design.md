# Shape Capability Expansion & Registry Unification Design Specification

**Date:** 2026-11-24  
**Scope:** Asymmetric shape expansion (7/9/10-gons, `SEMICIRCLE`/`QUADRANT` circle containers, canonical convex quadrilaterals), declarative shape catalog unification, Packomania importer, two-tier scheduler (`benchmark` vs. `frontier`), pre-expansion solver/metric bug fixes, and site visualization updates.

---

## 1. Goals & Architectural Constraints

1. **Asymmetric Capability Expansion:** Move away from an implicit $K \times K$ shape matrix (`ALL_FAMILIES`) toward capability-checked pairings:
   - Regular polygons `{3, 4, 5, 6, 7, 8, 9, 10}` (`7`, `9`, `10` enabled with Packomania `circle_in_7`, `circle_in_9`, `circle_in_10` benchmarks).
   - Closed-form curved containers (`SEMICIRCLE`, `QUADRANT`) restricted strictly to `inner == "CIRCLE"`.
   - Fixed canonical convex quadrilaterals (`RHOMBUS`, `PARALLELOGRAM`, `TRAPEZOID`) paired with `{3, 4, 5, 6, 8, CIRCLE}` and quad-in-quad (45 curated **Frontier** families).
2. **Exact Verification Integrity:** Never approximate curved containers (`SEMICIRCLE`, `QUADRANT`) with polygon approximations (`32`-gon). Containment and overlap checks must use exact closed-form SDFs matching `VERIFY_SAT_TOLERANCE = 1e-5`.
3. **Ponytail Minimalism & Single Source of Truth:** Consolidate duplicated token aliases, area formulas, and family capability logic into one canonical `shape_catalog.json` read by Python and TypeScript, mirrored and cross-tested against Rust (`packer_rs`).
4. **Copy & Aesthetic Guardrails:** Zero emojis and zero em dashes across all UI copy, generated pages, docs, and logs.

---

## 2. Canonical Geometry & Metric Mathematics

### 2.1. Regular Polygons (`7`, `9`, `10`)
- Canonical tokens: `"7"` (`HEPTAGON`, `HEP`), `"9"` (`NONAGON`, `NON`, `ENNEAGON`), `"10"` (`DECAGON`, `DEC`).
- Internal unit basis: circumradius $R = 1.0$, vertices $v_k = (\cos(2\pi k/n), \sin(2\pi k/n))$, outward normals $\vec{n}_k = (\cos(2\pi k/n + \pi/n), \sin(2\pi k/n + \pi/n))$, apothems $a_k = \cos(\pi/n)$.
- Friedman scale metric factor: $2 \sin(\pi/n)$.
- Area for unit side length $s$: $\frac{1}{4} n s^2 \cot(\pi/n)$.

### 2.2. Closed-Form Curved Circle Containers (`SEMICIRCLE`, `QUADRANT`)
- Strictly paired with `inner_token == "CIRCLE"` (`i_scale = 1.0`). Calling `get_shape_geometry()` or `get_shape_convex_parts()` on non-circle pairings for `SEMICIRCLE` or `QUADRANT` raises `ValueError` in Python and rejects in `validate_problem` / `is_pair_supported`.
- **`SEMICIRCLE` (`SEMI`)**: Upper unit half-disk $\{y \ge 0,\; x^2 + y^2 \le S^2\}$ centered at chord midpoint $(0,0)$.
  - Exact bounds for unit circle $c_i = (x_i, y_i)$ ($r=1.0$):
    1. Chord half-plane: $y_i \ge 1.0 \implies \text{viol} = \max(0, 1.0 - y_i)$, $\frac{\partial}{\partial y_i} = -2\cdot\text{viol}$.
    2. Radial arc: $\sqrt{x_i^2 + y_i^2} \le S - 1.0 \implies \text{viol} = \max(0, \|c_i\| - (S - 1.0))$.
  - Metric $s = S$ (semicircle radius $R$ per unit inner circle radius), Area $= \frac{1}{2}\pi s^2$.
- **`QUADRANT` (`QUAD`)**: First-quadrant quarter disk $\{x \ge 0,\; y \ge 0,\; x^2 + y^2 \le S^2\}$ centered at corner $(0,0)$.
  - Exact bounds for unit circle $c_i = (x_i, y_i)$:
    1. $x_i \ge 1.0$
    2. $y_i \ge 1.0$
    3. $\sqrt{x_i^2 + y_i^2} \le S - 1.0$
  - Metric $s = S$ (quadrant radius $R$ per unit inner circle radius), Area $= \frac{1}{4}\pi s^2$.

### 2.3. Canonical Fixed Convex Quadrilaterals (`RHOMBUS`, `PARALLELOGRAM`, `TRAPEZOID`)
All three operate as unit-short-edge convex 4-gons (`c_metric = S`, `i_scale = 1.0`, so $s = S$) with positive interior apothems for all 4 edges:

- **`RHOMBUS`** ($60^\circ / 120^\circ$ diamond, side $= 1.0$, centered at $(0,0)$):
  - Vertices (CCW): $(\frac{\sqrt{3}}{2}, 0),\; (0, \frac{1}{2}),\; (-\frac{\sqrt{3}}{2}, 0),\; (0, -\frac{1}{2})$.
  - Normals: $(\frac{1}{2}, \frac{\sqrt{3}}{2}),\; (-\frac{1}{2}, \frac{\sqrt{3}}{2}),\; (-\frac{1}{2}, -\frac{\sqrt{3}}{2}),\; (\frac{1}{2}, -\frac{\sqrt{3}}{2})$.
  - Uniform apothems: $[\frac{\sqrt{3}}{4},\; \frac{\sqrt{3}}{4},\; \frac{\sqrt{3}}{4},\; \frac{\sqrt{3}}{4}]$.
  - Area: $\frac{\sqrt{3}}{2} s^2$.

- **`PARALLELOGRAM`** (Tangram parallelogram, short side $= 1.0$, base $= \sqrt{2}$, acute angle $= 45^\circ$, centered at $(0,0)$):
  - Vertices (CCW): $(-\frac{3\sqrt{2}}{4}, -\frac{\sqrt{2}}{4}),\; (\frac{\sqrt{2}}{4}, -\frac{\sqrt{2}}{4}),\; (\frac{3\sqrt{2}}{4}, \frac{\sqrt{2}}{4}),\; (-\frac{\sqrt{2}}{4}, \frac{\sqrt{2}}{4})$.
  - Normals: $(0, -1),\; (\frac{\sqrt{2}}{2}, -\frac{\sqrt{2}}{2}),\; (0, 1),\; (-\frac{\sqrt{2}}{2}, \frac{\sqrt{2}}{2})$.
  - Apothems: $[\frac{\sqrt{2}}{4},\; 0.5,\; \frac{\sqrt{2}}{4},\; 0.5]$.
  - Area: $1.0 \, s^2$.

- **`TRAPEZOID`** (Half-hexagon isosceles trapezoid: bottom base $= 2.0$, top base $= 1.0$, legs $= 1.0$, $60^\circ$ base angles, centered at half-height $(0, \frac{\sqrt{3}}{4})$):
  - Vertices (CCW): $(-1.0, -\frac{\sqrt{3}}{4}),\; (1.0, -\frac{\sqrt{3}}{4}),\; (0.5, \frac{\sqrt{3}}{4}),\; (-0.5, \frac{\sqrt{3}}{4})$.
  - Normals: $(0, -1),\; (\frac{\sqrt{3}}{2}, 0.5),\; (0, 1),\; (-\frac{\sqrt{3}}{2}, 0.5)$.
  - Apothems: $[\frac{\sqrt{3}}{4},\; \frac{3\sqrt{3}}{8},\; \frac{\sqrt{3}}{4},\; \frac{3\sqrt{3}}{8}]$.
  - Area: $\frac{3\sqrt{3}}{4} s^2$.

---

## 3. Declarative Registry & Pre-Expansion Bug Fixes

### 3.1. Shared `src/shape_packing/shape_catalog.json`
Single declarative manifest defining:
- Every canonical token (`"3"`..`"10"`, `"CIRCLE"`, `"TAN"`, `"DOMINO"`, `"L"`, `"SEMICIRCLE"`, `"QUADRANT"`, `"RHOMBUS"`, `"PARALLELOGRAM"`, `"TRAPEZOID"`), uppercase aliases, display names, slug tokens, geometry class (`regular_polygon | fixed_convex | non_convex | curved_circle_container`), Friedman scale formula parameters, and area coefficient formulas.
- Allowed pair capability rules:
  - Convex/existing grid (`{3,4,5,6,8,CIRCLE,TAN,DOMINO,L}^2`, plus `circle_in_{7,9,10}`).
  - Curved container rule (`container in {SEMICIRCLE, QUADRANT} => inner == CIRCLE`).
  - Curated Frontier quad pairs (`{RHOMBUS, PARALLELOGRAM, TRAPEZOID}` paired symmetrically with `{3, 4, 5, 6, 8, CIRCLE}` and with each other).

### 3.2. Targeted Pre-Expansion Bug Fixes
1. **`scripts/build_site_data.py`**:
   - Delegate `compute_friedman_metric` / `inverse_friedman_metric` cleanly so `L` container uses `2.0 * S` and `L_in_L` returns `S` consistently in both directions.
   - Fix `lincir` -> `L_in_circle` and `linsqu` -> `L_in_4` (remove incorrect `line_in_*` labels), and handle `cirinttt` without aliasing to `circle_in_3`.
   - Fix `data/packingVerification/cirinoct.json` (re-normalize Packomania inner radius $r$ to octagon side length $s = 2\sin(\pi/8)/r$) and repair `cirindom.json` (currently duplicating `domincir`).
2. **`src/shape_packing/problems.py` & Unknown-Token Guardrails**:
   - Case-insensitive `_validate_token` lookup (`token.strip().upper()`).
   - Raise explicit `ValueError` on unrecognized shape tokens in `geometry.py`, `solution_tools.py`, and explicit `Result` / `None` rejection in Rust/coordinator instead of silently treating unknown strings (like `"ELLIPSE"`) as triangles.
3. **`packer_rs/src/solver.rs` & `src/shape_packing/optimization.py`**:
   - Scale **only** translation coordinates `(x, y)` (`idx % 3 != 2`) by `multiplier` during shrink steps, keeping angles `theta_i` unscaled.
   - Add missing separating-axis rotation derivative term (`d_axis / d_rot`) to `L`-shape cutout SAT (`solver.rs:1205-1221`) and `L`-shape 2x2 SAT (`solver.rs:1419-1458`), verified via finite-difference checks.
4. **`tests/test_solution_tools.py`**:
   - Isolate `TestRenderSolution.test_render_basic` and `test_render_with_flags` inside `tmp_path` (`monkeypatch.chdir(tmp_path)`) so CWD permissions never fail test runs.

---

## 4. Data Flow, Packomania Ingestion, & Two-Tier Queue

1. **Packomania Importer (`scripts/import_packomania.py`):**
   - Fetches/parses Packomania tables (including `cirinoct` octagon, `cirindom` domino, `cirin7` heptagon, `cirin9` nonagon, `cirin10` decagon, `cirinsemi` semicircle, and `cirinquad` circular quadrant) for `N = 1..50`.
   - Explicitly converts Packomania's unit-container inner radius $r$ into unit-inner-circle container metric $s$ ($2\sin(\pi/n)/r$ for $n$-gons, $1/r$ or $2/r$ per table radius/diameter basis for semicircle/quadrant/domino) and writes normalized benchmark JSONs into `data/packingVerification/` (`tier: "benchmark"`, `source: "packomania"`).
2. **Frontier Quad Seeding & Two-Tier Scheduler (`database.py`, `scheduler.py`, `ranker.py`):**
   - Add column `tier TEXT NOT NULL DEFAULT 'benchmark'` (`'benchmark' | 'frontier'`) to SQLite `problems` table (migrated idempotently via `ALTER TABLE` if missing).
   - Seed the 45 Frontier quad families for `N = 1..20` (`900` problems) with `reference_s = NULL`, `tier = 'frontier'`.
   - `scheduler.assign_work(..., tier_filter=None)` orders eligible problems so `'benchmark'` problems always take priority over `'frontier'` problems until open benchmark targets are exhausted or a worker explicitly requests `tier="frontier"`.
   - `ranker.py` ranks `'benchmark'` problems by gap/density and appends `'frontier'` problems as secondary tail work rather than crashing or skipping `best_value is None`.
   - `submit_solution` handles `frontier` problems cleanly: records `best_s`, marks `is_new_record = True` only against `reference_s` for `'benchmark'` tier and tracks `FRONTIER_BEST` improvements separately.

---

## 5. Visualization & Verification Plan

1. **Verifier (`solution_tools.py`):**
   - Exact closed-form checks in `_verify_container_bounds` for `SEMICIRCLE` and `QUADRANT` (`VERIFY_SAT_TOLERANCE = 1e-5`).
   - Generic area/metric verification for `RHOMBUS`, `PARALLELOGRAM`, `TRAPEZOID`, and `{7, 9, 10}`.
2. **Site Renderer & Explorer (`render_packing.ts`, `shape_badge.ts`, `PackingVisual.astro`, `results.astro`, `family/`):**
   - Support SVG `<path d="M ... A ... Z">` for `SEMICIRCLE` and `QUADRANT` containers.
   - Center the SVG viewBox on the rendered geometry bounding-box midpoint `(vbCx, vbCy)` instead of hardcoding `(0,0)` so asymmetric containers (`SEMICIRCLE`, `QUADRANT`, `L`, `TRAPEZOID`) sit evenly framed inside square plates.
   - Generate crisp 20x20 vector badges for `7`, `9`, `10`, `semicircle`, `quadrant`, `rhombus`, `parallelogram`, and `trapezoid`.
   - Display `Benchmark` vs `Frontier` tier filter tabs and badges cleanly on `/results` and `/family` pages.
3. **Verification Checkpoints:**
   - Rust (`cargo test`), Python (`pytest tests/`), and Frontend (`npm test --prefix site` + `npm run build --prefix site`), including analytical $N=1$ exact checks ($s_{\text{semi}}=2.0$, $s_{\text{quad}}=1+\sqrt{2}$, $s_{\text{circle in rhombus}}=4/\sqrt{3}$, $s_{\text{circle in para}}=2\sqrt{2}$, $s_{\text{circle in trap}}=4/\sqrt{3}$) and finite-difference gradient tests.
