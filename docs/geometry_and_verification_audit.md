# Geometry Engine, SAT Constraints, and Verification Audit Report

**Date:** August 27, 2026  
**Module Scope:** `src/shape_packing/geometry.py`, `src/shape_packing/solution_tools.py`, `src/shape_packing/packing_config.py`, `packer_rs/src/solver.rs`

---

## 1. Executive Summary

This audit evaluates the mathematical soundness, constraint formulations, and tolerance conventions across the Python and Rust geometry and verification engines. It confirms the correctness of existing convex shapes (`DOMINO`, `TAN`, regular $k$-gons), details the theoretical limitations of SAT on non-convex shapes (`L`, `EL`), audits the circle-approximation boundaries, and documents the resolution of a key normalization bug in `packing_config._normalize_key`.

---

## 2. Cross-Validation of Shape Geometries & SAT Math

### 2.1. `DOMINO` Geometry ($1 \times 2$ Rectangle)
In `src/shape_packing/geometry.py`, `DOMINO` is parameterized as:
- **Vertices:** `[[-1.0, -0.5], [1.0, -0.5], [1.0, 0.5], [-1.0, 0.5]]`
- **Dimensions:** Width $= 2.0$, Height $= 1.0$, Centered at origin $(0,0)$.
- **Edge Normals:** `[[0, -1], [1, 0], [0, 1], [-1, 0]]` with apothems `[0.5, 1.0, 0.5, 1.0]`.

This strictly adheres to Erich Friedman's $1 \times 2$ unit domino standard.

### 2.2. Regular $n$-gon Containers & Phase Offsets
For regular polygons with $n$ sides:
- **Vertices:** $v_i = \left(R \cos\left(\frac{2\pi i}{n}\right), R \sin\left(\frac{2\pi i}{n}\right)\right)$ for $i \in \{0, \dots, n-1\}$.
- **Outward Normals:** $n_i = \left(\cos\left(\frac{2\pi i}{n} + \frac{\pi}{n}\right), \sin\left(\frac{2\pi i}{n} + \frac{\pi}{n}\right)\right)$.
- **Apothem:** $a = R \cos\left(\frac{\pi}{n}\right)$.
- **Orientation:** For visual display matching Friedman's conventions (horizontal flat bottom edge), `get_container_rotation_offset()` provides exact visual phase alignment.

### 2.3. `TAN` (Tangram Right Isosceles Triangle)
- **Geometry Definition:**
  $$r = 1 - \frac{\sqrt{2}}{2} \approx 0.2928932188$$
  $$\text{Vertices: } (-r, -r), (1-r, -r), (-r, 1-r)$$
- **Properties:**
  - Leg lengths $= 1.0$, Hypotenuse $= \sqrt{2}$.
  - Origin $(0,0)$ is exactly the **incenter** of the right triangle.
  - Perpendicular distance from $(0,0)$ to all 3 edges is constant and equal to $r$.
- **Verification Against Benchmarks:**
  - `1_taninsqu`: 1 TAN in Square $\implies s = 1.0$.
  - `2_taninsqu`: 2 TANs in Square $\implies s = 1.0$ (two tans join to form a $1 \times 1$ square).
  - `1_4_in_tan`: 1 unit square in TAN $\implies s = 2.0$ (leg length of TAN container).
  - `1_cirintan`: 1 unit circle in TAN $\implies s = 2 + \sqrt{2} \approx 3.414214$.

---

## 3. The Non-Convex / Concave Shape Problem (`L`, `EL`, `TTT`)

### 3.1. Mathematical Conflict with Single-Polygon SAT
The **Separating Axis Theorem (SAT)** states that two closed compact sets $A, B \subset \mathbb{R}^2$ are disjoint if and only if there exists a separating axis $\vec{u}$ where their 1D projections do not overlap:
$$\Pi_{\vec{u}}(A) \cap \Pi_{\vec{u}}(B) = \emptyset$$
**This theorem holds strictly and exclusively for CONVEX sets.**

When SAT is applied directly to a concave polygon (such as an L-tromino with an internal reflex angle of $270^\circ$):
1. **Projection Equals Convex Hull:** The projection $\Pi_{\vec{u}}(L)$ along any axis $\vec{u}$ is identical to the projection of its convex hull $\text{Conv}(L)$.
2. **False Collision in Reflex Notches:** If shape $B$ is placed inside the concave notch/elbow of shape $A$ (which is valid in physical space), SAT projects the convex hull of $A$ over $B$ and reports a massive collision.
3. **Optimizer Infeasibility:** Continuous gradient descent and L-BFGS-B push interlocked shapes apart, rendering it impossible to discover optimal interlocking packings.
4. **Non-Convex Containers:** Inward boundary constraints cannot be expressed as a linear system $A\vec{x} \le \vec{b}$, because the interior of a concave container is a non-convex union, not a convex intersection.

```
  False-Positive SAT Collision with Concave Shapes:
  +-----+                 +-----+
  |  A  |                 |  A  |
  |     +-----+           |  ===+-----+   <--- Convex hull fills this notch!
  |           |    vs     |   B |  A  |        SAT treats piece B inside the notch
  +-----------+           +-----------+        as a full collision with piece A.
    (L-Shape)              (Interlocked)
```

