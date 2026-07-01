# Graph Report - /Users/kaiserluke/Documents/Git/shape-packing  (2026-07-01)

## Corpus Check
- Large corpus: 2969 files · ~1,610,182 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder.

## Summary
- 76 nodes · 101 edges · 11 communities (8 shown, 3 thin omitted)
- Extraction: 89% EXTRACTED · 10% INFERRED · 1% AMBIGUOUS · INFERRED: 10 edges (avg confidence: 0.81)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]

## God Nodes (most connected - your core abstractions)
1. `run_attempt()` - 8 edges
2. `verify()` - 7 edges
3. `Autoresearch Packing System` - 7 edges
4. `Experiment Loop Specification` - 6 edges
5. `main()` - 5 edges
6. `bh_function()` - 5 edges
7. `minimize_gradient()` - 4 edges
8. `render()` - 4 edges
9. `build_command()` - 4 edges
10. `Args` - 3 edges

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

## Communities (11 total, 3 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.23
Nodes (15): AtomicBool, Instant, Option, Args, main(), minimize_gradient(), OptResult, penalty_and_gradient() (+7 more)

### Community 1 - "Community 1"
Cohesion: 0.28
Nodes (11): load_solution(), main(), render(), get_normals_of_polygon(), load_best_value(), project_polygon(), regular_normals(), regular_vertices() (+3 more)

### Community 2 - "Community 2"
Cohesion: 0.17
Nodes (12): Test packing visualization, Optimization API Design, polygon-packer Library Purpose, Autonomous Experiment Loop, Autoresearch Packing System, Cline as Experiment Agent, No-ML Pure Optimization Constraint, polygon_packer.py Core Role (+4 more)

### Community 3 - "Community 3"
Cohesion: 0.20
Nodes (11): 5 triangles in square packing example, Diversity and Anti-Stuck Rules, Erich Friedman Packing Reference, Experiment Loop Specification, Minimize Container Objective, Problem Naming Convention, PACKING_REFERENCE.tsv Knowledge Base, Reference-Aware Problem Selection Rules (+3 more)

### Community 4 - "Community 4"
Cohesion: 0.43
Nodes (7): build_command(), ensure_problem_output_dir(), parse_problem(), Packing autoresearch experiment runner. Single purpose: run polygon_packer.py fo, run_experiment(), timestamp(), to_sides()

### Community 5 - "Community 5"
Cohesion: 0.60
Nodes (5): bh_function(), poking_penalty(), repetition(), rotate_vectors(), transform_polygon()

### Community 6 - "Community 6"
Cohesion: 0.83
Nodes (3): extract_float(), main(), parse_html()

## Ambiguous Edges - Review These
- `Autoresearch Packing System` → `Test packing visualization`  [AMBIGUOUS]
  test.png · relation: conceptually_related_to

## Knowledge Gaps
- **8 isolated node(s):** `autoresearch-packing`, `Cline as Experiment Agent`, `train.py Experiment Runner`, `Separating Axis Theorem (SAT) Verification`, `Erich Friedman Packing Reference` (+3 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Autoresearch Packing System` and `Test packing visualization`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `Experiment Loop Specification` connect `Community 3` to `Community 2`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Why does `Autonomous Experiment Loop` connect `Community 2` to `Community 3`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **What connects `packing_config.py  Helper configuration for the packing autoresearch loop. The a`, `prepare.py: no longer used. This repo is now a packing-only autoresearch environ`, `autoresearch-packing` to the rest of the system?**
  _14 weakly-connected nodes found - possible documentation gaps or missing edges._