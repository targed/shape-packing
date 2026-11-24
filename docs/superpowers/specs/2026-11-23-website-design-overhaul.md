# Website UI/UX Design & Architecture Overhaul

**Date:** November 23, 2026  
**Status:** Approved Design Specification  
**Design Direction:** Direction A: "Precision Geometry Atelier"  
**Scope:** Complete frontend overhaul across visual system, components, and pages (`site/`)

---

## 1. Executive Summary & Problem Diagnostics

The Shape Packing Benchmark & Analytics Hub is a scientific platform dedicated to 2D discrete geometry, mathematical optimization, and volunteer distributed computing against Erich Friedman's published packing records.

While functionally rich (Wasm solver, Rayon multi-threading, live coordinator telemetry, SAT collision verification, and an 80-family problem database), the frontend previously suffered from severe visual flaws:
* **The Dark-on-Dark Sludge**: Deep dark backgrounds (`bg-slate-950`) layered under dark cards (`bg-slate-900/60`), dark borders (`border-slate-800`), and dark text (`text-slate-950`), creating accidental low-contrast illegibility (as evidenced by broken hero CTAs and heading gradients washing out into the background).
* **Card-Soup SaaS Cliché**: Information trapped inside identical rounded rectangles with `rounded-2xl`, soft gray drop shadows, and purple/indigo gradient washes.
* **Template Chrome**: Tracked-out uppercase eyebrows, pulsing green indicator dots, and generic arrow glyphs appended to every link.
* **Domain Disconnect**: Discrete geometry is one of the most visually captivating branches of mathematics (polygonal tilings, kissing numbers, Keplerian sphere packings, Voronoi partitions). The website previously buried this geometric beauty under generic software boilerplate.

### Overhaul Objective
Transform the website into a premier scientific research atelier and volunteer computing hub. Retain and improve every existing capability while establishing a distinct, purposeful, domain-grounded visual identity.

---

## 2. Hard Aesthetic Constraints & Anti-Slop Rules

To strictly enforce craft and eliminate AI-generated visual tropes:
1. **Absolute Zero Emojis**: No emojis anywhere in the UI, code, documentation, badges, or buttons. All indicators must use mathematical glyphs ($\triangle$, $\square$, $\hexagon$, $\bigcirc$, $\times$, $\rightarrow$) or custom SVG icons.
2. **Strict WCAG AAA Contrast**: All body text must achieve $>7:1$ contrast against its backing canvas. Headings, labels, and interactive buttons must achieve $>4.5:1$. Text gradients that fade to dark or wash out are banned.
3. **No Blurry Drop-Shadows / Card Glows**: Replace all soft blurry box-shadows (`shadow-xl`, `shadow-cyan-500/20`) with 1px architectural hairline dividers (`rgba(255,255,255,0.08)` or `border-slate-800`).
4. **Three-Tier Radius Scale**:
   * **6px (`rounded-md`)**: Badges, form inputs, buttons, filter chips.
   * **8px (`rounded-lg`)**: Cards, data tables, code blocks, modal drawers.
   * **12px (`rounded-xl`)**: Main interactive visualizer canvas / oscilloscope container.
   * No arbitrary pill buttons or mixed inconsistent radiuses.
5. **No AI Cliché Elements**: No generic pulsing green dots, no purple/indigo gradient washes on dark cards, no tracked-out tiny uppercase subtitles, and no em dashes in prose.

---

## 3. Design System & Visual Foundation

### 3.1 Color Palette Tokens
* **Blueprint Canvas**: `#0b0f17` (obsidian blueprint slate). Grounding dark background with minimal eye fatigue.
* **Elevated Surfaces**:
  * Layer 1 (Cards & Data Tables): `#111827` (slate-900).
  * Layer 2 (Hover states & Active inputs): `#1e293b` (slate-800).
  * Hairline Rules & Dividers: `rgba(255, 255, 255, 0.08)`.
