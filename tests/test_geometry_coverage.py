"""
Additional tests to improve coverage of geometry.py internals.
"""
import math
import numpy as np
import pytest
from shape_packing.geometry import (
    bh_objective,
    regular_polygon_vertices,
    regular_polygon_outward_normals,
    transform_polygon,
    project_polygon,
    polygon_normals,
    sat_check_overlap,
    _ensure_array,
    get_shape_geometry,
)


class TestEnsureArray:
    def test_list(self):
        x = _ensure_array([1.0, 2.0])
        assert isinstance(x, np.ndarray)

    def test_tuple(self):
        x = _ensure_array((1.0, 2.0))
        assert isinstance(x, np.ndarray)

    def test_already_array(self):
        a = np.array([1.0, 2.0])
        assert _ensure_array(a) is a


class TestTransformPolygonReturnTypes:
    def test_returns_list_if_list(self):
        tri = regular_polygon_vertices(3, radius=0.5)
        poly_list = [(float(v[0]), float(v[1])) for v in tri]
        out = transform_polygon(poly_list, cx=0.0, cy=0.0, a=0.0)
        assert isinstance(out, list)
        assert len(out) == 3
        assert isinstance(out[0], tuple)


class TestNumbaBHObjectivePaths:
    def test_overlap_collision_path(self):
        # Two identical triangles at the same position -> collision -> penalty > 0
        N = 2
        nsi = 3
        unit_polygon_vertices = np.array([
            [0.0, 0.0],
            [0.5, 0.0],
            [0.25, 0.4330127018922193],
        ])
        # Use real edge normals so SAT has axes to check
        unit_polygon_vectors = np.array([
            [0.0, -1.0],
            [np.sqrt(3)/2, 0.5],
            [-np.sqrt(3)/2, 0.5],
        ])
        unit_container_vectors = np.array([
            [1.0, 0.0],
            [0.0, 1.0],
            [-1.0, 0.0],
            [0.0, -1.0],
        ])
        apothem = 1.0
        S = 5.0
        # Same position:
        x0 = np.array([0.0, 0.0, 0.0,
                       0.0, 0.0, 0.0])
        penalty = bh_objective(
            x0, S, N, nsi,
            unit_polygon_vertices, unit_polygon_vectors,
            unit_container_vectors, apothem,
        )
        assert penalty > 0.0

    def test_poking_penalty_path(self):
        # Triangle placed near container boundary -> poking penalty
        N = 1
        nsi = 3
        unit_polygon_vertices = np.array([
            [0.0, 0.0],
            [0.5, 0.0],
            [0.25, 0.4330127018922193],
        ])
        unit_polygon_vectors = np.zeros((3, 2))
        unit_container_vectors = np.array([
            [1.0, 0.0],
            [0.0, 1.0],
            [-1.0, 0.0],
            [0.0, -1.0],
        ])
        apothem = 0.5
        S = 0.5  # very small container -> poking
        x0 = np.array([0.0, 0.0, 0.0])
        penalty = bh_objective(
            x0, S, N, nsi,
            unit_polygon_vertices, unit_polygon_vectors,
            unit_container_vectors, apothem,
        )
        assert penalty > 0.0


class TestSatCheckOverlapTolerance:
    def test_just_touching_within_tolerance(self):
        # Two squares touching at edge -> should be no overlap if within tolerance
        a = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        b = [(1.0, 0.0), (2.0, 0.0), (2.0, 1.0), (1.0, 1.0)]
        na = polygon_normals(a)
        nb = polygon_normals(b)
        overlap, depth = sat_check_overlap(a, b, na, nb, tolerance=1e-12)
        # Ideally no overlap if touching exactly:
        assert overlap is False

    def test_separating_axis_no_overlap(self):
        # Simple horizontal separation
        a = [(0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5)]
        b = [(1.5, 0.0), (2.0, 0.0), (2.0, 0.5), (1.5, 0.5)]
        na = polygon_normals(a)
        nb = polygon_normals(b)
        overlap, _ = sat_check_overlap(a, b, na, nb, tolerance=1e-12)
        assert overlap is False


class TestPolygonNormalsMixedInputs:
    def test_from_list(self):
        poly = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
        normals = polygon_normals(poly)
        assert len(normals) == 3

    def test_from_numpy(self):
        poly = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        normals = polygon_normals(poly)
        assert len(normals) == 3


class TestGetShapeGeometryEdgeCases:
    def test_circle_token(self):
        # Circle maps to 32-sided polygon approximation
        sides, vertices, vectors, apothem = get_shape_geometry("CIRCLE")
        assert sides == 32
        assert vertices.shape[0] == sides

class TestNumbaDirectCoverage:
    """
    Call the Numba-decorated functions directly to ensure their bodies are covered.
    """
    def test_transform_polygon_nb(self):
        from shape_packing.geometry import _transform_polygon_nb
        v = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        out = _transform_polygon_nb(v, 2.0, 3.0, 0.0)
        assert out[0, 0] == pytest.approx(2.0)
        assert out[0, 1] == pytest.approx(3.0)

    def test_rotate_vectors_nb(self):
        from shape_packing.geometry import _rotate_vectors_nb
        vecs = np.array([[1.0, 0.0], [0.0, 1.0]])
        out = _rotate_vectors_nb(0.0, vecs)
        assert np.allclose(out, vecs)

    def test_poking_penalty_nb_no_poke(self):
        from shape_packing.geometry import _poking_penalty_nb
        v = np.array([[0.0, 0.0], [0.1, 0.0]])
        cv = np.array([[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0], [0.0, -1.0]])
        apothem = 1.0
        S = 10.0
        p = _poking_penalty_nb(v, S, cv, apothem)
        assert p == 0.0

    def test_poking_penalty_nb_with_poke(self):
        from shape_packing.geometry import _poking_penalty_nb
        v = np.array([[5.0, 0.0]])  # outside container
        cv = np.array([[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0], [0.0, -1.0]])
        apothem = 1.0
        S = 1.0
        p = _poking_penalty_nb(v, S, cv, apothem)
        assert p > 0.0

    def test_bh_objective_full_path(self):
        # Use bh_objective to ensure all loops run
        N = 3
        nsi = 3
        unit_polys = np.array([
            [0.0, 0.0],
            [0.5, 0.0],
            [0.25, 0.4330127018922193],
        ])
        unit_vecs = np.array([
            [0.0, -1.0],
            [np.sqrt(3)/2, 0.5],
            [-np.sqrt(3)/2, 0.5],
        ])
        unit_container_vectors = np.array([
            [1.0, 0.0],
            [0.0, 1.0],
            [-1.0, 0.0],
            [0.0, -1.0],
        ])
        apothem = 1.0
        S = 5.0
        values = np.array([
            0.0, 0.0, 0.0,
            2.0, 0.0, 0.0,
            -2.0, 0.0, 0.0,
        ])
        penalty = bh_objective(
            values, S, N, nsi,
            unit_polys, unit_vecs,
            unit_container_vectors, apothem,
        )
        assert isinstance(penalty, float)

