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

import math
import numpy as np

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
    for i in range(v.shape[0]):
        vx = v[i, 0]
        vy = v[i, 1]
        out[i, 0] = cx + (vx * cosa - vy * sina)
        out[i, 1] = cy + (vx * sina + vy * cosa)
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
        "unit_container_apothem",
    )

    def __init__(
        self,
        N: int,
        nsi: int,
        nsc: int,
        unit_polygon_vertices: np.ndarray,
        unit_polygon_vectors: np.ndarray,
        unit_container_vectors: np.ndarray,
        unit_container_apothem: float,
    ):
        self.N = N
        self.nsi = nsi
        self.nsc = nsc
        self.unit_polygon_vertices = unit_polygon_vertices
        self.unit_polygon_vectors = unit_polygon_vectors
        self.unit_container_vectors = unit_container_vectors
        self.unit_container_apothem = unit_container_apothem


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
def _poking_penalty_nb(vertices, S, container_vectors, apothem):
    penalty = 0.0
    limit = apothem * S
    for v in range(vertices.shape[0]):
        vx = vertices[v, 0]
        vy = vertices[v, 1]
        for i in range(container_vectors.shape[0]):
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
    unit_container_apothem,
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
            polys[i], S, unit_container_vectors, unit_container_apothem
        )

    for i in range(N):
        for j in range(i + 1, N):
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
    min_proj = float("inf")
    max_proj = float("-inf")
    nx, ny = normal[0], normal[1]
    for v in vertices:
        p = nx * v[0] + ny * v[1]
        if p < min_proj:
            min_proj = p
        if p > max_proj:
            max_proj = p
    return min_proj, max_proj


def polygon_normals(vertices):
    """
    Compute outward normals of each edge of a (possibly irregular) polygon.
    Accepts list[tuple] or np.ndarray; returns same style.
    """
    is_list = not isinstance(vertices, np.ndarray)
    v = _ensure_array(vertices)
    normals = []
    n = v.shape[0]
    for i in range(n):
        p1 = v[i]
        p2 = v[(i + 1) % n]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        normals.append((dy / length, -dx / length))
    return normals


def sat_check_overlap(poly1, poly2, normals1, normals2,
                      tolerance: float = 1e-12):
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
