# Design Spec: Non-Convex L-Tromino (`L`) Shape Enablement via Convex Decomposition

**Date:** 2026-08-27  
**Status:** Approved  
**Topic:** Implementing the Non-Convex L-Tromino in Geometry, SAT Solvers (Python & Rust), Containment, Verification, and Priority Queue

---

## 1. Goal & Requirements

Enable full end-to-end support for the **L-Tromino (`L`)** (a non-convex polyomino of 3 unit squares, Area = 3.0) across the continuous optimization solver (Rust `packer_rs` and Python), geometry engine, containment bounds, solution verification, and autonomous agent problem selection.

---

## 2. Mathematical & Geometric Model

### 2.1. Coordinate Parameterization
A unit L-tromino is composed of three $1 \times 1$ squares arranged in an L-shape. Centered at the center of mass $(0, 0)$:

$$\text{Center of Mass Offset: } \Delta x = \frac{5}{6}, \quad \Delta y = \frac{5}{6}$$

The 6 outer vertices in counter-clockwise order:
$$V = \left[
\left(-\frac{5}{6}, -\frac{5}{6}\right),
\left(\frac{7}{6}, -\frac{5}{6}\right),
\left(\frac{7}{6}, \frac{1}{6}\right),
\left(\frac{1}{6}, \frac{1}{6}\right),
\left(\frac{1}{6}, \frac{7}{6}\right),
\left(-\frac{5}{6}, \frac{7}{6}\right)
\right]$$

### 2.2. 2-Rectangle Convex Decomposition
Because the L-shape has a reflex corner at $(1/6, 1/6)$ ($270^\circ$ interior angle), classical single-polygon SAT fails. The L-tromino is decomposed into **2 disjoint convex rectangles**:

1. **Rectangle A ($1 \times 2$ vertical domino):**
   - Vertices: $\left(-\frac{5}{6}, -\frac{5}{6}\right), \left(\frac{1}{6}, -\frac{5}{6}\right), \left(\frac{1}{6}, \frac{7}{6}\right), \left(-\frac{5}{6}, \frac{7}{6}\right)$
   - Normals: $(0, -1), (1, 0), (0, 1), (-1, 0)$
   - Center: $\left(-\frac{1}{3}, \frac{1}{6}\right)$

2. **Rectangle B ($1 \times 1$ unit square):**
   - Vertices: $\left(\frac{1}{6}, -\frac{5}{6}\right), \left(\frac{7}{6}, -\frac{5}{6}\right), \left(\frac{7}{6}, \frac{1}{6}\right), \left(\frac{1}{6}, \frac{1}{6}\right)$
   - Normals: $(0, -1), (1, 0), (0, 1), (-1, 0)$
   - Center: $\left(\frac{2}{3}, -\frac{1}{3}\right)$

### 2.3. Metric Scaling
- **Inner Scale:** $i\_scale = 1.0$ (unit square edges of length $1.0$).
- **Container Scale:** $c\_metric = S$ (scale $S$ expands the outer $2S \times 2S$ boundary).
- **Friedman Metric:** $s = \frac{c\_metric}{i\_scale}$.

---

## 3. Physics & Solver Algorithms

### 3.1. Pairwise Collision (Composite SAT)
For any two shapes $i$ and $j$:
- If both shapes are convex (single part), perform $1 \times 1$ standard SAT check.
- If shape $i$ or $j$ is compound (e.g. L-tromino with parts $R_A, R_B$):
  - Transform each sub-rectangle $R_{i, a}$ and $R_{j, b}$ using $(x_i, y_i, \theta_i)$ and $(x_j, y_j, \theta_j)$.
  - Evaluate SAT on each sub-rectangle pair $(R_{i, a}, R_{j, b})$.
  - If penetration depth $> 0$, accumulate squared penalty:
    $$P_{\text{overlap}} += d^2$$
  - Apply contact normal force gradient to both pieces.

### 3.2. Container Boundary & Complement Obstacle
1. **L as Inner Shape (`L_in_container`):**
   - Check container penetration for all 6 outer vertices of each L-tromino against the container edges / circle radius.
2. **L as Container (`inner_in_L`):**
   - Outer bounding box: $\left[-\frac{5}{6}S, \frac{7}{6}S\right] \times \left[-\frac{5}{6}S, \frac{7}{6}S\right]$.
   - Complement Cutout Square Obstacle:
     $$C_{\text{cutout}} = \left[\frac{1}{6}S, \frac{7}{6}S\right] \times \left[\frac{1}{6}S, \frac{7}{6}S\right]$$
   - Penalty is applied if inner shapes penetrate the outer boundary or collide with $C_{\text{cutout}}$.

---

## 4. Pipeline & Verifier Integration

1. **`geometry.py` & `packer_rs/src/solver.rs`:**
   - Define canonical `get_shape_geometry("L")` returning 6 outer vertices and 2 convex decomposition parts.
   - Update SAT collision kernels to evaluate composite parts.
2. **`solution_tools.py`:**
   - `build_polygons()` produces 6-vertex L-shapes.
   - `_verify_overlap()` verifies pairwise disjointness using composite SAT / Shapely intersection area ($< 10^{-6}$).
3. **`agent_loop.py`:**
   - Unblock `"L"` in `_is_shape_unsupported()`.
   - Add area calculations: Area $= 3.0$ for unit L, Area $= 3.0 S^2$ for container L.
   - Support priority queue ingestion of the 15 benchmark datasets (`Linhex`, `Linpen`, `squinl`, `dominL`, etc.).

---

## 5. Verification Plan

1. **Geometry Tests (`tests/test_geometry.py`):**
   - Verify area $= 3.0$, center of mass at origin $(0, 0)$, 6 vertices, and 2 convex sub-rectangles.
2. **Solver Tests (`tests/test_solver_interface.py`):**
   - Test optimizing `1_L_in_4` and `2_L_in_6` with positive valid score and zero overlaps.
3. **Verification Tests (`tests/test_solution_tools.py`):**
   - Verify non-convex L-tromino solutions pass `verify_solution()`.
4. **Full Regression Test:**
   - Run `python -m pytest tests/` confirming 100% test pass rate across all 309+ tests.
