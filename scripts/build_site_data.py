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
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from shape_packing.catalog import (
    get_pair_tier,
    list_frontier_families,
    load_catalog,
    normalize_token,
)
from shape_packing.solution_tools import (
    compute_friedman_metric,
    inverse_friedman_metric,
)
PACKING_VERIFICATION_DIR = (
    ROOT_DIR / "data" / "packingVerification"
    if (ROOT_DIR / "data" / "packingVerification").exists()
    else ROOT_DIR / "packingVerification"
)
RESULTS_DIR = (
    ROOT_DIR / "data" / "results"
    if (ROOT_DIR / "data" / "results").exists()
    else ROOT_DIR / "results"
)
PRIORITY_QUEUE_PATH = (
    ROOT_DIR / "data" / "priority_queue.json"
    if (ROOT_DIR / "data" / "priority_queue.json").exists()
    else ROOT_DIR / "priority_queue.json"
)
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
    "cirin7": "circle_in_7", "circle_in_7": "circle_in_7",
    "cirin9": "circle_in_9", "circle_in_9": "circle_in_9",
    "cirin10": "circle_in_10", "circle_in_10": "circle_in_10",
    "cirinsemi": "circle_in_semicircle", "circle_in_semicircle": "circle_in_semicircle",
    "cirinquad": "circle_in_quadrant", "circle_in_quadrant": "circle_in_quadrant",
    "cirinel": "circle_in_ellipse", "circle_in_ellipse": "circle_in_ellipse",
    "cirinttt": "circle_in_arbitrary_triangle", "circle_in_arbitrary_triangle": "circle_in_arbitrary_triangle",
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
    # L-trominoes (including Friedman lincir / linsqu which pack L-trominoes)
    "LinL": "L_in_L", "L_in_L": "L_in_L",
    "Lindom": "L_in_domino", "L_in_domino": "L_in_domino",
    "Linhex": "L_in_6", "L_in_6": "L_in_6",
    "Linoct": "L_in_8", "L_in_8": "L_in_8",
    "Linpen": "L_in_5", "L_in_5": "L_in_5",
    "Lintan": "L_in_tan", "L_in_tan": "L_in_tan",
    "Lintri": "L_in_3", "L_in_3": "L_in_3",
    "lincir": "L_in_circle", "L_in_circle": "L_in_circle",
    "linsqu": "L_in_4", "L_in_4": "L_in_4",
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


def _build_family_display_names() -> Dict[str, str]:
    catalog = load_catalog()
    shapes = catalog["shapes"]
    names: Dict[str, str] = {
        "circle_in_ellipse": "Circles in Arbitrary Ellipse",
        "circle_in_arbitrary_triangle": "Circles in Arbitrary Triangle",
    }
    for i_spec in shapes.values():
        for c_spec in shapes.values():
            slug = f"{i_spec['slug']}_in_{c_spec['slug']}"
            names[slug] = f"{i_spec['display_plural']} in {c_spec['display_singular']}"
    return names


FAMILY_DISPLAY_NAMES = _build_family_display_names()


def _load_catalog_shape_variants() -> Dict[str, List[str]]:
    catalog = load_catalog()
    variants: Dict[str, List[str]] = {}
    for canonical, spec in catalog["shapes"].items():
        vals = [canonical, spec["slug"], spec["short_code"]] + list(spec.get("aliases", []))
        dedup: List[str] = []
        for v in vals:
            for form in (v, v.lower(), v.upper()):
                if form and form not in dedup:
                    dedup.append(form)
        variants[canonical] = dedup
        for alias in spec.get("aliases", []):
            variants[alias.upper()] = dedup
    return variants


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


def load_db_solutions() -> Dict[str, Dict[str, Any]]:
    db_path = ROOT_DIR / "shape_packing.db"
    solutions = {}
    if not db_path.exists():
        return solutions

    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        rows = c.execute(
            """
            SELECT s.problem_id, s.metric_s, s.coordinates_json, s.worker_username, s.verified_at,
                   p.n, p.inner_token, p.container_token, p.reference_s
            FROM solutions s
            JOIN problems p ON s.problem_id = p.id
            WHERE s.is_current_record = 1
            """
        ).fetchall()
        for r in rows:
            prob_id = r[0]
            metric_s = float(r[1])
            coords = json.loads(r[2]) if r[2] else []
            worker_username = r[3]
            verified_at = r[4]
            n = r[5]
            inner_token = r[6]
            container_token = r[7]
            ref_s = float(r[8]) if r[8] is not None else None

            sol_data = {
                "N": n,
                "inner_token": inner_token,
                "container_token": container_token,
                "computed_metric": metric_s,
                "S": inverse_friedman_metric(metric_s, inner_token, container_token),
                "values": coords,
                "worker_username": worker_username,
                "verified_at": str(verified_at),
                "source": "database",
            }
            solutions[prob_id] = sol_data
            solutions[f"{n}_{inner_token}_in_{container_token}"] = sol_data
            solutions[f"{n}_{inner_token.lower()}_in_{container_token.lower()}"] = sol_data
        conn.close()
    except Exception as exc:
        print(f"Warning: failed reading solutions from DB: {exc}")
    return solutions


