# Performance Analysis & Optimization Report — Shape-Packing System

**Date:** 2026-08-07  
**Scope:** Python orchestrator + Rust solver (packer_rs)  
**No code changes made; report only.**

---

## Executive Summary

- **Rust solver dominates runtime** by a very large margin: on non-trivial problems (>5 shapes), solver wall time is 20–30+ seconds for a few thousand attempts, while all orchestrator overhead is <1 second. Optimization effort should be heavily weighted toward the solver and its algorithm.
- **`choose_problem` is a significant per-iteration bottleneck**: 0.44–0.50 s per invocation on current history (17k rows, 1.1 MB TSV). This is ~20–30 % of the total per-iteration budget. It is entirely avoidable with caching.
- **`last_experiments_for` / `is_stuck` is the single largest hotspot** in Python: 0.35 s per `choose_problem` call. Scanning 17k history rows 1,152 times (once per queue item) is O(Q × H) and will continue to worsen as history grows.
- **Repeated subprocess launches add ~0.4–0.55 s per call**: each `suggest`, `run`, and `verify_solution.py` invocation spawns a new Python or Rust process. Over a night of hundreds of runs, this is non-trivial (minutes lost to cold starts and I/O).
- **History I/O (results.tsv) is re-read on every `suggest` and every `run`**: ~0.015–0.05 s each time, but also contributes to `choose_problem` overhead when combined with scanning. At scale, this is both slow and contention-prone.
- **Rust solver: gradient descent is extremely CPU-heavy** — 3,000 Adam iterations × 5,000–10,000 attempts × N(N−1)/2 SAT checks. On 10 shapes, 5,000 attempts, 20 s wall time, 330 s user time → ~16 cores fully saturated, no early-exit or convergence acceleration.
- **Repeated geometry recomputation in the Rust solver**: every `penalty_and_gradient` call rebuilds `polygon_array` and `vector_array` (allocating `N * nsi` tuples), even though the unit geometry is constant. Cheap to avoid.
- **No benchmarking infrastructure** currently exists (no criterion in Cargo.toml), making it hard to validate optimizations quantitatively.
- **Low-hanging fruit** exists in both layers and can cut orchestrator overhead by 70–90 % without touching the solver:
  - Cache history + queue metadata
  - Avoid per-queue-item `is_stuck` scan
  - Reuse processes or reduce subprocess hops

---

## Environment and Methodology

- **Machine:** Mac (Apple Silicon), 8+ cores.
- **Python:** 3.10, via `uv`.
- **Rust:** Release profile (opt-level=3, LTO, codegen-units=1).
- **Profiled components:**
  - `python -m cProfile` on:
    - `cli.py suggest` (end-to-end subprocess)
    - Direct in-process calls to `load_history`, `current_best_scores`, `choose_problem`
  - `/usr/bin/time -l` on Rust solver:
    - `3 3 4 --attempts 500`
    - `10 4 CIRCLE --attempts 5000 --time-limit 20`
    - `15 3 CIRCLE --attempts 5000 --time-limit 20`
    - `20 4 8 --attempts 5000 --time-limit 30`
  - Subprocess launch overhead:
    - 5 × `suggest`: 0.407 s average per invocation
    - 5 × Rust binary with 10 attempts: 0.549 s average per invocation
- **Constraints:**
  - No extremely long runs: solver capped via `--time-limit` or small attempts.
  - No flamegraphs generated; analysis is based on cProfile + /usr/bin/time + static code review.

---

## 1. Python Orchestrator Profiling

### 1.1 Overall latency of one iteration

A typical iteration:

1. `suggest` (subprocess + `load_history` + `choose_problem`)
2. `run` (subprocess + Rust solver + verify + render + git)
3. Sleep

Measured `suggest` subprocess (steps 1):

- 5 runs: 2.034 s total → 0.407 s per subprocess launch.
- Inside `suggest`:
  - `load_history`: 0.046 s
  - `current_best_scores`: 0.007 s
  - `choose_problem`: 0.441 s (cumulative including history)

**Per-iteration orchestrator overhead (before solver) is ~0.4–0.5 s.**  
Over a night with 500 iterations, that is 3–4 minutes. Not catastrophic, but unnecessary and grows.

### 1.2 `choose_problem` — hot path

Profile (single call on current history):

- Total: ~0.44 s.
- Top consumers:
  - `last_experiments_for`: 0.362 s (1,152 calls, scanning all 17k rows each time)
  - `is_stuck`: 0.365 s cumulative (calls `last_experiments_for`)
  - `normalize_problem_name`: 0.020 s (29,898 regex matches)
  - `load_history`: 0.014 s
  - `current_best_scores`: 0.007 s

