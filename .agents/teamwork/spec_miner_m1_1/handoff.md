# Milestone 1 Specification Report: Coordinator Database Layer & Problem Ingestion

This report provides the authoritative specification, DDL schemas, interface contracts, acceptance criteria, edge cases, and unit test requirements for Milestone 1 (Task 1) of the Distributed Shape Packing project.

---

## Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Database Initialization | `init_db` | Connects to SQLite DB, creates parent directory if needed, enables WAL mode, sets synchronous mode, enables foreign keys, executes DDL schema script, sets `row_factory = sqlite3.Row`. | `db_path: str = "data/distributed.db"` | `sqlite3.Connection` | Handles `:memory:` databases where WAL mode returns `'memory'` without crashing; creates missing parent dirs. | `ORIGINAL_REQUEST.md` §R1, Design Spec §3, Plan Task 1 |
| 2 | Worker Identity & Registration | `register_worker` | Idempotently registers or updates volunteer worker in `workers` table. If `worker_id` is omitted/None, generates UUID4. Updates `last_seen_at` and `username` on conflict. | `conn: sqlite3.Connection`, `username: str`, `client_type: str = "native"`, `worker_id: Optional[str] = None` | `Dict[str, Any]` (`{"worker_id": str, "username": str, "client_type": str}`) | Upsert on existing `worker_id` avoids PK collision; sanitizes inputs via SQL parameter binding. | Design Spec §3, §4.1; Plan Task 1 Step 1 & 3 |
| 3 | Problem Lookup | `get_problem` | Fetches single problem metadata row by canonical `problem_id` as dictionary. | `conn: sqlite3.Connection`, `problem_id: str` | `Optional[Dict[str, Any]]` | Returns `None` if problem does not exist; SQL injection immune via parameterized query. | `PROJECT.md` §Interface Contracts; Plan Task 1 Step 1 & 3 |
| 4 | Atomic Record Update | `update_solution_record` | Evaluates candidate metric against current best known, demotes previous active solutions (`is_current_record = 0`), inserts new solution, updates `problems.best_s`, and increments `workers.records_broken`. | `conn: sqlite3.Connection`, `problem_id: str`, `worker_id: str`, `username: str`, `metric_s: float`, `coordinates: List[float]` | `bool` (`True` if new record committed, `False` if rejected or missing) | Rejects solutions with $\Delta < 10^{-5}$ (`RECORD_MIN_IMPROVEMENT`); executes inside atomic transaction with immediate rollback on rejection. | Design Spec §6; Plan Task 1 Step 1 & 3; `packing_config.py:48` |
| 5 | Benchmark Seeding | `seed_problems_from_verification` | Ingests benchmark problem catalog from `data/packingVerification/*.json` (2,249+ unique problems) into `problems` table. | `conn: sqlite3.Connection`, `verification_dir: str = "data/packingVerification"` | `int` (count of problems inserted/updated) | Tolerates missing directory, corrupt JSON files, and non-list schemas by skipping corrupted records without failing overall execution. | `ORIGINAL_REQUEST.md` §R1, Design Spec §7, Plan Task 1 Step 3 |
| 6 | Database Schema DDL | 4 Core Tables (`problems`, `solutions`, `workers`, `active_leases`) | Relational SQLite schema with primary keys, foreign key constraints, default timestamps, and indexes. | N/A (Embedded SQL DDL string) | Tables and indexes created in database | `CREATE TABLE IF NOT EXISTS` ensures idempotent execution across multiple app/worker instances. | Design Spec §3; Plan Task 1 Step 3 |

---

## Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | `init_db` | `db_path=":memory:"` | SQLite does not support WAL for purely in-memory databases (`PRAGMA journal_mode=WAL` returns `'memory'`). The function must execute successfully without raising exceptions. |
| 2 | `init_db` | `db_path="nested/path/to/db.sqlite"` where directories do not exist | `os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)` must create all missing directories before connection. |
| 3 | `init_db` | Re-opening existing database (idempotency) | `CREATE TABLE IF NOT EXISTS` must not erase or overwrite existing rows in `problems`, `solutions`, `workers`, or `active_leases`. |
| 4 | `register_worker` | `worker_id=None` or omitted | Generates a valid UUID string (e.g. `uuid.uuid4()`) and returns it. |
| 5 | `register_worker` | `worker_id="custom-uuid-1234"` | Reuses client-provided `worker_id` verbatim. |
| 6 | `register_worker` | Calling with existing `worker_id` and different `username` | Executes `ON CONFLICT(id) DO UPDATE SET last_seen_at=CURRENT_TIMESTAMP, username=excluded.username, client_type=excluded.client_type`. No duplicate row created; existing row updated. |
| 7 | `get_problem` | `problem_id="unknown_problem_123"` | Returns `None` cleanly. |
| 8 | `get_problem` | `problem_id="' OR 1=1; --"` (SQL injection attempt) | Parameterized query `WHERE id = ?` treats input as literal string; safely returns `None`. |
| 9 | `update_solution_record` | Target problem does not exist in `problems` table | Transaction is rolled back; returns `False`. |
| 10 | `update_solution_record` | Problem has `best_s = None` (unattempted instance) | Any valid numeric metric is an improvement; updates `best_s = metric_s`, inserts record, increments worker `records_broken`, returns `True`. |
| 11 | `update_solution_record` | `metric_s > current_best` (worse metric) | Rejects: container metric $s$ is minimized. Rollback and returns `False`. |
| 12 | `update_solution_record` | `metric_s == current_best` (identical metric) | Rejects: requires strict improvement by $\ge 10^{-5}$ (`metric_s < current_best - 1e-5`). Rollback and returns `False`. |
| 13 | `update_solution_record` | `metric_s = current_best - 1e-6` (insufficient improvement) | Delta $< 10^{-5}$, violates `RECORD_MIN_IMPROVEMENT`. Rollback and returns `False`. |
| 14 | `update_solution_record` | Multiple consecutive improvements for same problem | Only the newest solution has `is_current_record = 1`; previous solutions updated to `is_current_record = 0`. Worker's `records_broken` increments on each successful record. |
| 15 | `update_solution_record` | Active transaction state in `sqlite3` driver | In Python's `sqlite3`, issuing `BEGIN IMMEDIATE` when a deferred transaction is already implicitly opened by the driver raises `sqlite3.OperationalError: cannot start a transaction within a transaction`. The implementation must ensure the connection is clean (e.g. by setting `conn.isolation_level = None` or calling `conn.commit()` / `conn.rollback()` before `BEGIN IMMEDIATE`). |
| 16 | `seed_problems_from_verification` | `verification_dir` directory does not exist or is empty | `glob.glob` returns empty list; returns `0` without error. |
| 17 | `seed_problems_from_verification` | Directory contains corrupted JSON or invalid syntax | `json.load` exception is caught, corrupted file is skipped, and parsing proceeds to the remaining files. |
| 18 | `seed_problems_from_verification` | JSON file contains non-list root object (e.g. dictionary or string) | Type check `isinstance(data, list)` fails; file is skipped without crashing. |
| 19 | `seed_problems_from_verification` | Entry lacks `our_problem` field | Skipped; entries without a canonical problem ID are not inserted. |
| 20 | `seed_problems_from_verification` | Duplicate problem IDs across files (e.g. 20 cross-file duplicates in `data/packingVerification/`) | Handled via `ON CONFLICT(id) DO UPDATE SET reference_s=excluded.reference_s`; updates baseline without overwriting a better `best_s` found during live runs. |

---

## 1. Observation

Direct observations from repository files and live checks:

1. **Original Request (`.agents/teamwork/ORIGINAL_REQUEST.md:15-16`)**:
   > "R1. Coordinator Database Layer and Problem Ingestion: Implement an SQLite database in WAL mode storing problems, solution records, registered workers, and active work leases in `src/shape_packing/server/database.py`. Support seeding baseline benchmark problems from `data/packingVerification/*.json`."

2. **Project Specification (`.agents/teamwork/orchestrator_1/PROJECT.md:42-46`)**:
   > "database.py ↔ scheduler.py:
   > - `init_db(db_path: str) -> sqlite3.Connection`
   > - `register_worker(conn: sqlite3.Connection, username: str, client_type: str, worker_id: Optional[str]) -> Dict[str, Any]`
   > - `get_problem(conn: sqlite3.Connection, problem_id: str) -> Optional[Dict[str, Any]]`
   > - `update_solution_record(conn: sqlite3.Connection, problem_id: str, worker_id: str, username: str, metric_s: float, coordinates: List[float]) -> bool`"

