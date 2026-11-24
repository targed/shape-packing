import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.resolve(__dirname, '..', 'src');

function getAllFiles(dir, extensions = ['.astro', '.ts', '.js', '.mjs', '.html']) {
  let files = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files = files.concat(getAllFiles(fullPath, extensions));
    } else if (extensions.includes(path.extname(entry.name))) {
      files.push(fullPath);
    }
  }
  return files;
}

describe('Global Quality & Anti-Slop Audit (Task 8)', () => {
  const allSourceFiles = getAllFiles(srcDir);

  it('guarantees absolute zero emojis across all site/src files', () => {
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;
    const failures = [];

    for (const f of allSourceFiles) {
      const content = fs.readFileSync(f, 'utf-8');
      if (emojiRegex.test(content)) {
        failures.push(path.relative(srcDir, f));
      }
    }

    assert.equal(failures.length, 0, `Files containing emojis: ${failures.join(', ')}`);
  });

  it('guarantees zero em dashes across all component and page templates', () => {
    const templateFiles = allSourceFiles.filter(f => f.endsWith('.astro'));
    const failures = [];

    for (const f of templateFiles) {
      const content = fs.readFileSync(f, 'utf-8');
      if (content.includes('\u2014') || content.includes('&mdash;')) {
        failures.push(path.relative(srcDir, f));
      }
    }

    assert.equal(failures.length, 0, `Template files containing em dashes: ${failures.join(', ')}`);
  });

  it('eradicates blurry card-soup drop shadows (shadow-xl, shadow-2xl)', () => {
    const templateFiles = allSourceFiles.filter(f => f.endsWith('.astro'));
    const failures = [];

    for (const f of templateFiles) {
      const content = fs.readFileSync(f, 'utf-8');
      if (content.includes('shadow-xl') || content.includes('shadow-2xl')) {
        failures.push(path.relative(srcDir, f));
      }
    }

    assert.equal(failures.length, 0, `Templates still containing shadow-xl or shadow-2xl: ${failures.join(', ')}`);
  });

  it('eradicates washed-out text-transparent text gradients in headers', () => {
    const templateFiles = allSourceFiles.filter(f => f.endsWith('.astro'));
    const failures = [];

    for (const f of templateFiles) {
      const content = fs.readFileSync(f, 'utf-8');
      if (content.includes('text-transparent bg-clip-text')) {
        failures.push(path.relative(srcDir, f));
      }
    }

    assert.equal(failures.length, 0, `Templates still containing washed-out text gradients: ${failures.join(', ')}`);
  });

  it('eradicates generic rounded-2xl cards across templates', () => {
    const templateFiles = allSourceFiles.filter(f => f.endsWith('.astro'));
    const failures = [];

    for (const f of templateFiles) {
      const content = fs.readFileSync(f, 'utf-8');
      if (content.includes('rounded-2xl')) {
        failures.push(path.relative(srcDir, f));
      }
    }

    assert.equal(failures.length, 0, `Templates still containing rounded-2xl: ${failures.join(', ')}`);
  });
});
