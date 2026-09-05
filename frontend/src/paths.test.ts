import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

describe('asset references', () => {
  it('uses absolute /assets and /ds paths only (Vite serves public/ at the root)', () => {
    const files = walk(import.meta.dirname).filter((f) => /\.(vue|js|ts)$/.test(f) && !f.endsWith('.test.ts'));
    const offenders: string[] = [];
    for (const f of files) {
      const src = readFileSync(f, 'utf8');
      const re = /["'(](assets|ds)\//g;
      let m: RegExpExecArray | null;
      while ((m = re.exec(src))) offenders.push(`${f}:${src.slice(0, m.index).split('\n').length}`);
    }
    expect(offenders).toEqual([]);
  });
});
