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


def test_e2e_worker_lifecycle_stats_leaderboard_and_frontier(tmp_path, monkeypatch):
    """End-to-end authenticated workflow: benchmark vs frontier, heartbeat credits, SAT solution commit, and stats/leaderboard."""
    monkeypatch.chdir(tmp_path)
    from src.shape_packing.server.app import create_app
    from src.shape_packing.server.database import init_db, seed_frontier_problems

    db_path = str(tmp_path / "e2e_sec.db")
    conn = init_db(db_path)
    conn.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, tier, density_rank)
        VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', 'benchmark', 0.90)
        """
    )
    conn.commit()
    seed_frontier_problems(conn, max_n=1)
    conn.close()

    app = create_app(db_path=db_path)

    # 1. Register worker A (wasm) & worker B (native)
    st_a, _, raw_a = asyncio.run(
        _asgi_call(app, "POST", "/api/v1/workers/register", {"username": "alice_web", "client_type": "wasm", "cores": 1})
    )
    assert st_a == 200
    reg_a = json.loads(raw_a)
    wid_a, auth_a = reg_a["worker_id"], {"Authorization": f"Bearer {reg_a['worker_secret']}"}

    st_b, _, raw_b = asyncio.run(
        _asgi_call(app, "POST", "/api/v1/workers/register", {"username": "bob_rust", "client_type": "native", "cores": 4})
    )
    assert st_b == 200
    reg_b = json.loads(raw_b)
    wid_b, auth_b = reg_b["worker_id"], {"Authorization": f"Bearer {reg_b['worker_secret']}"}

    # 2. Default queue prioritizes benchmark; explicit tier=frontier leases frontier
    st_bench, _, raw_bench = asyncio.run(_asgi_call(app, "GET", f"/api/v1/work?worker_id={wid_a}", headers=auth_a))
    assert st_bench == 200
    work_a = json.loads(raw_bench)
    assert work_a["problem"] == "3_3_in_circle"

    st_front, _, raw_front = asyncio.run(_asgi_call(app, "GET", f"/api/v1/work?worker_id={wid_b}&tier=frontier", headers=auth_b))
    assert st_front == 200
    work_front = json.loads(raw_front)
    assert work_front["problem"] != "3_3_in_circle"

    # 3. Cross-worker heartbeat spoofing (worker B using worker A's work_id) is ignored
    st_spoof, _, raw_spoof = asyncio.run(
        _asgi_call(
            app,
            "POST",
            "/api/v1/heartbeat",
            {"worker_id": wid_b, "work_id": work_a["work_id"], "attempts_completed": 500},
            headers=auth_b,
        )
    )
    assert st_spoof == 200
    assert json.loads(raw_spoof)["status"] == "ignored"
    assert json.loads(raw_spoof)["total_worker_attempts"] == 0

    # 4. Authenticated heartbeat for own lease credits attempts
    st_hb, _, raw_hb = asyncio.run(
        _asgi_call(
            app,
            "POST",
            "/api/v1/heartbeat",
            {"worker_id": wid_a, "work_id": work_a["work_id"], "attempts_completed": 500, "best_local_s": 2.5},
            headers=auth_a,
        )
    )
    assert st_hb == 200
    assert json.loads(raw_hb) == {"status": "recorded", "total_worker_attempts": 500}

    # 5. Overlapping / invalid solution rejected with 400
    st_bad, _, raw_bad = asyncio.run(
        _asgi_call(
            app,
            "POST",
            "/api/v1/solutions",
            {"work_id": work_a["work_id"], "worker_id": wid_a, "problem": "3_3_in_circle", "s": 2.5, "coordinates": [0.0] * 9},
            headers=auth_a,
        )
    )
    assert st_bad == 400
    assert json.loads(raw_bad)["verified"] is False

    # 6. Valid non-overlapping improvement accepted and reflected in stats, leaderboard, and recent_solutions
    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]
    st_ok, _, raw_ok = asyncio.run(
        _asgi_call(
            app,
            "POST",
            "/api/v1/solutions",
            {"work_id": work_a["work_id"], "worker_id": wid_a, "problem": "3_3_in_circle", "s": 2.5, "coordinates": valid_coords},
            headers=auth_a,
        )
    )
    assert st_ok == 200
    sol_ok = json.loads(raw_ok)
    assert sol_ok["verified"] is True
    assert sol_ok["is_new_record"] is True

    st_lb, _, raw_lb = asyncio.run(_asgi_call(app, "GET", "/api/v1/leaderboard"))
    assert st_lb == 200
    lb = json.loads(raw_lb)
    alice_entry = next(r for r in lb if r["username"] == "alice_web")
    assert alice_entry["total_attempts"] == 500
    assert alice_entry["records_broken"] == 1

    st_stats, _, raw_stats = asyncio.run(_asgi_call(app, "GET", "/api/v1/stats"))
    assert st_stats == 200
    stats = json.loads(raw_stats)
    assert stats["total_attempts"] == 500
    assert stats["records_broken"] == 1
    assert stats["verified_solutions"] == 1

    st_rec, _, raw_rec = asyncio.run(_asgi_call(app, "GET", "/api/v1/recent_solutions"))
    assert st_rec == 200
    rec = json.loads(raw_rec)
    assert len(rec) == 1 and rec[0]["problem_id"] == "3_3_in_circle" and rec[0]["worker_username"] == "alice_web"

    # 7. Authenticated deregister succeeds
    st_dereg, _, _ = asyncio.run(_asgi_call(app, "POST", "/api/v1/workers/deregister", {"worker_id": wid_a}, headers=auth_a))
    assert st_dereg == 200


def test_native_worker_e2e_against_asgi(tmp_path, monkeypatch):
    """Verify Python native_worker registration, work cycle, heartbeat, and deregister work end-to-end with Bearer auth."""
    from unittest import mock
    import urllib.parse
    from src.shape_packing.client import native_worker as nw

    app, _ = _setup_app(tmp_path, monkeypatch)
    conn = sqlite3.connect(str(tmp_path / "sec_coord.db"))
    conn.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, tier, density_rank) VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.0, 3.0, 'best_known', 'benchmark', 0.99)"
    )
    conn.commit()
    conn.close()

    def asgi_bridge(url: str, method: str = "GET", payload=None, headers=None, timeout: float = 10.0, data=None, **_kwargs):
        parsed = urllib.parse.urlparse(url)
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        body = payload if payload is not None else data
        st, _, raw = asyncio.run(_asgi_call(app, method, path, body=body, headers=headers))
        assert st in (200, 204), f"Unexpected status {st} on {method} {path}: {raw}"
        if st == 204 or not raw:
            return {}
        return json.loads(raw)

    valid_coords = [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]

    def mock_solver(**_kwargs):
        return {"success": True, "best_s": 2.5, "values": valid_coords}

    with mock.patch.object(nw, "send_request", side_effect=asgi_bridge):
        wid = nw.register_with_server("http://localhost:8000", "py_tester")
        secret = nw._WORKER_SECRETS[wid]
        cfg = nw.WorkerConfig(server_url="http://localhost:8000", username="py_tester", worker_id=wid, worker_secret=secret, cores=1)
        res = nw.run_worker_cycle(cfg, solver_fn=mock_solver, request_fn=asgi_bridge)
        assert res["status"] == "completed"
        assert res["found_improvement"] is True
        assert nw.deregister_with_server(cfg, request_fn=asgi_bridge) is True

    _, _, raw_lb = asyncio.run(_asgi_call(app, "GET", "/api/v1/leaderboard"))
    lb = json.loads(raw_lb)
    assert lb[0]["username"] == "py_tester"
    assert lb[0]["records_broken"] == 1
    assert lb[0]["total_attempts"] == res["attempts_completed"] == 1000
