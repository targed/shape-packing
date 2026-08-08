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
import numpy as np
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from .geometry import (
    polygon_normals,
    get_shape_geometry,
    sat_check_overlap,
    sat_check_overlap,
    transform_polygon,
)

from .packing_config import (
    VERIFY_SAT_TOLERANCE,
    VERIFY_METRIC_TOLERANCE,
    RENDER_DPI,
    RENDER_FIGURE_SIZE,
)

TOLERANCE: float = VERIFY_SAT_TOLERANCE  # Re-exported for backward compatibility


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


def compute_friedman_metric(S: float, inner_token: str, container_token: str) -> float:
    """
    Computes the correct Friedman metric corresponding to the container and inner shapes.
    """
    container_upper = container_token.strip().upper()
    inner_upper = inner_token.strip().upper()
    
    if container_upper in ("CIRCLE", "CIR", "TAN", "DOMINO", "L"):
        c_metric = S
    else:
        try:
            nsc = int(container_upper)
            c_metric = 2 * S * math.sin(math.pi / nsc)
        except ValueError:
            c_metric = 2 * S * math.sin(math.pi / 3)

    if inner_upper in ("CIRCLE", "CIR", "TAN", "DOMINO", "L"):
        i_scale = 1.0
    else:
        try:
            nsi = int(inner_upper)
            i_scale = 2 * math.sin(math.pi / nsi)
        except ValueError:
            i_scale = 2 * math.sin(math.pi / 3)

    return c_metric / i_scale

def inverse_friedman_metric(f_metric: float, inner_token: str, container_token: str) -> float:
    """
    Given a target Friedman metric, compute the corresponding solver S (circumradius).
    """
    container_upper = container_token.strip().upper()
    inner_upper = inner_token.strip().upper()
    
    # Get inner scale
    if inner_upper in ("CIRCLE", "CIR", "TAN", "DOMINO", "L"):
        i_scale = 1.0
    else:
        try:
            nsi = int(inner_upper)
            i_scale = 2 * math.sin(math.pi / nsi)
        except ValueError:
            i_scale = 2 * math.sin(math.pi / 3)

    c_metric = f_metric * i_scale

    # Reverse container metric
    if container_upper in ("CIRCLE", "CIR", "TAN", "DOMINO", "L"):
        return c_metric
    else:
        try:
            nsc = int(container_upper)
            return c_metric / (2 * math.sin(math.pi / nsc))
        except ValueError:
            return c_metric / (2 * math.sin(math.pi / 3))

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

        final_metric = compute_friedman_metric(S, inner_token, container_token)

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
    nsc, _, unit_container_vectors, unit_container_radii = get_shape_geometry(sol.container_token)
    S = sol.S

    is_inner_circle = sol.inner_token.upper() in ["CIRCLE", "CIR"]
    is_container_circle = sol.container_token.upper() in ["CIRCLE", "CIR"]

    # 1. Metric scaling verification
    calc_metric = compute_friedman_metric(S, sol.inner_token, sol.container_token)
    diff = abs(calc_metric - sol.final_metric)
    if diff > 1e-10:
        errors.append(
            f"Metric scaling is incorrect. Computed: {calc_metric}, "
            f"JSON says: {sol.final_metric}"
        )

    # 2. Container bounds verification
    container_limits = unit_container_radii * S
    container_normals = [(float(v[0]), float(v[1])) for v in unit_container_vectors]

    polygons = build_polygons(sol)

    for i, poly in enumerate(polygons):
        posx = sol.values[i * 3]
        posy = sol.values[i * 3 + 1]
        
        if is_container_circle:
            if is_inner_circle:
                dist = math.hypot(posx, posy)
                limit = S - 1.0
                if dist > limit + tolerance:
                    errors.append(f"Shape {i} (circle) out of circular bounds! Margin: {dist - limit}")
            else:
                for v in poly:
                    dist = math.hypot(v[0], v[1])
                    if dist > S + tolerance:
                        errors.append(f"Shape {i} out of circular bounds! Margin: {dist - S}")
        else:
            if is_inner_circle:
                for n_idx, n in enumerate(container_normals):
                    dist = posx * n[0] + posy * n[1]
                    limit = container_limits[n_idx] - 1.0
                    if dist > limit + tolerance:
                        errors.append(f"Shape {i} (circle) out of bounds! Margin: {dist - limit}")
            else:
                for v in poly:
                    for n_idx, n in enumerate(container_normals):
                        dist = v[0] * n[0] + v[1] * n[1]
                        if dist > container_limits[n_idx] + tolerance:
                            violation = dist - container_limits[n_idx]
                            errors.append(f"Shape {i} is out of bounds! Violation margin: {violation}")

    # 3. Overlap verification (SAT)
    poly_normals_list = [polygon_normals(p) for p in polygons]
    for i in range(N):
        for j in range(i + 1, N):
            if is_inner_circle:
                posxi = sol.values[i * 3]
                posyi = sol.values[i * 3 + 1]
                posxj = sol.values[j * 3]
                posyj = sol.values[j * 3 + 1]
                dist = math.hypot(posxi - posxj, posyi - posyj)
                if dist < 2.0 - tolerance:
                    errors.append(f"Shapes {i} and {j} overlap (circle)! Depth: {2.0 - dist}")
                continue

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


