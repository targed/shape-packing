# squincir: Square in Circle

Family: N_squ_in_CIRCLE (N squares inside a circle container).

1. Geometry:
- WHEN inner is "squ" and container is "CIRCLE" THEN:
  - both SHALL use canonical definitions.
  - scaling SHALL be derived from S via a documented rule.

2. Validity:
- WHEN a solution is generated THEN:
  - all squares SHALL be inside the circle.
  - no two squares SHALL overlap beyond tolerance (≤ 1e-15).

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