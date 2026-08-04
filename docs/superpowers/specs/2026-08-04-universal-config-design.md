# Universal Config Module — Design Spec

**Date:** 2026-08-04  
**Status:** Draft — pending user review

---

## 1. Problem Statement

Configuration values are scattered across 9+ files with no central authority:

- **Duplication**: `MAX_CONSECUTIVE_FAILURES = 5` and `BASE_BACKOFF = 5` exist independently in both `run_parallel_loop.py` and `run_autoresearch_loop.py`. Changing one does not update the other.
- **Magic hardcoded numbers**: `CIRCLE_SIDES = 32` is *defined* in `packing_config.py` but then hardcoded as `32` again independently in `geometry.py:81` and `agent_loop.py:495,497` — no import, no reference.
- **Inconsistent tolerance values**: Three distinct tolerance values (`1e-8`, `1e-12`, `1e-15`) appear in three different modules with no documentation of why they differ or which takes precedence.
- **Undocumented magic numbers**: `problem_cap1 = 60`, `problem_cap2 = 100`, `family_cap1 = 400`, `family_cap2 = 800` appear as inline function defaults in `agent_loop.py` with no description of what they control or how to tune them.
- **Hardcoded paths**: `"results.tsv"`, `"priority_queue.json"`, `"packer_rs/target/release/packer_rs"` scattered across 5+ files.

---

## 2. Approach & Design Decision

### Option A: Expand `packing_config.py` (✅ Recommended)

**What:** Evolve the existing `src/shape_packing/packing_config.py` into the single, authoritative config module for the entire project.

**Why:**
- Already exists, already imported by some modules.
- Avoids creating a new file that nobody knows to look at.
- Keeps Python as the config format — no TOML/YAML parser dependency, type-safe, editable with IDE autocomplete.
- Simple pattern: change a value in one file, effect propagates everywhere.

**Against:** None significant. The file already serves this purpose but is underused.

### Option B: TOML/YAML config file

**What:** External `config.toml` or `config.yaml` file read at runtime.

**Why rejected:**
- Adds a parser dependency.
- No type safety without schema validation tooling.
- Python constants are already inspectable, editable, and importable — TOML adds complexity with no clear gain for this project.
- Breaks existing patterns significantly.

### Option C: Environment variables only

**Why rejected:**
- Env vars are stateless across sessions and shell environments.
- Not discoverable — you'd have to read source code to know what vars exist.
- Poor fit for a local research tool.

---

## 3. Design: Expanded `packing_config.py`

### 3a. File Location

```
src/shape_packing/packing_config.py  (existing — expand in place)
```

### 3b. Section Layout

The config will be organized into clearly labeled sections with comments explaining **what each value does, what the trade-offs are, and what downstream files consume it**:

```python
# ===========================================================================
# SECTION 1: Geometry & Shape Representation
# ===========================================================================
CIRCLE_SIDES: int = 32  # Polygon approximation for circles. Higher = more accurate, slower.

# ===========================================================================
# SECTION 2: Solver — Rust Backend (packer_rs)
# ===========================================================================
RUST_BINARY: str = "packer_rs/target/release/packer_rs"
RUST_TOLERANCE: str = "1e-28"         # Convergence tolerance for Rust L-BFGS-B
RUST_DEFAULT_ATTEMPTS: int = 1000     # Default attempts per run (overridden by loop scripts)
RUST_DEFAULT_TIME_LIMIT: int = 290    # Seconds per solver run

# ===========================================================================
# SECTION 3: Solver — Python Backend (scipy/optimization.py)
# ===========================================================================
OPTIMIZER_ATTEMPTS: int = 1000        # Default basinhopping attempts
OPTIMIZER_TOLERANCE: float = 1e-8     # Convergence tolerance for scipy optimizer
OPTIMIZER_FINAL_STEP: float = 0.0001  # Final step size for refinement
OPTIMIZER_N_JOBS: int = -1            # -1 = all cores; 1 = serial

# ===========================================================================
# SECTION 4: Verification Tolerances
# ===========================================================================
VERIFY_SAT_TOLERANCE: float = 1e-5    # SAT overlap penetration tolerance for verify_solution()
VERIFY_METRIC_TOLERANCE: float = 1e-6 # Metric consistency check tolerance
GEOMETRY_SAT_TOLERANCE: float = 1e-12 # SAT projection separation tolerance in geometry.py
MIN_VALID_CIRCLE_SCORE: float = 0.1   # Physical validity floor for circle problem scores

# ===========================================================================
# SECTION 5: Loop & Scheduling
# ===========================================================================
LOOP_SLEEP_BETWEEN_RUNS: int = 2        # Seconds to sleep between autoresearch iterations
LOOP_MAX_CONSECUTIVE_FAILURES: int = 5  # Max failures before exponential backoff
LOOP_BASE_BACKOFF: int = 5              # Base backoff seconds
LOOP_MAX_BACKOFF: int = 120             # Max backoff seconds cap

# --- Parallel loop difficulty heuristics ---
LOOP_DEFAULT_ATTEMPTS: int = 5000
LOOP_HIGH_N_THRESHOLD: int = 8        # N >= this is "hard"
LOOP_HIGH_N_ATTEMPTS: int = 50000
LOOP_STUCK_ATTEMPTS: int = 500000
LOOP_STUCK_SWARM_COUNT: int = 20
LOOP_HARD_SWARM_COUNT: int = 5

# ===========================================================================
# SECTION 6: Priority Queue & Problem Selection
# ===========================================================================
QUEUE_FALLBACK_PROBLEM: str = "8_3_in_5"   # Used if priority_queue.json is missing
QUEUE_RECENT_WINDOW: int = 10               # Recent problems window for diversity
QUEUE_PROBLEM_CAP1: int = 60               # Soft run cap per problem (mild penalty)
QUEUE_PROBLEM_CAP2: int = 100              # Hard run cap per problem (strong penalty)
QUEUE_FAMILY_CAP1: int = 400              # Soft run cap per family
QUEUE_FAMILY_CAP2: int = 800              # Hard run cap per family

# ===========================================================================
# SECTION 7: File Paths
# ===========================================================================
RESULTS_TSV_PATH: str = "results.tsv"
RESULTS_DIR: str = "results"
PRIORITY_QUEUE_PATH: str = "priority_queue.json"
PACKING_VERIFICATION_DIR: str = "packingVerification"
FILTER_JSON_PATH: str = "filter.json"
PACKING_REFERENCE_TSV: str = "PACKING_REFERENCE.tsv"

# ===========================================================================
# SECTION 8: Rendering & Output
# ===========================================================================
RENDER_DPI: int = 300                  # Resolution for solution.png output
RENDER_FIGURE_SIZE: tuple = (6, 6)     # Matplotlib figure size (inches)
ANALYSIS_PLOT_DPI: int = 200           # Resolution for analyze_mill_log.py charts
```

