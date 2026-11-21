# Milestone 1 Investigation & Implementation Findings: Coordinator Database Layer & Problem Ingestion

## 1. Observation

### Authoritative Specifications & Architecture
- **Original Request Requirements**:
  - `ORIGINAL_REQUEST.md:15-16`: "R1. Coordinator Database Layer and Problem Ingestion. Implement an SQLite database in WAL mode storing problems, solution records, registered workers, and active work leases in `src/shape_packing/server/database.py`. Support seeding baseline benchmark problems from `data/packingVerification/*.json`."
  - `ORIGINAL_REQUEST.md:33`: Acceptance Criteria requires: "SQLite database initializes tables with WAL mode enabled."
  - `ORIGINAL_REQUEST.md:40`: "Verified improvements atomically update the best record and increment the finder's leaderboard score."
- **Project Structure & Interfaces**:
  - `orchestrator_1/PROJECT.md:42-46`: Defined interface contracts for `database.py`:
    - `init_db(db_path: str) -> sqlite3.Connection`
    - `register_worker(conn: sqlite3.Connection, username: str, client_type: str, worker_id: Optional[str]) -> Dict[str, Any]`
    - `get_problem(conn: sqlite3.Connection, problem_id: str) -> Optional[Dict[str, Any]]`
    - `update_solution_record(conn: sqlite3.Connection, problem_id: str, worker_id: str, username: str, metric_s: float, coordinates: List[float]) -> bool`
  - `orchestrator_1/PROJECT.md:63-74`: Code layout assigns server code to `src/shape_packing/server/` and tests to `tests/test_server_database.py`.

### Existing Codebase Conventions
- `src/shape_packing/packing_config.py:46-48`:
  ```python
  VERIFY_SAT_TOLERANCE: float = 1e-5
  VERIFY_METRIC_TOLERANCE: float = 1e-6
  RECORD_MIN_IMPROVEMENT: float = 1e-5
  ```
  The minimum improvement delta for a new solution record is consistently defined across the codebase as `RECORD_MIN_IMPROVEMENT = 1e-5` ($10^{-5}$).
- `src/shape_packing/problems.py:1-24`: Modules begin with `from __future__ import annotations`, structured docstrings, typing imports, and use dataclasses and standard naming conventions.
- `tests/conftest.py:14-15`: Adds `ROOT / "src"` to `sys.path`. Both `shape_packing.*` and `src.shape_packing.*` are resolvable.

### Empirical Testing Observations
1. **SQLite WAL Persistence & PRAGMA Scope**:
   - Running `PRAGMA journal_mode = WAL;` sets the journal mode to `wal` and stores this state in the database file header. Opening subsequent connections to the same file retains `journal_mode = wal`.
   - Running `PRAGMA synchronous = NORMAL;` and `PRAGMA foreign_keys = ON;` applies only to the *current connection*. On a newly opened connection to the same DB file:
     - `PRAGMA journal_mode` remains `wal`.
     - `PRAGMA synchronous` reverts to `2` (`FULL`).
     - `PRAGMA foreign_keys` reverts to `0` (`OFF`).
   - Private in-memory databases (`sqlite3.connect(':memory:')`) do not support WAL mode; SQLite returns `'memory'` as journal mode. File databases on disk (including temporary files in `/tmp` or `pytest tmp_path`) support WAL mode.
2. **Transaction Concurrency & `BEGIN IMMEDIATE`**:
   - Python 3.14 `sqlite3` default transaction behavior: executing DML (`INSERT`, `UPDATE`, `DELETE`) without an explicit commit activates an implicit transaction (`conn.in_transaction == True`).
   - If `BEGIN IMMEDIATE` is called while `conn.in_transaction == True`, SQLite raises `sqlite3.OperationalError: cannot start a transaction within a transaction`.
   - When separate connections in different threads execute `BEGIN IMMEDIATE`:
     - Thread 1 executes `BEGIN IMMEDIATE` and acquires SQLite's RESERVED lock.
     - Thread 2 executing `BEGIN IMMEDIATE` blocks in the SQLite busy handler until Thread 1 commits or the timeout (`timeout=30.0`) expires.
     - Upon Thread 1 committing, Thread 2 acquires the write lock and its subsequent `SELECT best_s FROM problems WHERE id = ?` reads the committed write from Thread 1.
     - When simulated with two concurrent threads submitting improvement candidates (Alice submitting `2.8449112`, Bob submitting `2.8449100`), Alice's update succeeded (`True`), best_s became `2.8449112`, and Bob's update observed Alice's new record, failed the `metric_s < current_best - 1e-5` condition, rolled back, and returned `False`.
