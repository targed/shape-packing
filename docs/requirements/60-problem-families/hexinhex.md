# hexinhex: Hexagon in Hexagon

Family: N_hex_in_hex (N hexagons inside a hexagon container).

1. Geometry:
- WHEN both inner and container are "hex" THEN:
  - both SHALL use the same canonical hexagon shape.
  - Scaling SHALL be derived from S via a documented rule.

2. Validity:
- WHEN a solution is generated THEN:
  - all inner hexagons SHALL be inside the container.
  - no two inner hexagons SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison:
- WHEN comparing to Friedman THEN:
  - use an explicit, documented conversion from S to his unit.
  - NEW_BEST is valid only if geometry and metric alignment are confirmed.

4. Test Expectations:
- Tests SHALL include:
  - construction of hexagon shapes.
  - a valid packing.
  - an overlapping pair.
  - a boundary-violation case.