"""Tests for scripts/import_packomania.py and normalized Packomania verification JSONs."""
import json
import math
from pathlib import Path
import pytest


def test_convert_packomania_ngon_and_curved_values():
    from scripts.import_packomania import convert_packomania_to_friedman_s

    # Heptagon N=1: cos(pi/7) -> 2 * tan(pi/7)
    r7 = math.cos(math.pi / 7.0)
    s7 = convert_packomania_to_friedman_s(r7, container_token="7", value_kind="radius", n=1)
    assert abs(s7 - 2.0 * math.tan(math.pi / 7.0)) < 1e-9

    # Octagon N=1: cos(pi/8) -> 2 * (sqrt(2) - 1)
    r8 = math.cos(math.pi / 8.0)
    s8 = convert_packomania_to_friedman_s(r8, container_token="8", value_kind="radius", n=1)
    assert abs(s8 - 2.0 * (math.sqrt(2.0) - 1.0)) < 1e-9

    # Nonagon & Decagon N=1 Packomania half-radius quirk correction
    r9_half = 0.5 * math.cos(math.pi / 9.0)
    s9 = convert_packomania_to_friedman_s(r9_half, container_token="9", value_kind="radius", n=1)
    assert abs(s9 - 2.0 * math.tan(math.pi / 9.0)) < 1e-9

    r10_half = 0.5 * math.cos(math.pi / 10.0)
    s10 = convert_packomania_to_friedman_s(r10_half, container_token="10", value_kind="radius", n=1)
    assert abs(s10 - 2.0 * math.tan(math.pi / 10.0)) < 1e-9

    # Semicircle & Quadrant ratio -> direct Friedman metric s
    assert abs(convert_packomania_to_friedman_s(2.0, container_token="SEMICIRCLE", value_kind="ratio", n=1) - 2.0) < 1e-9
    assert abs(convert_packomania_to_friedman_s(1.0 + math.sqrt(2.0), container_token="QUADRANT", value_kind="ratio", n=1) - (1.0 + math.sqrt(2.0))) < 1e-9


def test_packomania_verification_files_normalized(project_root):
    pv_dir = project_root / "data" / "packingVerification"

    # cirinoct.json must use Friedman octagon edge length (~0.8284 at N=1, growing with N)
    cirinoct = json.loads((pv_dir / "cirinoct.json").read_text(encoding="utf-8"))
    by_n = {int(row["N"]): row for row in cirinoct}
    assert abs(by_n[1]["best_value"] - 2.0 * (math.sqrt(2.0) - 1.0)) < 1e-6
    assert by_n[48]["best_value"] > 4.0

    # cirindom.json must be Circles in Dominoes, not Dominoes in Circles!
    cirindom = json.loads((pv_dir / "cirindom.json").read_text(encoding="utf-8"))
    assert cirindom[0]["inner_shape"] == "circle"
    assert cirindom[0]["container_shape"] == "domino"
    assert abs(cirindom[0]["best_value"] - 2.0) < 1e-6

    # All 5 newly imported Packomania benchmarks exist with exact Packomania range (48 for poly, 50 for curved)
    for fname, c_shape, expected_n in [
        ("cirin7.json", "heptagon", 48),
        ("cirin9.json", "nonagon", 48),
        ("cirin10.json", "decagon", 48),
        ("cirinsemi.json", "semicircle", 50),
        ("cirinquad.json", "quadrant", 50),
    ]:
        rows = json.loads((pv_dir / fname).read_text(encoding="utf-8"))
        assert len(rows) == expected_n, f"Expected {expected_n} rows in {fname}"
        assert rows[0]["inner_shape"] == "circle"
        assert rows[0]["container_shape"] == c_shape
        assert rows[-1]["best_value"] > rows[0]["best_value"]
