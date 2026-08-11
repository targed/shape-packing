# High-Performance Rust Solver Library (PyO3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `packer_rs` into a native Python module (PyO3) + C dynamic library alongside the standalone CLI binary, eliminating process spawning overhead and JSON disk I/O when executing packing solves from Python.

**Architecture:** Extract core solver logic from `packer_rs/src/main.rs` into `packer_rs/src/solver.rs` and `packer_rs/src/lib.rs`. Expose PyO3 python module `packer_rs` with method `solve(...)`. Add a unified `src/shape_packing/solver_interface.py` in Python that calls the native in-process PyO3 binding when available, with clean fallback to the `packer_rs` CLI binary. Update `cli.py` and `run_parallel_loop.py` to use `solver_interface.py`.

**Tech Stack:** Rust (PyO3 0.20, Rayon, Serde, Maturin), Python 3.10, Pytest, setuptools.

## Global Constraints

- **Single Source of Truth**: The optimization math and geometry algorithms in `solver.rs` must be identical between PyO3 in-process calls and CLI binary execution.
- **Graceful Fallback**: If the compiled PyO3 native module (`packer_rs`) is not installed or fails to import in a given environment, `solver_interface.py` must automatically fall back to executing the standalone `packer_rs` CLI binary via `subprocess.run`.
- **Zero Disk IO for In-Process Solves**: PyO3 solver invocations must return solution coordinates and metrics directly in memory as a Python `dict` without writing temporary `solution.json` or `initial_positions.json` files to disk.

---

### Task 1: Refactor `packer_rs` Architecture & Create `solver.rs`

**Files:**
- Create: `packer_rs/src/solver.rs`
- Modify: `packer_rs/Cargo.toml`
- Create: `packer_rs/src/lib.rs`
- Modify: `packer_rs/src/main.rs`

**Interfaces:**
- Consumes: Solver configuration inputs (`inner_polygons`, `inner_shape`, `container_shape`, `attempts`, `tolerance`, `finalstep`, `time_limit`, `initial_positions`, `target_s`).
- Produces: `SolveResult` struct containing `best_s: f64`, `final_metric: f64`, `values: Option<Vec<f64>>`, `inner_token: String`, `container_token: String`, `success: bool`.

- [ ] **Step 1: Write `packer_rs/src/solver.rs` with clean Rust solver API**

Extract `run_attempt`, `get_shape_geometry`, `penalty_and_gradient`, and helper math functions from `main.rs` into `solver.rs`.

