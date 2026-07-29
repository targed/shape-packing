# Mill Log Analysis Tool Guide

This document explains how to use the upgraded `scripts/analyze_mill_log.py` analysis script to process, customize, and visualize execution outputs from Slurm HPC runs on Missouri S&T's "The Mill" supercomputer.

---

## Overview

The log analyzer parses `.out` execution logs produced by `run_parallel_loop.py` (e.g., `results/mill-2330986.out`). It extracts problem events, calculates success metrics and shape features, generates 5 visualization plots using `matplotlib`, and compiles an automated Markdown report featuring statistical summaries and multiple customizable tables.

---

## Prerequisites

Ensure you have `pandas` and `matplotlib` installed in your Python environment:

```bash
pip install pandas matplotlib
```

---

## CLI Customization Options

The script features CLI flags via `argparse` to customize log inputs, filtering, table lengths, and chart outputs:

```bash
python scripts/analyze_mill_log.py [OPTIONS]
```

### Available Command-Line Arguments

| Argument | Default | Description |
| :--- | :--- | :--- |
| `--log-file PATH` | Latest `results/mill-*.out` | Explicit path to a Slurm `.out` log file |
| `--output-dir DIR` | `analysis` | Output directory for charts and `report.md` |
| `--top-n INT` | `15` | Number of items to display in top charts & markdown tables |
| `--min-runs INT` | `1` | Filter out problems with fewer than `MIN_RUNS` executions |
| `--family STR` | `None` | Filter analysis to a specific problem family (e.g., `3_in_5`, `4_in_3`) |
| `--min-n INT` | `None` | Filter problems where $N \ge \text{MIN\_N}$ |
| `--max-n INT` | `None` | Filter problems where $N \le \text{MAX\_N}$ |

---

## Usage Examples

### 1. Default Run (Latest Log File)
```bash
python scripts/analyze_mill_log.py
```

### 2. Customize Top Table Length (Top 25)
```bash
python scripts/analyze_mill_log.py --top-n 25
```

### 3. Analyze Only a Specific Problem Family (`3_in_5`)
```bash
python scripts/analyze_mill_log.py --family 3_in_5 --output-dir analysis/family_3_in_5
```

### 4. Filter by Problem Size Range ($N = 10 \dots 50$) and Minimum Runs
```bash
python scripts/analyze_mill_log.py --min-n 10 --max-n 50 --min-runs 5
```

---

## Generated Visualizations & Tables

Running the script creates the following artifacts in the specified output directory:

### Visual Charts (`.png` files)
1. **`top_problems.png`**: Bar plot of the top $N$ most frequently run problems.
2. **`family_distribution.png`**: Donut chart illustrating compute workload by problem family.
3. **`n_vs_success.png`**: Scatter plot with trend line illustrating problem size $N$ vs. success rate.
4. **`score_by_family.png`**: Multi-line plot demonstrating objective score scaling across shape count $N$ for top families.
5. **`attempts_distribution.png`**: Bar chart showing requested search attempts per run (e.g., 5,000 vs 50,000).

### Executive Tables in `report.md`
1. **High-Level Executive Summary**: Total problems, runs, total solver attempt iterations requested, overall success rate, and global score metrics (Min, Mean, Median, Max).
2. **Problem Family Breakdown Table**: Total problems, total runs, total compute attempts, average success rate, and best score range for every family.
3. **Top $N$ Best Improvements Table**: The lowest objective scores found across all problems.
4. **Highest Volume Problems Table**: The problems consuming the highest total search iterations.
5. **Hardest Problems Table**: Problems sorted by lowest success rates to identify bottlenecks.
