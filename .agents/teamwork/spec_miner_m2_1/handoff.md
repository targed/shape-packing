# Milestone 2 Specification Report: Work Scheduler and Priority Allocator

**Agent**: `spec_miner_m2_1`  
**Milestone**: Milestone 2: Work Scheduler and Priority Allocator  
**Target Module**: `src/shape_packing/server/scheduler.py`  
**Target Test Suite**: `tests/test_server_scheduler.py`  
**Date**: 2026-11-20T23:35:00Z  

---

## Executive Summary

This report defines the complete functional specification, interface contracts, return schemas, multi-armed bandit allocation policies, lease lifecycle mechanics, heartbeat accounting rules, input validation constraints, and comprehensive test requirements for **Milestone 2 (Task 2): Work Scheduler and Priority Allocator** in the Distributed Shape Packing project.

The scheduler acts as the coordinator's central resource allocator. Volunteer worker nodes request tasks over REST, and the scheduler selects packing instances to optimize network discovery probability across 2,249+ geometric configurations. The scheduler must enforce strict exclusion of mathematically proven optimal solutions, prioritize configurations by void space and record proximity, decay stuck problem weights, gracefully share workloads when worker supply exceeds unleased problems, safely manage lease expirations in SQLite WAL mode, and record compute progress without allowing unverified metrics to bypass geometric SAT validation.

---

## Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Work Leasing | `assign_work` | Assigns an active work lease to a registered worker based on multi-armed bandit priority scoring. Inserts record in `active_leases` table. | `conn: sqlite3.Connection`, `worker_id: str`, `cores: int = 1`, `lease_seconds: int = 300` | `Optional[Dict[str, Any]]` | Returns `None` if database is empty, contains only `proved_optimal` problems, or inputs are invalid. Auto-purges expired leases before selection. | `ORIGINAL_REQUEST.md` §R2, Design Spec §4.2, Plan Task 2 |
| 2 | Lease Management | `expire_stale_leases` | Prunes active leases whose `expires_at` timestamp has passed (`expires_at <= CURRENT_TIMESTAMP`), freeing expired problems for reassignment. | `conn: sqlite3.Connection` | `int` (count of deleted leases $\ge 0$) | Returns `0` if no leases expired. Operates atomically without raising exceptions on empty tables. | `ORIGINAL_REQUEST.md` §R2, Design Spec §5, Plan Task 2 |
| 3 | Telemetry & Accounting | `record_heartbeat` | Records progress batch attempts against the problem (if lease active) and credits cumulative worker compute and activity timestamp. | `conn: sqlite3.Connection`, `work_id: str`, `worker_id: str`, `attempts: int`, `best_s: Optional[float] = None` | `bool` (`True` if recorded successfully, `False` if validation fails) | Returns `False` on invalid arguments (`attempts < 0`, boolean types, empty IDs). Does NOT commit `best_s` to `problems.best_s`. | `ORIGINAL_REQUEST.md` §R2, Design Spec §4.4, Plan Task 2 |
| 4 | Constraint Enforcement | Proved Optimal Exclusion | Strictly excludes problems marked `proved_optimal` from work allocation under all stages (exploitation, exploration, fallback). | Problem table `status` | Filter in SQL queries (`LOWER(status) != 'proved_optimal'`) | If only `proved_optimal` problems exist in the database, `assign_work` returns `None`. | `ORIGINAL_REQUEST.md` §R2, Design Spec §5.1, Plan Task 2 |
| 5 | Resource Optimization | Hardware Attempt Scaling | Scales `recommended_attempts` per work assignment based on available worker cores to normalize batch completion duration (~5–15 sec). | `cores: int` | `recommended_attempts: int` in $[1000, 20000]$ | Clamps values: formula `max(1000, min(cores * 1000, 20000))`. Non-int or non-positive cores clamped to 1000. | Design Spec §4.2, Plan Task 2 line 467, Explorer 1 |
| 6 | Bandit Allocation | Geometric Void Space Priority | Prioritizes problems with lower packing density (greater void space) where $\rho = \frac{N \cdot A_{\text{inner}}}{A_{\text{container}}(s)}$, using `density_rank DESC`. | `problems.density_rank` | SQL `ORDER BY p.density_rank DESC` | Ties broken by random selection (`RANDOM()`). | Design Spec §5.2, `ranker.py:145`, Plan Task 2 |
| 7 | Bandit Allocation | Closeness-to-Record Boost | Boosts priority of problems whose current best metric $s$ is within 1% of historical baseline record ($\Delta \le 0.01$). | `best_s`, `reference_s` | Prioritized sorting tier | Problems with `abs(best_s - ref_s)/ref_s <= 0.01` prioritized before general search pool. | Design Spec §5.2 |
| 8 | Bandit Allocation | Stuck Problem Backoff | Decays priority weight by 50% (lower sorting tier) for problems with $>50,000$ cumulative attempts without improvement in 24 hours. | `total_attempts`, `updated_at` | Prioritized behind non-stuck problems | Automatically resets to normal priority once an improvement updates `updated_at`. | Design Spec §5.3 |
| 9 | Bandit Allocation | $\epsilon$-Greedy Exploration | Allocates 10% ($\epsilon = 0.10$) of work assignments uniformly at random across unattempted shape configurations. | `random.random() < 0.10` | Random unattempted problem | Falls back to normal exploitation if no unattempted problems remain in library. | Design Spec §5.3 |
| 10 | High-Concurrency | Stochastic Search Sharing | When all eligible problems have active leases, falls back to shared leasing on top non-optimal problems instead of starving workers. | Table state (`COUNT(unleased) = 0`) | Returns lease on top candidate | Workers execute stochastic search with different seeds without redundant work overlap. | Design Spec §5.1, Plan Task 2 line 444 |
| 11 | Concurrency Control | `BEGIN IMMEDIATE` Serialization | Wraps lease allocation and heartbeat transactions in immediate transactions to eliminate race conditions under concurrent worker load. | SQLite connection state | Atomic ACID transaction | Prevents double-leasing of unleased problems when multiple workers request work simultaneously. | Plan Task 1/2, Concurrency test suite, SQLite WAL specs |
| 12 | Foreign Key Safety | Worker Existence Handling | Ensures `worker_id` satisfies `REFERENCES workers(id)` on `active_leases` table under `PRAGMA foreign_keys = ON;`. | `worker_id` in `active_leases` | SQLite FK constraint | Either validates worker existence or auto-registers worker to avoid `sqlite3.IntegrityError`. | `database.py:65`, Explorer 2 findings |

