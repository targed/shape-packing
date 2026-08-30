"""
Packing autoresearch experiment runner (Mode 2).

Used in the LLM-assisted interactive research loop:
- An AI agent (Cline/Cursor/etc) or a human follows program.md.
- This script is the experiment harness: run it after each code change.
- It:
  - Enforces a time budget.
  - Calls the solver (Rust or Python).
  - Prints score and timing for the agent to analyze.

Usage:
    uv run train.py                     # use CURRENT_PROBLEM
    uv run train.py --auto-select       # pick next target from PACKING_REFERENCE
    uv run train.py --list-targets      # list candidate targets (no run)
"""

import argparse
import csv
import re
import subprocess
import sys
import time
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
src_path = os.path.join(repo_root, "src")
for p in [repo_root, src_path]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ProblemModule: single source of truth for problem names, tokens, and validation.
from shape_packing.problems import parse_problem, shape_token_to_sides

# ---------------------------------------------------------------------------
# CONFIG: edit this section to choose/switch problems
# ---------------------------------------------------------------------------

CURRENT_PROBLEM = "11_6_in_6"

# If "auto" is used, --auto-select will pick a target from PACKING_REFERENCE.
AUTO_MODE = False

TIME_BUDGET = 300

SOLVER_BACKEND = "rust"

PACKER_SCRIPT = os.path.join(os.path.dirname(__file__), "polygon_packer.py")

from shape_packing.packing_config import (
    RUST_BINARY as PACKER_RS_BIN,
    RUST_TOLERANCE,
    RUST_DEFAULT_TIME_LIMIT as RUST_TIME_LIMIT,
    RESULTS_DIR,
)

EXTRA_PACKER_ARGS = [
    "--time_limit", "300",
    "--output_format", "png",
    "--attempts", "2000",
]

RUST_ATTEMPTS = 500000  # train.py uses a higher value; keep local override

# Supported tokens for auto-select (only regular polygons + circle for now).
SUPPORTED_TOKENS = {"3", "4", "5", "6", "8", "CIRCLE"}

# ---------------------------------------------------------------------------
# END CONFIG
# ---------------------------------------------------------------------------

# Re-export for backward compatibility where needed
from shape_packing.problems import Problem


# ---------------------------------------------------------------------------
# Verification helpers (integrated from scripts/verify_packing_reference)
# ---------------------------------------------------------------------------

VERIFY_SCRIPT = "scripts/verify_packing_reference.py"


def run_verification_for(problem: str) -> Tuple[bool, str]:
    """
    Runs verify_packing_reference.py focused on a single problem.
    Returns (ok, message):
      - ok=False if contradicted by HTML.
      - ok=True otherwise (including not_found / no info).
    """
    try:
        res = subprocess.run(
            [sys.executable, VERIFY_SCRIPT, "--problem", problem],
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (res.stdout or "") + (res.stderr or "")
        mismatch = [l for l in out.splitlines() if l.startswith("MISMATCH:")]
        if mismatch:
            return False, "CONTRADICTED by HTML: " + "; ".join(mismatch[:5])
        not_found = [l for l in out.splitlines() if l.startswith("NOT_FOUND:")]
        if not_found:
            return True, "OK (NOT_FOUND in HTML; candidate to improve): " + "; ".join(not_found[:3])
        return True, "OK (no contradiction; no issues)"
    except Exception as e:
        # On error, allow run but warn.
        return True, f"WARNING: verification failed; continuing: {e}"


def load_packing_reference() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    path = "PACKING_REFERENCE.tsv"
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)
    return rows


def problem_from_tsv_row(row: Dict[str, str]) -> Optional[str]:
    pf = (row.get("problem_family") or "").strip()
    n = (row.get("n") or "").strip()
    bv = (row.get("best_value") or "").strip()
    if not pf or not n or not bv:
        return None
    return f"{n}_{pf}"


def is_supported_problem_family(pf: str) -> bool:
    parts = pf.split("_in_")
    if len(parts) != 2:
        return False
    inner, container = parts
    return (inner in SUPPORTED_TOKENS) and (container in SUPPORTED_TOKENS)


def select_auto_target() -> Tuple[str, str]:
    """
    Auto-select a target from PACKING_REFERENCE.tsv:
    - Exclude proved_optimal.
    - Exclude unsupported shape families.
    - Prioritize best_known entries that are NOT_FOUND in HTML.
    """
    rows = load_packing_reference()
    if not rows:
        raise RuntimeError("No rows in PACKING_REFERENCE.tsv")

    candidates: List[Tuple[str, str, int]] = []
    not_found_set: set = set()

    # First pass: detect NOT_FOUND via verification script in batch.
    batch_out = ""
    try:
        r = subprocess.run(
            [sys.executable, VERIFY_SCRIPT],
            capture_output=True,
            text=True,
            timeout=60,
        )
        batch_out = (r.stdout or "") + (r.stderr or "")
    except Exception:
        batch_out = ""

    for line in batch_out.splitlines():
        if line.startswith("NOT_FOUND:"):
            m = re.search(r"NOT_FOUND:\s+(\S+)\s+n=(\d+)", line)
            if m:
                not_found_set.add((m.group(1), m.group(2)))

    for row in rows:
        status = (row.get("status") or "").strip()
        if status == "proved_optimal":
            continue

        problem = problem_from_tsv_row(row)
        if not problem:
            continue

        pf = (row.get("problem_family") or "").strip()
        if not is_supported_problem_family(pf):
            continue

        n = (row.get("n") or "").strip()

        is_nf = (pf, n) in not_found_set
        priority = 0
        reason = "best_known in reference"
        if is_nf:
            priority = 1
            reason = "NOT_FOUND in HTML (priority target)"

        candidates.append((problem, reason, priority))

    if not candidates:
        raise RuntimeError("No candidate targets in PACKING_REFERENCE.tsv")

    # Sort by priority descending; tie-break by problem name.
    candidates.sort(key=lambda x: (-x[2], x[0]))

    # Filter out problems that already have at least one result directory.
    existing_problems = set()
    res_dir = RESULTS_DIR if os.path.isdir(RESULTS_DIR) else ("data/results" if os.path.isdir("data/results") else "results")
    if os.path.isdir(res_dir):
        for d in os.listdir(res_dir):
            if d.startswith("_") or d.startswith("."):
                continue
            if "/" in d:
                continue
            existing_problems.add(d)

    for problem, reason, _ in candidates:
        if problem not in existing_problems:
            return problem, reason

    # Fallback: allow reusing if all have results; caller can deduplicate later.
    problem, reason, _ = candidates[0]
    return problem, reason


