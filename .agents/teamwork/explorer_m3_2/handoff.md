# Geometric Verification & Solution Ingestion Blueprint (Milestone 3)

**Author:** explorer_m3_2  
**Target:** parent (`86ab9594-ed5d-48cc-9be1-f2844355b5e4`) / worker_m3 / implementer_m3  
**Date:** 2026-11-21T00:18:00Z  

---

## 1. Observation

Direct investigation of the geometric verification subsystem and related server modules revealed the following exact facts, signatures, and behaviors:

### 1.1 Location & Implementation of Verification Engine
- **Module Path**: `src/shape_packing/solution_tools.py`
  - Core verification entrypoint: `verify_solution(sol_path: str, problem_str: Optional[str] = None, tolerance: float = TOLERANCE, check_record: bool = True, reference_path: str = "PACKING_REFERENCE.tsv", min_improvement: float = RECORD_MIN_IMPROVEMENT) -> VerifyResult` (lines 536–592).
  - Tolerance constants defined in `src/shape_packing/packing_config.py` (lines 46–48):
    - `VERIFY_SAT_TOLERANCE = 1e-5` (aliased as `TOLERANCE = 1e-5` in `solution_tools.py:51`).
    - `VERIFY_METRIC_TOLERANCE = 1e-6`.
    - `RECORD_MIN_IMPROVEMENT = 1e-5`.
  - Return dataclass:
    ```python
    @dataclass
    class VerifyResult:
        valid: bool
        metric: float
        errors: List[str]
        new_record: bool
        message: str
    ```

### 1.2 Verification Flow & Internal Mechanics
Inside `verify_solution`:
1. **Solution Loading (`load_solution`, lines 136–200)**:
   - Reads `sol_path` using `json.load(f)`.
   - For `values-style` JSON, extracts:
     - `N = int(sol["N"])`
     - `inner_token = str(sol.get("inner_token", sol.get("inner_sides", 3)))`
     - `container_token = str(sol.get("container_token", sol.get("container_sides", 3)))`
     - `S = float(sol["S"])`
     - `final_metric = float(sol["final_metric"])`
     - `values = [float(v) for v in sol["values"]]`
2. **Metric Scaling Consistency (`_verify_metric_scaling`, lines 278–287)**:
   - Evaluates `calc_metric = compute_friedman_metric(sol.S, sol.inner_token, sol.container_token)`.
   - Checks `diff = abs(calc_metric - sol.final_metric)`.
   - If `diff > VERIFY_METRIC_TOLERANCE` (`1e-6`), appends error:
     `"Metric scaling is incorrect. Computed: {calc_metric}, JSON says: {sol.final_metric}"`.
3. **Container Boundary Confinement (`_verify_container_bounds`, lines 430–445)**:
   - Dispatches based on `sol.container_token.upper()`:
     - `"L"` -> `_verify_l_container_bounds`: bounding box check on vertices against $[-5/6 S, 7/6 S]$, plus reflex cutout obstacle $[1/6 S, 7/6 S]^2$ via SAT (penetration $> tolerance$).
     - `"CIRCLE"` / `"CIR"` -> `_verify_circle_container_bounds`: $\text{hypot}(x, y) \le S + tolerance$ (or $S - 1.0 + tolerance$ for inner circles).
     - Regular Polygons -> `_verify_polygon_container_bounds`: half-plane dot products $v \cdot n \le S \cdot edge\_radii + tolerance$.
   - Any boundary penetration produces error strings, e.g.:
     - `"Shape {i} out of circular bounds! Margin: {dist - limit}"`
     - `"Shape {i} is out of bounds! Violation margin: {violation}"`
     - `"Shape {i} intersects L-container reflex cut-out! Depth: {depth}"`
4. **Pairwise SAT Non-Overlap Check (`_verify_overlap`, lines 447–514)**:
   - Circle inners: distance check $\text{hypot}(\Delta x, \Delta y) \ge 2.0 - tolerance$.
   - Regular / convex polygons: computes outward normals and invokes `sat_check_overlap(poly1, poly2, normals1, normals2)` for all $N(N-1)/2$ pairs. If `overlap and depth > tolerance`, records:
     `"Shapes {i} and {j} overlap! Depth: {depth}"`.
   - Compound shapes (L-tromino): decomposes into convex parts and tests all constituent sub-parts.
