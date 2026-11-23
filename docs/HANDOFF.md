# Distributed Shape Packing: Project Handoff & Architecture Guide

## 1. Executive Summary

This project transforms a local mathematical optimization engine for 2D shape packing into **Distributed Shape Packing**, a community compute platform inspired by projects like GIMPS (Great Internet Mersenne Prime Search) and Folding@home.

### The Problem Domain
- **Shape Packing**: Continuous 2D geometric optimization searching for the densest non-overlapping arrangement of $N$ polygons or polyforms (triangles, squares, pentagons, hexagons, octagons, circles, dominoes, tans, and L-trominoes) inside a container polygon of minimal scale $S$.
- **Mathematical Asymmetry**: Discovering a denser packing requires thousands of random restarts and continuous gradient descent steps (Adam untangling followed by L-BFGS polish in Rust). In contrast, verifying a candidate packing requires only $O(N^2)$ pairwise Separating Axis Theorem (SAT) collision checks and container containment tests, which executes in **under 1 millisecond**.

### Why Distributed Compute?
Continuous shape packing is non-convex stochastic global optimization. Multiple machines searching the same problem with different random seeds explore different basins of attraction. However, without coordination, compute is wasted on already-solved or trivial problems. The coordinator acts as a resource allocator, directing volunteer machines toward high-leverage, loose packings.

---

## 2. System Architecture & File Map

The codebase is organized as a unified monorepo:

```
shape-packing/
├── src/shape_packing/
│   ├── server/                     # Coordinator Backend
│   │   ├── __init__.py             # Server package interface
│   │   ├── database.py             # SQLite WAL database layer & catalog seeder
│   │   ├── scheduler.py            # Multi-armed bandit work allocator & lease manager
│   │   └── app.py                  # FastAPI coordinator REST service & SAT verifier
│   ├── client/                     # Volunteer Client
│   │   ├── __init__.py             # Lazy attribute export package interface
│   │   └── native_worker.py        # Native worker daemon (idle priority, stdlib urllib)
│   ├── geometry.py                 # Polygon geometry, SAT routines, containment checks
│   ├── optimization.py             # Python basinhopping optimizer fallback
│   ├── solver_interface.py         # PyO3 in-process bridge and CLI binary fallback
│   └── solution_tools.py           # Verification engine (verify_solution) & rendering
├── packer_rs/                      # High-Performance Rust Solver
│   ├── src/lib.rs                  # PyO3 bindings module
│   ├── src/solver.rs               # Rayon parallel attempts, Adam untangling, L-BFGS
│   └── Cargo.toml                  # Rust dependencies and release profiles
├── data/
│   ├── packingVerification/        # 2,249 benchmark problems across 80 shape families
│   └── distributed.db              # SQLite database (generated on seed)
├── docs/
│   ├── 08_distributed_system.md    # User guide & operations manual
│   └── superpowers/
│       ├── specs/                  # Architecture specifications
│       └── plans/                  # Implementation plans
└── tests/                          # 221 passing unit, concurrency, and fleet tests
```

---

## 3. What We Have Done and Why

### 1. Feasibility Analysis & Architecture Decision
- Evaluated centralized coordination vs. blockchain/Web3.
- **Why blockchain was rejected**: Shape-packing solutions are scalar mathematical truths ($3.01 < 3.05$). Verification is trivial and objective; Byzantine fault tolerance and consensus tokens introduce friction (wallets, gas, node syncing) that discourages non-technical volunteers.
- **Why centralized REST + SQLite WAL was chosen**: Zero-friction client participation, sub-millisecond in-process verification, and high concurrent write performance without external database dependencies.

### 2. Coordinator Database Layer (`server/database.py`)
- SQLite Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) and immediate transaction isolation (`BEGIN IMMEDIATE`).
- Stores problems, solution history, registered workers, and active leases.
- Implemented `seed_problems_from_verification()` to ingest the full 2,249 benchmark library from `data/packingVerification/*.json`.

