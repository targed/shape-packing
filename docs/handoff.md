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

What’s broken / current issues:

1. I rewrote packing_config.py and lost many existing symbols.
- I removed large sections while reconstructing the adaptive-scaling logic.
- Now several modules fail to import due to missing symbols.

Missing symbols (from imports across src/ and tests/):
- VERIFY_SAT_TOLERANCE (solution_tools.py)
- OPTIMIZER_ATTEMPTS
- OPTIMIZER_TOLERANCE
- OPTIMIZER_FINAL_STEP
- OPTIMIZER_N_JOBS (optimization.py)
- RUST_BINARY (test_packing_config.py)
- Possibly others (run a grep to be safe).

2. Test failures:
- tests/test_solution_tools.py: ImportError VERIFY_SAT_TOLERANCE
- tests/test_optimization_coverage.py: ImportError OPTIMIZER_ATTEMPTS
- tests/test_packing_config.py: ImportError RUST_BINARY
- Other tests likely affected.

3. run_parallel_loop.py:
- Imports fixed partially (SHAPE_TO_SIDES, SPECIAL_SHAPES, ALL_FAMILIES, etc. added).
- Loop can start and spawn workers with adaptive attempts.
- But workers crash because worker_task -> handle_run -> solution_tools/optimization import errors.

What still has to be done (in order):

1) Restore missing symbols in packing_config.py
- Compare against git show HEAD:src/shape_packing/packing_config.py
- Restore:
    - VERIFY_SAT_TOLERANCE
    - OPTIMIZER_ATTEMPTS, OPTIMIZER_TOLERANCE, OPTIMIZER_FINAL_STEP, OPTIMIZER_N_JOBS
    - RUST_BINARY (alias for RUST_RELEASE_BIN)
    - Any others required by imports (run:
        grep -r "from .packing_config import\|from src.shape_packing.packing_config import" src/ tests/ scripts/ | sort | uniq
        and confirm all imported names exist in packing_config.py).
- Do NOT break the new adaptive-scaling functions.

2) Ensure all imports are stable
- Run:
    - python3 -c "from src.shape_packing import packing_config, solution_tools, optimization, problems"
    - Confirm no ImportError.

3) Run test suite
- Run:
    - python3 -m pytest tests/ -v --tb=short
- Fix any regressions related to packing_config.py changes.
- Make sure:
    - test_attempt_scaling.py: passes
    - test_solution_tools.py: passes
    - test_optimization_coverage.py: passes
    - test_packing_config.py: passes
    - Others: no new failures introduced.

4) Smoke-test run_parallel_loop.py
- Run:
    - timeout 30 python3 -u run_parallel_loop.py 2>&1
- Confirm:
    - No import errors
    - Workers start and complete (at least some)
    - Adaptive attempts logged reasonably (varied by difficulty)
    - No crashes (ignore SIGTERM/timeout shutdown).

5) Clean up
- Ensure:
    - No dead code / huge duplicated sections in packing_config.py.
    - Style consistent, concise.
- Commit:
    - One commit for:
    - adaptive-scaling functions
    - restored symbols
    - integration in run_parallel_loop.py
    - Message something like:
    "feat: adaptive attempt scaling based on problem difficulty and history"

Important constraints (from user):
- Never use PACKING_REFERENCE.tsv/json (bad HTML parser; wrong).
- Use only:
    - packingVerification/*.json as Friedman reference.
- Changes should:
    - Be additive and non-breaking.
    - Keep it KISS; no global redesign beyond what’s necessary.
    - Match existing code style.

If you need to, use:
- git show HEAD:src/shape_packing/packing_config.py
    to recover original structure and missing values.
- grep over src/ tests/ scripts/ to confirm all imported names exist.
- Run the tests and the loop as validation.

End of handoff.