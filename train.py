"""
Packing autoresearch experiment runner.
Single purpose: run polygon_packer.py for a chosen problem,
enforce a 5-minute time budget, parse score, print summary.

This file contains:
- A small config section at the top (you can edit this).
- A fixed harness below (do not change unless necessary).

Usage:
    uv run train.py
"""

import re
import subprocess
import sys
import time
import os
from datetime import datetime

# ---------------------------------------------------------------------------
# CONFIG: edit this section to choose/switch problems
# ---------------------------------------------------------------------------

CURRENT_PROBLEM = "6_3_in_5"

TIME_BUDGET = 300

SOLVER_BACKEND = "rust"

PACKER_SCRIPT = "polygon-packer/polygon_packer.py"

PACKER_RS_BIN = "packer_rs/target/release/packer_rs"

EXTRA_PACKER_ARGS = [
    "--time_limit", "300",
    "--output_format", "png",
    "--attempts", "2000",
]

RUST_ATTEMPTS = 400000
RUST_TIME_LIMIT = 290

# ---------------------------------------------------------------------------
# END CONFIG
# ---------------------------------------------------------------------------

CIRCLE_SIDES = 32

SHAPE_TO_SIDES = {
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "8": 8,
    "CIRCLE": CIRCLE_SIDES,
}

SPECIAL_SHAPES = {"TAN", "DOMINO", "L"}


def parse_problem(problem: str):
    m = re.match(r"^(\d+)_(.+)_(in)_(.+)$", problem)
    if not m:
        raise ValueError(f"Invalid problem format: {problem!r}")
    N = int(m.group(1))
    inner = m.group(2)
    container = m.group(4)
    return N, inner, container


def to_sides(token: str) -> int:
    if token in SPECIAL_SHAPES:
        return None
    if token in SHAPE_TO_SIDES:
        return SHAPE_TO_SIDES[token]
    try:
        s = int(token)
        if s >= 3:
            return s
    except ValueError:
        pass
    raise ValueError(f"Cannot map shape token to sides: {token!r}")


def ensure_problem_output_dir(problem: str) -> str:
    base = "results"
    if os.path.exists(base) and not os.path.isdir(base):
        os.remove(base)
    os.makedirs(base, exist_ok=True)
    # Per-problem base directory
    problem_dir = os.path.join(base, problem)
    os.makedirs(problem_dir, exist_ok=True)
    # Per-run subdirectory (unique timestamp)
    run_id = timestamp()
    out_dir = os.path.join(problem_dir, run_id)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_command(N, inner, container):
    out_dir = ensure_problem_output_dir(CURRENT_PROBLEM)

    use_rust = (SOLVER_BACKEND == "rust")

    inner_sides = to_sides(inner)
    container_sides = to_sides(container)
    if use_rust and (inner_sides is None or container_sides is None):
        use_rust = False

    if use_rust:
        # Store artifacts inside the run directory
        solution_json = os.path.join(out_dir, "solution.json")
        png_out = os.path.join(out_dir, "solution.png")

        cmd = [
            PACKER_RS_BIN,
            str(N),
            str(inner_sides),
            str(container_sides),
            "--attempts", str(RUST_ATTEMPTS),
            "--time-limit", str(RUST_TIME_LIMIT),
            "--solution-file", solution_json,
        ]

        return cmd, solution_json, png_out

    args_list = list(EXTRA_PACKER_ARGS)

    try:
        idx_fmt = args_list.index("--output_format")
        args_list[idx_fmt + 1] = "png"
    except (IndexError, ValueError):
        args_list.extend(["--output_format", "png"])

    args_list.extend(["--output_dir", out_dir])
    args_list.extend(["--output_prefix", f"run_{run_id}"])

    cmd = [sys.executable, PACKER_SCRIPT]
    cmd.append(str(N))

    if inner_sides is None:
        cmd.append("0")
    else:
        cmd.append(str(inner_sides))

    if container_sides is None:
        cmd.append("0")
    else:
        cmd.append(str(container_sides))

    if args_list:
        cmd.extend(args_list)

    return cmd


def run_experiment():
    t_start = time.time()

    try:
        N, inner, container = parse_problem(CURRENT_PROBLEM)
    except ValueError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)

    built = build_command(N, inner, container)
    if isinstance(built, tuple):
        use_rust_render = True
        cmd, solution_json, png_out = built
    else:
        use_rust_render = False
        cmd = built
        solution_json = None
        png_out = None

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as e:
        print(f"FATAL: failed to start packer: {e}", file=sys.stderr)
        sys.exit(1)

    full_output = []
    score = None

    while True:
        now = time.time()
        elapsed = now - t_start
        if elapsed > TIME_BUDGET + 10:
            try:
                proc.kill()
            except Exception:
                pass
            break

        try:
            line = proc.stdout.readline()
        except Exception:
            line = ""

        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.05)
            continue

        full_output.append(line)

        m = re.search(r"Final side length:\s*([0-9]+(?:\.[0-9]+)?)", line)
        if m:
            score = float(m.group(1))

        if time.time() - t_start > TIME_BUDGET:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception:
                pass
            time.sleep(0.1)
            try:
                remaining = proc.stdout.read()
                if remaining:
                    full_output.append(remaining)
            except Exception:
                pass
            break

    if score is None:
        for line in full_output:
            m = re.search(r"Final side length:\s*([0-9]+(?:\.[0-9]+)?)", line)
            if m:
                score = float(m.group(1))
                break

    t_end = time.time()
    total_seconds = t_end - t_start
    training_seconds = min(total_seconds, TIME_BUDGET)

    if use_rust_render and solution_json and png_out and os.path.exists(solution_json):
        try:
            render_cmd = [
                sys.executable,
                "render_solution.py",
                solution_json,
                png_out,
            ]
            res = subprocess.run(render_cmd, timeout=30, check=False, capture_output=True)
            if os.path.exists(png_out):
                print(f"image:          {png_out}")
            else:
                print(f"render failed! stdout: {res.stdout.decode()} stderr: {res.stderr.decode()}")
        except Exception as e:
            print(f"render exception: {e}")

    print(f"score:            {score if score is not None else 0.0}")
    print(f"training_seconds: {training_seconds:.1f}")
    print(f"total_seconds:    {total_seconds:.1f}")
    print(f"problem:          {CURRENT_PROBLEM}")


if __name__ == "__main__":
    run_experiment()