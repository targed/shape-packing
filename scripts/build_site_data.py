#!/usr/bin/env python3
"""
build_site_data.py

Comprehensive Data Pipeline & Analytics Builder for Shape Packing Dashboard.
Ingests:
- packingVerification/*.json (Erich Friedman verified benchmark references)
- results/ (Local solver runs and geometry solutions)
- results/mill-*.out (Slurm execution logs and worker stats)
- priority_queue.json (Priority queue targets ranked by density / promise)

Outputs site/src/data/site_data.json.
"""

import glob
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
PACKING_VERIFICATION_DIR = ROOT_DIR / "packingVerification"
RESULTS_DIR = ROOT_DIR / "results"
PRIORITY_QUEUE_PATH = ROOT_DIR / "priority_queue.json"
OUTPUT_PATH = ROOT_DIR / "site" / "src" / "data" / "site_data.json"

LEGACY_MAP = {
    # Triangles
    "triincir": "3_in_circle", "3_in_circle": "3_in_circle", "3_in_circle.json": "3_in_circle",
    "triinsqu": "3_in_4", "3_in_4": "3_in_4",
    "triintri": "3_in_3", "3_in_3": "3_in_3",
    "triinpen": "3_in_5", "3_in_5": "3_in_5",
    "triinhex": "3_in_6", "3_in_6": "3_in_6",
    "triinoct": "3_in_8", "3_in_8": "3_in_8",
    "triinL": "3_in_L", "3_in_L": "3_in_L",
    "triindom": "3_in_domino", "3_in_domino": "3_in_domino",
    "triintan": "3_in_tan", "3_in_tan": "3_in_tan",
    # Squares
    "squincir": "4_in_circle", "4_in_circle": "4_in_circle",
    "squinsqu": "4_in_4", "4_in_4": "4_in_4",
    "squintri": "4_in_3", "4_in_3": "4_in_3",
    "squinpen": "4_in_5", "4_in_5": "4_in_5",
    "squinhex": "4_in_6", "4_in_6": "4_in_6",
    "squinoct": "4_in_8", "4_in_8": "4_in_8",
    "squinl": "4_in_L", "4_in_L": "4_in_L",
    "squindom": "4_in_domino", "4_in_domino": "4_in_domino",
    "squintan": "4_in_tan", "4_in_tan": "4_in_tan",
    # Pentagons
    "penincir": "5_in_circle", "5_in_circle": "5_in_circle",
    "peninsqu": "5_in_4", "5_in_4": "5_in_4",
    "penintri": "5_in_3", "5_in_3": "5_in_3",
    "peninpen": "5_in_5", "5_in_5": "5_in_5",
    "peninhex": "5_in_6", "5_in_6": "5_in_6",
    "peninoct": "5_in_8", "5_in_8": "5_in_8",
    "peninL": "5_in_L", "5_in_L": "5_in_L",
    "penindom": "5_in_domino", "5_in_domino": "5_in_domino",
    "penintan": "5_in_tan", "5_in_tan": "5_in_tan",
    # Hexagons
    "hexincir": "6_in_circle", "6_in_circle": "6_in_circle",
    "hexinsqu": "6_in_4", "6_in_4": "6_in_4",
    "hexintri": "6_in_3", "6_in_3": "6_in_3",
    "hexinpen": "6_in_5", "6_in_5": "6_in_5",
    "hexinhex": "6_in_6", "6_in_6": "6_in_6",
    "hexinoct": "6_in_8", "6_in_8": "6_in_8",
    "hexinL": "6_in_L", "6_in_L": "6_in_L",
    "hexindom": "6_in_domino", "6_in_domino": "6_in_domino",
    "hexintan": "6_in_tan", "6_in_tan": "6_in_tan",
    # Octagons
    "octincir": "8_in_circle", "8_in_circle": "8_in_circle",
    "octinsqu": "8_in_4", "8_in_4": "8_in_4",
    "octintri": "8_in_3", "8_in_3": "8_in_3",
    "octinpen": "8_in_5", "8_in_5": "8_in_5",
    "octinhex": "8_in_6", "8_in_6": "8_in_6",
    "octinoct": "8_in_8", "8_in_8": "8_in_8",
    "octinL": "8_in_L", "8_in_L": "8_in_L",
    "octindom": "8_in_domino", "8_in_domino": "8_in_domino",
    "octintan": "8_in_tan", "8_in_tan": "8_in_tan",
    # Circles
    "cirincir": "circle_in_circle", "circle_in_circle": "circle_in_circle",
    "cirinsqu": "circle_in_4", "circle_in_4": "circle_in_4",
    "cirintri": "circle_in_3", "circle_in_3": "circle_in_3",
    "cirinpen": "circle_in_5", "circle_in_5": "circle_in_5",
    "cirinhex": "circle_in_6", "circle_in_6": "circle_in_6",
    "cirinoct": "circle_in_8", "circle_in_8": "circle_in_8",
    "cirinl": "circle_in_L", "circle_in_L": "circle_in_L",
    "cirindom": "circle_in_domino", "circle_in_domino": "circle_in_domino",
    "cirintan": "circle_in_tan", "circle_in_tan": "circle_in_tan",
    "cirinel": "circle_in_ellipse", "circle_in_ellipse": "circle_in_ellipse",
    "cirinttt": "circle_in_3",
    # Dominoes
    "domincir": "domino_in_circle", "domino_in_circle": "domino_in_circle",
    "dominsqu": "domino_in_4", "domino_in_4": "domino_in_4",
    "domintri": "domino_in_3", "domino_in_3": "domino_in_3",
    "dominpen": "domino_in_5", "domino_in_5": "domino_in_5",
    "dominhex": "domino_in_6", "domino_in_6": "domino_in_6",
    "dominoct": "domino_in_8", "domino_in_8": "domino_in_8",
    "dominL": "domino_in_L", "domino_in_L": "domino_in_L",
    "domindom": "domino_in_domino", "domino_in_domino": "domino_in_domino",
    "domintan": "domino_in_tan", "domino_in_tan": "domino_in_tan",
    # L-trominoes
    "LinL": "L_in_L", "L_in_L": "L_in_L",
    "Lindom": "L_in_domino", "L_in_domino": "L_in_domino",
    "Linhex": "L_in_6", "L_in_6": "L_in_6",
    "Linoct": "L_in_8", "L_in_8": "L_in_8",
    "Linpen": "L_in_5", "L_in_5": "L_in_5",
    "Lintan": "L_in_tan", "L_in_tan": "L_in_tan",
    "Lintri": "L_in_3", "L_in_3": "L_in_3",
    # Lines
    "lincir": "line_in_circle", "line_in_circle": "line_in_circle",
    "linsqu": "line_in_4", "line_in_4": "line_in_4",
    # Tans
    "tanincir": "tan_in_circle", "tan_in_circle": "tan_in_circle", "tan_in_cir": "tan_in_circle",
    "taninsqu": "tan_in_4", "tan_in_4": "tan_in_4",
    "tanintri": "tan_in_3", "tan_in_3": "tan_in_3",
    "taninpen": "tan_in_5", "tan_in_5": "tan_in_5",
    "taninhex": "tan_in_6", "tan_in_6": "tan_in_6",
    "taninoct": "tan_in_8", "tan_in_8": "tan_in_8",
    "taninL": "tan_in_L", "tan_in_L": "tan_in_L",
    "tanindom": "tan_in_domino", "tan_in_domino": "tan_in_domino",
    "tanintan": "tan_in_tan", "tan_in_tan": "tan_in_tan",
}


