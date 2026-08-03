# dominpen: Domino in Pentagon

Family: N_dom_in_pen (N dominoes inside a regular pentagon container).

1. Geometry:
- WHEN inner is "dom" and container is "pen" THEN:
  - domino and pentagon use canonical definitions.
  - Scaling SHALL be derived from S via a documented rule.

2. Validity:
- WHEN a solution is generated THEN:
  - all dominoes SHALL be inside the pentagon.
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
