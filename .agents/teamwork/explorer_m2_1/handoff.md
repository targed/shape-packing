# Milestone 2 Investigation Report: Work Scheduler and Priority Allocator

**Investigator**: explorer_m2_1  
**Target Milestone**: Milestone 2 (Work Scheduler and Priority Allocator)  
**Date**: 2026-11-20  

---

## 1. Observation

### 1.1 Design Specification §5: Multi-Armed Bandit Scheduling Policy
In `docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md`, lines 215–230:
```markdown
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
```

### 1.2 Database Schema and Indexes
In `src/shape_packing/server/database.py`, lines 67–115:
- `problems` table:
  - `id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0)`
  - `inner_token TEXT NOT NULL`
  - `container_token TEXT NOT NULL`
  - `n INTEGER NOT NULL CHECK (n > 0)`
  - `best_s REAL CHECK (best_s IS NULL OR (best_s > 0 AND best_s < 1e999))`
  - `reference_s REAL CHECK (reference_s IS NULL OR (reference_s > 0 AND reference_s < 1e999))`
  - `status TEXT NOT NULL DEFAULT 'unattempted'`
  - `total_attempts INTEGER DEFAULT 0`
  - `density_rank REAL DEFAULT 0.0`
  - `source_attribution TEXT`
  - `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
- `active_leases` table:
  - `work_id TEXT PRIMARY KEY`
  - `problem_id TEXT NOT NULL REFERENCES problems(id)`
  - `worker_id TEXT NOT NULL REFERENCES workers(id)`
  - `leased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
  - `expires_at TIMESTAMP NOT NULL`
- Existing indexes:
  - `CREATE INDEX IF NOT EXISTS idx_active_leases_problem ON active_leases(problem_id);`
  - `CREATE INDEX IF NOT EXISTS idx_active_leases_expires ON active_leases(expires_at);`
  - `CREATE INDEX IF NOT EXISTS idx_problems_status_attempts ON problems(status, total_attempts, density_rank);`

### 1.3 Implementation Plan Task 2 Scaffold
In `docs/superpowers/plans/2026-11-20-distributed-shape-packing.md`, lines 306–517:
- Module location: `src/shape_packing/server/scheduler.py`
- Test file: `tests/test_server_scheduler.py`
- Exported interfaces:
  - `assign_work(conn: sqlite3.Connection, worker_id: str, cores: int = 1, lease_seconds: int = 300) -> Optional[Dict[str, Any]]`
  - `record_heartbeat(conn: sqlite3.Connection, work_id: str, worker_id: str, attempts: int, best_s: Optional[float] = None) -> bool`
  - `expire_stale_leases(conn: sqlite3.Connection) -> int`
- Recommended attempts formula in plan line 467:
  `recommended = max(1000, min(cores * 1000, 20000))`
- Work unit dictionary structure (lines 470–479):
  ```python
  {
      "work_id": work_id,
      "problem": prob["id"],
      "inner_token": prob["inner_token"],
      "container_token": prob["container_token"],
      "n": prob["n"],
      "target_s": float(target_s),
      "recommended_attempts": recommended,
      "lease_seconds": lease_seconds,
  }
  ```

### 1.4 Geometry and Density Precedents
In `src/shape_packing/ranker.py`, lines 10–63 and 127–145:
- Polygon area formula: $\text{Area} = \frac{1}{4} k s^2 \cot(\pi / k)$.
- Shape area calculation helper: `get_shape_area(shape_token: str, size: float) -> float`.
- Density formula: $\rho = \frac{\text{total\_inner\_area}}{\text{container\_area}} = \frac{N \cdot A_{\text{inner}}(1.0)}{A_{\text{container}}(s)}$.
- Void space definition: lower density $\rho \implies$ more wasted space $\implies$ higher priority for packing.

---

## 2. Logic Chain

### 2.1 Multi-Armed Bandit Scheduling Policy Analysis
From the design spec §5 observations, the scheduling policy decomposes into four distinct mechanisms:

1. **Exclusion Stage**:
   - **Proved Optimal**: Any problem with `LOWER(status) = 'proved_optimal'` must never be assigned under any condition (exploitation, exploration, or fallback). Once proven optimal, further compute has zero marginal value.
   - **Active Leases**: If an active lease exists in `active_leases` whose `expires_at > CURRENT_TIMESTAMP`, the problem is considered occupied and should not be assigned to another worker, **unless** all eligible problems are leased.
   - **Fallback Sharing**: Stochastic continuous optimization with independent random seeds does not duplicate work. Therefore, when all eligible problems have active leases, the scheduler falls back to selecting from all eligible non-`proved_optimal` problems, prioritizing the highest-yield problem.
   - **Empty / Fully Optimal Catalog**: If the database contains zero non-`proved_optimal` problems, `assign_work` returns `None` (corresponding to HTTP `204 No Content`).

2. **Exploration Stage ($\epsilon$-greedy, $\epsilon = 0.10$)**:
   - With $10\%$ probability (`random.random() < 0.10`), the scheduler bypasses exploitation scoring.
   - It targets *unattempted* problems (`status = 'unattempted'` or `total_attempts = 0`), strictly excluding `proved_optimal`.
   - Prefer unleased unattempted problems (`l.work_id IS NULL`). If all unattempted problems are currently leased, fall back to leased unattempted problems.
   - If no unattempted problems exist anywhere in the catalog, seamlessly fall through to the exploitation stage.

3. **Exploitation Scoring Stage ($1 - \epsilon = 0.90$)**:
   The priority of an eligible problem $p$ is governed by three signals:
   - **Geometric Void Space / Density Rank**:
     $$\rho = \frac{N \cdot A_{\text{inner}}}{A_{\text{container}}(s)}$$
     Void space is $1.0 - \rho$. In `problems.density_rank`, higher values denote higher priority (`p.density_rank DESC`). If `density_rank` is 0.0 (the database default), it can be computed using `get_shape_area` or approximated by relative void space.
   - **Closeness Boost**:
     When $p.\text{reference\_s} > 0$ and $p.\text{best\_s} > 0$:
     $$\text{gap} = \frac{|p.\text{best\_s} - p.\text{reference\_s}|}{p.\text{reference\_s}}$$
     If $\text{gap} \le 0.01$ (within $1\%$), the candidate is within striking distance of breaking a historical world record. Such problems receive an allocation boost ($2.0\times$ priority multiplier or primary sort priority).
   - **Attempt Count & Fair Balancing**:
     Fewer cumulative attempts (`p.total_attempts ASC`) are prioritized to prevent starvation of newer problems, scaling smoothly as $1 / (1 + 0.001 \cdot \text{total\_attempts})$.

4. **Stuck Backoff Stage**:
   - Condition: `p.total_attempts > 50000` without an improvement in the last 24 hours.
   - Observation: When a solution record is improved, `database.py:update_solution_record` sets `problems.updated_at = CURRENT_TIMESTAMP`. In contrast, `record_heartbeat` only increments `total_attempts` and updates `workers.last_seen_at`.
   - Thus, a problem is stuck without improvement for 24h if:
     `p.total_attempts > 50000 AND (p.updated_at IS NULL OR p.updated_at < datetime('now', '-1 day'))`
   - When stuck, its priority weight decays by $50\%$ ($0.5\times$ multiplier or lower sorting tier) until a new improvement updates `updated_at`.

---

### 2.2 Recommended Algorithm and Concurrency Architecture

#### Transaction Serialization with `BEGIN IMMEDIATE`
Observation from `tests/test_server_database_concurrency.py`: In SQLite WAL mode, concurrent worker requests calling `GET /api/v1/work` can race on the read-modify-write cycle of `active_leases`.
If two workers execute `assign_work` simultaneously with default `DEFERRED` transactions, both will read Problem A as unleased, and both will insert a lease for Problem A, causing accidental duplicate leasing when unleased problems were available.

**Recommendation**: Execute `assign_work` within `cursor.execute("BEGIN IMMEDIATE")`:
1. Purge expired leases: `DELETE FROM active_leases WHERE expires_at <= CURRENT_TIMESTAMP`.
2. Evaluate 10% exploration check (`random.random() < 0.10`):
   - Query unleased unattempted problems (`ORDER BY RANDOM() LIMIT 1`).
   - If empty, query all unattempted problems (`ORDER BY RANDOM() LIMIT 1`).
