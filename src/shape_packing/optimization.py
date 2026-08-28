"""
optimization.py

Deep module for optimization + objective orchestration in this packing project.

Responsibilities:
- Construct the objective function from problem definition.
- Run a single optimization attempt (init, shrink, L-BFGS-B, basinhopping).
- Orchestrate many attempts in parallel.
- Encapsulate all optimizer choices and scheduling so callers stay thin.

Design goals:
- Stable interface: polygon_packer.py and future agents call into this.
- All optimizer-related knobs concentrated here.
- No geometry duplication; imports from geometry.py.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple, List, Dict, Any, Union

import numpy as np
from joblib import Parallel, delayed
from scipy.optimize import basinhopping, minimize

from .packing_config import (
    OPTIMIZER_ATTEMPTS,
    OPTIMIZER_TOLERANCE,
    OPTIMIZER_FINAL_STEP,
    OPTIMIZER_N_JOBS,
)

from .geometry import (
    bh_objective,
    get_shape_geometry,
)


@dataclass
class PackingProblem:
    """
    Describes a packing problem: N inner polygons (each with nsi sides)
    inside a container with nsc sides.
    """
    N: int
    inner_token: str
    container_token: str


@dataclass
class OptConfig:
    """
    High-level knobs for optimization behavior.
    """
    attempts: int = OPTIMIZER_ATTEMPTS
    tolerance: float = OPTIMIZER_TOLERANCE
    final_step: float = OPTIMIZER_FINAL_STEP
    time_limit: Optional[float] = None  # seconds; None = no limit
    n_jobs: int = OPTIMIZER_N_JOBS  # -1 = use all cores
    # Future: strategy, convergence_policy, etc.


# ------------ objective construction ------------


def build_objective(problem: PackingProblem):
    """
    Build a callable objective(values) using geometry.py.
    Returns:
        objective_fn(values, S) -> float
        geom: tuple with geometry constants
    """
    N = problem.N
    nsi, unit_polygon_vertices, unit_polygon_vectors, _ = get_shape_geometry(problem.inner_token)
    nsc, _, unit_container_vectors, unit_container_apothem = get_shape_geometry(problem.container_token)

    is_inner_circle = problem.inner_token.upper() in ("CIRCLE", "CIR")
    is_container_circle = problem.container_token.upper() in ("CIRCLE", "CIR")

    def objective(values: np.ndarray, S: float) -> float:
        return bh_objective(
            values,
            S,
            N,
            nsi,
            unit_polygon_vertices,
            unit_polygon_vectors,
            unit_container_vectors,
            unit_container_apothem,
            is_inner_circle,
            is_container_circle,
        )

    # Return objective + geometry constants for use inside attempts.
    geom = (
        unit_polygon_vertices,
        unit_polygon_vectors,
        unit_container_vectors,
        unit_container_apothem,
    )
    return objective, geom


# ------------ single attempt helpers ------------


def _generate_initial_configuration(N: int) -> Tuple[float, float, float, np.ndarray]:
    """
    Generate initial container size dynamic_S, lowest_S, range_val, and initial decision vector x0.
    """
    dynamic_S = np.sqrt(N) * (2.0 + np.random.rand() * 2.0)
    lowest_S = np.sqrt(N)
    range_val = dynamic_S - lowest_S

    if np.random.rand() < 0.5:
        x0 = np.random.uniform(-dynamic_S / 2, dynamic_S / 2, N * 3)
    else:
        grid_linspace = np.linspace(
            -dynamic_S / 2 * 0.9,
            dynamic_S / 2 * 0.9,
            int(np.ceil(np.sqrt(N))),
        )
        xx, yy = np.meshgrid(grid_linspace, grid_linspace)
        grid_points = np.column_stack((xx.flatten(), yy.flatten()))[:N]
        x0 = np.zeros(N * 3)
        x0[0::3] = grid_points[:, 0]
        x0[1::3] = grid_points[:, 1]
        x0[2::3] = np.random.uniform(0, 2 * np.pi, N)

    return dynamic_S, lowest_S, range_val, x0


def _calculate_shrink_multiplier(
    dynamic_S: float, lowest_S: float, range_val: float, final_step: float
) -> float:
    """Compute shrinking scale multiplier based on distance to lowest possible S."""
    return (
        1.0
        - final_step
        - (dynamic_S - lowest_S) * (0.01 - final_step) / range_val
    )


def _optimize_step(
    objective: Callable,
    x0: np.ndarray,
    dynamic_S: float,
    cfg: OptConfig,
) -> Optional[np.ndarray]:
    """
    Run local L-BFGS-B optimization step with basin-hopping fallback.
    Returns optimal decision vector if feasible (< tolerance), otherwise None.
    """
    minimized = minimize(
        objective,
        x0,
        args=(dynamic_S,),
        method="L-BFGS-B",
        tol=1e-7,
    )
    if minimized.fun < cfg.tolerance:
        return minimized.x.copy()

    # Try basin-hopping escape
    bh_result = basinhopping(
        objective,
        x0,
        minimizer_kwargs={
            "method": "L-BFGS-B",
            "args": (dynamic_S,),
            "tol": 1e-7,
        },
        niter=30,
        T=0.2,
        stepsize=0.12,
    )
    if bh_result.fun < cfg.tolerance:
        return bh_result.x.copy()

    return None


# ------------ single attempt ------------


def run_single_attempt(
    problem: PackingProblem,
    objective: Callable,
    geom,
    seed: int,
    cfg: OptConfig,
    run_start_time: float,
) -> Tuple[float, Optional[np.ndarray]]:
    """
    Run a single optimization attempt (with shrink + L-BFGS-B + basin-hopping).
    Returns:
        (S, values) where S is the container scale and values is the best
        decision vector; if aborted due to time, S may be inf and values None.
    """
    N = problem.N

    # Time guard
    if cfg.time_limit and (time.time() - run_start_time) > cfg.time_limit - 5:
        return float("inf"), None

    # Logging: only occasionally
    if seed % 100 == 0:
        print("Attempt", seed, flush=True)

    np.random.seed(seed)

    dynamic_S, lowest_S, range_val, x0 = _generate_initial_configuration(N)
    last_valid_x = x0.copy()
    last_valid_S = dynamic_S

    while True:
        # Time guard
        if cfg.time_limit and (time.time() - run_start_time) > cfg.time_limit - 5:
            break

        best_x = _optimize_step(objective, x0, dynamic_S, cfg)
        if best_x is None:
            break

        multiplier = _calculate_shrink_multiplier(
            dynamic_S, lowest_S, range_val, cfg.final_step
        )
        last_valid_x = best_x
        last_valid_S = dynamic_S
        x0 = best_x * multiplier
        dynamic_S *= multiplier

    return last_valid_S, last_valid_x


# ------------ many attempts ------------


def run_all_attempts(
    problem: PackingProblem,
    objective: Callable,
    geom,
    cfg: OptConfig,
) -> Tuple[float, Optional[np.ndarray]]:
    """
    Run many optimization attempts in parallel and return the best (S, values).
    """
    run_start_time = time.time()

    best_S: float = float("inf")
    best_values: Optional[np.ndarray] = None

    results = Parallel(n_jobs=cfg.n_jobs, prefer="processes")(
        delayed(run_single_attempt)(
            problem,
            objective,
            geom,
            i,
            cfg,
            run_start_time,
        )
        for i in range(cfg.attempts)
    )

    for s, values in results:
        if s < best_S and values is not None:
            best_S = s
            best_values = values

    return best_S, best_values