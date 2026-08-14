#!/usr/bin/env python3
"""
CLI script to audit and export all broken world records into a submission bundle.
Usage:
    python scripts/export_records.py [OPTIONS]
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.shape_packing.records_exporter import export_records

def main():
    parser = argparse.ArgumentParser(description="Export world-record packing solutions for submission to Erich Friedman.")
    parser.add_argument("--results-dir", default="results", help="Path to results directory (default: results)")
    parser.add_argument("--output-dir", default="records", help="Path to export directory (default: records)")
    parser.add_argument("--min-improvement", type=float, default=1e-5, help="Minimum improvement delta (default: 1e-5)")
    parser.add_argument("--family", default="all", help="Filter by shape family code (e.g. dominpen, dominhex, or all)")
    parser.add_argument("--clean", action="store_true", help="Clean output directory before exporting")
    parser.add_argument("--dpi", type=int, default=300, help="Image DPI for rendered PNGs (default: 300)")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose logging")

    args = parser.parse_args()

    print("=" * 80)
    print("SHAPE PACKING WORLD RECORDS EXPORTER")
    print("=" * 80)

    summary = export_records(
        results_dir=args.results_dir,
        output_dir=args.output_dir,
        min_improvement=args.min_improvement,
        family_filter=args.family if args.family != "all" else None,
        clean=args.clean,
        dpi=args.dpi,
        quiet=args.quiet,
    )

    print("\n" + "=" * 80)
    print("EXPORT COMPLETE:")
    print(f"  Total Record Candidates: {summary['candidates_count']}")
    print(f"  Successfully Exported:   {summary['exported_count']}")
    print(f"  Failed / Invalid:        {summary['failed_count']}")
    print(f"  Summary Report:          {summary['summary_path']}")
    print(f"  Manifest File:           {summary['manifest_path']}")
    print(f"  Email Drafts:            {len(summary['email_drafts'])} generated")
    print("=" * 80)

if __name__ == "__main__":
    main()
