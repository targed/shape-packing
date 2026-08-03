#!/usr/bin/env python3
"""
build_site_data.py

Ingests packingVerification/*.json (verified benchmark entries from Erich Friedman's site),
results.tsv, and results/ solution files to generate site/src/data/site_data.json.
"""

import json
import csv
from pathlib import Path
from typing import Dict, Any, List

ROOT_DIR = Path(__file__).resolve().parent.parent
PACKING_VERIFICATION_DIR = ROOT_DIR / "packingVerification"
RESULTS_DIR = ROOT_DIR / "results"
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
    cleaned = raw.strip()
    return LEGACY_MAP.get(cleaned, cleaned)


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
    ref_entries = load_reference_entries()
    if not ref_entries:
        raise FileNotFoundError("No reference benchmark entries found in packingVerification/.")

    solutions = load_solutions()

    # Index problems and group by normalized canonical family slug
    problems_list = []
    family_stats: Dict[str, Dict[str, Any]] = {}
    seen_ids = set()

    for entry in ref_entries:
        raw_family = entry.get("problem_family", "")
        family_slug = normalize_family_slug(raw_family)

        prob_n = entry.get("N")
        entry_id = f"{family_slug}_{prob_n}"

        # Prevent duplicate entries across files
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
                "solved_count": 0,
            }

        fam = family_stats[family_slug]
        fam["total_problems"] += 1
        status = entry.get("status", "unknown")
        if status == "proved_optimal":
            fam["proved_optimal_count"] += 1
        elif status == "best_known":
            fam["best_known_count"] += 1

        # Match local solution files
        problem_keys_to_try = [
            f"{prob_n}_{family_slug}",
            f"{prob_n}_{raw_family}",
            entry.get("our_problem", ""),
            f"{prob_n}_{entry.get('inner_shape')}_in_{entry.get('container_shape')}"
        ]
        sol_data = None
        for pk in problem_keys_to_try:
            if pk and pk in solutions:
                sol_data = solutions[pk]
                break

        if sol_data:
            fam["solved_count"] += 1

        best_val = entry.get("best_value")
        if best_val is not None:
            try:
                best_val = float(best_val)
            except (ValueError, TypeError):
                best_val = None

        item = {
            "id": entry_id,
            "problem_family": family_slug,
            "N": prob_n,
            "inner_shape": entry.get("inner_shape"),
            "container_shape": entry.get("container_shape"),
            "best_value": best_val,
            "status": status,
            "source_url": entry.get("source_url"),
            "source_note": entry.get("source_note"),
            "solution": sol_data,
        }
        problems_list.append(item)

    # Sort problems by family slug and then N numeric
    problems_list.sort(key=lambda p: (p["problem_family"], p["N"]))

    families_list = list(family_stats.values())
    families_list.sort(key=lambda x: x["slug"])

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
