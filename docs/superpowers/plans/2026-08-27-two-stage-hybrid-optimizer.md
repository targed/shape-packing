# Two-Stage Hybrid Optimizer (Adam + L-BFGS Polish) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accelerate the native Rust solver (`packer_rs`) by replacing the slow 3,000-iteration pure Adam optimizer with a high-performance Two-Stage Hybrid optimizer (Coarse Adam untangling followed by L-BFGS quasi-Newton polishing with Armijo line search and curvature safeguarding).

**Architecture:** 
- Stage 1: Fast Adam untangling (up to 250 iterations or until penalty is coarse $<10^{-2}$) to quickly resolve macroscopic overlaps and guide random shapes into packing pockets.
- Stage 2: Zero-dependency Limited-Memory BFGS (L-BFGS with history $m=8$) with Backtracking Armijo line search and Powell curvature damping to rapidly achieve quadratic convergence down to sub-tolerance ($\le 10^{-5}$).
- Benchmark comparison before and after via Criterion.rs (`cargo bench`).

**Tech Stack:** Rust (edition 2021), Criterion 0.5 (`plotters` backend), PyO3 0.22, Python pytest test suite.

## Global Constraints

- Must retain zero external solver dependencies in `packer_rs` (no heavy matrix/linear algebra crates).
- Must maintain identical PyO3 and CLI API signatures in `solver.rs` and `lib.rs`.
- Must pass all 318 tests in `pytest tests/` with zero regressions.
- Must verify performance improvement using `cargo bench` baseline comparison.

---

### Task 1: Implement Zero-Dependency L-BFGS Polish Module in Rust

**Files:**
- Modify: `packer_rs/src/solver.rs`
- Test: `packer_rs/tests/solver_tests.rs` (or inline unit test in `packer_rs/src/solver.rs`)

**Interfaces:**
- Produces: `fn minimize_lbfgs(...) -> OptResult` and `fn minimize_hybrid(...) -> OptResult`.
- Consumes: `penalty_and_gradient(...)` from `packer_rs/src/solver.rs`.

- [ ] **Step 1: Write unit tests for L-BFGS two-loop recursion and Armijo line search on convex quadratics and shape packing**

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hybrid_optimizer_convergence() {
        let (nsi, upv, upvectors, _) = get_shape_geometry("6");
        let (nsc, _, ucv, uap) = get_shape_geometry("5");
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let start = Instant::now();
        let stop_flag = AtomicBool::new(false);

        let result = run_attempt(
            &mut rng,
            3.5, // Feasible container scale for N=4 hexagons in pentagon
            nsi,
            nsc,
            &upv,
            &upvectors,
            &ucv,
            &uap,
            1e-5,
            0.001,
            &start,
            &stop_flag,
            Some(5.0),
            None,
            None,
            false,
            false,
            false,
            false,
        );

        assert!(result.is_some(), "Hybrid optimizer must find valid packing for 4_6_in_5 at S=3.5");
        let (final_s, _sol) = result.unwrap();
        assert!(final_s < 3.5, "Final scale S should be shrunk and feasible");
    }
}
```

- [ ] **Step 2: Run cargo test to verify test compiles and runs**

Run: `cargo test --lib -p packer_rs`
Expected: Passes or tests existing logic.

- [ ] **Step 3: Implement L-BFGS two-loop recursion and Backtracking Armijo Line Search in `packer_rs/src/solver.rs`**

```rust
struct LbfgsHistory {
    m: usize,
    s_history: Vec<Vec<f64>>,
    y_history: Vec<Vec<f64>>,
    rho_history: Vec<f64>,
}

impl LbfgsHistory {
    fn new(m: usize, n: usize) -> Self {
        Self {
            m,
            s_history: Vec::with_capacity(m),
            y_history: Vec::with_capacity(m),
            rho_history: Vec::with_capacity(m),
        }
    }

    fn push(&mut self, s: Vec<f64>, y: Vec<f64>) {
        let ys: f64 = s.iter().zip(y.iter()).map(|(a, b)| a * b).sum();
        let s_norm_sq: f64 = s.iter().map(|a| a * a).sum();
        // Curvature safeguard (Powell damping / positive definiteness condition)
        if ys > 1e-10 * s_norm_sq {
            if self.s_history.len() == self.m {
                self.s_history.remove(0);
                self.y_history.remove(0);
                self.rho_history.remove(0);
            }
            let rho = 1.0 / ys;
            self.s_history.push(s);
            self.y_history.push(y);
            self.rho_history.push(rho);
        }
    }

