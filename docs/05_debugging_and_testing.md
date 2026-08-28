# Debugging, Testing & Solution Verification

This document details the **Systematic Debugging Workflow**, solution verification engine (`verify_solution`), physical area bound checks, pytest test suite guidelines, and test coverage policy.

---

## 1. Systematic Debugging Protocol

When encountering unexpected behavior, solver crashes, or invalid metric scores, follow the **Systematic Debugging Workflow**:

```text
 ┌──────────────────────────┐
 │ 1. Read Raw Log Evidence │ (Do NOT guess - inspect full stack trace)
 └────────────┬─────────────┘
              │
              ▼
 ┌──────────────────────────┐
 │ 2. Reproduce Locally     │ (Run isolated CLI command)
 └────────────┬─────────────┘
              │
              ▼
 ┌──────────────────────────┐
 │ 3. Identify Root Cause   │ (SAT overlap vs boundary normal vs metric formula)
 └────────────┬─────────────┘
              │
              ▼
 ┌──────────────────────────┐
 │ 4. Fix & Verify          │ (Run pytest & verify_solution)
 └──────────────────────────┘
```

### Common Root Causes & Diagnostics

1. **Solver Returns Score 0.0 Immediately ("No valid packing found")**:
   - *Cause*: Injected `--target-s` is physically impossible due to a corrupt legacy score in `results.tsv`.
   - *Fix*: Clean corrupt rows from `results.tsv` using `is_physically_valid_score()`.

2. **Shapes Massively Overlapping or Stale Solver Logic Active**:
   - *Cause*: Python loaded a stale `.pyd` compiled weeks ago instead of the freshly built `.dll`.
   - *Fix*: Ensure `default = ["python"]` in `packer_rs/Cargo.toml` and use `solver_interface.py`'s automatic `mtime`-based newest binary sorting.

3. **Shapes Squeezed into Top-Left Corner of L-Containers**:
   - *Cause*: Applying linear half-plane intersection to non-convex containers chops off reflex arms.
   - *Fix*: Treat non-convex containers as an outer bounding box with a fixed reflex cut-out obstacle ($R_{\text{cutout}}$) checked via SAT.

4. **Shapes Extend Outside Boundary in Visualizer**:
   - *Cause*: `container_sides` token was unparsed or missing, causing visualizer to fallback to a 3-sided polygon.
   - *Fix*: Ensure `parseSides()` or `get_shape_geometry()` parses container token (`circle` $\rightarrow 32$, `L` $\rightarrow 6$).

5. **Metric Discrepancy between JSON and Verification**:
   - *Cause*: Using raw container scale $S$ instead of converted Friedman metric $s$.
   - *Fix*: Always verify with `compute_friedman_metric(S, inner_token, container_token)`.

6. **Sub-Precision Record Churn**:
   - *Cause*: Reusing geometric SAT tolerance as the record-beating threshold.
   - *Fix*: Decouple into `RECORD_MIN_IMPROVEMENT` ($10^{-5}$) in `packing_config.py`.

---

## 2. Solution Verification Engine (`solution_tools.py`)

Every generated solution is verified by `verify_solution(sol_path)` using 5 strict criteria:

```text
┌───────────────────────────┬────────────────────────────────────────────────────────┐
│ Verification Step         │ Condition Checked                                      │
├───────────────────────────┼────────────────────────────────────────────────────────┤
│ 1. Metric Consistency     │ |calc_metric - sol.final_metric| < 1e-6                │
│ 2. Container Bounds       │ Convex: v · n <= S | Non-Convex (L): BoundingBox &     │
│                           │ zero SAT overlap with reflex cut-out obstacle          │
│ 3. Overlap Check (SAT)    │ Compound SAT penetration depth <= 1e-5 across all pairs│
│ 4. Physical Area Check    │ N * Area(inner) <= Area(container)                     │
│ 5. Record Validation      │ calc_metric < best_known - 1e-5 (RECORD_MIN_IMPROVEMENT)│
└───────────────────────────┴────────────────────────────────────────────────────────┘
```

### Running Verification via CLI

To verify a single `solution.json`:

```bash
python -m src.shape_packing.cli verify results/4_6_in_5/20260801_191843/solution.json
```

Output:
```text
[PASS] Valid configuration, metric s=3.021926200073330
```

---

## 3. Test Suite & Coverage Policy

The test suite resides in `tests/` and is run using `pytest`:

```bash
python -m pytest tests/
```

### Test Organization

- **`test_agent_loop.py`**: Tests history loading, score tracking, problem choice, and loop candidate generation.
- **`test_build_site_data.py`**: Tests `site_data.json` aggregation, family slug normalization, and status counts.
- **`test_geometry.py` & `test_geometry_coverage.py`**: Tests polygon generation, transformations, SAT collision math, and Numba acceleration.
- **`test_solution_tools.py`**: Tests solution loading, metric conversion, and verification logic.
- **`test_problems.py`**: Tests problem key parsing.

### Coverage Guidelines

1. **God Modules**: `geometry.py`, `optimization.py`, `problems.py`, `agent_loop.py`, and `solution_tools.py` should maintain $>90\%$ line coverage.
2. **Never Ignore Test Failures**: Fix underlying contracts instead of commenting out assertions or adding silent fallback wrappers.

---

## 4. Criterion Microbenchmarking & Performance Testing

The native Rust solver includes a statistical microbenchmarking suite built on **Criterion.rs** to measure nanosecond execution times and prevent performance regressions in hot loops.

### Running Benchmarks

```bash
# Navigate to Rust crate directory:
cd packer_rs

# Run full microbenchmark suite:
cargo bench

# Run a specific benchmark group:
cargo bench --bench solver_benchmarks -- penalty_and_gradient
cargo bench --bench solver_benchmarks -- run_attempt
```

### Benchmark Cases & Scopes

| Benchmark Case | Scope / Geometry Tested | Target Execution Time |
| :--- | :--- | :--- |
| **`penalty_and_gradient/4_6_in_5_with_grad`** | $N=4$ Regular Polygons (Hexagon in Pentagon) | ~`1.1 µs` (1,100 ns) |
| **`penalty_and_gradient/6_TAN_in_L_container`** | Non-convex L-container reflex cut-out obstacle SAT | ~`1.2 µs` |
| **`penalty_and_gradient/6_L_in_4_compound_sat`** | Non-Convex L-Tromino ($2 \times 2$ compound sub-parts) | ~`1.6 µs` |
| **`penalty_and_gradient/12_3_in_circle_with_grad`**| Circle Container (32 inner normal projections) | ~`2.0 µs` |
| **`penalty_and_gradient/25_4_in_4_broadphase`** | Sweep & Prune Spatial Broadphase ($N=25$, 300 pairs) | ~`7.7 µs` |
| **`run_attempt/4_6_in_5_single_attempt`** | Full multi-start attempt convergence on polygon (Hybrid) | ~`3.2–3.3 ms` (28x speedup) |
| **`run_attempt/6_TAN_in_L_single_attempt`** | Full multi-start attempt on non-convex container (Hybrid) | ~`13.0–13.2 ms` (107x speedup) |

### Interpreting Benchmark Output

When running `cargo bench`, Criterion outputs statistical metrics:

```text
penalty_and_gradient/4_6_in_5_with_grad
                        time:   [1.0911 µs 1.0950 µs 1.0992 µs]
                        change: [-3.1199% -2.0658% -1.1287%] (p = 0.00 < 0.05)
                        Performance has improved.
Found 2 outliers among 100 measurements (2.00%)
  2 (2.00%) high mild
```

1. **Time Triplet `[Lower Bound, Median Estimate, Upper Bound]`**:
   - Criterion runs thousands of iterations across 100 sample batches, using bootstrap resampling to compute a **95% confidence interval**.
   - `1.0911 µs` is the lower bound, `1.0950 µs` is the point estimate (median), and `1.0992 µs` is the upper bound.
2. **Performance Change & Statistical Significance (`change: [...] (p = ...)` )**:
   - Compares the current run against the saved baseline in `target/criterion/.../base/`.
   - `p = 0.00 < 0.05`: The two-tailed hypothesis test confirms the speedup/slowdown is statistically significant and not background OS noise.
3. **Outlier Detection (Tukey's Box Plot)**:
   - Identifies samples distorted by OS context switches or thread scheduling, reporting mild ($1.5 \times \text{IQR}$) and severe ($3.0 \times \text{IQR}$) outliers.

### Visual HTML Reports

Criterion generates visual SVG charts and regression graphs at:
- **`packer_rs/target/criterion/report/index.html`**

Open this file in any web browser to view probability density functions (PDF), iteration vs time scatter plots, and violin distribution charts.
