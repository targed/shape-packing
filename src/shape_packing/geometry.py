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


def get_shape_geometry(token: str):
    token = str(token).upper()
    if token == "L":
        num_parts = 2
        max_sides = 4
        part_sides = np.array([4, 4], dtype=np.int32)
        part_offsets = np.array([[0.0, -0.5], [-0.5, 0.5]], dtype=float)
        
        vertices = np.zeros((2, 4, 2), dtype=float)
        # Part 0: Domino (2x1)
        vertices[0] = [[-1.0, -0.5], [1.0, -0.5], [1.0, 0.5], [-1.0, 0.5]]
        # Part 1: Square (1x1)
        vertices[1] = [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]]
        
        vectors = np.zeros((2, 4, 2), dtype=float)
        vectors[0] = [[0.0, -1.0], [1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]
        vectors[1] = [[0.0, -1.0], [1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]
        
        apothem = math.sqrt(2.0)
        return num_parts, max_sides, part_sides, part_offsets, vertices, vectors, apothem

    if token == "DOMINO":
        vertices = np.array([[-1.0, -0.5], [1.0, -0.5], [1.0, 0.5], [-1.0, 0.5]])
        vectors = np.array([[0.0, -1.0], [1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]])
        apothem = 0.5
        sides = 4
    elif token == "TAN":
        r = 1.0 - np.sqrt(2.0) / 2.0
        vertices = np.array([[-r, -r], [1.0 - r, -r], [-r, 1.0 - r]])
        vectors = np.array([[0.0, -1.0], [np.sqrt(2.0) / 2.0, np.sqrt(2.0) / 2.0], [-1.0, 0.0]])
        apothem = r
        sides = 3
    elif token in ("CIRCLE", "CIR"):
        sides = 32
        vertices = regular_polygon_vertices(sides, 1.0)
        vectors = regular_polygon_outward_normals(sides)
        apothem = float(np.cos(np.pi / sides))
    else:
        try:
            sides = int(token)
        except ValueError:
            sides = 3
        vertices = regular_polygon_vertices(sides, 1.0)
        vectors = regular_polygon_outward_normals(sides)
        apothem = float(np.cos(np.pi / sides))
        
    num_parts = 1
    max_sides = sides
    part_sides = np.array([sides], dtype=np.int32)
    part_offsets = np.array([[0.0, 0.0]], dtype=float)
    
    vert_arr = np.zeros((1, sides, 2), dtype=float)
    vert_arr[0] = vertices
    
    vec_arr = np.zeros((1, sides, 2), dtype=float)
    vec_arr[0] = vectors
    
    return num_parts, max_sides, part_sides, part_offsets, vert_arr, vec_arr, apothem



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
def _transform_part_nb(vertices, part_sides, part_offset, cx, cy, a):
    n = part_sides
    out = np.zeros_like(vertices)
    sina = math.sin(a)
    cosa = math.cos(a)
    # offset in world space
    ox = part_offset[0] * cosa - part_offset[1] * sina
    oy = part_offset[0] * sina + part_offset[1] * cosa
    for i in range(n):
        vx = vertices[i, 0]
        vy = vertices[i, 1]
        out[i, 0] = cx + ox + (vx * cosa - vy * sina)
        out[i, 1] = cy + oy + (vx * sina + vy * cosa)
    return out

@njit(cache=True)
def _rotate_part_vectors_nb(a, vectors, part_sides):
    n = part_sides
    out = np.zeros_like(vectors)
    sina = math.sin(a)
    cosa = math.cos(a)
    for i in range(n):
        vx = vectors[i, 0]
        vy = vectors[i, 1]
        out[i, 0] = vx * cosa - vy * sina
        out[i, 1] = vx * sina + vy * cosa
    return out

@njit(cache=True)
def _poking_penalty_impl(vertices, part_sides, S, container_vectors, container_sides, apothem):
    penalty = 0.0
    limit = apothem * S
    for v in range(part_sides):
        vx = vertices[v, 0]
        vy = vertices[v, 1]
        for i in range(container_sides):
            d = vx * container_vectors[i, 0] + vy * container_vectors[i, 1]
            if d > limit:
                diff = d - limit
                penalty += diff * diff
    return penalty

def _poking_penalty_nb(*args):
    if len(args) == 4:
        vertices, S, container_vectors, apothem = args
        return _poking_penalty_impl(vertices, len(vertices), float(S), container_vectors, len(container_vectors), float(apothem))
    vertices, part_sides, S, container_vectors, container_sides, apothem = args
    return _poking_penalty_impl(vertices, int(part_sides), float(S), container_vectors, int(container_sides), float(apothem))

def _transform_polygon_nb(vertices, cx, cy, a):
    return _transform_part_nb(vertices, len(vertices), np.array([0.0, 0.0]), cx, cy, a)

def _rotate_vectors_nb(a, vectors):
    return _rotate_part_vectors_nb(a, vectors, len(vectors))

@njit(cache=True)
def _bh_objective_multipart(
    values,
    S,
    N,
    num_parts,
    max_sides,
    part_sides,
    part_offsets,
    unit_polygon_vertices,
    unit_polygon_vectors,
    c_num_parts,
    c_max_sides,
    c_part_sides,
    c_part_offsets,
    unit_container_vertices,
    unit_container_vectors,
    unit_container_apothem,
) -> float:
    penalty = 0.0
    polys = np.zeros((N, num_parts, max_sides, 2))
    vecs = np.zeros((N, num_parts, max_sides, 2))

    # We assume container is always simple (c_num_parts=1) for now
    c_sides = c_part_sides[0]
    c_vecs = unit_container_vectors[0]

    for i in range(N):
        x = values[i * 3]
        y = values[i * 3 + 1]
        a = values[i * 3 + 2]
        for p in range(num_parts):
            polys[i, p] = _transform_part_nb(unit_polygon_vertices[p], part_sides[p], part_offsets[p], x, y, a)
            vecs[i, p] = _rotate_part_vectors_nb(a, unit_polygon_vectors[p], part_sides[p])
            penalty += _poking_penalty_nb(
                polys[i, p], part_sides[p], S, c_vecs, c_sides, unit_container_apothem
            )

    for i in range(N):
        for j in range(i + 1, N):
            for pi in range(num_parts):
                for pj in range(num_parts):
                    collision = True
                    min_overlap = 1e30

                    nsi = part_sides[pi]
                    nsj = part_sides[pj]
                    
                    for vec in range(nsi + nsj):
                        if vec < nsi:
                            ax = vecs[i, pi, vec, 0]
                            ay = vecs[i, pi, vec, 1]
                        else:
                            ax = vecs[j, pj, vec - nsi, 0]
                            ay = vecs[j, pj, vec - nsi, 1]

                        mn1 = 1e30
                        mx1 = -1e30
                        for k in range(nsi):
                            p_val = polys[i, pi, k, 0] * ax + polys[i, pi, k, 1] * ay
                            if p_val < mn1: mn1 = p_val
                            if p_val > mx1: mx1 = p_val

                        mn2 = 1e30
                        mx2 = -1e30
                        for k in range(nsj):
                            p_val = polys[j, pj, k, 0] * ax + polys[j, pj, k, 1] * ay
                            if p_val < mn2: mn2 = p_val
                            if p_val > mx2: mx2 = p_val

                        overlap = min(mx1, mx2) - max(mn1, mn2)
                        if overlap <= 0.0:
                            collision = False
                            break
                        if overlap < min_overlap:
                            min_overlap = overlap

                    if collision:
                        penalty += min_overlap * min_overlap

    return penalty


def bh_objective(*args):
    """
    Objective function supporting both legacy 8-argument signature
    and 16-argument multi-part signature.
    """
    if len(args) == 8:
        values, S, N, nsi, unit_polygon_vertices, unit_polygon_vectors, unit_container_vectors, unit_container_apothem = args
        num_parts = 1
        max_sides = int(nsi)
        part_sides = np.array([max_sides], dtype=np.int32)
        part_offsets = np.array([[0.0, 0.0]], dtype=float)
        vert_arr = np.zeros((1, max_sides, 2), dtype=float)
        vert_arr[0] = unit_polygon_vertices
        vec_arr = np.zeros((1, max_sides, 2), dtype=float)
        vec_arr[0] = unit_polygon_vectors
        c_num_parts = 1
        c_max_sides = len(unit_container_vectors)
        c_part_sides = np.array([c_max_sides], dtype=np.int32)
        c_part_offsets = np.array([[0.0, 0.0]], dtype=float)
        c_vert_arr = np.zeros((1, c_max_sides, 2), dtype=float)
        c_vec_arr = np.zeros((1, c_max_sides, 2), dtype=float)
        c_vec_arr[0] = unit_container_vectors
        return _bh_objective_multipart(
            values, float(S), int(N), num_parts, max_sides, part_sides, part_offsets,
            vert_arr, vec_arr, c_num_parts, c_max_sides, c_part_sides,
            c_part_offsets, c_vert_arr, c_vec_arr, float(unit_container_apothem)
        )
    return _bh_objective_multipart(*args)


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