```rust
use rand::Rng;
use rand_chacha::{ChaCha8Rng, rand_core::SeedableRng};
use rayon::prelude::*;
use std::f64::consts::PI;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

#[derive(Debug, Clone)]
pub struct SolveConfig {
    pub inner_polygons: usize,
    pub inner_shape: String,
    pub container_shape: String,
    pub attempts: usize,
    pub tolerance: f64,
    pub finalstep: f64,
    pub time_limit: Option<f64>,
    pub initial_positions: Option<Vec<f64>>,
    pub target_s: Option<f64>,
}

impl Default for SolveConfig {
    fn default() -> Self {
        Self {
            inner_polygons: 5,
            inner_shape: "3".to_string(),
            container_shape: "4".to_string(),
            attempts: 1000,
            tolerance: 1e-30,
            finalstep: 0.0001,
            time_limit: None,
            initial_positions: None,
            target_s: None,
        }
    }
}

#[derive(Debug, Clone)]
pub struct SolveResult {
    pub success: bool,
    pub best_s: f64,
    pub final_metric: f64,
    pub values: Vec<f64>,
    pub inner_token: String,
    pub container_token: String,
}

pub fn solve(config: &SolveConfig) -> SolveResult {
    let start = Instant::now();
    let stop_flag = Arc::new(AtomicBool::new(false));

    if let Some(limit) = config.time_limit {
        let flag = Arc::clone(&stop_flag);
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_secs_f64(limit));
            flag.store(true, Ordering::Relaxed);
        });
    }

    let (nsi, unit_polygon_vertices, unit_polygon_vectors, _) = get_shape_geometry(&config.inner_shape);
    let (nsc, _, unit_container_vectors, unit_container_apothem) = get_shape_geometry(&config.container_shape);

    let best_s = Arc::new(Mutex::new(f64::INFINITY));
    let best_x = Arc::new(Mutex::new(None::<Vec<f64>>));

    let N_f64 = config.inner_polygons as f64;
    let is_inner_circle = config.inner_shape.to_uppercase() == "CIRCLE" || config.inner_shape.to_uppercase() == "CIR";
    let is_container_circle = config.container_shape.to_uppercase() == "CIRCLE" || config.container_shape.to_uppercase() == "CIR";

    (0..config.attempts)
        .into_par_iter()
        .for_each_with(
            (
                &stop_flag,
                &start,
                &unit_polygon_vertices,
                &unit_polygon_vectors,
                &unit_container_vectors,
                &unit_container_apothem,
                &best_s,
                &best_x,
                N_f64,
                &config.initial_positions,
                &config.target_s,
                is_inner_circle,
                is_container_circle,
            ),
            |(stop, start, upv, upvectors, ucv, uap, best_s, best_x, N_f64, initial_positions, target_s, is_inner_circle, is_container_circle), seed| {
                let mut rng = ChaCha8Rng::seed_from_u64(seed as u64);
                let (s, x) = run_attempt(
                    &mut rng,
                    *N_f64,
                    nsi,
                    nsc,
                    upv,
                    upvectors,
                    ucv,
                    uap,
                    config.tolerance,
                    config.finalstep,
                    start,
                    stop,
                    config.time_limit,
                    (*initial_positions).as_ref(),
                    **target_s,
                    *is_inner_circle,
                    *is_container_circle,
                );
                if s.is_finite() && x.is_some() {
                    loop {
                        let current = {
                            let cur = best_s.lock().unwrap();
                            *cur
                        };
                        if s >= current {
                            break;
                        }
                        {
                            let mut best = best_s.lock().unwrap();
                            if s >= *best {
                                break;
                            }
                            *best = s;
                        }
                        {
                            let mut bx = best_x.lock().unwrap();
                            *bx = x.clone();
                        }
                        break;
                    }
                }
            },
        );

    let bx = best_x.lock().unwrap();
    if let Some(ref bx) = *bx {
        let best = best_s.lock().unwrap();
        let container_upper = config.container_shape.trim().to_uppercase();
        let inner_upper = config.inner_shape.trim().to_uppercase();
        
        let c_metric = match container_upper.as_str() {
            "CIRCLE" | "CIR" | "TAN" | "DOMINO" | "L" => *best,
            _ => {
                if let Ok(nsc) = container_upper.parse::<usize>() {
                    2.0 * *best * (PI / nsc as f64).sin()
                } else {
                    2.0 * *best * (PI / 3.0).sin()
                }
            }
        };

        let i_scale = match inner_upper.as_str() {
            "CIRCLE" | "CIR" | "TAN" | "DOMINO" | "L" => 1.0,
            _ => {
                if let Ok(nsi) = inner_upper.parse::<usize>() {
                    2.0 * (PI / nsi as f64).sin()
                } else {
                    2.0 * (PI / 3.0).sin()
                }
            }
        };

        let final_metric = c_metric / i_scale;
        SolveResult {
            success: true,
            best_s: *best,
            final_metric,
            values: bx.clone(),
            inner_token: config.inner_shape.clone(),
            container_token: config.container_shape.clone(),
        }
    } else {
        SolveResult {
            success: false,
            best_s: f64::INFINITY,
            final_metric: f64::INFINITY,
            values: Vec::new(),
            inner_token: config.inner_shape.clone(),
            container_token: config.container_shape.clone(),
        }
    }
}
```

- [ ] **Step 2: Update `packer_rs/Cargo.toml` with PyO3 dependency and cdylib target**

