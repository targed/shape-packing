import pytest
import json
import os
from src.shape_packing.records_exporter import (
    RecordCandidate,
    ExportResult,
    get_family_info,
)

def test_record_candidate_creation():
    rc = RecordCandidate(
        problem="21_DOMINO_in_5",
        N=21,
        inner_token="DOMINO",
        container_token="5",
        solution_path="results/21_DOMINO_in_5/20260806_230206/solution.json",
        run_dir="results/21_DOMINO_in_5/20260806_230206",
        S=4.603855,
        metric=5.412156,
        friedman_best=5.553080,
        improvement=-0.140924,
    )
    assert rc.problem == "21_DOMINO_in_5"
    assert rc.family_code == "dominpen"
    assert "erich-friedman.github.io" in rc.family_url

def test_get_family_info():
    code, url = get_family_info("DOMINO", "5")
    assert code == "dominpen"
    assert "dominpen" in url

    code, url = get_family_info("DOMINO", "6")
    assert code == "dominhex"

    code, url = get_family_info("4", "CIRCLE")
    assert code == "squincir"

def test_find_all_records_discovery(tmp_path):
    p_dir = tmp_path / "results" / "21_DOMINO_in_5" / "20260806_230206"
    p_dir.mkdir(parents=True)
    sol_file = p_dir / "solution.json"
    sol_file.write_text(json.dumps({
        "N": 21,
        "inner_token": "DOMINO",
        "container_token": "5",
        "S": 4.603855,
        "final_metric": 5.412156,
        "values": [0.0] * 63
    }))

    from src.shape_packing.records_exporter import find_all_records
    records = find_all_records(str(tmp_path / "results"), min_improvement=1e-5)
    assert len(records) >= 1
    rec = next(r for r in records if r.problem == "21_DOMINO_in_5")
    assert rec.N == 21
    assert rec.improvement < -0.1

from src.shape_packing.solution_tools import load_solution, verify_solution
from src.shape_packing.records_exporter import (
    generate_coordinates_text,
    generate_verification_text,
)

def test_generate_coordinates_text(tmp_path):
    p_file = tmp_path / "solution.json"
    p_file.write_text(json.dumps({
        "N": 2,
        "inner_token": "DOMINO",
        "container_token": "6",
        "S": 1.519672,
        "final_metric": 1.519672,
        "values": [0.0, 0.0, 0.0, 0.5, 0.5, 1.570796]
    }))
    sol = load_solution(str(p_file))
    cand = RecordCandidate(
        problem="2_DOMINO_in_6",
        N=2,
        inner_token="DOMINO",
        container_token="6",
        solution_path=str(p_file),
        run_dir=str(tmp_path),
        S=1.519672,
        metric=1.519672,
        friedman_best=1.519700,
        improvement=-0.000028,
    )
    coord_txt = generate_coordinates_text(cand, sol)
    assert "RECORD SUBMISSION: 2_DOMINO_in_6" in coord_txt
    assert "Pieces (2 total):" in coord_txt
    assert "Center (x, y)" in coord_txt

def test_generate_verification_text(tmp_path):
    p_file = tmp_path / "solution.json"
    p_file.write_text(json.dumps({
        "N": 2,
        "inner_token": "DOMINO",
        "container_token": "6",
        "S": 1.519672,
        "final_metric": 1.519672,
        "values": [0.0, 0.0, 0.0, 0.5, 0.5, 1.570796]
    }))
    sol = load_solution(str(p_file))
    cand = RecordCandidate(
        problem="2_DOMINO_in_6",
        N=2,
        inner_token="DOMINO",
        container_token="6",
        solution_path=str(p_file),
        run_dir=str(tmp_path),
        S=1.519672,
        metric=1.519672,
        friedman_best=1.519700,
        improvement=-0.000028,
    )
    v_res = verify_solution(str(p_file), "2_DOMINO_in_6")
    v_txt = generate_verification_text(cand, sol, v_res)
    assert "GEOMETRIC VALIDATION CERTIFICATE" in v_txt
    assert "Problem: 2_DOMINO_in_6" in v_txt
    assert "Collision Check" in v_txt

from src.shape_packing.records_exporter import (
    generate_manifest,
    generate_summary_markdown,
    generate_email_drafts,
)

def test_manifest_and_summary_generation(tmp_path):
    cand = RecordCandidate(
        problem="21_DOMINO_in_5",
        N=21,
        inner_token="DOMINO",
        container_token="5",
        solution_path="mock/path",
        run_dir="mock/dir",
        S=4.603855,
        metric=5.412156,
        friedman_best=5.553080,
        improvement=-0.140924,
    )
    manifest_path = generate_manifest([cand], str(tmp_path))
    assert os.path.exists(manifest_path)
    with open(manifest_path) as f:
        data = json.load(f)
    assert data["total_records"] == 1
    assert data["records"][0]["problem"] == "21_DOMINO_in_5"

    summary_path = generate_summary_markdown([cand], str(tmp_path))
    assert os.path.exists(summary_path)
    with open(summary_path) as f:
        md = f.read()
    assert "21_DOMINO_in_5" in md
    assert "-0.140924" in md

    drafts = generate_email_drafts([cand], str(tmp_path))
    assert len(drafts) == 1
    with open(drafts[0]) as f:
        email = f.read()
    assert "dominpen" in email

from src.shape_packing.records_exporter import export_records

def test_export_records_e2e(tmp_path):
    res_dir = tmp_path / "results"
    p_dir = res_dir / "21_DOMINO_in_5" / "20260806_230206"
    p_dir.mkdir(parents=True)
    
    real_sol_path = "results/21_DOMINO_in_5/20260806_230206/solution.json"
    if os.path.exists(real_sol_path):
        with open(real_sol_path) as f:
            sol_data = json.load(f)
    else:
        sol_data = {
            "N": 21,
            "inner_token": "DOMINO",
            "container_token": "5",
            "S": 4.603855,
            "final_metric": 5.412156,
            "values": [0.0] * 63
        }

    (p_dir / "solution.json").write_text(json.dumps(sol_data))

    out_dir = tmp_path / "records"
    summary = export_records(
        results_dir=str(res_dir),
        output_dir=str(out_dir),
        min_improvement=1e-5,
        family_filter="dominpen",
    )
    assert summary["exported_count"] >= 1
    assert os.path.exists(out_dir / "manifest.json")
    assert os.path.exists(out_dir / "summary.md")
    assert os.path.exists(out_dir / "dominpen" / "21_DOMINO_in_5" / "solution.json")
    assert os.path.exists(out_dir / "dominpen" / "21_DOMINO_in_5" / "coordinates.txt")
    assert os.path.exists(out_dir / "dominpen" / "21_DOMINO_in_5" / "verification.txt")
    assert os.path.exists(out_dir / "dominpen" / "21_DOMINO_in_5" / "render.png")
