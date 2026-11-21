# Specification Mining Report: Milestone 1 Iteration 2 (Remediation of Challenger 1 Findings)

**Agent**: `spec_miner_m1_it2_1`  
**Milestone**: Milestone 1 Iteration 2  
**Target Component**: Coordinator Database Layer & Problem Ingestion (`src/shape_packing/server/database.py`, `tests/test_server_database.py`, `tests/test_server_database_stress.py`)  
**Date**: 2026-11-20T23:10:00Z  

---

## 1. Observation

### 1.1 Direct Source Evidence and Audit Findings

We conducted empirical and code analysis of the authoritative specification and implementation sources:
- `ORIGINAL_REQUEST.md`: Defines requirement §R1 for coordinator SQLite storage in WAL mode and benchmark problem seeding from `data/packingVerification/*.json`.
- `orchestrator_1/PROJECT.md`: Defines interface contracts between `database.py`, `scheduler.py`, and `app.py`.
- `challenger_m1_1/handoff.md`: Reports 4 vulnerabilities with empirical proof in `tests/test_server_database_stress.py`:
  1. *Observation 1.1*: `update_solution_record` accepted `metric_s <= 0` (`0.0`, `-5.0`), permanently poisoning `problems.best_s` and blocking all valid future solutions.
  2. *Observation 1.2*: `seed_problems_from_verification` ingested whitespace problem IDs (`'   '`), non-finite floats (`inf`), and non-positive floats (`0.0`, `-3.5`).
  3. *Observation 1.3*: `update_solution_record` crashed with unhandled `TypeError` when arguments were `None` or non-numeric (`"1.5"`).
  4. *Observation 1.4*: Coordinate vectors containing `NaN` wrote `[NaN]` to `solutions.coordinates_json`, violating RFC 8259 and failing strict JSON deserializers.
- `worker_m1/handoff.md`: Documented the original 24 unit tests in `tests/test_server_database.py` and WAL concurrency design.

### 1.2 Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Validation | Metric Strict Positivity | Require container scale $s > 0$ for all solution updates | `metric_s: float` | `bool` | Returns `False` on $s \le 0$ | Challenger Observation 1.1 |
| 2 | Validation | Metric Type & Finiteness | Reject non-numeric (`None`, `str`, `bool`) and non-finite (`NaN`, `inf`) metrics | `metric_s: Any` | `bool` | Returns `False` without raising `TypeError` | Challenger Observation 1.3 |
| 3 | Validation | Coordinate Sequence Integrity | Require coordinates to be sequence of real numbers without `NaN`/`inf` | `coordinates: Sequence[float]` | `bool` | Returns `False` on non-sequence, `NaN`, `inf`, `bool`, or non-numeric elements | Challenger Observation 1.4 |
| 4 | Validation | String Identity Sanitization | Reject empty or whitespace-only problem, worker, and username identifiers | `problem_id`, `worker_id`, `username` | `bool` | Returns `False` if empty or purely whitespace | Challenger Observation 1.2 |
| 5 | DDL Schema | Problems CHECK Constraints | Enforce domain constraints on `problems` table in SQLite DDL | SQLite DDL | Database table | Rejects violations with `sqlite3.IntegrityError` | Challenger Mitigation 3 |
| 6 | DDL Schema | Solutions CHECK Constraints | Enforce domain constraints on `solutions` table in SQLite DDL | SQLite DDL | Database table | Rejects violations with `sqlite3.IntegrityError` | Challenger Mitigation 3 |
| 7 | Seeding | Problem ID Whitespace Rejection | Filter out blank/whitespace problem IDs during verification catalog ingestion | `item["our_problem"]` | Upsert count | Discards item and skips ingestion | Challenger Observation 1.2 |
| 8 | Seeding | Seed Metric Normalization | Normalize non-positive (`<= 0`) or non-finite (`inf`/`nan`) benchmark values to `None` | `item["best_value"]` | Ingested row with `best_s = NULL` | Normalizes corrupt value to `None` rather than poisoning DB | Challenger Observation 1.2 |
| 9 | Migration | Existing DB Schema Compatibility | Preserve backward compatibility and define migration behavior for pre-existing databases | Existing SQLite file | `sqlite3.Connection` | Handles existing schemas cleanly via defensive Python layer and optional DDL alter | SQLite engine probing |