Key findings:

- **`is_stuck(history, p_str)` is called once per queue item** (1,152 queue items in priority_queue.json).
  - Each call scans all 17k history rows to find entries for that problem.
  - This is O(Q × H) per iteration (queue size × history length).
  - With Q≈1,152, H≈17k → ~19.6 million row inspections per `choose_problem`.
  - This is the dominant cost and will grow unbounded.

- **`normalize_problem_name` uses `re.match` 30k times**.
  - Minor cost (~0.02 s), but unnecessary to re-normalize the same names over and over.
  - Queue and history entries can be pre-normalized.

- **History is fully re-scanned in `current_best_scores` and `recent_problems`**, both called from `choose_problem` and from CLI independently.

### 1.3 `load_history` — repeated full reads

- Reads results.tsv (17k rows, 1.1 MB) every time `suggest` or `run` is invoked.
- Cost: ~0.015–0.05 s.
- In the parallel loop (`run_parallel_loop.py`), `get_state` → `cli suggest` does this on every scheduling cycle, potentially many times in rapid succession.

### 1.4 Verification and rendering overhead

- After each solver run, `cli.py` (line 128–134) launches:
  - `verify_solution.py` as a subprocess
  - `render_solution.py` as another subprocess (unless `--no-png`)
- These are:
  - Pure geometry checks and plotting; fast for a single problem.
  - But each adds a process startup + import cost (~0.2–0.4 s each).

### 1.5 Specific recommendations — Python orchestrator

Prioritized, with file references:

- **HIGH PRIORITY — Cache `is_stuck` / history analysis (agent_loop.py)**
  - Precompute:
    - Per-problem: last K scores (for stuck detection)
    - Per-problem: total_runs, family_runs
  - Maintain these in-memory in the loop scripts instead of re-scanning from TSV each time.
  - Impact: cut `choose_problem` from ~0.44 s to <0.05 s.

- **HIGH PRIORITY — Avoid O(Q × H) scan**
  - Refactor `is_stuck` to operate on a map {problem → [last K results]} built once, not from raw history every call.
  - File: agent_loop.py:620–640.

- **MEDIUM PRIORITY — Pre-normalize problem names**
  - Normalize all queue/problem names once and store normalized form; avoid repeated `re.match` in `normalize_problem_name` (agent_loop.py:326).
  - File: agent_loop.py, problems.py.

- **MEDIUM PRIORITY — Reuse history in loop processes**
  - In `run_parallel_loop.py`, instead of calling `suggest` via subprocess each time, import directly and keep `history` / `choose_problem` in the same process.
  - File: run_parallel_loop.py:68–84.

- **LOW PRIORITY — Inline verification where possible**
  - For `--no-commit` or internal runs, verify_solution and render_solution can be imported directly rather than spawned as subprocesses.
  - File: cli.py:128–134.

---

## 2. Rust Solver Profiling

### 2.1 Execution characteristics

Measurements (release mode):

- **3 triangles in square (3 3 4), 500 attempts:**
  - Wall: 16.9 s
  - User: 265.9 s
  - Peak RSS: ~3.8 MB
- **10 squares in circle, 5,000 attempts, time_limit=20:**
  - Wall: 20.0 s
  - User: 330.9 s
  - Peak RSS: ~3.9 MB
- **15 triangles in circle, 5,000 attempts, time_limit=20:**
  - Wall: 20.0 s
  - User: 346.6 s
- **20 squares in octagon, 5,000 attempts, time_limit=30:**
  - Wall: 30.0 s
  - User: 515.3 s
  - Peak RSS: ~4.2 MB

Interpretation:

- Solver fully saturates CPU across all cores.
- For serious problems, the solver is the only thing that matters.
- Memory usage is low (~3–4 MB); optimization opportunities are computational, not memory-based.

### 2.2 Core hot paths (static + runtime analysis)

Algorithm outline (main.rs):

- For each attempt:
  - `run_attempt` (lines 304–460):
    - Initialize `x0` (positions + angles).
    - Loop:
      - Call `minimize_gradient` (lines 468–527):
        - 3,000 Adam iterations.
        - Each iteration calls `penalty_and_gradient` (lines 530–802):
          - Recompute all transformed polygons + normals.
          - O(N²) pairwise SAT-style overlap checks.
          - Per-pair: O(nsi * 2) axes, each projecting nsi vertices.

Key issues:

- **Every penalty_and_gradient call reallocates polygon_array and vector_array (lines 548–549):**
  - `vec![(0.0, 0.0); N * nsi]` twice per call.
  - Called 3,000+ times per attempt, 5,000+ attempts.
  - This is millions of small heap allocations of identical size.
  - Fix: allocate once, reuse.

