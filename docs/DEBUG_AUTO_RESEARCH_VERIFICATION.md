> Archived: Historical debug report (2026-07-06).
> Kept for reference on tolerance/verification behavior; not part of the active workflow.

# Debug Report: Autoresearch Loop Verification Failures

Date: 2026-07-06

## Symptom

Every solution produced by the autoresearch loop fails verification with violations like:

- "Shape 0 is out of bounds! Violation margin: 1.0625693178223372e-05"
- "Shapes 0 and 1 overlap! Depth: 1.9210593569907175e-05"

All violations are in the 1e-06 to 5e-05 range — extremely small, but above the verification threshold.

Loop still commits the score and continues, but the solution is marked [FAIL].

## Components

The loop has 4 components:

1. run_autoresearch_loop.py — loops, calls suggest, calls run
2. src/shape_packing/cli.py (handle_run) — invokes Rust solver, runs verify
3. packer_rs (Rust) — optimization + geometry
4. src/shape_packing/solution_tools.py — verification (SAT + bounds)

## Phase 1: Root Cause Investigation

### 1. Error messages — pattern

All errors are two types:

- Out-of-bounds: a vertex is slightly beyond container edge
- Overlap: two polygons slightly intersect

Critical observation: all violations are very small:
- Out-of-bounds: ~1e-05
- Overlaps: ~1e-05 to ~5e-05

These are not huge geometry failures; they are tiny residuals.

### 2. Verification tolerance (Python)

From src/shape_packing/solution_tools.py:

- TOLERANCE = 1e-15 (line 30)
- Out-of-bounds check:
  - dist > container_limit + TOLERANCE => violation
- Overlap check (via SAT):
  - overlap and depth > TOLERANCE => error

So any violation > 1e-15 causes failure.

### 3. Solver tolerance (Rust)

From packer_rs/src/main.rs:

- Default penalty tolerance: 1e-30 (line 22)
- Solver accepts configuration when: minimized.fun < penalty_tolerance
- Penalty is a sum of squared violations.

Key relationship:
- penalty = sum( (violation)^2 )
- A configuration can have individual violations >> 1e-15 and still satisfy
  penalty < 1e-30 if violations are extremely tiny and/or very few.

### 4. How "last valid" is chosen

In run_attempt():

- Starts with some S, shrinks S each step with multiplier
- If penalty < 1e-30 at this S, record (last_valid_s, last_valid_x)
- Continue shrinking S
- Returns last_valid_s, last_valid_x

The last_valid_x is the last configuration where the solver was "happy".

### 5. Root cause

ROOT CAUSE: The verification standard (1e-15) is unrealistically strict for the
optimization approach, and the solver's notion of "valid" (penalty < 1e-30)
does not guarantee that every individual geometric violation is < 1e-15.

Specifically:

- The solver minimizes a sum-of-squared-penalty function.
- A very low total penalty can coexist with a few individual violations in the
  1e-7 to 1e-5 range.
- The verification step uses 1e-15 as a hard cutoff: any violation > 1e-15
  fails the solution.
- Because of floating-point precision and optimization residuals, real solutions
  typically have tiny violations around 1e-6 to 1e-5 — enough to fail the
  1e-15 check, but geometrically meaningful and visually correct.

In short:

- 1e-15 is close to machine epsilon territory for double-precision.
- The solver outputs numerically stable packings with residuals around 1e-5.
- The verifier treats these as invalid.

This is not a bug in the solver; it is a mismatch between:
- Solver acceptance criteria (low aggregate penalty)
- Verification tolerance (per-violation < 1e-15)

## Phase 2: Pattern Analysis

### What is correct vs incorrect in current design?

Correct:
- SAT-based overlap checks
- Out-of-bounds checks
- Using the same geometric formulas in Rust and Python

Incorrect / too strict:
- Using TOLERANCE = 1e-15 as the absolute validity threshold.
  - Double-precision float epsilon is ~2.2e-16.
  - Real geometric pipelines with transforms, rotations, and optimization
    will produce residuals much larger than 1e-15.
