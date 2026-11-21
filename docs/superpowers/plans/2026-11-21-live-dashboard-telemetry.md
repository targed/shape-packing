# Live Astro Dashboard Telemetry Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the Astro documentation and results dashboard (`site/`) to the distributed coordinator API to display live cluster telemetry (active nodes, attempts completed, new records broken) and a real-time volunteer leaderboard, while preserving static site generation (SSG) fallbacks when the coordinator is offline.

**Architecture:** A client-side TypeScript service (`site/src/lib/api.ts`) queries the coordinator REST endpoints (`/api/v1/stats`, `/api/v1/leaderboard`) with configurable base URLs and short timeouts. An Astro component (`LiveClusterStats.astro`) hydrates in the browser to periodically poll `/api/v1/stats` and update DOM metrics. A dedicated `/leaderboard` page presents ranked volunteer contributions. When the coordinator is unreachable, the dashboard displays cached build-time snapshot numbers with an offline status indicator.

**Tech Stack:** Astro 5, TypeScript, Tailwind CSS, native browser `fetch`, `node:test` (Node standard test runner).

**Spec:** `docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md`

## Global Constraints

- Zero additional npm dependencies. Use native browser `fetch` and standard DOM manipulation in client scripts.
- The site must remain fully buildable and renderable even if the coordinator is completely offline during `astro build`.
- Polling intervals must be gentle on local and remote coordinators (default 10 seconds), with an automatic exponential backoff on consecutive network failures.
- Avoid em-dashes, forced triads, and filler prose throughout documentation and UI copy.

---

### Task 1: Coordinator API Client Service & Tests

**Files:**
- Create: `site/src/lib/api.ts`
- Test: `site/tests/api.test.js`

**Interfaces:**
- Consumes: Coordinator REST API (`GET /api/v1/stats`, `GET /api/v1/leaderboard`)
- Produces:
  - `fetchClusterStats(baseUrl?: string): Promise<ClusterStatsResult>`
  - `fetchLeaderboard(baseUrl?: string): Promise<LeaderboardResult>`
  - TypeScript types: `ClusterStats`, `LeaderboardEntry`, `ApiResult<T>`

- [ ] **Step 1: Write the failing Node test for the API client**

Create `site/tests/api.test.js` using Node's built-in test runner:

```javascript
// site/tests/api.test.js
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { fetchClusterStats, fetchLeaderboard } from '../src/lib/api.js';

describe('Coordinator API Client', () => {
  it('parses cluster stats response correctly', async () => {
    const mockFetch = async () => ({
      ok: true,
      json: async () => ({
        total_problems: 2249,
        active_workers: 4,
        total_attempts: 125000,
        records_broken: 3,
        verified_solutions: 3,
      }),
    });

    const result = await fetchClusterStats('http://localhost:8000', mockFetch);
    assert.equal(result.ok, true);
    assert.equal(result.data.active_workers, 4);
    assert.equal(result.data.total_attempts, 125000);
    assert.equal(result.data.records_broken, 3);
  });

  it('handles server offline gracefully with fallback status', async () => {
    const mockFailingFetch = async () => {
      throw new Error('Connection refused');
    };

    const result = await fetchClusterStats('http://localhost:8000', mockFailingFetch);
    assert.equal(result.ok, false);
    assert.match(result.error, /Connection refused/);
  });

  it('parses leaderboard rankings correctly', async () => {
    const mockFetch = async () => ({
      ok: true,
      json: async () => ([
        { username: 'targed', total_attempts: 90000, records_broken: 2 },
        { username: 'worker-beta', total_attempts: 35000, records_broken: 1 },
      ]),
    });

    const result = await fetchLeaderboard('http://localhost:8000', mockFetch);
    assert.equal(result.ok, true);
    assert.equal(result.data.length, 2);
    assert.equal(result.data[0].username, 'targed');
    assert.equal(result.data[0].records_broken, 2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test site/tests/api.test.js`
Expected: FAIL (Cannot find module `../src/lib/api.js`).

- [ ] **Step 3: Implement `site/src/lib/api.ts`**

Create `site/src/lib/api.ts`:

