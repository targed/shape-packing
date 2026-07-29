Shape Packing Project - Handoff Document

Created: 2026-07-27
Purpose: So any future agent (including a fresh session of me) can continue this project without relearning context.

1. Project overview

We are:
- Manually verifying Erich Friedman packing best-known values from https://erich-friedman.github.io/
  against our local packingVerification/*.json.
- Comparing our packing algorithm results (results/) to Friedman best values using compare_results.py,
  which writes compare_results.txt.
- Fixing inconsistencies in:
  - how our JSON encodes problem sets (schemas, ids)
  - how our comparison script uses metrics (S vs final_metric)

Key directories:
- erich-friedman.github.io/packing/
- packingVerification/
- results/
- compare_results.py
- compare_results.txt
- shapePackingSetNames.md

2. Packing verification workflow

We verify Friedman pages by reading HTML manually (no automated parsing) into packingVerification/<set>.json.

Each JSON is an array of entries, one per N (including ranges expanded).

Each entry has this exact schema (critical; past versions had wrong fields):

- problem_family: "X_in_Y" (e.g. "3_in_3", "6_in_4")
- N: integer (number of inner shapes)
- inner_shape: numeric or letter for inner (e.g. "3", "4", "L")
- container_shape: numeric or letter for container (e.g. "3", "6")
- best_value: float with ALL digits, no rounding (e.g. 6.10469)
- status: "trivial" if HTML says "Trivial." else "best_known"
- source_note: exact attribution text on the page (e.g. "Found by Maurizio Morandi in May 2008.")
- our_problem: "N_X_in_Y" (e.g. "10_6_in_4")
- id: "X_in_Y_N" (e.g. "6_in_4_10")
- source_url: URL of the Friedman page

Rules for best_value:
- Use only the decimal shown in HTML.
- Include all digits (e.g. 6.10469, 2.99837, 4.996, 6.42823).
- Never add "+" or extra precision.

Rules for status:
- "trivial" if HTML says "Trivial."
- "best_known" otherwise.

Rules for source_note:
- Use exactly the attribution text on the page.

Ranges:
- HTML often groups (e.g. "14.-16.") and we must expand to individual entries.

Workflow:
- From shapePackingSetNames.md, pick from bottom up.
- Use one subagent per problem set (to save context).
- After each:
  - Verify JSON (spot-check a few N and values).
  - Strikethrough set in shapePackingSetNames.md.
  - Move to next.

Current progress (from this session):
- Verified: squinhex (packingVerification/squinhex.json corrected; full N coverage 1-40).
- Others started/attempted: squcosqu (partially done, likely incomplete; review needed).
- Many sets still need verification; treat existing packingVerification JSON as "untrusted" until manually rechecked.

3. compare_results.py bug (important)

Problem:
- compare_results.txt previously showed obviously wrong NEW_BEST claims with huge margins, for example:
  - 10_6_in_4: Best S = 4.316875 vs Known = 6.104690 -> "NEW_BEST"
  - 13_6_in_3: Best S = 5.941165 vs Known = 10.288600 -> "NEW_BEST"
- This was wrong; our algorithm was not that good.

Root cause:
- Old compare_results.py was comparing:
  - our raw scale S
  - with Friedman normalized best_value
- But Friedman best_value matches our final_metric, not S.

What changed:
- Fixed compare_results.py to use normalize_final_metric:
  - Primary: use final_metric if present and finite.
  - Fallback: reconstruct from S and sides using sin(pi/n) scale.
  - For circle containers: treat as "incomparable" (different metric scale).
- Re-ran; compare_results.txt updated.
- New output:
  - No more giant false NEW_BEST.
  - Most entries: "worse_than_best_known" or very close.
  - Circle containers: marked "incomparable (circle)".

Examples (now correct):
- 10_6_in_4:
  - S = 4.3169, final_metric = 6.104982 vs Known 6.104690 -> slightly worse.
- 13_6_in_3:
  - final_metric = 10.290399 vs Known 10.2886 -> slightly worse.

Next-time checks:
- Any NEW_BEST in compare_results.txt should be manually inspected:
  - open that solution.json,
  - confirm final_metric and N,
  - compare with Friedman page.

4. S vs final_metric (key detail)

- S: packing scale from our algorithm (geometric scale factor).
- final_metric: normalized metric used for comparison to Friedman:
  - For polygons: final_metric = S * sin(pi / container_sides) / sin(pi / inner_sides)
  - For circles: currently on a different scale; do not trust NEW_BEST or diffs involving circle containers.
- Always use final_metric (via compare_results.py) for comparisons, never raw S.

5. Suggested skills for future agents

- subagent-driven-development:
  - Use when orchestrating many independent verification tasks (one per problem set).
- systematic-debugging:
  - Use when investigating weird metrics, unexpected NEW_BEST, or divergences in compare_results.py.
- verification-before-completion:
  - Use before declaring verification of a problem set as done.
- writing-plans:
  - Use when restructuring or re-planning the verification pipeline.

6. Remaining work (high level)

- Continue:
  - Manual verification of remaining problem sets (from shapePackingSetNames.md, bottom up).
  - Ensure all packingVerification JSON use the canonical schema.
- Investigate:
  - Any NEW_BEST entries in compare_results.txt.
  - Circle-related metrics (ensure they are correctly treated as incomparable).
- Align:
  - Any downstream tooling (train.py, PACKING_REFERENCE.json usage) with our corrected metrics.
