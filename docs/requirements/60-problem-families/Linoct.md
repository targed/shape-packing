# Linoct: L-tromino in Octagon

Family: N_L_in_oct (N L-trominoes inside a regular octagon container).

1. Geometry:
- WHEN inner is "L" and container is "oct" THEN:
  - use a canonical L-tromino definition and a regular octagon.
  - Scaling SHALL be derived from S via a documented rule.

2. Validity:
- WHEN a solution is generated THEN:
  - all inner L-trominoes SHALL be inside the octagon.
  - no two inner shapes SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison:
- WHEN comparing to Friedman THEN:
  - use an explicit, documented conversion from S to his unit.
  - NEW_BEST is valid only if geometry and metric alignment are confirmed.

4. Test Expectations:
- Tests SHALL include:
  - construction of both shapes.
  - a valid packing.
  - an overlapping pair.
  - a boundary-violation case.
