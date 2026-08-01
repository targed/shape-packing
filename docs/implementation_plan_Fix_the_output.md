# Shape-Aware Friedman Metric Implementation Plan

## Problem Statement

Our current `final_metric = S × sin(π/nsc) / sin(π/nsi)` is the correct formula only when both
inner and container shapes are **regular polygons** with circumradius = 1 in our solver convention.
It produces wrong values whenever `TAN`, `DOMINO`, `CIRCLE`, or `L` appear as either inner or container shape.

Empirically verified cases:
- `5_TAN_in_4`: old metric = 1.088 → new metric = **1.885** (Friedman = 1.788). Old was a false negative; new shows we're slightly worse.
- `5_DOMINO_in_4`: old metric = 2.828 → new metric = **4.000** (Friedman = 3.768). Old was a false "NEW_BEST"; new correctly shows we're worse.
- `4_6_in_5`, `5_6_in_4`, `5_4_in_3`: old = new (unchanged — regular polygon problems are already correct).

---

## Mathematical Foundation

### Why the current formula works for regular polygons

Friedman defines "unit polygon" as **side = 1**. Our solver uses **circumradius = 1**.
For a regular n-gon: `side = 2 × circumradius × sin(π/n)`.
So our unit inner shape is `2sin(π/nsi)` times larger than Friedman's unit.

The container: Friedman's metric = **side length** of the container polygon.
Our container has circumradius S → Friedman side = `2S × sin(π/nsc)`.

To compare apples-to-apples, we need the Friedman-equivalent container size if inner shapes were unit:
```
s_friedman = container_side / inner_scale = 2S·sin(π/nsc) / (2·sin(π/nsi)) = S·sin(π/nsc)/sin(π/nsi)
```
That's exactly the current formula — correct for all regular-polygon combinations.

### Why it breaks for special shapes

| Shape | Our "unit" | Friedman "unit" | Scale factor |
|-------|-----------|-----------------|--------------|
| Regular n-gon | circumradius = 1, **side = 2sin(π/n)** | side = 1 | `2sin(π/n)` |
| Circle | radius = 1 | radius = 1 | **1** |
| TAN | leg = 1 | leg = 1 | **1** |
| DOMINO | short side = 1 | short side = 1 | **1** |
| L-tromino | short side = 1 | short side = 1 | **1** |

For special shapes our unit **already matches** Friedman's, so no inner scale correction is needed.

