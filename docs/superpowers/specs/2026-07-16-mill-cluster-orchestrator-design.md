# Mill Cluster Auto-Agent Orchestrator Design

## 1. Goal
Adapt the shape packing autonomous research loop to run on the Missouri S&T "Mill" supercomputer. The system will leverage single-node multiprocessing to fully utilize large compute nodes (64-128 cores) safely and efficiently, without overwhelming the SLURM scheduler or corrupting shared state.

## 2. Architecture & Execution Model
- **Execution Target:** The orchestrator runs entirely on a single Mill compute node via a SLURM batch job (e.g., requesting 1 node, 64-128 cores, 2-day duration limit). 
- **`mill_runner.sub`:** A SLURM submission script that loads required modules (Python, Rust) and starts the orchestrator.
- **`run_parallel_loop.py`:** A new Python orchestrator script replacing `run_autoresearch_loop.py`. 
  - Detects available cores from SLURM environment variables (e.g., `$SLURM_CPUS_ON_NODE`).
  - Spawns a `concurrent.futures.ProcessPoolExecutor` with workers equal to the available cores.
  - The main thread acts as a dispatcher, feeding work to the worker pool.

## 3. Problem Selection & Strategy
- **In-Flight Tracking:** The main thread maintains a list of currently "in-flight" problems. It requests target problems in batches, avoiding assigning the exact same problem to a new core unless explicitly intended (Swarm mode).
- **Dynamic Effort Scaling (Depth):** The `--attempts` argument scales based on difficulty.
  - Normal/Unexplored: Base attempts (e.g., 5,000).
  - Hard: 10x multiplier (50,000).
  - Stuck: 100x multiplier (500,000).
- **Swarm Mode (Breadth):** For extremely stubborn problems, the main thread will explicitly assign the same problem to multiple cores simultaneously (e.g., 10-20 cores). Since the solver relies on randomized initialization/search, concurrent runs vastly increase the likelihood of finding a novel minimum.

## 4. Data Flow & Thread Safety
- **Worker Isolation:** Workers *do not* write to disk. They invoke the Rust CLI solver, capture the JSON output string, and return it to the main thread via the future callback.
- **Centralized I/O:** The single main thread serializes all disk operations. It compares worker results to the best-known scores, updates `PACKING_REFERENCE.json`, saves solution images/JSONs to `results/`, and performs git commits. This completely eliminates race conditions and file corruption.

## 5. Robustness & Lifecycle
- **Fault Tolerance:** If a specific solver run crashes, times out, or OOMs, the main thread catches the `Future` exception, logs the error, and simply dispatches a new task to keep the core utilized. One bad geometry will not crash the node.
- **Graceful Shutdown:** The Mill enforces hard time limits. The main thread will trap SLURM termination signals (e.g., `SIGTERM`, `SIGUSR1`). Upon catching the signal, it will stop dispatching new tasks, cancel pending ones, flush final updates to `PACKING_REFERENCE.json`, and exit cleanly.
- **Result Retrieval:** Results are synchronized by periodically pulling the `PACKING_REFERENCE.json` and `results/` directory from the Mill to the local machine via Globus or `rsync`/`scp`.