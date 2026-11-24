# Website UI/UX Overhaul: Precision Geometry Atelier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul the shape packing website (`site/`) into a premier scientific research atelier and volunteer computing hub, retaining and enhancing all functionality while eliminating AI-generated styling slop and contrast bugs.

**Architecture:** Built on Astro 5 and Tailwind CSS 3. The overhaul introduces a disciplined design token system (blueprint slate canvas `#0b0f17`, architectural surfaces, cyan `#0284c7`, cadmium gold `#f59e0b`, verification emerald `#10b981`), high-legibility typography (*Space Grotesk*, *Plus Jakarta Sans*, *IBM Plex Mono*), interactive SVG geometry plates, instant client-side filtering tabs, and a dual-option volunteer computing cockpit.

**Tech Stack:** Astro 5.4, Tailwind CSS 3.4, TypeScript, HTML5 Canvas, WebAssembly / Web Workers, Google Fonts.

## Global Constraints

- Absolute zero emojis across all code, UI, badges, buttons, and docs. Use mathematical glyphs or SVG icons.
- Strict WCAG AAA contrast: body text >7:1, headings/buttons >4.5:1. No text gradients that wash out into dark backgrounds.
- Consistent 3-tier radius scale: 6px (`rounded-md`), 8px (`rounded-lg`), 12px (`rounded-xl`). No arbitrary pill shapes.
- No blurry drop-shadows or card glows: use 1px hairline dividers (`rgba(255,255,255,0.08)` or `border-slate-800`).
- No em dashes in prose or documentation; keep language crisp and plain.
- Build command on Windows must run with `BypassSandbox: true`: `npm run build --prefix site`.

---

### Task 1: Design System Foundations & Global Layout

**Files:**
- Modify: `site/tailwind.config.mjs`
- Modify: `site/src/layouts/BaseLayout.astro`
- Modify: `site/src/components/LiveClusterStats.astro`
- Test: `site/tests/design_system.test.mjs` (or build check)

**Interfaces:**
- Consumes: Tailwind CSS theme configuration and Google Fonts.
- Produces: CSS variables and utility classes for `bg-canvas`, `bg-surface`, `bg-surface-elevated`, `border-hairline`, `font-display`, `font-sans`, `font-mono`, `text-blueprint`, `text-cadmium`, `text-emerald-verify`.

- [ ] **Step 1: Update Tailwind configuration with design tokens**