5. **Record Verification**:
   - Gated by `if check_record and problem_str:`.
   - When called with `check_record=False`, `new_record` is unconditionally `False`.

### 1.3 Exception Surface in `verify_solution`
When calling `verify_solution(sol_path, ...)`:
- `FileNotFoundError` / `OSError`: file does not exist or cannot be read.
- `json.JSONDecodeError`: malformed JSON.
- `KeyError`: missing `"N"`, `"S"`, `"final_metric"`, or `"values"`.
- `ValueError`: neither `"values"` nor `"positions"` present, or non-numeric values in numeric fields.
- `IndexError`: if `len(values) < 3 * N`, `build_polygons` raises `IndexError: list index out of range` on `sol.values[i * 3 + 2]`.
- If `len(values) > 3 * N`, `build_polygons` silently ignores the excess elements unless explicitly validated beforehand.

### 1.4 Empirical Verification Tests Run
1. **Metric Scaling Mismatch Test**:
   ```bash
   PYTHONPATH=src python3 -c "
   import tempfile, json, os
   from shape_packing.solution_tools import verify_solution
   data = {'S': 2.5, 'inner_token': '3', 'container_token': 'CIRCLE', 'final_metric': 2.5, 'N': 3, 'values': [0.0]*9}
   with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as tf:
       json.dump(data, tf); p = tf.name
   res = verify_solution(p, check_record=False)
   print(res.errors)
   "
   ```
   **Result**: `['Metric scaling is incorrect. Computed: 1.4433756729740645, JSON says: 2.5', 'Shapes 0 and 1 overlap! Depth: 1.5', ...]`
2. **Metric Consistency via `inverse_friedman_metric` Test**:
   ```bash
   PYTHONPATH=src python3 -c "
   import tempfile, json, os
   from shape_packing.solution_tools import verify_solution, compute_friedman_metric, inverse_friedman_metric
   s_submitted = 2.5
   solver_S = inverse_friedman_metric(s_submitted, '3', 'CIRCLE')
   data = {'S': solver_S, 'inner_token': '3', 'container_token': 'CIRCLE', 'final_metric': s_submitted, 'N': 3, 'values': [-2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0]}
   with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as tf:
       json.dump(data, tf); p = tf.name
   res = verify_solution(p, check_record=False)
   print('valid:', res.valid, 'metric:', res.metric, 'errors:', res.errors)
   "
   ```
   **Result**: `valid: True, metric: 2.5, errors: []`.
3. **Execution Latency Benchmark**:
   Benchmarked 100 iterations of writing a temporary JSON file to disk, calling `verify_solution`, and unlinking:
   **Result**: `100 verifications took: 0.0223s (0.22ms per verification)`.

---

## 2. Logic Chain

From the observed facts and specifications, the reasoning proceeds as follows:

1. **Parameter Interpretation ($s$ vs $S$)**:
   - In SQLite (`problems.best_s`, `problems.reference_s`) and Friedman benchmark files (`data/packingVerification/*.json`), stored metrics are the **Friedman metric** (ratio of container size to inner shape side length or container radius).
   - In continuous optimization solvers (`packer_rs`), the internal optimization variable is the container **circumradius $S$**.
   - Callers of `POST /api/v1/solutions` submit `"s": float` and `"coordinates": List[float]`. The coordinates are positioned in a coordinate frame scaled to circumradius $S$.
   - To construct a solution file that passes `_verify_metric_scaling` without synthetic scaling errors while evaluating container boundaries correctly:
     $$\text{solver\_S} = \text{inverse\_friedman\_metric}(\text{req.s}, \text{prob["inner\_token"]}, \text{prob["container\_token"]})$$
     $$\text{final\_metric} = \text{req.s}$$
   - When `verify_solution` loads this file, `compute_friedman_metric(solver_S, ...)` yields exactly `req.s`, satisfying `abs(calc_metric - final_metric) == 0.0 <= 1e-6`.
   - The returned `res.metric` is identical to `req.s` and directly comparable to `problems.best_s`.

2. **Pre-Verification Dimension Check**:
   - Because `verify_solution` raises an uncaught `IndexError` if `len(coordinates) < 3 * N`, and silently ignores trailing entries if `len(coordinates) > 3 * N`, the coordinator must validate `len(req.coordinates) == prob["n"] * 3` before attempting file creation.
   - If the count does not match, return HTTP 400 Bad Request immediately.

