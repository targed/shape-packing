# Distributed Shape Packing System

This guide explains the architecture, setup, configuration, and execution workflows for the **Distributed Shape Packing** community coordination system.

---

## 1. Overview

The distributed shape packing system coordinates compute across volunteer machines to discover dense 2D packings of regular polygons and polyforms inside geometric containers.

### Key Capabilities
- **Centralized Coordinator**: FastAPI service backed by SQLite in Write-Ahead Logging (WAL) mode.
- **In-Process Geometric SAT Verification**: Every candidate solution is checked in-process via Separating Axis Theorem (SAT) collision detection and container boundary confinement certificates. Invalid solutions or overlapping polygons are rejected with HTTP 400.
- **Multi-Armed Bandit Scheduler**: Balances 90% priority exploitation (targeting low packing density / high void space) with 10% exploration across unattempted families. Automatically excludes proved-optimal configurations.
- **Zero-Dependency Native Worker**: Client daemon written using Python's standard library `urllib` exclusively. Runs unattended at background idle OS priority (`nice 19` / `IDLE_PRIORITY_CLASS`) and integrates with `packer_rs`.

---

## 2. Environment and Prerequisites

### Requirements
- **Python**: Version 3.10 or higher.
- **Rust Toolchain**: `cargo` and `rustc` (required to compile `packer_rs`).
- **Dependencies**:
  - Coordinator Server: `fastapi`, `uvicorn`, `pydantic`.
  - Worker Daemon: Zero external networking dependencies (Python standard library only). Requires `packer_rs` (compiled via `cargo build --release` in `packer_rs/`).

### Python Environment (venv vs System)
You can run directly with system Python or create a dedicated virtual environment:

```bash
# Optional: Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install required dependencies
pip install -r requirements.txt
pip install fastapi uvicorn
```

### Build the Rust Solver
Ensure the native solver extension is compiled in release mode:

```bash
cd packer_rs
cargo build --release
cd ..
```

---

## 3. Running the Coordinator Server

### 1. Initialize and Seed the Database
Seed the SQLite database with the 2,200+ historical benchmarks cataloged in `data/packingVerification/`:

```bash
python -c "
from src.shape_packing.server.database import init_db, seed_problems_from_verification
conn = init_db('shape_packing.db')
count = seed_problems_from_verification(conn, 'data/packingVerification')
print(f'Successfully seeded {count} benchmark problems.')
conn.close()
"
```

### 2. Start the FastAPI Service with Uvicorn

```bash
# Development mode (single worker with auto-reload)
uvicorn src.shape_packing.server.app:app --host 0.0.0.0 --port 8000 --reload

# Production mode (multi-worker)
uvicorn src.shape_packing.server.app:app --host 0.0.0.0 --port 8000 --workers 4
```

The coordinator is now accessible at `http://localhost:8000`. You can explore the interactive OpenAPI documentation at:
- `http://localhost:8000/docs`

---

## 4. Running the Native Worker Daemon

Volunteers run the native worker daemon to request work units, execute optimization batches locally, and report verified improvements.

### Basic Execution

```bash
python -m src.shape_packing.client.native_worker --server http://localhost:8000 --username your_name
```

### Command-Line Options

| Option | Default | Description |
|---|---|---|
| `--server` | `http://localhost:8000` | URL of the central coordinator service |
| `--username` | `anonymous` | Volunteer handle for the community leaderboard |
| `--cores` | System CPU count | Number of CPU cores allocated for optimization |
| `--worker-id` | Auto-generated UUID | Optional persistent worker identifier |
| `--poll-interval`| `5.0` | Sleep time (seconds) when all problem leases are currently taken |
| `--max-cycles` | None (infinite) | Exit after completing a set number of work batches |

### Running at Background Idle Priority
On Linux and macOS, the worker automatically invokes `os.nice(19)` to ensure it yields CPU cycles to foreground user applications. On Windows, it sets `IDLE_PRIORITY_CLASS`.

### Graceful Interruption
Pressing `Ctrl+C` (`SIGINT`) or sending `SIGTERM` triggers an immediate graceful shutdown:
1. The solver halts its active batch.
2. Completed attempts are flushed to the coordinator via `/api/v1/heartbeat`.
3. The process exits cleanly without losing volunteer credits.

---

## 5. REST API Reference (`/api/v1`)

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/workers/register` | `POST` | Register or check in a volunteer worker handle |
| `/api/v1/work` | `GET` | Request an assigned work unit based on bandit priority |
| `/api/v1/solutions` | `POST` | Submit candidate coordinates for in-process SAT verification |
| `/api/v1/heartbeat` | `POST` | Report completed attempts and track progress |
| `/api/v1/leaderboard` | `GET` | Retrieve top contributors ranked by records broken |
| `/api/v1/stats` | `GET` | Cluster statistics (total problems, attempts, active workers) |
| `/api/v1/problems/{id}` | `GET` | Problem metadata and active record coordinates |

---

## 6. Running the Distributed Test Suite

The distributed engine includes unit tests, concurrency suites, and fleet integration tests:

```bash
# Run unit and end-to-end integration tests (177 tests)
pytest tests/test_server_database.py \
       tests/test_server_scheduler.py \
       tests/test_server_api.py \
       tests/test_native_worker.py \
       tests/test_distributed_e2e.py -v

# Run high-concurrency stress and race-condition tests (44 tests)
pytest tests/test_server_database_concurrency.py \
       tests/test_server_scheduler_concurrency.py \
       tests/test_server_api_concurrency.py \
       tests/test_native_worker_concurrency.py \
       tests/test_distributed_fleet_challenge.py -v
```
