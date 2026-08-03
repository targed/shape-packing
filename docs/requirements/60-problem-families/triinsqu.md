# Triangles in Squares Requirements

Family: N_3_in_4 (N triangles inside a square).

1. Geometry
- WHEN the problem uses token "3" for inner shape THEN:
  - triangles SHALL be regular, defined via circumradius-based construction.
- WHEN a square container is used THEN:
  - it SHALL be defined by 4 vertices forming a regular square (circumradius S).

2. Validity
- WHEN a solution is generated THEN:
  - all triangle vertices SHALL lie inside or on the square boundary,
  - no two triangles SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison
- Friedman’s metric: s = side length of the square.
- WHEN comparing to Friedman THEN:
  - the metric SHALL be s = S * sqrt(2).
- WHEN we claim NEW_BEST THEN:
  - our computed s SHALL be less than Friedman’s s,
  - AND geometry SHALL be verified.

4. Test Expectations
- WHEN testing this family THEN:
  - there SHALL be tests for:
    - construction of triangles,
    - a valid packing inside a square,
    - a case where a triangle overlaps another triangle,
    - a case where a triangle violates the square boundary.