### 3c. What Does NOT Go in the Config

- **Shape geometry math** (polygon vertices, area formulas) — these are computed constants, not user settings.
- **Shape token alias maps** — these are lookup tables, not tunable parameters.
- **Problem family catalog** (ALL_FAMILIES, CIRCLE_FAMILIES, etc.) — reference data, not config.
- **CLI argument defaults** — these already have well-defined argparse defaults exposed to the user.

---

## 4. Consumer Update Plan

All files currently using hardcoded values will be updated to `from .packing_config import <CONSTANT>` (or `from src.shape_packing.packing_config import <CONSTANT>` for root-level scripts):

| File | Current Hardcoded Values | → Config Constant(s) |
|---|---|---|
| `geometry.py:81` | `sides = 32` | `CIRCLE_SIDES` |
| `agent_loop.py:240` | `score < 0.1` | `MIN_VALID_CIRCLE_SCORE` |
| `agent_loop.py:354` | `"8_3_in_5"` | `QUEUE_FALLBACK_PROBLEM` |
| `agent_loop.py:347-350` | `problem_cap1=60`, `problem_cap2=100`, etc. | `QUEUE_PROBLEM_CAP1`, etc. |
| `agent_loop.py:356` | `last=10` | `QUEUE_RECENT_WINDOW` |
| `agent_loop.py:495,497` | `inner_sides = 32` | `CIRCLE_SIDES` |
| `solution_tools.py:30` | `TOLERANCE = 1e-15` | `VERIFY_SAT_TOLERANCE` |
| `solution_tools.py:363` | `dpi: int = 300` | `RENDER_DPI` |
| `solution_tools.py:382` | `figsize=(6, 6)` | `RENDER_FIGURE_SIZE` |
| `optimization.py:48-52` | `attempts=1000`, `tolerance=1e-8`, `final_step=0.0001`, `n_jobs=-1` | `OPTIMIZER_*` |
| `geometry.py:314` | `tolerance: float = 1e-12` | `GEOMETRY_SAT_TOLERANCE` |
| `run_parallel_loop.py:11-13` | `MAX_CONSECUTIVE_FAILURES=5`, `BASE_BACKOFF=5`, `MAX_BACKOFF=120` | `LOOP_*` |
| `run_parallel_loop.py:91,93,100-104` | `attempts=5000,50000,500000`, `swarm_count=20,5` | `LOOP_*` |
| `run_autoresearch_loop.py:24-27` | all 4 constants | `LOOP_*` |
| `train.py:40,46,54-56` | `TIME_BUDGET`, `PACKER_RS_BIN`, `RUST_*` | `RUST_*` |
| `scripts/analyze_mill_log.py` | `dpi=200` | `ANALYSIS_PLOT_DPI` |

---

## 5. What Does NOT Change

- The external `filter.json` file stays as-is — it's intentionally a runtime-editable per-run override that the loops read at startup. This is correct architecture.
- No module interfaces change (function signatures, return types, CLI flags).
- No behavioral changes — all values stay at their current defaults.

---

## 6. Testing Strategy

- All 203 existing pytest tests must still pass after the refactor.
- Add 1 new test in `tests/test_packing_config.py`:
  - Assert all exported constants exist and are the correct type.
  - Assert `CIRCLE_SIDES >= 3`.
  - Assert all tolerance constants are `> 0` and `< 1`.
  - Assert all path strings are non-empty.
  - Assert all integer caps are positive.
- Verify `geometry.py` still produces correct 32-gon for circles.

---

## 7. Open Questions

None — scope is clear and bounded. This is a pure refactor with no behavioral changes.
