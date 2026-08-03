# triintri: Triangle in Triangle

Family: N_tri_in_tri (N triangles inside a triangle container).

1. Geometry:
- WHEN both inner and container are "tri" THEN:
  - both SHALL use the same canonical triangle shape.
  - scaling SHALL be derived from S via a documented rule.

2. Validity:
- WHEN a solution is generated THEN:
  - all inner triangles SHALL be inside the container.
  - no two inner triangles SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison:
- WHEN comparing to Friedman THEN:
  - use an explicit, documented conversion from S to his unit.
  - NEW_BEST is valid only if geometry and metric alignment are confirmed.

4. Test Expectations:
- Tests SHALL include:
  - construction of triangle shapes.
  - a valid packing.
  - an overlapping pair.
  - a boundary-violation case.