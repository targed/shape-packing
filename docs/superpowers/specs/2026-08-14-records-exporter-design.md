# Records Exporter & Submission Bundle Design

## Overview
This document specifies the design for a standalone Records Exporter tool (`src/shape_packing/records_exporter.py` and `scripts/export_records.py`) that audits all packing experiment solutions in `results/`, identifies genuine world records that strictly beat Erich Friedman's published benchmarks (`packingVerification/*.json`), performs full geometric SAT and boundary validation, and exports a curated `records/` submission bundle ready for delivery to `erich-friedman.github.io`.

## Goals
- Identify every solution in `results/` that achieves a better metric than Erich Friedman's published records ($s_{\text{ours}} < s_{\text{Friedman}} - \epsilon$).
- Validate each record candidate against strict geometric criteria (0 SAT collisions, 100% boundary containment inside container, verified inner polygon geometry).
- Export an organized `records/` folder grouped by shape family (e.g. `dominpen`, `dominhex`, `squincir`).
- For each record, package:
  - `solution.json`: Raw solver output containing parameters and metric values.
  - `render.png`: Clean, tight-cropped high-resolution render of the packing.
  - `coordinates.txt`: Formatted text table of piece centers, orientations, and vertex coordinates suitable for independent verification by Erich Friedman.
  - `verification.txt`: Geometric validation log proving SAT collision separation and container containment.
- Generate top-level submission manifests:
  - `records/manifest.json`: Structured index of all exported records.
  - `records/summary.md`: Markdown summary table of all broken records and their improvements.
  - `records/submissions/<family>_submission.md`: Pre-drafted submission emails for each shape family.

## Non-Goals
- Modifying core solver math or optimizer internals.
- Exporting personal bests that do not beat the known world benchmark.
- Automatically emailing submissions without human review.

## Architecture & Module Structure

### 1. New Module: `src/shape_packing/records_exporter.py`
Contains the core record discovery, verification, and export logic:
- `find_all_records(results_dir, min_improvement=1e-5, family_filter=None) -> List[RecordCandidate]`
- `export_record(candidate, output_dir, crop_mode="tight", dpi=300) -> ExportResult`
- `generate_coordinates_text(solution) -> str`
- `generate_verification_text(solution, verify_result) -> str`
- `generate_submission_manifests(records, output_dir) -> Tuple[str, str]`
- `generate_email_drafts(records, output_dir) -> List[str]`

### 2. CLI Entrypoint: `scripts/export_records.py`
Thin executable script exposing command-line arguments:
- `--results-dir`: Path to results directory (default: `results/`)
- `--output-dir`: Destination path for export bundle (default: `records/`)
- `--min-improvement`: Threshold for record validation (default: `1e-5`)
- `--family`: Specific shape family code or `all` (default: `all`)
- `--clean`: Wipe output directory before exporting
- `--dpi`: Rendering DPI (default: `300`)
- `--quiet`: Suppress verbose progress logs

## File Layout Specification

```text
records/
├── summary.md
├── manifest.json
├── submissions/
│   ├── dominpen_submission.md
│   ├── dominhex_submission.md
│   └── ...
└── <family_code>/                  # e.g., dominpen, dominhex, squincir
    └── <N>_<inner>_in_<container>/   # e.g., 21_DOMINO_in_5
        ├── solution.json
        ├── render.png
        ├── coordinates.txt
        └── verification.txt
```

### Format of `coordinates.txt`
```text
================================================================================
RECORD SUBMISSION: 21 DOMINO in PENTAGON
================================================================================
Problem: 21_DOMINO_in_5
Family: dominpen (https://erich-friedman.github.io/packing/dominpen/index.html)
Inner Shape: Domino (unit 1.0 x 2.0 rectangle)
Container: Regular Pentagon
Circumradius S: 4.603855
Container Side Length s: 5.412156
Previous Friedman Benchmark: 5.553080
New Record Score: 5.412156
Improvement: -0.140924 (-2.54%)

Pieces (21 total):
#  | Center (x, y)          | Angle (deg)  | Vertices [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
1  | ( 0.521034, -2.140825) |   90.00 deg  | [(-0.478966, -2.640825), ( 1.521034, -2.640825), ...]
...
================================================================================
```

### Format of `verification.txt`
```text
================================================================================
GEOMETRIC VALIDATION LOG
================================================================================
Problem: 21_DOMINO_in_5
Verified At: 2026-08-14T09:28:00Z
Status: VALID

1. Inner Shapes:
   - Count: 21
   - Dimensions: All 21 polygons are exact 1.0 x 2.0 rectangles.

2. Pairwise Collision Check (SAT):
   - Pairs Tested: 210
   - Maximum Pairwise Overlap: 0.000000000000 (Tolerance: 1.0e-05)
   - Overlap Status: PASS (0 overlaps)

3. Container Containment Check:
   - Vertices Tested: 84 / 84
   - Maximum Out-of-Bounds Distance: 0.000000000000 (Tolerance: 1.0e-05)
   - Containment Status: PASS (All vertices inside regular pentagon)

4. Metric Calculation:
   - Solver S (Circumradius): 4.603854515775
   - Container Side Length s: 2 * S * sin(pi / 5) = 5.412155576146
   - Benchmark Score: 5.553080000000
   - Delta: -0.140924423854
================================================================================
```

## Testing Strategy
- `tests/test_records_exporter.py`:
  - Test record discovery with synthetic and existing `results/`.
  - Test candidate filtering (ensure non-records and ties are rejected).
  - Test `coordinates.txt` generation accuracy against polygon vertices.
  - Test `verification.txt` output formatting.
  - Test `export_records` end-to-end with temporary directories.
  - Test CLI argument parsing and error handling.
