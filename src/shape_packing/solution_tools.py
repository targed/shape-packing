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

import json
import math
import os
import numpy as np
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from .geometry import (
    polygon_normals,
    get_shape_geometry,
    get_shape_convex_parts,
    sat_check_overlap,
    transform_polygon,
)

from .packing_config import (
    VERIFY_SAT_TOLERANCE,
    VERIFY_METRIC_TOLERANCE,
    RECORD_MIN_IMPROVEMENT,
    RENDER_DPI,
    RENDER_FIGURE_SIZE,
    RENDER_CROP_MODE,
    RENDER_CONTAINER_LINEWIDTH,
    RENDER_INNER_LINEWIDTH,
    RENDER_SIZE_PX,
    RENDER_PAD_PX,
    RENDER_INNER_FACE_COLOR,
    RENDER_INNER_EDGE_COLOR,
    RENDER_CONTAINER_COLOR,
    RENDER_BG_COLOR,
    RENDER_ALIGN_CONTAINER,
    get_family_colors,
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

_REFERENCE_CACHE: Dict[str, Dict[str, float]] = {}


def load_reference_map(
    reference_path: str = "PACKING_REFERENCE.tsv",
) -> Dict[str, float]:
    """
    Load all problem -> best_value mappings from reference TSV with in-memory caching.
    """
    if not os.path.exists(reference_path):
        return {}

    abs_path = os.path.abspath(reference_path)
    mtime = os.path.getmtime(abs_path)
    cache_key = f"{abs_path}:{mtime}"

    if cache_key in _REFERENCE_CACHE:
        return _REFERENCE_CACHE[cache_key]

    ref_map: Dict[str, float] = {}
    with open(reference_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 6:
                continue
            our_prob = parts[5]
            try:
                ref_map[our_prob] = float(parts[2])
            except ValueError:
                pass

    _REFERENCE_CACHE[cache_key] = ref_map
    return ref_map


def load_best_value(
    reference_path: str = "PACKING_REFERENCE.tsv",
    problem_str: str = "",
) -> Optional[float]:
    """
    Load best known value for a problem from PACKING_REFERENCE.tsv using cached map.
    Returns None if not found.
    """
    ref_map = load_reference_map(reference_path)
    return ref_map.get(problem_str)


# --------------- Verification helpers ---------------


def _verify_metric_scaling(sol: Solution, calc_metric: float) -> List[str]:
    """Verify that calculated Friedman metric matches the solution JSON's final_metric."""
    errors: List[str] = []
    diff = abs(calc_metric - sol.final_metric)
    if diff > VERIFY_METRIC_TOLERANCE:
        errors.append(
            f"Metric scaling is incorrect. Computed: {calc_metric}, "
            f"JSON says: {sol.final_metric}"
        )
    return errors


def _verify_container_bounds(
    sol: Solution,
    polygons: List[Any],
    unit_container_vectors: Any,
    unit_container_radii: Any,
    tolerance: float,
) -> List[str]:
    """Verify that all shapes lie within the container boundaries."""
    errors: List[str] = []
    S = sol.S
    is_inner_circle = sol.inner_token.upper() in ("CIRCLE", "CIR")
    is_container_circle = sol.container_token.upper() in ("CIRCLE", "CIR")

    container_limits = unit_container_radii * S
    container_normals = [(float(v[0]), float(v[1])) for v in unit_container_vectors]

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
    return errors


def _verify_overlap(
    sol: Solution,
    polygons: List[Any],
    tolerance: float,
) -> List[str]:
    """Verify pairwise overlap among all inner shapes using circle distance or SAT."""
    errors: List[str] = []
    N = sol.N
    is_inner_circle = sol.inner_token.upper() in ("CIRCLE", "CIR")

    parts = get_shape_convex_parts(sol.inner_token)
    if len(parts) > 1:
        # Multi-part compound shape (e.g. L-tromino)
        transformed_parts = []
        for i in range(N):
            posx = sol.values[i * 3]
            posy = sol.values[i * 3 + 1]
            rot = sol.values[i * 3 + 2]
            shape_parts = []
            for (p_v, _) in parts:
                t_v = transform_polygon(p_v, posx, posy, rot)
                t_n = polygon_normals(t_v)
                shape_parts.append((t_v, t_n))
            transformed_parts.append(shape_parts)

        for i in range(N):
            for j in range(i + 1, N):
                for (p1_v, p1_n) in transformed_parts[i]:
                    for (p2_v, p2_n) in transformed_parts[j]:
                        overlap, depth = sat_check_overlap(p1_v, p2_v, p1_n, p2_n)
                        if overlap and depth > tolerance:
                            errors.append(f"Shapes {i} and {j} overlap! Depth: {depth}")
        return errors

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
    return errors


def _check_new_record(
    calc_metric: float,
    problem_str: Optional[str],
    check_record: bool,
    reference_path: str,
    min_improvement: float = RECORD_MIN_IMPROVEMENT,
) -> bool:
    """Check if the solution improves upon the known best benchmark value."""
    if not (problem_str and check_record):
        return False
    best = load_best_value(reference_path, problem_str)
    if best is not None and calc_metric < best - min_improvement:
        return True
    return False


# --------------- Verification ---------------


def verify_solution(
    sol_path: str,
    problem_str: Optional[str] = None,
    tolerance: float = TOLERANCE,
    check_record: bool = True,
    reference_path: str = "PACKING_REFERENCE.tsv",
    min_improvement: float = RECORD_MIN_IMPROVEMENT,
) -> "VerifyResult":
    """
    Verify a solution JSON:
      - metric scaling consistency
      - container bounds
      - pairwise overlap (SAT)
      - optional record comparison

    Returns a VerifyResult.
    """
    sol = load_solution(sol_path)
    _, _, unit_container_vectors, unit_container_radii = get_shape_geometry(sol.container_token)
    polygons = build_polygons(sol)

    calc_metric = compute_friedman_metric(sol.S, sol.inner_token, sol.container_token)

    errors: List[str] = []
    errors.extend(_verify_metric_scaling(sol, calc_metric))
    errors.extend(
        _verify_container_bounds(
            sol, polygons, unit_container_vectors, unit_container_radii, tolerance
        )
    )
    errors.extend(_verify_overlap(sol, polygons, tolerance))

    valid = len(errors) == 0
    new_record = (
        _check_new_record(
            calc_metric, problem_str, check_record, reference_path, min_improvement
        )
        if valid
        else False
    )

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


def to_plot_data(sol: "Solution", align_container: bool = RENDER_ALIGN_CONTAINER) -> Any:
    """
    Prepare geometry for plotting from a Solution.

    Returns dict with:
      - container_vertices: list of (x, y)
      - polygons: list of list of (x, y)
      - centers: list of (cx, cy)
    """
    rot = get_container_rotation_offset(sol.container_token) if align_container else 0.0
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
    size_px: Optional[int] = RENDER_SIZE_PX,
    width_px: Optional[int] = None,
    height_px: Optional[int] = None,
    crop_mode: str = RENDER_CROP_MODE,
    container_lw: float = RENDER_CONTAINER_LINEWIDTH,
    inner_lw: float = RENDER_INNER_LINEWIDTH,
    pad_px: float = RENDER_PAD_PX,
    align_container: bool = RENDER_ALIGN_CONTAINER,
    container_color: str = RENDER_CONTAINER_COLOR,
    inner_face_color: Optional[str] = None,
    inner_edge_color: str = RENDER_INNER_EDGE_COLOR,
    container_face_color: Optional[str] = None,
    bg_color: Optional[str] = None,
    show_axes: bool = False,
    show_grid: bool = False,
) -> None:
    """
    Render a solution JSON to a PNG with configurable resolution, line widths, crop modes, and styling.
    Automatically applies authentic shape-family color schemes from Erich Friedman's benchmark pages
    unless explicitly overridden.
    """
    try:
        import matplotlib
        matplotlib.use("Agg", force=False)
        import matplotlib.pyplot as plt
    except ImportError:
        print("[WARN] matplotlib is not installed. Skipping PNG rendering.")
        return

    sol = load_solution(sol_path)
    data = to_plot_data(sol, align_container=align_container)

    # Auto-resolve colors from shape family configuration if not explicitly specified
    fam_colors = get_family_colors(sol.inner_token, sol.container_token)
    if inner_face_color is None:
        inner_face_color = fam_colors.get("inner", RENDER_INNER_FACE_COLOR)
    if container_face_color is None:
        container_face_color = fam_colors.get("container", RENDER_BG_COLOR or "#FFFFFF")
    if bg_color is None:
        bg_color = fam_colors.get("container", RENDER_BG_COLOR or "#FFFFFF")

    target_w = width_px or (size_px if size_px else fam_colors.get("width", 240))
    target_h = height_px or (size_px if size_px else fam_colors.get("height", 240))

    if target_w and target_h:
        fig = plt.figure(figsize=(target_w / 72.0, target_h / 72.0), dpi=72)
        ax = fig.add_axes([0, 0, 1, 1])
        render_dpi = 72
    else:
        fig, ax = plt.subplots(figsize=RENDER_FIGURE_SIZE)
        render_dpi = dpi

    if bg_color:
        fig.patch.set_facecolor(bg_color)
        ax.set_facecolor(bg_color)

    is_inner_circle = sol.inner_token.upper() in ("CIRCLE", "CIR")
    is_container_circle = sol.container_token.upper() in ("CIRCLE", "CIR")

    if is_container_circle:
        if container_face_color and container_face_color.lower() != "none":
            c = plt.Circle((0, 0), sol.S, facecolor=container_face_color, edgecolor=container_color, linewidth=container_lw)
            ax.add_patch(c)
        else:
            c = plt.Circle((0, 0), sol.S, color=container_color, fill=False, linewidth=container_lw)
            ax.add_patch(c)
    else:
        container = list(data["container_vertices"]) + [data["container_vertices"][0]]
        if container_face_color and container_face_color.lower() != "none":
            ax.fill(
                [v[0] for v in container],
                [v[1] for v in container],
                facecolor=container_face_color,
                edgecolor=container_color,
                linewidth=container_lw,
            )
        else:
            ax.plot(
                [v[0] for v in container],
                [v[1] for v in container],
                color=container_color,
                linewidth=container_lw,
                solid_capstyle="projecting",
                solid_joinstyle="miter",
            )

    if is_inner_circle:
        for center in data["centers"]:
            c = plt.Circle(center, 1.0, facecolor=inner_face_color, edgecolor=inner_edge_color, linewidth=inner_lw)
            ax.add_patch(c)
    else:
        for poly in data["polygons"]:
            poly_plot = list(poly) + [poly[0]]
            ax.fill(
                [v[0] for v in poly_plot],
                [v[1] for v in poly_plot],
                facecolor=inner_face_color,
                edgecolor=inner_edge_color,
                linewidth=inner_lw,
            )

    crop = (crop_mode or "tight").lower().strip()
    if crop in ("tight", "container"):
        c_verts = np.array(data["container_vertices"])
        xmin, xmax = c_verts[:, 0].min(), c_verts[:, 0].max()
        ymin, ymax = c_verts[:, 1].min(), c_verts[:, 1].max()

        if target_w:
            w_data = xmax - xmin
            pad_data = (pad_px / float(target_w)) * w_data
        else:
            pad_data = pad_px * 0.01 * (xmax - xmin)

        ax.set_xlim(xmin - pad_data, xmax + pad_data)
        ax.set_ylim(ymin - pad_data, ymax + pad_data)
    elif crop in ("circumradius", "radius", "s"):
        ax.set_xlim(-sol.S, sol.S)
        ax.set_ylim(-sol.S, sol.S)
    else:
        ax.autoscale_view()

    ax.set_aspect("equal")
    if not show_axes:
        ax.axis("off")
    if show_grid:
        ax.grid(True, linestyle="--", alpha=0.3)

    if not (target_w and target_h):
        plt.tight_layout()

    fig.savefig(out_png, dpi=render_dpi, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    with open(out_png, "ab") as f:
        f.write(b"made by targed\n")


# --------------- End of solution_tools.py ---------------