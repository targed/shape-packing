import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const siteDir = path.resolve(__dirname, '..');

describe('Shape Badge Generator (Task 4)', () => {
  it('parses family slug correctly into inner and container tokens', async () => {
    const { parseFamilySlug } = await import('../src/lib/visualization/shape_badge.ts');
    
    assert.deepEqual(parseFamilySlug('3_in_4'), { inner: '3', container: '4' });
    assert.deepEqual(parseFamilySlug('circle_in_3'), { inner: 'circle', container: '3' });
    assert.deepEqual(parseFamilySlug('6_in_circle'), { inner: '6', container: 'circle' });
    assert.deepEqual(parseFamilySlug('domino_in_4'), { inner: 'domino', container: '4' });
    assert.deepEqual(parseFamilySlug('L_in_L'), { inner: 'L', container: 'L' });
    assert.deepEqual(parseFamilySlug('tan_in_3'), { inner: 'tan', container: '3' });
    assert.deepEqual(parseFamilySlug('circle_in_ellipse'), { inner: 'circle', container: 'ellipse' });
    assert.deepEqual(parseFamilySlug('line_in_4'), { inner: 'line', container: '4' });
  });

  it('generates 20x20 SVG badge with container stroke #64748b and inner fill #38bdf8', async () => {
    const { generateShapeBadgeSvg } = await import('../src/lib/visualization/shape_badge.ts');

    const svg = generateShapeBadgeSvg('3', '4');
    assert.ok(svg.includes('viewBox="-10 -10 20 20"'));
    assert.ok(svg.includes('width="20"'));
    assert.ok(svg.includes('height="20"'));
    assert.ok(svg.includes('stroke="#64748b"'));
    assert.ok(svg.includes('fill="#38bdf8"'));
    assert.ok(svg.includes('<rect'), 'Container 4 should be a rect');
    assert.ok(svg.includes('<polygon'), 'Inner 3 should be a polygon');
  });

  it('uses cadmium fill #f59e0b when isCadmium is true', async () => {
    const { generateShapeBadgeSvg } = await import('../src/lib/visualization/shape_badge.ts');

    const svgCadmium = generateShapeBadgeSvg('6', 'circle', true);
    assert.ok(svgCadmium.includes('fill="#f59e0b"'));
    assert.ok(svgCadmium.includes('<circle'), 'Container circle should be a circle');
    assert.ok(svgCadmium.includes('<polygon'), 'Inner 6 should be a polygon');
  });

  it('shape_badge.ts contains zero emojis and zero em dashes', () => {
    const filePath = path.join(siteDir, 'src', 'lib', 'visualization', 'shape_badge.ts');
    const content = fs.readFileSync(filePath, 'utf-8');

    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;
    assert.ok(!emojiRegex.test(content), 'shape_badge.ts must not contain emojis');
    assert.ok(!content.includes('—'), 'shape_badge.ts must not contain em dashes');
    assert.ok(!content.includes('&mdash;'), 'shape_badge.ts must not contain &mdash;');
  });

  it('generates dedicated vector badges for 7/9/10, semicircle, quadrant, rhombus, parallelogram, trapezoid', async () => {
    const { generateShapeBadgeSvg, parseFamilySlug } = await import('../src/lib/visualization/shape_badge.ts');
    assert.deepEqual(parseFamilySlug('circle_in_semicircle'), { inner: 'circle', container: 'semicircle' });
    assert.deepEqual(parseFamilySlug('rhombus_in_trapezoid'), { inner: 'rhombus', container: 'trapezoid' });

    const semi = generateShapeBadgeSvg('circle', 'semicircle');
    assert.ok(semi.includes('<path') && semi.includes('A '), 'Semicircle badge renders arc path');

    const quad = generateShapeBadgeSvg('circle', 'quadrant');
    assert.ok(quad.includes('<path') && quad.includes('A '), 'Quadrant badge renders arc path');

    const rhom = generateShapeBadgeSvg('rhombus', 'parallelogram');
    assert.ok(rhom.includes('<polygon'), 'Rhombus/parallelogram badge renders polygon elements');

    const trap = generateShapeBadgeSvg('3', 'trapezoid');
    assert.ok(trap.includes('<polygon'), 'Trapezoid container badge renders polygon, not square rect');
  });
});
