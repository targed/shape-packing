#!/usr/bin/env python3
"""
polygon_packer.py

Thin runner script.

All optimization logic is centralized in optimization.py.
This script:
- parses arguments,
- creates a PackingProblem and OptConfig,
- calls optimization,
- prints metric,
- optionally plots using geometry.
"""

import argparse
import os

import numpy as np
import sys
import os

# Allow imports when run from:
# - repo root: "python polygon-packer/polygon_packer.py"
# - inside polygon-packer: "python polygon_packer.py"
_SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
for p in (_REPO_ROOT, _SCRIPT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from geometry import get_shape_geometry, transform_polygon
from optimization import (
    build_objective,
    OptConfig,
    PackingProblem,
    run_all_attempts,
)

os.environ.setdefault("MPLBACKEND", "Agg")


def parse_args():
    arg_parser = argparse.ArgumentParser(
        description="Pack regular polygons into a regular container polygon."
    )
    arg_parser.add_argument(
        "inner_polygons", type=int, help="Number of inner polygons"
    )
    arg_parser.add_argument(
        "inner_sides", type=int, help="Number of sides of the inner polygons"
    )
    arg_parser.add_argument(
        "container_sides",
        type=int,
        help="Number of sides of the container polygon",
    )
    arg_parser.add_argument(
        "--attempts",
        type=int,
        default=1000,
        help="Number of attempts to run",
    )
    arg_parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-8,
        help="Overlap penalty tolerance (default: 1e-8)",
    )
    arg_parser.add_argument(
        "--finalstep",
        type=float,
        default=0.0001,
        help="Minimum step in container size decrease",
    )
    arg_parser.add_argument(
        "--output_format",
        type=str,
        default="none",
        help="Output image format: png, svg, or none (default: none)",
    )
    arg_parser.add_argument(
        "--time_limit",
        type=float,
        default=None,
        help="Hard time limit in seconds (optional)",
    )
    arg_parser.add_argument(
        "--output_dir",
        type=str,
        default=".",
        help="Directory to save output images",
    )
    arg_parser.add_argument(
        "--output_prefix",
        type=str,
        default="",
        help="Prefix for output filenames",
    )
    return arg_parser.parse_args()


def ensure_unique_path(candidate):
    if not os.path.exists(candidate):
        return candidate
    base, ext = os.path.split(candidate)
    name = os.path.splitext(base)[0]
    i = 1
    while os.path.exists(os.path.join(base, f"{name}_({i}){ext}")):
        i += 1
    return os.path.join(base, f"{name}_({i}){ext}")


def main():
    args = parse_args()

    # Build problem and optimization config
    problem = PackingProblem(
        N=args.inner_polygons,
        inner_token=str(args.inner_sides),
        container_token=str(args.container_sides),
    )

    cfg = OptConfig(
        attempts=args.attempts,
        tolerance=args.tolerance,
        final_step=args.finalstep,
        time_limit=args.time_limit,
        n_jobs=-1,
    )

    # Build objective using geometry
    objective, geom = build_objective(problem)

    # Run optimization (all attempts, all optimizer plumbing in optimization.py)
    best_S, best_values = run_all_attempts(problem, objective, geom, cfg)

    # Compute final metric consistent with previous behavior
    N = problem.N
    nsi, unit_vertices, _, _ = get_shape_geometry(str(args.inner_sides))
    nsc, _, _, _ = get_shape_geometry(str(args.container_sides))
    from src.shape_packing.solution_tools import compute_friedman_metric
    final_metric = compute_friedman_metric(best_S, str(args.inner_sides), str(args.container_sides))
    print("Final side length:", final_metric)

    # Optional plotting (thin; uses geometry)
    if args.output_format in ("png", "svg") and best_values is not None:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        container_plot = np.vstack(
            (unit_vertices * best_S, unit_vertices[0] * best_S)
        )

        fig, ax = plt.subplots()
        ax.plot(
            container_plot[:, 0],
            container_plot[:, 1],
            color="#000000",
            linewidth=0.5,
        )

        for i in range(N):
            polygon = transform_polygon(
                unit_vertices,
                best_values[i * 3],
                best_values[i * 3 + 1],
                best_values[i * 3 + 2],
            )
            polygon_plot = np.vstack((polygon, polygon[0]))
            ax.fill(
                polygon_plot[:, 0],
                polygon_plot[:, 1],
                "#CCCCCC",
                edgecolor="black",
                linewidth=0.5,
            )

        ax.set_aspect("equal")
        plt.title(f"Side length: {final_metric}")

        base_name = f"{N}_{nsi}_in_{nsc}"
        if args.output_prefix:
            base_name = f"{args.output_prefix}_{base_name}"

        out_dir = args.output_dir or "."
        os.makedirs(out_dir, exist_ok=True)

        if args.output_format == "png":
            candidate = os.path.join(out_dir, f"{base_name}.png")
            path = ensure_unique_path(candidate)
            plt.savefig(path)
        elif args.output_format == "svg":
            candidate = os.path.join(out_dir, f"{base_name}.svg")
            path = ensure_unique_path(candidate)
            plt.savefig(path)

        plt.close(fig)


if __name__ == "__main__":
    main()
