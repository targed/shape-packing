"""
Coordinator FastAPI application for distributed 2D shape packing.

Exposes REST API endpoints for:
- Worker node registration
- Work unit leasing via multi-armed bandit scheduler
- In-process geometric SAT verification and atomic solution commit
- Worker heartbeat and telemetry reporting
- Leaderboard ranking and global cluster statistics
- Problem metadata and active record coordinates
"""

from __future__ import annotations

import hmac
import json
import logging
import math
import os
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Generator, List, Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from .database import (
    RECORD_MIN_IMPROVEMENT,
    SUPPORTED_SHAPES,
    get_problem,
    init_db,
    register_worker,
    sync_problem_catalog,
    sync_records_to_db,
    update_solution_record,
    verify_worker_secret,
)
from .scheduler import assign_work, record_heartbeat
from .security import (
    BodySizeLimitMiddleware,
    SecurityHeadersMiddleware,
    TTLCache,
    TokenBucketRateLimiter,
    get_client_ip,
)
from ..solution_tools import (
    Solution,
    inverse_friedman_metric,
    verify_solution_obj,
)
from ..catalog import is_pair_supported, is_problem_enabled

logger = logging.getLogger(__name__)


class WorkerRegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    client_type: Literal["native", "wasm", "python"] = "native"
    worker_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("username")
    @classmethod
    def _clean_username(cls, v: str) -> str:
        cleaned = "".join(ch for ch in v.strip() if ord(ch) >= 32 and ch != "\x7f")
        if not cleaned:
            raise ValueError("Username cannot be empty")
        return cleaned[:64]


class WorkerDeregisterRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=64)


class SolutionSubmitRequest(BaseModel):
    work_id: Optional[str] = Field(default=None, max_length=64)
    worker_id: str = Field(..., min_length=1, max_length=64)
    problem: str = Field(..., min_length=1, max_length=80)
    s: float = Field(..., gt=0.0, le=1e12)
    coordinates: List[float] = Field(..., min_length=3, max_length=600)


class HeartbeatRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=64)
    work_id: str = Field(..., min_length=1, max_length=64)
    attempts_completed: int = Field(..., ge=0, le=50_000)
    best_local_s: Optional[float] = Field(default=None, gt=0.0, le=1e12)


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    return token or None