def normalize_family_slug(raw: str) -> str:
    cleaned = str(raw).strip()
    if cleaned in LEGACY_MAP:
        return LEGACY_MAP[cleaned]
    if cleaned.lower() in LEGACY_MAP:
        return LEGACY_MAP[cleaned.lower()]
    return cleaned


def normalize_status(raw: Any) -> str:
    if not raw:
        return "unknown"
    s = str(raw).strip().lower()
    if "trivial" in s:
        return "trivial"
    if "proved" in s or "proof" in s:
        return "proved_optimal"
    if "best" in s or "found" in s or "conjectured" in s:
        return "best_known"
    return "unknown"


FAMILY_DISPLAY_NAMES = {
    "3_in_3": "Triangles in Triangle",
    "3_in_4": "Triangles in Square",
    "3_in_5": "Triangles in Pentagon",
    "3_in_6": "Triangles in Hexagon",
    "3_in_8": "Triangles in Octagon",
    "3_in_circle": "Triangles in Circle",
    "3_in_domino": "Triangles in Domino",
    "3_in_L": "Triangles in L-tromino",
    "3_in_tan": "Triangles in Tan",
    "4_in_3": "Squares in Triangle",
    "4_in_4": "Squares in Square",
    "4_in_5": "Squares in Pentagon",
    "4_in_6": "Squares in Hexagon",
    "4_in_8": "Squares in Octagon",
    "4_in_circle": "Squares in Circle",
    "4_in_domino": "Squares in Domino",
    "4_in_L": "Squares in L-tromino",
    "4_in_tan": "Squares in Tan",
    "5_in_3": "Pentagons in Triangle",
    "5_in_4": "Pentagons in Square",
    "5_in_5": "Pentagons in Pentagon",
    "5_in_6": "Pentagons in Hexagon",
    "5_in_8": "Pentagons in Octagon",
    "5_in_circle": "Pentagons in Circle",
    "5_in_domino": "Pentagons in Domino",
    "5_in_L": "Pentagons in L-tromino",
    "5_in_tan": "Pentagons in Tan",
    "6_in_3": "Hexagons in Triangle",
    "6_in_4": "Hexagons in Square",
    "6_in_5": "Hexagons in Pentagon",
    "6_in_6": "Hexagons in Hexagon",
    "6_in_8": "Hexagons in Octagon",
    "6_in_circle": "Hexagons in Circle",
    "6_in_domino": "Hexagons in Domino",
    "6_in_L": "Hexagons in L-tromino",
    "6_in_tan": "Hexagons in Tan",
    "8_in_3": "Octagons in Triangle",
    "8_in_4": "Octagons in Square",
    "8_in_5": "Octagons in Pentagon",
    "8_in_6": "Octagons in Hexagon",
    "8_in_8": "Octagons in Octagon",
    "8_in_circle": "Octagons in Circle",
    "8_in_domino": "Octagons in Domino",
    "8_in_L": "Octagons in L-tromino",
    "8_in_tan": "Octagons in Tan",
    "circle_in_3": "Circles in Triangle",
    "circle_in_4": "Circles in Square",
    "circle_in_5": "Circles in Pentagon",
    "circle_in_6": "Circles in Hexagon",
    "circle_in_8": "Circles in Octagon",
    "circle_in_circle": "Circles in Circle",
    "circle_in_domino": "Circles in Domino",
    "circle_in_ellipse": "Circles in Ellipse",
    "circle_in_L": "Circles in L-tromino",
    "circle_in_tan": "Circles in Tan",
    "domino_in_3": "Dominoes in Triangle",
    "domino_in_4": "Dominoes in Square",
    "domino_in_5": "Dominoes in Pentagon",
    "domino_in_6": "Dominoes in Hexagon",
    "domino_in_8": "Dominoes in Octagon",
    "domino_in_circle": "Dominoes in Circle",
    "domino_in_domino": "Dominoes in Domino",
    "domino_in_L": "Dominoes in L-tromino",
    "domino_in_tan": "Dominoes in Tan",
    "L_in_3": "L-trominoes in Triangle",
    "L_in_5": "L-trominoes in Pentagon",
    "L_in_6": "L-trominoes in Hexagon",
    "L_in_8": "L-trominoes in Octagon",
    "L_in_circle": "L-trominoes in Circle",
    "L_in_domino": "L-trominoes in Domino",
    "L_in_L": "L-trominoes in L-tromino",
    "L_in_tan": "L-trominoes in Tan",
    "line_in_4": "Lines in Square",
    "line_in_circle": "Lines in Circle",
    "tan_in_3": "Tans in Triangle",
    "tan_in_4": "Tans in Square",
    "tan_in_5": "Tans in Pentagon",
    "tan_in_6": "Tans in Hexagon",
    "tan_in_8": "Tans in Octagon",
    "tan_in_circle": "Tans in Circle",
    "tan_in_domino": "Tans in Domino",
    "tan_in_L": "Tans in L-tromino",
    "tan_in_tan": "Tans in Tan",
}


