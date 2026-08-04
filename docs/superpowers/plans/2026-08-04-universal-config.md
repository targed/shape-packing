# Universal Config Module — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate all scattered configuration constants, tolerances, paths, and tuning parameters from 9+ files into a single authoritative `packing_config.py` module, with zero behavioral change.

**Architecture:** Expand the existing `src/shape_packing/packing_config.py` with all constants, organized into labeled sections. Update all consumers to import from it instead of hardcoding values. No new files, no interface changes.

**Tech Stack:** Python stdlib only. No new dependencies.

## Global Constraints

- All 203 existing pytest tests must pass after every task.
- Zero behavioral change — all constants keep their current default values.
- No changes to any function signature, CLI interface, or output format.
- No changes to `filter.json` (intentionally a runtime-editable override).
- Import style: `from .packing_config import CONSTANT` inside `src/`; `from src.shape_packing.packing_config import CONSTANT` in root-level scripts.
- Every task ends with a `git commit`.

---

### Task 1: Expand `packing_config.py` with All Constants

**Files:**
- Modify: `src/shape_packing/packing_config.py`
- Create: `tests/test_packing_config.py`

**Interfaces:**
- Produces: All constants listed below, importable from `src.shape_packing.packing_config`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_packing_config.py`:
```python
"""Tests for the universal packing config module."""
import pytest
from src.shape_packing.packing_config import (
    # Geometry
    CIRCLE_SIDES,
    # Rust solver
    RUST_BINARY,
    RUST_TOLERANCE,
    RUST_DEFAULT_ATTEMPTS,
    RUST_DEFAULT_TIME_LIMIT,
    # Python optimizer
    OPTIMIZER_ATTEMPTS,
    OPTIMIZER_TOLERANCE,
    OPTIMIZER_FINAL_STEP,
    OPTIMIZER_N_JOBS,
    # Verification
    VERIFY_SAT_TOLERANCE,
    VERIFY_METRIC_TOLERANCE,
    GEOMETRY_SAT_TOLERANCE,
    MIN_VALID_CIRCLE_SCORE,
    # Loop & scheduling
    LOOP_SLEEP_BETWEEN_RUNS,
    LOOP_MAX_CONSECUTIVE_FAILURES,
    LOOP_BASE_BACKOFF,
    LOOP_MAX_BACKOFF,
    LOOP_DEFAULT_ATTEMPTS,
    LOOP_HIGH_N_THRESHOLD,
    LOOP_HIGH_N_ATTEMPTS,
    LOOP_STUCK_ATTEMPTS,
    LOOP_STUCK_SWARM_COUNT,
    LOOP_HARD_SWARM_COUNT,
    # Priority queue
    QUEUE_FALLBACK_PROBLEM,
    QUEUE_RECENT_WINDOW,
    QUEUE_PROBLEM_CAP1,
    QUEUE_PROBLEM_CAP2,
    QUEUE_FAMILY_CAP1,
    QUEUE_FAMILY_CAP2,
    # Paths
    RESULTS_TSV_PATH,
    RESULTS_DIR,
    PRIORITY_QUEUE_PATH,
    PACKING_VERIFICATION_DIR,
    FILTER_JSON_PATH,
    PACKING_REFERENCE_TSV,
    # Rendering
    RENDER_DPI,
    RENDER_FIGURE_SIZE,
    ANALYSIS_PLOT_DPI,
)


def test_geometry_constants():
    assert isinstance(CIRCLE_SIDES, int)
    assert CIRCLE_SIDES >= 3


def test_rust_constants():
    assert isinstance(RUST_BINARY, str) and len(RUST_BINARY) > 0
    assert isinstance(RUST_TOLERANCE, str)
    assert isinstance(RUST_DEFAULT_ATTEMPTS, int) and RUST_DEFAULT_ATTEMPTS > 0
    assert isinstance(RUST_DEFAULT_TIME_LIMIT, int) and RUST_DEFAULT_TIME_LIMIT > 0


