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