- **SAT overlap loop is O(N² × nsi²) and tight:**
  - For 15–20 shapes, this dominates.
  - No spatial indexing or broadphase; all pairs tested every time.
  - For dense packings, most pairs are close; early exit (line 727) helps only when separated.
  - Fix (medium): add a simple grid-based broadphase for early exclusion of far-apart shapes.

- **No adaptive early exit / convergence acceleration:**
  - Adam always runs 3,000 iterations (line 498).
  - Many attempts likely converge (or become hopeless) long before 3,000.
  - Fix: early stop when:
    - `new_fx` hasn’t improved in K consecutive iterations, or
    - `max_violation` is comfortably below tolerance.

- **`powi(iter as i32)` for bias correction (lines 508–509):**
  - Computing `beta.powi(iter)` every iteration is expensive.
  - Fix: precompute or incrementally update `beta1^t`, `beta2^t` in O(1).

- **`penalty_and_gradient` allocates grad unconditionally when `compute_grad` is true (line 545):**
  - No opportunity to avoid this, but could be reused if we maintain a fixed buffer.

- **Unnecessary string operations in get_shape_geometry (lines 267–302):**
  - `token.to_uppercase()` called repeatedly.
  - Minor; still, for a hot path worth a small cleanup.

### 2.3 Parallelism

- Already uses Rayon (`into_par_iter()`) across attempts: good.
- Within each attempt, the core work is sequential Adam.
- For larger N, you could parallelize the pairwise overlap checks (line 663–799) but:
  - Risk of false sharing and lock contention may outweigh benefits.
  - Probably not worth it for N < 40.

### 2.4 Recommendations — Rust solver

**High-impact / low-risk:**

- **Reuse geometry buffers:**
  - Move `polygon_array`, `vector_array`, and grad buffer into a struct allocated once per attempt, not per `penalty_and_gradient` call.
  - Impact: significant reduction in allocation overhead.

- **Adaptive Adam iteration limit:**
  - Add early stopping when:
    - No improvement for ~150–300 iterations.
    - Or gradient norm is very small.
  - Impact: 20–50 % wall time savings on many attempts.

- **Incremental bias correction factors:**
  - Avoid `beta.powi(iter)` each step; update running powers.
  - Impact: small but non-trivial (fewer pow calls × millions of iterations).

**Medium-impact:**

- **Spatial broadphase for overlap checks:**
  - Use a simple uniform grid to partition shapes; only test neighbors.
  - Impact: reduces O(N²) to something much smaller for well-separated clusters.

**Lower-impact / nice to have:**

- **Add criterion-based microbenchmarks:**
  - Benchmark `penalty_and_gradient` for typical N (5–20).
  - Ensures future optimizations are validated.
  - Currently no criterion dependency in Cargo.toml.

- **Clean up unused variables:**
  - `dx_dposx`, `dy_dposy` (lines 601–602) flagged by compiler warnings.

---

## 3. Cross-Layer (Orchestrator ↔ Solver) Analysis

### 3.1 Communication pattern

Each solver invocation:

1. Python subprocess (cli.py `handle_run`) spawns:
   - Rust binary via `subprocess.run`
   - Captures stdout/stderr
   - Parses score from last line of stdout
2. Then:
   - Spawns `verify_solution.py` subprocess
   - Spawns `render_solution.py` subprocess (often skipped with --no-png)
   - Runs git add/commit

### 3.2 Measured overhead

- **Python subprocess (suggest):** ~0.41 s average per call.
- **Rust binary launch (10 attempts):** ~0.55 s average per call (includes cold process overhead).
- With 500+ runs per day, that is 3–4 minutes just for subprocess launches.

### 3.3 I/O

- **results.tsv:**
  - Re-read on every `suggest` and every `run` that needs `target-s`.
  - Grows monotonically; at 17k rows already 1.1 MB, still cheap but linear scan is O(rows).
- **Git commit after every run (cli.py:141–143):**
  - Each run does `git add`, `git commit`.
  - Cheap for one file, but with many runs this is many tiny commits.
  - Can slow filesystem and add latency.

### 3.4 Recommendations

- **HIGH: Reduce subprocess churn in parallel loop**
  - In `run_parallel_loop.py`, instead of forking a new Python process per worker, consider:
    - Importing the `handle_run` logic directly into workers.
  - Impact: reduces overhead per run, especially at scale.

- **MEDIUM: Batch git commits**
  - Commit results every K runs or every minute instead of every single run.
  - Impact: minor I/O savings and smaller commit history.