def test_optimizer_constants():
    assert isinstance(OPTIMIZER_ATTEMPTS, int) and OPTIMIZER_ATTEMPTS > 0
    assert 0 < OPTIMIZER_TOLERANCE < 1
    assert 0 < OPTIMIZER_FINAL_STEP < 1
    assert isinstance(OPTIMIZER_N_JOBS, int)


def test_verification_tolerances():
    assert 0 < VERIFY_SAT_TOLERANCE < 1
    assert 0 < VERIFY_METRIC_TOLERANCE < 1
    assert 0 < GEOMETRY_SAT_TOLERANCE < 1
    assert 0 < MIN_VALID_CIRCLE_SCORE < 1


def test_loop_constants():
    assert LOOP_SLEEP_BETWEEN_RUNS >= 0
    assert LOOP_MAX_CONSECUTIVE_FAILURES > 0
    assert LOOP_BASE_BACKOFF > 0
    assert LOOP_MAX_BACKOFF >= LOOP_BASE_BACKOFF
    assert LOOP_DEFAULT_ATTEMPTS > 0
    assert LOOP_HIGH_N_THRESHOLD > 0
    assert LOOP_HIGH_N_ATTEMPTS > LOOP_DEFAULT_ATTEMPTS
    assert LOOP_STUCK_ATTEMPTS > LOOP_HIGH_N_ATTEMPTS
    assert LOOP_STUCK_SWARM_COUNT > 0
    assert LOOP_HARD_SWARM_COUNT > 0


def test_queue_constants():
    assert isinstance(QUEUE_FALLBACK_PROBLEM, str) and "_in_" in QUEUE_FALLBACK_PROBLEM
    assert QUEUE_RECENT_WINDOW > 0
    assert QUEUE_PROBLEM_CAP1 < QUEUE_PROBLEM_CAP2
    assert QUEUE_FAMILY_CAP1 < QUEUE_FAMILY_CAP2


def test_path_constants():
    for p in [RESULTS_TSV_PATH, RESULTS_DIR, PRIORITY_QUEUE_PATH,
              PACKING_VERIFICATION_DIR, FILTER_JSON_PATH, PACKING_REFERENCE_TSV]:
        assert isinstance(p, str) and len(p) > 0


def test_render_constants():
    assert isinstance(RENDER_DPI, int) and RENDER_DPI > 0
    assert len(RENDER_FIGURE_SIZE) == 2
    assert isinstance(ANALYSIS_PLOT_DPI, int) and ANALYSIS_PLOT_DPI > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_packing_config.py -v
```
Expected: FAIL — `ImportError: cannot import name 'RUST_BINARY' from 'src.shape_packing.packing_config'`

- [ ] **Step 3: Expand `packing_config.py`**

Replace the bottom section of `src/shape_packing/packing_config.py` (everything from line 183 down) with the full new config. Leave the existing content at the top (shape catalogs, SHAPE_TO_SIDES, SPECIAL_SHAPES) completely intact.

Add the following to the **bottom** of `src/shape_packing/packing_config.py` (after `DEFAULT_EXPERIMENT_KWARGS`):

```python
# ===========================================================================
# SECTION 2: Solver — Rust Backend (packer_rs)
# ===========================================================================

#: Path to compiled Rust solver binary.
RUST_BINARY: str = "packer_rs/target/release/packer_rs"

#: Convergence tolerance passed to Rust L-BFGS-B solver via --tolerance flag.
RUST_TOLERANCE: str = "1e-28"

#: Default number of solver restart attempts per run (overridden by loop scripts and CLI).
RUST_DEFAULT_ATTEMPTS: int = 1000

#: Default time limit in seconds for a single Rust solver run.
RUST_DEFAULT_TIME_LIMIT: int = 290

# ===========================================================================
# SECTION 3: Solver — Python Backend (scipy/optimization.py)
# ===========================================================================

#: Default number of basinhopping attempts in the Python optimizer.
OPTIMIZER_ATTEMPTS: int = 1000