def load_recent_solutions(limit: int = 20) -> List[Dict[str, Any]]:
    db_path = ROOT_DIR / "shape_packing.db"
    if not db_path.exists():
        return []

    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        rows = c.execute(
            """
            SELECT s.id, s.problem_id, s.metric_s, s.worker_username, s.verified_at, s.is_current_record,
                   p.n, p.inner_token, p.container_token, p.reference_s, p.status
            FROM solutions s
            LEFT JOIN problems p ON s.problem_id = p.id
            ORDER BY s.verified_at DESC, s.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        results = []
        for r in rows:
            prob_id = r[1]
            metric_s = float(r[2])
            worker_username = r[3]
            verified_at = r[4]
            is_record = bool(r[5])
            n = r[6]
            inner_token = r[7]
            container_token = r[8]
            ref_s = r[9]
            diff = (metric_s - float(ref_s)) if (ref_s is not None) else None

            results.append({
                "id": r[0],
                "problem_id": prob_id,
                "n": n,
                "inner_token": inner_token,
                "container_token": container_token,
                "metric_s": round(metric_s, 6),
                "reference_s": round(float(ref_s), 6) if ref_s is not None else None,
                "diff": round(diff, 6) if diff is not None else None,
                "is_current_record": is_record,
                "worker_username": worker_username,
                "verified_at": str(verified_at),
            })
        conn.close()
        return results
    except Exception as exc:
        print(f"Warning: could not load recent solutions: {exc}")
        return []


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


SHAPE_VARIANTS = _load_catalog_shape_variants()


def generate_key_variants(entry: Dict[str, Any]) -> List[str]:
    prob_n = entry.get("N")
    raw_family = entry.get("problem_family", "")
    family_slug = normalize_family_slug(raw_family)
    inner_token = str(entry.get("inner_shape", "")).upper()
    container_token = str(entry.get("container_shape", "")).upper()
    our_prob_key = entry.get("our_problem")

    inner_vars = SHAPE_VARIANTS.get(inner_token, [inner_token, inner_token.lower()])
    container_vars = SHAPE_VARIANTS.get(container_token, [container_token, container_token.lower()])

    keys = []
    if our_prob_key:
        keys.extend([our_prob_key, our_prob_key.lower(), our_prob_key.upper()])

    keys.extend([
        f"{prob_n}_{raw_family}",
        f"{prob_n}_{raw_family.lower()}",
        f"{prob_n}_{raw_family.upper()}",
        f"{prob_n}_{family_slug}",
        f"{prob_n}_{family_slug.upper()}",
    ])

    for iv in inner_vars:
        for cv in container_vars:
            keys.append(f"{prob_n}_{iv}_in_{cv}")

    seen = set()
    res = []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            res.append(k)
    return res


def main():
    ref_entries = load_reference_entries()
    if not ref_entries:
        raise FileNotFoundError("No reference benchmark entries found in packingVerification/.")

    local_solutions = load_local_solutions()
    db_solutions = load_db_solutions()
    solutions = dict(local_solutions)
    for k, sol in db_solutions.items():
        if k not in solutions:
            solutions[k] = sol
        else:
            local_metric = solutions[k].get("computed_metric")
            db_metric = sol.get("computed_metric")
            if db_metric is not None and (local_metric is None or db_metric < local_metric):
                solutions[k] = sol

    recent_solutions = load_recent_solutions(limit=25)
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

        # Fix legacy cirinttt -> arbitrary triangle & lincir/linsqu -> L-tromino metadata
        if raw_family.lower() == "cirinttt":
            inner_shape = "circle"
            container_shape = "arbitrary_triangle"
        elif raw_family.lower() in ("lincir", "linsqu"):
            inner_shape = "L"
            container_shape = entry.get("container_shape")
        else:
            inner_shape = entry.get("inner_shape")
            container_shape = entry.get("container_shape")

        prob_tier = entry.get("tier") or get_pair_tier(inner_shape, container_shape) or "benchmark"

        if family_slug not in family_stats:
            family_name = FAMILY_DISPLAY_NAMES.get(family_slug, family_slug)
            family_stats[family_slug] = {
                "slug": family_slug,
                "name": family_name,
                "inner_shape": inner_shape,
                "container_shape": container_shape,
                "tier": prob_tier,
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

        possible_folder_keys = generate_key_variants(entry)

        sol_data = None
        for pk in possible_folder_keys:
            if pk and pk in solutions:
                sol_data = solutions[pk]
                break

        # Check execution logs
        l_stat = {}
        for pk in possible_folder_keys:
            if pk and pk in log_stats:
                l_stat = log_stats[pk]
                break

        # Check priority queue
        pq_item = None
        for pk in possible_folder_keys:
            if pk and pk in pq_dict:
                pq_item = pq_dict[pk]
                break

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
            "inner_shape": inner_shape,
            "container_shape": container_shape,
            "tier": prob_tier,
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

    # Append curated Frontier quad families (N=1..20) cleanly after benchmark entries
    for f_slug, f_inner, f_container in list_frontier_families():
        if f_slug not in family_stats:
            family_stats[f_slug] = {
                "slug": f_slug,
                "name": FAMILY_DISPLAY_NAMES.get(f_slug, f_slug),
                "inner_shape": f_inner.lower() if f_inner != "L" else "L",
                "container_shape": f_container.lower() if f_container != "L" else "L",
                "tier": "frontier",
                "total_problems": 0,
                "proved_optimal_count": 0,
                "best_known_count": 0,
                "trivial_count": 0,
                "attempted_count": 0,
                "new_best_count": 0,
            }
        fam = family_stats[f_slug]
        for prob_n in range(1, 21):
            entry_id = f"{f_slug}_{prob_n}"
            if entry_id in seen_ids:
                continue
            seen_ids.add(entry_id)
            fam["total_problems"] += 1

            stub_entry = {
                "N": prob_n,
                "problem_family": f_slug,
                "inner_shape": f_inner,
                "container_shape": f_container,
                "our_problem": f"{prob_n}_{f_inner}_in_{f_container}",
            }
            sol_data = None
            for pk in generate_key_variants(stub_entry):
                if pk and pk in solutions:
                    sol_data = solutions[pk]
                    break
            our_best_metric = sol_data.get("computed_metric") if sol_data else None
            attempted = sol_data is not None
            if attempted:
                fam["attempted_count"] += 1

            f_item = {
                "id": entry_id,
                "problem_family": f_slug,
                "N": prob_n,
                "inner_shape": fam["inner_shape"],
                "container_shape": fam["container_shape"],
                "tier": "frontier",
                "known_value": None,
                "best_value": None,
                "ref_status": "frontier",
                "status": "frontier",
                "attempted": attempted,
                "our_best_metric": round(our_best_metric, 6) if our_best_metric is not None else None,
                "our_best_s": round(sol_data.get("S"), 6) if sol_data and sol_data.get("S") else None,
                "comparison_status": "frontier_best" if our_best_metric is not None else "unattempted",
                "diff": None,
                "closeness_pct": None,
                "starts": 0,
                "attempts": 0,
                "successes": 0,
                "fails": 0,
                "priority_rank": None,
                "density": None,
                "source_url": None,
                "source_note": "Original Frontier family (canonical quadrilateral prototype).",
                "solution": sol_data,
            }
            problems_list.append(f_item)
            if attempted:
                attempted_list.append(f_item)

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
            "benchmark_families": sum(1 for f in families_list if f.get("tier", "benchmark") == "benchmark"),
            "frontier_families": sum(1 for f in families_list if f.get("tier") == "frontier"),
            "total_problems": len(problems_list),
            "frontier_problems": sum(1 for p in problems_list if p.get("tier") == "frontier"),
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
        "recent_solutions": recent_solutions,
        "families": families_list,
        "problems": problems_list,
    })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(site_data, f, indent=2)

    print(f"Generated analytics site_data.json with {len(families_list)} families, {len(problems_list)} problems, {len(new_best_list)} NEW_BEST records, and {len(attempted_list)} attempted problems at {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
