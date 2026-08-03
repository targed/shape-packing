# dominL: Domino in L-tromino

Family: N_dom_in_L (N dominoes inside an L-tromino container).

1. Geometry:
- WHEN inner is "dom" and container is "L" THEN:
  - both SHALL use canonical definitions.
  - Scaling SHALL be derived from S via a documented rule.

2. Validity:
- WHEN a solution is generated THEN:
  - all dominoes SHALL be inside the L-tromino.
  - no two dominoes SHALL overlap beyond tolerance (≤ 1e-15).

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
