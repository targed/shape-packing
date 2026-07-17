# Mill Cluster Auto-Agent Orchestrator Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a highly constrained, token-efficient autonomous research loop that uses single-node multiprocessing to fully utilize Mill compute nodes (64-128 cores) safely.

**Architecture:** A standalone SLURM batch file `mill_runner.sub` launches `run_parallel_loop.py`. The Python orchestrator discovers available cores, spins up a `ProcessPoolExecutor`, and dispatches jobs dynamically. Workers invoke the Rust CLI without writing to disk, returning JSON output to the main thread, which serializes writes to `PACKING_REFERENCE.json` and git.

**Tech Stack:** Python 3.11 (multiprocessing, concurrent.futures, subprocess), SLURM, Rust (existing backend).

---

### Task 1: Create the SLURM submission script

**Objective:** Create `mill_runner.sub` to request a whole node and launch the new parallel Python loop.

**Files:**
- Create: `mill_runner.sub`

**Step 1: Write implementation**

```bash
#!/bin/bash
#SBATCH --job-name=ShapePackOrchestrator
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --time=2-00:00:00
#SBATCH --mail-type=begin,end,fail
#SBATCH --export=all
#SBATCH --out=results/mill-%j.out

# Load necessary modules (adjust versions based on Mill environment)
module load anaconda/2023.07
module load gcc/12.2.0

# Optional: activate a virtual environment if needed
# source .venv/bin/activate

# Execute the parallel loop
python run_parallel_loop.py
```

**Step 2: Commit**

```bash
git add mill_runner.sub
git commit -m "feat: add SLURM submission script for Mill cluster"
```

---

### Task 2: Create the base parallel orchestrator script

**Objective:** Create `run_parallel_loop.py` that reads SLURM cores and sets up a `ProcessPoolExecutor`.

**Files:**
- Create: `run_parallel_loop.py`

**Step 1: Write implementation**

```python
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
    print(f"\\n[Main] Caught signal {signum}. Initiating graceful shutdown...")
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
```

**Step 2: Commit**

```bash
git add run_parallel_loop.py
git commit -m "feat: setup base parallel orchestrator and signal handling"
```

---

### Task 3: Implement problem suggestion logic with in-flight tracking

**Objective:** Add logic to request batches of problems from the CLI, passing in-flight jobs to prevent duplicate assignments unless explicitly swarming.

**Files:**
- Modify: `run_parallel_loop.py`

**Step 1: Write implementation**

Add the `get_suggest_command` and `get_state` functions, adapting them to handle in-flight problems.

```python
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
```

**Step 2: Commit**

```bash
git add run_parallel_loop.py
git commit -m "feat: add problem suggestion with in-flight tracking"
```

---

### Task 4: Implement worker execution function

**Objective:** Write the `worker_task` function that runs the solver CLI and returns the stdout string without writing to disk.

**Files:**
- Modify: `run_parallel_loop.py`

**Step 1: Write implementation**

```python
def worker_task(problem, attempts):
    """
    Executes the solver via the CLI. 
    Does not perform file I/O to avoid race conditions.
    """
    cmd = [
        sys.executable,
        "-m",
        "src.shape_packing.cli",
        "run",
        "--problem", problem,
        "--attempts", str(attempts),
        "--no-commit",  # Tell CLI not to git commit; main thread handles it
        "--json-out"    # Tell CLI to output pure JSON to stdout
    ]
    
    try:
        # We capture output. We do NOT stream to stdout to prevent garbled console logs from 128 workers.
        res = subprocess.run(cmd, capture_output=True, text=True)
        return {
            "problem": problem,
            "success": res.returncode == 0,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "exit_code": res.returncode
        }
    except Exception as e:
        return {
            "problem": problem,
            "success": False,
            "error": str(e)
        }
```

**Step 2: Commit**

```bash
git add run_parallel_loop.py
git commit -m "feat: add isolated worker task function"
```

---

### Task 5: Implement dynamic effort scaling & swarm heuristics

**Objective:** Define how many attempts to allocate and determine if a problem should be swarmed.

**Files:**
- Modify: `run_parallel_loop.py`

**Step 1: Write implementation**

```python
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
```

**Step 2: Commit**

```bash
git add run_parallel_loop.py
git commit -m "feat: add dynamic effort scaling and swarm logic"
```

---

### Task 6: Implement main dispatcher and result handler loop

**Objective:** Wire up the `ProcessPoolExecutor`, dispatch tasks, handle completed futures, and safely update the master files.

**Files:**
- Modify: `run_parallel_loop.py`

**Step 1: Write implementation**

Replace the `pass` in `run_loop` with the dispatcher logic.

```python
def process_result(result):
    """Safely process a completed worker result on the main thread."""
    prob = result.get("problem", "unknown")
    if not result.get("success"):
        err = result.get("error", result.get("stderr", "Unknown error"))
        print(f"[Main] Worker failed on {prob}: {err[:200]}")
        return

    try:
        # Assume the CLI outputs a specific JSON payload on success when --json-out is passed
        data = json.loads(result["stdout"])
        # TODO: integrate with actual file writing/git committing logic
        # For now, just print success
        score = data.get("score", "unknown")
        print(f"[Main] Worker finished {prob} with score {score}")
    except json.JSONDecodeError:
        print(f"[Main] Failed to parse JSON from {prob} output.")

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
```

**Step 2: Commit**

```bash
git add run_parallel_loop.py
git commit -m "feat: implement main dispatcher and result processing loop"
```

---

### Task 7: Update CLI to support `--no-commit` and `--json-out`

**Objective:** Modify `src/shape_packing/cli.py` to allow workers to run without committing to git or dumping verbose output.

**Files:**
- Modify: `src/shape_packing/cli.py`

*(Note: Since `cli.py` is complex and not fully provided in context, this step involves modifying `setup_run_parser` to accept `--no-commit` and `--json-out`, and wrapping the final `log_result` and `commit_result` calls in checks for those flags. A subagent will need to read `cli.py` to implement this precisely.)*

**Step 1: Subagent Implementation Detail**
- Read `src/shape_packing/cli.py`
- Find where `git commit` is executed and wrap it in `if not args.no_commit:`
- Find where output is printed and if `args.json_out` is true, ensure ONLY valid JSON is printed to stdout.

**Step 2: Commit**
```bash
git add src/shape_packing/cli.py
git commit -m "feat(cli): add --no-commit and --json-out for parallel workers"
```

---

### Task 8: Implement centralized write & git commit in main thread

**Objective:** Fleshing out `process_result` in `run_parallel_loop.py` to actually update `PACKING_REFERENCE.json` safely.

**Files:**
- Modify: `run_parallel_loop.py`

*(Note: The main thread will need to replicate the saving logic previously handled by `cli.py run`. It should take the JSON payload containing the solution coordinates and score, load `PACKING_REFERENCE.json`, compare the score, and if better, overwrite it and run `git commit`.)*

**Step 1: Subagent Implementation Detail**
- Implement safe file reading/writing using `json` module.
- Use `subprocess.run(["git", "commit", "-m", ...])` directly in the main thread.

**Step 2: Commit**
```bash
git add run_parallel_loop.py
git commit -m "feat: implement centralized file writing and git commits"
```