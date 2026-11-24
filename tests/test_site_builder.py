"""Tests for scripts/build_site_data.py metric normalization, slug mapping, and Frontier inclusion."""
import math
import pytest


def test_build_site_data_metric_roundtrip_parity():
    from scripts.build_site_data import compute_friedman_metric, inverse_friedman_metric

    for inner, container, s_val in [
        ("CIRCLE", "L", 2.0),
        ("L", "L", 2.5),
        ("CIRCLE", "7", 1.5),
        ("CIRCLE", "SEMICIRCLE", 2.0),
        ("CIRCLE", "QUADRANT", 1.0 + math.sqrt(2.0)),
        ("RHOMBUS", "TRAPEZOID", 3.2),
        ("PARALLELOGRAM", "4", 2.4),
    ]:
        f = compute_friedman_metric(s_val, inner, container)
        s_back = inverse_friedman_metric(f, inner, container)
        assert abs(s_back - s_val) < 1e-9, f"Roundtrip failed for {inner} in {container}"


def test_build_site_data_fixes_lincir_linsqu_and_cirinttt_slugs():
    from scripts.build_site_data import normalize_family_slug, FAMILY_DISPLAY_NAMES

    assert normalize_family_slug("lincir") == "L_in_circle"
    assert normalize_family_slug("linsqu") == "L_in_4"
    assert normalize_family_slug("cirinttt") == "circle_in_arbitrary_triangle"
    assert normalize_family_slug("cirinsemi") == "circle_in_semicircle"
    assert normalize_family_slug("cirinquad") == "circle_in_quadrant"
    assert "rhombus_in_4" in FAMILY_DISPLAY_NAMES
