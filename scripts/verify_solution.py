#!/usr/bin/env python3
"""
Thin entrypoint for solution verification.

Delegates all logic to solution_tools.verify_solution.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    from shape_packing.solution_tools import verify_solution
except ImportError:
    from src.shape_packing.solution_tools import verify_solution


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python verify_solution.py <solution.json> [problem_string]")
        sys.exit(1)

    sol_path = sys.argv[1]
    problem_str = sys.argv[2] if len(sys.argv) > 2 else None

    result = verify_solution(sol_path, problem_str=problem_str)

    if result.valid:
        print(f"[PASS] {result.message}")
        if result.new_record:
            print("*** NEW RECORD DISCOVERED! ***")
    else:
        print(f"[FAIL] {result.message}")

    sys.exit(0 if result.valid else 1)


if __name__ == "__main__":
    main()