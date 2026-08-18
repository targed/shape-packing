import pytest
import os
import json
from src.shape_packing.packing_config import (
    load_family_colors,
    get_family_colors,
    FAMILY_COLORS_PATH,
)
from src.shape_packing.solution_tools import render_solution

def test_family_colors_json_exists():
    assert os.path.exists(FAMILY_COLORS_PATH)
    colors = load_family_colors()
    assert len(colors) >= 60
    assert "dominpen" in colors
    assert "cirinpen" in colors
    assert "dominhex" in colors

def test_get_family_colors_by_family_name():
    # Regular family
    c = get_family_colors("dominpen")
    assert c["inner"].lower() == "#fed4d1"
    assert c["container"].lower() == "#ffffff"

    # cirinpen with special container color
    c_pen = get_family_colors("cirinpen")
    assert c_pen["inner"].lower() == "#99ff99"
    assert c_pen["container"].lower() == "#fff3e6"

    # Mixed case family name
    c_l = get_family_colors("dominL")
    assert c_l["inner"].lower() == "#feffdc"

def test_get_family_colors_by_tokens():
    c = get_family_colors("DOMINO", "5")
    assert c["inner"].lower() == "#fed4d1"

    c_hex = get_family_colors("DOMINO", "6")
    assert c_hex["inner"].lower() == "#fed4d1"

    c_oct = get_family_colors("DOMINO", "8")
    assert c_oct["inner"].lower() == "#fdf4c0"

    c_squ = get_family_colors("4", "CIRCLE")
    assert c_squ["inner"].lower() == "#cccccc"

def test_get_family_colors_by_problem_string():
    c = get_family_colors("21_DOMINO_in_5")
    assert c["inner"].lower() == "#fed4d1"

    c2 = get_family_colors("22_CIRCLE_in_6")
    assert c2["inner"].lower() == "#b5b5b5"

def test_get_family_colors_fallback():
    c = get_family_colors("nonexistent_shape", "nonexistent_container")
    assert "inner" in c
    assert "container" in c

def test_render_solution_applies_family_colors(tmp_path):
    sol_file = tmp_path / "solution.json"
    sol_file.write_text(json.dumps({
        "N": 2,
        "inner_token": "DOMINO",
        "container_token": "5",
        "S": 2.0,
        "final_metric": 2.0,
        "values": [0.0, 0.0, 0.0, 0.5, 0.5, 0.0]
    }))
    out_png = tmp_path / "rendered.png"
    render_solution(str(sol_file), str(out_png))
    assert os.path.exists(out_png)
    assert os.path.getsize(out_png) > 0
