"""
Tests for src/shape_packing/solution_tools.py

Covers:
- load_solution (values-style and positions-style)
- build_polygons
- verify_solution:
  - metric scaling consistency
  - container bounds
  - overlap checks
  - record comparison via reference TSV
- to_plot_data shape
"""
import os
import json
import pytest
from shape_packing.solution_tools import (
    load_solution,
    build_polygons,
    verify_solution,
    load_best_value,
    to_plot_data,
    Solution,
    TOLERANCE,
    inverse_friedman_metric,
    compute_friedman_metric,
    get_container_rotation_offset,
)
import math


class TestGetContainerRotationOffset:
    def test_special_tokens_return_zero(self):
        for token in ("CIRCLE", "CIR", "DOMINO", "TAN", "L", "  circle  ", "tan"):
            assert get_container_rotation_offset(token) == 0.0

    def test_odd_sides_return_pi_over_2(self):
        for token in ("3", "5", "7", "9"):
            assert get_container_rotation_offset(token) == pytest.approx(math.pi / 2.0)

    def test_even_sides_multiple_of_4_return_pi_over_n(self):
        # 4 // 2 = 2 (even) -> pi / 4
        assert get_container_rotation_offset("4") == pytest.approx(math.pi / 4.0)
        # 8 // 2 = 4 (even) -> pi / 8
        assert get_container_rotation_offset("8") == pytest.approx(math.pi / 8.0)
        # 12 // 2 = 6 (even) -> pi / 12
        assert get_container_rotation_offset("12") == pytest.approx(math.pi / 12.0)

    def test_even_sides_not_multiple_of_4_return_zero(self):
        # 6 // 2 = 3 (odd) -> 0.0
        assert get_container_rotation_offset("6") == 0.0
        # 10 // 2 = 5 (odd) -> 0.0
        assert get_container_rotation_offset("10") == 0.0

    def test_invalid_tokens_return_zero(self):
        for token in ("invalid", "abc", "", "   "):
            assert get_container_rotation_offset(token) == 0.0


def test_inverse_friedman_metric():
    # Regular polygon
    f_val = compute_friedman_metric(3.0, "3", "4")
    assert abs(inverse_friedman_metric(f_val, "3", "4") - 3.0) < 1e-9
    
    # Special shapes
    f_val = compute_friedman_metric(2.0, "TAN", "CIRCLE")
    assert abs(inverse_friedman_metric(f_val, "TAN", "CIRCLE") - 2.0) < 1e-9

    # L-tromino container scaling:
    # 1. With circle inner (i_scale = 1.0): S = 1.70710678 gives Friedman metric s = 2 * S = 3.41421356 (Friedman 1_cirinl benchmark)
    s_cirinl = compute_friedman_metric(1.70710678, "CIRCLE", "L")
    assert abs(s_cirinl - 3.41421356) < 1e-6
    assert abs(inverse_friedman_metric(3.41421356, "CIRCLE", "L") - 1.70710678) < 1e-6

    # 2. With square inner (i_scale = sqrt(2)): S = sqrt(2) gives Friedman metric s = 2.0 (Friedman 1_squinl benchmark)
    s_squinl = compute_friedman_metric(math.sqrt(2.0), "4", "L")
    assert abs(s_squinl - 2.0) < 1e-9
    assert abs(inverse_friedman_metric(2.0, "4", "L") - math.sqrt(2.0)) < 1e-9

    # 3. Named polygon tokens: "square" must match "4", "pentagon" must match "5"
    assert compute_friedman_metric(math.sqrt(2.0), "square", "L") == pytest.approx(2.0)
    assert inverse_friedman_metric(2.0, "square", "L") == pytest.approx(math.sqrt(2.0))
    assert compute_friedman_metric(1.5, "pentagon", "circle") == pytest.approx(compute_friedman_metric(1.5, "5", "circle"))

    # 4. LinL (L-in-L container): metric is the linear dilation factor S (Friedman 1_LinL benchmark = 1.0)
    assert compute_friedman_metric(1.0, "L", "L") == 1.0
    assert compute_friedman_metric(2.5, "L", "L") == 2.5
    assert inverse_friedman_metric(1.0, "L", "L") == 1.0
    assert inverse_friedman_metric(2.5, "L", "L") == 2.5

