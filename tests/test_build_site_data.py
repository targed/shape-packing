import json
from pathlib import Path
import pytest
from scripts.build_site_data import main, OUTPUT_PATH


def test_build_site_data():
    main()
    assert OUTPUT_PATH.exists()

    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "summary" in data
    assert "families" in data
    assert "problems" in data

    assert data["summary"]["total_families"] > 0
    assert data["summary"]["total_problems"] > 0
    assert len(data["families"]) > 0
    assert len(data["problems"]) > 0

    first_prob = data["problems"][0]
    assert "problem_family" in first_prob
    assert "N" in first_prob
    assert "status" in first_prob
