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

## 6. Universal Configuration (`packing_config.py`)

All global constants, tuning parameters, tolerances, and file paths are defined in:

```python
src/shape_packing/packing_config.py
```

**To tune the system, edit ONLY this file.** The 8 configuration sections are:

| Section | Constants | Controls |
|---|---|---|
| 1. Geometry | `CIRCLE_SIDES`, `SHAPE_TO_SIDES` | Circle polygon approximation & token-to-sides mapping |
| 2. Rust Solver | `RUST_BINARY`, `RUST_TOLERANCE`, etc. | Rust packer_rs execution & parameters |
| 3. Python Optimizer | `OPTIMIZER_ATTEMPTS`, `OPTIMIZER_TOLERANCE`, etc. | Scipy basinhopping fallback |
| 4. Verification | `VERIFY_SAT_TOLERANCE`, `RECORD_MIN_IMPROVEMENT`, etc. | Physical overlap tolerance & record threshold |
| 5. Loop & Scheduling | `LOOP_*` constants | Backoff, attempts, swarm sizes |
| 6. Priority Queue | `QUEUE_*` constants | Problem selection and diversity |
| 7. File Paths | `RESULTS_TSV_PATH`, `RESULTS_DIR`, etc. | All data file locations |
| 8. Rendering | `RENDER_DPI`, `RENDER_FIGURE_SIZE`, etc. | PNG output quality |

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
2. **Execute Solver**: Calls `solver_interface.run_solver()` which communicates directly with `packer_rs` via PyO3 in-process native bindings (or falls back to the compiled CLI binary).
3. **Verify Solution**: `verify_solution()` inspects `solution.json` using exact compound SAT overlap, container boundary containment, metric scaling, and physical area checks.
4. **Log Result**: `log_result()` appends the experiment score to `results.tsv` with status `keep`, `discard`, or `crash`.
5. **Update Site Data**: `scripts/build_site_data.py` aggregates `packingVerification/*.json`, `results/`, `results.tsv`, and `priority_queue.json` to produce `site/src/data/site_data.json` for the Astro web dashboard.

---

## 3. Solver Integration & Native PyO3 Bridge

The system features two interconnected solver execution modes:

- **In-Process PyO3 Native Extension (`packer_rs`)**:
  - High-performance Rust solver compiled as a native Python extension module (`.pyd` on Windows, `.so` on Linux, `.dylib` on macOS).
  - Configured with `default = ["python"]` in `packer_rs/Cargo.toml` so all standard `cargo build --release` runs build the native extension.
  - `solver_interface.py` dynamically inspects candidate extension paths and sorts them by **modification timestamp (`mtime` descending)**, guaranteeing that the freshest compiled binary is always loaded.
- **CLI Subprocess Fallback (`packer_rs.exe` / `packer_rs`)**:
  - Standalone compiled Rust executable used in headless cluster environments or subprocess pipelines.

### Compound SAT & Non-Convex Shape Decompositions

1. **Non-Convex Inner Shapes (L-Tromino `L`)**:
   - Decomposed into 2 convex sub-rectangles: Part A ($1 \times 2$ domino) and Part B ($1 \times 1$ square).
   - Pairwise collision evaluates 4 sub-rectangle SAT checks ($2 \times 2$), allowing non-convex pieces to interlock accurately with zero false positives.

2. **Non-Convex Container Confinement (L-Container `L`)**:
   - Confinement is enforced using the **Bounding Box + Reflex Cut-Out Obstacle** model:
     - Outer Bounding Box: $\left[-\frac{5}{6}S, \frac{7}{6}S\right] \times \left[-\frac{5}{6}S, \frac{7}{6}S\right]$
     - Fixed Cut-Out Obstacle Square: $R_{\text{cutout}} = \left[\frac{1}{6}S, \frac{7}{6}S\right] \times \left[\frac{1}{6}S, \frac{7}{6}S\right]$
   - Shapes are free to pack throughout both the vertical and horizontal arms of the L without being trapped by artificial half-plane intersections.

### PNG Rendering Control & Storage Optimization

To prevent high-volume parallel runs from consuming excessive disk space and slowing down Git commits, the runner CLI supports skipping PNG generation:

- **Disable PNG Output**: Pass `--no-png` to `python -m src.shape_packing.cli run --problem 4_3_in_circle --no-png` to output ONLY `solution.json`.
- **Batch / Recursive Rendering**: Use `scripts/render_solution.py` to recursively generate PNGs on demand for JSON solutions:
  ```bash
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
| `6_TAN_in_L` | 6 Tans in L-Tromino | `TAN` | `L` |
| `2_domino_in_circle` | 2 Dominoes in Circle | `domino` | `circle` |
| `5_tan_in_5` | 5 Tans in Pentagon | `tan` | `5` |

The `normalize_family_slug()` function handles converting legacy Friedman folder names (e.g. `hexinpen` $\rightarrow$ `6_in_5`, `squincir` $\rightarrow$ `4_in_circle`, `taninL` $\rightarrow$ `TAN_in_L`).

---

## 5. Performance Optimizations Architecture

To handle high-throughput autonomous search across thousands of configurations, the architecture integrates low-overhead IPC and fast SAT broadphase:

1. **Direct In-Memory CLI Invocation**:
   - `cli.py` exposes `handle_suggest()` and `handle_run()` with a `direct_call=True` mode, returning internal Python objects instead of forcing `sys.exit()` and JSON stdout parsing.
   - Long-lived runner threads (`run_parallel_loop.py`, `run_autoresearch_loop.py`) keep an in-memory cache of `results.tsv` (`_GLOBAL_HISTORY`) via worker initialization hooks, preventing repeated disk scans.

2. **Rust Solver Sweep & Prune Broadphase**:
   - For $N > 20$, the Rust solver (`packer_rs`) dynamically calculates bounding boxes for each transformed polygon and sorts them along the X-axis.
   - Overlap checks prune non-overlapping candidate pairs early (`min_x2 > max_x1`), avoiding expensive SAT projections and scaling from $O(N^2)$ to $O(N \log N)$.