def list_auto_targets() -> Tuple[List[str], List[str]]:
    """
    List candidate targets from PACKING_REFERENCE.tsv, same logic as select_auto_target.
    Returns (targets, reasons) sorted by priority.
    """
    rows = load_packing_reference()
    if not rows:
        raise RuntimeError("No rows in PACKING_REFERENCE.tsv")

    candidates: List[Tuple[str, str, int]] = []
    not_found_set: set = set()

    # First pass: detect NOT_FOUND via verification script in batch.
    batch_out = ""
    try:
        r = subprocess.run(
            [sys.executable, VERIFY_SCRIPT],
            capture_output=True,
            text=True,
            timeout=60,
        )
        batch_out = (r.stdout or "") + (r.stderr or "")
    except Exception:
        batch_out = ""

    for line in batch_out.splitlines():
        if line.startswith("NOT_FOUND:"):
            m = re.search(r"NOT_FOUND:\s+(\S+)\s+n=(\d+)", line)
            if m:
                not_found_set.add((m.group(1), m.group(2)))

    for row in rows:
        status = (row.get("status") or "").strip()
        if status == "proved_optimal":
            continue

        problem = problem_from_tsv_row(row)
        if not problem:
            continue

        pf = (row.get("problem_family") or "").strip()
        if not is_supported_problem_family(pf):
            continue

        n = (row.get("n") or "").strip()

        is_nf = (pf, n) in not_found_set
        priority = 0
        reason = "best_known in reference"
        if is_nf:
            priority = 1
            reason = "NOT_FOUND in HTML (priority target)"

        candidates.append((problem, reason, priority))

    if not candidates:
        raise RuntimeError("No candidate targets in PACKING_REFERENCE.tsv")

    # Sort by priority descending; tie-break by problem name.
    candidates.sort(key=lambda x: (-x[2], x[0]))
    targets = [c[0] for c in candidates]
    reasons = [c[1] for c in candidates]
    return targets, reasons


# ---------------------------------------------------------------------------
# END Verification helpers
# ---------------------------------------------------------------------------


def ensure_problem_output_dir(problem: str) -> str:
    base = RESULTS_DIR
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
    run_id = os.path.basename(out_dir)

    use_rust = (SOLVER_BACKEND == "rust")

    inner_sides = shape_token_to_sides(inner)
    container_sides = shape_token_to_sides(container)
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
            "--tolerance", RUST_TOLERANCE,
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

    # Use the central ProblemModule to parse the problem.
    try:
        p = parse_problem(CURRENT_PROBLEM)
    except ValueError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)

    N = p.N
    inner = p.inner_token
    container = p.container_token

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
                os.path.join("scripts", "render_solution.py"),
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

    # Auto-verify the solution if JSON exists
    if use_rust_render and solution_json and os.path.exists(solution_json):
        try:
            verify_cmd = [
                sys.executable,
                os.path.join("scripts", "verify_solution.py"),
                solution_json,
                CURRENT_PROBLEM,
            ]
            vres = subprocess.run(verify_cmd, timeout=30, check=False, capture_output=True, text=True)
            for vline in vres.stdout.strip().splitlines():
                print(f"verify:           {vline}")
        except Exception as e:
            print(f"verify exception: {e}")

    print(f"score:            {score if score is not None else 0.0}")
    print(f"training_seconds: {training_seconds:.1f}")
    print(f"total_seconds:    {total_seconds:.1f}")
    print(f"problem:          {CURRENT_PROBLEM}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Packing autoresearch experiment runner")
    parser.add_argument("--auto-select", action="store_true", help="Auto-select a target from PACKING_REFERENCE.tsv")
    parser.add_argument("--list-targets", action="store_true", help="List candidate targets (no run)")
    args = parser.parse_args()

    if args.list_targets:
        targets, reasons = list_auto_targets()
        for t, r in zip(targets, reasons):
            print(f"{t}\t{r}")
        sys.exit(0)

    if args.auto_select:
        problem, reason = select_auto_target()
        print(f"[auto-select] chosen problem: {problem}  reason: {reason}")
        CURRENT_PROBLEM = problem
        AUTO_MODE = True
    else:
        problem = CURRENT_PROBLEM

    # Pre-run verification: refuse if contradicted.
    ok, msg = run_verification_for(problem)
    print(f"[verify] problem={problem}  {msg}")
    if not ok:
        print(f"[verify] FATAL: problem {problem} contradicted by reference HTML. Aborting.", file=sys.stderr)
        sys.exit(1)

    run_experiment()