```typescript
export interface ClusterStats {
  total_problems: number;
  active_workers: number;
  total_attempts: number;
  records_broken: number;
  verified_solutions: number;
}

export interface LeaderboardEntry {
  username: string;
  total_attempts: number;
  records_broken: number;
}

export interface ApiResult<T> {
  ok: boolean;
  data?: T;
  error?: string;
}

export function getDefaultCoordinatorUrl(): string {
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);
    const queryOverride = params.get('coordinator');
    if (queryOverride) {
      return queryOverride.replace(/\/$/, '');
    }
    const stored = window.localStorage.getItem('shape_packing_coordinator_url');
    if (stored) {
      return stored.replace(/\/$/, '');
    }
  }
  return 'http://localhost:8000';
}

export async function fetchClusterStats(
  baseUrl?: string,
  fetchFn: typeof fetch = fetch
): Promise<ApiResult<ClusterStats>> {
  const url = `${baseUrl || getDefaultCoordinatorUrl()}/api/v1/stats`;
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3500);
    const response = await fetchFn(url, { signal: controller.signal });
    clearTimeout(timeoutId);

    if (!response.ok) {
      return { ok: false, error: `HTTP ${response.status}: ${response.statusText}` };
    }
    const data = (await response.json()) as ClusterStats;
    return { ok: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: message };
  }
}

export async function fetchLeaderboard(
  baseUrl?: string,
  fetchFn: typeof fetch = fetch
): Promise<ApiResult<LeaderboardEntry[]>> {
  const url = `${baseUrl || getDefaultCoordinatorUrl()}/api/v1/leaderboard`;
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3500);
    const response = await fetchFn(url, { signal: controller.signal });
    clearTimeout(timeoutId);

    if (!response.ok) {
      return { ok: false, error: `HTTP ${response.status}: ${response.statusText}` };
    }
    const data = (await response.json()) as LeaderboardEntry[];
    return { ok: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: message };
  }
}
```

- [ ] **Step 4: Re-run tests and verify pass**

Run: `node --test site/tests/api.test.js`
Expected: 3 passing tests.

---

### Task 2: Live Cluster Telemetry Widget Component

**Files:**
- Create: `site/src/components/LiveClusterStats.astro`

**Interfaces:**
- Props: `initialStats?: ClusterStats` (Optional SSG fallback passed from build data)
- DOM Attributes: Identifiable data attributes (`data-stat="active-workers"`, etc.) for seamless script updating.

- [ ] **Step 1: Implement `site/src/components/LiveClusterStats.astro`**

```astro
---
interface Props {
  initialAttempts?: number;
  initialRecords?: number;
}

const { initialAttempts = 0, initialRecords = 0 } = Astro.props;
---

<div id="live-cluster-container" class="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur-sm space-y-4">
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-2.5">
      <span id="cluster-indicator" class="w-2.5 h-2.5 rounded-full bg-slate-600"></span>
      <span id="cluster-status-text" class="text-xs font-semibold text-slate-400 uppercase tracking-wider">
        Coordinator: Checking...
      </span>
    </div>
    <div class="flex items-center gap-3">
      <span id="cluster-last-updated" class="text-[11px] text-slate-500 font-mono">Connecting</span>
      <button
        id="btn-refresh-stats"
        class="text-xs px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium transition-colors"
        title="Refresh live cluster numbers"
      >
        Refresh
      </button>
    </div>
  </div>

  <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
    <div class="bg-slate-950/70 border border-slate-800/80 rounded-xl p-4 flex flex-col">
      <span class="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Active Workers</span>
      <span id="stat-active-workers" class="text-2xl font-extrabold text-sky-400 mt-1 font-mono">0</span>
      <span class="text-[10px] text-slate-500 mt-1">Nodes reporting heartbeat</span>
    </div>

    <div class="bg-slate-950/70 border border-slate-800/80 rounded-xl p-4 flex flex-col">
      <span class="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Total Attempts</span>
      <span id="stat-total-attempts" class="text-2xl font-extrabold text-indigo-400 mt-1 font-mono">
        {initialAttempts.toLocaleString()}
      </span>
      <span class="text-[10px] text-slate-500 mt-1">Multi-start iterations</span>
    </div>

    <div class="bg-slate-950/70 border border-amber-500/30 rounded-xl p-4 bg-amber-500/5 flex flex-col">
      <span class="text-[11px] uppercase tracking-wider font-bold text-amber-400">Records Broken</span>
      <span id="stat-records-broken" class="text-2xl font-extrabold text-amber-300 mt-1 font-mono">
        {initialRecords}
      </span>
      <span class="text-[10px] text-amber-400/80 mt-1">Better than Friedman bound</span>
    </div>

    <div class="bg-slate-950/70 border border-slate-800/80 rounded-xl p-4 flex flex-col">
      <span class="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Verified Solutions</span>
      <span id="stat-verified-solutions" class="text-2xl font-extrabold text-emerald-400 mt-1 font-mono">
        {initialRecords}
      </span>
      <span class="text-[10px] text-slate-500 mt-1">SAT collision check passed</span>
    </div>
  </div>
</div>

<script>
  import { fetchClusterStats, getDefaultCoordinatorUrl } from '../lib/api';

  const indicator = document.getElementById('cluster-indicator');
  const statusText = document.getElementById('cluster-status-text');
  const lastUpdated = document.getElementById('cluster-last-updated');
  const activeWorkers = document.getElementById('stat-active-workers');
  const totalAttempts = document.getElementById('stat-total-attempts');
  const recordsBroken = document.getElementById('stat-records-broken');
  const verifiedSolutions = document.getElementById('stat-verified-solutions');
  const refreshBtn = document.getElementById('btn-refresh-stats');

  let pollTimer: number | null = null;
  let consecutiveErrors = 0;

  async function updateStats() {
    const res = await fetchClusterStats();
    const now = new Date().toLocaleTimeString();

    if (res.ok && res.data) {
      consecutiveErrors = 0;
      if (indicator) {
        indicator.className = 'w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse';
      }
      if (statusText) {
        statusText.textContent = `Coordinator: Online (${res.data.active_workers} active)`;
        statusText.className = 'text-xs font-semibold text-emerald-400 uppercase tracking-wider';
      }
      if (activeWorkers) activeWorkers.textContent = res.data.active_workers.toLocaleString();
      if (totalAttempts) totalAttempts.textContent = res.data.total_attempts.toLocaleString();
      if (recordsBroken) recordsBroken.textContent = res.data.records_broken.toLocaleString();
      if (verifiedSolutions) verifiedSolutions.textContent = res.data.verified_solutions.toLocaleString();
      if (lastUpdated) lastUpdated.textContent = `Updated ${now}`;
    } else {
      consecutiveErrors += 1;
      if (indicator) {
        indicator.className = 'w-2.5 h-2.5 rounded-full bg-amber-500';
      }
      if (statusText) {
        statusText.textContent = 'Coordinator: Offline (Snapshot Mode)';
        statusText.className = 'text-xs font-semibold text-amber-400 uppercase tracking-wider';
      }
      if (lastUpdated) lastUpdated.textContent = `Check failed ${now}`;
    }

    scheduleNextPoll();
  }

  function scheduleNextPoll() {
    if (pollTimer) clearTimeout(pollTimer);
    const delay = consecutiveErrors > 3 ? 30000 : 10000;
    pollTimer = window.setTimeout(updateStats, delay);
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      if (statusText) statusText.textContent = 'Refreshing...';
      updateStats();
    });
  }

  updateStats();
</script>
```

