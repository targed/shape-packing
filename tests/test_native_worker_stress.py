"""Adversarial stress test suite for Native Worker Client Daemon.

Empirically tests:
1. Transient network drop simulation (1, 2, 3 packets with 500/503 errors, backoff and recovery)
2. HTTP 204 starve-to-work transition (poll_interval sleeping, immediate work pickup, no busy spinning)
3. Malformed coordinator responses (truncated JSON, HTML errors, 400 rejections with error diagnostics)
4. Loopback proxy pollution (http_proxy=http://127.0.0.1:9999 bypass for 127.0.0.1 and localhost)
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import os
import threading
import time
import tracemalloc
from typing import Any, Dict, List
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

import src.shape_packing.client.native_worker as nw
from src.shape_packing.client.native_worker import (
    HeartbeatReporter,
    WorkerConfig,
    run_worker_cycle,
    run_worker_loop,
    send_request,
)


@pytest.fixture(autouse=True)
def reset_worker_state():
    """Ensure clean shutdown flags and in-flight tracking between tests."""
    nw._SHUTDOWN = False
    nw._GLOBAL_STOP_EVENT.clear()
    with nw._IN_FLIGHT_STATE["lock"]:
        nw._IN_FLIGHT_STATE["work_id"] = None
        nw._IN_FLIGHT_STATE["attempts"] = 0
        nw._IN_FLIGHT_STATE["best_s"] = None
    yield
    nw._SHUTDOWN = False
    nw._GLOBAL_STOP_EVENT.clear()


# ============================================================================
# Vector 1: Transient Network Drop Simulation & Backoff Recovery
# ============================================================================


def test_transient_drop_single_500_recovery():
    """Test dropping 1 request with HTTP 500 error, verifying 5s backoff and recovery."""
    config = WorkerConfig(worker_id="w_drop1", max_backoff=60.0)
    sleep_durations: List[float] = []

    def fake_sleep(dur: float) -> None:
        sleep_durations.append(dur)

    call_count = 0

    def mock_send(url: str, method: str = "GET", payload: Any = None, **kwargs: Any) -> Dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            err = urllib.error.HTTPError(
                url=url,
                code=500,
                msg="Internal Server Error",
                hdrs=MagicMock(),
                fp=io.BytesIO(b'{"detail": "Temporary coordinator crash"}'),
            )
            raise err
        if "work" in url:
            return {
                "work_id": "wu_rec_1",
                "problem": "3_3_in_circle",
                "n": 3,
                "target_s": 3.0,
                "recommended_attempts": 100,
            }
        return {"status": "ok"}

    with patch.object(
        nw._GLOBAL_STOP_EVENT,
        "wait",
        side_effect=lambda timeout=None: (sleep_durations.append(timeout) or False),
    ):
        history = run_worker_loop(
            config=config,
            max_cycles=1,
            solver_fn=lambda **kw: {"success": True, "score": 3.5, "values": [0.0] * 9},
            request_fn=mock_send,
        )

    assert len(history) == 1
    assert history[0]["status"] == "completed"
    assert call_count >= 2
    # Verify 1 backoff sleep occurred with 5.0 seconds (5.0 * 1)
    assert len(sleep_durations) == 1
    assert sleep_durations[0] == 5.0


def test_transient_drop_double_500_503_recovery():
    """Test dropping 2 requests (500 then 503), verifying progressive backoff (5s, 10s) and recovery."""
    config = WorkerConfig(worker_id="w_drop2", max_backoff=60.0)
    sleep_durations: List[float] = []

    call_count = 0

    def mock_send(url: str, method: str = "GET", payload: Any = None, **kwargs: Any) -> Dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise urllib.error.HTTPError(
                url=url,
                code=500,
                msg="Internal Server Error",
                hdrs=MagicMock(),
                fp=io.BytesIO(b'{"detail": "Database lock timeout"}'),
            )
        elif call_count == 2:
            raise urllib.error.HTTPError(
                url=url,
                code=503,
                msg="Service Unavailable",
                hdrs=MagicMock(),
                fp=io.BytesIO(b'{"detail": "Server overloaded"}'),
            )
        if "work" in url:
            return {
                "work_id": "wu_rec_2",
                "problem": "3_3_in_circle",
                "n": 3,
                "target_s": 3.0,
                "recommended_attempts": 100,
            }
        return {"status": "ok"}

    with patch.object(
        nw._GLOBAL_STOP_EVENT,
        "wait",
        side_effect=lambda timeout=None: (sleep_durations.append(timeout) or False),
    ):
        history = run_worker_loop(
            config=config,
            max_cycles=1,
            solver_fn=lambda **kw: {"success": True, "score": 3.5, "values": [0.0] * 9},
            request_fn=mock_send,
        )

    assert len(history) == 1
    assert history[0]["status"] == "completed"
    assert sleep_durations == [5.0, 10.0]


def test_transient_drop_triple_503_recovery():
    """Test dropping 3 requests with 503 errors, verifying backoff sequence [5s, 10s, 15s] and recovery."""
    config = WorkerConfig(worker_id="w_drop3", max_backoff=60.0)
    sleep_durations: List[float] = []

    call_count = 0

    def mock_send(url: str, method: str = "GET", payload: Any = None, **kwargs: Any) -> Dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            raise urllib.error.HTTPError(
                url=url,
                code=503,
                msg="Service Unavailable",
                hdrs=MagicMock(),
                fp=io.BytesIO(b'{"detail": "Gateway queue full"}'),
            )
        if "work" in url:
            return {
                "work_id": "wu_rec_3",
                "problem": "3_3_in_circle",
                "n": 3,
                "target_s": 3.0,
                "recommended_attempts": 100,
            }
        return {"status": "ok"}

    with patch.object(
        nw._GLOBAL_STOP_EVENT,
        "wait",
        side_effect=lambda timeout=None: (sleep_durations.append(timeout) or False),
    ):
        history = run_worker_loop(
            config=config,
            max_cycles=1,
            solver_fn=lambda **kw: {"success": True, "score": 3.5, "values": [0.0] * 9},
            request_fn=mock_send,
        )

    assert len(history) == 1
    assert history[0]["status"] == "completed"
    assert sleep_durations == [5.0, 10.0, 15.0]


def test_transient_drop_max_backoff_capping():
    """Test that progressive backoff never exceeds config.max_backoff."""
    config = WorkerConfig(worker_id="w_cap", max_backoff=12.0)
    sleep_durations: List[float] = []

    call_count = 0

    def mock_send(url: str, method: str = "GET", payload: Any = None, **kwargs: Any) -> Dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count <= 4:
            raise urllib.error.URLError("Temporary outage")
        if "work" in url:
            return {
                "work_id": "wu_cap",
                "problem": "3_3_in_circle",
                "n": 3,
                "target_s": 3.0,
                "recommended_attempts": 100,
            }
        return {"status": "ok"}

    with patch.object(
        nw._GLOBAL_STOP_EVENT,
        "wait",
        side_effect=lambda timeout=None: (sleep_durations.append(timeout) or False),
    ):
        history = run_worker_loop(
            config=config,
            max_cycles=1,
            solver_fn=lambda **kw: {"success": True, "score": 3.5, "values": [0.0] * 9},
            request_fn=mock_send,
        )

    assert len(history) == 1
    # Failures: 1 (5.0s), 2 (10.0s), 3 (12.0s capped), 4 (12.0s capped)
    assert sleep_durations == [5.0, 10.0, 12.0, 12.0]


def test_heartbeat_recredits_unreported_attempts_on_network_fault():
    """Verify HeartbeatReporter retains unacknowledged attempts when coordinator drops connection."""
    failed = True

    def flakey_request(url: str, method: str = "GET", payload: Any = None, **kwargs: Any) -> Dict[str, Any]:
        nonlocal failed
        if failed:
            failed = False
            raise urllib.error.URLError("Network down")
        return {"status": "recorded"}

    reporter = HeartbeatReporter(
        server_url="http://coord:8000",
        worker_id="w1",
        work_id="wu_retry",
        interval_seconds=1.0,
        request_fn=flakey_request,
    )
    reporter.record_attempts(250, best_s=2.8)

    # First flush fails
    ok1 = reporter.flush(force=True)
    assert ok1 is False
    # Verify attempts were safely preserved in reporter
    assert reporter._unreported_attempts == 250
    assert reporter._best_local_s == 2.8

    # Second flush succeeds
    ok2 = reporter.flush(force=True)
    assert ok2 is True
    assert reporter._unreported_attempts == 0


# ============================================================================
# Vector 2: HTTP 204 Starve-to-Work Transition
# ============================================================================


def test_204_starvation_sleeps_poll_interval_without_busy_spinning():
    """Verify worker properly sleeps poll_interval on each 204 response without busy-spinning."""
    config = WorkerConfig(worker_id="w_starve", poll_interval=4.25)
    sleep_calls: List[float] = []

    cycle_count = 0

    def mock_send(url: str, method: str = "GET", payload: Any = None, **kwargs: Any) -> Dict[str, Any]:
        nonlocal cycle_count
        cycle_count += 1
        return {}  # HTTP 204 No Content

    with patch.object(
        nw._GLOBAL_STOP_EVENT,
        "wait",
        side_effect=lambda timeout=None: (sleep_calls.append(timeout) or False),
    ):
        history = run_worker_loop(
            config=config,
            max_cycles=5,
            request_fn=mock_send,
        )

    assert len(history) == 5
    assert all(c["status"] == "idle" for c in history)
    assert sleep_calls == [4.25, 4.25, 4.25, 4.25, 4.25]


def test_204_starve_to_work_immediate_pickup():
    """Verify immediate pickup of new work when transitioning from 204 starvation to 200 OK."""
    config = WorkerConfig(worker_id="w_trans", poll_interval=3.0)
    sleep_calls: List[float] = []

    work_query_count = 0

    def mock_send(url: str, method: str = "GET", payload: Any = None, **kwargs: Any) -> Dict[str, Any]:
        nonlocal work_query_count
        if "work" in url:
            work_query_count += 1
            if work_query_count <= 2:
                return {}  # 204 No Content
            else:
                return {
                    "work_id": "wu_new_job",
                    "problem": "circle_3",
                    "n": 3,
                    "target_s": 3.0,
                    "recommended_attempts": 50,
                }
        return {"status": "ok"}

    solver_called = False

    def mock_solver(**kw: Any) -> Dict[str, Any]:
        nonlocal solver_called
        solver_called = True
        return {"success": True, "score": 2.9, "values": [0.0] * 9}

    with patch.object(
        nw._GLOBAL_STOP_EVENT,
        "wait",
        side_effect=lambda timeout=None: (sleep_calls.append(timeout) or False),
    ):
        history = run_worker_loop(
            config=config,
            max_cycles=3,
            solver_fn=mock_solver,
            request_fn=mock_send,
        )

    assert len(history) == 3
    assert history[0]["status"] == "idle"
    assert history[1]["status"] == "idle"
    assert history[2]["status"] == "completed"
    assert solver_called is True
    # Sleeps occurred on 204 cycles, but NOT on completed work cycle
    assert sleep_calls == [3.0, 3.0]


def test_204_starvation_memory_profile():
    """Empirically audit memory footprint during repeated 204 cycles using tracemalloc."""
    config = WorkerConfig(worker_id="w_mem", poll_interval=0.01)

    orig_wait = nw._GLOBAL_STOP_EVENT.wait
    nw._GLOBAL_STOP_EVENT.wait = lambda timeout=None: False

    try:
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        history = run_worker_loop(
            config=config,
            max_cycles=100,
            request_fn=lambda url, **kw: {},
        )

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()
    finally:
        nw._GLOBAL_STOP_EVENT.wait = orig_wait

    assert len(history) == 100
    top_stats = snapshot_after.compare_to(snapshot_before, "lineno")
    total_diff_kb = sum(stat.size_diff for stat in top_stats) / 1024.0

    # 100 idle cycles should consume negligible memory (< 30 KB total heap delta)
    assert total_diff_kb < 30.0, f"Excessive memory delta detected during 204 starvation: {total_diff_kb} KB"


# ============================================================================
# Vector 3: Malformed Coordinator Responses & Diagnostics
# ============================================================================


def test_malformed_truncated_json_response_handling():
    """Verify worker survives truncated JSON response, logs/backs off, and recovers."""
    config = WorkerConfig(worker_id="w_trunc")
    sleep_calls: List[float] = []

    # Directly test send_request on truncated JSON
    mock_resp_truncated = MagicMock()
    mock_resp_truncated.__enter__.return_value = mock_resp_truncated
    mock_resp_truncated.status = 200
    mock_resp_truncated.read.return_value = b'{"work_id": "wu_1", "problem": "3_3_'

    with patch("urllib.request.urlopen", return_value=mock_resp_truncated):
        with pytest.raises(json.JSONDecodeError):
            send_request("http://coordinator.example.com/api/v1/work")

    # Now verify that run_worker_loop catches JSONDecodeError, backs off, and recovers
    query_count = 0

    def mock_send(url: str, method: str = "GET", payload: Any = None, **kwargs: Any) -> Dict[str, Any]:
        nonlocal query_count
        query_count += 1
        if query_count == 1:
            raise json.JSONDecodeError("Unterminated string starting at line 1", "", 20)
        if "work" in url:
            return {
                "work_id": "wu_valid",
                "problem": "3_3_in_circle",
                "n": 3,
                "target_s": 3.0,
                "recommended_attempts": 10,
            }
        return {"status": "ok"}

    with patch.object(
        nw._GLOBAL_STOP_EVENT,
        "wait",
        side_effect=lambda timeout=None: (sleep_calls.append(timeout) or False),
    ):
        history = run_worker_loop(
            config=config,
            max_cycles=1,
            solver_fn=lambda **kw: {"success": True, "score": 3.2, "values": [0.0] * 9},
            request_fn=mock_send,
        )

    assert len(history) == 1
    assert history[0]["status"] == "completed"
    assert sleep_calls == [5.0]


def test_malformed_corrupted_html_error_handling():
    """Verify worker survives non-JSON HTML error body from proxy or gateway."""
    config = WorkerConfig(worker_id="w_html")
    sleep_calls: List[float] = []

    call_count = 0

    def mock_send(url: str, method: str = "GET", payload: Any = None, **kwargs: Any) -> Dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Simulate 502 Bad Gateway returning raw HTML
            err = urllib.error.HTTPError(
                url=url,
                code=502,
                msg="Bad Gateway",
                hdrs=MagicMock(),
                fp=io.BytesIO(b"<html><body>502 Bad Gateway: Nginx</body></html>"),
            )
            raise err
        if "work" in url:
            return {
                "work_id": "wu_after_html",
                "problem": "3_3_in_circle",
                "n": 3,
                "target_s": 3.0,
                "recommended_attempts": 10,
            }
        return {"status": "ok"}

    with patch.object(
        nw._GLOBAL_STOP_EVENT,
        "wait",
        side_effect=lambda timeout=None: (sleep_calls.append(timeout) or False),
    ):
        history = run_worker_loop(
            config=config,
            max_cycles=1,
            solver_fn=lambda **kw: {"success": True, "score": 3.2, "values": [0.0] * 9},
            request_fn=mock_send,
        )

    assert len(history) == 1
    assert history[0]["status"] == "completed"
    assert sleep_calls == [5.0]


def test_http_400_rejection_surfaces_error_diagnostics():
    """Verify HTTP 400 rejection parses and exposes JSON error diagnostics on exception object."""
    error_json_bytes = b'{"status": "rejected", "verified": false, "message": "SAT pairwise polygon overlap at shape 1 and 2"}'
    http_err = urllib.error.HTTPError(
        url="http://coordinator.example.com/api/v1/solutions",
        code=400,
        msg="Bad Request",
        hdrs=MagicMock(),
        fp=io.BytesIO(error_json_bytes),
    )

    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            send_request("http://coordinator.example.com/api/v1/solutions", method="POST", payload={"s": 2.1})

    exc = exc_info.value
    assert exc.code == 400
    assert hasattr(exc, "error_data")
    assert exc.error_data.get("message") == "SAT pairwise polygon overlap at shape 1 and 2"
    assert exc.error_data.get("verified") is False
    # Ensure stream can still be read
    assert exc.read() == error_json_bytes


def test_worker_survives_400_solution_rejection():
    """Verify worker loop survives an HTTP 400 rejection on solution submission and proceeds."""
    config = WorkerConfig(worker_id="w_400", server_url="http://coord:8000")
    sleep_calls: List[float] = []

    cycle_index = 0

    def mock_send(url: str, method: str = "GET", payload: Any = None, **kwargs: Any) -> Dict[str, Any]:
        nonlocal cycle_index
        if "work" in url:
            cycle_index += 1
            return {
                "work_id": f"wu_{cycle_index}",
                "problem": "3_3_in_circle",
                "n": 3,
                "target_s": 3.0,
                "recommended_attempts": 10,
            }
        elif "solutions" in url:
            if cycle_index == 1:
                # First submission rejected with 400
                err = urllib.error.HTTPError(
                    url=url,
                    code=400,
                    msg="Bad Request",
                    hdrs=MagicMock(),
                    fp=io.BytesIO(b'{"status": "rejected", "message": "Container penetration"}'),
                )
                raise err
            else:
                return {"status": "accepted", "is_new_record": True}
        return {"status": "recorded"}

    with patch.object(
        nw._GLOBAL_STOP_EVENT,
        "wait",
        side_effect=lambda timeout=None: (sleep_calls.append(timeout) or False),
    ):
        history = run_worker_loop(
            config=config,
            max_cycles=1,
            solver_fn=lambda **kw: {"success": True, "score": 2.5, "values": [0.0] * 9},
            request_fn=mock_send,
        )

    # First cycle failed with 400 on solution post, slept backoff (5.0s), second cycle succeeded
    assert len(history) == 1
    assert history[0]["status"] == "completed"
    assert sleep_calls == [5.0]


# ============================================================================
# Vector 4: Loopback Proxy Pollution
# ============================================================================


class LocalMockCoordinatorHandler(BaseHTTPRequestHandler):
    """Minimal HTTP server recording incoming requests for proxy testing."""

    def do_GET(self) -> None:
        if self.path.startswith("/api/v1/work"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "work_id": "wu_proxy_test",
                "problem": "3_3_in_circle",
                "n": 3,
                "target_s": 3.0,
                "recommended_attempts": 10,
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')

    def do_POST(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "recorded", "worker_id": "mock_id"}')

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def local_http_server():
    """Start in-process HTTP server on 127.0.0.1 for live network testing."""
    server = HTTPServer(("127.0.0.1", 0), LocalMockCoordinatorHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}", f"http://localhost:{port}"
    server.shutdown()
    server.server_close()


def test_loopback_proxy_pollution_bypass_127_0_0_1(local_http_server):
    """Verify requests to 127.0.0.1 bypass polluted http_proxy/HTTP_PROXY environment."""
    url_127, _ = local_http_server
    proxy_env = {
        "http_proxy": "http://127.0.0.1:9999",
        "HTTP_PROXY": "http://127.0.0.1:9999",
    }

    with patch.dict(os.environ, proxy_env, clear=False):
        resp = send_request(f"{url_127}/api/v1/work", method="GET")

    assert resp.get("work_id") == "wu_proxy_test"


def test_loopback_proxy_pollution_bypass_localhost(local_http_server):
    """Verify requests to localhost bypass polluted http_proxy/HTTP_PROXY environment."""
    _, url_localhost = local_http_server
    proxy_env = {
        "http_proxy": "http://127.0.0.1:9999",
        "HTTP_PROXY": "http://127.0.0.1:9999",
    }

    with patch.dict(os.environ, proxy_env, clear=False):
        resp = send_request(f"{url_localhost}/api/v1/work", method="GET")

    assert resp.get("work_id") == "wu_proxy_test"


def test_loopback_proxy_pollution_full_worker_cycle(local_http_server):
    """Verify complete worker cycle executes against local server despite proxy pollution."""
    url_127, _ = local_http_server
    proxy_env = {
        "http_proxy": "http://127.0.0.1:9999",
        "HTTP_PROXY": "http://127.0.0.1:9999",
    }

    config = WorkerConfig(
        server_url=url_127,
        worker_id="w_proxy_victim",
    )

    with patch.dict(os.environ, proxy_env, clear=False):
        res = run_worker_cycle(
            config=config,
            solver_fn=lambda **kw: {"success": True, "score": 3.1, "values": [0.0] * 9},
        )

    assert res["status"] == "completed"
    assert res["attempts_completed"] == 10
    assert res["metric_s"] == 3.1


def test_non_loopback_proxy_routing_negative_check():
    """Verify non-loopback addresses DO route through proxy and fail when proxy is invalid."""
    proxy_env = {
        "http_proxy": "http://127.0.0.1:9999",
        "HTTP_PROXY": "http://127.0.0.1:9999",
    }

    with patch.dict(os.environ, proxy_env, clear=False):
        with pytest.raises(urllib.error.URLError) as exc_info:
            send_request("http://example.com/api/v1/work", timeout=0.5)

    # Confirms it failed trying to reach the invalid proxy 127.0.0.1:9999
    assert "refused" in str(exc_info.value).lower() or "connection" in str(exc_info.value).lower()


# ============================================================================
# Additional Stress & Boundary Vectors
# ============================================================================


def test_nan_and_inf_metrics_not_submitted():
    """Verify solver returning NaN or Inf metric is never submitted as an improvement."""
    config = WorkerConfig(worker_id="w_nan")
    solutions_called: List[Dict[str, Any]] = []

    def mock_send(url: str, method: str = "GET", payload: Any = None, **kwargs: Any) -> Dict[str, Any]:
        if "work" in url:
            return {
                "work_id": "wu_nan",
                "problem": "3_3_in_circle",
                "n": 3,
                "target_s": 3.0,
                "recommended_attempts": 100,
            }
        elif "solutions" in url:
            solutions_called.append(payload)
            return {"status": "accepted"}
        return {"status": "ok"}

    # Test with NaN
    res_nan = run_worker_cycle(
        config=config,
        solver_fn=lambda **kw: {"success": True, "score": float("nan"), "values": [0.0] * 9},
        request_fn=mock_send,
    )
    assert res_nan["found_improvement"] is False
    assert len(solutions_called) == 0

    # Test with Inf
    res_inf = run_worker_cycle(
        config=config,
        solver_fn=lambda **kw: {"success": True, "score": float("inf"), "values": [0.0] * 9},
        request_fn=mock_send,
    )
    assert res_inf["found_improvement"] is False
    assert len(solutions_called) == 0


def test_400_with_plaintext_non_json_body():
    """Verify send_request safely handles HTTP 400 with non-JSON plaintext error body."""
    raw_plaintext = b"Bad Request: Malformed coordinate array length"
    http_err = urllib.error.HTTPError(
        url="http://coordinator.example.com/api/v1/solutions",
        code=400,
        msg="Bad Request",
        hdrs=MagicMock(),
        fp=io.BytesIO(raw_plaintext),
    )

    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            send_request("http://coordinator.example.com/api/v1/solutions", method="POST", payload={})

    exc = exc_info.value
    assert exc.code == 400
    assert exc.error_data == {}
    assert exc.error_body == raw_plaintext.decode("utf-8")
    # Stream is still replayable via exc.read()
    assert exc.read() == raw_plaintext


def test_registration_400_surfaces_error_diagnostics():
    """Verify worker registration failure with 400 raises HTTPError with parsed error_data."""
    error_payload = b'{"detail": "Username cannot be empty"}'
    http_err = urllib.error.HTTPError(
        url="http://coordinator.example.com:8000/api/v1/workers/register",
        code=400,
        msg="Bad Request",
        hdrs=MagicMock(),
        fp=io.BytesIO(error_payload),
    )

    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            nw.register_with_server("http://coordinator.example.com:8000", username="")

    exc = exc_info.value
    assert exc.code == 400
    assert hasattr(exc, "error_data")
    assert exc.error_data.get("detail") == "Username cannot be empty"

