# Solver Core Requirements

Scope:
geometry.py, optimization.py, packer_rs, and the Python backend polygon-packer.

1. Geometry

- WHEN a regular polygon is specified by its side count THEN geometry.py SHALL:
  - compute vertices using circumradius-based construction,
  - compute outward edge normals consistent with those vertices.

- WHEN a special shape token (TAN, DOMINO, L) is specified THEN:
  - the system SHALL use an explicitly defined set of vertices and edge normals,
  - it SHALL NOT fall back to regular-polygon formulas.

- WHEN a shape’s geometry is used both in Python and Rust THEN:
  - both implementations SHALL define the same vertices, normals, and apothem
  - within a tolerance of 1e-12.

2. Objective Function

- WHEN computing the objective THEN:
  - the solver SHALL include penalties for:
    - overlaps between inner shapes,
    - inner shape vertices leaving the container (poking penalty).
- WHEN overlap is detected between two convex inner shapes THEN:
  - it SHALL be detected via SAT-style projections using edge normals.

3. Tolerances

- WHEN verifying packings (for record consideration) THEN:
  - the solver SHALL use overlap tolerance ≤ 1e-15,
  - any packing with overlapping shapes beyond that tolerance SHALL be treated as invalid.

4. Optimizer Behavior

- WHEN a problem is being solved THEN:
  - the solver MAY use:
    - gradient-based optimizers (e.g., L-BFGS-B),
    - global-search strategies (e.g., basin-hopping),
    - multiple randomized restarts,
  - BUT it SHALL NOT alter geometry or tolerance rules to artificially improve results.

- IF local minima trap the solver THEN:
  - the system SHALL allow strategies like:
    - more attempts,
    - larger random perturbations,
    - swarm/multi-core exploration,
  - WITHOUT changing the underlying geometry.

5. Rust Solver (packer_rs)

- WHEN packer_rs is invoked THEN it SHALL:
  - implement the same geometric definitions and tolerances as the Python codebase,
  - produce solution.json with:
    - N, inner_token, container_token, S, final_metric, and shape positions.
- WHEN packer_rs detects an improvement THEN:
  - it SHALL record the metric consistently with the Python verification layer.
