# minrect: Minimum Rectangle Problems

Family: minrect (N shapes packed into a minimal rectangle container).

1. Geometry:
- WHEN the minrect family is used THEN:
  - the container SHALL be a rectangle with adjustable dimensions.
  - inner shapes SHALL use canonical definitions.

2. Validity:
- WHEN a solution is generated THEN:
  - all shapes SHALL be fully inside the rectangle.
  - no two shapes SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison:
- WHEN comparing to Friedman THEN:
  - the metric SHALL use his defined measure (e.g., rectangle area or side).
  - NEW_BEST is valid only if geometry and metric alignment are confirmed.

4. Test Expectations:
- Tests SHALL include:
  - construction of rectangle and inner shapes.
  - a valid packing.
  - an overlapping pair.
  - a boundary-violation case.