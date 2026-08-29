"""
Tests for src/shape_packing/ranker.py

Covers:
- polygon_area
- get_shape_area (polygons, circle, tan, domino, L)
- generate_queue integration with packingVerification
"""
import math
import json
import os
import pytest
from shape_packing.ranker import (
    polygon_area,
    get_shape_area,
    generate_queue,
)


class TestPolygonArea:
    def test_equilateral_triangle(self):
        # side 1, area = (sqrt(3)/4)*1^2
        area = polygon_area(3, 1.0)
        assert abs(area - math.sqrt(3) / 4) < 1e-9

    def test_square(self):
        area = polygon_area(4, 1.0)
        assert abs(area - 1.0) < 1e-9

    def test_positive(self):
        assert polygon_area(6, 2.0) > 0.0


class TestGetShapeArea:
    def test_triangle(self):
        a = get_shape_area("3", 1.0)
        assert a is not None and a > 0

    def test_triangle_alias(self):
        a = get_shape_area("triangle", 1.0)
        assert a is not None and a > 0

    def test_square(self):
        a = get_shape_area("4", 1.0)
        assert a is not None and abs(a - 1.0) < 1e-9

    def test_hexagon(self):
        a = get_shape_area("6", 1.0)
        assert a is not None and a > 0

    def test_circle(self):
        r = 2.0
        a = get_shape_area("circle", r)
        assert a is not None and abs(a - math.pi * r * r) < 1e-9

    def test_tan(self):
        # area = 0.5 * size^2
        a = get_shape_area("tan", 1.0)
        assert a is not None and abs(a - 0.5) < 1e-9

    def test_domino(self):
        # area = 2*size^2
        a = get_shape_area("domino", 1.0)
        assert a is not None and abs(a - 2.0) < 1e-9

    def test_l_tromino(self):
        # area = 3*size^2
        a = get_shape_area("l", 1.0)
        assert a is not None and abs(a - 3.0) < 1e-9

    def test_unknown(self):
        a = get_shape_area("UNKNOWN", 1.0)
        assert a is None

    def test_heptagon(self):
        a = get_shape_area("7", 1.0)
        assert a is not None and a > 0

    def test_nonagon(self):
        a = get_shape_area("9", 1.0)
        assert a is not None and a > 0

    def test_decagon(self):
        a = get_shape_area("10", 1.0)
        assert a is not None and a > 0

    def test_numeric_fallback(self):
        a = get_shape_area("12", 1.0)
        assert a is not None and a > 0


