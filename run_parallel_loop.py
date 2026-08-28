from __future__ import annotations

import json
import subprocess
import time
import os
import signal
import concurrent.futures
from typing import Any, Dict, List, Optional, Tuple, Set, Union
from src.shape_packing.agent_loop import log_result

from src.shape_packing.packing_config import (
    LOOP_MAX_CONSECUTIVE_FAILURES as MAX_CONSECUTIVE_FAILURES,
    LOOP_BASE_BACKOFF as BASE_BACKOFF,
    LOOP_MAX_BACKOFF as MAX_BACKOFF,
    LOOP_DEFAULT_ATTEMPTS,
    LOOP_HIGH_N_THRESHOLD,
    LOOP_HIGH_N_ATTEMPTS,
    LOOP_STUCK_ATTEMPTS,
    LOOP_STUCK_SWARM_COUNT,
    LOOP_HARD_SWARM_COUNT,
    get_problem_history_stats,
    get_friedman_best_for_problem,
    compute_problem_difficulty_score,
    compute_adaptive_attempts,
)

# Global shutdown flag for graceful exit
_SHUTDOWN = False

def handle_sigterm(signum, frame):
    global _SHUTDOWN
    print(f"\n[Main] Caught signal {signum}. Initiating graceful shutdown...")
    _SHUTDOWN = True

def get_available_cores():
    # Attempt to read SLURM environment variable
    slurm_cpus = os.environ.get("SLURM_CPUS_ON_NODE")
    if slurm_cpus:
        try:
            return int(slurm_cpus)
        except ValueError:
            pass
    # Fallback to os.cpu_count()
    return os.cpu_count() or 4

class DummyArgs:
    pass

_GLOBAL_HISTORY = None

def init_worker(history):
    global _GLOBAL_HISTORY
    _GLOBAL_HISTORY = history

def get_state(in_flight=None):
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

    if in_flight:
        args.exclude_problems = ",".join(in_flight)

    try:
        return handle_suggest(args, history_cache=_GLOBAL_HISTORY, direct_call=True)
    except Exception as e:
        print(f"[Main] suggest failed (runtime error): {e}")
        return None

def analyze_difficulty(problem_state):
    """
    Returns (attempts, swarm_count) based on difficulty and history.
    Uses adaptive scaling instead of fixed bins.
    """
    problem = problem_state.get("problem", "")
    status = problem_state.get("status", "normal")

    # Gather history-based stats
    stats = get_problem_history_stats(problem)
    friedman_best = get_friedman_best_for_problem(problem)

    # Compute difficulty [0,1] from history, N, and gap to Friedman
    difficulty = compute_problem_difficulty_score(
        problem,
        stats,
        friedman_best
    )

    # Adaptive attempt count
    attempts = compute_adaptive_attempts(
        difficulty=difficulty,
        status=status
    )

    # Swarm count: scale up for harder or stuck problems
    swarm_count = 1
    if status in ("stuck", "hard"):
        swarm_count = LOOP_STUCK_SWARM_COUNT
    elif difficulty >= 0.8:
        swarm_count = LOOP_HARD_SWARM_COUNT

    # Logging (concise, visible in loop output)
    print(
        f"[diff] {problem}: "
        f"diff={difficulty:.2f} "
        f"hist={stats['total_runs']} "
        f"fr_best={friedman_best}"
        f" -> attempts={attempts} swarm={swarm_count}"
    )

    return attempts, swarm_count

def worker_task(problem, attempts):
    print(f"[{problem}] Starting ({attempts} attempts)")
    from src.shape_packing.cli import handle_run
    
    args = DummyArgs()
    args.problem = problem
    args.attempts = attempts
    args.init_script = None
    args.no_commit = True
    args.json_out = True
    args.no_png = True
    args.no_build = True

    try:
        res = handle_run(args, history_cache=_GLOBAL_HISTORY, direct_call=True)
        res["problem"] = problem
        if res.get("success"):
            print(f"[{problem}] Success!")
        else:
            if res.get("returncode") == 42:
                print(f"[{problem}] Solution valid but NOT an improvement.")
            else:
                print(f"[{problem}] Search failed: {res.get('error')}")
        return res
    except Exception as e:
        print(f"[{problem}] Worker exception: {e}")
        return {"success": False, "error": str(e), "returncode": 1, "problem": problem}

