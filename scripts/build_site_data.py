#!/usr/bin/env python3
"""
build_site_data.py

Ingests PACKING_REFERENCE.json, results.tsv, and results/ solution files
to generate site/src/data/site_data.json for the Astro dashboard.
"""

import json
import csv
from pathlib import Path
from typing import Dict, Any, List

ROOT_DIR = Path(__file__).resolve().parent.parent
PACKING_REF_PATH = ROOT_DIR / "PACKING_REFERENCE.json"
RESULTS_TSV_PATH = ROOT_DIR / "results.tsv"
RESULTS_DIR = ROOT_DIR / "results"
OUTPUT_PATH = ROOT_DIR / "site" / "src" / "data" / "site_data.json"

SHAPE_NAMES = {
    "3": "Triangle",
    "4": "Square",
    "5": "Pentagon",
    "6": "Hexagon",
    "8": "Octagon",
    "CIRCLE": "Circle",
    "DOMINO": "Domino",
    "L": "L-tromino",
    "TAN": "Tan (7-iamond)",
}

FAMILY_NAMES = {
    "triincir": "Triangles in Circle",
    "triintan": "Triangles in Tan",
    "triinsqu": "Triangles in Square",
    "triintri": "Triangles in Triangle",
    "triinpen": "Triangles in Pentagon",
    "triinhex": "Triangles in Hexagon",
    "triinoct": "Triangles in Octagon",
    "triinL": "Triangles in L-tromino",
    "triindom": "Triangles in Domino",
    "squincir": "Squares in Circle",
    "squintan": "Squares in Tan",
    "squinsqu": "Squares in Square",
    "squintri": "Squares in Triangle",
    "squinpen": "Squares in Pentagon",
    "squinhex": "Squares in Hexagon",
    "squinoct": "Squares in Octagon",
    "squinl": "Squares in L-tromino",
    "squindom": "Squares in Domino",
    "penincir": "Pentagons in Circle",
    "penintan": "Pentagons in Tan",
    "peninsqu": "Pentagons in Square",
    "penintri": "Pentagons in Triangle",
    "peninpen": "Pentagons in Pentagon",
    "peninhex": "Pentagons in Hexagon",
    "peninoct": "Pentagons in Octagon",
    "peninL": "Pentagons in L-tromino",
    "penindom": "Pentagons in Domino",
    "hexincir": "Hexagons in Circle",
    "hexintan": "Hexagons in Tan",
    "hexinsqu": "Hexagons in Square",
    "hexintri": "Hexagons in Triangle",
    "hexinpen": "Hexagons in Pentagon",
    "hexinhex": "Hexagons in Hexagon",
    "hexinoct": "Hexagons in Octagon",
    "hexinL": "Hexagons in L-tromino",
    "hexindom": "Hexagons in Domino",
    "octincir": "Octagons in Circle",
    "octintan": "Octagons in Tan",
    "octinsqu": "Octagons in Square",
    "octintri": "Octagons in Triangle",
    "octinpen": "Octagons in Pentagon",
    "octinhex": "Octagons in Hexagon",
    "octinoct": "Octagons in Octagon",
    "octinL": "Octagons in L-tromino",
    "octindom": "Octagons in Domino",
    "cirincir": "Circles in Circle",
    "cirintan": "Circles in Tan",
    "cirinsqu": "Circles in Square",
    "cirintri": "Circles in Triangle",
    "cirinpen": "Circles in Pentagon",
    "cirinhex": "Circles in Hexagon",
    "cirinoct": "Circles in Octagon",
    "cirinl": "Circles in L-tromino",
    "cirindom": "Circles in Domino",
    "cirinel": "Circles in Ellipse",
    "cirinttt": "Circles in Equilateral Triangle",
    "tanincir": "Tans in Circle",
    "tanintan": "Tans in Tan",
    "taninsqu": "Tans in Square",
    "tanintri": "Tans in Triangle",
    "taninpen": "Tans in Pentagon",
    "taninhex": "Tans in Hexagon",
    "taninoct": "Tans in Octagon",
    "taninL": "Tans in L-tromino",
    "tanindom": "Tans in Domino",
    "domincir": "Dominoes in Circle",
    "domintan": "Dominoes in Tan",
    "dominsqu": "Dominoes in Square",
    "domintri": "Dominoes in Triangle",
    "dominpen": "Dominoes in Pentagon",
    "dominhex": "Dominoes in Hexagon",
    "dominoct": "Dominoes in Octagon",
    "dominL": "Dominoes in L-tromino",
    "domindom": "Dominoes in Domino",
    "LinL": "L-trominoes in L-tromino",
    "Lindom": "L-trominoes in Domino",
    "Linhex": "L-trominoes in Hexagon",
    "Linoct": "L-trominoes in Octagon",
    "Linpen": "L-trominoes in Pentagon",
    "Lintan": "L-trominoes in Tan",
    "Lintri": "L-trominoes in Triangle",
    "lincir": "Lines in Circle",
    "linsqu": "Lines in Square",
}


