# Autoresearch loop (concise reference)

This doc is a short reference. For full usage, see README.md.

## Modes (canonical)

- Mode 1 (pure code, recommended):
  - Script: run_autoresearch_loop.py
  - No LLM. Infinite loop:
    - Reads filter.json (optional).
    - Calls: python -m src.shape_packing.cli suggest
    - Calls: python -m src.shape_packing.cli run --problem <X> --attempts <Y>
  - Logs to results.tsv, commits with git.
  - Run:
    - uv run run_autoresearch_loop.py

- Mode 2 (LLM-assisted interactive research):
  - Files:
    - program.md: instructions for agent/human.
    - train.py: experiment runner.
  - Use when you want deep algorithmic exploration.
  - Typical:
    - Agent/human follows program.md.
    - Edits polygon-packer/polygon_packer.py and/or train.py.
    - Runs: uv run train.py

## Problem selection

- Managed by:
  - src/shape_packing/agent_loop.py (choose_problem)
- Uses:
  - priority_queue.json (density)
  - results.tsv (history)
  - PACKING_REFERENCE.tsv (status, best_value)
- Avoids:
  - Trivial/proved_optimal problems
  - Unsupported special shapes by default
- Prefers:
  - Problems where current best is far from best_value
  - Best_known problems with improvement room
  - Diverse families and N

## Prior loop (auto_agent.py)

- Old JSON-mode LLM loop was brittle.
- Removed; concepts merged into the two modes above.
