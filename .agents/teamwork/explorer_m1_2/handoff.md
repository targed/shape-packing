# Milestone 1 Investigation Report: Problem Catalog Ingestion & Schema Mapping

## 1. Observation

### 1.1 Dataset Inventory and Verification JSON Structure
Analysis of `/home/targed/Documents/Git/shape-packing/data/packingVerification/`:
- **File Count**: 82 JSON files.
- **Root Format**: 100% of files (82/82) contain a JSON array (list) of objects. Zero malformed JSON files.
- **Total Problem Records**: 2,269 objects across all 82 files.
- **Unique Problem IDs (`our_problem`)**: 2,249 distinct identifiers (20 duplicate keys detected).

#### Field Catalog (All 2,269 Items)
Across the entire dataset, exactly 10 distinct keys appear:

| Field Name | Type | Presence | Observed Values / Range | Description |
|---|---|---|---|---|
| `our_problem` | `str` | 2,269 / 2,269 (100%) | e.g. `"1_cirincir"`, `"14_TAN_in_circle"`, `"1_6_in_4"` | Canonical problem identifier used across repo |
| `id` | `str` | 2,269 / 2,269 (100%) | e.g. `"cirincir_1"`, `"tan_in_cir_14"`, `"6_in_4_1"` | Verification dataset internal row ID (`id != our_problem` in 100% of rows) |
| `problem_family` | `str` | 2,269 / 2,269 (100%) | e.g. `"cirincir"`, `"domincir"`, `"6_in_4"`, `"L_in_L"` | Short family code |
| `N` | `int` | 2,269 / 2,269 (100%) | Range: `[1, 54]` | Quantity of inner shapes |
| `inner_shape` | `str` | 2,269 / 2,269 (100%) | `'3'`, `'4'`, `'6'`, `'L'`, `'circle'`, `'domino'`, `'hexagon'`, `'l'`, `'octagon'`, `'pentagon'`, `'square'`, `'tan'`, `'triangle'` | Inner shape token |
| `container_shape` | `str` | 2,269 / 2,269 (100%) | `'3'`, `'4'`, `'5'`, `'L'`, `'cir'`, `'circle'`, `'domino'`, `'ellipse'`, `'hexagon'`, `'octagon'`, `'pentagon'`, `'square'`, `'tan'`, `'triangle'`, `'triangle (arbitrary)'` | Container shape token |
| `best_value` | `int` or `float` | 2,269 / 2,269 (100%) | Range: `[0.122028320701, 194.49896]` (103 ints, 2,166 floats) | Baseline reference metric from Friedman |
| `status` | `str` | 2,269 / 2,269 (100%) | `'best_known'` (1,755), `'trivial'` (465), `'proved_optimal'` (49) | Verification proof status |
| `source_note` | `str` | 2,269 / 2,269 (100%) | Text attribution, e.g. `"r = √5/2 = 1.11803+ Trivial."` | Historical attribution note |
| `source_url` | `str` | 2,215 / 2,269 (97.6%) | URL pointing to Friedman's packing site | Missing only in `triinhex.json` (54 items) |

### 1.2 Duplicate Keys in Verification Files
There are exactly 20 duplicate `our_problem` keys:
- `1_domincir` through `20_domincir` appear in **both** `data/packingVerification/cirindom.json` and `data/packingVerification/domincir.json`.
- In `cirindom.json`:
  ```json
  {
    "problem_family": "domincir",
    "N": 1,
    "inner_shape": "domino",
    "container_shape": "circle",
    "best_value": 1.11803,
    "status": "trivial",
    "source_note": "r = √5/2 = 1.11803+ Trivial.",
    "our_problem": "1_domincir",
    "id": "domincir_1",
    "source_url": "https://erich-friedman.github.io/packing/domincir/index.html"
  }
  ```
- In `domincir.json`:
  ```json
  {
    "problem_family": "domincir",
    "N": 1,
    "inner_shape": "domino",
    "container_shape": "circle",
    "best_value": 1.118,
    "status": "trivial",
    "source_note": "r = √5/2 = 1.11803+ Trivial.",
    "our_problem": "1_domincir",
    "id": "domincir_1",
    "source_url": "https://erich-friedman.github.io/packing/domincir/index.html"
  }
  ```
