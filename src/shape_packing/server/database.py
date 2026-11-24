"""Coordinator database layer for distributed shape packing.

Implements SQLite storage in WAL mode storing problems, solution records,
registered volunteer workers, and active work leases.
"""
from __future__ import annotations

import glob
import json
import logging
import math
import os
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from ..catalog import (
    get_canonical_tokens,
    get_pair_tier,
    is_pair_supported,
    list_frontier_families,
    normalize_token,
)

logger = logging.getLogger(__name__)

# Minimum improvement delta required to break an existing solution record.
# Consistent with shape_packing.packing_config.RECORD_MIN_IMPROVEMENT.
RECORD_MIN_IMPROVEMENT: float = 1e-5

# Set of shape tokens supported by geometry kernels and solver engines.
SUPPORTED_SHAPES: Set[str] = get_canonical_tokens()

# Map shape tokens and aliases to canonical tokens recognized by geometry.py,
# solution_tools.py, and packer_rs.
CANONICAL_SHAPE_TOKENS: Dict[str, str] = {
    "3": "3",
    "TRIANGLE": "3",
    "TRI": "3",
    "4": "4",
    "SQUARE": "4",
    "SQU": "4",
    "5": "5",
    "PENTAGON": "5",
    "PEN": "5",
    "6": "6",
    "HEXAGON": "6",
    "HEX": "6",
    "7": "7",
    "HEPTAGON": "7",
    "HEP": "7",
    "8": "8",
    "OCTAGON": "8",
    "OCT": "8",
    "9": "9",
    "NONAGON": "9",
    "NON": "9",
    "ENNEAGON": "9",
    "10": "10",
    "DECAGON": "10",
    "DEC": "10",
    "CIRCLE": "CIRCLE",
    "CIR": "CIRCLE",
    "DOMINO": "DOMINO",
    "DOM": "DOMINO",
    "TAN": "TAN",
    "TANGRAM": "TAN",
    "L": "L",
    "LTROMINO": "L",
    "L-TROMINO": "L",
}