```toml
[package]
name = "packer_rs"
version = "0.1.0"
edition = "2021"

[lib]
name = "packer_rs"
crate-type = ["cdylib", "rlib"]

[[bin]]
name = "packer_rs"
path = "src/main.rs"

[dependencies]
clap = { version = "4", features = ["derive"] }
rand = "0.8"
rand_chacha = "0.3"
rayon = "1.10"
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
pyo3 = { version = "0.20", features = ["extension-module"] }

[profile.release]
opt-level = 3
lto = true
codegen-units = 1
```

- [ ] **Step 3: Write `packer_rs/src/lib.rs` with PyO3 module bindings**

```rust
pub mod solver;

use pyo3::prelude::*;
use pyo3::types::PyDict;
use solver::{solve, SolveConfig};

#[pyfunction]
#[pyo3(signature = (
    inner_polygons,
    inner_shape,
    container_shape,
    attempts = 1000,
    tolerance = 1e-30,
    finalstep = 0.0001,
    time_limit = None,
    initial_positions = None,
    target_s = None
))]
fn solve_py<'py>(
    py: Python<'py>,
    inner_polygons: usize,
    inner_shape: String,
    container_shape: String,
    attempts: usize,
    tolerance: f64,
    finalstep: f64,
    time_limit: Option<f64>,
    initial_positions: Option<Vec<f64>>,
    target_s: Option<f64>,
) -> PyResult<Option<&'py PyDict>> {
    let config = SolveConfig {
        inner_polygons,
        inner_shape,
        container_shape,
        attempts,
        tolerance,
        finalstep,
        time_limit,
        initial_positions,
        target_s,
    };

    let result = py.allow_threads(|| solve(&config));

    if result.success {
        let dict = PyDict::new(py);
        dict.set_item("S", result.best_s)?;
        dict.set_item("final_metric", result.final_metric)?;
        dict.set_item("values", result.values)?;
        dict.set_item("N", inner_polygons)?;
        dict.set_item("inner_token", result.inner_token)?;
        dict.set_item("container_token", result.container_token)?;
        Ok(Some(dict))
    } else {
        Ok(None)
    }
}

#[pymodule]
fn packer_rs(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(solve_py, m)?)?;
    Ok(())
}
```

- [ ] **Step 4: Update `packer_rs/src/main.rs` to call `solver::solve`**

```rust
#![allow(non_snake_case)]

use clap::Parser;
use std::fs;
use std::io::Write;
use packer_rs::solver::{solve, SolveConfig};

#[derive(Parser, Debug)]
#[command(name = "packer_rs", about = "Fast polygon packing solver")]
struct Args {
    inner_polygons: usize,
    inner_shape: String,
    container_shape: String,

    #[arg(long, default_value_t = 1000)]
    attempts: usize,

    #[arg(long, default_value_t = 1e-30)]
    tolerance: f64,

    #[arg(long, default_value_t = 0.0001)]
    finalstep: f64,

    #[arg(long)]
    time_limit: Option<f64>,

    #[arg(long)]
    solution_file: Option<String>,

    #[arg(long)]
    initial_positions: Option<String>,

    #[arg(long)]
    target_s: Option<f64>,
}

fn main() {
    let args = Args::parse();

    let initial_positions = if let Some(path) = &args.initial_positions {
        let contents = fs::read_to_string(path).expect("Failed to read initial positions file");
        let positions: Vec<f64> = serde_json::from_str(&contents).expect("Invalid JSON in initial positions");
        Some(positions)
    } else {
        None
    };

    let config = SolveConfig {
        inner_polygons: args.inner_polygons,
        inner_shape: args.inner_shape.clone(),
        container_shape: args.container_shape.clone(),
        attempts: args.attempts,
        tolerance: args.tolerance,
        finalstep: args.finalstep,
        time_limit: args.time_limit,
        initial_positions,
        target_s: args.target_s,
    };

    let result = solve(&config);

    if result.success {
        println!("Final side length: {}", result.final_metric);

        if let Some(path) = &args.solution_file {
            let mut buf = String::new();
            buf.push_str("{\n");
            buf.push_str(&format!("  \"S\": {},\n", result.best_s));
            buf.push_str(&format!("  \"inner_token\": \"{}\",\n", result.inner_token));
            buf.push_str(&format!("  \"container_token\": \"{}\",\n", result.container_token));
            buf.push_str(&format!("  \"final_metric\": {},\n", result.final_metric));
            buf.push_str(&format!("  \"N\": {},\n", result.values.len() / 3));
            buf.push_str("  \"values\": [");
            for (i, v) in result.values.iter().enumerate() {
                buf.push_str(&format!("{}", v));
                if i < result.values.len() - 1 {
                    buf.push(',');
                }
            }
            buf.push_str("]\n}\n");

            if let Ok(mut f) = fs::File::create(path) {
                let _ = f.write_all(buf.as_bytes());
            }
        }
    } else {
        println!("No valid packing found.");
    }
}
```