The difference is minor decimal rounding (e.g. `1.11803` vs `1.118`).
Executing an unconditional `INSERT INTO problems (id, ...)` causes `sqlite3.IntegrityError: UNIQUE constraint failed: problems.id`.

### 1.3 Filename vs Problem Family Discrepancies
In 12 files, the base filename does not match `problem_family`:
- `LinL.json` -> `L_in_L`
- `cirindom.json` -> `domincir` (duplicate of `domincir.json`)
- `hexinsqu.json` -> `6_in_4`
- `squintan.json` -> `4_in_tan`
- `squintri.json` -> `4_in_3`
- `tanincir.json` -> `tan_in_cir`
- `tanintan.json` -> `tan_in_tan`
- `triincir.json` -> `3_in_circle`
- `triinpen.json` -> `3_in_5`
- `triinsqu.json` -> `3_in_4`
- `triintan.json` -> `3_in_tan`
- `triintri.json` -> `3_in_3`

### 1.4 Downstream Geometry and Token Parsing Mismatch
In `src/shape_packing/geometry.py:67-124`:
```python
def get_shape_geometry(token: str):
    token = str(token).upper()
    if token == "DOMINO": ...
    if token == "TAN": ...
    if token == "L": ...
    if token in ("CIRCLE", "CIR"): ...
    # Fallback for numeric tokens
    try:
        sides = int(token)
    except ValueError:
        sides = 3 # default fallback
```
In `src/shape_packing/solution_tools.py:80-105`:
```python
def compute_friedman_metric(S: float, inner_token: str, container_token: str) -> float:
    container_upper = container_token.strip().upper()
    inner_upper = inner_token.strip().upper()
    if container_upper in ("CIRCLE", "CIR", "TAN", "DOMINO", "L"):
        c_metric = S
    else:
        try:
            nsc = int(container_upper)
            c_metric = 2 * S * math.sin(math.pi / nsc)
        except ValueError:
            c_metric = 2 * S * math.sin(math.pi / 3)
```
In `packer_rs/src/solver.rs:259`:
```rust
let sides: usize = token.parse().unwrap_or(3);
```
**Observation Test**:
```python
get_shape_geometry("6")[0]        # Returns 6
get_shape_geometry("HEXAGON")[0]  # Returns 3 (FALLBACK TO TRIANGLE!)
compute_friedman_metric(1.0, "3", "6")        # Returns 0.5773502691896257
compute_friedman_metric(1.0, "3", "HEXAGON")  # Returns 1.0 (WRONG METRIC!)
```
When `seed_problems_from_verification` naively inserts `inner_shape.upper()` (`"HEXAGON"`, `"SQUARE"`, `"PENTAGON"`, `"OCTAGON"`, `"TRIANGLE"`), both `packer_rs` and `solution_tools.py:verify_solution` fail to parse the polygon sides and fall back to 3 sides (triangle).

### 1.5 Benchmark Seeding Timings
Measured on local host:
- `cursor.execute` within a single `BEGIN TRANSACTION` / `conn.commit()`: **0.0100s** (10 ms) for all 82 files (2,269 items).
- `cursor.executemany` within a single transaction: **0.0074s** (7.4 ms) for all 82 files.

---

## 2. Logic Chain

1. **Schema Requirement**:
   `ORIGINAL_REQUEST.md §R1` and `2026-11-20-distributed-shape-packing.md Task 1` require `seed_problems_from_verification` to ingest baseline benchmark problems from `data/packingVerification/*.json` into the `problems` SQLite table.

2. **Ingestion Key Selection**:
   In `data/packingVerification/*.json`, `our_problem` contains the canonical problem string (e.g. `1_cirincir`, `14_TAN_in_circle`, `1_6_in_4`), matching what workers and the scheduler pass to `parse_problem` or `/api/v1/work`. In contrast, `id` has inverted suffix notation (`cirincir_1`). Therefore, `problems.id` must map from `item["our_problem"]`.

