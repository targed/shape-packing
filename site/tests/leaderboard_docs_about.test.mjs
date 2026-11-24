import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const siteDir = path.resolve(__dirname, '..');

describe('Leaderboard, Docs Hub & About Pages (Task 7)', () => {
  const leaderboardPagePath = path.join(siteDir, 'src', 'pages', 'leaderboard.astro');
  const leaderboardTablePath = path.join(siteDir, 'src', 'components', 'LeaderboardTable.astro');
  const docsPagePath = path.join(siteDir, 'src', 'pages', 'docs.astro');
  const docSlugPagePath = path.join(siteDir, 'src', 'pages', 'docs', '[...slug].astro');
  const aboutPagePath = path.join(siteDir, 'src', 'pages', 'about.astro');

  const task7Files = [
    leaderboardPagePath,
    leaderboardTablePath,
    docsPagePath,
    docSlugPagePath,
    aboutPagePath,
  ];

  it('leaderboard.astro includes brandmark badge and live cluster telemetry', () => {
    const content = fs.readFileSync(leaderboardPagePath, 'utf-8');

    // Brandmark badge
    assert.ok(
      content.includes('bg-surface-elevated text-blueprint-light border border-hairline rounded-md text-xs font-mono'),
      'Header includes architectural volunteer grid badge'
    );
    assert.ok(content.includes('Distributed Volunteer Grid'), 'Mentions Distributed Volunteer Grid');

    // LiveClusterStats component
    assert.ok(content.includes('<LiveClusterStats'), 'Mounts LiveClusterStats component');
    assert.ok(content.includes('<LeaderboardTable'), 'Mounts LeaderboardTable component');

    // No animate-pulse
    assert.ok(!content.includes('animate-pulse'), 'No animate-pulse in leaderboard header');
  });

  it('LeaderboardTable.astro satisfies architectural plate aesthetic and high-contrast typography', () => {
    const content = fs.readFileSync(leaderboardTablePath, 'utf-8');

    // Table container
    assert.ok(
      content.includes('bg-surface') && content.includes('border-hairline') && content.includes('rounded-lg'),
      'Table container styled with bg-surface border border-hairline rounded-lg'
    );

    // Refresh button
    assert.ok(
      content.includes('bg-surface-elevated hover:bg-surface-hover text-slate-300 border border-hairline rounded-md font-mono text-xs'),
      'Refresh button styled with bg-surface-elevated hover:bg-surface-hover text-slate-300 border border-hairline rounded-md font-mono text-xs'
    );

    // Monospace columns
    assert.ok(content.includes('font-mono'), 'Uses font-mono');
    assert.ok(content.includes('w-2 h-2 rounded-md bg-verify'), 'Volunteer indicator dot uses w-2 h-2 rounded-md bg-verify');

    // Clean badges without medal emojis
    assert.ok(content.includes('#1') && content.includes('#2') && content.includes('#3'), 'Renders clean badges #1, #2, #3');
    assert.ok(!content.includes('(Gold)') && !content.includes('(Silver)') && !content.includes('(Bronze)'), 'No medal text');
  });

  it('docs.astro and docs/[...slug].astro implement technical documentation cards and high-contrast prose', () => {
    const docsContent = fs.readFileSync(docsPagePath, 'utf-8');

    // Technical docs card styling
    assert.ok(
      docsContent.includes('bg-surface border border-hairline hover:border-blueprint/50'),
      'Docs cards use bg-surface border border-hairline hover:border-blueprint/50'
    );
    assert.ok(
      docsContent.includes('font-mono text-[10px] uppercase tracking-wider text-blueprint-light bg-surface-elevated border border-hairline px-2 py-0.5 rounded-md'),
      'Category badges use architectural pill with blueprint-light on surface-elevated'
    );
    assert.ok(!docsContent.toLowerCase().includes('diataxis'), 'Zero mentions of Diataxis in docsContent');

    const slugContent = fs.readFileSync(docSlugPagePath, 'utf-8');

    // Breadcrumbs
    assert.ok(slugContent.includes('Docs') && slugContent.includes('/'), 'Includes breadcrumbs Docs / <Doc Title>');

    // High-contrast prose typography
    assert.ok(slugContent.includes('prose-headings:font-display'), 'Prose headings use font-display');
    assert.ok(slugContent.includes('prose-code:font-mono'), 'Prose code uses font-mono');
    assert.ok(slugContent.includes('Back to Docs Hub'), 'Includes Back to Docs Hub link');
    assert.ok(!slugContent.toLowerCase().includes('diataxis'), 'Zero mentions of Diataxis in slugContent');
  });

  it('about.astro contains structured architectural plates for Purpose, Notice, and Platform Guide', () => {
    const content = fs.readFileSync(aboutPagePath, 'utf-8');

    // Project Purpose plate
    assert.ok(
      content.includes('bg-surface border border-hairline rounded-lg p-6'),
      'Purpose plate uses bg-surface border border-hairline rounded-lg p-6'
    );
    assert.ok(content.includes('Project Purpose'), 'Includes Project Purpose heading');

    // Scientific Reference & Use Notice plate
    assert.ok(
      content.includes('bg-surface border border-blueprint/30 rounded-lg p-6'),
      'Notice plate uses bg-surface border border-blueprint/30 rounded-lg p-6'
    );
    assert.ok(content.includes('Scientific Reference &amp; Use Notice') || content.includes('Scientific Reference & Use Notice'), 'Includes Scientific Reference notice heading');
    assert.ok(content.includes('Erich Friedman'), 'Cites Erich Friedman');

    // How to Use This Platform plate
    assert.ok(content.includes('How to Use This Platform'), 'Includes How to Use This Platform heading');
    assert.ok(content.includes('Results Explorer'), 'Covers Results Explorer');
    assert.ok(content.includes('Volunteer Contributor Grid'), 'Covers Volunteer Grid');
  });

  it('adheres strictly to the zero emoji constraint across all Task 7 files', () => {
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;

    for (const filePath of task7Files) {
      const content = fs.readFileSync(filePath, 'utf-8');
      const hasEmoji = emojiRegex.test(content);
      assert.strictEqual(
        hasEmoji,
        false,
        `File ${path.basename(filePath)} must contain zero emojis`
      );
    }
  });

  it('eradicates all em dashes across all Task 7 files', () => {
    const emDashRegex = /[\u2013\u2014]/;

    for (const filePath of task7Files) {
      const content = fs.readFileSync(filePath, 'utf-8');
      const hasEmDash = emDashRegex.test(content);
      assert.strictEqual(
        hasEmDash,
        false,
        `File ${path.basename(filePath)} must contain zero em/en dashes`
      );
    }
  });

  it('enforces 3-tier radius scale (rounded-md, rounded-lg, rounded-xl) with no rounded-2xl or rounded-full', () => {
    for (const filePath of task7Files) {
      const content = fs.readFileSync(filePath, 'utf-8');

      assert.strictEqual(
        content.includes('rounded-2xl'),
        false,
        `File ${path.basename(filePath)} must not use rounded-2xl`
      );
      assert.strictEqual(
        content.includes('rounded-full'),
        false,
        `File ${path.basename(filePath)} must not use rounded-full`
      );
      assert.strictEqual(
        content.includes('shadow-xl'),
        false,
        `File ${path.basename(filePath)} must not use shadow-xl`
      );
    }
  });
});
