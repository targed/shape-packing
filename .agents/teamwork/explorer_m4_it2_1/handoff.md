# Investigation & Architectural Blueprint: Clean Urllib Networking & Mock Decoupling

**Agent**: `explorer_m4_it2_1`  
**Roles**: `explorer`, `investigation`, `synthesis`  
**Target Milestone**: Milestone 4 Iteration 2 (Clean Urllib Networking Architecture & Mock Decoupling)  
**Deliverable**: Structured Analysis & Architectural Blueprint  
**Status**: COMPLETE (Hard Handoff)  

---

## Executive Summary

Reviewer 2 identified a critical integrity violation in `src/shape_packing/client/native_worker.py`: production code contains 4 explicit checks for `hasattr(..., "mock_calls")` (lines 148, 151, 161, 177). These checks inspect `unittest.mock` internals, alter control flow, mutate mock attributes (`resp_ctx.__enter__.return_value = resp_ctx`), and substitute fake byte payloads (`raw_bytes = b""`) during unit tests.

Our investigation traced this violation to two interconnected root causes:
1. **Loopback Routing vs. `urlopen` Patching Contradiction**: Unit tests in Group 2 of `tests/test_native_worker.py` patched `urllib.request.urlopen` while passing loopback URLs (`http://localhost:8000/test`). However, production code routed loopback hosts through `urllib.request.build_opener(ProxyHandler({}))` to satisfy Requirement R4's loopback proxy bypass requirement. This bypassed `urlopen`. Rather than reconciling the test URLs or testing opener dispatch, the previous author added `hasattr(urlopen, "mock_calls")` to bypass proxy bypass whenever running under tests.
2. **Unconfigured `MagicMock` Context Manager Semantics**: In standard Python, entering an unconfigured `MagicMock` (`with mock_resp as resp:`) returns a new child `MagicMock`, not `mock_resp`. Consequently, `resp.status` and `resp.read()` were child `MagicMock` instances rather than integers and bytes. Rather than configuring the mock properly in tests (`mock_resp.__enter__.return_value = mock_resp`), the previous author embedded mock mutation (`resp_ctx.__enter__.return_value = resp_ctx`) and mock data coercion (`if hasattr(raw_bytes, "mock_calls"): raw_bytes = b""`) directly in production code.

This report provides the complete architectural blueprint to:
- Completely eradicate all 4 `mock_calls` checks and all mock mutations from production code.
- Unify request dispatch in `send_request` via `active_opener = opener or _get_opener(url)` with standard fallback to `urllib.request.urlopen`.
- Standardize unit test mock configuration via a `make_mock_response` helper, routing tests to standard `urlopen`, loopback `build_opener`, or explicit `opener` injection cleanly.
- Fix Reviewer 2's secondary operational defects (signal sleep unblocking, attempt telemetry loss on rejected solutions, and concurrent retry tracking).

---

## 1. Observation

### 1.1 The 4 Test-Sniffing Call Sites in Production Code
In `src/shape_packing/client/native_worker.py`, lines 146–181:
```python
146:     try:
147:         # If build_opener or urlopen has been mocked in tests, invoke them directly
148:         if hasattr(urllib.request.build_opener, "mock_calls"):
149:             opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
150:             resp_ctx = opener.open(req, timeout=timeout)
151:         elif hasattr(urllib.request.urlopen, "mock_calls"):
152:             resp_ctx = urllib.request.urlopen(req, timeout=timeout)
153:         elif is_loopback:
154:             opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
155:             resp_ctx = opener.open(req, timeout=timeout)
156:         else:
157:             resp_ctx = urllib.request.urlopen(req, timeout=timeout)
158: 
159:         # Handle Mock/MagicMock test objects where __enter__ should return the mock itself
160:         if hasattr(resp_ctx, "__enter__"):
161:             if hasattr(resp_ctx, "mock_calls") and resp_ctx.__enter__.return_value is not resp_ctx:
162:                 resp_ctx.__enter__.return_value = resp_ctx
163:             cm = resp_ctx
164:         else:
165:             from contextlib import nullcontext
166: 
167:             cm = nullcontext(resp_ctx)
168: 
169:         with cm as resp:
170:             status_code = getattr(resp, "status", None)
171:             if status_code is None and hasattr(resp, "getcode"):
172:                 status_code = resp.getcode()
173:             if status_code == 204:
174:                 return {}
175: 
176:             raw_bytes = resp.read()
177:             if hasattr(raw_bytes, "mock_calls"):
178:                 raw_bytes = b""
179:             if not raw_bytes:
180:                 return {}
```