SCHEMA: str = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS problems (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    inner_token TEXT NOT NULL,
    container_token TEXT NOT NULL,
    n INTEGER NOT NULL CHECK (n > 0),
    best_s REAL CHECK (best_s IS NULL OR (best_s > 0 AND best_s < 1e999)),
    reference_s REAL CHECK (reference_s IS NULL OR (reference_s > 0 AND reference_s < 1e999)),
    status TEXT NOT NULL DEFAULT 'unattempted',
    total_attempts INTEGER DEFAULT 0,
    density_rank REAL DEFAULT 0.0,
    source_attribution TEXT,
    tier TEXT NOT NULL DEFAULT 'benchmark',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS solutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id TEXT NOT NULL REFERENCES problems(id),
    metric_s REAL NOT NULL CHECK (metric_s > 0 AND metric_s < 1e999),
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
CREATE INDEX IF NOT EXISTS idx_problems_tier_status ON problems(tier, status, total_attempts);
CREATE INDEX IF NOT EXISTS idx_workers_records_broken ON workers(records_broken DESC, total_attempts DESC);
"""


def normalize_shape_token(token: Any) -> str:
    """Normalize shape token to canonical format expected by solvers and verifiers."""
    if token is None:
        return ""
    s = str(token).strip().upper()
    if s in CANONICAL_SHAPE_TOKENS:
        return CANONICAL_SHAPE_TOKENS[s]
    return normalize_token(s)


def init_db(db_path: str = "data/distributed.db") -> sqlite3.Connection:
    """
    Initialize SQLite database with WAL mode and schema.

    Creates parent directory if it does not exist. Idempotent across multiple runs.
    """
    if db_path != ":memory:" and not db_path.startswith(":memory:") and not db_path.startswith("file:"):
        dirname = os.path.dirname(os.path.abspath(db_path))
        if dirname:
            os.makedirs(dirname, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")

    # Idempotent migration for pre-existing databases lacking the `tier` column
    existing_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='problems'"
    ).fetchone()
    if existing_table:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(problems)").fetchall()}
        if "tier" not in cols:
            conn.execute("ALTER TABLE problems ADD COLUMN tier TEXT NOT NULL DEFAULT 'benchmark'")
            conn.commit()

    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def register_worker(
    conn: sqlite3.Connection,
    username: str,
    client_type: str = "native",
    worker_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Register or update a worker handle and return registration details.

    Generates a UUID4 if worker_id is omitted or empty.
    Updates last_seen_at, username, and client_type if worker_id already exists.
    """
    w_id = str(worker_id).strip() if worker_id and str(worker_id).strip() else str(uuid.uuid4())
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO workers (id, username, client_type, last_seen_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            last_seen_at = CURRENT_TIMESTAMP,
            username = excluded.username,
            client_type = excluded.client_type
        """,
        (w_id, username, client_type),
    )
    conn.commit()
    return {"worker_id": w_id, "username": username, "client_type": client_type}


def get_problem(conn: sqlite3.Connection, problem_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve problem record by canonical problem identifier."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM problems WHERE id = ?", (problem_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    if hasattr(row, "keys"):
        return dict(row)
    col_names = [col[0] for col in cursor.description]
    return dict(zip(col_names, row))


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

    Must use BEGIN IMMEDIATE for atomic concurrency.
    Requires metric_s < current_best - RECORD_MIN_IMPROVEMENT (1e-5) to qualify.
    Updates solutions.is_current_record, problems.best_s, and workers.records_broken.
    """
    # 1. Validate connection and identifiers
    if not isinstance(conn, sqlite3.Connection):
        return False
    if not isinstance(problem_id, str) or not problem_id.strip():
        return False
    if not isinstance(worker_id, str) or not worker_id.strip():
        return False
    if not isinstance(username, str) or not username.strip():
        return False

    # 2. Validate metric_s: must be finite positive real number (reject bool, non-numeric, <= 0)
    if isinstance(metric_s, bool) or not isinstance(metric_s, (int, float)):
        return False
    if math.isnan(metric_s) or math.isinf(metric_s) or metric_s <= 0.0:
        return False

    # 3. Validate coordinates: must be non-empty sequence of finite real numbers (reject bool, NaN, Inf)
    if not isinstance(coordinates, (list, tuple)):
        return False
    if len(coordinates) == 0:
        return False
    for c in coordinates:
        if isinstance(c, bool) or not isinstance(c, (int, float)) or math.isnan(c) or math.isinf(c):
            return False

    coords_list = [float(c) for c in coordinates]

    if conn.in_transaction:
        conn.commit()

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

        # Demote previous active records for this problem
        cursor.execute(
            "UPDATE solutions SET is_current_record = 0 WHERE problem_id = ?",
            (problem_id,),
        )
        # Insert new record with verified flag and coordinates JSON
        cursor.execute(
            """
            INSERT INTO solutions (
                problem_id, metric_s, worker_username, worker_id, coordinates_json, is_current_record
            )
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (problem_id, float(metric_s), username, worker_id, json.dumps(coords_list, allow_nan=False)),
        )
        # Update problem's current best metric and timestamp
        cursor.execute(
            """
            UPDATE problems
            SET best_s = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (float(metric_s), problem_id),
        )
        # Update worker record break count and last seen
        cursor.execute(
            """
            INSERT INTO workers (id, username, client_type, records_broken, last_seen_at)
            VALUES (?, ?, 'native', 1, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                records_broken = workers.records_broken + 1,
                last_seen_at = CURRENT_TIMESTAMP,
                username = excluded.username
            """,
            (worker_id, username),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise


def seed_problems_from_verification(
    conn: sqlite3.Connection, verification_dir: str = "data/packingVerification"
) -> int:
    """
    Seed problems table from data/packingVerification/*.json.

    Normalizes shape tokens to canonical forms. Handles duplicate keys gracefully
    via ON CONFLICT(id) DO UPDATE without overwriting better live records.
    Tolerates corrupt or missing files.

    Returns the total number of items processed/upserted.
    """
    if not os.path.isdir(verification_dir):
        logger.warning("Verification directory '%s' does not exist.", verification_dir)
        return 0

    pattern = os.path.join(verification_dir, "*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        return 0

    rows: List[Tuple[str, str, str, int, Optional[float], Optional[float], str, str]] = []
    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                continue

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

                raw_status = item.get("status")
                clean_status = str(raw_status).strip().lower() if raw_status else ""

                if clean_status == "proved_optimal":
                    status = "proved_optimal"
                elif not is_pair_supported(inner, container):
                    status = "unsupported"
                elif raw_status:
                    status = str(raw_status)
                elif best_val is not None:
                    status = "best_known"
                else:
                    status = "unattempted"

                tier = str(item.get("tier") or get_pair_tier(inner, container) or "benchmark")
                note = str(item.get("source_note") or "")

                rows.append((our_problem, inner, container, n, best_val, best_val, status, note, tier))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to parse verification file %s: %s", file_path, exc)
            continue

    if not rows:
        return 0

    if conn.in_transaction:
        conn.commit()

    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        cursor.executemany(
            """
            INSERT INTO problems (
                id, inner_token, container_token, n, best_s, reference_s, status, source_attribution, tier
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                reference_s = excluded.reference_s,
                tier = excluded.tier,
                source_attribution = COALESCE(excluded.source_attribution, problems.source_attribution),
                status = CASE
                    WHEN problems.status = 'proved_optimal' THEN problems.status
                    WHEN excluded.status = 'proved_optimal' THEN excluded.status
                    ELSE excluded.status
                END,
                best_s = CASE
                    WHEN problems.best_s IS NULL THEN excluded.best_s
                    WHEN excluded.best_s IS NOT NULL AND excluded.best_s < problems.best_s THEN excluded.best_s
                    ELSE problems.best_s
                END
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise


def seed_frontier_problems(conn: sqlite3.Connection, max_n: int = 20) -> int:
    """
    Seed curated canonical quadrilateral Frontier families (tier='frontier', reference_s=NULL)
    for N=1..max_n across RHOMBUS, PARALLELOGRAM, and TRAPEZOID pairings.
    """
    if max_n <= 0:
        return 0

    rows: List[Tuple[str, str, str, int, str, str, str]] = []
    for _, inner, container in list_frontier_families():
        for n in range(1, max_n + 1):
            prob_id = f"{n}_{inner}_in_{container}"
            rows.append((prob_id, inner, container, n, "unattempted", "Frontier Canonical Baseline", "frontier"))

    if not rows:
        return 0

    if conn.in_transaction:
        conn.commit()

    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        cursor.executemany(
            """
            INSERT INTO problems (
                id, inner_token, container_token, n, status, source_attribution, tier
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                tier = excluded.tier,
                source_attribution = COALESCE(problems.source_attribution, excluded.source_attribution)
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise


def sync_records_to_db(
    conn: sqlite3.Connection,
    manifest_path: str = "data/records/manifest.json",
    records_dir: str = "data/records",
    results_dir: str = "data/results",
) -> int:
    """
    Sync verified world records from data/records/manifest.json into shape_packing.db.
    Ensures solutions table, problems.best_s, and worker attribution are consistent.
    """
    if not os.path.exists(manifest_path):
        return 0

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as exc:
        logger.warning("Could not read manifest at %s: %s", manifest_path, exc)
        return 0

    records = manifest.get("records", [])
    if not records:
        return 0

    if conn.in_transaction:
        conn.commit()

    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    inserted = 0
    try:
        for r in records:
            prob_str = r.get("problem", "")
            if not prob_str:
                continue
            parts = prob_str.split("_")
            try:
                n = int(parts[0])
            except (ValueError, IndexError):
                continue
            inner = normalize_shape_token(parts[1]) if len(parts) > 1 else ""
            container = normalize_shape_token(parts[3]) if len(parts) > 3 else ""

            row = cursor.execute(
                "SELECT id, best_s, reference_s FROM problems WHERE id = ?", (prob_str,)
            ).fetchone()
            if not row:
                row = cursor.execute(
                    "SELECT id, best_s, reference_s FROM problems WHERE n = ? AND inner_token = ? AND container_token = ?",
                    (n, inner, container),
                ).fetchone()

            if not row:
                continue

            prob_id = row[0]
            m_metric = float(r["metric"])

            sol_file = None
            cand1 = os.path.join(records_dir, f"{prob_str}/solution.json")
            if os.path.exists(cand1):
                sol_file = cand1
            else:
                for root, _, files in os.walk(records_dir):
                    if root.endswith(prob_str) and "solution.json" in files:
                        sol_file = os.path.join(root, "solution.json")
                        break
            if not sol_file and os.path.exists(results_dir):
                for root, _, files in os.walk(os.path.join(results_dir, prob_str)):
                    if "solution.json" in files:
                        sol_file = os.path.join(root, "solution.json")
                        break

            if not sol_file:
                continue

            try:
                with open(sol_file, "r", encoding="utf-8") as sf:
                    sol_data = json.load(sf)
                coords = sol_data.get("values", [])
            except Exception:
                continue

            existing = cursor.execute(
                "SELECT id, metric_s FROM solutions WHERE problem_id = ? AND is_current_record = 1",
                (prob_id,),
            ).fetchone()

            if existing:
                ex_id, ex_metric = existing
                if m_metric < ex_metric - 1e-5:
                    cursor.execute(
                        "UPDATE solutions SET is_current_record = 0 WHERE problem_id = ?",
                        (prob_id,),
                    )
                    cursor.execute(
                        """
                        INSERT INTO solutions (
                            problem_id, metric_s, worker_username, worker_id, coordinates_json, is_current_record, verified_at
                        ) VALUES (?, ?, 'local_solver', 'archive_node', ?, 1, datetime('now', '-1 day'))
                        """,
                        (prob_id, m_metric, json.dumps(coords)),
                    )
                    cursor.execute(
                        "UPDATE problems SET best_s = ? WHERE id = ?", (m_metric, prob_id)
                    )
                    inserted += 1
            else:
                cursor.execute(
                    """
                    INSERT INTO solutions (
                        problem_id, metric_s, worker_username, worker_id, coordinates_json, is_current_record, verified_at
                    ) VALUES (?, ?, 'local_solver', 'archive_node', ?, 1, datetime('now', '-2 days'))
                    """,
                    (prob_id, m_metric, json.dumps(coords)),
                )
                cursor.execute(
                    "UPDATE problems SET best_s = ? WHERE id = ?", (m_metric, prob_id)
                )
                inserted += 1

        archive_records = cursor.execute(
            "SELECT COUNT(*) FROM solutions WHERE worker_id = 'archive_node' AND is_current_record = 1"
        ).fetchone()[0]
        if archive_records > 0:
            cursor.execute(
                """
                INSERT INTO workers (id, username, client_type, records_broken, total_attempts, last_seen_at)
                VALUES ('archive_node', 'local_solver', 'native', ?, 100000, datetime('now', '-1 day'))
                ON CONFLICT(id) DO UPDATE SET records_broken = ?
                """,
                (archive_records, archive_records),
            )
        conn.commit()
        return inserted
    except Exception:
        conn.rollback()
        raise
