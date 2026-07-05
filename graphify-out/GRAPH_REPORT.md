# Graph Report - src  (2026-07-04)

## Corpus Check
- 7 files · ~5,385 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 185 nodes · 275 edges · 16 communities (12 shown, 4 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 11 edges (avg confidence: 0.78)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Geometry & Verification|Geometry & Verification]]
- [[_COMMUNITY_Agent Loop|Agent Loop]]
- [[_COMMUNITY_Documentation & Overviews|Documentation & Overviews]]
- [[_COMMUNITY_Problem Parsing & Config|Problem Parsing & Config]]
- [[_COMMUNITY_Rust Packer Core|Rust Packer Core]]
- [[_COMMUNITY_Solution Rendering & Validation|Solution Rendering & Validation]]
- [[_COMMUNITY_Optimization Engine|Optimization Engine]]
- [[_COMMUNITY_Experiment Runner|Experiment Runner]]
- [[_COMMUNITY_Polygon Packer Helper|Polygon Packer Helper]]
- [[_COMMUNITY_Erich Friedman Scraper|Erich Friedman Scraper]]
- [[_COMMUNITY_Geo Config|Geo Config]]
- [[_COMMUNITY_Packing Config|Packing Config]]
- [[_COMMUNITY_Preparation Script|Preparation Script]]
- [[_COMMUNITY_Shape Packing Init|Shape Packing Init]]
- [[_COMMUNITY_Autoresearch Package|Autoresearch Package]]

## God Nodes (most connected - your core abstractions)
1. `ExperimentResult` - 11 edges
2. `choose_problem()` - 9 edges
3. `verify_solution()` - 9 edges
4. `run_attempt()` - 8 edges
5. `verify()` - 7 edges
6. `Autoresearch Packing System` - 7 edges
7. `make_loop_candidate()` - 7 edges
8. `regular_polygon_vertices()` - 7 edges
9. `bh_objective()` - 7 edges
10. `Experiment Loop Specification` - 6 edges

## Surprising Connections (you probably didn't know these)
- `Test packing visualization` --conceptually_related_to--> `Autoresearch Packing System`  [AMBIGUOUS]
  test.png → README.md
- `Autonomous Experiment Loop` --semantically_similar_to--> `Experiment Loop Specification`  [INFERRED] [semantically similar]
  README.md → program.md
- `Efficient Heuristic Design Goal` --semantically_similar_to--> `No-ML Pure Optimization Constraint`  [INFERRED] [semantically similar]
  ShapePackingSummary.md → README.md
- `polygon-packer Library Purpose` --semantically_similar_to--> `polygon_packer.py Core Role`  [INFERRED] [semantically similar]
  polygon-packer/README.md → README.md
- `5 triangles in square packing example` --conceptually_related_to--> `Minimize Container Objective`  [INFERRED]
  5_3_in_4.png → program.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Autoresearch Loop Components** — readme_autoresearchpacking, readme_cline_agent, readme_train_py_runner, readme_polygon_packer_core, readme_verify_solution [EXTRACTED 1.00]
- **Problem Selection Ecosystem** — programmd_problem_selection_rules, programmd_packing_reference, programmd_erich_friedman_reference, programmd_diversity_rules [EXTRACTED 1.00]

## Communities (16 total, 4 thin omitted)

### Community 0 - "Geometry & Verification"
Cohesion: 0.09
Nodes (37): Any, bh_objective(), _ensure_array(), _poking_penalty_nb(), polygon_normals(), project_polygon(), geometry.py  Single, deep module for all low-level geometry used in this packi, Core objective: penalty for container overflow + overlaps (SAT-style).     Mirr (+29 more)

### Community 1 - "Agent Loop"
Cohesion: 0.11
Nodes (32): append_result(), choose_problem(), current_best_scores(), ExperimentResult, extract_problem_family(), has_improved(), is_preferred_reference(), is_reference_blocked() (+24 more)