3. **Temporary File Management**:
   - `verify_solution` strictly takes a file path string. In-memory StringIO is not accepted.
   - Using `tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)` wrapped in a `try...finally` block guarantees that the file is deleted regardless of whether verification succeeds, fails, or raises an unexpected error.
   - At 0.22ms per verification, disk file round-trips add zero measurable overhead to the coordinator service.

4. **HTTP Status Code & Response Payload Mapping**:
   - Acceptance Criteria §Geometric Verification states:
     - Submissions with overlapping polygons or boundary penetrations are rejected with a 400 error.
     - Verified improvements atomically update the best record and increment the finder's leaderboard score.
   - FastAPIs default `HTTPException(status_code=400, detail=...)` produces `{"detail": ...}`, which breaks clients expecting `{"status": "rejected", "verified": false, "message": ...}`.
   - Therefore, geometric rejections must return `fastapi.responses.JSONResponse`:
     - **HTTP 400 Bad Request**:
       ```json
       {
         "status": "rejected",
         "verified": false,
         "message": "Geometric verification failed: <errors>"
       }
       ```
     - **HTTP 200 OK (New Record)**:
       ```json
       {
         "status": "accepted",
         "verified": true,
         "is_new_record": true,
         "metric_s": 2.8449112,
         "previous_best_s": 2.8451203,
         "message": "New world record registered! Rank updated."
       }
       ```
     - **HTTP 200 OK (Duplicate / Valid Non-Improvement)**:
       ```json
       {
         "status": "duplicate",
         "verified": true,
         "is_new_record": false,
         "metric_s": 2.8449112,
         "previous_best_s": 2.8451203,
         "message": "Valid configuration, but not lower than current best"
       }
       ```
     - **HTTP 404 Not Found**: problem does not exist in `problems` table (`{"detail": "Problem not found"}`).
     - **HTTP 422 Unprocessable Entity**: malformed JSON or Pydantic validation failure.

5. **Gating the Atomic Commit (`update_solution_record`)**:
   - `update_solution_record` acquires a SQLite `BEGIN IMMEDIATE` transaction write lock, updates `solutions.is_current_record = 0`, inserts the new record, updates `problems.best_s`, and increments `workers.records_broken`.
   - `update_solution_record` must **NEVER** be called if `res.valid == False` or if coordinate checks fail.
   - It is executed **ONLY** after `res.valid is True`.
   - If `update_solution_record` returns `False` (because the metric does not beat `current_best` by at least `RECORD_MIN_IMPROVEMENT = 1e-5`), the response is mapped to HTTP 200 with `status="duplicate"` and `is_new_record=False`.

---

## 3. Caveats

1. **Non-Numeric and Special Floats**:
   - Coordinates or metric $s$ containing `NaN` or `+/-Infinity` pass JSON parsing in Python's standard `json` module if `allow_nan=True`, but corrupt SQLite and geometric formulas. Pydantic request models and pre-checks must reject `math.isnan(c)` and `math.isinf(c)` with HTTP 400.
2. **`check_record` Parameter**:
   - `verify_solution` contains historical logic to check records against `PACKING_REFERENCE.tsv`. In the distributed coordinator service, `check_record=False` must ALWAYS be passed to `verify_solution`. Record tracking is strictly owned by SQLite `update_solution_record`.
3. **Shape Token Normalization**:
   - When retrieving problem details from SQLite, `prob["inner_token"]` and `prob["container_token"]` are already canonicalized (e.g. `"3"`, `"CIRCLE"`, `"TAN"`, `"L"`). If arbitrary worker input is ever accepted directly, tokens must pass through `database.py:normalize_shape_token`.

---

## 4. Conclusion & Verification Integration Blueprint

### 4.1 Endpoint Handler Implementation for `POST /api/v1/solutions`

Below is the complete, drop-in Python implementation for the verification and solution ingestion pipeline in `src/shape_packing/server/app.py`:

```python
import json
import math
import os
import sqlite3
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .database import get_problem, update_solution_record
from ..solution_tools import (
    compute_friedman_metric,
    inverse_friedman_metric,
    verify_solution,
)


class SolutionSubmitRequest(BaseModel):
    problem: str
    s: float = Field(..., gt=0.0)
    coordinates: List[float]
    worker_id: str
    work_id: Optional[str] = None


@app.post("/api/v1/solutions", status_code=status.HTTP_200_OK)
def submit_solution(
    req: SolutionSubmitRequest,
    conn: sqlite3.Connection = Depends(get_db),
):
    # 1. Verify metric_s is finite and positive
    if math.isnan(req.s) or math.isinf(req.s) or req.s <= 0.0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": "rejected",
                "verified": False,
                "message": "Metric s must be a finite positive number.",
            },
        )

    # 2. Look up problem in database
    prob = get_problem(conn, req.problem)
    if prob is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Problem '{req.problem}' not found.",
        )

    n_shapes = int(prob["n"])
    expected_coords = n_shapes * 3

    # 3. Validate coordinate count
    if len(req.coordinates) != expected_coords:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": "rejected",
                "verified": False,
                "message": f"Expected {expected_coords} coordinates, received {len(req.coordinates)}.",
            },
        )

    # 4. Validate coordinates are finite numbers
    for idx, c in enumerate(req.coordinates):
        if math.isnan(c) or math.isinf(c):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "status": "rejected",
                    "verified": False,
                    "message": f"Coordinate at index {idx} is invalid (NaN or Inf).",
                },
            )

    # 5. Format temporary solution file for verify_solution
    inner_token = prob["inner_token"]
    container_token = prob["container_token"]
    solver_S = inverse_friedman_metric(req.s, inner_token, container_token)

    sol_payload = {
        "N": n_shapes,
        "inner_token": inner_token,
        "container_token": container_token,
        "S": float(solver_S),
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

    # 6. Reject if geometry check failed (SAT overlap, boundary penetration)
    if not res.valid:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": "rejected",
                "verified": False,
                "message": f"Geometric verification failed: {res.message}",
            },
        )

    # 7. Geometry verified: look up worker username for record attribution
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM workers WHERE id = ?", (req.worker_id,))
    w_row = cursor.fetchone()
    if w_row:
        username = w_row["username"] if hasattr(w_row, "keys") else w_row[0]
    else:
        username = "anonymous"

    prev_best_s = prob.get("best_s")

    # 8. Atomically attempt to update solution record
    improved = update_solution_record(
        conn=conn,
        problem_id=req.problem,
        worker_id=req.worker_id,
        username=username,
        metric_s=res.metric,
        coordinates=req.coordinates,
    )

    if improved:
        return {
            "status": "accepted",
            "verified": True,
            "is_new_record": True,
            "metric_s": res.metric,
            "previous_best_s": prev_best_s,
            "message": "New world record registered! Rank updated.",
        }
    else:
        return {
            "status": "duplicate",
            "verified": True,
            "is_new_record": False,
            "metric_s": res.metric,
            "previous_best_s": prev_best_s,
            "message": "Valid configuration, but not lower than current best",
        }
```

---

## 5. Verification Method

To independently verify this blueprint against the codebase:

1. **Verify Geometric Tests via pytest**:
   ```bash
   PYTHONPATH=src pytest tests/test_solution_tools.py -v
   ```
   *Expected output*: All 33 tests in `tests/test_solution_tools.py` PASS with zero failures.

2. **Verify Database Record Logic via pytest**:
   ```bash
   PYTHONPATH=src pytest tests/test_server_database.py -v
   ```
   *Expected output*: All 94 tests in `tests/test_server_database.py` PASS with zero failures.

3. **Verify Interactive Verification Flow**:
   Run the following standalone check:
   ```bash
   PYTHONPATH=src python3 -c "
   import json, tempfile, os
   from shape_packing.solution_tools import verify_solution, inverse_friedman_metric

   # Test valid placement of 3 triangles in circle
   s = 2.5
   S = inverse_friedman_metric(s, '3', 'CIRCLE')
   sol = {'N': 3, 'inner_token': '3', 'container_token': 'CIRCLE', 'S': S, 'final_metric': s, 'values': [-2.0, -1.0, 0.0, 0.0, 1.5, 0.0, 2.0, -1.0, 0.0]}
   with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as tf:
       json.dump(sol, tf); p = tf.name
   res = verify_solution(p, check_record=False)
   assert res.valid is True
   assert abs(res.metric - 2.5) < 1e-6
   os.remove(p)
   print('Verification blueprint confirmed!')
   "
   ```
   *Expected output*: `Verification blueprint confirmed!`
