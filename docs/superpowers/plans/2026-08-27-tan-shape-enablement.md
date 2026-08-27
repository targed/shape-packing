# TAN Shape Full Enablement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fully unblock and enable the `TAN` shape ($45^\circ-45^\circ-90^\circ$ right isosceles triangle) across agent loop problem selection, priority queue, configuration, solver interfaces, and verification.

**Architecture:** Update `agent_loop._is_shape_unsupported()` to treat `TAN` as a first-class supported shape alongside `DOMINO`. Align legacy `tangram_triangle_vertices()` in `packing_config.py` with canonical incenter geometry. Add end-to-end unit and integration tests covering priority queue selection, optimization solve, verification, and CLI problem dispatching for TAN.

**Tech Stack:** Python 3.14, NumPy, Pytest, Rust (`packer_rs`)

## Global Constraints

- Preserve incenter parameterization ($r = 1 - \sqrt{2}/2$) from `geometry.py`.
- Metric scaling: `c_metric = S` when container is TAN; `i_scale = 1.0` when inner shape is TAN.
- All pytest test suites must pass cleanly.

---

### Task 1: Unblock TAN in Problem Selection & Agent Loop

**Files:**
- Modify: `src/shape_packing/agent_loop.py:375-395`
- Test: `tests/test_agent_loop.py`

**Interfaces:**
- `_is_shape_unsupported(token: str, filters: dict) -> bool`
- Consumes: `is_special_shape(token)`
- Produces: Returns `False` for `token in ("TAN", "DOMINO")`

- [ ] **Step 1: Write the failing test in `tests/test_agent_loop.py`**
```python
def test_tan_shape_supported_in_agent_loop():
    from src.shape_packing.agent_loop import _is_shape_unsupported
    assert not _is_shape_unsupported("TAN", {})
    assert not _is_shape_unsupported("tan", {})
```

- [ ] **Step 2: Run test to confirm failure**
```bash
python -m pytest tests/test_agent_loop.py -k test_tan_shape_supported_in_agent_loop
```

- [ ] **Step 3: Update `_is_shape_unsupported()` and `allowed` set in `src/shape_packing/agent_loop.py`**
Enable `TAN` alongside `DOMINO` and add `"TAN"` to `allowed`.

- [ ] **Step 4: Run test to confirm it passes**
```bash
python -m pytest tests/test_agent_loop.py -k test_tan_shape_supported_in_agent_loop
```

---

### Task 2: Align Legacy TAN Vertices in `packing_config.py`

**Files:**
- Modify: `src/shape_packing/packing_config.py:281-290`
- Test: `tests/test_packing_config.py`

**Interfaces:**
- `tangram_triangle_vertices(size: float = 1.0) -> List[Tuple[float, float]]`

- [ ] **Step 1: Write test for canonical TAN vertices in `tests/test_packing_config.py`**
```python
def test_tangram_triangle_vertices_canonical():
    from src.shape_packing.packing_config import tangram_triangle_vertices
    verts = tangram_triangle_vertices(1.0)
    assert len(verts) == 3
    # Verify right isosceles triangle with legs of length 1.0
    dx1 = verts[1][0] - verts[0][0]
    dy1 = verts[1][1] - verts[0][1]
    dx2 = verts[2][0] - verts[0][0]
    dy2 = verts[2][1] - verts[0][1]
    assert abs(math.hypot(dx1, dy1) - 1.0) < 1e-6
    assert abs(math.hypot(dx2, dy2) - 1.0) < 1e-6
```

- [ ] **Step 2: Update `tangram_triangle_vertices` in `src/shape_packing/packing_config.py`**

- [ ] **Step 3: Run test to confirm pass**
```bash
python -m pytest tests/test_packing_config.py -k test_tangram_triangle_vertices_canonical
```

---

### Task 3: End-to-End TAN Solving & Verification Integration Tests

**Files:**
- Modify: `tests/test_solver_interface.py`
- Modify: `tests/test_cli_integration.py`

- [ ] **Step 1: Add integration test solving a TAN problem (e.g. `1_tan_in_4` or `2_tan_in_4`)**
- [ ] **Step 2: Add CLI integration test for TAN problem suggest and run**
- [ ] **Step 3: Run full pytest suite to verify zero regressions**
```bash
python -m pytest tests/
```
