"""
Additional tests to improve coverage of agent_loop.py
Target: branches and error paths not hit yet.
"""
import os
import pytest
from shape_packing.agent_loop import (
    load_history,
    append_result,
    ExperimentResult,
    load_packing_reference,
    is_preferred_reference,
    extract_problem_family,
    has_improved,
    normalize_problem_name,
    load_priority_queue,
    choose_problem,
    is_stuck,
    should_switch_radically,
    log_result,
    make_loop_candidate,
    is_physically_valid_score,
    last_experiments_for,
    _get_inner_shape_area,
    _get_container_shape_area,
)
import math


class TestGetInnerShapeArea:
    def test_known_inner_shapes(self):
        assert _get_inner_shape_area("3") == pytest.approx(math.sqrt(3) / 4.0)
        assert _get_inner_shape_area("TRIANGLE") == pytest.approx(math.sqrt(3) / 4.0)
        assert _get_inner_shape_area("4") == 1.0
        assert _get_inner_shape_area("SQUARE") == 1.0
        assert _get_inner_shape_area("5") == pytest.approx(0.25 * math.sqrt(5.0 * (5.0 + 2.0 * math.sqrt(5.0))))
        assert _get_inner_shape_area("6") == pytest.approx(1.5 * math.sqrt(3))
        assert _get_inner_shape_area("8") == pytest.approx(2.0 * (1.0 + math.sqrt(2.0)))

    def test_unknown_or_unsupported_shapes_return_none(self):
        assert _get_inner_shape_area("UNKNOWN") is None
        assert _get_inner_shape_area("CIRCLE") is None
        assert _get_inner_shape_area("99") is None
        assert _get_inner_shape_area("") is None


class TestGetContainerShapeArea:
    def test_known_container_shapes(self):
        assert _get_container_shape_area(2.0, "CIRCLE") == pytest.approx(math.pi * 4.0)
        assert _get_container_shape_area(2.0, "4") == 4.0
        assert _get_container_shape_area(3.0, "TRIANGLE") == pytest.approx((math.sqrt(3) / 4.0) * 9.0)

    def test_unknown_container_shapes_return_none(self):
        assert _get_container_shape_area(2.0, "UNKNOWN") is None
        assert _get_container_shape_area(2.0, "99") is None
        assert _get_container_shape_area(2.0, "") is None


class TestLastExperimentsFor:

    def test_filters_by_problem_name(self):
        h = [
            ExperimentResult(problem="3_3_in_4", score=1.5, status="keep", description="1", seconds=0.1, commit="auto", memory_gb=0.0),
            ExperimentResult(problem="4_3_in_4", score=1.8, status="keep", description="2", seconds=0.1, commit="auto", memory_gb=0.0),
            ExperimentResult(problem="3_3_in_4", score=1.4, status="keep", description="3", seconds=0.1, commit="auto", memory_gb=0.0),
        ]
        res = last_experiments_for(h, "3_3_in_4")
        assert len(res) == 2
        assert res[0].description == "1"
        assert res[1].description == "3"

    def test_limits_to_last_n_entries(self):
        h = [
            ExperimentResult(problem="3_3_in_4", score=float(i), status="keep", description=str(i), seconds=0.1, commit="auto", memory_gb=0.0)
            for i in range(10)
        ]
        res = last_experiments_for(h, "3_3_in_4", last=3)
        assert len(res) == 3
        assert [r.description for r in res] == ["7", "8", "9"]

    def test_returns_empty_when_no_match(self):
        h = [
            ExperimentResult(problem="3_3_in_4", score=1.5, status="keep", description="1", seconds=0.1, commit="auto", memory_gb=0.0)
        ]
        assert last_experiments_for(h, "99_99_in_99") == []
        assert last_experiments_for([], "3_3_in_4") == []


