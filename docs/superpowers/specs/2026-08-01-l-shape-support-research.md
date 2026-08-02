# L-Shape (Non-Convex) Support Research & Implementation Strategy

## 1. The Mathematical Limitation of SAT
**Claim:** The Separating Axis Theorem (SAT) fundamentally cannot be applied directly to non-convex (concave) shapes like an L-tromino.
**Source:** *Real-Time Collision Detection* by Christer Ericson (CRC Press, 2005, Ch. 5.1). Verified live against primary documentation: [dyn4j SAT article](https://dyn4j.org/2010/01/sat/) (William Bittle, 2010), which explicitly states: *"SAT can only handle convex shapes."*
**Explanation:** SAT is built on the **Hyperplane Separation Theorem** (finite-dimensional form), which states that for any two disjoint *convex* sets, there exists a hyperplane that separates them. If a shape has a "dent" (concavity), a separating axis might not exist even if the shapes are entirely disjoint, causing the SAT algorithm to falsely report a collision.

## 2. The Industry Standard Solution: Convex Decomposition
**Claim:** To resolve collisions for concave shapes using SAT, the shape must be algorithmically or manually broken down into a union of smaller convex parts.
**Source:** Verified live: [dyn4j SAT article](https://dyn4j.org/2010/01/sat/) (primary implementation reference), which states verbatim: *"non-convex shapes can be represented by a combination of convex shapes (called a convex decomposition). So if we take the non-convex shape and perform a convex decomposition we can obtain two convex shapes. We can then test each convex shape to determine collision for the whole shape."*
**Explanation:** By performing **Convex Decomposition**, a complex concave shape is represented as an array of convex sub-polygons. The collision system then loops over these sub-components. Two rigid bodies $A$ and $B$ overlap if and only if any convex sub-component of $A$ overlaps with any convex sub-component of $B$.

## 3. Application to the L-Tromino
**Claim:** An L-Tromino can be optimally decomposed into exactly two convex sub-polygons (rectangles).
**Source:** Standard polyomino mathematical definition (Golomb, S. W. *Polyominoes*, 1994). 
**Explanation:** An L-tromino is composed of 3 unit squares. It can be decomposed cleanly into a $2 \times 1$ rectangle (domino) and a $1 \times 1$ square. These two components are rigidly attached to the same center of mass/rotation.

## 4. Architectural Impact on the `shape-packing` Codebase
**Claim:** The current `packer_rs/src/main.rs` SAT implementation hardcodes a 1-to-1 mapping between a physical shape state (`x, y, theta`) and a single array of `nsi` vertices. 
**Source:** Source code: `packer_rs/src/main.rs` (Lines 515-600, `penalty_and_gradient` function).
**Explanation:** Currently, the nested loops for SAT assume:
1. `polygon_array` has exactly `N * nsi` vertices.
2. Collision between shape $i$ and shape $j$ is a single pass checking `nsi` axes against `nsi` axes.

### Required Changes for Implementation:
To support L-shapes (and any future non-convex shapes), the solver must transition from a "Single-Polygon-Per-Object" model to a **"Multi-Polygon-Per-Object"** model:
1. **Data Structures & Signature:** The geometry function `get_shape_geometry` must return a `Vec` of polygons (where each polygon has its own vertices, vectors, and local offset from the shape's center of origin) instead of a flat array. The `penalty_and_gradient` function signature must change from `unit_polygon_vertices: &[(f64,f64)]` + `nsi: usize` to `unit_polygon_parts: &[Vec<(f64,f64)>]`.
2. **Kinematics:** The single `[x, y, theta]` state for the L-tromino must apply a rigid-body transformation to *both* internal rectangles simultaneously, using each part's local offset to compute the world-space vertices.
3. **Shape-vs-Shape Collision Loop:** The `penalty_and_gradient` function must add an inner loop to check `(Shape I, Sub-polygon A)` against `(Shape J, Sub-polygon B)`. The penalty gradients (derivatives of overlap distance with respect to $x, y, \theta$) from all colliding sub-components must be summed together to push the L-shape out of the collision as a single unified rigid body.
4. **Container Boundary Loop:** The current container boundary check (lines 555–580 in `main.rs`) also loops over `nsi` vertices of a single polygon. This must also be updated to iterate over *all* vertices of *all* sub-components of each shape, otherwise an L-shape's second rectangle will clip outside the container boundary undetected.
