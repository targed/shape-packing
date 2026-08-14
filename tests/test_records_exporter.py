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