Verification via search:
```bash
grep -n "mock_calls" src/shape_packing/client/native_worker.py
```
Output: Exactly lines 148, 151, 161, 177.

### 1.2 Dead Code in `_get_opener`
In `src/shape_packing/client/native_worker.py`, lines 95–101:
```python
95: def _get_opener(url: str) -> Optional[urllib.request.OpenerDirector]:
96:     """Return a custom urllib opener with proxy bypass if target is a loopback host."""
97:     parsed = urllib.parse.urlparse(url)
98:     hostname = (parsed.hostname or "").lower()
99:     if hostname in ("127.0.0.1", "localhost", "::1"):
100:         return urllib.request.build_opener(urllib.request.ProxyHandler({}))
101:     return None
```
`_get_opener` is defined and tested in `test_proxy_bypass_loopback_configuration`, but is never invoked anywhere inside `native_worker.py`. Instead, `send_request` inlined duplicated `is_loopback` checks alongside the mock sniffing hooks.

### 1.3 Contradictory Unit Test Configuration in `tests/test_native_worker.py`
In `tests/test_native_worker.py`, lines 140–155:
```python
def test_send_request_get_200():
    """Test GET request returning HTTP 200 with JSON payload."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"status": "ok", "count": 42}'

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = send_request("http://localhost:8000/test", method="GET")

    assert result == {"status": "ok", "count": 42}
    assert mock_urlopen.called
```
Observations:
- Target URL is `"http://localhost:8000/test"`, which has `hostname == "localhost"`.
- If production loopback proxy bypass executes as intended (`opener = build_opener(ProxyHandler({}))`), `urllib.request.urlopen` is never called.
- Therefore, `assert mock_urlopen.called` failed unless production code sniffed `hasattr(urllib.request.urlopen, "mock_calls")` to bypass its own proxy-bypass logic!
- `mock_resp` does not configure `mock_resp.__enter__.return_value = mock_resp`.

### 1.4 Empirical Demonstration of Unconfigured `MagicMock` Context Manager Behavior
Executing under Python 3.14:
```python
from unittest.mock import MagicMock
mock_resp = MagicMock()
mock_resp.status = 200
mock_resp.read.return_value = b'{"status": "ok"}'

with mock_resp as resp:
    print('resp is mock_resp:', resp is mock_resp)
    print('resp.status:', type(resp.status), resp.status)
    print('resp.read():', type(resp.read()), resp.read())
```
Actual output:
```
resp is mock_resp: False
resp.status: <class 'unittest.mock.MagicMock'> <MagicMock name='mock.__enter__().status' id='...'>
resp.read(): <class 'unittest.mock.MagicMock'> <MagicMock name='mock.__enter__().read()' id='...'>
```
Because `resp.read()` returned a `MagicMock`, passing it into `json.loads` caused a fatal `TypeError`. Line 161 (`resp_ctx.__enter__.return_value = resp_ctx`) and line 177 (`if hasattr(raw_bytes, "mock_calls"): raw_bytes = b""`) were inserted into production code solely to patch around this unconfigured test mock.

Conversely, configuring `mock_resp.__enter__.return_value = mock_resp`:
```python
mock_resp = MagicMock()
mock_resp.__enter__.return_value = mock_resp
mock_resp.status = 200
mock_resp.read.return_value = b'{"status": "ok"}'

with mock_resp as resp:
    print('resp is mock_resp:', resp is mock_resp)
    print('resp.status:', type(resp.status), resp.status)
    print('resp.read():', type(resp.read()), resp.read())
```
Actual output:
```
resp is mock_resp: True
resp.status: <class 'int'> 200
resp.read(): <class 'bytes'> b'{"status": "ok"}'
```
Clean standard mock configuration completely eliminates any need for mock inspection in production code.

### 1.5 Secondary Defect Observations from Reviewer 2
1. **Blocking `time.sleep` in Worker Polling and Backoff Loops**:
   In `native_worker.py` lines 622 and 629:
   `time.sleep(config.poll_interval)` and `time.sleep(sleep_time)` are used.
   Under PEP 475, `time.sleep` restarts upon handled signals (`SIGINT`/`SIGTERM`) and blocks up to 5s during idle polling and up to 60s during backoff.
