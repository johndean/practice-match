import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const CONFIG = join(fileURLToPath(new URL('.', import.meta.url)), 'playwright.config.ts');
const FLAG = '--disable-partial-raster';

// ---------------------------------------------------------------------------------------
// Task V17, review Minor 1. `capture-determinism.spec.ts` is the behavioural guard on the
// oracle's reproducibility, but it is PROBABILISTIC: at the measured ~13 % per-capture flip
// rate its ten loads catch a missing `--disable-partial-raster` about 75 % of the time per
// state. Deleting the flag — a merge, a "tidy the config" commit — would therefore reinstate
// V16's flake with no error most runs, which is the same silent class of failure the task
// exists to remove. This is the deterministic half of the pair: the flag's PRESENCE, in the
// one place it works from.
//
// It has to be `use.launchOptions` at the TOP level. Moved into a single project's `use`,
// the flag would still be "present" while the `reference` and `app` projects rasterised
// differently — which is worse than not having it, because then the oracle and the app
// disagree by exactly those pixels at `maxDiffPixels: 0`. So this asserts the nesting, not
// just the string.
// ---------------------------------------------------------------------------------------

/**
 * `src` with every comment blanked, character for character, so offsets still line up with
 * the original. Used to find the flag: an occurrence inside a comment must not count.
 */
function withoutComments(src: string): string {
  return blank(src, false);
}

/**
 * `src` with every comment AND every string/template literal blanked, offsets preserved.
 * Brace matching runs over this, so a `{` inside a comment, a quoted path or a template's
 * `${…}` can never throw the nesting off — `snapshotPathTemplate`'s `{testDir}` and the
 * projects' `` `http://localhost:${REF}` `` are both in this file.
 */
function skeleton(src: string): string {
  return blank(src, true);
}

/** The one scanner both of the above use. Anything blanked becomes a space; newlines stay. */
function blank(src: string, alsoStrings: boolean): string {
  const out = src.split('');
  const hide = (i: number) => { if (out[i] !== '\n') out[i] = ' '; };
  let i = 0;
  while (i < src.length) {
    const two = src.slice(i, i + 2);
    if (two === '//') {
      while (i < src.length && src[i] !== '\n') hide(i++);
      continue;
    }
    if (two === '/*') {
      const end = src.indexOf('*/', i + 2);
      const stop = end === -1 ? src.length : end + 2;
      while (i < stop) hide(i++);
      continue;
    }
    if (src[i] === "'" || src[i] === '"' || src[i] === '`') {
      const quote = src[i];
      const start = i;
      i += 1;
      while (i < src.length && src[i] !== quote) i += src[i] === '\\' ? 2 : 1;
      i = Math.min(i + 1, src.length);
      if (alsoStrings) for (let j = start; j < i; j++) hide(j);
      continue;
    }
    i += 1;
  }
  return out.join('');
}

/** `[start, end]` of the balanced pair opened by `src[open]`. `end` is the closing index. */
function matchPair(src: string, open: number): [number, number] {
  const close = src[open] === '{' ? '}' : ']';
  let depth = 0;
  for (let i = open; i < src.length; i++) {
    if (src[i] === src[open]) depth += 1;
    else if (src[i] === close) {
      depth -= 1;
      if (depth === 0) return [open, i];
    }
  }
  throw new Error(`unbalanced ${src[open]} at ${open} in playwright.config.ts`);
}

/**
 * The `[start, end]` of the block opened by the first `{`/`[` after `key:` — searching only
 * within `[from, to)` of the skeleton, and (when `atDepth` is given) only at that brace
 * depth, so the top-level `use:` is told apart from each project's own `use:`.
 */
