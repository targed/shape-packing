# Shape Packing System Refactoring & HPC Cluster Integration Guide

## 1. Overview & Background

### 1.1 What We Were Trying to Do and Why
The Shape Packing project aims to autonomously discover and improve packing/covering configurations for geometric shapes (polygons, circles, dominoes, L-trominoes, etc.) inside container boundaries based on benchmarks compiled by mathematician Erich Friedman.

Previously, the system faced two major bottlenecks:
1. **Outdated Reference Data & Naive Ranking:** Problem selection relied on a legacy, flat `PACKING_REFERENCE.tsv` file. It lacked support for non-polygon shapes, contained outdated/unverified scores, and did not properly estimate spatial density for complex shape combinations.
2. **Compute Bottlenecks:** Optimization runs executed locally on a single machine sequentially. To find state-of-the-art packing density records, we needed to leverage high-performance compute (HPC) clusters with hundreds of parallel CPU cores.

---

## 2. Theoretical Framework & Architecture Plan

### 2.1 Spatial Prioritization & Mathematical Area Calculation
To intelligently select which problems to optimize first, we rank candidate problems by **packing density** ($\rho$). Problems with lower packing density represent configurations with significant wasted space, offering the highest potential for score improvements.

#### Mathematical Definitions:
* **Regular Polygons ($n$-gons with side length $s$):**
  $$\text{Area}(n, s) = \frac{1}{4} n s^2 \cot\left(\frac{\pi}{n}\right)$$
* **Circles (radius $r$):**
  $$\text{Area}(r) = \pi r^2$$
* **Dominoes ("dom"):** Composed of 2 unit squares.
  $$\text{Area}(s) = 2 s^2$$
* **L-Trominoes ("L"):** Composed of 3 unit squares.
  $$\text{Area}(s) = 3 s^2$$
* **Tans ("tan"):** Right isosceles triangle with legs $1, 1, \sqrt{2}$.
  $$\text{Area}(s) = 0.5 s^2$$

#### Density Formulae:
* **Packing Problems:**
  $$\rho = \frac{N \cdot \text{Area}_{\text{inner}}(1.0)}{\text{Area}_{\text{container}}(s_{\text{best}})}$$
  *(Sorted lowest density first — highest wasted volume prioritized).*
* **Covering Problems:**
  $$\rho = \frac{\text{Area}_{\text{container}}(s_{\text{best}})}{N \cdot \text{Area}_{\text{inner}}(1.0)}$$
  *(Inverted for covering problems so lower values indicate high overlap/room for optimization).*

---

### 2.2 Distributed HPC Architecture (The Mill Supercomputer)
To scale beyond local CPU limits, we designed a **Master-Worker Architecture** interfacing with Missouri S&T's **The Mill** HPC cluster (Slurm workload manager).

```
 +----------------------------------+             +-----------------------------------+
 |          LOCAL MASTER            |             |        THE MILL HPC CLUSTER       |
 |                                  |  SSH / SCP  |                                   |
 |  +----------------------------+  | ----------> |  +-----------------------------+  |
 |  |  Local LLM (Localhost:8080)|  |             |  | Slurm Batch Queue (sbatch)  |  |
 |  +----------------------------+  |             |  +-----------------------------+  |
 |                |                 |             |                |                  |
 |  +----------------------------+  |             |  +-----------------------------+  |
 |  | auto_agent.py (Dispatcher) |  |             |  | Compute Nodes (R6525/C6525) |  |
 |  +----------------------------+  | <---------- |  |  packer_rs (64-128 threads)  |  |
 +----------------------------------+    rsync    |  +-----------------------------+  |
                                                  +-----------------------------------+
```

1. **Local Master Node:** Runs `auto_agent.py` and the local LLM. Handles problem selection, prompt engineering, initial seed position generation, and global Git history tracking.
2. **HPC Compute Workers:** Slurm scripts dispatch `packer_rs` (compiled with Rust & Rayon) to run 100,000+ random-restart multi-threaded optimization trials per node.
3. **Decoupled Aggregation:** Compute nodes only output solution JSONs. The local master polls completed jobs via `rsync`, runs `verify_solution.py`, updates `results.tsv`, and commits clean records.

---

## 3. Implementation Summary (What We Did)

### 3.1 Data Verification & System Refactoring
1. **Verified Dataset (`packingVerification/*.json`):** Replaced legacy TSV with 100+ verified JSON datasets representing the complete benchmark set from Erich Friedman's website.
2. **Refactored `src/shape_packing/ranker.py`:**
   - Implemented exact area functions (`polygon_area`, `get_shape_area`).
   - Built `generate_queue()` to parse all `packingVerification/*.json` files, compute mathematical densities, filter out already-proved optimal configurations, and export `priority_queue.json` (1,909 active problems).
