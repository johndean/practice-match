import { describe, expect, it } from 'vitest';
import { gzipSync } from 'node:zlib';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const DIST = join(import.meta.dirname, '..', 'dist', '_app');
const gz = (f: string) => gzipSync(readFileSync(join(DIST, f))).length / 1024;
const files = () => readdirSync(DIST).filter((f) => f.endsWith('.js'));

describe('bundle budgets (KB gzipped)', () => {
  it('main bundle ≤ 220', () => { expect(gz(files().find((f) => f.startsWith('index-'))!)).toBeLessThanOrEqual(220); });
  it('engine-leaflet ≤ 60, engine-google ≤ 12', () => {
    const l = files().find((f) => f.startsWith('engine-leaflet-')); const g = files().find((f) => f.startsWith('engine-google-'));
    if (l) expect(gz(l)).toBeLessThanOrEqual(60);
    if (g) expect(gz(g)).toBeLessThanOrEqual(12);
  });
  it('first-load JS ≤ 300', () => {
    const first = files().filter((f) => f.startsWith('index-') || f.startsWith('engine-leaflet-'));
    expect(first.reduce((s, f) => s + gz(f), 0)).toBeLessThanOrEqual(300);
  });
});
