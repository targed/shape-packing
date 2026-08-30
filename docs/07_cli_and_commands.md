# CLI Commands Reference & User Manual

Welcome to the comprehensive command reference for the **Shape Packing Auto-Researcher & Benchmark Engine**. This guide covers every CLI tool, background script, native solver invocation, and web utility available in the repository.

---

## ⚡ Quick Start & Common Run Commands

Here are copy-pasteable commands for the most common workflows:

### 1. Run a Single Packing Problem
```bash
# Run 100 attempts for 6 Tans in an L-Tromino container:
python -m src.shape_packing.cli run --problem 6_TAN_in_L --attempts 100

# Run 50 attempts for 4 Hexagons in a Pentagon without generating PNG images (faster):
python -m src.shape_packing.cli run --problem 4_6_in_5 --attempts 50 --no-png

# Run 20 attempts for 5 Triangles in a Circle with a 10-second timeout:
python -m src.shape_packing.cli run --problem 5_3_in_circle --attempts 20 --time-limit 10.0
```

### 2. Launch Autonomous Auto-Researcher Loop
```bash
# Run 25 consecutive problem optimizations automatically selected from the priority queue:
python -m src.shape_packing.cli loop --max-runs 25 --attempts 50

# Run multi-worker parallel auto-research loop across all CPU cores:
python scripts/run_parallel_loop.py --workers 8 --runs 50
```

### 3. Mathematically Verify a Solution
```bash
# Verify an existing solution JSON against strict SAT, container bounds, and area checks:
python -m src.shape_packing.cli verify results/6_TAN_in_L/20260827_155937/solution.json --problem 6_TAN_in_L
```

### 4. Update the Web Dashboard Site Data
```bash
# Rebuild site_data.json aggregating all results, benchmarks, and priority queue data:
python -m src.shape_packing.cli site-data
```

### 5. Compile Rust Native Solver
```bash
# Compile optimized Rust binary & PyO3 native extension:
cd packer_rs && cargo build --release && cd ..
```

### 6. Run the Test Suite
```bash
# Run all 318+ automated unit and integration tests:
python -m pytest tests/
```

### 7. Run Criterion Microbenchmarks
```bash
# Run statistical nanosecond microbenchmarks on solver hot loops:
cd packer_rs && cargo bench && cd ..
```

---

## 📖 Command Index