class TestLoadSolutionValuesStyle:
    def test_load_basic(self, sample_solution_values):
        sol = load_solution(sample_solution_values)
        assert isinstance(sol, Solution)
        assert sol.N == 4
        assert len(sol.values) == sol.N * 3

    def test_reads_inner_and_container_token(self, tmp_path):
        data = {
            "N": 3,
            "inner_token": "3",
            "container_token": "5",
            "S": 1.2,
            "final_metric": 0.9,
            "values": [0.0, 0.0, 0.0,
                       0.1, 0.0, 0.0,
                       -0.1, 0.0, 0.0],
        }
        p = tmp_path / "s.json"
        p.write_text(json.dumps(data))
        sol = load_solution(str(p))
        assert sol.inner_token == "3"
        assert sol.container_token == "5"


class TestLoadSolutionPositionsStyle:
    def test_load_basic(self, sample_solution_positions):
        sol = load_solution(sample_solution_positions)
        assert isinstance(sol, Solution)
        assert len(sol.values) == sol.N * 3


class TestBuildPolygons:
    def test_count(self, sample_solution_values):
        sol = load_solution(sample_solution_values)
        polys = build_polygons(sol)
        assert len(polys) == sol.N

    def test_vertex_count(self, sample_solution_values):
        sol = load_solution(sample_solution_values)
        polys = build_polygons(sol)
        # inner_token defaults to 3 -> triangles
        for poly in polys:
            assert len(poly) >= 3


class TestLoadBestValue:
    def test_not_found(self, sample_tsv_reference):
        val = load_best_value(
            reference_path=sample_tsv_reference,
            problem_str="999_3_in_3",
        )
        assert val is None

    def test_found(self, sample_tsv_reference):
        val = load_best_value(
            reference_path=sample_tsv_reference,
            problem_str="8_3_in_5",
        )
        assert val is not None
        assert abs(val - 2.0) < 1e-9


class TestVerifySolution:
    def test_valid_no_overlap_small(self, tmp_path, sample_tsv_reference):
        # Tiny, well-separated triangles inside square.
        data = {
            "N": 2,
            "inner_token": "3",
            "container_token": "4",
            "S": 5.0,
            "final_metric": 3.0,
            "values": [0.0, 0.0, 0.0,
                       1.0, 0.0, 0.0],
        }
        p = tmp_path / "sol.json"
        p.write_text(json.dumps(data))
        res = verify_solution(
            sol_path=str(p),
            problem_str="8_3_in_5",
            tolerance=1e-6,
            check_record=True,
            reference_path=sample_tsv_reference,
        )
        # May not be new record, but must be structurally valid or have understandable errors
        # Here we mainly check no crash and fields present
        assert hasattr(res, "valid")
        assert hasattr(res, "metric")
        assert isinstance(res.errors, list)

    def test_overlap_detected(self, tmp_path):
        # Two overlapping triangles (same position)
        data = {
            "N": 2,
            "inner_token": "3",
            "container_token": "4",
            "S": 2.0,
            "final_metric": 1.0,
            "values": [0.0, 0.0, 0.0,
                       0.0, 0.0, 0.0],
        }
        p = tmp_path / "sol_overlapping.json"
        p.write_text(json.dumps(data))
        res = verify_solution(
            sol_path=str(p),
            problem_str="8_3_in_5",
            tolerance=TOLERANCE,
            check_record=False,
        )
        assert not res.valid
        assert any("overlap" in e.lower() for e in res.errors)

    def test_metric_scaling_mismatch(self, tmp_path):
        # Intentionally wrong final_metric.
        data = {
            "N": 3,
            "inner_token": "3",
            "container_token": "4",
            "S": 1.0,
            "final_metric": 999.0,  # intentionally bad
            "values": [0.0, 0.0, 0.0,
                       0.5, 0.0, 0.0,
                       -0.5, 0.0, 0.0],
        }
        p = tmp_path / "sol_bad_metric.json"
        p.write_text(json.dumps(data))
        res = verify_solution(
            sol_path=str(p),
            problem_str="8_3_in_5",
            tolerance=TOLERANCE,
            check_record=False,
        )
        assert not res.valid
        assert any("Metric scaling" in e for e in res.errors)

    def test_verify_l_container_squinl(self, tmp_path):
        """Verify that a 1-square packing in an L-container scales as s = 2S and verifies bounds."""
        S = math.sqrt(2.0)
        s_metric = 2.0
        # Square placed in lower-left arm [-5/6 S, 1/6 S] x [-5/6 S, 1/6 S]
        cx = -math.sqrt(2.0) / 3.0
        cy = -math.sqrt(2.0) / 3.0
        data = {
            "problem": "1_squinl",
            "N": 1,
            "inner_token": "4",
            "container_token": "L",
            "S": S,
            "final_metric": s_metric,
            "values": [cx, cy, math.pi / 4.0],
        }
        p = tmp_path / "sol_squinl.json"
        p.write_text(json.dumps(data))
        res = verify_solution(str(p), "1_squinl", check_record=False)
        assert res.valid
        assert res.errors == []
        assert abs(res.metric - 2.0) < 1e-6

    def test_verify_l_container_cirinl(self, tmp_path):
        """Verify that a 1-circle packing in an L-container scales as s = 2S and verifies reflex corner."""
        S = 1.0 + math.sqrt(2.0) / 2.0
        s_metric = 2.0 * S
        # Circle tangent to left and bottom walls: x = -5/6 S + 1, y = -5/6 S + 1
        cx = -5.0 / 6.0 * S + 1.0
        cy = -5.0 / 6.0 * S + 1.0
        data = {
            "problem": "1_cirinl",
            "N": 1,
            "inner_token": "CIRCLE",
            "container_token": "L",
            "S": S,
            "final_metric": s_metric,
            "values": [cx, cy, 0.0],
        }
        p = tmp_path / "sol_cirinl.json"
        p.write_text(json.dumps(data))
        res = verify_solution(str(p), "1_cirinl", check_record=False)
        assert res.valid
        assert res.errors == []
        assert abs(res.metric - (2.0 + math.sqrt(2.0))) < 1e-6


