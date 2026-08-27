# Comprehensive Reference: Solver Scale ($S$) vs. Published Friedman Metric ($s$)

This document is the definitive reference for the relationship between the internal solver scale variable ($S$) and the published benchmark metric ($s$ / `final_metric`) across all shape families.

---

## 1. Executive Summary & Core Concept

In shape packing research and benchmarks (such as [Erich Friedman's Packing Center](https://erich-friedman.github.io/packing/)), the published metric $s$ measures the **characteristic side length** of the container when the packed inner pieces have unit characteristic size ($1.0$).

However, continuous numerical optimization algorithms (L-BFGS-B, Basin-hopping, Adam, and SAT physics engines) operate on **circumradii** and unit circles ($R = 1.0$) centered at the origin $(0, 0)$.

$$\boxed{\text{Solver Scale } S \quad \longleftrightarrow \quad \text{Published Benchmark Metric } s = \text{final\_metric}}$$

- **$S$ (Internal Scale):** The scaling multiplier applied to the container's unit geometry (where regular polygons have circumradius $R = 1.0$).
- **$s$ (Published Metric):** The real-world physical side length of the container divided by the unit side length of the inner shapes.

---

## 2. Shape Parameterization & Conversion Table

For a regular $n$-gon ($n \ge 3$) with circumradius $R$, the side length $s$ is:
$$s = 2 R \sin\left(\frac{\pi}{n}\right)$$

When $R = 1.0$, the conversion factor between circumradius and side length is $2\sin(\pi/n)$:

| Shape Token | Shape Name | Internal Geometry Basis ($R=1$) | Side Length Factor $k = 2\sin(\pi/n)$ | Do $S$ and $s$ Agree? |
| :--- | :--- | :--- | :--- | :--- |
| **`CIRCLE`** / `CIR` / `0` | Circle | Radius $R = 1.0$ | $1.0$ | **Yes** ($S = s$) |
| **`TAN`** | $45^\circ-45^\circ-90^\circ$ Triangle | Leg length $= 1.0$ | $1.0$ | **Yes** ($S = s$) |
| **`DOMINO`** | $1 \times 2$ Rectangle | Short side $= 1.0$ | $1.0$ | **Yes** ($S = s$) |
| **`6` (HEXAGON)** | Regular Hexagon | Circumradius $R = 1.0$ | $2\sin(30^\circ) = \mathbf{1.0}$ | **Yes** ($S = s$) |
| **`4` (SQUARE)** | Square | Circumradius $R = 1.0$ | $2\sin(45^\circ) = \sqrt{2} \approx \mathbf{1.41421356}$ | **No** ($s = \sqrt{2} \cdot S$) |
| **`3` (TRIANGLE)** | Equilateral Triangle | Circumradius $R = 1.0$ | $2\sin(60^\circ) = \sqrt{3} \approx \mathbf{1.73205081}$ | **No** ($s = \sqrt{3} \cdot S$) |
| **`5` (PENTAGON)** | Regular Pentagon | Circumradius $R = 1.0$ | $2\sin(36^\circ) \approx \mathbf{1.17557050}$ | **No** ($s \approx 1.1756 \cdot S$) |
| **`8` (OCTAGON)** | Regular Octagon | Circumradius $R = 1.0$ | $2\sin(22.5^\circ) \approx \mathbf{0.76536686}$ | **No** ($s \approx 0.7654 \cdot S$) |

---

## 3. General Mathematical Conversion Formulas

Given a packing problem with container shape $C$ and inner shape $I$:

### Forward Conversion ($S \longrightarrow s$):
$$s = \frac{c\_metric(S)}{i\_scale}$$

Where:
$$c\_metric(S) = \begin{cases} 
S & \text{if } C \in \{\text{CIRCLE}, \text{TAN}, \text{DOMINO}, \text{L}\} \\
2 \cdot S \cdot \sin(\pi / n_C) & \text{if } C \text{ is a regular } n_C\text{-gon}
\end{cases}$$

$$i\_scale = \begin{cases} 
1.0 & \text{if } I \in \{\text{CIRCLE}, \text{TAN}, \text{DOMINO}, \text{L}\} \\
2 \cdot \sin(\pi / n_I) & \text{if } I \text{ is a regular } n_I\text{-gon}
\end{cases}$$

### Inverse Conversion ($s \longrightarrow S$):
To configure the solver's target threshold from a published benchmark record:
$$S = s \cdot \frac{i\_scale}{c\_metric\_factor}$$

Where $c\_metric\_factor = c\_metric(1.0)$.

---

## 4. Step-by-Step Worked Examples

### Example 1: `6_TAN_in_8` (Tans in Octagon)
- **Container:** Regular Octagon ($n_C = 8$), $c\_metric(S) = 2 \cdot S \cdot \sin(\pi / 8) \approx 0.76536686 \cdot S$.
- **Inner:** Tangram right isosceles triangle ($I = \text{TAN}$), $i\_scale = 1.0$.
- **Solver Result:** $S = 1.2524265703608692$.
- **Calculation:**
  $$s = \frac{2 \cdot 1.2524265703608692 \cdot \sin(22.5^\circ)}{1.0} = \mathbf{0.9585657974618701}$$
- **Verification:** `solution.json` reports `"S": 1.2524265703608692` and `"final_metric": 0.9585657974618701`.

---

### Example 2: `1_4_in_3` (Square in Equilateral Triangle)
- **Container:** Triangle ($n_C = 3$), $c\_metric = 2 \cdot S \cdot \sin(\pi / 3) = \sqrt{3} \cdot S$.
- **Inner:** Square ($n_I = 4$), $i\_scale = 2 \cdot \sin(\pi / 4) = \sqrt{2}$.
- **Formula:**
  $$s = S \cdot \frac{\sqrt{3}}{\sqrt{2}} = S \cdot \sqrt{\frac{3}{2}} \approx 1.22474487 \cdot S$$

---

### Example 3: `1_CIRCLE_in_4` (Circle in Square)
- **Container:** Square ($n_C = 4$), $c\_metric = 2 \cdot S \cdot \sin(\pi / 4) = \sqrt{2} \cdot S$.
- **Inner:** Circle ($I = \text{CIRCLE}$, unit radius $= 1.0$), $i\_scale = 1.0$.
- **Formula:**
  $$s = \sqrt{2} \cdot S$$
- **Physical check:** A unit circle (radius $1.0$, diameter $2.0$) tightly packed in a square has side length $s = 2.0$.  
  In solver circumradius coordinates: $S = \frac{2.0}{\sqrt{2}} = \sqrt{2} \approx 1.41421356$.

---

## 5. Architectural Rationale & Why We Keep This Design

1. **Uniform SIMD & SAT Physics Kernels:**
   All regular polygon vertices are precomputed on the unit circle:
   $$v_k = \left(\cos\left(\frac{2\pi k}{n}\right), \sin\left(\frac{2\pi k}{n}\right)\right)$$
   This ensures:
   - Rotations around origin $(0, 0)$ are perfectly symmetric with zero torque bias.
   - Normals are normalized unit vectors with zero division overhead.
   - Poking penetration distance into circle containers reduces to simple hypotenuse checks ($\sqrt{x^2+y^2} \le S$).

2. **Decoupled Internal Math vs. Published Standard:**
   The solver is pure mathematics: it operates on scale multipliers. The presentation layer ([`solution_tools.py`](file:///c:/Users/ltkli/Documents/GitHub/shape-packing/src/shape_packing/solution_tools.py) and [`build_site_data.py`](file:///c:/Users/ltkli/Documents/GitHub/shape-packing/scripts/build_site_data.py)) handles mapping to Erich Friedman's published tables.

3. **Invasive Refactoring Avoidance:**
   Redefining all polygon coordinates to have side length $1.0$ internally would:
   - Break symmetry with circles (which are naturally radius-based).
   - Require re-tuning all gradient learning rates, Basin-hopping step sizes, and shrink factors.
   - Invalidate hundreds of existing solution files in `results/`.

---

## 6. Codebase Implementation Locations

| File | Function / Component | Responsibility |
| :--- | :--- | :--- |
| [`src/shape_packing/geometry.py`](file:///c:/Users/ltkli/Documents/GitHub/shape-packing/src/shape_packing/geometry.py) | `get_shape_geometry()` | Generates unit circumradius vertices and normals. |
| [`src/shape_packing/solution_tools.py`](file:///c:/Users/ltkli/Documents/GitHub/shape-packing/src/shape_packing/solution_tools.py) | `compute_friedman_metric()` | Converts $S \to s$ during verification and export. |
| [`src/shape_packing/solution_tools.py`](file:///c:/Users/ltkli/Documents/GitHub/shape-packing/src/shape_packing/solution_tools.py) | `inverse_friedman_metric()` | Converts $s \to S$ to set optimizer stopping thresholds. |
| [`packer_rs/src/solver.rs`](file:///c:/Users/ltkli/Documents/GitHub/shape-packing/packer_rs/src/solver.rs) | `get_shape_geometry()` & `solve()` | Implements the identical trigonometric conversion in Rust. |
| [`scripts/build_site_data.py`](file:///c:/Users/ltkli/Documents/GitHub/shape-packing/scripts/build_site_data.py) | `compute_friedman_metric()` | Builds static site data matching official competition records. |
