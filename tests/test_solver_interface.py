from src.shape_packing.solver_interface import run_solver
from src.shape_packing.solution_tools import verify_solution

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


def test_run_solver_tan(tmp_path):
    sol_file = str(tmp_path / "tan_sol.json")
    result = run_solver(
        n_shapes=1,
        inner_shape="TAN",
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
        # Verify solution file passes verifier
        v_res = verify_solution(sol_file, "1_tan_in_4", check_record=False)
        assert v_res.valid is True
