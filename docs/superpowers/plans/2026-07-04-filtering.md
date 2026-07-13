> Archived: Historical design/planning docs.
> Not part of the current workflow; kept for context only.

# Problem Filtering System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a robust filtering system that allows you to narrow down the problem space by number of shapes, shape types, and shape sizes.

**Architecture:**
- Expand `cli.py suggest` to accept various filtering flags.
- Update `agent_loop.py -> choose_problem()` to apply these filters to the priority queue before selecting the lowest-density problem.
- Modify `auto_agent.py` to optionally pass these filters to the CLI (e.g., by reading a `filter.json` config file or accepting CLI args itself).

## Proposed Filters
We will add the following flags to `cli.py suggest`:

**Count Filters ($N$)**
- `--min-n <int>`: Minimum number of shapes (e.g. 10)
- `--max-n <int>`: Maximum number of shapes (e.g. 50)
- `--equal-n <int>`: Exact number of shapes

**Inner Shape Filters**
- `--include-inner <str>`: Comma-separated tokens (e.g. `3,4,CIRCLE`) to strictly include.
- `--exclude-inner <str>`: Comma-separated tokens to strictly exclude.
- `--min-inner-sides <int>`: Minimum sides of inner shape (e.g., `>=3`)
- `--max-inner-sides <int>`: Maximum sides of inner shape

**Container Shape Filters**
- `--include-container <str>`
- `--exclude-container <str>`
- `--min-container-sides <int>`
- `--max-container-sides <int>`

---

> [!IMPORTANT]
> **Open Question for User**: How would you prefer to supply these filters to the autonomous agent (`auto_agent.py`)?
> **Option A**: `auto_agent.py` reads a `config.json` (or `filter.json`) file on every loop iteration, so you can dynamically change the filters without restarting the agent.
> **Option B**: You pass the flags directly when launching `python auto_agent.py --max-n 20 --exclude-inner CIRCLE`.

---

### Task 1: Implement Filtering in `agent_loop.py`

- [ ] **Step 1: Update `choose_problem` signature and logic**
  Add a `filters: dict = None` parameter. Inside the loop, for each candidate in the priority queue, parse the problem string (`parse_problem(p)`) and check it against all provided filters. If it fails any filter, `continue` and skip it.

- [ ] **Step 2: Commit**
  `git commit -m "feat: add filtering logic to agent_loop"`

### Task 2: Expose Filters in `cli.py`

- [ ] **Step 1: Add argparse arguments**
  Add all the `--min-n`, `--max-n`, `--include-...` arguments to the `suggest` subparser in `cli.py`.
- [ ] **Step 2: Pass filters to `choose_problem`**
  Construct a dictionary of the provided arguments (ignoring `None` values) and pass it to `choose_problem`.
- [ ] **Step 3: Commit**
  `git commit -m "feat: expose filtering flags in cli.py"`

### Task 3: Integrate into `auto_agent.py`

- [ ] **Step 1: Wire up the chosen configuration method**
  (Pending your answer to the Open Question above).
- [ ] **Step 2: Commit**
  `git commit -m "feat: support filters in auto_agent"`