* **Technical Accents**:
  * **Precision Blueprint Cyan (`#0284c7` / `#38bdf8`)**: Primary interactive accent, active tabs, coordinates, and primary call-to-action buttons.
  * **Cadmium Benchmark Gold (`#f59e0b` / `#fbbf24`)**: Reserved strictly for new benchmark records (`NEW_BEST` improvements over Erich Friedman's bounds).
  * **Verification Emerald (`#10b981`)**: Optimal proofs, valid SAT collision checks, and active coordinator grid heartbeats.
  * **Coordinate Slate (`#94a3b8` / `#64748b`)**: Secondary annotations, dimension callouts, and mathematical formulas.
* **Text Hierarchy**:
  * Primary High-Contrast Text: `#f8fafc` (pure slate-50).
  * Secondary Text: `#cbd5e1` (slate-300).
  * Muted / Metadata Text: `#94a3b8` (slate-400).

### 3.2 Typography
* **Display & Headings**: *Space Grotesk* (clean, geometric, architectural character).
* **Body & Interface**: *Plus Jakarta Sans* (crisp humanist geometry, high readability across desktop and mobile).
* **Data, Coordinates & Mathematical Metrics**: *IBM Plex Mono* (high-legibility tabular lining numerals for aligned floating-point bounds and dimensions).

---

## 4. Component Architecture & Detailed Page Specifications

### 4.1 Global Navigation & Header (`src/components/Header.astro` & `BaseLayout.astro`)
* **Drafting Mark**: Clean architectural brandmark: SVG polygonal packing icon paired with `SHAPE PACKING` in *Space Grotesk* and a subtle version tag `v2.4`.
* **Navigation Links**: Clean text links with bottom border indicator on active route (*Explore Results*, *Shape Families*, *Volunteer Grid*, *Leaderboard*, *Documentation*).
* **Live Coordinator Grid Pill**: High-contrast status pill showing active worker count and grid status (`ONLINE (N ACTIVE)`), with a manual refresh button.

### 4.2 Interactive Geometry Hero (`src/pages/index.astro`)
* **Split Drafting Layout**:
  * **Left Column (Context & Action)**:
    * High-contrast typography: "Geometric Packing Benchmark & Distributed Solver".
    * Direct, concise explanation of the project's mathematical mission and Friedman benchmark tracking.
    * Two prominent primary actions:
      * Solid Cyan Primary CTA: "Explore 2,242 Records" (linking to `/results`).
      * Structured Drafting Secondary CTA: "Volunteer Compute" (linking to `/contribute`).
    * Inline cluster metric counters: Problem Families (80), Records Broken (75), Total Attempts, Active Grid Workers.
  * **Right Column (Interactive Geometry Showcase)**:
    * Interactive SVG visualizer displaying live solution geometries.
    * Toggleable showcase problems (e.g., 14 hexagons in triangle, 10 circles in L-tromino, 15 pentagons in square).
    * Overlay controls: Zoom toggle, coordinate crosshairs toggle, container boundary dimension display.

### 4.3 Results & Benchmark Explorer (`src/pages/results.astro` & `ResultsTable.astro`)
* **Visual Geometric Badges**: In addition to text slugs (e.g. `3_in_4`), render a mini SVG shape badge for each row representing the container and packed shape.
* **Instant Client-Side Filtering**:
  * `All Records` (2,242 entries)
  * `Records Broken (NEW_BEST)` (75 entries, highlighted with cadmium gold accent)
  * `Proved Optimal`
  * `Priority Targets` (unsolved or largest bound gaps)
* **High-Density Monospace Table**: Columns for Family, $N$, Metric $s$, Friedman Bound, Improvement $\Delta\%$, Optimal Status, and Timestamp.
* **Instant Hover Popover**: Hovering over any solved problem row renders an instant vector preview of the packing with bounding dimensions.

### 4.4 Shape Family Detail Pages (`src/pages/family/[slug].astro` & `family/index.astro`)
* **Family Header**: Mathematical definition of container $C$ and shape $S$, degrees of freedom, and total solved instances.
* **Benchmark Curve Chart ($N$ vs. $s$)**: Vector SVG curve comparing Erich Friedman's reference bounds against our solver's current best bounds across all $N$.
* **$N$ Solution Gallery**: Responsive grid of packing plates with dimension callouts, optimal ratios, and SVG export.
* **Mathematical Spec Drawer**: Collapsible technical drawer with exact SAT collision matrices and coordinate limits.

### 4.5 Volunteer Contributor Cockpit (`src/pages/contribute.astro`)
* **Dual-Choice Architecture**:
  * Clear side-by-side presentation:
    * **Option 1: In-Browser Cruncher (Wasm)**: Instant zero-install worker running simulated annealing in a web worker.
    * **Option 2: Standalone Native Executable (CLI)**: Maximum throughput with Rayon multi-threading utilizing 4+ CPU cores.
  * Unifying banner: *"Both clients connect to the exact same coordinator grid, lease from the same problem queue, and contribute verified solutions to the public benchmark. They are complementary options."*
* **Oscilloscope Canvas Visualizer**: Live HTML5 Canvas rendering annealing steps, temperature decay, best-so-far metric, and attempt counters.
* **Coordinator Diagnostics**: Real-time ping latency, active lease ticker, and core count selector.

### 4.6 Leaderboard (`src/pages/leaderboard.astro`) & Docs (`src/pages/docs.astro`)
* **Leaderboard**: High-contrast tabular standings with verified records broken, multi-start iterations donated, and live status.
* **Documentation**: Clean Diátaxis structure (Tutorials, How-To Guides, Technical Reference for SAT collision and verification, Architecture Explanations) with clean typography and copy-to-clipboard code blocks.

---

## 5. Verification & Quality Assurance Protocol

1. **Static Build Gate**: Run `npm run build --prefix site` (with `BypassSandbox: true` on Windows) to verify all 93 static pages compile with 0 errors.
2. **Zero-Emoji Lint**: Verify via regex search across all files in `site/src/` that 0 emoji characters exist.
3. **Contrast & Rendering Audit**: Verify text contrast and button styling across desktop, tablet, and mobile breakpoints.
4. **Wasm & Telemetry Test**: Verify in-browser worker and coordinator polling execute without console errors.
5. **System Regression Test**: Run Rust test suite (`cargo test --no-default-features`) and Python solver tests (`pytest tests/test_solution_tools.py`) to confirm no backend regressions.
