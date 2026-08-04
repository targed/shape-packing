# System Architecture & Module Design

This document details the single-responsibility architecture, core modules, data flow pipelines, CLI interfaces, Rust solver IPC integration, and JSON data schemas of the **Shape Packing Benchmark Engine**.

---

## 1. Single Responsibility God Modules

The architecture follows a strict "God Module" pattern where each major sub-domain has exactly one primary Python module. All secondary scripts, web endpoints, and CLI utilities act as thin entrypoints importing from these core modules:

```text
                     ┌───────────────────────┐
                     │     cli.py (CLI)      │
                     └──────────┬────────────┘
                                │
   ┌────────────────────────────┼────────────────────────────┐
   │                            │                            │
   ▼                            ▼                            ▼
┌──────────────────────┐  ┌──────────────────┐  ┌──────────────────────┐
│  agent_loop.py       │  │ optimization.py  │  │ solution_tools.py    │
│  (Orchestration)     │  │ (Objective Math) │  │ (Verification/Plot)  │
└──────────┬───────────┘  └────────┬─────────┘  └──────────┬───────────┘
           │                       │                       │
           └───────────────────────┼───────────────────────┘
                                   │
                                   ▼
                         ┌───────────────────┐
                         │   geometry.py     │
                         │ (Pure Math Engine)│
                         └───────────────────┘
```

### Module Responsibilities

1. **`src/shape_packing/geometry.py`**:
   - Pure geometry math: Regular polygon vertex generation ($n=3,4,5,6,8,32$), transformations, rotation matrices, and Separating Axis Theorem (SAT) overlap detection.
   - Poking/boundary penalty calculations.
   - Zero dependence on optimizers, CLI, or agent state.

2. **`src/shape_packing/optimization.py`**:
   - Optimization formulation and objective construction (`build_objective`).
   - Bounds calculation and target metric conversion.
   - Search attempt runner (`run_single_attempt`, `run_all_attempts`).

3. **`src/shape_packing/problems.py`**:
   - Problem string parsing (e.g. `4_6_in_5`, `5_3_in_circle`, `2_L_in_4`).
   - Token mapping and side count resolution (`shape_token_to_sides`).

4. **`src/shape_packing/agent_loop.py`**:
   - Auto-researcher loop orchestration (`choose_problem`, `log_result`, `make_loop_candidate`).
   - `results.tsv` history loading, score filtering (`is_physically_valid_score`), and stuck problem detection.

5. **`src/shape_packing/solution_tools.py`**:
   - Solution JSON loading (`load_solution`) and metric computation (`compute_friedman_metric`, `inverse_friedman_metric`).
   - Exact non-overlap & boundary verification (`verify_solution`).
   - PNG rendering engine (`render_solution`).

---

## 2. Auto-Researcher Loop Workflow

The auto-researcher operates as an autonomous continuous improvement loop:

```text
 ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
 │ 1. Choose    │ ──> │ 2. Execute   │ ──> │ 3. Verify    │
 │    Problem   │     │    Solver    │     │    Solution  │
 └──────────────┘     └──────────────┘     └──────────────┘
        ▲                                         │
        │                                         ▼
 ┌──────────────┐                          ┌──────────────┐
 │ 5. Update    │ <─────────────────────── │ 4. Log to    │
 │    Dashboard │                          │    TSV & JSON│
 └──────────────┘                          └──────────────┘
```

1. **Select Target**: `agent_loop.choose_problem()` selects the next highest priority problem from `priority_queue.json` or `results.tsv`.
2. **Execute Solver**: Calls `packer_rs` (Rust solver binary) via subprocess with `--attempts N` and `--target-s <target_scale>`.
3. **Verify Solution**: `verify_solution()` inspects `solution.json` using SAT overlap and boundary normal checks.
4. **Log Result**: `log_result()` appends the experiment score to `results.tsv` with status `keep`, `discard`, or `crash`.
5. **Update Site Data**: `scripts/build_site_data.py` aggregates `packingVerification/*.json`, `results/`, `results.tsv`, and `priority_queue.json` to produce `site/src/data/site_data.json` for the Astro web dashboard.

---

## 3. Solver Integration & Inter-Process Communication (IPC)

The system supports two optimization backends:

- **Python Backend (`optimization.py`)**: Uses SciPy `L-BFGS-B` or `basinhopping` with Numba-accelerated geometry functions.
- **Rust Backend (`packer_rs`)**: High-performance multi-threaded solver binary located in `packer_rs/`.

### Subprocess Invocation Protocol

When invoked via `src.shape_packing.cli run`:

```bash
packer_rs/target/release/packer_rs <N> <inner_token> <container_token> \
  --attempts <attempts> \
  --solution-file <path_to_solution.json> \
  --target-s <target_scale>
```

### PNG Rendering Control & Storage Optimization

To prevent high-volume parallel runs (e.g., thousands of Slurm worker iterations) from consuming excessive disk space and slowing down Git commits with `solution.png` files, the runner CLI supports skipping PNG generation:

- **Disable PNG Output**: Pass `--no-png` to `python -m src.shape_packing.cli run --problem 4_3_in_circle --no-png` to output ONLY `solution.json`.
- **Batch / Recursive Rendering**: Use `scripts/render_solution.py` to recursively generate PNGs on demand for JSON solutions:
  ```bash
  # Batch render missing solution.png images across results/ in parallel (4 cores):
  python scripts/render_solution.py results/ --recursive --jobs 4
  ```

### JSON Solution Schema

Both Python and Rust solvers emit solution files compliant with the following schema:

```json
{
  "S": 2.5706039648725856,
  "inner_token": "6",
  "container_token": "5",
  "final_metric": 3.0219262000733296,
  "N": 4,
  "values": [
    -0.9091235310650287, -0.979855301492594, 2.8268796475437905,
    0.9132797703526396, -0.7948090368584271, 0.9553221932876965,
    -1.123932035606314, 0.9078797148657954, 2.4068611681160434,
    0.7583983307142401, 1.0175762038002754, 1.149572458423567
  ]
}
```

- **`S`**: Scaled container bounding radius/apothem.
- **`final_metric`**: Computed Erich Friedman metric $s$.
- **`values`**: Flat array of $N \times 3$ values representing $[x_1, y_1, \theta_1, x_2, y_2, \theta_2, \dots, x_N, y_N, \theta_N]$.

---

## 4. Problem Key & Token Mapping

Problem strings follow strict naming conventions across the system:

| Canonical Key | Description | Inner Token | Container Token |
| :--- | :--- | :--- | :--- |
| `4_6_in_5` | 4 Hexagons in Pentagon | `6` | `5` |
| `5_3_in_circle` | 5 Triangles in Circle | `3` | `circle` |
| `3_L_in_4` | 3 L-Trominoes in Square | `L` | `4` |
| `2_domino_in_circle` | 2 Dominoes in Circle | `domino` | `circle` |
| `5_tan_in_5` | 5 Tans in Pentagon | `tan` | `5` |

The `normalize_family_slug()` function handles converting legacy Friedman folder names (e.g. `hexinpen` $\rightarrow$ `6_in_5`, `squincir` $\rightarrow$ `4_in_circle`).