class TestGenerateQueue:
    def test_generate_from_real_verification(self, project_root, tmp_path):
        verif_dir = (
            project_root / "data" / "packingVerification"
            if (project_root / "data" / "packingVerification").exists()
            else project_root / "packingVerification"
        )

        out_path = tmp_path / "priority_queue.json"
        generate_queue(verif_dir=str(verif_dir), out_path=str(out_path))
        assert out_path.exists()

        with open(out_path, "r") as f:
            queue = json.load(f)

        assert isinstance(queue, list)
        assert len(queue) > 0
        for item in queue:
            assert "problem" in item
            assert "density" in item
            assert "best_value" in item

        # Sorted by density ascending
        densities = [x["density"] for x in queue]
        assert densities == sorted(densities)

    def test_generate_queue_no_dir(self, tmp_path, capsys):
        out_path = tmp_path / "q.json"
        generate_queue(verif_dir=str(tmp_path / "no_such_dir"), out_path=str(out_path))
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()
        assert not out_path.exists()

    def test_generate_queue_non_list_json(self, tmp_path, capsys):
        verif_dir = tmp_path / "pv"
        verif_dir.mkdir()
        (verif_dir / "bad.json").write_text(json.dumps({"not": "list"}))

        out_path = tmp_path / "q.json"
        generate_queue(verif_dir=str(verif_dir), out_path=str(out_path))
        assert out_path.exists()
        with open(out_path) as f:
            queue = json.load(f)
        assert queue == []

    def test_generate_queue_skip_missing_fields(self, tmp_path):
        verif_dir = tmp_path / "pv"
        verif_dir.mkdir()

        data = [
            {"our_problem": "3_4_in_4", "status": "best_known", "best_value": 1.0, "inner_shape": "4", "container_shape": "4", "N": 3},
            {"our_problem": "3_4_in_4", "status": "best_known", "best_value": None},
            {"our_problem": "3_4_in_4", "status": "best_known", "best_value": "bad"},
            {"our_problem": "", "status": "best_known", "best_value": 1.0},
            {"our_problem": "3_4_in_4", "status": "trivial", "best_value": 1.0, "inner_shape": "4", "container_shape": "4", "N": 3},
        ]
        (verif_dir / "test.json").write_text(json.dumps(data))

        out_path = tmp_path / "q.json"
        generate_queue(verif_dir=str(verif_dir), out_path=str(out_path))
        with open(out_path) as f:
            queue = json.load(f)

        # Only the first valid entry should survive
        assert len(queue) == 1
        assert queue[0]["problem"] == "3_4_in_4"

    def test_generate_queue_covering_density(self, tmp_path):
        verif_dir = tmp_path / "pv"
        verif_dir.mkdir()

        item = {
            "our_problem": "3_4_in_4_cov",
            "status": "best_known",
            "best_value": 2.0,
            "inner_shape": "4",
            "container_shape": "4",
            "N": 3,
        }
        (verif_dir / "cov.json").write_text(json.dumps([item]))

        out_path = tmp_path / "q.json"
        generate_queue(verif_dir=str(verif_dir), out_path=str(out_path))
        with open(out_path) as f:
            queue = json.load(f)

        assert len(queue) == 1
        assert queue[0]["problem"] == "3_4_in_4_cov"

    def test_generate_queue_invalid_area_continue(self, tmp_path):
        # Items with unrecognizable shapes -> None areas -> skipped
        verif_dir = tmp_path / "pv"
        verif_dir.mkdir()

        data = [
            {
                "our_problem": "1_BADSHAPE_in_4",
                "status": "best_known",
                "best_value": 1.0,
                "inner_shape": "BADSHAPE",
                "container_shape": "4",
                "N": 1,
            },
        ]
        (verif_dir / "bad.json").write_text(json.dumps(data))

        out_path = tmp_path / "q.json"
        generate_queue(verif_dir=str(verif_dir), out_path=str(out_path))
        with open(out_path) as f:
            queue = json.load(f)

        # All skipped because unknown shape
        assert queue == []

    def test_generate_queue_file_error(self, tmp_path, monkeypatch, capsys):
        from shape_packing import ranker
        import json as _json

        verif_dir = tmp_path / "pv"
        verif_dir.mkdir()
        (verif_dir / "err.json").write_text("[]")

        orig_load = _json.load

        def failing_load(*args, **kwargs):
            raise RuntimeError("oops")

        class FakeJson:
            @staticmethod
            def load(*args, **kwargs):
                failing_load(*args, **kwargs)

            dumps = _json.dumps
            dump = _json.dump

        monkeypatch.setattr(ranker, "json", FakeJson, raising=True)

        out_path = tmp_path / "q.json"
        generate_queue(verif_dir=str(verif_dir), out_path=str(out_path))

        # Restore temporarily so our own json.load works
        ranker.json.load = orig_load
        with open(out_path) as f:
            queue = json.load(f)
        assert queue == []

        captured = capsys.readouterr()
        assert "Failed to process" in captured.out

    def test_generate_queue_main(self, tmp_path, monkeypatch):
        # Confirm that if __name__ == "__main__" branch runs generate_queue()
        # We can't easily test __main__ here, but we ensure generate_queue is callable
        verif_dir = tmp_path / "pv"
        verif_dir.mkdir()
        (verif_dir / "x.json").write_text("[]")
        out_path = tmp_path / "q.json"
        generate_queue(verif_dir=str(verif_dir), out_path=str(out_path))
        assert out_path.exists()