### 3. Multi-Armed Bandit Scheduler (`server/scheduler.py`)
- Allocates problems based on a 90% priority exploitation (high void space / low packing density $\rho$, close to record bounds) and 10% exploration policy.
- Strictly excludes all `proved_optimal` problems from assignment queues.
- Automatically reclaims expired leases (default 300s timeout) and accumulates non-record search attempts via heartbeats.

### 4. Coordinator REST API & In-Process Verifier (`server/app.py`)
- FastAPI endpoints for registration, work leasing, solution submission, heartbeats, statistics, and leaderboards.
- Candidate submissions bypass client trust: coordinates are validated against $3N$ floats and passed directly to `verify_solution()`.
- Invalid geometry, polygon collisions, or boundary penetrations are rejected with HTTP 400. Valid improvements atomically update records and credit the volunteer.

### 5. Native Worker Daemon (`client/native_worker.py`)
- Engineered with **zero external networking dependencies** using Python's standard library `urllib`.
- Drops process priority to background idle (`nice 19` on Linux/macOS, `IDLE_PRIORITY_CLASS` on Windows).
- Runs batches via `packer_rs`, filters local candidate improvements, and submits verified coordinates.
- Captures `SIGINT` and `SIGTERM`, flushing pending attempts before cleanly exiting.

---

## 4. Key Challenges Encountered & How They Were Resolved

### Challenge 1: Worker Saturated All CPU Cores (227W, 100°C) Despite `--cores 4`
- **Symptom**: On a 24-thread Intel Core i9-12900K, running with `--cores 4` spiked CPU utilization to 92-100%, drawing 227 Watts and triggering thermal throttling.
- **Root Cause**: The Rust solver (`packer_rs`) uses Rayon for parallel attempt execution. Rayon defaults to `num_cpus` (all 24 threads) unless the `RAYON_NUM_THREADS` environment variable is set. The `--cores` flag was being passed to the server for work-batch sizing, but was never forwarded to Rayon.
- **Resolution**: Updated `WorkerConfig` in `src/shape_packing/client/native_worker.py` to automatically set `os.environ["RAYON_NUM_THREADS"] = str(config.cores)` and `os.environ["OMP_NUM_THREADS"] = str(config.cores)`. When running with `--cores 4`, Rayon now spawns exactly 4 threads, keeping CPU load around 16% on a 24-thread machine.

### Challenge 2: Python `runpy` RuntimeWarning on Module Execution
- **Symptom**: Running `python -m src.shape_packing.client.native_worker` produced `<frozen runpy>:128: RuntimeWarning: 'src.shape_packing.client.native_worker' found in sys.modules...`.
- **Root Cause**: `src/shape_packing/client/__init__.py` was eagerly importing `from .native_worker import ...`. When Python resolved the module via `-m`, it was already present in `sys.modules`.
- **Resolution**: Refactored `src/shape_packing/client/__init__.py` to use lazy attribute resolution via `__getattr__`. The warning is eliminated.

### Challenge 3: Leaderboard Showed Duplicate Rows for the Same Username
- **Symptom**: Re-running the client created separate leaderboard entries for `"targed"` (e.g. 48,000 attempts on row 1, 20,000 attempts on row 2).
- **Root Cause**: Two issues: (1) each client restart generated a fresh random UUID worker ID, and (2) the leaderboard query lacked a `GROUP BY username` clause.
- **Resolution**:
  - Server: Updated `GET /api/v1/leaderboard` to query `GROUP BY username` with `COALESCE(SUM(total_attempts), 0)` and `COALESCE(SUM(records_broken), 0)`.
  - Client: Added local worker ID persistence via `~/.shape_packing_worker.json`. Re-running the worker on the same machine reuses the existing worker ID.

### Challenge 4: `active_workers` Metric Did Not Reflect Real-Time State
- **Symptom**: `GET /api/v1/stats` displayed `"active_workers": 3` even when zero workers were running.
- **Root Cause**: The endpoint was executing `SELECT COUNT(*) FROM workers`, returning total historical worker rows rather than currently connected nodes.
- **Resolution**:
  - Redefined `active_workers` to query nodes active within the last 2 minutes (`WHERE last_seen_at >= datetime('now', '-2 minutes')`).
  - Added a graceful deregister endpoint (`POST /api/v1/workers/deregister`) called automatically on `Ctrl+C` shutdown, dropping active workers to 0 immediately upon exit.
  - Added a separate `"total_workers"` field in the stats response to preserve total historical contributor counts.

