from __future__ import annotations

import os
import json
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from .packing_config import (
    get_family_colors,
    get_family_properties,
    get_family_target_filename,
)

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

    with os.scandir(results_dir) as entries:
        for folder_entry in entries:
            if not folder_entry.is_dir():
                continue

            with os.scandir(folder_entry.path) as run_entries:
                for run_entry in run_entries:
                    if not run_entry.is_dir():
                        continue

                    sol_path = os.path.join(run_entry.path, "solution.json")
                    if not os.path.isfile(sol_path):
                        continue

                    try:
                        sol = load_solution(sol_path)
                    except Exception:
                        continue

                    inner_u = str(sol.inner_token).upper()
                    container_u = str(sol.container_token).upper()
                    p_token = f"{sol.N}_{inner_u}_in_{container_u}"
                    if p_token not in best_per_problem or sol.S < best_per_problem[p_token][0]:
                        best_per_problem[p_token] = (sol.S, run_entry.path, sol_path, sol)

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
        f"Reported Side Length / Radius s (5 dec): {cand.metric:.5f}+",
        f"Exact Metric s: {cand.metric:.12f}",
        f"Previous Friedman Benchmark: {cand.friedman_best:.5f}+ (exact: {cand.friedman_best:.12f})",
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
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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


from collections import defaultdict


def generate_manifest(records: List[RecordCandidate], output_dir: str) -> str:
    """Generate structured JSON index of all exported records."""
    manifest_path = os.path.join(output_dir, "manifest.json")
    os.makedirs(output_dir, exist_ok=True)

    data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
                "site_image": f"{r.family_code}/{r.problem}/{get_family_target_filename(r.family_code, r.N)}",
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
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        f"**Total Verified Record Improvements:** {len(records)}",
        "",
        "| Problem | Family | N | Our Metric $s$ (5 dec) | Our Exact $s$ | Friedman Best | Improvement $\\Delta s$ | Folder Link |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]

    for r in records:
        folder_link = f"[{r.problem}](./{r.family_code}/{r.problem})"
        lines.append(
            f"| `{r.problem}` | [`{r.family_code}`]({r.family_url}) | {r.N} | **{r.metric:.5f}+** | {r.metric:.12f} | {r.friedman_best:.5f}+ | **{r.improvement:+.6f}** | {folder_link} |"
        )

    lines.append("")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return summary_path


def generate_email_drafts(records: List[RecordCandidate], output_dir: str) -> List[str]:
    """Generate ready-to-send submission email templates grouped per shape family adhering to Dr. Friedman's guidelines."""
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
        fam_props = get_family_properties(first_r.inner_token, first_r.container_token)
        target_w = fam_props.get("width", 240)
        target_h = fam_props.get("height", 240)

        lines = [
            f"# Submission Draft: {fam}",
            "",
            f"**To:** Erich Friedman (via packing website)",
            f"**Subject:** New packing records for {fam} ({first_r.inner_token} in {first_r.container_token})",
            f"**Problem Page:** {first_r.family_url}",
            "",
            "---",
            "",
            "Dear Dr. Friedman,",
            "",
            f"This is Luke Kaiser. We have found improved packing configurations for **{fam}** ({first_r.inner_token} in {first_r.container_token}):",
            "",
            "### Methodology",
            "We discovered these packings using a continuous global optimization solver combining randomized geometric basin-hopping with Separating Axis Theorem (SAT) collision constraints and SLSQP local gradient refinement. All solutions have been validated with 0 pairwise overlaps and strict container boundary containment.",
            "",
            "### New Packings",
            "| N | Our s (5 dec) | Our Exact s | Friedman Best s | Improvement | Attached Image |",
            "| :---: | :---: | :---: | :---: | :---: | :---: |",
        ]

        for r in fam_records:
            target_fn = get_family_target_filename(r.family_code, r.N)
            lines.append(
                f"| {r.N} | {r.metric:.5f}+ | {r.metric:.12f} | {r.friedman_best:.5f}+ | {r.improvement:+.6f} | `{target_fn}` |"
            )

        lines.extend([
            "",
            "### Image Attachments",
            f"The replacement image files are attached directly with exact matching colors ({fam_props.get('inner', '#CCCCCC')} on {fam_props.get('container', '#FFFFFF')}), orientation, no borders or text, and target website pixel dimensions ({target_w}x{target_h} px):",
        ])
        for r in fam_records:
            target_fn = get_family_target_filename(r.family_code, r.N)
            lines.append(f"- `{target_fn}`")

        lines.extend([
            "",
            "Coordinate tables and certificates for each solution are included in the repository records.",
            "",
            "Sincerely,",
            "Luke Kaiser",
            "",
        ])

        with open(draft_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        draft_files.append(draft_path)

    return draft_files


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
    verify geometries, render tight PNGs matching website pixel dimensions, and package full submission kits into output_dir.
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
        family_dir = os.path.join(output_dir, cand.family_code)
        cand_out_dir = os.path.join(family_dir, cand.problem)
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

        # 5. Render site-ready direct replacement picture: records/<family>/<problem>/<target_filename>
        target_fn = get_family_target_filename(cand.family_code, cand.N)
        site_image_path = os.path.join(cand_out_dir, target_fn)
        render_solution(cand.solution_path, site_image_path, crop_mode="tight")

        # 6. Render high-res render.png and renderFull.png inside candidate folder
        render_path = os.path.join(cand_out_dir, "render.png")
        render_solution(cand.solution_path, render_path, crop_mode="tight", dpi=dpi)

        render_path_full = os.path.join(cand_out_dir, "renderFull.png")
        render_solution(cand.solution_path, render_path_full, crop_mode="tight", dpi=dpi)

        exported.append(cand)
        if not quiet:
            print(f"  [OK] {cand.problem}: s={cand.metric:.5f}+ (exact: {cand.metric:.6f}) vs {cand.friedman_best:.5f}+ ({cand.improvement:+.6f}) -> {site_image_path}")

    # 7. Generate manifests & drafts
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