3. **Architecture Specification (`docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md:64-115`)**:
   - SQLite Pragmas:
     `PRAGMA journal_mode = WAL; PRAGMA synchronous = NORMAL;`
   - Exact table structures for:
     `problems`, `solutions`, `workers`, `active_leases`.
   - Metric record breaking condition (§6, line 239):
     "Recalculates $s$ directly from coordinates and verifies that $s_{\text{submitted}} < s_{\text{best}} - 10^{-5}$."

4. **Implementation Plan (`docs/superpowers/plans/2026-11-20-distributed-shape-packing.md:22-303`)**:
   - Defines Task 1 files:
     - `src/shape_packing/server/__init__.py`
     - `src/shape_packing/server/database.py`
     - `tests/test_server_database.py`
   - Defines exact schema and reference implementation for `init_db`, `register_worker`, `get_problem`, `update_solution_record`, `seed_problems_from_verification`.

5. **Existing Verification Catalog (`data/packingVerification/`)**:
   - 82 JSON files containing 2,269 total problem records.
   - 2,249 unique `our_problem` identifiers.
   - Statuses present: `proved_optimal`, `best_known`, `trivial`.
   - All `best_value` fields are valid numeric floats.
   - Shape tokens: Inners include `['3', '4', '6', 'L', 'tan', 'circle', 'domino', ...]`; Containers include `['3', '4', '5', '6', 'circle', 'cir', 'L', 'tan', ...]`. Normalization via `.upper()` handles case differences.

6. **SQLite Driver Transaction Dynamics**:
   - When Python's `sqlite3` connection has default `isolation_level`, executing DML before `cursor.execute("BEGIN IMMEDIATE")` raises `sqlite3.OperationalError: cannot start a transaction within a transaction`.
   - Setting `isolation_level = None` (autocommit mode) or managing transactions cleanly guarantees that explicit `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` works reliably without driver interference.

---

## 2. Logic Chain

1. **WAL Mode and Concurrency Requirements**:
   - Multiple worker clients and scheduler routines will access the database concurrently.
   - `PRAGMA journal_mode = WAL;` allows simultaneous readers and one writer without contention.
   - `PRAGMA synchronous = NORMAL;` prevents disk I/O bottlenecks while maintaining durability.
   - `timeout = 30.0` ensures concurrent transactions wait rather than failing with `sqlite3.OperationalError: database is locked`.

2. **Schema & Integrity**:
   - `problems` needs to store `best_s` (current best metric found by the network) and `reference_s` (historical baseline).
   - `solutions` needs foreign key reference to `problems(id)`, a boolean flag `is_current_record` to distinguish the active record from historical attempts, and `coordinates_json` containing the raw float array.
   - `workers` tracks `records_broken` and `total_attempts` to power the coordinator leaderboard.
   - `active_leases` tracks `expires_at` for work scheduling and lease reclamation.

3. **Improvement Condition (`update_solution_record`)**:
   - In 2D packing, the container size metric $s$ (side length or radius) is minimized.
   - A candidate is an improvement if and only if `metric_s < best_s - 1e-5`.
   - If `best_s is None`, any valid metric becomes the initial best record.
   - The operation must execute under `BEGIN IMMEDIATE` to prevent race conditions where two simultaneous submissions read the same `best_s` and both record improvements.

4. **Problem Ingestion Resilience (`seed_problems_from_verification`)**:
   - `data/packingVerification/*.json` contains 82 files with varying shapes and 20 cross-file duplicate problem entries.
   - Using `ON CONFLICT(id) DO UPDATE SET reference_s=excluded.reference_s` guarantees that re-running seeding updates the reference baseline without wiping out newly improved `best_s` values discovered by network workers.
   - Graceful try/except around file reads ensures corrupt files do not abort the import of remaining files.

---

## 3. Caveats

1. **In-Memory Testing**: In-memory databases (`:memory:`) do not switch to WAL mode (`PRAGMA journal_mode = WAL` returns `'memory'`). Unit tests verifying WAL mode must use a disk-backed database file (e.g. `tmp_path / "test.db"`).
2. **Transaction Isolation in Python `sqlite3`**: Developers must be careful with Python's built-in transaction management. When `BEGIN IMMEDIATE` is invoked manually, setting `conn.isolation_level = None` avoids `OperationalError`.
3. **Geometric Validation Seam**: `update_solution_record` assumes the submitted coordinates and metric have already been verified by the caller (or will be verified by the coordinator REST API in Milestone 3 using `verify_solution`). `database.py` is strictly the storage layer and does not run SAT checks itself.

---

## 4. Conclusion

