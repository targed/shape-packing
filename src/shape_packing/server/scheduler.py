"""Work scheduler and priority allocator for distributed shape packing coordinator.

Implements multi-armed bandit scheduling to allocate problem leases to volunteer
workers, handles active lease lifecycles and expiration, and records progress heartbeats.
"""
from __future__ import annotations

import datetime
import logging
import math
import random
import sqlite3
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def expire_stale_leases(conn: sqlite3.Connection) -> int:
    """
    Delete expired leases from active_leases where expires_at <= CURRENT_TIMESTAMP.

    Returns the count of pruned stale leases.
    """
    if not isinstance(conn, sqlite3.Connection):
        return 0

    if conn.in_transaction:
        conn.commit()

    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        cursor.execute("DELETE FROM active_leases WHERE expires_at <= CURRENT_TIMESTAMP")
        deleted = cursor.rowcount
        conn.commit()
        return max(0, deleted or 0)
    except Exception:
        conn.rollback()
        raise


def assign_work(
    conn: sqlite3.Connection,
    worker_id: str,
    cores: int = 1,
    lease_seconds: int = 300,
) -> Optional[Dict[str, Any]]:
    """
    Lease a problem to a worker using a multi-armed bandit allocation policy.

    Parameters:
    - conn: Active SQLite connection in WAL mode.
    - worker_id: Identifier of the requesting worker node.
    - cores: Hardware cores available to worker (scales batch attempt recommendation).
    - lease_seconds: Lease validity duration (default 300s).

    Returns:
    - Dictionary with 8 keys describing the work unit, or None if no eligible problems exist.
    """
    if not isinstance(conn, sqlite3.Connection):
        return None
    if not isinstance(worker_id, str) or not worker_id.strip():
        return None

    clean_worker_id = worker_id.strip()

    MAX_LEASE_SECONDS = 604800  # 7 days max lease duration

    # Normalize cores and calculate recommended attempts: max(1000, min(cores * 1000, 20000))
    if isinstance(cores, bool) or not isinstance(cores, int):
        try:
            c = max(1, int(cores))
        except (ValueError, TypeError, OverflowError):
            c = 1
    else:
        c = max(1, cores)
    recommended_attempts = max(1000, min(c * 1000, 20000))

    # Normalize lease_seconds
    if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int):
        try:
            ls = min(max(1, int(lease_seconds)), MAX_LEASE_SECONDS)
        except (ValueError, TypeError, OverflowError):
            ls = 300
    else:
        ls = min(max(1, lease_seconds), MAX_LEASE_SECONDS)

    # Automatically purge stale leases before querying problem availability
    expire_stale_leases(conn)

    if conn.in_transaction:
        conn.commit()

    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        # Auto-register worker or ensure worker_id exists in workers table before inserting lease
        cursor.execute(
            """
            INSERT INTO workers (id, username, client_type, last_seen_at)
            VALUES (?, ?, 'native', CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET last_seen_at = CURRENT_TIMESTAMP
            """,
            (clean_worker_id, clean_worker_id),
        )

        prob = None
        # 10% Probability exploration stage over unattempted shape configurations
        if random.random() < 0.10:
            # First attempt unleased unattempted candidates
            cursor.execute(
                """
                SELECT p.*
                FROM problems p
                LEFT JOIN active_leases l ON p.id = l.problem_id
                WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'
                  AND (p.status = 'unattempted' OR p.total_attempts = 0)
                  AND l.work_id IS NULL
                ORDER BY RANDOM()
                LIMIT 1
                """
            )
            prob = cursor.fetchone()

        # 90% Exploitation scoring stage (or fall-through if no unattempted candidates exist)
        if prob is None:
            # Primary: unleased non-proved_optimal candidates
            cursor.execute(
                """
                SELECT p.*
                FROM problems p
                LEFT JOIN active_leases l ON p.id = l.problem_id
                WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'
                  AND l.work_id IS NULL
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
                LIMIT 1
                """
            )
            prob = cursor.fetchone()

            # Fallback: if all eligible candidates are currently leased, fall back to shared leasing
            if prob is None:
                cursor.execute(
                    """
                    SELECT p.*
                    FROM problems p
                    WHERE COALESCE(LOWER(p.status), '') != 'proved_optimal'
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
                    LIMIT 1
                    """
                )
                prob = cursor.fetchone()

        if prob is None:
            conn.rollback()
            return None

        # Convert row to dictionary for robust field access
        if hasattr(prob, "keys"):
            prob_dict = dict(prob)
        else:
            col_names = [col[0] for col in cursor.description]
            prob_dict = dict(zip(col_names, prob))

        best_s = prob_dict.get("best_s")
        ref_s = prob_dict.get("reference_s")
        if best_s is not None:
            target_s = float(best_s)
        elif ref_s is not None:
            target_s = float(ref_s)
        else:
            target_s = 10.0

        work_id = f"wu_{uuid.uuid4().hex[:12]}"
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        expires_at_dt = now_utc + datetime.timedelta(seconds=ls)
        expires_at_str = expires_at_dt.strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """
            INSERT INTO active_leases (work_id, problem_id, worker_id, leased_at, expires_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
            """,
            (work_id, prob_dict["id"], clean_worker_id, expires_at_str),
        )
        conn.commit()

        return {
            "work_id": work_id,
            "problem": prob_dict["id"],
            "inner_token": prob_dict["inner_token"],
            "container_token": prob_dict["container_token"],
            "n": int(prob_dict["n"]),
            "target_s": float(target_s),
            "recommended_attempts": int(recommended_attempts),
            "lease_seconds": int(ls),
        }
    except Exception:
        conn.rollback()
        raise


