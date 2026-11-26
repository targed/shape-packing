"""Adversarial & unit security tests for the coordinator API, auth, rate limits, and verifier."""
from __future__ import annotations

import asyncio
import json
import math
import sqlite3

import pytest


async def _asgi_call(app, method: str, path: str, body: dict | bytes | None = None, headers: dict | None = None):
    payload = b""
    req_headers = [(b"host", b"testserver")]
    if isinstance(body, bytes):
        payload = body
        req_headers.append((b"content-type", b"application/json"))
        req_headers.append((b"content-length", str(len(payload)).encode("ascii")))
    elif body is not None:
        payload = json.dumps(body).encode("utf-8")
        req_headers.append((b"content-type", b"application/json"))
        req_headers.append((b"content-length", str(len(payload)).encode("ascii")))
    if headers:
        for k, v in headers.items():
            req_headers.append((k.lower().encode("ascii"), v.encode("ascii")))

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
        "headers": req_headers,
        "client": ("198.51.100.10", 12345),
        "server": ("testserver", 8000),
    }
    sent = False
    status_code = None
    resp_headers = {}
    chunks = []

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        await asyncio.sleep(0.05)
        return {"type": "http.disconnect"}

    async def send(msg):
        nonlocal status_code
        if msg["type"] == "http.response.start":
            status_code = msg["status"]
            resp_headers.update({k.decode("latin1").lower(): v.decode("latin1") for k, v in msg.get("headers", [])})
        elif msg["type"] == "http.response.body":
            chunks.append(msg.get("body", b""))

    await app(scope, receive, send)
    return status_code, resp_headers, b"".join(chunks)


def _setup_app(tmp_path, monkeypatch, env_overrides=None):
    monkeypatch.chdir(tmp_path)
    if env_overrides:
        for k, v in env_overrides.items():
            if v is None:
                monkeypatch.delenv(k, raising=False)
            else:
                monkeypatch.setenv(k, v)
    from src.shape_packing.server.app import create_app
    from src.shape_packing.server.database import init_db, seed_frontier_problems

    db_path = str(tmp_path / "sec_coord.db")
    conn = init_db(db_path)
    seed_frontier_problems(conn, max_n=2)
    conn.close()
    return create_app(db_path=db_path), db_path


def test_export_db_fail_closed_and_token_auth(tmp_path, monkeypatch):
    app, _ = _setup_app(tmp_path, monkeypatch, {"SHAPE_PACKING_BACKUP_TOKEN": None, "SHAPE_PACKING_ALLOW_UNAUTH_EXPORT": None})
    st, _, _ = asyncio.run(_asgi_call(app, "GET", "/api/v1/export/db"))
    assert st == 503

    app2, _ = _setup_app(tmp_path, monkeypatch, {"SHAPE_PACKING_BACKUP_TOKEN": "top-secret-backup-token"})
    st_noauth, _, _ = asyncio.run(_asgi_call(app2, "GET", "/api/v1/export/db"))
    assert st_noauth == 401

    st_raw, _, _ = asyncio.run(_asgi_call(app2, "GET", "/api/v1/export/db", headers={"Authorization": "top-secret-backup-token"}))
    assert st_raw == 401

    st_ok, hdrs, body = asyncio.run(_asgi_call(app2, "GET", "/api/v1/export/db", headers={"Authorization": "Bearer top-secret-backup-token"}))
    assert st_ok == 200
    assert hdrs.get("cache-control") == "no-store"
    assert body.startswith(b"SQLite format 3\x00")


