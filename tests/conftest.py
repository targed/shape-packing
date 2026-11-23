"""
Shared pytest fixtures for shape-packing tests.
"""
import json
import os
import socket
import sys
import tempfile
import textwrap
import threading
from pathlib import Path

import pytest

# Ensure default socket timeout to prevent indefinite hangs
DEFAULT_SOCKET_TIMEOUT = float(os.environ.get("SOCKET_TIMEOUT", "10.0"))
socket.setdefaulttimeout(DEFAULT_SOCKET_TIMEOUT)

# Guard socket._fallback_socketpair with strict timeouts so accept() never hangs
_orig_fallback_socketpair = getattr(socket, "_fallback_socketpair", None)
if _orig_fallback_socketpair is not None:
    def _timed_fallback_socketpair(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
        lsock = socket.socket(family, type, proto)
        try:
            lsock.settimeout(2.0)
            host = socket._LOCALHOST if family == socket.AF_INET else socket._LOCALHOST_V6
            lsock.bind((host, 0))
            lsock.listen(1)
            addr, port = lsock.getsockname()[:2]
            csock = socket.socket(family, type, proto)
            try:
                csock.settimeout(2.0)
                csock.connect((addr, port))
                ssock, _ = lsock.accept()
                ssock.settimeout(None)
                csock.settimeout(None)
            except Exception:
                csock.close()
                raise
        finally:
            lsock.close()
        return (ssock, csock)

    socket._fallback_socketpair = _timed_fallback_socketpair
    if hasattr(socket, "socketpair"):
        socket.socketpair = _timed_fallback_socketpair


def _probe_loopback_socket_access() -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c.settimeout(0.5)
        c.connect(("127.0.0.1", port))
        conn, _ = s.accept()
        conn.close()
        c.close()
        s.close()
        return True
    except Exception:
        return False


LOOPBACK_SOCKET_AVAILABLE = _probe_loopback_socket_access()


@pytest.fixture(autouse=True)
def test_timeout_timer(request):
    """Execution timer for every test to prevent suite freezing or hanging."""
    timeout_sec = float(os.environ.get("TEST_TIMEOUT", "20.0"))
    marker = request.node.get_closest_marker("timeout")
    if marker and marker.args:
        try:
            timeout_sec = float(marker.args[0])
        except (ValueError, TypeError):
            pass

    target_thread_id = threading.get_ident()
    timed_out = threading.Event()

    def _on_timer_expired():
        timed_out.set()
        frame = sys._current_frames().get(target_thread_id)
        if frame:
            import traceback
            tb_lines = traceback.format_stack(frame)
            sys.stderr.write(
                f"\n[TEST TIMER EXPIRED] Test '{request.node.nodeid}' exceeded timer of {timeout_sec:.1f}s!\n"
                f"Active stack trace:\n{''.join(tb_lines)}\n"
            )
            sys.stderr.flush()
        if sys.platform == "win32":
            import ctypes
            ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(target_thread_id),
                ctypes.py_object(TimeoutError),
            )

    timer = threading.Timer(timeout_sec, _on_timer_expired)
    timer.daemon = True
    timer.start()
    try:
        # Check loopback permission for socket-dependent tests
        if not LOOPBACK_SOCKET_AVAILABLE:
            node_file = str(getattr(request.node, "fspath", "") or getattr(request.node, "path", ""))
            node_name = request.node.name
            socket_test_files = (
                "test_distributed_e2e",
                "test_distributed_fleet_challenge",
                "test_native_worker_concurrency",
                "test_server_api",
                "test_server_api_adversarial",
                "test_server_api_concurrency",
                "test_rust_worker_e2e",
            )
            if any(name in node_file for name in socket_test_files) or "loopback" in node_name:
                pytest.skip("Loopback socket networking is disabled or restricted in this environment")

        yield
    finally:
        timer.cancel()

# Ensure src is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="session")
def project_root():
    return ROOT


@pytest.fixture
def tmp_project(project_root, tmp_path):
    """
    A temporary 'project' directory with src on path.
    Useful when we need files visible to the package.
    """
    src_link = tmp_path / "src"
    src_link.symlink_to(project_root / "src", target_is_directory=True)
    return tmp_path


# Example problem names to reuse
PROBLEM_8_3_IN_5 = "8_3_in_5"
PROBLEM_10_6_IN_4 = "10_6_in_4"
PROBLEM_12_3_IN_CIRCLE = "12_3_in_CIRCLE"


