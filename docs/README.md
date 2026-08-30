# Shape Packing Benchmark System Documentation

Welcome to the central documentation hub for the **Shape Packing Auto-Researcher & Benchmark Engine**. This documentation set provides a complete, authoritative guide to the architecture, geometric theory, HPC cluster execution, verification pipelines, and benchmark dataset.

---

## Documentation Index

### 1. [System Architecture & Module Design](01_system_architecture.md)
Detailed specification of the core codebase architecture, God module responsibilities (`geometry.py`, `optimization.py`, `problems.py`, `agent_loop.py`, `solution_tools.py`), CLI interfaces, Rust solver IPC (`packer_rs`), and data schemas.

### 2. [Research & Shape Geometry](02_research_and_geometry.md)
Comprehensive mathematical guide to discrete shape packing. Covers regular polygons ($n=3,4,5,6,8$), circle container & inner approximations (32-gon), special polyforms (L-trominoes, dominoes, tans, lines, ellipses), Separating Axis Theorem (SAT) overlap detection, and metric scaling ($s$ vs $S$) formulas.

### 3. [Benchmarks & Priority Queue Ranking](03_benchmarks_and_ranking.md)
Full specification of the Erich Friedman benchmark dataset (`data/packingVerification/`), record classifications (Trivial, Proved Optimal, Best Known), priority queue density calculations ($\rho = N \cdot A_{inner} / A_{container}$), target selection strategies, and closeness metric math.

### 4. [HPC & Cluster Execution Guide](04_hpc_and_cluster_execution.md)
Guide for running massive parallel searches on Slurm/HPC clusters. Explains `mill-*.out` log parsing via `analyze_mill_log.py`, worker execution, job batching, and high-performance compute scaling protocols.

### 5. [Debugging, Testing & Solution Verification](05_debugging_and_testing.md)
Systematic debugging workflows, solution verification engine (`verify_solution`), physical area bound checks, pytest suite organization, test coverage policies, and **Criterion.rs statistical microbenchmarking suite**.

### 6. [Project Milestone History & Handoffs](06_project_history.md)
Chronological record of major development milestones, design evolutions, past bug resolutions, and handoff summaries.

### 7. [CLI Commands Reference & User Manual](07_cli_and_commands.md)
Complete quick-start guide, detailed argument and option specifications for all CLI subcommands (`run`, `loop`, `verify`, `site-data`, `export-records`, `compare`, `suggest`), utility scripts, native Rust solver commands, and Astro web dashboard workflows.

---

## Directory Organization

- `docs/01_system_architecture.md` - Core system architecture and schemas.
- `docs/02_research_and_geometry.md` - Geometric theory and shape token math.
- `docs/03_benchmarks_and_ranking.md` - Benchmarks, priority queue, and metrics.
- `docs/04_hpc_and_cluster_execution.md` - HPC Slurm batching and log analysis.
- `docs/05_debugging_and_testing.md` - Verification engine and testing policies.
- `docs/06_project_history.md` - Historical milestones and handoffs.
- `docs/07_cli_and_commands.md` - Comprehensive CLI command reference & user manual.
- `data/erich-friedman.github.io/` - Local mirror of Erich Friedman's Packing Center pages.
- `docs/graphify-out/` - Graphify knowledge graph outputs.
- `docs/superpowers/` - System customization and feature specs.

