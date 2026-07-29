Circle Containers: Current Situation, Risks, and Cautious Path

Last updated: 2026-07-29

Purpose:
Single source of truth for how circle containers are handled, why they are currently marked incomparable, what we know from empirical checks, and the cautious path forward.

1. High-level summary

- Today:
  - For problems with circle containers (e.g. 10_6_in_CIRCLE, 10_3_in_CIRCLE), compare_results.py:
    - Skips direct comparison against Friedman’s best_value.
    - Marks them as:
      “incomparable (circle)”.
- Why:
  - Our S and final_metric were derived for polygon containers.
  - Circle containers:
    - Are approximated as a regular 32-gon.
    - Use formulas not aligned with Friedman’s radius metric r.
- Current decision:
  - Do not trust our existing final_metric for circles.
  - Do not claim NEW_BEST for circle problems based on the old (broken) formula.
  - Keep circles as incomparable until we have a verified mapping.

2. How we model circles internally

- Container:
  - container_token = "CIRCLE"
  - Implemented as a regular polygon with container_sides = 32
  - S is the scale factor for this 32-gon.
- Inner shapes:
  - For polygons: unit size is defined via circumradius = 1.
  - This is consistent for polygon-in-polygon and circle containers.
- final_metric (current, polygon-based):
  - Formula used:
    - final_metric = S * sin(π / container_sides) / sin(π / inner_sides)
  - This was designed to normalize scores across different (polygon, polygon) pairs.
  - For a 32-gon container, it produces small values (e.g. 0.3–0.7) that do not match Friedman’s r at all.

3. How Friedman defines circle problems

- Friedman’s metric for circle containers is always:
  - r = radius of the smallest known containing circle.
- Examples:
  - Circles in Circles:
    - “n unit circles packed inside the smallest known circle (of radius r)”
  - Triangles in Circles:
    - “n equilateral triangles with side 1 packed inside the smallest known circle (of radius r)”
  - Hexagons in Circles:
    - “n unit hexagons packed inside the smallest known circle (with radius r)”
- Critical point:
  - Friedman’s unit is defined in a problem-specific way:
    - For triangles: “side 1”
    - For hexagons: “unit hexagons” (effectively side length 1)
  - Our solver uses:
    - Inner shapes with circumradius 1.
  - This mismatch in unit definitions is a primary source of scale differences.

4. Known issues with current circle handling

- Issue 1: Wrong metric (final_metric vs r)
  - We compare final_metric (designed for polygons) against r (radius of container circle).
  - These are not dimensionally equivalent for circles:
    - final_metric uses sin(π/32) scaling;
    - r is a pure geometric radius.
  - Result: large spurious differences; unreliable “NEW_BEST” flags.

- Issue 2: Unit-size mismatch
  - Friedman:
    - Triangles: side 1
    - Hexagons: side 1
    - Circles: radius 1
  - We:
    - Always use inner shapes with circumradius 1.
  - For some shapes this matches (e.g. circles: radius = 1),
    for others (e.g. triangles) it does not, causing systematic offsets.

- Issue 3: 32-gon approximation vs true circle
  - A regular 32-gon is very close to a circle, but not identical.
  - Any comparison must account for:
    - The fact that S is for a 32-gon, while Friedman’s r is for a true circle.
  - For many practical N, this difference is tiny compared to unit mismatch,
    but it is not zero.

5. Empirical observations (Option A, cautious checks)

We performed targeted checks (no code changes) comparing Friedman’s r with our best S for circle containers.

Hexagons in Circles (promising):

- 10_6_in_CIRCLE:
  - Friedman r: 3.48172
  - Our S: 3.493711
  - Relative difference: ~+0.35%
- 13_6_in_CIRCLE:
  - Friedman r: 3.82289
  - Our S: 3.831711
  - Relative difference: ~+0.23%
- Observations:
  - S is extremely close to Friedman’s r.
  - This suggests that:
    - For hexagons:
      - Our S ≈ Friedman’s r,
      - and our circumradius-based “unit hexagon” is effectively aligned with Friedman’s “unit hexagon” for these N.
  - Hypothesis:
    - For hexagons in circles, final_metric_for_comparison = S is a good approximation (after verification).

Triangles in Circles (mismatched scale):

- 10_3_in_CIRCLE:
  - Friedman r: 1.38468
  - Our S: 3.066754
- 12_3_in_CIRCLE:
  - Friedman r: 1.507
  - Our S: 3.360469
- Observations:
  - S is far larger than r (off by factor ~2.2).
  - Cause: unit mismatch:
    - Friedman: side 1
    - Us: circumradius 1 (which is larger)
  - Hypothesis:
    - For triangles:
      - r ≈ S * (Friedman’s side-to-circumradius conversion factor).
  - This requires derivation/verification per N before we can use S vs r.

Key conclusions from empirical checks:

- We can compare circle containers, but:
  - Not with our current final_metric.
  - Only via S, with a shape-specific mapping to Friedman’s r.
- For hexagons in circles:
  - S ≈ r (very strong evidence).
- For triangles in circles:
  - S and r differ by a predictable scale factor, but must be derived.

6. What is NOT allowed right now

Until we implement a verified mapping, do not:

- Use the existing final_metric for circle containers in compare_results.py.
- Claim “NEW_BEST” for circle problems based on the old formula.
- Treat circles as directly comparable without:
  - Explicit, documented, per-shape conversion from S to r.

7. Cautious path forward (Option A)

This is the recommended approach: conservative, step-by-step, reversible.

Step 1: Isolate circle logic

- In compare_results.py:
  - Keep circles as “incomparable (circle)” by default.
  - Add a dedicated section:
    - For each circle problem:
      - Show:
        - Friedman best_value (r)
        - Our best S
      - Label: “needs mapping” instead of a difference or NEW_BEST.

Step 2: Validate hexagon-in-circle mapping

- For multiple N (e.g. 8, 10, 11, 12, 13, 14, 15):
  - Compare Friedman r with our S.
- If consistently within <1%:
  - Define:
    - final_metric_for_comparison = S for hexagons_in_circle.
  - Update compare_results.py with:
    - A small, documented, hexagon-specific rule.
- Only then:
  - Enable comparison and NEW_BEST flags for hexagons_in_circle.

Step 3: Derive triangle-in-circle mapping

- Compute theoretical factor:
  - For equilateral triangle with:
    - side a = 1
    - circumradius R = a / (sqrt(3))
  - Our unit triangle uses circumradius 1, so:
    - Our triangle is larger by a factor of (1 / R) relative to Friedman.
- Verify with several N (e.g. 10, 11, 12, 13):
  - Compare Friedman r with S * (conversion factor).
- If alignment is strong:
  - Introduce a triangle-specific mapping.

Step 4: Extend to other shapes in circles

- For each inner shape (pentagons, etc.) that appears:
  - Repeat:
    - Compute unit-size mapping (circumradius vs Friedman’s definition).
    - Compare S * factor vs r across 3+ N.
  - Only enable comparison once verified.

8. Risks if we change too early

- False NEW_BEST claims:
  - Could look good but be mathematically invalid.
- Misaligned metrics:
  - Might silently encourage wrong design decisions in solver.
- Loss of trust:
  - If our comparison logic is unclear, future collaborators (or ourselves) will distrust all results.

9. Open questions (to answer later)

- For each (inner_shape, circle):
  - Confirm exact mapping from S to Friedman’s r.
- Should we:
  - Store both S and r_equivalent in solution.json for circle problems?
- Should we:
  - Add a field “metric_type”: “S_polygon”, “r_circle”, etc. to make this explicit?

End of document.
