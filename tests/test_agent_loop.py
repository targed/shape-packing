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
    last_experiments_for,
    has_improved,
    log_result,
    ExperimentLogContext,
    ExperimentResult,
    _parse_filter_sets,
    _build_problem_stats,
    _matches_external_filters,
)
from shape_packing.problems import parse_problem


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


class TestLastExperimentsFor:
    def test_empty_history(self):
        assert last_experiments_for([], "3_3_in_4") == []

    def test_no_matching_problem(self):
        history = [
            ExperimentResult(problem="5_3_in_3", score=1.0, status="keep", description="", seconds=0.1, commit="auto", memory_gb=0.0),
            ExperimentResult(problem="8_3_in_5", score=1.2, status="keep", description="", seconds=0.1, commit="auto", memory_gb=0.0),
        ]
        assert last_experiments_for(history, "3_3_in_4") == []

    def test_filters_by_problem_name(self):
        r1 = ExperimentResult(problem="3_3_in_4", score=1.5, status="keep", description="run 1", seconds=0.1, commit="auto", memory_gb=0.0)
        r2 = ExperimentResult(problem="8_3_in_5", score=1.1, status="keep", description="other", seconds=0.1, commit="auto", memory_gb=0.0)
        r3 = ExperimentResult(problem="3_3_in_4", score=1.4, status="keep", description="run 2", seconds=0.1, commit="auto", memory_gb=0.0)
        history = [r1, r2, r3]

        matches = last_experiments_for(history, "3_3_in_4")
        assert len(matches) == 2
        assert matches[0] == r1
        assert matches[1] == r3

    def test_default_last_limit(self):
        # Default is last=5
        history = [
            ExperimentResult(problem="3_3_in_4", score=float(i), status="keep", description=f"run {i}", seconds=0.1, commit="auto", memory_gb=0.0)
            for i in range(8)
        ]
        matches = last_experiments_for(history, "3_3_in_4")
        assert len(matches) == 5
        assert [r.score for r in matches] == [3.0, 4.0, 5.0, 6.0, 7.0]

    def test_fewer_than_last(self):
        history = [
            ExperimentResult(problem="3_3_in_4", score=float(i), status="keep", description=f"run {i}", seconds=0.1, commit="auto", memory_gb=0.0)
            for i in range(3)
        ]
        matches = last_experiments_for(history, "3_3_in_4", last=5)
        assert len(matches) == 3
        assert [r.score for r in matches] == [0.0, 1.0, 2.0]

    def test_exact_last(self):
        history = [
            ExperimentResult(problem="3_3_in_4", score=float(i), status="keep", description=f"run {i}", seconds=0.1, commit="auto", memory_gb=0.0)
            for i in range(4)
        ]
        matches = last_experiments_for(history, "3_3_in_4", last=4)
        assert len(matches) == 4
        assert [r.score for r in matches] == [0.0, 1.0, 2.0, 3.0]

    def test_custom_last_slice(self):
        history = [
            ExperimentResult(problem="3_3_in_4", score=float(i), status="keep", description=f"run {i}", seconds=0.1, commit="auto", memory_gb=0.0)
            for i in range(6)
        ]
        matches = last_experiments_for(history, "3_3_in_4", last=2)
        assert len(matches) == 2
        assert [r.score for r in matches] == [4.0, 5.0]

    def test_order_preservation(self):
        r1 = ExperimentResult(problem="target", score=3.0, status="keep", description="first", seconds=0.1, commit="auto", memory_gb=0.0)
        r2 = ExperimentResult(problem="target", score=2.0, status="keep", description="second", seconds=0.2, commit="auto", memory_gb=0.0)
        r3 = ExperimentResult(problem="target", score=1.0, status="keep", description="third", seconds=0.3, commit="auto", memory_gb=0.0)
        history = [r1, r2, r3]
        matches = last_experiments_for(history, "target", last=3)
        assert matches == [r1, r2, r3]


