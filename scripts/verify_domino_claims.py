#!/usr/bin/env python3
"""
Comprehensive critic and verification audit for all domino packing solutions:
- Check domino shape & dimension (1x2 rectangle)
- Check polygon boundary containment (all vertices inside container polygon)
- Check overlap (SAT separation check between all pairs)
- Recompute metric vs Erich Friedman's reference values
"""
import os
import sys
import json
import math
import glob

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.shape_packing.solution_tools import (
    load_solution,
    verify_solution,
    compute_friedman_metric,
    build_polygons,
)
from src.shape_packing.packing_config import (
    get_friedman_best_for_problem,
    _load_friedman_verification_jsons,
)

def audit_domino_solutions():
    print("=" * 90)
    print("DOMINO PACKING SOLUTIONS AUDIT & CRITIC VERIFICATION")
    print("=" * 90)

    _load_friedman_verification_jsons()

    results_dir = os.path.join(REPO_ROOT, "results")
    if not os.path.exists(results_dir):
        print(f"ERROR: results directory not found at {results_dir}")
        return

    # Find all solution.json files under results/
    pattern = os.path.join(results_dir, "*", "*", "solution.json")
    sol_paths = glob.glob(pattern)
    print(f"Found {len(sol_paths)} total solution files under results/\n")

    domino_solutions = []

    for path in sol_paths:
        try:
            sol = load_solution(path)
        except Exception as e:
            continue

        inner = str(sol.inner_token).upper()
        if "DOMINO" in inner or inner == "DOM":
            domino_solutions.append((path, sol))

    print(f"Found {len(domino_solutions)} domino solution files to verify.\n")

    # Target problem list from user screenshot:
    # domino in 6: N=12, 14, 16, 17, 20, 21, 22, 28
    # domino in 8: N=4, 15
    # domino in 5: N=12, 15, 16, 19, 20, 21, 22, 23, 24, 25, 26

    # Group solutions by problem token
    problem_groups = {}
    for path, sol in domino_solutions:
        p_token = f"{sol.N}_{sol.inner_token}_in_{sol.container_token}"
        if p_token not in problem_groups:
            problem_groups[p_token] = []
        problem_groups[p_token].append((path, sol))

    results_summary = []

    for p_token, entries in sorted(problem_groups.items()):
        # Find entry with lowest S (best metric)
        best_path, best_sol = min(entries, key=lambda x: x[1].S)

        # 1. Verification with verify_solution
        v_res = verify_solution(best_path, problem_str=p_token)

        # 2. Check individual domino polygon dimensions
        polys = build_polygons(best_sol)
        poly_dim_ok = True
        poly_errors = []

        for idx, poly in enumerate(polys):
            # Check edge lengths of the 4 vertices
            v = poly
            if len(v) != 4:
                poly_dim_ok = False
                poly_errors.append(f"Poly {idx} has {len(v)} vertices, expected 4")
                continue

            e0 = math.hypot(v[1][0] - v[0][0], v[1][1] - v[0][1])
            e1 = math.hypot(v[2][0] - v[1][0], v[2][1] - v[1][1])

            # Dimensions should be 1.0 and 2.0 (or vice versa)
            dims = sorted([e0, e1])
            if abs(dims[0] - 1.0) > 1e-4 or abs(dims[1] - 2.0) > 1e-4:
                poly_dim_ok = False
                poly_errors.append(f"Poly {idx} dimensions ({dims[0]:.4f}, {dims[1]:.4f}) != (1.0, 2.0)")

        # 3. Friedman comparison
        recalculated_metric = compute_friedman_metric(best_sol.S, best_sol.inner_token, best_sol.container_token)
        friedman_best = get_friedman_best_for_problem(p_token)

        diff = None
        status = "UNKNOWN"
        if friedman_best is not None:
            diff = recalculated_metric - friedman_best
            if diff < -1e-5 and v_res.valid and poly_dim_ok:
                status = "BEATS_FRIEDMAN (RECORD!)"
            elif abs(diff) <= 1e-4 and v_res.valid and poly_dim_ok:
                status = "MATCHES_FRIEDMAN"
            elif diff > 1e-4:
                status = "WORSE_THAN_FRIEDMAN"
            else:
                status = "INVALID_RECORD_CLAIM"

        results_summary.append({
            "problem": p_token,
            "N": best_sol.N,
            "S": best_sol.S,
            "recalculated_metric": recalculated_metric,
            "friedman_best": friedman_best,
            "diff": diff,
            "valid": v_res.valid,
            "v_errors": v_res.errors,
            "poly_dim_ok": poly_dim_ok,
            "poly_errors": poly_errors,
            "status": status,
            "path": best_path,
        })

    # Print Report Table
    print(f"{'Problem':<22} {'S':>10} {'Metric':>10} {'Friedman':>10} {'Diff':>10} {'Valid?':<7} {'Status'}")
    print("-" * 90)

    records_cnt = 0
    invalid_cnt = 0

    for r in results_summary:
        fr_str = f"{r['friedman_best']:.6f}" if r['friedman_best'] is not None else "N/A"
        diff_str = f"{r['diff']:+.6f}" if r['diff'] is not None else "N/A"
        valid_str = "YES" if (r['valid'] and r['poly_dim_ok']) else "NO"

        if r['status'].startswith("BEATS_FRIEDMAN"):
            records_cnt += 1
        elif not r['valid'] or not r['poly_dim_ok']:
            invalid_cnt += 1

        print(f"{r['problem']:<22} {r['S']:>10.6f} {r['recalculated_metric']:>10.6f} {fr_str:>10} {diff_str:>10} {valid_str:<7} {r['status']}")

    print("\n" + "=" * 90)
    print(f"AUDIT SUMMARY:")
    print(f"  Total Domino Problems Evaluated: {len(results_summary)}")
    print(f"  Valid New World Records:        {records_cnt}")
    print(f"  Invalid / Flawed Solutions:     {invalid_cnt}")
    print("=" * 90)

    if invalid_cnt > 0:
        print("\nDETAILS OF INVALID SOLUTIONS:")
        for r in results_summary:
            if not r['valid'] or not r['poly_dim_ok']:
                print(f"\n--- Problem: {r['problem']} ({r['path']}) ---")
                print(f"  Geometry Valid: {r['valid']}")
                if r['v_errors']:
                    for err in r['v_errors']:
                        print(f"    - {err}")
                print(f"  Polygon Dimensions Valid: {r['poly_dim_ok']}")
                if r['poly_errors']:
                    for err in r['poly_errors']:
                        print(f"    - {err}")

if __name__ == "__main__":
    audit_domino_solutions()
