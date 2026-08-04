# HPC & Cluster Execution Guide

This document provides instructions for running high-performance shape packing searches on Slurm/HPC clusters, parsing execution logs (`mill-*.out`), and utilizing the `mill` parallel worker suite.

---

## 1. Slurm Cluster Architecture & Mill Scripts

When executing large-scale searches across thousands of problem instances, solver jobs are dispatched to Slurm compute nodes using the `mill` runner framework.

### Work Distribution Pipeline

```text
 ┌──────────────────────┐
 │  Slurm Batch Job     │ (e.g. sbatch run_mill.sh)
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐
 │  scripts/mill_runner │ (Spawns worker instances)
 └──────────┬───────────┘
            │
            ├───────────────┬───────────────┐
            ▼               ▼               ▼
     ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
     │ Worker #1   │ │ Worker #2   │ │ Worker #N   │
     │ (packer_rs) │ │ (packer_rs) │ │ (packer_rs) │
     └─────────────┘ └─────────────┘ └─────────────┘
```

### Key Scripts

- **`scripts/mill_runner.py`**: Cluster orchestrator that manages parallel worker processes, distributes problem keys, and captures output.
- **`scripts/analyze_mill_log.py`**: Log parsing utility that scans `mill-*.out` log files for worker performance statistics, scores, attempts, and crashes.

---

## 2. Slurm Log File Structure (`mill-*.out`)

Slurm jobs write stdout/stderr to log files formatted as `results/mill-<job_id>.out`.

### Key Log Line Patterns

```text
[3_6_in_5] Starting (5000 attempts)
[3_6_in_5] Success!
[Main] Worker finished 3_6_in_5 with score 2.564905
[3_6_in_5] Search failed
```

- **`[problem_key] Starting (N attempts)`**: Worker launched for problem.
- **`[Main] Worker finished <key> with score <score>`**: Completed run score.
- **`Search failed`**: Run completed without finding a valid configuration below target.

---

## 3. Log Analysis with `scripts/analyze_mill_log.py`

To summarize the results of a Slurm execution run, execute `analyze_mill_log.py`:

```bash
python scripts/analyze_mill_log.py
```

### Aggregated Metrics

The analyzer parses all `mill-*.out` log files in `results/` and extracts:

1. **Total Job Starts**: Total number of worker launches.
2. **Total Attempts**: Sum of all optimization attempts across all workers.
3. **Success / Fail Counts**: Total successful solutions vs failed searches.
4. **Score Summaries**: Best score achieved per problem key.

These log stats are automatically integrated into `site_data.json` by `scripts/build_site_data.py`.

---

## 4. High-Performance Execution Protocols

1. **Binary Compilation**: Always compile `packer_rs` in `--release` mode before submitting Slurm jobs:
   ```bash
   cargo build --release --manifest-path packer_rs/Cargo.toml
   ```
2. **Target Injection**: Ensure `cli.py` or `mill_runner.py` injects `--target-s` to truncate searches early once a target bound is reached.
3. **Log Retention**: Keep `mill-*.out` files in `results/` so `build_site_data.py` can report complete cluster stats on the dashboard.