function block(sk: string, key: string, from: number, to: number, atDepth?: number): [number, number] {
  const re = new RegExp(`\\b${key}\\s*:\\s*[{[]`, 'g');
  re.lastIndex = from;
  for (let m = re.exec(sk); m && m.index < to; m = re.exec(sk)) {
    const open = m.index + m[0].length - 1;
    if (atDepth === undefined || depthAt(sk, m.index) === atDepth) return matchPair(sk, open);
  }
  throw new Error(`no ${key}: block found in playwright.config.ts`);
}

/** How many `{` are open at `index` — 1 inside `defineConfig({ … })`'s own object. */
function depthAt(sk: string, index: number): number {
  let depth = 0;
  for (let i = 0; i < index; i++) {
    if (sk[i] === '{') depth += 1;
    else if (sk[i] === '}') depth -= 1;
  }
  return depth;
}

describe('playwright.config.ts pins Chromium\'s raster', () => {
  const src = readFileSync(CONFIG, 'utf8');
  const code = withoutComments(src);
  const sk = skeleton(src);

  it(`passes ${FLAG} to Chromium`, () => {
    expect(
      code,
      `playwright.config.ts no longer passes ${FLAG}. Chromium's partial raster redraws only ` +
      `the invalidated part of a compositor tile and reuses the rest, so the antialiasing of ` +
      `the Browse results rail's rounded card corners — which sit at fractional y offsets — ` +
      `comes out one grey level either way depending on which tiles fullPage's ` +
      `captureBeyondViewport pass invalidates. Without the flag the baselines written by ` +
      `reference-baselines.spec.ts stop being reproducible: header-1000-darwin.png flips ` +
      `between hashes in ~13 % of runs with no code change (V16), and header-1100 and browse ` +
      `flip with it. Restore it or record the ruling that removed it (Task V17).`
    ).toContain(FLAG);
  });

  it('carries it in the TOP-LEVEL use.launchOptions.args, so every project rasterises alike', () => {
    const flagAt = code.indexOf(FLAG);
    const [useStart, useEnd] = block(sk, 'use', 0, sk.length, 1);
    const [loStart, loEnd] = block(sk, 'launchOptions', useStart, useEnd);
    const [argsStart, argsEnd] = block(sk, 'args', loStart, loEnd);
    expect(
      flagAt > argsStart && flagAt < argsEnd,
      `${FLAG} is in playwright.config.ts but not inside the top-level use.launchOptions.args ` +
      `(use: ${useStart}–${useEnd}, launchOptions: ${loStart}–${loEnd}, args: ${argsStart}–` +
      `${argsEnd}, flag at ${flagAt}). It must be top-level: inside one project's own \`use\` ` +
      `it would leave the \`reference\` and \`app\` projects rasterising differently, which is ` +
      `worse than not having it — the oracle and the app would then disagree by exactly those ` +
      `pixels at maxDiffPixels: 0.`
    ).toBe(true);
    // It is a launch argument, not a stray mention: the enclosing array is a string list.
    expect(src.slice(argsStart, argsEnd + 1)).toMatch(/\[\s*(?:'[^']*'|"[^"]*")(?:\s*,\s*(?:'[^']*'|"[^"]*"))*\s*,?\s*\]/);
  });

  it('keeps zero pixel tolerance beside it — the flag is determinism, not leniency', () => {
    // Global Constraint (e): the fix must never have been a relaxed gate.
    expect(code).toContain('maxDiffPixels: 0');
    expect(code).toContain('threshold: 0.1');
    expect(code).not.toMatch(/maxDiffPixelRatio\s*:/);
  });

  it('runs the determinism guard: capture-determinism.spec.ts is in the reference project', () => {
    const [projStart, projEnd] = block(sk, 'projects', 0, sk.length, 1);
    const reference = src.slice(projStart, projEnd + 1).split('\n').find((l) => l.includes("name: 'reference'")) ?? '';
    expect(
      reference,
      'the reference project no longer matches capture-determinism.spec.ts, so ' +
      '`npm run test:visual:baselines` stops running the behavioural guard on its own output.'
    ).toContain('capture-determinism');
  });
});