class TestLoadSolutionError:
    def test_unsupported_format(self, tmp_path):
        # Missing both 'values' and 'positions'
        data = {"N": 2}
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="Unsupported solution JSON format"):
            load_solution(str(p))


class TestLoadBestValueEdgeCases:
    def test_file_not_exists(self):
        val = load_best_value(
            reference_path="nonexistent.tsv",
            problem_str="1_3_in_3",
        )
        assert val is None

    def test_short_line_skipped(self, tmp_path):
        ref = tmp_path / "ref.tsv"
        ref.write_text("id\tproblem_family\n")
        val = load_best_value(
            reference_path=str(ref),
            problem_str="1_3_in_3",
        )
        assert val is None

    def test_float_error_returns_none(self, tmp_path):
        ref = tmp_path / "ref.tsv"
        ref.write_text(
            "id\tproblem_family\tBADVALUE\tstatus\tsource\t1_3_in_3\n"
        )
        val = load_best_value(
            reference_path=str(ref),
            problem_str="1_3_in_3",
        )
        assert val is None


class TestVerifyRecordCheck:
    def test_valid_new_record(self, tmp_path):
        # Create reference where best_value is large, so our calc_metric is better.
        ref = tmp_path / "ref.tsv"
        ref.write_text(
            "id\tfamily\t9.0\tbest_known\tnote\t1_3_in_3\n"
        )

        # Build a valid, tiny solution:
        # One triangle at origin in a large square.
        # final_metric will be recomputed from S; we must ensure geometry is valid.
        S = 5.0
        # calc_metric = S * sin(pi/4) / sin(pi/3)
        import math
        nsi = 3
        nsc = 4
        final_metric = S * math.sin(math.pi / nsc) / math.sin(math.pi / nsi)

        data = {
            "N": 1,
            "inner_token": "3",
            "container_token": "4",
            "S": S,
            "final_metric": final_metric,
            "values": [0.0, 0.0, 0.0],
        }
        p = tmp_path / "sol.json"
        p.write_text(json.dumps(data))

        res = verify_solution(
            sol_path=str(p),
            problem_str="1_3_in_3",
            tolerance=1e-15,
            check_record=True,
            reference_path=str(ref),
        )

        # Must be valid and new_record True (calc_metric ~2.68 < 9.0)
        assert res.valid is True
        assert res.new_record is True
        assert "NEW RECORD" in res.message

    def test_valid_no_new_record(self, tmp_path):
        # best_value very small so we cannot beat it.
        ref = tmp_path / "ref.tsv"
        ref.write_text(
            "id\tfamily\t0.0001\tbest_known\tnote\t1_3_in_3\n"
        )

        S = 5.0
        import math
        nsi = 3
        nsc = 4
        final_metric = S * math.sin(math.pi / nsc) / math.sin(math.pi / nsi)

        data = {
            "N": 1,
            "inner_token": "3",
            "container_token": "4",
            "S": S,
            "final_metric": final_metric,
            "values": [0.0, 0.0, 0.0],
        }
        p = tmp_path / "sol.json"
        p.write_text(json.dumps(data))

        res = verify_solution(
            sol_path=str(p),
            problem_str="1_3_in_3",
            tolerance=1e-15,
            check_record=True,
            reference_path=str(ref),
        )

        # Valid but not a new record
        assert res.valid is True
        assert res.new_record is False
        assert "Valid configuration" in res.message

    def test_valid_new_record_message(self, tmp_path):
        # Another case: different problem, just to ensure branch coverage
        ref = tmp_path / "ref.tsv"
        ref.write_text(
            "id\tfamily\t9.0\tbest_known\tnote\t2_3_in_4\n"
        )

        S = 10.0
        import math
        nsi = 3
        nsc = 4
        final_metric = S * math.sin(math.pi / nsc) / math.sin(math.pi / nsi)

        data = {
            "N": 2,
            "inner_token": "3",
            "container_token": "4",
            "S": S,
            "final_metric": final_metric,
            "values": [0.0, 0.0, 0.0, 5.0, 0.0, 0.0],  # far apart
        }
        p = tmp_path / "sol.json"
        p.write_text(json.dumps(data))

        res = verify_solution(
            sol_path=str(p),
            problem_str="2_3_in_4",
            tolerance=1e-15,
            check_record=True,
            reference_path=str(ref),
        )

        assert res.valid is True
        assert res.new_record is True
        assert "NEW RECORD" in res.message

    def test_load_best_value_file_not_exists(self):
        val = load_best_value(
            reference_path="nonexistent.tsv",
            problem_str="1_3_in_3",
        )
        assert val is None

    def test_load_best_value_short_line(self, tmp_path):
        ref = tmp_path / "ref.tsv"
        ref.write_text("id\tfamily\n")
        val = load_best_value(
            reference_path=str(ref),
            problem_str="1_3_in_3",
        )
        assert val is None

    def test_load_best_value_float_error(self, tmp_path):
        ref = tmp_path / "ref.tsv"
        ref.write_text(
            "id\tfamily\tNOT_NUMBER\tstatus\tsource\t1_3_in_3\n"
        )
        val = load_best_value(
            reference_path=str(ref),
            problem_str="1_3_in_3",
        )
        assert val is None

    def test_load_reference_map_caching(self, tmp_path):
        from src.shape_packing.solution_tools import load_reference_map
        ref = tmp_path / "ref.tsv"
        ref.write_text("id\tfamily\t1.2345\tstatus\tsource\t1_3_in_3\n")
        
        m1 = load_reference_map(str(ref))
        assert m1.get("1_3_in_3") == 1.2345
        
        # Second call returns cached dictionary
        m2 = load_reference_map(str(ref))
        assert m1 is m2
        assert load_best_value(str(ref), "1_3_in_3") == 1.2345

    def test_unsupported_format(self, tmp_path):
        # Missing both 'values' and 'positions'
        data = {"N": 2}
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="Unsupported solution JSON format"):
            load_solution(str(p))

    def test_extracted_verification_helpers(self, sample_solution_values):
        from src.shape_packing.solution_tools import (
            _verify_metric_scaling,
            _verify_container_bounds,
            _verify_overlap,
            _check_new_record,
            get_shape_geometry,
            build_polygons,
        )
        sol = load_solution(sample_solution_values)
        _, _, unit_container_vectors, unit_container_radii = get_shape_geometry(sol.container_token)
        polygons = build_polygons(sol)

        # Metric scaling
        errs_metric = _verify_metric_scaling(sol, sol.final_metric)
        assert len(errs_metric) == 0

        errs_metric_bad = _verify_metric_scaling(sol, sol.final_metric + 1.0)
        assert len(errs_metric_bad) == 1

        # Bounds
        errs_bounds = _verify_container_bounds(
            sol, polygons, unit_container_vectors, unit_container_radii, 1e-6
        )
        assert isinstance(errs_bounds, list)

        # Overlap
        errs_overlap = _verify_overlap(sol, polygons, 1e-6)
        assert isinstance(errs_overlap, list)

        # Record check
        is_rec = _check_new_record(sol.final_metric, None, False, "nonexistent.tsv", 1e-6)
        assert is_rec is False