def _require_worker_auth(conn: sqlite3.Connection, worker_id: str, authorization: Optional[str]) -> None:
    token = _extract_bearer(authorization)
    if not verify_worker_secret(conn, worker_id, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing worker credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _enforce_rate_limit(limiter: TokenBucketRateLimiter, key: str) -> None:
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


def get_db(request: Request) -> Generator[sqlite3.Connection, None, None]:
    """
    FastAPI dependency yielding a thread-isolated SQLite connection.
    Schema initialization runs once at startup lifespan.
    """
    db_path = getattr(request.app.state, "db_path", "shape_packing.db")
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    try:
        yield conn
    finally:
        conn.close()


def create_app(db_path: str = "shape_packing.db", auto_seed: bool = False) -> FastAPI:
    """
    Factory creating a FastAPI coordinator service instance.

    Initializes database tables and WAL configuration on startup.
    When auto_seed=True, migrates legacy IDs and seeds Benchmark + Frontier problems.
    """
    if (
        db_path != ":memory:"
        and not db_path.startswith("file:")
        and not os.path.exists(db_path)
        and os.path.abspath(db_path) != os.path.abspath("shape_packing.db")
        and os.path.exists("shape_packing.db")
    ):
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.copy2("shape_packing.db", db_path)

    def _bootstrap_db() -> None:
        init_conn = init_db(db_path)
        try:
            if auto_seed:
                sync_problem_catalog(init_conn)
            sync_records_to_db(init_conn)
        except Exception as exc:
            logger.warning("Startup DB sync warning: %s", exc)
        finally:
            init_conn.close()

    _bootstrap_db()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    enable_docs = os.environ.get("SHAPE_PACKING_ENABLE_DOCS", "0") == "1"
    app = FastAPI(
        title="Distributed Shape Packing Coordinator",
        description="REST API for coordinating continuous geometric shape-packing optimization.",
        version="1.0.0",
        docs_url="/docs" if enable_docs else None,
        redoc_url="/redoc" if enable_docs else None,
        openapi_url="/openapi.json" if enable_docs else None,
        lifespan=lifespan,
    )
    app.state.db_path = db_path

    default_origins = [
        "https://targed.github.io",
        "https://erich-friedman.github.io",
        "http://localhost:4321",
        "http://127.0.0.1:4321",
    ]
    extra_origins = [
        o.strip()
        for o in os.environ.get("SHAPE_PACKING_ALLOWED_ORIGINS", "").split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=default_origins + extra_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.add_middleware(
        BodySizeLimitMiddleware,
        path_limits={
            "/api/v1/solutions": 65_536,
            "/api/v1/workers/register": 8_192,
            "/api/v1/workers/deregister": 4_096,
            "/api/v1/heartbeat": 8_192,
            "/api/v1/work/heartbeat": 8_192,
        },
        default_limit=16_384,
    )
    app.add_middleware(SecurityHeadersMiddleware)

    # Donor-friendly rate limiters & 10s read cache
    register_ip_limiter = TokenBucketRateLimiter(rate_per_sec=10.0 / 60.0, capacity=20.0)
    work_worker_limiter = TokenBucketRateLimiter(rate_per_sec=20.0 / 60.0, capacity=6.0)
    work_ip_limiter = TokenBucketRateLimiter(rate_per_sec=600.0 / 60.0, capacity=120.0)
    solution_worker_limiter = TokenBucketRateLimiter(rate_per_sec=10.0 / 60.0, capacity=5.0)
    solution_ip_limiter = TokenBucketRateLimiter(rate_per_sec=60.0 / 60.0, capacity=15.0)
    read_ip_limiter = TokenBucketRateLimiter(rate_per_sec=120.0 / 60.0, capacity=40.0)
    export_limiter = TokenBucketRateLimiter(rate_per_sec=1.0 / 60.0, capacity=2.0)
    read_cache = TTLCache(ttl_seconds=10.0, max_items=128)

    @app.post("/api/v1/workers/register", status_code=status.HTTP_200_OK)
    def register(
        req: WorkerRegisterRequest,
        request: Request,
        authorization: Optional[str] = Header(None),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Dict[str, Any]:
        """Register or update a worker node handle and issue a per-worker bearer secret."""
        _enforce_rate_limit(register_ip_limiter, f"reg:{get_client_ip(request)}")
        clean_worker_id = req.worker_id.strip() if req.worker_id and req.worker_id.strip() else None

        result = register_worker(
            conn,
            username=req.username,
            client_type=req.client_type,
            worker_id=clean_worker_id,
            presented_secret=_extract_bearer(authorization),
            require_secret_on_existing=True,
        )
        return {
            "worker_id": result["worker_id"],
            "worker_secret": result["worker_secret"],
            "username": result["username"],
            "client_type": result["client_type"],
            "status": "registered",
        }

    @app.post("/api/v1/workers/deregister", status_code=status.HTTP_200_OK)
    def deregister(
        req: WorkerDeregisterRequest,
        authorization: Optional[str] = Header(None),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Dict[str, Any]:
        """Mark worker node as offline and clear its active leases on graceful shutdown."""
        clean_worker_id = req.worker_id.strip() if req.worker_id else ""
        if clean_worker_id:
            _require_worker_auth(conn, clean_worker_id, authorization)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE workers SET last_seen_at = datetime('now', '-10 minutes') WHERE id = ?",
                (clean_worker_id,),
            )
            cursor.execute(
                "DELETE FROM active_leases WHERE worker_id = ?",
                (clean_worker_id,),
            )
            conn.commit()
        return {"status": "deregistered"}

    @app.get("/api/v1/work")
    def get_work(
        request: Request,
        worker_id: str = Query(..., min_length=1, max_length=64),
        cores: int = Query(1, ge=1, le=128),
        lease_seconds: int = Query(300, ge=1, le=1800),
        tier: Optional[str] = Query(None),
        authorization: Optional[str] = Header(None),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Any:
        """
        Lease a work unit via the multi-armed bandit scheduler.
        Returns HTTP 204 No Content with an empty body when no work is available.
        """
        clean_worker_id = worker_id.strip() if worker_id else ""
        if not clean_worker_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="worker_id cannot be empty",
            )
        _require_worker_auth(conn, clean_worker_id, authorization)
        _enforce_rate_limit(work_worker_limiter, f"work_w:{clean_worker_id}")
        _enforce_rate_limit(work_ip_limiter, f"work_ip:{get_client_ip(request)}")

        assignment = assign_work(
            conn,
            worker_id=clean_worker_id,
            cores=cores,
            lease_seconds=lease_seconds,
            tier_filter=tier,
        )
        if assignment is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        assignment["timeout_seconds"] = assignment["lease_seconds"]
        return assignment

    @app.post("/api/v1/solutions", status_code=status.HTTP_200_OK)
    def submit_solution(
        req: SolutionSubmitRequest,
        request: Request,
        authorization: Optional[str] = Header(None),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Any:
        """
        In-process geometric SAT verification and atomic solution commit.
        """
        clean_worker_id = req.worker_id.strip() if req.worker_id else ""
        if not clean_worker_id:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"status": "rejected", "verified": False, "message": "worker_id cannot be empty"},
            )

        _require_worker_auth(conn, clean_worker_id, authorization)
        _enforce_rate_limit(solution_worker_limiter, f"sol_w:{clean_worker_id}")
        _enforce_rate_limit(solution_ip_limiter, f"sol_ip:{get_client_ip(request)}")

        if math.isnan(req.s) or math.isinf(req.s) or req.s <= 0.0 or req.s > 1e12:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"status": "rejected", "verified": False, "message": "Metric s must be finite and within bounds."},
            )

        prob = get_problem(conn, req.problem)
        if not prob:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Problem not found",
            )

        prob_status = str(prob.get("status") or "").lower()
        if prob_status in ("proved_optimal", "unsupported"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"status": "rejected", "verified": False, "message": f"Problem is closed ({prob_status})."},
            )

        n_shapes = int(prob["n"])
        expected_coords = n_shapes * 3
        if len(req.coordinates) != expected_coords:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"status": "rejected", "verified": False, "message": f"Expected {expected_coords} coordinates (3 * N)."},
            )

        for idx, val in enumerate(req.coordinates):
            if math.isnan(val) or math.isinf(val) or abs(val) > 1e9:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"status": "rejected", "verified": False, "message": f"Coordinate at index {idx} is invalid."},
                )

        inner_token = prob["inner_token"]
        container_token = prob["container_token"]
        if not is_pair_supported(inner_token, container_token) or not is_problem_enabled(req.problem, inner_token, container_token):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"status": "rejected", "verified": False, "message": "Shape problem is disabled or unsupported."},
            )

        # Cheap pre-SAT rejection: do not burn F1 CPU verifying non-improving candidates
        current_best = prob.get("best_s")
        if current_best is not None and req.s >= (float(current_best) - RECORD_MIN_IMPROVEMENT):
            return {
                "status": "duplicate",
                "verified": False,
                "is_new_record": False,
                "metric_s": req.s,
                "previous_best_s": current_best,
                "message": "Not lower than current best record.",
            }

        try:
            solver_s = inverse_friedman_metric(req.s, inner_token, container_token)
            sol_obj = Solution(
                path="<api>",
                N=n_shapes,
                inner_token=inner_token,
                container_token=container_token,
                S=float(solver_s),
                final_metric=float(req.s),
                values=[float(c) for c in req.coordinates],
            )
            res = verify_solution_obj(sol_obj, problem_str=req.problem, check_record=False, fast_fail=True)
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"status": "rejected", "verified": False, "message": "Geometric verification failed."},
            )

        if not res.valid:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"status": "rejected", "verified": False, "message": f"Geometric verification failed: {res.message[:200]}"},
            )

        cursor = conn.cursor()
        cursor.execute("SELECT username FROM workers WHERE id = ?", (clean_worker_id,))
        w_row = cursor.fetchone()
        username = (w_row["username"] if hasattr(w_row, "keys") else w_row[0]) if w_row else clean_worker_id

        improved = update_solution_record(
            conn=conn,
            problem_id=req.problem,
            worker_id=clean_worker_id,
            username=username,
            metric_s=res.metric,
            coordinates=req.coordinates,
        )
        if improved:
            read_cache.clear()

        return {
            "status": "accepted" if improved else "duplicate",
            "verified": True,
            "is_new_record": improved,
            "metric_s": res.metric,
            "previous_best_s": prob["best_s"],
            "message": "New world record registered! Rank updated." if improved else "Valid packing, but not lower than current best",
        }

    @app.post("/api/v1/heartbeat", status_code=status.HTTP_200_OK)
    @app.post("/api/v1/work/heartbeat", status_code=status.HTTP_200_OK)
    def heartbeat(
        req: HeartbeatRequest,
        request: Request,
        authorization: Optional[str] = Header(None),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Dict[str, Any]:
        """Record heartbeat and compute attempts for an active lease."""
        clean_worker_id = req.worker_id.strip() if req.worker_id else ""
        clean_work_id = req.work_id.strip() if req.work_id else ""
        if not clean_worker_id or not clean_work_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Identifiers cannot be empty",
            )
        _require_worker_auth(conn, clean_worker_id, authorization)
        _enforce_rate_limit(work_worker_limiter, f"hb_w:{clean_worker_id}")
        _enforce_rate_limit(work_ip_limiter, f"hb_ip:{get_client_ip(request)}")

        success = record_heartbeat(
            conn,
            work_id=clean_work_id,
            worker_id=clean_worker_id,
            attempts=req.attempts_completed,
            best_s=req.best_local_s,
            require_existing_lease=True,
        )

        cursor = conn.cursor()
        cursor.execute("SELECT total_attempts FROM workers WHERE id = ?", (clean_worker_id,))
        w_row = cursor.fetchone()
        total_attempts = (
            w_row["total_attempts"] if w_row and hasattr(w_row, "keys") else (w_row[0] if w_row else 0)
        )

        return {
            "status": "recorded" if success else "ignored",
            "total_worker_attempts": total_attempts,
        }

    @app.get("/api/v1/stats", status_code=status.HTTP_200_OK)
    def get_stats(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> Dict[str, Any]:
        """Return cluster-wide summary statistics."""
        _enforce_rate_limit(read_ip_limiter, f"read:{get_client_ip(request)}")
        cached = read_cache.get("stats")
        if cached is not None:
            return cached

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM problems")
        total_probs = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM workers")
        total_workers = cursor.fetchone()[0]

        # Active workers: nodes that checked in or heartbeat within the last 2 minutes
        cursor.execute(
            """
            SELECT COUNT(*) FROM workers
            WHERE last_seen_at >= datetime('now', '-2 minutes')
            """
        )
        active_workers = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(total_attempts), 0) FROM problems")
        total_attempts = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM solutions")
        total_solutions = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(records_broken), 0) FROM workers")
        records_broken = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(tier, 'benchmark'), COUNT(*) FROM problems GROUP BY COALESCE(tier, 'benchmark')")
        tier_counts = {row[0]: row[1] for row in cursor.fetchall()}

        payload = {
            "total_problems": total_probs,
            "tier_counts": tier_counts,
            "active_workers": active_workers,
            "total_workers": total_workers,
            "total_attempts": total_attempts,
            "records_broken": records_broken,
            "verified_solutions": total_solutions,
        }
        read_cache.set("stats", payload)
        return payload

    @app.get("/api/v1/problems", status_code=status.HTTP_200_OK)
    def list_problems(
        tier: Optional[str] = Query(None),
        problem_status: Optional[str] = Query(None, alias="status"),
        inner: Optional[str] = Query(None),
        container: Optional[str] = Query(None),
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Dict[str, Any]:
        """List defined problems in the coordinator database with optional tier/shape filters."""
        where_clauses = []
        params: List[Any] = []
        if tier:
            where_clauses.append("LOWER(COALESCE(tier, 'benchmark')) = ?")
            params.append(tier.strip().lower())
        if problem_status:
            where_clauses.append("LOWER(COALESCE(status, '')) = ?")
            params.append(problem_status.strip().lower())
        if inner:
            where_clauses.append("UPPER(inner_token) = ?")
            params.append(inner.strip().upper())
        if container:
            where_clauses.append("UPPER(container_token) = ?")
            params.append(container.strip().upper())

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        cursor = conn.cursor()
        total = cursor.execute(f"SELECT COUNT(*) FROM problems {where_sql}", params).fetchone()[0]
        rows = cursor.execute(
            f"""
            SELECT id, inner_token, container_token, n, best_s, reference_s, status, tier, total_attempts
            FROM problems {where_sql}
            ORDER BY tier ASC, inner_token ASC, container_token ASC, n ASC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()
        items = [dict(r) if hasattr(r, "keys") else {
            "id": r[0], "inner_token": r[1], "container_token": r[2], "n": r[3],
            "best_s": r[4], "reference_s": r[5], "status": r[6], "tier": r[7], "total_attempts": r[8],
        } for r in rows]
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    @app.get("/api/v1/leaderboard", status_code=status.HTTP_200_OK)
    def get_leaderboard(
        request: Request,
        limit: int = Query(50, ge=1, le=500),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> List[Dict[str, Any]]:
        """Return contributor leaderboard ranked by records broken and attempts."""
        _enforce_rate_limit(read_ip_limiter, f"read:{get_client_ip(request)}")
        cache_key = f"leaderboard:{limit}"
        cached = read_cache.get(cache_key)
        if cached is not None:
            return cached

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                username, 
                COALESCE(SUM(total_attempts), 0) AS total_attempts, 
                COALESCE(SUM(records_broken), 0) AS records_broken
            FROM workers
            GROUP BY username
            ORDER BY records_broken DESC, total_attempts DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        payload = [
            {
                "username": r["username"] if hasattr(r, "keys") else r[0],
                "total_attempts": r["total_attempts"] if hasattr(r, "keys") else r[1],
                "records_broken": r["records_broken"] if hasattr(r, "keys") else r[2],
            }
            for r in rows
        ]
        read_cache.set(cache_key, payload)
        return payload

    @app.get("/api/v1/recent_solutions", status_code=status.HTTP_200_OK)
    def get_recent_solutions(
        request: Request,
        limit: int = Query(20, ge=1, le=100),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> List[Dict[str, Any]]:
        """Return the most recently verified packing solutions in descending order."""
        _enforce_rate_limit(read_ip_limiter, f"read:{get_client_ip(request)}")
        cache_key = f"recent:{limit}"
        cached = read_cache.get(cache_key)
        if cached is not None:
            return cached
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                s.id,
                s.problem_id,
                s.metric_s,
                s.worker_username,
                s.verified_at,
                s.is_current_record,
                p.n,
                p.inner_token,
                p.container_token,
                p.reference_s,
                p.status
            FROM solutions s
            LEFT JOIN problems p ON s.problem_id = p.id
            ORDER BY s.verified_at DESC, s.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        results = []
        for r in rows:
            prob_id = r["problem_id"] if hasattr(r, "keys") else r[1]
            metric_s = float(r["metric_s"] if hasattr(r, "keys") else r[2])
            worker_username = r["worker_username"] if hasattr(r, "keys") else r[3]
            verified_at = r["verified_at"] if hasattr(r, "keys") else r[4]
            is_record = bool(r["is_current_record"] if hasattr(r, "keys") else r[5])
            n = r["n"] if hasattr(r, "keys") else r[6]
            inner_token = r["inner_token"] if hasattr(r, "keys") else r[7]
            container_token = r["container_token"] if hasattr(r, "keys") else r[8]
            ref_s = r["reference_s"] if hasattr(r, "keys") else r[9]
            diff = (metric_s - float(ref_s)) if (ref_s is not None) else None

            results.append({
                "id": r["id"] if hasattr(r, "keys") else r[0],
                "problem_id": prob_id,
                "n": n,
                "inner_token": inner_token,
                "container_token": container_token,
                "metric_s": round(metric_s, 6),
                "reference_s": round(float(ref_s), 6) if ref_s is not None else None,
                "diff": round(diff, 6) if diff is not None else None,
                "is_current_record": is_record,
                "worker_username": worker_username,
                "verified_at": str(verified_at),
            })
        return results

    @app.get("/api/v1/problems/{problem_id}", status_code=status.HTTP_200_OK)
    def get_problem_detail(
        problem_id: str,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Dict[str, Any]:
        """Retrieve problem metadata and current record coordinates."""
        prob = get_problem(conn, problem_id)
        if not prob:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Problem '{problem_id}' not found",
            )

        cursor = conn.cursor()
        cursor.execute(
            "SELECT coordinates_json FROM solutions WHERE problem_id = ? AND is_current_record = 1",
            (problem_id,),
        )
        sol_row = cursor.fetchone()
        if sol_row:
            raw_coords = sol_row["coordinates_json"] if hasattr(sol_row, "keys") else sol_row[0]
            try:
                prob["coordinates"] = json.loads(raw_coords) if raw_coords else None
            except Exception:
                prob["coordinates"] = None
        else:
            prob["coordinates"] = None

        return prob

    @app.get("/api/v1/export/db", status_code=status.HTTP_200_OK)
    def export_database_snapshot(
        request: Request,
        authorization: Optional[str] = Header(None),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> StreamingResponse:
        """Create and stream an atomic online SQLite backup snapshot of the coordinator DB."""
        expected_token = os.environ.get("SHAPE_PACKING_BACKUP_TOKEN", "").strip()
        allow_unauth = os.environ.get("SHAPE_PACKING_ALLOW_UNAUTH_EXPORT", "0") == "1"
        if not expected_token:
            if not allow_unauth:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Database export token is not configured",
                )
        else:
            supplied = _extract_bearer(authorization)
            if not supplied or not hmac.compare_digest(supplied, expected_token):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid backup token")
        _enforce_rate_limit(export_limiter, f"export:{get_client_ip(request)}")

        fd, tmp_path = tempfile.mkstemp(prefix="shape_packing_backup_", suffix=".db")
        os.close(fd)
        dest_conn = sqlite3.connect(tmp_path)
        try:
            conn.backup(dest_conn)
        finally:
            dest_conn.close()

        def _stream_and_cleanup():
            try:
                with open(tmp_path, "rb") as f:
                    while True:
                        chunk = f.read(65_536)
                        if not chunk:
                            break
                        yield chunk
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        return StreamingResponse(
            _stream_and_cleanup(),
            media_type="application/x-sqlite3",
            headers={"Content-Disposition": 'attachment; filename="shape_packing.db"'},
        )

    return app


# Default application instance for standard ASGI servers (e.g. uvicorn)
app = create_app(
    db_path=os.environ.get("SHAPE_PACKING_DB_PATH", "shape_packing.db"),
    auto_seed=os.environ.get("SHAPE_PACKING_AUTO_SEED", "1") == "1",
)