1. [`python -m src.shape_packing.cli run`](#1-cli-run-single-problem-optimizer) — Run solver on a specific problem.
2. [`python -m src.shape_packing.cli loop`](#2-cli-loop-autonomous-researcher-loop) — Autonomous priority queue search loop.
3. [`python -m src.shape_packing.cli verify`](#3-cli-verify-solution-verifier) — Validate solution JSON files.
4. [`python -m src.shape_packing.cli site-data`](#4-cli-site-data-dashboard-data-builder) — Build web dashboard database.
5. [`python -m src.shape_packing.cli export-records`](#5-cli-export-records-benchmark-record-exporter) — Export verified records to `records/`.
6. [`python -m src.shape_packing.cli compare`](#6-cli-compare-result-comparison-utility) — Compare results between runs or TSV files.
7. [`python -m src.shape_packing.cli suggest`](#7-cli-suggest-priority-queue-inspector) — Suggest next target problem.
8. [`scripts/render_solution.py`](#8-scriptsrender_solutionpy-batch-image-renderer) — Parallel/recursive PNG image renderer.
9. [`scripts/run_parallel_loop.py`](#9-scriptsrun_parallel_looppy-multi-process-parallel-search) — High-throughput multi-worker swarm.
10. [`scripts/analyze_mill_log.py`](#10-scriptsanalyze_mill_logpy-hpc-log-analyzer) — HPC Slurm cluster log analyzer.
11. [`packer_rs` (Rust Native Binary)](#11-packer_rs-direct-rust-cli-binary) — Direct CLI access to compiled Rust solver.
12. [`cargo bench` (Criterion Microbenchmarks)](#12-cargo-bench-criterion-microbenchmarks) — Nanosecond microbenchmark performance profiling.
13. [`site/` (Astro Web Dashboard)](#13-site-astro-interactive-web-dashboard) — Web UI development and build.

---

## 1. `cli run` (Single Problem Optimizer)

Executes the high-performance Rust solver (or Python fallback) on a specific discrete packing problem.

```bash
python -m src.shape_packing.cli run [OPTIONS]
```

### Options & Flags

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--problem`, `-p` | `STRING` | *Required* | Problem token string (e.g. `4_6_in_5`, `6_TAN_in_L`, `5_3_in_circle`, `2_L_in_4`). |
| `--attempts`, `-a` | `INT` | `50` | Number of random multi-start optimization attempts. |
| `--time-limit`, `-t` | `FLOAT` | `280.0` | Global wall-clock timeout in seconds for all attempts combined. |
| `--tolerance` | `FLOAT` | `1e-5` | Maximum allowed constraint violation depth for valid packing. |
| `--finalstep` | `FLOAT` | `0.001` | Multiplier step size reduction rate during final convergence. |
| `--target-s` | `FLOAT` | `None` | Target container scale $S$; attempts abort early if they exceed this value. |
| `--no-png` | `FLAG` | `False` | Disables rendering `solution.png` (saves disk I/O during large batch runs). |
| `--visualize`, `-v` | `FLAG` | `False` | Force render `solution.png` immediately after solving. |
| `--output-dir`, `-o` | `PATH` | `results/<problem>/<timestamp>/` | Custom destination directory for `solution.json` and `solution.png`. |
| `--json` | `FLAG` | `False` | Output structured result JSON to stdout for programmatic scripting. |
| `--save-best` | `FLAG` | `True` | Automatically log results to `results.tsv` and record if valid. |

### Examples

```bash
# High-effort search for 6 L-Trominoes in a Square (500 attempts):
python -m src.shape_packing.cli run --problem 6_L_in_4 --attempts 500

# Scripted run returning JSON output to stdout:
python -m src.shape_packing.cli run --problem 2_DOMINO_in_CIRCLE --attempts 20 --json
```

---

## 2. `cli loop` (Autonomous Researcher Loop)

Runs the continuous improvement loop, repeatedly selecting high-priority problems from `priority_queue.json` and attempting improvements.

```bash
python -m src.shape_packing.cli loop [OPTIONS]
```

### Options & Flags

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--max-runs`, `-n` | `INT` | `100` | Maximum number of problems to attempt before stopping. |
| `--attempts`, `-a` | `INT` | `50` | Base number of solver attempts per problem instance. |
| `--time-limit`, `-t` | `FLOAT` | `280.0` | Maximum seconds allowed per individual problem run. |
| `--dynamic-attempts` | `FLAG` | `False` | Automatically scale attempts based on shape count $N$ and problem difficulty. |
| `--swarm-size` | `INT` | `1` | Number of parallel worker threads running problem instances simultaneously. |
| `--allow-stuck` | `FLAG` | `False` | Include problems previously flagged as "stuck" (no progress in 5+ runs). |
| `--force-new` | `FLAG` | `False` | Only attempt problems that have zero existing entries in `results.tsv`. |

### Examples

```bash
# Autonomous loop running 50 problem runs with dynamic difficulty scaling:
python -m src.shape_packing.cli loop --max-runs 50 --dynamic-attempts

# Focus exclusively on unattempted problems in the benchmark catalog:
python -m src.shape_packing.cli loop --force-new --max-runs 20
```

---

## 3. `cli verify` (Solution Verifier)

Verifies a `solution.json` file against mathematical constraints: compound SAT non-overlap, container boundary containment, metric scaling consistency, and theoretical physical area bounds.

```bash
python -m src.shape_packing.cli verify <PATH_TO_SOLUTION_JSON> [OPTIONS]
```

### Arguments & Flags

| Argument / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `sol_path` | `PATH` | *Positional* | Path to `solution.json` to verify. |
| `--problem`, `-p` | `STRING` | Inferred | Problem key (e.g. `6_TAN_in_L`); auto-detected from JSON if omitted. |
| `--tolerance` | `FLOAT` | `1e-5` | Maximum permissible SAT overlap / boundary protrusion depth. |
| `--check-record` | `FLAG` | `False` | Also checks if metric beats known benchmark records in `data/packingVerification/`. |
| `--min-improvement` | `FLOAT` | `1e-5` | Required improvement margin to count as a new record (`RECORD_MIN_IMPROVEMENT`). |
| `--json` | `FLAG` | `False` | Output verification verdict and error list as JSON. |

### Examples

```bash
# Standard verification:
python -m src.shape_packing.cli verify results/6_L_in_4/20260827_143000/solution.json

# Verification with record check:
python -m src.shape_packing.cli verify results/6_TAN_in_L/20260827_155937/solution.json --check-record
```

---

## 4. `cli site-data` (Dashboard Data Builder)

Aggregates `data/packingVerification/*.json`, `data/results/`, `data/results.tsv`, and `data/priority_queue.json` into `site/src/data/site_data.json` for the interactive web frontend.

```bash
python -m src.shape_packing.cli site-data [OPTIONS]
```

### Options & Flags

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--records-dir` | `PATH` | `data/packingVerification/` | Directory containing Erich Friedman benchmark JSON files. |
| `--results-tsv` | `PATH` | `data/results.tsv` | Path to the experiment history TSV file. |
| `--output`, `-o` | `PATH` | `site/src/data/site_data.json` | Destination path for the aggregated web database. |
| `--quiet`, `-q` | `FLAG` | `False` | Suppress progress output during aggregation. |

### Examples

```bash
python -m src.shape_packing.cli site-data
```

---

## 5. `cli export-records` (Benchmark Record Exporter)

Scans `results.tsv` and `results/` for all verified optimal or record-beating packings and exports clean, canonical solution files into `records/`.

```bash
python -m src.shape_packing.cli export-records [OPTIONS]
```

### Options & Flags

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--results-tsv` | `PATH` | `results.tsv` | Path to `results.tsv`. |
| `--output-dir`, `-o` | `PATH` | `records/` | Output directory for canonical records. |
| `--min-improvement` | `FLOAT` | `1e-5` | Minimum margin required to displace existing record. |

---

## 6. `cli compare` (Result Comparison Utility)

Compares two TSV result files or benchmark datasets to evaluate solver performance, improvements, and regressions.

```bash
python -m src.shape_packing.cli compare <FILE1> <FILE2> [OPTIONS]
```

### Options & Flags

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `file1` | `PATH` | *Positional* | Baseline TSV file or results directory. |
| `file2` | `PATH` | *Positional* | Comparison TSV file or results directory. |
| `--output`, `-o` | `PATH` | `None` | Optional path to write markdown summary report. |
| `--summary-only` | `FLAG` | `False` | Display high-level summary counts without listing every problem. |

---

## 7. `cli suggest` (Priority Queue Inspector)

Queries the priority queue and ranking engine to suggest the next highest-yield problem to optimize.

```bash
python -m src.shape_packing.cli suggest [OPTIONS]
```

### Options & Flags

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--limit`, `-n` | `INT` | `10` | Number of candidate suggestions to display. |
| `--strategy` | `CHOICE` | `density` | Selection heuristic: `density`, `stuck`, `unattempted`, or `random`. |
| `--json` | `FLAG` | `False` | Output suggestion list as JSON. |

---

## 8. `scripts/render_solution.py` (Batch Image Renderer)

Recursively crawls directories and generates high-resolution `solution.png` diagrams for every `solution.json` found.

```bash
python scripts/render_solution.py <TARGET_PATH> [OPTIONS]
```

### Options & Flags

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `path` | `PATH` | *Positional* | File path or directory containing solutions. |
| `--recursive`, `-r` | `FLAG` | `False` | Recursively scan all subdirectories for `solution.json`. |
| `--jobs`, `-j` | `INT` | `1` | Number of parallel worker processes to spawn. |
| `--force`, `-f` | `FLAG` | `False` | Overwrite existing `solution.png` files. |
| `--dpi` | `INT` | `150` | DPI resolution for rendered PNG graphics. |

### Examples

```bash
# Render all missing solution.png files across results/ in parallel using 8 CPU cores:
python scripts/render_solution.py results/ --recursive --jobs 8
```

---

## 9. `scripts/run_parallel_loop.py` (Multi-Process Parallel Search)

High-throughput autonomous worker pool for multi-core workstations and dedicated compute nodes.

```bash
python scripts/run_parallel_loop.py [OPTIONS]
```

### Options & Flags

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--workers`, `-w` | `INT` | CPU count | Number of independent parallel worker processes. |
| `--runs`, `-r` | `INT` | `100` | Total number of problem runs per worker. |
| `--attempts`, `-a` | `INT` | `50` | Multi-start attempts per problem instance. |
| `--time-limit`, `-t` | `FLOAT` | `280.0` | Timeout per problem instance in seconds. |

---

## 10. `scripts/analyze_mill_log.py` (HPC Log Analyzer)

Parses Slurm/HPC cluster batch run logs (`mill-*.out`), extracts improved solutions, validates them with `verify_solution`, and safely merges them into `results.tsv`.

```bash
python scripts/analyze_mill_log.py <LOG_PATH_OR_GLOB> [OPTIONS]
```

### Options & Flags

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `log_path` | `GLOB` | *Positional* | Path or glob pattern for Slurm output files (e.g. `mill-*.out`). |
| `--output-tsv` | `PATH` | `results.tsv` | Destination TSV to append verified solutions. |
| `--export-json` | `FLAG` | `True` | Save extracted `solution.json` and `solution.png` to `results/`. |

---

## 11. `packer_rs` (Direct Rust CLI Binary)

For maximum performance, the compiled Rust binary can be invoked directly from the command line:

```bash
# Windows
packer_rs\target\release\packer_rs.exe <N> <INNER_TOKEN> <CONTAINER_TOKEN> [FLAGS]

# Linux / macOS
packer_rs/target/release/packer_rs <N> <INNER_TOKEN> <CONTAINER_TOKEN> [FLAGS]
```

### Positional Arguments
1. `N` (`usize`): Number of inner shapes to pack (e.g. `6`).
2. `INNER_TOKEN` (`string`): Inner shape token (`3`, `4`, `5`, `6`, `8`, `CIRCLE`, `TAN`, `DOMINO`, `L`).
3. `CONTAINER_TOKEN` (`string`): Container shape token (`3`, `4`, `5`, `6`, `8`, `CIRCLE`, `TAN`, `DOMINO`, `L`).

### Flags
- `--attempts <INT>`: Number of randomized multi-start search attempts (default: `50`).
- `--solution-file <PATH>`: Destination path to write the best valid `solution.json`.
- `--target-s <FLOAT>`: Scale threshold $S$; attempts terminate early if they cannot beat this metric.
- `--tolerance <FLOAT>`: Overlap tolerance (default: `1e-5`).
- `--time-limit <FLOAT>`: Maximum execution duration in seconds.

---

## 12. `cargo bench` (Criterion Microbenchmarks)

Executes statistical nanosecond/microsecond benchmarks using Criterion.rs across core solver math (SAT overlap calculations, normal projections, spatial broadphase, compound polyform decomposition, and end-to-end attempts).

```bash
# Run all solver benchmarks:
cd packer_rs && cargo bench

# Run specific microbenchmark group:
cargo bench --bench solver_benchmarks -- penalty_and_gradient

# Run specific attempt group:
cargo bench --bench solver_benchmarks -- run_attempt
```

### Visual Reports
HTML charts and regression curves are automatically generated and saved to:
- `packer_rs/target/criterion/report/index.html`

---

## 13. `site/` (Astro Interactive Web Dashboard)

The web dashboard provides real-time visualization of all packings, family comparison tables, metric graphs, and interactive SVG diagrams.

```bash
# Navigate to web dashboard directory:
cd site

# Install dependencies:
npm install

# Run local development server (starts at http://localhost:4321):
npm run dev

# Build production bundle:
npm run build
```

