#!/usr/bin/env python3
"""
render_solution.py

Takes a JSON solution file from packer_rs and renders a packing image (PNG).
Usage:
    uv run render_solution.py solution.json output.png
"""

import json
import math
import sys
import os

os.environ.setdefault("MPLBACKEND", "Agg")


def load_solution(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def render(solution: dict, out_path: str):
    N = solution["N"]
    values = solution["values"]
    nsi = solution["inner_sides"]
    nsc = solution["container_sides"]
    final_metric = solution["final_metric"]

    # vertices of unit regular polygons
    def regular_vertices(sides: int, radius: float):
        return [
            (radius * math.cos(2 * math.pi * i / sides),
             radius * math.sin(2 * math.pi * i / sides))
            for i in range(sides)
        ]

    unit_inner = regular_vertices(nsi, 1.0)
    unit_container = regular_vertices(nsc, 1.0)

    def transform(vertices, cx, cy, a, s):
        sa = math.sin(a)
        ca = math.cos(a)
        out = []
        for (vx, vy) in vertices:
            x = cx + (vx * ca - vy * sa) * s
            y = cy + (vx * sa + vy * ca) * s
            out.append((x, y))
        return out

    # Build container polygon
    container = transform(unit_container, 0.0, 0.0, 0.0, solution["S"])
    # Build inner polygons
    inner_polys = []
    for i in range(N):
        x = values[i * 3]
        y = values[i * 3 + 1]
        a = values[i * 3 + 2]
        poly = transform(unit_inner, x, y, a, 1.0)
        inner_polys.append(poly)

    # Use matplotlib
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()

    # Plot container (closed: append first vertex at end)
    container_closed = container + [container[0]]
    cx = [v[0] for v in container_closed]
    cy = [v[1] for v in container_closed]
    ax.plot(cx, cy, color="#000000", linewidth=0.5)

    # Plot inner polygons (closed)
    for poly in inner_polys:
        poly_closed = poly + [poly[0]]
        px = [v[0] for v in poly_closed]
        py = [v[1] for v in poly_closed]
        ax.fill(px, py, "#CCCCCC", edgecolor="black", linewidth=0.5)

    ax.set_aspect("equal")
    plt.title(f"Side length: {final_metric}")
    ax.axis("off")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    plt.savefig(out_path, dpi=120)
    plt.close(fig)


def main():
    if len(sys.argv) < 3:
        print("Usage: render_solution.py <solution.json> <output.png>", file=sys.stderr)
        sys.exit(1)
    sol_path = sys.argv[1]
    out_path = sys.argv[2]
    sol = load_solution(sol_path)
    render(sol, out_path)


if __name__ == "__main__":
    main()