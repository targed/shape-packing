# cirinttt: Circles in Truncated Triangle (TTT)

Family: N_CIRCLE_in_TTT (N circles inside a TTT-shaped container).

1. Geometry:
- WHEN inner is "CIRCLE" and container is "TTT" THEN:
  - circles SHALL be represented consistently.
  - container SHALL use a clearly defined TTT shape.
  - Scaling SHALL be derived from S via a documented rule.

2. Validity:
- WHEN a solution is generated THEN:
  - all circles SHALL be inside the TTT container.
  - no two circles SHALL overlap beyond tolerance (≤ 1e-15).

3. Friedman Comparison:
- WHEN comparing to Friedman THEN:
  - use an explicit, documented conversion from S to his unit.
  - NEW_BEST is valid only if geometry and metric alignment are confirmed.

4. Test Expectations:
- Tests SHALL include:
  - construction of both shapes.
  - a valid packing.
  - an overlapping pair.
  - a boundary-violation case.