---

### Task 3: Real-Time Volunteer Leaderboard Page & Component

**Files:**
- Create: `site/src/components/LeaderboardTable.astro`
- Create: `site/src/pages/leaderboard.astro`
- Modify: `site/src/layouts/BaseLayout.astro` (Add navigation link to Leaderboard)

**Interfaces:**
- Consumes: `site/src/lib/api.ts` -> `fetchLeaderboard`
- Produces: Dynamic ranking table with username, attempts, and records broken.

- [ ] **Step 1: Implement `site/src/components/LeaderboardTable.astro`**

```astro
---
---

<div class="space-y-4">
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-2">
      <h2 class="text-xl font-bold text-white tracking-tight">Active Contributors</h2>
      <span id="leaderboard-count-badge" class="px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
        0 Volunteers
      </span>
    </div>
    <button
      id="btn-refresh-leaderboard"
      class="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium transition-colors border border-slate-700 flex items-center gap-1.5"
    >
      <span>Refresh Rankings</span>
    </button>
  </div>

  <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur-sm shadow-xl">
    <table class="w-full text-left text-xs text-slate-300">
      <thead class="bg-slate-950/80 uppercase text-slate-400 border-b border-slate-800 font-semibold tracking-wider font-mono">
        <tr>
          <th class="px-4 py-3.5 text-center w-16">Rank</th>
          <th class="px-5 py-3.5">Volunteer</th>
          <th class="px-5 py-3.5 text-right">Compute Attempts</th>
          <th class="px-5 py-3.5 text-right text-amber-400">Records Broken</th>
        </tr>
      </thead>
      <tbody id="leaderboard-tbody" class="divide-y divide-slate-800/60 font-mono">
        <tr>
          <td colspan="4" class="px-6 py-8 text-center text-slate-500">
            Querying coordinator for active rankings...
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</div>

<script>
  import { fetchLeaderboard } from '../lib/api';

  const tbody = document.getElementById('leaderboard-tbody');
  const countBadge = document.getElementById('leaderboard-count-badge');
  const refreshBtn = document.getElementById('btn-refresh-leaderboard');

  async function renderLeaderboard() {
    const res = await fetchLeaderboard();
    if (!tbody) return;

    if (!res.ok || !res.data || res.data.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="4" class="px-6 py-8 text-center text-slate-500">
            ${res.ok ? 'No volunteer records registered yet. Start a native or browser worker to appear here.' : 'Coordinator is offline. Connect to coordinator to view live rankings.'}
          </td>
        </tr>
      `;
      if (countBadge) countBadge.textContent = '0 Volunteers';
      return;
    }

    if (countBadge) {
      countBadge.textContent = `${res.data.length} Volunteers`;
    }

    tbody.innerHTML = res.data.map((row, index) => {
      const rank = index + 1;
      let medal = `#${rank}`;
      if (rank === 1) medal = '🥇 #1';
      else if (rank === 2) medal = '🥈 #2';
      else if (rank === 3) medal = '🥉 #3';

      return `
        <tr class="hover:bg-slate-800/40 transition-colors">
          <td class="px-4 py-3.5 text-center font-bold text-slate-400">${medal}</td>
          <td class="px-5 py-3.5 font-bold text-slate-100 flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
            ${escapeHtml(row.username)}
          </td>
          <td class="px-5 py-3.5 text-right text-slate-200">${row.total_attempts.toLocaleString()}</td>
          <td class="px-5 py-3.5 text-right font-bold text-amber-300">${row.records_broken.toLocaleString()}</td>
        </tr>
      `;
    }).join('');
  }

  function escapeHtml(text: string): string {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', renderLeaderboard);
  }

  renderLeaderboard();