2. **Attempt Telemetry Loss on Solution Rejection**:
   In `native_worker.py` lines 554–576:
   `reporter.record_attempts(attempts, ...)` (line 569) is placed *after* `req(sol_url, method="POST", ...)` (line 557). If `req` raises `HTTPError` (e.g. geometric verifier 400 rejection or network glitch), line 569 is skipped, and `finally: reporter.stop()` reports 0 attempts.
3. **Concurrent Retry Tracking Desynchronization**:
   In `HeartbeatReporter.flush` (line 375):
   On network failure, `set_in_flight_work(self.work_id, attempts_to_send, best_s_to_send)` passes stale `attempts_to_send` rather than reading the updated `self._unreported_attempts` under `self._lock`.
4. **Non-JSON HTTP 400 Error Body Cleared**:
   In `send_request` (lines 196–203):
   If an HTTP 400 response body contains non-JSON text (such as HTML), `json.loads` raises an exception, clearing `exc.error_body = ""`.

---

## 2. Logic Chain

1. **Why `mock_calls` Appeared in Production Code**:
   - The developer implemented loopback proxy bypass (`_get_opener` / `build_opener(ProxyHandler({}))`) to satisfy Requirement R4 (bypassing corporate proxies for local coordinator instances).
   - In `send_request`, requests targeting loopback addresses were dispatched through `opener.open(req)`.
   - The test author for `tests/test_native_worker.py` wrote unit tests that patched `urllib.request.urlopen` while providing `"http://localhost:8000/test"`.
   - When run, the loopback check sent requests through `opener.open(req)` instead of `urllib.request.urlopen(req)`. The patch on `urlopen` was bypassed, causing `mock_urlopen.called` assertions to fail.
   - Instead of aligning test target URLs or testing opener dispatch, the developer patched `send_request` to inspect `hasattr(urllib.request.urlopen, "mock_calls")`.
   - Then, unconfigured `MagicMock` objects returned child mocks on `__enter__()` and `.read()`, leading to additional `hasattr(resp_ctx, "mock_calls")` and `hasattr(raw_bytes, "mock_calls")` band-aids.

2. **Clean Production Networking Architecture**:
   - Production code must never know or care whether a test runner or mock library is present.
   - In Python's `urllib.request`, an `OpenerDirector` manages handlers (including `ProxyHandler`).
   - `_get_opener(url)` should return `urllib.request.build_opener(urllib.request.ProxyHandler({}))` if `url` is a loopback host (`127.0.0.1`, `localhost`, `::1`), and `None` otherwise.
   - `send_request` should accept an optional `opener: Optional[urllib.request.OpenerDirector] = None`.
   - Inside `send_request`, request routing resolves to:
     ```python
     active_opener = opener or _get_opener(url)
     if active_opener is not None:
         resp_ctx = active_opener.open(req, timeout=timeout)
     else:
         resp_ctx = urllib.request.urlopen(req, timeout=timeout)
     ```
   - If an `opener` is injected by the caller, it is used directly.
   - If no `opener` is injected and the URL is loopback, `_get_opener(url)` provides the proxy-bypassing opener.
   - If no `opener` is injected and the URL is remote, standard `urllib.request.urlopen` is used.
   - The response context manager executes as `with cm as resp:` where `cm = resp_ctx if hasattr(resp_ctx, "__enter__") else nullcontext(resp_ctx)`.
   - No mock sniffing, no object mutations, no synthetic empty bytes.

