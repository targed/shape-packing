# tanindom: Tan in Domino

Family: N_tan_in_dom (N tans inside a domino container).

1. Geometry:
- WHEN inner is "tan" and container is "dom" THEN:
  - both SHALL use canonical definitions.
  - scaling SHALL be derived from S via a documented rule.

2. Validity:
- WHEN a solution is generated THEN:
  - all tans SHALL be inside the domino.
  - no two tans SHALL overlap beyond tolerance (≤ 1e-15).

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