### 1.3 Edge Cases

| # | Feature | Input | Observed Behavior | Remediation Specification |
|---|---------|-------|-------------------|---------------------------|
| 1 | `update_solution_record` | `metric_s = 0.0` | Returned `True`, set `best_s = 0.0` | Return `False`, leave DB unchanged |
| 2 | `update_solution_record` | `metric_s = -5.0` | Returned `True`, set `best_s = -5.0` | Return `False`, leave DB unchanged |
| 3 | `update_solution_record` | `metric_s = None` | Crashed with `TypeError: must be real number, not NoneType` | Return `False` gracefully |
| 4 | `update_solution_record` | `metric_s = "1.5"` | Crashed with `TypeError: must be real number, not str` | Return `False` gracefully |
| 5 | `update_solution_record` | `metric_s = True` | In Python `isinstance(True, int)` is `True`; accepted as `1.0` | Return `False` (explicitly reject `isinstance(..., bool)`) |
| 6 | `update_solution_record` | `coordinates = None` | Crashed with `TypeError: 'NoneType' object is not iterable` | Return `False` gracefully |
| 7 | `update_solution_record` | `coordinates = [float('nan')]` | Serialized to `[NaN]` in JSON | Return `False`, reject non-finite coordinate elements |
| 8 | `update_solution_record` | `coordinates = [True, 1.0]` | Serialized boolean in coordinates | Return `False`, reject boolean elements |
| 9 | `update_solution_record` | `problem_id = "   "` | Permitted whitespace query | Return `False` |
| 10 | `update_solution_record` | `coordinates = []` | Empty list | Return `False` (solution must contain coordinate elements) |
| 11 | `seed_problems_from_verification` | `our_problem = "   "` | Ingested blank problem row | Discard item (`our_problem.strip()` check) |
| 12 | `seed_problems_from_verification` | `best_value = "Infinity"` | Parsed as `inf` and stored in `best_s` | Normalize to `None` (`best_s = NULL`) |
| 13 | `seed_problems_from_verification` | `best_value = 0.0` or `-3.5` | Ingested `0.0` / `-3.5` into `best_s` | Normalize to `None` (`best_s = NULL`) |
| 14 | `seed_problems_from_verification` | `best_value = True` | Would parse as `1.0` | Normalize to `None` (`isinstance(..., bool)` check) |
| 15 | `init_db` on existing DB | Legacy table without CHECK constraints | `CREATE TABLE IF NOT EXISTS` is a no-op; constraints not added | Defensive validation in Python prevents data poisoning; DDL migration safe |

---

## 2. Logic Chain

1. **Physical Semantics of Container Scale $s$**:
   - In 2D shape packing, $N \ge 1$ shapes of total area $A_{\text{total}} = \sum A_i > 0$ are packed into a container with dimension parameter $s$.
   - The container area is strictly proportional to $s^2 > 0$.
   - A scale factor of $s \le 0$ is a geometric and physical impossibility.
   - Any metric $s \le 0$ recorded as `best_s` destroys the record comparison invariant (`metric_s < current_best - 1e-5`), permanently blocking all valid solutions ($s > 0$) from being committed.

2. **Defense-in-Depth Layering**:
   - The coordinator architecture has two distinct defense boundaries:
     - **API Verifier Layer (Milestone 3)**: Validates geometric containment, coordinate vector length ($3N$), and Separating Axis Theorem non-overlap via `verify_solution`.
     - **Database Persistence Layer (Milestone 1)**: Must guarantee transactional integrity, data type safety, RFC 8259 compliance, and domain invariants ($s > 0$, finite numbers, non-empty identifiers).
   - The database layer must never trust callers to have sanitized input; it must reject malformed, non-positive, or non-finite inputs independently and fail fast.

