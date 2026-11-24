import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const siteDir = path.resolve(__dirname, '..');

describe('Shape Family Detail & Benchmark Curve Gallery (Task 5)', () => {
  const familyDetailPagePath = path.join(siteDir, 'src', 'pages', 'family', '[slug].astro');
  const familyIndexPagePath = path.join(siteDir, 'src', 'pages', 'family', 'index.astro');
  const benchmarkCurvePath = path.join(siteDir, 'src', 'components', 'BenchmarkCurve.astro');
  const shapeBadgePath = path.join(siteDir, 'src', 'lib', 'visualization', 'shape_badge.ts');

  it('shape_badge.ts exports getShapeBadgeSvg alias for generateShapeBadgeSvg', async () => {
    const shapeBadgeModule = await import('../src/lib/visualization/shape_badge.ts');
    assert.strictEqual(typeof shapeBadgeModule.getShapeBadgeSvg, 'function', 'getShapeBadgeSvg must be exported');
    assert.strictEqual(typeof shapeBadgeModule.generateShapeBadgeSvg, 'function', 'generateShapeBadgeSvg must be exported');
    const svg1 = shapeBadgeModule.getShapeBadgeSvg('3', '4');
    const svg2 = shapeBadgeModule.generateShapeBadgeSvg('3', '4');
    assert.strictEqual(svg1, svg2, 'Both methods should produce identical SVG output');
  });

  it('family/[slug].astro includes breadcrumbs, badges, benchmark curve, packing gallery, and spec drawer', () => {
    const content = fs.readFileSync(familyDetailPagePath, 'utf-8');

    // Breadcrumb
    assert.ok(content.includes('/results'), 'Includes breadcrumb link to /results');
    assert.ok(content.includes('family.slug'), 'Includes family slug in breadcrumb');

    // Shape badge
    assert.ok(content.includes('getShapeBadgeSvg') || content.includes('generateShapeBadgeSvg'), 'Integrates shape badge');
    assert.ok(content.includes('badgeSvg'), 'Renders badgeSvg');

    // Technical badges
    assert.ok(content.includes('familyProblems.length'), 'Displays total problems count');
    assert.ok(content.includes('proved_optimal_count'), 'Displays proved optimal count');
    assert.ok(content.includes('newBestCount') || content.includes('Records Broken'), 'Displays records broken count');

    // Container & Inner shape metadata
    assert.ok(content.includes('inner_shape'), 'Displays inner_shape');
    assert.ok(content.includes('container_shape'), 'Displays container_shape');

    // Benchmark curve
    assert.ok(content.includes('BenchmarkCurve'), 'Renders BenchmarkCurve component');

    // Packing visualizer gallery
    assert.ok(content.includes('PackingVisual'), 'Renders PackingVisual component');
    assert.ok(content.includes('solvedProblems'), 'Filters and renders solvedProblems');

    // Collapsible specification drawer
    assert.ok(content.includes('<details'), 'Uses collapsible <details> element');
    assert.ok(content.includes('<summary'), 'Uses <summary> trigger');
    assert.ok(content.includes('reqData.content'), 'Renders reqData.content');

    // ResultsTable
    assert.ok(content.includes('<ResultsTable'), 'Renders ResultsTable component');
  });

  it('family/index.astro includes 80 families header, search filter, and cards with shape badges', () => {
    const content = fs.readFileSync(familyIndexPagePath, 'utf-8');

    // Header & Summary badges
    assert.ok(content.includes('Problem Family Catalog'), 'Includes page title');
    assert.ok(content.includes('families.length'), 'Displays families count');

    // Instant search input
    assert.ok(content.includes('id="family-search"'), 'Includes family search input');
    assert.ok(content.includes('bg-surface-elevated'), 'Search input uses bg-surface-elevated');
    assert.ok(content.includes('border-hairline'), 'Search input uses border-hairline');
    assert.ok(content.includes('rounded-md'), 'Search input uses rounded-md');

    // Cards with shape badges
    assert.ok(content.includes('getShapeBadgeSvg') || content.includes('generateShapeBadgeSvg'), 'Uses shape badges on cards');
    assert.ok(content.includes('bg-surface border border-hairline hover:border-blueprint/50 rounded-lg p-5'), 'Uses required card styling');
  });

  it('BenchmarkCurve.astro renders SVG vector curves with Friedman reference, Solver series, and cadmium records', () => {
    const content = fs.readFileSync(benchmarkCurvePath, 'utf-8');

    // Both series
    assert.ok(content.includes('#64748b'), 'Friedman reference series stroke #64748b');
    assert.ok(content.includes('#0284c7'), 'Solver best series stroke #0284c7');
    assert.ok(content.includes('#f59e0b'), 'Cadmium points stroke/fill #f59e0b for NEW_BEST');
    assert.ok(content.includes('NEW_BEST'), 'Identifies NEW_BEST status');

    // Monospace axis labels and grid hairlines
    assert.ok(content.includes('font-mono'), 'Uses monospace labels');
    assert.ok(content.includes('grid-y') || content.includes('grid-x'), 'Includes grid hairlines');
    assert.ok(content.includes('Instances (N)'), 'Includes N-axis title');
    assert.ok(content.includes('Metric (s)'), 'Includes s-axis title');

    // Legend
    assert.ok(content.includes('Erich Friedman Reference'), 'Includes Friedman reference legend');
    assert.ok(content.includes('Solver Best Bound'), 'Includes Solver best bound legend');
    assert.ok(content.includes('New Record Broken') || content.includes('Record Broken'), 'Includes record broken legend');
  });

  it('adheres strictly to the zero emoji constraint across all Task 5 files', () => {
    const files = [familyDetailPagePath, familyIndexPagePath, benchmarkCurvePath, shapeBadgePath];
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;

    for (const f of files) {
      const content = fs.readFileSync(f, 'utf-8');
      assert.ok(!emojiRegex.test(content), `${path.basename(f)} must not contain emojis`);
    }
  });

  it('eradicates all em dashes across all Task 5 files', () => {
    const files = [familyDetailPagePath, familyIndexPagePath, benchmarkCurvePath, shapeBadgePath];

    for (const f of files) {
      const content = fs.readFileSync(f, 'utf-8');
      assert.ok(!content.includes('\u2014'), `${path.basename(f)} must not contain em dash (\\u2014)`);
      assert.ok(!content.includes('&mdash;'), `${path.basename(f)} must not contain &mdash;`);
    }
  });

  it('enforces 3-tier radius scale (rounded-md, rounded-lg, rounded-xl) with no rounded-full or rounded-2xl', () => {
    const files = [familyDetailPagePath, familyIndexPagePath, benchmarkCurvePath];

    for (const f of files) {
      const content = fs.readFileSync(f, 'utf-8');
      assert.ok(!content.includes('rounded-full'), `${path.basename(f)} should not contain rounded-full`);
      assert.ok(!content.includes('rounded-2xl'), `${path.basename(f)} should not contain rounded-2xl`);
    }
  });
});
