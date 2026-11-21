# Milestone 1 Challenger Report: Coordinator Database Layer & Problem Ingestion

**Verdict**: `REQUEST_CHANGES`  
**Overall Risk Assessment**: HIGH

---

## 1. Observation

### Observation 1.1: Acceptance of Zero and Negative Metrics Corrupts `best_s`
- **Location**: `src/shape_packing/server/database.py:204-222`
- **Code**:
  ```python
  if math.isnan(metric_s) or math.isinf(metric_s):
      return False
  ...
  current_best = row["best_s"]
  if current_best is not None and metric_s >= (current_best - RECORD_MIN_IMPROVEMENT):
      conn.rollback()
      return False
  ```
- **Direct Empirical Test**:
  Executed via `python3` / `tests/test_server_database_stress.py::test_zero_and_negative_metrics_empirical_behavior`:
  ```python
  res_zero = update_solution_record(conn, 'p_zero', 'w1', 'user', 0.0, [0.0])
  # Result: res_zero == True, problems.best_s == 0.0

  res_neg = update_solution_record(conn, 'p_neg', 'w1', 'user', -5.0, [0.0])
  # Result: res_neg == True, problems.best_s == -5.0
  ```
  Neither `database.py` nor SQLite's table schema (`SCHEMA` lines 67-90) enforce `metric_s > 0` or `best_s > 0`.

### Observation 1.2: Seeding Benchmark Problems Ingests Non-Positive Values, Infs, and Whitespace IDs
- **Location**: `src/shape_packing/server/database.py:296-322`
- **Code**:
  ```python
  our_problem = item.get("our_problem")
  if not our_problem:
      continue
  ...
  raw_val = item.get("best_value")
  try:
      best_val = float(raw_val) if raw_val is not None else None
  except (ValueError, TypeError):
      best_val = None
  ```
- **Direct Empirical Test**:
  Running `tests/test_server_database_stress.py::test_seed_problems_corrupt_files_and_extreme_items`:
  - When `raw_val = "Infinity"`, `float("Infinity")` evaluates to `inf` without raising an error. It inserts `best_s = inf` into `problems`.
  - When `raw_val = 0.0` or `-3.5`, `float(...)` inserts `best_s = 0.0` and `best_s = -3.5`.
  - When `our_problem = "   "`, `if not our_problem` evaluates to `False` (whitespace string is truthy), inserting a blank problem ID `'   '` into the database.

### Observation 1.3: Non-Numeric and Invalid Types Cause Unhandled `TypeError`
- **Location**: `src/shape_packing/server/database.py:204`, line 237
- **Direct Empirical Test**:
  Running `tests/test_server_database_stress.py::test_non_numeric_and_none_metric_type_errors`:
  - `update_solution_record(..., metric_s=None)` crashes with `TypeError: must be real number, not NoneType`.
  - `update_solution_record(..., metric_s="1.5")` crashes with `TypeError: must be real number, not str`.
  - `update_solution_record(..., coordinates=None)` crashes with `TypeError: 'NoneType' object is not iterable`.