class TestToPlotData:
    def test_structure(self, sample_solution_values):
        sol = load_solution(sample_solution_values)
        d = to_plot_data(sol)
        assert "container_vertices" in d
        assert "polygons" in d
        assert "centers" in d
        assert isinstance(d["centers"], list)
        assert len(d["polygons"]) == sol.N


class TestRenderSolution:
    def test_render_basic(self, sample_solution_values, tmp_path, monkeypatch):
        pytest.importorskip("matplotlib")
        from shape_packing.solution_tools import render_solution
        import os
        monkeypatch.chdir(tmp_path)
        render_solution(sample_solution_values)
        assert os.path.exists("solution.png")
        os.remove("solution.png")

    def test_render_with_flags(self, sample_solution_values, tmp_path, monkeypatch):
        pytest.importorskip("matplotlib")
        from shape_packing.solution_tools import render_solution
        import os
        monkeypatch.chdir(tmp_path)
        render_solution(sample_solution_values, show_axes=True, show_grid=True)
        assert os.path.exists("solution.png")
        os.remove("solution.png")

    def test_render_with_custom_styling_and_dimensions(self, sample_solution_values, tmp_path):
        pytest.importorskip("matplotlib")
        from shape_packing.solution_tools import render_solution
        from PIL import Image
        out_png = str(tmp_path / "custom_243.png")

        render_solution(
            sample_solution_values,
            out_png=out_png,
            size_px=243,
            crop_mode="tight",
            container_lw=2.0,
            inner_lw=1.0,
            pad_px=1.0,
            container_color="#000000",
            inner_face_color="#CCCCCC",
            inner_edge_color="#000000",
            bg_color="#FFFFFF",
            align_container=True,
        )

        assert (tmp_path / "custom_243.png").exists()
        img = Image.open(out_png)
        assert img.size == (243, 243)

    def test_render_import_error(self, sample_solution_values, monkeypatch, capsys):
        from shape_packing.solution_tools import render_solution
        import sys
        monkeypatch.setitem(sys.modules, "matplotlib", None)
        render_solution(sample_solution_values, "dummy.png")
        captured = capsys.readouterr()
        assert "[WARN] matplotlib is not installed" in captured.out


