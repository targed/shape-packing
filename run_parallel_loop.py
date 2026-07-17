import json
import subprocess
import time
import sys
import os
import signal
import concurrent.futures

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

def worker_task(problem, attempts):
    print(f"[{problem}] Starting ({attempts} attempts)")
    cmd = [sys.executable, "-m", "src.shape_packing.cli", "search", "--problem", problem, "--attempts", str(attempts)]
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
    except Exception as e:
        print(f"[{problem}] Worker error: {e}")
        return problem, False
        
    if res.returncode == 0:
        print(f"[{problem}] Success!")
        return problem, True
    elif res.returncode == 42:
        print(f"[{problem}] Solution valid but NOT an improvement.")
        return problem, False
    else:
        print(f"[{problem}] Search failed/completed without new best.")
        return problem, False

def run_loop():
    global _SHUTDOWN
    # Trap termination signals
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)
    
    num_cores = get_available_cores()
    print(f"[Main] Starting parallel loop on {num_cores} cores.")
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_cores) as executor:
        # Loop will be fleshed out in next tasks
        pass

if __name__ == "__main__":
    run_loop()