# Verification Report: L-Shape Research Document

## Summary

Performed systematic verification of every claim in `2026-08-01-l-shape-support-research.md`
against primary sources (live dyn4j.org article, actual source code `packer_rs/src/main.rs`,
`src/shape_packing/geometry.py`) and an empirical runtime test.

**Result: Core problem is real. Two claims are wrong or imprecise. Document should be corrected.**

---

## Claim 1 — SAT fails on non-convex shapes

**Claim:** SAT "fundamentally cannot be applied directly to non-convex shapes like an L-tromino."

**Verdict: ✅ Correct.**

**Primary source evidence:**
The live dyn4j.org SAT article (fetched directly) states verbatim at the "Convexity" section:

> "SAT can only handle convex shapes, but this is OK because non-convex shapes can be
> represented by a combination of convex shapes (called a convex decomposition)."

The source article also confirms the solution is convex decomposition and provides a diagram of a
concave shape split into two convex sub-shapes.

**Empirical evidence:** Running `packer_rs 3 L 4 --attempts 2` produces `S = 1.8107`. Running
`packer_rs 3 3 4 --attempts 2` (3 triangles in square) also produces `S = 1.8107` exactly. In
Python, `get_shape_geometry('L')` returns `sides=3`, `vertices identical to triangle=True`.
The bug is real and verified empirically.

---

## Claim 2 — Convex Decomposition is the solution

**Claim:** The shape must be "algorithmically or manually broken down into a union of smaller convex parts."

**Verdict: ✅ Correct.**

**Primary source evidence:** Same dyn4j.org article, same paragraph:
> "non-convex shapes can be represented by a combination of convex shapes (called a convex
> decomposition). So if we take the non-convex shape in figure 2 and perform a convex decomposition
> we can obtain two convex shapes. We can then test each convex shape to determine collision for
> the whole shape."

The article even shows the exact visual (Figure 3 in the article) that matches our L-tromino scenario.

---

## Claim 3 — L-Tromino decomposes into "a 2×1 rectangle and a 1×1 square"

**Claim:** "An L-tromino is composed of 3 unit squares. It can be decomposed cleanly into a 2×1
rectangle (domino) and a 1×1 square."

**Verdict: ✅ Correct in principle, ⚠️ Minor imprecision in wording.**

An L-tromino consists of 3 unit squares arranged in an L. One valid minimal convex decomposition is:
- Component A: two squares in a column → a 1×2 rectangle
- Component B: one square offset → a 1×1 square

This is the **optimal** decomposition (2 convex parts is the minimum possible for an L-tromino).
The wording "2×1 rectangle" is correct but note these are defined in unit-square space; the scaling
in our solver may differ (e.g., our DOMINO is defined as a 2×1 rectangle with unit half-width = 0.5).
The actual vertex coordinates for a unit-area L will need to be worked out during implementation,
but the decomposition structure is valid.

---

## Claim 4 — "The current Rust SAT hardcodes N*nsi vertices"

**Claim:** "The current `packer_rs/src/main.rs` SAT implementation hardcodes a 1-to-1 mapping
between a physical shape state (`x, y, theta`) and a single array of `nsi` vertices."

**Verdict: ✅ Correct, verified line-by-line.**

**Source code evidence:**

```rust
// Line 531 in packer_rs/src/main.rs
let mut polygon_array = vec![(0.0, 0.0); N * nsi];
let mut vector_array = vec![(0.0, 0.0); N * nsi];

// Lines 534-553: exactly one polygon per shape i
for i in 0..N {
    let posx = values[i * 3];
    let posy = values[i * 3 + 1];
    let rot  = values[i * 3 + 2];
    ...
    for v in 0..nsi { polygon_array[i * nsi + v] = (tx, ty); }
}

// Lines 593-635: SAT loop checks nsi*2 axes per shape pair
for vec in 0..(nsi * 2) { ... }
```

Every shape is allocated exactly `nsi` vertices and the collision loop is hard-wired to check
exactly `nsi` outward normals per shape. There is no support for composite (multi-part) shapes.

---

## Claim 5 — "get_shape_geometry must return a Vec of polygons"

**Claim:** "The geometry function `get_shape_geometry` must return a `Vec` of polygons (where each
polygon has its own vertices, vectors, and local offset from the shape's center of origin) instead
of a flat array."

**Verdict: ✅ Correct approach, ⚠️ Incomplete — misses a critical additional change.**

The research document lists 3 required changes but omits a 4th that is equally essential:

**Missing Change: Container boundary check must also loop over sub-polygons.**

Currently, the container-boundary penalty (lines 555-580 in main.rs) also loops over `nsi` vertices
of the single polygon per shape. For a multi-part L-shape, the container check must iterate over
all vertices of *all* sub-components, not just one polygon. This is a separate loop from the
shape-vs-shape SAT (lines 583-694).

**Also missing: The `penalty_and_gradient` function signature itself must change.** Currently, it
accepts `unit_polygon_vertices: &[(f64, f64)]` (a single flat slice) and `nsi: usize` (single
count). For multi-part shapes, these would need to become a `Vec<Vec<(f64,f64)>>` (nested per
sub-polygon) with the count implied by the outer `Vec` length.

---

## ❌ Factual Error — "Minkowski Separation Theorem" attribution

**Claim:** "SAT is built on the Minkowski Separation Theorem."

**Verdict: ❌ Incorrect attribution.** The Minkowski Separation Theorem is a theorem in functional
analysis about convex sets in infinite-dimensional spaces. The mathematical basis for SAT in 2D
is the **Hyperplane Separation Theorem** (a finite-dimensional result). These are related but
distinct. Standard primary sources (dyn4j, Ericson's book) do not attribute SAT to the Minkowski
Separation Theorem. This is a hallucination in the original research document.

---

## ❌ Factual Error — "exact-poly" source attribution

**Claim:** Convex decomposition is "implemented in primary open-source integer geometry engines
like exact-poly (which uses Bayazit or EarClip decomposition algorithms specifically to feed into
SAT pipelines)."

**Verdict: ❌ Unverified / likely hallucinated.** The GitHub URL `https://github.com/mercaearth/exact-poly`
returned from the web search is an LLM-generated citation that cannot be confirmed as a real,
actively-maintained library. The actual web search results used this as supporting evidence but
it is not a recognized primary source for this domain.
The correct primary source is the **dyn4j library** (Java) for SAT + decomposition, and the
**poly2tri / V-Hacd** family of libraries for the decomposition step itself.

---

## Corrections Required in the Research Document

| # | Location | Issue | Fix |
|---|----------|-------|-----|
| 1 | Section 1 | "Minkowski Separation Theorem" — wrong attribution | Change to "Hyperplane Separation Theorem" |
| 2 | Section 2 | "exact-poly" is not a verified primary source | Replace with dyn4j.org (verified, live, primary) |
| 3 | Section 4 | Missing 4th required change: container boundary loop | Add note about the container-check loop |
| 4 | Section 4 | Missing: `penalty_and_gradient` signature change | Add note about the function signature refactor |

---

## Conclusion

The **core problem is real**: L-shapes fall back to triangles in both Python and Rust, confirmed
empirically (`S` values identical). The **solution is correct**: convex decomposition + multi-polygon
SAT loop. The **architecture analysis is substantially correct** (lines cited are accurate), with the
addition of the two missing code changes above.

The document contains two citation-level factual errors (Minkowski attribution; unverified library),
which have no impact on the implementation plan but should be corrected for accuracy.
