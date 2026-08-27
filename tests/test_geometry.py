"""
Tests for src/shape_packing/geometry.py

Covers:
- regular_polygon_vertices
- regular_polygon_outward_normals
- transform_polygon
- project_polygon
- polygon_normals
- sat_check_overlap
- bh_objective basic behavior
"""
import math
from typing import List, Tuple
import numpy as np
import pytest

from shape_packing.geometry import (
    regular_polygon_vertices,
    regular_polygon_outward_normals,
    transform_polygon,
    project_polygon,
    polygon_normals,
    sat_check_overlap,
    bh_objective,
)


def vertices_list(v):
    return [(float(x), float(y)) for x, y in v]


class TestRegularPolygonVertices:
    def test_triangle_count(self):
        v = regular_polygon_vertices(3, radius=1.0)
        assert len(v) == 3

    def test_square_count(self):
        v = regular_polygon_vertices(4, radius=1.0)
        assert len(v) == 4

    def test_radius_approx(self):
        v = regular_polygon_vertices(4, radius=1.0)
        # distance from origin should be ~1.0
        for x, y in v:
            d = math.hypot(x, y)
            assert abs(d - 1.0) < 1e-9


class TestOutwardNormals:
    def test_count(self):
        normals = regular_polygon_outward_normals(5)
        assert len(normals) == 5

    def test_unit_length(self):
        normals = regular_polygon_outward_normals(6)
        for nx, ny in normals:
            assert abs(math.hypot(nx, ny) - 1.0) < 1e-9


class TestTransformPolygon:
    def test_translate_only(self):
        tri = regular_polygon_vertices(3, radius=1.0)
        t = transform_polygon(vertices_list(tri), cx=2.0, cy=3.0, a=0.0)
        # Check centroid moved
        cx = sum(x for x, _ in t) / len(t)
        cy = sum(y for _, y in t) / len(t)
        assert abs(cx - 2.0) < 1e-9
        assert abs(cy - 3.0) < 1e-9

    def test_rotate_square_90_deg(self):
        sq = regular_polygon_vertices(4, radius=1.0)
        t = transform_polygon(vertices_list(sq), cx=0.0, cy=0.0, a=math.pi / 2)
        assert len(t) == 4
        # Radius unchanged
        for x, y in t:
            assert abs(math.hypot(x, y) - 1.0) < 1e-9


class TestProjectPolygon:
    def test_simple_projection(self):
        poly = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        axis = (1.0, 0.0)
        mn, mx = project_polygon(axis, poly)
        assert mn == pytest.approx(0.0)
        assert mx == pytest.approx(1.0)

    def test_y_axis(self):
        poly = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        axis = (0.0, 1.0)
        mn, mx = project_polygon(axis, poly)
        assert mn == pytest.approx(0.0)
        assert mx == pytest.approx(1.0)


class TestPolygonNormals:
    def test_square(self):
        poly = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        normals = polygon_normals(poly)
        assert len(normals) == 4
        for n in normals:
            assert abs(math.hypot(*n) - 1.0) < 1e-9


class TestSATOverlap:
    def test_no_overlap(self):
        a = [(0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5)]
        b = [(1.0, 0.0), (1.5, 0.0), (1.5, 0.5), (1.0, 0.5)]
        na = polygon_normals(a)
        nb = polygon_normals(b)
        overlap, depth = sat_check_overlap(a, b, na, nb)
        assert overlap is False

    def test_overlap(self):
        a = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        b = [(0.5, 0.0), (1.5, 0.0), (1.5, 1.0), (0.5, 1.0)]
        na = polygon_normals(a)
        nb = polygon_normals(b)
        overlap, depth = sat_check_overlap(a, b, na, nb)
        assert overlap is True
        assert depth > 0.0


class TestBHObjective:
    def test_triangle_in_square_no_collision(self):
        N = 1
        nsi = 3
        unit_polys = np.array([[0.0, 0.0],
                                [0.5, 0.0],
                                [0.25, 0.4330127018922193]])
        unit_vectors = np.zeros((3, 2))
        unit_container_vectors = np.array([[1.0, 0.0],
                                            [0.0, 1.0],
                                            [-1.0, 0.0],
                                            [0.0, -1.0]])
        edge_radii = np.ones(4)
        S = 10.0
        x0 = np.array([0.0, 0.0, 0.0])
        penalty = bh_objective(
            x0, S, N, nsi,
            unit_polys, unit_vectors,
            unit_container_vectors, edge_radii
        )
        # Large S => shape well inside => penalty very small
        assert penalty < 1e-3

    def test_huge_S_no_poking(self):
        N = 2
        nsi = 3
        unit_polys = np.array([[0.0, 0.0],
                                [0.5, 0.0],
                                [0.25, 0.4330127018922193]])
        unit_vectors = np.zeros((3, 2))
        unit_container_vectors = np.array([[1.0, 0.0],
                                            [0.0, 1.0],
                                            [-1.0, 0.0],
                                            [0.0, -1.0]])
        edge_radii = np.ones(4)
        S = 100.0
        x0 = np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
        penalty = bh_objective(
            x0, S, N, nsi,
            unit_polys, unit_vectors,
            unit_container_vectors, edge_radii
        )
        assert penalty < 1e-4


def test_l_tromino_geometry_and_convex_parts():
    from shape_packing.geometry import get_shape_geometry, get_shape_convex_parts
    sides, verts, vecs, radii = get_shape_geometry("L")
    assert sides == 6
    assert verts.shape == (6, 2)
    # Verify 6 outer vertices and area = 3.0
    # Center of mass:
    # vertices: (-5/6, -5/6), (7/6, -5/6), (7/6, 1/6), (1/6, 1/6), (1/6, 7/6), (-5/6, 7/6)
    expected_v = np.array([
        [-5.0/6.0, -5.0/6.0],
        [7.0/6.0, -5.0/6.0],
        [7.0/6.0, 1.0/6.0],
        [1.0/6.0, 1.0/6.0],
        [1.0/6.0, 7.0/6.0],
        [-5.0/6.0, 7.0/6.0],
    ])
    np.testing.assert_allclose(verts, expected_v, atol=1e-6)

    parts = get_shape_convex_parts("L")
    assert len(parts) == 2  # 2 convex rectangles
    rect_a_verts, rect_a_normals = parts[0]
    rect_b_verts, rect_b_normals = parts[1]
    assert rect_a_verts.shape == (4, 2)
    assert rect_b_verts.shape == (4, 2)
    assert rect_a_normals.shape == (4, 2)
    assert rect_b_normals.shape == (4, 2)
