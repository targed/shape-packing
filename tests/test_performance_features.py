"""
Tests for direct_call and in-memory history caching features.
"""
import pytest
from unittest.mock import patch, MagicMock
from src.shape_packing.cli import handle_suggest, handle_run
from src.shape_packing.agent_loop import ExperimentResult



class DummyArgs:
    def __init__(self):
        self.min_n = None
        self.max_n = None
        self.equal_n = None
        self.include_inner = None
        self.exclude_inner = None
        self.include_container = None
        self.exclude_container = None
        self.min_inner_sides = None
        self.max_inner_sides = None
        self.min_container_sides = None
        self.max_container_sides = None
        self.exclude_problems = None
        self.problem = "5_3_in_4"
        self.attempts = 10
        self.init_script = None
        self.no_commit = True
        self.json_out = True
        self.no_png = True
        self.no_build = True


class TestDirectCallAndHistoryCache:
    def test_handle_suggest_direct_call_with_history_cache(self):
        args = DummyArgs()
        fake_history = [
            ExperimentResult(problem="5_3_in_4", score=1.5, status="keep", description="", seconds=0.1, commit="auto", memory_gb=0.0)
        ]

        with patch("src.shape_packing.cli.load_history") as mock_load, \
             patch("src.shape_packing.cli.choose_problem", return_value="5_3_in_4"):


            result = handle_suggest(args, history_cache=fake_history, direct_call=True)

            # load_history should NOT be called since history_cache was provided
            mock_load.assert_not_called()

            # Should return a dictionary directly
            assert isinstance(result, dict)
            assert result["problem"] == "5_3_in_4"
            assert result["best_score"] == 1.5

    def test_handle_run_direct_call_success(self):
        args = DummyArgs()
        fake_history = []

        mock_solver_res = {"success": True, "score": 1.803, "values": [0.0]*9, "output": "Final side length: 1.803"}

        with patch("src.shape_packing.cli.run_solver", return_value=mock_solver_res), \
             patch("src.shape_packing.cli.load_history") as mock_load:

            result = handle_run(args, history_cache=fake_history, direct_call=True)

            mock_load.assert_not_called()

            assert isinstance(result, dict)
            assert result["success"] is True
            assert result["score"] == 1.803

    def test_handle_run_direct_call_no_valid_packing(self):
        args = DummyArgs()

        mock_solver_res = {"success": False, "score": 0.0, "output": "No valid packing found"}

        with patch("src.shape_packing.cli.run_solver", return_value=mock_solver_res):
            result = handle_run(args, history_cache=[], direct_call=True)

            assert isinstance(result, dict)
            assert result["success"] is False
            assert result["returncode"] == 42
            assert "No valid packing found" in result["error"]



class TestLoopDirectIntegration:
    def test_parallel_loop_get_state_uses_history(self):
        import run_parallel_loop

        fake_history = [
            ExperimentResult(problem="3_3_in_4", score=1.2, status="keep", description="", seconds=0.1, commit="auto", memory_gb=0.0)
        ]
        run_parallel_loop._GLOBAL_HISTORY = fake_history

        with patch("src.shape_packing.cli.choose_problem", return_value="3_3_in_4"):
            state = run_parallel_loop.get_state()
            assert state is not None
            assert state["problem"] == "3_3_in_4"
            assert state["best_score"] == 1.2

    def test_autoresearch_loop_get_state_uses_history(self):
        import importlib.util
        from pathlib import Path
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "autoresearch" / "run_autoresearch_loop.py"
        spec = importlib.util.spec_from_file_location("run_autoresearch_loop", script_path)
        run_autoresearch_loop = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run_autoresearch_loop)

        fake_history = [
            ExperimentResult(problem="4_4_in_circle", score=2.0, status="keep", description="", seconds=0.1, commit="auto", memory_gb=0.0)
        ]
        run_autoresearch_loop._GLOBAL_HISTORY = fake_history

        with patch("src.shape_packing.cli.choose_problem", return_value="4_4_in_circle"):
            state = run_autoresearch_loop.get_state()
            assert state is not None
            assert state["problem"] == "4_4_in_circle"
            assert state["best_score"] == 2.0
