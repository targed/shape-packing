# Geometric Ranker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mathematical ranker to prioritize problems with low packing density (wasted space) and update the orchestrator to use it.

**Architecture:** A new python script `ranker.py` to precompute densities into a JSON queue, and a modified `agent_loop.py` that selects problems from this queue while applying a stagnation penalty.

**Tech Stack:** Python 3.14 (math, json, csv)

## Global Constraints

- Must correctly handle Python's `math.tan` or `math.tan(pi/n)**-1` for cotangent.
- `priority_queue.json` must be reproducible by running `python -m src.shape_packing.ranker`.

---

### Task 1: Create `src/shape_packing/ranker.py`

**Files:**
- Create: `src/shape_packing/ranker.py`
- Test: Manual verification by running the script

**Interfaces:**
- Consumes: `PACKING_REFERENCE.tsv`
- Produces: `priority_queue.json` containing a list of `{"problem": str, "density": float}`

- [ ] **Step 1: Write `ranker.py` skeleton and area function**

```python
import csv
import json
import math
import os

def polygon_area(sides: int, side_length: float) -> float:
    # Area = (1/4) * n * s^2 * cot(pi/n)
    return 0.25 * sides * (side_length ** 2) / math.tan(math.pi / sides)
```

- [ ] **Step 2: Implement `generate_queue()`**

```python
def generate_queue(ref_path="PACKING_REFERENCE.tsv", out_path="priority_queue.json"):
    from .problems import parse_problem, shape_token_to_sides
    
    queue = []
    with open(ref_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            our_problem = (row.get("our_problem") or "").strip()
            if not our_problem:
                continue
                
            status = (row.get("status") or "").strip().lower()
            if status in ("trivial", "proved_optimal"):
                continue
                
            best_val_str = (row.get("best_value") or "").strip()
            if not best_val_str:
                continue
                
            try:
                best_value = float(best_val_str)
                p = parse_problem(our_problem)
                inner_sides = shape_token_to_sides(p.inner_token)
                container_sides = shape_token_to_sides(p.container_token)
                
                inner_area = p.N * polygon_area(inner_sides, 1.0)
                container_area = polygon_area(container_sides, best_value)
                density = inner_area / container_area
                
                queue.append({
                    "problem": our_problem,
                    "density": density
                })
            except Exception:
                continue
                
    queue.sort(key=lambda x: x["density"])
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)

if __name__ == "__main__":
    generate_queue()
```

- [ ] **Step 3: Run the script to generate the queue**

Run: `python -m src.shape_packing.ranker`
Expected: A `priority_queue.json` file is created with problems sorted by density.

- [ ] **Step 4: Commit**

```bash
git add src/shape_packing/ranker.py priority_queue.json
git commit -m "feat: add geometric ranker to prioritize problems"
```

---

### Task 2: Integrate Priority Queue into `agent_loop.py`

**Files:**
- Modify: `src/shape_packing/agent_loop.py`

**Interfaces:**
- Consumes: `priority_queue.json`, `results.tsv`
- Produces: Updated `choose_problem()` logic.

- [ ] **Step 1: Implement `load_priority_queue`**

```python
# Add at top of file
import json

def load_priority_queue(path: str = "priority_queue.json") -> List[Dict[str, float]]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []
```

- [ ] **Step 2: Update `choose_problem()`**

Replace the existing `choose_problem()` function with this priority-driven one:

```python
def choose_problem(
    history: List[ExperimentResult],
    queue_path: str = "priority_queue.json",
    prefer_different: bool = False,
) -> str:
    queue = load_priority_queue(queue_path)
    if not queue:
        # Fallback if queue missing
        return "8_3_in_5"
        
    recent = recent_problems(history, last=10)
    
    # Calculate stagnation: number of times a problem appears in the last 10 attempts
    # If it has been run a lot recently and hasn't improved, we heavily penalize it.
    best = current_best_scores(history)
    
    scored_candidates = []
    
    for item in queue:
        p = item["problem"]
        base_density = item["density"]
        
        # Penalize if it's very recent
        stagnation = sum(1 for r in recent if r == p)
        
        # We can also check if we've already beaten the reference best_value!
        # If we have a very good score, our *actual* density might be even better.
        # For simplicity, we just add a penalty of +0.05 per recent attempt.
        penalty = stagnation * 0.05
        
        scored_candidates.append((p, base_density + penalty))
        
    scored_candidates.sort(key=lambda x: x[1])
    return scored_candidates[0][0]
```

- [ ] **Step 3: Test `cli.py suggest`**

Run: `python -m src.shape_packing.cli suggest`
Expected: It should return the problem with the lowest density (plus penalties).

- [ ] **Step 4: Commit**

```bash
git add src/shape_packing/agent_loop.py
git commit -m "feat: use geometric ranker queue in agent_loop"
```
