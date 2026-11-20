# Distributed Shape Packing Architecture and Design Specification

## 1. Overview and Goals

This document specifies the architecture, data models, network protocols, and execution workflows for **Distributed Shape Packing**, a community-coordinated computation platform that distributes continuous geometric shape-packing optimization across volunteer machines.

### Core Objectives
1. **Coordinate Distributed Compute**: Enable technical and non-technical volunteers to contribute CPU time without redundant overlap or local stagnation.
2. **Instant Verification**: Exploit the mathematical asymmetry of shape packing, where discovering a dense configuration requires millions of optimization steps, but verifying it with Separating Axis Theorem (SAT) collision and boundary tests takes under 1 millisecond.
3. **Universal Geometry Catalog**: Expand beyond Erich Friedman's historical tables to act as an open repository for shape-packing records across higher $N$ ($N \le 200+$), arbitrary polyforms, and multi-source benchmarks (Friedman, Packomania, academic literature).
4. **Monorepo Integration**: House the coordinator server, worker clients, and web interfaces within the existing `shape-packing` repository to reuse native Rust solvers and Python geometry routines directly.

---

## 2. System Architecture

The architecture consists of a centralized coordinator service, two worker client implementations, and an open database.

```
                    ┌────────────────────────────────────────┐
                    │          Coordinator Service           │
                    │               (FastAPI)                │
                    │                                        │
                    │  ┌────────────────┐  ┌──────────────┐  │
                    │  │ Work Scheduler │  │ SAT Verifier │  │
                    │  └───────┬────────┘  └──────▲───────┘  │
                    └──────────┼──────────────────┼──────────┘
                               │                  │
               GET /api/v1/work│                  │ POST /api/v1/solutions
                               ▼                  │
                    ┌─────────────────────────────┴──────────┐
                    │             Worker Clients             │
                    │                                        │
                    │  [Native Worker Daemon]                │
                    │  - Multi-threaded Python/Rust runner   │
                    │  - Background idle process priority    │
                    │                                        │
                    │  [Browser WebAssembly Worker]          │
                    │  - In-browser Wasm execution           │
                    │  - Zero-install contribution           │
                    └────────────────────────────────────────┘
```

### Component Roles

1. **Coordinator Service (`server/`)**:
   - Built with FastAPI, running under Uvicorn/Gunicorn.
   - Embeds the existing `src/shape_packing/solution_tools.py` module for in-process geometric validation.
   - Exposes REST endpoints for work leasing, solution verification, heartbeat accounting, and leaderboard reporting.
   - Manages state using SQLite configured in Write-Ahead Logging (WAL) mode.

2. **Native Worker Daemon (`client/native_worker.py`)**:
   - Python-based client that wraps `packer_rs` via PyO3 in-process bindings (or the compiled CLI binary).
   - Automatically detects logical cores, runs at idle priority, executes parallel attempt batches, filters candidate improvements, and communicates with the coordinator.

3. **Browser WebAssembly Client (`site/src/components/WasmWorker.astro`)**:
   - Compiles `packer_rs` to WebAssembly (`wasm32-unknown-unknown`).
   - Runs optimization attempts inside browser Web Workers, letting casual users donate compute simply by keeping a web tab open.

---

## 3. Database Schema

The database is managed via SQLite in WAL mode (`PRAGMA journal_mode = WAL; PRAGMA synchronous = NORMAL;`).

### Tables

