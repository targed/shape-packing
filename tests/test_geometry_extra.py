"""
Additional tests to improve coverage of src/shape_packing/geometry.py
"""
import numpy as np
import pytest
from shape_packing.geometry import (
    bh_objective,
    GeoConfig,
    get_shape_geometry,
)


class TestGetShapeGeometry:
    def test_domino_shape(self):
        num_parts, max_sides, part_sides, part_offsets, vertices, vectors, apothem = get_shape_geometry("DOMINO")
        assert max_sides == 4
        assert vertices.shape == (1, 4, 2)
        assert vectors.shape == (1, 4, 2)
        assert abs(apothem - 0.5) < 1e-9

    def test_tan_shape(self):
        num_parts, max_sides, part_sides, part_offsets, vertices, vectors, apothem = get_shape_geometry("TAN")
        assert max_sides == 3
        assert vertices.shape == (1, 3, 2)
        assert vectors.shape == (1, 3, 2)
        assert apothem > 0.0

    def test_numeric_shape(self):
        num_parts, max_sides, part_sides, part_offsets, vertices, vectors, apothem = get_shape_geometry("4")
        assert max_sides == 4
        assert vertices.shape == (1, 4, 2)
        assert vectors.shape == (1, 4, 2)

    def test_unknown_shape_fallback(self):
        # Unknown token should trigger ValueError fallback
        num_parts, max_sides, part_sides, part_offsets, vertices, vectors, apothem = get_shape_geometry("XYZ")
        assert max_sides == 3  # default fallback
        assert vertices.shape == (1, 3, 2)


class TestGeoConfig:
    def test_basic_attributes(self):
        g = GeoConfig(
            N=2,
            nsi=3,
            nsc=4,
            unit_polygon_vertices=np.zeros((3, 2)),
            unit_polygon_vectors=np.zeros((3, 2)),
            unit_container_vectors=np.zeros((4, 2)),
            unit_container_apothem=1.0,
        )
        assert g.N == 2
        assert g.nsi == 3
        assert g.nsc == 4
        assert g.unit_container_apothem == 1.0

    def test_slots_enforcement(self):
        g = GeoConfig(
            N=1,
            nsi=3,
            nsc=3,
            unit_polygon_vertices=np.zeros((3, 2)),
            unit_polygon_vectors=np.zeros((3, 2)),
            unit_container_vectors=np.zeros((3, 2)),
            unit_container_apothem=1.0,
        )
        with pytest.raises(AttributeError):
            g.random_extra_field = 123

    def test_bh_objective_with_geometric_shapes(self):
        # Two triangles in square container
        N = 2
        nsi = 3
        unit_polygon_vertices = np.array([
            [0.0, 0.0],
            [1.0, 0.0],
            [0.5, 0.8660254037844386]
        ])
        unit_polygon_vectors = np.zeros((3, 2))
        unit_container_vectors = np.array([
            [1.0, 0.0],
            [0.0, 1.0],
            [-1.0, 0.0],
            [0.0, -1.0]
        ])
        unit_container_apothem = 1.0
        S = 5.0
        values = np.array([0.0, 0.0, 0.0, 2.0, 0.0, 0.0])

        penalty = bh_objective(
            values, S, N, nsi,
            unit_polygon_vertices, unit_polygon_vectors,
            unit_container_vectors, unit_container_apothem
        )
        assert isinstance(penalty, float)