def load_solutions() -> Dict[str, Dict[str, Any]]:
    solutions = {}
    if not RESULTS_DIR.exists():
        return solutions

    for problem_dir in RESULTS_DIR.iterdir():
        if not problem_dir.is_dir():
            continue
        problem_key = problem_dir.name
        best_sol = None
        best_s = None

        for run_dir in problem_dir.iterdir():
            if not run_dir.is_dir():
                continue
            sol_file = run_dir / "solution.json"
            if sol_file.exists():
                try:
                    with open(sol_file, "r", encoding="utf-8") as f:
                        sol_data = json.load(f)
                    s_val = sol_data.get("S") or sol_data.get("final_metric")
                    if s_val is not None and (best_s is None or s_val > best_s):
                        best_s = float(s_val)
                        best_sol = sol_data
                except Exception:
                    pass

        if best_sol:
            solutions[problem_key] = best_sol

    return solutions


def main():
    if not PACKING_REF_PATH.exists():
        raise FileNotFoundError(f"{PACKING_REF_PATH} does not exist. Run parse_erich_friedman.py first.")

    with open(PACKING_REF_PATH, "r", encoding="utf-8") as f:
        ref_entries = json.load(f)

    solutions = load_solutions()

    # Index problems and group by family
    problems_list = []
    family_stats: Dict[str, Dict[str, Any]] = {}

    for entry in ref_entries:
        family_id = entry.get("problem_family", "")
        if family_id not in family_stats:
            family_name = FAMILY_NAMES.get(family_id, family_id)
            family_stats[family_id] = {
                "slug": family_id,
                "name": family_name,
                "inner_shape": entry.get("inner_shape"),
                "container_shape": entry.get("container_shape"),
                "total_problems": 0,
                "proved_optimal_count": 0,
                "best_known_count": 0,
                "solved_count": 0,
            }

        fam = family_stats[family_id]
        fam["total_problems"] += 1
        status = entry.get("status", "unknown")
        if status == "proved_optimal":
            fam["proved_optimal_count"] += 1
        elif status == "best_known":
            fam["best_known_count"] += 1

        prob_n = entry.get("N")
        problem_key = f"{prob_n}_{entry.get('inner_shape')}_in_{entry.get('container_shape')}"
        sol_data = solutions.get(problem_key) or solutions.get(f"{prob_n}_{family_id}")
        if sol_data:
            fam["solved_count"] += 1

        item = {
            "id": entry.get("id"),
            "problem_family": family_id,
            "N": prob_n,
            "inner_shape": entry.get("inner_shape"),
            "container_shape": entry.get("container_shape"),
            "best_value": entry.get("best_value"),
            "status": status,
            "source_url": entry.get("source_url"),
            "source_note": entry.get("source_note"),
            "solution": sol_data,
        }
        problems_list.append(item)

    families_list = list(family_stats.values())
    families_list.sort(key=lambda x: x["name"])

    site_data = {
        "summary": {
            "total_families": len(families_list),
            "total_problems": len(problems_list),
            "proved_optimal": sum(f["proved_optimal_count"] for f in families_list),
            "best_known": sum(f["best_known_count"] for f in families_list),
            "total_visualizations": len(solutions),
        },
        "families": families_list,
        "problems": problems_list,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(site_data, f, indent=2)

    print(f"Generated site_data.json with {len(families_list)} families and {len(problems_list)} problems at {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