```sql
-- Catalog of all packable configurations
CREATE TABLE problems (
    id TEXT PRIMARY KEY,                       -- e.g. "14_TAN_in_circle"
    inner_token TEXT NOT NULL,                 -- e.g. "TAN"
    container_token TEXT NOT NULL,             -- e.g. "CIRCLE"
    n INTEGER NOT NULL,                        -- piece count
    best_s REAL,                               -- best verified metric found by network
    reference_s REAL,                         -- baseline metric (Friedman/Specht/literature)
    status TEXT NOT NULL DEFAULT 'unattempted',-- unattempted | best_known | proved_optimal
    total_attempts INTEGER DEFAULT 0,          -- cumulative attempts reported by all workers
    density_rank REAL DEFAULT 0.0,             -- void space priority score
    source_attribution TEXT,                   -- historical record credit
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Verified solution history and coordinates
CREATE TABLE solutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id TEXT NOT NULL REFERENCES problems(id),
    metric_s REAL NOT NULL,
    worker_username TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    coordinates_json TEXT NOT NULL,            -- serialized [x1, y1, theta1, ...]
    is_current_record BOOLEAN DEFAULT 1,
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Contributor identity and stats
CREATE TABLE workers (
    id TEXT PRIMARY KEY,                       -- client-generated UUID
    username TEXT NOT NULL,                    -- volunteer handle
    client_type TEXT NOT NULL,                 -- "native" or "web"
    total_attempts INTEGER DEFAULT 0,
    records_broken INTEGER DEFAULT 0,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Active work assignment leases
CREATE TABLE active_leases (
    work_id TEXT PRIMARY KEY,
    problem_id TEXT NOT NULL REFERENCES problems(id),
    worker_id TEXT NOT NULL REFERENCES workers(id),
    leased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);
```

---

## 4. REST API Contract (`/api/v1`)

### 1. Register Worker
`POST /api/v1/workers/register`
- **Request Body**:
  ```json
  {
    "username": "targed",
    "client_type": "native",
    "worker_id": "a1b2c3d4-e5f6-7890"
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "worker_id": "a1b2c3d4-e5f6-7890",
    "username": "targed",
    "status": "registered"
  }
  ```

### 2. Request Work Assignment
`GET /api/v1/work?worker_id={worker_id}&cores={cores}`
- **Response** (`200 OK`):
  ```json
  {
    "work_id": "lease_49102",
    "problem": "14_TAN_in_circle",
    "inner_token": "TAN",
    "container_token": "CIRCLE",
    "n": 14,
    "target_s": 2.8451203,
    "recommended_attempts": 4000,
    "timeout_seconds": 300
  }
  ```
- **Error Response** (`204 No Content`): Returned when all eligible problems are completed or leased.

### 3. Submit Solution
`POST /api/v1/solutions`
- **Request Body**:
  ```json
  {
    "work_id": "lease_49102",
    "worker_id": "a1b2c3d4-e5f6-7890",
    "problem": "14_TAN_in_circle",
    "s": 2.8449112,
    "coordinates": [0.12, -0.45, 1.57, 0.33, 0.21, 0.0]
  }
  ```
- **Response (Verified New Record)** (`200 OK`):
  ```json
  {
    "status": "accepted",
    "verified": true,
    "is_new_record": true,
    "metric_s": 2.8449112,
    "previous_best_s": 2.8451203,
    "message": "New world record registered! Rank updated."
  }
  ```
- **Response (Rejected)** (`400 Bad Request`):
  ```json
  {
    "status": "rejected",
    "verified": false,
    "message": "SAT overlap detected between shape 2 and shape 7 (penetration = 0.0021)."
  }
  ```

### 4. Heartbeat and Attempt Logging
`POST /api/v1/heartbeat`
- **Request Body**:
  ```json
  {
    "worker_id": "a1b2c3d4-e5f6-7890",
    "work_id": "lease_49102",
    "attempts_completed": 4000,
    "best_local_s": 2.849102
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "status": "recorded",
    "total_worker_attempts": 124000
  }
  ```

### 5. Public Statistics and Leaderboard
- `GET /api/v1/leaderboard`: Returns top contributors ranked by records broken and total compute attempts.
- `GET /api/v1/problems/{id}`: Returns problem status, coordinate tables, and SVG rendering payload.
- `GET /api/v1/stats`: Returns global summary metrics (total problems cataloged, records beaten, active workers, total attempts).

---

## 5. Work Scheduling and Multi-Armed Bandit Allocation