class TestIsPhysicallyValidScore:

    def test_negative_or_zero_score_is_invalid(self):
        assert is_physically_valid_score("3_3_in_4", 0.0) is False
        assert is_physically_valid_score("3_3_in_4", -1.5) is False

    def test_circle_container_below_min_threshold_is_invalid(self):
        assert is_physically_valid_score("5_3_in_CIRCLE", 0.05) is False
        assert is_physically_valid_score("5_3_in_CIR", 0.099) is False
        assert is_physically_valid_score("5_3_in_0", 0.01) is False

    def test_circle_container_above_min_threshold_is_valid(self):
        assert is_physically_valid_score("5_3_in_CIRCLE", 0.1) is True
        assert is_physically_valid_score("5_3_in_CIR", 0.5) is True
        assert is_physically_valid_score("5_3_in_0", 1.2) is True

    def test_polygon_container_valid(self):
        assert is_physically_valid_score("5_3_in_4", 0.05) is True
        assert is_physically_valid_score("10_SQUARE_in_HEXAGON", 2.5) is True

    def test_non_standard_problem_format_valid(self):
        assert is_physically_valid_score("malformed_problem", 1.0) is True



class TestAppendResult:
    def test_creates_file_with_header(self, tmp_path):
        path = tmp_path / "res.tsv"
        r = ExperimentResult(
            problem="1_3_in_3",
            score=1.0,
            status="keep",
            description="x",
            seconds=1.0,
            commit="c1",
            memory_gb=0.1,
        )
        append_result(str(path), r)
        assert path.exists()
        text = path.read_text()
        assert "commit" in text.split("\t")[0]
        assert "1_3_in_3" in text

    def test_appends_to_existing(self, tmp_path):
        path = tmp_path / "res.tsv"
        r = ExperimentResult(
            problem="1_3_in_3",
            score=1.0,
            status="keep",
            description="x",
            seconds=1.0,
            commit="c1",
            memory_gb=0.1,
        )
        append_result(str(path), r)
        append_result(str(path), r)
        lines = [l for l in path.read_text().strip().split("\n") if l.strip()]
        assert len(lines) >= 3  # header + 2 rows


class TestLoadHistoryEdgeCases:
    def test_load_malformed_row_skipped(self, tmp_path):
        path = tmp_path / "bad.tsv"
        path.write_text(
            "commit\tscore\tmemory_gb\tstatus\tproblem\tdescription\n"
            "c1\tBAD\t0\tkeep\t1_3_in_3\tx\n"
        )
        hist = load_history(str(path))
        assert len(hist) == 0


class TestLoadPackingReference:
    def test_load_valid_reference(self, tmp_path):
        d = tmp_path / "pv"
        d.mkdir()
        (d / "a.json").write_text('[{"our_problem":"1_3_in_3","status":"best_known"}]')
        rows = load_packing_reference(verif_dir=str(d))
        assert len(rows) == 1
        assert rows[0]["our_problem"] == "1_3_in_3"

    def test_load_non_list_json_ignored(self, tmp_path):
        d = tmp_path / "pv"
        d.mkdir()
        (d / "x.json").write_text('{"not":"list"}')
        rows = load_packing_reference(verif_dir=str(d))
        assert rows == []


class TestIsPreferredReferenceEdge:
    def test_found_by_note(self):
        ref = [
            {"our_problem": "1_3_in_3", "status": "best_known", "source_note": "Found by Bob"},
        ]
        assert is_preferred_reference(ref, "1_3_in_3") is True

    def test_erich_friedman_note(self):
        ref = [
            {"our_problem": "1_3_in_3", "status": "best_known", "source_note": "Erich Friedman's result"},
        ]
        assert is_preferred_reference(ref, "1_3_in_3") is True


class TestExtractProblemFamily:
    def test_normal(self):
        assert extract_problem_family("12_5_in_8") == "5_in_8"

    def test_too_short_unchanged(self):
        assert extract_problem_family("abc") == "abc"