Milestone 1 is cleanly isolated to `src/shape_packing/server/database.py` and `src/shape_packing/server/__init__.py`, tested via `tests/test_server_database.py`.

### Complete SQL DDL Specification
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS problems (
    id TEXT PRIMARY KEY,
    inner_token TEXT NOT NULL,
    container_token TEXT NOT NULL,
    n INTEGER NOT NULL,
    best_s REAL,
    reference_s REAL,
    status TEXT NOT NULL DEFAULT 'unattempted',
    total_attempts INTEGER DEFAULT 0,
    density_rank REAL DEFAULT 0.0,
    source_attribution TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS solutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id TEXT NOT NULL REFERENCES problems(id),
    metric_s REAL NOT NULL,
    worker_username TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    coordinates_json TEXT NOT NULL,
    is_current_record BOOLEAN DEFAULT 1,
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    client_type TEXT NOT NULL DEFAULT 'native',
    total_attempts INTEGER DEFAULT 0,
    records_broken INTEGER DEFAULT 0,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS active_leases (
    work_id TEXT PRIMARY KEY,
    problem_id TEXT NOT NULL REFERENCES problems(id),
    worker_id TEXT NOT NULL REFERENCES workers(id),
    leased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_problems_status_attempts ON problems(status, total_attempts);
CREATE INDEX IF NOT EXISTS idx_solutions_problem_current ON solutions(problem_id, is_current_record);
CREATE INDEX IF NOT EXISTS idx_active_leases_problem ON active_leases(problem_id);
CREATE INDEX IF NOT EXISTS idx_active_leases_expires ON active_leases(expires_at);
CREATE INDEX IF NOT EXISTS idx_workers_records_attempts ON workers(records_broken DESC, total_attempts DESC);
```

### Complete Interface Signatures
- `init_db(db_path: str = "data/distributed.db") -> sqlite3.Connection`
- `register_worker(conn: sqlite3.Connection, username: str, client_type: str = "native", worker_id: Optional[str] = None) -> Dict[str, Any]`
- `get_problem(conn: sqlite3.Connection, problem_id: str) -> Optional[Dict[str, Any]]`
- `update_solution_record(conn: sqlite3.Connection, problem_id: str, worker_id: str, username: str, metric_s: float, coordinates: List[float]) -> bool`
- `seed_problems_from_verification(conn: sqlite3.Connection, verification_dir: str = "data/packingVerification") -> int`

---

## 5. Verification Method

To verify the Milestone 1 implementation once built:

1. **Run Unit Tests**:
   ```bash
   pytest tests/test_server_database.py -v
   ```
   Must pass with 0 failures.

2. **Verify WAL Mode & Table Creation**:
   ```bash
   python3 -c "
   import sqlite3, os
   from shape_packing.server.database import init_db
   conn = init_db('test_verify.db')
   cursor = conn.cursor()
   cursor.execute('PRAGMA journal_mode')
   mode = cursor.fetchone()[0]
   cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
   tables = {r[0] for r in cursor.fetchall()}
   conn.close()
   for f in ['test_verify.db', 'test_verify.db-wal', 'test_verify.db-shm']:
       if os.path.exists(f): os.remove(f)
   assert mode.lower() == 'wal', f'Expected wal, got {mode}'
   assert {'problems', 'solutions', 'workers', 'active_leases'}.issubset(tables)
   print('Database WAL mode and schema verified.')
   "
   ```

3. **Verify Problem Ingestion**:
   ```bash
   python3 -c "
   import sqlite3, os
   from shape_packing.server.database import init_db, seed_problems_from_verification
   conn = init_db('test_seed.db')
   count = seed_problems_from_verification(conn, 'data/packingVerification')
   print(f'Seeded {count} records.')
   assert count >= 2249, f'Expected at least 2249 records, got {count}'
   conn.close()
   for f in ['test_seed.db', 'test_seed.db-wal', 'test_seed.db-shm']:
       if os.path.exists(f): os.remove(f)
   "
   ```

4. **Invalidation Conditions**:
   - If `update_solution_record` accepts a metric where $\Delta < 10^{-5}$, the specification is violated.
   - If `register_worker` fails when called twice with the same `worker_id`, idempotency is broken.
   - If `init_db` fails when given a path in a directory that does not yet exist, directory initialization is missing.
   - If `seed_problems_from_verification` crashes when encountering an invalid JSON file in the target directory, error isolation is broken.
