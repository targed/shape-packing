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
        sides, vertices, vectors, edge_radii = get_shape_geometry("DOMINO")
        assert sides == 4
        assert vertices.shape == (4, 2)
        assert vectors.shape == (4, 2)
        assert abs(edge_radii[0] - 0.5) < 1e-9
        assert abs(edge_radii[1] - 1.0) < 1e-9

    def test_tan_shape(self):
        sides, vertices, vectors, edge_radii = get_shape_geometry("TAN")
        assert sides == 3
        assert vertices.shape == (3, 2)
        assert vectors.shape == (3, 2)
        assert edge_radii[0] > 0.0

    def test_numeric_shape(self):
        sides, vertices, vectors, edge_radii = get_shape_geometry("4")
        assert sides == 4
        assert vertices.shape == (4, 2)
        assert vectors.shape == (4, 2)

    def test_unknown_shape_raises(self):
        # Unknown token should fail loudly instead of silently falling back to triangle
        with pytest.raises(ValueError):
            get_shape_geometry("XYZ")


class TestGeoConfig:
    def test_basic_attributes(self):
        g = GeoConfig(
            N=2,
            nsi=3,
            nsc=4,
            unit_polygon_vertices=np.zeros((3, 2)),
            unit_polygon_vectors=np.zeros((3, 2)),
            unit_container_vectors=np.zeros((4, 2)),
            unit_container_radii=1.0,
        )
        assert g.N == 2
        assert g.nsi == 3
        assert g.nsc == 4
        assert np.all(g.unit_container_radii == 1.0)

    def test_slots_enforcement(self):
        g = GeoConfig(
            N=1,
            nsi=3,
            nsc=3,
            unit_polygon_vertices=np.zeros((3, 2)),
            unit_polygon_vectors=np.zeros((3, 2)),
            unit_container_vectors=np.zeros((3, 2)),
            unit_container_radii=1.0,
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
        unit_container_radii = np.ones(4)
        S = 5.0
        values = np.array([0.0, 0.0, 0.0, 2.0, 0.0, 0.0])

        penalty = bh_objective(
            values, S, N, nsi,
            unit_polygon_vertices, unit_polygon_vectors,
            unit_container_vectors, unit_container_radii
        )
        assert isinstance(penalty, float)

    def test_canonical_quad_geometries_and_strict_unknown(self):
        import math
        from shape_packing.geometry import get_shape_geometry
        for tok in ("RHOMBUS", "PARALLELOGRAM", "TRAPEZOID"):
            sides, verts, vecs, radii = get_shape_geometry(tok)
            assert sides == 4
            assert len(verts) == 4
            assert len(vecs) == 4
            assert np.all(radii > 0)
            # Every vertex satisfies v . vecs[i] <= radii[i] + 1e-12
            for i in range(4):
                dots = verts @ vecs[i]
                assert np.max(dots) <= radii[i] + 1e-12
                # Corresponding edge endpoints saturate dot == radii[i]
                assert abs(float(verts[i] @ vecs[i]) - float(radii[i])) < 1e-12
                assert abs(float(verts[(i + 1) % 4] @ vecs[i]) - float(radii[i])) < 1e-12

        with pytest.raises(ValueError):
            get_shape_geometry("ELLIPSE")
        with pytest.raises(ValueError):
            get_shape_geometry("SEMICIRCLE")

    def test_curved_container_objective_bounds_and_scale_preserves_angles(self):
        from shape_packing.optimization import PackingProblem, build_objective, scale_positions_only
        prob = PackingProblem(N=1, inner_token="CIRCLE", container_token="SEMICIRCLE")
        obj, _ = build_objective(prob)
        assert obj(np.array([0.0, 1.0, 0.5]), 2.0) == 0.0
        assert obj(np.array([0.0, 0.5, 0.5]), 2.0) > 0.0

        scaled = scale_positions_only(np.array([2.0, 4.0, 1.25]), 0.5)
        assert abs(scaled[0] - 1.0) < 1e-12
        assert abs(scaled[1] - 2.0) < 1e-12
        assert abs(scaled[2] - 1.25) < 1e-12

    def test_agent_loop_expanded_area_and_normalization(self):
        import math
        from shape_packing.agent_loop import _get_inner_shape_area, _get_container_shape_area, normalize_problem_name
        assert _get_inner_shape_area("7") is not None
        assert _get_inner_shape_area("9") is not None
        assert _get_inner_shape_area("10") is not None
        assert abs(_get_inner_shape_area("RHOMBUS") - math.sqrt(3.0) / 2.0) < 1e-9
        assert abs(_get_container_shape_area(2.0, "SEMICIRCLE") - 2.0 * math.pi) < 1e-9
        assert abs(_get_container_shape_area(2.0, "QUADRANT") - math.pi) < 1e-9
        assert normalize_problem_name("5_cirinsemi") == "5_CIRCLE_in_SEMICIRCLE"
        assert normalize_problem_name("10_cirinhep") == "10_CIRCLE_in_7"