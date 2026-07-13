# autoresearch-packing (Mode 2)

You are running an autonomous research loop for 2D shape packing.
No neural training. No MLX. Pure optimization.

## Goal

- Iteratively improve packings by:
  - Selecting problems
  - Editing strategies in polygon_packer.py or config in train.py
  - Running experiments (uv run train.py)
  - Logging results to results.tsv

NEVER STOP once the loop has begun.
Do NOT ask "should I keep going?" or "is this a good stopping point?".
Run until interrupted.

## Key files (only these matter)

- program.md: This file. Your instruction manual.
- train.py: Experiment runner (Mode 2).
  - CURRENT_PROBLEM at the top: the target problem.
  - Enforces time budget, runs solver, prints summary.
- polygon-packer/polygon_packer.py:
  - Main algorithmic file you edit to change strategies.
- src/shape_packing/:
  - Core modules used by the system:
    - problems.py: problem parsing, token mapping
    - geometry.py: geometry/overlap logic
    - optimization.py: optimization/orchestration
    - agent_loop.py: history, stuck detection, problem selection
- results.tsv:
  - Columns: commit, score, memory_gb, status, problem, description
- PACKING_REFERENCE.tsv:
  - Columns: problem_family, n, best_value, source, status, our_problem
  - Use this to:
    - Avoid trivial / proved_optimal problems
    - Prefer best_known or human-found problems

## Setup (once)

Before starting the loop:

1) Install:

   - uv sync

2) Test run:

   - Set CURRENT_PROBLEM in train.py to something simple, e.g.:
     - 10_3_in_CIRCLE
   - Run:
     - uv run train.py
   - Confirm it prints:
     - score: ...
     - training_seconds: ...
     - total_seconds: ...
     - problem: ...

3) Initialize results.tsv:

   - Header:
     - commit	score	memory_gb	status	problem	description
   - Log your first baseline run.

## Problem naming

- Format: {N}_{inner}_in_{container}
- Examples:
  - 20_3_in_CIRCLE
  - 30_4_in_6
  - 15_TAN_in_CIRCLE

Shape tokens:

- CIRCLE (approximate with high-sided polygon or dedicated logic)
- 3 (triangles), 4 (squares), 5 (pentagons), 6 (hexagons), 8 (octagons)
- Special: TAN, DOMINO, L

## Problem selection (reference-aware)

Before choosing a problem:

- Consult PACKING_REFERENCE.tsv and the last ~20 rows of results.tsv.

Hard rules:

- Do not pick problems where:
  - status == "trivial", or
  - status == "proved_optimal"
  - unless you are explicitly validating the packer on known values.

Soft rules:

- Prefer:
  - best_known problems
  - Problems where source is human-found (e.g., "Found by ...")
  - Problems with small-to-moderate N (e.g., 3–15) unless specifically exploring larger N.
- Avoid:
  - Problems where our best score is within 1e-6 of the reference best_value,
    unless you are trying a radically different algorithm.

Diversity:

- Rotate across different problem families.
- If stuck on one, switch family or N.

## Experiment loop

LOOP FOREVER (until manually stopped):

1. Inspect context:

   - Current branch/commit.
   - Last ~20 rows of results.tsv.
   - PACKING_REFERENCE.tsv for candidate problems.
   - Identify:
     - current best score per problem
     - where you are stuck
     - where you have not tried much

2. Choose or keep a problem:

   - Set CURRENT_PROBLEM in train.py.

   - If last 5-7 experiments on the same problem did not improve:
     - Switch to a different problem or different N.

   - Every ~20-30 experiments:
     - Try something more radical (new strategy, new family).

3. Form a hypothesis:

   - Examples:
     - Change initialization layout
     - Tune optimizer (L-BFGS-B vs basinhopping)
     - Adjust penalty / tolerance
     - Use shape-specific heuristics
   - Write a short description.

4. Implement:

   - Edit polygon_packer.py and/or train.py config.
   - Keep changes focused and testable.

5. Commit:

   - git add train.py polygon-packer/polygon_packer.py
   - git commit -m "experiment: <short description>"

6. Run:

   - uv run train.py > run.log 2>&1
   - Do NOT let raw output flood your context.

7. Read results:

   - Use:
     - grep "^score:" run.log
     - grep "^problem:" run.log
   - If empty or run exceeded 15 minutes:
     - Treat as crash/failure.

8. Log to results.tsv:

   - Columns:
     - commit (short, 7 chars)
     - score (float; 0 if crash)
     - memory_gb (approx peak; 0.0 if crash)
     - status: keep / discard / crash
     - problem: CURRENT_PROBLEM
     - description: short text
   - If score improved (lower) for that problem:
     - status = keep
     - git add results.tsv
     - git commit --amend --no-edit
   - Else:
     - status = discard
     - Record commit hash.
     - git reset --hard <previous kept commit>

9. Decide next:

   - If improving: continue same problem, refine.
   - If stuck: switch problem or N.
   - If repeating: try a more radical idea or family.

## Diversity rules

- After 5-7 non-improving experiments on the same (problem, N):
  - Switch to a different problem or N.
- Every ~20-30 experiments:
  - Try:
    - A different shape family
    - A more aggressive strategy
- Never:
  - Run the exact same config twice
  - Blindly tweak one hyperparameter without rationale

## Simplicity criterion

- All else equal, simpler is better.
- Tiny improvement + lots of messy code:
  - Probably discard.
- Same or better with simpler code:
  - Definitely keep.
- Radical change only if:
  - It yields a clear, meaningful improvement.
