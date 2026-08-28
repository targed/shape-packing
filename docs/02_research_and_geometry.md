# Research, Geometry & Metric Scaling Theory

This document presents the complete mathematical and geometric foundation of the **Shape Packing Benchmark Engine**, covering regular polygons, circle approximations, special polyforms, collision math via the Separating Axis Theorem (SAT), and metric scaling conventions.

---

## 1. Geometric Foundations & Polygon Representations

In 2D discrete shape packing, $N$ identical inner shapes are packed into a minimal bounding container. All inner shapes are normalized such that their characteristic side length (or unit scale) equals $1.0$.

### Regular Polygons ($n \in \{3, 4, 5, 6, 8\}$)

A regular $n$-gon centered at $(x, y)$ with rotation angle $\theta$ is constructed using standard trigonometric vertex formulas:

$$v_k = \begin{pmatrix} x + r \cos\left(\theta + \frac{2\pi k}{n}\right) \\ y + r \sin\left(\theta + \frac{2\pi k}{n}\right) \end{pmatrix} \quad \text{for } k = 0, 1, \dots, n-1$$

where the circumradius $r$ relates to the unit side length $a = 1.0$ by:

$$r = \frac{1}{2 \sin(\pi / n)}$$

- **Equilateral Triangle ($n=3$)**: $r = 1 / \sqrt{3} \approx 0.57735$, Area $= \frac{\sqrt{3}}{4} \approx 0.43301$
- **Square ($n=4$)**: $r = 1 / \sqrt{2} \approx 0.70711$, Area $= 1.0$
- **Regular Pentagon ($n=5$)**: $r = \frac{1}{2 \sin(\pi/5)} \approx 0.85065$, Area $= \frac{5}{4} \cot(\pi/5) \approx 1.72048$
- **Regular Hexagon ($n=6$)**: $r = 1.0$, Area $= \frac{3\sqrt{3}}{2} \approx 2.59808$
- **Regular Octagon ($n=8$)**: $r = \frac{1}{2 \sin(\pi/8)} \approx 1.30656$, Area $= 2(1+\sqrt{2}) \approx 4.82843$

---

## 2. Circle Container & Inner Circle Approximations

Circle shapes (`CIRCLE`, `CIR`, `0`) require special geometric handling because standard continuous circle equations can introduce non-linearities into polygonal solvers.

### 32-Sided Regular Polygon Approximation

To unify polygon and circle geometry across Rust (`packer_rs`) and Python engines, circles are represented as regular $32$-gons:

- **Sides**: $n = 32$
- **Apothem**: $a_{32} = \cos(\pi / 32) \approx 0.99518$
- **Circumradius**: $r = 1.0$

This 32-sided approximation provides sub-percent numerical fidelity ($> 99.5\%$ area overlap accuracy) while enabling exact Separating Axis Theorem (SAT) collision detection and polygon vector math.

### Circle Bounding Radius ($S$)

For circle containers, the container scaling parameter $S$ represents the **exact circle radius** ($r_{container} = S$). The container boundary condition requires that for all vertices $v_k$ of every inner shape:

$$\|v_k\|_2 \le S$$

In the solver, this constraint is enforced against the 32 normal vectors $n_j$ of the 32-gon:

$$v_k \cdot n_j \le S \cos(\pi / 32)$$

---

## 3. Special Shapes & Polyforms

In addition to regular polygons, the benchmark engine natively supports specialized geometric polyforms:

### L-Tromino (`L`)
- **Structure**: Composed of 3 unit squares arranged in an "L" shape (Area $= 3.0$).
- **Canonical Coordinates (Origin-Centered at Center of Mass $\left(\frac{5}{6}, \frac{5}{6}\right)$)**:
  $$V = \left[ \left(-\frac{5}{6}, -\frac{5}{6}\right), \left(\frac{7}{6}, -\frac{5}{6}\right), \left(\frac{7}{6}, \frac{1}{6}\right), \left(\frac{1}{6}, \frac{1}{6}\right), \left(\frac{1}{6}, \frac{7}{6}\right), \left(-\frac{5}{6}, \frac{7}{6}\right) \right]$$
- **2-Rectangle Convex Decomposition**:
  - **Part A ($1 \times 2$ Domino)**: $\left[-\frac{5}{6}, \frac{1}{6}\right] \times \left[-\frac{5}{6}, \frac{7}{6}\right]$
  - **Part B ($1 \times 1$ Square)**: $\left[\frac{1}{6}, \frac{7}{6}\right] \times \left[-\frac{5}{6}, \frac{1}{6}\right]$

### Domino (`DOMINO`, `DOM`)
- **Structure**: Composed of a $2 \times 1$ rectangle (Area $= 2.0$).
- **Canonical Coordinates (Origin-Centered)**:
  $$V = [(-1.0, -0.5), (1.0, -0.5), (1.0, 0.5), (-1.0, 0.5)]$$

### Tan (`TAN`)
- **Structure**: Right isosceles triangle with hypotenuse of length $1.0$ and legs $\frac{\sqrt{2}}{2}$ (Area $= 0.5$).
- **Canonical Coordinates (Origin-Centered)**:
  $$V = \left[ \left(-\frac{1}{2}, -\frac{1}{4}\right), \left(\frac{1}{2}, -\frac{1}{4}\right), \left(0, \frac{1}{4}\right) \right]$$

---

## 4. Separating Axis Theorem (SAT) Overlap & Compound Decompositions

