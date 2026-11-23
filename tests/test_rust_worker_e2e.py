"""End-to-End integration test: Pure Rust shape-packing-worker.exe against Python Coordinator."""

import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time

import pytest
import uvicorn

from shape_packing.server.app import create_app, get_db
from shape_packing.server.database import init_db


def test_rust_worker_e2e_against_python_coordinator(tmp_path: Path):
    exe_path = Path("packer_rs/target/release/shape-packing-worker.exe")
    if not exe_path.exists():
        exe_path = Path("packer_rs/target/debug/shape-packing-worker.exe")
    if not exe_path.exists():
        pytest.skip("shape-packing-worker binary not found")

    # 1. Ephemeral port and sqlite database
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    db_path = str(tmp_path / "rust_e2e_coord.db")
    conn = init_db(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, density_rank)
        VALUES ('3_3_in_circle', '3', 'CIRCLE', 3, 3.5, 3.5, 'best_known', 0.8)
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)

    def thread_safe_get_db():
        c = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode = WAL;")
        c.execute("PRAGMA synchronous = NORMAL;")
        c.execute("PRAGMA foreign_keys = ON;")
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_db] = thread_safe_get_db

    server_config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(server_config)
    server_thread = threading.Thread(target=server.run, daemon=True, name="RustCoordServer")
    server_thread.start()

    # Wait for server ready
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)

    server_url = f"http://127.0.0.1:{port}"
    cfg_file = str(tmp_path / "worker_config.json")

    # 2. Launch Rust worker binary
    proc_kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if sys.platform == "win32":
        proc_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        [
            str(exe_path),
            "--server",
            server_url,
            "--username",
            "rust_volunteer_1",
            "--cores",
            "1",
            "--no-interactive",
            "--config",
            cfg_file,
        ],
        **proc_kwargs,
    )

    try:
        # Give worker time to register, lease work, solve (3 triangles in circle is super fast), and report
        time.sleep(3.5)

        # Terminate or signal the worker
        if sys.platform == "win32":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.send_signal(signal.SIGINT)

        try:
            stdout, stderr = proc.communicate(timeout=4.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()

        print("STDOUT:\n", stdout)
        print("STDERR:\n", stderr)

        # 3. Assertions
        assert "[STARTUP] Registered successfully" in stdout
        assert "[WORK] Leased" in stdout

        # Verify database
        db_conn = sqlite3.connect(db_path)
        db_conn.row_factory = sqlite3.Row
        c = db_conn.cursor()
        c.execute("SELECT username, total_attempts FROM workers WHERE username = 'rust_volunteer_1'")
        worker_row = c.fetchone()
        assert worker_row is not None
        assert worker_row["username"] == "rust_volunteer_1"
        assert worker_row["total_attempts"] > 0
        db_conn.close()

    finally:
        if proc.poll() is None:
            proc.kill()
