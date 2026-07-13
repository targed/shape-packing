import json
import subprocess
import time
import sys
import os

# This is the canonical pure-code, no-LLM autonomous research loop.
#
# Usage:
#   uv run run_autoresearch_loop.py
#
# Behavior:
#   - Runs forever until you stop it (Ctrl+C).
#   - For each iteration:
#       1) Reads filter.json (if present) and maps it to CLI flags.
#       2) Calls: python -m src.shape_packing.cli suggest [flags]
#          to choose the next target problem.
#       3) Calls: python -m src.shape_packing.cli run --problem <X> --attempts <Y>
#          to run the solver, verify, render, log results, and commit.
#       4) Brief sleep, then repeat.
#
# No LLM, no external services. Pure automated search.

SLEEP_BETWEEN_RUNS = 2  # seconds between successful runs
MAX_CONSECUTIVE_FAILURES = 5  # after this many failures, we back off longer
BASE_BACKOFF = 5  # seconds for first backoff
MAX_BACKOFF = 120  # seconds cap


def get_suggest_command():
    # Build the command for suggest including filter.json mappings.
    cmd = [sys.executable, "-m", "src.shape_packing.cli", "suggest"]

    if not os.path.exists("filter.json"):
        return cmd

    try:
        with open("filter.json", "r") as f:
            filters = json.load(f)
    except Exception:
        return cmd

    mapping = {
        "min_n": "--min-n",
        "max_n": "--max-n",
        "equal_n": "--equal-n",
        "include_inner": "--include-inner",
        "exclude_inner": "--exclude-inner",
        "include_container": "--include-container",
        "exclude_container": "--exclude-container",
        "min_inner_sides": "--min-inner-sides",
        "max_inner_sides": "--max-inner-sides",
        "min_container_sides": "--min-container-sides",
        "max_container_sides": "--max-container-sides",
    }

    for k, flag in mapping.items():
        v = filters.get(k)
        if v is not None:
            cmd.extend([flag, str(v)])

    return cmd


def get_state():
    # Ask the suggest command to pick a target problem.
    cmd = get_suggest_command()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        print("[Loop] suggest timed out.")
        return None
    except Exception as e:
        print(f"[Loop] suggest failed (runtime error): {e}")
        return None

    if res.returncode != 0:
        print(f"[Loop] suggest failed (exit {res.returncode}):")
        print(res.stderr.strip()[:1200])
        return None

    try:
        out = json.loads(res.stdout)
    except json.JSONDecodeError:
        print("[Loop] suggest returned invalid JSON.")
        print(res.stdout.strip()[:1200])
        return None

    return out


def choose_attempts(problem):
    # Heuristic: more attempts for harder (larger N) problems.
    try:
        parts = problem.split("_")
        n = int(parts[0])
    except Exception:
        n = 5

    if n >= 8:
        return 10000
    return 5000


def run_loop():
    print("[Loop] Starting pure-code autoresearch loop (no LLM).")
    print("[Loop] Press Ctrl+C to stop.")

    consecutive_failures = 0

    while True:
        try:
            state = get_state()
        except KeyboardInterrupt:
            print("[Loop] Interrupted (Ctrl+C). Exiting loop.")
            sys.exit(0)
        except Exception as e:
            print(f"[Loop] Unexpected error calling suggest: {e}")
            consecutive_failures += 1
            sleep = min(MAX_BACKOFF, BASE_BACKOFF * (2 ** (min(consecutive_failures - 1, 4))))
            print(f"[Loop] Suggest error. Backing off {sleep}s.")
            time.sleep(sleep)
            continue

        if not state or "problem" not in state:
            consecutive_failures += 1
            sleep = min(MAX_BACKOFF, BASE_BACKOFF * (2 ** (min(consecutive_failures - 1, 4))))
            print(f"[Loop] Invalid state from suggest (failure {consecutive_failures}). Backing off {sleep}s...")
            time.sleep(sleep)
            continue

        problem = state["problem"]
        best_score = state.get("best_score", "None")
        print(f"\n[Loop] Target problem: {problem} (best score so far: {best_score})")

        attempts = choose_attempts(problem)
        print(f"[Loop] Running solver on {problem} with {attempts} attempts...")

        cmd = [
            sys.executable,
            "-m",
            "src.shape_packing.cli",
            "run",
            "--problem",
            problem,
            "--attempts",
            str(attempts),
        ]

        try:
            res = subprocess.run(cmd)
        except KeyboardInterrupt:
            print("[Loop] Interrupted (Ctrl+C). Exiting loop.")
            sys.exit(0)
        except Exception as e:
            print(f"[Loop] Runtime error running solver: {e}")
            consecutive_failures += 1
            sleep = min(MAX_BACKOFF, BASE_BACKOFF * (2 ** (min(consecutive_failures - 1, 4))))
            print(f"[Loop] Solver error. Backing off {sleep}s.")
            time.sleep(sleep)
            continue

        if res.returncode != 0:
            consecutive_failures += 1
            sleep = min(MAX_BACKOFF, BASE_BACKOFF * (2 ** (min(consecutive_failures - 1, 4))))
            print(f"[Loop] Solver failed (exit {res.returncode}, failure {consecutive_failures}). Backing off {sleep}s...")
            time.sleep(sleep)
        else:
            consecutive_failures = 0
            print(f"[Loop] Execution complete. Sleeping {SLEEP_BETWEEN_RUNS}s...")
            time.sleep(SLEEP_BETWEEN_RUNS)


if __name__ == "__main__":
    run_loop()