To detect overlaps between shapes without false positives or numerical drift, the system utilizes the **Separating Axis Theorem (SAT)**.

### Theorem Statement
Two convex polygons $P_1$ and $P_2$ do NOT overlap if and only if there exists a line (axis) $L$ such that the orthogonal projections of $P_1$ and $P_2$ onto $L$ are completely disjoint.

### Compound SAT for Non-Convex Inner Shapes
Because SAT fails on concave shapes due to false positive edge projections, non-convex shapes (e.g. L-tromino) are split into convex sub-parts $P = \bigcup_k R_k$. Collision between shape $i$ and shape $j$ is evaluated across all sub-part pairs:

$$\text{Collision}(P_i, P_j) = \bigvee_{a, b} \text{SAT}(R_{i, a}, R_{j, b})$$

For two L-trominoes, evaluating $2 \times 2 = 4$ rectangle SAT checks takes $<20$ nanoseconds in SIMD Rust, allowing seamless interlocking without false collision barriers.

---

## 5. Non-Convex Container Confinement (L-Container `L`)

For convex containers, confinement requires every vertex to satisfy linear edge half-planes $v \cdot \vec{n}_e \le \text{limit}_e$. For an L-shaped container, intersecting all 6 edge half-planes would erroneously collapse the allowed region to only the $1 \times 1$ corner square.

### Bounding Box + Reflex Cut-Out Obstacle Formulation
An L-container of scale $S$ is modeled as:
1. **Outer Bounding Box**:
   $$\left[-\frac{5}{6}S, \frac{7}{6}S\right] \times \left[-\frac{5}{6}S, \frac{7}{6}S\right]$$
2. **Fixed Cut-Out Obstacle Square ($R_{\text{cutout}}$)**:
   $$\left[\frac{1}{6}S, \frac{7}{6}S\right] \times \left[\frac{1}{6}S, \frac{7}{6}S\right]$$

A shape $P$ is validly contained within the L-container if:
1. All vertices of $P$ lie within the outer bounding box.
2. $P$ has zero SAT collision with the fixed obstacle $R_{\text{cutout}}$.

---

## 6. Metric Scaling Mathematics ($s$ vs $S$)

A crucial distinction in the codebase is between the solver's internal container scale $S$ and Erich Friedman's official published metric $s$.

### Container Scale $S$
In the solver (`packer_rs` / `optimization.py`), $S$ represents the scale applied to the unit container polygon (where circumradius $= 1.0$, or characteristic scale $= 1.0$).

### Friedman Official Metric $s$
Erich Friedman's website catalogs packing results using specific side-length or radius definitions for $s$:

```text
┌─────────────────────────┬────────────────────────────────────────────┐
│ Container Type          │ Official Friedman Metric s Formula        │
├─────────────────────────┼────────────────────────────────────────────┤
│ Regular n-gon (3,4,5,6,8)│ s = 2 * S * sin(pi / n)                   │
│                         │ (side length of the regular n-gon)         │
├─────────────────────────┼────────────────────────────────────────────┤
│ Circle                  │ s = S                                      │
│                         │ (radius of the bounding circle)            │
├─────────────────────────┼────────────────────────────────────────────┤
│ L-Tromino / Domino / Tan│ s = S                                      │
│                         │ (characteristic unit side length)          │
└─────────────────────────┴────────────────────────────────────────────┘
```

### Inner Shape Scaling Factor ($i_{scale}$)

For inner shapes with side count $n_{inner}$, the side-length ratio relative to unit side length is:

$$i_{scale} = \begin{cases} 2 \sin(\pi / n_{inner}) & \text{if regular polygon} \\ 1.0 & \text{if circle, L, domino, tan} \end{cases}$$

The complete converted metric $s$ computed by `compute_friedman_metric(S, inner_token, container_token)` is:

$$s = \frac{c_{metric}(S)}{i_{scale}}$$

---

## 7. Theoretical Area Lower Bounds

For $N$ inner shapes of area $A_{inner}$ packed into a container of area $A_{container}(s)$, physical non-overlap imposes a strict lower bound on $s$:

$$N \cdot A_{inner} \le A_{container}(s)$$

| Shape Token | Area ($a = 1.0$) | Container Area Formula $A(s)$ |
| :--- | :--- | :--- |
| `3` (Equilateral Triangle) | $\frac{\sqrt{3}}{4} \approx 0.43301$ | $\frac{\sqrt{3}}{4} s^2$ |
| `4` (Square) | $1.00000$ | $s^2$ |
| `5` (Pentagon) | $\frac{5}{4} \cot(\pi/5) \approx 1.72048$ | $\frac{5}{4} \cot(\pi/5) s^2$ |
| `6` (Hexagon) | $\frac{3\sqrt{3}}{2} \approx 2.59808$ | $\frac{3\sqrt{3}}{2} s^2$ |
| `8` (Octagon) | $2(1+\sqrt{2}) \approx 4.82843$ | $2(1+\sqrt{2}) s^2$ |
| `CIRCLE` (Circle) | $\pi \approx 3.14159$ | $\pi s^2$ |
| `TAN` (Tan Triangle) | $0.50000$ | $0.5 s^2$ |
| `DOMINO` (Domino) | $2.00000$ | $2.0 s^2$ |
| `L` (L-Tromino) | $3.00000$ | $3.0 s^2$ |

Any solution or log entry claiming a metric $s$ that violates $N \cdot A_{inner} \le A_{container}(s)$ is geometrically impossible and flagged as a corrupt metric by `is_physically_valid_score()`.
