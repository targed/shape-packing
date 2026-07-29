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
