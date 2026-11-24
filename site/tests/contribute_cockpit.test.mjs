import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const siteDir = path.resolve(__dirname, '..');

describe('Volunteer Contributor Cockpit (Task 6)', () => {
  const contributePagePath = path.join(siteDir, 'src', 'pages', 'contribute.astro');
  const liveCanvasPath = path.join(siteDir, 'src', 'components', 'LivePackingCanvas.astro');

  it('contribute.astro includes dual-standing choice architecture cards with CLI box and unifying banner', () => {
    const content = fs.readFileSync(contributePagePath, 'utf-8');

    // Header badge
    assert.ok(
      content.includes('bg-surface-elevated text-verify-light border border-hairline'),
      'Header volunteer grid badge uses bg-surface-elevated and text-verify-light'
    );
    assert.ok(content.includes('Distributed Volunteer Grid'), 'Includes Distributed Volunteer Grid badge');

    // Option 1: Standalone Worker
    assert.ok(content.includes('Option 1: Standalone Worker (Fastest)'), 'Includes Option 1 card title');
    assert.ok(content.includes('Pure Rust Standalone Binary'), 'Option 1 mentions Pure Rust binary');
    assert.ok(content.includes('Rayon'), 'Option 1 mentions Rayon multi-threading');
    assert.ok(content.includes('./shape-packing-worker'), 'Option 1 includes CLI binary invocation');
    assert.ok(content.includes('edit'), 'Option 1 includes edit command');
    assert.ok(content.includes('reconfigure'), 'Option 1 includes reconfigure command');
    assert.ok(content.includes('autostart enable'), 'Option 1 includes autostart enable command');
    assert.ok(
      content.includes('bg-blueprint hover:bg-blueprint-dark text-white rounded-md font-semibold text-xs'),
      'Download button styled with bg-blueprint hover:bg-blueprint-dark text-white rounded-md font-semibold text-xs'
    );

    // Option 2: In-Browser Web Cruncher
    assert.ok(content.includes('Option 2: In-Browser Web Cruncher (Zero Install)'), 'Includes Option 2 card title');
    assert.ok(content.includes('Browser WebAssembly Engine'), 'Option 2 mentions WebAssembly engine');
    assert.ok(
      content.includes('bg-surface-elevated hover:bg-surface-hover text-verify-light border border-hairline rounded-md'),
      'Quick-jump button styled with bg-surface-elevated hover:bg-surface-hover text-verify-light border border-hairline rounded-md'
    );

    // Unifying Banner
    const expectedBannerText =
      'Both clients connect to the exact same coordinator grid, lease from the same problem queue, and contribute verified solutions to the public benchmark. They are complementary options.';
    assert.ok(
      content.includes(expectedBannerText),
      'Includes exact unifying architectural banner text'
    );
  });

  it('contribute.astro includes high-contrast controls, form inputs, telemetry cards, and monospace session log', () => {
    const content = fs.readFileSync(contributePagePath, 'utf-8');

    // Form inputs styled with bg-surface-elevated border border-hairline rounded-md text-xs font-mono text-slate-100
    assert.ok(content.includes('id="worker-username"'), 'Includes worker username input');
    assert.ok(content.includes('id="worker-server-url"'), 'Includes coordinator URL input');
    assert.ok(content.includes('id="worker-cores"'), 'Includes thread selection');
    assert.ok(content.includes('id="worker-batch-size"'), 'Includes max attempts selection');
    assert.ok(
      content.includes('bg-surface-elevated border border-hairline rounded-md px-3 py-2 text-xs font-mono text-slate-100'),
      'Inputs use bg-surface-elevated border border-hairline rounded-md text-xs font-mono text-slate-100'
    );

    // High-contrast start button
    assert.ok(
      content.includes('bg-verify hover:bg-emerald-600 text-white font-bold text-xs rounded-md') ||
      content.includes('bg-verify hover:bg-emerald-600 text-white font-bold'),
      'Start button uses high-contrast bg-verify hover:bg-emerald-600 text-white font-bold rounded-md'
    );
    assert.ok(content.includes('id="btn-start"'), 'Includes btn-start element');
    assert.ok(content.includes('id="btn-stop"'), 'Includes btn-stop element');

    // Telemetry stats
    assert.ok(content.includes('id="metric-attempts"'), 'Includes attempts telemetry counter');
    assert.ok(content.includes('id="metric-leases"'), 'Includes leases telemetry counter');
    assert.ok(content.includes('id="metric-records"'), 'Includes solutions verified / records telemetry counter');
    assert.ok(content.includes('id="metric-ping"'), 'Includes server ping indicator');

    // Monospace session activity log
    assert.ok(content.includes('id="worker-log"'), 'Includes worker-log element');
    assert.ok(content.includes('bg-canvas border border-hairline rounded-md'), 'Log box styled with bg-canvas and hairline border');
  });

  it('LivePackingCanvas.astro satisfies architectural oscilloscope canvas specifications', () => {
    const content = fs.readFileSync(liveCanvasPath, 'utf-8');

    // Container and stage styling
    assert.ok(
      content.includes('bg-surface border border-hairline rounded-lg p-3 space-y-2.5'),
      'Container styled with bg-surface border border-hairline rounded-lg p-3 space-y-2.5'
    );
    assert.ok(
      content.includes('bg-canvas border border-hairline rounded-md relative flex items-center justify-center overflow-hidden'),
      'Stage styled with bg-canvas border border-hairline rounded-md relative flex items-center justify-center overflow-hidden'
    );

    // Canvas rendering checks
    assert.ok(
      content.includes('rgba(255, 255, 255, 0.05)'),
      'Drafting coordinate grid lines rendered in rgba(255, 255, 255, 0.05)'
    );
    assert.ok(
      content.includes('rgba(255, 255, 255, 0.15)'),
      'Origin crosshairs rendered in rgba(255, 255, 255, 0.15)'
    );
    assert.ok(
      content.includes('BLUEPRINT_PALETTE'),
      'Imports and uses BLUEPRINT_PALETTE'
    );
    assert.ok(
      content.includes('"IBM Plex Mono", monospace'),
      'Canvas text rendered with IBM Plex Mono font'
    );

    // Overlays
    assert.ok(content.includes('id="canvas-status-label"'), 'Includes status label overlay');
    assert.ok(content.includes('id="canvas-status-dot"'), 'Includes status dot indicator');
    assert.ok(content.includes('id="canvas-problem-name"'), 'Includes active problem overlay');
    assert.ok(content.includes('id="canvas-scale-value"'), 'Includes current scale value overlay');
    assert.ok(content.includes('id="canvas-inspect-banner"'), 'Includes history inspect banner');
  });

  it('adheres strictly to the zero emoji constraint across all Task 6 files', () => {
    const files = [contributePagePath, liveCanvasPath];
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;

    for (const f of files) {
      const content = fs.readFileSync(f, 'utf-8');
      assert.ok(!emojiRegex.test(content), `${path.basename(f)} must not contain emojis`);
    }
  });

  it('eradicates all em dashes across all Task 6 files', () => {
    const files = [contributePagePath, liveCanvasPath];

    for (const f of files) {
      const content = fs.readFileSync(f, 'utf-8');
      assert.ok(!content.includes('\u2014'), `${path.basename(f)} must not contain em dash (\\u2014)`);
      assert.ok(!content.includes('&mdash;'), `${path.basename(f)} must not contain &mdash;`);
    }
  });

  it('enforces 3-tier radius scale (rounded-md, rounded-lg, rounded-xl) with no rounded-full or rounded-2xl', () => {
    const files = [contributePagePath, liveCanvasPath];

    for (const f of files) {
      const content = fs.readFileSync(f, 'utf-8');
      assert.ok(!content.includes('rounded-full'), `${path.basename(f)} should not contain rounded-full`);
      assert.ok(!content.includes('rounded-2xl'), `${path.basename(f)} should not contain rounded-2xl`);
    }
  });
});
