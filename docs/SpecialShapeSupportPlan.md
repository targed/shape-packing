Special Shape Support Plan (Tan, Domino, L)

Purpose:
Explain why Tan/Domino/L are missing from current runs, and outline concrete steps to add support without breaking existing polygon behavior.

1. Current situation

- On Friedman's site:
  - Tan, Domino, and L-shape (L-tromino) are widely used in both containers and as packed shapes.
- In our code:
  - They appear conceptually:
    - packing_config.py lists families like “Tans in Circles”, “L’s in Squares”.
  - They are NOT actually supported in the solver:
    - geometry.py assumes regular polygons with:
      - unit_polygon_vertices
      - unit_polygon_vectors (normals)
      - unit_container_vectors
      - unit_container_apothem
    - These are built for regular, rotationally symmetric shapes.
    - Tan/Domino/L are not regular polygons.
  - agent_loop.py:
    - Treats them as “special shapes” (SPECIAL_SHAPES).
    - Filters them out by default unless include_inner / include_container explicitly allow them.
    - Result: they never appear in normal problem selection.

So: the list in packing_config.py is aspirational, not operational.

2. Why they don’t work today

Our SAT-style overlap/boundary checks in bh_objective rely on:
- A fixed number of edges nsi (inner) and nsc (container).
- Uniformly constructed vertices and normals for a regular polygon.

Issues for Tan/Domino/L:

- Different geometry:
  - Domino: 1x2 rectangle (4 edges, but fixed aspect ratio).
  - L-tromino: 6-edge orthogonal shape.
  - Tan: fixed parallelogram/trapezoid shape.
- Not rotation-invariant in the same way:
  - Their geometry cannot be fully described by a single radius and a single angle step.
- Not handled in the hot path:
  - bh_objective currently takes:
    - unit_polygon_vertices: (nsi x 2) array for a regular shape.
    - unit_polygon_vectors: (nsi x 2) normals.
  - For special shapes:
    - These must be hand-coded.
    - Their container geometry may also be special (if the container is a Tan/L).

So we must:
- Extend geometry.py to handle:
  - Non-regular inner polygons.
  - Non-regular container polygons.
- Update packing_config.py and agent_loop.py to expose and select these problems safely.

3. High-level design

Key constraints:
- No changes to core behavior for existing regular polygons.
- Keep Numba-friendly bh_objective.
- Localize changes (no global rewrite).

We’ll:

- Treat special shapes as “unit polygons with a fixed vertex set.”
- Provide per-shape definitions:
  - unit_vertices (relative to center)
  - unit_vectors (outward normals per edge)
- Keep:
  - S as a uniform scale factor (same geometric meaning: how big the container is).
- Extend:
  - The geometry construction step so that:
    - If inner/outer is special:
      - Use custom vertices/vectors instead of regular-polygon formulas.

4. Step-by-step plan

Step 1: Normalize “unit” definitions

- For each special shape, define a canonical unit version:
  - Domino:
    - 1x2 rectangle centered at (0,0), sides parallel to axes.
  - L-tromino:
    - Standard L formed from three unit squares:
      - Use coordinates so that:
        - Its area is 3.
        - It is centered at (0,0).
  - Tan:
    - Use the standard tangram parallelogram/trapezoid definition (as used by Friedman).
      - Must verify exact orientation and scale from Friedman's site.
- This ensures:
  - Our “unit” shape matches Friedman’s “unit” shape.
  - This alignment is critical for correct comparison.

Step 2: Extend geometry.py

Current pattern (regular polygons):

- regular_polygon_vertices(sides, radius)
- regular_polygon_outward_normals(sides)
- GeoConfig(unit_polygon_vertices, unit_polygon_vectors, ...)

We’ll add:

- Helper functions:
  - get_special_inner_geometry(shape_token)
  - get_special_container_geometry(shape_token)

Each returns:
- vertices: (m x 2) array
- vectors: (m x 2) outward normals

Example for Domino:

- Domino:
  - Vertices (for 1x2 rectangle centered at 0):
    - (-1, -0.5), (1, -0.5), (1, 0.5), (-1, 0.5)
  - Normals:
    - (0, -1)
    - (1, 0)
    - (0, 1)
    - (-1, 0)

Integration into GeoConfig:

- When creating GeoConfig:
  - If inner_token in SPECIAL_SHAPES:
    - Use get_special_inner_geometry(inner_token)
  - Else:
    - Use regular_polygon_vertices(inner_sides, radius=1)
  - Similar for container.

Important:
- Keep these in pure NumPy.
- Ensure they’re Numba-compatible when passed into bh_objective.

Step 3: Ensure bh_objective remains valid

bh_objective currently uses:
- unit_polygon_vertices (N, nsi, 2)
- unit_polygon_vectors (N, nsi, 2)
- unit_container_vectors, unit_container_apothem

We must:
- Confirm:
  - The SAT checks only depend on vertices and edge normals.
  - This is shape-agnostic (convex polygon SAT works for any convex polygon).
- For domino and many L-shapes/Tan:
  - SAT still applies (convex shapes: domino, Tan; for non-convex L, see below).

Edge cases:
- L-tromino:
  - Is concave, so SAT with only edge normals is not sufficient for overlap checks.
- Options:
  - Decompose L into convex components (e.g., 2 rectangles or 3 unit squares) and:
    - Check SAT per component.
  - This is more involved; may be best done after convex shapes (domino/Tan) are supported.

So recommended order:
- First: support convex special shapes:
  - Domino
  - Tan
- Second: L-tromino (concave), possibly with decomposition.

Step 4: Extend container support

We currently only use:
- Regular polygon containers + circle (32-gon).

We now need:
- Special containers as well (e.g. Tan-in-Tan, L-in-L, etc.)

Approach:
- Similar logic as inner shapes:
  - If container_token in SPECIAL_SHAPES:
    - Use get_special_container_geometry(container_token)
- Adjust:
  - unit_container_vectors: derived from container’s edge normals.
  - unit_container_apothem: for irregular containers, define as:
    - Minimum distance from center to any edge (inward).
    - Or equivalent projection limit.
  - This keeps poking_penalty concept valid.

This is straightforward once the geometry helpers exist.

Step 5: Update packing_config.py and agent_loop.py

Currently:
- SPECIAL_SHAPES = {"TAN", "DOMINO", "L"}
- agent_loop.py skips them unless explicitly included.

After implementing geometry:

- Update packing_config.py:
  - Clarify which special shapes are now fully supported vs partially supported.
- Update agent_loop.py:
  - In is_unsupported and choose_problem:
    - Allow TAN and DOMINO by default.
    - Possibly allow L once it is implemented.
  - Keep explicit controls (include_inner, include_container) for fine-tuning.

Step 6: Align naming and Friedman mapping

We must ensure:
- Our problem names match:
  - e.g., 10_TAN_in_CIRCLE corresponds cleanly to Friedman’s “Tans in Circles N=10”.
- For packingVerification:
  - Define:
    - inner_shape = "TAN" / "DOMINO" / "L"
    - container_shape as appropriate
  - Confirm Friedman’s “unit” definitions:
    - For each shape, compare our canonical unit with his images/text.

This alignment is necessary so that:
- final_metric or S-based comparisons are meaningful.

5. Recommended rollout order

To avoid large, risky changes:

- Phase 1: Domino (convex rectangle)
  - Simplest: 4 edges, easy normals, fits SAT.
  - Great first test to validate the new geometry pipeline.
- Phase 2: Tan
  - Slightly more complex but still convex.
  - Confirms we can support a non-symmetric shape.
- Phase 3: L-tromino
  - Requires handling concavity.
  - Either decompose into convex parts or extend the SAT logic.
  - Treat this as advanced; only after Domino/Tan work cleanly.

6. What is NOT required

We do NOT need to:
- Rewrite the solver core.
- Abandon the current regular-polygon handling.
- Break existing results.

We are adding:
- A small geometry layer that:
  - Chooses custom vertices and normals when a special shape token is detected.

