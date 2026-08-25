import csv
import math

import pytest

from src.shape_packing.packing_config import (
    get_problem_history_stats,
    get_friedman_best_for_problem,
    compute_problem_difficulty_score,
)


@pytest.fixture
def history_path() -> str:
    return "results.tsv"


def _min_score_for_problem(problem: str, path: str) -> float | None:
    """Utility: read TSV and return minimum numeric score for given problem."""
    best = None
    with open(path, newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if (row.get("problem") or "").strip() != problem:
                continue
            raw = (row.get("score") or "").strip()
            try:
                v = float(raw)
            except (ValueError, TypeError):
                continue
            if best is None or v < best:
                best = v
    return best


def test_get_problem_history_stats_basic(history_path: str):
    """
    Basic sanity check using a real problem from results.tsv.
    """
    # 1_3_in_3 is known to exist in results.tsv.
    problem = "1_3_in_3"
    stats = get_problem_history_stats(problem, history_path=history_path)

    assert isinstance(stats, dict)

    # Required keys
    assert "total_runs" in stats
    assert "success_count" in stats
    assert "failure_count" in stats
    assert "best_score" in stats

    # Basic invariants
    assert stats["total_runs"] >= 0

    # All rows are classified as either success or failure (no ambiguous cases for this problem)
    # At minimum, their sum cannot exceed total_runs
    assert stats["success_count"] + stats["failure_count"] <= stats["total_runs"]

    # best_score should match independently computed minimum from TSV
    expected_best = _min_score_for_problem(problem, history_path)
    if expected_best is not None:
        assert stats["best_score"] is not None
        assert math.isclose(stats["best_score"], expected_best, rel_tol=1e-9, abs_tol=1e-9)
    else:
        # If no numeric scores at all, best_score must be None
        assert stats["best_score"] is None


def test_get_problem_history_stats_nonexistent_problem(history_path: str):
    """
    When problem does not appear in TSV, all counts should be zero and best_score None.
    """
    stats = get_problem_history_stats("DOES_NOT_EXIST_problem", history_path=history_path)

    assert stats["total_runs"] == 0
    assert stats["success_count"] == 0
    assert stats["failure_count"] == 0
    assert stats["best_score"] is None


def test_get_problem_history_stats_cache_behavior(history_path: str):
    """
    Ensure caching semantics:
    - If cache dict provided and contains problem, that value is returned.
    - If cache dict provided and does not contain problem, it is populated.
    - If cache is None, function still works and does not try to modify it.
    """
    problem = "1_3_in_3"

    # 1) Without cache
    stats_no_cache = get_problem_history_stats(problem, history_path=history_path, cache=None)

    # 2) With empty cache: should fill it
    cache: dict = {}
    stats_with_cache = get_problem_history_stats(problem, history_path=history_path, cache=cache)

    assert stats_with_cache == stats_no_cache
    assert problem in cache

    # 3) Second call with same cache: should return cached value (same content)
    stats_cached = get_problem_history_stats(problem, history_path=history_path, cache=cache)
    assert stats_cached == stats_no_cache

    # 4) Pre-populated cache is respected
    fake_stats = {"total_runs": 999, "success_count": 999, "failure_count": 0, "best_score": -999.0}
    override_cache = {problem: fake_stats}
    stats_overridden = get_problem_history_stats(problem, history_path=history_path, cache=override_cache)
    assert stats_overridden == fake_stats


def test_get_problem_history_stats_missing_file():
    """
    If history file does not exist, return zeroed-out stats.
    """
    stats = get_problem_history_stats("anything", history_path="DOES_NOT_EXIST.tsv")

    assert stats["total_runs"] == 0
    assert stats["success_count"] == 0
    assert stats["failure_count"] == 0
    assert stats["best_score"] is None


def test_load_all_problem_history_stats_caching(tmp_path):
    from src.shape_packing.packing_config import load_all_problem_history_stats
    tsv = tmp_path / "results.tsv"
    tsv.write_text("problem\tscore\tstatus\n1_3_in_3\t2.5\tsuccess\n1_3_in_3\t2.1\tsuccess\n2_3_in_3\t3.0\tFAIL\n")

    s1 = load_all_problem_history_stats(str(tsv))
    norm_k = "1_3_in_3"
    assert s1[norm_k]["total_runs"] == 2
    assert s1[norm_k]["success_count"] == 2
    assert s1[norm_k]["best_score"] == 2.1

    # Second call returns identical cached dictionary
    s2 = load_all_problem_history_stats(str(tsv))
    assert s1 is s2


# ---- Friedman best lookup tests ----


class TestGetFriedmanBestForProblem:
    """
    Tests for get_friedman_best_for_problem(...)
    These rely on the packingVerification JSON files only (no TSV).
    """

    def test_known_cirincir_problem(self):
        # Example problem name pattern: '5_CIRCLE_in_CIRCLE'
        # If it exists in cirincir.json, we expect a float best_score.
        best = get_friedman_best_for_problem("5_CIRCLE_in_CIRCLE")
        # Just ensure it behaves: either a float or None (file may not contain this exact problem)
        assert best is None or isinstance(best, float)

    def test_nonexistent_problem_returns_none(self):
        best = get_friedman_best_for_problem("DOES_NOT_EXIST_problem")
        assert best is None

    def test_cache_is_populated(self):
        # Internal sanity: after a call, the module-level cache should contain something.
        from src.shape_packing import packing_config

        # Trigger a lookup
        get_friedman_best_for_problem("1_CIRCLE_in_CIRCLE")
        # Ensure cache was actually filled (at least one entry).
        assert len(packing_config._FRIEDMAN_BEST_CACHE) > 0


# ---- Difficulty scoring tests ----


class TestComputeProblemDifficultyScore:
    """
    Tests for compute_problem_difficulty_score(...)
    Use synthetic stats and simple problem strings to check behavior.
    """

    def _stats(
        self,
        total_runs: int = 100,
        success_count: int = 60,
        failure_count: int = 40,
        best_score: float | None = 0.5,
    ) -> dict:
        return {
            "total_runs": total_runs,
            "success_count": success_count,
            "failure_count": failure_count,
            "best_score": best_score,
        }

    def test_basic_return_type_and_range(self):
        score = compute_problem_difficulty_score(
            "2_domino_in_5",
            stats=self._stats(),
            friedman_best=None,
        )
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_easy_problem_low_difficulty(self):
        """
        Low N, low failure ratio, no gap info -> should be relatively low.
        """
        # N=2, total=100, failure=10 => failure_ratio=0.1
        score = compute_problem_difficulty_score(
            "2_domino_in_5",
            stats=self._stats(total_runs=100, failure_count=10, success_count=90),
            friedman_best=None,
        )
        # Expect: base 0.3 + small failure term; definitely < 0.6
        assert score < 0.6

    def test_high_N_increases_difficulty(self):
        """
        Larger N should push score up due to N >= 10 / >= 15 bonuses.
        """
        low_N = compute_problem_difficulty_score(
            "5_squares_in_5",
            stats=self._stats(),
            friedman_best=None,
        )
        high_N_10 = compute_problem_difficulty_score(
            "10_squares_in_5",
            stats=self._stats(),
            friedman_best=None,
        )
        high_N_15 = compute_problem_difficulty_score(
            "15_squares_in_5",
            stats=self._stats(),
            friedman_best=None,
        )

        # Each step should not be lower than the previous
        assert high_N_10 >= low_N
        assert high_N_15 >= high_N_10

    def test_high_failure_ratio_increases_difficulty(self):
        """
        If almost everything fails, difficulty should be higher.
        """
        easy = compute_problem_difficulty_score(
            "2_domino_in_5",
            stats=self._stats(total_runs=100, failure_count=5, success_count=95),
            friedman_best=None,
        )
        hard = compute_problem_difficulty_score(
            "2_domino_in_5",
            stats=self._stats(total_runs=100, failure_count=90, success_count=10),
            friedman_best=None,
        )
        assert hard > easy

    def test_gap_to_friedman_increases_difficulty(self):
        """
        If our best_score is worse (larger) than Friedman's best,
        difficulty should be higher than when they match.
        """
        stats_good_gap = self._stats(best_score=1.0)
        stats_close_gap = self._stats(best_score=0.55)
        friedman = 0.5

        score_wide = compute_problem_difficulty_score(
            "2_domino_in_5",
            stats=stats_good_gap,
            friedman_best=friedman,
        )
        score_tight = compute_problem_difficulty_score(
            "2_domino_in_5",
            stats=stats_close_gap,
            friedman_best=friedman,
        )
        assert score_wide > score_tight

    def test_clamping_at_one(self):
        """
        Extreme inputs should not exceed 1.0.
        """
        score = compute_problem_difficulty_score(
            "50_domino_in_5",
            stats=self._stats(total_runs=100, failure_count=100, success_count=0, best_score=100.0),
            friedman_best=1.0,
        )
        assert 0.0 <= score <= 1.0

    def test_zero_runs_uses_default_behavior(self):
        """
        With zero runs, failure_ratio should not blow up; function must not raise.
        """
        score = compute_problem_difficulty_score(
            "3_squares_in_5",
            stats=self._stats(total_runs=0, success_count=0, failure_count=0, best_score=None),
            friedman_best=None,
        )
        assert 0.0 <= score <= 1.0


# ---- compute_adaptive_attempts tests ----


class TestComputeAdaptiveAttempts:
    """
    Tests for compute_adaptive_attempts(...)
    """

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.shape_packing.packing_config import compute_adaptive_attempts
        self.ca = compute_adaptive_attempts

    # ---------- basic behavior ----------

    def test_returns_int(self):
        v = self.ca(0.5)
        assert isinstance(v, int)

    def test_min_difficulty_yields_low_attempts(self):
        v0 = self.ca(0.0)
        v1 = self.ca(0.1)
        v2 = self.ca(0.2)
        # All should be relatively low
        assert v0 <= v1
        assert v1 <= v2
        # Should be in lower range
        from src.shape_packing.packing_config import LOOP_DEFAULT_ATTEMPTS
        assert v2 <= LOOP_DEFAULT_ATTEMPTS

    def test_max_difficulty_yields_high_attempts(self):
        v = self.ca(1.0)
        # Should be at max_attempts (default 200_000)
        assert v == 200_000

    def test_monotonic_across_full_range(self):
        """
        Higher difficulty must never decrease attempts.
        """
        prev = 0
        for d_int in range(0, 101, 1):
            d = d_int / 100.0
            attempts = self.ca(d)
            assert attempts >= prev, (
                f"Monotonicity violation: difficulty {d:.2f} -> {attempts} < {prev}"
            )
            prev = attempts

    def test_within_bounds_default(self):
        """
        All outputs must lie in [min_attempts, max_attempts] with defaults.
        """
        min_a = 500
        max_a = 200_000
        for d_int in range(0, 101, 5):
            d = d_int / 100.0
            v = self.ca(d)
            assert min_a <= v <= max_a, f"Out of range at difficulty {d:.2f}: {v}"

    def test_within_bounds_custom(self):
        """
        Custom min/max must be respected.
        """
        mn = 1_000
        mx = 50_000
        for d in [0.0, 0.2, 0.5, 0.8, 1.0]:
            v = self.ca(d, min_attempts=mn, max_attempts=mx)
            assert mn <= v <= mx, f"At difficulty {d}: {v}"

    # ---------- stuck / hard bias ----------

    def test_stuck_increases_attempts(self):
        """
        For same difficulty, 'stuck' status should yield >= normal.
        """
        for d in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
            normal = self.ca(d, status="normal")
            stuck = self.ca(d, status="stuck")
            assert stuck >= normal, (
                f"stuck should be >= normal at difficulty {d}, "
                f"got {stuck} < {normal}"
            )
        # And for at least some difficulties, strictly greater.
        assert self.ca(0.3, status="stuck") > self.ca(0.3, status="normal")

    def test_hard_increases_attempts(self):
        """
        For same difficulty, 'hard' status should yield >= normal.
        """
        for d in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
            normal = self.ca(d, status="normal")
            hard = self.ca(d, status="hard")
            assert hard >= normal, (
                f"hard should be >= normal at difficulty {d}, "
                f"got {hard} < {normal}"
            )
        assert self.ca(0.5, status="hard") > self.ca(0.5, status="normal")

    # ---------- band behavior (structural) ----------

    def test_low_band(self):
        """
        difficulty in [0, 0.2] -> attempts in [min, LOOP_DEFAULT_ATTEMPTS].
        """
        from src.shape_packing.packing_config import LOOP_DEFAULT_ATTEMPTS
        mn = 500
        v0 = self.ca(0.0)
        v1 = self.ca(0.1)
        v2 = self.ca(0.2)
        assert mn <= v0 <= LOOP_DEFAULT_ATTEMPTS
        assert mn <= v1 <= LOOP_DEFAULT_ATTEMPTS
        assert mn <= v2 <= LOOP_DEFAULT_ATTEMPTS

    def test_mid_band(self):
        """
        difficulty in (0.2, 0.5] -> attempts in [LOOP_DEFAULT_ATTEMPTS, LOOP_HIGH_N_ATTEMPTS].
        """
        from src.shape_packing.packing_config import (
            LOOP_DEFAULT_ATTEMPTS,
            LOOP_HIGH_N_ATTEMPTS,
        )
        v21 = self.ca(0.25)
        v35 = self.ca(0.35)
        v50 = self.ca(0.5)
        assert LOOP_DEFAULT_ATTEMPTS <= v21 <= LOOP_HIGH_N_ATTEMPTS
        assert LOOP_DEFAULT_ATTEMPTS <= v35 <= LOOP_HIGH_N_ATTEMPTS
        assert LOOP_DEFAULT_ATTEMPTS <= v50 <= LOOP_HIGH_N_ATTEMPTS

    def test_high_mid_band(self):
        """
        difficulty in (0.5, 0.8] -> attempts in [LOOP_HIGH_N_ATTEMPTS, max*0.7].
        """
        from src.shape_packing.packing_config import LOOP_HIGH_N_ATTEMPTS
        mx = 200_000
        upper_mid = mx * 0.7
        v60 = self.ca(0.6)
        v80 = self.ca(0.8)
        assert LOOP_HIGH_N_ATTEMPTS <= v60 <= upper_mid
        assert LOOP_HIGH_N_ATTEMPTS <= v80 <= upper_mid

    def test_top_band(self):
        """
        difficulty in (0.8, 1.0] -> attempts in [max*0.7, max].
        """
        mx = 200_000
        lower = mx * 0.7
        v90 = self.ca(0.9)
        v100 = self.ca(1.0)
        assert lower <= v90 <= mx
        assert lower <= v100 <= mx

    # ---------- edge and sanity ----------

    def test_out_of_range_clamped(self):
        """
        difficulty outside [0,1] should be clamped, not raise.
        """
        v_neg = self.ca(-0.3)
        v_pos = self.ca(1.5)
        v0 = self.ca(0.0)
        v1 = self.ca(1.0)
        assert v_neg == v0
        assert v_pos == v1

    def test_no_effect_on_other_functions(self):
        """
        Sanity: importing compute_adaptive_attempts does not break others.
        """
        from src.shape_packing.packing_config import (
            get_problem_history_stats,
            get_friedman_best_for_problem,
            compute_problem_difficulty_score,
        )
        # Ensure they are callable
        stats = get_problem_history_stats("X")
        assert isinstance(stats, dict)
        fb = get_friedman_best_for_problem("X")
        assert fb is None or isinstance(fb, float)
        s = compute_problem_difficulty_score(
            "2_domino_in_5",
            stats={"total_runs": 10, "success_count": 5, "failure_count": 5, "best_score": 0.5},
            friedman_best=None,
        )
        assert 0.0 <= s <= 1.0
