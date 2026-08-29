#!/usr/bin/env python3
"""
DO NOT USE. OUTDATED. GIVES BAD INFO. LOOK AT PACKING VERIFICATION FOLDER
Parse Erich Friedman's packing pages (local HTML) into a structured JSON reference.

Input:
- erich-friedman.github.io/packing/<folder>/index.html

Output:
- PACKING_REFERENCE.json: list of entries with:
    id, problem_family, N, inner_shape, container_shape,
    best_value (float|null), status, source_url, source_note, our_problem

Status values:
- trivial
- proved_optimal
- best_known
- unknown (if unclear)

Usage:
- uv run scripts/parse_erich_friedman.py
- python3 scripts/parse_erich_friedman.py
"""

import json
import re
import sys
from pathlib import Path

root_candidates = [
    Path(__file__).resolve().parent.parent / "data" / "erich-friedman.github.io" / "packing",
    Path(__file__).resolve().parent.parent / "docs" / "erich-friedman.github.io" / "packing",
    Path(__file__).resolve().parent.parent / "erich-friedman.github.io" / "packing",
]
ROOT = next((c for c in root_candidates if c.exists()), root_candidates[0])
OUT = Path(__file__).resolve().parent.parent / "PACKING_REFERENCE.json"
BASE_URL = "https://erich-friedman.github.io/packing"

# Mapping from folder names to (inner_token, container_token)
FOLDER_MAP = {
    # Triangles in ...
    "triincir": ("3", "CIRCLE"),
    "triintan": ("3", "TAN"),
    "triinsqu": ("3", "4"),
    "triintri": ("3", "3"),
    "triinpen": ("3", "5"),
    "triinhex": ("3", "6"),
    "triinoct": ("3", "8"),
    "triinL":   ("3", "L"),
    "triindom": ("3", "DOMINO"),
    # Squares in ...
    "squincir": ("4", "CIRCLE"),
    "squintan": ("4", "TAN"),
    "squinsqu": ("4", "4"),
    "squintri": ("4", "3"),
    "squinpen": ("4", "5"),
    "squinhex": ("4", "6"),
    "squinoct": ("4", "8"),
    "squinl":   ("4", "L"),
    "squindom": ("4", "DOMINO"),
    # Pentagons in ...
    "penincir": ("5", "CIRCLE"),
    "penintan": ("5", "TAN"),
    "peninsqu": ("5", "4"),
    "penintri": ("5", "3"),
    "peninpen": ("5", "5"),
    "peninhex": ("5", "6"),
    "peninoct": ("5", "8"),
    "peninL":   ("5", "L"),
    "penindom": ("5", "DOMINO"),
    # Hexagons in ...
    "hexincir": ("6", "CIRCLE"),
    "hexintan": ("6", "TAN"),
    "hexinsqu": ("6", "4"),
    "hexintri": ("6", "3"),
    "hexinpen": ("6", "5"),
    "hexinhex": ("6", "6"),
    "hexinoct": ("6", "8"),
    "hexinL":   ("6", "L"),
    "hexindom": ("6", "DOMINO"),
    # Octagons in ...
    "octincir": ("8", "CIRCLE"),
    "octintan": ("8", "TAN"),
    "octinsqu": ("8", "4"),
    "octintri": ("8", "3"),
    "octinpen": ("8", "5"),
    "octinhex": ("8", "6"),
    "octinoct": ("8", "8"),
    "octinL":   ("8", "L"),
    "octindom": ("8", "DOMINO"),
    # Tans in ...
    "tanincir": ("TAN", "CIRCLE"),
    "tanintan": ("TAN", "TAN"),
    "taninsqu": ("TAN", "4"),
    "tanintri": ("TAN", "3"),
    "taninpen": ("TAN", "5"),
    "taninhex": ("TAN", "6"),
    "taninoct": ("TAN", "8"),
    "taninL":   ("TAN", "L"),
    "tanindom": ("TAN", "DOMINO"),
    # Dominoes in ...
    "domincir": ("DOMINO", "CIRCLE"),
    "domintan": ("DOMINO", "TAN"),
    "dominsqu": ("DOMINO", "4"),
    "domintri": ("DOMINO", "3"),
    "dominpen": ("DOMINO", "5"),
    "dominhex": ("DOMINO", "6"),
    "dominoct": ("DOMINO", "8"),
    "dominL":   ("DOMINO", "L"),
    "domindom": ("DOMINO", "DOMINO"),
    # L in ...
    "lincir":   ("L", "CIRCLE"),
    "Lintan":   ("L", "TAN"),
    "linsqu":   ("L", "4"),
    "Lintri":   ("L", "3"),
    "Linpen":   ("L", "5"),
    "Linhex":   ("L", "6"),
    "Linoct":   ("L", "8"),
    "LinL":     ("L", "L"),
    "Lindom":   ("L", "DOMINO"),
}


