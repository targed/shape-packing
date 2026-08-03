# Hexagons in Squares Requirements

Family: N_6_in_4 (N hexagons inside a square).

1. Geometry
- WHEN the problem uses token "6" THEN:
  - hexagons SHALL be regular, defined via circumradius-based construction.
- WHEN the container is "4" THEN:
  - it SHALL be a square defined by 4 vertices with circumradius S.

2. Validity
- WHEN a solution is generated THEN:
  - all hexagon vertices SHALL lie inside or on the square boundary,
  - no two hexagons SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison
- Friedman’s metric for this family uses a consistent normalization.
- WHEN comparing to Friedman THEN:
  - the metric SHALL be derived from S using an explicit, documented formula
    (e.g., based on S and sin(pi/n) where appropriate),
  - NEW_BEST is only valid if:
    - geometry is verified,
    - metric alignment with Friedman is confirmed.

4. Test Expectations
- WHEN testing this family THEN:
  - there SHALL be tests for:
    - construction of hexagons and square,
    - a valid packing inside the square,
    - a case with overlap,
    - a case with boundary violation.