---

## 5. How to Run the System

### 1. Compile the Rust Solver
```bash
cd packer_rs
cargo build --release
cd ..
```

### 2. Seed the Coordinator Database
```bash
python -c "
from src.shape_packing.server.database import init_db, seed_problems_from_verification
conn = init_db('shape_packing.db')
n = seed_problems_from_verification(conn, 'data/packingVerification')
print(f'Successfully seeded {n} problems into shape_packing.db')
conn.close()
"
```

### 3. Launch the Coordinator Server
```bash
# Production multi-worker setup
uvicorn src.shape_packing.server.app:app --host 0.0.0.0 --port 8000 --workers 4
```
- Interactive API Swagger UI: `http://localhost:8000/docs`
- Live Leaderboard: `http://localhost:8000/api/v1/leaderboard`
- Network Stats: `http://localhost:8000/api/v1/stats`

### 4. Run Volunteer Workers
On any machine that can reach the server:
```bash
python -m src.shape_packing.client.native_worker --server http://localhost:8000 --username your_handle --cores 4
```

---

## 6. What Remains Left to Do (Future Roadmap)

1. **Browser WebAssembly Worker (`/contribute` page)**:
   - Compile `packer_rs` via `wasm-pack build --target web`.
   - Embed a background Web Worker in the Astro web frontend (`site/`) with a canvas visualizer rendering the live untangling process.
2. **Multi-Source Catalog Ingestors**:
   - Ingest Eckard Specht's Packomania dataset for circle packing in squares, circles, and triangles up to large $N$ ($N \ge 100$).
   - Add procedural problem generation for untested polygon combinations.
3. **Desktop System Tray GUI & Background Service**:
   - Built a lightweight, cross-platform Tkinter + `pystray` + `Pillow` desktop application (`src/shape_packing/client/gui.py`) and background controller (`src/shape_packing/client/controller.py`).
   - Features dynamic CPU core sliders (`RAYON_NUM_THREADS` and `OMP_NUM_THREADS`), active hours scheduling (including midnight-crossing intervals), pause/resume, and snooze controls (30m, 1h, 2h).
   - Zero-elevation user-level autostart manager (`src/shape_packing/client/autostart.py`) supporting Windows Registry (`pythonw.exe`), macOS LaunchAgents, and Linux XDG Autostart with full CLI support (`status`, `enable`, `disable`).
4. **Public Dashboard API Integration**:
   - Wire the Astro frontend to query the coordinator's live `/api/v1/leaderboard` and `/api/v1/stats` endpoints directly.

---

## 7. Verification Evidence & Test Commands

Full test suite passes with zero regressions:

```bash
# 1. Desktop GUI, Controller & Autostart Tests
pytest tests/test_client_controller.py \
       tests/test_client_autostart.py \
       tests/test_client_tray.py \
       tests/test_client_gui.py -v

# 2. Acceptance and Unit Test Suite (177 tests)
pytest tests/test_server_database.py \
       tests/test_server_scheduler.py \
       tests/test_server_api.py \
       tests/test_native_worker.py \
       tests/test_distributed_e2e.py -v

# 2. Concurrency, Race Condition, and Fleet Stress Suite (44 tests)
pytest tests/test_server_database_concurrency.py \
       tests/test_server_scheduler_concurrency.py \
       tests/test_server_api_concurrency.py \
       tests/test_native_worker_concurrency.py \
       tests/test_distributed_fleet_challenge.py -v
```

---

## 8. Suggested Skills for the Next Agent

When picking up the next phase of this project, the incoming agent should invoke:
- **`tdd` / `test-driven-development`**: For maintaining test coverage when implementing the Wasm bridge or new catalog ingestors.
- **`python-performance-optimization`**: When tuning database query performance or WAL checkpoint intervals under large-scale worker fleets.
- **`verification-before-completion`**: To enforce fresh verification evidence before declaring milestones complete.
- **`frontend-design`**: When designing the live contributor interface and canvas visualizer for the web dashboard.
