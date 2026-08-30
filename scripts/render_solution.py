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


def _worker_render(args_tuple: Tuple[str, str, bool, dict]) -> Tuple[str, bool, str]:
    json_path, png_path, overwrite, kwargs = args_tuple
    if not overwrite and os.path.exists(png_path):
        return (json_path, True, "skipped (exists)")
    try:
        render_solution(json_path, out_png=png_path, **kwargs)
        return (json_path, True, "rendered")
    except Exception as e:
        return (json_path, False, str(e))


def render_single(json_path: str, png_path: str, overwrite: bool = True, **kwargs) -> bool:
    if not overwrite and os.path.exists(png_path):
        print(f"[SKIP] {png_path} already exists.")
        return True
    try:
        render_solution(json_path, out_png=png_path, **kwargs)
        print(f"[RENDERED] {json_path} -> {png_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed rendering {json_path}: {e}")
        return False


def render_batch(json_paths: List[str], overwrite: bool = False, jobs: int = 1, **kwargs) -> None:
    tasks: List[Tuple[str, str, bool, dict]] = []
    for j_path in json_paths:
        p = Path(j_path)
        png_path = str(p.parent / "solution.png")
        tasks.append((j_path, png_path, overwrite, kwargs))

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
    default_target = "data/results" if os.path.exists("data/results") else "results"
    parser.add_argument(
        "target",
        nargs="?",
        default=default_target,
        help="Path to a solution.json file or directory (default: data/results)",
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

    # Rendering Customizations
    parser.add_argument(
        "--size-px",
        type=int,
        default=None,
        help="Exact output image width and height in pixels (e.g. 243, 240, 500)",
    )
    parser.add_argument(
        "--width-px",
        type=int,
        default=None,
        help="Exact output image width in pixels",
    )
    parser.add_argument(
        "--height-px",
        type=int,
        default=None,
        help="Exact output image height in pixels",
    )
    parser.add_argument(
        "--crop-mode",
        choices=["tight", "circumradius", "autoscale"],
        default=None,
        help="Bounding crop mode: 'tight' (container edge-to-edge), 'circumradius' ([-S, S]), or 'autoscale'",
    )
    parser.add_argument(
        "--container-lw",
        type=float,
        default=None,
        help="Line thickness/width for container boundary (e.g. 2.0, 1.8)",
    )
    parser.add_argument(
        "--inner-lw",
        type=float,
        default=None,
        help="Line thickness/width for inner shapes (e.g. 1.0, 0.5)",
    )
    parser.add_argument(
        "--pad-px",
        type=float,
        default=None,
        help="Padding in pixels around tight container bounds (e.g. 1.0 for stroke alignment, 0.0 for zero inset)",
    )
    parser.add_argument(
        "--no-align",
        dest="align_container",
        action="store_false",
        help="Disable automatic regular polygon container visual rotation alignment",
    )
    parser.add_argument(
        "--container-color",
        type=str,
        default=None,
        help="Hex/named color for container stroke (e.g. '#000000')",
    )
    parser.add_argument(
        "--container-face-color",
        type=str,
        default=None,
        help="Hex/named color for container fill (e.g. '#FFF3E6', '#FFFFFF')",
    )
    parser.add_argument(
        "--face-color",
        type=str,
        default=None,
        help="Hex/named color for inner shape fill (e.g. '#CCCCCC', '#FED4D1')",
    )
    parser.add_argument(
        "--edge-color",
        type=str,
        default=None,
        help="Hex/named color for inner shape edge (e.g. '#000000')",
    )
    parser.add_argument(
        "--bg-color",
        type=str,
        default=None,
        help="Hex/named background color (e.g. '#FFFFFF')",
    )

    args = parser.parse_args()
    target_path = Path(args.target)

    # Build render options dict from CLI flags (only pass non-None values)
    render_opts = {}
    if args.size_px is not None: render_opts["size_px"] = args.size_px
    if args.width_px is not None: render_opts["width_px"] = args.width_px
    if args.height_px is not None: render_opts["height_px"] = args.height_px
    if args.crop_mode is not None: render_opts["crop_mode"] = args.crop_mode
    if args.container_lw is not None: render_opts["container_lw"] = args.container_lw
    if args.inner_lw is not None: render_opts["inner_lw"] = args.inner_lw
    if args.pad_px is not None: render_opts["pad_px"] = args.pad_px
    if args.align_container is False: render_opts["align_container"] = False
    if args.container_color is not None: render_opts["container_color"] = args.container_color
    if args.container_face_color is not None: render_opts["container_face_color"] = args.container_face_color
    if args.face_color is not None: render_opts["inner_face_color"] = args.face_color
    if args.edge_color is not None: render_opts["inner_edge_color"] = args.edge_color
    if args.bg_color is not None: render_opts["bg_color"] = args.bg_color

    # 1. Single File Mode
    if target_path.is_file():
        out_png = args.output_png or str(target_path.parent / "solution.png")
        render_single(str(target_path), out_png, overwrite=True, **render_opts)

    # 2. Directory / Recursive Mode
    elif target_path.is_dir():
        if args.recursive or not args.output_png:
            found_jsons = [str(p) for p in target_path.glob("**/solution.json")]
            if not found_jsons:
                print(f"No solution.json files found in {target_path}")
                sys.exit(0)
            render_batch(found_jsons, overwrite=args.overwrite, jobs=args.jobs, **render_opts)
        else:
            print(f"Error: {target_path} is a directory. Use --recursive / -r to process directories.")
            sys.exit(1)
    else:
        print(f"Error: Target path '{args.target}' does not exist.")
        sys.exit(1)


if __name__ == "__main__":
    main()