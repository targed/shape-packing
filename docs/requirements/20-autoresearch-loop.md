# Autoresearch Loop Requirements

Scope:
agent_loop.py, run_autoresearch_loop.py, run_parallel_loop.py.

1. Problem Selection (choose_problem)

- WHEN the autoresearch loop selects the next problem THEN it SHALL:
  - consult:
    - PACKING_REFERENCE (to avoid trivial/proved_optimal),
    - history of recent runs (to avoid overfitting to one problem),
  - prefer problems marked best_known over those marked trivial or proved_optimal.

- IF a problem has been attempted excessively THEN:
  - the scheduler SHALL increase its penalty so other problems can be tried.

- WHEN a problem family has consumed too many runs THEN:
  - the scheduler SHALL penalize further selection from that family.

- WHEN a problem has zero or very few attempts THEN:
  - it SHALL receive a bonus in selection scoring so it is tried at least once.

2. Fairness and Diversity

- WHEN the priority queue includes problems in compact or shorthand names THEN:
  - they SHALL be normalized into canonical N_X_in_Y format before evaluation.
- WHEN problems are scored THEN:
  - bonuses based on distance to best_value SHALL be bounded and not dominate selection.

3. Pure-Code Mode (run_autoresearch_loop.py)

- WHEN run_autoresearch_loop.py is running THEN:
  - it SHALL operate fully automatically using internal heuristics only (no LLM).
- WHEN it finishes a run THEN:
  - it SHALL:
    - log the result into results.tsv or equivalent,
    - update PACKING_REFERENCE if a new record is confirmed.

4. Cluster Mode (run_parallel_loop.py)

- WHEN run_parallel_loop.py starts on a SLURM node THEN:
  - it SHALL discover the allocated CPU count,
  - it SHALL launch that many worker processes.

- WHEN workers are running THEN:
  - they SHALL NOT write directly to shared disk files,
  - all disk writes, PACKING_REFERENCE updates, and git operations SHALL be done by a single main thread.

- WHEN SLURM sends SIGTERM (graceful shutdown) THEN:
  - the orchestrator SHALL:
    - stop dispatching new tasks,
    - let in-progress tasks finish (up to a short timeout),
    - flush all writes,
    - exit cleanly without corrupting JSON/TSV.

- IF a problem is determined to be stuck THEN:
  - the system MAY:
    - increase the number of attempts,
    - assign multiple cores to the same problem (swarm mode) using different random initializations.

5. History and Logging

- WHEN an experiment is completed THEN:
  - a row SHALL be recorded with:
    - problem,
    - score/metric,
    - commit,
    - status (keep/discard/crash).
- WHEN the history is used for decisions THEN:
  - the system SHALL prefer recent history to detect stuck problems and imbalanced families.
