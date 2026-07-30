I made scripts/analyze_mill_log.py that analyzes the run log in the results folder. There are some interesting results from that. One of the big things is that the distribution of problem attempts are not 
evenly or close to evenly distributed. There seem to be a few problems that it keeps trying over and over again/many times which make up most of the percentage of the problem attempts while the others got a few but not nearly as many. 
Could you use the systematic debugging skill to look into this.

Phase 1: Root cause investigation

From the analyze_mill_log.py report:

- 9184 total runs
- 211 unique problems
- 6 families, with massive skew:
    - 3_in_5: 3522 runs (38.3%)
    - 3_in_4: 2435 (26.5%)
    - 4_in_3: 2101 (22.9%)
    - 6_in_4: 806 (8.8%)
    - 3_in_circle: 164 (1.8%)
    - 3_in_3: 156 (1.7%)

- Top individual problems:
    - 18_4_in_3: 90 runs
    - 9_3_in_5: 88
    - 41_4_in_3: 87
    - 39_4_in_3: 86
    - many 4_in_3 problems around 85–86

Symptom:
- A handful of problems get most attempts while many others get almost none.
- Distribution is extremely lopsided, not close to uniform.

Hypothesis:
- This is not a random imbalance; it’s caused by how choose_problem and priority_queue.json interact.

Phase 2: Evidence gathering

1. Check priority_queue.json format vs scheduler expectations

- agent_loop.py choose_problem uses:

    - p0 = parse_problem(p_str)
    - parse_problem expects: "^(\\d+)(.+)(in)_(.+)$"
    - Example: "10_4_in_3"

2. Count how many queue problems match vs don’t match:

- Total problems in queue: 1703
- Match pattern (can be selected): 297
- Do not match (always ignored): 1406
- 82.6% are effectively invisible to the scheduler.

3. Inspect examples of ignored problems:

- 6_squinl
- 4_cirinl
- 7_squinl
- 13_cirinl
- etc.

These are compact names like:
- "squinl" = squares in L
- "cirinl" = circles in L
They are real Friedman-style problems but in short codes, not N_X_in_Y format.

Result:
- Most valid problems are excluded purely because their names don’t match the parser regex.
- The scheduler chooses only from 297 parseable problems.

4. Look at eligible families and their densities

Only 11 families are parseable:

- 3_in_5: 48 problems, mean density ~0.845
- 3_in_4: 46 problems, mean ~0.836
- 4_in_3: 41 problems, mean ~0.778
- 3_in_3: 28, ~0.881
- 3_in_circle: 26, ~0.754
- 6_in_4: 22, ~0.759
- 3_in_tan: 27, ~0.811
- 4_in_tan: 18, ~0.764
- tan_in_tan: 19, ~0.938
- tan_in_cir: 17, ~0.783
- L_in_L: 5, ~0.787

And choose_problem selects by:

- total_score = density + penalties
- Penalties include:
    - history-based penalties (stagnation, total_runs)
    - reference-based penalties (if near best_value: +5.0; if far: -1.0)
    - best_known / human-found bonuses

So:
- With only 297 candidates, a few families with:
    - Many problems
    - Low densities
    - Large gaps vs Friedman best_value
- Get repeatedly selected with high priority, driving 3_in_5, 3_in_4, 4_in_3 to thousands of runs.

5. Confirm with top-volume problems

Highest-volume problems:

- 18_4_in_3: 90 runs
- 9_3_in_5: 88
- 41_4_in_3: 87
- 39_4_in_3: 86
- 31_4_in_3: 86
- 24_4_in_3: 86
- etc.

All in families that:
- Are parseable (N_X_in_Y)
- Have many problems
- Are heavily penalized/buffed by the scheduler logic depending on distance to best_value.

Result:
- The same 3 families absorb almost all compute.
- Many other problems (including circle and special-shape families) either:
    - Are non-parseable → never selected
    - Are selected rarely due to density/penalty rules.

Phase 3: Root cause (concise)

Root cause:
- 1) Format mismatch:
    - Many queue problems use compact names (e.g. 6_squinl) instead of N_X_in_Y.
    - parse_problem in agent_loop.py ignores them → 82.6% of queue never considered.
- 2) Extreme concentration:
    - Only 297 parseable problems remain.
    - Those are dominated by a few families (3_in_5, 3_in_4, 4_in_3).
    - Density + reference-based scoring heavily favors them, so they are repeatedly re-selected.

Effect:
- A small set of problems gets thousands of attempts.
- Most others get very few.
- This is not random; it’s structural in the scheduler and naming format.

If you’d like, I can next:
- Propose minimal fixes so:
    - Compact names are handled (or normalized).
    - Distribution becomes more balanced (e.g. caps per family or per problem) without changing the core logic.

Phase 1: Make more problems actually selectable (biggest impact)

Problem:
- 82.6% of priority_queue.json problems are silently ignored because their names don’t match "^(\\d+)(.+)(in)_(.+)$".
- Examples: "6_squinl", "4_cirinl" → never chosen.

Goal:
- Normalize/parse these compact names so choose_problem can select them.

Steps:

1) Identify naming patterns

From the data we saw:

- "6_squinl":
    - inner_shape: "square"
    - container_shape: "L"
- "4_cirinl":
    - inner_shape: "circle"
    - container_shape: "L"

Pattern:
- N_shortcode, where shortcode = "<inner_prefix>in<container_prefix>"
    - "squinl" = "squ" + "in" + "l"
    - "cirinl" = "cir" + "in" + "l"

We can map:

- squ → 4 (square)
- cir → CIRCLE
- tri → 3
- pen → 5
- hex → 6
- oct → 8
- l   → L
- tan → TAN
- etc.