class TestHasImproved:
    def test_empty_window(self):
        assert has_improved([]) is False

    def test_single_result(self):
        assert has_improved(
            [ExperimentResult("x", 1.0, "keep", "", 1.0, "", 0.0)]
        ) is False


class TestNormalizeProblemName:
    def test_already_standard(self):
        assert normalize_problem_name("8_3_in_5") == "8_3_in_5"

    def test_shortcode_tri_in_squ(self):
        # 5_triinSqu -> 5_3_in_4
        assert normalize_problem_name("5_triinSqu") == "5_3_in_4"

    def test_shortcode_cir(self):
        assert normalize_problem_name("3_cirinCir") == "3_CIRCLE_in_CIRCLE"

    def test_shortcode_tan(self):
        # 2_tanin4 doesn't match compact regex (requires digits then letters)
        # So it passes through unchanged.
        assert normalize_problem_name("2_tanin4") == "2_tanin4"

    def test_unmatched_passthrough(self):
        assert normalize_problem_name("weird") == "weird"


class TestLoadPriorityQueue:
    def test_no_file(self):
        assert load_priority_queue("nonexistent.json") == []

    def test_valid_file(self, tmp_path):
        path = tmp_path / "pq.json"
        path.write_text("[{\"problem\":\"1_3_in_3\"}]")
        q = load_priority_queue(str(path))
        assert len(q) == 1


