# Design Spec: Full End-to-End Enablement of the TAN Shape

**Date:** 2026-08-27  
**Status:** Approved  
**Topic:** Enablement of the Tangram Right Isosceles Triangle (`TAN`) across Solver, Agent Loop, Config, and Verification

---

## 1. Goal

Fully enable the `TAN` shape ($45^\circ-45^\circ-90^\circ$ right isosceles triangle) across all subsystems of the shape-packing repository. This enables autonomous selection, optimization solving (Python and Rust engines), verification, priority queue ranking, and rendering for all problem families involving `tan_in_*` and `*_in_tan`.

---

## 2. Background & Mathematical Model

In Erich Friedman's published problems:
- A unit **TAN** is a right isosceles triangle with legs of length $1.0$ and hypotenuse of length $\sqrt{2}$ (area $= 0.5$).
- When **TAN** is a container with scale $S$, its legs have length $S$ (area $= 0.5 S^2$).
- In [`src/shape_packing/geometry.py`](file:///c:/Users/ltkli/Documents/GitHub/shape-packing/src/shape_packing/geometry.py), the incenter is placed at $(0,0)$:
  $$r = 1 - \frac{\sqrt{2}}{2} \approx 0.2928932188$$
  $$\text{Vertices: } (-r, -r), (1-r, -r), (-r, 1-r)$$
  $$\text{Outward Normals: } (0, -1), \left(\frac{\sqrt{2}}{2}, \frac{\sqrt{2}}{2}\right), (-1, 0)$$
  $$\text{Apothem (edge distances from origin): } [r, r, r]$$
- **Metric Scaling:**
  - Container metric $c\_metric = S$
  - Inner scale $i\_scale = 1.0$
  - Friedman metric: $s = \frac{c\_metric}{i\_scale}$

---

## 3. Required Architectural Changes

### 3.1. Problem Selection & Agent Loop (`src/shape_packing/agent_loop.py`)
- In `_is_shape_unsupported(token, filters)`:
  - Remove the block preventing `TAN` from being selected. Treat `TAN` and `DOMINO` as supported special shapes.
  - Add `"TAN"` to `allowed` set.
- In `_parse_filter_sets(filters)`:
  - Normalize `"TAN"` when passed in `--include-inner` or `--include-container`.

### 3.2. Configuration & Legacy Helpers (`src/shape_packing/packing_config.py`)
- Update `tangram_triangle_vertices(size)` to match canonical $45^\circ-45^\circ-90^\circ$ geometry from `geometry.py`:
  $$\text{vertices } = [[-r \cdot \text{size}, -r \cdot \text{size}], [(1-r) \cdot \text{size}, -r \cdot \text{size}], [-r \cdot \text{size}, (1-r) \cdot \text{size}]]$$
- Ensure `SHAPE_TO_SIDES` / `SPECIAL_SHAPES` / `TAN_FAMILIES` are fully recognized in `packing_config.py`.

### 3.3. Solver & Verification Pipeline Integration
- Validate end-to-end solving for `tan` inner shapes and container shapes in:
  - Python continuous optimizer ([`src/shape_packing/optimization.py`](file:///c:/Users/ltkli/Documents/GitHub/shape-packing/src/shape_packing/optimization.py)).
  - Rust solver ([`packer_rs/src/solver.rs`](file:///c:/Users/ltkli/Documents/GitHub/shape-packing/packer_rs/src/solver.rs) via `solver_interface.py`).
  - Verification & plotting ([`src/shape_packing/solution_tools.py`](file:///c:/Users/ltkli/Documents/GitHub/shape-packing/src/shape_packing/solution_tools.py)).

---

## 4. Verification Plan

1. **Unit Tests:**
   - Test `_is_shape_unsupported("TAN", filters)` returns `False` in `tests/test_agent_loop.py`.
   - Test `tangram_triangle_vertices` in `tests/test_packing_config.py`.
   - Test problem parsing and validation for `Problem(2, "TAN", "4")` and `Problem(1, "4", "TAN")` in `tests/test_problems.py`.
2. **Integration Tests:**
   - Solve a known trivial/simple TAN problem (e.g. `1_tan_in_4` or `2_tan_in_4`) via `run_solver` and verify the result passes `verify_solution()`.
   - Test CLI suggest/run commands on TAN problems via `test_cli_integration.py`.
3. **Full Regression Test:**
   - Run `python -m pytest tests/` to ensure 100% test pass rate with zero regressions.
