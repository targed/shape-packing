# Records Exporter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone, verified Records Exporter tool (`src/shape_packing/records_exporter.py` and `scripts/export_records.py`) that scans `results/`, identifies genuine world-record packings beating Erich Friedman's published benchmarks, validates geometries with SAT and containment checks, and packages an organized `records/` folder with cropped PNGs, solution JSONs, plaintext coordinates, validation proofs, manifest, summary table, and ready-to-send submission email drafts.

**Architecture:** A modular Python pipeline consisting of `RecordFinder` (audits `results/` against `packingVerification/*.json`), `RecordValidator` (rigorous SAT overlap, vertex boundary containment, polygon dimension validation), `RecordRenderer` (tight-cropped PNG generation), `RecordFormatter` (generates `coordinates.txt`, `verification.txt`, email drafts, `manifest.json`, and `summary.md`), and `export_records_cli` CLI interface.

**Tech Stack:** Python 3.10+, numpy, matplotlib, shapely (if present, fallback to internal geometry), standard library (json, csv, os, sys, glob, argparse, datetime).

## Global Constraints

- No modifications to core solver math or optimizer internals.
- Export only valid solutions strictly beating published Friedman benchmarks (`metric < friedman_best - min_improvement`).
- Backward compatible with existing repo structures and tests.
- High-res tight cropped renders without extra margins or truncated edges.
- Complete type annotations and docstrings.

---

### Task 1: Record Models & Data Structures

**Files:**
- Create: `src/shape_packing/records_exporter.py`
- Test: `tests/test_records_exporter.py`

**Interfaces:**
- Produces:
  - `RecordCandidate`: Dataclass containing problem metadata, run folder, solution path, metrics, Friedman benchmark, and delta.
  - `ExportResult`: Dataclass containing export status, output folder, and generated file paths.
  - `get_family_info(inner_token: str, container_token: str) -> Tuple[str, str]`: Family code (e.g. `dominpen`) and URL.

- [ ] **Step 1: Write the failing unit tests for data structures & family info**

```python
# tests/test_records_exporter.py
import pytest
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_records_exporter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.shape_packing.records_exporter'`

- [ ] **Step 3: Implement data structures & `get_family_info`**

Create `src/shape_packing/records_exporter.py`:

```python
from __future__ import annotations

import os
import sys
import json
import math
import glob
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

SIDES_TO_NAME = {
    "3": "tri",
    "4": "squ",
    "5": "pen",
    "6": "hex",
    "7": "hep",
    "8": "oct",
    "9": "non",
    "10": "dec",
}

SPECIAL_NAMES = {
    "circle": "cir",
    "cir": "cir",
    "tan": "tan",
    "domino": "dom",
    "dom": "dom",
    "l": "L",
    "l-tromino": "L",
}

def name_for(token: str) -> str:
    s = str(token).strip().lower()
    if s in SIDES_TO_NAME:
        return SIDES_TO_NAME[s]
    return SPECIAL_NAMES.get(s, s)

def get_family_info(inner_token: str, container_token: str) -> Tuple[str, str]:
    """Return the family code (e.g. dominpen) and official Erich Friedman URL."""
    inner_name = name_for(inner_token)
    container_name = name_for(container_token)
    family_code = f"{inner_name}in{container_name}"
    url = f"https://erich-friedman.github.io/packing/{family_code}/index.html"
    return family_code, url

@dataclass
class RecordCandidate:
    problem: str
    N: int
    inner_token: str
    container_token: str
    solution_path: str
    run_dir: str
    S: float
    metric: float
    friedman_best: float
    improvement: float
    family_code: str = field(init=False)
    family_url: str = field(init=False)

    def __post_init__(self):
        self.family_code, self.family_url = get_family_info(self.inner_token, self.container_token)

@dataclass
class ExportResult:
    problem: str
    success: bool
    output_dir: str
    files: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_records_exporter.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 1**

```bash
git add src/shape_packing/records_exporter.py tests/test_records_exporter.py
git commit -m "feat: add RecordCandidate models and family info lookup in records_exporter"
```

---

### Task 2: Record Discovery & Filtering Pipeline

**Files:**
- Modify: `src/shape_packing/records_exporter.py`
- Test: `tests/test_records_exporter.py`

**Interfaces:**
- Consumes: `RecordCandidate`, `get_friedman_best_for_problem`, `compute_friedman_metric`, `load_solution`
- Produces: `find_all_records(results_dir: str, min_improvement: float = 1e-5, family_filter: Optional[str] = None) -> List[RecordCandidate]`

- [ ] **Step 1: Write tests for `find_all_records`**

Add to `tests/test_records_exporter.py`:

```python
def test_find_all_records_discovery(tmp_path):
    # Setup mock results directory
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_records_exporter.py::test_find_all_records_discovery -v`
Expected: FAIL with `ImportError: cannot import name 'find_all_records'`

- [ ] **Step 3: Implement `find_all_records`**

Add to `src/shape_packing/records_exporter.py`:

```python
from .solution_tools import load_solution, compute_friedman_metric
from .packing_config import get_friedman_best_for_problem, _load_friedman_verification_jsons

