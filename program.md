# autoresearch-packing

An autonomous research loop for 2D shape packing.
You (the agent) follow this document to iteratively improve packings
using polygon_packer.py and a 5-minute experiment runner.

No neural training. No MLX. Pure optimization.

## Quick summary

- Goal: minimize container size for a given set of inner shapes.
- Each experiment:
  - You edit polygon_packer.py and/or train.py config.
  - Run: uv run train.py
  - Budget: 5 minutes (wall clock).
  - Metric: score (container side length). Lower is better.
- Loop forever until stopped.
- Switch problems when stuck. Explore broadly. Never repeat identical configs.

## Core files

- program.md:
  - This file. Your instruction manual. Do not remove.
- train.py:
  - Experiment runner.
  - At the top: configuration section you can edit (CURRENT_PROBLEM, etc.).
  - Rest is a fixed harness: launches polygon_packer.py, enforces time budget,
    parses output, prints summary.
- polygon-packer/polygon_packer.py:
  - Core packing algorithm.
  - This is the main file you modify to try new strategies.
- results.tsv:
  - Log of experiments. Tab-separated.
  - Columns:
    - commit
    - score
    - memory_gb
    - status
    - problem
    - description
- PACKING_REFERENCE.tsv:
  - Auto-generated from Erich Friedman's packing pages.
  - Columns:
    - problem_family
    - n
    - best_value
    - source
    - status (trivial / best_known / proved_optimal)
    - our_problem
  - Used to:
    - Avoid trivial and proved-optimal problems.
    - Prioritize open problems where current best is uncertain or recent.

## Setup

Before starting the loop:

1. Ensure dependencies installed:
   - uv sync (or equivalent) so polygon_packer.py can run.
2. Test run:
   - Set CURRENT_PROBLEM in train.py to something simple, e.g.:
     - 10_3_in_CIRCLE
   - Run: uv run train.py
   - Confirm it prints a summary with:
     - score: ...
     - problem: ...
3. Initialize results.tsv:
   - Header:
     - commit	score	memory_gb	status	problem	description
   - Log your first baseline run.

Once setup is done, enter the experiment loop.

## Problem selection (reference-aware)

Before choosing a problem:

- Consult PACKING_REFERENCE.tsv (and last ~20 rows of results.tsv).
- Hard rules:
  - Do not pick problems where:
    - status == "trivial", or
    - status == "proved_optimal", unless:
      - You are explicitly validating the packer on known values.
- Soft rules:
  - Prefer:
    - "best_known" problems.
    - Problems where source is a human finder (e.g., "Found by ...") rather than a formal proof.
    - Problems where N is small-to-moderate (e.g., 3–15), unless you are specifically exploring large N.
  - Avoid:
    - Problems already at or extremely close to our best score (within 1e-6) unless you are trying a radically different algorithm.
- Diversity:
  - Rotate across different problem families.
  - If stuck on one, switch family or N.

## Problem catalog

You may choose problems from this catalog (and similar variants).
Each entry is a family; you pick N (count) each time.

Naming convention:
- {N}_{inner}_in_{container}
- Examples:
  - 20_3_in_CIRCLE
  - 30_4_in_6
  - 15_TAN_in_CIRCLE

Shape tokens:
- CIRCLE      (approximate with high-sided polygon or dedicated logic)
- 3           (triangles)
- 4           (squares)
- 5           (pentagons)
- 6           (hexagons)
- 8           (octagons)
- TAN         (tan shapes)
- DOMINO      (dominoes)
- L           (L-tromino / L-shapes)

Catalog families (use these as a guide; you can pick N dynamically):

- Circles in Circles
- Triangles in Circles
- Squares in Circles
- Pentagons in Circles
- Hexagons in Circles
- Octagons in Circles
- Tans in Circles
- Dominoes in Circles
- L's in Circles

- Circles in Triangles
- Triangles in Triangles
- Squares in Triangles
- Pentagons in Triangles
- Hexagons in Triangles
- Octagons in Triangles
- Tans in Triangles
- Dominoes in Triangles
- L's in Triangles

- Circles in Squares
- Triangles in Squares
- Squares in Squares
- Pentagons in Squares
- Hexagons in Squares
- Octagons in Squares
- Tans in Squares
- Dominoes in Squares
- L's in Squares

