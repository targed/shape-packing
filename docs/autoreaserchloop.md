# Autonomous Shape Packing Search Loop

Last updated: 2026-07-13

This repo has two modes for running experiments:

1) Pure code loop (recommended default)

- File: run_autoresearch_loop.py
- Behavior:
  - No LLM.
  - Infinite loop:
    - Reads filter.json (if present) and maps it to CLI flags.
    - Calls: python -m src.shape_packing.cli suggest [flags]
    - Calls: python -m src.shape_packing.cli run --problem <X> --attempts <Y>
  - Logs to results.tsv, commits with git.
- Use this for hands-off, continuous research.

Command:

- uv run run_autoresearch_loop.py

2) LLM-assisted interactive loop (research mode)

- File: program.md (instructions) + train.py (runner)
- Use this when:
  - You want a smart agent (Cline, Cursor, etc.) to:
    - Read context.
    - Modify polygon_packer.py or train.py configs.
    - Try new algorithms/strategies.
- This is for deeper, reasoning-heavy exploration.

Usage:

- Tell the agent: "Follow program.md and start the packing autoresearch loop."

Prior loop (auto_agent.py):

- Previously there was an LLM-in-the-loop script using strict JSON responses.
- It was brittle and underperforming.
- It has been removed; its useful concepts were merged into the current modes.
