# Circles in Circles Requirements

Family: N_CIRCLE_in_CIRCLE (N circles inside a larger circle).

1. Geometry
- WHEN the inner shape is "CIRCLE" THEN:
  - it SHALL be modeled with a consistent numeric representation (e.g., high-sided polygon or dedicated circle logic),
  - its unit size SHALL be stable across all N.
- WHEN the container is "CIRCLE" THEN:
  - it SHALL be modeled consistently with the same logic,
  - its size SHALL be represented by radius r (mapped from S).

2. Validity
- WHEN a solution is generated THEN:
  - all inner circle boundaries SHALL lie inside the outer circle,
  - no two inner circles SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison
- Friedman’s metric for circle-in-circle problems uses his specific radius r.
- WHEN comparing to Friedman THEN:
  - the metric SHALL be derived from S via an explicit, per-shape conversion,
  - old sin-scaled final_metric values SHALL NOT be used directly as r.
- IF the mapping is uncertain THEN:
  - the problem SHALL be marked incomparable
    and no NEW_BEST SHALL be claimed.

4. Test Expectations
- WHEN testing this family THEN:
  - there SHALL be tests for:
    - construction of circle representations,
    - a valid packing inside a circle,
    - an overlapping-circle case,
    - a boundary-violation case where an inner circle extends outside.