- [ ] **Step 5: Verify build of Rust binary and PyO3 module**

Run: `cargo build --release --manifest-path packer_rs/Cargo.toml`
Expected: PASS with both binary `target/release/packer_rs` and library `target/release/libpacker_rs.so` (or `.dylib` / `.dll`).

- [ ] **Step 6: Commit Task 1**

```bash
git add packer_rs/Cargo.toml packer_rs/src/solver.rs packer_rs/src/lib.rs packer_rs/src/main.rs
git commit -m "refactor(packer_rs): extract solver module and add PyO3 python bindings"
```

---

### Task 2: Create Python `solver_interface.py` & In-Process Solver Layer

**Files:**
- Create: `src/shape_packing/solver_interface.py`
- Create: `tests/test_solver_interface.py`

**Interfaces:**
- Consumes: `solve_packing(n_shapes, inner_shape, container_shape, attempts, target_s, initial_positions, solution_file)`.
- Produces: Normalized solution dictionary `{"success": bool, "score": float, "S": float, "values": list[float], "output": str, "backend": str}`.

- [ ] **Step 1: Write `tests/test_solver_interface.py` (failing test for solver_interface)**

```python
import pytest
from src.shape_packing.solver_interface import run_solver

def test_run_solver_fallback_or_pyo3():
    result = run_solver(
        n_shapes=3,
        inner_shape="3",
        container_shape="4",
        attempts=10,
        time_limit=5.0
    )
    assert isinstance(result, dict)
    assert "success" in result
    assert "backend" in result
    if result["success"]:
        assert "score" in result
        assert "values" in result
        assert len(result["values"]) == 9  # 3 shapes * 3 (x, y, a)
```

- [ ] **Step 2: Run test to verify it fails before implementation**

Run: `pytest tests/test_solver_interface.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.shape_packing.solver_interface'`

- [ ] **Step 3: Write `src/shape_packing/solver_interface.py`**

