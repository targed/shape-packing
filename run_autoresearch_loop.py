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

SLEEP_BETWEEN_RUNS = 2  # seconds


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
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[Loop] suggest failed (exit {res.returncode}):\n{res.stderr.strip()}")
        return None

    try:
        out = json.loads(res.stdout)
    except json.JSONDecodeError:
        print(f"[Loop] suggest returned invalid JSON:\n{res.stdout.strip()}")
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

    while True:
        state = get_state()
        if not state or "problem" not in state:
            print("[Loop] Suggestion engine returned invalid state. Waiting 5s...")
            time.sleep(5)
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

        # Run the command synchronously; output is streamed to console.
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            print("[Loop] Interrupted (Ctrl+C). Exiting loop.")
            sys.exit(0)

        print("[Loop] Execution complete. Sleeping", SLEEP_BETWEEN_RUNS, "seconds...")
        time.sleep(SLEEP_BETWEEN_RUNS)


if __name__ == "__main__":
    run_loop()