class TestDecoupledRecordImprovement:
    def test_check_new_record_decoupled(self, tmp_path):
        from shape_packing.solution_tools import _check_new_record
        ref_file = tmp_path / "ref.tsv"
        ref_file.write_text("id\tfamily\t1.500000\tbest_known\tnote\t3_3_in_4\n")

        # Metric slightly better than 1.500000 by 1e-6 (less than default 1e-5 min_improvement)
        calc_metric = 1.499999
        assert not _check_new_record(calc_metric, "3_3_in_4", True, str(ref_file), min_improvement=1e-5)

        # But with min_improvement=1e-7, it is recognized
        assert _check_new_record(calc_metric, "3_3_in_4", True, str(ref_file), min_improvement=1e-7)

        # Metric better by 1e-4 is recognized under default 1e-5
        assert _check_new_record(1.499900, "3_3_in_4", True, str(ref_file))

    def test_verify_solution_with_custom_min_improvement(self, tmp_path):
        ref = tmp_path / "ref.tsv"
        ref.write_text("id\tfamily\t10.0\tbest_known\tnote\t1_3_in_4\n")

        S = 5.0
        nsi = 3
        nsc = 4
        final_metric = S * math.sin(math.pi / nsc) / math.sin(math.pi / nsi)

        data = {
            "N": 1,
            "inner_token": "3",
            "container_token": "4",
            "S": S,
            "final_metric": final_metric,
            "values": [0.0, 0.0, 0.0],
        }
        p = tmp_path / "sol.json"
        p.write_text(json.dumps(data))

        res = verify_solution(
            sol_path=str(p),
            problem_str="1_3_in_4",
            reference_path=str(ref),
            min_improvement=1e-5,
        )
        assert res.valid is True
        assert res.new_record is True