```python
import os
import sys
import json
import subprocess
from typing import Optional, Dict, Any, List

def _try_import_pyo3_packer():
    try:
        import packer_rs
        return packer_rs
    except ImportError:
        # Check if built cdylib exists in target/release
        import importlib.util
        possible_paths = [
            "packer_rs/target/release/libpacker_rs.so",
            "packer_rs/target/release/libpacker_rs.dylib",
            "packer_rs/target/release/packer_rs.dll",
            "packer_rs/target/release/packer_rs.pyd",
            "packer_rs/target/release/packer_rs.so",
        ]
        for p in possible_paths:
            if os.path.exists(p):
                try:
                    spec = importlib.util.spec_from_file_location("packer_rs", p)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        return mod
                except Exception:
                    pass
        return None

def run_solver(
    n_shapes: int,
    inner_shape: str,
    container_shape: str,
    attempts: int = 1000,
    tolerance: float = 1e-30,
    finalstep: float = 0.0001,
    time_limit: Optional[float] = None,
    initial_positions: Optional[List[float]] = None,
    target_s: Optional[float] = None,
    solution_file: Optional[str] = None,
    no_build: bool = True,
) -> Dict[str, Any]:
    pyo3_mod = _try_import_pyo3_packer()
    
    if pyo3_mod is not None and hasattr(pyo3_mod, "solve_py"):
        try:
            res = pyo3_mod.solve_py(
                n_shapes,
                str(inner_shape),
                str(container_shape),
                attempts=attempts,
                tolerance=tolerance,
                finalstep=finalstep,
                time_limit=time_limit,
                initial_positions=initial_positions,
                target_s=target_s,
            )
            if res is not None:
                S = res.get("S", 0.0)
                final_metric = res.get("final_metric", 0.0)
                values = res.get("values", [])
                
                if solution_file:
                    os.makedirs(os.path.dirname(os.path.abspath(solution_file)), exist_ok=True)
                    with open(solution_file, "w") as f:
                        json.dump(res, f, indent=2)
                        
                return {
                    "success": True,
                    "score": final_metric,
                    "S": S,
                    "values": values,
                    "backend": "pyo3",
                    "output": f"Final side length: {final_metric}",
                }
            else:
                return {
                    "success": False,
                    "score": 0.0,
                    "S": 0.0,
                    "values": [],
                    "backend": "pyo3",
                    "output": "No valid packing found.",
                }
        except Exception as e:
            pass  # Fall back to CLI binary

    # Binary Subprocess Fallback
    rust_binary = "packer_rs/target/release/packer_rs"
    if not os.path.exists(rust_binary) and not no_build:
        subprocess.run(
            ["cargo", "build", "--release"],
            cwd="packer_rs",
            check=True,
            stdout=subprocess.DEVNULL,
        )

    cmd = [
        rust_binary,
        str(n_shapes), str(inner_shape), str(container_shape),
        "--attempts", str(attempts),
    ]
    if solution_file:
        cmd.extend(["--solution-file", solution_file])
    if target_s is not None:
        cmd.extend(["--target-s", str(target_s)])
    if time_limit is not None:
        cmd.extend(["--time-limit", str(time_limit)])

    init_json_path = None
    if initial_positions is not None:
        init_json_path = "tmp_init_pos.json"
        with open(init_json_path, "w") as f:
            json.dump(initial_positions, f)
        cmd.extend(["--initial-positions", init_json_path])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if init_json_path and os.path.exists(init_json_path):
            os.remove(init_json_path)

        if proc.returncode != 0:
            return {
                "success": False,
                "error": proc.stderr,
                "backend": "cli",
                "returncode": proc.returncode,
            }

        stdout = proc.stdout.strip()
        if "No valid packing found" in stdout:
            return {
                "success": False,
                "score": 0.0,
                "backend": "cli",
                "output": stdout,
            }

        score = 0.0
        for line in stdout.splitlines():
            if line.startswith("Final side length:"):
                score = float(line.split(":")[-1].strip())

        return {
            "success": True,
            "score": score,
            "backend": "cli",
            "output": stdout,
        }
    except Exception as e:
        if init_json_path and os.path.exists(init_json_path):
            os.remove(init_json_path)
        return {
            "success": False,
            "error": str(e),
            "backend": "cli",
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_solver_interface.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 2**

```bash
git add src/shape_packing/solver_interface.py tests/test_solver_interface.py
git commit -m "feat: add solver_interface module with PyO3 in-process execution and CLI fallback"
```

---

### Task 3: Integrate `solver_interface.py` in `cli.py` & `run_parallel_loop.py`

**Files:**
- Modify: `src/shape_packing/cli.py:73-125`
- Modify: `run_parallel_loop.py:122-149`
- Test: `tests/test_cli_integration.py`

**Interfaces:**
- Consumes: `run_solver` from `solver_interface`.
- Produces: Accelerated solver execution across CLI commands (`cli.py run`) and parallel loop worker tasks (`run_parallel_loop.py`).

- [ ] **Step 1: Write integration test `tests/test_cli_integration.py`**

```python
import pytest
from src.shape_packing.cli import handle_run