### Community 2 - "Documentation & Overviews"
Cohesion: 0.09
Nodes (23): 5 triangles in square packing example, Test packing visualization, Optimization API Design, polygon-packer Library Purpose, Diversity and Anti-Stuck Rules, Erich Friedman Packing Reference, Experiment Loop Specification, Minimize Container Objective (+15 more)

### Community 3 - "Problem Parsing & Config"
Cohesion: 0.14
Nodes (18): packing_config.py  Helper configuration for the packing autoresearch loop. Th, is_special_shape(), list_problem_families(), parse_problem(), Problem, problem_to_packer_args(), problems.py  ProblemModule: deep module for "what is a packing problem?"  Si, True if token corresponds to a special (non-regular-polygon) shape     requirin (+10 more)

### Community 4 - "Rust Packer Core"
Cohesion: 0.23
Nodes (15): AtomicBool, Instant, Option, Args, main(), minimize_gradient(), OptResult, penalty_and_gradient() (+7 more)

### Community 5 - "Solution Rendering & Validation"
Cohesion: 0.28
Nodes (11): load_solution(), main(), render(), get_normals_of_polygon(), load_best_value(), project_polygon(), regular_normals(), regular_vertices() (+3 more)

### Community 6 - "Optimization Engine"
Cohesion: 0.29
Nodes (10): OptConfig, PackingProblem, ndarray, optimization.py  Deep module for optimization + objective orchestration in thi, Run a single optimization attempt (with shrink + L-BFGS-B + basin-hopping)., Run many optimization attempts in parallel and return the best (S, values)., Describes a packing problem: N inner polygons (each with nsi sides)     inside, High-level knobs for optimization behavior. (+2 more)

### Community 7 - "Experiment Runner"
Cohesion: 0.43
Nodes (7): build_command(), ensure_problem_output_dir(), parse_problem(), Packing autoresearch experiment runner. Single purpose: run polygon_packer.py fo, run_experiment(), timestamp(), to_sides()

### Community 8 - "Polygon Packer Helper"
Cohesion: 0.60
Nodes (5): bh_function(), poking_penalty(), repetition(), rotate_vectors(), transform_polygon()

### Community 9 - "Erich Friedman Scraper"
Cohesion: 0.83
Nodes (3): extract_float(), main(), parse_html()

### Community 10 - "Geo Config"
Cohesion: 0.50
Nodes (3): GeoConfig, ndarray, Bundles geometry constants used by bh_objective.

## Ambiguous Edges - Review These
- `Autoresearch Packing System` → `Test packing visualization`  [AMBIGUOUS]
  test.png · relation: conceptually_related_to

## Knowledge Gaps
- **8 isolated node(s):** `autoresearch-packing`, `Cline as Experiment Agent`, `train.py Experiment Runner`, `Separating Axis Theorem (SAT) Verification`, `Erich Friedman Packing Reference` (+3 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Autoresearch Packing System` and `Test packing visualization`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `regular_polygon_vertices()` connect `Geometry & Verification` to `Optimization Engine`?**
  _High betweenness centrality (0.012) - this node is a cross-community bridge._
- **What connects `packing_config.py  Helper configuration for the packing autoresearch loop. The a`, `prepare.py: no longer used. This repo is now a packing-only autoresearch environ`, `autoresearch-packing` to the rest of the system?**
  _63 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Geometry & Verification` be split into smaller, more focused modules?**
  _Cohesion score 0.08771929824561403 - nodes in this community are weakly interconnected._
- **Should `Agent Loop` be split into smaller, more focused modules?**
  _Cohesion score 0.10606060606060606 - nodes in this community are weakly interconnected._
- **Should `Documentation & Overviews` be split into smaller, more focused modules?**
  _Cohesion score 0.09090909090909091 - nodes in this community are weakly interconnected._
- **Should `Problem Parsing & Config` be split into smaller, more focused modules?**
  _Cohesion score 0.1368421052631579 - nodes in this community are weakly interconnected._