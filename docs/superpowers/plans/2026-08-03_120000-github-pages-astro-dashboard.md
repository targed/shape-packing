# Shape Packing GitHub Pages (Astro) Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build an internal-facing but public GitHub Pages site for shape packing that:
- Documents the system (overview, architecture, how-to).
- Acts as a semi-live dashboard of best packings from PACKING_REFERENCE.
- Provides simple visualizations (B-level) of packings.
- Is generated from repo data and docs via a repeatable GitHub Actions workflow.

**Architecture:** Astro-based static site:
- Content as MDX.
- Data-driven pages generated at build time from:
  - PACKING_REFERENCE.json
  - solution JSONs (best packings)
  - docs/requirements/60-problem-families/*.md
- GitHub Actions builds and deploys to GitHub Pages.

**Tech Stack:**
- Astro (with MDX integration)
- Tailwind CSS (for layout)
- A small client-side canvas/SVG visualization for packings
- GitHub Actions (build + deploy)
- Python or Node script (build-time) to transform PACKING_REFERENCE and solution data

---

### Task 1: Scaffold Astro site in site/

Objective: Create the Astro project that will become the GitHub Pages dashboard.

Files:
- Create: site/package.json (via Astro create)
- Create: site/astro.config.mjs
- Create: site/tsconfig.json
- Create: site/src/pages/index.astro

Steps:
- Run: `cd site && npm create astro@latest .`
- Use:
  - “Minimal” starter
  - Enable TypeScript
  - Enable MDX
- Verify:
  - `cd site && npm run dev`
  - Open local URL; confirm base page loads.
- Commit:
  - `git add site/`
  - `git commit -m "feat: add Astro site scaffold for GitHub Pages dashboard"`

---

### Task 2: Add basic project layout and navigation

Objective: Define the site structure and navigation.

Files:
- Modify: site/src/pages/index.astro
- Create: site/src/layouts/BaseLayout.astro
- Create: site/src/pages/about.astro
- Create: site/src/pages/docs.astro
- Create: site/src/pages/results.astro

Steps:
- Add nav with links: Home | Docs | Results | About.
- index.astro: short intro:
  - “Shape Packing Auto-Researcher”
  - Purpose: internal debugging, visualization, and documentation hub.
  - No external citation recommended.
- docs.astro: placeholder for architecture + how-to.
- results.astro: placeholder for dashboard (tables + visuals).
- Verify:
  - Run dev; check all links render without errors.
- Commit:
  - `git commit -m "feat: add basic Astro layout and navigation"`

---

### Task 3: Integrate MDX content for docs

Objective: Add MDX-based documentation pages (architecture, how-to, etc.).

Files:
- Create: site/src/content/docs/overview.mdx
- Create: site/src/content/docs/architecture.mdx
- Create: site/src/content/docs/how-to-run.mdx
- Create: site/src/content/docs/problem-families.mdx
- Create: site/src/content/docs/methodology.mdx
- Create: site/src/content/docs/verification-and-metrics.mdx
- Create: site/src/content/config.ts

Steps:
- Create content config for MDX.
- Write:
  - overview: short summary + link to repo.
  - architecture: explain Python orchestration + Rust solver.
  - how-to-run: local run + cluster run (from README and existing docs).
  - problem-families: link to catalog (later dynamic).
  - methodology: SAT checks, tolerances, Friedman comparison rules.
  - verification-and-metrics: how verify_solution and compare_results work.
- In docs.astro, list links to each doc page.
- Verify:
  - Run dev; navigate each doc; confirm readable, no build errors.
- Commit:
  - `git commit -m "docs: add core documentation pages for shape packing site"`

---

### Task 4: Create data ingestion script for PACKING_REFERENCE

Objective: Build a build-time script that reads PACKING_REFERENCE and generates:
- A JSON index of all problem families and current best metrics.
- Per-family data for dashboard and per-family pages.

Files:
- Create: scripts/build_site_data.py
- Create: site/src/lib/site_data/packing_reference.ts (or JSON)

Steps:
- script logic:
  - Input: PACKING_REFERENCE.json
  - Output: site_data.json with:
    - families: list of {family, N, best_value, status, source_url, last_updated}
    - problems: flat list of entries.
- Run locally:
  - `python scripts/build_site_data.py`
  - Confirm site_data.json is created and valid JSON.
- Test:
  - Create tests/test_build_site_data.py:
    - Load PACKING_REFERENCE, run script, assert:
      - families and problems are populated.
      - best_value is numeric when present.
- Commit:
  - `git commit -m "feat: add build_site_data.py to transform PACKING_REFERENCE"`

---

### Task 5: Implement results dashboard page

Objective: Provide a filterable view of packing results.

Files:
- Modify: site/src/pages/results.astro
- Create: site/src/components/ResultsTable.astro
- Create: site/src/components/ResultsFilters.astro

Steps:
- ResultsTable:
  - Table columns:
    - Family
    - N
    - Best Value
    - Status
    - Link to packing (if available)
- ResultsFilters:
  - Filter by:
    - family (dropdown)
    - status (e.g., best_known / trivial / proved_optimal)
- Wire up:
  - Astro page loads site_data.json and passes to components.
- Verify:
  - Run dev; confirm you can see and filter results.
- Commit:
  - `git commit -m "feat: add results dashboard with filters from PACKING_REFERENCE"`

---

### Task 6: Add per-family pages generated from requirements

Objective: For each family in docs/requirements/60-problem-families/, generate a dedicated page showing:
- Requirements.
- Associated results from PACKING_REFERENCE.

Files:
- Create: site/src/pages/family/[slug]/index.astro
- Create: scripts/build_family_slugs.py

Steps:
- build_family_slugs.py:
  - List all markdown files in docs/requirements/60-problem-families/
  - Generate:
    - A JSON map: slug -> metadata (name, family_token).
- index.astro:
  - Get static paths from that JSON.
  - On build:
    - Read corresponding requirements MD.
    - Read related results from site_data.json.
    - Render:
      - Family header.
      - Requirements (markdown)
      - Current best packings table.
- Verify:
  - Build; confirm at least 3 families render.
- Commit:
  - `git commit -m "feat: add per-family pages generated from requirements and PACKING_REFERENCE"`

---

### Task 7: Implement B-level packing visualizations

Objective: Render simple packings for best solutions as SVG/canvas visuals.

Files:
- Create: site/src/lib/visualization/render_packing.ts
- Create: site/src/components/PackingVisual.astro

Steps:
- render_packing.ts:
  - Input: solution JSON with shape positions (x, y, angle, scale, vertices).
  - Output: SVG or canvas drawing:
    - Draw container outline.
    - Draw each inner shape (polygon).
    - Use simple colors; no complex interactivity.
- PackingVisual:
  - Accept a solution JSON (or ID).
  - Use client:load to run visualization.
- Integration:
  - On per-family and/or results pages, for selected best packings:
    - Embed PackingVisual.
- Constraints:
  - Only visualize packings that:
    - Have valid solution JSON.
    - Are small enough (e.g., N <= 30) to avoid clutter.
- Verify:
  - Hard-code a known solution JSON into one page; confirm visual appears.
- Commit:
  - `git commit -m "feat: add B-level packing visualization components"`

---

### Task 8: Configure GitHub Actions for build + deploy

Objective: Automate site generation and GitHub Pages deployment.

Files:
- Create: .github/workflows/deploy-astro.yml

Steps:
- Workflow:
  - On: push to main (or main+development, your choice).
  - Jobs:
    - build:
      - Checkout repo.
      - Install Node.
      - Install Python dependencies (if needed for build scripts).
      - Run:
        - python scripts/build_site_data.py
        - python scripts/build_family_slugs.py (if used)
      - cd site && npm install && npm run build
      - Upload Pages artifact from site/dist.
      - (Use standard GitHub Pages deployment step.)
- Verify:
  - Trigger on test branch; ensure build succeeds locally first.
- Commit:
  - `git commit -m "ci: add GitHub Actions workflow for Astro build and Pages deploy"`

---

### Task 9: Polish usability and safety

Objective: Ensure site is safe for public view, easy for you to use.

Files:
- Modify: site/src/pages/index.astro
- Modify: any doc pages as needed

Steps:
- Add:
  - Short notice: “Internal working site; for debugging, visualization, and documentation. Not intended for external citation without confirmation.”
- Ensure:
  - No internal credentials/paths exposed.
  - No raw logs; only aggregated results.
- Add:
  - A small “How to use this site” section for you (filters, family pages, visualization hints).
- Commit:
  - `git commit -m "docs: polish site text, add internal-use note"`

---

### Task 10: Final validation

Objective: Validate end-to-end that the site works as intended.

Steps:
- Run:
  - `npm run build` in site/.
  - Preview build locally.
- Check:
  - Home page: clear intro.
  - Docs: architecture, how-to, methodology, metrics all readable.
  - Results: filtered dashboard works.
  - Family pages: render requirements + results.
  - Visuals: at least a handful of packings displayed.
- If issues:
  - Fix inline, commit small and focused.

Result: A working GitHub Pages-ready Astro site that:
- Documents the system.
- Shows PACKING_REFERENCE as a dashboard.
- Visualizes best packings.
- Is rebuildable from repo data.
