# System Overview: Shape Packing Auto-Researcher

Purpose:
High-level, stable requirements that define what this system is, what it is supposed to do, and what it must not do.

1. System Purpose

- The system SHALL discover dense 2D shape packings (polygons, circles, special shapes) inside container shapes.
- The system SHALL do this using deterministic, mathematically verifiable optimization — no machine learning / neural training.

Core principles:

- WHEN evaluating packings THEN decisions SHALL be based on geometry and numeric verification, not on visual appearance or intuition.
- WHEN a packing is claimed as improved THEN it SHALL be provably valid by SAT-style checks at or better than 1e-15 tolerance.
- WHEN comparing to known results (Friedman) THEN comparisons SHALL use metrics that are explicitly aligned with the reference source.

2. Modes of Operation

- Mode 1 (pure-code autoresearch):
  - WHEN run_autoresearch_loop.py or run_parallel_loop.py is used THEN the system SHALL:
    - select problems,
    - run the solver,
    - log results,
    - maintain PACKING_REFERENCE,
    - make no LLM calls.
- Mode 2 (LLM-assisted interactive research):
  - WHEN using program.md + train.py THEN the LLM MAY propose:
    - algorithmic edits,
    - parameter changes,
    - new heuristics,
  - BUT geometric validation and metric comparison SHALL remain unchanged.

3. Precision and Correctness

- WHEN a packing is marked as valid THEN:
  - no pair of inner shapes SHALL overlap beyond tolerance,
  - all inner shapes SHALL be fully contained in the container.
- IF floating-point anomalies could cause false records THEN:
  - the system SHALL:
    - enforce tight tolerances,
    - avoid relaxing constraints to “accept” suspicious packings.

4. Friedman Reference Handling

- WHEN a known best_value from Friedman is used THEN:
  - it SHALL be stored in PACKING_REFERENCE (or equivalent) with exact decimal digits.
- WHEN comparing our packings to Friedman THEN:
  - the system SHALL NOT claim NEW_BEST unless:
    - the metric used is explicitly comparable (same units, same unit shape),
    - geometry is verified.
- IF a family uses incompatible metrics (e.g., circles) THEN:
  - the system SHALL treat those packings as incomparable until an explicit conversion is implemented and documented.

5. Non-Goals

- This system SHALL NOT:
  - rely on neural training,
  - silently change unit sizes to match Friedman,
  - relax tolerances to make a result “look” better.
