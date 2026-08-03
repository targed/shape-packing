# Dominoes in Squares Requirements

Family: N_DOMINO_in_4 (N dominoes inside a square).

1. Geometry
- WHEN the problem uses token "DOMINO" THEN:
  - the domino SHALL be defined using an explicit rectangular vertex set and edge normals
    matching the implemented shape,
  - it SHALL NOT fall back to regular-polygon formulas.
- WHEN the container is "4" THEN:
  - it SHALL be a square defined by 4 vertices with circumradius S.

2. Validity
- WHEN a solution is generated THEN:
  - all domino vertices SHALL lie inside or on the square boundary,
  - no two dominoes SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison
- Friedman’s metric for domino problems is his stated unit and normalization.
- WHEN comparing to Friedman THEN:
  - the metric SHALL be derived from S using a consistent, documented conversion
    that matches the domino’s unit size,
  - NEW_BEST is only valid if:
    - geometry is verified,
    - metric alignment is confirmed.

4. Test Expectations
- WHEN testing this family THEN:
  - there SHALL be tests for:
    - construction of the domino shape,
    - a valid packing inside a square,
    - an overlapping-domino case,
    - a boundary-violation case.