def compute_friedman_metric(S: float, inner_token: str, container_token: str) -> float:
    container_upper = str(container_token).strip().upper()
    inner_upper = str(inner_token).strip().upper()

    if container_upper in ("CIRCLE", "CIR", "0"):
        c_metric = S
    elif container_upper in ("TAN", "DOMINO", "L"):
        c_metric = S
    else:
        try:
            nsc = int(container_upper)
            c_metric = 2 * S * math.sin(math.pi / nsc)
        except ValueError:
            c_metric = 2 * S * math.sin(math.pi / 3)

    if inner_upper in ("CIRCLE", "CIR", "0"):
        i_scale = 1.0
    elif inner_upper in ("TAN", "DOMINO", "L"):
        i_scale = 1.0
    else:
        try:
            nsi = int(inner_upper)
            i_scale = 2 * math.sin(math.pi / nsi)
        except ValueError:
            i_scale = 2 * math.sin(math.pi / 3)

    return c_metric / i_scale


def load_reference_entries() -> List[Dict[str, Any]]:
    entries = []
    if PACKING_VERIFICATION_DIR.exists():
        for json_file in sorted(PACKING_VERIFICATION_DIR.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    file_entries = json.load(f)
                    if isinstance(file_entries, list):
                        entries.extend(file_entries)
            except Exception as e:
                print(f"Warning: failed reading {json_file}: {e}")
    return entries


def load_local_solutions() -> Dict[str, Dict[str, Any]]:
    solutions = {}
    if not RESULTS_DIR.exists():
        return solutions

    for problem_dir in RESULTS_DIR.iterdir():
        if not problem_dir.is_dir():
            continue
        folder_name = problem_dir.name
        tokens = folder_name.split("_")
        inner_token = tokens[1] if len(tokens) >= 4 else "3"
        container_token = tokens[3] if len(tokens) >= 4 else "3"

        best_sol = None
        best_metric = None

        for run_dir in problem_dir.iterdir():
            if not run_dir.is_dir():
                continue
            sol_file = run_dir / "solution.json"
            if sol_file.exists():
                try:
                    with open(sol_file, "r", encoding="utf-8") as f:
                        sol_data = json.load(f)
                    S = sol_data.get("S")
                    if S is not None:
                        nsi = sol_data.get("inner_token") or sol_data.get("inner_sides") or sol_data.get("nsi") or inner_token
                        nsc = sol_data.get("container_token") or sol_data.get("container_sides") or sol_data.get("nsc") or container_token
                        metric = compute_friedman_metric(float(S), str(nsi), str(nsc))
                        if best_metric is None or metric < best_metric:
                            best_metric = metric
                            sol_data["computed_metric"] = metric
                            sol_data["inner_token"] = str(nsi)
                            sol_data["container_token"] = str(nsc)
                            sol_data["folder_name"] = folder_name
                            best_sol = sol_data
                except Exception:
                    pass

        if best_sol:
            solutions[folder_name] = best_sol

    return solutions


def parse_slurm_mill_logs() -> Dict[str, Dict[str, Any]]:
    log_stats = {}
    log_files = glob.glob(os.path.join(str(RESULTS_DIR), "mill-*.out"))

    start_re = re.compile(r"\[([a-zA-Z0-9_]+)\] Starting \((\d+) attempts\)")
    success_re = re.compile(r"\[([a-zA-Z0-9_]+)\] Success!")
    score_re = re.compile(r"\[Main\] Worker finished ([a-zA-Z0-9_]+) with score ([\d\.]+)")
    fail_re = re.compile(r"\[([a-zA-Z0-9_]+)\] Search failed")

    for lf in log_files:
        try:
            with open(lf, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    for m in start_re.finditer(line):
                        prob = m.group(1)
                        log_stats.setdefault(prob, {"starts": 0, "attempts": 0, "successes": 0, "fails": 0})
                        log_stats[prob]["starts"] += 1
                        log_stats[prob]["attempts"] += int(m.group(2))
                    for m in success_re.finditer(line):
                        prob = m.group(1)
                        log_stats.setdefault(prob, {"starts": 0, "attempts": 0, "successes": 0, "fails": 0})
                        log_stats[prob]["successes"] += 1
                    for m in fail_re.finditer(line):
                        prob = m.group(1)
                        log_stats.setdefault(prob, {"starts": 0, "attempts": 0, "successes": 0, "fails": 0})
                        log_stats[prob]["fails"] += 1
        except Exception:
            pass

    return log_stats


def load_priority_queue() -> Dict[str, Dict[str, Any]]:
    pq_dict = {}
    if PRIORITY_QUEUE_PATH.exists():
        try:
            with open(PRIORITY_QUEUE_PATH, "r", encoding="utf-8") as f:
                pq_list = json.load(f)
            for idx, item in enumerate(pq_list):
                prob = item.get("problem", "")
                pq_dict[prob] = {
                    "priority_rank": idx + 1,
                    "density": item.get("density"),
                    "status": item.get("status"),
                    "best_value": item.get("best_value"),
                }
        except Exception:
            pass
    return pq_dict


def main():
    ref_entries = load_reference_entries()
    if not ref_entries:
        raise FileNotFoundError("No reference benchmark entries found in packingVerification/.")

    solutions = load_local_solutions()
    log_stats = parse_slurm_mill_logs()
    pq_dict = load_priority_queue()

    problems_list = []
    family_stats: Dict[str, Dict[str, Any]] = {}
    seen_ids = set()

    new_best_list = []
    matches_best_list = []
    attempted_list = []

    for entry in ref_entries:
        raw_family = entry.get("problem_family", "")
        family_slug = normalize_family_slug(raw_family)

        prob_n = entry.get("N")
        entry_id = f"{family_slug}_{prob_n}"

        if entry_id in seen_ids:
            continue
        seen_ids.add(entry_id)

        if family_slug not in family_stats:
            family_name = FAMILY_DISPLAY_NAMES.get(family_slug, family_slug)
            family_stats[family_slug] = {
                "slug": family_slug,
                "name": family_name,
                "inner_shape": entry.get("inner_shape"),
                "container_shape": entry.get("container_shape"),
                "total_problems": 0,
                "proved_optimal_count": 0,
                "best_known_count": 0,
                "trivial_count": 0,
                "attempted_count": 0,
                "new_best_count": 0,
            }

        fam = family_stats[family_slug]
        fam["total_problems"] += 1
        ref_status = normalize_status(entry.get("status", "unknown"))
        if ref_status == "proved_optimal":
            fam["proved_optimal_count"] += 1
        elif ref_status == "best_known":
            fam["best_known_count"] += 1
        elif ref_status == "trivial":
            fam["trivial_count"] += 1

        known_value = entry.get("best_value")
        if known_value is not None:
            try:
                known_value = float(known_value)
            except (ValueError, TypeError):
                known_value = None

        # Match local solution run folders
        inner_token = entry.get("inner_shape")
        container_token = entry.get("container_shape")
        our_prob_key = entry.get("our_problem") or f"{prob_n}_{raw_family}"

        possible_folder_keys = [
            f"{prob_n}_{inner_token}_in_{container_token}",
            f"{prob_n}_{raw_family}",
            our_prob_key,
            f"{prob_n}_{family_slug}",
        ]

        sol_data = None
        for pk in possible_folder_keys:
            if pk and pk in solutions:
                sol_data = solutions[pk]
                break

        # Check execution logs
        l_stat = log_stats.get(our_prob_key) or log_stats.get(f"{prob_n}_{family_slug}") or {}

        # Check priority queue
        pq_item = pq_dict.get(our_prob_key) or pq_dict.get(f"{prob_n}_{raw_family}") or pq_dict.get(f"{prob_n}_{family_slug}")

        attempted = (sol_data is not None) or (l_stat.get("starts", 0) > 0)
        if attempted:
            fam["attempted_count"] += 1

        # Comparison status & diff metric
        our_best_metric = sol_data.get("computed_metric") if sol_data else None
        comparison_status = "unattempted"
        diff = None
        closeness_pct = None

        if our_best_metric is not None:
            if known_value is None:
                comparison_status = "no_best_known"
            elif our_best_metric < known_value - 1e-6:
                comparison_status = "NEW_BEST"
                fam["new_best_count"] += 1
                diff = our_best_metric - known_value
                closeness_pct = (known_value / our_best_metric) * 100.0
            elif abs(our_best_metric - known_value) < 1e-4:
                comparison_status = "matches_best_known"
                diff = 0.0
                closeness_pct = 100.0
            else:
                comparison_status = "worse_than_best_known"
                diff = our_best_metric - known_value
                closeness_pct = (known_value / our_best_metric) * 100.0 if our_best_metric > 0 else 0.0

        item = {
            "id": entry_id,
            "problem_family": family_slug,
            "N": prob_n,
            "inner_shape": inner_token,
            "container_shape": container_token,
            "known_value": known_value,
            "best_value": known_value,
            "ref_status": ref_status,
            "status": ref_status,
            "attempted": attempted,
            "our_best_metric": round(our_best_metric, 6) if our_best_metric is not None else None,
            "our_best_s": round(sol_data.get("S"), 6) if sol_data and sol_data.get("S") else None,
            "comparison_status": comparison_status,
            "diff": round(diff, 6) if diff is not None else None,
            "closeness_pct": round(closeness_pct, 2) if closeness_pct is not None else None,
            "starts": l_stat.get("starts", 0),
            "attempts": l_stat.get("attempts", 0),
            "successes": l_stat.get("successes", 0),
            "fails": l_stat.get("fails", 0),
            "priority_rank": pq_item.get("priority_rank") if pq_item else None,
            "density": round(pq_item.get("density"), 4) if pq_item and pq_item.get("density") else None,
            "source_url": entry.get("source_url"),
            "source_note": entry.get("source_note"),
            "solution": sol_data,
        }
        problems_list.append(item)

        if comparison_status == "NEW_BEST":
            new_best_list.append(item)
        elif comparison_status == "matches_best_known":
            matches_best_list.append(item)

        if attempted:
            attempted_list.append(item)

    problems_list.sort(key=lambda p: (p["problem_family"], p["N"]))
    families_list = list(family_stats.values())
    families_list.sort(key=lambda x: x["slug"])

    priority_targets = [p for p in problems_list if p.get("priority_rank") is not None]
    priority_targets.sort(key=lambda p: p["priority_rank"])

    def sanitize_floats(obj):
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        elif isinstance(obj, dict):
            return {k: sanitize_floats(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [sanitize_floats(x) for x in obj]
        return obj

    site_data = sanitize_floats({
        "summary": {
            "total_families": len(families_list),
            "total_problems": len(problems_list),
            "proved_optimal": sum(f["proved_optimal_count"] for f in families_list),
            "best_known": sum(f["best_known_count"] for f in families_list),
            "trivial": sum(f["trivial_count"] for f in families_list),
            "total_attempted": len(attempted_list),
            "total_new_bests": len(new_best_list),
            "total_matches": len(matches_best_list),
            "total_visualizations": len(solutions),
            "total_slurm_starts": sum(p["starts"] for p in problems_list),
            "total_slurm_attempts": sum(p["attempts"] for p in problems_list),
        },
        "new_bests": new_best_list,
        "matches_bests": matches_best_list,
        "priority_targets": priority_targets[:25],
        "families": families_list,
        "problems": problems_list,
    })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(site_data, f, indent=2)

    print(f"Generated analytics site_data.json with {len(families_list)} families, {len(problems_list)} problems, {len(new_best_list)} NEW_BEST records, and {len(attempted_list)} attempted problems at {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
