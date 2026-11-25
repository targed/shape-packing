"""Comprehensive test suite for Native Worker Client Daemon.

Covers all 9 specification categories plus AST inspection and proxy bypass tests:
1. Configuration Initialization (WorkerConfig)
2. Client Networking with stdlib urllib (send_request)
3. Worker Registration Flow (register_with_server)
4. Work Polling Loop with 204 Backoff
5. Heartbeat Emission (HeartbeatReporter)
6. Solution Submission on Improvement
7. Idle OS Priority Scheduling (set_process_idle_priority / set_idle_priority)
8. Signal Handling & Graceful Shutdown
9. Single-Cycle & Multi-Cycle Execution
10. AST Dependency Verification & Loopback Proxy Bypass
"""

from __future__ import annotations

import ast
import io
import os
import signal
import threading
import time
from typing import Any, Dict, List
import urllib.error
import urllib.request
from unittest.mock import MagicMock, Mock, patch

import pytest

import src.shape_packing.client.native_worker as nw
from src.shape_packing.client.native_worker import (
    HeartbeatReporter,
    WorkerConfig,
    _get_opener,
    flush_in_flight_heartbeat,
    handle_signal,
    main,
    register_with_server,
    run_worker_cycle,
    run_worker_loop,
    send_request,
    set_idle_priority,
    set_in_flight_work,
    set_process_idle_priority,
)


@pytest.fixture(autouse=True)
def reset_global_worker_state():
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
# Group 1: Configuration Initialization (WorkerConfig)
# ============================================================================


def test_config_defaults():
    """Test WorkerConfig default parameter values."""
    config = WorkerConfig()
    assert config.server_url == "https://shape-packing-ggd4d5e8c2ctggam.eastus-01.azurewebsites.net"
    assert config.coordinator_url == "https://shape-packing-ggd4d5e8c2ctggam.eastus-01.azurewebsites.net"
    assert config.username == "anonymous"
    assert config.worker_id is None
    assert config.cores == 1
    assert config.poll_interval == 5.0
    assert config.heartbeat_interval == 30.0
    assert config.timeout == 10.0
    assert config.client_type == "native"


def test_config_from_env():
    """Test WorkerConfig.from_env() ingesting environment variables."""
    env = {
        "SHAPE_PACKING_SERVER_URL": "http://coord:9000",
        "SHAPE_PACKING_USERNAME": "volunteer1",
        "SHAPE_PACKING_CORES": "8",
        "SHAPE_PACKING_WORKER_ID": "worker-uuid-42",
    }
    with patch.dict(os.environ, env, clear=False):
        config = WorkerConfig.from_env()
        assert config.server_url == "http://coord:9000"
        assert config.coordinator_url == "http://coord:9000"
        assert config.username == "volunteer1"
        assert config.cores == 8
        assert config.worker_id == "worker-uuid-42"


def test_config_overrides():
    """Test constructor overrides take precedence over defaults and environment."""
    env = {
        "SHAPE_PACKING_SERVER_URL": "http://env-coord:8000",
        "SHAPE_PACKING_CORES": "2",
    }
    with patch.dict(os.environ, env, clear=False):
        config = WorkerConfig.from_env(
            server_url="http://custom-host:8080",
            cores=4,
            username="custom_user",
        )
        assert config.server_url == "http://custom-host:8080"
        assert config.cores == 4
        assert config.username == "custom_user"


def test_config_normalization():
    """Test trailing slashes are stripped from server_url and empty url raises."""
    config = WorkerConfig(server_url="http://localhost:8000///")
    assert config.server_url == "http://localhost:8000"
    assert config.coordinator_url == "http://localhost:8000"

    with pytest.raises(ValueError, match="server_url cannot be empty"):
        WorkerConfig(server_url="")


def test_config_validation_cores():
    """Test validation rejecting cores < 1."""
    with pytest.raises(ValueError, match="cores must be >= 1"):
        WorkerConfig(cores=0)

    with pytest.raises(ValueError, match="cores must be >= 1"):
        WorkerConfig(cores=-2)


# ============================================================================
# Group 2: send_request with stdlib urllib
# ============================================================================


