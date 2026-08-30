# 2D Shape Packing Auto-Researcher and Benchmark Engine

An autonomous mathematical optimization engine designed to discover dense, valid 2D packings of regular polygons and polyforms (triangles, squares, pentagons, hexagons, octagons, circles, dominoes, tans, and L-trominoes) inside geometric containers.

The system benchmarks solutions against Erich Friedman's comprehensive Packing Center reference records (2,200+ problem instances across 80 shape families), automatically logs verified improvements, and exports publication-ready submission packages.

---

## Key Features

- Fast Rust Solver (`packer_rs`): Continuous gradient-based packing engine featuring Separating Axis Theorem (SAT) overlap detection, container boundary containment, and Adam optimization.
- Dual Execution Modes: Direct in-process native execution via PyO3 bindings for high throughput, with automated CLI subprocess fallback.
- Smart Problem Ranking: Heuristic priority queue that prioritizes high-impact targets, unstuck problems, and near-record opportunities.
- HPC Cluster Multiprocessing: Scalable parallel runner (`run_parallel_loop.py`) with dynamic difficulty scaling and multi-worker swarming designed for Slurm clusters.
- Exact Verification Engine: Multi-stage geometric verifier with SAT collision checks, boundary containment certificates, and physical area bound validation.
- World Record Submission Kits: Automated exporter (`scripts/export_records.py`) that renders publication-quality PNGs, writes coordinate tables, and generates formatted submission drafts.
- Interactive Web Dashboard: Modern Astro-based visualization interface with family matrices, difficulty heatmaps, and SVG solution renders.

---

## System Requirements

- Python: Version 3.10 or higher
- Rust: Stable toolchain (cargo, rustc 1.75+)
- C/C++ Compiler: GCC, Clang, or MSVC (required by PyO3/setuptools)

---

## Installation and Setup

### 1. Clone the Repository

```bash
git clone https://github.com/targed/shape-packing.git
cd shape-packing
```

### 2. Set Up Python Environment

Create and activate a virtual environment:

```bash
# On Linux / macOS:
python3 -m venv .venv
source .venv/bin/activate

# On Windows (PowerShell):
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install the dependencies and the `shape_packing` package in editable mode:

```bash
pip install -r requirements.txt
```

### 3. Build the Rust Solver

Compile the Rust solver in release mode for maximum optimization:

```bash
cd packer_rs
cargo build --release
cd ..
```

Note: If Rust is not installed on your system or HPC cluster node, install it using standard rustup or the included helper script:
```bash
sh rustup-init.sh -y
source "$HOME/.cargo/env"
```

---

## Quick Start

### 1. Suggest the Next Target Problem

Query the priority ranker to pick the highest-leverage unsolved or improvable problem:

```bash
python -m src.shape_packing.cli suggest
```

Filter suggestions by shape family or piece count:
```bash
python -m src.shape_packing.cli suggest --min-n 3 --max-n 12 --include-inner TAN
```

### 2. Run the Solver on a Problem

Run the optimization engine on a specific problem instance:

```bash
python -m src.shape_packing.cli run --problem 5_TAN_in_4 --attempts 5000
```

### 3. Launch the Autonomous Search Loop

Run the automated local search loop:

```bash
python scripts/autoresearch/run_autoresearch_loop.py
```

### 4. Run on a Slurm HPC Cluster

Submit the pre-configured Slurm batch script on your compute cluster:

```bash
sbatch mill_runner.sub
```

Or invoke the multiprocessing orchestrator directly:
```bash
python run_parallel_loop.py
```

### 5. Export World Records for Submission

Audit all solution runs, verify geometries against Erich Friedman benchmarks, and export submission kits:

```bash
python scripts/export_records.py --clean
```

Exported artifacts are written to `data/records/` including summary tables, manifests, and email drafts.

### 6. Build Web Dashboard Data

Generate the aggregated dataset for the Astro web frontend:

```bash
python scripts/build_site_data.py
```

### 7. Run the Test Suite

Run the full pytest suite:

```bash
pytest tests/
```

---

## Project Structure

```text
shape-packing/
├── data/
│   ├── packingVerification/       # Erich Friedman benchmark JSON datasets (75 families)
│   ├── results/                   # Solver run outputs organized by problem and timestamp
│   ├── records/                   # Verified world-record submission packages
│   ├── analysis/                  # Slurm logs, difficulty audits, and performance charts
│   ├── erich-friedman.github.io/  # Scraped website reference archive
│   ├── results.tsv                # Global experiment history ledger
│   └── priority_queue.json        # Dynamic target ranking queue
├── src/shape_packing/
│   ├── geometry.py                # Regular polygons, circle approximations, polyforms, SAT
│   ├── optimization.py            # Adam optimizer, collision penalties, gradient descent
│   ├── agent_loop.py              # Priority queue loaders, problem selector, history logger
│   ├── packing_config.py          # Global path constants, family definitions, thresholds
│   ├── cli.py                     # Command-line interface subcommands
│   ├── solution_tools.py          # Metric conversions (s vs S), visualizer, verifier
│   ├── solver_interface.py        # PyO3 in-process bridge and binary fallback
│   └── records_exporter.py        # World-record auditor and submission kit generator
├── packer_rs/
│   ├── src/                       # Rust solver source code (SIMD SAT, Adam optimizer, PyO3)
│   └── Cargo.toml                 # Rust dependencies and release build profiles
├── scripts/
│   ├── autoresearch/              # Autonomous search loop and standalone polygon packer
│   ├── export_records.py          # World records exporter CLI
│   ├── build_site_data.py         # Dashboard data builder
│   ├── render_solution.py         # Solution JSON to PNG visualizer
│   ├── analyze_mill_log.py        # Slurm cluster log parser and auditor
│   └── compare_results.py         # Solution comparison against baseline benchmarks
├── site/                          # Astro-based interactive web dashboard
├── tests/                         # Complete test suite (pytest, hypothesis, coverage)
├── docs/                          # Comprehensive technical documentation
├── mill_runner.sub                # Slurm batch submission script for cluster jobs
├── requirements.txt               # Python package dependencies
├── pyproject.toml                 # Package configuration and build specification
└── rustup-init.sh                 # Bootstrap script for offline/cluster Rust toolchain setup
```

---

## Documentation

Comprehensive guides and architectural specifications are available in the `docs/` directory:

1. [System Architecture and Module Design](docs/01_system_architecture.md): Core package structure, God modules, and PyO3 native bridge.
2. [Research and Shape Geometry](docs/02_research_and_geometry.md): Regular polygons, polyforms, SAT collision detection, and metric scaling mathematics.
3. [Benchmarks and Ranking](docs/03_benchmarks_and_ranking.md): Friedman benchmarks, density formulas, and priority queue scoring.
4. [HPC and Cluster Execution Guide](docs/04_hpc_and_cluster_execution.md): Slurm job batching, multiprocessing worker dispatch, and log analysis.
5. [Debugging, Testing and Verification](docs/05_debugging_and_testing.md): Solution verification certificates, physical area checks, and pytest coverage.
6. [Project Milestone History](docs/06_project_history.md): Development chronology, design decisions, and resolved edge cases.
7. [CLI Commands Reference and User Manual](docs/07_cli_and_commands.md): Complete reference for all CLI subcommands, flags, and options.