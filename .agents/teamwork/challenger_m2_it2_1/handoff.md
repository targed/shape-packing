# Empirical Challenge Report — Milestone 2 Scheduler (Iteration 2)

**Agent**: `challenger_m2_it2_1`  
**Target File**: `src/shape_packing/server/scheduler.py`  
**Parent Conversation ID**: `86ab9594-ed5d-48cc-9be1-f2844355b5e4`  
**Timestamp**: 2026-11-21T00:06:00Z  
**Verdict**: **APPROVE**  

---

## 1. Observation

Direct empirical tests were executed against `src/shape_packing/server/scheduler.py` covering extreme/corrupt inputs, priority queue ranking invariants, and concurrency behaviors.

### 1.1 Extreme and Corrupt Inputs to `assign_work`
Execution of boundary parameters against `assign_work(conn, worker_id, cores, lease_seconds)` yielded:
1. `cores=float('inf')`:
   - Line 74 in `src/shape_packing/server/scheduler.py` caught `OverflowError: cannot convert float infinity to integer`.
   - Result: `recommended_attempts = 1000`. No exception raised.
2. `cores=-100`:
   - Line 77 clamped `c = max(1, cores) = 1`.
   - Result: `recommended_attempts = 1000`.
3. `lease_seconds=float('inf')`:
   - Line 84 caught `OverflowError`.
   - Result: `lease_seconds = 300` (safe default).
4. `lease_seconds=1e308`:
   - Lines 83 and 87 clamped `ls` to `MAX_LEASE_SECONDS = 604800` (7 days max).
   - `datetime.timedelta(seconds=ls)` executed without `OverflowError` or `date value out of range`.
5. `worker_id=None`:
   - Line 63 returned `None` immediately.
6. Additional corrupt worker IDs (`""`, `"   "`, `12345`, `['list']`, `{'dict': 1}`, `True`, `False`):
   - All cleanly returned `None`.
7. Additional extreme cores & lease_seconds (`cores=float('nan')`, `cores=float('-inf')`, `cores=10**20`, `cores=True`, `lease_seconds=1e400`, `lease_seconds=10**300`):
   - Handled with zero exceptions; returned bounded, well-formed work dictionaries.

### 1.2 Extreme and Corrupt Inputs to `record_heartbeat`
Execution of boundary parameters against `record_heartbeat(conn, work_id, worker_id, attempts, best_s)` yielded:
1. `attempts=2**64`:
   - Line 268 rejected via guard `attempts > 2**63 - 1`.
   - Result: returned `False` immediately, preventing SQLite signed 64-bit binding overflow.
2. `attempts=2**63`:
   - Exceeds signed 64-bit maximum (`9223372036854775807`). Guard cleanly rejected and returned `False`.
3. `attempts=2**63 - 1`:
   - Max permissible 64-bit integer successfully accepted and recorded; returned `True`.
4. `best_s=1e400`:
   - Line 280 caught `math.isinf(f_best_s)`. Returned `False`.
5. `best_s=float('inf')` and `best_s=float('-inf')`:
   - Line 280 caught `math.isinf(f_best_s)`. Returned `False`.
6. `best_s=float('nan')`:
   - Line 280 caught `math.isnan(f_best_s)`. Returned `False`.
7. `best_s=10**400` (arbitrary-precision integer):
   - Line 278 caught `OverflowError: int too large to convert to float`. Returned `False`.
8. `best_s=-1.0`, `0.0`, `True`, `False`, `"abc"`:
   - Line 280 guards `f_best_s <= 0.0` or type checks rejected and returned `False`.

### 1.3 Priority Ordering: Stuck Backoff vs Closeness Boost
Empirical verification of the multi-armed bandit SQL `ORDER BY` clause:
```sql
ORDER BY
    -- Tier 1: Stuck backoff (>50k attempts without improvement decays priority)
    CASE
        WHEN p.total_attempts > 50000
             AND (p.updated_at IS NULL OR p.updated_at < datetime('now', '-1 day'))
        THEN 1 ELSE 0
    END ASC,
    -- Tier 2: Closeness boost (within 1% of baseline record prioritized)
    CASE
        WHEN p.reference_s IS NOT NULL AND p.best_s IS NOT NULL AND p.reference_s > 0
             AND (abs(p.best_s - p.reference_s) / p.reference_s) <= 0.01
        THEN 0 ELSE 1
    END ASC,
    -- Tier 3: Attempt count fair balancing (total_attempts ASC)
    p.total_attempts ASC,
    -- Tier 4: Density rank void space (density_rank DESC)
    p.density_rank DESC,
    -- Tier 5: Random tie-breaker
    RANDOM()
```
Empirical test results:
- **Test 1**: Given Problem A (`total_attempts=60000`, `updated_at=2 days ago`, `best_s=9.99`, `reference_s=10.0` -> Stuck=1, Boost=0) and Problem B (`total_attempts=10000`, `updated_at=2 days ago`, `best_s=5.0`, `reference_s=10.0` -> Stuck=0, Boost=1):
  - `assign_work` assigned **Problem B** (`p_not_stuck_far`).
  - Confirmed: **Stuck backoff (Tier 1) strictly overrides closeness boost (Tier 2)**.