#: Convergence tolerance for scipy L-BFGS-B. Lower = more precise, slower.
OPTIMIZER_TOLERANCE: float = 1e-8

#: Final step size for the optimizer's local refinement stage.
OPTIMIZER_FINAL_STEP: float = 0.0001

#: Number of parallel jobs for joblib. -1 = all cores, 1 = serial.
OPTIMIZER_N_JOBS: int = -1

# ===========================================================================
# SECTION 4: Verification Tolerances
# ===========================================================================

#: Maximum allowed SAT penetration depth when verifying boundary containment
#: in solution_tools.verify_solution(). Small positive value to allow float rounding.
VERIFY_SAT_TOLERANCE: float = 1e-5

#: Tolerance when comparing computed Friedman metric against stored final_metric in JSON.
VERIFY_METRIC_TOLERANCE: float = 1e-6

#: Tolerance used inside geometry.sat_check_overlap() for separating axis projection.
#: Tighter than VERIFY_SAT_TOLERANCE since this is an internal math primitive.
GEOMETRY_SAT_TOLERANCE: float = 1e-12

#: Physical validity floor for circle problem scores. Scores below this value
#: are treated as corrupt legacy metrics (old broken formula) and ignored.
MIN_VALID_CIRCLE_SCORE: float = 0.1

# ===========================================================================
# SECTION 5: Loop & Scheduling (autoresearch and parallel loops)
# ===========================================================================

#: Seconds to sleep between successful solver runs in run_autoresearch_loop.py.
LOOP_SLEEP_BETWEEN_RUNS: int = 2

#: Maximum number of consecutive failures before applying exponential backoff.
LOOP_MAX_CONSECUTIVE_FAILURES: int = 5

#: Starting backoff duration in seconds after a failure.
LOOP_BASE_BACKOFF: int = 5

#: Maximum backoff duration cap in seconds.
LOOP_MAX_BACKOFF: int = 120

#: Default solver attempts for "normal" difficulty problems in the parallel loop.
LOOP_DEFAULT_ATTEMPTS: int = 5000

#: N threshold above which a problem is considered "hard" (more attempts allocated).
LOOP_HIGH_N_THRESHOLD: int = 8

#: Solver attempts for hard problems (N >= LOOP_HIGH_N_THRESHOLD).
LOOP_HIGH_N_ATTEMPTS: int = 50000

#: Solver attempts for "stuck" problems (status='stuck' returned by suggest).
LOOP_STUCK_ATTEMPTS: int = 500000

#: Number of parallel swarm workers dispatched for stuck problems.
LOOP_STUCK_SWARM_COUNT: int = 20

#: Number of parallel swarm workers dispatched for hard problems.
LOOP_HARD_SWARM_COUNT: int = 5

# ===========================================================================
# SECTION 6: Priority Queue & Problem Selection
# ===========================================================================

#: Fallback problem key used if priority_queue.json is missing or empty.
QUEUE_FALLBACK_PROBLEM: str = "8_3_in_5"

#: Window size for recent_problems() diversity check.
QUEUE_RECENT_WINDOW: int = 10

#: Soft run cap per problem — beyond this, mild score penalty applied.
QUEUE_PROBLEM_CAP1: int = 60

#: Hard run cap per problem — beyond this, strong score penalty applied.
QUEUE_PROBLEM_CAP2: int = 100

#: Soft run cap per problem family — beyond this, mild score penalty applied.
QUEUE_FAMILY_CAP1: int = 400

#: Hard run cap per problem family — beyond this, strong score penalty applied.
QUEUE_FAMILY_CAP2: int = 800

# ===========================================================================
# SECTION 7: File Paths (relative to project root)
# ===========================================================================

#: Path to the experiment history TSV file.
RESULTS_TSV_PATH: str = "results.tsv"

#: Directory where per-run result subdirectories are saved.
RESULTS_DIR: str = "results"

#: Path to the JSON priority queue file.
PRIORITY_QUEUE_PATH: str = "priority_queue.json"