- Circles in Pentagons
- Triangles in Pentagons
- Squares in Pentagons
- Pentagons in Pentagons
- Hexagons in Pentagons
- Octagons in Pentagons
- Tans in Pentagons
- Dominoes in Pentagons
- L's in Pentagons

- Circles in Hexagons
- Triangles in Hexagons
- Squares in Hexagons
- Pentagons in Hexagons
- Hexagons in Hexagons
- Octagons in Hexagons
- Tans in Hexagons
- Dominoes in Hexagons
- L's in Hexagons

- Circles in Octagons
- Triangles in Octagons
- Squares in Octagons
- Pentagons in Octagons
- Hexagons in Octagons
- Octagons in Octagons
- Tans in Octagons
- Dominoes in Octagons
- L's in Octagons

- Circles in Tans
- Triangles in Tans
- Squares in Tans
- Pentagons in Tans
- Hexagons in Tans
- Octagons in Tans
- Tans in Tans
- Dominoes in Tans
- L's in Tans

- Circles in Dominoes
- Triangles in Dominoes
- Squares in Dominoes
- Pentagons in Dominoes
- Hexagons in Dominoes
- Octagons in Dominoes
- Tans in Dominoes
- Dominoes in Dominoes
- L's in Dominoes

- Circles in L's
- Triangles in L's
- Squares in L's
- Pentagons in L's
- Hexagons in L's
- Octagons in L's
- Tans in L's
- Dominoes in L's
- L's in L's

You do not have to do all of them. Focus where improvements are meaningful,
but keep exploring across families.

## Experiment loop

LOOP FOREVER (until manually stopped):

1. Inspect context:
   - Look at current branch/commit.
   - Scan last ~20 rows of results.tsv.
   - Consult PACKING_REFERENCE.tsv for candidate problems.
   - Identify:
     - current best score per problem
     - where you are stuck
     - where you have not tried much

2. Choose or keep a problem:
   - Set CURRENT_PROBLEM in train.py.
   - Rules:
     - Respect "Problem selection (reference-aware)" above.
     - If last 5-7 experiments on the same problem did not improve:
       - Switch to a different problem or different N.
     - If you see a family you haven't touched:
       - Try a baseline there.
     - Every ~20-30 experiments:
       - Try something more radical (new strategy, new family).

3. Form a hypothesis:
   - Example ideas:
     - Increase --attempts.
     - Use grid/spiral/layered initialization.
     - Tune basinhopping T, stepsize, niter.
     - Multi-stage shrinking: coarse pack, then refine.
     - Change optimizer (L-BFGS-B vs others).
     - Add shape-specific heuristics.
   - Write a short description of what you're trying.

4. Implement:
   - Edit polygon_packer.py and/or train.py config.
   - Keep changes focused and testable.

5. Commit:
   - git add train.py polygon-packer/polygon_packer.py
   - git commit -m "experiment: <short description>"

6. Run:
   - uv run train.py > run.log 2>&1
   - Do NOT let output flood your context.

7. Read results:
   - Use:
     - grep "^score:" run.log
     - grep "^problem:" run.log
   - If empty or run exceeded 15 minutes:
     - Treat as crash/failure.
     - Optionally inspect tail -n 50 run.log to understand.

8. Log to results.tsv:
   - Columns:
     - commit (short, 7 chars)
     - score (float; 0 if crash)
     - memory_gb (approx peak memory in GB; 0.0 if crash)
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
   - If improving:
     - Continue same problem, refine.
   - If stuck:
     - Switch problem or N.
   - If you feel you are repeating:
     - Try a more radical idea or different family.

NEVER STOP once the loop has begun.
Do NOT ask "should I keep going?" or "is this a good stopping point?".
Run until interrupted.

## Diversity rules (avoid getting stuck)

- After 5-7 non-improving experiments on the same (problem, N):
  - Switch to a different problem or N.
- Every ~20-30 experiments:
  - Try:
    - A different shape family.
    - A more aggressive strategy.
- Never:
  - Run the exact same config twice.
  - Blindly tweak one hyperparameter without a rationale.

## Simplicity criterion

- All else equal, simpler is better.
- Tiny improvement + lots of messy code:
  - Probably discard.
- Same or better with simpler code:
  - Definitely keep.
- Radical change only if:
  - It yields a clear, meaningful improvement.

## Output format (from train.py)

Each successful run prints:

- score:            2.534000
- training_seconds: 298.4
- total_seconds:    310.1
- problem:          20_3_in_CIRCLE

You can rely on this format when grepping logs.