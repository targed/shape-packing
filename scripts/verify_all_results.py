#!/usr/bin/env python3
"""
Recursively verify all solution.json files under results/
using solution_tools.verify_solution, collect failures, then remove them.

Usage (from shape-packing root):
  uv run python scripts/verify_all_results.py --dry-run
  uv run python scripts/verify_all_results.py
"""

import argparse
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

_SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = _SCRIPT_DIR.parent / "results"

# Import verify_solution in-process (avoids per-file subprocess overhead)
sys.path.insert(0, str(_SCRIPT_DIR.parent / "src"))
try:
    from shape_packing.solution_tools import verify_solution
except ImportError:
    raise RuntimeError("Cannot import shape_packing.solution_tools. "
                       "Ensure you are running from the shape-packing root.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify all results/ solution.json files and remove failures."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List failures but do not delete anything."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel workers (default: 8)."
    )
    args = parser.parse_args()

    json_files = sorted(RESULTS_DIR.rglob("solution.json"))
    print(f"Found {len(json_files)} solution.json files under results/")

    failures: list[tuple[Path, str, str]] = []
    passed = 0

    def verify_one(sol: Path):
        problem_str = sol.parent.name
        r = verify_solution(str(sol), problem_str=problem_str)
        if r.valid:
            msg = r.message or "OK"
            return sol, problem_str, True, msg
        return sol, problem_str, False, r.message or "Invalid"

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(verify_one, s): s for s in json_files}
        for i, fut in enumerate(as_completed(futures), 1):
            sol, problem_str, valid, msg = fut.result()
            if valid:
                passed += 1
            else:
                failures.append((sol, problem_str, msg.strip()))
            if i % 5000 == 0 or i == len(json_files):
                print(f"[{i}/{len(json_files)}] passed={passed} failed={len(failures)}")

    print("\n=== SUMMARY ===")
    print(f"Total:  {len(json_files)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    if not failures:
        print("No invalid solutions found. Nothing to remove.")
        return

    print("\n=== FAILED SOLUTIONS ===")
    for sol, prob, reason in failures:
        print(f"- {sol}  problem={prob}  reason: {reason}")

    if args.dry_run:
        print("\n(Dry run: no files deleted.)")
        return

    # Confirm
    answer = input(f"\nDelete {len(failures)} failed solution.json (+ PNG)? [y/N]: ").strip()
    if answer.lower() not in ("y", "yes"):
        print("Aborted.")
        return

    removed = 0
    for sol, _, _ in failures:
        run_dir = sol.parent
        png = run_dir / "solution.png"
        if sol.exists():
            sol.unlink()
            removed += 1
        if png.exists():
            png.unlink()
            removed += 1
        try:
            if not any(run_dir.iterdir()):
                run_dir.rmdir()
        except OSError:
            pass

    print(f"\nRemoved {removed} files associated with {len(failures)} failed solutions.")


if __name__ == "__main__":
    main()
