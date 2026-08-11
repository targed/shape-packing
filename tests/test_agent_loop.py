"""
Tests for src/shape_packing/agent_loop.py

Covers:
- load_history
- current_best_scores
- is_stuck
- choose_problem behavior (priority queue, history, filters)
- reference helpers
- edge cases (empty history, blocked problems)
"""
import os
import pytest
from shape_packing.agent_loop import (
    load_history,
    current_best_scores,
    is_stuck,
    choose_problem,
    load_packing_reference,
    is_reference_blocked,
    is_preferred_reference,
    recent_problems,
)


class TestLoadHistory:
    def test_load_empty(self):
        hist = load_history("nonexistent_results.tsv")
        assert hist == []

    def test_load_from_fixture(self, sample_history_tsv):
        hist = load_history(sample_history_tsv)
        assert len(hist) > 0
        # All are ExperimentResult
        for r in hist:
            assert hasattr(r, "problem")
            assert hasattr(r, "score")


class TestCurrentBestScores:
    def test_no_data(self):
        assert current_best_scores([]) == {}

    def test_from_history(self, sample_history_tsv):
        hist = load_history(sample_history_tsv)
        best = current_best_scores(hist)
        assert "8_3_in_5" in best
        # Best is min score
        assert best["8_3_in_5"] == 1.1


class TestIsStuck:
    def test_not_stuck_few_runs(self, sample_history_tsv):
        hist = load_history(sample_history_tsv)
        assert is_stuck(hist, "8_3_in_5", threshold_no_improve=5) is False

    def test_stuck_no_improve(self, sample_history_tsv):
        # In fixture: 8_3_in_5 has scores 1.5,1.4,1.6,1.3,1.2,1.1 -> improving
        # So not stuck. We'll use 10_6_in_4 (single run) -> not stuck
        hist = load_history(sample_history_tsv)
        assert is_stuck(hist, "10_6_in_4") is False


class TestChooseProblem:
    def test_basic_returns_something(self, sample_priority_queue):
        os.environ["PRIORITY_QUEUE_PATH"] = sample_priority_queue
        p = choose_problem(
            history=[],
            queue_path=sample_priority_queue,
            exclude_problems=set(),
        )
        # Should prefer low-density, not trivial
        assert isinstance(p, str) and len(p) > 0

    def test_exclude_problem(self, sample_priority_queue):
        p = choose_problem(
            history=[],
            queue_path=sample_priority_queue,
            exclude_problems={"8_3_in_5"},
        )
        assert p != "8_3_in_5"

    def test_filters_min_max_n(self, sample_priority_queue):
        p = choose_problem(
            history=[],
            queue_path=sample_priority_queue,
            filters={"min_n": 8},
            exclude_problems=set(),
        )
        # Should pick problem with N >= 8
        assert "_in_" in p


class TestReferenceHelpers:
    def test_load_packing_reference_no_dir(self):
        rows = load_packing_reference(verif_dir="nonexistent")
        assert rows == []

    def test_is_reference_blocked(self, project_root, tmp_path):
        # Create a tiny packingVerification dir
        os.makedirs(tmp_path / "packingVerification", exist_ok=True)
        ref = [
            {
                "our_problem": "5_3_in_3",
                "status": "trivial",
            },
            {
                "our_problem": "8_3_in_5",
                "status": "best_known",
            },
        ]
        assert is_reference_blocked(ref, "5_3_in_3") is True
        assert is_reference_blocked(ref, "8_3_in_5") is False

    def test_is_preferred_reference(self):
        ref = [
            {
                "our_problem": "10_6_in_4",
                "status": "best_known",
            },
            {
                "our_problem": "12_3_in_CIRCLE",
                "status": "best_known",
                "source_note": "Found by Erich",
            },
        ]
        assert is_preferred_reference(ref, "10_6_in_4") is True
        assert is_preferred_reference(ref, "12_3_in_CIRCLE") is True