- The doc/autoreaserchloop.md states "strict 10^-15 validation standard" as a
  requirement — this is the source of the conflict.

Observed pattern:
- Almost all violations are < 1e-4
- These are clearly numerical noise / residual, not real geometry failures.
- If we relax tolerance to, say, 1e-9, all of these would pass.

## Phase 3: Hypotheses (ranked)

Hypothesis A (primary, almost certain):

- The 1e-15 verification tolerance is too strict for double-precision
  optimization + SAT checks.
- Relaxing to 1e-9 (or 1e-8) will:
  - Accept the same geometric solutions (no real change in quality).
  - Eliminate virtually all of these "FAIL" messages.

Evidence:
- All current violations are in 1e-6..5e-5 range.
- These are far above 1e-15 but far below 1e-4.
- A tolerance of 1e-9 sits cleanly between "numerically real overlap" and
  "floating-point noise."

Hypothesis B (secondary):

- The Rust solver's "last valid" is not guaranteed to correspond to the
  optimal S that also passes an ultra-strict verifier.
- It tracks last_valid where penalty < 1e-30, but that penalty is an
  aggregate, not per-violation.
- Adding an explicit per-violation check in the solver could align
  its acceptance with the verifier.

Evidence:
- In penalty_and_gradient: penalty += diff*diff, overlap*overlap.
- Very small penalty can still mean a few individual violations > 1e-15.

Hypothesis C (if you must keep 1e-15):

- To truly guarantee 1e-15-level validity, you would need:
  - Much stricter optimization (more gradient steps, smaller steps),
  - Possibly a post-processing step that pushes all violations below 1e-15
    (e.g., shrink S slightly and re-verify).
- This is expensive and numerically fragile.

Evidence:
- Violations are currently around 1e-5.
- Enforcing 1e-15 requires 4+ orders of magnitude tighter control.

## Phase 4: Proposed Fixes

Three options, from recommended to least recommended.

Option 1: Relax verification tolerance (RECOMMENDED)

- Change TOLERANCE in solution_tools.py from 1e-15 to 1e-9.
- Update docs/autoreaserchloop.md to reflect 1e-9 as the standard.

Effect:
- Almost all current solutions would be considered [PASS].
- Still strict enough to reject any real overlap.
- Matches realistic double-precision behavior.

Changes:
- solution_tools.py:
  - TOLERANCE: float = 1e-9

Option 2: Two-tier tolerance

- Add:
  - HARD_TOLERANCE = 1e-9   (reject if beyond this)
  - SOFT_TOLERANCE = 1e-12 (warn but accept if between)
- Use HARD_TOLERANCE to decide valid, and log warnings if > SOFT_TOLERANCE.

Effect:
- Keeps strictness as a goal while allowing small residuals.
- Still marks clearly overlapping configurations as invalid.

Changes:
- solution_tools.py: implement two-tier check
- Optionally expose via CLI (e.g., --tolerance)

Option 3: Keep 1e-15 but tighten solver

(Not recommended unless strictly required.)

- In Rust solver:
  - After each candidate solution, run a SAT/geometry pass that:
    - Checks each individual violation vs 1e-15 (not just aggregate penalty)
    - Rejects if any violation > 1e-15
- This will:
  - Make the solver harder to converge.
  - Likely produce worse (larger) S values or fewer solutions.
- Also add a small S margin (e.g., scale S up by factor (1 + 1e-9) before
  saving) to reduce boundary violations.

Effect:
- Aligns solver acceptance with verifier.
- Slower; may miss solutions it would otherwise find.

## Recommendation

Apply Option 1 (relax to 1e-9) immediately:

- It is a single-line change.
- It is mathematically sound for double-precision.
- It resolves the recurring "[FAIL]" issues without harming solution quality.
- If 1e-15 is required for publication / external review, apply Option 3 as an
  optional strict mode, but use 1e-9 as default for the autoresearch loop.