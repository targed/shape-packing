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
