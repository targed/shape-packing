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