3. If not exploring or no unattempted problems found, evaluate exploitation query:
   - Primary: Query unleased candidates (`l.work_id IS NULL`) with bandit ordering.
   - Fallback: If 0 rows returned, query all candidates (omitting `l.work_id IS NULL`) with bandit ordering.
4. If no eligible problem exists in the database, commit/rollback and return `None`.
5. Generate `work_id = f"wu_{uuid.uuid4().hex[:12]}"`.
6. Calculate `expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=lease_seconds)`.
7. Insert lease into `active_leases`.
8. Commit transaction and return work dictionary.

#### SQL Query Structures

**Primary Exploitation Query (Unleased Candidates)**:
```sql
SELECT p.*
FROM problems p
LEFT JOIN active_leases l ON p.id = l.problem_id
WHERE LOWER(p.status) != 'proved_optimal' AND l.work_id IS NULL
ORDER BY
    -- Tier 1: Stuck backoff (stuck problems pushed behind non-stuck)
    CASE
        WHEN p.total_attempts > 50000
             AND (p.updated_at IS NULL OR p.updated_at < datetime('now', '-1 day'))
        THEN 1 ELSE 0
    END ASC,
    -- Tier 2: Closeness boost (problems within 1% of baseline record prioritized)
    CASE
        WHEN p.reference_s IS NOT NULL AND p.best_s IS NOT NULL AND p.reference_s > 0
             AND (abs(p.best_s - p.reference_s) / p.reference_s) <= 0.01
        THEN 0 ELSE 1
    END ASC,
    -- Tier 3: Exploration balancing (fewer attempts prioritized)
    p.total_attempts ASC,
    -- Tier 4: Geometric void space / density rank (highest void space prioritized)
    p.density_rank DESC,
    -- Tier 5: Random tie-breaker
    RANDOM()
LIMIT 1;
```

**Fallback Exploitation Query (When All Problems Are Leased)**:
```sql
SELECT p.*
FROM problems p
WHERE LOWER(p.status) != 'proved_optimal'
ORDER BY
    CASE
        WHEN p.total_attempts > 50000
             AND (p.updated_at IS NULL OR p.updated_at < datetime('now', '-1 day'))
        THEN 1 ELSE 0
    END ASC,
    CASE
        WHEN p.reference_s IS NOT NULL AND p.best_s IS NOT NULL AND p.reference_s > 0
             AND (abs(p.best_s - p.reference_s) / p.reference_s) <= 0.01
        THEN 0 ELSE 1
    END ASC,
    p.total_attempts ASC,
    p.density_rank DESC,
    RANDOM()
LIMIT 1;
```

**Exploration Query (10% Unattempted Family Selection)**:
```sql
SELECT p.*
FROM problems p
LEFT JOIN active_leases l ON p.id = l.problem_id
WHERE LOWER(p.status) != 'proved_optimal'
  AND (p.status = 'unattempted' OR p.total_attempts = 0)
  AND l.work_id IS NULL
ORDER BY RANDOM()
LIMIT 1;
```

---

### 2.3 Recommended Attempts Calculation Based on Cores

The recommended formula is:
$$\text{recommended\_attempts} = \max(1000, \min(c \times 1000, 20000)) \quad \text{where } c = \max(1, \text{int}(\text{cores}))$$

**Derivation and Rationale**:
1. **Per-Core Rate ($1,000 \text{ attempts/core}$)**:
   - In continuous geometry optimization, each attempt takes ~5–15 ms in `packer_rs`.
   - $1,000$ attempts take approximately 5–15 seconds per CPU core.
   - Because native workers divide the recommended attempts across all local worker threads (`attempts_per_core = recommended // cores`), every worker machine finishes its assigned batch in approximately the same wall-clock time (~5–15 seconds), regardless of whether it is a 1-core cloud node or a 16-core workstation.
2. **Floor ($1,000 \text{ attempts}$)**:
   - Prevents micro-leasing storms where workers request new leases every few hundred milliseconds, overloading coordinator HTTP endpoints.
   - Amortizes HTTP round-trip latency and SQLite transaction overhead.