---

## Edge Cases

| # | Feature | Input | Observed / Expected Behavior | Specification / Remediation |
|---|---------|-------|------------------------------|-----------------------------|
| 1 | `assign_work` | Empty database (0 problems) | No problems available in `problems` table | Return `None` cleanly (API returns HTTP 204 No Content). |
| 2 | `assign_work` | Database contains ONLY `proved_optimal` problems | All rows have `status = 'proved_optimal'` | Return `None` cleanly. Must NOT assign optimal configurations. |
| 3 | `assign_work` | Mixed statuses (`proved_optimal`, `best_known`, `unattempted`) | Worker requests assignment | SQL query filters `WHERE LOWER(status) != 'proved_optimal'`. Proved optimal problems are strictly skipped. |
| 4 | `assign_work` | All non-optimal problems are currently leased | Active leases exist for every candidate | Falls back to shared stochastic search: selects top non-optimal problem by `total_attempts ASC, RANDOM() LIMIT 1`, inserts new lease, and returns valid dictionary. |
| 5 | `assign_work` | Worker ID not pre-registered in `workers` table | `worker_id = "unregistered-uuid"` | Under `PRAGMA foreign_keys = ON`, direct insert into `active_leases` raises `sqlite3.IntegrityError: FOREIGN KEY constraint failed`. The implementation must either auto-upsert the worker into `workers` (`INSERT OR IGNORE INTO workers (id, username, client_type) VALUES (?, ?, 'native')`) or validate existence and return `None`. |
| 6 | `assign_work` | `worker_id` is empty string or pure whitespace (`""`, `"   "`) | Blank identifier | Return `None` (invalid identity). |
| 7 | `assign_work` | `worker_id` is `None` or non-string type | Non-string type | Return `None` gracefully without crashing. |
| 8 | `assign_work` | `cores = 0` or negative (`cores = -4`) | Invalid core count | Clamps to floor: `cores = 1`, resulting in `recommended_attempts = 1000`. |
| 9 | `assign_work` | `cores = 64` or `cores = 128` (high-end workstation) | Large core count | Clamps to ceiling: `recommended_attempts = 20000` (prevents oversized batches that delay heartbeats). |
| 10 | `assign_work` | `cores` passed as `bool` (`cores = True`) | Python `isinstance(True, int) == True` | Explicit check `not isinstance(cores, bool)`; normalize `True` to 1 or default. |
| 11 | `assign_work` | `lease_seconds <= 0` | Invalid lease duration | Clamp to minimum: `lease_seconds = max(1, lease_seconds)` or fallback to default `300`. |
| 12 | `assign_work` | Problem has `best_s = 3.4`, `reference_s = 3.5` | Target metric calculation | `target_s = float(prob["best_s"])` (return `3.4`). |
| 13 | `assign_work` | Problem has `best_s = None`, `reference_s = 3.5` | Target metric calculation | `target_s = float(prob["reference_s"])` (return `3.5`). |
| 14 | `assign_work` | Problem has `best_s = None`, `reference_s = None` | Target metric calculation | Fallback to default `10.0` (as positive float). |
| 15 | `expire_stale_leases` | Table `active_leases` is empty | No active leases | Executes deletion query safely, returns `0`. |
| 16 | `expire_stale_leases` | All active leases expire in future (`expires_at > CURRENT_TIMESTAMP`) | Active non-expired leases | Deletes 0 rows, all leases preserved, returns `0`. |
| 17 | `expire_stale_leases` | Multiple leases expired in past (`expires_at < CURRENT_TIMESTAMP`) | Stale leases present | Deletes all matching rows in single query, commits transaction, returns count $\ge 1$. |
| 18 | `expire_stale_leases` | Timestamp format contains ISO `'T'` separator | E.g. `'2026-11-20T10:00:00'` vs SQLite `CURRENT_TIMESTAMP` | In ASCII, `'T'` (84) > `' '` (32). Lexical string comparison `'2026-11-20T10:00:00' < '2026-11-20 17:00:00'` evaluates to FALSE! Timestamps MUST be stored as `'%Y-%m-%d %H:%M:%S'` or compared using `datetime(expires_at) <= CURRENT_TIMESTAMP`. |
| 19 | `record_heartbeat` | Active lease exists for `work_id` | Valid heartbeat | Updates `problems.total_attempts += attempts`, `workers.total_attempts += attempts`, `workers.last_seen_at = CURRENT_TIMESTAMP`, returns `True`. |
| 20 | `record_heartbeat` | Lease has expired and was removed from `active_leases` | Stale heartbeat / late flush | Problem attempts cannot be updated (no lease mapping), but worker's `total_attempts` and `last_seen_at` are still credited. Returns `True`. |
| 21 | `record_heartbeat` | `attempts = 0` (liveness ping) | Heartbeat without new search attempts | Updates `workers.last_seen_at = CURRENT_TIMESTAMP`, attempts remain unchanged, returns `True`. |
| 22 | `record_heartbeat` | `attempts < 0` (negative count, e.g. `-100`) | Corrupt or malicious counter | Rejects: returns `False`, database unchanged. |
| 23 | `record_heartbeat` | `attempts` is `bool` (`attempts = True`) | Boolean passed as int | Explicitly reject `isinstance(attempts, bool)`; returns `False`. |
| 24 | `record_heartbeat` | `attempts` is non-integer (`"500"`, `12.5`, `None`) | Type violation | Rejects: returns `False` without raising `TypeError`. |
| 25 | `record_heartbeat` | `work_id` or `worker_id` is empty string or pure whitespace | Blank identity | Rejects: returns `False`. |
| 26 | `record_heartbeat` | Heartbeat reports candidate `best_s = 2.0` on problem with `best_s = 3.5` | Worker attempts to commit solution via heartbeat | MUST NOT update `problems.best_s`! Solutions require Separating Axis Theorem (SAT) collision and boundary verification via `/api/v1/solutions`. Heartbeat `best_s` is purely informational telemetry. |
| 27 | `record_heartbeat` | Unregistered `worker_id` reports heartbeat | Worker not in `workers` table | In SQLite, `UPDATE workers ... WHERE id = ?` affects 0 rows. To ensure compute credit is recorded, either auto-upsert the worker or return `False` if worker is missing. |
| 28 | Concurrency | Two threads call `assign_work` simultaneously when 1 unleased problem exists | Race condition on lease creation | With `BEGIN IMMEDIATE`, Thread 1 locks and leases the problem. Thread 2 begins after commit, detects all problems are leased, and executes fallback shared lease without throwing errors or creating corrupt state. |
| 29 | Concurrency | Multiple threads call `record_heartbeat` simultaneously for same problem | Atomic increment race | `UPDATE ... SET total_attempts = total_attempts + ?` in SQLite WAL mode is atomic; all reported attempts are accurately preserved without lost updates. |

