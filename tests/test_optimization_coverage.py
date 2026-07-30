"""
Lightweight tests to improve coverage of optimization.py.
Avoid long-running scipy / joblib calls.
"""
import numpy as np
import pytest
from shape_packing.optimization import (
    PackingProblem,
    OptConfig,
    build_objective,
    run_single_attempt,
    run_all_attempts,
)


class TestBuildObjective:
    def test_triangle_in_square(self):
        problem = PackingProblem(N=3, inner_token="3", container_token="4")
        objective, geom = build_objective(problem)
        # geometry is a 4-tuple
        assert len(geom) == 4
        # objective callable
        vals = np.zeros(problem.N * 3)
        p = objective(vals, S=5.0)
        assert isinstance(p, float)


class TestRunSingleAttempt:
    def test_very_small_problem(self):
        problem = PackingProblem(N=2, inner_token="3", container_token="4")
        objective, geom = build_objective(problem)
        cfg = OptConfig(
            attempts=1,
            tolerance=1e-6,
            final_step=0.01,
            time_limit=None,
            n_jobs=1,
        )
        S, values = run_single_attempt(
            problem, objective, geom, seed=0, cfg=cfg, run_start_time=0.0
        )
        # Should return some finite S
        assert isinstance(S, float)
        assert np.isfinite(S)
        assert values is not None

    def test_time_limit_aborts_early(self):
        # Set time_limit so that (time.time() - run_start_time) > time_limit - 5
        # is immediately true: use a negative effective window.
        problem = PackingProblem(N=2, inner_token="3", container_token="4")
        objective, geom = build_objective(problem)
        import time
        run_start = time.time() - 10
        cfg = OptConfig(
            attempts=1,
            tolerance=1e-6,
            final_step=0.01,
            time_limit=2.0,
            n_jobs=1,
        )
        # elapsed 10s > time_limit - 5 = -3s => early return
        S, values = run_single_attempt(
            problem, objective, geom, seed=0, cfg=cfg, run_start_time=run_start
        )
        assert S == float("inf")
        assert values is None


class TestRunAllAttempts:
    def test_minimal_run(self):
        problem = PackingProblem(N=2, inner_token="3", container_token="4")
        objective, geom = build_objective(problem)
        cfg = OptConfig(
            attempts=2,
            tolerance=1e-6,
            final_step=0.01,
            time_limit=None,
            n_jobs=1,
        )
        S, values = run_all_attempts(problem, objective, geom, cfg)
        assert np.isfinite(S)
        assert values is not None
