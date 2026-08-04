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

In addition to regular polygons, the benchmark engine supports specialized geometric shapes:

### L-Tromino (`L`)
- Composed of 3 unit squares arranged in an "L" shape.
- Vertices: $(0,0), (2,0), (2,1), (1,1), (1,2), (0,2)$.
- Area $= 3.0$.

### Domino (`DOMINO`, `DOM`)
- Composed of a $2 \times 1$ rectangle.
- Vertices: $(0,0), (2,0), (2,1), (0,1)$.
- Area $= 2.0$.

### Tan (`TAN`)
- Isosceles right triangle with legs of length $1$ and hypotenuse $\sqrt{2}$.
- Vertices: $(0,0), (1,0), (0,1)$.
- Area $= 0.5$.

### Line Segment (`LINE`)
- Represented as an infinitely thin segment or narrow rectangle of length $1$.

### Ellipse (`ELLIPSE`, `EL`)
- Approximated via a stretched 32-sided polygon with major/minor axis ratio.

---

## 4. Separating Axis Theorem (SAT) Overlap Detection

To detect overlaps between two convex polygons $P_1$ and $P_2$ without false positives or numerical drift, the system utilizes the **Separating Axis Theorem (SAT)**.

### Theorem Statement
Two convex polygons $P_1$ and $P_2$ do NOT overlap if and only if there exists a line (axis) $L$ such that the orthogonal projections of $P_1$ and $P_2$ onto $L$ are completely disjoint.

### Candidate Axes
For 2D polygons, the candidate separating axes are strictly the outward normal vectors of the edges of $P_1$ and $P_2$:

$$N_{axes} = \{ \text{normals of } P_1 \} \cup \{ \text{normals of } P_2 \}$$

For each axis $n \in N_{axes}$:
1. Project all vertices of $P_1$ onto $n$: $I_1 = [\min_{v \in P_1} (v \cdot n), \max_{v \in P_1} (v \cdot n)]$
2. Project all vertices of $P_2$ onto $n$: $I_2 = [\min_{v \in P_2} (v \cdot n), \max_{v \in P_2} (v \cdot n)]$
3. Compute penetration depth: $\delta_n = \min(\max(I_1) - \min(I_2), \max(I_2) - \min(I_1))$
4. If $I_1 \cap I_2 = \emptyset$ (i.e. $\delta_n \le 0$), the polygons are **separated** (no collision).

If $\delta_n > 0$ across ALL axes $n$, the polygons overlap, and the minimal penetration depth $\min_n \delta_n$ defines the collision penalty depth.

---

## 5. Metric Scaling Mathematics ($s$ vs $S$)

A crucial distinction in the codebase is between the solver's internal container scale $S$ and Erich Friedman's official published metric $s$.

### Container Scale $S$
In the solver (`packer_rs` / `optimization.py`), $S$ represents the scale applied to the unit container polygon (where circumradius $= 1.0$).

### Friedman Official Metric $s$
Erich Friedman's website catalogs packing results using specific side-length or radius definitions for $s$:

```text
┌─────────────────────────┬────────────────────────────────────────────┐
│ Container Type          │ Official Friedman Metric s Formula        │
├─────────────────────────┼────────────────────────────────────────────┤
│ Regular n-gon (3,4,5,6) │ s = 2 * S * sin(pi / n)                    │
│                         │ (side length of the regular n-gon)         │
├─────────────────────────┼────────────────────────────────────────────┤
│ Circle                  │ s = S                                      │
│                         │ (radius of the bounding circle)            │
├─────────────────────────┼────────────────────────────────────────────┤
│ L-Tromino / Domino / Tan│ s = S                                      │
└─────────────────────────┴────────────────────────────────────────────┘
```

### Inner Shape Scaling Factor ($i_{scale}$)

For inner shapes with side count $n_{inner}$, the side-length ratio relative to unit side length is:

$$i_{scale} = \begin{cases} 2 \sin(\pi / n_{inner}) & \text{if regular polygon} \\ 1.0 & \text{if circle, L, domino, tan} \end{cases}$$

The complete converted metric $s$ computed by `compute_friedman_metric(S, inner_token, container_token)` is:

$$s = \frac{c_{metric}(S)}{i_{scale}}$$

---

## 6. Theoretical Area Lower Bounds

For $N$ inner shapes of area $A_{inner}$ packed into a container of area $A_{container}(s)$, physical non-overlap imposes a strict lower bound on $s$:

$$N \cdot A_{inner} \le A_{container}(s)$$

Any solution or log entry claiming a metric $s$ that violates this inequality is geometrically impossible and flagged as a corrupt metric by `is_physically_valid_score()`.