---

## 1. Observation

### 1.1 Direct Source Evidence and Document Audits

1. **Original User Request (`.agents/teamwork/ORIGINAL_REQUEST.md:18-20, 32-36, 46-48`)**:
   - *Requirement §R2*:
     > "Implement a multi-armed bandit scheduler in `src/shape_packing/server/scheduler.py` that leases problems to workers based on geometric void space (packing density), gap to records, and stuck problem backoff, while strictly excluding `proved_optimal` instances. Handle lease expiry and heartbeat accounting."
   - *Acceptance Criteria*:
     > "- SQLite database initializes tables with WAL mode enabled.  
     > - Work scheduler assigns non-optimal problems and recovers expired leases.  
     > - Heartbeat endpoint updates attempt tallies on both problem and worker records."
   - *Test Suite*:
     > "`pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_api.py tests/test_native_worker.py tests/test_distributed_e2e.py` passes with 0 failures."

2. **Orchestrator Project Plan (`.agents/teamwork/orchestrator_1/PROJECT.md:19-22, 48-52, 56, 70`)**:
   - *Milestone 2 Scope*: `scheduler.py`: bandit allocation, lease expiry, heartbeat accounting.
   - *Interface Contract*:
     ```python
     assign_work(conn: sqlite3.Connection, worker_id: str, cores: int, lease_seconds: int) -> Optional[Dict[str, Any]]
     record_heartbeat(conn: sqlite3.Connection, work_id: str, worker_id: str, attempts: int, best_s: Optional[float]) -> bool
     expire_stale_leases(conn: sqlite3.Connection) -> int
     ```
   - *REST API Payload Contract*:
     `GET /api/v1/work?worker_id={id}&cores={cores}` $\to$
     ```json
     {
       "work_id": str,
       "problem": str,
       "inner_token": str,
       "container_token": str,
       "n": int,
       "target_s": float,
       "recommended_attempts": int,
       "lease_seconds": int
     }
     ```