3. **Cap ($20,000 \text{ attempts}$)**:
   - For high-core machines (32–128 cores), an uncapped allocation could take tens of thousands of attempts.
   - If a worker crashes or drops off the network, an excessively large attempt allocation would delay discovery.
   - The $20,000$ cap guarantees that high-core workers report back and submit heartbeats frequently within the 300-second lease window.
4. **Input Sanitization**:
   - If `cores` is negative, zero, non-numeric, or `None`, defaulting to $c = 1$ ensures safe execution:
     `max(1000, min(1 * 1000, 20000)) = 1000`.

---

## 3. Caveats

1. **`density_rank` Population**:
   - In `src/shape_packing/server/database.py:seed_problems_from_verification`, `density_rank` is currently inserted with the default value of `0.0`.
   - For `p.density_rank DESC` to differentiate between problems with equal attempt counts, `scheduler.py` can optionally compute $\rho = \frac{N \cdot A_{\text{inner}}}{A_{\text{container}}(s)}$ via a utility function (importing from `ranker.py:get_shape_area` or implementing a standalone polygon area formula) if desired, or `density_rank` can be backfilled during catalog seeding.
2. **Clock Skew between App and SQLite**:
   - SQLite evaluates `CURRENT_TIMESTAMP` and `datetime('now')` using system UTC.
   - When Python calculates `expires_at`, it must strictly use UTC (`datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")`) rather than local machine time to ensure consistent comparison in `WHERE expires_at <= CURRENT_TIMESTAMP`.
3. **Non-destructive Heartbeats**:
   - Heartbeats report `best_local_s`, but `record_heartbeat` must NEVER update `problems.best_s`. All solution record updates must go through `/api/v1/solutions` with full SAT verification to uphold mathematical integrity.

---

## 4. Conclusion

The Work Scheduler and Priority Allocator for Milestone 2 can be cleanly and robustly implemented in `src/shape_packing/server/scheduler.py` following these architectural decisions:
1. **Strict Exclusion**: Always exclude `LOWER(status) = 'proved_optimal'`.
2. **Two-Stage Leasing**: Prioritize unleased problems (`l.work_id IS NULL`), with automatic fallback to shared leasing when all eligible candidates are leased.
3. **$\epsilon$-Greedy Bandit**: $10\%$ uniform random exploration over unattempted candidates; $90\%$ exploitation scoring incorporating void space, closeness boost ($\le 1\%$), low attempt preference, and stuck backoff ($>50\text{k}$ attempts without improvement decaying priority).
4. **Concurrency Safety**: Wrap `assign_work` in `BEGIN IMMEDIATE` to prevent race conditions during lease allocation.
5. **Standardized Attempt Scaling**: Use `max(1000, min(max(1, int(cores)) * 1000, 20000))` to normalize worker lease cycle times across all hardware configurations.

---

## 5. Verification Method

To verify these findings and validate the implementation when Milestone 2 is built:
1. **Unit Test Suite**: Run `pytest tests/test_server_scheduler.py -v`.
   - Verify `assign_work` strictly ignores problems with `status = 'proved_optimal'`.
   - Verify lease expiry deletes stale leases and makes problems re-assignable.
   - Verify heartbeat updates both `problems.total_attempts` and `workers.total_attempts`.
2. **Concurrency Verification**:
   - Execute concurrent multi-threaded requests against `assign_work` using Python's `ThreadPoolExecutor` (e.g. 10 workers requesting tasks simultaneously) to ensure no duplicate leases are created while unleased problems exist.
3. **Bandit Policy Verification**:
   - Verify that when two problems are eligible, one close to record ($\le 1\%$) and one distant, the close problem is chosen first.
   - Verify that when a problem exceeds $50,000$ attempts without an improvement for 24h, it yields priority to an unattempted problem.
   - Verify that `recommended_attempts` matches:
     - 1 core $\to$ 1,000
     - 4 cores $\to$ 4,000
     - 16 cores $\to$ 16,000
     - 64 cores $\to$ 20,000
