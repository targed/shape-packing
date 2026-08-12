#!/usr/bin/env python3
"""
Ad-hoc verification for 2_8_in_3 and dyld-fix:
- 2_8_in_3 with aggressive target-s must say "No valid packing found."
- 4_3_in_3 normal run must succeed and be valid.
- No dyld / PyExc_AttributeError crashes.
"""
import os
import sys
import tempfile
import subprocess
import json
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.shape_packing.packing_config import RUST_RELEASE_BIN
SOLVER = RUST_RELEASE_BIN if not os.name == 'nt' else RUST_RELEASE_BIN + ".exe"
TOLERANCE = 1e-5

def run_solver(args_list, out_json):
    cmd = [SOLVER] + args_list + ["--solution-file", out_json]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return r.stdout.strip(), r.stderr.strip(), r.returncode, out_json

def verify_no_solution(stdout):
    return "No valid packing found" in stdout

def verify_solution_json(path, problem_str=None):
    from src.shape_packing.solution_tools import verify_solution
    return verify_solution(path, problem_str=problem_str)

def main():
    errors = []

    # TEST 1: 2_8_in_3 with aggressive target-s should NOT produce a solution
    tmp_dir = tempfile.gettempdir()
    tmp1 = os.path.join(tmp_dir, "hermes-verify-2_8_in_3.json")
    out, err, rc, _ = run_solver(
        ["2", "8", "3", "--attempts", "2000", "--target-s", "2.83"],
        tmp1
    )
    if verify_no_solution(out):
        print("TEST1 PASS: 2_8_in_3 with target-s=2.83 correctly says 'No valid packing found.'")
        if os.path.exists(tmp1):
            os.remove(tmp1)
    else:
        msg = "TEST1 FAIL: Solver should have reported no valid packing for 2_8_in_3 with aggressive target-s."
        if os.path.exists(tmp1):
            vr = verify_solution_json(tmp1, "2_8_in_3")
            msg += f" Instead wrote JSON; valid={vr.valid}, errors={vr.errors[:3]}"
            os.remove(tmp1)
        print(msg)
        errors.append(msg)

    # TEST 2: Normal run on easy problem (4_3_in_3) should still succeed
    tmp2 = os.path.join(tmp_dir, "hermes-verify-4_3_in_3.json")
    out2, err2, rc2, _ = run_solver(
        ["4", "3", "3", "--attempts", "5000"],
        tmp2
    )
    if not verify_no_solution(out2) and os.path.exists(tmp2):
        vr2 = verify_solution_json(tmp2, "4_3_in_3")
        if vr2.valid:
            with open(tmp2) as f:
                d = json.load(f)
            print(f"TEST2 PASS: 4_3_in_3 solution valid. S={d['S']:.6f}, final_metric={d['final_metric']:.6f}")
            os.remove(tmp2)
        else:
            msg = f"TEST2 FAIL: 4_3_in_3 produced invalid solution: {vr2.errors}"
            print(msg)
            errors.append(msg)
            os.remove(tmp2)
    else:
        msg = "TEST2 FAIL: 4_3_in_3 did not produce any solution at all."
        print(msg)
        errors.append(msg)
        if os.path.exists(tmp2):
            os.remove(tmp2)

    # SUMMARY
    if errors:
        print("\nVERIFICATION FAILED:")
        for e in errors:
            print(" -", e)
        return 1
    else:
        print("\nAll ad-hoc verifications passed.")
        return 0

if __name__ == "__main__":
    sys.exit(main())