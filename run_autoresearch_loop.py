import json
import subprocess
import time
import sys
import os

def get_state():
    cmd = [sys.executable, "-m", "src.shape_packing.cli", "suggest"]
    
    if os.path.exists("filter.json"):
        try:
            with open("filter.json", "r") as f:
                filters = json.load(f)
            
            # Map json keys to CLI args
            mapping = {
                "min_n": "--min-n", "max_n": "--max-n", "equal_n": "--equal-n",
                "include_inner": "--include-inner", "exclude_inner": "--exclude-inner",
                "include_container": "--include-container", "exclude_container": "--exclude-container",
                "min_inner_sides": "--min-inner-sides", "max_inner_sides": "--max-inner-sides",
                "min_container_sides": "--min-container-sides", "max_container_sides": "--max-container-sides"
            }
            
            for k, v in filters.items():
                if k in mapping and v is not None:
                    cmd.extend([mapping[k], str(v)])
        except Exception as e:
            print(f"[Loop] Error reading filter.json: {e}")
            
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        print(f"[Loop] Error parsing CLI output: {res.stdout}")
        return None

def run_loop():
    print("[Loop] Starting autonomous shape-packing search loop...")
    while True:
        state = get_state()
        if not state or "problem" not in state:
            print("[Loop] Suggestion engine returned invalid state. Waiting 5s...")
            time.sleep(5)
            continue
            
        problem = state["problem"]
        best_score = state.get("best_score", "None")
        print(f"\n[Loop] Target problem: {problem} (best score so far: {best_score})")
        
        # Determine attempts. For harder problems (N >= 8), use 10,000 attempts. Otherwise, 5,000.
        try:
            parts = problem.split("_")
            N = int(parts[0])
        except Exception:
            N = 5
            
        attempts = 10000 if N >= 8 else 5000
        print(f"[Loop] Running solver on {problem} with {attempts} attempts...")
        
        cmd = [sys.executable, "-m", "src.shape_packing.cli", "run", "--problem", problem, "--attempts", str(attempts)]
        
        # Run the command synchronously so that each problem gets executed fully before moving on
        subprocess.run(cmd)
        
        print("[Loop] Execution complete. Sleeping 2 seconds before next query...")
        time.sleep(2)

if __name__ == "__main__":
    run_loop()
