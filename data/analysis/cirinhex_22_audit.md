# Audit: 22_CIRCLE_in_6

**Scope:** Holistic validity check of the proposed `22_CIRCLE_in_6` record in `records/cirinhex/22_CIRCLE_in_6/solution.json` against the official Friedman benchmark and the repository’s own verification model.

## Sources checked
- Official benchmark page: https://erich-friedman.github.io/packing/cirinhex/index.html
- Benchmark data: `packingVerification/cirinhex.json`
- Candidate record: `records/cirinhex/22_CIRCLE_in_6/solution.json`
- Exported coordinate dump: `records/cirinhex/22_CIRCLE_in_6/coordinates.txt`
- Exported verification log: `records/cirinhex/22_CIRCLE_in_6/verification.txt`
- Solver geometry model: `src/shape_packing/packing_config.py`, `src/shape_packing/geometry.py`, `src/shape_packing/solution_tools.py`

## What the official record is
The Friedman page for circles in hexagons lists the 22-circle benchmark as `s = 5.952+`, found by David W. Cantrell in July 2012. The repository’s `packingVerification/cirinhex.json` mirrors that entry with `best_value: 5.952` and the same source note.

## What the candidate claims
The candidate solution reports:
- `S = 5.95186267022939`
- `final_metric = 5.9518626702293895`
- `N = 22`

That is lower than 5.952 by about `0.000137329771`, which is a five-decimal-visible improvement.

## Main issue
The repository does **not** model `CIRCLE` as an exact circle in the packing solver. In `src/shape_packing/packing_config.py`, circles are explicitly handled as a `64`-sided polygon approximation (`CIRCLE_APPROX_VERTICES = 64`). In `src/shape_packing/geometry.py`, `get_shape_geometry("CIRCLE")` returns the 64-gon vertices and SAT normals for that approximation. The verification path in `src/shape_packing/solution_tools.py` therefore certifies the packing of the approximation, not an exact Euclidean circle.

For this problem that matters because the approximation error is not tiny relative to the claimed win. A 64-gon inscribed in a unit circle has inward radial error of `1 - cos(pi/64) ≈ 0.001204543795`, or about `0.1206%`. The candidate’s margin over the 5.952 benchmark is only `0.000137329771`, about `0.0023%`. The approximation gap is therefore much larger than the reported improvement, so the current result is not strong enough to treat as a genuine exact-circle record.

## Secondary note
The exported `verification.txt` correctly says the configuration is geometrically valid under the repo’s current model, but that does not resolve the exact-circle mismatch. It proves the 64-gon packing is valid; it does **not** prove the same configuration is valid for true circles.

## Conclusion
- **Internally valid under the repository’s 64-gon circle model:** yes.
- **Genuine exact-circle world record for Friedman’s `22_CIRCLE_in_6`:** not established.
- **Recommendation:** do not submit this as a confirmed record without a separate exact-circle check or a higher-confidence approximation analysis that shows the record survives the circle-model gap at the five-decimal level.
