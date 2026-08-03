# Triangles in Pentagons Requirements

Family: N_3_in_5 (N triangles inside a regular pentagon).

1. Geometry
- WHEN the problem uses token "3" for inner shape THEN:
  - triangles SHALL be regular, defined via circumradius-based construction.
- WHEN the container is "5" THEN:
  - it SHALL be a regular pentagon defined by 5 vertices with circumradius S.

2. Validity
- WHEN a solution is generated THEN:
  - all triangle vertices SHALL lie inside or on the pentagon boundary,
  - no two triangles SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison
- Friedman’s metric for this family uses his specific container-side/area normalization.
- WHEN comparing to Friedman THEN:
  - the metric SHALL be derived from S using a consistent, documented formula,
  - it SHALL NOT be used as a universal metric across different families.

4. Test Expectations
- WHEN testing this family THEN:
  - there SHALL be tests for:
    - construction of triangles and pentagon,
    - a valid packing inside a pentagon,
    - a case with overlap,
    - a case with boundary violation.
