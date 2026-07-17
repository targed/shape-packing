# Shape Packing Auto-Researcher (Cluster Ready)

This repository contains an autonomous research loop for discovering mathematically dense shape packings. It pairs a fast Rust backend with a Python-based intelligent orchestrator. 

As of July 2026, the orchestrator has been upgraded to safely and efficiently run on high-performance computing clusters (like the Missouri S&T "Mill" supercomputer) utilizing massive single-node multiprocessing.

---

## 🚀 The Cluster Upgrade (July 2026)

### What Changed?
Previously, the orchestrator (`run_autoresearch_loop.py`) ran sequentially. It would ask the recommender for a problem, run the solver, write the files, commit to git, and repeat. 

Running a sequential loop on a 128-core supercomputer node wastes 127 cores. 

We built a new parallel orchestrator (`run_parallel_loop.py`) designed specifically for SLURM-based clusters. 

### How It Works
1. **Node Discovery**: The script reads the `$SLURM_CPUS_ON_NODE` environment variable to determine exactly how many cores it has been allocated.
2. **Process Pool**: It spins up a Python `ProcessPoolExecutor` utilizing every available core.
3. **Smart Dispatching**: The main thread tracks which problems are currently "in-flight". It asks the recommender for a batch of problems, explicitly telling the recommender *not* to suggest problems that are already running on other cores.
4. **Dynamic Scaling & Swarming**:
   * *Normal Problems*: Gets a standard 5,000 attempts on 1 core.
   * *Hard Problems ($N \ge 8$)*: Gets 50,000 attempts.
   * *Stuck Problems*: Gets 500,000 attempts AND is assigned to 20 cores simultaneously ("Swarm mode"). Because the Rust solver uses randomized initialization, throwing 20 concurrent threads at a deep local minimum drastically increases the chances of breaking out.
5. **Thread-Safe I/O**: Worker cores **do not** write to disk. They run the solver entirely in memory/stdout and return a clean JSON payload back to the main thread. The main single thread handles all updates to `PACKING_REFERENCE.json`, TSV files, and `git commit` actions. This perfectly prevents race conditions and corrupted JSON files.

---

## 🛠 How to Use It on the Mill

### 1. Uploading the Code
The Mill requires you to connect using standard tools (like Globus, `scp`, or `rsync`).
1. Connect to the Mill via Globus (Endpoint: "Missouri S&T Mill").
2. Transfer this entire repository directory to your Scratch space (`/share/ceph/scratch/$USER/`) or your Home directory.

### 2. Submitting the Job
We have included a pre-configured SLURM batch file: `mill_runner.sub`.

1. SSH into the Mill login node: `ssh username@mill.mst.edu`
2. Navigate to your uploaded project directory.
3. Submit the batch script to the SLURM scheduler:
   ```bash
   sbatch mill_runner.sub
   ```

**What `mill_runner.sub` does:**
- Requests 1 full node.
- Requests a 2-day execution limit (the max for the `general` partition).
- Loads the necessary Anaconda and GCC modules.
- Executes `python run_parallel_loop.py`.

### 3. Monitoring the Job
You can check the status of your running job:
```bash
squeue -u $USER
```
To watch the live logs as the orchestrator dispatches tasks to the 128 cores:
```bash
tail -f results/mill-<JOB_ID>.out
```

### 4. Retrieving the Results
Because the orchestrator writes the results safely to the disk on the cluster, you simply pull the data back down when the job finishes (or while it's running).
1. Open Globus.
2. Transfer `PACKING_REFERENCE.json` and the `results/` folder back to your local laptop.

---

## 📂 Core Files
- `run_parallel_loop.py`: The new cluster-aware multiprocess orchestrator.
- `mill_runner.sub`: The SLURM job submission script.
- `src/shape_packing/cli.py`: The command-line interface. (Updated with `--no-commit` and `--json-out` flags to support silent worker isolation).
- `packer_rs/`: The compiled Rust solver that actually does the heavy lifting.

---

## Graceful Shutdowns
The Mill enforces hard time limits. If the 2-day limit is reached, SLURM will send a `SIGTERM` signal shortly before killing the job forcefully. `run_parallel_loop.py` traps this signal, stops dispatching new tasks, waits a few seconds for pending disk writes to finish, and exits cleanly so no JSON files are corrupted mid-write.