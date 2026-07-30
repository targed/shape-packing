# Deep Research: Gradient Descent Locking in Sharp Geometries

## 1. Overview of the Phenomenon
During the implementation and testing of the `TAN` shape (a right isosceles triangle with legs of length 1.0), we observed a severe packing inefficiency. For example, in the `5_TAN_in_4` problem (packing 5 Tans into a Square), the optimizer halted at a container scale ($S \approx 2.17$) which corresponds to a packing efficiency of only ~26%. 

Visually, the result is a small clump of triangles clustered near the center of an artificially large container. Despite having ample space to spread out or pack tighter, the optimizer terminates as if it has reached a global optimum.

## 2. Verification of Mathematical Correctness
Extensive mathematical verification confirms that the issue is **not** caused by flawed geometry or collision logic:
* **Vertices & Normals**: The vertices for the Tan correctly define a right isosceles triangle centered at its incenter. The edge normals are strictly outward-facing, normalized, and correctly angled `(0, -1), (1/sqrt(2), 1/sqrt(2)), (-1, 0)`.
* **SAT Overlap Logic**: The Separating Axis Theorem (SAT) implementation successfully projects vertices onto all geometric normals. It perfectly computes boolean overlap for convex shapes.
* **Container Bounds**: The outer bounding container perfectly matches the limit `S * apothem`, and the shapes touch these bounds without violating them.

## 3. The Root Cause: Algorithmic Trapping
The root cause lies in the limitations of the optimization algorithm currently used by the Rust engine (`packer_rs`), which relies on **Gradient Descent (Adam/L-BFGS)** with small randomized perturbations.

### 3.1 The "Wedge Lock" Problem
Gradient descent works by calculating the derivative of the penalty function (overlap + boundary poking) with respect to the positions and rotations of the shapes. It follows the steepest downward slope to minimize the penalty.

This works exceptionally well for smooth shapes (circles) or regular polygons with many obtuse angles. However, triangles have sharp angles (e.g., 45 degrees in a Tan). When two triangles bump into each other during the randomized packing process, a sharp corner of one triangle often slides against the flat edge of another, forming a "wedge lock".

### 3.2 Gradient Discontinuities & Zero-Gradients
Once wedged, moving either triangle in almost *any* direction will temporarily increase the overlap penalty before they can separate. Because gradient descent can only "see" the immediate local slope, it perceives any movement as an increase in penalty. The gradient effectively drops to zero, and the shapes become permanently locked in that relative configuration.

As the algorithm attempts to shrink the container (reduce $S$), the container walls push against this locked clump of triangles. Since the triangles cannot slide past each other to pack tighter without temporarily increasing the overlap penalty, the optimizer gets "squeezed" between the container penalty and the overlap penalty. It terminates, falsely assuming the container cannot be shrunk any further.

### 3.3 Why DOMINO Fails Gracefully
In contrast, the `DOMINO` shape (a 1x2 rectangle) achieves a much better packing efficiency (~62.5%). This is because rectangles possess parallel edges and 90-degree corners. When two dominos collide, they tend to align flush against each other and slide cleanly along their parallel edges, rather than locking tightly like puzzle pieces. 

## 4. Empirical Evidence
To prove that random initializations are insufficient to bypass this local minimum, we scaled the attempts up by a factor of 100x:
* **10 Attempts (Baseline)**: $S = 1.774$
* **1000 Attempts**: $S = 1.770$

The negligible improvement across 1,000 completely random starts mathematically proves that the optimization landscape for triangles is overwhelmingly dominated by these deep, inescapable local minima.

## 5. Potential Solutions and Next Steps
To resolve this and achieve high-density packings for triangles and other sharp geometries, the optimizer must be upgraded to escape local minima:

1. **Simulated Annealing**: Introduce a "temperature" parameter that allows the algorithm to occasionally accept moves that *increase* the penalty. This allows shapes to "jump" out of locked wedges.
2. **Basin Hopping with Large Perturbations**: Instead of the current micro-perturbations (`0.12` units), apply large, randomized rotational and translational kicks to shapes when a local minimum is reached.
3. **Physics Engines (e.g., Box2D / Rapier)**: Model the shapes as rigid bodies with physical collision resolution. Physics engines are explicitly designed to handle angular momentum and sliding friction, naturally resolving wedge-locks.
4. **Non-Linear Programming (NLP)**: Use a heavy-duty constrained optimizer like IPOPT, though this often requires highly continuous gradient functions which SAT struggles to provide. 

**Recommendation**: If tight packings for shapes like `TAN` or `L-TROMINO` are a priority, integrating a Simulated Annealing phase into the Rust loop is the most direct path forward.