Update `site/tailwind.config.mjs` with exact colors, typography, and radiuses:

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        canvas: '#0b0f17',
        surface: {
          DEFAULT: '#111827',
          elevated: '#1a2234',
          hover: '#1e293b',
        },
        blueprint: {
          DEFAULT: '#0284c7',
          light: '#38bdf8',
          dark: '#0369a1',
        },
        cadmium: {
          DEFAULT: '#f59e0b',
          light: '#fbbf24',
          dark: '#d97706',
        },
        verify: {
          DEFAULT: '#10b981',
          light: '#34d399',
        },
        hairline: 'rgba(255, 255, 255, 0.08)',
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
      borderRadius: {
        sm: '4px',
        md: '6px',
        lg: '8px',
        xl: '12px',
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 2: Update BaseLayout with typography, architectural header, and clean footer**

Update `site/src/layouts/BaseLayout.astro` to import Google Fonts (*Space Grotesk*, *Plus Jakarta Sans*, *IBM Plex Mono*), apply `bg-canvas` and `text-slate-100`, replace the generic purple gradient icon with a geometric SVG brandmark, remove the yellow notice banner, and install the clean technical header and footer:

```astro
---
interface Props {
  title?: string;
  description?: string;
}

const {
  title = "Shape Packing Geometric Benchmark & Solver",
  description = "Scientific benchmark and volunteer distributed computing grid for 2D geometric packing optimization against Erich Friedman reference records."
} = Astro.props;

const base = import.meta.env.BASE_URL.replace(/\/$/, "");
---

<!DOCTYPE html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title} | Shape Packing</title>
    <meta name="description" content={description} />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
    <style is:global>
      body {
        font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
      }
      h1, h2, h3, h4, .font-display {
        font-family: 'Space Grotesk', system-ui, sans-serif;
      }
      code, pre, .font-mono {
        font-family: 'IBM Plex Mono', monospace;
        font-feature-settings: "tnum" on, "lnum" on;
      }
    </style>
  </head>
  <body class="bg-canvas text-slate-100 min-h-screen flex flex-col antialiased selection:bg-blueprint selection:text-white">
    <!-- Header -->
    <header class="sticky top-0 z-50 backdrop-blur-md bg-canvas/90 border-b border-hairline">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <a href={`${base}/`} class="flex items-center gap-3 group">
          <div class="w-8 h-8 rounded-md bg-surface-elevated border border-hairline flex items-center justify-center text-blueprint-light group-hover:border-blueprint/50 transition-colors">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5" />
              <line x1="12" y1="22" x2="12" y2="15.5" />
              <polyline points="22 8.5 12 15.5 2 8.5" />
            </svg>
          </div>
          <div class="flex flex-col">
            <div class="flex items-center gap-2">
              <span class="font-display font-bold text-slate-100 tracking-tight text-base group-hover:text-blueprint-light transition-colors">SHAPE PACKING</span>
              <span class="text-[10px] font-mono px-1.5 py-0.2 rounded bg-surface border border-hairline text-slate-400">v2.4</span>
            </div>
            <span class="text-[10px] uppercase tracking-wider font-mono text-slate-400">Geometric Benchmark</span>
          </div>
        </a>

        <nav class="flex items-center gap-1 sm:gap-2">
          <a href={`${base}/`} class="px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium text-slate-300 hover:text-white hover:bg-surface-elevated transition-colors">Home</a>
          <a href={`${base}/results`} class="px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium text-slate-300 hover:text-white hover:bg-surface-elevated transition-colors">Results</a>
          <a href={`${base}/leaderboard`} class="px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium text-slate-300 hover:text-white hover:bg-surface-elevated transition-colors">Leaderboard</a>
          <a href={`${base}/contribute`} class="px-3 py-1.5 rounded-md text-xs sm:text-sm font-semibold text-verify-light bg-verify/10 hover:bg-verify/20 border border-verify/30 transition-colors">
            Volunteer Grid
          </a>
          <a href={`${base}/docs`} class="px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium text-slate-300 hover:text-white hover:bg-surface-elevated transition-colors">Docs</a>
          <a href={`${base}/about`} class="px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium text-slate-300 hover:text-white hover:bg-surface-elevated transition-colors">About</a>
        </nav>
      </div>
    </header>

    <!-- Main Content -->
    <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <slot />
    </main>

    <!-- Technical Drafting Footer -->
    <footer class="border-t border-hairline bg-surface/50 py-8 text-xs text-slate-400 font-mono">
      <div class="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row justify-between items-center gap-4">
        <div class="flex items-center gap-3">
          <span class="w-2 h-2 rounded-full bg-verify"></span>
          <span>Shape Packing Research Platform &bull; Static Astro Build</span>
        </div>
        <div class="flex items-center gap-6 text-slate-400">
          <a href="https://github.com/erich-friedman/packing" target="_blank" rel="noopener noreferrer" class="hover:text-blueprint-light transition-colors">Erich Friedman Benchmark</a>
          <a href={`${base}/docs`} class="hover:text-blueprint-light transition-colors">Technical Architecture</a>
          <a href={`${base}/contribute`} class="hover:text-blueprint-light transition-colors">Contribute Compute</a>
        </div>
      </div>
    </footer>
  </body>
</html>
```

- [ ] **Step 3: Redesign LiveClusterStats with architectural hairline rules and no emojis**

Update `site/src/components/LiveClusterStats.astro` to remove generic card soup and pulsing green dots, using structured architectural dividers:

```astro
---
interface Props {
  familiesCount?: number;
  problemsCount?: number;
  initialAttempts?: number;
  initialRecords?: number;
}

const {
  familiesCount = 80,
  problemsCount = 2242,
  initialAttempts = 0,
  initialRecords = 0,
} = Astro.props;

const base = import.meta.env.BASE_URL.replace(/\/$/, "");
---

<div id="live-cluster-container" class="rounded-lg border border-hairline bg-surface p-5 space-y-4">
  <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-hairline pb-3">
    <div class="flex items-center gap-2.5 font-mono text-xs">
      <span id="cluster-indicator" class="w-2 h-2 rounded-full bg-slate-500"></span>
      <span id="cluster-status-text" class="font-semibold text-slate-300 uppercase tracking-wider">
        Coordinator: Checking...
      </span>
      <span id="cluster-last-updated" class="text-slate-500 ml-2">Connecting</span>
    </div>
    <div class="flex items-center gap-3 text-xs">
      <button
        id="btn-refresh-stats"
        class="px-2.5 py-1 rounded-md bg-surface-elevated hover:bg-surface-hover text-slate-300 font-medium transition-colors cursor-pointer border border-hairline font-mono"
        title="Refresh live cluster metrics"
      >
        Refresh
      </button>
      <a href={`${base}/leaderboard`} class="font-medium text-blueprint-light hover:underline font-mono">
        Leaderboard &rarr;
      </a>
      <a href={`${base}/contribute`} class="font-semibold text-verify-light hover:underline font-mono">
        Join Grid &rarr;
      </a>
    </div>
  </div>

  <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
    <!-- Problem Families -->
    <div class="bg-surface-elevated border border-hairline rounded-md p-3.5 flex flex-col">
      <span class="text-[10px] uppercase tracking-wider font-mono text-slate-400">Problem Families</span>
      <span class="text-2xl font-bold text-white mt-1 font-mono">{familiesCount}</span>
      <span class="text-[10px] text-slate-400 mt-1">Catalogued Sets</span>
    </div>

    <!-- Benchmark Records -->
    <div class="bg-surface-elevated border border-hairline rounded-md p-3.5 flex flex-col">
      <span class="text-[10px] uppercase tracking-wider font-mono text-slate-400">Benchmark Records</span>
      <span class="text-2xl font-bold text-blueprint-light mt-1 font-mono">{problemsCount.toLocaleString()}</span>
      <span class="text-[10px] text-slate-400 mt-1">Friedman Bound Entries</span>
    </div>

    <!-- Records Broken -->
    <div class="bg-surface-elevated border border-cadmium/40 rounded-md p-3.5 flex flex-col">
      <span class="text-[10px] uppercase tracking-wider font-mono font-bold text-cadmium-light">Records Broken</span>
      <span id="stat-records-broken" class="text-2xl font-bold text-cadmium mt-1 font-mono">
        {initialRecords}
      </span>
      <span class="text-[10px] text-cadmium-light/80 mt-1">Tighter than reference</span>
    </div>

    <!-- Compute Attempts -->
    <div class="bg-surface-elevated border border-hairline rounded-md p-3.5 flex flex-col">
      <span class="text-[10px] uppercase tracking-wider font-mono text-slate-400">Compute Attempts</span>
      <span id="stat-total-attempts" class="text-2xl font-bold text-slate-200 mt-1 font-mono">
        {initialAttempts.toLocaleString()}
      </span>
      <span class="text-[10px] text-slate-400 mt-1">Multi-start iterations</span>
    </div>

    <!-- Active Workers -->
    <div class="bg-surface-elevated border border-hairline rounded-md p-3.5 flex flex-col col-span-2 sm:col-span-1">
      <span class="text-[10px] uppercase tracking-wider font-mono text-slate-400">Active Workers</span>
      <span id="stat-active-workers" class="text-2xl font-bold text-verify-light mt-1 font-mono">0</span>
      <span class="text-[10px] text-slate-400 mt-1">Reporting heartbeat</span>
    </div>
  </div>
</div>

<script>
  import { fetchClusterStats } from '../lib/api';

  const indicator = document.getElementById('cluster-indicator');
  const statusText = document.getElementById('cluster-status-text');
  const lastUpdated = document.getElementById('cluster-last-updated');
  const activeWorkers = document.getElementById('stat-active-workers');
  const totalAttempts = document.getElementById('stat-total-attempts');
  const recordsBroken = document.getElementById('stat-records-broken');
  const refreshBtn = document.getElementById('btn-refresh-stats');

  let pollTimer: number | null = null;
  let consecutiveErrors = 0;

  async function updateStats() {
    try {
      const res = await fetchClusterStats();
      if (res.ok && res.data) {
        consecutiveErrors = 0;
        if (indicator) {
          indicator.className = 'w-2 h-2 rounded-full bg-verify';
        }
        if (statusText) {
          statusText.textContent = `COORDINATOR: ONLINE (${res.data.active_workers} ACTIVE)`;
          statusText.className = 'font-semibold text-verify-light uppercase tracking-wider';
        }
        if (lastUpdated) {
          lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
        }
        if (activeWorkers) activeWorkers.textContent = String(res.data.active_workers);
        if (totalAttempts) totalAttempts.textContent = res.data.total_attempts.toLocaleString();
        if (recordsBroken) recordsBroken.textContent = String(res.data.records_broken);
      } else {
        handleOffline();
      }
    } catch {
      handleOffline();
    }
  }

  function handleOffline() {
    consecutiveErrors++;
    if (indicator) {
      indicator.className = 'w-2 h-2 rounded-full bg-slate-500';
    }
    if (statusText) {
      statusText.textContent = 'COORDINATOR: OFFLINE (STATIC DATA)';
      statusText.className = 'font-semibold text-slate-400 uppercase tracking-wider';
    }
    if (lastUpdated) {
      lastUpdated.textContent = `Checked ${new Date().toLocaleTimeString()}`;
    }
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', updateStats);
  }

  updateStats();
  pollTimer = window.setInterval(updateStats, 10000);

  window.addEventListener('beforeunload', () => {
    if (pollTimer !== null) clearInterval(pollTimer);
  });
</script>
```

- [ ] **Step 4: Test build of Phase 1**

Run: `npm run build --prefix site`
Expected: Build succeeds with 0 errors.

- [ ] **Step 5: Commit Phase 1**

```bash
git add site/tailwind.config.mjs site/src/layouts/BaseLayout.astro site/src/components/LiveClusterStats.astro
git commit -m "feat(site): establish design tokens, typography, and BaseLayout architectural theme"
```

---

### Task 2: Architectural Visualization Plate Component

**Files:**
- Modify: `site/src/components/PackingVisual.astro`
- Modify: `site/src/lib/visualization/render_packing.ts`
- Test: Build verification

**Interfaces:**
- Consumes: `SolutionData` object from `site_data.json`.
- Produces: `<PackingVisual solution={solution} title="N=14" />` with blueprint coordinate axes, crosshairs, dimension tags, and SVG export.

- [ ] **Step 1: Enhance `render_packing.ts` for clean architectural blueprint styling**

Update `site/src/lib/visualization/render_packing.ts` so polygon vertices and circles have consistent blueprint stroke colors (`#38bdf8` for packed shapes, `#64748b` for container boundaries), and exports bounding box dimensions.

- [ ] **Step 2: Update `PackingVisual.astro` with architectural plate aesthetics and SVG export**

Update `site/src/components/PackingVisual.astro`:
- Outer container styled as an architectural plate: `bg-surface border border-hairline rounded-lg p-3`.
- Internal stage: `bg-canvas border border-hairline rounded-md`.
- Vector SVG with subtle coordinate crosshairs at the origin.
- Bottom footer with $N$, metric $s$, and a one-click "Export SVG" button.
- Absolute zero emojis.

- [ ] **Step 3: Test build with updated visualizer**

Run: `npm run build --prefix site`
Expected: 93 static pages build without errors.

- [ ] **Step 4: Commit Task 2**

```bash
git add site/src/components/PackingVisual.astro site/src/lib/visualization/render_packing.ts
git commit -m "feat(site): modernize PackingVisual with architectural blueprint plate styling"
```

---

### Task 3: Interactive Drafting Hero & Homepage Overhaul

**Files:**
- Modify: `site/src/pages/index.astro`
- Modify: `site/src/components/RecentlyUpdated.astro`
- Test: Build verification and inspect dist HTML

**Interfaces:**
- Consumes: `siteData` (problems, summary, new_bests, recent_solutions).
- Produces: High-contrast hero section with interactive geometry showcase, solid CTAs (eradicating the text fade bug and blacked-out button bug), and clean live activity stream.

- [ ] **Step 1: Rewrite Hero in `site/src/pages/index.astro`**

Replace lines 17-44 of `site/src/pages/index.astro`:
- Remove the broken gradient `bg-clip-text bg-gradient-to-r...` and replace with solid `#f8fafc` text.
- Replace the broken button with a high-contrast solid cyan CTA:
  `px-5 py-2.5 rounded-md bg-blueprint hover:bg-blueprint-dark text-white font-semibold text-sm transition-colors`.
- Secondary CTA:
  `px-5 py-2.5 rounded-md bg-surface-elevated hover:bg-surface-hover text-slate-200 font-semibold text-sm border border-hairline transition-colors`.
- Introduce split-column layout:
  - Left: Headline, description, action buttons, key metrics.
  - Right: Live interactive SVG visualizer showcasing selected solutions (e.g. 14 hexagons in triangle, 10 circles in L-tromino) with family switcher.

- [ ] **Step 2: Update Record-Beating Results section in `index.astro`**

Style the `new_bests` highlight cards as clean architectural cards with cadmium gold accents, high-contrast monospace tables, and zero emojis.

- [ ] **Step 3: Update `RecentlyUpdated.astro`**

Update `site/src/components/RecentlyUpdated.astro`:
- Clean architectural timeline with 1px hairline rules.
- Monospace timestamps and verified delta indicators.
- No emojis.

- [ ] **Step 4: Test build and verify hero HTML**

Run: `npm run build --prefix site`
Expected: Build passes with 0 errors.

- [ ] **Step 5: Commit Task 3**

```bash
git add site/src/pages/index.astro site/src/components/RecentlyUpdated.astro
git commit -m "feat(site): overhaul homepage with high-contrast interactive geometry hero"
```

---

### Task 4: Results Explorer & Geometric Badges Table

**Files:**
- Modify: `site/src/pages/results.astro`
- Modify: `site/src/components/ResultsTable.astro`
- Test: Build verification

**Interfaces:**
- Consumes: `problems` array (2,242 entries).
- Produces: Instant tab filtering (*All*, *Records Broken*, *Proved Optimal*, *Priority Targets*), search input, mini SVG shape badges, and hover solution preview.

- [ ] **Step 1: Implement mini SVG shape badge helper in `ResultsTable.astro`**

Map shape tokens (`circle`, `square`, `triangle`, `pentagon`, `hexagon`, `l_tromino`, `domino`) to mini vector SVG icons so rows display geometric visual badges (e.g., triangle inside square) next to the family name.

- [ ] **Step 2: Implement quick-filter tabs in `results.astro` and `ResultsTable.astro`**

Add filter buttons:
- `All (2,242)`
- `Records Broken (75)`
- `Proved Optimal`
- `Priority Targets`
Filter the table dynamically in JavaScript without page reloads.

- [ ] **Step 3: Add instant hover popover for solution previews**

When hovering a row with a valid solution, display a floating thumbnail of the packing vector.

- [ ] **Step 4: Test build of Results Explorer**

Run: `npm run build --prefix site`
Expected: Build passes with 0 errors.

- [ ] **Step 5: Commit Task 4**

```bash
git add site/src/pages/results.astro site/src/components/ResultsTable.astro
git commit -m "feat(site): upgrade ResultsTable with shape badges, filter tabs, and hover preview"
```

---

### Task 5: Shape Family Detail & Benchmark Curve Gallery

**Files:**
- Modify: `site/src/pages/family/[slug].astro`
- Modify: `site/src/pages/family/index.astro`
- Test: Build verification across all 80 family pages

**Interfaces:**
- Consumes: `family_slugs.json`, `site_data.json`.
- Produces: Dynamic family detail pages with $N$-grid gallery, comparison benchmark curves, and collapsible mathematical specification drawers.

- [ ] **Step 1: Overhaul `family/[slug].astro`**

Update layout to:
1. Header: Shape definition, degrees of freedom, and solved count.
2. Benchmark Curve: Inline SVG graph comparing Friedman benchmark $s$ against solver best $s$ across all $N$.
3. Gallery: Responsive grid of `PackingVisual` cards for all solved $N$ values.
4. Specification Drawer: Monospace drawer displaying raw collision rules and coordinates.

- [ ] **Step 2: Overhaul `family/index.astro`**

Update the family catalog index with a clean responsive grid of the 80 problem families, complete with mini SVG geometry previews, problem counts, and record counts.

- [ ] **Step 3: Test build of all 80 family pages**

Run: `npm run build --prefix site`
Expected: All 80 family pages build cleanly.

- [ ] **Step 4: Commit Task 5**

```bash
git add site/src/pages/family/[slug].astro site/src/pages/family/index.astro
git commit -m "feat(site): overhaul family detail pages with benchmark curves and packing gallery"
```

---

### Task 6: Volunteer Contributor Cockpit (Dual-Option & Oscilloscope)

**Files:**
- Modify: `site/src/pages/contribute.astro`
- Modify: `site/src/components/LivePackingCanvas.astro`
- Test: Build verification & in-browser worker test

**Interfaces:**
- Consumes: Wasm worker (`wasm_packer_worker.ts`) and coordinator REST endpoints.
- Produces: Dual-option choice layout, architectural oscilloscope canvas, live diagnostics pill, persistent settings.

- [ ] **Step 1: Overhaul Volunteer Choice Architecture in `contribute.astro`**

Present two distinct, equal-standing cards:
- **Option 1: In-Browser Cruncher (Wasm)**: Zero installation, runs immediately in web worker.
- **Option 2: Standalone Native Executable (CLI)**: High throughput multi-threading with Rayon (4+ CPU cores), background daemon capability.
Include prominent note explaining both options lease from and contribute to the same shared coordinator grid.

- [ ] **Step 2: Redesign Oscilloscope Visualizer in `LivePackingCanvas.astro`**

Update the HTML5 Canvas to render simulated annealing progress with architectural drafting crosshairs, temperature gauge, and convergence curve.

- [ ] **Step 3: Update Diagnostics Bar**

Include real-time latency ping to coordinator, active lease ticker, and core count selector.

- [ ] **Step 4: Test build and verify Web Worker scripts**

Run: `npm run build --prefix site`
Expected: Build passes with 0 errors.

- [ ] **Step 5: Commit Task 6**

```bash
git add site/src/pages/contribute.astro site/src/components/LivePackingCanvas.astro
git commit -m "feat(site): overhaul contribute cockpit with dual-option cards and oscilloscope canvas"
```

---

### Task 7: Leaderboard, Docs & About Pages

**Files:**
- Modify: `site/src/pages/leaderboard.astro`
- Modify: `site/src/components/LeaderboardTable.astro`
- Modify: `site/src/pages/docs.astro`
- Modify: `site/src/pages/docs/[...slug].astro`
- Modify: `site/src/pages/about.astro`
- Test: Build verification

**Interfaces:**
- Consumes: Markdown documentation collection and coordinator leaderboard API.
- Produces: Refined contributor rankings, Diátaxis documentation layout, and high-contrast About page.

- [ ] **Step 1: Overhaul `LeaderboardTable.astro` and `leaderboard.astro`**

Replace medals with clean rank badges (`#1`, `#2`, `#3`), high-contrast tabular lining numbers, and verified solution metrics. Zero emojis.

- [ ] **Step 2: Overhaul Docs Hub (`docs.astro` & `docs/[...slug].astro`)**

Apply Diátaxis styling: Tutorials, How-To Guides, Technical Reference, and Architecture Explanations. Clean syntax highlighting and copy-code buttons.

- [ ] **Step 3: Overhaul About Page (`about.astro`)**

Refine typography and structure into clear architectural sections explaining the mathematical methodology and open-source contribution guidelines.

- [ ] **Step 4: Test build of all documentation and static pages**

Run: `npm run build --prefix site`
Expected: All pages build cleanly.

- [ ] **Step 5: Commit Task 7**

```bash
git add site/src/pages/leaderboard.astro site/src/components/LeaderboardTable.astro site/src/pages/docs.astro site/src/pages/docs/[...slug].astro site/src/pages/about.astro
git commit -m "feat(site): polish leaderboard, Diátaxis documentation hub, and about pages"
```

---

### Task 8: Global Quality Audit & Verification Suite

**Files:**
- Verify: All files in `site/src/`
- Test: Build, lint, and backend test suites

**Interfaces:**
- Consumes: Complete built website and existing Rust/Python tests.
- Produces: Clean verification report confirming zero emojis, WCAG AAA contrast compliance, 0 build errors, and 0 backend regressions.

- [ ] **Step 1: Run zero-emoji audit across all source files**

Run a script or regex search across `site/src/` to confirm no unicode emojis exist.

- [ ] **Step 2: Run static production build**

Run: `npm run build --prefix site` (with BypassSandbox: true).
Expected: 93 pages generated successfully with 0 errors.

- [ ] **Step 3: Run backend regression tests**

Run:
- `cargo test --no-default-features`
- `pytest tests/test_solution_tools.py`
Expected: All tests pass.

- [ ] **Step 4: Final commit and summary**

```bash
git commit --allow-empty -m "chore(site): complete website UI/UX overhaul verification"
```