If you'd like, I can turn this into a concrete implementation plan (with exact code changes) for Domino as the first shape.

---

# DOMINO Implementation Documentation (Added 2026-07-29)

We have successfully implemented DOMINO support across both the Python toolchain and the Rust solver engine.

### Changes Made:
1. **Geometry Pipeline (`src/shape_packing/geometry.py`)**:
   - Introduced `get_shape_geometry(token: str)` which returns the number of sides, vertices, normals, and apothem based on the string token.
   - For `"DOMINO"`, it returns a 1x2 rectangle with vertices `[(-1.0, -0.5), (1.0, -0.5), (1.0, 0.5), (-1.0, 0.5)]` and appropriate normals.

2. **Python Solver & Tools (`src/shape_packing/optimization.py`, `polygon-packer/polygon_packer.py`, `solution_tools.py`)**:
   - Upgraded `PackingProblem` and `Solution` dataclasses to use `inner_token` and `container_token` strings instead of integers `nsi` and `nsc`.
   - Replaced direct calls to `regular_polygon_vertices` with `get_shape_geometry` so special shapes are routed and handled smoothly during verification and rendering.

3. **Rust Solver (`packer_rs/src/main.rs`)**:
   - Updated the CLI to parse `inner_shape` and `container_shape` as strings rather than integers.
   - Used the string tokens to construct the appropriate vertices and normals inside `get_shape_geometry`.
   - Updated the `serde_json_to_string` serialization to output the string tokens in the solution JSON (`inner_token` and `container_token`).

4. **Agent Loop (`src/shape_packing/agent_loop.py`)**:
   - Modified the `is_unsupported` function to allow `"DOMINO"` by default. Problems like `5_DOMINO_in_4` are now seamlessly handled by the experimentation loop.

### How it works:
When the loop or user requests a run with a `DOMINO`, the string token `"DOMINO"` propagates all the way into both the Python plotting/verification scripts and the Rust solving engine. Both ecosystems use a `get_shape_geometry` mapping function to retrieve custom arrays of vertices and normals for the SAT collision checks. By changing the `nsi` and `nsc` variables into strings everywhere, we opened the door for any arbitrary special shape without compromising the existing Numba/Rust math logic.

### How to use it:
To run a test with DOMINO, simply invoke the CLI with DOMINO as the inner shape token. For example:
```bash
python -m src.shape_packing.cli run --problem 5_DOMINO_in_4 --attempts 10
```
This is fully supported, renders appropriately via `render_solution.py`, and is verifiable via `verify_solution.py`.

---

# TAN Implementation Documentation (Added 2026-07-29)

Following the same pattern as DOMINO, we have also successfully implemented TAN support across both the Python toolchain and the Rust solver engine.

### Changes Made:
1. **Geometry Pipeline (`src/shape_packing/geometry.py`)**:
   - Expanded `get_shape_geometry(token: str)` to support the `"TAN"` token.
   - For `"TAN"`, it returns a right isosceles triangle (with legs 1, 1, hypotenuse sqrt(2)) centered at its incenter. 
   - Vertices: `[[-r, -r], [1.0 - r, -r], [-r, 1.0 - r]]` where `r = 1.0 - sqrt(2.0)/2.0`.
   - By centering it at the incenter, the distance to all 3 edges is perfectly represented by the single `apothem = r`, making it compatible with both `inner_shape` and `container_shape` logic.

2. **Rust Solver (`packer_rs/src/main.rs`)**:
   - Updated `get_shape_geometry` in Rust to identically mirror the Python TAN definition with exact vertices, normals, and apothem derived from the inradius.

3. **Agent Loop (`src/shape_packing/agent_loop.py`)**:
   - Modified `is_unsupported` to explicitly allow `"TAN"` by default, alongside `"DOMINO"`.

### How to use it:
You can now run tests with TAN as well:
```bash
python -m src.shape_packing.cli run --problem 5_TAN_in_4 --attempts 10
```
As with DOMINO, the solutions will successfully generate, verify, and render properly!