def find_all_records(
    results_dir: str = "results",
    min_improvement: float = 1e-5,
    family_filter: Optional[str] = None,
) -> List[RecordCandidate]:
    """
    Scans results_dir, identifies the best valid run per problem,
    and returns RecordCandidates that strictly beat Erich Friedman's known benchmarks.
    """
    _load_friedman_verification_jsons()
    if not os.path.exists(results_dir):
        return []

    # Map problem -> best (S, run_dir, solution_path, sol_obj)
    best_per_problem: Dict[str, Tuple[float, str, str, Any]] = {}

    for folder in os.listdir(results_dir):
        p_path = os.path.join(results_dir, folder)
        if not os.path.isdir(p_path):
            continue

        for run in os.listdir(p_path):
            run_dir = os.path.join(p_path, run)
            sol_path = os.path.join(run_dir, "solution.json")
            if not os.path.isfile(sol_path):
                continue

            try:
                sol = load_solution(sol_path)
            except Exception:
                continue

            p_token = f"{sol.N}_{sol.inner_token}_in_{sol.container_token}"
            if p_token not in best_per_problem or sol.S < best_per_problem[p_token][0]:
                best_per_problem[p_token] = (sol.S, run_dir, sol_path, sol)

    candidates: List[RecordCandidate] = []
    for p_token, (best_s, run_dir, sol_path, sol) in best_per_problem.items():
        recalc_metric = compute_friedman_metric(best_s, sol.inner_token, sol.container_token)
        friedman_best = get_friedman_best_for_problem(p_token)

        if friedman_best is None:
            continue

        improvement = recalc_metric - friedman_best
        if improvement < -min_improvement:
            cand = RecordCandidate(
                problem=p_token,
                N=sol.N,
                inner_token=str(sol.inner_token),
                container_token=str(sol.container_token),
                solution_path=sol_path,
                run_dir=run_dir,
                S=best_s,
                metric=recalc_metric,
                friedman_best=friedman_best,
                improvement=improvement,
            )
            if family_filter and family_filter.lower() != "all":
                if cand.family_code.lower() != family_filter.lower():
                    continue
            candidates.append(cand)

    candidates.sort(key=lambda c: (c.family_code, c.N, c.problem))
    return candidates
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_records_exporter.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 2**

```bash
git add src/shape_packing/records_exporter.py tests/test_records_exporter.py
git commit -m "feat: implement find_all_records discovery and benchmark filtering"
```

---

### Task 3: Text Generators (`coordinates.txt` & `verification.txt`)

**Files:**
- Modify: `src/shape_packing/records_exporter.py`
- Test: `tests/test_records_exporter.py`

**Interfaces:**
- Consumes: `Solution`, `RecordCandidate`, `VerifyResult`, `build_polygons`
- Produces:
  - `generate_coordinates_text(candidate: RecordCandidate, sol: Solution) -> str`
  - `generate_verification_text(candidate: RecordCandidate, sol: Solution, v_res: VerifyResult) -> str`

