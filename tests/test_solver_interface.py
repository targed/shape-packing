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
