#!/usr/bin/env python3
"""
Solution Rendering Utility.

Renders solution JSON files into PNG visualizer images.
Supports single-file rendering, batch rendering, and recursive directory scanning.

Usage:
  # Render a single solution file:
  python scripts/render_solution.py results/4_3_in_circle/20260803_201400/solution.json

  # Recursively render all solution JSON files in results/ (skips existing PNGs by default):
  python scripts/render_solution.py results/ --recursive

  # Force re-render / overwrite existing PNG files:
  python scripts/render_solution.py results/ --recursive --overwrite

  # Parallel batch rendering across multi-core CPU:
  python scripts/render_solution.py results/ --recursive --jobs 4
"""

import argparse
import glob
import multiprocessing
import os
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

try:
    from shape_packing.solution_tools import render_solution
except ImportError:
    from src.shape_packing.solution_tools import render_solution


def _worker_render(args_tuple: Tuple[str, str, bool]) -> Tuple[str, bool, str]:
    json_path, png_path, overwrite = args_tuple
    if not overwrite and os.path.exists(png_path):
        return (json_path, True, "skipped (exists)")
    try:
        render_solution(json_path, out_png=png_path)
        return (json_path, True, "rendered")
    except Exception as e:
        return (json_path, False, str(e))


def render_single(json_path: str, png_path: str, overwrite: bool = True) -> bool:
    if not overwrite and os.path.exists(png_path):
        print(f"[SKIP] {png_path} already exists.")
        return True
    try:
        render_solution(json_path, out_png=png_path)
        print(f"[RENDERED] {json_path} -> {png_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed rendering {json_path}: {e}")
        return False


def render_batch(json_paths: List[str], overwrite: bool = False, jobs: int = 1) -> None:
    tasks: List[Tuple[str, str, bool]] = []
    for j_path in json_paths:
        p = Path(j_path)
        png_path = str(p.parent / "solution.png")
        tasks.append((j_path, png_path, overwrite))

    print(f"Found {len(tasks)} solution JSON files to process (jobs={jobs}, overwrite={overwrite})...")

    rendered = 0
    skipped = 0
    failed = 0

    if jobs > 1:
        with multiprocessing.Pool(processes=jobs) as pool:
            for json_path, success, status in pool.imap_unordered(_worker_render, tasks):
                if not success:
                    print(f"[ERROR] {json_path}: {status}")
                    failed += 1
                elif status.startswith("skipped"):
                    skipped += 1
                else:
                    rendered += 1
    else:
        for task in tasks:
            json_path, success, status = _worker_render(task)
            if not success:
                print(f"[ERROR] {json_path}: {status}")
                failed += 1
            elif status.startswith("skipped"):
                skipped += 1
            else:
                rendered += 1

    print(f"\nBatch rendering complete: {rendered} rendered, {skipped} skipped, {failed} failed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render solution JSON files to PNG visualizer images."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="results",
        help="Path to a solution.json file or directory (default: 'results')",
    )
    parser.add_argument(
        "output_png",
        nargs="?",
        default=None,
        help="Output PNG filepath (for single file mode only)",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively scan directory for all solution.json files",
    )
    parser.add_argument(
        "-f",
        "--overwrite",
        action="store_true",
        help="Force overwrite existing solution.png files",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=1,
        help="Number of parallel worker processes (default: 1)",
    )

    args = parser.parse_args()
    target_path = Path(args.target)

    # 1. Single File Mode
    if target_path.is_file():
        out_png = args.output_png or str(target_path.parent / "solution.png")
        render_single(str(target_path), out_png, overwrite=True)

    # 2. Directory / Recursive Mode
    elif target_path.is_dir():
        if args.recursive or not args.output_png:
            found_jsons = [str(p) for p in target_path.glob("**/solution.json")]
            if not found_jsons:
                print(f"No solution.json files found in {target_path}")
                sys.exit(0)
            render_batch(found_jsons, overwrite=args.overwrite, jobs=args.jobs)
        else:
            print(f"Error: {target_path} is a directory. Use --recursive / -r to process directories.")
            sys.exit(1)
    else:
        print(f"Error: Target path '{args.target}' does not exist.")
        sys.exit(1)


if __name__ == "__main__":
    main()