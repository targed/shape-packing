# Template: Problem Family Requirements

Use this as a template when adding a new family (e.g., N_3_in_6, N_TAN_in_CIRCLE).

1. Geometry
- WHEN inner shape X is used THEN:
  - it SHALL be constructed with a stable, documented unit definition (vertices, normals, or radius).
- WHEN container Y is used THEN:
  - it SHALL be constructed consistently with the same circumradius S convention.

2. Validity
- WHEN a solution is generated THEN:
  - all inner shapes SHALL lie inside or on the container boundary,
  - no two inner shapes SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison
- WHEN Friedman’s metric is used THEN:
  - it SHALL be derived from S via an explicit, documented conversion that matches Friedman’s unit.
- WHEN claiming NEW_BEST THEN:
  - geometry must be verified,
  - metric alignment must be confirmed,
  - if uncertain, treat as incomparable instead of asserting NEW_BEST.

4. Test Expectations
- WHEN testing this family THEN:
  - there SHALL be tests for:
    - construction of the inner and container shapes,
    - a valid packing,
    - an overlapping case,
    - a boundary-violation case.