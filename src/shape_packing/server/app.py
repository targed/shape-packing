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

import json
import math
import os
import sqlite3
import tempfile
import uuid
from typing import Any, Dict, Generator, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .database import (
    get_problem,
    init_db,
    register_worker,
    update_solution_record,
)
from .scheduler import assign_work, record_heartbeat
from ..solution_tools import (
    inverse_friedman_metric,
    verify_solution,
)


class WorkerRegisterRequest(BaseModel):
    username: str
    client_type: str = "native"
    worker_id: Optional[str] = None


class SolutionSubmitRequest(BaseModel):
    work_id: Optional[str] = None
    worker_id: str
    problem: str
    s: float
    coordinates: List[float]


class HeartbeatRequest(BaseModel):
    worker_id: str
    work_id: str
    attempts_completed: int
    best_local_s: Optional[float] = None


def get_db(request: Request) -> Generator[sqlite3.Connection, None, None]:
    """
    FastAPI dependency yielding a thread-isolated SQLite connection in WAL mode.
    Safely closes connection in finally block.
    """
    db_path = getattr(request.app.state, "db_path", "shape_packing.db")
    conn = init_db(db_path)
    try:
        yield conn
    finally:
        conn.close()


def create_app(db_path: str = "shape_packing.db") -> FastAPI:
    """
    Factory creating a FastAPI coordinator service instance.

    Initializes database tables and WAL configuration on startup.
    """
    init_conn = init_db(db_path)
    init_conn.close()

    app = FastAPI(
        title="Distributed Shape Packing Coordinator",
        description="REST API for coordinating continuous geometric shape-packing optimization.",
        version="1.0.0",
    )
    app.state.db_path = db_path

    @app.post("/api/v1/workers/register", status_code=status.HTTP_200_OK)
    def register(
        req: WorkerRegisterRequest,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Dict[str, Any]:
        """Register or update a worker node handle."""
        clean_username = req.username.strip() if req.username else ""
        if not clean_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username cannot be empty",
            )

        clean_worker_id = req.worker_id.strip() if req.worker_id and req.worker_id.strip() else None

        result = register_worker(
            conn,
            username=clean_username,
            client_type=req.client_type,
            worker_id=clean_worker_id,
        )
        return {
            "worker_id": result["worker_id"],
            "username": result["username"],
            "client_type": result["client_type"],
            "status": "registered",
        }

    @app.get("/api/v1/work")
    def get_work(
        worker_id: str = Query(...),
        cores: int = Query(1),
        lease_seconds: int = Query(300),
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
        if cores < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cores must be >= 1",
            )

        assignment = assign_work(
            conn,
            worker_id=clean_worker_id,
            cores=cores,
            lease_seconds=lease_seconds,
        )
        if assignment is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        assignment["timeout_seconds"] = assignment["lease_seconds"]
        return assignment

    @app.post("/api/v1/solutions", status_code=status.HTTP_200_OK)
    def submit_solution(
        req: SolutionSubmitRequest,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Any:
        """
        In-process geometric SAT verification and atomic solution commit.

        Reconstructs shape polygons and checks Separating Axis Theorem (SAT) non-overlap
        and container boundary confinement. Rejects invalid solutions with HTTP 400.
        Accepts valid solutions with HTTP 200, updating current record if improved.
        """
        clean_worker_id = req.worker_id.strip() if req.worker_id else ""
        if not clean_worker_id:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "status": "rejected",
                    "verified": False,
                    "message": "worker_id cannot be empty",
                },
            )

        if math.isnan(req.s) or math.isinf(req.s) or req.s <= 0.0:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "status": "rejected",
                    "verified": False,
                    "message": "Metric s must be a finite positive number.",
                },
            )

        prob = get_problem(conn, req.problem)
        if not prob:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Problem '{req.problem}' not found",
            )

        n_shapes = int(prob["n"])
        expected_coords = n_shapes * 3
        if len(req.coordinates) != expected_coords:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "status": "rejected",
                    "verified": False,
                    "message": f"Expected {expected_coords} coordinates (3 * N), received {len(req.coordinates)}",
                },
            )

        for idx, val in enumerate(req.coordinates):
            if math.isnan(val) or math.isinf(val):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "status": "rejected",
                        "verified": False,
                        "message": f"Coordinate at index {idx} is invalid (NaN or Inf)",
                    },
                )

        inner_token = prob["inner_token"]
        container_token = prob["container_token"]
        solver_s = inverse_friedman_metric(req.s, inner_token, container_token)

        sol_payload = {
            "N": n_shapes,
            "inner_token": inner_token,
            "container_token": container_token,
            "S": float(solver_s),
            "final_metric": float(req.s),
            "values": [float(c) for c in req.coordinates],
        }

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(sol_payload, tf)
            temp_path = tf.name

        try:
            res = verify_solution(temp_path, problem_str=req.problem, check_record=False)
        except Exception as exc:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "status": "rejected",
                    "verified": False,
                    "message": f"Geometric verification encountered an error: {str(exc)}",
                },
            )
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        if not res.valid:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "status": "rejected",
                    "verified": False,
                    "message": f"Geometric verification failed: {res.message}",
                },
            )

        cursor = conn.cursor()
        cursor.execute("SELECT username FROM workers WHERE id = ?", (clean_worker_id,))
        w_row = cursor.fetchone()
        if w_row:
            username = w_row["username"] if hasattr(w_row, "keys") else w_row[0]
        else:
            username = clean_worker_id

        improved = update_solution_record(
            conn=conn,
            problem_id=req.problem,
            worker_id=clean_worker_id,
            username=username,
            metric_s=res.metric,
            coordinates=req.coordinates,
        )

        return {
            "status": "accepted" if improved else "duplicate",
            "verified": True,
            "is_new_record": improved,
            "metric_s": res.metric,
            "previous_best_s": prob["best_s"],
            "message": "New world record registered! Rank updated." if improved else "Valid packing, but not lower than current best",
        }

    @app.post("/api/v1/heartbeat", status_code=status.HTTP_200_OK)
    def heartbeat(
        req: HeartbeatRequest,
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
        if req.attempts_completed < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="attempts_completed must be >= 0",
            )

        success = record_heartbeat(
            conn,
            work_id=clean_work_id,
            worker_id=clean_worker_id,
            attempts=req.attempts_completed,
            best_s=req.best_local_s,
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
    def get_stats(conn: sqlite3.Connection = Depends(get_db)) -> Dict[str, Any]:
        """Return cluster-wide summary statistics."""
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM problems")
        total_probs = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM workers")
        total_workers = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(total_attempts), 0) FROM problems")
        total_attempts = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM solutions")
        total_solutions = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(records_broken), 0) FROM workers")
        records_broken = cursor.fetchone()[0]

        return {
            "total_problems": total_probs,
            "active_workers": total_workers,
            "total_attempts": total_attempts,
            "records_broken": records_broken,
            "verified_solutions": total_solutions,
        }

    @app.get("/api/v1/leaderboard", status_code=status.HTTP_200_OK)
    def get_leaderboard(
        limit: int = Query(50, ge=1, le=500),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> List[Dict[str, Any]]:
        """Return contributor leaderboard ranked by records broken and attempts."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT username, total_attempts, records_broken
            FROM workers
            ORDER BY records_broken DESC, total_attempts DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [
            {
                "username": r["username"] if hasattr(r, "keys") else r[0],
                "total_attempts": r["total_attempts"] if hasattr(r, "keys") else r[1],
                "records_broken": r["records_broken"] if hasattr(r, "keys") else r[2],
            }
            for r in rows
        ]

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

    return app


# Default application instance for standard ASGI servers (e.g. uvicorn)
app = create_app()
