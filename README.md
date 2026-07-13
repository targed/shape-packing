# autoresearch-packing

Autonomous 2D shape packing research loop (no ML training).
Adapted from Karpathy's autoresearch concept: iterative improvement using a fixed experiment harness.

- No neural training. No MLX. Pure optimization.
- Rust solver (packer_rs) is the core optimization engine.
- Two clear modes:
  - Mode 1: Pure code autonomous loop (recommended default).
  - Mode 2: LLM-assisted interactive research (for deep exploration).

## Modes

### Mode 1: Pure code autonomous loop (recommended)

Fully automatic, no LLM, set-and-forget.

- Script: run_autoresearch_loop.py
- Uses:
  - src.shape_packing.cli suggest -> chooses next problem.
  - src.shape_packing.cli run -> runs solver, verifies, renders, logs, commits.

Usage:

- uv run run_autoresearch_loop.py

Behavior:
- Runs in an infinite loop until stopped.
- For each iteration:
  - Reads filter.json (if present) to constrain problems.
  - Calls suggest to get the next target problem.
  - Runs solver on that problem.
  - Logs to results.tsv, commits with git.
- No LLM calls. Fully deterministic given the same environment.

If you just want "run the agent and let it work", use this mode.

### Mode 2: LLM-assisted interactive research

Intended for use with an AI agent (e.g., Cline, Cursor) or a human researcher.
The LLM reads a short instruction file and iteratively modifies code/configs.

- File: program.md
- Experiment runner: train.py

How to use with an AI agent:

- Open this repo.
- Tell the agent: "Follow program.md and run the shape packing autoresearch loop."
- The agent will:
  - Read program.md.
  - Edit polygon-packer/polygon_packer.py and/or train.py configs.
  - Run: uv run train.py (with CURRENT_PROBLEM set).
  - Analyze logs.
  - Update results.tsv.
  - Continue until stopped.

This mode is for deeper research where the LLM should understand and change algorithms, not just pick hyperparameters.

## Core files

- run_autoresearch_loop.py:
  - Mode 1: pure-code autonomous loop (recommended default).
- program.md:
  - Mode 2: instructions for LLM-assisted research loop.
- train.py:
  - Experiment runner used in Mode 2.
  - Set CURRENT_PROBLEM at the top, then:
    - uv run train.py
- src/shape_packing/:
  - Central modules:
    - cli.py: CLI for suggest and run.
    - agent_loop.py: history, problem selection, stuck detection.
    - problems.py: problem naming and validation.
    - optimization.py: optimization/orchestration (for Python backend).
- polygon-packer/polygon_packer.py:
  - Python packing algorithm (legacy/alternative backend).
- packer_rs/:
  - Rust solver (primary optimization engine).
- verify_solution.py:
  - Strict geometric verifier using the Separating Axis Theorem (SAT).
  - Use:
    - .venv/Scripts/python.exe verify_solution.py <solution.json> [PROBLEM_NAME]
- results.tsv:
  - Tab-separated log of all experiments.
  - Columns: commit, score, memory_gb, status, problem, description.

## The Floating-Point Record Mirage

CRITICAL:
Double-precision floats will accumulate rounding errors.
Solvers can hallucinate fake world records by squeezing slightly beyond true limits (e.g., 1e-5 overlaps).

To prevent this:
- packer_rs uses extreme gradient penalty tolerance: 1e-30.
- verify_solution.py uses SAT overlap checks with tolerance: 1e-15.

Never relax these tolerances to claim a record.
Any record that cannot verify at 1e-15 precision is a floating-point artifact, not a real solution.

## Problem Filtering (filter.json)

For Mode 1 (run_autoresearch_loop.py), you can control what problems are allowed using filter.json.

Available keys:
- min_n / max_n / equal_n (int): Filter by number of items.
- include_inner / exclude_inner (string): Comma-separated inner shapes (e.g., "3,4" or "TRIANGLE,SQUARE").
- include_container / exclude_container (string): Comma-separated container shapes.
- min_inner_sides / max_inner_sides (int): Filter by inner polygon sides.
- min_container_sides / max_container_sides (int): Filter by container polygon sides.

Example filter.json:

{
  "min_n": 5,
  "max_n": 10,
  "include_inner": "HEXAGON",
  "exclude_container": "CIRCLE"
}

The loop re-reads filter.json on each iteration, so changes apply immediately.

## Quick start

1) Install dependencies:

   - uv sync

2) Pure code loop (default, recommended):

   - uv run run_autoresearch_loop.py

   Let it run. It will:
   - Choose problems.
   - Run the solver.
   - Verify solutions.
   - Log results and commit.

3) LLM-assisted loop (interactive):

   - Open program.md.
   - Tell your AI agent:
       "Follow program.md and start the packing autoresearch loop."

   The agent will iterate, edit strategies, and run train.py.

## Knowledge graph (graphify)

This repo includes a graphify knowledge graph for architectural queries.

- graphify-out/ contains the graph, HTML viewer, and report.
- graphify_query.py is a CLI wrapper.
- See GRAPHIFY_USAGE.md for details.

Examples:

- python3 graphify_query.py query "How is the gradient computed?"
- python3 graphify_query.py explain "penalty_and_gradient"
- python3 graphify_query.py path "train" "render"