### Observation 1.4: Non-Standard JSON Generation for NaN Coordinates
- **Location**: `src/shape_packing/server/database.py:237`
- **Code**: `json.dumps(list(coordinates))`
- **Direct Empirical Test**:
  Running `tests/test_server_database_stress.py::test_nan_in_coordinates_rfc8259`:
  - Submitting `coordinates=[float('nan')]` succeeds (`True`) and writes `'[NaN]'` to `solutions.coordinates_json`.
  - Under RFC 8259, `NaN` is not valid JSON. Strict decoders (such as Rust's `serde_json` used by `packer_rs`) fail to deserialize this payload.

### Observation 1.5: Epsilon Threshold Precision Behavior
- **Location**: `src/shape_packing/server/database.py:220`
- **Code**: `if current_best is not None and metric_s >= (current_best - RECORD_MIN_IMPROVEMENT):`
- **Direct Empirical Test**:
  Running `tests/test_server_database_stress.py::test_epsilon_boundary_precision`:
  - For `current_best = 5.0` and `RECORD_MIN_IMPROVEMENT = 1e-5`:
    - `metric_s = 4.99999` (exact delta of $10^{-5}$) returns `False` (rejected).
    - `metric_s = 4.999989999` (delta $10^{-5} + 10^{-9}$) returns `True` (accepted).
  - Worker M1's handoff report claimed: *"Strictly better metric ($\Delta \ge 10^{-5}$ via `RECORD_MIN_IMPROVEMENT`)"*. The actual implementation enforces $\Delta > 10^{-5}$.

### Observation 1.6: High-Throughput Concurrency Performance
- **Location**: `src/shape_packing/server/database.py:126-144`, `200-265`
- **Direct Empirical Test**:
  Running `tests/test_server_database_stress.py::test_concurrent_worker_registration_high_throughput`, `test_concurrent_solution_updates_hotspot`, and `test_mixed_concurrent_workload`:
  - 50 concurrent worker threads executed 2,500 continuous write operations on a single hotspot problem in 2.91 seconds with **0 errors**.
  - `PRAGMA integrity_check` returned `ok`.
  - `PRAGMA foreign_key_check` returned empty `[]`.
  - Exactly 1 row remained with `is_current_record = 1`.
  - Sum of `workers.records_broken` exactly matched total committed solutions (2,421 rows).

---

## 2. Logic Chain

1. **Physical Meaning of Container Scale $s$**:
   - In 2D shape packing, $N$ shapes with positive area $\sum A_i > 0$ are packed into a container with dimension parameter $s$.
   - The container area is proportional to $s^2 > 0$, requiring $s > 0$. Container dimensions $\le 0$ are physical impossibilities.

2. **Permanent Problem Poisoning Vulnerability**:
   - By Observation 1.1, `update_solution_record` accepts `metric_s <= 0` and sets `problems.best_s` to `0.0` or a negative value.
   - To update an existing record, line 220 requires `metric_s < current_best - 1e-5`.
   - If `current_best <= 0`, any legitimate subsequent candidate (which must have $s > 0$) satisfies $s > 0 > \text{current\_best} - 10^{-5}$.
   - Thus, once a zero or negative metric is recorded, **no subsequent valid solution can ever qualify as an improvement**. The problem is permanently poisoned in the coordinator database.

3. **Seeding Vulnerability**:
   - By Observation 1.2, if an external benchmark file in `data/packingVerification/` contains `best_value` of `0.0`, negative numbers, or `"Infinity"`, `seed_problems_from_verification` persists those values directly into `best_s`.
   - Persisting `best_s = inf` distorts initial ranking and scheduler heuristics; persisting `best_s <= 0` corrupts the problem record immediately upon startup.

4. **Robustness and Contract Defense-in-Depth**:
   - While Milestone 3 will introduce API-level verification (`verify_solution`), the database persistence layer must enforce its own contract invariants against corrupt inputs, malformed types, and data poisoning.

---

## 3. Caveats

- **Concurrency and WAL Serialization**: No race conditions, deadlocks, or lock upgrade deadlocks were observed. The combination of `PRAGMA journal_mode = WAL`, `timeout=30.0`, and `BEGIN IMMEDIATE` is proven highly effective under heavy multi-threaded load.
- **Existing Tests**: All 24 original unit tests in `tests/test_server_database.py` pass without regression.

---

## 4. Conclusion

**Verdict: `REQUEST_CHANGES`**

While the core WAL architecture and concurrency locking are implemented correctly and robustly, the persistence layer suffers from critical boundary validation gaps:
1. **Critical**: `update_solution_record` permits $s \le 0$, allowing corrupt or zero metrics to permanently poison problem records.
2. **High**: `seed_problems_from_verification` accepts non-finite (`inf`), non-positive (`<= 0`), and blank/whitespace problem identifiers.
3. **Medium**: `update_solution_record` throws unhandled `TypeError` on invalid argument types instead of returning `False`.
4. **Medium**: Coordinate serialization permits `NaN` which generates invalid RFC 8259 JSON (`[NaN]`).

### Recommended Mitigations for Worker M1:

1. In `update_solution_record` (`src/shape_packing/server/database.py`):
   - Add input validation:
     ```python
     if not isinstance(metric_s, (int, float)) or math.isnan(metric_s) or math.isinf(metric_s) or metric_s <= 0.0:
         return False
     if not isinstance(coordinates, (list, tuple)):
         return False
     if any(not isinstance(c, (int, float)) or math.isnan(c) or math.isinf(c) for c in coordinates):
         return False
     ```
2. In `seed_problems_from_verification` (`src/shape_packing/server/database.py`):
   - Reject empty or whitespace-only problem IDs:
     ```python
     our_problem = str(item.get("our_problem") or "").strip()
     if not our_problem:
         continue
     ```
   - Enforce positive, finite `best_val`:
     ```python
     try:
         best_val = float(raw_val) if raw_val is not None else None
         if best_val is not None and (math.isnan(best_val) or math.isinf(best_val) or best_val <= 0.0):
             best_val = None
     except (ValueError, TypeError):
         best_val = None
     ```
3. In `SCHEMA` (lines 67-90):
   - Add `CHECK (best_s IS NULL OR best_s > 0)` to `problems` and `CHECK (metric_s > 0)` to `solutions`.

---

## 5. Verification Method

To independently reproduce and verify all findings:

1. **Run full pytest test suite (including stress tests)**:
   ```bash
   pytest tests/test_server_database.py tests/test_server_database_stress.py -v
   ```
   *Expected outcome*: All 32 tests pass, empirically demonstrating the exact behavior described in Observations 1.1 through 1.6.

2. **Run direct zero/negative metric poisoning reproduction**:
   ```bash
   PYTHONPATH=src python3 -c "
   from shape_packing.server.database import init_db, update_solution_record, get_problem
   conn = init_db(':memory:')
   conn.execute(\"INSERT INTO problems (id, inner_token, container_token, n, best_s) VALUES ('p1', '3', '3', 1, 2.0)\")
   assert update_solution_record(conn, 'p1', 'w1', 'u', 0.0, [0.0]) is True
   assert get_problem(conn, 'p1')['best_s'] == 0.0
   # Valid positive candidate is now permanently blocked:
   assert update_solution_record(conn, 'p1', 'w1', 'u', 1.0, [0.0]) is False
   print('Poisoning vulnerability successfully reproduced.')
   "
   ```

3. **Invalidation Condition**:
   These findings will be invalidated once `update_solution_record` and `seed_problems_from_verification` reject non-positive/infinite values and whitespace IDs, and when `tests/test_server_database_stress.py::test_zero_and_negative_metrics_empirical_behavior` is updated to assert rejection (`res is False`) and passes.
