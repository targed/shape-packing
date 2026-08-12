# Attempt Scaling Analysis and Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce adaptive, per-problem attempt scaling so the loop allocates more attempts to hard/stuck problems and fewer to easy or solved ones, without wasting compute or missing opportunities.

**Architecture:** Extend analyze_difficulty() with a history-driven difficulty model: read past run counts, outcomes, and metric gaps from history, map them to a difficulty score, then compute attempts in a smooth range (e.g., 500–200k) instead of two fixed bins.

**Tech Stack:** Python (run_parallel_loop.py, src/shape_packing/), existing history in results.tsv.

## Global Constraints

- Keep changes backward compatible.
- No changes to core geometry or solver math.
- No new external dependencies.
- Prefer configuration and heuristics that are easy to read and tweak.
- Assume run_parallel_loop.py is the primary consumer of this logic.

---

## 1. Current behavior (analysis)

Current attempt allocation:

- Constants (packing_config.py):
  - LOOP_DEFAULT_ATTEMPTS = 5000
  - LOOP_HIGH_N_THRESHOLD = 10
  - LOOP_HIGH_N_ATTEMPTS = 50000
  - LOOP_STUCK_ATTEMPTS = 100000
  - Loop swarm counts (e.g., LOOP_STUCK_SWARM_COUNT, LOOP_HARD_SWARM_COUNT).

- Logic in run_parallel_loop.py (analyze_difficulty):
  - Extracts N from problem token.
  - If N >= LOOP_HIGH_N_THRESHOLD → LOOP_HIGH_N_ATTEMPTS.
  - If status == "stuck" → LOOP_STUCK_ATTEMPTS + swarm.
  - If status == "hard" → LOOP_HIGH_N_ATTEMPTS + swarm.
  - Otherwise → LOOP_DEFAULT_ATTEMPTS.

Key observations:

- Two main “real” states:
  - Easy/normal: 5k attempts.
  - High N / hard: 50k attempts.
- No per-problem adaptation:
  - A problem that failed 20 times at 5k still gets 5k on the next run.
  - A problem already solved and stable still gets the same attempts.
- No feedback from:
  - Frequency of “No valid packing found.”
  - Frequency of invalid or overlapping solutions.
  - Proximity of current best_score to Friedman best_score.
- No efficiency tuning:
  - No way to say: “This problem is easy, try 500–1000 first.”
  - No way to say: “This problem consistently fails at 50k, escalate to 100k+.”

This is exactly what you suspected: currently it is effectively two states (5k vs 50k) plus special stuck/hard flags. That’s insufficient for robust long-run scaling.

## 2. Problems we want to solve

- Avoid wasting time:
  - Reduce attempts on problems that:
    - Are already solved close to known best.
    - Repeatedly succeed with small effort.
- Invest more where needed:
  - Increase attempts when:
    - A problem repeatedly fails (“No valid packing found”) with many workers.
    - A problem has a large gap to known Friedman best.
    - A problem shows many invalid solutions or overlaps.
- Be per-problem:
  - Scaling must be specific to each (N, inner, container), not global.
- Keep it simple:
  - Deterministic, config-driven, easy to audit.

## 3. Design direction (recommended)

We will:

- Introduce a “difficulty” and “effort” model per problem.
- Use historical results (from results.tsv) plus a few heuristics.
- Replace the two-state logic with:
  - A base range (e.g., 500–200,000 attempts).
  - Adjustments up/down based on:
    - Problem size N.
    - Past failure rate.
    - Proximity to known best_score.
    - Whether it is currently marked “stuck”/“hard.”

### 3.1. Data sources

Use:

- history (results.tsv):
  - Count of previous runs for each problem.
  - Success vs failure:
    - success = valid solution logged.
    - failure = error, “No valid packing found”, or invalid geometry.
  - Score quality:
    - best_score achieved.
