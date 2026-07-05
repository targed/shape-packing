#!/usr/bin/env python3
"""
Parse Erich Friedman's packing pages into a single reference TSV.

Usage:
    uv run scripts/parse_erich_friedman.py
"""
import os
import re
import sys
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "erich-friedman.github.io" / "packing"
OUT = Path(__file__).resolve().parent.parent / "PACKING_REFERENCE.tsv"

# Mapping from folder names to our (inner, container) tokens
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

def extract_float(s):
    # s is the string before <br>
    # Find all floats/ints in the string
    nums = re.findall(r"(\d*\.\d+|\d+)", (s or ""))
    if nums:
        # Return the last number found (which is usually the evaluated float)
        return str(float(nums[-1]))
    return None

def parse_html(html, family, inner_token, container_token):
    rows = []
    # Split into chunks per N based on "<font size=+3>N."
    tokens = re.split(r'<font\s+size=?\+?3\s*>', html)
    for tok in tokens:
        # first token before any N is header
        m = re.match(r'^(\d+)\.', tok)
        if not m:
            continue
        n = int(m.group(1))

        # find the numeric value
        val = None
        
        # Grab everything between <font size=+1> and 'Found by', 'Trivial', 'proved', or table cell endings
        # This handles multi-line math derivations where the evaluated float is on the second line.
        metric_match = re.search(r'<font\s+size=\+?1\s*>(.*?)(?:Found by|Trivial|proved|<td|<\/td)', tok, re.IGNORECASE | re.DOTALL)
        if metric_match:
            metric_str = metric_match.group(1)
            val = extract_float(metric_str)
        
        # Fallback if the first method didn't match anything
        if not val:
            metric_match = re.search(r'<font\s+size=\+?1\s*>(.*?)(?:<br>|$)', tok, re.IGNORECASE)
            if metric_match:
                metric_str = metric_match.group(1)
                val = extract_float(metric_str)

        # source / trivial / status
        status = "unknown"
        source = ""
        if "Trivial" in tok:
            status = "trivial"
        elif "proved" in tok.lower():
            status = "proved_optimal"
        elif "best known" in tok.lower():
            status = "best_known"
        else:
            status = "best_known"  # default assumption for non-trivial

        # extract author
        am = re.search(r'Found by (.+?)<br>', tok, re.IGNORECASE | re.DOTALL)
        if am:
            source = am.group(1).strip().replace('\n', ' ')

        rows.append({
            "problem_family": family,
            "n": n,
            "best_value": val or "",
            "source": source,
            "status": status,
            "our_problem": f"{n}_{inner_token}_in_{container_token}"
        })

    return rows

def main():
    if not ROOT.exists():
        print(f"Error: root not found: {ROOT}", file=sys.stderr)
        sys.exit(1)

    all_rows = []

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

        # if mapping known, use it
        if name in FOLDER_MAP:
            inner_token, container_token = FOLDER_MAP[name]
            family = f"{inner_token}_in_{container_token}"
            rows = parse_html(html, family, inner_token, container_token)
            all_rows.extend(rows)
        else:
            # Unknown folder: parse as-is but mark family as folder name
            family = name
            rows = parse_html(html, family, "?", "?")
            for r in rows:
                r["our_problem"] = None
            all_rows.extend(rows)

    # Write TSV
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["problem_family", "n", "best_value", "source", "status", "our_problem"])
        for r in sorted(all_rows, key=lambda x: (x["problem_family"], x["n"])):
            w.writerow([
                r["problem_family"],
                r["n"],
                r["best_value"],
                r["source"],
                r["status"],
                r["our_problem"]
            ])

    print(f"Written PACKING_REFERENCE.tsv with {len(all_rows)} entries to {OUT}")

if __name__ == "__main__":
    main()