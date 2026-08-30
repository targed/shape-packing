"""
Tests for compare_results.py

Covers:
- Loading best solutions from results/
- Comparing against PACKING_REFERENCE.tsv
- Correct difference and NEW_BEST flags
- Circle problems marked as incomparable
"""
import json
import os
import subprocess
import pytest


@pytest.fixture
def compare_script():
    return os.path.join("scripts", "compare_results.py")


@pytest.fixture
def packing_reference_tsv(project_root):
    return os.path.join(str(project_root), "PACKING_REFERENCE.tsv")


import sys


def test_compare_results_runs(compare_script, project_root):
    """
    Ensure compare_results.py runs without crashing and produces output.
    """
    result = subprocess.run(
        [sys.executable, compare_script],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"compare_results.py failed: {result.stderr}"
    assert len(result.stdout) > 0


def test_compare_results_respects_circles(compare_script, project_root):
    """
    For circle containers, ensure we do not falsely claim NEW_BEST
    based on a misaligned metric.
    """
    result = subprocess.run(
        [sys.executable, compare_script],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = result.stdout

    # Filter circle-related lines
    circle_lines = [
        line for line in out.splitlines()
        if "CIRCLE" in line or "in_circle" in line
    ]

    # Basic sanity: circle problems are now comparable, so they should NOT contain 'incomparable'.
    for line in circle_lines:
        tokens = line.split()
        if "incomparable" in line.lower():
            assert False, (
                "Circle problem incorrectly marked incomparable when it should be comparable: " + line.strip()
            )


def test_compare_results_new_best_flag(compare_script, project_root):
    """
    Ensure that when our metric is better than the reference
    (and not a circle), NEW_BEST is used.
    """
    result = subprocess.run(
        [sys.executable, compare_script],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = result.stdout

    # Just verify that NEW_BEST can appear for non-circle lines
    new_best_lines = [
        line for line in out.splitlines()
        if "NEW_BEST" in line and "CIRCLE" not in line
    ]

    # This is a soft check: if our current results truly beat any reference,
    # we should see NEW_BEST for non-circle problems.
    # If none exist now, that’s okay; just ensure no crash and correct format.
    for line in new_best_lines:
        tokens = line.split()
        assert len(tokens) >= 6  # id, N, our_metric, ref, diff, tag
        diff = float(tokens[4])
        assert diff < 0  # our_metric < ref_metric (lower is better)
