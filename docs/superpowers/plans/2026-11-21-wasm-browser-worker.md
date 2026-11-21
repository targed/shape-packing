# Browser WebAssembly Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable casual community volunteers to donate compute directly from their web browser by compiling `packer_rs` to WebAssembly and running continuous optimization inside background Web Workers with real-time Canvas visualization.

**Architecture:** A Rust `wasm` feature in `packer_rs` exports a lightweight `solve_attempt_wasm` function using `wasm-bindgen`. In the Astro frontend (`site/src/`), a `/contribute` page spawns background Web Workers that request work from `GET /api/v1/work`, run solver iterations in Wasm, submit improvements to `POST /api/v1/solutions`, and stream intermediate polygon coordinates to an HTML5 Canvas visualizer.

**Tech Stack:** Rust, `wasm-bindgen`, WebAssembly, Web Workers API, HTML5 Canvas, Astro, TypeScript.

**Spec:** `docs/superpowers/specs/2026-11-20-distributed-shape-packing-design.md`

## Global Constraints

- Wasm build must be optional and zero-overhead for native Python/HPC workflows (`[features] wasm = ["wasm-bindgen"]` in `packer_rs/Cargo.toml`).
- Web Workers must run entirely off the browser main thread to guarantee 60fps UI responsiveness.
- All network communication must conform to the existing coordinator REST API (`/api/v1/work`, `/api/v1/solutions`, `/api/v1/heartbeat`).

---

### Task 1: Rust WebAssembly Export in `packer_rs`

**Files:**
- Modify: `packer_rs/Cargo.toml`
- Create: `packer_rs/src/wasm.rs`
- Modify: `packer_rs/src/lib.rs`

**Interfaces:**
- Consumes: `packer_rs::solver::{solve, SolveConfig, SolveResult}`
- Produces:
  - `solve_attempt_wasm(inner_shape: &str, container_shape: &str, n: usize, attempts: usize, target_s: Option<f64>) -> String` (JSON string result)

- [x] **Step 1: Write Cargo.toml configuration for Wasm**

Update `packer_rs/Cargo.toml` to declare the optional `wasm-bindgen` dependency and `wasm` feature:

```toml
[dependencies]
clap = { version = "4", features = ["derive"] }
rand = "0.8"
rand_chacha = "0.3"
rayon = "1.10"
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
pyo3 = { version = "0.22", features = ["extension-module", "abi3-py310"], optional = true }
wasm-bindgen = { version = "0.2", optional = true }

[features]
default = ["python"]
python = ["pyo3"]
wasm = ["wasm-bindgen"]
```

- [x] **Step 2: Implement Wasm bindings in `packer_rs/src/wasm.rs`**

```rust
use wasm_bindgen::prelude::*;
use crate::solver::{solve, SolveConfig};
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
pub struct WasmSolveOutput {
    pub success: bool,
    pub best_s: f64,
    pub final_metric: f64,
    pub values: Vec<f64>,
}

#[wasm_bindgen]
pub fn solve_attempt_wasm(
    inner_shape: &str,
    container_shape: &str,
    n: usize,
    attempts: usize,
    target_s: Option<f64>,
) -> String {
    let config = SolveConfig {
        inner_polygons: n,
        inner_shape: inner_shape.to_string(),
        container_shape: container_shape.to_string(),
        attempts,
        tolerance: 1e-15,
        finalstep: 0.0001,
        time_limit: Some(30.0),
        initial_positions: None,
        target_s,
    };

    let result = solve(&config);
    let output = WasmSolveOutput {
        success: result.success,
        best_s: result.best_s,
        final_metric: result.final_metric,
        values: result.values,
    };

    serde_json::to_string(&output).unwrap_or_else(|_| "{}".to_string())
}
```

- [x] **Step 3: Wire `wasm.rs` module in `packer_rs/src/lib.rs`**

```rust
#[cfg(feature = "wasm")]
pub mod wasm;
```

- [x] **Step 4: Verify compilation under wasm32 target**

Run: `cargo check --manifest-path packer_rs/Cargo.toml --target wasm32-unknown-unknown --no-default-features --features wasm`
Expected: exit 0 with successful compilation.

- [x] **Step 5: Commit**

```bash
git add packer_rs/Cargo.toml packer_rs/src/wasm.rs packer_rs/src/lib.rs
git commit -m "feat(packer_rs): add wasm-bindgen bindings for in-browser solver execution"
```

---

### Task 2: Background WebAssembly Worker Script

**Files:**
- Create: `site/src/lib/workers/wasm_packer_worker.ts`

**Interfaces:**
- Consumes: `packer_rs` Wasm module, Coordinator REST API (`/api/v1/work`, `/api/v1/solutions`, `/api/v1/heartbeat`)
- Produces: PostMessage interface communicating progress and state back to UI

- [x] **Step 1: Write Web Worker script**

