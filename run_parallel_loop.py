import json
import subprocess
import time
import sys
import os
import signal
import concurrent.futures
from src.shape_packing.agent_loop import log_result

# Configuration
MAX_CONSECUTIVE_FAILURES = 5
BASE_BACKOFF = 5
MAX_BACKOFF = 120

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

def get_suggest_command(in_flight=None):
    cmd = [sys.executable, "-m", "src.shape_packing.cli", "suggest"]
    
    if os.path.exists("filter.json"):
        try:
            with open("filter.json", "r") as f:
                filters = json.load(f)
            mapping = {
                "min_n": "--min-n", "max_n": "--max-n", "equal_n": "--equal-n",
                "include_inner": "--include-inner", "exclude_inner": "--exclude-inner",
                "include_container": "--include-container", "exclude_container": "--exclude-container",
                "min_inner_sides": "--min-inner-sides", "max_inner_sides": "--max-inner-sides",
                "min_container_sides": "--min-container-sides", "max_container_sides": "--max-container-sides",
            }
            for k, flag in mapping.items():
                v = filters.get(k)
                if v is not None:
                    cmd.extend([flag, str(v)])
        except Exception:
            pass
            
    if in_flight:
        # Pass in-flight problems as a comma-separated list
        cmd.extend(["--exclude-problems", ",".join(in_flight)])
        
    return cmd

def get_state(in_flight=None):
    cmd = get_suggest_command(in_flight)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception as e:
        print(f"[Main] suggest failed (runtime error): {e}")
        return None

    if res.returncode != 0:
        print(f"[Main] suggest failed (exit {res.returncode}):")
        return None

    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        print("[Main] suggest returned invalid JSON.")
        return None

def analyze_difficulty(problem_state):
    """
    Returns (attempts, swarm_count) based on difficulty.
    """
    problem = problem_state.get("problem", "")
    
    # Try to extract N
    try:
        n = int(problem.split("_")[0])
    except Exception:
        n = 5
        
    attempts = 5000
    if n >= 8:
        attempts = 50000  # Harder problems get more attempts
        
    # Heuristic based on state (e.g., if CLI flagged it as 'stuck')
    status = problem_state.get("status", "normal")
    swarm_count = 1
    
    if status == "stuck":
        attempts = 500000
        swarm_count = 20 # Swarm it!
    elif status == "hard":
        attempts = 50000
        swarm_count = 5
        
    return attempts, swarm_count

def worker_task(problem, attempts):
    print(f"[{problem}] Starting ({attempts} attempts)")
    cmd = [
        sys.executable,
        "-m",
        "src.shape_packing.cli",
        "run",
        "--problem",
        problem,
        "--attempts",
        str(attempts),
        "--no-commit",
        "--json-out",
        "--no-png",
    ]
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
    except Exception as e:
        print(f"[{problem}] Worker error: {e}")
        return {
            "problem": problem,
            "success": False,
            "error": str(e),
            "stdout": "",
            "stderr": "",
        }
        
    if res.returncode == 0:
        print(f"[{problem}] Success!")
        return {
            "problem": problem,
            "success": True,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "returncode": res.returncode,
        }
    elif res.returncode == 42:
        print(f"[{problem}] Solution valid but NOT an improvement.")
        return {
            "problem": problem,
            "success": False,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "returncode": res.returncode,
        }
    else:
        print(f"[{problem}] Search failed/completed without new best.")
        return {
            "problem": problem,
            "success": False,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "returncode": res.returncode,
        }

def process_result(result):
    """Safely process a completed worker result on the main thread."""
    if isinstance(result, tuple) and len(result) == 2:
        result = {
            "problem": result[0],
            "success": result[1],
            "stdout": "",
            "stderr": "",
        }

    prob = result.get("problem", "unknown")
    if not result.get("success"):
        err = result.get("error", result.get("stderr", "Unknown error"))
        print(f"[Main] Worker failed on {prob}: {err[:200]}")
        return

    try:
        stdout = result.get("stdout", "")
        data = None
        for line in reversed([line.strip() for line in stdout.splitlines() if line.strip()]):
            try:
                data = json.loads(line)
                break
            except json.JSONDecodeError:
                continue

        if data is None:
            raise json.JSONDecodeError("No JSON payload found in worker output", stdout, 0)

        score = data.get("score", "unknown")
        print(f"[Main] Worker finished {prob} with score {score}")
        # Centralized logging and committing
        log_result(None, prob, score, 0.0, "Parallel run loop", commit="auto")
    except json.JSONDecodeError:
        print(f"[Main] Failed to parse JSON from {prob} output.")
    except Exception as e:
        print(f"[Main] Error during log_result on {prob}: {e}")

def run_loop():
    global _SHUTDOWN
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)
    
    num_cores = get_available_cores()
    print(f"[Main] Starting parallel loop on {num_cores} cores.")
    
    in_flight = {} # Map of Future -> problem_name
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_cores) as executor:
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
                    except Exception as e:
                        print(f"[Main] Future for {prob} raised exception: {e}")
            else:
                time.sleep(1)
                
        print("[Main] Shutting down. Waiting for pending workers to finish...")
        # Executor context manager will automatically wait for running futures to finish

if __name__ == "__main__":
    run_loop()