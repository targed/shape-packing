# Mill Log Analysis Tool Guide

This document explains how to use the `scripts/analyze_mill_log.py` analysis script to process and visualize execution outputs from Slurm HPC runs on Missouri S&T's "The Mill" supercomputer.

---

## Overview

The log analyzer parses `.out` execution logs produced by `run_parallel_loop.py` (e.g., `results/mill-2330986.out`). It extracts problem events, calculates success metrics and shape features, generates visualization plots using `matplotlib`, and compiles an automated Markdown report.

---

## Prerequisites

Ensure you have `pandas` and `matplotlib` installed in your Python environment:

```bash
pip install pandas matplotlib
```

---

## How to Run

By default, the script processes `results/mill-2330986.out` and outputs the resulting report and figures to the `analysis/` folder:

```bash
python scripts/analyze_mill_log.py
```

### Passing a Custom Log File (Optional)

You can run the script against any Slurm output file by calling the functions in Python or modifying the input path inside `scripts/analyze_mill_log.py`:

```python
from scripts.analyze_mill_log import parse_log, extract_features, generate_charts, write_report

# Parse custom log
df = parse_log("results/mill-YOUR_JOB_ID.out")
agg_df = extract_features(df)

# Output to custom directory
generate_charts(agg_df, output_dir="analysis")
write_report(agg_df, output_dir="analysis")
```

---

## Generated Artifacts

Running the script creates/updates the following files in the `analysis/` directory:

1. **`report.md`**: The primary Markdown summary report containing high-level statistics, top scores, and embedded chart references.
2. **`top_problems.png`**: A bar plot showing the top 15 most frequently attempted problems.
3. **`family_distribution.png`**: A pie chart depicting the distribution of attempts across different problem families (e.g., `3_in_5`, `4_in_3`, `3_in_circle`).
4. **`n_vs_success.png`**: A scatter plot comparing $N$ (number of inner shapes) against the job success rate to visualize problem difficulty scaling.

---

## Extracted Metrics

- **`N`**: Number of inner shapes to pack (parsed from problem string `N_inner_in_container`).
- **`inner_sides`**: Geometry token for the packed shape (e.g. `3`, `4`, `6`, `CIRCLE`).
- **`container_sides`**: Geometry token for the container shape (e.g. `3`, `4`, `5`, `CIRCLE`).
- **`problem_family`**: Combined shape classification string (e.g., `3_in_5`).
- **`success_rate`**: Percentage of runs for a problem that yielded valid optimization improvements.
- **`best_score`**: Lowest objective score recorded for each problem during the HPC run.