3. **Design Specification (`docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md:107-115, 215-230`)**:
   - *Active Leases DDL*:
     ```sql
     CREATE TABLE active_leases (
         work_id TEXT PRIMARY KEY,
         problem_id TEXT NOT NULL REFERENCES problems(id),
         worker_id TEXT NOT NULL REFERENCES workers(id),
         leased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
         expires_at TIMESTAMP NOT NULL
     );
     ```
   - *Bandit Policy (§5)*:
     - **Exclusion**: Exclude configurations marked `proved_optimal`. Exclude problems currently leased to active workers unless all candidates are leased.
     - **Exploitation Scoring**: Rank by geometric void space ($\rho = \frac{N \cdot A_{\text{inner}}}{A_{\text{container}}(s)}$) and closeness to baseline record ($\le 1\%$ receives boost).
     - **Exploration and Stuck Backoff**: $>50,000$ attempts without improvement decays priority weight by 50% for 24 hours. 10% of assignments picked uniformly at random from unattempted shape families.

4. **Implementation Plan Task 2 Scaffold (`docs/superpowers/plans/2026-11-20-distributed-shape-packing.md:306-519`)**:
   - Confirms default parameter values: `cores: int = 1`, `lease_seconds: int = 300`, `best_s: Optional[float] = None`.
   - Confirms attempt formula: `recommended = max(1000, min(cores * 1000, 20000))`.
   - Confirms work unit identifier generation pattern: `f"wu_{uuid.uuid4().hex[:12]}"`.
   - Outlines initial unit tests: `test_assign_work_skips_proved_optimal`, `test_lease_expiry_reassigns_problem`, `test_record_heartbeat`.

5. **Existing Codebase State (`src/shape_packing/server/database.py`)**:
   - `SCHEMA` has foreign keys enabled (`PRAGMA foreign_keys = ON;`).
   - `active_leases` references `problems(id)` and `workers(id)`.
   - `problems` table has `status TEXT NOT NULL DEFAULT 'unattempted'`, `best_s REAL`, `reference_s REAL`, `density_rank REAL DEFAULT 0.0`, `total_attempts INTEGER DEFAULT 0`.
   - `update_solution_record` executes `BEGIN IMMEDIATE` to ensure concurrency serialization.

6. **Empirical SQLite Probing Results**:
   - Probing revealed: Inserting into `active_leases` with a `worker_id` not present in `workers` table immediately raises `sqlite3.IntegrityError: FOREIGN KEY constraint failed` when foreign keys are active.
   - Probing revealed: SQLite string comparison `'2026-11-20T10:00:00' < '2026-11-20 17:00:00'` evaluates to `0` (False) because ASCII `'T'` (84) > ASCII `' '` (32). Therefore, all stored timestamps must use `%Y-%m-%d %H:%M:%S` format to ensure correct expiration comparisons with SQLite's `CURRENT_TIMESTAMP`.

---

## 2. Logic Chain

### 2.1 Multi-Armed Bandit Scheduling Pipeline

The goal of the scheduler is to maximize the expected probability of discovering record-breaking shape packings while ensuring fair distribution of volunteer compute resources. The allocation pipeline operates in four logical steps:

```
                  ┌────────────────────────────────────────┐
                  │ Worker Requests Work                   │
                  │ (worker_id, cores, lease_seconds)      │
                  └───────────────────┬────────────────────┘
                                      │
                                      ▼
                  ┌────────────────────────────────────────┐
                  │ 1. Purge Expired Leases                │
                  │ DELETE WHERE expires_at <= CURRENT_TIME│
                  └───────────────────┬────────────────────┘
                                      │
                                      ▼
                  ┌────────────────────────────────────────┐
                  │ 2. Exploration Check (10% Probability) │
                  │ Uniform random pick from unattempted   │
                  │ configurations (excluding optimal)     │
                  └─────────┬───────────────────┬──────────┘
           Hit (10%)        │                   │ Miss (90%)
           ┌────────────────┘                   │
           ▼                                    ▼
┌──────────────────────────┐   ┌────────────────────────────────────────┐
│ Pick Random Unattempted  │   │ 3. Exploitation Scoring                │
│ Candidate (Unleased 1st) │   │ - Exclude status = 'proved_optimal'    │
└──────────┬───────────────┘   │ - Tier 1: Stuck Backoff (>50k, >24h)   │
           │                   │ - Tier 2: Closeness Boost (gap <= 1%)  │
           │                   │ - Tier 3: Least Attempts (Fairness)    │
           │                   │ - Tier 4: Void Space (density_rank)    │
           │                   │ - Prefer unleased; fallback to shared  │
           │                   └───────────────────┬────────────────────┘
           │                                       │
           └───────────────────┬───────────────────┘
                               │
                               ▼
                  ┌────────────────────────────────────────┐
                  │ 4. Issue Work Lease                    │
                  │ - Insert into active_leases            │
                  │ - Calculate recommended_attempts       │
                  │ - Return Schema Dictionary             │
                  └────────────────────────────────────────┘
```

