# Multi-Source Catalog Ingestion & Procedural Frontiers Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the coordinator problem catalog beyond Erich Friedman by building automated ingestors for Eckard Specht's Packomania circle-packing datasets and a procedural frontier generator for arbitrary polygon pairings up to $N \le 200$.

**Architecture:** A modular ingestor package in `src/shape_packing/server/ingestors/` parses external data tables and calculates theoretical lower area bounds ($\rho = 1.0$). The procedural generator synthesizes $(N, \text{inner}, \text{container})$ problem records with initial infinite best metrics, feeding the multi-armed bandit scheduler with new frontier problems.

**Tech Stack:** Python 3, `urllib.request`, `html.parser`, SQLite WAL, pytest.

**Spec:** `docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md`

## Global Constraints

- No third-party scraping libraries (use Python's standard library `html.parser` and `urllib.request`).
- Ingestion must be idempotent: existing world records in `problems.best_s` found by the network must never be overwritten or clobbered by incoming reference scores.
- Every ingested record must have valid normalized shape tokens (`CIRCLE`, `3`, `4`, `5`, `6`, `8`, `TAN`, `DOMINO`, `L`).

---

### Task 1: Packomania Circle Packing Ingestor

**Files:**
- Create: `src/shape_packing/server/ingestors/__init__.py`
- Create: `src/shape_packing/server/ingestors/packomania.py`
- Test: `tests/test_ingestor_packomania.py`

**Interfaces:**
- Consumes: `urllib.request`, `html.parser`, `src/shape_packing/server/database.py`
- Produces:
  - `parse_packomania_table(html_content: str, container_token: str) -> List[Dict[str, Any]]`
  - `ingest_packomania_to_db(conn: sqlite3.Connection, html_content: str, container_token: str) -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingestor_packomania.py
import sqlite3
import pytest
from src.shape_packing.server.database import init_db, get_problem
from src.shape_packing.server.ingestors.packomania import (
    parse_packomania_table,
    ingest_packomania_to_db,
)

SAMPLE_PACKOMANIA_HTML = """
<table>
  <tr><th>n</th><th>r</th><th>s</th><th>author</th></tr>
  <tr><td>1</td><td>0.500000</td><td>2.000000</td><td>Trivial</td></tr>
  <tr><td>2</td><td>0.292893</td><td>3.414213</td><td>Pirl</td></tr>
  <tr><td>3</td><td>0.254333</td><td>3.931851</td><td>Kravitz</td></tr>
</table>
"""

def test_parse_packomania_table():
    records = parse_packomania_table(SAMPLE_PACKOMANIA_HTML, container_token="4")
    assert len(records) == 3
    assert records[0]["n"] == 1
    assert records[0]["reference_s"] == pytest.approx(2.0)
    assert records[1]["n"] == 2
    assert records[1]["reference_s"] == pytest.approx(3.414213)
    assert records[1]["source_author"] == "Pirl"

def test_ingest_packomania_to_db(tmp_path):
    db_path = str(tmp_path / "test_packomania.db")
    conn = init_db(db_path)

    count = ingest_packomania_to_db(conn, SAMPLE_PACKOMANIA_HTML, container_token="4")
    assert count == 3

    prob = get_problem(conn, "2_CIRCLE_in_4")
    assert prob is not None
    assert prob["n"] == 2
    assert prob["inner_token"] == "CIRCLE"
    assert prob["container_token"] == "4"
    assert prob["reference_s"] == pytest.approx(3.414213)
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingestor_packomania.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.shape_packing.server.ingestors'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/shape_packing/server/ingestors/__init__.py
"""Ingestion modules for external shape packing databases."""

# src/shape_packing/server/ingestors/packomania.py
from __future__ import annotations
import re
import sqlite3
from html.parser import HTMLParser
from typing import Any, Dict, List

class PackomaniaHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.rows: List[List[str]] = []
        self.current_row: List[str] = []
        self.current_cell: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
        elif tag == "tr" and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.current_cell = []

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                self.rows.append(self.current_row)
        elif tag in ("td", "th") and self.in_cell:
            self.in_cell = False
            self.current_row.append("".join(self.current_cell).strip())

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell.append(data)

def parse_packomania_table(html_content: str, container_token: str) -> List[Dict[str, Any]]:
    parser = PackomaniaHTMLParser()
    parser.feed(html_content)
    results = []

    for row in parser.rows:
        if not row or not row[0].isdigit():
            continue
        try:
            n = int(row[0])
            s = float(row[2]) if len(row) > 2 else float(row[1])
            author = row[3] if len(row) > 3 else "Packomania"
            results.append({
                "problem_id": f"{n}_CIRCLE_in_{container_token.upper()}",
                "n": n,
                "inner_token": "CIRCLE",
                "container_token": container_token.upper(),
                "reference_s": s,
                "source_author": author,
            })
        except (ValueError, IndexError):
            continue
    return results

def ingest_packomania_to_db(
    conn: sqlite3.Connection, html_content: str, container_token: str
) -> int:
    records = parse_packomania_table(html_content, container_token)
    cursor = conn.cursor()
    inserted = 0

    for r in records:
        cursor.execute(
            """
            INSERT INTO problems (id, inner_token, container_token, n, reference_s, best_s, status, source_attribution)
            VALUES (?, ?, ?, ?, ?, ?, 'best_known', ?)
            ON CONFLICT(id) DO UPDATE SET reference_s = excluded.reference_s
            WHERE problems.best_s IS NULL OR problems.best_s > excluded.reference_s
            """,
            (
                r["problem_id"],
                r["inner_token"],
                r["container_token"],
                r["n"],
                r["reference_s"],
                r["reference_s"],
                f"Eckard Specht (Packomania) - {r['source_author']}",
            ),
        )
        inserted += 1

    conn.commit()
    return inserted
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingestor_packomania.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/shape_packing/server/ingestors/__init__.py src/shape_packing/server/ingestors/packomania.py tests/test_ingestor_packomania.py
git commit -m "feat(server): add Packomania circle packing ingestor"
```

---

### Task 2: Procedural Frontier Problem Generator

**Files:**
- Create: `src/shape_packing/server/ingestors/frontier_generator.py`
- Test: `tests/test_frontier_generator.py`

**Interfaces:**
- Consumes: `src/shape_packing/geometry.py`, `src/shape_packing/server/database.py`
- Produces:
  - `generate_frontier_problems(conn: sqlite3.Connection, inner_tokens: List[str], container_tokens: List[str], min_n: int = 1, max_n: int = 100) -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_frontier_generator.py
import sqlite3
import pytest
from src.shape_packing.server.database import init_db, get_problem
from src.shape_packing.server.ingestors.frontier_generator import generate_frontier_problems

def test_generate_frontier_problems(tmp_path):
    db_path = str(tmp_path / "frontier_test.db")
    conn = init_db(db_path)

    # Pre-seed one problem with known record
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO problems (id, inner_token, container_token, n, best_s, reference_s, status) "
        "VALUES ('5_3_in_4', '3', '4', 5, 3.2, 3.2, 'best_known')"
    )
    conn.commit()

    count = generate_frontier_problems(
        conn,
        inner_tokens=["3"],
        container_tokens=["4"],
        min_n=5,
        max_n=7,
    )
    assert count == 2  # N=6 and N=7 generated, N=5 skipped

    p6 = get_problem(conn, "6_3_in_4")
    assert p6 is not None
    assert p6["status"] == "unattempted"
    assert p6["best_s"] is None
    assert p6["reference_s"] is None
    assert p6["density_rank"] > 0

    p5 = get_problem(conn, "5_3_in_4")
    assert p5["best_s"] == pytest.approx(3.2)  # Untouched
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_frontier_generator.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# src/shape_packing/server/ingestors/frontier_generator.py
from __future__ import annotations
import math
import sqlite3
from typing import List

SHAPE_UNIT_AREAS = {
    "3": math.sqrt(3) / 4.0,
    "4": 1.0,
    "5": 0.25 * math.sqrt(5 * (5 + 2 * math.sqrt(5))),
    "6": 1.5 * math.sqrt(3),
    "8": 2.0 * (1.0 + math.sqrt(2)),
    "CIRCLE": math.pi,
    "TAN": 0.5,
    "DOMINO": 2.0,
    "L": 3.0,
}

def generate_frontier_problems(
    conn: sqlite3.Connection,
    inner_tokens: List[str],
    container_tokens: List[str],
    min_n: int = 1,
    max_n: int = 100,
) -> int:
    cursor = conn.cursor()
    generated = 0

    for inner in inner_tokens:
        inner_norm = inner.strip().upper()
        a_inner = SHAPE_UNIT_AREAS.get(inner_norm, 1.0)

        for container in container_tokens:
            container_norm = container.strip().upper()

            for n in range(min_n, max_n + 1):
                prob_id = f"{n}_{inner_norm}_in_{container_norm}"
                cursor.execute("SELECT id FROM problems WHERE id = ?", (prob_id,))
                if cursor.fetchone():
                    continue

                # Theoretical void space density score
                density_priority = 1.0 / math.sqrt(n)

                cursor.execute(
                    """
                    INSERT INTO problems (id, inner_token, container_token, n, status, density_rank, source_attribution)
                    VALUES (?, ?, ?, ?, 'unattempted', ?, 'Procedural Frontier Generator')
                    """,
                    (prob_id, inner_norm, container_norm, n, density_priority),
                )
                generated += 1

    conn.commit()
    return generated
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_frontier_generator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/shape_packing/server/ingestors/frontier_generator.py tests/test_frontier_generator.py
git commit -m "feat(server): implement procedural frontier generator for unattempted high-N configurations"
```
