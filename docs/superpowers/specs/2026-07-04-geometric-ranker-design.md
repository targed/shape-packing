> Archived: Historical design/planning docs.
> Not part of the current workflow; kept for context only.

# Geometric Ranker & Priority Queue Design

## Goal
To intelligently guide the autonomous shape packing agent by ranking the problem space. Instead of random selection, the agent should prioritize problems that have the most "wasted space" (lowest packing density) and therefore the highest potential for immediate improvement.

## Approach
We will build a static mathematical ranker that calculates the geometric packing density of every known record in the database, and integrate it into the agent's problem selection loop with a stagnation penalty.

### 1. Geometric Ranker (`src/shape_packing/ranker.py`)
- We will write a script that parses `PACKING_REFERENCE.tsv`.
- For each problem, we use the formula for the area of a regular $n$-gon:
  `Area = 0.25 * n * s^2 * cot(pi / n)`
- Assuming inner polygons have side length `s=1`, the total area of the packed objects is `N * Area(inner)`.
- The container's area is calculated using the `best_value` from the reference file as its side length `s=S`.
- `Density = Total Inner Area / Container Area`.
- The script generates a sorted `priority_queue.json` listing problems from lowest density (most wasted space) to highest density.

### 2. Integration with Orchestrator (`src/shape_packing/agent_loop.py`)
- We modify `choose_problem()` to read from `priority_queue.json` instead of building a random list of candidates.
- **Stagnation Penalty**: To prevent the agent from getting permanently stuck on the #1 easiest problem, we factor in the experiment history (`results.tsv`). If a problem has been attempted multiple times recently without breaking the best score, we artificially penalize its density score when selecting the next problem.
- This creates a sliding window where the agent aggressively targets low-hanging fruit, but cycles through the top few problems to maintain diversity if it hits a wall.

## Global Constraints
- Must correctly handle Python's `math.tan` or `math.tan(pi/n)**-1` for cotangent.
- `priority_queue.json` must be reproducible by running `python -m src.shape_packing.ranker`.