### 3.2. Architecture Solution: Convex Decomposition (Compound Shapes)
To properly support `L` and other polyominoes:
- **Decomposition:** Represent each non-convex shape as a union of convex components:
  $$L = R_1 \cup R_2$$
  *(e.g., one $1 \times 2$ rectangle and one $1 \times 1$ square)*.
- **Pairwise Collision:** Compound shapes $A = \bigcup_{i} A_i$ and $B = \bigcup_{j} B_j$ overlap $\iff \exists (i, j)$ such that $A_i$ and $B_j$ overlap under SAT.
- **Convex Container Containment:** $A \subset C \iff \forall i, A_i \subset C$.

---

## 4. Circle Approximations & Correctness Fencing

### 4.1. Audit of Circle Implementations

| Subsystem | Formulation | Error Margin | Status |
| :--- | :--- | :--- | :--- |
| **Circle – Circle Collision** | Exact Euclidean center distance: $\|c_i - c_j\| \ge 2.0$ | **$0.0\%$ (Exact)** | ✅ Closed-Form |
| **Circle in Circle Container** | Center distance from origin: $\|c_i\| \le S - 1.0$ | **$0.0\%$ (Exact)** | ✅ Closed-Form |
| **Circle in Polygon Container** | Inset boundary half-space: $c_i \cdot \vec{n}_k \le S \cdot a_k - 1.0$ | **$0.0\%$ (Exact)** | ✅ Closed-Form |
| **Polygon in Circle Container** | Maximum vertex radius: $\max_{v \in P}\|v\| \le S$ | **$0.0\%$ (Exact)** | ✅ Closed-Form |
| **Fallback Generic Token** | 32-sided polygon approximation (`CIRCLE_SIDES = 32`) | **$\sim 0.48\%$ at facets** | ⚠️ Generic SAT only |

### 4.2. Verification Isolation
In `src/shape_packing/solution_tools.py`, the `_verify_container_bounds` and `_verify_overlap` routines explicitly branch on `is_inner_circle` and `is_container_circle`. **The 32-sided polygon fallback is never invoked during solution verification**, ensuring 0% approximation error and preventing false-positive verifications.

---

## 5. Bug Resolution: `_normalize_key()` Substring Clobbering

### 5.1. Root Cause Analysis
In `src/shape_packing/packing_config.py`, `_normalize_key()` previously used naive chained `.replace()` calls:
```python
# PREVIOUS BUGGY CODE:
s = str(p_str).strip().lower()
return (
    s.replace("pentagon", "5")
    .replace("hexagon", "6")
    .replace("triangle", "3")
    .replace("square", "4")
    .replace("octagon", "8")
    .replace("circle", "circle")
    .replace("cir", "circle")  # <-- BUG: "cir" is a substring of "circle"
)
```
- When input was `"1_CIRCLE_in_CIRCLE"`, the `.replace("cir", "circle")` step replaced the `"cir"` prefix of `"circle"`, turning it into `"1_circlecle_in_circlecle"`.
- When input was `"1_CIR_in_CIR"`, it normalized to `"1_circle_in_circle"`.
- Result: Silent cache misses in `_FRIEDMAN_BEST_CACHE` and `_HISTORY_STATS_CACHE`, causing valid benchmark lookups to return `None`.

### 5.2. Fixed Implementation
The function was refactored to use delimiter-aware, token-level dictionary replacement:
```python
def _normalize_key(p_str: str) -> str:
    """Normalize problem token for robust key matching across case and shape synonyms."""
    s = str(p_str).strip().lower()
    replacements = {
        "pentagon": "5",
        "hexagon": "6",
        "triangle": "3",
        "square": "4",
        "octagon": "8",
        "cir": "circle",
        "circ": "circle",
        "dom": "domino",
    }
    parts = re.split(r"(_|\s+)", s)
    norm_parts = [replacements.get(p, p) for p in parts]
    return "".join(norm_parts)
```
Unit tested and verified in `tests/test_packing_config.py`.

---

## 6. Tolerance Standards & Metric Conversions ($S \leftrightarrow s$)

### 6.1. Tolerances
- `VERIFY_SAT_TOLERANCE = 1e-5`: Margin for geometric SAT overlap and container penetration checks during verification.
- `VERIFY_METRIC_TOLERANCE = 1e-6`: Tolerance for validating calculated Friedman metric vs JSON `final_metric`.
- `GEOMETRY_SAT_TOLERANCE = 1e-12`: High-precision tolerance for low-level continuous optimizer gradients.

### 6.2. Solver Circumradius $S$ vs Friedman Metric $s$
- **Solver Representation:** Shapes are scaled with unit circumradius ($R=1.0$) or unit leg ($1.0$). The container has circumradius $S$.
- **Friedman Published Metric $s$:** Side length of regular container polygon (or radius for circular container).
- **Forward Mapping:**
  $$s = \text{compute\_friedman\_metric}(S, \text{inner}, \text{container}) = \frac{c\_metric(S)}{i\_scale}$$
- **Inverse Mapping (for `--target-s` funneling):**
  $$S = \text{inverse\_friedman\_metric}(s, \text{inner}, \text{container})$$
