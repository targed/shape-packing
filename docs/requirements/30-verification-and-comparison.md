# Verification and Comparison Requirements

Scope:
verify_solution.py, compare_results.py, PACKING_REFERENCE, packingVerification/*.json.

1. Verification (verify_solution.py)

- WHEN a solution JSON is passed to verify_solution.py THEN the system SHALL:
  - reconstruct all inner shapes and the container,
  - check:
    - all inner shapes are inside the container,
    - no overlaps between any pair of inner shapes (SAT, tolerance ≤ 1e-15),
    - reported metrics (S, final_metric) are internally consistent with the defined formula.

- IF any violation is detected THEN:
  - the solution SHALL be marked invalid with a clear reason:
    - “out of bounds”,
    - “overlap”,
    - “metric mismatch”.

- WHEN verifying circle containers THEN:
  - the system SHALL not assume final_metric = Friedman’s r unless explicitly derived and documented per shape.

2. Metric Consistency

- WHEN a solution claims a metric THEN:
  - it SHALL match the deterministic calculation from S, inner and container definitions,
  - no ad-hoc adjustments or “eyeballed” scaling are allowed.

3. Comparison to Known Results (compare_results.py)

- WHEN comparing to Friedman’s known best_value THEN:
  - the metric used SHALL be aligned with Friedman’s metric for that family (e.g., same unit, same geometric meaning).

- WHEN a solution is geometrically valid AND its metric is less than best_value by more than a tiny epsilon THEN:
  - it MAY be labeled NEW_BEST,
  - but only after:
    - the metric alignment is correct,
    - geometry is verified.

- IF a problem’s metric alignment is uncertain or uses different units (e.g., circles vs polygons, special shapes) THEN:
  - compare_results.py SHALL NOT treat it as directly comparable
    without an explicit conversion rule.

4. PACKING_REFERENCE and packingVerification

- WHEN PACKING_REFERENCE entries are used THEN:
  - they SHALL be based on real, cited Friedman pages or authoritative sources,
  - no values SHALL be invented.

- WHEN a family is considered “incomparable” (e.g., due to unit mismatch) THEN:
  - it SHALL be explicitly marked as such,
  - no NEW_BEST SHALL be claimed until alignment is proven.