def record_heartbeat(
    conn: sqlite3.Connection,
    work_id: str,
    worker_id: str,
    attempts: int,
    best_s: Optional[float] = None,
) -> bool:
    """
    Record search progress and telemetry from an active work lease.

    Parameters:
    - conn: Active SQLite connection.
    - work_id: Work unit identifier from assign_work.
    - worker_id: Reporting worker identifier.
    - attempts: Incremental count of search attempts completed (must be integer >= 0).
    - best_s: Optional local candidate metric (telemetry only; NEVER updates problems.best_s).

    Returns:
    - True if progress recorded against active lease;
    - False if lease not found / expired (worker compute is still credited) or input invalid.
    """
    if not isinstance(conn, sqlite3.Connection):
        return False
    if not isinstance(work_id, str) or not work_id.strip():
        return False
    if not isinstance(worker_id, str) or not worker_id.strip():
        return False

    # attempts must be integer >= 0, within signed 64-bit int bounds, and not boolean
    if (
        isinstance(attempts, bool)
        or not isinstance(attempts, int)
        or attempts < 0
        or attempts > 2**63 - 1
    ):
        return False

    # Validate best_s if provided: must be finite positive float <= 1e308
    if best_s is not None:
        if isinstance(best_s, bool) or not isinstance(best_s, (int, float)):
            return False
        try:
            f_best_s = float(best_s)
        except (ValueError, TypeError, OverflowError):
            return False
        if math.isnan(f_best_s) or math.isinf(f_best_s) or f_best_s <= 0.0 or f_best_s > 1e308:
            return False

    clean_work_id = work_id.strip()
    clean_worker_id = worker_id.strip()

    if conn.in_transaction:
        conn.commit()

    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        # Check active_leases for matching lease
        cursor.execute(
            """
            SELECT problem_id, expires_at
            FROM active_leases
            WHERE work_id = ? AND worker_id = ?
            """,
            (clean_work_id, clean_worker_id),
        )
        lease_row = cursor.fetchone()

        # Update workers: total_attempts += attempts, last_seen_at = CURRENT_TIMESTAMP
        cursor.execute(
            """
            INSERT INTO workers (id, username, client_type, total_attempts, last_seen_at)
            VALUES (?, ?, 'native', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                total_attempts = workers.total_attempts + excluded.total_attempts,
                last_seen_at = CURRENT_TIMESTAMP
            """,
            (clean_worker_id, clean_worker_id, attempts),
        )

        if lease_row is None:
            conn.commit()
            return False

        # Verify lease is still active (expires_at > CURRENT_TIMESTAMP)
        cursor.execute(
            """
            SELECT 1
            FROM active_leases
            WHERE work_id = ? AND worker_id = ? AND expires_at > CURRENT_TIMESTAMP
            """,
            (clean_work_id, clean_worker_id),
        )
        is_active = cursor.fetchone() is not None

        if is_active:
            prob_id = lease_row["problem_id"] if hasattr(lease_row, "keys") else lease_row[0]
            cursor.execute(
                """
                UPDATE problems
                SET total_attempts = total_attempts + ?
                WHERE id = ?
                """,
                (attempts, prob_id),
            )
            conn.commit()
            return True
        else:
            conn.commit()
            return False
    except Exception:
        conn.rollback()
        raise