def make_mock_response(status: int = 200, body: bytes = b"{}") -> MagicMock:
    """Create a mock urllib HTTPResponse that acts as a context manager and readable stream."""
    resp = MagicMock()
    resp.__enter__.return_value = resp
    resp.status = status
    resp.getcode.return_value = status
    resp.read.return_value = body
    return resp


def test_send_request_get_200():
    """Test GET request returning HTTP 200 with JSON payload."""
    mock_resp = make_mock_response(status=200, body=b'{"status": "ok", "count": 42}')

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = send_request("http://coordinator.example.com/test", method="GET")

    assert result == {"status": "ok", "count": 42}
    assert mock_urlopen.called
    req = mock_urlopen.call_args[0][0]
    assert req.get_method() == "GET"
    assert req.get_header("Accept") == "application/json"


def test_send_request_post_200():
    """Test POST request with UTF-8 JSON payload and content headers."""
    mock_resp = make_mock_response(status=200, body=b'{"status": "accepted"}')

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = send_request(
            "http://coordinator.example.com/api/v1/solutions",
            method="POST",
            payload={"s": 2.5, "n": 3},
        )

    assert result == {"status": "accepted"}
    req = mock_urlopen.call_args[0][0]
    assert req.get_method() == "POST"
    assert req.get_header("Content-type") == "application/json"
    assert req.data == b'{"s": 2.5, "n": 3}'


def test_send_request_204_no_content():
    """Test HTTP 204 No Content response returning empty dict without JSONDecodeError."""
    mock_resp = make_mock_response(status=204, body=b"")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = send_request("http://coordinator.example.com/api/v1/work", method="GET")

    assert result == {}


def test_send_request_400_bad_request():
    """Test HTTP 400 Bad Request error payload extraction and re-raising."""
    error_body = b'{"status": "rejected", "message": "Geometric verification failed"}'
    http_err = urllib.error.HTTPError(
        url="http://coordinator.example.com/api/v1/solutions",
        code=400,
        msg="Bad Request",
        hdrs=MagicMock(),
        fp=io.BytesIO(error_body),
    )

    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            send_request("http://coordinator.example.com/api/v1/solutions", method="POST", payload={})

    assert exc_info.value.code == 400
    assert hasattr(exc_info.value, "error_data")
    assert exc_info.value.error_data.get("message") == "Geometric verification failed"
    assert exc_info.value.error_body == error_body.decode("utf-8")
    # Ensure fp can still be read
    assert exc_info.value.read() == error_body