def process_result(result):
    """Safely process a completed worker result on the main thread."""
    prob = result.get("problem", "unknown")
    if not result.get("success"):
        err = result.get("error", "Unknown error")
        print(f"[Main] Worker failed on {prob}: {str(err)[:200]}")
        return

    try:
        score = result.get("score")
        if score is None:
            print(f"[Main] No score found for {prob}")
            return
            
        print(f"[Main] Worker finished {prob} with score {score}")
        
        # Centralized logging and committing
        from src.shape_packing.agent_loop import ExperimentResult
        global _GLOBAL_HISTORY
        
        log_result(_GLOBAL_HISTORY, prob, score, 0.0, "Parallel run loop", commit="auto")
        
        # Also need to manually append to _GLOBAL_HISTORY so next suggest sees it
        if _GLOBAL_HISTORY is not None:
            _GLOBAL_HISTORY.append(ExperimentResult(
                problem=prob,
                score=score,
                status="keep",  # Approximation, will be checked properly next load
                description="Parallel run loop",
                seconds=0.0,
                commit="auto",
                memory_gb=0.0
            ))
            
    except Exception as e:
        print(f"[Main] Error during log_result on {prob}: {e}")

def run_loop():
    global _SHUTDOWN
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)
    
    num_cores = get_available_cores()
    print(f"[Main] Starting parallel loop on {num_cores} cores.")
    
    print("[Main] Compiling Rust solver once before spawning workers...")
    try:
        subprocess.run(
            ["cargo", "build", "--release"],
            cwd="packer_rs",
            check=True,
            stdout=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"[Main] Failed to compile Rust solver: {e}")
        print("[Main] Continuing anyway, assuming the binary is already compiled...")
    
    in_flight = {} # Map of Future -> problem_name
    results_since_commit = 0
    
    from src.shape_packing.agent_loop import load_history
    global _GLOBAL_HISTORY
    print("[Main] Loading history into memory...")
    _GLOBAL_HISTORY = load_history("results.tsv")
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_cores, initializer=init_worker, initargs=(_GLOBAL_HISTORY,)) as executor:
        while not _SHUTDOWN:
            # Fill the pool
            while len(in_flight) < num_cores and not _SHUTDOWN:
                state = get_state(list(in_flight.values()))
                if not state or "problem" not in state:
                    print("[Main] Failed to get valid state. Backing off 5s.")
                    time.sleep(5)
                    break # Break inner loop, wait for existing futures
                
                attempts, swarm_count = analyze_difficulty(state)
                prob = state["problem"]
                
                for _ in range(swarm_count):
                    if len(in_flight) >= num_cores:
                        break
                    future = executor.submit(worker_task, prob, attempts)
                    in_flight[future] = prob
            
            if _SHUTDOWN:
                break
                
            # Wait for at least one future to complete
            if in_flight:
                done, _ = concurrent.futures.wait(
                    in_flight.keys(), 
                    return_when=concurrent.futures.FIRST_COMPLETED,
                    timeout=5.0
                )
                
                for future in done:
                    prob = in_flight.pop(future)
                    try:
                        result = future.result()
                        process_result(result)
                        if isinstance(result, dict) and result.get("success"):
                            results_since_commit += 1
                            if results_since_commit >= 10:
                                print(f"[Main] Batch committing {results_since_commit} runs...")
                                subprocess.run(["git", "add", "results.tsv", "results/"])
                                subprocess.run(["git", "commit", "-m", f"auto: batch update of {results_since_commit} runs"])
                                results_since_commit = 0
                    except Exception as e:
                        print(f"[Main] Future for {prob} raised exception: {e}")
            else:
                time.sleep(1)
                
        print("[Main] Shutting down. Waiting for pending workers to finish...")
        # Executor context manager will automatically wait for running futures to finish

if __name__ == "__main__":
    run_loop()