#: Directory containing benchmark verification JSON files.
PACKING_VERIFICATION_DIR: str = "packingVerification"

#: Path to the optional runtime filter JSON file.
FILTER_JSON_PATH: str = "filter.json"

#: Path to the legacy PACKING_REFERENCE.tsv file.
PACKING_REFERENCE_TSV: str = "PACKING_REFERENCE.tsv"

# ===========================================================================
# SECTION 8: Rendering & Output
# ===========================================================================

#: DPI for solution.png renders (solution_tools.render_solution).
RENDER_DPI: int = 300

#: Matplotlib figure size in inches for solution renders.
RENDER_FIGURE_SIZE: tuple = (6, 6)

#: DPI for analysis charts produced by scripts/analyze_mill_log.py.
ANALYSIS_PLOT_DPI: int = 200
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_packing_config.py -v
```
Expected: All test_packing_config tests PASS.

- [ ] **Step 5: Run full suite to catch regressions**

```bash
python -m pytest tests/
```
Expected: 204 passed (203 existing + 1 new).

- [ ] **Step 6: Commit**

```bash
git add src/shape_packing/packing_config.py tests/test_packing_config.py
git commit -m "feat: expand packing_config.py with universal constants"
```

---

### Task 2: Update `geometry.py` and `solution_tools.py`

**Files:**
- Modify: `src/shape_packing/geometry.py`
- Modify: `src/shape_packing/solution_tools.py`

**Interfaces:**
- Consumes: `CIRCLE_SIDES`, `GEOMETRY_SAT_TOLERANCE`, `VERIFY_SAT_TOLERANCE`, `VERIFY_METRIC_TOLERANCE`, `RENDER_DPI`, `RENDER_FIGURE_SIZE` from `packing_config`.

- [ ] **Step 1: Update `geometry.py`**

In `src/shape_packing/geometry.py`, add import at the top after the existing imports:
```python
from .packing_config import CIRCLE_SIDES, GEOMETRY_SAT_TOLERANCE
```

Find line 81 (`sides = 32`) inside `get_shape_geometry()`:
```python
# Before:
        sides = 32
# After:
        sides = CIRCLE_SIDES
```

Find the `sat_check_overlap` function signature at line ~314:
```python
# Before:
def sat_check_overlap(poly1, poly2, normals1, normals2,
                      tolerance: float = 1e-12):
# After:
def sat_check_overlap(poly1, poly2, normals1, normals2,
                      tolerance: float = GEOMETRY_SAT_TOLERANCE):
```

- [ ] **Step 2: Update `solution_tools.py`**

In `src/shape_packing/solution_tools.py`, update the existing import block at the top to include:
```python
from .packing_config import (
    VERIFY_SAT_TOLERANCE,
    VERIFY_METRIC_TOLERANCE,
    RENDER_DPI,
    RENDER_FIGURE_SIZE,
)
```

Replace the module-level constant definition:
```python
# Before (line 30):
TOLERANCE: float = 1e-15

# After:
TOLERANCE: float = VERIFY_SAT_TOLERANCE  # Re-exported for backward compatibility
```

Update `render_solution()` signature:
```python
# Before:
def render_solution(
    sol_path: str,
    out_png: str = "solution.png",
    dpi: int = 300,
    show_axes: bool = False,
    show_grid: bool = False,
) -> None:

# After:
def render_solution(
    sol_path: str,
    out_png: str = "solution.png",
    dpi: int = RENDER_DPI,
    show_axes: bool = False,
    show_grid: bool = False,
) -> None:
```

Update the `fig, ax = plt.subplots(...)` call in `render_solution`:
```python
# Before:
    fig, ax = plt.subplots(figsize=(6, 6))

# After:
    fig, ax = plt.subplots(figsize=RENDER_FIGURE_SIZE)
```

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest tests/
```
Expected: 204 passed, 0 failed.

- [ ] **Step 4: Commit**