def test_send_request_timeout():
    """Test socket / network timeout raising URLError."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timed out")):
        with pytest.raises(urllib.error.URLError):
            send_request("http://coordinator.example.com/api/v1/work", timeout=0.1)


def test_send_request_connection_refused():
    """Test unreachable coordinator host raising URLError."""
    err = urllib.error.URLError(ConnectionRefusedError("Connection refused"))
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(urllib.error.URLError):
            send_request("http://unreachable-host:9999/api/v1/work")


def test_send_request_loopback_proxy_bypass_routing():
    """Test loopback URLs route through build_opener(ProxyHandler({})) and bypass urlopen."""
    mock_resp = make_mock_response(status=200, body=b'{"status": "loopback_ok"}')
    mock_opener = MagicMock()
    mock_opener.open.return_value = mock_resp

    with patch("urllib.request.build_opener", return_value=mock_opener) as mock_build:
        with patch("urllib.request.urlopen") as mock_urlopen:
            res = send_request("http://localhost:8000/api/v1/work")

    assert res == {"status": "loopback_ok"}
    assert mock_build.called
    assert mock_opener.open.called
    assert not mock_urlopen.called


def test_send_request_custom_opener_injection():
    """Test caller-supplied opener is directly invoked without using urlopen or _get_opener."""
    mock_resp = make_mock_response(status=200, body=b'{"status": "injected_ok"}')
    mock_opener = MagicMock()
    mock_opener.open.return_value = mock_resp

    with patch("urllib.request.urlopen") as mock_urlopen:
        res = send_request("http://any-server:8000/test", opener=mock_opener)

    assert res == {"status": "injected_ok"}
    assert mock_opener.open.called
    assert not mock_urlopen.called


# ============================================================================
# Group 3: Worker Registration Flow
# ============================================================================


def test_register_with_server_generates_id():
    """Test worker registration successfully returning assigned worker_id."""
    mock_resp = {"worker_id": "uuid-test-1", "username": "alice", "status": "registered"}
    with patch("src.shape_packing.client.native_worker.send_request", return_value=mock_resp):
        w_id = register_with_server("http://localhost:8000", "alice")

    assert w_id == "uuid-test-1"


def test_register_with_server_existing_id():
    """Test worker registration preserving client-supplied worker_id."""
    captured: Dict[str, Any] = {}

    def mock_send(url, method="GET", payload=None, **kwargs):
        captured["url"] = url
        captured["payload"] = payload
        return {"worker_id": payload["worker_id"], "status": "registered"}

    with patch("src.shape_packing.client.native_worker.send_request", side_effect=mock_send):
        w_id = register_with_server("http://localhost:8000", "bob", worker_id="fixed-uuid")

    assert w_id == "fixed-uuid"
    assert captured["url"] == "http://localhost:8000/api/v1/workers/register"
    assert captured["payload"] == {
        "username": "bob",
        "client_type": "native",
        "worker_id": "fixed-uuid",
    }


def test_register_with_server_network_error():
    """Test worker registration raising when coordinator is unreachable."""
    with patch(
        "src.shape_packing.client.native_worker.send_request",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        with pytest.raises(urllib.error.URLError):
            register_with_server("http://localhost:8000", "alice")


# ============================================================================
# Group 4: Work Polling Loop with 204 Backoff
# ============================================================================


def test_run_worker_cycle_204_idle():
    """Test single cycle returns idle status when coordinator returns 204 No Content."""
    config = WorkerConfig(worker_id="test_w1")
    with patch("src.shape_packing.client.native_worker.send_request", return_value={}):
        mock_solver = MagicMock()
        result = run_worker_cycle(config, solver_fn=mock_solver)

    assert result == {"status": "idle", "attempts_completed": 0, "found_improvement": False}
    assert not mock_solver.called


def test_run_worker_loop_204_backoff_sleep():
    """Test worker loop performs poll_interval backoff sleep on 204 No Content."""
    config = WorkerConfig(worker_id="test_w1", poll_interval=3.5)

    with patch("src.shape_packing.client.native_worker.send_request", return_value={}):
        with patch.object(nw._GLOBAL_STOP_EVENT, "wait", return_value=False) as mock_wait:
            history = run_worker_loop(config, max_cycles=1)

    assert len(history) == 1
    assert history[0]["status"] == "idle"
    mock_wait.assert_called_with(timeout=3.5)


# ============================================================================
# Group 5: Heartbeat Emission
# ============================================================================


def test_heartbeat_emitted_after_solver_batch():
    """Test heartbeat reporting total completed attempts and best score to coordinator."""
    config = WorkerConfig(worker_id="w_heartbeat", server_url="http://coord:8000")

    mock_work = {
        "work_id": "wu_1",
        "problem": "3_3_in_circle",
        "inner_token": "3",
        "container_token": "CIRCLE",
        "n": 3,
        "target_s": 3.0,
        "recommended_attempts": 1000,
    }

    mock_solver_res = {
        "success": True,
        "score": 2.95,
        "values": [0.0] * 9,
    }

    recorded_calls: List[Dict[str, Any]] = []

    def mock_send(url, method="GET", payload=None, **kwargs):
        if "work" in url:
            return mock_work
        elif "heartbeat" in url:
            recorded_calls.append(payload)
            return {"status": "recorded"}
        elif "solutions" in url:
            return {"status": "accepted"}
        return {}

    with patch("src.shape_packing.client.native_worker.send_request", side_effect=mock_send):
        run_worker_cycle(config, solver_fn=lambda **kw: mock_solver_res)

    assert len(recorded_calls) >= 1
    last_hb = recorded_calls[-1]
    assert last_hb["worker_id"] == "w_heartbeat"
    assert last_hb["work_id"] == "wu_1"
    assert last_hb["attempts_completed"] == 1000
    assert last_hb["best_local_s"] == 2.95


def test_heartbeat_flush_retry_preserves_concurrent_in_flight_attempts():
    """Verify in-flight state is not overwritten by stale values when flush network call fails."""
    reporter = HeartbeatReporter(
        server_url="http://localhost:8000",
        worker_id="w_retry_sync",
        work_id="wu_sync_test",
    )

    reporter.record_attempts(100, best_s=3.0)

    def failing_send(url, method="POST", payload=None, **kwargs):
        reporter.record_attempts(50, best_s=2.8)
        raise ConnectionResetError("Transient network failure")

    reporter.request_fn = failing_send

    success = reporter.flush(force=True)
    assert success is False

    assert reporter._unreported_attempts == 150
    assert reporter._best_local_s == 2.8

    with nw._IN_FLIGHT_STATE["lock"]:
        assert nw._IN_FLIGHT_STATE["attempts"] == 150
        assert nw._IN_FLIGHT_STATE["best_s"] == 2.8


# ============================================================================
# Group 6: Solution Submission on Improvement
# ============================================================================


def test_solution_submitted_on_improvement():
    """Test candidate solution is submitted when metric beats target_s."""
    config = WorkerConfig(worker_id="w_opt", server_url="http://coord:8000")

    mock_work = {
        "work_id": "wu_opt",
        "problem": "3_3_in_circle",
        "inner_token": "3",
        "container_token": "CIRCLE",
        "n": 3,
        "target_s": 3.0,
        "recommended_attempts": 200,
    }

    coords = [0.1 * i for i in range(9)]
    mock_solver_res = {
        "success": True,
        "best_s": 2.90,
        "values": coords,
    }

    solution_payloads: List[Dict[str, Any]] = []

    def mock_send(url, method="GET", payload=None, **kwargs):
        if "work" in url:
            return mock_work
        elif "solutions" in url:
            solution_payloads.append(payload)
            return {"status": "accepted", "is_new_record": True}
        elif "heartbeat" in url:
            return {"status": "recorded"}
        return {}

    with patch("src.shape_packing.client.native_worker.send_request", side_effect=mock_send):
        res = run_worker_cycle(config, solver_fn=lambda **kw: mock_solver_res)

    assert res["found_improvement"] is True
    assert res["attempts_completed"] == 200
    assert len(solution_payloads) == 1
    assert solution_payloads[0]["work_id"] == "wu_opt"
    assert solution_payloads[0]["problem"] == "3_3_in_circle"
    assert solution_payloads[0]["s"] == 2.90
    assert solution_payloads[0]["coordinates"] == coords


def test_solution_not_submitted_when_no_improvement():
    """Test solution is NOT submitted when metric does not improve target_s."""
    config = WorkerConfig(worker_id="w_no_opt", server_url="http://coord:8000")

    mock_work = {
        "work_id": "wu_no_opt",
        "problem": "3_3_in_circle",
        "inner_token": "3",
        "container_token": "CIRCLE",
        "n": 3,
        "target_s": 3.0,
        "recommended_attempts": 1000,
    }

    # Solver found 3.10 which is worse than target 3.0
    mock_solver_res = {
        "success": True,
        "best_s": 3.10,
        "values": [0.0] * 9,
    }

    solutions_called = []
    heartbeats_called = []

    def mock_send(url, method="GET", payload=None, **kwargs):
        if "work" in url:
            return mock_work
        elif "solutions" in url:
            solutions_called.append(payload)
            return {"status": "accepted"}
        elif "heartbeat" in url:
            heartbeats_called.append(payload)
            return {"status": "recorded"}
        return {}

    with patch("src.shape_packing.client.native_worker.send_request", side_effect=mock_send):
        res = run_worker_cycle(config, solver_fn=lambda **kw: mock_solver_res)

    assert res["found_improvement"] is False
    assert res["attempts_completed"] == 1000
    assert len(solutions_called) == 0
    assert len(heartbeats_called) >= 1
    assert heartbeats_called[-1]["attempts_completed"] == 1000


def test_solution_not_submitted_on_solver_failure():
    """Test solution is NOT submitted when solver reports success=False."""
    config = WorkerConfig(worker_id="w_fail", server_url="http://coord:8000")

    mock_work = {
        "work_id": "wu_fail",
        "problem": "3_3_in_circle",
        "inner_token": "3",
        "container_token": "CIRCLE",
        "n": 3,
        "target_s": 3.0,
        "recommended_attempts": 500,
    }

    mock_solver_res = {
        "success": False,
        "error": "Optimization did not converge",
    }

    solutions_called = []

    def mock_send(url, method="GET", payload=None, **kwargs):
        if "work" in url:
            return mock_work
        elif "solutions" in url:
            solutions_called.append(payload)
            return {}
        elif "heartbeat" in url:
            return {"status": "recorded"}
        return {}

    with patch("src.shape_packing.client.native_worker.send_request", side_effect=mock_send):
        res = run_worker_cycle(config, solver_fn=lambda **kw: mock_solver_res)

    assert res["found_improvement"] is False
    assert len(solutions_called) == 0


def test_attempts_preserved_on_solution_400_rejection():
    """Verify completed solver attempts are flushed to coordinator even if solution POST fails with 400."""
    config = WorkerConfig(worker_id="w_rej_test", server_url="http://coord:8000")

    mock_work = {
        "work_id": "wu_rej_test",
        "problem": "3_3_in_circle",
        "inner_token": "3",
        "container_token": "CIRCLE",
        "n": 3,
        "target_s": 3.0,
        "recommended_attempts": 500,
    }

    mock_solver_res = {
        "success": True,
        "best_s": 2.80,
        "values": [0.0] * 9,
    }

    flushed_heartbeats: List[Dict[str, Any]] = []

    def mock_send(url: str, method: str = "GET", payload: Any = None, **kwargs: Any) -> Dict[str, Any]:
        if "work" in url:
            return mock_work
        elif "solutions" in url:
            # Simulate 400 rejection from geometric verifier
            raw_err = b'{"status": "rejected", "message": "SAT polygon overlap"}'
            raise urllib.error.HTTPError(
                url=url,
                code=400,
                msg="Bad Request",
                hdrs=MagicMock(),
                fp=io.BytesIO(raw_err),
            )
        elif "heartbeat" in url:
            flushed_heartbeats.append(payload)
            return {"status": "recorded"}
        return {}

    with pytest.raises(urllib.error.HTTPError):
        run_worker_cycle(config, solver_fn=lambda **kw: mock_solver_res, request_fn=mock_send)

    # 500 attempts MUST have been flushed to heartbeat despite 400 error
    assert len(flushed_heartbeats) >= 1
    total_attempts_reported = sum(h["attempts_completed"] for h in flushed_heartbeats)
    assert total_attempts_reported == 500
    assert flushed_heartbeats[-1]["work_id"] == "wu_rej_test"
    assert flushed_heartbeats[-1]["best_local_s"] == 2.80


# ============================================================================
# Group 7: Idle Priority Setting (os.nice)
# ============================================================================


def test_set_idle_priority_posix_success():
    """Test POSIX os.nice(19) priority adjustment success path."""
    with patch("sys.platform", "linux"):
        with patch("os.nice", return_value=19, create=True) as mock_nice:
            assert set_idle_priority() is True
            mock_nice.assert_called_with(19)


def test_set_idle_priority_permission_error_fallback():
    """Test graceful fallback returning False when os.nice raises PermissionError."""
    with patch("sys.platform", "linux"):
        with patch("os.nice", side_effect=PermissionError("Operation not permitted"), create=True):
            assert set_idle_priority() is False


def test_set_idle_priority_windows_fallback():
    """Test graceful fallback returning False when os has no nice attribute."""
    # Ensure set_idle_priority handles platforms without os.nice
    with patch("sys.platform", "linux"):
        orig_nice = getattr(os, "nice", None)
        orig_setpriority = getattr(os, "setpriority", None)
        try:
            if hasattr(os, "nice"):
                delattr(os, "nice")
            if hasattr(os, "setpriority"):
                delattr(os, "setpriority")
            assert set_idle_priority() is False
        finally:
            if orig_nice is not None:
                setattr(os, "nice", orig_nice)
            if orig_setpriority is not None:
                setattr(os, "setpriority", orig_setpriority)


# ============================================================================
# Group 8: Signal Handling & Graceful Shutdown
# ============================================================================


def test_handle_signal_sets_shutdown_flag():
    """Test handle_signal sets _SHUTDOWN flag and unblocks global event."""
    assert nw._SHUTDOWN is False
    handle_signal(signal.SIGINT, None)
    assert nw._SHUTDOWN is True
    assert nw._GLOBAL_STOP_EVENT.is_set()


def test_graceful_shutdown_flushes_inflight_heartbeat():
    """Test flush_in_flight_heartbeat reports in-flight attempts upon shutdown."""
    config = WorkerConfig(worker_id="w_shutdown", server_url="http://coord:8000")
    set_in_flight_work("wu_inflight", 500, 2.85)

    flushed_payloads: List[Dict[str, Any]] = []

    def mock_send(url, method="GET", payload=None, **kwargs):
        if "heartbeat" in url:
            flushed_payloads.append(payload)
            return {"status": "recorded"}
        return {}

    success = flush_in_flight_heartbeat(config, request_fn=mock_send)
    assert success is True
    assert len(flushed_payloads) == 1
    assert flushed_payloads[0] == {
        "worker_id": "w_shutdown",
        "work_id": "wu_inflight",
        "attempts_completed": 500,
        "best_local_s": 2.85,
    }


def test_loop_terminates_promptly_when_shutdown_requested():
    """Test worker loop exits immediately without executing work if shutdown is set."""
    config = WorkerConfig(worker_id="w_stop")
    nw._SHUTDOWN = True

    mock_send = MagicMock()
    history = run_worker_loop(config, request_fn=mock_send)

    assert history == []
    assert not mock_send.called


def test_sigint_unblocks_idle_wait_immediately():
    """Verify worker loop terminates immediately when signal triggers stop_event during idle poll wait."""
    config = WorkerConfig(worker_id="w_sig_test", poll_interval=10.0)
    ev = threading.Event()

    timer = threading.Timer(0.05, ev.set)
    timer.start()

    t0 = time.time()
    with patch("src.shape_packing.client.native_worker.send_request", return_value={}):
        history = run_worker_loop(config, stop_event=ev)
    elapsed = time.time() - t0
    timer.cancel()

    assert elapsed < 1.0, f"Worker loop hung for {elapsed:.2f}s during idle wait"


# ============================================================================
# Group 9: Single-Cycle & Multi-Cycle Execution
# ============================================================================


def test_single_cycle_end_to_end():
    """Test full single-cycle execution matching complete return schema."""
    config = WorkerConfig(worker_id="w_e2e", server_url="http://coord:8000")
    mock_work = {
        "work_id": "wu_e2e",
        "problem": "circle_sq",
        "inner_token": "4",
        "container_token": "SQUARE",
        "n": 4,
        "target_s": 4.5,
        "recommended_attempts": 100,
    }

    mock_solver_res = {
        "success": True,
        "score": 4.2,
        "coordinates": [0.0] * 12,
    }

    def mock_send(url, method="GET", payload=None, **kwargs):
        if "work" in url:
            return mock_work
        elif "solutions" in url:
            return {"status": "accepted", "is_new_record": True}
        elif "heartbeat" in url:
            return {"status": "recorded"}
        return {}

    cycle_res = run_worker_cycle(
        config,
        solver_fn=lambda **kw: mock_solver_res,
        request_fn=mock_send,
    )

    assert cycle_res["status"] == "completed"
    assert cycle_res["attempts_completed"] == 100
    assert cycle_res["found_improvement"] is True
    assert cycle_res["metric_s"] == 4.2


def test_multi_cycle_max_cycles():
    """Test multi-cycle loop executes exactly max_cycles iterations."""
    config = WorkerConfig(worker_id="w_multi", server_url="http://coord:8000")
    counter = 0

    def mock_send(url, method="GET", payload=None, **kwargs):
        nonlocal counter
        if "work" in url:
            counter += 1
            return {
                "work_id": f"wu_{counter}",
                "problem": "prob",
                "inner_token": "3",
                "container_token": "CIRCLE",
                "n": 3,
                "target_s": 3.0,
                "recommended_attempts": 50,
            }
        return {"status": "ok"}

    history = run_worker_loop(
        config,
        max_cycles=3,
        solver_fn=lambda **kw: {"success": True, "score": 3.2, "values": [0.0] * 9},
        request_fn=mock_send,
    )

    assert len(history) == 3
    assert all(c["status"] == "completed" for c in history)
    assert all(c["attempts_completed"] == 50 for c in history)


def test_multi_cycle_error_recovery():
    """Test worker loop catches transient URLError, backs off, and recovers on next cycle."""
    config = WorkerConfig(worker_id="w_retry", server_url="http://coord:8000")
    call_count = 0

    def mock_send(url, method="GET", payload=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise urllib.error.URLError("Temporary connection glitch")
        if "work" in url:
            return {
                "work_id": "wu_recovered",
                "problem": "prob",
                "inner_token": "3",
                "container_token": "CIRCLE",
                "n": 3,
                "target_s": 3.0,
                "recommended_attempts": 50,
            }
        return {"status": "ok"}

    with patch.object(nw._GLOBAL_STOP_EVENT, "wait", return_value=False) as mock_wait:
        history = run_worker_loop(
            config,
            max_cycles=1,
            solver_fn=lambda **kw: {"success": True, "score": 3.2, "values": [0.0] * 9},
            request_fn=mock_send,
        )

    # First attempt failed, backoff sleep occurred, second attempt succeeded
    assert len(history) == 1
    assert history[0]["status"] == "completed"
    assert mock_wait.called


# ============================================================================
# Group 10: Mandatory AST Verification & Proxy Bypass
# ============================================================================


def test_zero_external_networking_dependencies():
    """AST inspection verifying zero forbidden networking libraries imported."""
    client_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "src",
        "shape_packing",
        "client",
        "native_worker.py",
    )
    client_path = os.path.abspath(client_path)
    assert os.path.exists(client_path), f"File {client_path} does not exist"

    with open(client_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=client_path)

    forbidden = {"requests", "httpx", "aiohttp", "urllib3"}
    imported: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])

    violations = imported.intersection(forbidden)
    assert not violations, f"Forbidden networking libraries imported in native_worker.py: {violations}"


def test_proxy_bypass_loopback_configuration():
    """Verify loopback addresses create custom opener with empty ProxyHandler."""
    assert _get_opener("http://127.0.0.1:8000/api") is not None
    assert _get_opener("http://localhost:8000/api") is not None
    assert _get_opener("http://[::1]:8000/api") is not None
    assert _get_opener("http://remote-cluster.internal:8000/api") is None


def test_main_cli_execution():
    """Verify CLI main entrypoint registers worker and runs specified cycles."""
    mock_reg = {"worker_id": "cli_uuid_1"}
    mock_work = {
        "work_id": "wu_cli",
        "problem": "3_3_in_circle",
        "inner_token": "3",
        "container_token": "CIRCLE",
        "n": 3,
        "target_s": 3.0,
        "recommended_attempts": 10,
    }

    def mock_send(url, method="GET", payload=None, **kwargs):
        if "register" in url:
            return mock_reg
        elif "work" in url:
            return mock_work
        return {"status": "ok"}

    with patch("src.shape_packing.client.native_worker.send_request", side_effect=mock_send):
        with patch(
            "src.shape_packing.client.native_worker._invoke_solver",
            return_value={"success": True, "score": 3.1, "values": [0.0] * 9},
        ):
            main(["--server", "http://localhost:8000", "--username", "testcli", "--max-cycles", "1"])


def test_zero_mock_sniffing_in_production():
    """Verify zero test-framework sniffing or mock attribute inspections exist in production code."""
    import ast
    client_path = os.path.abspath("src/shape_packing/client/native_worker.py")
    with open(client_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    # 1. Plaintext / grep assertions
    assert "mock_calls" not in source_code, (
        "Integrity violation: 'mock_calls' detected in production native_worker.py"
    )
    assert "unittest.mock" not in source_code, (
        "Integrity violation: 'unittest.mock' imported in production native_worker.py"
    )

    # 2. Comprehensive AST walk
    tree = ast.parse(source_code, filename=client_path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr != "mock_calls", (
                f"Line {node.lineno}: Prohibited test-sniffing attribute access '.{node.attr}' in production code"
            )
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                assert "mock_calls" not in node.value, (
                    f"Line {node.lineno}: Prohibited 'mock_calls' string literal in production code"
                )