- [ ] **Step 1: Write tests for text generators**

Add to `tests/test_records_exporter.py`:

```python
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
    assert "GEOMETRIC VALIDATION LOG" in v_txt
    assert "Problem: 2_DOMINO_in_6" in v_txt
    assert "Pairwise Collision Check (SAT)" in v_txt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_records_exporter.py::test_generate_coordinates_text -v`
Expected: FAIL with `ImportError: cannot import name 'generate_coordinates_text'`

- [ ] **Step 3: Implement `generate_coordinates_text` and `generate_verification_text`**

Add to `src/shape_packing/records_exporter.py`:

```python
from .solution_tools import build_polygons, VerifyResult

def generate_coordinates_text(cand: RecordCandidate, sol: Any) -> str:
    """Format piece centers, angles, and vertex coordinates in clean tabular plaintext for Erich Friedman."""
    polygons = build_polygons(sol)
    pct_imp = (cand.improvement / cand.friedman_best) * 100.0 if cand.friedman_best else 0.0

    lines = [
        "=" * 80,
        f"RECORD SUBMISSION: {cand.problem}",
        "=" * 80,
        f"Problem: {cand.problem}",
        f"Family: {cand.family_code} ({cand.family_url})",
        f"Inner Shape: {cand.inner_token}",
        f"Container: {cand.container_token}",
        f"Solver Circumradius S: {cand.S:.12f}",
        f"Reported Metric s: {cand.metric:.12f}",
        f"Previous Friedman Benchmark: {cand.friedman_best:.12f}",
        f"Improvement Delta: {cand.improvement:+.12f} ({pct_imp:+.3f}%)",
        "",
        f"Pieces ({sol.N} total):",
        f"{'#':<3} | {'Center (x, y)':<25} | {'Angle (deg)':<12} | {'Vertices [(x,y), ...]'}",
        "-" * 80,
    ]

    for i in range(sol.N):
        cx = sol.values[i * 3]
        cy = sol.values[i * 3 + 1]
        a_rad = sol.values[i * 3 + 2]
        a_deg = math.degrees(a_rad) % 360.0
        poly = polygons[i] if i < len(polygons) else []
        poly_str = ", ".join(f"({x:+.6f}, {y:+.6f})" for x, y in poly)
        lines.append(f"{i+1:<3} | ({cx:+10.6f}, {cy:+10.6f}) | {a_deg:>8.2f} deg | [{poly_str}]")

    lines.extend(["=" * 80, ""])
    return "\n".join(lines)


def generate_verification_text(cand: RecordCandidate, sol: Any, v_res: Any) -> str:
    """Generate formal verification certificate detailing SAT overlap and containment results."""
    now_utc = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    status_str = "VALID" if v_res.valid else "INVALID"

    lines = [
        "=" * 80,
        "GEOMETRIC VALIDATION CERTIFICATE",
        "=" * 80,
        f"Problem: {cand.problem}",
        f"Verified At: {now_utc}",
        f"Validation Status: {status_str}",
        f"Result Metric: {v_res.metric:.12f}",
        "",
        "1. Geometry Checks:",
        f"   - Piece Count: {sol.N}",
        f"   - Geometric Valid Flag: {v_res.valid}",
        "",
        "2. Collision Check (Separating Axis Theorem):",
        f"   - Pairwise Overlap Status: {'PASS (0 overlaps)' if v_res.valid else 'FAIL'}",
        "",
        "3. Verification Messages:",
    ]
    if v_res.errors:
        for err in v_res.errors:
            lines.append(f"   - ERROR: {err}")
    else:
        lines.append(f"   - {v_res.message}")

    lines.extend(["=" * 80, ""])
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_records_exporter.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 3**

```bash
git add src/shape_packing/records_exporter.py tests/test_records_exporter.py
git commit -m "feat: implement plaintext coordinates and verification text formatters"
```

---

### Task 4: Manifest & Email Draft Generators

**Files:**
- Modify: `src/shape_packing/records_exporter.py`
- Test: `tests/test_records_exporter.py`

**Interfaces:**
- Consumes: `List[RecordCandidate]`
- Produces:
  - `generate_manifest(records: List[RecordCandidate], output_dir: str) -> str`
  - `generate_summary_markdown(records: List[RecordCandidate], output_dir: str) -> str`
  - `generate_email_drafts(records: List[RecordCandidate], output_dir: str) -> List[str]`

- [ ] **Step 1: Write tests for manifests & email drafts**

Add to `tests/test_records_exporter.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_records_exporter.py::test_manifest_and_summary_generation -v`
Expected: FAIL with `ImportError: cannot import name 'generate_manifest'`

- [ ] **Step 3: Implement manifest, summary, and email draft generators**

Add to `src/shape_packing/records_exporter.py`:

```python
from collections import defaultdict