```bash
git add src/shape_packing/geometry.py src/shape_packing/solution_tools.py
git commit -m "refactor: use packing_config constants in geometry and solution_tools"
```

---

### Task 3: Update `optimization.py` and `agent_loop.py`

**Files:**
- Modify: `src/shape_packing/optimization.py`
- Modify: `src/shape_packing/agent_loop.py`

**Interfaces:**
- Consumes: `OPTIMIZER_*`, `CIRCLE_SIDES`, `MIN_VALID_CIRCLE_SCORE`, `QUEUE_*` from `packing_config`.

- [ ] **Step 1: Update `optimization.py`**

Add import to `src/shape_packing/optimization.py`:
```python
from .packing_config import (
    OPTIMIZER_ATTEMPTS,
    OPTIMIZER_TOLERANCE,
    OPTIMIZER_FINAL_STEP,
    OPTIMIZER_N_JOBS,
)
```

Update `OptConfig` dataclass defaults:
```python
# Before:
@dataclass
class OptConfig:
    attempts: int = 1000
    tolerance: float = 1e-8
    final_step: float = 0.0001
    time_limit: Optional[float] = None
    n_jobs: int = -1

# After:
@dataclass
class OptConfig:
    attempts: int = OPTIMIZER_ATTEMPTS
    tolerance: float = OPTIMIZER_TOLERANCE
    final_step: float = OPTIMIZER_FINAL_STEP
    time_limit: Optional[float] = None
    n_jobs: int = OPTIMIZER_N_JOBS
```

- [ ] **Step 2: Update `agent_loop.py`**

Add import near the top of `src/shape_packing/agent_loop.py`:
```python
from .packing_config import (
    CIRCLE_SIDES,
    MIN_VALID_CIRCLE_SCORE,
    QUEUE_FALLBACK_PROBLEM,
    QUEUE_RECENT_WINDOW,
    QUEUE_PROBLEM_CAP1,
    QUEUE_PROBLEM_CAP2,
    QUEUE_FAMILY_CAP1,
    QUEUE_FAMILY_CAP2,
)
```

At line 240 in `is_physically_valid_score`:
```python
# Before:
    if container in ("CIRCLE", "CIR", "0") and score < 0.1:
# After:
    if container in ("CIRCLE", "CIR", "0") and score < MIN_VALID_CIRCLE_SCORE:
```

At line 354 in `choose_problem`:
```python
# Before:
        return "8_3_in_5"
# After:
        return QUEUE_FALLBACK_PROBLEM
```

At line 356 in `choose_problem`:
```python
# Before:
    recent = recent_problems(history, last=10)
# After:
    recent = recent_problems(history, last=QUEUE_RECENT_WINDOW)
```

Update `choose_problem` function signature (lines 347-350):
```python
# Before:
def choose_problem(
    history: List[ExperimentResult],
    queue_path: str = "priority_queue.json",
    prefer_different: bool = False,
    filters: dict = None,
    exclude_problems: set = None,
    problem_cap1: int = 60,
    problem_cap2: int = 100,
    family_cap1: int = 400,
    family_cap2: int = 800,
) -> str:

# After:
def choose_problem(
    history: List[ExperimentResult],
    queue_path: str = PRIORITY_QUEUE_PATH,
    prefer_different: bool = False,
    filters: dict = None,
    exclude_problems: set = None,
    problem_cap1: int = QUEUE_PROBLEM_CAP1,
    problem_cap2: int = QUEUE_PROBLEM_CAP2,
    family_cap1: int = QUEUE_FAMILY_CAP1,
    family_cap2: int = QUEUE_FAMILY_CAP2,
) -> str:
```

(Note: also add `PRIORITY_QUEUE_PATH` to the packing_config import list for agent_loop.py)

