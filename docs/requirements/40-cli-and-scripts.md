# CLI and Scripts Requirements

Scope:
cli.py, scripts/analyze_mill_log.py, scripts/render_solution.py, scripts/verify_solution.py, scripts/compare_results.py.

1. CLI (cli.py)

- WHEN the CLI is invoked with a solve/run command THEN it SHALL:
  - parse the problem name in N_X_in_Y form,
  - validate that tokens (X, Y) are supported,
  - pass the request to the solver without silently altering geometry.

- WHEN the CLI outputs results THEN it SHALL:
  - include:
    - problem,
    - N,
    - S,
    - final_metric,
    - status (valid/invalid/NEW_BEST/crash),
  - and NOT present unverifiable or fabricated metrics.

- IF the user specifies a configuration or mode flag (e.g., --no-commit, --json-out) THEN:
  - the behavior SHALL be deterministic and match the documented mode.

2. Verify Solution Script (scripts/verify_solution.py)

- WHEN a solution file is passed THEN:
  - the script SHALL use the same geometric definitions and tolerances (≤ 1e-15) as the core solver,
  - it SHALL report:
    - whether the packing is valid,
    - any overlaps or out-of-bounds issues,
    - whether it qualifies as a new record (subject to correct metric alignment).

3. Compare Results Script (scripts/compare_results.py)

- WHEN comparing to known values THEN:
  - it SHALL:
    - load PACKING_REFERENCE (and packingVerification),
    - ensure the metric used is aligned with Friedman for that family,
    - avoid declaring NEW_BEST when metrics are incomparable.

- WHEN a solution is NEW_BEST THEN:
  - it SHALL be:
    - geometrically valid,
    - based on a correct, explicitly comparable metric.

4. Mill Log Analysis (scripts/analyze_mill_log.py)

- WHEN analyzing cluster logs THEN:
  - it SHALL extract:
    - per-problem run counts,
    - per-problem improvement stats,
    - fairness/skew indicators (e.g., one problem dominating runs),
  - and NOT alter the logs or solution files.

5. Rendering (scripts/render_solution.py)

- WHEN a solution is rendered THEN:
  - it SHALL use the same geometric definitions as the solver,
  - the visualization SHALL be consistent with the numeric solution.