class TestRecentProblems:
    def test_empty_history(self):
        assert recent_problems([]) == []
        assert recent_problems([], last=5) == []

    def test_default_last_is_ten(self):
        history = [
            ExperimentResult(problem=f"prob_{i}", score=1.0, status="keep", description="", seconds=0.1, commit="auto", memory_gb=0.0)
            for i in range(15)
        ]
        res = recent_problems(history)
        assert len(res) == 10
        assert res == [f"prob_{i}" for i in range(5, 15)]

    def test_recent_problems_fewer_than_last(self):
        history = [
            ExperimentResult(problem="prob_a", score=1.0, status="keep", description="", seconds=0.1, commit="auto", memory_gb=0.0),
        ]
        assert recent_problems(history, last=5) == ["prob_a"]

    def test_recent_problems_exact_last(self):
        history = [
            ExperimentResult(problem=f"prob_{i}", score=1.0, status="keep", description="", seconds=0.1, commit="auto", memory_gb=0.0)
            for i in range(5)
        ]
        assert recent_problems(history, last=5) == [f"prob_{i}" for i in range(5)]

    def test_custom_last_slice(self):
        history = [
            ExperimentResult(problem="prob_a", score=1.0, status="keep", description="", seconds=0.1, commit="auto", memory_gb=0.0),
            ExperimentResult(problem="prob_b", score=1.0, status="keep", description="", seconds=0.1, commit="auto", memory_gb=0.0),
            ExperimentResult(problem="prob_c", score=1.0, status="keep", description="", seconds=0.1, commit="auto", memory_gb=0.0),
        ]
        assert recent_problems(history, last=2) == ["prob_b", "prob_c"]
        assert recent_problems(history, last=1) == ["prob_c"]

    def test_preserves_order_and_duplicates(self):
        history = [
            ExperimentResult(problem="prob_a", score=1.0, status="keep", description="", seconds=0.1, commit="auto", memory_gb=0.0),
            ExperimentResult(problem="prob_b", score=1.0, status="keep", description="", seconds=0.1, commit="auto", memory_gb=0.0),
            ExperimentResult(problem="prob_a", score=1.0, status="keep", description="", seconds=0.1, commit="auto", memory_gb=0.0),
        ]
        assert recent_problems(history, last=3) == ["prob_a", "prob_b", "prob_a"]


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


class TestLogResult:
    def test_log_result_with_context_object(self, tmp_path):
        tsv_path = str(tmp_path / "test_results.tsv")
        ctx = ExperimentLogContext(
            problem="10_DOMINO_in_5",
            score=2.15,
            seconds=5.0,
            description="Test run",
            path=tsv_path,
        )
        status = log_result(context=ctx)
        assert status == "keep"
        hist = load_history(tsv_path)
        assert len(hist) == 1
        assert hist[0].problem == "10_DOMINO_in_5"
        assert hist[0].score == 2.15

class TestTanShapeSupport:
    def test_tan_shape_supported_in_agent_loop(self):
        from shape_packing.agent_loop import _is_shape_unsupported, _get_inner_shape_area, _get_container_shape_area
        assert not _is_shape_unsupported("TAN", {})
        assert not _is_shape_unsupported("tan", {})
        assert not _is_shape_unsupported("tangram", {})
        assert _get_inner_shape_area("TAN") == 0.5
        assert _get_container_shape_area(2.0, "TAN") == 2.0

    def test_tan_problem_selection(self, tmp_path):
        import json
        q_path = str(tmp_path / "tan_queue.json")
        items = [
            {"problem": "2_TAN_in_4", "density": 0.85, "status": "best_known", "N": 2, "inner_shape": "TAN", "container_shape": "4", "best_value": 1.0},
        ]
        with open(q_path, "w") as f:
            json.dump(items, f)
        p = choose_problem(
            history=[],
            queue_path=q_path,
            exclude_problems=set(),
        )
        assert p == "2_TAN_in_4"


class TestLTrominoSupport:
    def test_l_shape_supported_in_agent_loop(self):
        from shape_packing.agent_loop import _is_shape_unsupported, _get_inner_shape_area, _get_container_shape_area
        assert not _is_shape_unsupported("L", {})
        assert not _is_shape_unsupported("l", {})
        assert not _is_shape_unsupported("ltromino", {})
        assert not _is_shape_unsupported("l-tromino", {})
        assert _get_inner_shape_area("L") == 3.0
        assert _get_container_shape_area(2.0, "L") == 12.0

    def test_l_problem_selection(self, tmp_path):
        import json
        q_path = str(tmp_path / "l_queue.json")
        items = [
            {"problem": "1_L_in_4", "density": 0.75, "status": "best_known", "N": 1, "inner_shape": "L", "container_shape": "4", "best_value": 2.0},
        ]
        with open(q_path, "w") as f:
            json.dump(items, f)
        p = choose_problem(
            history=[],
            queue_path=q_path,
            exclude_problems=set(),
        )
        assert p == "1_L_in_4"


