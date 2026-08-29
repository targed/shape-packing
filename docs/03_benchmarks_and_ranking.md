# Benchmarks & Priority Queue Ranking

This document details the **Erich Friedman Benchmark Dataset**, record classification standards, priority queue density formulas, candidate target selection policies, and closeness metrics.

---

## 1. Erich Friedman Benchmark Reference Dataset

The benchmark dataset represents the authoritative historical record of optimal shape packings cataloged by Dr. Erich Friedman (Stetson University).

### Directory Structure: `data/packingVerification/`
The verified benchmark reference data resides in `data/packingVerification/*.json`. Each JSON file contains an array of problem definitions for a specific shape family:

```json
[
  {
    "problem_family": "6_in_5",
    "N": 4,
    "inner_shape": "hexagon",
    "container_shape": "pentagon",
    "best_value": 3.01521,
    "status": "best_known",
    "source_note": "s = 3.01521+ Found by Bhavithran Ananthan in July 2026.",
    "our_problem": "4_6_in_5",
    "id": "6_in_5_4",
    "source_url": "https://erich-friedman.github.io/packing/hexinpen/index.html"
  }
]
```

### Record Classifications

1. **`trivial`**: Configurations where optimality is self-evident (e.g. $N=1$ or $N=2$ matching container symmetries).
2. **`proved_optimal`**: Packings backed by analytical/algebraic mathematical proof of global optimality (e.g. proved by Graham, Peikert, or Melissen).
3. **`best_known`**: High-density packings discovered via computational search heuristics that currently stand as the world record.

---

## 2. Priority Queue & Target Selection Policy

To systematically discover new records, the auto-researcher maintains a **Priority Queue** (`priority_queue.json`) that ranks unattempted or promising problems.

### Density Calculation Formula ($\rho$)

The primary ranking metric for a packing problem $(N, \text{inner}, \text{container})$ with reference score $s$ is its **Geometric Packing Density** ($\rho$):

$$\rho = \frac{N \cdot A_{inner}}{A_{container}(s)}$$

Where:
- $A_{inner}$ is the area of a single unit inner shape.
- $A_{container}(s)$ is the area of the container polygon of size metric $s$.

#### High-Density Principle
Problems with **lower packing density $\rho$** (large void space or loose packing) represent "promising targets" where a superior arrangement with smaller $s$ is most likely to exist.

### Target Selection Rules (`choose_problem()`)

When `agent_loop.choose_problem()` selects the next problem for solver execution:

1. **Avoid Stuck Problems**: Problems that have failed to improve after $K$ consecutive attempts are temporarily demoted.
2. **Prefer Unattempted Records**: Prioritizes `best_known` entries over `proved_optimal` (since proved optimal entries cannot be beaten).
3. **Density Rank**: Selects targets ranked highest by density gap in `priority_queue.json`.
4. **Radical Diversification**: Every 20–30 attempts, randomly selects a problem from a completely different shape family to prevent local trap stagnation.

---

## 3. Comparison Metrics & Closeness Calculation

When local solver runs finish, `build_site_data.py` compares our best metric $s_{our}$ against the reference metric $s_{ref}$:

```text
┌───────────────────────────┬──────────────────────────────────────────┐
│ Comparison Status         │ Mathematical Condition                   │
├───────────────────────────┼──────────────────────────────────────────┤
│ NEW_BEST                  │ s_our < s_ref - 1e-6 (Beat Record!)      │
│ matches_best_known        │ |s_our - s_ref| <= 1e-4                  │
│ worse_than_best_known     │ s_our > s_ref + 1e-4                     │
│ unattempted               │ No valid local solver run executed yet   │
└───────────────────────────┴──────────────────────────────────────────┘
```

### Closeness Percentage Formula

To measure how close our solver got to the world record:

$$\text{Closeness \%} = \min\left(100.0, \frac{s_{ref}}{s_{our}} \times 100.0\right)$$

- If $s_{our} = 3.021926$ and $s_{ref} = 3.01521$, Closeness $= \frac{3.01521}{3.021926} \times 100 = 99.78\%$.
- If $s_{our} < s_{ref}$ (NEW BEST), Closeness is capped at $\ge 100.0\%$.

---

## 4. Benchmark Summary Statistics

The overall state of the benchmark benchmark is summarized in `site_data.json`:

- **`total_families`**: Total normalized shape families (e.g. 80 families).
- **`total_problems`**: Total distinct $(N, \text{inner}, \text{container})$ configurations cataloged (e.g. 2,242 problems).
- **`proved_optimal`**: Count of proved optimal reference problems.
- **`best_known`**: Count of best known reference problems.
- **`trivial`**: Count of trivial reference problems.
- **`total_attempted`**: Total problems with at least one local solver run.
- **`total_new_bests`**: Total problems where our solver beat the published world record.
