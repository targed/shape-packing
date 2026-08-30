#!/usr/bin/env python3
"""
Batch verify all domino solutions:
- Ensure each is geometrically valid
- Check domino shape and count
- Compare best metrics to Friedman reference
"""
import json
import os
import csv
import subprocess
from collections import defaultdict

RESULTS_DIR = (
    os.path.join("data", "results")
    if os.path.exists(os.path.join("data", "results"))
    else "results"
)
FRIEDMAN_TSV = "scratch/PACKING_REFERENCE.tsv"

def load_friedman_ref():
    ref = {}
    with open(FRIEDMAN_TSV, "r") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        for row in reader:
            if not row:
                continue
            token = row[0].strip()
            best_score = float(row[1]) if row[1] else None
            ref[token] = {
                "best_score": best_score,
                "reference": row[2].strip() if len(row) > 2 else ""
            }
    return ref

def gather_domino_solutions():
    solutions = []
    for root, dirs, files in os.walk(RESULTS_DIR):
        for f in files:
            if f == "solution.json":
                path = os.path.join(root, f)
                with open(path, "r") as fh:
                    j = json.load(fh)
                inner = str(j.get("inner_token", ""))
                if "domino" in inner.lower():
                    solutions.append((path, j))
    return solutions

def verify_single(path, problem_str=None):
    cmd = [sys.executable, "scripts/verify_solution.py", path]
    if problem_str:
        cmd.append(problem_str)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.stdout.strip(), r.stderr.strip()

def main():
    friedman = load_friedman_ref()
    solutions = gather_domino_solutions()
    print(f"Found {len(solutions)} domino solution files")

    # Group by problem
    groups = defaultdict(list)
    for path, j in solutions:
        N = j.get("N")
        inner = j.get("inner_token")
        container = j.get("container_token")
        metric = float(j.get("final_metric", float("inf")))
        key = f"{N}_{inner}_{container}"
        groups[key].append((path, j, metric))

    # Per-problem checks
    invalid_solutions = []
    suspicious_beats = []

    for key in sorted(groups.keys()):
        entries = groups[key]
        # Find best metric and its path
        best_metric = None
        best_path = None
        for path, j, m in entries:
            if best_metric is None or m < best_metric:
                best_metric = m
                best_path = path

        # Compare to Friedman
        fr = friedman.get(key)
        fr_best = fr["best_score"] if fr and fr["best_score"] is not None else None

        status = ""
        if fr_best is not None:
            if best_metric < fr_best:
                status = "BEATS_FRIEDMAN (suspicious)"
                suspicious_beats.append(key)
            elif abs(best_metric - fr_best) < 1e-6:
                status = "matches_Friedman"
            else:
                status = "worse_than_Friedman"

        # Verify the best solution
        stdout, stderr = verify_single(best_path, problem_str=key)
        valid_line = stdout or stderr

        # Quick check: if metric == 6.404244654058302, it's suspect
        if best_metric == 6.404244654058302:
            invalid_solutions.append((key, best_path, "metric_matches_2_8_in_3_bug"))

        # Print summary
        print(f"{key}: "
              f"solutions={len(entries)}, "
              f"best_metric={best_metric:.6f}, "
              f"fr_best={fr_best}, "
              f"{status}, "
              f"verify={valid_line[:120]}")

    # Summary
    print("\n=== SUMMARY ===")
    print(f"Total domino solutions: {len(solutions)}")
    print(f"Problems: {len(groups)}")
    print(f"Suspicious (beat Friedman): {len(suspicious_beats)}")
    for k in suspicious_beats:
        print(f" - {k}")
    print(f"Clearly invalid (6.4042...): {len(invalid_solutions)}")
    for k, p, reason in invalid_solutions:
        print(f" - {k} ({p}) [{reason}]")

if __name__ == "__main__":
    main()