class TestParseFilterSets:
    def test_none_or_empty_filters(self):
        assert _parse_filter_sets(None) == (set(), set(), set(), set())
        assert _parse_filter_sets({}) == (set(), set(), set(), set())

    def test_filters_with_empty_or_falsy_values(self):
        filters = {
            "include_inner": None,
            "exclude_inner": "",
            "include_container": [],
            "exclude_container": False,
        }
        assert _parse_filter_sets(filters) == (set(), set(), set(), set())

    def test_comma_separated_strings(self):
        filters = {
            "include_inner": " square , 4 , domino ",
            "exclude_container": "circle, 5",
        }
        inc_i, exc_i, inc_c, exc_c = _parse_filter_sets(filters)
        assert inc_i == {"SQUARE", "4", "DOMINO"}
        assert exc_i == set()
        assert inc_c == set()
        assert exc_c == {"CIRCLE", "CIR", "5"}

    def test_list_inputs_and_numeric_values(self):
        filters = {
            "include_container": ["triangle", 4, "octagon"],
            "exclude_inner": ["tan"],
        }
        inc_i, exc_i, inc_c, exc_c = _parse_filter_sets(filters)
        assert inc_i == set()
        assert exc_i == {"TAN", "TANGRAM"}
        assert inc_c == {"3", "TRIANGLE", "4", "OCTAGON"}
        assert exc_c == set()

    def test_single_non_string_non_list_value(self):
        filters = {"include_inner": 3}
        inc_i, exc_i, inc_c, exc_c = _parse_filter_sets(filters)
        assert inc_i == {"3", "TRIANGLE"}
        assert exc_i == set()
        assert inc_c == set()
        assert exc_c == set()

    def test_synonym_expansions(self):
        # Circle synonyms
        filters = {"include_inner": "cir", "exclude_inner": "circle"}
        inc_i, exc_i, _, _ = _parse_filter_sets(filters)
        assert inc_i == {"CIR", "CIRCLE"}
        assert exc_i == {"CIR", "CIRCLE"}

        # Triangle synonyms
        filters = {"include_inner": "3", "exclude_inner": "triangle"}
        inc_i, exc_i, _, _ = _parse_filter_sets(filters)
        assert inc_i == {"3", "TRIANGLE"}
        assert exc_i == {"3", "TRIANGLE"}

        # Tan synonyms
        filters = {"include_inner": "tan", "exclude_inner": "tangram"}
        inc_i, exc_i, _, _ = _parse_filter_sets(filters)
        assert inc_i == {"TAN", "TANGRAM"}
        assert exc_i == {"TAN", "TANGRAM"}

        # L-tromino synonyms
        for sym in ["l", "ltromino", "l-tromino"]:
            inc_i, _, _, _ = _parse_filter_sets({"include_inner": sym})
            assert inc_i == {"L", "LTROMINO", "L-TROMINO"}

    def test_all_four_sets_returned_in_correct_order(self):
        filters = {
            "include_inner": "4",
            "exclude_inner": "5",
            "include_container": "6",
            "exclude_container": "8",
        }
        inc_i, exc_i, inc_c, exc_c = _parse_filter_sets(filters)
        assert inc_i == {"4"}
        assert exc_i == {"5"}
        assert inc_c == {"6"}
        assert exc_c == {"8"}


class TestBuildProblemStats:
    def test_empty_history(self):
        problem_runs, family_runs, problem_last_k = _build_problem_stats([])
        assert len(problem_runs) == 0
        assert len(family_runs) == 0
        assert len(problem_last_k) == 0

    def test_problem_and_family_runs_tallying(self):
        h = [
            ExperimentResult(problem="3_3_in_4", score=1.5, status="keep", description="1", seconds=0.1, commit="auto", memory_gb=0.0),
            ExperimentResult(problem="3_3_in_4", score=1.4, status="keep", description="2", seconds=0.1, commit="auto", memory_gb=0.0),
            ExperimentResult(problem="4_3_in_4", score=1.8, status="keep", description="3", seconds=0.1, commit="auto", memory_gb=0.0),
            ExperimentResult(problem="5_3_in_5", score=2.0, status="keep", description="4", seconds=0.1, commit="auto", memory_gb=0.0),
        ]
        problem_runs, family_runs, problem_last_k = _build_problem_stats(h)

        assert problem_runs["3_3_in_4"] == 2
        assert problem_runs["4_3_in_4"] == 1
        assert problem_runs["5_3_in_5"] == 1
        assert problem_runs["nonexistent"] == 0

        # Check family runs
        assert family_runs["3_in_4"] == 3
        assert family_runs["3_in_5"] == 1

    def test_problem_last_k_window_capping(self):
        h = [
            ExperimentResult(problem="3_3_in_4", score=float(i), status="keep", description=f"run {i}", seconds=0.1, commit="auto", memory_gb=0.0)
            for i in range(5)
        ]
        _, _, problem_last_k = _build_problem_stats(h, k=3)

        assert len(problem_last_k["3_3_in_4"]) == 3
        assert [r.score for r in problem_last_k["3_3_in_4"]] == [2.0, 3.0, 4.0]


