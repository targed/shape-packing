# LinL: L-tromino in L-tromino

Family: N_L_in_L (N L-trominoes inside an L-tromino container).

1. Geometry:
- WHEN inner and container shapes are both "L" THEN:
  - both SHALL use the same canonical L-tromino definition.
  - Scaling SHALL be done via a documented conversion from S.

2. Validity:
- WHEN a solution is generated THEN:
  - all inner L-trominoes SHALL be inside the container L-tromino.
  - no two inner shapes SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison:
- Friedman’s metric is defined for this family in his source.
- WHEN comparing to Friedman THEN:
  - use an explicit, documented conversion from S to his unit.
  - NEW_BEST is valid only if geometry and metric alignment are confirmed.

4. Test Expectations:
- Tests SHALL include:
  - construction of L-tromino shapes.
  - a valid packing.
  - an overlapping pair.
  - a boundary-violation case.