def test_worker_auth_prevents_impersonation_and_spoofing(tmp_path, monkeypatch):
    app, db_path = _setup_app(tmp_path, monkeypatch)

    # Register legitimate worker
    st, _, raw = asyncio.run(_asgi_call(app, "POST", "/api/v1/workers/register", {"username": "alice", "client_type": "wasm"}))
    assert st == 200
    reg = json.loads(raw)
    wid = reg["worker_id"]
    secret = reg["worker_secret"]
    assert secret

    # Attempting to overwrite alice's worker_id without secret issues a new isolated worker_id
    st2, _, raw2 = asyncio.run(_asgi_call(app, "POST", "/api/v1/workers/register", {"worker_id": wid, "username": "evil", "client_type": "native"}))
    assert st2 == 200
    reg2 = json.loads(raw2)
    assert reg2["worker_id"] != wid

    # Unauthenticated /work, /heartbeat, /solutions, /deregister rejected with 401
    st_w_noauth, _, _ = asyncio.run(_asgi_call(app, "GET", f"/api/v1/work?worker_id={wid}"))
    assert st_w_noauth == 401

    st_hb_noauth, _, _ = asyncio.run(_asgi_call(app, "POST", "/api/v1/heartbeat", {"worker_id": wid, "work_id": "wu_fake", "attempts_completed": 100}))
    assert st_hb_noauth == 401

    st_dereg_noauth, _, _ = asyncio.run(_asgi_call(app, "POST", "/api/v1/workers/deregister", {"worker_id": wid}))
    assert st_dereg_noauth == 401

    # Authenticated /work succeeds
    auth_hdr = {"Authorization": f"Bearer {secret}"}
    st_w_ok, _, raw_w = asyncio.run(_asgi_call(app, "GET", f"/api/v1/work?worker_id={wid}", headers=auth_hdr))
    assert st_w_ok == 200
    work = json.loads(raw_w)

    # Heartbeat with > 50_000 attempts rejected by Pydantic (422)
    st_hb_big, _, _ = asyncio.run(
        _asgi_call(app, "POST", "/api/v1/heartbeat", {"worker_id": wid, "work_id": work["work_id"], "attempts_completed": 2**60}, headers=auth_hdr)
    )
    assert st_hb_big == 422

    # Heartbeat with nonexistent work_id does NOT credit worker attempts
    st_hb_fake, _, raw_hb_fake = asyncio.run(
        _asgi_call(app, "POST", "/api/v1/heartbeat", {"worker_id": wid, "work_id": "wu_does_not_exist", "attempts_completed": 500}, headers=auth_hdr)
    )
    assert st_hb_fake == 200
    assert json.loads(raw_hb_fake)["status"] == "ignored"
    assert json.loads(raw_hb_fake)["total_worker_attempts"] == 0

    # Valid heartbeat credits attempts
    st_hb_ok, _, raw_hb_ok = asyncio.run(
        _asgi_call(app, "POST", "/api/v1/heartbeat", {"worker_id": wid, "work_id": work["work_id"], "attempts_completed": 500}, headers=auth_hdr)
    )
    assert st_hb_ok == 200
    assert json.loads(raw_hb_ok)["status"] == "recorded"
    assert json.loads(raw_hb_ok)["total_worker_attempts"] == 500


def test_payload_limits_rate_limits_cors_and_verifier_bounds(tmp_path, monkeypatch):
    app, _ = _setup_app(tmp_path, monkeypatch)

    # Oversized JSON body on /solutions (> 64 KB) rejected with 413
    oversized = b'{"worker_id":"x","problem":"p","s":1.0,"coordinates":[' + b"0.0," * 20000 + b"0.0]}"
    st_413, _, _ = asyncio.run(_asgi_call(app, "POST", "/api/v1/solutions", body=oversized))
    assert st_413 == 413

    # Oversized username rejected with 422
    st_uname, _, _ = asyncio.run(_asgi_call(app, "POST", "/api/v1/workers/register", {"username": "A" * 500}))
    assert st_uname == 422

    # Security headers & tightened CORS
    st_stats, hdrs, _ = asyncio.run(
        _asgi_call(app, "GET", "/api/v1/stats", headers={"Origin": "https://evil.example"})
    )
    assert st_stats == 200
    assert hdrs.get("x-content-type-options") == "nosniff"
    assert hdrs.get("x-frame-options") == "DENY"
    assert hdrs.get("access-control-allow-origin") is None

    # 16 concurrent browser WASM thread registrations from the same NAT IP must succeed
    for i in range(16):
        st_reg, _, _ = asyncio.run(_asgi_call(app, "POST", "/api/v1/workers/register", {"username": "donor", "client_type": "wasm"}))
        assert st_reg == 200

    # Verify solution_tools rejects N <= 0 and NaN
    from src.shape_packing.solution_tools import Solution, verify_solution_obj
    with pytest.raises(ValueError):
        verify_solution_obj(Solution("<t>", 0, "3", "4", 1.0, 1.0, []), check_record=False)
    with pytest.raises(ValueError):
        verify_solution_obj(Solution("<t>", 1, "3", "4", float("nan"), 1.0, [0.0, 0.0, 0.0]), check_record=False)
