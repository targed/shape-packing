# Investigation Report: Remediation of Challenger 1 Findings (Milestone 1 Iteration 2)

**Author**: Explorer M1 It2  
**Target Audience**: Orchestrator, Worker M1  
**Scope**: Verification catalog integrity, problem seeding validation rules, SQLite schema CHECK constraints, and solution update contract hardening.

---

## 1. Observation

### Observation 1.1: Verification Catalog (`data/packingVerification/*.json`) Integrity Audit
A complete programmatic audit of all JSON benchmark files in `data/packingVerification/` was performed across all 82 files and 2,269 items:
- **Total files scanned**: 82 files.
- **Corrupt / unparseable JSON files**: 0 files.
- **Non-list files**: 0 files.
- **Missing or non-string `our_problem`**: 0 items.
- **Whitespace-only or blank `our_problem` identifiers**: 0 items (all 2,269 are non-empty stripped strings).
- **Non-positive or non-integer `N`**: 0 items (all $N \in [1, 25]$).
- **Non-positive `best_value` ($s \le 0$)**: 0 items.
- **Non-finite `best_value` (`NaN`, `+Inf`, `-Inf`)**: 0 items.
- **Null `best_value`**: 0 items.
- **`best_value` range across catalog**:
  - Minimum: `0.122028320701` (`48_cirinoct` in `data/packingVerification/cirinoct.json`)
  - Maximum: `194.49896` (`50_cirinttt` in `data/packingVerification/cirinttt.json`)
- **Normalized shape tokens**: All 2,269 items map to recognized canonical shape tokens (`'3'`-`'10'`, `'CIRCLE'`, `'DOMINO'`, `'TAN'`, `'L'`).
- **Status distribution**: `best_known`: 1,755, `trivial`: 465, `proved_optimal`: 49.
- **Unique problem IDs**: 2,249 distinct problems (20 duplicate cross-file keys between `cirindom.json` and `domincir.json` correctly handled).

**Conclusion on Catalog**: The existing catalog in `data/packingVerification` is 100% clean, valid, and free of non-positive, infinite, NaN, or whitespace values.

### Observation 1.2: Code-Level Ingestion Vulnerabilities in `seed_problems_from_verification`
- **Location**: `src/shape_packing/server/database.py:296-322`
- **Current Code**:
  ```python
  our_problem = item.get("our_problem")
  if not our_problem:
      continue

  try:
      n = int(item.get("N", 0))
      if n <= 0:
          continue
  except (ValueError, TypeError):
      continue

  raw_val = item.get("best_value")
  try:
      best_val = float(raw_val) if raw_val is not None else None
  except (ValueError, TypeError):
      best_val = None
  ```
- **Observed Flaws**:
  1. `if not our_problem:` fails on whitespace strings (e.g. `'   '`, `'\t\n'`). In Python, `'   '` is truthy, so `not our_problem` evaluates to `False`. The whitespace string passes into SQL `problems.id`.
  2. `float(raw_val)` parses `"Infinity"`, `"+inf"`, `"-inf"`, and `"NaN"` without raising `ValueError` or `TypeError`. It assigns `best_val = inf`, inserting `inf` into `problems.best_s` and `problems.reference_s`.
  3. Non-positive numbers (`0.0`, `-3.5`) are parsed by `float(...)` and inserted directly into `problems.best_s` and `problems.reference_s`.
  4. If `raw_n` is boolean `True`, Python's `isinstance(True, int)` is `True` and `int(True)` evaluates to `1`.