class TestMatchesExternalFilters:
    def test_matches_with_no_filters(self):
        p0 = parse_problem("3_3_in_4")
        item = {"inner_shape": "3", "container_shape": "4", "N": 3}
        assert _matches_external_filters(p0, item, {}, set(), set(), set(), set()) is True

    def test_n_bounds_filters(self):
        p0 = parse_problem("5_3_in_4")
        item = {"inner_shape": "3", "container_shape": "4", "N": 5}

        # min_n
        assert _matches_external_filters(p0, item, {"min_n": 5}, set(), set(), set(), set()) is True
        assert _matches_external_filters(p0, item, {"min_n": 6}, set(), set(), set(), set()) is False

        # max_n
        assert _matches_external_filters(p0, item, {"max_n": 5}, set(), set(), set(), set()) is True
        assert _matches_external_filters(p0, item, {"max_n": 4}, set(), set(), set(), set()) is False

        # equal_n
        assert _matches_external_filters(p0, item, {"equal_n": 5}, set(), set(), set(), set()) is True
        assert _matches_external_filters(p0, item, {"equal_n": 6}, set(), set(), set(), set()) is False

    def test_include_and_exclude_inner(self):
        p_tri = parse_problem("3_3_in_4")
        p_sq = parse_problem("3_4_in_4")
        item_tri = {"inner_shape": "3", "container_shape": "4", "N": 3}
        item_sq = {"inner_shape": "4", "container_shape": "4", "N": 3}

        # Include inner
        inc_inner = {"3", "TRIANGLE"}
        assert _matches_external_filters(p_tri, item_tri, {}, inc_inner, set(), set(), set()) is True
        assert _matches_external_filters(p_sq, item_sq, {}, inc_inner, set(), set(), set()) is False

        # Exclude inner
        exc_inner = {"4", "SQUARE"}
        assert _matches_external_filters(p_tri, item_tri, {}, set(), exc_inner, set(), set()) is True
        assert _matches_external_filters(p_sq, item_sq, {}, set(), exc_inner, set(), set()) is False

    def test_include_and_exclude_container(self):
        p_cir = parse_problem("3_3_in_circle")
        p_sq = parse_problem("3_3_in_4")
        item_cir = {"inner_shape": "3", "container_shape": "CIRCLE (COVERING)", "N": 3}
        item_sq = {"inner_shape": "3", "container_shape": "4", "N": 3}

        # Include container
        inc_cont = {"CIRCLE", "CIR"}
        assert _matches_external_filters(p_cir, item_cir, {}, set(), set(), inc_cont, set()) is True
        assert _matches_external_filters(p_sq, item_sq, {}, set(), set(), inc_cont, set()) is False

        # Exclude container
        exc_cont = {"4", "SQUARE"}
        assert _matches_external_filters(p_cir, item_cir, {}, set(), set(), set(), exc_cont) is True
        assert _matches_external_filters(p_sq, item_sq, {}, set(), set(), set(), exc_cont) is False

    def test_sides_bounds_filters(self):
        p_tri_sq = parse_problem("3_3_in_4")
        item = {"inner_shape": "3", "container_shape": "4", "N": 3}

        # Inner sides bounds (triangle has 3 sides)
        assert _matches_external_filters(p_tri_sq, item, {"min_inner_sides": 3}, set(), set(), set(), set()) is True
        assert _matches_external_filters(p_tri_sq, item, {"min_inner_sides": 4}, set(), set(), set(), set()) is False
        assert _matches_external_filters(p_tri_sq, item, {"max_inner_sides": 3}, set(), set(), set(), set()) is True
        assert _matches_external_filters(p_tri_sq, item, {"max_inner_sides": 2}, set(), set(), set(), set()) is False

        # Container sides bounds (square has 4 sides)
        assert _matches_external_filters(p_tri_sq, item, {"min_container_sides": 4}, set(), set(), set(), set()) is True
        assert _matches_external_filters(p_tri_sq, item, {"min_container_sides": 5}, set(), set(), set(), set()) is False
        assert _matches_external_filters(p_tri_sq, item, {"max_container_sides": 4}, set(), set(), set(), set()) is True
        assert _matches_external_filters(p_tri_sq, item, {"max_container_sides": 3}, set(), set(), set(), set()) is False

    def test_circle_sides_bounds(self):
        from shape_packing.packing_config import CIRCLE_SIDES
        p_cir = parse_problem("3_circle_in_circle")
        item = {"inner_shape": "CIRCLE", "container_shape": "CIRCLE", "N": 3}

        assert _matches_external_filters(p_cir, item, {"min_inner_sides": CIRCLE_SIDES}, set(), set(), set(), set()) is True
        assert _matches_external_filters(p_cir, item, {"max_inner_sides": CIRCLE_SIDES - 1}, set(), set(), set(), set()) is False
        assert _matches_external_filters(p_cir, item, {"min_container_sides": CIRCLE_SIDES}, set(), set(), set(), set()) is True
        assert _matches_external_filters(p_cir, item, {"max_container_sides": CIRCLE_SIDES - 1}, set(), set(), set(), set()) is False

    def test_exception_returns_false(self):
        # Malformed or None input should return False without raising
        assert _matches_external_filters(None, {}, {}, set(), set(), set(), set()) is False