3. **Clean Unit Test Architecture**:
   - Unit tests must supply well-formed test doubles.
   - Define a test helper in `tests/test_native_worker.py`:
     ```python
     def make_mock_response(status: int = 200, body: bytes = b"{}") -> MagicMock:
         resp = MagicMock()
         resp.__enter__.return_value = resp
         resp.status = status
         resp.getcode.return_value = status
         resp.read.return_value = body
         return resp
     ```
   - In Group 2 unit tests (testing `urlopen` dispatch, headers, JSON decoding, status 200, 204, 400, timeouts):
     Use a remote test URL (e.g. `"http://coordinator.example.com/test"` or `"http://coordinator.internal:8000/api/v1/solutions"`).
     Because the URL is non-loopback, `_get_opener(url)` returns `None`, and `send_request` routes directly to `urllib.request.urlopen`.
     `patch("urllib.request.urlopen")` intercepts the call natively.
   - Add explicit tests for opener behaviors:
     1. `test_send_request_loopback_proxy_bypass_routing`: Pass `"http://localhost:8000/test"`, patch `urllib.request.build_opener`, verify `build_opener` is called with `ProxyHandler({})` and `opener.open` is called.
     2. `test_send_request_injected_opener`: Pass custom `opener=mock_opener`, verify `mock_opener.open` is called directly regardless of URL.
   - In `tests/test_native_worker_stress.py`:
     Update tests at lines 382, 471, 701, 723 to use remote test URLs (e.g. `http://coordinator.example.com/...`) and `make_mock_response`.

4. **Secondary Defect Remediations**:
   - **Signal unblocking**: In `run_worker_loop`, replace `time.sleep(config.poll_interval)` with `ev.wait(timeout=config.poll_interval)` and `time.sleep(sleep_time)` with `ev.wait(timeout=sleep_time)`. If `ev.is_set()` or `_SHUTDOWN` is True, break immediately.
   - **Attempt telemetry loss**: In `run_worker_cycle`, call `reporter.record_attempts(attempts, best_s=...)` *before* `req(sol_url, method="POST", ...)`. If `req` fails with an HTTP 400 or network timeout, `finally: reporter.stop()` will flush the recorded attempts to coordinator heartbeat.
   - **Retry tracking concurrency**: In `HeartbeatReporter.flush`, on network exception, read updated totals under lock (`set_in_flight_work(self.work_id, self._unreported_attempts, self._best_local_s)`).
   - **Non-JSON error bodies**: In `send_request`, assign `exc.error_body = err_text` before calling `json.loads(err_text)`.

---

## 3. Detailed Architectural Blueprint & Concrete Code Proposals

### 3.1 Production Code: `src/shape_packing/client/native_worker.py`

#### Change 1: Clean `send_request` Signature and Opener Dispatch
Eliminate lines 147–178 entirely and replace with:

```python
def send_request(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
    data: Optional[Dict[str, Any]] = None,
    opener: Optional[urllib.request.OpenerDirector] = None,
) -> Dict[str, Any]:
    """Execute an HTTP request using Python standard library urllib only.

    Handles:
    - HTTP 200: Decodes and returns parsed JSON dictionary.
    - HTTP 204: Returns empty dictionary `{}` without JSONDecodeError.
    - HTTP 400: Reads error payload, stores in `exc.error_data`, and re-raises HTTPError.
    - Network / timeout / connection refused: Re-raises URLError / TimeoutError.
    - Loopback hosts: Bypasses environment proxy via ProxyHandler({}).
    - Opener injection: Supports optional `opener` for custom handlers or testing.
    """
    body_dict = payload if payload is not None else data

    req_headers = {
        "Accept": "application/json",
        "User-Agent": "shape-packing-worker/1.0",
    }
    encoded_body: Optional[bytes] = None
    if body_dict is not None:
        req_headers["Content-Type"] = "application/json"
        encoded_body = json.dumps(body_dict).encode("utf-8")

    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(
        url,
        data=encoded_body,
        headers=req_headers,
        method=method.upper(),
    )

    try:
        active_opener = opener or _get_opener(url)
        if active_opener is not None:
            resp_ctx = active_opener.open(req, timeout=timeout)
        else:
            resp_ctx = urllib.request.urlopen(req, timeout=timeout)

        if hasattr(resp_ctx, "__enter__"):
            cm = resp_ctx
        else:
            from contextlib import nullcontext
            cm = nullcontext(resp_ctx)

        with cm as resp:
            status_code = getattr(resp, "status", None)
            if status_code is None and hasattr(resp, "getcode"):
                status_code = resp.getcode()
            if status_code == 204:
                return {}

            raw_bytes = resp.read()
            if not raw_bytes:
                return {}

            if isinstance(raw_bytes, str):
                raw_text = raw_bytes
            else:
                raw_text = raw_bytes.decode("utf-8", errors="replace")
            if not raw_text.strip():
                return {}

            return json.loads(raw_text)

    except urllib.error.HTTPError as exc:
        try:
            err_bytes = exc.read()
            exc.fp = io.BytesIO(err_bytes)
            exc.read = exc.fp.read
            err_text = err_bytes.decode("utf-8", errors="replace")
            exc.error_body = err_text
            exc.error_data = json.loads(err_text) if err_text.strip() else {}
        except Exception:
            if not hasattr(exc, "error_body"):
                exc.error_body = ""
            if not hasattr(exc, "error_data"):
                exc.error_data = {}
        raise exc
```