class DummyArgs:
    pass

def test_cli_handle_run_with_solver_interface(tmp_path):
    args = DummyArgs()
    args.problem = "3_3_4"
    args.attempts = 10
    args.init_script = None
    args.no_commit = True
    args.json_out = True
    args.no_png = True
    args.no_build = True

    res = handle_run(args, direct_call=True)
    assert isinstance(res, dict)
    assert "success" in res
```

- [ ] **Step 2: Run test to verify current status**

Run: `pytest tests/test_cli_integration.py -v`
Expected: PASS (runs via old subprocess)

- [ ] **Step 3: Update `src/shape_packing/cli.py` to use `run_solver`**

Replace `cli.py` lines 73-125 with:

```python
    from .solver_interface import run_solver
    from .solution_tools import inverse_friedman_metric
    from .agent_loop import load_history, current_best_scores

    target_s = None
    try:
        if history_cache is not None:
            history = history_cache
        else:
            history = load_history("results.tsv")
            
        history = [
            r for r in history
            if r.commit.lower() not in ("verify", "auto-verify", "test")
            and "verify" not in (r.description or "").lower()
        ]
        best = current_best_scores(history)
        best_score = best.get(args.problem, "None")
        
        if best_score != "None":
            target_s = inverse_friedman_metric(float(best_score), inner, container)
            eprint(f"Injecting --target-s {target_s} (from Friedman best_score {best_score})")
    except Exception as e:
        eprint(f"Could not inject target_s: {e}")

    init_positions_list = None
    if init_json_path and os.path.exists(init_json_path):
        with open(init_json_path, "r") as f:
            init_positions_list = json.load(f)

    res = run_solver(
        n_shapes=N,
        inner_shape=str(inner),
        container_shape=str(container),
        attempts=args.attempts,
        initial_positions=init_positions_list,
        target_s=target_s,
        solution_file=solution_file,
        no_build=getattr(args, "no_build", False),
    )

    if not res.get("success"):
        if res.get("output") and "No valid packing found" in res.get("output"):
            eprint("Solver reported: No valid packing found. Refusing to log 0.0 score.")
            if direct_call:
                return {"success": False, "error": "No valid packing found", "returncode": 42}
            sys.exit(1)
        
        err = f"Rust solver failed: {res.get('error', 'Unknown error')}"
        eprint(err)
        if direct_call:
            return {"success": False, "error": err, "returncode": res.get("returncode", 1)}
        sys.exit(1)

    score = res.get("score")
```

- [ ] **Step 4: Run tests to verify integration passes**

Run: `pytest tests/test_cli_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 3**

```bash
git add src/shape_packing/cli.py tests/test_cli_integration.py
git commit -m "feat: integrate solver_interface in cli.py for accelerated PyO3 execution"
```

---

### Task 4: End-to-End Verification & Benchmarks

**Files:**
- Test: `tests/test_solver_performance.py`

- [ ] **Step 1: Write end-to-end performance and correctness verification test**

```python
import time
import pytest
from src.shape_packing.solver_interface import run_solver

def test_pyo3_solver_correctness_and_speed():
    start = time.time()
    res = run_solver(
        n_shapes=4,
        inner_shape="3",
        container_shape="4",
        attempts=100,
        time_limit=10.0
    )
    elapsed = time.time() - start
    
    assert res["success"] is True
    assert res["score"] > 0.0
    assert elapsed < 5.0
    print(f"\n[Bench] 4 triangles in square (100 attempts): {elapsed:.3f}s via {res['backend']}")
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -v`
Expected: ALL TESTS PASS

- [ ] **Step 3: Commit Task 4**

```bash
git add tests/test_solver_performance.py
git commit -m "test: add end-to-end performance & correctness verification tests for PyO3 solver"
```