def extract_float(s: str):
    nums = re.findall(r"(\d+\.\d+|\d+)", (s or ""))
    if not nums:
        return None
    try:
        return float(nums[-1])
    except ValueError:
        return None


def parse_status(tok: str):
    lower = tok.lower()

    # "Trivial" explicitly stated
    if "trivial" in lower:
        return "trivial"

    # "proved" / "proof" / "optimal" with clear meaning
    # Use this only when it really looks like an optimality claim.
    if "proved optimal" in lower or "proof" in lower:
        return "proved_optimal"

    # "best known" / "best_known" / "best-known"
    if "best known" in lower or "best_known" in lower:
        return "best_known"

    # Default: best_known (Erich often lists best known without extra label)
    return "best_known"


def parse_html(html: str, family: str, inner_token: str, container_token: str):
    rows = []
    # Split into sections by N: look for "<font size=+3>N."
    tokens = re.split(r'<font\s+size=?\+?3\s*>', html)

    for tok in tokens:
        # Try to match N at start
        m = re.match(r'^(\d+)\.', tok)
        if not m:
            continue
        n = int(m.group(1))

        # Extract metric value from <font size=+1> or <font size=1> block.
        # The HTML often contains things like "s = 8.37807+<br>Found by ..."
        # so we must handle '+' and other trailing symbols.
        val = None
        metric_match = re.search(
            r'<font\s+size=\+?1\s*>(.*?)(?:Found by|Trivial|proved|<td|</td>)',
            tok,
            re.IGNORECASE | re.DOTALL,
        )
        if metric_match:
            val = extract_float(metric_match.group(1))
        if val is None:
            metric_match = re.search(
                r'<font\s+size=\+?1\s*>(.*?)(?:<br>|$)',
                tok,
                re.IGNORECASE,
            )
            if metric_match:
                val = extract_float(metric_match.group(1))

        status = parse_status(tok)

        # Extract author note
        source_note = ""
        am = re.search(r'Found by (.+?)<br>', tok, re.IGNORECASE | re.DOTALL)
        if am:
            source_note = " ".join(am.group(1).split()).strip()

        rows.append({
            "problem_family": family,
            "N": n,
            "inner_shape": inner_token,
            "container_shape": container_token,
            "best_value": val,
            "status": status,
            "source_note": source_note,
            "our_problem": f"{n}_{inner_token}_in_{container_token}",
        })

    return rows


def main():
    if not ROOT.exists():
        print(f"Error: root not found: {ROOT}", file=sys.stderr)
        sys.exit(1)

    all_entries = []

    for folder in sorted(ROOT.iterdir()):
        if not folder.is_dir():
            continue
        name = folder.name
        if name.startswith(".") or name in ("logos", "almost"):
            continue

        html_file = folder / "index.html"
        if not html_file.exists():
            continue

        html = html_file.read_text(encoding="utf-8", errors="ignore")
        source_url = f"{BASE_URL}/{name}/index.html"

        if name in FOLDER_MAP:
            inner_token, container_token = FOLDER_MAP[name]
            family = f"{inner_token}_in_{container_token}"
            entries = parse_html(html, family, inner_token, container_token)
        else:
            # Unknown folder: parse but mark as unknown shapes
            family = name
            entries = parse_html(html, family, "?", "?")
            # For unknown mapping, our_problem becomes None
            for e in entries:
                e["our_problem"] = None

        # Attach source_url, id
        for e in entries:
            if e["our_problem"]:
                e["id"] = f"{family}_{e['N']}"
            else:
                e["id"] = f"{family}_{e['N']}"
            e["source_url"] = source_url

        all_entries.extend(entries)

    # Sort by problem_family, N
    all_entries.sort(key=lambda x: (x["problem_family"], x["N"]))

    # Write JSON
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, indent=2, ensure_ascii=False)

    print(f"Written PACKING_REFERENCE.json with {len(all_entries)} entries to {OUT}")


if __name__ == "__main__":
    main()