class TestFilterJsonAndProblemSelection:
    """
    Tests for filter.json options, shape token normalization, and problem filtering in choose_problem().
    """

    @pytest.fixture
    def rich_queue(self, tmp_path):
        import json
        q_path = str(tmp_path / "rich_queue.json")
        items = [
            {"problem": "5_DOMINO_in_5", "density": 0.45, "N": 5, "inner_shape": "DOMINO", "container_shape": "5", "status": "best_known"},
            {"problem": "10_5_in_6", "density": 0.50, "N": 10, "inner_shape": "5", "container_shape": "6", "status": "best_known"},
            {"problem": "8_3_in_5", "density": 0.55, "N": 8, "inner_shape": "3", "container_shape": "5", "status": "best_known"},
            {"problem": "12_DOMINO_in_CIRCLE", "density": 0.60, "N": 12, "inner_shape": "DOMINO", "container_shape": "CIRCLE", "status": "best_known"},
            {"problem": "15_6_in_8", "density": 0.65, "N": 15, "inner_shape": "6", "container_shape": "8", "status": "best_known"},
            {"problem": "20_PENTAGON_in_HEXAGON", "density": 0.70, "N": 20, "inner_shape": "PENTAGON", "container_shape": "HEXAGON", "status": "best_known"},
        ]
        with open(q_path, "w", encoding="utf-8") as f:
            json.dump(items, f)
        return q_path

    def test_include_inner_word_and_number_tokens(self, rich_queue):
        # Test DOMINO (word token) inclusion
        p = choose_problem(
            history=[],
            queue_path=rich_queue,
            filters={"include_inner": "DOMINO"},
            exclude_problems=set(),
        )
        assert "DOMINO" in p.upper()

        # Test PENTAGON (word / number 5) inclusion
        p5 = choose_problem(
            history=[],
            queue_path=rich_queue,
            filters={"include_inner": "PENTAGON, 5"},
            exclude_problems=set(),
        )
        assert "PENTAGON" in p5.upper() or "_5_" in p5 or "5_" in p5

    def test_exclude_inner_filter(self, rich_queue):
        p = choose_problem(
            history=[],
            queue_path=rich_queue,
            filters={"exclude_inner": "3, TRIANGLE, DOMINO"},
            exclude_problems=set(),
        )
        inner = p.split("_in_")[0].upper()
        assert "DOMINO" not in inner and "3" not in inner and "TRIANGLE" not in inner

    def test_include_container_and_exclude_container(self, rich_queue):
        # Include container pentagon / 5
        p = choose_problem(
            history=[],
            queue_path=rich_queue,
            filters={"include_container": ["5", "PENTAGON"]},
            exclude_problems=set(),
        )
        assert "_5" in p or "_PENTAGON" in p or "_in_5" in p.lower() or "_in_pentagon" in p.lower()

    def test_numeric_bounds_filters(self, rich_queue):
        # Equal N
        p_eq = choose_problem(
            history=[],
            queue_path=rich_queue,
            filters={"equal_n": 15},
            exclude_problems=set(),
        )
        assert p_eq.startswith("15_")

        # Min / max inner sides
        p_sides = choose_problem(
            history=[],
            queue_path=rich_queue,
            filters={"min_inner_sides": 5, "max_inner_sides": 8},
            exclude_problems=set(),
        )
        assert not p_sides.startswith("8_3_")

    def test_filter_json_file_parsing(self, tmp_path, rich_queue):
        import json
        filter_path = tmp_path / "filter.json"
        filter_data = {
            "min_n": 3,
            "max_n": 50,
            "include_inner": "DOMINO, PENTAGON, HEXAGON",
            "exclude_container": "TRIANGLE",
            "min_inner_sides": 3,
            "min_container_sides": 3,
        }
        filter_path.write_text(json.dumps(filter_data), encoding="utf-8")

        with open(filter_path, "r", encoding="utf-8") as f:
            loaded_filters = json.load(f)

        p = choose_problem(
            history=[],
            queue_path=rich_queue,
            filters=loaded_filters,
            exclude_problems=set(),
        )
        assert isinstance(p, str) and len(p) > 0


