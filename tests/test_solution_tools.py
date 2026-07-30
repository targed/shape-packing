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
)


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

    def test_unsupported_format(self, tmp_path):
        # Missing both 'values' and 'positions'
        data = {"N": 2}
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="Unsupported solution JSON format"):
            load_solution(str(p))


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
    def test_render_basic(self, sample_solution_values):
        from shape_packing.solution_tools import render_solution
        import os
        render_solution(sample_solution_values)
        assert os.path.exists("solution.png")
        os.remove("solution.png")

    def test_render_with_flags(self, sample_solution_values):
        from shape_packing.solution_tools import render_solution
        import os
        render_solution(sample_solution_values, show_axes=True, show_grid=True)
        assert os.path.exists("solution.png")
        os.remove("solution.png")
