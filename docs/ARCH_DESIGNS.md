> Archived reference: High-level architecture / module design notes.
> Not required to run or use the current system; kept for context.

# Architecture & Module Design

This doc tracks the deepening of this repo into focused, testable modules with stable interfaces.

High-level goal:
- Each concept (geometry, optimization, problem definition, agent loop, tools) has exactly one "god module."
- Other files are thin: entrypoints, runners, renderers, etc., importing from those modules.
- New problem types or strategies can plug in via interfaces, not by editing many files.

Current deep modules:
- geometry.py
- optimization.py
- problems.py
- agent_loop.py
- solution_tools.py

Details per module below.

---

## 1. Geometry Module (geometry.py)

Purpose:
- Single, authoritative place for all geometric primitives used in packing:
  - polygon construction
  - transformations
  - collision / overlap / poking metrics
  - SAT-based overlap checks
  - helper functions used across Python and reference-implementations

Owns:
- regular_polygon(n, radius, center)
- transform_polygon(polygon, dx, dy, scale, theta)
- rotate_vectors, translate helpers
- SAT-based overlap functions (edges, projections)
- poking_penalty / bh_function (geometry-only part, i.e., computing penalties, not orchestration)
- metrics like overlap_area, max_poke, etc. (if present)

Used by:
- polygon_packer.py (core geometry calls)
- solution_tools.py (verification + rendering via geometry)
- tests / scripts

Rules:
- Must not:
  - contain optimizer orchestration (no basinhopping, no loop control)
  - depend on train.py or agent behavior
- Should:
  - be pure or nearly pure math functions
  - be easy to unit-test in isolation
  - be importable by both Python and any future bindings (e.g., from Rust via reference)

How to use:
- If you are adding or changing:
  - any shape construction
  - any transform
  - any overlap/poke math
  → implement or adjust it in geometry.py and call it from other files.

---

## 2. Optimization Module (optimization.py)

Purpose:
- Deep module for optimization strategy and objective logic.
- Encapsulates how we formulate and run the packing optimization, so that:
  - the objective and schedule can change centrally
  - the same optimization core is used from different runners/backends.

Owns (conceptually):
- PackingProblem:
  - Encapsulates:
    - N: number of inner polygons
    - inner_sides: sides of inner polygon or None for special shapes
    - container_sides: sides of container or None
- OptConfig:
  - Configuration for runs:
    - time_limit
    - attempts
    - tolerance
    - randomness / diversity knobs
- build_objective(p, geometry_fn):
  - Constructs a callable objective(x) that:
    - interprets x as layout variables
    - applies geometry to compute penalties
    - returns a scalar to minimize
- run_single_attempt(objective, x0, config):
  - Runs one local/global optimization attempt (e.g., L-BFGS-B or basinhopping).
- run_all_attempts(objective, x0_factory, config):
  - Repeatedly calls run_single_attempt according to schedule.
  - Tracks best solution, enforces time/attempt limits.
  - Applies convergence / early-stopping / diversity policy.

Used by:
- polygon_packer.py:
  - Thin wrapper that:
    - parses CLI args
    - constructs PackingProblem + OptConfig
    - calls optimization.py functions
    - writes outputs (JSON, PNG via render_solution.py)
- packer_rs:
  - Should align its internal logic to the same conceptual interface:
    - same objective structure
    - same scheduling/loop semantics
  - Implementation in Rust, design mirrored from optimization.py.

Rules:
- Must not:
  - hardcode problem names or parsing logic (use problems.py for that)
  - contain geometry primitives (use geometry.py)
- Should:
  - expose a small, stable interface
  - make it easy to swap optimizers or strategies in one place
  - be testable with synthetic objectives

How to use:
- If you want to:
  - change the penalty formula
  - change attempts / time policy
  - change convergence/diversity heuristics
  → adjust optimization.py; leave runners thin.

---

## 3. Problem Module (problems.py)

Purpose:
- Single seam for "what is a packing problem?"
- Centralizes:
  - problem name parsing
  - shape token mapping
  - validation
  - generation of arguments for packers

Owns:
- Data model:
  - Problem(name, N, inner_token, container_token)
- Functions:
  - parse_problem(name) -> Problem
  - shape_token_to_sides(token) -> int | None
  - is_special_shape(token) -> bool
  - validate_problem(p) -> None
  - problem_to_packer_args(p) -> (N, inner_sides, container_sides)
  - list_problem_families() -> list[str]

Uses:
- packing_config.py:
  - SHAPE_TO_SIDES
  - SPECIAL_SHAPES
  - ALL_FAMILIES
  (packing_config is a data/canonical-catalog file; problems.py is the interface.)

Used by:
- train.py:
  - Imports from problems to:
    - parse CURRENT_PROBLEM
    - derive N, inner, container, sides
- agent_loop.py:
  - Via shared conventions for problem names.
- Future:
  - Agent loops / experiment selectors / reference-aware problem pickers.

Rules:
- Must not:
  - run optimization or call geometry directly.
- Should:
  - be pure: input is tokens/strings, output is structured problem info.
  - be easy to test with edge cases (invalid names, unknown tokens, etc.).

How to use:
- To interpret a problem:
  - p = parse_problem("10_4_in_CIRCLE")
  - N, i_sides, c_sides = problem_to_packer_args(p)