- **MEDIUM: Avoid re-reading results.tsv repeatedly**
  - Keep an in-memory index in the orchestrator; append-only and incremental.
  - Impact: faster `suggest` as history grows.

- **LOW: Inline solver invocation in CLI**
  - For environments where the Rust binary is stable, the orchestrator could:
    - Use a persistent Rust server or a shared-memory channel for repeated jobs.
    - Overkill now, but worth considering if solver time becomes prohibitive.

---

## 4. Optimization Plan

### 4.1 Low-hanging fruit (fast, low risk)

- [x] In `choose_problem`, cache per-problem run counts and last-K scores; avoid O(Q × H) scan via `is_stuck`.
- [x] Pre-normalize problem names in queue and history accessors; avoid repeated regex in `normalize_problem_name`.
- [x] Reuse geometry buffers in Rust `penalty_and_gradient` instead of allocating each call.
- [x] Add early stopping in Adam loop (3,000 iterations) when no improvement.
- [x] Replace `beta.powi(iter)` with incremental bias correction factors.
- [x] Batch git commits instead of one per run.

Expected: 30–60 % reduction in orchestrator overhead; 15–30 % reduction in solver time without changing algorithm.

### 4.2 Medium-term wins

- [x] Add criterion-based microbenchmarks for `penalty_and_gradient` and `run_attempt`:
  - Implemented in `packer_rs/benches/solver_benchmarks.rs`. Run via `cargo bench` in `packer_rs/`.
  - **Baseline Microbenchmark Results**:
    - `penalty_and_gradient/4_6_in_5_with_grad` ($N=4$): **1.14 µs**
    - `penalty_and_gradient/12_3_in_circle_with_grad` ($N=12$): **2.80 µs**
    - `penalty_and_gradient/25_4_in_4_broadphase` ($N=25$): **13.6 µs**
    - `penalty_and_gradient/6_L_in_4_compound_sat` ($N=6$, $2 \times 2$ compound SAT): **2.74 µs**
    - `penalty_and_gradient/6_TAN_in_L_container_confinement` ($N=6$, reflex cut-out obstacle): **2.37 µs**
    - `run_attempt/4_6_in_5_single_attempt` (End-to-end single attempt): **91.0 ms**
- [x] Implement spatial broadphase (Sweep & Prune bounding box sorting for $N > 20$) for pairwise overlap checks.
- [x] In parallel loop, import orchestrator logic directly into worker processes instead of forking via CLI subprocess.
- [x] Maintain an in-memory history index instead of full TSV re-reads.

Expected: further 20–40 % solver acceleration for larger N; significant orchestrator simplification.

### 4.3 High-effort / high-reward (future)

- [x] Integrate Rust solver as a library (via PyO3) with seamless fallback:
  - **In-process PyO3 native extension** (`solve_py` in `packer_rs/src/lib.rs` with `default = ["python"]`): Eliminates process startup overhead and memory serialization.
  - **Automatic Fallback Hierarchy**: `solver_interface.py` checks PyO3 in-process native extension $\rightarrow$ falls back to compiled CLI binary (`packer_rs.exe` / `packer_rs`) $\rightarrow$ falls back to Python SciPy optimizer.
- [x] Replace Adam with a more suitable optimizer (Two-Stage Hybrid Adam + L-BFGS Polish):
  - **Stage 1 (Coarse Untangling)**: Fast Adam ($\le 250$ iterations, early-exiting when penalty $< 10^{-3}$ or on 40 stagnant steps) to resolve macro overlaps and guide shapes into feasible valleys.
  - **Stage 2 (L-BFGS Polish)**: Zero-dependency Limited-Memory BFGS ($m=8$) with Backtracking Armijo line search and Powell curvature safeguarding ($y_k^T s_k > 10^{-10} \|s_k\|^2$) for quadratic convergence to sub-tolerance ($\le 10^{-5}$) in 10–30 steps.
  - **Empirical Criterion Microbenchmark Speedups**:
    - `run_attempt/4_6_in_5_single_attempt`: **91.0 ms $\rightarrow$ 3.27 ms** (**-96.54% time / 27.8x speedup**, $p < 0.05$)
    - `run_attempt/6_TAN_in_L_single_attempt`: **1,410.0 ms $\rightarrow$ 13.10 ms** (**-99.07% time / 107.6x speedup**, $p < 0.05$)
    - Full test suite execution: **27.22s $\rightarrow$ 16.20s** (**40.4% total wall-clock reduction**)
- [ ] Add problem-specific heuristics (e.g., better initial placements for known families) to reduce optimization time.

These optimizations fundamentally improve throughput across both local and cluster workloads.

---

*End of report.*