def generate_manifest(records: List[RecordCandidate], output_dir: str) -> str:
    """Generate structured JSON index of all exported records."""
    manifest_path = os.path.join(output_dir, "manifest.json")
    os.makedirs(output_dir, exist_ok=True)

    data = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_records": len(records),
        "records": [
            {
                "problem": r.problem,
                "N": r.N,
                "inner_token": r.inner_token,
                "container_token": r.container_token,
                "family_code": r.family_code,
                "family_url": r.family_url,
                "solver_S": r.S,
                "metric": r.metric,
                "friedman_best": r.friedman_best,
                "improvement": r.improvement,
                "folder": f"{r.family_code}/{r.problem}",
            }
            for r in records
        ],
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return manifest_path


def generate_summary_markdown(records: List[RecordCandidate], output_dir: str) -> str:
    """Generate human-readable summary table of all broken records."""
    summary_path = os.path.join(output_dir, "summary.md")
    os.makedirs(output_dir, exist_ok=True)

    lines = [
        "# Shape Packing World Records Summary",
        "",
        f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        f"**Total Verified Record Improvements:** {len(records)}",
        "",
        "| Problem | Family | N | Solver $S$ | Our Metric $s$ | Friedman Best | Improvement $\\Delta s$ | Folder Link |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]

    for r in records:
        folder_link = f"[{r.problem}](./{r.family_code}/{r.problem})"
        lines.append(
            f"| `{r.problem}` | [`{r.family_code}`]({r.family_url}) | {r.N} | {r.S:.6f} | **{r.metric:.6f}** | {r.friedman_best:.6f} | **{r.improvement:+.6f}** | {folder_link} |"
        )

    lines.append("")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return summary_path


def generate_email_drafts(records: List[RecordCandidate], output_dir: str) -> List[str]:
    """Generate ready-to-send submission email templates grouped per shape family."""
    sub_dir = os.path.join(output_dir, "submissions")
    os.makedirs(sub_dir, exist_ok=True)

    by_family = defaultdict(list)
    for r in records:
        by_family[r.family_code].append(r)

    draft_files = []
    for fam, fam_records in by_family.items():
        fam_records.sort(key=lambda x: x.N)
        draft_path = os.path.join(sub_dir, f"{fam}_submission.md")
        first_r = fam_records[0]

        lines = [
            f"# Submission Draft: {fam}",
            "",
            f"**To:** Erich Friedman (via packing website contact)",
            f"**Subject:** New packing record(s) for {fam} ({first_r.inner_token} in {first_r.container_token})",
            f"**Problem Page:** {first_r.family_url}",
            "",
            "---",
            "",
            "Dear Professor Friedman,",
            "",
            f"We have found improved packing configurations for **{fam}** ({first_r.inner_token} in {first_r.container_token}):",
            "",
            "| N | Our Metric (s) | Current Best | Improvement |",
            "| :---: | :---: | :---: | :---: |",
        ]

        for r in fam_records:
            lines.append(f"| {r.N} | {r.metric:.6f} | {r.friedman_best:.6f} | {r.improvement:+.6f} |")

        lines.extend([
            "",
            "All configurations have been verified with Separating Axis Theorem (SAT) collision detection and boundary containment.",
            "Coordinates and high-resolution diagrams for each solution are attached / included in the submission folder.",
            "",
            "Best regards,",
            "[Your Name / Research Group]",
            "",
        ])

        with open(draft_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        draft_files.append(draft_path)

    return draft_files
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_records_exporter.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 4**

```bash
git add src/shape_packing/records_exporter.py tests/test_records_exporter.py
git commit -m "feat: add manifest, summary table, and email draft generators"
```

---

### Task 5: End-to-End Exporter & CLI Script

**Files:**
- Modify: `src/shape_packing/records_exporter.py`
- Create: `scripts/export_records.py`
- Test: `tests/test_records_exporter.py`

**Interfaces:**
- Consumes: `find_all_records`, `verify_solution`, `render_solution`, `generate_coordinates_text`, `generate_verification_text`, `generate_manifest`, `generate_summary_markdown`, `generate_email_drafts`
- Produces:
  - `export_records(results_dir: str, output_dir: str, min_improvement: float = 1e-5, family_filter: Optional[str] = None, clean: bool = False, dpi: int = 300) -> Dict[str, Any]`
  - Executable `scripts/export_records.py` CLI.

- [ ] **Step 1: Write tests for `export_records` end-to-end**

Add to `tests/test_records_exporter.py`:

```python
import subprocess
from src.shape_packing.records_exporter import export_records

def test_export_records_e2e(tmp_path):
    res_dir = tmp_path / "results"
    p_dir = res_dir / "21_DOMINO_in_5" / "20260806_230206"
    p_dir.mkdir(parents=True)
    (p_dir / "solution.json").write_text(json.dumps({
        "N": 21,
        "inner_token": "DOMINO",
        "container_token": "5",
        "S": 4.603855,
        "final_metric": 5.412156,
        "values": [0.0] * 63
    }))

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_records_exporter.py::test_export_records_e2e -v`
Expected: FAIL with `ImportError: cannot import name 'export_records'`

- [ ] **Step 3: Implement `export_records` in `src/shape_packing/records_exporter.py`**

Add to `src/shape_packing/records_exporter.py`:

```python
import shutil
from .solution_tools import verify_solution, render_solution

def export_records(
    results_dir: str = "results",
    output_dir: str = "records",
    min_improvement: float = 1e-5,
    family_filter: Optional[str] = None,
    clean: bool = False,
    dpi: int = 300,
    quiet: bool = False,
) -> Dict[str, Any]:
    """
    Audit results_dir, filter all genuine world records beating Friedman benchmarks,
    verify geometries, render tight PNGs, and package full submission kits into output_dir.
    """
    if clean and os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    os.makedirs(output_dir, exist_ok=True)
    candidates = find_all_records(results_dir, min_improvement, family_filter)

    if not quiet:
        print(f"Found {len(candidates)} record candidate(s) to verify and export.")

    exported: List[RecordCandidate] = []
    failed: List[Tuple[RecordCandidate, List[str]]] = []

    for cand in candidates:
        cand_out_dir = os.path.join(output_dir, cand.family_code, cand.problem)
        os.makedirs(cand_out_dir, exist_ok=True)

        # 1. Verify geometry
        v_res = verify_solution(cand.solution_path, cand.problem)
        if not v_res.valid:
            failed.append((cand, v_res.errors))
            if not quiet:
                print(f"  [FAIL] {cand.problem}: invalid geometry ({v_res.errors})")
            continue

        try:
            sol = load_solution(cand.solution_path)
        except Exception as e:
            failed.append((cand, [f"load_solution failed: {e}"]))
            continue

        # 2. Copy raw solution.json
        shutil.copy2(cand.solution_path, os.path.join(cand_out_dir, "solution.json"))

        # 3. Write coordinates.txt
        coord_txt = generate_coordinates_text(cand, sol)
        with open(os.path.join(cand_out_dir, "coordinates.txt"), "w", encoding="utf-8") as f:
            f.write(coord_txt)

        # 4. Write verification.txt
        v_txt = generate_verification_text(cand, sol, v_res)
        with open(os.path.join(cand_out_dir, "verification.txt"), "w", encoding="utf-8") as f:
            f.write(v_txt)

        # 5. Render tight-cropped render.png
        render_path = os.path.join(cand_out_dir, "render.png")
        render_solution(cand.solution_path, render_path, crop_mode="tight", render_dpi=dpi)

        exported.append(cand)
        if not quiet:
            print(f"  [OK] {cand.problem}: metric={cand.metric:.6f} vs {cand.friedman_best:.6f} ({cand.improvement:+.6f}) -> {cand_out_dir}")

    # 6. Generate manifests & drafts
    manifest_path = generate_manifest(exported, output_dir)
    summary_path = generate_summary_markdown(exported, output_dir)
    email_drafts = generate_email_drafts(exported, output_dir)

    return {
        "candidates_count": len(candidates),
        "exported_count": len(exported),
        "failed_count": len(failed),
        "manifest_path": manifest_path,
        "summary_path": summary_path,
        "email_drafts": email_drafts,
        "exported_records": exported,
    }
```

- [ ] **Step 4: Create `scripts/export_records.py` CLI wrapper**

Create `scripts/export_records.py`:

```python
#!/usr/bin/env python3
"""
CLI script to audit and export all broken world records into a submission bundle.
Usage:
    python scripts/export_records.py [OPTIONS]
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.shape_packing.records_exporter import export_records

def main():
    parser = argparse.ArgumentParser(description="Export world-record packing solutions for submission to Erich Friedman.")
    parser.add_argument("--results-dir", default="results", help="Path to results directory (default: results)")
    parser.add_argument("--output-dir", default="records", help="Path to export directory (default: records)")
    parser.add_argument("--min-improvement", type=float, default=1e-5, help="Minimum improvement delta (default: 1e-5)")
    parser.add_argument("--family", default="all", help="Filter by shape family code (e.g. dominpen, dominhex, or all)")
    parser.add_argument("--clean", action="store_true", help="Clean output directory before exporting")
    parser.add_argument("--dpi", type=int, default=300, help="Image DPI for rendered PNGs (default: 300)")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose logging")

    args = parser.parse_args()

    print("=" * 80)
    print("SHAPE PACKING WORLD RECORDS EXPORTER")
    print("=" * 80)

    summary = export_records(
        results_dir=args.results_dir,
        output_dir=args.output_dir,
        min_improvement=args.min_improvement,
        family_filter=args.family if args.family != "all" else None,
        clean=args.clean,
        dpi=args.dpi,
        quiet=args.quiet,
    )

    print("\n" + "=" * 80)
    print(f"EXPORT COMPLETE:")
    print(f"  Total Record Candidates: {summary['candidates_count']}")
    print(f"  Successfully Exported:   {summary['exported_count']}")
    print(f"  Failed / Invalid:        {summary['failed_count']}")
    print(f"  Summary Report:          {summary['summary_path']}")
    print(f"  Manifest File:           {summary['manifest_path']}")
    print(f"  Email Drafts:            {len(summary['email_drafts'])} generated")
    print("=" * 80)

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests & execute CLI script on repository results**

Run: `pytest tests/test_records_exporter.py -v`
Run: `python scripts/export_records.py --output-dir records --clean`
Expected: PASS and export ~49+ records into `records/`.

- [ ] **Step 6: Commit Task 5**

```bash
git add src/shape_packing/records_exporter.py scripts/export_records.py tests/test_records_exporter.py
git commit -m "feat: complete records_exporter and export_records CLI script"
```

---

### Task 6: Full Verification Suite

**Files:**
- Test: Full repo test suite (`tests/`)

- [ ] **Step 1: Run full pytest suite**

Run: `python -m pytest tests/`
Expected: 280+ passed, 0 failures.

- [ ] **Step 2: Commit generated records directory or update .gitignore if desired**
