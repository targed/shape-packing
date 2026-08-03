# tanintan: Tan in Tan

Family: N_tan_in_tan (N tans inside a Tan container).

1. Geometry:
- WHEN both inner and container are "tan" THEN:
  - both SHALL use the same canonical Tan shape.
  - scaling SHALL be derived from S via a documented rule.

2. Validity:
- WHEN a solution is generated THEN:
  - all inner tans SHALL be inside the container.
  - no two inner tans SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison:
- WHEN comparing to Friedman THEN:
  - use an explicit, documented conversion from S to his unit.
  - NEW_BEST is valid only if geometry and metric alignment are confirmed.

4. Test Expectations:
- Tests SHALL include:
  - construction of Tan shapes.
  - a valid packing.
  - an overlapping pair.
  - a boundary-violation case.