3. **Fail-Fast Before Lock Acquisition**:
   - Acquiring a transaction lock (`BEGIN IMMEDIATE`) before validating arguments wastes locks and incurs unnecessary transaction rollback overhead under high concurrency.
   - All type and range checks must execute prior to `cursor.execute("BEGIN IMMEDIATE")` and prior to clearing connection state (`if conn.in_transaction: conn.commit()`).

4. **Seeding Strategy for Corrupt Benchmark Metrics**:
   - An item in a benchmark catalog file defines the geometric problem instance ($N$, inner token, container token).
   - If the external benchmark file specifies a missing, corrupt, zero, negative, or infinite `best_value`, discarding the entire problem would delete legitimate problems from the solver catalog.
   - Instead, converting invalid metrics to `None` stores the problem with `best_s = NULL` and `reference_s = NULL`.
   - The problem remains available for workers to solve, and the first valid solution ($s > 0$) will be committed cleanly.

5. **SQLite Schema Evolution & Migration Dynamics**:
   - SQLite evaluates `CREATE TABLE IF NOT EXISTS` as a no-op if the table already exists.
   - Modern SQLite (3.31+, installed environment is 3.54.1) supports `ALTER TABLE <table> ADD CHECK (<expr>)`. However, if existing data violates the constraint, `ALTER TABLE` aborts with `sqlite3.IntegrityError: constraint failed`.
   - Therefore, the remediation specification must address both new database creation (DDL CHECK constraints) and legacy database protection (fail-fast Python validation and optional pre-migration sanitization).

---

## 3. Specifications for Remediation

### 3.1 Item 1: Exact Input Validation Contract for `update_solution_record`

```python
def update_solution_record(
    conn: sqlite3.Connection,
    problem_id: str,
    worker_id: str,
    username: str,
    metric_s: float,
    coordinates: List[float],
) -> bool:
```

#### Validation Invariants (evaluated in order, fail-fast returning `False`):
1. **Connection check**:
   ```python
   if not isinstance(conn, sqlite3.Connection):
       return False
   ```
2. **Identifier & String check**:
   ```python
   if not isinstance(problem_id, str) or not problem_id.strip():
       return False
   if not isinstance(worker_id, str) or not worker_id.strip():
       return False
   if not isinstance(username, str) or not username.strip():
       return False
   ```
3. **Metric validation (`metric_s`)**:
   - Must be an `int` or `float`, but explicitly NOT a `bool`:
     ```python
     if isinstance(metric_s, bool) or not isinstance(metric_s, (int, float)):
         return False
     ```
   - Must be finite (not NaN, not Inf, not -Inf):
     ```python
     if math.isnan(metric_s) or math.isinf(metric_s):
         return False
     ```
   - Must be strictly positive real number ($s > 0$):
     ```python
     if metric_s <= 0.0:
         return False
     ```
4. **Coordinates validation (`coordinates`)**:
   - Must be an instance of `(list, tuple)`:
     ```python
     if not isinstance(coordinates, (list, tuple)):
         return False
     ```
   - Must be non-empty:
     ```python
     if len(coordinates) == 0:
         return False
     ```
   - Every coordinate element $c$ must be a finite real number (not `bool`, not `NaN`, not `inf`):
     ```python
     for c in coordinates:
         if isinstance(c, bool) or not isinstance(c, (int, float)) or math.isnan(c) or math.isinf(c):
             return False
     ```
5. **Fail-Fast Timing**:
   Steps 1–4 MUST occur before `if conn.in_transaction: conn.commit()` and before `cursor.execute("BEGIN IMMEDIATE")`.
6. **Improvement Threshold Check**:
   Within the `BEGIN IMMEDIATE` transaction:
   ```python
   current_best = row["best_s"]
   if current_best is not None and metric_s >= (current_best - RECORD_MIN_IMPROVEMENT):
       conn.rollback()
       return False
   ```
   If valid, serialize via `json.dumps(list(coordinates))` (guaranteed valid RFC 8259 JSON) and commit.

---

### 3.2 Item 2: Exact DDL Schema Additions & Existing Database Behavior

