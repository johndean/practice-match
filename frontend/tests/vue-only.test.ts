import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const FRONTEND = join(import.meta.dirname, '..');
const SRC = join(FRONTEND, 'src');
const DIST = join(FRONTEND, 'dist', '_app');

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

// Global Constraint (c) — John, 2026-09-06: "convert to vue.js zero-gaps zero-regression".
// MarketMapV3.jsx and the rest of the handoff's React files are reference material to PORT,
// never to import or ship. convert-dc.mjs is the only path from the design file to Vue.
describe('the app is Vue-only', () => {
  it('no file under src/ imports react, react-dom or a .jsx module', () => {
    const offenders: string[] = [];
    for (const f of walk(SRC).filter((f) => /\.(vue|ts|js)$/.test(f))) {
      const src = readFileSync(f, 'utf8');
      if (/\bfrom\s+['"]react(-dom)?(\/[^'"]*)?['"]/.test(src)) offenders.push(`${relative(SRC, f)}: react import`);
      // A side-effect import (`import 'react';`) and a dynamic one (`import('react')`) both
      // bundle React without the word `from` anywhere near it.
      if (/\bimport\s+['"]react(-dom)?(\/[^'"]*)?['"]/.test(src)) offenders.push(`${relative(SRC, f)}: bare react import`);
      if (/\bimport\(\s*['"]react(-dom)?(\/[^'"]*)?['"]\s*\)/.test(src)) offenders.push(`${relative(SRC, f)}: dynamic react import`);
      if (/\brequire\(\s*['"]react(-dom)?['"]\s*\)/.test(src)) offenders.push(`${relative(SRC, f)}: react require`);
      if (/\bfrom\s+['"][^'"]+\.jsx['"]/.test(src)) offenders.push(`${relative(SRC, f)}: .jsx import`);
      if (/\bimport\(\s*['"][^'"]+\.jsx['"]\s*\)/.test(src)) offenders.push(`${relative(SRC, f)}: dynamic .jsx import`);
    }
    expect(offenders).toEqual([]);
  });

  it('react is not a dependency of the app', () => {
    const pkg = JSON.parse(readFileSync(join(FRONTEND, 'package.json'), 'utf8')) as { dependencies: Record<string, string>; devDependencies: Record<string, string> };
    expect(Object.keys(pkg.dependencies)).not.toContain('react');
    expect(Object.keys(pkg.dependencies)).not.toContain('react-dom');
    expect(Object.keys(pkg.devDependencies)).not.toContain('react');
    expect(Object.keys(pkg.devDependencies)).not.toContain('react-dom');
  });

  it('the built bundle carries no React runtime', () => {
    const js = readdirSync(DIST).filter((f) => f.endsWith('.js'));
    expect(js.length, 'no built bundle to check — run npm run build first').toBeGreaterThan(0);
    const offenders = js.filter((f) => {
      const text = readFileSync(join(DIST, f), 'utf8');
      // The first three markers are react-dom-centric; the element symbol is React itself, so
      // a bundled plain `react` (no DOM renderer) is caught too, minified either way.
      return text.includes('__REACT_DEVTOOLS_GLOBAL_HOOK__') || text.includes('react-dom')
        || /\breact\.production\.min\b/.test(text)
        || text.includes('Symbol.for("react.') || text.includes("Symbol.for('react.")
        || /\breact\.element\b/.test(text);
    });
    expect(offenders).toEqual([]);
  });
});
