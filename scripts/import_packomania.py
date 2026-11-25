#!/usr/bin/env python3
"""Import and normalize Packomania circle-packing benchmarks into data/packingVerification/."""
from __future__ import annotations

import json
import math
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from shape_packing.catalog import canonical_problem_id

PV_DIR = PROJECT_ROOT / "data" / "packingVerification"

PACKOMANIA_SOURCES: List[Dict[str, Any]] = [
    {
        "family": "cirin7",
        "our_suffix": "cirin7",
        "container_token": "7",
        "container_shape": "heptagon",
        "url": "https://www.packomania.com/chp/txt/radius.txt",
        "page_url": "https://www.packomania.com/chp/chp.html",
        "value_kind": "radius",
        "max_n": 50,
    },
    {
        "family": "cirinoct",
        "our_suffix": "cirinoct",
        "container_token": "8",
        "container_shape": "octagon",
        "url": "https://www.packomania.com/coc/txt/radius.txt",
        "page_url": "https://www.packomania.com/coc/coc.html",
        "value_kind": "radius",
        "max_n": 50,
    },
    {
        "family": "cirin9",
        "our_suffix": "cirin9",
        "container_token": "9",
        "container_shape": "nonagon",
        "url": "https://www.packomania.com/cno/txt/radius.txt",
        "page_url": "https://www.packomania.com/cno/cno.html",
        "value_kind": "radius",
        "max_n": 50,
    },
    {
        "family": "cirin10",
        "our_suffix": "cirin10",
        "container_token": "10",
        "container_shape": "decagon",
        "url": "https://www.packomania.com/cdc/txt/radius.txt",
        "page_url": "https://www.packomania.com/cdc/cdc.html",
        "value_kind": "radius",
        "max_n": 50,
    },
    {
        "family": "cirinsemi",
        "our_suffix": "cirinsemi",
        "container_token": "SEMICIRCLE",
        "container_shape": "semicircle",
        "url": "https://www.packomania.com/csc/txt/ratio.txt",
        "page_url": "https://www.packomania.com/csc/csc.html",
        "value_kind": "ratio",
        "max_n": 50,
    },
    {
        "family": "cirinquad",
        "our_suffix": "cirinquad",
        "container_token": "QUADRANT",
        "container_shape": "quadrant",
        "url": "https://www.packomania.com/ccq/txt/ratio.txt",
        "page_url": "https://www.packomania.com/ccq/ccq.html",
        "value_kind": "ratio",
        "max_n": 50,
    },
    {
        "family": "cirindom",
        "our_suffix": "cirindom",
        "container_token": "DOMINO",
        "container_shape": "domino",
        "url": "https://www.packomania.com/crc_500/txt/ratio.txt",
        "page_url": "https://www.packomania.com/crc_500/crc.html",
        "value_kind": "ratio",
        "max_n": 50,
    },
]


def convert_packomania_to_friedman_s(
    raw_val: float,
    container_token: str,
    value_kind: str,
    n: int,
) -> float:
    """
    Convert Packomania metric to our benchmark metric s (container edge length or radius per unit circle).

    For regular n-gons (value_kind='radius'), Packomania reports inner circle radius r
    inside a unit-circumradius polygon (R=1.0). We convert to side length s = 2*sin(pi/n)/r,
    correcting Packomania's N=1 half-radius table quirk on cno (9) and cdc (10).
    For SEMICIRCLE, QUADRANT, and DOMINO (value_kind='ratio'), ratio.txt already stores R/r or short_side/r.
    """
    if raw_val <= 0:
        raise ValueError(f"Invalid positive value expected, got {raw_val}")

    kind = value_kind.strip().lower()
    if kind == "ratio":
        return float(raw_val)

    if kind == "radius":
        sides = int(container_token)
        r = float(raw_val)
        # Packomania cno (N=9) and cdc (N=10) list 0.5 * cos(pi/n) on N=1 instead of cos(pi/n)
        if sides in (9, 10) and n == 1 and r < 0.6:
            r *= 2.0
        return (2.0 * math.sin(math.pi / sides)) / r

    raise ValueError(f"Unsupported value_kind: {value_kind!r}")


def parse_packomania_txt(text: str, max_n: int = 50) -> List[Tuple[int, float]]:
    """Parse '<N> <value>' lines from a Packomania txt endpoint."""
    rows: List[Tuple[int, float]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        try:
            n = int(parts[0])
            val = float(parts[1])
        except ValueError:
            continue
        if 1 <= n <= max_n:
            rows.append((n, val))
    rows.sort(key=lambda item: item[0])
    return rows


def fetch_and_import_all(pv_dir: Path = PV_DIR) -> Dict[str, int]:
    """Fetch Packomania reference tables and write normalized JSON files under pv_dir."""
    pv_dir.mkdir(parents=True, exist_ok=True)
    counts: Dict[str, int] = {}

    for spec in PACKOMANIA_SOURCES:
        req = urllib.request.Request(
            spec["url"],
            headers={"User-Agent": "shape-packing-benchmark-importer/1.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw_text = resp.read().decode("utf-8", "ignore")

        parsed = parse_packomania_txt(raw_text, max_n=int(spec["max_n"]))
        out_rows: List[Dict[str, Any]] = []
        for n, raw_val in parsed:
            s_val = convert_packomania_to_friedman_s(
                raw_val,
                container_token=spec["container_token"],
                value_kind=spec["value_kind"],
                n=n,
            )
            status = "trivial" if n == 1 else "best_known"
            fam = spec["family"]
            out_rows.append(
                {
                    "problem_family": fam,
                    "N": n,
                    "inner_shape": "circle",
                    "container_shape": spec["container_shape"],
                    "best_value": round(s_val, 12),
                    "status": status,
                    "tier": "benchmark",
                    "source_note": "Packomania (Eckard Specht), normalized to unit inner circle.",
                    "our_problem": canonical_problem_id(n, "circle", spec["container_shape"]),
                    "id": f"{fam}_{n}",
                    "source_url": spec["page_url"],
                }
            )

        out_path = pv_dir / f"{spec['family']}.json"
        out_path.write_text(json.dumps(out_rows, indent=2) + "\n", encoding="utf-8")
        counts[spec["family"]] = len(out_rows)
        print(f"Wrote {len(out_rows)} entries to {out_path}")

    return counts


if __name__ == "__main__":
    fetch_and_import_all()