Action:
- In agent_loop.py (choose_problem), before parse_problem(p_str):
    - Add a helper: normalize_problem_name(p_str)
    - If:
    - not in N_X_in_Y format
    - but matches "^(\\d+)_(.+)in(.+)$"
    - then translate tokens:
        - left token (inner) → canonical token
        - right token (container) → canonical token
    - Return: N_canonicalInner_in_canonicalContainer
    - Fallback:
    - If unparseable: leave as-is, let parse_problem fail → ignored (current behavior).

This alone:
- Drastically increases selectable problems (likely from 297 → 1000+)
- Directly reduces concentration in the current 3 families.

Phase 2: Add fairness limits so no single problem or family dominates

Even with more problems, the scheduler’s density/penalty logic will still heavily favor some. We add soft caps.

Goal:
- Prevent runaway attempts on a few problems while still allowing real exploration.

Changes in agent_loop.py choose_problem:

2a) Per-problem run cap

- Idea:
    - If a problem has had many total_runs in history, add a large penalty so it rarely wins.
- Implementation:
    - After:
    - total_runs = sum(1 for r in history if r.problem == p_str)
    - penalty += total_runs * 0.01
    - Add a soft cap:
    - If total_runs > 60:
        - penalty += 5.0
    - If total_runs > 100:
        - penalty += 15.0
- Effect:
    - Problems like 18_4_in_3 (90 runs) become strongly deprioritized after 60 runs.
    - Still selectable if truly attractive, but not monopolizing.

2b) Per-family run cap

- Idea:
    - Don’t allow one family to consume almost all compute.
- Implementation:
    - For each candidate:
    - family = extract_problem_family(p_str)
    - family_runs = sum(1 for r in history if extract_problem_family(r.problem) == family)
    - If family_runs > 400:
        - penalty += 5.0
    - If family_runs > 800:
        - penalty += 15.0
- This directly limits families like 3_in_5, 3_in_4, 4_in_3 from swallowing thousands of runs.

Phase 3: Prefer problems with low or no attempts

Currently:
- We penalize problems by:
    - total_runs * 0.01
    - history overlap
- But not strongly enough vs density/best_value gap bonuses.

Goal:
- Bias the scheduler toward under-attempted problems.

Changes in choose_problem:

3a) Boost low-run problems

- For each candidate:
    - If total_runs == 0:
        - penalty -= 3.0   (strong bonus to be tried at least once)
    - If total_runs <= 5:
        - penalty -= 1.5

- Effect:
    - New problems get a real chance.
    - Prevents them from being drowned out by “popular” problems.

Phase 4: Reduce aggressive best_value-gap bonuses

Current:
- If rel_gap > 0.10:
    - penalty -= 1.0  (bonus for “under-achieved”)
- This:
    - Repeatedly pulls problems with large gaps back into selection.
    - Encourages many runs on a handful of “far from best” problems.

Goal:
- Dampen this so it doesn’t fully override fairness.

Change:
- Reduce:
    - From: penalty -= 1.0
    - To:   penalty -= 0.3

- And optionally:
    - Only apply this bonus if total_runs < 30 for that problem.

Phase 5: Optional: explicit diversity control

If after Phases 1–4 distribution is still too skewed, add a simple diversity rule.

Options:
- If last K experiments (e.g., 20–30) are all from same family:
    - Apply extra penalty to that family (e.g. +5.0).
- This forces the scheduler to rotate.

This is not needed at first; add only if still unbalanced.

Summary (concise)

- Phase 1: Normalize compact problem names → huge increase in selectable problems.
- Phase 2: Add per-problem and per-family soft caps → prevents monopolization.
- Phase 3: Boost low-run problems → spread attempts.
- Phase 4: Tone down best_value-gap bonuses → less pull on same problems.
- Phase 5 (if needed): Hard diversity rotation → ensures family-level balance.

If you’d like, I can:
- Turn this into a concrete patch set for agent_loop.py (exact code changes) in a next step, or
- Implement it directly and show the diff.

## Implementation Log

The proposed fixes were successfully implemented in `src/shape_packing/agent_loop.py`.

### What was done
1. **Problem Name Normalization**: Added a `normalize_problem_name` function that converts compact shortcodes (e.g., `6_squinl`, `4_cirinl`) into canonical formats (e.g., `6_4_in_L`, `4_CIRCLE_in_L`) before they are checked. This re-enables ~80% of the queued problems that were previously being ignored.
2. **Run Count Caching**: Replaced the O(N * M) loop to calculate history counts with a single pass through history at the start of `choose_problem`, pre-computing `problem_runs` and `family_runs` dictionaries.
3. **Configurable Soft Caps**: Added new keyword arguments to `choose_problem` to restrict monopolization by heavily run problems:
   - `problem_cap1` (default 60): Adds a +5.0 penalty.
   - `problem_cap2` (default 100): Adds a +15.0 penalty.
   - `family_cap1` (default 400): Adds a +5.0 penalty to the family.
   - `family_cap2` (default 800): Adds a +15.0 penalty to the family.
4. **Low-run Boost**: Problems with 0 attempts get a -3.0 penalty, and <= 5 attempts get a -1.5 penalty.
5. **Reduced Best-Value Pull**: The bonus for being far from `best_value` was reduced from -1.0 to -0.3, and is now only applied if the problem has been run fewer than 30 times.

### How to use it
These adjustments are now active by default. You can tune the distribution caps in `run_parallel_loop.py` or wherever `choose_problem()` is invoked by simply passing the optional arguments:
```python
choose_problem(history, problem_cap1=40, problem_cap2=80, family_cap1=200, family_cap2=500)
```