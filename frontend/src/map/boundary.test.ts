import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const SRC = join(import.meta.dirname, '..');
const ALLOWED = [/^map\/engines\//, /^lib\/leaflet\.js$/, /^map\/testing\//];
function walk(d: string): string[] { return readdirSync(d).flatMap((n) => { const p = join(d, n); return statSync(p).isDirectory() ? walk(p) : [p]; }); }

describe('map engine import boundary (Map-engines spec §2.2)', () => {
  it('only src/map/engines/* and src/lib/leaflet.js touch Leaflet or window.L', () => {
    const offenders = walk(SRC).filter((f) => /\.(vue|js|ts)$/.test(f) && !f.endsWith('.test.ts')).filter((f) => {
      const rel = relative(SRC, f);
      if (ALLOWED.some((re) => re.test(rel))) return false;
      const s = readFileSync(f, 'utf8');
      return /from\s+['"]leaflet|require\(['"]leaflet|window\.L\b|\bL\.(map|tileLayer|marker|divIcon|circle|layerGroup|control)\(/.test(s);
    }).map((f) => relative(SRC, f));
    expect(offenders).toEqual([]);
  });
});
