# Project Milestone History & Handoff Logs

This document tracks the chronological history, major milestones, past bug resolutions, and handoff records of the **Shape Packing Benchmark Engine**.

---

## Chronological Milestones

### Milestone 1: Initial Core Framework & Python Optimizer
- Formulated the fundamental regular polygon packing mathematics.
- Built initial geometry module (`geometry.py`), Scipy L-BFGS-B optimization module (`optimization.py`), and CLI (`cli.py`).
- Established `results.tsv` schema for recording solver experiment results.

### Milestone 2: Rust Solver Acceleration (`packer_rs`)
- Implemented high-performance C++/Rust solver in `packer_rs/` using multi-threaded parallel attempts.
- Added IPC subprocess interface between Python `cli.py` and `packer_rs`.
- Achieved $100\times$ speedup over pure Python optimization loops.

### Milestone 3: Slurm Cluster Integration & HPC Runner
- Built `scripts/mill_runner.py` and `scripts/analyze_mill_log.py` for Slurm cluster batching.
- Scaled execution across thousands of problem instances (`mill-*.out` log files).

### Milestone 4: Priority Queue & Erich Friedman Benchmark Dataset
- Ingested Dr. Erich Friedman's Packing Center records into `packingVerification/*.json`.
- Built `priority_queue.json` density ranking ($\rho = N \cdot A_{inner} / A_{container}$) to automatically target unattempted or loose packings.

### Milestone 5: Astro Web Dashboard & Interactive Analytics
- Built Astro static web dashboard in `site/` with TailwindCSS and dynamic SVG vector rendering.
- Implemented `scripts/build_site_data.py` to aggregate benchmarks, solver runs, Slurm logs, and priority queue data into `site_data.json`.

### Milestone 6: Circle Support & Metric Normalization Fixes
- Added regular 32-gon approximation for circle container/inner geometry.
- Fixed metric scaling ($s = S$ for circle containers, $s = 2 S \sin(\pi/n)$ for regular polygons).
- Cleaned legacy corrupt scores from `results.tsv` and added physical area bound validation (`is_physically_valid_score`).
- Reorganized documentation structure into 6 comprehensive modular guides.

### Milestone 7: Low & Medium Term Performance Optimizations
- **Rust Solver Allocation & Broadphase**:
  - Eliminated heap allocation inside hot-loop `penalty_and_gradient` by introducing reusable pre-allocated buffers.
  - Implemented early stopping in Adam optimizer after 300 non-improving iterations.
  - Added Sweep & Prune (Spatial Broadphase) bounding-box sorting for $N > 20$, reducing overlap complexity to $O(N \log N)$.
- **Python Orchestrator & Multi-Processing**:
  - Implemented batched git commits (1 commit per 10 successful solver runs) to minimize filesystem I/O.
  - Refactored `cli.py` to expose direct Python invocation functions (`direct_call=True`) avoiding subprocess execution overhead.
  - Added global in-memory caching of `results.tsv` across process pools in `run_parallel_loop.py` and `run_autoresearch_loop.py`.

### Milestone 8: Universal Configuration & Tan Shape Enablement
- Centralized all system parameters, tolerances, and thresholds into `src/shape_packing/packing_config.py`.
- Enabled right isosceles triangle (`TAN`) across geometry engine, Python verifiers, Rust solver, benchmark ingestor, and web visualization.
- Decoupled `RECORD_MIN_IMPROVEMENT` ($10^{-5}$) from physical overlap tolerance to eliminate micro-churn.

### Milestone 9: Non-Convex L-Tromino Support & PyO3 Build Hygiene
- **L-Tromino Non-Convex Decomposition**:
  - Solved SAT limitation on concave shapes by splitting L-tromino into 2 convex sub-rectangles ($1 \times 2$ domino + $1 \times 1$ square) for $2 \times 2$ compound SAT collision detection in Rust and Python.
- **Non-Convex L-Container Confinement**:
  - Replaced linear half-plane intersection with **Bounding Box + Reflex Cut-Out Obstacle ($R_{\text{cutout}}$)** model, unlocking both horizontal and vertical arms in problems like `6_TAN_in_L`.
- **PyO3 Native Extension Hardening**:
  - Added `default = ["python"]` feature to `Cargo.toml` so standard `cargo build --release` compiles native PyO3 modules.
  - Added dynamic `mtime`-based sorting in `solver_interface.py` to ensure newest compiled native binaries always take precedence.

### Milestone 10: Criterion Microbenchmarking Suite & Performance Baselines
- **Statistical Microbenchmarking Framework**:
  - Added Criterion.rs suite (`packer_rs/benches/solver_benchmarks.rs`) with the `plotters` backend for statistical nanosecond profiling and regression testing.
  - Formulated 5 distinct hot-loop scenarios (`penalty_and_gradient`) and 2 multi-start macrobenchmarks (`run_attempt`).
- **Baseline Verification**:
  - Verified standard polygon SAT at **1.09–1.14 µs** (~900k–1M SAT evals/sec/core).
  - Verified compound $2 \times 2$ non-convex L-tromino SAT at **1.48–1.57 µs**.
  - Verified non-convex obstacle confinement at **1.16–2.26 µs**.
  - Verified Sweep & Prune broadphase scaling ($N=25$) at **7.30–7.77 µs**.
  - Established automated visual HTML reports generated under `packer_rs/target/criterion/report/index.html`.

### Milestone 12: Exhaustive Per-Image Dimension Database & Exact Per-$N$ Lookup
- **Friedman Image Catalog Parser (`scripts/generate_image_properties.py`)**:
  - Scanned all 74 packing family folders in `docs/erich-friedman.github.io/packing-with-images/` across **2,040+ individual benchmark images** using PIL.
  - Automatically extracted exact pixel `(width, height)` and format (`png`, `gif`) for each individual problem ($N=1 \dots 50+$) across all families.
  - Augmented `src/shape_packing/family_properties.json` with an `images` dictionary per family while maintaining family colors (`inner`, `container`), filename templates, and median dimension fallbacks.
- **Dynamic Accessor APIs (`src/shape_packing/packing_config.py` & `solution_tools.py`)**:
  - Updated `get_family_properties(family, N=...)` and `get_family_colors` to look up exact per-$N$ dimensions on demand.
  - Added `get_problem_image_dimensions(problem: str) -> Tuple[int, int]` for instantaneous dimension retrieval from problem strings (e.g. `"21_DOMINO_in_5"` $\rightarrow (250, 237)$).
  - Updated `render_solution` to automatically pass $N=\text{sol.N}$, ensuring exported solution PNGs match the exact native website pixel dimensions.
- **Verification**:
  - Cross-verified random sample of 25 images across diverse families directly against disk files with 100% precision.
  - Full test suite passing (319/319 tests).