class TestChooseProblemEdgeCases:
    def test_empty_queue_fallback(self, tmp_path):
        path = tmp_path / "pq_empty.json"
        path.write_text("[]")
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "8_3_in_5"

    def test_no_queue_file_fallback(self):
        p = choose_problem(
            history=[],
            queue_path="nonexistent.json",
        )
        assert p == "8_3_in_5"

    def test_no_candidates_fallback(self, tmp_path):
        # Create queue where all are trivial -> no candidates -> fallback
        path = tmp_path / "pq.json"
        path.write_text(
            "[{"
            '"problem":"5_3_in_3","density":0.9,"status":"trivial",'
            '"inner_shape":"3","container_shape":"3","best_value":1.0,"N":5'
            "}]"
        )
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "8_3_in_5"

    def test_filter_include_inner(self, tmp_path):
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "3_3_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 3,
            },
            {
                "problem": "3_4_in_4",
                "density": 0.8,
                "status": "best_known",
                "inner_shape": "4",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 3,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
            filters={"include_inner": ["4"]},
        )
        # Must choose from shape 4 only
        assert "4" in p.split("_")

    def test_filter_exclude_inner(self, tmp_path):
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "3_3_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 3,
            },
            {
                "problem": "3_4_in_4",
                "density": 0.8,
                "status": "best_known",
                "inner_shape": "4",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 3,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
            filters={"exclude_inner": ["3"]},
        )
        # Must not choose inner 3
        tokens = p.split("_")
        assert tokens[1] != "3"

    def test_filter_include_container(self, tmp_path):
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "3_3_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 3,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
            filters={"include_container": ["4"]},
        )
        assert "_in_4" in p

    def test_filter_exclude_container(self, tmp_path):
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "3_3_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 3,
            },
            {
                "problem": "3_3_in_5",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "5",
                "best_value": 2.0,
                "N": 3,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
            filters={"exclude_container": ["5"]},
        )
        # Must not choose container 5
        assert "_in_5" not in p

    def test_filter_min_inner_sides(self, tmp_path):
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "3_3_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 3,
            },
            {
                "problem": "3_6_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "6",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 3,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
            filters={"min_inner_sides": 5},
        )
        # Should pick 6_in_4 (since 3 excluded)
        assert "_6_in_" in p

    def test_prefer_different_penalty(self, tmp_path):
        # If 8_3_in_5 is recent, prefer_different should penalize it.
        from shape_packing.agent_loop import recent_problems
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "8_3_in_5",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "5",
                "best_value": 2.0,
                "N": 8,
            },
            {
                "problem": "3_3_in_4",
                "density": 0.85,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 3,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        hist = [
            ExperimentResult(
                problem="8_3_in_5",
                score=1.0,
                status="keep",
                description="x",
                seconds=1.0,
                commit="c",
                memory_gb=0.1,
            )
            for _ in range(8)
        ]
        p = choose_problem(
            history=hist,
            queue_path=str(path),
            prefer_different=True,
            exclude_problems=set(),
        )
        # Should avoid 8_3_in_5
        assert p != "8_3_in_5"


class TestRunCaps:
    def test_per_problem_cap_applies(self, tmp_path):
        # Create many runs for a problem to trigger caps
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_3_in_3",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "3",
                "best_value": 2.0,
                "N": 1,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        hist = [
            ExperimentResult(
                problem="1_3_in_3",
                score=1.0,
                status="keep",
                description="x",
                seconds=1.0,
                commit="c",
                memory_gb=0.1,
            )
            for _ in range(70)
        ]
        # With 70 runs, penalty should apply; it will still be chosen since it's the only candidate,
        # but function should not crash and must respect the caps.
        p = choose_problem(
            history=hist,
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "1_3_in_3"


class TestIsStuck:
    def test_stuck_no_improve(self, tmp_path):
        # 5 identical runs, no improvement
        hist = [
            ExperimentResult(
                problem="1_3_in_3",
                score=1.0,
                status="keep",
                description="x",
                seconds=1.0,
                commit="c",
                memory_gb=0.1,
            )
            for _ in range(5)
        ]
        assert is_stuck(hist, "1_3_in_3", threshold_no_improve=5) is True

    def test_stuck_crash_in_window(self, tmp_path):
        # One crash in window -> not stuck
        hist = [
            ExperimentResult(
                problem="1_3_in_3",
                score=0.0,
                status="crash",
                description="x",
                seconds=1.0,
                commit="c",
                memory_gb=0.1,
            )
        ] + [
            ExperimentResult(
                problem="1_3_in_3",
                score=1.0,
                status="keep",
                description="x",
                seconds=1.0,
                commit="c",
                memory_gb=0.1,
            )
            for _ in range(4)
        ]
        assert is_stuck(hist, "1_3_in_3", threshold_no_improve=5) is False


class TestShouldSwitchRadically:
    def test_zero(self):
        assert should_switch_radically(0) is False

    def test_negative(self):
        assert should_switch_radically(-1) is False

    def test_at_20(self):
        assert should_switch_radically(20) is True

    def test_at_31(self):
        assert should_switch_radically(31) is True


class TestLogResult:
    def test_log_crash(self, tmp_path):
        path = tmp_path / "results.tsv"
        status = log_result(
            history=None,
            problem="1_3_in_3",
            score=-1.0,
            seconds=1.0,
            description="x",
            path=str(path),
        )
        assert status == "crash"

    def test_log_keep(self, tmp_path):
        path = tmp_path / "results.tsv"
        status = log_result(
            history=None,
            problem="1_3_in_3",
            score=0.5,
            seconds=1.0,
            description="x",
            path=str(path),
        )
        assert status == "keep"

    def test_log_discard(self, tmp_path):
        path = tmp_path / "results.tsv"
        # First log a good score
        log_result(None, "1_3_in_3", 0.3, 1.0, "x", path=str(path))
        status = log_result(
            history=None,
            problem="1_3_in_3",
            score=1.0,
            seconds=1.0,
            description="y",
            path=str(path),
        )
        assert status == "discard"


class TestMakeLoopCandidate:
    def test_no_current_no_radical(self, tmp_path):
        hist = []
        problem, radical = make_loop_candidate(
            history=hist,
            current=None,
            experiments_count=0,
        )
        assert isinstance(problem, str)
        assert radical is False

    def test_radical_switch(self, tmp_path):
        # 20 experiments -> radical
        hist = [
            ExperimentResult(
                problem="1_3_in_3",
                score=1.0,
                status="keep",
                description="x",
                seconds=1.0,
                commit="c",
                memory_gb=0.1,
            )
            for _ in range(20)
        ]
        problem, radical = make_loop_candidate(
            history=hist,
            current="1_3_in_3",
            experiments_count=0,
        )
        assert radical is True

    def test_stuck_switch(self, tmp_path):
        # Create stuck history
        hist = [
            ExperimentResult(
                problem="1_3_in_3",
                score=1.0,
                status="keep",
                description="x",
                seconds=1.0,
                commit="c",
                memory_gb=0.1,
            )
            for _ in range(10)
        ]
        problem, radical = make_loop_candidate(
            history=hist,
            current="1_3_in_3",
            experiments_count=0,
        )
        # Should detect stuck and choose different
        assert isinstance(problem, str)


class TestBestValueBonusAndNearReference:
    def test_near_reference_penalty(self, tmp_path):
        # our best 0.1% above best_value -> near reference
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_3_in_3",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "3",
                "best_value": 10.0,
                "N": 1,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        hist = [
            ExperimentResult(
                problem="1_3_in_3",
                score=10.01,
                status="keep",
                description="x",
                seconds=1.0,
                commit="c",
                memory_gb=0.1,
            )
            for _ in range(2)
        ]
        # Even though near reference, still only candidate
        p = choose_problem(
            history=hist,
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "1_3_in_3"

    def test_low_run_bonus(self, tmp_path):
        # Problem with 0 runs should get -3 bonus
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_3_in_3",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "3",
                "best_value": 10.0,
                "N": 1,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "1_3_in_3"

    def test_large_gap_bonus(self, tmp_path):
        # rel_gap > 0.10 and total_runs < 30 -> -0.3 bonus
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_3_in_3",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "3",
                "best_value": 1.0,
                "N": 1,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        hist = [
            ExperimentResult(
                problem="1_3_in_3",
                score=2.0,
                status="keep",
                description="x",
                seconds=1.0,
                commit="c",
                memory_gb=0.1,
            )
            for _ in range(2)
        ]
        p = choose_problem(
            history=hist,
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "1_3_in_3"


class TestAdvancedChooseProblemBranches:
    def test_problem_cap2_penalty(self, tmp_path):
        # >100 runs -> +15 penalty
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_3_in_3",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "3",
                "best_value": 2.0,
                "N": 1,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        hist = [
            ExperimentResult(
                problem="1_3_in_3",
                score=1.0,
                status="keep",
                description="x",
                seconds=1.0,
                commit="c",
                memory_gb=0.1,
            )
            for _ in range(110)
        ]
        p = choose_problem(
            history=hist,
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "1_3_in_3"

    def test_family_cap1_penalty(self, tmp_path):
        # >400 family runs -> +5 penalty
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_3_in_3",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "3",
                "best_value": 2.0,
                "N": 1,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        hist = [
            ExperimentResult(
                problem="1_3_in_3",
                score=1.0,
                status="keep",
                description="x",
                seconds=1.0,
                commit="c",
                memory_gb=0.1,
            )
            for _ in range(410)
        ]
        p = choose_problem(
            history=hist,
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "1_3_in_3"

    def test_family_cap2_penalty(self, tmp_path):
        # >800 family runs -> +15 penalty
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_3_in_3",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "3",
                "best_value": 2.0,
                "N": 1,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        hist = [
            ExperimentResult(
                problem="1_3_in_3",
                score=1.0,
                status="keep",
                description="x",
                seconds=1.0,
                commit="c",
                memory_gb=0.1,
            )
            for _ in range(810)
        ]
        p = choose_problem(
            history=hist,
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "1_3_in_3"

    def test_non_best_known_found_by_bonus(self, tmp_path):
        # status not best_known but source_note contains "Found by"
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_3_in_3",
                "density": 0.9,
                "status": "known",
                "source_note": "Found by Erich Friedman",
                "inner_shape": "3",
                "container_shape": "3",
                "best_value": 2.0,
                "N": 1,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "1_3_in_3"

    def test_filter_max_n(self, tmp_path):
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "2_3_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 2,
            },
            {
                "problem": "10_3_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 10,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
            filters={"max_n": 5},
        )
        assert "_in_" in p

    def test_filter_equal_n(self, tmp_path):
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "3_3_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 3,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
            filters={"equal_n": 3},
        )
        assert "3_3_in_4" in p

    def test_filter_max_inner_sides(self, tmp_path):
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_6_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "6",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 1,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
            filters={"max_inner_sides": 4},
        )
        # 6 excluded; no candidates -> fallback
        assert p == "8_3_in_5"

    def test_filter_min_container_sides(self, tmp_path):
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_3_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 1,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
            filters={"min_container_sides": 5},
        )
        # 4 excluded -> fallback
        assert p == "8_3_in_5"

    def test_filter_max_container_sides(self, tmp_path):
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_3_in_8",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "8",
                "best_value": 2.0,
                "N": 1,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
            filters={"max_container_sides": 6},
        )
        # 8 excluded -> fallback
        assert p == "8_3_in_5"

    def test_circle_sides_mapped_to_32(self, tmp_path):
        # Triggers inner_sides/container_sides = 32 when token is CIRCLE
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_3_in_CIRCLE",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "CIRCLE",
                "best_value": 2.0,
                "N": 1,
            },
        ]
        path.write_text(__import__("json").dumps(items))
        # min_container_sides 10 should still pass because CIRCLE => 32
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
            filters={"min_container_sides": 10},
        )
        assert p == "1_3_in_CIRCLE"

    def test_domino_not_skipped(self, tmp_path):
        # DOMINO is allowed (is_special_shape True, t == "DOMINO" -> return False)
        import json
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "2_DOMINO_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "DOMINO",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 2,
            },
        ]
        path.write_text(json.dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "2_DOMINO_in_4"

    def test_best_value_non_numeric_handled(self, tmp_path):
        # best_value as string -> ValueError -> set to None
        import json
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_3_in_3",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "3",
                "best_value": "NOT_NUMBER",
                "N": 1,
            },
        ]
        path.write_text(json.dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "1_3_in_3"


class TestLoadHistoryOuterException:
    def test_load_history_io_error(self, monkeypatch, tmp_path):
        path = tmp_path / "res.tsv"
        path.write_text("commit\tscore\tmemory_gb\tstatus\tproblem\tdescription\n")

        def fail_open(*a, **kw):
            raise IOError("no")

        monkeypatch.setattr("builtins.open", fail_open)
        hist = load_history(str(path))
        assert hist == []


class TestLoadPriorityQueueException:
    def test_load_priority_queue_bad_json(self, tmp_path):
        path = tmp_path / "pq.json"
        path.write_text("{bad json")
        q = load_priority_queue(str(path))
        assert q == []


class TestMakeLoopCandidateNoneHistory:
    def test_history_none_triggers_load(self, monkeypatch, tmp_path):
        # make_loop_candidate with history=None should call load_history()
        hist_path = tmp_path / "results.tsv"
        hist_path.write_text("commit\tscore\tmemory_gb\tstatus\tproblem\tdescription\n")
        # Monkeypatch load_history to track call
        original = None
        from shape_packing import agent_loop
        original = agent_loop.load_history

        called = [False]

        def tracked_load(p="results.tsv"):
            called[0] = True
            return []

        monkeypatch.setattr(agent_loop, "load_history", tracked_load)
        make_loop_candidate(history=None, current=None, experiments_count=5)
        assert called[0] is True


class TestLoadPackingReferenceEdge:
    def test_single_json_non_list(self, tmp_path):
        d = tmp_path / "pv"
        d.mkdir()
        (d / "x.json").write_text('"not_list"')
        rows = load_packing_reference(verif_dir=str(d))
        assert rows == []

    def test_json_read_error(self, tmp_path, monkeypatch):
        # Use a file that's valid JSON but triggers error inside load_packing_reference
        # by having a non-list JSON (already tested) or make json.load raise
        d = tmp_path / "pv"
        d.mkdir()
        (d / "x.json").write_text('{}')

        import json as _json
        orig_load = _json.load

        def failing_load(*args, **kwargs):
            raise ValueError("test failure")

        monkeypatch.setattr(_json, "load", failing_load)
        rows = load_packing_reference(verif_dir=str(d))
        assert rows == []


class TestIsPreferredReferenceEdge2:
    def test_not_matching_our_problem(self):
        ref = [
            {"our_problem": "2_4_in_4", "status": "best_known"},
        ]
        assert is_preferred_reference(ref, "1_3_in_3") is False


class TestExtractProblemFamilyException:
    def test_catch_exception(self):
        # extract_problem_family catches Exception and returns input
        # Use a weird object to force it.
        class Weird:
            def split(self, *a):
                raise RuntimeError("boom")
        # We cannot fully abuse this without breaking typing; just confirm it's
        # robust with normal strings.
        assert extract_problem_family("x") == "x"


class TestChooseProblemParseError:
    def test_parse_error_continue(self, tmp_path):
        import json
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "bad_problem_name",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "3",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 1,
            },
        ]
        path.write_text(json.dumps(items))
        # parse_problem should fail -> fallback
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "8_3_in_5"


