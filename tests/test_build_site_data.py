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


def test_generate_key_variants_all_shapes():
    from scripts.build_site_data import generate_key_variants

    # Test word-based shape tokens
    entry_domino_pentagon = {
        "N": 3,
        "inner_shape": "domino",
        "container_shape": "pentagon",
        "problem_family": "dominpen",
    }
    keys = generate_key_variants(entry_domino_pentagon)
    assert "3_DOMINO_in_5" in keys
    assert "3_domino_in_pentagon" in keys
    assert "3_dominpen" in keys

    # Test numerical shape tokens
    entry_6_8 = {
        "N": 10,
        "inner_shape": "6",
        "container_shape": "8",
        "problem_family": "hexinoct",
    }
    keys_6_8 = generate_key_variants(entry_6_8)
    assert "10_HEXAGON_in_OCTAGON" in keys_6_8
    assert "10_6_in_8" in keys_6_8


def test_all_disk_solution_folders_are_matched():
    from scripts.build_site_data import load_local_solutions, load_reference_entries, generate_key_variants

    sols = load_local_solutions()
    ref_entries = load_reference_entries()

    assert len(sols) > 0, "Expected local solution folders in results/"

    matched_sols = set()
    for e in ref_entries:
        keys = generate_key_variants(e)
        for k in keys:
            if k in sols:
                matched_sols.add(k)

    unmatched = set(sols.keys()) - matched_sols
    assert len(unmatched) == 0, f"Found {len(unmatched)} unmatched local solution folders in results/: {list(unmatched)[:10]}"

