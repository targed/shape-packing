# Tans in Squares Requirements

Family: N_TAN_in_4 (N tans inside a square).

1. Geometry
- WHEN the problem uses token "TAN" THEN:
  - the tan SHALL be defined as a right isosceles triangle with:
    - leg length = 1.0,
    - vertices and normals explicitly specified, not via regular-polygon formulas.
- WHEN the container is "4" THEN:
  - it SHALL be a square defined by 4 vertices with circumradius S.

2. Validity
- WHEN a solution is generated THEN:
  - all tan vertices SHALL lie inside or on the square boundary,
  - no two tans SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison
- Friedman’s metric: s = side length of the square that encloses N tans of leg 1.
- WHEN comparing to Friedman THEN:
  - the metric SHALL be s = S * sqrt(2).
- WHEN we claim NEW_BEST THEN:
  - our computed s SHALL be less than Friedman’s s,
  - geometry SHALL be verified,
  - and the result SHALL be within a plausible margin (e.g., < 1% of our best known for that N) to avoid false records.

4. Test Expectations
- WHEN testing this family THEN:
  - there SHALL be tests for:
    - construction of TAN shape,
    - a valid packing inside a square,
    - an overlapping-tan case,
    - a boundary-violation case.