### Observation 1.3: SQLite Behavior with CHECK Constraints and IEEE 754 Floating-Point Values
Direct testing of SQLite 3.54.1 behavior under CHECK constraints revealed:
- `CHECK (best_s IS NULL OR best_s > 0)`:
  - Blocks `0.0`: `CHECK constraint failed` (IntegrityError).
  - Blocks `-1.0`: `CHECK constraint failed` (IntegrityError).
  - **Permits `float('inf')`**: In SQLite / IEEE 754, `+Infinity > 0` evaluates to **TRUE**! Therefore, a standard `CHECK (best_s > 0)` or `CHECK (metric_s > 0)` **does NOT reject `+Infinity`**.
  - For `float('nan')`: Python's `sqlite3` driver converts `float('nan')` to `None` (`NULL`). In `best_s IS NULL OR best_s > 0`, it is allowed as `NULL`. In `metric_s REAL NOT NULL`, it triggers `NOT NULL constraint failed`.
- `CHECK (best_s IS NULL OR (best_s > 0 AND best_s < 1e999))`:
  - In SQLite, the literal `1e999` overflows IEEE 754 float representation and represents `+Infinity`.
  - The condition `best_s < 1e999` evaluates to `False` when `best_s` is `+Infinity` (`inf < inf` is false).
  - **Empirical result**: `CHECK (best_s IS NULL OR (best_s > 0 AND best_s < 1e999))` successfully blocks `0.0`, `-1.0`, `-inf`, and `+inf`, while permitting valid positive floats (`1e-10` to `1e300`) and `NULL`.

### Observation 1.4: Existing Stress Test Suite Structure
- **Location**: `tests/test_server_database_stress.py:231-372`
- Challenger 1 added 8 empirical tests. Four tests specifically codified the unhardened behavior:
  - `test_zero_and_negative_metrics_empirical_behavior` (lines 231-262): asserts `zero_accepted is True`, `neg_accepted is True`.
  - `test_non_numeric_and_none_metric_type_errors` (lines 263-286): asserts `update_solution_record` raises `TypeError`.
  - `test_nan_in_coordinates_rfc8259` (lines 288-306): asserts `[NaN]` is written to JSON.
  - `test_seed_problems_corrupt_files_and_extreme_items` (lines 312-372): asserts `seeded_count == 7` because `'   '`, `p_zero_val`, `p_neg_val`, and `p_inf_val` were ingested.

---

## 2. Logic Chain

1. **Physical Scale Principle**:
   - In 2D shape packing, $N$ shapes with positive total area are packed into a container with dimension parameter $s$. Container area scales as $s^2 > 0$, requiring $s > 0$.
   - Any metric $s \le 0$ or $s = \infty$ is physically invalid.

2. **Permanent Record Poisoning Prevention**:
   - `update_solution_record` enforces `metric_s < current_best - RECORD_MIN_IMPROVEMENT` ($10^{-5}$) to break a record.
   - If `current_best` is ever recorded as $\le 0$, no subsequent valid solution ($s > 0$) can satisfy $s \le -10^{-5}$. The problem becomes permanently un-improvable.
   - Therefore, `update_solution_record` must strictly reject any metric $s \le 0$, non-numeric types, booleans, NaN, and Inf by returning `False`.

3. **Defense-in-Depth Architecture**:
   - Application-level validation in Python (`seed_problems_from_verification`, `update_solution_record`) provides the first line of defense, gracefully handling dirty data without raising unhandled exceptions or failing batch transactions.
   - Database-level SQLite `CHECK` constraints provide an absolute barrier, ensuring data integrity even if queries bypass application helper functions.
   - Because SQLite evaluates `+inf > 0` as true, SQLite CHECK constraints must explicitly bound values with `AND best_s < 1e999` (or `best_s != 1e999`) to reject Infinity.

4. **Seeding Sanitization Strategy**:
   - For `our_problem`: An empty or whitespace-only problem identifier cannot be referenced or solved. It must be rejected (`continue`). Any surrounding whitespace on valid identifiers must be stripped (`raw_problem.strip()`).
   - For `N`: Must be a positive integer ($N \ge 1$), excluding booleans.
   - For `best_value`: If `best_value` is missing (`None`), invalid, non-finite (`inf`, `nan`), or non-positive ($\le 0$), it should be coerced to `None` rather than skipping the problem definition. This preserves legitimate benchmark problem definitions (e.g. unsolved or open problems) as `status='unattempted'` so workers can compute solutions, without poisoning the `best_s` column.