    fn compute_direction(&self, grad: &[f64]) -> Vec<f64> {
        let k = self.s_history.len();
        let n = grad.len();
        if k == 0 {
            return grad.iter().map(|g| -g).collect();
        }

        let mut q = grad.to_vec();
        let mut alphas = vec![0.0f64; k];

        // First loop (backward)
        for i in (0..k).rev() {
            let s = &self.s_history[i];
            let y = &self.y_history[i];
            let rho = self.rho_history[i];

            let sq: f64 = s.iter().zip(q.iter()).map(|(a, b)| a * b).sum();
            let alpha = rho * sq;
            alphas[i] = alpha;

            for j in 0..n {
                q[j] -= alpha * y[j];
            }
        }

        // Initial Hessian scaling H0 = (s_last . y_last) / (y_last . y_last) * I
        let s_last = &self.s_history[k - 1];
        let y_last = &self.y_history[k - 1];
        let sy: f64 = s_last.iter().zip(y_last.iter()).map(|(a, b)| a * b).sum();
        let yy: f64 = y_last.iter().map(|a| a * a).sum();
        let gamma = if yy > 1e-12 { sy / yy } else { 1.0 };

        let mut r: Vec<f64> = q.iter().map(|qi| gamma * qi).collect();

        // Second loop (forward)
        for i in 0..k {
            let s = &self.s_history[i];
            let y = &self.y_history[i];
            let rho = self.rho_history[i];

            let yr: f64 = y.iter().zip(r.iter()).map(|(a, b)| a * b).sum();
            let beta = rho * yr;

            for j in 0..n {
                r[j] += s[j] * (alphas[i] - beta);
            }
        }

        r.iter().map(|ri| -ri).collect()
    }
}
```

- [ ] **Step 4: Implement Two-Stage `minimize_gradient` in `packer_rs/src/solver.rs`**
  - Stage 1: Run Adam for up to 200 iterations (or until $f(x) < 10^{-2}$ or 40 non-improving steps).
  - Stage 2: Run L-BFGS with Armijo line search ($c_1 = 10^{-4}, \rho = 0.5$) for up to 60 iterations (or until $f(x) < \text{tol}$ or $\|\nabla f\| < 10^{-6}$).

- [ ] **Step 5: Run tests and verify compilation**

Run: `cargo test --release -p packer_rs`
Expected: PASS

- [ ] **Step 6: Commit Stage 1 & 2 Optimizer Implementation**

```bash
git add packer_rs/src/solver.rs
git commit -m "feat(solver): implement two-stage hybrid Adam + L-BFGS optimizer"
```

---

### Task 2: Verify Python Integration & Full Pytest Suite

**Files:**
- Modify: `packer_rs/src/lib.rs` (if any signature needs updating, otherwise build .pyd)
- Test: `tests/`

- [ ] **Step 1: Build release `.dll` and update `packer_rs.pyd`**

Run: `cd packer_rs && cargo build --release && cp target/release/packer_rs.dll target/release/packer_rs.pyd && cd ..`
Expected: Build succeeds with 0 errors.

- [ ] **Step 2: Run full automated pytest test suite**

Run: `python -m pytest tests/`
Expected: **318 / 318 passed**.

- [ ] **Step 3: Mathematically verify standard and non-convex solutions via CLI**

Run: `python -m src.shape_packing.cli run --problem 4_6_in_5 --attempts 10 --time-limit 5.0`
Expected: Finds feasible solution and verifies successfully.

---

### Task 3: Benchmark Comparison via Criterion (`cargo bench`)

**Files:**
- Benchmark: `packer_rs/benches/solver_benchmarks.rs`
- Documentation: `docs/performance-report.md`

- [ ] **Step 1: Run `cargo bench` to benchmark before/after speedup**

Run: `cd packer_rs && cargo bench && cd ..`
Expected: Criterion reports statistical percentage changes across `run_attempt/4_6_in_5_single_attempt` and `run_attempt/6_TAN_in_L_single_attempt`.

- [ ] **Step 2: Record new performance benchmarks in `docs/performance-report.md`**
  - Update Section 4.3 with the new hybrid optimizer benchmark times and speedup factors.

- [ ] **Step 3: Commit benchmark results and performance report**

```bash
git add docs/performance-report.md packer_rs/
git commit -m "perf(solver): benchmark two-stage hybrid optimizer speedup in performance report"
```

---

## Verification Plan

### Automated Tests
- `cargo test --release -p packer_rs`: Verify Rust internal unit and regression tests.
- `python -m pytest tests/`: Full regression test suite covering all 318 tests.
- `cargo bench`: Criterion benchmark comparisons showing statistical speedup.

### Manual / CLI Verification
- Run `python -m src.shape_packing.cli run --problem 6_TAN_in_L --attempts 20` to verify non-convex obstacle packing.
- Run `python -m src.shape_packing.cli verify <solution_path>` to ensure geometric validity.