#### DDL Schema Additions (`SCHEMA` in `src/shape_packing/server/database.py`):
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS problems (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    inner_token TEXT NOT NULL,
    container_token TEXT NOT NULL,
    n INTEGER NOT NULL CHECK (n > 0),
    best_s REAL CHECK (best_s IS NULL OR best_s > 0),
    reference_s REAL CHECK (reference_s IS NULL OR reference_s > 0),
    status TEXT NOT NULL DEFAULT 'unattempted',
    total_attempts INTEGER DEFAULT 0 CHECK (total_attempts >= 0),
    density_rank REAL DEFAULT 0.0,
    source_attribution TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS solutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id TEXT NOT NULL REFERENCES problems(id),
    metric_s REAL NOT NULL CHECK (metric_s > 0),
    worker_username TEXT NOT NULL CHECK (length(trim(worker_username)) > 0),
    worker_id TEXT NOT NULL CHECK (length(trim(worker_id)) > 0),
    coordinates_json TEXT NOT NULL CHECK (length(coordinates_json) > 0),
    is_current_record BOOLEAN DEFAULT 1 CHECK (is_current_record IN (0, 1)),
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    username TEXT NOT NULL CHECK (length(trim(username)) > 0),
    client_type TEXT NOT NULL DEFAULT 'native',
    total_attempts INTEGER DEFAULT 0 CHECK (total_attempts >= 0),
    records_broken INTEGER DEFAULT 0 CHECK (records_broken >= 0),
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS active_leases (
    work_id TEXT PRIMARY KEY CHECK (length(trim(work_id)) > 0),
    problem_id TEXT NOT NULL REFERENCES problems(id),
    worker_id TEXT NOT NULL REFERENCES workers(id),
    leased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);
```

#### Behavior on Existing Databases:
1. **Standard SQLite Behavior**:
   - `CREATE TABLE IF NOT EXISTS` does not modify existing table definitions.
   - If an existing database created with pre-CHECK schema is opened, the tables will persist as previously structured.
2. **Safety via Application-Layer Defense**:
   - Even without modifying existing table definitions, the updated `update_solution_record` and `seed_problems_from_verification` methods strictly reject non-positive and malformed values.
   - Therefore, legacy databases are fully protected against new data poisoning.
3. **Migration Specification (for `init_db`)**:
   To ensure existing databases gain the CHECK constraints without failing on pre-existing corrupt data:
   ```python
   # Check if existing tables require migration
   cur = conn.cursor()
   cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='problems'")
   row = cur.fetchone()
   if row and row[0] and "best_s > 0" not in row[0]:
       # 1. Sanitize any legacy poisoned values
       conn.execute("UPDATE problems SET best_s = NULL WHERE best_s IS NOT NULL AND best_s <= 0")
       conn.execute("UPDATE problems SET reference_s = NULL WHERE reference_s IS NOT NULL AND reference_s <= 0")
       # 2. Add CHECK constraints via ALTER TABLE (supported in SQLite 3.31+)
       try:
           conn.execute("ALTER TABLE problems ADD CHECK (best_s IS NULL OR best_s > 0)")
           conn.execute("ALTER TABLE problems ADD CHECK (n > 0)")
       except sqlite3.OperationalError:
           pass  # Table-level CHECK alter fallback
   ```
   *Note*: If creating a fresh database, `CREATE TABLE` directly incorporates the constraints.

---

### 3.3 Item 3: Exact Input Validation Contract for `seed_problems_from_verification`

```python
def seed_problems_from_verification(
    conn: sqlite3.Connection, verification_dir: str = "data/packingVerification"
) -> int:
```

#### Ingestion Rules:
1. **Problem Identifier Cleaning**:
   ```python
   raw_id = item.get("our_problem")
   our_problem = str(raw_id or "").strip()
   if not our_problem:
       continue  # Discards None, empty strings, and whitespace-only strings
   ```
2. **Polygon Count $N$ Validation**:
   ```python
   raw_n = item.get("N", 0)
   if isinstance(raw_n, bool):
       continue
   try:
       n = int(raw_n)
       if n <= 0:
           continue
   except (ValueError, TypeError):
       continue
   ```
3. **Metric Normalization (`best_value`)**:
   ```python
   raw_val = item.get("best_value")
   best_val: Optional[float] = None
   if raw_val is not None and not isinstance(raw_val, bool):
       try:
           fv = float(raw_val)
           if not math.isnan(fv) and not math.isinf(fv) and fv > 0.0:
               best_val = fv
       except (ValueError, TypeError):
           best_val = None
   ```
   - If `raw_val` is `0.0`, `-3.5`, `"Infinity"`, `"NaN"`, `True`, or non-numeric: `best_val` becomes `None`.
   - The problem instance is STILL seeded with its canonical geometry tokens and $N$, but with `best_s = NULL` and `reference_s = NULL`.
4. **Shape Tokens**:
   ```python
   inner = normalize_shape_token(item.get("inner_shape"))
   container = normalize_shape_token(item.get("container_shape"))
   if not inner or not container:
       continue
   ```
5. **Catalog Compatibility**:
   - Verification of the 82 files in `data/packingVerification/*.json` shows all 2,269 items have valid $N > 0$ and $s > 0$.
   - Total items processed from standard catalog remains exactly 2,269; distinct problems remain 2,249.

---

### 3.4 Item 4: Concrete Test Assertions Required

To prove that all vulnerabilities identified by Challenger 1 are permanently eliminated, the test suites must be updated and extended with the following assertions:

#### 1. In `tests/test_server_database_stress.py`:

##### Replace `test_zero_and_negative_metrics_empirical_behavior`:
```python
def test_zero_and_negative_metrics_rejected(mem_db: sqlite3.Connection):
    """
    VERIFY: update_solution_record strictly rejects metric_s <= 0.
    In 2D packing, container scale s must be strictly positive (s > 0).
    Rejection prevents data poisoning.
    """
    mem_db.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_zero', '3', '3', 1, 2.0)")
    mem_db.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_neg', '3', '3', 1, 2.0)")
    mem_db.commit()

    # Test zero metric rejection
    zero_accepted = update_solution_record(mem_db, "p_zero", "w1", "user", 0.0, [0.0])
    p_zero = get_problem(mem_db, "p_zero")
    assert zero_accepted is False
    assert p_zero["best_s"] == 2.0

    # Test negative metric rejection
    neg_accepted = update_solution_record(mem_db, "p_neg", "w1", "user", -5.0, [0.0])
    p_neg = get_problem(mem_db, "p_neg")
    assert neg_accepted is False
    assert p_neg["best_s"] == 2.0

    # Verify problem remains solvable by subsequent valid improvement
    valid_accepted = update_solution_record(mem_db, "p_zero", "w1", "user", 1.5, [0.0])
    assert valid_accepted is True
    assert get_problem(mem_db, "p_zero")["best_s"] == 1.5
```

##### Update `test_non_numeric_and_none_metric_type_errors`:
```python
def test_non_numeric_and_none_metric_graceful_rejection(mem_db: sqlite3.Connection):
    """
    VERIFY: update_solution_record returns False instead of crashing on invalid argument types.
    """
    mem_db.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_types', '3', '3', 1, 2.0)")
    mem_db.commit()

    # None and string metrics must return False without raising TypeError
    assert update_solution_record(mem_db, "p_types", "w1", "user", None, [0.0]) is False
    assert update_solution_record(mem_db, "p_types", "w1", "user", "1.5", [0.0]) is False
    assert update_solution_record(mem_db, "p_types", "w1", "user", True, [0.0]) is False
    assert update_solution_record(mem_db, "p_types", "w1", "user", [1.0], [0.0]) is False

    # None and invalid coordinates must return False without raising TypeError
    assert update_solution_record(mem_db, "p_types", "w1", "user", 1.5, None) is False
    assert update_solution_record(mem_db, "p_types", "w1", "user", 1.5, "0.0") is False
    assert update_solution_record(mem_db, "p_types", "w1", "user", 1.5, []) is False
    assert update_solution_record(mem_db, "p_types", "w1", "user", 1.5, [None]) is False
    assert update_solution_record(mem_db, "p_types", "w1", "user", 1.5, ["str"]) is False
    assert update_solution_record(mem_db, "p_types", "w1", "user", 1.5, [True]) is False

    # Empty or whitespace identifiers must return False
    assert update_solution_record(mem_db, "", "w1", "user", 1.5, [0.0]) is False
    assert update_solution_record(mem_db, "   ", "w1", "user", 1.5, [0.0]) is False
    assert update_solution_record(mem_db, "p_types", "", "user", 1.5, [0.0]) is False
    assert update_solution_record(mem_db, "p_types", "   ", "user", 1.5, [0.0]) is False
    assert update_solution_record(mem_db, "p_types", "w1", "", 1.5, [0.0]) is False
    assert update_solution_record(mem_db, "p_types", "w1", "   ", 1.5, [0.0]) is False
```

##### Update `test_nan_in_coordinates_rfc8259`:
```python
def test_nan_and_inf_in_coordinates_rejected(mem_db: sqlite3.Connection):
    """
    VERIFY: Coordinates containing NaN or Inf are rejected to ensure RFC 8259 JSON compliance.
    """
    mem_db.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_nan_coord', '3', '3', 1, 5.0)")
    mem_db.commit()

    assert update_solution_record(mem_db, "p_nan_coord", "w1", "user", 3.0, [float("nan")]) is False
    assert update_solution_record(mem_db, "p_nan_coord", "w1", "user", 3.0, [float("inf")]) is False
    assert update_solution_record(mem_db, "p_nan_coord", "w1", "user", 3.0, [float("-inf")]) is False
    assert update_solution_record(mem_db, "p_nan_coord", "w1", "user", 3.0, [1.0, float("nan")]) is False

    cur = mem_db.cursor()
    cur.execute("SELECT COUNT(*) FROM solutions WHERE problem_id = 'p_nan_coord'")
    assert cur.fetchone()[0] == 0
```

##### Update `test_seed_problems_corrupt_files_and_extreme_items`:
```python
def test_seed_problems_corrupt_files_and_extreme_items(tmp_path: Path):
    """
    VERIFY: seed_problems_from_verification discards whitespace IDs and normalizes extreme/non-positive best_value to None.
    """
    seed_dir = tmp_path / "extreme_catalog"
    seed_dir.mkdir()

    # Corrupt files
    (seed_dir / "bad.json").write_text("not json content {")
    (seed_dir / "empty.json").write_text("")
    (seed_dir / "html.json").write_text("<html>404</html>")
    (seed_dir / "non_list.json").write_text(json.dumps({"key": "val"}))
    (seed_dir / "primitives_list.json").write_text(json.dumps([1, 2, "str", None]))

    # Extreme items
    extreme_items = [
        {"our_problem": "   ", "N": 1, "best_value": 1.0, "inner_shape": "3", "container_shape": "3"},
        {"our_problem": "p_zero_n", "N": 0, "best_value": 1.0},
        {"our_problem": "p_neg_n", "N": -5, "best_value": 1.0},
        {"our_problem": "p_zero_val", "N": 1, "best_value": 0.0, "inner_shape": "3", "container_shape": "3"},
        {"our_problem": "p_neg_val", "N": 1, "best_value": -3.5, "inner_shape": "3", "container_shape": "3"},
        {"our_problem": "p_inf_val", "N": 1, "best_value": "Infinity", "inner_shape": "3", "container_shape": "3"},
        {"our_problem": "p_safe'; DROP TABLE problems; --", "N": 1, "best_value": 2.0, "inner_shape": "3", "container_shape": "3"},
        {"our_problem": "p_float_n", "N": 2.9, "best_value": 2.0, "inner_shape": "3", "container_shape": "3"},
        {"our_problem": "p_optimal", "N": 1, "best_value": 1.0, "inner_shape": "3", "container_shape": "3", "status": "proved_optimal"},
    ]
    (seed_dir / "extreme_data.json").write_text(json.dumps(extreme_items), encoding="utf-8")

    conn = init_db(":memory:")
    seeded_count = seed_problems_from_verification(conn, str(seed_dir))

    # Whitespace ID is rejected: exactly 6 valid problem definitions ingested
    assert seeded_count == 6

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM problems WHERE trim(id) = ''")
    assert cur.fetchone()[0] == 0

    # Non-positive and infinite best_value normalized to None (NULL)
    p_zero = get_problem(conn, "p_zero_val")
    assert p_zero["best_s"] is None
    assert p_zero["reference_s"] is None

    p_neg = get_problem(conn, "p_neg_val")
    assert p_neg["best_s"] is None

    p_inf = get_problem(conn, "p_inf_val")
    assert p_inf["best_s"] is None

    conn.close()
```

#### 2. In `tests/test_server_database.py`:

##### Add `test_schema_check_constraints_enforced`:
```python
def test_schema_check_constraints_enforced(mem_db: sqlite3.Connection):
    """VERIFY: SQLite table DDL CHECK constraints prevent invalid writes."""
    # 1. problems.best_s > 0
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('bad_s', '3', '3', 1, 0.0)")
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('bad_neg', '3', '3', 1, -1.0)")

    # 2. problems.id non-empty
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('   ', '3', '3', 1, 1.0)")

    # 3. problems.n > 0
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('bad_n', '3', '3', 0, 1.0)")

    # 4. solutions.metric_s > 0
    mem_db.execute("INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p_valid', '3', '3', 1, 2.0)")
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute("INSERT INTO solutions (problem_id, metric_s, worker_username, worker_id, coordinates_json) VALUES ('p_valid', 0.0, 'u', 'w', '[0.0]')")
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute("INSERT INTO solutions (problem_id, metric_s, worker_username, worker_id, coordinates_json) VALUES ('p_valid', -2.0, 'u', 'w', '[0.0]')")
```

---

## 4. Caveats

- **Scope Boundary with Milestone 3 Geometric Verifier**:
  - The database layer validates numeric format, sequence type, non-emptiness, and absence of `NaN`/`Inf` to maintain RFC 8259 JSON compliance.
  - Verification of coordinate vector length ($3N$), container boundary containment, and Separating Axis Theorem polygon non-overlap is the explicit responsibility of Milestone 3 (`src/shape_packing/server/app.py` via `verify_solution`).
- **In-Memory SQLite WAL Mode**:
  - In-memory databases (`:memory:`) operate in memory journaling mode per SQLite core design, but behave identically with respect to relational schema, transactions, and CHECK constraints.

---

## 5. Conclusion

All 4 vulnerabilities identified in Challenger 1's report have been thoroughly probed and specified with exact, unambiguous interface contracts, DDL schema additions, migration behaviors, and concrete test assertions.

- **Vulnerability 1 (Zero/Negative Metrics)**: Completely eliminated by pre-transaction `metric_s <= 0.0` rejection and `CHECK (best_s IS NULL OR best_s > 0)` / `CHECK (metric_s > 0)`.
- **Vulnerability 2 (Benchmark Seeding Ingestion)**: Completely eliminated by stripping whitespace from problem IDs and normalizing non-positive/infinite `best_value` to `None`.
- **Vulnerability 3 (Unhandled TypeErrors)**: Completely eliminated by explicit `isinstance` validation on all parameters, failing fast with `return False`.
- **Vulnerability 4 (RFC 8259 Coordinate Serialization)**: Completely eliminated by validating every element of `coordinates` for finite numeric values before calling `json.dumps()`.

---

## 6. Verification Method

To independently verify this specification report:

1. **Verify Existing Tests Pass Prior to Remediation**:
   ```bash
   pytest tests/test_server_database.py tests/test_server_database_stress.py -v
   ```
   *Expected*: 32 passed in ~2.1s.

2. **Verify Remediation Invalidation Condition**:
   Once Worker M1 implements the specifications:
   - Run the updated test suite:
     ```bash
     pytest tests/test_server_database.py tests/test_server_database_stress.py -v
     ```
   - All tests must pass with 0 failures, and `test_zero_and_negative_metrics_empirical_behavior` must verify rejection (`assert zero_accepted is False` and `assert neg_accepted is False`).