3. **Collision Avoidance via `ON CONFLICT`**:
   Because `cirindom.json` and `domincir.json` both define `1_domincir` .. `20_domincir`, duplicate primary key collisions are guaranteed during standard seeding. An `ON CONFLICT(id)` clause is required:
   ```sql
   INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status, source_attribution)
   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
   ON CONFLICT(id) DO UPDATE SET
       reference_s = excluded.reference_s,
       source_attribution = COALESCE(excluded.source_attribution, problems.source_attribution),
       status = CASE
           WHEN problems.status = 'proved_optimal' THEN problems.status
           WHEN excluded.status = 'proved_optimal' THEN excluded.status
           ELSE excluded.status
       END,
       best_s = CASE
           WHEN problems.best_s IS NULL THEN excluded.best_s
           WHEN excluded.best_s IS NOT NULL AND excluded.best_s < problems.best_s THEN excluded.best_s
           ELSE problems.best_s
       END
   ```
   This ensures that re-seeding on a live coordinator never overwrites solutions improved by volunteer workers with baseline metrics.

4. **Token Canonicalization**:
   Because `geometry.py`, `solution_tools.py`, and `packer_rs` interpret polygon tokens numerically via `int(token)` / `token.parse::<usize>()`, storing English words (`"hexagon"`, `"square"`, etc.) corrupts polygon container geometries into triangles. Normalizing tokens during seeding guarantees consistent geometry across coordinator verification and worker solvers.

5. **Exclusion Filtering for Scheduler**:
   The scheduler (`Task 2`) requires strictly excluding `proved_optimal` problems (`WHERE status != 'proved_optimal'`). Preserving `status` from the verification JSON (`proved_optimal`, `trivial`, `best_known`) allows the scheduler to automatically exclude all 49 proved optimal problems.

6. **Transaction Boundary**:
   Grouping all file reads and inserts into a single transaction achieves sub-10ms seeding for all 2,269 entries.

---

## 3. Caveats

1. **Non-Standard Container Geometries**:
   24 items in `cirinel.json` have container shape `"ellipse"`, and 31 items in `cirinttt.json` have container shape `"triangle (arbitrary)"`. These containers are not regular polygons and do not currently have analytic SAT representation in `packer_rs` or `geometry.py`. They will seed successfully into the database, but workers attempting them would need dedicated solver routines.
2. **Missing `source_url` in `triinhex.json`**:
   `triinhex.json` (54 items) does not include a `source_url` key. Since `source_url` is not a column in the `problems` table schema, this causes no database ingestion issues.
3. **Seeding Return Value Semantics**:
   If counting items processed, the return value is 2,269. If counting distinct rows created/upserted in the table, the count is 2,249 (due to 20 duplicate IDs in `cirindom.json`/`domincir.json`). The implementation should document whether it returns total items parsed or rows upserted.

---

## 4. Conclusion

### 4.1 Recommended Implementation for `seed_problems_from_verification`
In `src/shape_packing/server/database.py`:

```python
import glob
import json
import logging
import os
import sqlite3
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Map shape names to canonical tokens recognized by geometry.py, solution_tools.py, and packer_rs
CANONICAL_SHAPE_TOKENS: Dict[str, str] = {
    "3": "3", "TRIANGLE": "3", "TRI": "3",
    "4": "4", "SQUARE": "4", "SQU": "4",
    "5": "5", "PENTAGON": "5", "PEN": "5",
    "6": "6", "HEXAGON": "6", "HEX": "6",
    "7": "7", "HEPTAGON": "7", "HEP": "7",
    "8": "8", "OCTAGON": "8", "OCT": "8",
    "9": "9", "NONAGON": "9", "NON": "9",
    "10": "10", "DECAGON": "10", "DEC": "10",
    "CIRCLE": "CIRCLE", "CIR": "CIRCLE",
    "DOMINO": "DOMINO", "DOM": "DOMINO",
    "TAN": "TAN", "TANGRAM": "TAN",
    "L": "L", "LTROMINO": "L", "L-TROMINO": "L",
}

def normalize_shape_token(token: Any) -> str:
    """Normalize shape token to canonical format expected by solvers and verifiers."""
    if token is None:
        return ""
    s = str(token).strip().upper()
    return CANONICAL_SHAPE_TOKENS.get(s, s)

def seed_problems_from_verification(
    conn: sqlite3.Connection, verification_dir: str = "data/packingVerification"
) -> int:
    """
    Seed problems table from data/packingVerification/*.json.
    
    Returns the total number of items processed/upserted.
    """
    if not os.path.isdir(verification_dir):
        logger.warning("Verification directory '%s' does not exist.", verification_dir)
        return 0

    pattern = os.path.join(verification_dir, "*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        return 0

    rows = []
    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                continue

            for item in data:
                if not isinstance(item, dict):
                    continue

                our_problem = item.get("our_problem")
                if not our_problem:
                    continue

                n_raw = item.get("N", 0)
                try:
                    n = int(n_raw)
                    if n <= 0:
                        continue
                except (ValueError, TypeError):
                    continue

                raw_val = item.get("best_value")
                try:
                    best_val = float(raw_val) if raw_val is not None else None
                except (ValueError, TypeError):
                    best_val = None

                inner = normalize_shape_token(item.get("inner_shape"))
                container = normalize_shape_token(item.get("container_shape"))
                status = str(item.get("status") or "best_known")
                note = str(item.get("source_note") or "")

                rows.append((our_problem, inner, container, n, best_val, best_val, status, note))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to parse verification file %s: %s", file_path, exc)
            continue

    if not rows:
        return 0

    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    cursor.executemany(
        """
        INSERT INTO problems (
            id, inner_token, container_token, n, best_s, reference_s, status, source_attribution
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            reference_s = excluded.reference_s,
            source_attribution = COALESCE(excluded.source_attribution, problems.source_attribution),
            status = CASE
                WHEN problems.status = 'proved_optimal' THEN problems.status
                WHEN excluded.status = 'proved_optimal' THEN excluded.status
                ELSE excluded.status
            END,
            best_s = CASE
                WHEN problems.best_s IS NULL THEN excluded.best_s
                WHEN excluded.best_s IS NOT NULL AND excluded.best_s < problems.best_s THEN excluded.best_s
                ELSE problems.best_s
            END
        """,
        rows,
    )
    conn.commit()
    return len(rows)
```

---

## 5. Verification Method

### 5.1 Independent Verification Script
Run the following self-contained test command in the project root:

```bash
python3 -c '
import sqlite3
from src.shape_packing.server.database import init_db, seed_problems_from_verification

conn = init_db(":memory:")
count = seed_problems_from_verification(conn, "data/packingVerification")
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM problems")
total_unique = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM problems WHERE status = \"proved_optimal\"")
optimal_count = cursor.fetchone()[0]

cursor.execute("SELECT inner_token, container_token FROM problems WHERE id = \"1_cirinhex\"")
row = cursor.fetchone()

print(f"Items processed: {count} (expected 2269)")
print(f"Unique problems in DB: {total_unique} (expected 2249)")
print(f"Proved optimal problems: {optimal_count} (expected 49)")
print(f"1_cirinhex tokens: {row} (expected (\"CIRCLE\", \"6\"))")

assert count == 2269
assert total_unique == 2249
assert optimal_count == 49
assert row[0] == "CIRCLE" and row[1] == "6"
print("All verifications PASSED!")
'
```

### 5.2 Unit Test Cases for `tests/test_server_database.py`
Add to `tests/test_server_database.py`:
1. `test_seed_problems_from_verification`: Ingests from `data/packingVerification`, asserts `count == 2269`, asserts `cursor.execute("SELECT COUNT(*) FROM problems").fetchone()[0] == 2249`.
2. `test_seed_token_normalization`: Queries `SELECT inner_token, container_token FROM problems WHERE id = '1_cirinhex'`, asserts container is `"6"` (not `"HEXAGON"`).
3. `test_seed_preserves_improved_best_s`: Seeds once, updates `best_s` to `0.5`, re-seeds, verifies `best_s` remains `0.5` while `reference_s` reflects Friedman baseline.
4. `test_seed_missing_dir_handles_gracefully`: Calls `seed_problems_from_verification(conn, "non_existent_dir")`, asserts returns `0`.
