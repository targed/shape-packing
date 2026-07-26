#!/usr/bin/env python3
"""
Thin entrypoint for solution rendering.

Delegates all logic to solution_tools.render_solution.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    from shape_packing.solution_tools import render_solution
except ImportError:
    from src.shape_packing.solution_tools import render_solution


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python render_solution.py solution.json [output.png]")
        sys.exit(1)

    sol_path = sys.argv[1]
    out_png = sys.argv[2] if len(sys.argv) >= 3 else "solution.png"
    render_solution(sol_path, out_png=out_png)


if __name__ == "__main__":
    main()