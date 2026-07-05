# Handoff: shape-packing codebase restructuring (src layout)

Project: /Users/kaiserluke/Documents/Git/shape-packing

Status: In progress — layout is half-migrated; imports and entrypoints still need wiring.

## Context

- Goal: Clean up the "messy" root by introducing a proper src layout:
  - One main package: shape_packing
  - Root scripts as thin entrypoints (train.py, render_solution.py, verify_solution.py, prepare.py)
  - Tests in tests/
- This follows prior architectural discussion (see ARCH_DESIGNS.md and graphify-out/GRAPH_REPORT.md).

## What has been done (concrete)

1. Created:
   - src/shape_packing/
     - __init__.py
     - geometry.py (moved from root)
     - optimization.py (moved from root)
     - problems.py (moved from root)
     - packing_config.py (moved from root)
     - agent_loop.py (moved from root)
     - solution_tools.py (moved from root)

2. Updated imports inside src/shape_packing:
   - solution_tools.py: uses relative import from .geometry
   - problems.py: uses relative import from .packing_config
   - optimization.py: uses relative import from .geometry

3. Not yet done (needs next agent):
   - Update root scripts to import from shape_packing.*:
     - train.py (currently does: from problems import ...)
     - render_solution.py
     - verify_solution.py
     - prepare.py
   - Update any other root/scratch/scripts that import from:
     - geometry / optimization / problems / agent_loop / solution_tools directly.
   - Wire pyproject.toml to src layout:
     - Add [tool.setuptools.packages.find] with where = ["src"].
   - Add tests/:
     - At least one smoke test importing shape_packing.* modules.
   - Run smoke tests:
     - uv run python train.py (with a small test config) or import-level checks.
     - uv run python render_solution.py test.json test.png
     - uv run python verify_solution.py test.json
   - Clean up leftover __pycache__ and any broken imports.

## Current risks

- Imports are partially migrated:
  - The src/shape_packing/* files are ready as a package.
  - Root scripts (train.py, etc.) still import from the old flat modules (which no longer exist at root).
- Until root scripts and pyproject.toml are updated, `uv run train.py` etc. will fail.

## Key files and paths

- Package:
  - src/shape_packing/__init__.py
  - src/shape_packing/geometry.py
  - src/shape_packing/optimization.py
  - src/shape_packing/problems.py
  - src/shape_packing/packing_config.py
  - src/shape_packing/agent_loop.py
  - src/shape_packing/solution_tools.py
- Entrypoints (need update):
  - train.py
  - render_solution.py
  - verify_solution.py
  - prepare.py
- Config:
  - pyproject.toml (needs [tool.setuptools.packages.find] where = ["src"])
- Reference:
  - ARCH_DESIGNS.md
  - graphify-out/GRAPH_REPORT.md
  - program.md

## Next steps (for next agent)

- Continue from "Not yet done" above.
- First: make all root entrypoints import from shape_packing.*.
- Second: update pyproject.toml for src layout.
- Third: run smoke tests to confirm nothing is broken.
- Fourth (optional): add minimal tests/ module.

## Suggested skills

- codebase-design: for validating/refining the layout decisions.
- using-superpowers: for general power-user workflows.
- systematic-debugging: if smoke tests fail or import errors appear.