"""
solution_tools.py (ToolsModule)

Single module for:
- loading a solution JSON
- reconstructing polygons
- verifying a solution (geometry + record check)
- rendering a solution to PNG

Scripts verify_solution.py and render_solution.py should become
thin entrypoints that import from here.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from .geometry import (
    polygon_normals,
    get_shape_geometry,
    sat_check_overlap,
    sat_check_overlap,
    transform_polygon,
)

TOLERANCE: float = 1e-15


# --------------- Data models ---------------


@dataclass
class Solution:
    path: str
    N: int
    inner_token: str
    container_token: str
    S: float
    final_metric: float
    values: List[float]


@dataclass
class VerifyResult:
    valid: bool
    metric: float
    errors: List[str]
    new_record: bool
    message: str


# --------------- Solution loading ---------------


def load_solution(path: str) -> "Solution":
    """
    Load solution JSON into a typed Solution.

    Supports two JSON shapes used in the repo:

    - A) values-style:
        { N, inner_sides, container_sides, S, final_metric, values[...] }

    - B) positions-style:
        { N, nsi, nsc, S, positions[...] }
    """
    with open(path, "r", encoding="utf-8") as f:
        sol = json.load(f)

    N = int(sol["N"])

    # A) values-style
    if "values" in sol:
        inner_token = str(sol.get("inner_token", sol.get("inner_sides", 3)))
        container_token = str(sol.get("container_token", sol.get("container_sides", 3)))
        S = float(sol["S"])
        final_metric = float(sol["final_metric"])
        values = [float(v) for v in sol["values"]]
        return Solution(
            path=path,
            N=N,
            inner_token=inner_token,
            container_token=container_token,
            S=S,
            final_metric=final_metric,
            values=values,
        )

    # B) positions-style
    if "positions" in sol:
        inner_token = str(sol.get("nsi", sol.get("inner_token", "3")))
        container_token = str(sol.get("nsc", sol.get("container_token", "3")))
        S = float(sol["S"])
        positions: List[Any] = sol["positions"]

        values: List[float] = []
        for p in positions:
            cx = float(p["cx"])
            cy = float(p["cy"])
            a = float(p["a"])
            values.extend([cx, cy, a])

        # derive final_metric if needed, but usually we just read it.
        # For circle containers, final_metric = S (circumradius = Friedman's r).
        # For polygon containers, use the standard sin-scaling formula.
        nsi, _, _, _ = get_shape_geometry(inner_token)
        nsc_val, _, _, _ = get_shape_geometry(container_token)
        container_upper = container_token.strip().upper()
        if container_upper in ("CIRCLE", "CIR"):
            final_metric = S
        else:
            final_metric = S * math.sin(math.pi / nsc_val) / math.sin(math.pi / nsi)

        return Solution(
            path=path,
            N=N,
            inner_token=inner_token,
            container_token=container_token,
            S=S,
            final_metric=final_metric,
            values=values,
        )

    raise ValueError(
        f"Unsupported solution JSON format in {path}: "
        "must contain 'values' or 'positions'."
    )


# --------------- Polygon reconstruction ---------------


def build_polygons(sol: "Solution") -> List[List[Tuple[float, float]]]:
    """
    Build all inner polygons from a Solution:
    Each polygon is a list of (x, y) vertices.
    """
    _, unit_inner, _, _ = get_shape_geometry(sol.inner_token)
    polygons: List[List[Tuple[float, float]]] = []

    for i in range(sol.N):
        x = sol.values[i * 3]
        y = sol.values[i * 3 + 1]
        a = sol.values[i * 3 + 2]
        poly = transform_polygon(unit_inner, x, y, a)
        # Ensure poly is a plain list of (x,y).
        polygons.append(
            [(float(v[0]), float(v[1])) for v in poly]
        )

    return polygons


# --------------- Reference helpers ---------------


def load_best_value(
    reference_path: str = "PACKING_REFERENCE.tsv",
    problem_str: str = "",
) -> Optional[float]:
    """
    Load best known value for a problem from PACKING_REFERENCE.tsv.
    Returns None if not found.
    """
    if not os.path.exists(reference_path):
        return None

    with open(reference_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 6:
                continue
            our_prob = parts[5]
            if our_prob == problem_str:
                try:
                    return float(parts[2])
                except ValueError:
                    return None
    return None


# --------------- Verification ---------------


def verify_solution(
    sol_path: str,
    problem_str: Optional[str] = None,
    tolerance: float = TOLERANCE,
    check_record: bool = True,
    reference_path: str = "PACKING_REFERENCE.tsv",
) -> "VerifyResult":
    """
    Verify a solution JSON:
      - metric scaling consistency
      - container bounds
      - pairwise overlap (SAT)
      - optional record comparison

    Returns a VerifyResult.
    """
    errors: List[str] = []
    new_record = False

    sol = load_solution(sol_path)
    N = sol.N
    nsi, _, _, _ = get_shape_geometry(sol.inner_token)
    nsc, _, unit_container_vectors, unit_container_apothem = get_shape_geometry(sol.container_token)
    S = sol.S

    # 1. Metric scaling verification
    container_upper = sol.container_token.strip().upper()
    if container_upper in ("CIRCLE", "CIR"):
        # For circle containers, final_metric = S (Friedman's r = circumradius of 32-gon).
        calc_metric = S
    else:
        calc_metric = S * math.sin(math.pi / nsc) / math.sin(math.pi / nsi)
    diff = abs(calc_metric - sol.final_metric)
    if diff > 1e-10:
        errors.append(
            f"Metric scaling is incorrect. Computed: {calc_metric}, "
            f"JSON says: {sol.final_metric}"
        )

    # 2. Container bounds verification
    container_limit = unit_container_apothem * S
    container_normals = [(float(v[0]), float(v[1])) for v in unit_container_vectors]

    polygons = build_polygons(sol)

    for i, poly in enumerate(polygons):
        for v in poly:
            for n in container_normals:
                dist = v[0] * n[0] + v[1] * n[1]
                if dist > container_limit + tolerance:
                    violation = dist - container_limit
                    errors.append(
                        f"Shape {i} is out of bounds! Violation margin: {violation}"
                    )

    # 3. Overlap verification (SAT)
    poly_normals_list = [polygon_normals(p) for p in polygons]
    for i in range(N):
        for j in range(i + 1, N):
            overlap, depth = sat_check_overlap(
                polygons[i],
                polygons[j],
                poly_normals_list[i],
                poly_normals_list[j],
            )
            if overlap and depth > tolerance:
                errors.append(
                    f"Shapes {i} and {j} overlap! Depth: {depth}"
                )

    valid = len(errors) == 0

    # 4. Record check
    if problem_str and check_record and valid:
        best = load_best_value(reference_path, problem_str)
        if best is not None:
            if calc_metric < best - tolerance:
                new_record = True

    if valid:
        if new_record:
            message = f"NEW RECORD. s={calc_metric:.15f}"
        else:
            message = f"Valid configuration, metric s={calc_metric:.15f}"
    else:
        message = "; ".join(errors)

    return VerifyResult(
        valid=valid,
        metric=calc_metric,
        errors=errors,
        new_record=new_record,
        message=message,
    )


# --------------- Plotting helpers ---------------


def to_plot_data(sol: "Solution") -> Any:
    """
    Prepare geometry for plotting from a Solution.

    Returns dict with:
      - container_vertices: list of (x, y)
      - polygons: list of list of (x, y)
      - centers: list of (cx, cy)
    """
    _, unit_container, _, _ = get_shape_geometry(sol.container_token)
    container_vertices = unit_container * sol.S
    polygons = build_polygons(sol)

    centers: List[Tuple[float, float]] = []
    for i in range(sol.N):
        cx = sol.values[i * 3]
        cy = sol.values[i * 3 + 1]
        centers.append((cx, cy))

    return {
        "container_vertices": [
            (float(v[0]), float(v[1])) for v in container_vertices
        ],
        "polygons": polygons,
        "centers": centers,
    }


# --------------- Rendering ---------------


def render_solution(
    sol_path: str,
    out_png: str = "solution.png",
    dpi: int = 300,
    show_axes: bool = False,
    show_grid: bool = False,
) -> None:
    """
    Render a solution JSON to a PNG.
    """
    try:
        import matplotlib
        matplotlib.use("Agg", force=False)
        import matplotlib.pyplot as plt
    except ImportError:
        print("[WARN] matplotlib is not installed. Skipping PNG rendering.")
        return

    sol = load_solution(sol_path)
    data = to_plot_data(sol)

    fig, ax = plt.subplots(figsize=(6, 6))

    container = list(data["container_vertices"]) + [data["container_vertices"][0]]
    ax.plot(
        [v[0] for v in container],
        [v[1] for v in container],
        color="#000000",
        linewidth=0.5,
    )

    for poly in data["polygons"]:
        poly_plot = list(poly) + [poly[0]]
        ax.fill(
            [v[0] for v in poly_plot],
            [v[1] for v in poly_plot],
            "#CCCCCC",
            edgecolor="black",
            linewidth=0.5,
        )

    ax.set_aspect("equal")
    if not show_axes:
        ax.axis("off")
    if show_grid:
        ax.grid(True, linestyle="--", alpha=0.3)

    plt.tight_layout()
    fig.savefig(out_png, dpi=dpi)
    plt.close(fig)


# --------------- End of solution_tools.py ---------------