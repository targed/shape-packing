"""Tests for the universal packing config module."""
import pytest
from src.shape_packing.packing_config import (
    # Geometry
    CIRCLE_SIDES,
    # Rust solver
    RUST_BINARY,
    RUST_TOLERANCE,
    RUST_DEFAULT_ATTEMPTS,
    RUST_DEFAULT_TIME_LIMIT,
    # Python optimizer
    OPTIMIZER_ATTEMPTS,
    OPTIMIZER_TOLERANCE,
    OPTIMIZER_FINAL_STEP,
    OPTIMIZER_N_JOBS,
    # Verification
    VERIFY_SAT_TOLERANCE,
    VERIFY_METRIC_TOLERANCE,
    GEOMETRY_SAT_TOLERANCE,
    MIN_VALID_CIRCLE_SCORE,
    # Loop & scheduling
    LOOP_SLEEP_BETWEEN_RUNS,
    LOOP_MAX_CONSECUTIVE_FAILURES,
    LOOP_BASE_BACKOFF,
    LOOP_MAX_BACKOFF,
    LOOP_DEFAULT_ATTEMPTS,
    LOOP_HIGH_N_THRESHOLD,
    LOOP_HIGH_N_ATTEMPTS,
    LOOP_STUCK_ATTEMPTS,
    LOOP_STUCK_SWARM_COUNT,
    LOOP_HARD_SWARM_COUNT,
    # Priority queue
    QUEUE_FALLBACK_PROBLEM,
    QUEUE_RECENT_WINDOW,
    QUEUE_PROBLEM_CAP1,
    QUEUE_PROBLEM_CAP2,
    QUEUE_FAMILY_CAP1,
    QUEUE_FAMILY_CAP2,
    # Paths
    RESULTS_TSV_PATH,
    RESULTS_DIR,
    PRIORITY_QUEUE_PATH,
    PACKING_VERIFICATION_DIR,
    FILTER_JSON_PATH,
    PACKING_REFERENCE_TSV,
    # Rendering
    RENDER_DPI,
    RENDER_FIGURE_SIZE,
    ANALYSIS_PLOT_DPI,
)


def test_geometry_constants():
    assert isinstance(CIRCLE_SIDES, int)
    assert CIRCLE_SIDES >= 3


def test_rust_constants():
    assert isinstance(RUST_BINARY, str) and len(RUST_BINARY) > 0
    assert isinstance(RUST_TOLERANCE, str)
    assert isinstance(RUST_DEFAULT_ATTEMPTS, int) and RUST_DEFAULT_ATTEMPTS > 0
    assert isinstance(RUST_DEFAULT_TIME_LIMIT, int) and RUST_DEFAULT_TIME_LIMIT > 0


def test_optimizer_constants():
    assert isinstance(OPTIMIZER_ATTEMPTS, int) and OPTIMIZER_ATTEMPTS > 0
    assert 0 < OPTIMIZER_TOLERANCE < 1
    assert 0 < OPTIMIZER_FINAL_STEP < 1
    assert isinstance(OPTIMIZER_N_JOBS, int)


def test_verification_tolerances():
    assert 0 < VERIFY_SAT_TOLERANCE < 1
    assert 0 < VERIFY_METRIC_TOLERANCE < 1
    assert 0 < GEOMETRY_SAT_TOLERANCE < 1
    assert 0 < MIN_VALID_CIRCLE_SCORE < 1


def test_loop_constants():
    assert LOOP_SLEEP_BETWEEN_RUNS >= 0
    assert LOOP_MAX_CONSECUTIVE_FAILURES > 0
    assert LOOP_BASE_BACKOFF > 0
    assert LOOP_MAX_BACKOFF >= LOOP_BASE_BACKOFF
    assert LOOP_DEFAULT_ATTEMPTS > 0
    assert LOOP_HIGH_N_THRESHOLD > 0
    assert LOOP_HIGH_N_ATTEMPTS > LOOP_DEFAULT_ATTEMPTS
    assert LOOP_STUCK_ATTEMPTS > LOOP_HIGH_N_ATTEMPTS
    assert LOOP_STUCK_SWARM_COUNT > 0
    assert LOOP_HARD_SWARM_COUNT > 0