- **Test 2**: Given Problem A (Not stuck, Closeness boost active, `total_attempts=40000`) and Problem B (Not stuck, No boost, `total_attempts=100`):
  - `assign_work` assigned **Problem A** (`p_close_high_attempts`).
  - Confirmed: **Closeness boost (Tier 2) strictly overrides attempt count (Tier 3)**.
- **Test 3**: Given Problem A (Not stuck, Boosted, `total_attempts=100`) and Problem B (Not stuck, Boosted, `total_attempts=500`):
  - `assign_work` assigned **Problem A**.
  - Confirmed: **Attempt count ASC breaks ties between boosted problems**.
- **Test 4**: Given Problem A and Problem B tied on Stuck, Boost, and Attempts:
  - `assign_work` assigned the problem with higher `density_rank`.
  - Confirmed: **Density rank DESC acts as Tier 4 tie-breaker**.
- **Test 5**: Stuck backoff threshold:
  - At `total_attempts=50000`, problem is not stuck.
  - At `total_attempts=50001`, problem is marked stuck (Tier 1 = 1).
- **Test 6**: Closeness boost threshold:
  - At relative difference `0.0100` (1.000%), boost activates.
  - At relative difference `0.01001` (1.001%), boost does not activate.

### 1.4 Exploration Fall-Through Verification
Tested scenario where 1 unattempted problem is in-flight leased, and 5 active non-optimal problems exist:
- When a new worker rolled exploration (`random.random() < 0.10`), `assign_work` cleanly fell through to an unleased active problem rather than creating a duplicate lease on the in-flight unattempted candidate.

### 1.5 Test Suite Results
1. Targeted Scheduler Suite:
   `pytest tests/test_server_scheduler.py tests/test_server_scheduler_stress.py -v`
   - **Result**: `109 passed in 1.57s` (0 failures).
2. Full Integration & DB Suite:
   `pytest tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py tests/test_server_database.py -v`
   - **Result**: `147 passed in 7.70s` (0 failures).

---

## 2. Logic Chain

1. **Safety under Malformed and Extreme Numeric Inputs**:
   - `assign_work` wraps `int(cores)` and `int(lease_seconds)` with `(ValueError, TypeError, OverflowError)`. Any non-convertible or infinite float reverts to sensible defaults (`c=1`, `ls=300`).
   - Clamping `ls` to `[1, 604800]` ensures `datetime.timedelta(seconds=ls)` operates strictly within Python and C-level integer ranges, preventing date overflow crashes.
   - `record_heartbeat` enforces `attempts <= 2**63 - 1` and `0.0 < best_s <= 1e308`. These checks eliminate SQLite type binding failures and protect against floating point exceptions.

2. **Priority Ordering Conformance**:
   - The ordering hierarchy in SQL is deterministic:
     `Tier 1 (Stuck backoff ASC) -> Tier 2 (Closeness boost ASC) -> Tier 3 (total_attempts ASC) -> Tier 4 (density_rank DESC) -> Tier 5 (RANDOM())`.
   - Empirically verified: stuck problems are deferred behind all non-stuck problems regardless of closeness; for non-stuck problems, close configurations are prioritized before fair attempt balancing.

3. **Lease Concurrency and Exploration Integrity**:
   - Removing the premature fallback query from the exploration block allows the 10% exploration stage to fall through to the 90% exploitation query when all unattempted problems are in-flight.
   - Fallback shared leasing engages only when all non-optimal problems in the catalog are actively leased.

---

## 3. Caveats

- **No Caveats**: All requested edge cases, parameter bounds, overflow possibilities, priority interactions, and test suites were executed directly and verified with zero defects observed.

---

## 4. Conclusion

**Verdict**: **APPROVE**

The work scheduler and priority allocator implementation in `src/shape_packing/server/scheduler.py` is empirically robust, secure against integer and floating-point overflow attacks, maintains strict multi-armed bandit tier precedence, correctly isolates `proved_optimal` problems, and passes 100% of all regression, stress, and concurrency tests.

---

## 5. Verification Method

To independently reproduce all empirical verification results:

### 5.1 Project Test Command
```bash
pytest tests/test_server_scheduler.py tests/test_server_scheduler_stress.py tests/test_server_scheduler_concurrency.py tests/test_server_database.py -v
```
Expected output:
```text
============================= 147 passed in 7.70s ==============================
```

### 5.2 Standalone Boundary and Priority Harness
```bash
PYTHONPATH=src python3 -c "
from shape_packing.server.database import init_db
from shape_packing.server.scheduler import assign_work, record_heartbeat

conn = init_db(':memory:')
conn.execute('''INSERT INTO problems (id, inner_token, container_token, n, status) VALUES ('p1', '4', '4', 1, 'unattempted')''')
conn.commit()

# Extreme cores and lease
w = assign_work(conn, 'w1', cores=float('inf'), lease_seconds=1e308)
assert w is not None
assert w['recommended_attempts'] == 1000
assert w['lease_seconds'] == 604800

# Extreme heartbeat
assert record_heartbeat(conn, w['work_id'], 'w1', attempts=2**64) is False
assert record_heartbeat(conn, w['work_id'], 'w1', attempts=10, best_s=1e400) is False
assert record_heartbeat(conn, w['work_id'], 'w1', attempts=2**63 - 1) is True
print('VERIFICATION SUCCESSFUL')
"
```
Expected output:
```text
VERIFICATION SUCCESSFUL
```
