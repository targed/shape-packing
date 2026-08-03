# octinoct: Octagon in Octagon

Family: N_oct_in_oct (N octagons inside an octagon container).

1. Geometry:
- WHEN both inner and container are "oct" THEN:
  - both SHALL use the same canonical octagon shape.
  - Scaling SHALL be derived from S via a documented rule.

2. Validity:
- WHEN a solution is generated THEN:
  - all inner octagons SHALL be inside the container.
  - no two inner octagons SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison:
- WHEN comparing to Friedman THEN:
  - use an explicit, documented conversion from S to his unit.
  - NEW_BEST is valid only if geometry and metric alignment are confirmed.

4. Test Expectations:
- Tests SHALL include:
  - construction of octagon shapes.
  - a valid packing.
  - an overlapping pair.
  - a boundary-violation case.