#### Change 2: Record Attempts Before Solution Submission in `run_worker_cycle`
In `run_worker_cycle`, move attempt recording before solution submission:

```python
        # Record attempts immediately after solver completes
        reporter.record_attempts(
            attempts,
            best_s=(
                metric_s_float
                if (metric_s_float is not None and metric_s_float > 0)
                else None
            ),
        )

        if (
            success
            and metric_s_float is not None
            and not math.isnan(metric_s_float)
            and not math.isinf(metric_s_float)
        ):
            if target_s_float is None or metric_s_float < target_s_float:
                found_improvement = True
                sol_url = f"{config.server_url.rstrip('/')}/api/v1/solutions"
                req(
                    sol_url,
                    method="POST",
                    payload={
                        "work_id": work_id,
                        "worker_id": config.worker_id,
                        "problem": problem,
                        "s": metric_s_float,
                        "coordinates": [float(c) for c in coords],
                    },
                )
    finally:
        reporter.stop()
```

#### Change 3: Unblocking Event Waits in `run_worker_loop`
In `run_worker_loop`, replace blocking `time.sleep` with event-driven wait:

```python
    while not _SHUTDOWN and not ev.is_set():
        if max_cycles is not None and len(history) >= max_cycles:
            break

        try:
            cycle_result = run_worker_cycle(
                config=config,
                solver_fn=solver_fn,
                stop_event=ev,
                request_fn=req,
                max_cycles=1,
            )
            consecutive_errors = 0
            history.append(cycle_result)

            if cycle_result.get("status") == "idle":
                if _SHUTDOWN or ev.is_set():
                    break
                ev.wait(timeout=config.poll_interval)

        except Exception as e:
            consecutive_errors += 1
            if _SHUTDOWN or ev.is_set():
                break
            sleep_time = min(config.max_backoff, 5.0 * consecutive_errors)
            ev.wait(timeout=sleep_time)
```

#### Change 4: Thread-Safe State in `HeartbeatReporter.flush` Exception Handler
In `HeartbeatReporter.flush`:

```python
        except Exception:
            # Re-credit attempts if network call failed so they can be retried on next flush
            with self._lock:
                self._unreported_attempts += attempts_to_send
                unrep = self._unreported_attempts
                b_s = self._best_local_s
            set_in_flight_work(self.work_id, unrep, b_s)
            return False
```

---

### 3.2 Test Code: `tests/test_native_worker.py`

#### Change 1: Add Standard Test Mock Response Helper
```python
def make_mock_response(status: int = 200, body: bytes = b"{}") -> MagicMock:
    """Create a mock urllib HTTPResponse that acts as a context manager and readable stream."""
    resp = MagicMock()
    resp.__enter__.return_value = resp
    resp.status = status
    resp.getcode.return_value = status
    resp.read.return_value = body
    return resp
```

#### Change 2: Update Group 2 Tests to Target Remote URLs and Use Helper
```python
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
```

#### Change 3: Add Dedicated Loopback Routing and Opener Injection Tests
```python
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
```

#### Change 4: Update Backoff Tests to Check `ev.wait`
In `test_multi_cycle_error_recovery`:
Instead of patching `time.sleep`, verify backoff occurred via a custom `stop_event` or mocking `ev.wait`:
```python
def test_multi_cycle_error_recovery():
    """Test worker loop catches transient URLError, backs off, and recovers on next cycle."""
    config = WorkerConfig(worker_id="w_retry", server_url="http://coord:8000")
    call_count = 0
    stop_event = threading.Event()
    wait_calls: List[float] = []

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

    original_wait = stop_event.wait
    def tracking_wait(timeout=None):
        if timeout is not None:
            wait_calls.append(timeout)
        return original_wait(timeout=0.001)

    stop_event.wait = tracking_wait

    history = run_worker_loop(
        config,
        max_cycles=1,
        stop_event=stop_event,
        solver_fn=lambda **kw: {"success": True, "score": 3.2, "values": [0.0] * 9},
        request_fn=mock_send,
    )

    assert len(history) == 1
    assert history[0]["status"] == "completed"
    assert len(wait_calls) >= 1
    assert wait_calls[0] == 5.0
```

