from __future__ import annotations

import json
import subprocess
import time
import sys
import os
from typing import Any, Dict, List, Optional, Tuple, Set, Union

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# This is the canonical pure-code, no-LLM autonomous research loop.
#
# Usage:
#   python scripts/autoresearch/run_autoresearch_loop.py
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

from src.shape_packing.packing_config import (
    LOOP_SLEEP_BETWEEN_RUNS as SLEEP_BETWEEN_RUNS,
    LOOP_MAX_CONSECUTIVE_FAILURES as MAX_CONSECUTIVE_FAILURES,
    LOOP_BASE_BACKOFF as BASE_BACKOFF,
    LOOP_MAX_BACKOFF as MAX_BACKOFF,
    RESULTS_DIR,
    RESULTS_TSV_PATH,
)

FORCE_DIVERSE = False



class DummyArgs:
    pass

_GLOBAL_HISTORY = None

def get_state():
    from src.shape_packing.cli import handle_suggest
    args = DummyArgs()
    args.min_n = None
    args.max_n = None
    args.equal_n = None
    args.include_inner = None
    args.exclude_inner = None
    args.include_container = None
    args.exclude_container = None
    args.min_inner_sides = None
    args.max_inner_sides = None
    args.min_container_sides = None
    args.max_container_sides = None
    args.exclude_problems = None

    if os.path.exists("filter.json"):
        try:
            with open("filter.json", "r") as f:
                filters = json.load(f)
            args.min_n = filters.get("min_n")
            args.max_n = filters.get("max_n")
            args.equal_n = filters.get("equal_n")
            args.include_inner = filters.get("include_inner")
            args.exclude_inner = filters.get("exclude_inner")
            args.include_container = filters.get("include_container")
            args.exclude_container = filters.get("exclude_container")
            args.min_inner_sides = filters.get("min_inner_sides")
            args.max_inner_sides = filters.get("max_inner_sides")
            args.min_container_sides = filters.get("min_container_sides")
            args.max_container_sides = filters.get("max_container_sides")
        except Exception:
            pass

    try:
        return handle_suggest(args, history_cache=_GLOBAL_HISTORY, direct_call=True)
    except Exception as e:
        print(f"[Loop] suggest failed (runtime error): {e}")
        return None


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
    global _GLOBAL_HISTORY
    print(f"[Loop] Starting infinite search loop.")
    from src.shape_packing.agent_loop import load_history
    global _GLOBAL_HISTORY
    _GLOBAL_HISTORY = load_history(RESULTS_TSV_PATH)
    print(f"[Loop] Mode: {'Radical/Diverse' if FORCE_DIVERSE else 'Incremental/Exploitative'}")

    bin_candidates = [
        os.path.join("packer_rs", "target", "release", "packer_rs"),
        os.path.join("packer_rs", "target", "release", "packer_rs.exe"),
        os.path.join("packer_rs", "target", "release", "libpacker_rs.so"),
        os.path.join("packer_rs", "target", "release", "packer_rs.so"),
        os.path.join("packer_rs", "target", "release", "packer_rs.pyd"),
        os.path.join("packer_rs", "target", "release", "packer_rs.dll"),
    ]
    has_compiled = any(os.path.exists(p) for p in bin_candidates)

    if has_compiled:
        print("[Loop] Compiled Rust solver binary / library found. Skipping recompilation.")
    else:
        print("[Loop] Compiling Rust solver once before starting...")
        try:
            env = os.environ.copy()
            subprocess.run(
                ["cargo", "build", "--release"],
                cwd="packer_rs",
                check=True,
                stdout=subprocess.DEVNULL,
                env=env,
            )
            print("[Loop] Rust solver compiled successfully.")
        except Exception as e:
            print(f"[Loop] Note: cargo build returned {e}. Continuing assuming binary exists...")

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

        from src.shape_packing.cli import handle_run
        args = DummyArgs()
        args.problem = problem
        args.attempts = attempts
        args.init_script = None
        args.no_commit = True
        args.json_out = False
        args.no_png = True
        args.no_build = True

        try:
            res = handle_run(args, history_cache=_GLOBAL_HISTORY, direct_call=True)
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

        if not res.get("success") and res.get("returncode") != 42:
            consecutive_failures += 1
            sleep = min(MAX_BACKOFF, BASE_BACKOFF * (2 ** (min(consecutive_failures - 1, 4))))
            print(f"[Loop] Solver failed (exit {res.get('returncode')}, failure {consecutive_failures}). Backing off {sleep}s...")
            time.sleep(sleep)
        else:
            # We must manually log here if success since no_commit is True
            # (Or actually, cli.py does NOT log if no_commit is True!)
            if res.get("success"):
                score = res.get("score")
                from src.shape_packing.agent_loop import log_result, ExperimentResult
                log_result(_GLOBAL_HISTORY, problem, score, 0.0, "Auto run attempts=" + str(attempts), commit="auto")
                if _GLOBAL_HISTORY is not None:
                    _GLOBAL_HISTORY.append(ExperimentResult(problem=problem, score=score, status="keep", description="", seconds=0.0, commit="auto", memory_gb=0.0))
            consecutive_failures = 0
            results_since_commit += 1
            if results_since_commit >= 10:
                print(f"[Loop] Batch committing {results_since_commit} runs...")
                subprocess.run(["git", "add", RESULTS_TSV_PATH, RESULTS_DIR])
                subprocess.run(["git", "commit", "-m", f"auto: batch update of {results_since_commit} runs"])
                results_since_commit = 0
                
            print(f"[Loop] Execution complete. Sleeping {SLEEP_BETWEEN_RUNS}s...")
            time.sleep(SLEEP_BETWEEN_RUNS)


if __name__ == "__main__":
    run_loop()
