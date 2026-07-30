"""
Shared pytest fixtures for shape-packing tests.
"""
import json
import os
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

# Ensure src is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="session")
def project_root():
    return ROOT


@pytest.fixture
def tmp_project(project_root, tmp_path):
    """
    A temporary 'project' directory with src on path.
    Useful when we need files visible to the package.
    """
    src_link = tmp_path / "src"
    src_link.symlink_to(project_root / "src", target_is_directory=True)
    return tmp_path


# Example problem names to reuse
PROBLEM_8_3_IN_5 = "8_3_in_5"
PROBLEM_10_6_IN_4 = "10_6_in_4"
PROBLEM_12_3_IN_CIRCLE = "12_3_in_CIRCLE"


@pytest.fixture
def sample_solution_values(tmp_path):
    """
    Minimal solution JSON in 'values' style.
    """
    data = {
        "N": 4,
        "inner_sides": 3,
        "container_sides": 4,
        "S": 2.0,
        "final_metric": 1.5,
        "values": [0.0, 0.0, 0.0,
                   1.0, 0.0, 0.0,
                   0.0, 1.0, 0.0,
                   -1.0, 0.0, 0.0],
    }
    path = tmp_path / "solution_values.json"
    path.write_text(json.dumps(data))
    return str(path)


@pytest.fixture
def sample_solution_positions(tmp_path):
    """
    Minimal solution JSON in 'positions' style.
    """
    data = {
        "N": 3,
        "nsi": 3,
        "nsc": 4,
        "S": 2.0,
        "positions": [
            {"cx": 0.0, "cy": 0.0, "a": 0.0},
            {"cx": 1.0, "cy": 0.0, "a": 0.0},
            {"cx": -1.0, "cy": 0.0, "a": 0.0},
        ],
    }
    path = tmp_path / "solution_positions.json"
    path.write_text(json.dumps(data))
    return str(path)


@pytest.fixture
def sample_tsv_reference(tmp_path):
    """
    A PACKING_REFERENCE.tsv with a few known entries.
    """
    content = textwrap.dedent(
        """\
        id	problem_family	best_value	status	source_note	our_problem
        3_in_3_1	3_in_3	1.000000	best_known	Found by Erich	1_3_in_3
        3_in_3_8	3_in_3	2.000000	best_known	Found by Erich	8_3_in_5
        6_in_4_10	6_in_4	3.000000	best_known	Proved	10_6_in_4
        """
    )
    path = tmp_path / "PACKING_REFERENCE.tsv"
    path.write_text(content)
    return str(path)


@pytest.fixture
def sample_priority_queue(tmp_path):
    """
    A small priority_queue.json for agent_loop tests.
    """
    items = [
        {
            "problem": PROBLEM_8_3_IN_5,
            "density": 0.9,
            "status": "best_known",
            "source_note": "Found by Erich",
            "best_value": 2.0,
            "inner_shape": "3",
            "container_shape": "5",
            "N": 8,
        },
        {
            "problem": PROBLEM_10_6_IN_4,
            "density": 0.6,
            "status": "best_known",
            "source_note": "Found by someone",
            "best_value": 3.0,
            "inner_shape": "6",
            "container_shape": "4",
            "N": 10,
        },
        {
            "problem": "5_3_in_3",
            "density": 0.95,
            "status": "trivial",
            "source_note": "Trivial",
            "best_value": 1.1,
            "inner_shape": "3",
            "container_shape": "3",
            "N": 5,
        },
        {
            "problem": "3_3_in_CIRCLE",
            "density": 0.4,
            "status": "best_known",
            "source_note": "Found by Erich",
            "best_value": 0.5,
            "inner_shape": "3",
            "container_shape": "CIRCLE",
            "N": 3,
        },
    ]
    path = tmp_path / "priority_queue.json"
    path.write_text(json.dumps(items))
    return str(path)


@pytest.fixture
def sample_history_tsv(tmp_path):
    """
    A results.tsv with a few experiments.
    """
    lines = [
        "commit\tscore\tmemory_gb\tstatus\tproblem\tdescription\tseconds",
        "abc\t1.5\t0.1\tkeep\t8_3_in_5\ttest run\t10.0",
        "abc\t1.4\t0.1\tkeep\t8_3_in_5\ttest run\t10.0",
        "abc\t1.6\t0.1\tkeep\t8_3_in_5\ttest run\t10.0",
        "abc\t1.3\t0.1\tkeep\t8_3_in_5\ttest run\t10.0",
        "abc\t1.2\t0.1\tkeep\t8_3_in_5\ttest run\t10.0",
        "abc\t1.1\t0.1\tkeep\t8_3_in_5\ttest run\t10.0",
        "abc\t2.0\t0.1\tkeep\t10_6_in_4\ttest run\t10.0",
        "abc\t0\t0.1\tcrash\t12_3_in_CIRCLE\tcrash\t5.0",
    ]
    path = tmp_path / "results.tsv"
    path.write_text("\n".join(lines))
    return str(path)
