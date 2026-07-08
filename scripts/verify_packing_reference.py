#!/usr/bin/env python3
"""
verify_packing_reference.py

For each row in PACKING_REFERENCE.tsv with numeric best_value:
  - Map problem_family -> Erich Friedman HTML dir
  - Parse n and corresponding s from that page
  - Compare to best_value
"""

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE = Path("erich-friedman.github.io/packing")

shape_to_token: Dict[str, str] = {
    "3": "tri",
    "4": "squ",
    "5": "pen",
    "6": "hex",
    "8": "oct",
    "CIRCLE": "cir",
    "DOMINO": "dom",
    "L": "L",
    "TAN": "tan",
}


def family_to_dir(pf: str) -> str:
    parts = pf.split("_in_")
    if len(parts) != 2:
        return ""
    ti = shape_to_token.get(parts[0], "")
    tc = shape_to_token.get(parts[1], "")
    if not ti or not tc:
        return ""
    return f"{ti}in{tc}"


def read_html(dir_name: str) -> str:
    p = BASE / dir_name / "index.html"
    if not p.exists():
        return ""
    return p.read_text(errors="ignore")


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s)


def extract_s_value(text: str) -> Optional[str]:
    m = re.search(r"s\s*=\s*.*?\s*=\s*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"s\s*=\s*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"=\s*([0-9]+\.[0-9]+)\+", text)
    if m:
        return m.group(1)
    return None


def parse_tr_rows(html: str) -> List[List[str]]:
    """
    Return list of TRs, each as list of TD cell texts (strip_tags).
    """
    table_blocks = re.split(r"<TABLE", html, flags=re.IGNORECASE)
    all_rows: List[List[str]] = []

    for block in table_blocks:
        tr_blocks = re.split(r"<TR", block, flags=re.IGNORECASE)
        for tr in tr_blocks:
            cells = re.findall(r"<TD[^>]*>(.*?)</TD>", tr, re.IGNORECASE | re.DOTALL)
            texts = [strip_tags(c).strip() for c in cells]
            if texts:
                all_rows.append(texts)

    return all_rows


def parse_n_s_map(html: str) -> Dict[int, str]:
    """
    For each TR:
      - Detect if it is a label row (contains N.)
      - Detect if it is an s-value row.
    Then, for pairs of rows (label_row, s_row) with same length:
      - For each column, if label -> n, and s_row[col] has s-value, record.
    """
    rows = parse_tr_rows(html)
    result: Dict[int, str] = {}

    # Identify label rows and s-rows by content
    label_rows: List[Tuple[int, List[Optional[int]]]] = []
    s_rows: List[Tuple[int, List[Optional[str]]]] = []

    for ri, row in enumerate(rows):
        labels: List[Optional[int]] = [None] * len(row)
        svals: List[Optional[str]] = [None] * len(row)

        for ci, cell in enumerate(row):
            # Check label: "N." or "N-M."
            m = re.search(r"^(\d+)\s*(?:[-–—]\s*(\d+))?\.(?!\d)", cell.strip())
            if m:
                n1 = int(m.group(1))
                n2 = int(m.group(2)) if m.group(2) else n1
                for n in range(n1, n2 + 1):
                    labels[ci] = n  # last wins; for ranges, same cell
            # Check s-value
            sv = extract_s_value(cell)
            if sv is not None:
                svals[ci] = sv

        if any(x is not None for x in labels):
            label_rows.append((ri, labels))
        if any(x is not None for x in svals):
            s_rows.append((ri, svals))

    # For each label row, find nearest s-row after it with same length
    for lri, labels in label_rows:
        best = None
        best_dist = None
        for sri, svals in s_rows:
            if sri <= lri:
                continue
            if len(svals) != len(labels):
                continue
            dist = sri - lri
            if best_dist is None or dist < best_dist:
                best = svals
                best_dist = dist

        if best is None:
            continue

        for n, sv in zip(labels, best):
            if n is not None and sv is not None:
                result[n] = sv

    return result


def verify_row(pf: str, n_str: Optional[str], bv_str: Optional[str],
               src_str: Optional[str], status_str: Optional[str]) -> None:
    if not n_str or not bv_str:
        return

    try:
        n = int(n_str)
    except ValueError:
        return

    try:
        bv = float(bv_str)
    except ValueError:
        return

    dir_name = family_to_dir(pf)
    if not dir_name:
        return

    html = read_html(dir_name)
    if not html:
        return

    n_s = parse_n_s_map(html)

    if n in n_s:
        try:
            hv = float(n_s[n])
            diff = abs(hv - bv)
            if diff > 0.001:
                print(f"MISMATCH: {pf} n={n}: TSV={bv}, HTML={hv}, diff={diff:.5f}")
        except ValueError:
            print(f"PARSE_ERROR: {pf} n={n}: HTML s='{n_s[n]}' not numeric")
    else:
        if status_str in ("best_known", "proved_optimal"):
            print(f"NOT_FOUND: {pf} n={n}: not present in HTML (status={status_str})")

    if src_str:
        src = src_str.strip()
        tokens = [t for t in re.split(r"\s+", src) if len(t) >= 3]
        if tokens:
            any_found = any(t.lower() in html.lower() for t in tokens)
            if not any_found:
                print(f"SOURCE_MISSING: {pf} n={n}: source='{src}' not found in page")


def main() -> None:
    rows: List[Dict[str, str]] = []
    with open("PACKING_REFERENCE.tsv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)

    print("Starting verification of PACKING_REFERENCE.tsv against HTML...")
    count = 0
    for row in rows:
        pf = row.get("problem_family", "").strip()
        n = row.get("n", "").strip() or None
        bv = row.get("best_value", "").strip() or None
        src = row.get("source", "").strip() or None
        status = row.get("status", "").strip() or None

        if bv:
            count += 1
            verify_row(pf, n, bv, src, status)

    print(f"Done. Checked {count} rows with numeric best_value.")


if __name__ == "__main__":
    main()