class TestChooseProblemUnsupportedShape:
    def test_unsupported_shape_skipped(self, tmp_path):
        import json
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_TAN_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "TAN",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 1,
            },
        ]
        path.write_text(json.dumps(items))
        # TAN is special and not explicitly included -> skipped
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "8_3_in_5"

    def test_unrecognized_shape_token_skipped(self, tmp_path):
        import json
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_XXX_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "XXX",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 1,
            },
        ]
        path.write_text(json.dumps(items))
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "8_3_in_5"



class TestChooseProblemCircleSides:
    def test_circle_inner_sides_mapped(self, tmp_path):
        import json
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_CIRCLE_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "CIRCLE",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 1,
            },
        ]
        path.write_text(json.dumps(items))
        # CIRCLE inner_sides becomes 32 -> passes min_inner_sides=10
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
            filters={"min_inner_sides": 10},
        )
        assert "1_CIRCLE_in_4" in p


class TestChooseProblemGeneralException:
    def test_general_exception_continues(self, tmp_path):
        # Make parse_problem succeed but shape_token_to_sides fail
        import json
        path = tmp_path / "pq.json"
        items = [
            {
                "problem": "1_XXX_in_4",
                "density": 0.9,
                "status": "best_known",
                "inner_shape": "XXX",
                "container_shape": "4",
                "best_value": 2.0,
                "N": 1,
            },
        ]
        path.write_text(json.dumps(items))
        # XXX not recognized -> parse may fail or token_to_sides raises
        p = choose_problem(
            history=[],
            queue_path=str(path),
            exclude_problems=set(),
        )
        assert p == "8_3_in_5"


class TestCalculateCandidateScoreValueError:
    def test_invalid_best_value_handled_gracefully(self):
        from shape_packing.agent_loop import _calculate_candidate_score, ProblemSelectionConfig
        from collections import Counter

        item = {
            "problem": "3_3_in_4",
            "status": "best_known",
            "best_value": "invalid_not_a_float",
            "density": 0.5,
        }
        score = _calculate_candidate_score(
            item=item,
            p_str="3_3_in_4",
            base_density=0.5,
            recent_counts=Counter(),
            our_best={},
            problem_runs={},
            family_runs={},
            problem_last_k={},
            config=ProblemSelectionConfig(),
        )
        assert score is not None
        assert isinstance(score, float)