#### Step 1: Strict Ineligibility Gate
Any problem with `LOWER(status) = 'proved_optimal'` must be strictly excluded from every query. In mathematical shape packing, proved optimal packings cannot be improved. Allocating volunteer CPU cycles to them produces zero marginal value.

#### Step 2: $\epsilon$-Greedy Exploration ($\epsilon = 0.10$)
10% of assignments are selected uniformly at random from problems where `status = 'unattempted'` or `total_attempts = 0`.
- Priority is given to unleased unattempted candidates.
- If all unattempted problems are currently leased, it falls back to leased unattempted candidates.
- If no unattempted problems exist in the entire database, the scheduler seamlessly falls back to the exploitation stage.

#### Step 3: Multi-Armed Bandit Exploitation Scoring
When not exploring, the scheduler evaluates eligible non-`proved_optimal` candidates:
1. **Unleased Candidate Preference**: Candidates with `l.work_id IS NULL` are prioritized over currently leased candidates.
2. **Stuck Backoff (Tier 1)**: If a problem has accumulated $>50,000$ attempts and has not had an improvement recorded in the last 24 hours (`p.updated_at < datetime('now', '-1 day')`), it is penalized to the lowest sorting priority. Once a new record is discovered, `database.py:update_solution_record` sets `updated_at = CURRENT_TIMESTAMP`, automatically clearing the stuck penalty.
3. **Closeness Boost (Tier 2)**: If $p.\text{best\_s}$ is within 1% of the baseline historical record ($\frac{|p.\text{best\_s} - p.\text{reference\_s}|}{p.\text{reference\_s}} \le 0.01$), the problem receives an allocation boost.
4. **Attempt Balancing (Tier 3)**: Problems with fewer total attempts (`p.total_attempts ASC`) are prioritized to prevent worker starvation and promote balanced search coverage.
5. **Geometric Void Space (Tier 4)**: Problems with higher void space / lower packing density (`p.density_rank DESC`) are prioritized.
6. **Tie-Breaker (Tier 5)**: `RANDOM()` provides uniform stochastic distribution among equally ranked problems.

#### Step 4: Fallback to Stochastic Search Sharing
If all eligible non-optimal problems in the database are currently leased, the scheduler does not refuse work. Because continuous shape packing uses stochastic local search with independent random seeds, multiple workers executing parallel searches on the same problem do not duplicate effort. The scheduler falls back to selecting from all non-optimal candidates using the bandit scoring order.

---

### 2.2 Lease Expiration and Time Synchronization

1. **Storage Format**: Timestamps in SQLite must be stored in UTC format without the `'T'` or `'Z'` characters:
   `YYYY-MM-DD HH:MM:SS`
   This is computed in Python via:
   ```python
   expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=lease_seconds)
   expires_at_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")
   ```
   Or computed directly in SQL:
   `datetime('now', '+' || ? || ' seconds')`
2. **Reclamation Query**:
   `expire_stale_leases` deletes expired leases using:
   ```sql
   DELETE FROM active_leases WHERE expires_at <= CURRENT_TIMESTAMP;
   ```
   Calling this function at the start of `assign_work` guarantees that stale leases are immediately cleaned up and made available for reassignment.

---

### 2.3 Heartbeat Accounting and Telemetry Boundaries

1. **Problem Attempt Accounting**:
   When a heartbeat arrives with `attempts > 0`:
   - It queries `SELECT problem_id FROM active_leases WHERE work_id = ?`.
   - If the lease is active, `problems.total_attempts` is incremented:
     ```sql
     UPDATE problems SET total_attempts = total_attempts + ? WHERE id = ?;
     ```
2. **Worker Compute Accounting**:
   Regardless of whether the lease is still active (e.g. if the worker submitted a delayed heartbeat after the lease expired):
   - The worker's `total_attempts` is incremented.
   - The worker's `last_seen_at` is updated to `CURRENT_TIMESTAMP`.
   This ensures volunteer contributors always receive full credit on the public leaderboard.
3. **Telemetry Boundary (IRON RULE)**:
   The `record_heartbeat` interface accepts `best_s: Optional[float] = None`.
   **The scheduler must NEVER update `problems.best_s` from a heartbeat.**
   All candidate solution improvements MUST be submitted through `POST /api/v1/solutions` and undergo in-process Separating Axis Theorem (SAT) collision and boundary verification via `src/shape_packing/solution_tools.py:verify_solution`. Allowing heartbeat telemetry to update records would create an unverified data corruption vector.

---

## 3. Return Dictionary Schema for `assign_work`

When `assign_work` identifies an eligible problem and issues a lease, it returns a dictionary with **exactly 8 keys**:

```python
{
    "work_id": str,
    "problem": str,
    "inner_token": str,
    "container_token": str,
    "n": int,
    "target_s": float,
    "recommended_attempts": int,
    "lease_seconds": int,
}
```

### Detailed Field Specifications

| Key | Type | Description | Constraints & Fallback Rules | Example |
|-----|------|-------------|------------------------------|---------|
| `work_id` | `str` | Unique lease identifier generated per assignment | Non-empty string. Format: `f"wu_{uuid.uuid4().hex[:12]}"` | `"wu_7a8f9b0c1d2e"` |
| `problem` | `str` | Canonical problem identifier | Matches `problems.id` foreign key. Must not be empty. | `"14_TAN_in_circle"` |
| `inner_token` | `str` | Token representing the inner shape | Matches canonical shape token (e.g. `"TAN"`, `"3"`, `"DOMINO"`). | `"TAN"` |
| `container_token` | `str` | Token representing the container shape | Matches canonical container token (e.g. `"CIRCLE"`, `"4"`, `"6"`). | `"CIRCLE"` |
| `n` | `int` | Number of inner shapes to pack | Strictly positive integer ($N \ge 1$). | `14` |
| `target_s` | `float` | Target container metric to beat | Strictly positive finite float. Value rule: `prob["best_s"]` if not `None`, else `prob["reference_s"]` if not `None`, else fallback `10.0`. | `2.8451203` |
| `recommended_attempts` | `int` | Recommended search attempts for worker batch | Bounded integer in range $[1000, 20000]$. Formula: `max(1000, min(cores * 1000, 20000))`. | `4000` |
| `lease_seconds` | `int` | Duration of active lease in seconds | Strictly positive integer. Default: `300`. Clamped: $\ge 1$. | `300` |

---

## 4. Input Validation and Security Specifications

### 4.1 `assign_work` Validation Rules
1. `conn`: Must be an active `sqlite3.Connection`. Returns `None` if invalid or disconnected.
2. `worker_id`:
   - Must be an instance of `str`. Reject `None`, `int`, `dict`, etc. $\to$ return `None`.
   - Must not be empty or pure whitespace (`not worker_id.strip()`) $\to$ return `None`.
   - **Foreign Key Invariant**: To satisfy `REFERENCES workers(id)` on `active_leases`:
     The scheduler must ensure the worker exists in `workers` table before inserting the lease:
     ```sql
     INSERT OR IGNORE INTO workers (id, username, client_type) VALUES (?, ?, 'native');
     ```
3. `cores`:
   - Must not be `bool` (reject `isinstance(cores, bool)`).
   - If `cores` is negative, zero, or non-int: clamp or default to 1.
   - Clamping logic: `c = max(1, int(cores))` followed by `recommended_attempts = max(1000, min(c * 1000, 20000))`.
4. `lease_seconds`:
   - Must not be `bool`.
   - If $\le 0$ or non-int: clamp to `max(1, int(lease_seconds))` or default to 300.

### 4.2 `record_heartbeat` Validation Rules
1. `conn`: Must be an active `sqlite3.Connection`. Returns `False` if invalid.
2. `work_id` & `worker_id`:
   - Must be non-empty strings. If `None`, non-str, or whitespace-only $\to$ return `False`.
3. `attempts`:
   - Must be an `int`.
   - **Strict Type Check**: Must reject boolean values (`if isinstance(attempts, bool): return False`).
   - Must be non-negative: `attempts < 0` $\to$ return `False`.
   - `attempts == 0` is valid (represents a liveness ping without new search iterations).
4. `best_s`:
   - If provided, must be a finite positive float (`isinstance(best_s, (int, float)) and not math.isnan(best_s) and not math.isinf(best_s) and best_s > 0`). Reject invalid types or non-positive values gracefully.
   - Must never update `problems.best_s`.
5. Worker Existence:
   - If `worker_id` does not exist in `workers`, execute upsert:
     ```sql
     INSERT INTO workers (id, username, client_type, total_attempts, last_seen_at)
     VALUES (?, ?, 'native', ?, CURRENT_TIMESTAMP)
     ON CONFLICT(id) DO UPDATE SET
         total_attempts = workers.total_attempts + excluded.total_attempts,
         last_seen_at = CURRENT_TIMESTAMP;
     ```

### 4.3 `expire_stale_leases` Validation Rules
1. `conn`: Must be an active `sqlite3.Connection`. Returns `0` if invalid.
2. Must execute inside an immediate or autocommit transaction to ensure atomic lease reclamation across concurrent worker threads.

---

## 5. Required Unit and Integration Tests (`tests/test_server_scheduler.py`)

The test suite for Milestone 2 must be created at `tests/test_server_scheduler.py` and contain the following tests:

### Group 1: Interface & Schema Conformance
1. `test_assign_work_schema_compliance`: Verify returned dictionary contains exactly the 8 required keys with exact expected types.
2. `test_assign_work_recommended_attempts_bounds`:
   - `cores = 1` $\to 1,000$
   - `cores = 4` $\to 4,000$
   - `cores = 8` $\to 8,000$
   - `cores = 20` $\to 20,000$
   - `cores = 64` $\to 20,000$ (capped)
   - `cores = 0` $\to 1,000$ (floored)
   - `cores = -3` $\to 1,000$ (floored)
3. `test_assign_work_target_s_fallback`:
   - When `best_s` is present: `target_s == best_s`.
   - When `best_s` is None and `reference_s` is present: `target_s == reference_s`.
   - When both are None: `target_s == 10.0`.
4. `test_assign_work_custom_lease_seconds`: Verify `lease_seconds=600` is reflected in both the return dictionary and the database `expires_at` column.

### Group 2: Constraint & Allocation Policies
5. `test_assign_work_skips_proved_optimal`: Populate database with `proved_optimal` and `best_known` problems. Verify `assign_work` strictly never assigns `proved_optimal`.
6. `test_assign_work_returns_none_when_only_proved_optimal`: Database containing only `proved_optimal` problems returns `None`.
7. `test_assign_work_returns_none_when_db_empty`: Empty database returns `None`.
8. `test_assign_work_excludes_currently_leased`: Worker 1 leases Problem A. Worker 2 requests work; receives Problem B, not Problem A.
9. `test_assign_work_fallback_sharing_when_all_leased`: Database has 2 problems. Worker 1 and Worker 2 lease both. Worker 3 requests work; receives a shared lease on an eligible problem rather than `None`.
10. `test_assign_work_priority_least_attempts_first`: Problem with `total_attempts = 0` is prioritized over problem with `total_attempts = 5000`.
11. `test_assign_work_priority_density_rank`: When attempt counts are equal, problem with higher `density_rank` is prioritized.
12. `test_assign_work_priority_closeness_boost`: Problem whose `best_s` is within 1% of `reference_s` is prioritized over distant problem.
13. `test_assign_work_stuck_backoff`: Problem with $>50,000$ attempts and `updated_at < datetime('now', '-1 day')` yields priority to newer problems.
14. `test_assign_work_exploration_unattempted_selection`: When exploration triggers, unattempted problems are chosen.

### Group 3: Lease Lifecycle & Expiration
15. `test_expire_stale_leases_empty`: Returns `0` on empty `active_leases`.
16. `test_expire_stale_leases_future_intact`: Leases expiring in future are preserved; returns `0`.
17. `test_expire_stale_leases_past_deleted`: Stale leases in the past are purged; returns exact count deleted.
18. `test_assign_work_auto_expires_stale_leases`: Calling `assign_work` automatically purges expired leases and reassigns the freed problem.

### Group 4: Heartbeat & Telemetry Accounting
19. `test_record_heartbeat_updates_problem_and_worker_attempts`: Verifies both `problems.total_attempts` and `workers.total_attempts` increment by reported attempts.
20. `test_record_heartbeat_updates_worker_last_seen`: Verifies `workers.last_seen_at` is updated to current timestamp.
21. `test_record_heartbeat_multiple_cumulative`: Verifies sequential heartbeats of 2000 and 3500 accumulate to 5500 on problem and worker.
22. `test_record_heartbeat_zero_attempts_liveness`: Zero attempts ping succeeds, updates `last_seen_at`, total attempts unchanged.
23. `test_record_heartbeat_after_lease_expired`: Worker attempts still credited even if lease has already been expired and deleted.
24. `test_record_heartbeat_does_not_modify_best_s`: Calling `record_heartbeat` with lower `best_s` leaves `problems.best_s` unchanged.

### Group 5: Input Validation & Defensive Edge Cases
25. `test_assign_work_invalid_worker_id`: Passing `None`, `""`, `"   "`, or numbers returns `None`.
26. `test_assign_work_unregistered_worker_auto_registration`: Calling `assign_work` with new `worker_id` does not violate foreign keys.
27. `test_record_heartbeat_negative_attempts_rejected`: `attempts = -50` returns `False`.
28. `test_record_heartbeat_bool_attempts_rejected`: `attempts = True` returns `False`.
29. `test_record_heartbeat_non_int_attempts_rejected`: `attempts = "100"` or `10.5` returns `False`.
30. `test_record_heartbeat_invalid_identifiers`: Empty strings or `None` for `work_id` or `worker_id` return `False`.

### Group 6: Concurrency & Thread Safety
31. `test_concurrent_work_assignment_no_duplicates`: 10 concurrent threads call `assign_work` on a database with 10 unleased problems. Each worker receives a distinct problem with zero collisions.
32. `test_concurrent_heartbeats_no_lost_updates`: 10 concurrent threads send 100 attempts each for the same problem and worker; final count on both is exactly 1,000.
33. `test_concurrent_expire_and_assign`: Threads simultaneously expiring leases and requesting assignments execute without deadlocks.

---

## 5-Component Handoff Report

