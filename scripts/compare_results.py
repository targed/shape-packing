import json
import os
from collections import defaultdict

RESULTS_DIR = (
    os.path.join("data", "results")
    if os.path.exists(os.path.join("data", "results"))
    else "results"
)
PACKING_VER_DIR = (
    os.path.join("data", "packingVerification")
    if os.path.exists(os.path.join("data", "packingVerification"))
    else "packingVerification"
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

def name_for(s):
    s = str(s).strip().lower()
    if s in SIDES_TO_NAME:
        return SIDES_TO_NAME[s]
    return SPECIAL_NAMES.get(s, s)

def is_circle_token(token):
    if token is None:
        return False
    t = str(token).strip().upper()
    return t in ("CIRCLE", "CIR", "0")

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

try:
    from shape_packing.solution_tools import compute_friedman_metric
except ImportError:
    from src.shape_packing.solution_tools import compute_friedman_metric

def normalize_final_metric(data, is_circle_container=False):
    """
    Canonical metric to compare with Friedman best_value is 'final_metric'.
    We recompute this directly from S and shape metadata using compute_friedman_metric
    to ensure we override any stale/incorrect metrics stored in old JSONs.
    """
    S = data.get("S")
    if S is None:
        return None
    try:
        S = float(S)
    except (TypeError, ValueError):
        return None

    nsi_raw = str(data.get("inner_sides") or data.get("nsi") or data.get("inner_token", "3"))
    nsc_raw = str(data.get("container_sides") or data.get("nsc") or data.get("container_token", "3"))

    if is_circle_container:
        nsc_raw = "CIRCLE"

    return compute_friedman_metric(S, nsi_raw, nsc_raw)


def find_best_solution(problem_dir, is_circle_container=False):
    best_metric = None
    best_data = None
    best_file = None

    for run in sorted(os.listdir(problem_dir)):
        sol_path = os.path.join(problem_dir, run, "solution.json")
        if not os.path.isfile(sol_path):
            continue

        with open(sol_path, "r") as f:
            try:
                data = json.load(f)
            except Exception:
                continue

        metric = normalize_final_metric(data, is_circle_container=is_circle_container)
        if metric is not None and (best_metric is None or metric < best_metric):
            best_metric = metric
            best_data = data
            best_file = sol_path

    return best_data, best_metric, best_file

def main():
    comparison = defaultdict(list)

    if not os.path.isdir(RESULTS_DIR) or not os.path.isdir(PACKING_VER_DIR):
        print("Run this script from the root shape-packing directory.")
        return

    for folder in os.listdir(RESULTS_DIR):
        folder_path = os.path.join(RESULTS_DIR, folder)
        if not os.path.isdir(folder_path):
            continue

        # Expect pattern: N_X_in_Y (e.g. 10_4_in_3, 10_6_in_CIRCLE)
        tokens = folder.split("_")
        if len(tokens) != 4 or tokens[2].lower() != "in":
            continue

        try:
            N = int(tokens[0])
        except ValueError:
            continue

        inner_sides = tokens[1]
        container_sides = tokens[3]

        inner_name = name_for(inner_sides)
        container_name = name_for(container_sides)
        pack_file = f"{inner_name}in{container_name}.json"
        pack_path = os.path.join(PACKING_VER_DIR, pack_file)

        # Skip problems without a matching verification file
        if not os.path.isfile(pack_path):
            continue

        container_is_circle = is_circle_token(container_sides)
        best, best_metric, best_file = find_best_solution(
            folder_path, is_circle_container=container_is_circle
        )
        if best_metric is None:
            continue

        with open(pack_path, "r") as f:
            try:
                known = json.load(f)
            except Exception:
                known = []

        entry = next((k for k in known if k.get("N") == N), None)
        known_value = entry.get("best_value") if entry else None

        # Determine comparison status
        # Note: circle containers now compare normally - final_metric = S ≈ Friedman's r
        if known_value is None:
            status = "no_best_known"
        elif best_metric < known_value - 1e-6:
            status = "NEW_BEST"
        elif abs(best_metric - known_value) < 1e-4:
            status = "matches_best_known"
        else:
            status = "worse_than_best_known"

        comparison[folder].append({
            "N": N,
            "best_metric": best_metric,
            "known_value": known_value,
            "status": status,
            "best_file": best_file
        })

    # Print summary
    print(f"{'Problem':<24} {'N':<4} {'Best metric':>10} {'Known':>10} {'Diff':>10} {'Status'}")
    print("-" * 80)
    for problem, entries in sorted(comparison.items()):
        for e in entries:
            diff = ""
            if e["known_value"] is not None:
                diff = f"{e['best_metric'] - e['known_value']:+.6f}"
            known_str = f"{e['known_value']:.6f}" if e["known_value"] is not None else "N/A"
            print(
                f"{problem:<24} {e['N']:<4} "
                f"{e['best_metric']:>10.6f} "
                f"{known_str:>10} "
                f"{diff:>10} {e['status']}"
            )

if __name__ == "__main__":
    main()