3. **Thread Safety with Shared Connection**:
   - Sharing a single `sqlite3.Connection` object across multiple concurrent threads simultaneously triggers `sqlite3.InterfaceError: bad parameter or other API misuse`. Separate connections per thread/request avoid this completely.
4. **Benchmark Problem Catalog Seeding**:
   - `data/packingVerification/*.json` contains 82 JSON files with 2,269 problem definitions representing 2,249 unique problem IDs.
   - Parsing all 82 files and inserting into SQLite via `INSERT INTO problems ... ON CONFLICT(id) DO UPDATE SET reference_s=excluded.reference_s` executed in **9 milliseconds** (0.009s) on Linux.
   - Status distribution in benchmark files: 1,739 `best_known`, 49 `proved_optimal`, 461 `trivial`.

---

## 2. Logic Chain

1. **WAL & Pragmas** (from Observations 1.1, 1.2, 1.3):
   - SQLite WAL mode is mandated by Requirement R1 to support concurrent reads while writes are occurring.
   - Because `PRAGMA synchronous = NORMAL;` and `PRAGMA foreign_keys = ON;` are per-connection settings, `init_db` should execute these pragmas upon creating the database connection.
   - For file databases, `conn.executescript(SCHEMA)` safely executes the PRAGMAs along with the `CREATE TABLE` and `CREATE INDEX` statements.
   - If unit tests use `tmp_path` (file database), WAL mode is active and verified. If `:memory:` is used, WAL is ignored by SQLite, so tests checking WAL mode specifically must use a file path (as provided by pytest's `tmp_path`).

2. **Concurrency & Atomic Record Updates** (from Observations 1.2, 2.1, 2.2):
   - In distributed computing, multiple workers may solve the same problem concurrently and submit results within milliseconds of each other.
   - If deferred transactions were used, both workers would read the old record, compute an improvement, and attempt to write, causing the second writer to crash with a database locked error or produce a lost update.
   - Using `BEGIN IMMEDIATE` guarantees that the write lock is reserved prior to reading `best_s`.
   - The second transaction blocks until the first completes, then reads the updated `best_s`.
   - Because smaller container scale $s$ indicates a superior packing, an improvement requires $s_{\text{submitted}} < s_{\text{best}} - 10^{-5}$ (`RECORD_MIN_IMPROVEMENT`).
   - If the condition is met, the transaction:
     a. Sets `is_current_record = 0` on prior solution records for that `problem_id`.
     b. Inserts the new solution record with `is_current_record = 1` and `coordinates_json = json.dumps(coordinates)`.
     c. Updates `problems.best_s = metric_s` and `updated_at = CURRENT_TIMESTAMP`.
     d. Increments `workers.records_broken = records_broken + 1` and updates `last_seen_at = CURRENT_TIMESTAMP`.
     e. Commits and returns `True`.
   - If the condition is not met (or if the problem does not exist), the transaction rolls back (`conn.rollback()`) and returns `False`.
   - To guard against transaction leaks in unexpected failures, a `try...except` block wraps the operation and issues `conn.rollback()` before re-raising.

3. **Schema Design & Query Optimization** (from Observations 1.1, 1.2, 3.1):
   - Downstream milestones M2 (`scheduler.py`) and M3 (`app.py`) query:
     - `problems` filtered by `status != 'proved_optimal'` and ordered by `total_attempts ASC, density_rank DESC`.
     - `active_leases` joined on `problems.id = active_leases.problem_id` and filtered by `expires_at < CURRENT_TIMESTAMP`.
     - `solutions` filtered by `problem_id` and `is_current_record = 1`.
     - `workers` ordered by `records_broken DESC, total_attempts DESC` for leaderboards.
   - Adding secondary indexes (`idx_active_leases_problem`, `idx_active_leases_expires`, `idx_solutions_problem_record`, `idx_problems_status_attempts`, `idx_workers_records_broken`) optimizes these queries from $O(N)$ table scans to $O(\log N)$ index lookups with negligible write overhead.

4. **Seeding Idempotency** (from Observations 1.1, 4.1, 4.2):
   - `seed_problems_from_verification` must be safe to call on startup, migration, or test setup without failing on duplicate primary keys.
   - Using `ON CONFLICT(id) DO UPDATE SET reference_s=excluded.reference_s` ensures idempotent re-runs while preserving any live network updates to `best_s` and `total_attempts`.

---

## 3. Caveats

1. **System Python Environment vs Virtualenv**:
   - The system Python 3.14 has `sqlite3`, `pytest`, `json`, and `numpy` installed, but does not currently have `fastapi` or `scipy` installed.
   - Milestone 1 uses exclusively Python standard library modules (`sqlite3`, `json`, `uuid`, `glob`, `os`, `typing`) and `pytest`. It has zero external dependencies and runs cleanly in the current environment.
   - Subsequent milestones (M3 REST API) will require `fastapi` and `uvicorn`.
2. **In-Memory Database Limitations**:
   - SQLite does not support WAL mode for private `:memory:` databases (`PRAGMA journal_mode` returns `memory`). Tests verifying `assert journal_mode == "wal"` must use a file database path (such as `tmp_path / "test.db"`).
3. **Thread Safety with Connections**:
   - A single `sqlite3.Connection` cannot be shared concurrently across multiple active Python threads. Each thread (or request worker) must instantiate its own connection or use a connection factory.

---

## 4. Conclusion & Concrete Implementation Recommendations

The implementation for Milestone 1 requires:
1. `src/shape_packing/server/__init__.py`: Package marker.
2. `src/shape_packing/server/database.py`: Implementation of `SCHEMA`, `init_db`, `register_worker`, `get_problem`, `update_solution_record`, and `seed_problems_from_verification`.
3. `tests/test_server_database.py`: Comprehensive test suite covering schema creation, WAL mode, worker registration, atomic record updates, concurrency serialization, idempotency of seeding, and error handling.

### Recommended Implementation Details

#### A. Database Schema (`SCHEMA`)
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

CREATE INDEX IF NOT EXISTS idx_active_leases_problem ON active_leases(problem_id);
CREATE INDEX IF NOT EXISTS idx_active_leases_expires ON active_leases(expires_at);
CREATE INDEX IF NOT EXISTS idx_solutions_problem_record ON solutions(problem_id, is_current_record);
CREATE INDEX IF NOT EXISTS idx_problems_status_attempts ON problems(status, total_attempts, density_rank);
CREATE INDEX IF NOT EXISTS idx_workers_records_broken ON workers(records_broken DESC, total_attempts DESC);
```

#### B. Function Signatures & Implementation Contract

```python
# src/shape_packing/server/database.py
from __future__ import annotations
import glob
import json
import os
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

RECORD_MIN_IMPROVEMENT: float = 1e-5

def init_db(db_path: str = "data/distributed.db") -> sqlite3.Connection:
    """Initialize SQLite database with WAL mode and schema."""
    dirname = os.path.dirname(os.path.abspath(db_path))
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn

def register_worker(
    conn: sqlite3.Connection,
    username: str,
    client_type: str = "native",
    worker_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Register or update a worker handle and return their registration details."""
    w_id = worker_id or str(uuid.uuid4())
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO workers (id, username, client_type, last_seen_at) "
        "VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(id) DO UPDATE SET last_seen_at=CURRENT_TIMESTAMP, username=excluded.username",
        (w_id, username, client_type),
    )
    conn.commit()
    return {"worker_id": w_id, "username": username, "client_type": client_type}

def get_problem(conn: sqlite3.Connection, problem_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve problem record by canonical problem identifier."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM problems WHERE id = ?", (problem_id,))
    row = cursor.fetchone()
    if not row:
        return None
    return dict(row)

def update_solution_record(
    conn: sqlite3.Connection,
    problem_id: str,
    worker_id: str,
    username: str,
    metric_s: float,
    coordinates: List[float],
) -> bool:
    """
    Atomically verify improvement and commit new solution record.
    Requires metric_s < current_best - 1e-5 to qualify as a record break.
    """
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        cursor.execute("SELECT best_s, status FROM problems WHERE id = ?", (problem_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False

        current_best = row["best_s"]
        if current_best is not None and metric_s >= (current_best - RECORD_MIN_IMPROVEMENT):
            conn.rollback()
            return False

        cursor.execute(
            "UPDATE solutions SET is_current_record = 0 WHERE problem_id = ?",
            (problem_id,),
        )
        cursor.execute(
            "INSERT INTO solutions (problem_id, metric_s, worker_username, worker_id, coordinates_json, is_current_record) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (problem_id, metric_s, username, worker_id, json.dumps(coordinates)),
        )
        cursor.execute(
            "UPDATE problems SET best_s = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (metric_s, problem_id),
        )
        cursor.execute(
            "UPDATE workers SET records_broken = records_broken + 1, last_seen_at = CURRENT_TIMESTAMP WHERE id = ?",
            (worker_id,),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise

def seed_problems_from_verification(
    conn: sqlite3.Connection, verification_dir: str = "data/packingVerification"
) -> int:
    """Seed baseline problems from JSON benchmark records idempotently."""
    inserted = 0
    pattern = os.path.join(verification_dir, "*.json")
    cursor = conn.cursor()
    for file_path in glob.glob(pattern):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                continue
            for item in data:
                our_problem = item.get("our_problem")
                if not our_problem:
                    continue
                inner = str(item.get("inner_shape", "")).upper()
                container = str(item.get("container_shape", "")).upper()
                n = int(item.get("N", 0))
                best_val = item.get("best_value")
                status = item.get("status", "best_known")
                note = item.get("source_note", "")

                cursor.execute(
                    "INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, source_attribution) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET reference_s=excluded.reference_s",
                    (our_problem, inner, container, n, best_val, best_val, status, note),
                )
                inserted += 1
        except Exception:
            continue
    conn.commit()
    return inserted
```

---

## 5. Verification Method

Once implemented, the implementation can be independently verified with the following steps:

1. **Run Database Unit Tests**:
   ```bash
   pytest tests/test_server_database.py -v
   ```
   *Expected*: All tests pass with 0 failures.

2. **Verify WAL Mode Activation**:
   Inspect the journal mode on a physical temporary file:
   ```python
   cursor.execute("PRAGMA journal_mode")
   assert cursor.fetchone()[0] == "wal"
   ```

3. **Verify Concurrency & Record Break Race Condition**:
   Run two simultaneous threads attempting to update the same problem:
   - Worker 1 with $s = 3.4$
   - Worker 2 with $s = 3.399995$ (less than $10^{-5}$ improvement over 3.4)
   *Expected*: Worker 1 succeeds (`True`), Worker 2 fails (`False`), `problems.best_s == 3.4`, and `workers.records_broken == 1` for Worker 1 and `0` for Worker 2.

4. **Verify Seeding Count & Idempotency**:
   ```python
   count = seed_problems_from_verification(conn, "data/packingVerification")
   assert count > 2000
   count2 = seed_problems_from_verification(conn, "data/packingVerification")
   cursor.execute("SELECT COUNT(*) FROM problems")
   unique_count = cursor.fetchone()[0]
   assert unique_count == 2249
   ```

5. **Invalidation Conditions**:
   - If `update_solution_record` does not use `BEGIN IMMEDIATE`, concurrent submissions will fail with `sqlite3.OperationalError: database is locked` on lock upgrade or overwrite records silently.
   - If `seed_problems_from_verification` does not use `ON CONFLICT(id) DO UPDATE`, calling it a second time will crash with `sqlite3.IntegrityError: UNIQUE constraint failed: problems.id`.