### 1. Observation
- **Authoritative Files Inspected**:
  - `ORIGINAL_REQUEST.md:18-20, 32-36`: Mandates SQLite WAL mode, multi-armed bandit scheduler, lease expiry, heartbeat accounting, and strictly excluding `proved_optimal`.
  - `orchestrator_1/PROJECT.md:48-52, 56`: Specifies exact interface signatures between `scheduler.py` and `app.py`.
  - `docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md:107-115, 215-230`: Defines `active_leases` table schema, exclusion rules, exploration/exploitation bandit weights, and heartbeat telemetry.
  - `docs/superpowers/plans/2026-11-20-distributed-shape-packing.md:306-519`: Defines Task 2 reference implementation, recommended attempts formula `max(1000, min(cores * 1000, 20000))`, and test fixtures.
  - `src/shape_packing/server/database.py:62-115, 137-144`: Confirms `PRAGMA foreign_keys = ON;` and index structure.
  - `tests/test_server_database_concurrency.py:1-40`: Proves importance of `BEGIN IMMEDIATE` transaction serialization in SQLite WAL mode.
- **Direct Empirical Verification**:
  - Python SQLite driver test confirmed: Unregistered `worker_id` inserted into `active_leases` triggers `sqlite3.IntegrityError: FOREIGN KEY constraint failed`.
  - Python SQLite driver test confirmed: Comparing timestamps with ISO `'T'` separator against SQLite's `CURRENT_TIMESTAMP` fails on same-day comparisons due to ASCII lexical sorting. Format must be `'%Y-%m-%d %H:%M:%S'`.

### 2. Logic Chain
1. *Observation*: The coordinator REST API (`app.py`) delegates all work allocation, lease checking, and attempt accounting directly to `scheduler.py`.
2. *Inference*: `scheduler.py` must expose three clean functions: `assign_work`, `record_heartbeat`, and `expire_stale_leases`.
3. *Observation*: Volunteer machines vary from single-core cloud instances to 64-core multi-socket servers.
4. *Inference*: `recommended_attempts` must be normalized using `max(1000, min(cores * 1000, 20000))` so all machines complete batches in ~5–15 seconds while avoiding micro-leasing request storms.
5. *Observation*: Shape packing is stochastic; running multiple workers with different random seeds on the same problem does not duplicate work.
6. *Inference*: When worker demand exceeds unleased problems, the scheduler must fall back to shared leasing on top non-optimal problems instead of returning `None` and starving volunteers.
7. *Observation*: `record_heartbeat` receives `best_s`, but `ORIGINAL_REQUEST.md` requires all records to be verified mathematically with SAT non-overlap checks.
8. *Inference*: `record_heartbeat` must never update `problems.best_s`; `best_s` updates belong exclusively to `update_solution_record` after geometric verification.

### 3. Caveats
1. **Clock Synchronization**: Python's `datetime.datetime.now(datetime.timezone.utc)` and SQLite's `CURRENT_TIMESTAMP` both rely on the system clock. Storing UTC timestamps without timezone offset strings (i.e. `%Y-%m-%d %H:%M:%S`) ensures 100% interoperability with SQLite datetime functions.
2. **Transaction Isolation**: In Python's `sqlite3`, starting an explicit transaction when one is already open can raise `sqlite3.OperationalError`. The scheduler should check `if conn.in_transaction: conn.commit()` before executing `BEGIN IMMEDIATE`.
3. **Density Rank Pre-population**: If `problems.density_rank` is 0.0 (the default from seed data), the query `ORDER BY p.density_rank DESC` will treat all problems equally for void space until density rank values are calculated or backfilled.

### 4. Conclusion
Milestone 2 requires implementing `src/shape_packing/server/scheduler.py` with:
1. `assign_work(conn, worker_id, cores=1, lease_seconds=300) -> Optional[Dict[str, Any]]` returning the 8-key dictionary (`work_id`, `problem`, `inner_token`, `container_token`, `n`, `target_s`, `recommended_attempts`, `lease_seconds`).
2. `record_heartbeat(conn, work_id, worker_id, attempts, best_s=None) -> bool` updating problem and worker total attempts while keeping `problems.best_s` strictly untouched.
3. `expire_stale_leases(conn) -> int` deleting expired leases and returning the deletion count.
4. Comprehensive test suite in `tests/test_server_scheduler.py` covering all 33 specified unit, edge case, and concurrency tests.

### 5. Verification Method
1. **Failing Test Scaffold**:
   Create `tests/test_server_scheduler.py` and run `pytest tests/test_server_scheduler.py -v`. Confirm failure with `ModuleNotFoundError: No module named 'shape_packing.server.scheduler'`.
2. **Implementation Verification**:
   Implement `src/shape_packing/server/scheduler.py` adhering to all constraints. Run `pytest tests/test_server_scheduler.py -v` and confirm 100% pass rate.
3. **Regression Suite**:
   Run full test suite:
   `pytest tests/test_server_database.py tests/test_server_database_concurrency.py tests/test_server_database_stress.py tests/test_server_scheduler.py -v`
   Verify 0 failures.
