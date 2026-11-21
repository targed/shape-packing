# Milestone 2 Investigation Report: Active Lease Lifecycle, Heartbeat Accounting, and Edge Cases

## 1. Observation

### 1.1 Database Schema and Existing Infrastructure
- **File**: `src/shape_packing/server/database.py`, lines 102–115:
  ```sql
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
- **File**: `src/shape_packing/server/database.py`, lines 137–144:
  `init_db` sets `PRAGMA foreign_keys = ON;`, `PRAGMA journal_mode = WAL;`, and `PRAGMA synchronous = NORMAL;`.
  Foreign key enforcement rejects any row inserted into `active_leases` whose `worker_id` does not exist in `workers` or whose `problem_id` does not exist in `problems`.

### 1.2 Deprecation of `utcnow()` in Python 3.14
- **Command**: `python -W error -c "import datetime; datetime.datetime.utcnow()"`
- **Result**:
  ```text
  Traceback (most recent call last):
    File "<string>", line 1, in <module>
      import datetime; datetime.datetime.utcnow()
                       ~~~~~~~~~~~~~~~~~~~~~~~~^^
  DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
  ```
- **Command**: `python -c "import datetime; print(datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))"`
- **Result**: Emits format `2026-11-20 23:27:19` without warnings.

### 1.3 SQLite Timestamp Representation and Comparison Pitfall
- SQLite `CURRENT_TIMESTAMP` and `datetime('now')` return a space-separated 19-character string: `'YYYY-MM-DD HH:MM:SS'`.
- **Command**: `python -c "import sqlite3; conn = sqlite3.connect(':memory:'); print(conn.execute(\"SELECT '2026-11-20T10:00:00' < '2026-11-20 12:00:00'\").fetchone())"`
- **Result**: `(0,)` (Evaluates to `False`!)
- **Mechanism**: In ASCII, `'T'` is code 84, whereas `' '` (space) is code 32. In SQLite lexical string comparisons, any timestamp with an ISO `'T'` separator evaluates as *greater* than a space-separated `CURRENT_TIMESTAMP`, breaking `<` expiration comparisons unless both sides strictly adhere to `%Y-%m-%d %H:%M:%S`.

### 1.4 SQLite Index Utilization for Lease Deletion
- **Command**: `EXPLAIN QUERY PLAN DELETE FROM active_leases WHERE expires_at < CURRENT_TIMESTAMP`
- **Result**: `SEARCH active_leases USING INDEX idx_active_leases_expires (expires_at<?)`
- When using direct string comparison `expires_at < CURRENT_TIMESTAMP`, SQLite utilizes the B-tree index `idx_active_leases_expires` ($O(\log N + K)$).
- Conversely, `EXPLAIN QUERY PLAN DELETE FROM active_leases WHERE datetime(expires_at) < CURRENT_TIMESTAMP` results in `SCAN active_leases` (full table scan), unless a functional index is created.

### 1.5 Specification and Plan Interfaces
- **Spec**: `docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md`, §4.4:
  `POST /api/v1/heartbeat`:
  Request Body: `{"worker_id": str, "work_id": str, "attempts_completed": int, "best_local_s": Optional[float]}`.
  Response: `{"status": "recorded", "total_worker_attempts": int}`.
- **Plan**: `docs/superpowers/plans/2026-11-20-distributed-shape-packing.md`, lines 314–318:
  Task 2 requires:
  - `assign_work(conn: sqlite3.Connection, worker_id: str, cores: int = 1, lease_seconds: int = 300) -> Optional[Dict[str, Any]]`
  - `record_heartbeat(conn: sqlite3.Connection, work_id: str, worker_id: str, attempts: int, best_s: Optional[float] = None) -> bool`
  - `expire_stale_leases(conn: sqlite3.Connection) -> int`
- **Plan**: lines 488–505:
  Minimal implementation updates `problems.total_attempts` if `active_leases` has `work_id`, and updates `workers.total_attempts` and `workers.last_seen_at`.

---

## 2. Logic Chain

### 2.1 Active Lease Lifecycle in SQLite
1. **Creation**:
   - `assign_work` must assign a non-optimal problem, generate a unique `work_id` (e.g. `f"wu_{uuid.uuid4().hex[:12]}"`), and insert into `active_leases`.
   - By Observation 1.1, `worker_id` must already exist in `workers` because foreign keys are enabled. If `worker_id` does not exist, an `IntegrityError` is thrown. Therefore, `assign_work` must validate `worker_id` upfront or handle the exception cleanly.
   - By Observation 1.2 and 1.3, Python 3.14 deprecates `utcnow()`, and SQLite requires space-separated `'YYYY-MM-DD HH:MM:SS'`. `expires_at` must be calculated as:
     `now = datetime.datetime.now(datetime.timezone.utc)`
     `expires_at = (now + datetime.timedelta(seconds=lease_seconds)).strftime("%Y-%m-%d %H:%M:%S")`
     (or calculated directly in SQL via `datetime('now', '+' || ? || ' seconds')`).
2. **Expiration (`expire_stale_leases`)**:
   - Query: `DELETE FROM active_leases WHERE expires_at < CURRENT_TIMESTAMP;`
   - By Observation 1.4, this query matches the index `idx_active_leases_expires` directly and executes as an indexed range deletion without a table scan.
   - Returning `cursor.rowcount` accurately reflects the number of expired leases deleted.
   - Running `expire_stale_leases(conn)` at the beginning of `assign_work` ensures that stale leases are purged immediately before querying available problems, maximizing allocation efficiency.

### 2.2 Heartbeat Accounting in `record_heartbeat`
1. **Contract and Validation**:
   - Signature: `record_heartbeat(conn, work_id, worker_id, attempts, best_s=None) -> bool`.
   - Validate `attempts`: must be an integer, non-boolean (`isinstance(attempts, int) and not isinstance(attempts, bool)`), and non-negative (`attempts >= 0`). Rejects negative counts, NaN, Inf.
   - If `attempts == 0`, it serves as a keepalive ping, refreshing `last_seen_at`.
2. **Lease Identification & Worker Authentication**:
   - Query: `SELECT problem_id, expires_at FROM active_leases WHERE work_id = ? AND worker_id = ?;`
   - Matching both `work_id` AND `worker_id` ensures that worker A cannot submit heartbeats or manipulate metrics for worker B's lease.
3. **Attempt Updates**:
   - If the lease exists and is active (`expires_at >= CURRENT_TIMESTAMP`):
     - Update problem: `UPDATE problems SET total_attempts = total_attempts + ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;`
   - If the lease is expired or not found:
     - Do not update `problems.total_attempts` (either because the problem ID is untracked or the lease is stale).
   - Worker update:
     - Update worker: `UPDATE workers SET total_attempts = total_attempts + ?, last_seen_at = CURRENT_TIMESTAMP WHERE id = ?;`
     - If the worker does not exist (`cursor.rowcount == 0`), return `False`.
4. **Transaction Safety**:
   - Under SQLite WAL mode, readers do not block writers, but concurrent write transactions must be serialized.
   - Following the tested pattern from `database.py` (`update_solution_record` and `seed_problems_from_verification`), wrapping `record_heartbeat` in `BEGIN IMMEDIATE` prevents reader-to-writer lock escalation deadlocks and guarantees atomic updates of problem and worker attempt tallies.

### 2.3 Edge Case Handling
1. **Worker Disconnection / Crash**:
   - A crashed worker stops sending heartbeats.
   - The lease remains in `active_leases` until `expires_at`.
   - When `expire_stale_leases` executes, the lease is deleted, releasing the problem back to the available pool.
   - All previously acknowledged heartbeats remain safely recorded in `problems.total_attempts` and `workers.total_attempts`.
   - Worker `last_seen_at` is preserved, allowing `/api/v1/stats` to identify inactive workers (`last_seen_at < datetime('now', '-15 minutes')`).
2. **Multiple Heartbeats for the Same `work_id`**:
   - The `attempts` parameter represents the incremental delta completed since the previous heartbeat.
   - Successive heartbeats monotonically increment `problems.total_attempts` and `workers.total_attempts`.
   - Default batch leases do not require sliding renewal because native workers run finite batches (1,000–20,000 attempts) and request new assignments upon completion.
3. **Stale Heartbeat After Lease Expiration**:
   - If `expires_at` has passed or the row was deleted:
     - Problem counter is NOT incremented (avoiding skewing multi-armed bandit statistics for reassigned problems).
     - Worker compute time is still credited in `workers.total_attempts`.
     - Returning `False` signals to the worker daemon that the lease has lapsed, prompting it to abort and request a new task.
   - Independent Geometric Validation: If a worker discovers a record improvement on an expired lease, `/api/v1/solutions` verifies geometry via SAT regardless of lease status. Physical geometric correctness is never rejected due to lease expiration.

---

## 3. Caveats
1. **Heartbeat Replay / Idempotency**: The `/api/v1/heartbeat` REST API contract does not include a transaction ID or monotonic sequence counter. If a client retries an HTTP POST due to a transient network timeout, attempts could be counted twice. Given that attempt counts are heuristic metrics for volunteer ranking and multi-armed bandit exploration weights, this is standard in distributed volunteer computing.
2. **In-Memory vs File-Backed SQLite**: In-memory databases (`:memory:`) do not support multiple independent process connections, though multi-threading with a shared connection or URI is supported. All production concurrency assumptions rely on WAL mode on file-backed SQLite.
3. **Lease Extension Policy**: The current specification does not specify sliding-window renewal (extending `expires_at` on heartbeat). If long-running tasks require lease extension in the future, `UPDATE active_leases SET expires_at = datetime('now', '+' || ? || ' seconds') WHERE work_id = ?` can be added without altering the public API.

---

## 4. Conclusion
1. **Lease Storage**: Store `expires_at` formatted strictly as `%Y-%m-%d %H:%M:%S` using `datetime.datetime.now(datetime.timezone.utc) + timedelta(...)` to avoid Python 3.14 deprecation warnings and ensure direct SQLite index usage (`idx_active_leases_expires`).
2. **Stale Lease Deletion**: `expire_stale_leases(conn)` must execute `DELETE FROM active_leases WHERE expires_at < CURRENT_TIMESTAMP` and return `cursor.rowcount`. It must be called at the start of `assign_work` and be available as a standalone maintenance function.
3. **Heartbeat Accounting**: `record_heartbeat` must:
   - Validate input parameters (`attempts >= 0` and integer).
   - Authenticate `(work_id, worker_id)` against `active_leases`.
   - Atomically increment `problems.total_attempts` (if lease active), `workers.total_attempts`, and update `workers.last_seen_at` inside `BEGIN IMMEDIATE`.
   - Return `True` on success, `False` if worker is unknown, input is invalid, or lease has expired.
4. **Edge Cases**: Disconnections are resolved cleanly by TTL expiration; multiple heartbeats report incremental deltas; stale heartbeats credit the worker while rejecting problem updates and notifying the client.

---

## 5. Verification Method

To verify these findings independently, execute the following commands in the workspace:

1. **Verify Python 3.14 Datetime Formatting without Warnings**:
   ```bash
   python -W error -c "import datetime; now = datetime.datetime.now(datetime.timezone.utc); exp = (now + datetime.timedelta(seconds=300)).strftime('%Y-%m-%d %H:%M:%S'); assert len(exp) == 19"
   ```

2. **Verify SQLite Expiry Index Plan**:
   ```bash
   python -c "
   import sqlite3
   conn = sqlite3.connect(':memory:')
   conn.execute('CREATE TABLE active_leases (work_id TEXT PRIMARY KEY, expires_at TIMESTAMP NOT NULL)')
   conn.execute('CREATE INDEX idx_active_leases_expires ON active_leases(expires_at)')
   plan = conn.execute('EXPLAIN QUERY PLAN DELETE FROM active_leases WHERE expires_at < CURRENT_TIMESTAMP').fetchall()
   assert any('idx_active_leases_expires' in str(step) for step in plan)
   print('Verified index usage:', plan)
   "
   ```

3. **Verify Existing Database Test Suite Integrity**:
   ```bash
   pytest tests/test_server_database.py -v
   ```

4. **Verify Concurrency Pattern with BEGIN IMMEDIATE**:
   ```bash
   pytest tests/test_server_database_concurrency.py -v -k "test_concurrent_conflicting_updates_single_problem"
   ```