- To add or restrict problem types:
  - adjust logic in validate_problem / shape_token_to_sides, not across many files.

---

## 4. Agent Loop Module (agent_loop.py)

Purpose:
- Deep module that owns the experiment loop behavior currently described in program.md.
- Encapsulates:
  - how we choose problems
  - how we detect being "stuck"
  - how we decide to switch problems or try something radical
  - how we log and interpret results

Owns:
- Data model:
  - ExperimentResult(problem, score, status, description, seconds, commit, memory_gb)
- Core functions:
  - load_history(path) -> list[ExperimentResult]
  - append_result(path, result)
  - current_best_scores(history) -> dict[problem -> best_score]
  - choose_problem(history, ...) -> str
  - is_stuck(history, problem) -> bool
  - should_switch_radically(total_experiments, ...) -> bool
  - log_result(...) -> "keep" | "discard" | "crash"
  - make_loop_candidate(history, current, ...) -> (problem, be_radical)

Uses:
- problems.py:
  - Via shared conventions for problem names.
- PACKING_REFERENCE.tsv:
  - To avoid trivial / proved_optimal problems; prefer best_known or human-found.
- results.tsv:
  - As the canonical log of experiments.

Used by:
- program.md (conceptually):
  - program.md now references agent_loop.py as the authoritative implementation.
- Future automation:
  - A scripted agent loop can:
    - call choose_problem
    - run an experiment (train.py)
    - call log_result
    - check is_stuck / should_switch_radically
    - decide next step.

Rules:
- Must not:
  - run geometry or optimization directly.
  - hardwire low-level hyperparameters; those live in optimization.py and polygon_packer.py.
- Should:
  - keep all diversity / switching / logging policy in one place.
  - be testable with synthetic or real histories.

How to use:
- Example loop (pseudo-code):

  - history = load_history()
  - current = choose_problem(history)
  - while True:
      - (score, seconds, desc) = run_experiment(current)
      - status = log_result(history, current, score, seconds, desc)
      - if is_stuck(history, current) or should_switch_radically(len(history)):
          - current, radical = make_loop_candidate(history, current)

---

## 5. Tools Module (solution_tools.py)

Purpose:
- Deep module for "tools" around solutions:
  - loading a solution JSON
  - reconstructing polygons
  - verifying a solution (geometry + record check)
  - rendering a solution to PNG
- Makes verify_solution.py and render_solution.py into thin entrypoints.

Owns:
- Data model:
  - Solution(path, N, inner_sides, container_sides, S, final_metric, values)
  - VerifyResult(valid, metric, errors, new_record, message)
- Core functions:
  - load_solution(path) -> Solution
  - build_polygons(sol) -> list of polygons
  - to_plot_data(sol) -> dict with plotting geometry
  - load_best_value(reference_path, problem_str) -> float | None
  - verify_solution(sol_path, problem_str, ...) -> VerifyResult
  - render_solution(sol_path, out_png, ...) -> None

Uses:
- geometry.py:
  - For polygon construction, transforms, SAT, normals.

Used by:
- verify_solution.py:
  - Thin CLI wrapper:
    - parse args
    - call verify_solution(...)
    - print [PASS]/[FAIL] and record status
- render_solution.py:
  - Thin CLI wrapper:
    - parse args
    - call render_solution(...)
- Future:
  - Agents or tests can call verify_solution/render_solution programmatically.

Rules:
- Must not:
  - run optimization or experiment loops.
- Should:
  - be the single place for how we interpret, verify, and render solution JSONs.
  - be easy to unit-test with small synthetic solutions.

How to use:
- From scripts:
  - verify_solution.py and render_solution.py import from solution_tools.
- From agents/tests:
  - res = verify_solution("best.json", problem_str="12_5_in_8")
  - render_solution("best.json", "out.png")

---

## 6. How things fit together

High-level flow (conceptual):

- Agent / human:
  - uses agent_loop.py to choose a problem, e.g. "12_5_in_8".
- problems.py:
  - parse_problem("12_5_in_8") → Problem
  - problem_to_packer_args → N, inner_sides, container_sides
- train.py:
  - thin runner that:
    - uses Problem from problems.py
    - invokes packer (Python or Rust)
- polygon_packer.py:
  - uses optimization.py (objective, schedule) and geometry.py (shape, collisions).
- packer_rs:
  - mirrors optimization.py conceptually, with its own Rust geometry/util implementation.
- agent_loop.py:
  - orchestrates the loop over problems and experiments:
    - reads results.tsv and PACKING_REFERENCE.tsv
    - decides when to switch or radicalize
    - logs each run via log_result
- solution_tools.py:
  - verifies and renders solutions:
    - verify_solution.py calls solution_tools.verify_solution(...)
    - render_solution.py calls solution_tools.render_solution(...)

Design principle:
- Changing geometry: edit geometry.py.
- Changing optimization/strategy: edit optimization.py.
- Changing problem definition/parsing: edit problems.py (and packing_config for data).
- Changing experiment loop policies: edit agent_loop.py; leave program.md as high-level narrative.
- Changing solution verification/rendering behavior: edit solution_tools.py; keep scripts as thin wrappers.