Update `agent_loop.py` lines 495 and 497 where `inner_sides = 32` and `container_sides = 32`:
```python
# Before:
                    inner_sides = 32
# After:
                    inner_sides = CIRCLE_SIDES
```
```python
# Before:
                    container_sides = 32
# After:
                    container_sides = CIRCLE_SIDES
```

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest tests/
```
Expected: 204 passed, 0 failed.

- [ ] **Step 4: Commit**

```bash
git add src/shape_packing/optimization.py src/shape_packing/agent_loop.py
git commit -m "refactor: use packing_config constants in optimization and agent_loop"
```

---

### Task 4: Update Root-Level Scripts

**Files:**
- Modify: `run_parallel_loop.py`
- Modify: `run_autoresearch_loop.py`
- Modify: `scripts/analyze_mill_log.py`
- Modify: `train.py`

**Interfaces:**
- Consumes: `LOOP_*`, `RUST_*`, `ANALYSIS_PLOT_DPI` from `src.shape_packing.packing_config`.

- [ ] **Step 1: Update `run_parallel_loop.py`**

Replace the top constants block:
```python
# Before:
# Configuration
MAX_CONSECUTIVE_FAILURES = 5
BASE_BACKOFF = 5
MAX_BACKOFF = 120

# After:
from src.shape_packing.packing_config import (
    LOOP_MAX_CONSECUTIVE_FAILURES as MAX_CONSECUTIVE_FAILURES,
    LOOP_BASE_BACKOFF as BASE_BACKOFF,
    LOOP_MAX_BACKOFF as MAX_BACKOFF,
    LOOP_DEFAULT_ATTEMPTS,
    LOOP_HIGH_N_THRESHOLD,
    LOOP_HIGH_N_ATTEMPTS,
    LOOP_STUCK_ATTEMPTS,
    LOOP_STUCK_SWARM_COUNT,
    LOOP_HARD_SWARM_COUNT,
)
```

Update `analyze_difficulty`:
```python
# Before:
    attempts = 5000
    if n >= 8:
        attempts = 50000
    ...
    if status == "stuck":
        attempts = 500000
        swarm_count = 20
    elif status == "hard":
        attempts = 50000
        swarm_count = 5

# After:
    attempts = LOOP_DEFAULT_ATTEMPTS
    if n >= LOOP_HIGH_N_THRESHOLD:
        attempts = LOOP_HIGH_N_ATTEMPTS
    ...
    if status == "stuck":
        attempts = LOOP_STUCK_ATTEMPTS
        swarm_count = LOOP_STUCK_SWARM_COUNT
    elif status == "hard":
        attempts = LOOP_HIGH_N_ATTEMPTS
        swarm_count = LOOP_HARD_SWARM_COUNT
```

- [ ] **Step 2: Update `run_autoresearch_loop.py`**

Replace the top constants block:
```python
# Before:
SLEEP_BETWEEN_RUNS = 2
MAX_CONSECUTIVE_FAILURES = 5
BASE_BACKOFF = 5
MAX_BACKOFF = 120

# After:
from src.shape_packing.packing_config import (
    LOOP_SLEEP_BETWEEN_RUNS as SLEEP_BETWEEN_RUNS,
    LOOP_MAX_CONSECUTIVE_FAILURES as MAX_CONSECUTIVE_FAILURES,
    LOOP_BASE_BACKOFF as BASE_BACKOFF,
    LOOP_MAX_BACKOFF as MAX_BACKOFF,
)
```

- [ ] **Step 3: Update `scripts/analyze_mill_log.py`**

Add near the top of `scripts/analyze_mill_log.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
try:
    from shape_packing.packing_config import ANALYSIS_PLOT_DPI
except ImportError:
    from src.shape_packing.packing_config import ANALYSIS_PLOT_DPI
```

Replace all 5 occurrences of `dpi=200` with `dpi=ANALYSIS_PLOT_DPI`.

- [ ] **Step 4: Update `train.py`**

In `train.py`, replace:
```python
# Before:
PACKER_RS_BIN = "packer_rs/target/release/packer_rs"
RUST_ATTEMPTS = 500000
RUST_TIME_LIMIT = 290
RUST_TOLERANCE = "1e-28"

