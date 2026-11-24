import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const siteDir = path.resolve(__dirname, '..');

describe('Results Explorer & Geometric Badges Table (Task 4)', () => {
  const resultsPagePath = path.join(siteDir, 'src', 'pages', 'results.astro');
  const resultsTablePath = path.join(siteDir, 'src', 'components', 'ResultsTable.astro');
  const shapeBadgePath = path.join(siteDir, 'src', 'lib', 'visualization', 'shape_badge.ts');

  it('results.astro contains instant quick-filter tabs for all, NEW_BEST, proved_optimal, and priority', () => {
    const content = fs.readFileSync(resultsPagePath, 'utf-8');

    assert.ok(content.includes('data-tab="all"'), 'Includes All tab');
    assert.ok(content.includes('data-tab="NEW_BEST"'), 'Includes Records Broken tab');
    assert.ok(content.includes('data-tab="proved_optimal"'), 'Includes Proved Optimal tab');
    assert.ok(content.includes('data-tab="priority"'), 'Includes Priority Targets tab');
    assert.ok(content.includes('quick-filter-tab'), 'Includes quick-filter-tab class');
    assert.ok(content.includes('setActiveTab'), 'Includes tab switcher logic in script');
  });

  it('ResultsTable.astro includes mini SVG geometric shape badges and imports shape_badge', () => {
    const content = fs.readFileSync(resultsTablePath, 'utf-8');

    assert.ok(content.includes('generateShapeBadgeSvg'), 'Imports or uses generateShapeBadgeSvg');
    assert.ok(content.includes('parseFamilySlug'), 'Imports or uses parseFamilySlug');
    assert.ok(content.includes('badgeSvg'), 'Generates badgeSvg for each row');
  });

  it('ResultsTable.astro includes instant solution preview hover popover and trigger', () => {
    const content = fs.readFileSync(resultsTablePath, 'utf-8');

    assert.ok(content.includes('solution-hover-popover'), 'Includes popover container id');
    assert.ok(content.includes('solution-popover-trigger'), 'Includes solution trigger class');
    assert.ok(content.includes('data-solution'), 'Includes data-solution attribute');
    assert.ok(content.includes('data-priority'), 'Includes data-priority attribute');
    assert.ok(content.includes('(0, 0)'), 'Displays coordinate origin');
    assert.ok(content.includes('popover-dimensions'), 'Includes dimensions container');
  });

  it('ResultsTable.astro and results.astro adhere to zero emoji constraint', () => {
    const resultsContent = fs.readFileSync(resultsPagePath, 'utf-8');
    const tableContent = fs.readFileSync(resultsTablePath, 'utf-8');
    const badgeContent = fs.readFileSync(shapeBadgePath, 'utf-8');

    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;
    assert.ok(!emojiRegex.test(resultsContent), 'results.astro must not contain emojis');
    assert.ok(!emojiRegex.test(tableContent), 'ResultsTable.astro must not contain emojis');
    assert.ok(!emojiRegex.test(badgeContent), 'shape_badge.ts must not contain emojis');
  });

  it('ResultsTable.astro and results.astro eradicate all em dashes', () => {
    const resultsContent = fs.readFileSync(resultsPagePath, 'utf-8');
    const tableContent = fs.readFileSync(resultsTablePath, 'utf-8');

    assert.ok(!resultsContent.includes('—'), 'results.astro must not contain —');
    assert.ok(!resultsContent.includes('&mdash;'), 'results.astro must not contain &mdash;');
    assert.ok(!tableContent.includes('—'), 'ResultsTable.astro must not contain —');
    assert.ok(!tableContent.includes('&mdash;'), 'ResultsTable.astro must not contain &mdash;');
  });

  it('enforces 3-tier radius scale (rounded-md, rounded-lg, rounded-xl) with no rounded-full or rounded-2xl', () => {
    const resultsContent = fs.readFileSync(resultsPagePath, 'utf-8');
    const tableContent = fs.readFileSync(resultsTablePath, 'utf-8');

    assert.ok(!resultsContent.includes('rounded-full'), 'results.astro should not contain rounded-full');
    assert.ok(!resultsContent.includes('rounded-2xl'), 'results.astro should not contain rounded-2xl');
    assert.ok(!tableContent.includes('rounded-full'), 'ResultsTable.astro should not contain rounded-full');
    assert.ok(!tableContent.includes('rounded-2xl'), 'ResultsTable.astro should not contain rounded-2xl');
  });

  it('removes animate-pulse from ResultsTable.astro', () => {
    const tableContent = fs.readFileSync(resultsTablePath, 'utf-8');
    assert.ok(!tableContent.includes('animate-pulse'), 'ResultsTable.astro must not contain animate-pulse');
  });
});