---

## 3. Caveats

1. **No Catalog Corruption Found**: The verification catalog (`data/packingVerification/*.json`) is currently completely clean. No catalog data migration or JSON patching is required. The remediation is purely code and schema hardening.
2. **Stress Test Assertions**: In `tests/test_server_database_stress.py`, four tests were intentionally written by Challenger 1 to assert the presence of the bugs. When Worker M1 applies the fixes, those four stress tests must be updated to assert the secure behavior (`False` on non-positive metrics, 6 seeded items instead of 7 with whitespace ID skipped and bad values coerced to `None`).

---

## 4. Conclusion & Recommended Remediation

### 4.1. Recommendations for SQLite `SCHEMA` in `src/shape_packing/server/database.py`

Update `SCHEMA` to include the following table constraints:

```sql
CREATE TABLE IF NOT EXISTS problems (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    inner_token TEXT NOT NULL CHECK (length(trim(inner_token)) > 0),
    container_token TEXT NOT NULL CHECK (length(trim(container_token)) > 0),
    n INTEGER NOT NULL CHECK (n > 0),
    best_s REAL CHECK (best_s IS NULL OR (best_s > 0 AND best_s < 1e999)),
    reference_s REAL CHECK (reference_s IS NULL OR (reference_s > 0 AND reference_s < 1e999)),
    status TEXT NOT NULL DEFAULT 'unattempted',
    total_attempts INTEGER DEFAULT 0 CHECK (total_attempts >= 0),
    density_rank REAL DEFAULT 0.0,
    source_attribution TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS solutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id TEXT NOT NULL REFERENCES problems(id) CHECK (length(trim(problem_id)) > 0),
    metric_s REAL NOT NULL CHECK (metric_s > 0 AND metric_s < 1e999),
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

### 4.2. Exact Filtering Rules for `seed_problems_from_verification`

In `src/shape_packing/server/database.py`, replace lines 296-322 with:

```python
            for item in data:
                if not isinstance(item, dict):
                    continue

                raw_prob = item.get("our_problem")
                if not isinstance(raw_prob, str):
                    continue
                our_problem = raw_prob.strip()
                if not our_problem:
                    continue

                raw_n = item.get("N")
                if isinstance(raw_n, bool):
                    continue
                try:
                    n = int(raw_n)
                    if n <= 0:
                        continue
                except (ValueError, TypeError):
                    continue

                raw_val = item.get("best_value")
                best_val: Optional[float] = None
                if raw_val is not None and not isinstance(raw_val, bool):
                    try:
                        parsed_val = float(raw_val)
                        if not (math.isnan(parsed_val) or math.isinf(parsed_val) or parsed_val <= 0.0):
                            best_val = parsed_val
                    except (ValueError, TypeError):
                        best_val = None

                inner = normalize_shape_token(item.get("inner_shape"))
                container = normalize_shape_token(item.get("container_shape"))
                if not inner or not container:
                    continue

                status = str(item.get("status") or ("best_known" if best_val is not None else "unattempted"))
                note = str(item.get("source_note") or "")

                rows.append((our_problem, inner, container, n, best_val, best_val, status, note))
```

### 4.3. Validation Rules for `update_solution_record`

In `src/shape_packing/server/database.py`, replace lines 204-206 with:

```python
    # Validate metric_s: must be a finite positive real number, not bool, not None, not str
    if (
        isinstance(metric_s, bool)
        or not isinstance(metric_s, (int, float))
        or math.isnan(metric_s)
        or math.isinf(metric_s)
        or metric_s <= 0.0
    ):
        return False

    # Validate coordinates: must be a list or tuple of finite real numbers (RFC 8259 compliance)
    if not isinstance(coordinates, (list, tuple)):
        return False

    for c in coordinates:
        if (
            isinstance(c, bool)
            or not isinstance(c, (int, float))
            or math.isnan(c)
            or math.isinf(c)
        ):
            return False

    if not isinstance(problem_id, str) or not problem_id.strip():
        return False
    if not isinstance(worker_id, str) or not worker_id.strip():
        return False
    if not isinstance(username, str) or not username.strip():
        return False
