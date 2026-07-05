# Autonomous Shape Packing Search Loop

Create a robust, non-LLM-dependent autonomous loop runner script `run_autoresearch_loop.py`. This script will parse `filter.json` directly, call the `suggest` command to find eligible problems, run the solver with optimal attempts, and cycle indefinitely to discover or improve shape packing records under the strict $10^{-15}$ validation standard.

## Proposed Changes

### [New Script]
#### [NEW] [run_autoresearch_loop.py](file:///c:/Users/ltkli/Documents/GitHub/shape-packing/run_autoresearch_loop.py)
A Python script that:
1. Parses `filter.json` (watching for changes on each iteration).
2. Maps `filter.json` properties to CLI flags.
3. Invokes `python -m src.shape_packing.cli suggest [flags]` to obtain the next target problem.
4. Invokes `python -m src.shape_packing.cli run --problem <problem> --attempts 5000` to execute the solver, verify the output, and commit results.
5. Logs runs and sleeps briefly between cycles.
6. Runs in an infinite loop until stopped.

## Verification Plan

### Manual Verification
- Execute `uv run python run_autoresearch_loop.py` to ensure it successfully:
  - Detects `filter.json` constraints.
  - Queries `suggest`.
  - Runs the solver on the suggested problem.
  - Correctly verifies, commits the result to Git, and continues to the next suggested problem.
