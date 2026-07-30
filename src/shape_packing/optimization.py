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

import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import numpy as np
from joblib import Parallel, delayed
from scipy.optimize import basinhopping, minimize

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
    attempts: int = 1000
    tolerance: float = 1e-8
    final_step: float = 0.0001
    time_limit: Optional[float] = None  # seconds; None = no limit
    n_jobs: int = -1  # -1 = use all cores
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
        )

    # Return objective + geometry constants for use inside attempts.
    geom = (
        unit_polygon_vertices,
        unit_polygon_vectors,
        unit_container_vectors,
        unit_container_apothem,
    )
    return objective, geom


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

    # Initial container size
    dynamic_S = np.sqrt(N) * (2.0 + np.random.rand() * 2.0)
    initial_S = dynamic_S
    lowest_S = np.sqrt(N)
    range_val = initial_S - lowest_S

    # Initial positions
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

    last_valid_x = x0.copy()
    last_valid_S = dynamic_S

    # These are used inside loop but not recomputed:
    # unit_polygon_vertices = geom[0]  # not used in loop
    # unit_polygon_vectors = geom[1]  # not used in loop
    # unit_container_vectors = geom[2]  # not used in loop
    # unit_container_apothem = geom[3]  # not used in loop

    while True:
        # Time guard
        if cfg.time_limit and (time.time() - run_start_time) > cfg.time_limit - 5:
            break

        # L-BFGS-B step
        minimized = minimize(
            objective,
            x0,
            args=(dynamic_S,),
            method="L-BFGS-B",
            tol=1e-7,
        )

        multiplier = (
            1.0
            - cfg.final_step
            - (dynamic_S - lowest_S) * (0.01 - cfg.final_step) / range_val
        )

        if minimized.fun < cfg.tolerance:
            # Feasible enough: record and shrink
            last_valid_x = minimized.x.copy()
            last_valid_S = dynamic_S
            x0 = minimized.x * multiplier
            dynamic_S *= multiplier
        else:
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
                last_valid_x = bh_result.x.copy()
                last_valid_S = dynamic_S
                x0 = bh_result.x * multiplier
                dynamic_S *= multiplier
            else:
                break

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