class TestLTrominoVerification:
    def test_verify_l_tromino_solution(self, tmp_path):
        # 1 L-tromino inside a square container
        S = 3.0
        final_metric = 2 * S * math.sin(math.pi / 4)
        data = {
            "N": 1,
            "inner_token": "L",
            "container_token": "4",
            "S": S,
            "final_metric": final_metric,
            "values": [0.0, 0.0, 0.0],
        }
        p = tmp_path / "l_sol.json"
        p.write_text(json.dumps(data))

        res = verify_solution(
            sol_path=str(p),
            problem_str="1_L_in_4",
            check_record=False,
        )
        assert res.valid is True
        assert len(res.errors) == 0

    def test_verify_l_tromino_overlap(self, tmp_path):
        # 2 L-trominoes colliding directly at origin
        S = 10.0
        final_metric = 2 * S * math.sin(math.pi / 4)
        data = {
            "N": 2,
            "inner_token": "L",
            "container_token": "4",
            "S": S,
            "final_metric": final_metric,
            "values": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }
        p = tmp_path / "l_overlap.json"
        p.write_text(json.dumps(data))

        res = verify_solution(
            sol_path=str(p),
            problem_str="2_L_in_4",
            check_record=False,
        )
        assert res.valid is False
        assert any("overlap" in e for e in res.errors)

    def test_verify_l_container_valid(self, tmp_path):
        # 1 TAN triangle in horizontal branch of L container
        # Horizontal branch: [1/6 S, 7/6 S] x [-5/6 S, 1/6 S]
        # At S = 3.0: [0.5, 3.5] x [-2.5, 0.5]
        # Place TAN centered at (1.5, -1.0)
        # For L container, Friedman metric s = 2.0 * S = 6.0
        data = {
            "N": 1,
            "inner_token": "TAN",
            "container_token": "L",
            "S": 3.0,
            "final_metric": 6.0,
            "values": [1.5, -1.0, 0.0],
        }
        p = tmp_path / "tan_in_l.json"
        p.write_text(json.dumps(data))

        res = verify_solution(
            sol_path=str(p),
            problem_str="1_TAN_in_L",
            check_record=False,
        )
        assert res.valid is True
        assert len(res.errors) == 0

    def test_verify_l_container_cutout_violation(self, tmp_path):
        # Place shape in top-right reflex cut-out: [1/6 S, 7/6 S] x [1/6 S, 7/6 S]
        # At S = 3.0: [0.5, 3.5] x [0.5, 3.5]
        # Place shape centered at (2.0, 2.0)
        # For L container, Friedman metric s = 2.0 * S = 6.0
        data = {
            "N": 1,
            "inner_token": "TAN",
            "container_token": "L",
            "S": 3.0,
            "final_metric": 6.0,
            "values": [2.0, 2.0, 0.0],
        }
        p = tmp_path / "tan_in_l_cutout.json"
        p.write_text(json.dumps(data))

        res = verify_solution(
            sol_path=str(p),
            problem_str="1_TAN_in_L",
            check_record=False,
        )
        assert res.valid is False
        assert any("reflex cut-out" in e for e in res.errors)