@pytest.fixture
def sample_solution_values(tmp_path):
    """
    Minimal solution JSON in 'values' style.
    """
    data = {
        "N": 4,
        "inner_sides": 3,
        "container_sides": 4,
        "S": 2.0,
        "final_metric": 1.5,
        "values": [0.0, 0.0, 0.0,
                   1.0, 0.0, 0.0,
                   0.0, 1.0, 0.0,
                   -1.0, 0.0, 0.0],
    }
    path = tmp_path / "solution_values.json"
    path.write_text(json.dumps(data))
    return str(path)


@pytest.fixture
def sample_solution_positions(tmp_path):
    """
    Minimal solution JSON in 'positions' style.
    """
    data = {
        "N": 3,
        "nsi": 3,
        "nsc": 4,
        "S": 2.0,
        "positions": [
            {"cx": 0.0, "cy": 0.0, "a": 0.0},
            {"cx": 1.0, "cy": 0.0, "a": 0.0},
            {"cx": -1.0, "cy": 0.0, "a": 0.0},
        ],
    }
    path = tmp_path / "solution_positions.json"
    path.write_text(json.dumps(data))
    return str(path)


@pytest.fixture
def sample_tsv_reference(tmp_path):
    """
    A PACKING_REFERENCE.tsv with a few known entries.
    """
    content = textwrap.dedent(
        """\
        id	problem_family	best_value	status	source_note	our_problem
        3_in_3_1	3_in_3	1.000000	best_known	Found by Erich	1_3_in_3
        3_in_3_8	3_in_3	2.000000	best_known	Found by Erich	8_3_in_5
        6_in_4_10	6_in_4	3.000000	best_known	Proved	10_6_in_4
        """
    )
    path = tmp_path / "PACKING_REFERENCE.tsv"
    path.write_text(content)
    return str(path)


@pytest.fixture
def sample_priority_queue(tmp_path):
    """
    A small priority_queue.json for agent_loop tests.
    """
    items = [
        {
            "problem": PROBLEM_8_3_IN_5,
            "density": 0.9,
            "status": "best_known",
            "source_note": "Found by Erich",
            "best_value": 2.0,
            "inner_shape": "3",
            "container_shape": "5",
            "N": 8,
        },
        {
            "problem": PROBLEM_10_6_IN_4,
            "density": 0.6,
            "status": "best_known",
            "source_note": "Found by someone",
            "best_value": 3.0,
            "inner_shape": "6",
            "container_shape": "4",
            "N": 10,
        },
        {
            "problem": "5_3_in_3",
            "density": 0.95,
            "status": "trivial",
            "source_note": "Trivial",
            "best_value": 1.1,
            "inner_shape": "3",
            "container_shape": "3",
            "N": 5,
        },
        {
            "problem": "3_3_in_CIRCLE",
            "density": 0.4,
            "status": "best_known",
            "source_note": "Found by Erich",
            "best_value": 0.5,
            "inner_shape": "3",
            "container_shape": "CIRCLE",
            "N": 3,
        },
    ]
    path = tmp_path / "priority_queue.json"
    path.write_text(json.dumps(items))
    return str(path)


@pytest.fixture
def sample_history_tsv(tmp_path):
    """
    A results.tsv with a few experiments.
    """
    lines = [
        "commit\tscore\tmemory_gb\tstatus\tproblem\tdescription\tseconds",
        "abc\t1.5\t0.1\tkeep\t8_3_in_5\ttest run\t10.0",
        "abc\t1.4\t0.1\tkeep\t8_3_in_5\ttest run\t10.0",
        "abc\t1.6\t0.1\tkeep\t8_3_in_5\ttest run\t10.0",
        "abc\t1.3\t0.1\tkeep\t8_3_in_5\ttest run\t10.0",
        "abc\t1.2\t0.1\tkeep\t8_3_in_5\ttest run\t10.0",
        "abc\t1.1\t0.1\tkeep\t8_3_in_5\ttest run\t10.0",
        "abc\t2.0\t0.1\tkeep\t10_6_in_4\ttest run\t10.0",
        "abc\t0\t0.1\tcrash\t12_3_in_CIRCLE\tcrash\t5.0",
    ]
    path = tmp_path / "results.tsv"
    path.write_text("\n".join(lines))
    return str(path)
