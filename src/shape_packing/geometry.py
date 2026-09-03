"""
geometry.py

Single, deep module for all low-level geometry used in this packing project:
- polygon construction
- transforms / rotations
- projections
- SAT-style overlap checks
- boundary / "poking" penalty
- core objective (bh_function)

Design goals:
- Stable interface: callers (polygon_packer, render_solution, verify_solution)
  import from here instead of re-implementing helpers.
- Numba-friendly core functions so performance is preserved.
- No changes to numerical behavior.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
from .packing_config import CIRCLE_SIDES, GEOMETRY_SAT_TOLERANCE

try:
    from numba import njit
except ImportError:
    def njit(*args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            return args[0]
        def decorator(func):
            return func
        return decorator


def _ensure_array(x):
    # Ensure input is np.ndarray so Numba and vector ops are safe.
    if isinstance(x, np.ndarray):
        return x
    if isinstance(x, (list, tuple)):
        return np.array(x, dtype=float)
    return np.array(x, dtype=float)


# ------------ public helpers (non-Numba, for scripts) ------------

def regular_polygon_vertices(sides: int, radius: float = 1.0):
    """
    Vertices of a regular polygon centered at origin.
    If called with numpy inputs or from a numpy-using caller, returns ndarray.
    For simple script use, can be consumed as array-like (v[0], v[1]).
    """
    angles = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    return np.column_stack((radius * np.cos(angles), radius * np.sin(angles)))


def regular_polygon_outward_normals(sides: int):
    """
    Outward normals (one per edge), for a regular polygon.
    """
    angles = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    nangles = angles + np.pi / sides
    return np.column_stack((np.cos(nangles), np.sin(nangles)))


def get_shape_geometry(token: str):
    token = str(token).upper()
    if token == "DOMINO":
        vertices = np.array([[-1.0, -0.5], [1.0, -0.5], [1.0, 0.5], [-1.0, 0.5]])
        vectors = np.array([[0.0, -1.0], [1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]])
        edge_radii = np.array([0.5, 1.0, 0.5, 1.0])
        sides = 4
        return sides, vertices, vectors, edge_radii
        
    if token == "TAN":
        r = 1.0 - np.sqrt(2.0) / 2.0
        vertices = np.array([[-r, -r], [1.0 - r, -r], [-r, 1.0 - r]])
        vectors = np.array([[0.0, -1.0], [np.sqrt(2.0) / 2.0, np.sqrt(2.0) / 2.0], [-1.0, 0.0]])
        edge_radii = np.array([r, r, r])
        sides = 3
        return sides, vertices, vectors, edge_radii
        
    if token == "L":
        vertices = np.array([
            [-5.0/6.0, -5.0/6.0],
            [7.0/6.0, -5.0/6.0],
            [7.0/6.0, 1.0/6.0],
            [1.0/6.0, 1.0/6.0],
            [1.0/6.0, 7.0/6.0],
            [-5.0/6.0, 7.0/6.0],
        ])
        vectors = np.array([
            [0.0, -1.0],
            [1.0, 0.0],
            [0.0, -1.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [-1.0, 0.0],
        ])
        edge_radii = np.array([5.0/6.0, 7.0/6.0, 1.0/6.0, 1.0/6.0, 7.0/6.0, 5.0/6.0])
        sides = 6
        return sides, vertices, vectors, edge_radii

    if token in ("CIRCLE", "CIR"):
        sides = CIRCLE_SIDES
        vertices = regular_polygon_vertices(sides, 1.0)
        vectors = regular_polygon_outward_normals(sides)
        apothem = float(np.cos(np.pi / sides))
        edge_radii = np.full(sides, apothem)
        return sides, vertices, vectors, edge_radii

    # Fallback for numeric tokens
    try:
        sides = int(token)
    except ValueError:
        sides = 3 # default fallback
        
    vertices = regular_polygon_vertices(sides, 1.0)
    vectors = regular_polygon_outward_normals(sides)
    apothem = float(np.cos(np.pi / sides))
    edge_radii = np.full(sides, apothem)
    return sides, vertices, vectors, edge_radii


def get_shape_convex_parts(token: str) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Return a list of (vertices, outward_normals) for each convex component of the shape.
    For convex shapes (polygons, domino, tan), returns a 1-element list with the shape itself.
    For non-convex shapes (like L-tromino), returns the 2-rectangle convex decomposition.
    """
    token = str(token).upper()
    if token == "L":
        part_a_v = np.array([
            [-5.0/6.0, -5.0/6.0],
            [1.0/6.0, -5.0/6.0],
            [1.0/6.0, 7.0/6.0],
            [-5.0/6.0, 7.0/6.0],
        ])
        part_a_n = np.array([
            [0.0, -1.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [-1.0, 0.0],
        ])

        part_b_v = np.array([
            [1.0/6.0, -5.0/6.0],
            [7.0/6.0, -5.0/6.0],
            [7.0/6.0, 1.0/6.0],
            [1.0/6.0, 1.0/6.0],
        ])
        part_b_n = np.array([
            [0.0, -1.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [-1.0, 0.0],
        ])
        return [(part_a_v, part_a_n), (part_b_v, part_b_n)]

    sides, verts, vecs, _ = get_shape_geometry(token)
    return [(verts, vecs)]


def transform_polygon(vertices, cx: float, cy: float, a: float):
    """
    Rotate vertices by angle a about origin, then translate by (cx, cy).
    Accepts list[tuple] or np.ndarray[(n,2)]; returns same type.
    """
    is_list = not isinstance(vertices, np.ndarray)
    v = _ensure_array(vertices)
    cosa = math.cos(a)
    sina = math.sin(a)
    out = np.empty_like(v)
    out[:, 0] = cx + (v[:, 0] * cosa - v[:, 1] * sina)
    out[:, 1] = cy + (v[:, 0] * sina + v[:, 1] * cosa)
    if is_list:
        return [(float(x), float(y)) for x, y in out]
    return out


# ------------ internal geometry config for hot path ------------

class GeoConfig:
    """
    Bundles geometry constants used by bh_objective.
    """
    __slots__ = (
        "N",
        "nsi",
        "nsc",
        "unit_polygon_vertices",
        "unit_polygon_vectors",
        "unit_container_vectors",
        "unit_container_radii",
        "is_inner_circle",
        "is_container_circle",
    )

    def __init__(
        self,
        N: int,
        nsi: int,
        nsc: int,
        unit_polygon_vertices: np.ndarray,
        unit_polygon_vectors: np.ndarray,
        unit_container_vectors: np.ndarray,
        unit_container_radii: np.ndarray,
        is_inner_circle: bool = False,
        is_container_circle: bool = False,
    ):
        self.N = N
        self.nsi = nsi
        self.nsc = nsc
        self.unit_polygon_vertices = _ensure_array(unit_polygon_vertices)
        self.unit_polygon_vectors = _ensure_array(unit_polygon_vectors)
        self.unit_container_vectors = _ensure_array(unit_container_vectors)
        self.unit_container_radii = _ensure_array(unit_container_radii)
        self.is_inner_circle = is_inner_circle
        self.is_container_circle = is_container_circle


# ------------ Numba-accelerated core ------------

@njit(cache=True)
def _transform_polygon_nb(vertices, cx, cy, a):
    n = vertices.shape[0]
    out = np.empty_like(vertices)
    sina = math.sin(a)
    cosa = math.cos(a)
    for i in range(n):
        vx = vertices[i, 0]
        vy = vertices[i, 1]
        out[i, 0] = cx + (vx * cosa - vy * sina)
        out[i, 1] = cy + (vx * sina + vy * cosa)
    return out


@njit(cache=True)
def _rotate_vectors_nb(a, vectors):
    n = vectors.shape[0]
    out = np.empty_like(vectors)
    sina = math.sin(a)
    cosa = math.cos(a)
    for i in range(n):
        vx = vectors[i, 0]
        vy = vectors[i, 1]
        out[i, 0] = vx * cosa - vy * sina
        out[i, 1] = vx * sina + vy * cosa
    return out


@njit(cache=True)
def _poking_penalty_nb(vertices, S, container_vectors, edge_radii, is_inner_circle, is_container_circle, posx, posy):
    penalty = 0.0
    if is_container_circle:
        if is_inner_circle:
            limit = S - 1.0
            if limit > 0.0:
                dist_sq = posx * posx + posy * posy
                if dist_sq > limit * limit:
                    diff = math.sqrt(dist_sq) - limit
                    penalty += diff * diff
            else:
                dist = math.hypot(posx, posy)
                if dist > limit:
                    diff = dist - limit
                    penalty += diff * diff
        else:
            limit = S
            if limit > 0.0:
                limit_sq = limit * limit
                for v in range(vertices.shape[0]):
                    vx = vertices[v, 0]
                    vy = vertices[v, 1]
                    dist_sq = vx * vx + vy * vy
                    if dist_sq > limit_sq:
                        diff = math.sqrt(dist_sq) - limit
                        penalty += diff * diff
            else:
                for v in range(vertices.shape[0]):
                    dist = math.hypot(vertices[v, 0], vertices[v, 1])
                    if dist > limit:
                        diff = dist - limit
                        penalty += diff * diff
    else:
        if is_inner_circle:
            for i in range(container_vectors.shape[0]):
                limit = edge_radii[i] * S - 1.0
                d = posx * container_vectors[i, 0] + posy * container_vectors[i, 1]
                if d > limit:
                    diff = d - limit
                    penalty += diff * diff
        else:
            for v in range(vertices.shape[0]):
                vx = vertices[v, 0]
                vy = vertices[v, 1]
                for i in range(container_vectors.shape[0]):
                    limit = edge_radii[i] * S
                    d = vx * container_vectors[i, 0] + vy * container_vectors[i, 1]
                    if d > limit:
                        diff = d - limit
                        penalty += diff * diff
    return penalty


@njit(cache=True)
def bh_objective(
    values,
    S,
    N,
    nsi,
    unit_polygon_vertices,
    unit_polygon_vectors,
    unit_container_vectors,
    unit_container_radii,
    is_inner_circle=False,
    is_container_circle=False,
) -> float:
    """
    Core objective: penalty for container overflow + overlaps (SAT-style).
    Mirrors polygon_packer.py's bh_function exactly.
    """
    penalty = 0.0
    polys = np.zeros((N, nsi, 2))
    vecs = np.zeros((N, nsi, 2))

    for i in range(N):
        x = values[i * 3]
        y = values[i * 3 + 1]
        a = values[i * 3 + 2]
        polys[i] = _transform_polygon_nb(unit_polygon_vertices, x, y, a)
        vecs[i] = _rotate_vectors_nb(a, unit_polygon_vectors)
        penalty += _poking_penalty_nb(
            polys[i], S, unit_container_vectors, unit_container_radii, is_inner_circle, is_container_circle, x, y
        )

    for i in range(N):
        for j in range(i + 1, N):
            if is_inner_circle:
                dx = values[j * 3] - values[i * 3]
                dy = values[j * 3 + 1] - values[i * 3 + 1]
                dist = math.hypot(dx, dy)
                if dist < 2.0:
                    diff = 2.0 - dist
                    penalty += diff * diff
                continue

            collision = True
            min_overlap = 1e30

            # axes from both polygons
            for vec in range(nsi * 2):
                if vec < nsi:
                    ax = vecs[i, vec, 0]
                    ay = vecs[i, vec, 1]
                else:
                    ax = vecs[j, vec - nsi, 0]
                    ay = vecs[j, vec - nsi, 1]

                # project poly i
                mn1 = 1e30
                mx1 = -1e30
                for k in range(nsi):
                    p = polys[i, k, 0] * ax + polys[i, k, 1] * ay
                    if p < mn1:
                        mn1 = p
                    if p > mx1:
                        mx1 = p

                # project poly j
                mn2 = 1e30
                mx2 = -1e30
                for k in range(nsi):
                    p = polys[j, k, 0] * ax + polys[j, k, 1] * ay
                    if p < mn2:
                        mn2 = p
                    if p > mx2:
                        mx2 = p

                overlap = (mx1 if mx1 < mx2 else mx2) - (mn1 if mn1 > mn2 else mn2)
                if overlap <= 0:
                    collision = False
                    break
                if overlap < min_overlap:
                    min_overlap = overlap

            if collision:
                penalty += min_overlap * min_overlap

    return penalty


# ------------ public helpers for SAT verification (non-Numba) ------------

def project_polygon(normal, vertices):
    """
    Project polygon onto a given axis.
    Returns (min_proj, max_proj).
    """
    v = _ensure_array(vertices)
    n = _ensure_array(normal)
    dots = v @ n
    return float(dots.min()), float(dots.max())



def polygon_normals(vertices):
    """
    Compute outward normals of each edge of a (possibly irregular) polygon.
    Accepts list[tuple] or np.ndarray; returns same style.
    """
    is_list = not isinstance(vertices, np.ndarray)
    v = _ensure_array(vertices)
    diffs = np.roll(v, -1, axis=0) - v
    dx = diffs[:, 0]
    dy = diffs[:, 1]
    lengths = np.hypot(dx, dy)
    lengths = np.where(lengths == 0, 1.0, lengths)
    out = np.column_stack((dy / lengths, -dx / lengths))
    if is_list:
        return [(float(x), float(y)) for x, y in out]
    return out


def sat_check_overlap(poly1, poly2, normals1, normals2,
                      tolerance: float = GEOMETRY_SAT_TOLERANCE):
    """
    Separating Axis Theorem check between two convex polygons.
    Returns:
      - overlap: bool
      - min_overlap: float (minimum penetration depth among tested axes)
    """
    axes = list(normals1) + list(normals2)
    max_overlap = float("inf")

    for axis in axes:
        min1, max1 = project_polygon(axis, poly1)
        min2, max2 = project_polygon(axis, poly2)

        # separating axis -> no overlap
        if max1 <= min2 + tolerance or max2 <= min1 + tolerance:
            return False, 0.0

        overlap = min(max1 - min2, max2 - min1)
        if overlap < max_overlap:
            max_overlap = overlap

    return True, max_overlap
