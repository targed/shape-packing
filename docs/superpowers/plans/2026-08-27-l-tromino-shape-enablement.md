# Non-Convex L-Tromino (`L`) Shape Enablement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fully implement and enable the non-convex `L` (L-tromino) shape across the geometry engine, SAT optimization solver (Python and Rust), solution verification, and agent loop problem selector.

**Architecture:** Use 2-rectangle convex decomposition ($1 \times 2$ vertical domino + $1 \times 1$ square) for L-tromino pairwise collision. Support container bounds checking against outer 6 vertices for `L_in_container` and corner obstacle cutout for `inner_in_L`. Unblock `"L"` in the autonomous agent loop and verify with unit/integration tests.

**Tech Stack:** Python 3.14, NumPy, Numba, Pytest, Rust (`packer_rs`)

## Global Constraints

- L-tromino center of mass at origin $(0, 0)$.
- Unit L-tromino: 3 unit squares, Area $= 3.0$.
- Metric scaling: `c_metric = S` when container is L; `i_scale = 1.0` when inner shape is L.
- Zero performance or mathematical regressions on existing convex shapes (`3`, `4`, `5`, `6`, `8`, `CIRCLE`, `DOMINO`, `TAN`).

---

### Task 1: Geometry & 2-Rectangle Convex Decomposition in `geometry.py`

**Files:**
- Modify: `src/shape_packing/geometry.py:70-110`
- Test: `tests/test_geometry.py`

**Interfaces:**
- `get_shape_geometry(token: str)` -> `(sides: int, vertices: np.ndarray, vectors: np.ndarray, edge_radii: np.ndarray)`
- `get_shape_convex_parts(token: str)` -> `List[Tuple[np.ndarray, np.ndarray]]` (returns list of `(vertices, outward_normals)` for each convex decomposition component)

- [ ] **Step 1: Write the failing test in `tests/test_geometry.py`**
```python
def test_l_tromino_geometry_and_convex_parts():
    from src.shape_packing.geometry import get_shape_geometry, get_shape_convex_parts
    sides, verts, vecs, radii = get_shape_geometry("L")
    assert sides == 6
    assert verts.shape == (6, 2)
    # Verify center of mass at origin
    assert abs(np.mean(verts[:, 0])) < 1e-6
    assert abs(np.mean(verts[:, 1])) < 1e-6
    
    parts = get_shape_convex_parts("L")
    assert len(parts) == 2  # 2 convex rectangles
    rect_a_verts, rect_a_normals = parts[0]
    rect_b_verts, rect_b_normals = parts[1]
    assert rect_a_verts.shape == (4, 2)
    assert rect_b_verts.shape == (4, 2)
```

- [ ] **Step 2: Run test to confirm failure**
```bash
python -m pytest tests/test_geometry.py -k test_l_tromino_geometry_and_convex_parts
```

- [ ] **Step 3: Implement L-tromino geometry and `get_shape_convex_parts()` in `src/shape_packing/geometry.py`**
Define canonical 6 outer vertices and the 2 convex sub-rectangles ($[-5/6, 1/6] \times [-5/6, 7/6]$ and $[1/6, 7/6] \times [-5/6, 1/6]$).

- [ ] **Step 4: Run test to confirm it passes**
```bash
python -m pytest tests/test_geometry.py -k test_l_tromino_geometry_and_convex_parts
```

- [ ] **Step 5: Commit Task 1**
```bash
git add src/shape_packing/geometry.py tests/test_geometry.py
git commit -m "feat(geometry): add L-tromino canonical coordinates and 2-rectangle convex decomposition"
```

---

### Task 2: Rust Solver (`packer_rs`) Multi-Part SAT & L-Tromino Support

**Files:**
- Modify: `packer_rs/src/solver.rs:200-350`
- Test: `tests/test_solver_interface.py`

**Interfaces:**
- `get_shape_geometry(token: &str)` in Rust returning decomposition parts for `"L"`.
- `penalty_and_gradient()` evaluating sub-part rectangle SAT for compound shapes.

- [ ] **Step 1: Write test for L-tromino solving in `tests/test_solver_interface.py`**
```python
def test_run_solver_l_tromino(tmp_path):
    sol_file = str(tmp_path / "l_sol.json")
    result = run_solver(
        n_shapes=1,
        inner_shape="L",
        container_shape="4",
        attempts=20,
        time_limit=5.0,
        solution_file=sol_file,
    )
    assert isinstance(result, dict)
    assert "success" in result
    if result["success"]:
        assert result["score"] > 0
        assert len(result["values"]) == 3
```

- [ ] **Step 2: Update `packer_rs/src/solver.rs` with L-tromino geometry and composite SAT collision**
- [ ] **Step 3: Compile Rust release binary with `cargo build --release`**
- [ ] **Step 4: Run test to confirm pass**
```bash
python -m pytest tests/test_solver_interface.py -k test_run_solver_l_tromino
```

- [ ] **Step 5: Commit Task 2**
```bash
git add packer_rs/src/solver.rs tests/test_solver_interface.py
git commit -m "feat(solver): implement compound SAT and L-tromino solving in packer_rs"
```

---

### Task 3: Solution Verification, Exporter, and Agent Loop Unblocking

**Files:**
- Modify: `src/shape_packing/solution_tools.py:150-450`
- Modify: `src/shape_packing/agent_loop.py:215-430`
- Test: `tests/test_solution_tools.py`
- Test: `tests/test_agent_loop.py`
- Test: `tests/test_cli_integration.py`

**Interfaces:**
- `build_polygons()` generates 6-vertex L-polygons.
- `_verify_overlap()` evaluates composite rectangular SAT for L inner shapes.
- `_is_shape_unsupported("L")` returns `False`.
- `_get_inner_shape_area("L")` returns `3.0`.
- `_get_container_shape_area(s, "L")` returns `3.0 * s**2`.

- [ ] **Step 1: Write tests in `tests/test_solution_tools.py` and `tests/test_agent_loop.py`**
- [ ] **Step 2: Implement L verification in `solution_tools.py` and unblock L in `agent_loop.py`**
- [ ] **Step 3: Run pytest on updated modules**
```bash
python -m pytest tests/test_solution_tools.py tests/test_agent_loop.py tests/test_cli_integration.py
```

- [ ] **Step 4: Run full test suite (`python -m pytest tests/`) to ensure 100% pass across all tests**
- [ ] **Step 5: Commit Task 3**
```bash
git add src/shape_packing/solution_tools.py src/shape_packing/agent_loop.py tests/
git commit -m "feat(agent_loop, verification): unblock L shape in agent loop and support composite verification"
```
