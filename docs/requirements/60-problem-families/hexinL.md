# hexinL: Hexagon in L-tromino

Family: N_hex_in_L (N hexagons inside an L-tromino container).

1. Geometry:
- WHEN inner is "hex" and container is "L" THEN:
  - both SHALL use canonical definitions.
  - Scaling SHALL be derived from S via a documented rule.

2. Validity:
- WHEN a solution is generated THEN:
  - all hexagons SHALL be inside the L-tromino.
  - no two hexagons SHALL overlap beyond tolerance (≤ 1e-15).

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