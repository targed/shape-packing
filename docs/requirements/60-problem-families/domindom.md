# domindom: Domino in Domino

Family: N_dom_in_dom (N dominoes inside a domino container).

1. Geometry:
- WHEN both inner and container are "dom" THEN:
  - both SHALL use the same canonical domino shape.
  - Scaling SHALL be derived from S via a documented rule.

2. Validity:
- WHEN a solution is generated THEN:
  - all inner dominoes SHALL be inside the container.
  - no two inner dominoes SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison:
- WHEN comparing to Friedman THEN:
  - use an explicit, documented conversion from S to his unit.
  - NEW_BEST is valid only if geometry and metric alignment are confirmed.

4. Test Expectations:
- Tests SHALL include:
  - construction of domino shapes.
  - a valid packing.
  - an overlapping pair.
  - a boundary-violation case.