def get_container_rotation_offset(token: str) -> float:
    """
    Returns rotation angle in radians to rotate the container (and all packed shapes)
    so that the container has a horizontal flat edge at the bottom, matching
    Erich Friedman's standard visual orientation.
    """
    t = str(token).strip().upper()
    if t in ("CIRCLE", "CIR", "DOMINO", "TAN", "L"):
        return 0.0
    try:
        sides = int(t)
    except ValueError:
        return 0.0

    if sides % 2 == 1:
        return math.pi / 2.0
    else:
        if (sides // 2) % 2 == 0:
            return math.pi / sides
        else:
            return 0.0


def to_plot_data(sol: "Solution") -> Any:
    """
    Prepare geometry for plotting from a Solution.

    Returns dict with:
      - container_vertices: list of (x, y)
      - polygons: list of list of (x, y)
      - centers: list of (cx, cy)
    """
    rot = get_container_rotation_offset(sol.container_token)
    cosa = math.cos(rot)
    sina = math.sin(rot)

    _, unit_container, _, _ = get_shape_geometry(sol.container_token)
    if rot != 0.0:
        unit_container = np.array([
            [vx * cosa - vy * sina, vx * sina + vy * cosa]
            for vx, vy in unit_container
        ])
    container_vertices = unit_container * sol.S

    _, unit_inner, _, _ = get_shape_geometry(sol.inner_token)
    polygons: List[List[Tuple[float, float]]] = []
    centers: List[Tuple[float, float]] = []

    for i in range(sol.N):
        x = sol.values[i * 3]
        y = sol.values[i * 3 + 1]
        a = sol.values[i * 3 + 2]

        rx = x * cosa - y * sina
        ry = x * sina + y * cosa
        ra = a + rot

        poly = transform_polygon(unit_inner, rx, ry, ra)
        polygons.append([(float(v[0]), float(v[1])) for v in poly])
        centers.append((rx, ry))

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
    dpi: int = RENDER_DPI,
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

    fig, ax = plt.subplots(figsize=RENDER_FIGURE_SIZE)

    is_inner_circle = sol.inner_token.upper() in ["CIRCLE", "CIR"]
    is_container_circle = sol.container_token.upper() in ["CIRCLE", "CIR"]

    if is_container_circle:
        c = plt.Circle((0, 0), sol.S, color="#000000", fill=False, linewidth=0.5)
        ax.add_patch(c)
    else:
        container = list(data["container_vertices"]) + [data["container_vertices"][0]]
        ax.plot(
            [v[0] for v in container],
            [v[1] for v in container],
            color="#000000",
            linewidth=0.5,
        )

    if is_inner_circle:
        for center in data["centers"]:
            c = plt.Circle(center, 1.0, facecolor="#CCCCCC", edgecolor="black", linewidth=0.5)
            ax.add_patch(c)
    else:
        for poly in data["polygons"]:
            poly_plot = list(poly) + [poly[0]]
            ax.fill(
                [v[0] for v in poly_plot],
                [v[1] for v in poly_plot],
                "#CCCCCC",
                edgecolor="black",
                linewidth=0.5,
            )

    ax.autoscale_view()

    ax.set_aspect("equal")
    if not show_axes:
        ax.axis("off")
    if show_grid:
        ax.grid(True, linestyle="--", alpha=0.3)

    plt.tight_layout()
    fig.savefig(out_png, dpi=dpi)
    plt.close(fig)


# --------------- End of solution_tools.py ---------------