</script>
```

- [ ] **Step 2: Create `site/src/pages/leaderboard.astro`**

```astro
---
import BaseLayout from '../layouts/BaseLayout.astro';
import LeaderboardTable from '../components/LeaderboardTable.astro';
import LiveClusterStats from '../components/LiveClusterStats.astro';
import fs from 'node:fs';
import path from 'node:path';

let totalAttempts = 0;
let totalRecords = 0;
try {
  const siteData = JSON.parse(fs.readFileSync(path.resolve(process.cwd(), 'src/data/site_data.json'), 'utf-8'));
  totalAttempts = siteData.summary?.total_slurm_attempts || 0;
  totalRecords = siteData.summary?.total_new_bests || 0;
} catch {
  // Graceful fallback if data file is absent
}
---

<BaseLayout title="Leaderboard | Shape Packing Volunteer Grid">
  <div class="space-y-8">
    <div class="space-y-3">
      <h1 class="text-3xl font-extrabold text-white tracking-tight">Volunteer Leaderboard</h1>
      <p class="text-sm text-slate-400 max-w-2xl">
        Live volunteer grid statistics and contributor rankings. Every compute cycle runs geometric collision checks and gradient descent to push packing bounds forward.
      </p>
    </div>

    <LiveClusterStats initialAttempts={totalAttempts} initialRecords={totalRecords} />

    <LeaderboardTable />
  </div>
</BaseLayout>
```

- [ ] **Step 3: Update `site/src/layouts/BaseLayout.astro` Navigation**

In `site/src/layouts/BaseLayout.astro`, add a navigation link to Leaderboard:

```astro
        <nav class="flex items-center gap-1 sm:gap-2">
          <a href={`${base}/`} class="px-3 py-2 rounded-md text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors">Home</a>
          <a href={`${base}/results`} class="px-3 py-2 rounded-md text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors">Results</a>
          <a href={`${base}/leaderboard`} class="px-3 py-2 rounded-md text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors">Leaderboard</a>
          <a href={`${base}/docs`} class="px-3 py-2 rounded-md text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors">Docs</a>
          <a href={`${base}/about`} class="px-3 py-2 rounded-md text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors">About</a>
        </nav>
```

---

### Task 4: Home Page Integration & Build Verification

**Files:**
- Modify: `site/src/pages/index.astro`

**Interfaces:**
- Connects `LiveClusterStats` directly under the Hero Section of the homepage.

- [ ] **Step 1: Embed `LiveClusterStats` on `site/src/pages/index.astro`**

Import and add `LiveClusterStats` directly after the hero section and before the stat cards:

```astro
    <!-- Live Cluster Telemetry -->
    <LiveClusterStats
      initialAttempts={summary.total_slurm_attempts}
      initialRecords={summary.total_new_bests}
    />
```

- [ ] **Step 2: Build the Astro site to verify SSG integrity**

Run: `cd site && npm run build`
Expected: Astro build succeeds, emitting static HTML and JavaScript assets into `dist/`.

- [ ] **Step 3: Test live coordination integration**

Start the FastAPI coordinator in background:
```bash
python -m uvicorn src.shape_packing.server.app:app --port 8000
```
Run native worker for 1 problem:
```bash
python -m src.shape_packing.client.native_worker --server http://localhost:8000 --username web_test --cores 1 --max-attempts 100
```
Run Astro preview server and verify the page queries `http://localhost:8000/api/v1/stats`:
```bash
cd site && npm run preview -- --port 4321
```
Open `http://localhost:4321/leaderboard` in browser or curl the preview page to confirm `web_test` shows in rankings.