- packingVerification/*:
  - Pre-parsed JSON files (one per shape family, e.g. cirincir.json, domindom.json, hexintri.json).
  - Authoritative Friedman reference best scores for each (N, inner, container) family.
  - Gap = current_best - Friedman_best_score from these files.

Note:
- Never use PACKING_REFERENCE.tsv/json; that was from a bad HTML parser and is incorrect.
- Do not read erich-friedman.github.io HTML directly; use packingVerification JSON files as the single source of truth.

From this we compute:

- failure_ratio(problem) = failed_runs / total_runs
- improvement_count(problem) = number of times score improved
- gap_ratio(problem) = (current_best - Friedman_best) / Friedman_best (if known)

### 3.2. Difficulty score (0–1)

Define a simple difficulty_score per problem:

- Start at 0.3 (neutral).
- Adjust:
  - +0.15 if N >= 10
  - +0.25 if N >= 15
  - +0.15 * min(1, failure_ratio / 0.5)  (more failures → harder)
  - +0.15 * min(1, gap_ratio)           (far from known best → likely harder)
- Cap difficulty_score in [0, 1].

This is intentionally crude and tunable; the point is:
- Easy/solved problems: 0–0.3
- Medium: 0.3–0.6
- Hard/stuck: 0.6–1.0

### 3.3. Mapping difficulty → attempts

Define:

- LOOP_MIN_ATTEMPTS (e.g., 500)
- LOOP_DEFAULT_ATTEMPTS (e.g., 5000)
- LOOP_HIGH_N_ATTEMPTS (e.g., 50000)
- LOOP_MAX_ATTEMPTS (e.g., 200000)

Pseudo logic:

- If difficulty_score <= 0.2:
  - attempts between LOOP_MIN_ATTEMPTS and LOOP_DEFAULT_ATTEMPTS
- If 0.2 < difficulty_score <= 0.5:
  - between LOOP_DEFAULT_ATTEMPTS and LOOP_HIGH_N_ATTEMPTS
- If 0.5 < difficulty_score <= 0.8:
  - between LOOP_HIGH_N_ATTEMPTS and LOOP_MAX_ATTEMPTS
- If difficulty_score > 0.8 or status in ["stuck", "hard"]:
  - use LOOP_MAX_ATTEMPTS

Implementation:

- Keep it as:
  - A function in packing_config.py:
    - compute_adaptive_attempts(problem_state, history_stats)
  - Or a small module under src/shape_packing/attempt_scaling.py if it grows.

This replaces analyze_difficulty() with:

- Attempts = compute_adaptive_attempts(...)
- Swarm count = derive_swarm_count(...)
- Both guided by the same difficulty score.

### 3.4. Behavior for “already solved” problems

If:

- best_score is within ~1% of Friedman best_score, and
- last 5+ runs are all successes, and
- failure_ratio is low,

then:

- Reduce difficulty_score toward 0.1–0.2
- Cap attempts at something like 1000–2000
- Keep at least a baseline so we still occasionally search

This avoids burning 50k attempts on a problem we’re effectively done with.

## 4. Concrete implementation plan

This is where the “bite-sized” tasks live. Each is small, testable, and focused.

### Task 1: Add history-stats helper

**Files:**
- Modify: src/shape_packing/packing_config.py
- Test: tests/test_attempt_scaling.py

**Goal:** Provide a small function that summarizes per-problem history from results.tsv.

- [ ] **Step 1: Write test for history stats**

Create test: tests/test_attempt_scaling.py

- Test that get_problem_history_stats("2_domino_in_5") returns:
  - total_runs > 0
  - success_count + failure_count = total_runs
  - best_score matches the best known from history

- [ ] **Step 2: Implement get_problem_history_stats**

In src/shape_packing/packing_config.py:

- Read results.tsv once (cache if needed).
- Group by problem.
- For each problem, track:
  - total_runs
  - success_count
  - failure_count
  - best_score

- [ ] **Step 3: Run tests**

Run: pytest tests/test_attempt_scaling.py -v
Expected: PASS

- [ ] **Step 4: Commit**

git add src/shape_packing/packing_config.py tests/test_attempt_scaling.py
git commit -m "feat: add per-problem history stats helper"

### Task 2: Add difficulty scoring logic

**Files:**
- Modify: src/shape_packing/packing_config.py
- Test: tests/test_attempt_scaling.py

**Goal:** Introduce compute_problem_difficulty_score(problem, stats, friedman_best) and test it.

- [ ] **Step 1: Write tests**

Test edge cases:
- Easy problem: low N, low failures, close to Friedman → low score.
- Hard problem: high N, many failures, far from Friedman → high score.
- Unknown Friedman: score not penalized for gap.

- [ ] **Step 2: Implement compute_problem_difficulty_score**

Use the formula from Section 3.2.

- [ ] **Step 3: Run tests**

Run: pytest tests/test_attempt_scaling.py -v
Expected: PASS

- [ ] **Step 4: Commit**

git add src/shape_packing/packing_config.py tests/test_attempt_scaling.py
git commit -m "feat: add difficulty scoring for attempt scaling"

### Task 3: Add adaptive_attempts computation

**Files:**
- Modify: src/shape_packing/packing_config.py
- Test: tests/test_attempt_scaling.py

**Goal:** Implement compute_adaptive_attempts(problem_state, difficulty, history_stats).

- [ ] **Step 1: Write tests**

Test that:
- For difficulty in [0,1], attempts are in [LOOP_MIN_ATTEMPTS, LOOP_MAX_ATTEMPTS].
- Very easy → low attempts.
- Very hard/stuck → high attempts.

- [ ] **Step 2: Implement**

Add:
- LOOP_MIN_ATTEMPTS
- LOOP_MAX_ATTEMPTS
- compute_adaptive_attempts(difficulty, status)

Use ranges from Section 3.3.

- [ ] **Step 3: Run tests**

Run: pytest tests/test_attempt_scaling.py -v
Expected: PASS

- [ ] **Step 4: Commit**

git add src/shape_packing/packing_config.py tests/test_attempt_scaling.py
git commit -m "feat: add adaptive_attempts computation"

### Task 4: Integrate into run_parallel_loop.py

**Files:**
- Modify: run_parallel_loop.py
- No new tests required here; rely on existing behavior + config tests.

**Goal:** Replace current analyze_difficulty() logic with new adaptive scaling.

- [ ] **Step 1: Refactor analyze_difficulty**

In run_parallel_loop.py:

- Use:
  - stats = get_problem_history_stats(problem)
  - difficulty = compute_problem_difficulty_score(...)
  - attempts = compute_adaptive_attempts(difficulty, status, stats)

- Keep swarm_count logic but base it on difficulty too:
  - E.g., if difficulty > 0.7 or status in ["stuck", "hard"] → higher swarm.

- [ ] **Step 2: Smoke test**

Run run_parallel_loop.py for a short time (e.g., 1–2 minutes):

- Confirm:
  - No crashes.
  - Different problems get different attempts.
  - Hard/stuck problems get more attempts than easy.

- [ ] **Step 3: Commit**

git add run_parallel_loop.py
git commit -m "feat: integrate adaptive attempt scaling into parallel loop"

## 5. Tuning and next steps (after implementation)

Not part of initial implementation, but important:

- Monitor:
  - For 2–3 days after enabling:
    - Average attempts per problem.
    - Ratio of success/failure.
    - Whether any problem that used to succeed now fails (too low attempts).
- Tune:
  - Adjust difficulty weights.
  - Adjust attempt ranges in packing_config.py.

If you’d like, I can next:
- Draft example config values more concretely (specific numbers), or
- Turn this into sub-tasks for subagent-driven development and start implementing immediately.