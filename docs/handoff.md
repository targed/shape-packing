Project:
- /Users/kaiserluke/Documents/Git/shape-packing
- Branch: development (ahead 13, behind 0)

High-level goal:
- Replace the two-state attempt logic (5k vs 50k) in run_parallel_loop.py with adaptive, per-problem attempt scaling based on difficulty, history, and Friedman best scores.
- Ensure no regressions; keep code KISS and non-breaking.

What’s already done (and working):

1. Rust PyO3 / dyld issue (related, completed):
- Problem: macOS dyld error (_PyExc_AttributeError) when running packer_rs as standalone binary.
- Fix:
    - Made PyO3 optional via feature = "python".
    - Binary no longer hard-links Python C-API; parallel loop stable.
- Verified: run_parallel_loop.py no longer dyld-crashes.

2. Attempt-scaling analysis and plan:
- File:
    - docs/attempt-scaling-analysis-and-plan.md
- Contents:
    - Critique of old 5k/50k logic.
    - New approach: per-problem difficulty score in [0,1] that drives attempts in [500, 200k] plus swarm counts.
    - Uses:
    - N
    - history stats (success/failure counts)
    - gap vs Friedman best_score from packingVerification JSONs
    - Task breakdown (Tasks 1–4) for incremental implementation.

3. Core scaling functions added to src/shape_packing/packing_config.py:
- get_problem_history_stats(problem, history_path, cache):
    - Reads results.tsv; returns total_runs, success_count, failure_count, best_score.
- get_friedman_best_for_problem(problem):
    - Loads from packingVerification/*.json (the correct reference; not PACKING_REFERENCE).
    - Handles both list-of-objects and dict-by-token formats.
    - Normalizes keys to lowercase to match runtime tokens.
- compute_problem_difficulty_score(problem, stats, friedman_best):
    - Base 0.3.
    - +0.15 if N>=10, +0.10 if N>=15.
    - + based on failure_ratio and gap to Friedman best.
    - Clamped [0,1].
- compute_adaptive_attempts(difficulty, status, min_attempts, max_attempts):
    - Four bands mapping difficulty to attempts:
    - [0,0.2] → [min_attempts, LOOP_DEFAULT_ATTEMPTS]
    - (0.2,0.5] → [LOOP_DEFAULT_ATTEMPTS, LOOP_HIGH_N_ATTEMPTS]
    - (0.5,0.8] → [LOOP_HIGH_N_ATTEMPTS, 0.7*max]
    - (0.8,1] → [0.7*max, max]
    - stuck/hard: difficulty * 1.2 (clamped) → more attempts.
    - Monotonic, bounded, tested.

4. Integration into run_parallel_loop.py:
- analyze_difficulty(problem_state):
    - Now:
    - Calls get_problem_history_stats
    - Calls get_friedman_best_for_problem
    - Computes difficulty
    - Computes attempts via compute_adaptive_attempts
    - Logs: “[diff] {problem}: diff=... hist=... fr_best=... -> attempts=... swarm=...”
    - Swarm count:
    - stuck/hard → LOOP_STUCK_SWARM_COUNT
    - difficulty>=0.8 → LOOP_HARD_SWARM_COUNT
    - else 1

5. Tests:
- tests/test_attempt_scaling.py:
    - 28 tests:
    - history stats behavior
    - Friedman cache and lookup
    - difficulty scoring
    - adaptive_attempts monotonicity, ranges, stuck/hard behavior

## Completed Features & Fixes:

1. **Restored Missing Constants in `packing_config.py`:**
   - Restored `VERIFY_SAT_TOLERANCE`, `VERIFY_METRIC_TOLERANCE`, `GEOMETRY_SAT_TOLERANCE`, `OPTIMIZER_ATTEMPTS`, `OPTIMIZER_TOLERANCE`, `OPTIMIZER_FINAL_STEP`, `OPTIMIZER_N_JOBS`, `RUST_BINARY`, `RUST_TOLERANCE`, `RUST_DEFAULT_TIME_LIMIT`, `CIRCLE_SIDES`, `SHAPE_TO_SIDES["CIRCLE"]`, `SPECIAL_SHAPES`, `ALL_FAMILIES`, etc.
   - All modules and tests import cleanly without `ImportError`.

2. **Adaptive Attempt Scaling (`packing_config.py` & `run_parallel_loop.py`):**
   - Implemented `get_problem_history_stats`, `get_friedman_best_for_problem`, `compute_problem_difficulty_score`, `compute_adaptive_attempts`.
   - Added robust `_normalize_key()` token normalization across shape synonyms (`pentagon` ↔ `5`, `square` ↔ `4`, `domino` ↔ `DOMINO`).
   - Integrated into `run_parallel_loop.py::analyze_difficulty`.

3. **World Records Exporter & Erich Friedman Submission Bundler:**
   - Implemented `src/shape_packing/records_exporter.py` and `scripts/export_records.py`.
   - Audits all results against `packingVerification/*.json`, verifies 0 SAT collisions and 100% boundary containment, generates tight cropped PNGs, `coordinates.txt`, `verification.txt`, `manifest.json`, `summary.md`, and 19 `submissions/<family>_submission.md` email drafts.
   - Exported and verified 49 record solutions in `records/`.

4. **Test Suite Status:**
   - Full suite passes: `284 passed in 18s` (`python -m pytest tests/`).