```

### 4.4. Test Update Plan for `tests/test_server_database_stress.py`

Once Worker M1 applies the changes above, update the following stress tests:

1. `test_zero_and_negative_metrics_empirical_behavior`:
   Change assertions:
   ```python
   assert zero_accepted is False, "Zero metric must be rejected"
   assert p_zero["best_s"] == 2.0, "best_s must not be poisoned"
   assert neg_accepted is False, "Negative metric must be rejected"
   assert p_neg["best_s"] == 2.0, "best_s must not be poisoned"
   ```

2. `test_non_numeric_and_none_metric_type_errors`:
   Replace `with pytest.raises(TypeError):` with direct assertions:
   ```python
   assert update_solution_record(conn, "p_types", "w1", "user", None, [0.0]) is False
   assert update_solution_record(conn, "p_types", "w1", "user", "1.5", [0.0]) is False
   assert update_solution_record(conn, "p_types", "w1", "user", 1.5, None) is False
   ```

3. `test_nan_in_coordinates_rfc8259`:
   Change assertions:
   ```python
   res = update_solution_record(conn, "p_nan_coord", "w1", "user", 3.0, [float("nan")])
   assert res is False
   ```

4. `test_seed_problems_corrupt_files_and_extreme_items`:
   Change assertions:
   ```python
   # Whitespace ID is rejected; p_zero_val, p_neg_val, p_inf_val have best_s coerced to None
   # Ingested items: p_zero_val, p_neg_val, p_inf_val, p_safe..., p_float_n, p_optimal = 6 items
   assert seeded_count == 6
   assert get_problem(conn, "   ") is None

   p_zero = get_problem(conn, "p_zero_val")
   assert p_zero["best_s"] is None

   p_neg = get_problem(conn, "p_neg_val")
   assert p_neg["best_s"] is None

   p_inf = get_problem(conn, "p_inf_val")
   assert p_inf["best_s"] is None
   ```

---

## 5. Verification Method

To verify these findings and test the remediation:

1. **Verify catalog cleanliness independently**:
   ```bash
   PYTHONPATH=src python3 -c "
   import glob, json, math
   files = sorted(glob.glob('data/packingVerification/*.json'))
   assert len(files) == 82
   total = 0
   for f in files:
       with open(f) as fp:
           data = json.load(fp)
       total += len(data)
       for item in data:
           assert isinstance(item['our_problem'], str) and item['our_problem'].strip()
           assert isinstance(item['N'], int) and item['N'] > 0
           v = float(item['best_value'])
           assert v > 0 and not math.isnan(v) and not math.isinf(v)
   print(f'Catalog verified: {total} items across {len(files)} files are 100% valid.')
   "
   ```

2. **Verify SQLite Inf / CHECK constraint behavior**:
   ```bash
   python3 -c "
   import sqlite3
   conn = sqlite3.connect(':memory:')
   conn.execute('CREATE TABLE t (s REAL CHECK (s IS NULL OR (s > 0 AND s < 1e999))))')
   for val in [0.0, -1.0, float('inf'), float('-inf')]:
       try:
           conn.execute('INSERT INTO t VALUES (?)', (val,))
           assert False, f'Failed to block {val}'
       except sqlite3.IntegrityError:
           pass
   conn.execute('INSERT INTO t VALUES (NULL)')
   conn.execute('INSERT INTO t VALUES (1.5)')
   print('CHECK constraint behavior verified.')
   "
   ```

3. **Run existing test suite**:
   ```bash
   PYTHONPATH=src pytest tests/test_server_database.py tests/test_server_database_stress.py -v
   ```