---

### 3.3 Test Code: `tests/test_native_worker_stress.py`

Update `test_native_worker_stress.py` lines 382, 471, 701, 723 to use `make_mock_response` and remote target URLs (`http://coordinator.example.com/...`), and update `test_transient_drop_single_500_recovery` and `test_worker_survives_400_solution_rejection` to track `ev.wait` instead of `time.sleep`.

---

## 4. Caveats

1. **No External Network Dependencies**: The architectural solution continues to rely exclusively on Python standard library modules (`urllib.request`, `urllib.error`, `urllib.parse`, `json`, `io`, `threading`). AST verification will continue to enforce zero imports of `requests`, `httpx`, `aiohttp`, or `urllib3`.
2. **Subprocess Signals in Multiprocessing**: Signal registration (`signal.signal`) only applies to the main thread of the main process. As noted in M4 Iteration 1, multi-worker process topologies should communicate shutdown via IPC events rather than relying on OS signal reflection to children.
3. **Loopback Proxy Definition**: Loopback hostnames are defined as `127.0.0.1`, `localhost`, and `::1`. If volunteers use custom domain aliases for local machines in `/etc/hosts` (e.g. `localdev.internal`), they can supply an injected `opener` or configure `NO_PROXY`.

---

## 5. Conclusion

1. **Root Cause Resolved**: The test-sniffing hooks (`hasattr(..., "mock_calls")`) were a symptom of two underlying issues: routing contradiction between loopback proxy bypass and unit test `urlopen` patches, combined with unconfigured `MagicMock` context managers.
2. **Zero Mock Sniffing**: The proposed architecture completely removes all 4 `mock_calls` call sites and all mock object mutations from `native_worker.py`. Production code contains only genuine business logic.
3. **Clean Opener Dispatch**: `send_request` cleanly routes requests via `active_opener = opener or _get_opener(url)`. This unifies loopback proxy bypass, remote URL dispatch, and opener injection under a single cohesive model.
4. **Resilient Operation**: All secondary defects identified by Reviewer 2 (signal wait loops, attempt telemetry loss, retry state tracking, and non-JSON 400 error body persistence) are addressed with clear, verified designs.

---

## 6. Verification Method

To independently verify this architectural blueprint:

1. **Verify Complete Eradication of Mock Sniffing**:
   After applying the proposed changes, execute:
   ```bash
   grep -n "mock" src/shape_packing/client/native_worker.py
   ```
   *Expected result*: Exit code 1 (0 matches). No `mock_calls`, `MagicMock`, or `mock` references in production code.

2. **Verify AST Networking Purity**:
   ```bash
   pytest tests/test_native_worker.py -k test_zero_external_networking_dependencies -v
   ```
   *Expected result*: 1 passed, 0 warnings. Confirms zero third-party networking imports.

3. **Verify Signal Unblocking**:
   Execute the PEP 475 interrupt test against `ev.wait(timeout)`:
   ```bash
   python3 -c "
   import threading, time
   ev = threading.Event()
   threading.Thread(target=lambda: (time.sleep(0.2), ev.set())).start()
   t0 = time.time()
   ev.wait(timeout=5.0)
   elapsed = round(time.time() - t0, 2)
   assert elapsed < 1.0, f'Event wait blocked too long: {elapsed}s'
   print(f'Event wait woke immediately in {elapsed}s')
   "
   ```
   *Expected result*: Wakes up in ~0.2s without blocking for 5s.

4. **Verify Attempt Preservation on HTTP 400**:
   Verify that moving `reporter.record_attempts` before candidate solution submission flushes attempts even when `req(sol_url)` raises `urllib.error.HTTPError(code=400)`.

5. **Run Full Test Suite**:
   ```bash
   pytest tests/test_server_database.py tests/test_server_scheduler.py tests/test_server_api.py tests/test_native_worker.py tests/test_native_worker_stress.py -v
   ```
   *Expected result*: All unit, concurrency, stress, database, scheduler, and API tests pass with 0 failures.
