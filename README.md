# autoresearch-packing

Autonomous 2D shape packing research loop (no ML training).

This repo implements a Karpathy-style autoresearch workflow for packing problems:
- Iterative experiments
- A fixed experiment harness
- Logging to results.tsv
- Strict geometric verification

No neural training. No MLX. Pure optimization.

## Two modes (pick one)

Only these two modes are live and maintained.

- Mode 1: Pure-code autonomous loop (recommended)
  - Fully automatic, no LLM, set-and-forget.
  - Script: run_autoresearch_loop.py
  - Uses:
    - src.shape_packing.cli suggest → choose next problem
    - src.shape_packing.cli run → run solver, verify, render, log, commit
  - Usage:
    - uv run run_autoresearch_loop.py

- Mode 2: LLM-assisted interactive research
  - Used with an AI agent (Cline, Cursor, etc.) or a human researcher.
  - Instruction file: program.md
  - Experiment harness: train.py
  - Typical flow:
    - Agent/human follows program.md
    - Edits polygon-packer/polygon_packer.py and/or train.py configs
    - Runs: uv run train.py
    - Analyzes logs and updates results.tsv
  - Use this when you want deep, reasoning-heavy algorithmic exploration.

Prior auto_agent.py (JSON-mode LLM loop) has been removed; its useful concepts are merged into these two modes.

## Quick start

1) Install:

   - uv sync

2) Run Mode 1 (recommended):

   - uv run run_autoresearch_loop.py

   It will:
   - Choose problems
   - Run the Rust solver
   - Verify solutions
   - Log results and commit

3) Run Mode 2 (interactive):

   - Open program.md.
   - Tell your AI agent: "Follow program.md and start the packing autoresearch loop."

## Key files and responsibilities

Canonical files (use these):

- run_autoresearch_loop.py: Mode 1 (pure-code autonomous loop).
- program.md: Mode 2 instructions for agent/human.
- train.py: Mode 2 experiment runner (Rust/Python backend).
- priority_queue.json: Problem priority list (density-based).
- filter.json: (optional) Constrain Mode 1 problem selection.
- results.tsv: Experiment log (commit, score, memory_gb, status, problem, description).

Core modules (src/shape_packing):

- cli.py: CLI entry (suggest, run, etc.).
- agent_loop.py: Problem selection, stuck detection, history, logging.
- problems.py: Problem parsing, validation, token mapping.
- packing_config.py: Shape/config data used by problems.py.
- optimization.py: Optimization/orchestration (Python backend).
- solution_tools.py: Verification (SAT) and rendering helpers.

Solver backends:

- packer_rs/: Rust solver (primary, production).
- polygon-packer/polygon_packer.py: Python packing algorithm (legacy/alternative).

Verification and rendering:

- verify_solution.py: SAT-based verification CLI (uses solution_tools.py).
- render_solution.py: Render solution JSON to PNG (uses solution_tools.py).

## The floating-point record mirage

CRITICAL:

Double-precision floats can produce false "world records" by exploiting rounding errors.
We enforce strict tolerances to prevent hallucinated solutions.

Current standards:

- Rust solver:
  - Uses extreme gradient penalty tolerance: 1e-30.
- Verification:
  - Uses SAT overlap/bounds checks with tolerance: 1e-15.

Do not relax these tolerances to claim a record.
Any solution that cannot verify at 1e-15 is a floating-point artifact, not a real solution.

## Problem filtering (Mode 1)

Optionally create filter.json to constrain problems for run_autoresearch_loop.py.

Keys:

- min_n / max_n / equal_n: Filter by number of items.
- include_inner / exclude_inner: Comma-separated inner shape tokens.
- include_container / exclude_container: Comma-separated container tokens.
- min_inner_sides / max_inner_sides: Filter by inner polygon sides.
- min_container_sides / max_container_sides: Filter by container polygon sides.

Example:

{
  "min_n": 5,
  "max_n": 10,
  "include_inner": "HEXAGON",
  "exclude_container": "CIRCLE"
}

The loop re-reads filter.json each iteration.

## Problem selection

Problem selection is handled by:

- src/shape_packing/agent_loop.py: choose_problem()
- Uses:
  - priority_queue.json (density-based priorities)
  - results.tsv (history, stagnation, diversity)
  - PACKING_REFERENCE.tsv (status, best_value)
- Avoids:
  - Unsupported/special shapes (TAN, DOMINO, L) unless explicitly allowed
  - Trivial and proved_optimal problems (via reference)
- Prefers:
  - Problems where our best is still far from known best_value
  - Best_known problems with room for improvement
  - Diverse problem families and N values

## Knowledge graph (optional)

For architectural questions, a graphify knowledge graph is available.

- graphify-out/ contains the graph, HTML viewer, and report.
- graphify_query.py is a CLI wrapper.
- See graphify-out/GRAPHIFY_USAGE.md.

Examples:

- python3 graphify_query.py query "How is the gradient computed?"
- python3 graphify_query.py explain "penalty_and_gradient"
- python3 graphify_query.py path "train" "render"