class TestExpandedShapeVerification:
    def test_verify_circle_in_semicircle_exact(self, tmp_path):
        # N=1 circle in semicircle: center (0, 1.0) touches chord y=0 and arc at S=2.0
        p = tmp_path / "circle_in_semi.json"
        p.write_text(json.dumps({
            "N": 1, "inner_token": "CIRCLE", "container_token": "SEMICIRCLE",
            "S": 2.0, "final_metric": 2.0, "values": [0.0, 1.0, 0.0],
        }))
        res = verify_solution(str(p), problem_str="1_CIRCLE_in_SEMICIRCLE", check_record=False)
        assert res.valid is True

        # Violates flat chord bound (y < 1.0)
        p_bad = tmp_path / "circle_in_semi_bad.json"
        p_bad.write_text(json.dumps({
            "N": 1, "inner_token": "CIRCLE", "container_token": "SEMICIRCLE",
            "S": 2.0, "final_metric": 2.0, "values": [0.0, 0.99, 0.0],
        }))
        res_bad = verify_solution(str(p_bad), problem_str="1_CIRCLE_in_SEMICIRCLE", check_record=False)
        assert res_bad.valid is False

    def test_verify_circle_in_quadrant_exact(self, tmp_path):
        import math
        s_exact = 1.0 + math.sqrt(2.0)
        p = tmp_path / "circle_in_quad.json"
        p.write_text(json.dumps({
            "N": 1, "inner_token": "CIRCLE", "container_token": "QUADRANT",
            "S": s_exact, "final_metric": s_exact, "values": [1.0, 1.0, 0.0],
        }))
        res = verify_solution(str(p), problem_str="1_CIRCLE_in_QUADRANT", check_record=False)
        assert res.valid is True

        # Violates x < 1.0 wall
        p_bad = tmp_path / "circle_in_quad_bad.json"
        p_bad.write_text(json.dumps({
            "N": 1, "inner_token": "CIRCLE", "container_token": "QUADRANT",
            "S": s_exact, "final_metric": s_exact, "values": [0.99, 1.0, 0.0],
        }))
        res_bad = verify_solution(str(p_bad), problem_str="1_CIRCLE_in_QUADRANT", check_record=False)
        assert res_bad.valid is False

    def test_verify_circle_in_canonical_quads_exact(self, tmp_path):
        import math
        cases = [
            ("RHOMBUS", 4.0 / math.sqrt(3.0)),
            ("PARALLELOGRAM", 2.0 * math.sqrt(2.0)),
            ("TRAPEZOID", 4.0 / math.sqrt(3.0)),
        ]
        for container, s_val in cases:
            p = tmp_path / f"circle_in_{container.lower()}.json"
            p.write_text(json.dumps({
                "N": 1, "inner_token": "CIRCLE", "container_token": container,
                "S": s_val, "final_metric": s_val, "values": [0.0, 0.0, 0.0],
            }))
            res = verify_solution(str(p), problem_str=f"1_CIRCLE_in_{container}", check_record=False)
            assert res.valid is True, f"Failed valid check for {container}: {res.errors}"

            # Shrink by 1% -> invalid
            p_bad = tmp_path / f"circle_in_{container.lower()}_bad.json"
            p_bad.write_text(json.dumps({
                "N": 1, "inner_token": "CIRCLE", "container_token": container,
                "S": s_val * 0.99, "final_metric": s_val * 0.99, "values": [0.0, 0.0, 0.0],
            }))
            res_bad = verify_solution(str(p_bad), problem_str=f"1_CIRCLE_in_{container}", check_record=False)
            assert res_bad.valid is False, f"Failed rejection check for {container}"

    def test_reject_non_circle_in_semicircle_and_unknown_token(self, tmp_path):
        p_non_cir = tmp_path / "sq_in_semi.json"
        p_non_cir.write_text(json.dumps({
            "N": 1, "inner_token": "4", "container_token": "SEMICIRCLE",
            "S": 3.0, "final_metric": 3.0, "values": [0.0, 1.0, 0.0],
        }))
        with pytest.raises(ValueError):
            verify_solution(str(p_non_cir), check_record=False)

        p_unk = tmp_path / "unk.json"
        p_unk.write_text(json.dumps({
            "N": 1, "inner_token": "CIRCLE", "container_token": "ELLIPSE",
            "S": 2.0, "final_metric": 2.0, "values": [0.0, 0.0, 0.0],
        }))
        with pytest.raises(ValueError):
            verify_solution(str(p_unk), check_record=False)