# After:
from shape_packing.packing_config import (
    RUST_BINARY as PACKER_RS_BIN,
    RUST_TOLERANCE,
    RUST_DEFAULT_TIME_LIMIT as RUST_TIME_LIMIT,
)
RUST_ATTEMPTS = 500000  # train.py uses a higher value; keep local override
```

(Note: `train.py` uses `RUST_ATTEMPTS = 500000` which is different from `RUST_DEFAULT_ATTEMPTS = 1000` in config — this is intentional, `train.py` is a heavy standalone runner with its own override. Keep it as a local override with a comment.)

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/
```
Expected: 204 passed, 0 failed.

- [ ] **Step 6: Verify CLI still works**

```bash
python -m src.shape_packing.cli suggest
python -m src.shape_packing.cli run -h
```
Expected: Normal output, no import errors.

- [ ] **Step 7: Commit**

```bash
git add run_parallel_loop.py run_autoresearch_loop.py scripts/analyze_mill_log.py train.py
git commit -m "refactor: root-level scripts use packing_config constants"
```

---

### Task 5: Update Documentation

**Files:**
- Modify: `docs/01_system_architecture.md`
- Modify: `docs/05_debugging_and_testing.md`

- [ ] **Step 1: Update `docs/01_system_architecture.md`**

Add a new section after the existing "Module Responsibilities" section:

```markdown
## 6. Universal Configuration (`packing_config.py`)

All global constants, tuning parameters, tolerances, and file paths are defined in:

```python
src/shape_packing/packing_config.py
```

**To tune the system, edit ONLY this file.** The 8 configuration sections are:

| Section | Constants | Controls |
|---|---|---|
| 1. Geometry | `CIRCLE_SIDES` | Circle polygon approximation resolution |
| 2. Rust Solver | `RUST_BINARY`, `RUST_TOLERANCE`, etc. | Rust packer_rs execution |
| 3. Python Optimizer | `OPTIMIZER_ATTEMPTS`, `OPTIMIZER_TOLERANCE`, etc. | Scipy basinhopping |
| 4. Verification | `VERIFY_SAT_TOLERANCE`, `GEOMETRY_SAT_TOLERANCE`, etc. | Solution validity checks |
| 5. Loop & Scheduling | `LOOP_*` constants | Backoff, attempts, swarm sizes |
| 6. Priority Queue | `QUEUE_*` constants | Problem selection and diversity |
| 7. File Paths | `RESULTS_TSV_PATH`, `RESULTS_DIR`, etc. | All data file locations |
| 8. Rendering | `RENDER_DPI`, `RENDER_FIGURE_SIZE`, etc. | PNG output quality |
```

- [ ] **Step 2: Update `docs/05_debugging_and_testing.md`**

Add a note to the Common Root Causes section:

```markdown
4. **Unexpected behavior from stale constants**:
   - *Cause*: Constants edited in one place but not reflected elsewhere due to duplicate definitions.
   - *Fix*: All constants now live in `packing_config.py`. If a behavioral parameter seems wrong, check there first.
```

- [ ] **Step 3: Commit**

```bash
git add docs/01_system_architecture.md docs/05_debugging_and_testing.md
git commit -m "docs: document universal packing_config.py config module"
```

---

## Verification Checklist (run after all tasks)

```bash
# 1. Full test suite
python -m pytest tests/ -v

# 2. CLI sanity check
python -m src.shape_packing.cli suggest
python -m src.shape_packing.cli run --help

# 3. Build site
cd site && npm run build

# 4. Import sanity
python -c "from src.shape_packing.packing_config import CIRCLE_SIDES, RUST_BINARY, LOOP_MAX_BACKOFF; print('OK')"
```

Expected results:
- `python -m pytest tests/`: 204 passed, 0 failed
- `python -m src.shape_packing.cli suggest`: returns `{"problem": "...", "best_score": "..."}`
- `npm run build`: 91 pages built
- `python -c "..."`: prints `OK`