3. **Refactored `src/shape_packing/agent_loop.py`:**
   - Updated problem selection to consume `priority_queue.json`.
   - Added robust alias handling (e.g. mapping `"3"` $\leftrightarrow$ `"TRIANGLE"`, `"CIR"` $\leftrightarrow$ `"CIRCLE"`, `"DOM"` $\leftrightarrow$ `"DOMINO"`).
   - Enforced status penalties to block `"trivial"` and `"proved_optimal"` problems while prioritizing `"best_known"` candidates.
4. **Rust Binary Safety & Auto-Compilation:**
   - Updated `src/shape_packing/cli.py` to trigger `cargo build --release` automatically before solver invocation.
   - Enforced strict $N \times 3$ (`[x, y, theta]`) position input validation inside `packer_rs/src/main.rs`.

---

## 4. How to Use & Workflow Guide

### 4.1 Regenerating the Priority Queue
If new benchmark dataset JSONs are added to `packingVerification/`:
```bash
python src/shape_packing/ranker.py
```
This updates `priority_queue.json` with the latest problem rankings.

### 4.2 Querying Problem Suggestions
To inspect what problem the agent recommends next based on density and past history:
```bash
python -m src.shape_packing.cli suggest
```

### 4.3 Running Local Autonomous Loops
To run the autonomous agent locally:
```bash
python auto_agent.py
```

### 4.4 Submitting Jobs to The Mill Supercomputer

#### Step 1: First-Time Cluster Setup
Log into The Mill and clone the repository:
```bash
ssh <username>@mill.mst.edu
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
git clone https://github.com/LukeTKaiser/shape-packing.git
cd shape-packing/packer_rs
cargo build --release
```

#### Step 2: Submitting Batch Jobs
Submit Slurm batch jobs using `sbatch`:
```bash
sbatch mill_runner.sub
```

#### Step 3: Monitoring Jobs
Check job status on the cluster:
```bash
squeue -u <username>
```

---

## 5. File & Module Reference

| File | Purpose |
| :--- | :--- |
| `src/shape_packing/ranker.py` | Computes shape areas, density ratios, and outputs `priority_queue.json`. |
| `src/shape_packing/agent_loop.py` | Orchestrates problem selection policy, alias mapping, and history tracking. |
| `src/shape_packing/cli.py` | Command Line Interface wrapper for `suggest`, `run`, and solver compilation. |
| `packingVerification/*.json` | 100+ verified benchmark JSON datasets. |
| `priority_queue.json` | Ranked queue of active shape packing problems. |
| `packer_rs/src/main.rs` | High-performance multi-threaded Rust solver using Rayon. |
| `auto_agent.py` | Autonomous LLM decision loop and experiment runner. |


Viewed SYSTEM_REFACTOR_AND_HPC_GUIDE.md:84-116
Searched for "filter.json"
Viewed run_autoresearch_loop.py:30-60

`filter.json` is an **optional configuration file**. It does not exist in the repository by default, but you can create it at any time in the root folder of the project:

📁 **Location:** `c:\Users\ltkli\Documents\GitHub\shape-packing\filter.json`

---

### What it does:
When you create `filter.json`, the auto-research scripts (`auto_agent.py`, `run_autoresearch_loop.py`, and `run_parallel_loop.py`) automatically detect it on every iteration. They will pass its constraints to problem selection so you can dynamically filter what shapes or problems the agent works on without restarting the script.

---

### Example `filter.json` template:

You can create `filter.json` in the root directory with any combination of these options:

```json
{
  "min_n": 3,
  "max_n": 20,
  "exclude_container": "circle",
  "exclude_inner": "circle",
  "min_inner_sides": 3,
  "max_inner_sides": 8
}
```

### Supported Filter Options:

| Key | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `min_n` | Integer | Minimum number of shapes ($N$) | `3` |
| `max_n` | Integer | Maximum number of shapes ($N$) | `20` |
| `equal_n` | Integer | Exact number of shapes ($N$) | `5` |
| `include_inner` | String | Comma-separated inner shape whitelist | `"3,4,square"` |
| `exclude_inner` | String | Comma-separated inner shape blacklist | `"circle"` |
| `include_container` | String | Comma-separated container whitelist | `"square,hexagon"` |
| `exclude_container` | String | Comma-separated container blacklist | `"circle"` |
| `min_inner_sides` | Integer | Minimum side count for inner polygon | `3` |
| `max_inner_sides` | Integer | Maximum side count for inner polygon | `8` |
| `min_container_sides` | Integer | Minimum side count for container | `4` |
| `max_container_sides` | Integer | Maximum side count for container | `8` |