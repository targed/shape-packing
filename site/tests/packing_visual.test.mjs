import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  BLUEPRINT_PALETTE,
  generatePackingSvgElements,
} from '../src/lib/visualization/render_packing.ts';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const siteDir = path.resolve(__dirname, '..');

describe('Architectural Visualization Plate (Task 2)', () => {
  it('render_packing.ts exports cohesive blueprint palette matching spec', () => {
    assert.deepEqual(BLUEPRINT_PALETTE, [
      '#38bdf8', // cyan
      '#0284c7', // sky
      '#2563eb', // cobalt
      '#818cf8', // slate blue
      '#f59e0b', // cadmium
      '#14b8a6', // teal
      '#10b981', // emerald
    ]);
  });

  it('generatePackingSvgElements returns bounding box metrics (minX, maxX, minY, maxY, spanX, spanY)', () => {
    const mockSolution = {
      N: 2,
      S: 2.5,
      final_metric: 2.5,
      values: [0, 0, 0, 1, 1, 0],
      container_token: 'CIRCLE',
      inner_token: 'CIRCLE',
    };

    const res = generatePackingSvgElements(mockSolution);
    assert.ok(res, 'SVG data generated');
    assert.equal(typeof res.minX, 'number');
    assert.equal(typeof res.maxX, 'number');
    assert.equal(typeof res.minY, 'number');
    assert.equal(typeof res.maxY, 'number');
    assert.equal(typeof res.spanX, 'number');
    assert.equal(typeof res.spanY, 'number');
    assert.equal(typeof res.padding, 'number');

    assert.ok(res.spanX > 0, 'spanX must be positive');
    assert.ok(res.spanY > 0, 'spanY must be positive');
    assert.equal(res.spanX, res.maxX - res.minX);
    assert.equal(res.spanY, res.maxY - res.minY);
  });

  it('PackingVisual.astro satisfies architectural plate aesthetic and zero emoji constraint', () => {
    const visualPath = path.join(siteDir, 'src', 'components', 'PackingVisual.astro');
    const content = fs.readFileSync(visualPath, 'utf-8');

    // Architectural plate container styling
    assert.ok(content.includes('bg-surface'), 'Uses bg-surface');
    assert.ok(content.includes('border-hairline'), 'Uses border-hairline');
    assert.ok(content.includes('rounded-lg'), 'Uses rounded-lg');
    assert.ok(content.includes('p-3.5'), 'Uses p-3.5');
    assert.ok(content.includes('space-y-2.5'), 'Uses space-y-2.5');

    // Internal stage
    assert.ok(content.includes('bg-canvas'), 'Stage uses bg-canvas');
    assert.ok(content.includes('rounded-md'), 'Stage uses rounded-md');

    // Origin crosshairs
    assert.ok(content.includes('crosshairs'), 'Contains crosshairs group');
    assert.ok(content.includes('y1="0"'), 'Horizontal crosshair on y=0');
    assert.ok(content.includes('x1="0"'), 'Vertical crosshair on x=0');

    // Container boundary & shape opacity
    assert.ok(content.includes('stroke-dasharray="0.1,0.1"'), 'Container dashed stroke');
    assert.ok(content.includes('fill-opacity="0.45"'), 'Shape clean fill opacity 0.45');

    // Footer metrics & tokens
    assert.ok(content.includes('text-blueprint-light'), 'N formatted with text-blueprint-light');
    assert.ok(content.includes('text-verify-light'), 'Metric formatted with text-verify-light');

    // Clean Export SVG button
    assert.ok(content.includes('export-svg-btn'), 'Has export-svg-btn class');
    assert.ok(content.includes('Export SVG'), 'Button text Export SVG');
    assert.ok(content.includes('data-filename'), 'Has download filename');

    // Zero emojis check
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;
    assert.ok(!emojiRegex.test(content), 'PackingVisual.astro should contain no emojis');
  });

  it('supports curved SVG arc paths (SEMICIRCLE, QUADRANT) and canonical quad polygons centered cleanly', () => {
    const semiRes = generatePackingSvgElements({
      N: 1,
      S: 2.0,
      final_metric: 2.0,
      values: [0, 1.0, 0],
      container_token: 'SEMICIRCLE',
      inner_token: 'CIRCLE',
    });
    assert.ok(semiRes, 'Semicircle SVG data generated');
    assert.ok(semiRes.containerArcPath && semiRes.containerArcPath.includes('A '), 'Semicircle produces SVG arc path');
    // Upper half-disk y in [0, S] -> SVG y in [-S, 0]; viewBox should frame [-2, 0] symmetrically without wasting half canvas
    assert.ok(semiRes.minY >= -2.1 && semiRes.maxY <= 0.1, `Expected semicircle bounds in upper half SVG, got [${semiRes.minY}, ${semiRes.maxY}]`);

    const quadRes = generatePackingSvgElements({
      N: 1,
      S: 1 + Math.SQRT2,
      final_metric: 1 + Math.SQRT2,
      values: [1.0, 1.0, 0],
      container_token: 'QUADRANT',
      inner_token: 'CIRCLE',
    });
    assert.ok(quadRes && quadRes.containerArcPath && quadRes.containerArcPath.includes('L '), 'Quadrant produces SVG arc+corner path');

    const rhomRes = generatePackingSvgElements({
      N: 1,
      S: 4 / Math.sqrt(3),
      final_metric: 4 / Math.sqrt(3),
      values: [0, 0, 0],
      container_token: 'RHOMBUS',
      inner_token: 'CIRCLE',
    });
    assert.ok(rhomRes && rhomRes.containerVertices && rhomRes.containerVertices.length === 4, 'Rhombus has 4 vertices');
  });
});