def test_queue_constants():
    assert isinstance(QUEUE_FALLBACK_PROBLEM, str) and "_in_" in QUEUE_FALLBACK_PROBLEM
    assert QUEUE_RECENT_WINDOW > 0
    assert QUEUE_PROBLEM_CAP1 < QUEUE_PROBLEM_CAP2
    assert QUEUE_FAMILY_CAP1 < QUEUE_FAMILY_CAP2


def test_path_constants():
    for p in [RESULTS_TSV_PATH, RESULTS_DIR, PRIORITY_QUEUE_PATH,
              PACKING_VERIFICATION_DIR, FILTER_JSON_PATH, PACKING_REFERENCE_TSV]:
        assert isinstance(p, str) and len(p) > 0


def test_render_constants():
    assert isinstance(RENDER_DPI, int) and RENDER_DPI > 0
    assert len(RENDER_FIGURE_SIZE) == 2
    assert isinstance(ANALYSIS_PLOT_DPI, int) and ANALYSIS_PLOT_DPI > 0


def test_normalize_key_circle_substring_bug_fixed():
    from src.shape_packing.packing_config import _normalize_key
    assert _normalize_key("1_CIRCLE_in_CIRCLE") == "1_circle_in_circle"
    assert _normalize_key("1_cir_in_cir") == "1_circle_in_circle"
    assert _normalize_key("1_CIRC_in_CIRC") == "1_circle_in_circle"
    assert _normalize_key("20_PENTAGON_in_HEXAGON") == "20_5_in_6"
    assert _normalize_key("21_DOMINO_in_PENTAGON") == "21_domino_in_5"
    assert _normalize_key("21_dom_in_5") == "21_domino_in_5"


def test_tangram_triangle_vertices_canonical():
    import math
    from src.shape_packing.packing_config import tangram_triangle_vertices
    verts = tangram_triangle_vertices(1.0)
    assert len(verts) == 3
    # Verify right isosceles triangle with legs of length 1.0
    dx1 = verts[1][0] - verts[0][0]
    dy1 = verts[1][1] - verts[0][1]
    dx2 = verts[2][0] - verts[0][0]
    dy2 = verts[2][1] - verts[0][1]
    assert abs(math.hypot(dx1, dy1) - 1.0) < 1e-6
    assert abs(math.hypot(dx2, dy2) - 1.0) < 1e-6


def test_shape_catalog_normalization_and_pair_support():
    from src.shape_packing.catalog import (
        normalize_token,
        is_pair_supported,
        list_frontier_families,
        get_pair_tier,
    )

    assert normalize_token("heptagon") == "7"
    assert normalize_token("enneagon") == "9"
    assert normalize_token("NONAGON") == "9"
    assert normalize_token("dec") == "10"
    assert normalize_token("semi") == "SEMICIRCLE"
    assert normalize_token("quad") == "QUADRANT"
    assert normalize_token("diamond") == "RHOMBUS"
    assert normalize_token("para") == "PARALLELOGRAM"
    assert normalize_token("trap") == "TRAPEZOID"

    assert is_pair_supported("CIRCLE", "7") is True
    assert is_pair_supported("CIRCLE", "SEMICIRCLE") is True
    assert is_pair_supported("CIRCLE", "QUADRANT") is True
    assert is_pair_supported("4", "SEMICIRCLE") is False
    assert is_pair_supported("TAN", "QUADRANT") is False
    assert is_pair_supported("RHOMBUS", "4") is True
    assert is_pair_supported("7", "9") is False  # unbenchmarked 7x9 not enabled in Option B

    frontier = list_frontier_families()
    # 3 quads paired symmetrically with 6 base shapes (3*6*2=36) + 3x3 quad-in-quad (9) = 45
    assert len(frontier) == 45
    assert get_pair_tier("CIRCLE", "SEMICIRCLE") == "benchmark"
    assert get_pair_tier("RHOMBUS", "4") == "frontier"