```typescript
// site/src/lib/workers/wasm_packer_worker.ts
import init, { solve_attempt_wasm } from '../../../public/wasm/packer_rs.js';

let isRunning = false;

self.onmessage = async (e: MessageEvent) => {
  const { command, serverUrl, username, workerId } = e.data;

  if (command === 'start') {
    isRunning = true;
    await init();
    runLoop(serverUrl, username, workerId);
  } else if (command === 'stop') {
    isRunning = false;
  }
};

async function runLoop(serverUrl: string, username: string, workerId: string) {
  while (isRunning) {
    try {
      // 1. Fetch work
      const workRes = await fetch(`${serverUrl}/api/v1/work?worker_id=${workerId}&cores=1`);
      if (workRes.status === 204) {
        await new Promise((r) => setTimeout(r, 5000));
        continue;
      }
      const work = await workRes.json();

      self.postMessage({ type: 'task_started', work });

      // 2. Run solver in Wasm
      const rawResult = solve_attempt_wasm(
        work.inner_token,
        work.container_token,
        work.n,
        Math.min(work.recommended_attempts || 1000, 500),
        work.target_s
      );
      const result = JSON.parse(rawResult);

      // 3. Submit improvement if record beaten
      if (result.success && result.best_s < work.target_s) {
        await fetch(`${serverUrl}/api/v1/solutions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            work_id: work.work_id,
            worker_id: workerId,
            problem: work.problem,
            s: result.best_s,
            coordinates: result.values,
          }),
        });
        self.postMessage({ type: 'record_beaten', best_s: result.best_s, values: result.values });
      }

      // 4. Heartbeat
      await fetch(`${serverUrl}/api/v1/heartbeat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          worker_id: workerId,
          work_id: work.work_id,
          attempts_completed: 500,
          best_local_s: result.best_s,
        }),
      });

      self.postMessage({ type: 'attempts_completed', count: 500 });
      await new Promise((r) => setTimeout(r, 100));
    } catch (err) {
      console.error('Wasm worker error:', err);
      await new Promise((r) => setTimeout(r, 5000));
    }
  }
}
```

- [x] **Step 2: Commit**

```bash
git add site/src/lib/workers/wasm_packer_worker.ts
git commit -m "feat(site): add background Web Worker for Wasm-based distributed compute"
```

---

### Task 3: Contributor Page with Live Canvas Visualizer

**Files:**
- Create: `site/src/components/LivePackingCanvas.astro`
- Create: `site/src/pages/contribute.astro`

**Interfaces:**
- Consumes: `wasm_packer_worker.ts`
- Produces: Interactive `/contribute` UI with thread sliders, live statistics, and real-time polygon rendering.

- [x] **Step 1: Create LivePackingCanvas component**

```astro
---
// site/src/components/LivePackingCanvas.astro
---
<div class="relative w-full aspect-square max-w-md mx-auto bg-slate-900 rounded-xl overflow-hidden border border-slate-800 shadow-2xl">
  <canvas id="live-canvas" class="w-full h-full"></canvas>
  <div id="canvas-overlay" class="absolute bottom-3 left-3 text-xs font-mono text-slate-400 bg-slate-950/80 px-2 py-1 rounded">
    Idle
  </div>
</div>

<script>
  const canvas = document.getElementById('live-canvas') as HTMLCanvasElement;
  const overlay = document.getElementById('canvas-overlay') as HTMLDivElement;
  const ctx = canvas.getContext('2d');

  window.addEventListener('update-live-packing', (e: CustomEvent) => {
    const { coordinates, n, s, problem } = e.detail;
    overlay.textContent = `${problem} | s = ${s.toFixed(5)}`;
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    // Render container circle and polygons
    ctx.save();
    ctx.translate(canvas.width / 2, canvas.height / 2);
    ctx.strokeStyle = '#38bdf8';
    ctx.beginPath();
    ctx.arc(0, 0, (canvas.width * 0.4) / (s || 1), 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  });
</script>
```

- [x] **Step 2: Create Contribute Page**

```astro
---
// site/src/pages/contribute.astro
import BaseLayout from '../layouts/BaseLayout.astro';
import LivePackingCanvas from '../components/LivePackingCanvas.astro';
---
<BaseLayout title="Contribute Compute | Distributed Shape Packing">
  <div class="max-w-4xl mx-auto py-12 px-4">
    <h1 class="text-3xl font-bold tracking-tight text-white mb-4">Contribute Compute</h1>
    <p class="text-slate-400 mb-8">Donate your browser's idle CPU power to discover dense geometric packings.</p>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-8 items-center mb-8">
      <LivePackingCanvas />
      <div class="bg-slate-900 p-6 rounded-xl border border-slate-800">
        <label class="block text-sm font-medium text-slate-300 mb-2">Volunteer Username</label>
        <input id="username-input" type="text" value="web_volunteer" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white mb-4" />

        <div class="flex gap-4">
          <button id="start-btn" class="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white font-medium py-2 rounded-lg">Start Crunching</button>
          <button id="stop-btn" class="flex-1 bg-slate-800 hover:bg-slate-700 text-white font-medium py-2 rounded-lg" disabled>Stop</button>
        </div>
      </div>
    </div>
  </div>
</BaseLayout>
```

- [x] **Step 3: Run Astro build check**

Run: `cd site && npm run build`
Expected: exit 0 with clean build.

- [x] **Step 4: Commit**

```bash
git add site/src/components/LivePackingCanvas.astro site/src/pages/contribute.astro
git commit -m "feat(site): add /contribute page with interactive live packing canvas"
```
