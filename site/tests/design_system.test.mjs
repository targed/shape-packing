import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const siteDir = path.resolve(__dirname, '..');

describe('Design System Foundations', () => {
  it('tailwind.config.mjs includes required design tokens', async () => {
    const configModule = await import('../tailwind.config.mjs');
    const config = configModule.default;
    const themeExtend = config.theme?.extend;

    assert.ok(themeExtend, 'theme.extend is defined');
    
    // Check colors
    assert.equal(themeExtend.colors.canvas, '#0b0f17');
    assert.equal(themeExtend.colors.surface.DEFAULT, '#111827');
    assert.equal(themeExtend.colors.surface.elevated, '#1a2234');
    assert.equal(themeExtend.colors.surface.hover, '#1e293b');
    assert.equal(themeExtend.colors.blueprint.DEFAULT, '#0284c7');
    assert.equal(themeExtend.colors.cadmium.DEFAULT, '#f59e0b');
    assert.equal(themeExtend.colors.verify.DEFAULT, '#10b981');
    assert.equal(themeExtend.colors.hairline, 'rgba(255, 255, 255, 0.08)');

    // Check fonts
    assert.ok(themeExtend.fontFamily.display[0].includes('Space Grotesk'));
    assert.ok(themeExtend.fontFamily.sans[0].includes('Plus Jakarta Sans'));
    assert.ok(themeExtend.fontFamily.mono[0].includes('IBM Plex Mono'));

    // Check border radii
    assert.equal(themeExtend.borderRadius.sm, '4px');
    assert.equal(themeExtend.borderRadius.md, '6px');
    assert.equal(themeExtend.borderRadius.lg, '8px');
    assert.equal(themeExtend.borderRadius.xl, '12px');
  });

  it('BaseLayout.astro includes Google Fonts and no emojis', () => {
    const baseLayoutPath = path.join(siteDir, 'src', 'layouts', 'BaseLayout.astro');
    const content = fs.readFileSync(baseLayoutPath, 'utf-8');

    // Google Fonts link
    assert.ok(content.includes('family=IBM+Plex+Mono'));
    assert.ok(content.includes('family=Plus+Jakarta+Sans'));
    assert.ok(content.includes('family=Space+Grotesk'));

    // Architectural theme elements
    assert.ok(content.includes('bg-canvas'));
    assert.ok(content.includes('border-hairline'));

    // Emoji check regex
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;
    assert.ok(!emojiRegex.test(content), 'BaseLayout.astro should not contain emojis');
  });

  it('LiveClusterStats.astro includes no emojis and uses hairline borders', () => {
    const statsPath = path.join(siteDir, 'src', 'components', 'LiveClusterStats.astro');
    const content = fs.readFileSync(statsPath, 'utf-8');

    assert.ok(content.includes('border-hairline'));
    assert.ok(content.includes('bg-surface'));

    // Emoji check regex
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;
    assert.ok(!emojiRegex.test(content), 'LiveClusterStats.astro should not contain emojis');
  });
});
