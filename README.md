# autoresearch-packing

Autonomous 2D shape packing research loop (no ML).
Adapted from Karpathy's autoresearch concept: an LLM-driven agent iteratively improves packing strategies using a fixed experiment harness.

- No neural training. No MLX. Pure optimization.
- Uses polygon_packer.py as the core packing algorithm.
- 5-minute time budget per experiment.
- Agent follows program.md and never stops until interrupted.

## Files

- program.md:
  - Agent instruction manual.
  - Defines experiment loop, diversity rules, and logging format.
- train.py:
  - Experiment runner.
  - You set CURRENT_PROBLEM (e.g., 20_3_in_CIRCLE) and run:
    - uv run train.py
  - Enforces a 5-minute time budget, calls polygon_packer.py, prints summary.
- polygon-packer/polygon_packer.py:
  - Core packing algorithm (the main file to modify).
- packing_config.py:
  - Shape mappings, naming conventions, and problem catalog.
- verify_solution.py:
  - Strict geometric verifier using the Separating Axis Theorem (SAT).
  - Use to mathematically prove records: `.\.venv\Scripts\python.exe verify_solution.py <solution.json> [PROBLEM_NAME]`
- results.tsv:
  - Tab-separated log of all experiments.
  - Columns: commit, score, memory_gb, status, problem, description.

## ⚠️ The Floating-Point Record Mirage
**CRITICAL WARNING FOR ALL AGENTS AND RESEARCHERS:** 
When searching for absolute world records in discrete geometric packing, standard double-precision floats (`f64`) will inevitably accumulate rounding errors. Solvers trapped in tightly jammed local minima will often report a "new record" by crushing the container slightly beyond its mathematical limit, causing the internal shapes to overlap by microscopic margins (e.g., $10^{-5}$). 

Because the difference between a world record and a failure is often in the 5th decimal place, **a loose solver tolerance will hallucinate fake records.** 
To combat this, the pipeline enforces strict algebraic boundaries:
1. **The Rust Engine (`packer_rs`)** runs with an extreme gradient penalty tolerance of `1e-30`. 
2. **The Python Verifier (`verify_solution.py`)** runs SAT overlap checks with a strict `1e-15` geometric tolerance. 
Never relax these tolerances to claim a record. Any record that cannot mathematically verify at $10^{-15}$ precision is a floating-point artifact and not a true geometric solution.

## Quick start

1. Install dependencies:
   - uv sync
2. Run a baseline:
   - Open train.py
   - Set CURRENT_PROBLEM to something like 10_3_in_CIRCLE
   - Run: uv run train.py
3. Then:
   - Open program.md
   - Let the agent (Cline) follow the experiment loop autonomously.

## Knowledge graph (graphify)

This repo includes a graphify knowledge graph for fast architectural queries.

- graphify-out/ contains the graph, HTML viewer, and report.
- graphify_query.py is a thin CLI wrapper.
- See GRAPHIFY_USAGE.md for details, commands, and Cline system-prompt snippet.

Quick examples:

- python3 graphify_query.py query "How is the gradient computed?"
- python3 graphify_query.py explain "penalty_and_gradient"
- python3 graphify_query.py path "train" "render"

## Usage with Cline (in VS Code)

- Open this repo in VS Code.
- Open program.md in Cline.
- Start in Act mode with a prompt like:
  - "Follow program.md and start the packing autoresearch loop."
- Cline will:
  - Read program.md
  - Edit polygon_packer.py / train.py
  - Run experiments
  - Update results.tsv
  - Switch problems when stuck
  - Continue indefinitely until stopped