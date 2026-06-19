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