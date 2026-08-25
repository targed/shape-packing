import pytest
import os
import json
from src.shape_packing.packing_config import (
    load_family_colors,
    load_family_properties,
    get_family_colors,
    get_family_properties,
    get_family_target_filename,
    FAMILY_PROPERTIES_PATH,
    FAMILY_COLORS_PATH,
)
from src.shape_packing.solution_tools import render_solution

def test_family_properties_json_exists():
    assert os.path.exists(FAMILY_PROPERTIES_PATH)
    props = load_family_properties()
    assert len(props) >= 60
    assert "dominpen" in props
    assert "cirinpen" in props
    assert "dominhex" in props
    assert "cirinhex" in props

def test_get_family_properties_by_family_name():
    # Regular family
    p = get_family_properties("dominpen")
    assert p["inner"].lower() == "#fed4d1"
    assert p["container"].lower() == "#ffffff"
    assert p["width"] == 250
    assert p["height"] == 237
    assert p["file_format"] == "png"
    assert p["filename_template"] == "{n}.png"

    # cirinpen with special container color and pent.<n>.png naming
    p_pen = get_family_properties("cirinpen")
    assert p_pen["inner"].lower() == "#99ff99"
    assert p_pen["container"].lower() == "#fff3e6"
    assert p_pen["width"] == 212
    assert p_pen["height"] == 201
    assert p_pen["filename_template"] == "pent.{n}.png"

    # cirinhex with hc<n>.gif naming
    p_hex = get_family_properties("cirinhex")
    assert p_hex["file_format"] == "gif"
    assert p_hex["filename_template"] == "hc{n}.gif"
    assert p_hex["width"] == 180
    assert p_hex["height"] == 156

def test_get_family_target_filename():
    assert get_family_target_filename("cirinpen", 21) == "pent.21.png"
    assert get_family_target_filename("cirinhex", 22) == "hc22.gif"
    assert get_family_target_filename("cirincir", 5) == "ccc5.gif"
    assert get_family_target_filename("squintri", 6) == "ts6.gif"
    assert get_family_target_filename("triinsqu", 4) == "t4.gif"
    assert get_family_target_filename("dominhex", 2) == "2.png"
    assert get_family_target_filename("dominpen", 21) == "21.png"

def test_get_family_properties_variable_warning(capsys):
    p = get_family_properties("cirinel")
    captured = capsys.readouterr()
    assert "[WARN]" in captured.out
    assert "cirinel" in captured.out
    assert p["variable_dimensions"] is True
    assert p["manual_check_required"] is True
    assert p["filename_template"] == "e{n}.gif"

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
    from PIL import Image
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
    img = Image.open(out_png)
    # dominpen default resolution is 250x237
    assert img.size == (250, 237)
