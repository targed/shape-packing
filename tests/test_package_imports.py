"""Regression tests for package import hygiene, packaging metadata, and server startup."""
from __future__ import annotations

import ast
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PKG = REPO_ROOT / "src" / "shape_packing"


async def _asgi_request(app, method: str, path: str, body: dict | None = None):
    """Execute a real ASGI HTTP request against a FastAPI app without external HTTP clients."""
    payload = json.dumps(body).encode("utf-8") if body is not None else b""
    headers = [(b"host", b"testserver")]
    if body is not None:
        headers.append((b"content-type", b"application/json"))
        headers.append((b"content-length", str(len(payload)).encode("ascii")))

    pure_path, _, query = path.partition("?")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": pure_path,
        "raw_path": pure_path.encode("ascii"),
        "query_string": query.encode("ascii"),
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 8000),
    }

    sent_body = False
    status_code = None
    chunks: list[bytes] = []

    async def receive():
        nonlocal sent_body
        if not sent_body:
            sent_body = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal status_code
        if message["type"] == "http.response.start":
            status_code = message["status"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    raw_bytes = b"".join(chunks)
    if path.startswith("/api/v1/export/db"):
        return status_code, raw_bytes
    raw = raw_bytes.decode("utf-8")
    return status_code, json.loads(raw) if raw else None


def test_no_internal_absolute_shape_packing_imports():
    """Every module inside src/shape_packing/ must use relative imports for sibling modules.

    Absolute `from shape_packing...` or `import shape_packing...` breaks when callers run
    `uvicorn src.shape_packing.server.app:app` while an older wheel exists in site-packages.
    """
    violations = []
    for py_file in sorted(SRC_PKG.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module and (
                    node.module == "shape_packing" or node.module.startswith("shape_packing.")
                ):
                    violations.append(
                        f"{py_file.relative_to(REPO_ROOT)}:{node.lineno}: from {node.module} import ..."
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "shape_packing" or alias.name.startswith("shape_packing."):
                        violations.append(
                            f"{py_file.relative_to(REPO_ROOT)}:{node.lineno}: import {alias.name}"
                        )

    assert violations == [], "Found absolute internal imports:\n" + "\n".join(violations)


def test_pyproject_includes_shape_catalog_package_data():
    """Ensure shape_catalog.json is declared as package data for wheel/editable installs."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "shape_catalog.json" in pyproject


def test_uvicorn_import_from_string_both_targets(tmp_path):
    """Verify uvicorn can load both `src.shape_packing.server.app:app` and `shape_packing.server.app:app`."""
    for target in ("src.shape_packing.server.app:app", "shape_packing.server.app:app"):
        env = dict(os.environ)
        if target.startswith("src."):
            env["PYTHONPATH"] = str(REPO_ROOT)
        code = (
            "from uvicorn.importer import import_from_string; "
            f"app = import_from_string({target!r}); "
            "paths = {r.path for r in app.routes}; "
            "assert '/api/v1/work' in paths; "
            "assert '/api/v1/solutions' in paths; "
            "assert '/api/v1/stats' in paths; "
            "print('OK')"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, f"{target} failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
        assert "OK" in proc.stdout


def test_create_app_serves_real_asgi_requests(tmp_path, monkeypatch):
    """Verify create_app initializes DB, registers workers, and serves /stats and /work over ASGI."""
    monkeypatch.chdir(tmp_path)
    from src.shape_packing.server.app import create_app
    from src.shape_packing.server.database import init_db, seed_frontier_problems

    db_path = str(tmp_path / "coord.db")
    conn = init_db(db_path)
    seeded = seed_frontier_problems(conn, max_n=2)
    conn.close()
    assert seeded > 0

    app = create_app(db_path=db_path)

    status_stats, stats_body = asyncio.run(_asgi_request(app, "GET", "/api/v1/stats"))
    assert status_stats == 200
    assert stats_body["total_problems"] == seeded
    assert stats_body["tier_counts"]["frontier"] == seeded

    status_probs, probs_body = asyncio.run(
        _asgi_request(app, "GET", "/api/v1/problems?tier=frontier&inner=RHOMBUS&limit=10")
    )
    assert status_probs == 200
    assert probs_body["total"] > 0
    assert all(item["inner_token"] == "RHOMBUS" for item in probs_body["items"])

    status_reg, reg_body = asyncio.run(
        _asgi_request(app, "POST", "/api/v1/workers/register", {"username": "tester", "cores": 2})
    )
    assert status_reg == 200
    assert reg_body["worker_id"]

    status_work, work_body = asyncio.run(
        _asgi_request(app, "GET", f"/api/v1/work?worker_id={reg_body['worker_id']}")
    )
    assert status_work == 200
    assert work_body["problem"]
    assert work_body["work_id"]
    assert work_body["inner_token"]
    assert work_body["container_token"]

    status_export, db_bytes = asyncio.run(_asgi_request(app, "GET", "/api/v1/export/db"))
    assert status_export == 200
    assert db_bytes.startswith(b"SQLite format 3\x00")
    snap_path = tmp_path / "exported_snapshot.db"
    snap_path.write_bytes(db_bytes)
    import sqlite3
    snap_conn = sqlite3.connect(str(snap_path))
    assert snap_conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert snap_conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0] == seeded
    snap_conn.close()
