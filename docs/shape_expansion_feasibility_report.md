# Shape Capability Expansion: Critical Feasibility & Architecture Report

**Date:** November 24, 2026  
**Scope:** Feasibility, mathematical soundness, architectural touchpoints, and scope critique for adding $N \in \{7, 9, 10\}$-gons, curved shapes (semicircle, circular quadrant), and affine quadrilaterals (trapezoid, rhombus, parallelogram) before bulk benchmark imports.  
**Mode:** `/research`, `/ponytail`, `/brainstorming` (Report only; no production code modified).

---

## 1. Executive Critique Summary (The Critic's Verdict)

Expanding shape coverage is **technically feasible in selective tiers**, but doing it as a blind Cartesian product ($K \times K$ grid) across arbitrary curved and parametric shapes is an **architectural and compute trap**. Three findings dominate the investigation:

1. **7-, 9-, and 10-gons are already built in the math engines, just blocked by UI and config hardcodes.** `geometry.py`, `packer_rs/src/solver.rs`, `solution_tools.py`, `server/database.py`, and `render_packing.ts` already accept `"7"`, `"9"`, `"10"`, `"HEPTAGON"`, `"NONAGON"`, and `"DECAGON"`. Only 6 peripheral lookup/UI files hardcode `{3, 4, 5, 6, 8}`. However, Erich Friedman's archive contains **zero** 7-, 9-, or 10-gon packing tables; only Packomania tracks Circles in 7/9/10-gons. Expanding from 9 to 12 all-pairs adds 63 unbenchmarked families.
2. **Semicircles and circular quadrants hit a strict SAT wall if used outside `Circle-in-Container`.** As **containers exclusively for `CIRCLE`** (matching Packomania's exact catalog), semicircle and quadrant constraints are 2 to 3 trivial closed-form inequalities with 0.0% error. As general inner shapes or containers for polygons, they cannot use our convex polygon SAT kernel or our `32`-gon fallback without breaking verification integrity. They would require a brand-new analytic Chord + Arc collision and cusp-gradient engine.
3. **Trapezoids, rhombuses, and parallelograms are under-specified (0-parameter vs. multi-parameter gap).** Unlike regular polygons or `DOMINO` ($1 \times 2$), a rhombus has 1 continuous shape parameter ($\alpha$), a parallelogram has 2 ($b/a, \alpha$), and a trapezoid has 3. Either they must be pinned to fixed canonical prototypes (e.g., Tangram $1:\sqrt{2}$ parallelogram, $60^\circ$ rhombus, half-hexagon trapezoid), which work **immediately** in existing convex SAT, or they become variable-aspect Area-minimization problems like `cirinel` (Circles in Arbitrary Ellipses) and `cirinttt` (Circles in Arbitrary Triangles), which the solver currently marks `unsupported`.

**Core Recommendation (Ponytail Critique):** Fix existing shape/metric bugs in the current codebase first, then expand **asymmetrically** (targeted capability lists instead of an $N \times N$ explosion): enable `7/9/10` selectively (or only `circle_in_{7,9,10}`), add exact closed-form `circle_in_semicircle` / `circle_in_quadrant` container constraints if Packomania parity is desired, and choose fixed prototypes if adding quadrilaterals.

---

## 2. Primary-Source Benchmark Reality Check

### 2.1. Erich Friedman's Packing Center (`data/erich-friedman.github.io/packing/`)
Inspection of `data/erich-friedman.github.io/packing/index.html` (lines 1-88) confirms **125 content directories**, grouped into 8 categories:
- **Equal Copies (`index.html:3-68`):** 81 pairs from `{Circle, 3, 4, 5, 6, 8, Tan, Domino, L}` plus 2 arbitrary-container categories (`cirinel` for Arbitrary Ellipses, `cirinttt` for Arbitrary Triangles).
  - *Note:* `squinsqu` links externally to David Ellsworth (`kingbird.myphotos.cc`), while `cirinoct` and `cirindom` link externally to Packomania (`packomania.com/coc/coc.html` and `packomania.com/crc_500/crc.html`).
- **Other Categories (`index.html:70-84`):** Maximize Total Perimeter (`*R*`, 16 folders), 3D Packings (3 folders), Covering (`*cov*`/`*co*`, 9 folders), Heilbronn (3 folders), Consecutive/Almost/Animations (7 folders), Related distance/area puzzles (6 folders).
- **Zero occurrence of new candidate shapes:** Searching all packing HTML pages in `data/erich-friedman.github.io/packing/` yields **0 hits** for `7`, `9`, `10`, `heptagon`, `nonagon`, `enneagon`, `decagon`, `semicircle`, `quadrant`, `trapezoid`, `rhombus`, or `parallelogram` as equal-copy benchmarks (`numbers.html` mentions polygonal numbers only as trivia).

### 2.2. Packomania (`packomania.com`) Catalog Scope
Packomania (maintained by Eckard Specht) focuses specifically on **packing circles into fixed containers** (equal, unequal, and bidisperse circles):
- **Present on Packomania:** `Circles in a regular heptagon` (7), `octagon` (8), `nonagon` (9), `decagon` (10), plus `Circles in a semicircle` and `Circles in a circular quadrant`, and `Circles in rectangles`.
- **Absent on Packomania:** Polygons in polygons, semidisks packing semidisks, trapezoids, rhombuses, and parallelograms.

### 2.3. What Exists in `data/packingVerification/` Today
`data/packingVerification/` holds **82 JSON files** (2,269 records; 2,249 distinct `our_problem` IDs):
- Covers 80 of the 81 equal-copy grid pairs (missing `squinsqu`) plus `cirinel.json` (24 entries) and `cirinttt.json` (31 entries).
- `server/database.py:26-29, 369-370` intentionally seeds `cirinel` and `cirinttt` with `status = 'unsupported'`, skipping them in `scheduler.py:118,136,169`.

### 2.4. Latent Bugs & Drifts Found in the Current Pipeline (Fix Before Expanding)
Expanding shapes on top of existing silent drifts will amplify broken renders and false metrics:

| Bug / Drift | Primary Location | Impact |
| :--- | :--- | :--- |
| **`compute_friedman_metric` vs `inverse_friedman_metric` 2x drift on `L`** | `scripts/build_site_data.py:253-254` vs `299-300` | `compute_friedman_metric` uses `c_metric = S` for `L` and misses `L_in_L`, whereas `inverse_friedman_metric` divides by `2.0`. |
| **Mislabeled `lincir` / `linsqu` as Lines** | `scripts/build_site_data.py:123-124, 233-234` | `packingVerification/lincir.json:5` and `linsqu.json:5` are L-trominoes (`L`), but `build_site_data.py` turns them into `line_in_circle` and `line_in_4`. |
| **Mislabeled `cirinttt` as Equilateral Triangle** | `scripts/build_site_data.py:103` | Maps `"cirinttt"` (Arbitrary Triangles) to `"circle_in_3"` instead of marking it arbitrary/unsupported. |
| **`_validate_token` case-sensitivity bug** | `src/shape_packing/problems.py:150` | Checks `if token in SHAPE_TO_SIDES:` without `.upper()`, rejecting lowercase `"circle"` / `"square"`. |
| **Shrink loop mutates orientation angles** | `src/shape_packing/optimization.py:232`, `packer_rs/src/solver.rs:490-493, 526-529` | Multiplies the full `3*N` state vector `[x, y, theta]` by `shrink_multiplier` instead of scaling only `(x, y)`. |
| **Missing `d_axis / d_rot` gradient on `L` shapes** | `packer_rs/src/solver.rs:1205-1221, 1419-1458` | Generic SAT includes separating-axis rotation derivative (`1564-1570`); `L` cutout & 2x2 SAT omit it, distorting L-BFGS rotational polish. |
| **Silent fallback to triangle (`sides = 3`)** | `geometry.py:130`, `solver.rs:339`, `build_site_data.py:260` | Unknown tokens (`"ELLIPSE"`, `"SEMICIRCLE"`) silently evaluate as equilateral triangles instead of failing loudly. |
| **Legacy broken `shape_to_vertices()`** | `src/shape_packing/packing_config.py:383-424` | Maps `"DOMINO"` to L-vertices and checks typo `"TRANGLE"` returning `TAN`. |

---

## 3. Codebase Touchpoint Audit: Where Shapes Live

Today there is **no unified shape registry**. Every shape token crosses 12 distinct subsystems across 3 languages:

```text
  [DB Seed / Reference JSON] --> problems.py / packing_config.py --> geometry.py (Python)
             |                                                          |
             v                                                          v
    scheduler.py / ranker.py                                  packer_rs/src/solver.rs (Rust/WASM)
             |                                                          |
             +---------------------------+------------------------------+
                                         |
                                         v
            solution_tools.py (Verify) --> build_site_data.py --> render_packing.ts / shape_badge.ts
```

1. **Core Physics (`geometry.py:67-175`, `packer_rs/src/solver.rs:281-347`):** Stores vertices centered at origin, outward edge normals, and edge apothems.
2. **Metric Normalization (`solution_tools.py:92-166`, `solver.rs:216-261`, `render_packing.ts:148-184`, `build_site_data.py:247-307`):** Maps between solver scale $S$ and published metric $s$.
3. **Hardcoded Shape Allowlists (`packing_config.py:872-962`, `database.py:26-68`, `agent_loop.py:232-271`):** Controls valid tokens, area calculations (for density ranking), and family grids.
4. **Verification (`solution_tools.py:322-546`):** Enforces independent tolerance checks (`1e-5` overlap/bounds, `1e-6` metric parity).
5. **Frontend (`render_packing.ts:57-184`, `shape_badge.ts:45-132`, `PackingVisual.astro`):** Generates vector plates, badges, and interactive WASM preview polygons.

---

## 4. Deep-Dive Feasibility & Critique by Shape Group

### 4.1. Tier 1: Regular Polygons (`7` Heptagon, `9` Nonagon, `10` Decagon)

#### Technical Status
- **Solver & Verifier:** **Already implemented.** `geometry.py:119-135`, `solver.rs:207-210, 335-338`, `solution_tools.py:85-88`, `database.py:27`, and `render_packing.ts:62-65` already build arbitrary regular $n$-gons on unit circumradius $R = 1.0$, compute outward normals, convert Friedman edge-length metrics via $2 \sin(\pi/n)$, and rotate odd vs. even containers visually.
- **Missing Hardcodes (Only 6 files need small edits):**
  1. `src/shape_packing/packing_config.py:872-890` (`SHAPE_TO_SIDES` lacks `"7"`, `"9"`, `"10"`, uses `"ENNEAGON"` vs `"NONAGON"`; `ALL_FAMILIES` lacks them).
  2. `src/shape_packing/agent_loop.py:232-271, 364-367` (`_get_inner_shape_area` and `_get_container_shape_area` hardcode `3, 4, 5, 6, 8` and return `None` for 7, 9, 10!).
  3. `scripts/build_site_data.py:41-135, 160-244, 522-538` (`LEGACY_MAP`, `FAMILY_DISPLAY_NAMES`, `SHAPE_VARIANTS`).
  4. `site/src/lib/visualization/shape_badge.ts:52-69, 99-116` (works for numeric `"7"` via fallback at line 78, but named `"heptagon"`, `"nonagon"`, `"decagon"` fall back to square/circle).
  5. `scripts/parse_erich_friedman.py` / `scripts/verify_packing_reference.py` (`shape_to_token`).
  6. `src/shape_packing/family_properties.json` (only has 75 scraped Friedman keys).

#### The Critic's Perspective
- **Feasibility:** **Trivial (hours, not days).**
- **Value vs. Bloat Trap:** Turning $\{3,4,5,6,8\}$ + `{Circle, Tan, Domino, L}` into a $12 \times 12$ cross product creates **144 problem families** (+63 new families). Only **3** (`circle_in_7`, `circle_in_9`, `circle_in_10`) have external benchmarks (Packomania). The remaining 60 (`7_in_9`, `10_in_L`, `9_in_domino`, etc.) have **zero benchmark targets**, meaning `ranker.py` cannot score percentage improvements or flag `NEW_BEST` against literature, and cluster workers would burn compute on ~1,800+ unbenchmarked $(family, N)$ slots.
- **Computational Note:** Higher $n$-gons increase SAT edge checks quadratically ($n_A + n_B$ axes $\times$ $n$ vertices per pair). Decagon-in-decagon ($10 + 10$ axes, $10$ vertices) does ~3.3x more work per pair than square-in-square ($4 + 4$ axes, $4$ vertices). Still totally tractable in Rust (`N <= 30`), especially with broadphase AABB enabled for `N > 20`.

---

### 4.2. Tier 2: Curved Containers & Shapes (`SEMICIRCLE`, `QUADRANT`)

#### How They Appear on Packomania
Packomania catalogs **"Circles in a semicircle"** and **"Circles in a circular quadrant"** (both normalized to container radius $R = 1.0$ or diameter $2.0$ depending on Packomania table convention; needs explicit verification per table header before importing). Packomania does **not** pack polygons into semicircles/quadrants, nor semicircles/quadrants as inner tiles.

#### Two Very Different Engineering Scopes

##### Scope 2A: `CIRCLE` inside `SEMICIRCLE` or `QUADRANT` (Container-Only Curved Support)
- **Mathematical Model:**
  - `SEMICIRCLE` ($R = S$, flat base on $y = 0$, upper disk $y \ge 0$, $x^2 + y^2 \le S^2$; centered at area centroid $(0, \frac{4S}{3\pi})$ or origin $(0,0)$):
    A unit circle at $(x_i, y_i)$ with radius $r = 1.0$ is strictly inside the semicircle if and only if:
    1. $y_i \ge 1.0$ (linear half-plane constraint against the chord, exact gradient $[0, -1]$)
    2. $\sqrt{x_i^2 + y_i^2} \le S - 1.0$ (radial disk constraint, exact gradient $\frac{(x_i, y_i)}{\|c_i\|}$)
    *Corner verification check:* Does any corner where $y = 0$ meets $x^2+y^2 = S^2$ allow a false positive? Any disk with center $y_i \ge 1$ and $\|c_i\| \le S - 1$ lies inside the intersection of the closed half-plane $\{y \ge 0\}$ and closed disk $\{\|p\| \le S\}$ eroded by Minkowski radius $1.0$. Because both are convex sets, the Minkowski erosion of their intersection equals the intersection of their erosions: $(H \cap D) \ominus B_1 = (H \ominus B_1) \cap (D \ominus B_1)$. **There are NO corner edge-cases; these two inequalities are 100% necessary and sufficient.**
  - `QUADRANT` ($x \ge 0, y \ge 0, x^2 + y^2 \le S^2$):
    By the same convex Minkowski identity, $x_i \ge 1.0$, $y_i \ge 1.0$, and $\|c_i\| \le S - 1.0$ are **100% exact, closed-form, smooth (up to boundary cusps), and zero-error**.
- **Feasibility:** **High (~50-100 lines across Rust, Python, Verifier, Renderer).** Note that `get_shape_geometry` polygon approximation should **not** be used; like `CIRCLE` today, both require dedicated analytic branches in `solver.rs`, `geometry.py`, `solution_tools.py`, and `<path d="M ... A ... Z">` SVG rendering in `render_packing.ts` / `shape_badge.ts`.

##### Scope 2B: `SEMICIRCLE` or `QUADRANT` as General Inner Shapes or Containing Polygons
- **Mathematical Wall:**
  1. Pure SAT **cannot** check arc-to-edge or arc-to-arc collisions cleanly. Approximating the arc with a $k$-gon (even 32-gon) leaves chordal undercuts of $1 - \cos(\pi/32) \approx 0.48\%$ and fails `VERIFY_SAT_TOLERANCE = 1e-5` on true tight Packomania packings, violating the verification fence in `docs/geometry_and_verification_audit.md:93`.
  2. Exact inner-vs-inner **Semicircle-vs-Semicircle** or **Semicircle-vs-Polygon** collision requires solving:
     - Edge-to-edge intersection (straight chord vs. polygon edge / other chord).
     - Exact shortest signed distance from every vertex to the opposing semicircle (point-in-sector vs chord + arc Voronoi regions).
     - **Arc-to-segment intersection** (quadratic projection onto segment $[a,b]$, clamping $t \in [0,1]$, checking if vector from arc center to closest point falls inside the semicircle's active angular interval $[\theta_i, \theta_i + \pi]$!).
     - **Arc-to-arc intersection** (two circular arcs of radii $1.0$ overlap if center distance $< 2.0$ AND the intersection lens midpoint / endpoints lie inside **both** angular half-planes $n_i \cdot (p - c_i) \ge 0$!).
     - Smooth $C^1$ penalty gradients break at the $90^\circ$ corner vertices where flat chords meet curved arcs, causing L-BFGS-B line searches to stall without carefully damped SDF clamping.
- **The Critic's Verdict on Packomania Circle Packings:**
  Even if you implement Scope 2A cleanly, consider **why** you want Packomania's `circle_in_semicircle` and `circle_in_quadrant`:
  - Those Packomania tables have been optimized for decades up to $N = 100\text{--}1000+$ by specialized circle-only billiard/NLP/basin algorithms tailored specifically to isotropic disks and kissing-graph perturbations.
  - Our general rigid-body polygon engine (`Adam + L-BFGS-B + 10 random perturbations`) is unlikely to break Packomania's circle-in-semicircle or circle-in-quadrant records for moderate $N$. Its value there would be **benchmark validation and completeness**, whereas packing **polygons inside semicircle/quadrant** (or semicircles inside polygons) genuinely enters uncharted territory where nobody maintains tables.

---

### 4.3. Tier 3: Affine / Parametric Quadrilaterals (`TRAPEZOID`, `RHOMBUS`, `PARALLELOGRAM`)

#### The Fundamental Ambiguity
In geometry, triangles (equilateral) and regular $n$-gons have **0 shape degrees of freedom** beyond uniform scale $S$. By contrast:

| Shape | Degrees of Freedom (modulo scale & rotation) | What User Has Not Specified |
| :--- | :--- | :--- |
| **Rhombus** | **1 parameter:** acute angle $\alpha \in (0^\circ, 90^\circ)$ | Is it a $60^\circ$ diamond (2 equilateral triangles)? $45^\circ$ Penrose rhombus? $72^\circ$? Variable $\alpha$? |
| **Parallelogram** | **2 parameters:** side ratio $b/a > 0$, angle $\alpha \in (0^\circ, 90^\circ)$ | Is it the Tangram parallelogram ($b/a = \sqrt{2}, \alpha = 45^\circ$, stubbed in `packing_config.py:341`)? $1:2$ at $60^\circ$? Variable $(b/a, \alpha)$? |
| **Trapezoid** | **3 parameters:** top/bottom ratio $b_2/b_1$, leg angle(s) / height | Is it an isosceles half-hexagon ($1:2:1:1$, $60^\circ$)? Right trapezoid? Or arbitrary convex trapezoid? |

This ambiguity splits into **two completely different software problems**:

#### Case 3A: Fixed Canonical Prototypes (Like `DOMINO` = $1\times 2$ Rectangle, `TAN` = $45^\circ$-$45^\circ$-$90^\circ$ Triangle)
- **Example prototypes:**
  - `RHOMBUS` (e.g., $60^\circ$ rhombus, side $= 1.0$, diagonals $\sqrt{3}$ and $1.0$).
  - `PARALLELOGRAM` (e.g., Tangram parallelogram: base $\sqrt{2}$, slanted edge $1.0$, $45^\circ$, already drafted at `packing_config.py:341-348`).
  - `TRAPEZOID` (e.g., 3-triangle regular isosceles trapezoid: bases $1.0$ and $2.0$, legs $1.0$, $60^\circ$ base angles).
- **Feasibility:** **VERY HIGH.** All three are convex 4-gons! Once centered at origin (or incenter/circumcenter) with unit edge length $1.0$ (matching `TAN`/`DOMINO`), they plug **directly** into existing convex SAT overlap (`solver.rs:1464`, `geometry.py:362`, `solution_tools.py:525`) and half-plane containment with **zero physics algorithm changes**.
- **Critic's Caution on Symmetry & Novelty:**
  - Every rhombus and parallelogram **tiles the plane edge-to-edge**. Packing congruent rhombuses into squares, hexagons, or circles exhibits strong lattice structure, and `60_rhombus` or `halfhex_trapezoid` at small $N$ often behaves like clustered triangles.
  - Because **nobody publishes benchmark tables** for `rhombus_in_circle` or `trapezoid_in_5`, `priority_queue.json`, gap scores, and `NEW_BEST` vs. literature **do not apply**. You are generating *original baseline datasets* rather than beating external records, which is valuable for novelty ("things nobody has done") provided the website clearly separates **Reference Benchmarks** (Friedman/Packomania) from **Original Frontier** families!

#### Case 3B: Parametric / Arbitrary Shape Optimization (Like `cirinel` Ellipses & `cirinttt` Arbitrary Triangles)
- **What it means:** Optimizing *both* the $N$ piece placements $(x_i, y_i, \theta_i)$ AND the container's aspect ratio / vertex parameters $(p_1, p_2, \dots)$ to minimize **Area** (fixing `Area` normalization instead of edge scale `S`).
- **Feasibility:** **Low without major refactoring.**
  1. `optimization.py` and `solver.rs` optimize a fixed geometry template scaled by scalar `S` via outer binary/multiplicative shrinking (`S *= 0.99`). They cannot differentiate with respect to vertex positions `V(p)`.
  2. `database.py`, `ranker.py`, and `site_data.json` store a single scalar `metric_s` and `[x, y, theta]` positions; they have no schema for variable container parameters `[a, b]` or arbitrary triangle side triples `[a, b, c]`.
  3. Notice that even `cirinel` and `cirinttt` (which ARE on Erich Friedman's site and ALREADY in `data/packingVerification/`) remain marked `unsupported` for this exact architectural reason.

---

## 5. Comprehensive Effort & Risk Matrix

| Candidate Expansion | Core Geometry Complexity | Pipeline Touchpoints | External Benchmark Exists? | Recommended Action |
| :--- | :--- | :--- | :--- | :--- |
| **`7`, `9`, `10` Polygons** | **Already Done** (generic $n$-gon SAT & metric) | 6 Python/TS allowlist/badge files | **Partial:** Packomania `circle_in_{7,9,10}` only | Clean up the 6 hardcoded lists + fix `build_site_data.py` bugs; selectively enable `circle_in_{7,9,10}` or opt-in pairs (avoid blind 144-family explosion). |
| **`SEMICIRCLE` / `QUADRANT` (Circle Containers)** | **Low** (2–3 exact closed-form SDF bounds) | `solver.rs`, `geometry.py`, `solution_tools.py`, SVG path renderer, `database.py` | **Yes:** Packomania `circle_in_semicircle` & `circle_in_quadrant` | Feasible and mathematically clean if scoped strictly to **containers for `CIRCLE`**. |
| **`SEMICIRCLE` / `QUADRANT` (Full $N \times N$ Inner + Poly Containers)** | **High** (analytic Chord+Arc collisions + cusp gradients) | Entire collision kernel across Rust, Python, Verifier, SVG | **No** (no Packomania/Friedman tables for polygons/arcs) | **Reject for now (Ponytail YAGNI).** Very high complexity and bug surface; cannot legally approximate with `32`-gon. |
| **Fixed-Shape Convex Quads (`60-Rhombus`, `Tangram-Para`, `HalfHex-Trap`)** | **Very Low** (convex 4-gons work in current SAT!) | New token registry, vertex defs, metric convention ($s$), UI badges, `database.py` | **No** (genuine uncharted frontier) | **Feasible** if canonical aspect/angles and `s=1` definitions are pinned upfront and separated cleanly from benchmarked families on the site. |
| **Arbitrary/Parametric Shapes (`Arbitrary Trapezoid`, `cirinel`, `cirinttt`)** | **High** (variable-shape area minimization, `V(p)` gradients) | New optimizer architecture, DB schema, JSON export, UI plate | **Yes** for `cirinel` (24) & `cirinttt` (31) only | Defer until after static shape pipeline is cleaned up; solve `cirinel`/`cirinttt` first if you ever want variable containers. |

---

## 6. Three Brainstormed Approaches (Architectural Options)

### Approach A: Ponytail Surgical Cleanup + Unblock Existing Capabilities (Recommended First Step)
**What:** Fix the 7 latent codebase drifts listed in Section 2.4 (`build_site_data.py` `L` metric bug, `lincir` mislabeling, `problems.py` case-sensitivity, `L` rotational gradient, shrink `theta` scaling). Refactor the 6 `{3,4,5,6,8}` hardcodes into generic $n$-gon support ($n \in [3, 10]$) driven by a single shared problem catalog rather than a forced $K \times K$ cross product. Import `circle_in_7`, `circle_in_9`, `circle_in_10` from Packomania (plus keep `cirinoct` & `cirindom` clean).
- **Pros:** Minimal code, fixes real bugs affecting current packings, immediately unlocks `7/9/10` cleanly without wasting cluster cycles on 60 unbenchmarked families.
- **Cons:** Does not yet add semicircles, quadrants, or quadrilaterals.

### Approach B: Asymmetric Capability Expansion ("Curved Circle-Containers + Canonical Quads")
**What:** Everything in Approach A **plus**:
1. Add a **Curved Container Interface** in Rust/Python/Verifier/TS supporting `SEMICIRCLE` and `QUADRANT` strictly for `CIRCLE` packings (closed-form 0.0% error), importing Packomania's `circle_in_semicircle` and `circle_in_quadrant` benchmarks.
2. Add **2-3 pinned canonical convex quadrilaterals** (e.g., `RHOMBUS60`, `PARALLELOGRAM_TAN`, `TRAPEZOID_HEX`), explicitly typed as **"Frontier / Unbenchmarked Families"** so `ranker.py` and the site dashboard handle `benchmark_s: null` gracefully alongside benchmarked Friedman/Packomania families.
3. Introduce a single declarative **Shape Registry** (or shared JSON spec consumed by Python/TS and mirrored/validated by Rust tests) so future convex shapes require adding 1 data entry instead of patching 12 files.
- **Pros:** Delivers every shape type mentioned by the user ("7, 9, 10", "semicircle/quadrant", "trapezoid/rhombus/parallelogram") with high geometric rigor and zero fragile arc-to-arc physics hacks.
- **Cons:** Medium upfront refactoring to replace implicit $K \times K$ assumptions with capability-aware family generation (`supported_pairs`).

### Approach C: Full General Geometry Engine (Hybrid Arcs + Arbitrary Parametric Shapes)
**What:** Rewrite the collision and optimization engines to support piecewise straight+arc shapes (`SEMICIRCLE`/`QUADRANT` as inner shapes and polygon containers) AND variable-shape Area optimization (`cirinel`, `cirinttt`, arbitrary trapezoids/rhombuses).
- **Pros:** Maximum mathematical generality; unlocks `cirinel`/`cirinttt` already sitting in `data/packingVerification/`.
- **Cons:** Major multi-week rewrite across Rust SIMD/L-BFGS gradients, Python verifier, SQLite schema, and Astro viewer. High risk of numerical gradient discontinuities at arc corners and breaks the current scalar `metric_s` model.

---

## 7. Open Design Decisions Required Before Implementation

1. **Shape Registry Coupling:** Do we stop treating all shapes as an automatic $K \times K$ grid and instead support asymmetric capability pairs (e.g., `CIRCLE in SEMICIRCLE` allowed, `DOMINO in SEMICIRCLE` forbidden)?
2. **Quadrilateral Canonicalization:** Which exact fixed aspect ratios / angles define your `TRAPEZOID`, `RHOMBUS`, and `PARALLELOGRAM` (or are you envisioning variable-parameter optimization)?
3. **Unbenchmarked Frontier UX:** Since nobody maintains tables for `7_in_9`, `trapezoid_in_5`, or `rhombus_in_circle`, how should the site leaderboard, ranker, and worker priority queue treat families with no external reference target?
4. **Centroid / Origin Convention for Asymmetric Shapes:** Unlike regular $n$-gons (`(0,0)` = circumcenter), `SEMICIRCLE` and `TRAPEZOID` have non-coincident circumcenters, area centroids, and half-plane origins. One explicit origin and Friedman metric $s$ convention must be standardized per shape before writing any verification code.
