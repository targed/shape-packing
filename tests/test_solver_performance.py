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
    assert res["backend"] == "pyo3"
    assert len(res["values"]) == 12  # 4 shapes * 3 (x, y, a)
    assert elapsed < 5.0
    print(f"\n[Bench] 4 triangles in square (100 attempts): {elapsed:.3f}s via {res['backend']}")