Because shape packing is continuous stochastic optimization, multiple workers running on the same problem with different random seeds do not duplicate work. The scheduler uses a multi-armed bandit policy to maximize discovery probability across the library:

1. **Exclusion**:
   - Excludes all configurations marked `proved_optimal`.
   - Excludes problems currently leased to active workers unless all candidates are leased.
2. **Exploitation Scoring**:
   - Ranks problems by geometric packing void space:
     $$\rho = \frac{N \cdot A_{\text{inner}}}{A_{\text{container}}(s)}$$
   - Computes closeness to baseline record. Problems where current $s$ is within 1% of the record receive an allocation boost.
3. **Exploration and Stuck Backoff**:
   - If a problem receives more than 50,000 attempts without an improvement, its priority weight decays by 50% for 24 hours.
   - 10% of all assignments are picked uniformly at random from unattempted shape families.

---

## 6. Geometric Verification Pipeline

Candidate submissions are verified in-process using `src/shape_packing/solution_tools.py:verify_solution`:

1. **Dimension Check**: Ensures `len(coordinates) == 3 * N`.
2. **Containment Check**: Reconstructs each polygon and validates that all vertices lie inside the container polygon apothem/boundary with tolerance $\le 10^{-6}$.
3. **Pairwise SAT Collision Check**: Evaluates Separating Axis Theorem between all $N(N-1)/2$ polygon pairs. Max penetration must be $\le 10^{-6}$.
4. **Metric Verification**: Recalculates $s$ directly from coordinates and verifies that $s_{\text{submitted}} < s_{\text{best}} - 10^{-5}$.
5. **Atomic Commit**: If valid, opens an SQLite transaction (`BEGIN IMMEDIATE`), marks previous records as `is_current_record = 0`, inserts the new solution, updates `problems.best_s`, and increments the worker's `records_broken` counter.

---

## 7. Problem Catalog Expansion and Ingestion

The coordinator supports multi-source problem ingestion and procedural scaling:

1. **Friedman Ingestor**: Imports the existing 2,242 problems in `data/packingVerification/*.json`.
2. **Packomania Ingestor**: Scrapes and normalizes circle-in-polygon records from Eckard Specht's dataset.
3. **Procedural Generator**: Dynamically registers unattempted problem instances for arbitrary polygon combinations up to $N = 200$.
4. **Exportable Solution Certificates**: Outputs canonical JSON certificates with exact coordinates, verification tolerances, and finder attribution for publication in OEIS or mathematical journals.

---

## 8. Client Implementations

### Native Worker Daemon (`client/native_worker.py`)
- Python process running at OS idle priority (`nice` or Windows idle).
- Configurable via CLI flags:
  ```bash
  python client/native_worker.py --server http://localhost:8000 --username targed --cores 8
  ```
- Graceful shutdown: captures `SIGINT` / `SIGTERM`, finishes the current batch, flushes completed attempts via `/api/v1/heartbeat`, and exits.

### Browser WebAssembly Runner (`site/src/components/WasmWorker.astro`)
- Compiles `packer_rs` via `wasm-pack build --target web`.
- Runs inside background Web Workers using `wasm-bindgen`.
- Features a live canvas visualizer rendering the current packing and an interactive thread-count slider.

---

## 9. Testing Strategy

1. **Server Unit Tests (`tests/test_server_api.py`)**:
   - Worker registration and lease management using FastAPI `TestClient`.
   - Solution submission verification: valid packings accepted, overlapping/out-of-bounds packings rejected.
   - Atomic race condition tests for concurrent submissions.
2. **Worker Integration Tests (`tests/test_worker_client.py`)**:
   - End-to-end simulated worker cycle verifying assignment retrieval, local optimization, candidate submission, and heartbeat flushing.
3. **High-Concurrency Benchmarks**:
   - Simulated load testing of 100 concurrent workers against SQLite WAL mode to ensure request latency remains under 10ms.