Container metric conversions (S → Friedman's metric):

| Container | Friedman metric | Formula |
|-----------|----------------|---------|
| Triangle (n=3) | side s | `s = 2S·sin(π/3) = S√3` |
| Square (n=4) | side s | `s = 2S·sin(π/4) = S√2` |
| Pentagon (n=5) | side s | `s = 2S·sin(π/5) ≈ 1.1756S` |
| Hexagon (n=6) | side s | `s = 2S·sin(π/6) = S` |
| Octagon (n=8) | side s | `s = 2S·sin(π/8) ≈ 0.7654S` |
| Circle (32-gon approx) | radius r | `r ≈ S` |
| TAN | leg | `leg = S` |
| DOMINO | short side | `short_side = S` |
| L | short side | `short_side = S` (needs verification once L is implemented) |

### Complete formula

```python
def compute_friedman_metric(S, inner_token, container_token):
    container_metric = container_side(S, container_token)   # Friedman's s or r
    inner_scale = inner_unit_scale(inner_token)             # how big OUR unit is vs Friedman's
    return container_metric / inner_scale

def container_side(S, token):
    if token in ("CIRCLE", "CIR"):
        return S                               # circle radius = circumradius of 32-gon
    if token in ("TAN",):
        return S                               # leg = S
    if token in ("DOMINO",):
        return S                               # short side = S
    if token in ("L",):
        return S                               # short side = S (pending L implementation)
    n = int(token)
    return 2 * S * math.sin(math.pi / n)      # regular polygon side

def inner_unit_scale(token):
    if token in ("CIRCLE", "CIR", "TAN", "DOMINO", "L"):
        return 1.0                             # our unit = Friedman's unit
    n = int(token)
    return 2 * math.sin(math.pi / n)          # our polygon side at circumradius=1
```

---

## Affected Files

### 1. `src/shape_packing/solution_tools.py`
Two locations:
- **`verify_solution`** (line ~220): `calc_metric = S * math.sin(...) / math.sin(...)` → replace with `compute_friedman_metric(S, inner, container)`
- **`load_solution`** positions-style path (~line 111): same formula → same fix

### 2. `packer_rs/src/main.rs`
- Line ~143: The `final_metric` computation (already fixed for CIRCLE, but not for TAN/DOMINO) → use shape-aware formula

### 3. `compare_results.py`
- `normalize_final_metric`: Already overrides circle metric with `S`. Same logic needed for TAN/DOMINO inner shapes.
- The function must **always recompute from S** for any solution involving special shapes, because old JSONs have stale `final_metric` values.

### 4. Existing solution JSON files (migration)
Old JSONs with special shapes store the **wrong** `final_metric`. Options:
- **Option A (recommended)**: `normalize_final_metric` always ignores stored `final_metric` and recomputes from `S` + shape tokens. This is already done for circles. Extend to TAN/DOMINO.
- Option B: Run a migration script to rewrite all affected JSONs.

Option A is safer — no data mutation, source of truth stays as `S`.

---

## What changes per problem class

| Problem class | Old formula | New formula | Change? |
|---|---|---|---|
| poly in poly (e.g. 5_6_in_4) | `S·sin(π/4)/sin(π/6)` | Same | ✅ No change |
| TAN in poly (e.g. 5_TAN_in_4) | `S·sin(π/4)/sin(π/3)` | `S·√2` | ⚠️ Changes |
| DOMINO in poly (e.g. 5_DOMINO_in_4) | `S·sin(π/4)/sin(π/4) = S` | `S·√2` | ⚠️ Changes |
| CIRCLE in poly (e.g. 5_CIR_in_4) | `S·sin(π/4)/sin(π/32)≈broken` | `S·√2` | ⚠️ Changes |
| poly in CIRCLE (e.g. 10_3_in_circle) | Already fixed to return S | `S / √3` for triangles | ⚠️ Changes |
| poly in TAN | `S·r/sin(π/n)` (broken) | `S / (2sin(π/n))` | ⚠️ Changes |
| poly in DOMINO | `S·0.5/sin(π/n)` (broken) | `S / (2sin(π/n))` | ⚠️ Changes |
| TAN in CIRCLE | Already fixed to S | `S / 1 = S` | ✅ Same |
| TAN in TAN | broken | `S / 1 = S` | ⚠️ Changes |

---

## Open Questions for Review

> [!IMPORTANT]
> **L-tromino**: The L shape is in packingVerification but not yet implemented in the solver. The plan treats it as `short_side = S`, but this needs verification once L geometry is implemented.

> [!IMPORTANT]  
> **Polygon-in-CIRCLE correction**: We currently return `S` for all circle containers. With the new formula, it should be `S / inner_unit_scale`. For hexagons-in-circle, inner_scale = 1.0 so it stays `S`. For triangles-in-circle, it becomes `S / √3`. This changes circle comparisons for non-hexagon inner shapes. **Is this the right time to make that change, or defer?**

> [!NOTE]
> **The `5_TAN_in_4` NEW_BEST claim** (and any similar spurious entries) will be corrected once the formula is fixed. The solver's actual packing quality hasn't changed — only the metric reported changes. With the correct formula, `5_TAN_in_4` will show as `worse_than_best_known` (+0.097), which is honest.

---

## Verification Plan

1. **Run 201 existing tests** — should still pass (no geometry changes)
2. **Check `4_6_in_5`, `5_6_in_4`, `5_4_in_3`** — metrics should be identical to current (regular-polygon problems must not change)
3. **Check `5_TAN_in_4`** — metric should be `1.885` (not `1.088`), compare against Friedman `1.788` → `worse_than_best_known`
4. **Check `5_DOMINO_in_4`** — metric should be `~4.000`, compare against Friedman `3.768` → `worse_than_best_known`
5. **Check `10_6_in_CIRCLE`** — should remain near `3.493` vs `3.482` (unchanged, hexagons scale = 1)
6. **Check `10_3_in_circle`** — should change from `3.067` to `3.067/√3 = 1.771` vs `1.385` (still worse but correctly comparable)

---

## Handling Past and Future Runs

The implementation correctly handles both legacy results and future runs without requiring data migration:

1. **Future Runs**: The core solver scripts (`polygon_packer.py` and `packer_rs/src/main.rs`) have been updated to use `compute_friedman_metric()`. Any new solutions generated will have the correct, shape-aware `final_metric` written directly into their `solution.json` files.
2. **Past Runs**: To avoid the need to rewrite thousands of historical `solution.json` files that contain incorrect `final_metric` calculations for special shapes, the `compare_results.py` script has been updated to dynamically ignore the stored metric. Instead, it re-calculates the metric from scratch using the raw `S` (circumradius) value from the JSON and the shape metadata.

This ensures all analysis tools are completely robust against historical data errors, while allowing new runs to produce natively correct metrics.
