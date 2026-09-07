import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const CONFIG = join(fileURLToPath(new URL('.', import.meta.url)), 'playwright.config.ts');
const SMOKE = join(fileURLToPath(new URL('.', import.meta.url)), 'smoke.spec.ts');
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
    expect(
      project('reference'),
      'the reference project no longer matches capture-determinism.spec.ts, so ' +
      '`npm run test:visual:baselines` stops running the behavioural guard on its own output.'
    ).toContain('capture-determinism');
  });

  /**
   * The source of ONE project object out of the `projects` array, found by brace-matching
   * rather than by reading a single line (re-review M11a): the four projects happen to be
   * one-liners today, and a reformat that split the `reference` object across lines would have
   * failed the case above on a perfectly correct config. Brace matching runs over the
   * skeleton, where strings are blanked, so the `name:` search itself reads `src`.
   */
  function project(name: string): string {
    const [projStart, projEnd] = block(sk, 'projects', 0, sk.length, 1);
    const wanted = new RegExp(`name\\s*:\\s*['\"]${name}['\"]`);
    for (let i = projStart; i <= projEnd; i++) {
      if (sk[i] !== '{') continue;
      const [start, end] = matchPair(sk, i);
      const object = src.slice(start, end + 1);
      if (wanted.test(object)) return object;
      i = end;   // a project that is not the one asked for: skip its nested braces whole
    }
    throw new Error(`no project named '${name}' in playwright.config.ts`);
  }
});

// ---------------------------------------------------------------------------------------
// Review round 2, ruling 1. The form sign-in tests (I2) type a password into the design's own
// card, so a FAILING run's trace carries it — and CI publishes `frontend/test-results`.
//
// In every local and CI run that password is the documented test-only default, so a trace
// discloses nothing. The one run where it is a real secret is a LIVE one: `PW_APP_URL` set, which
// is the QA hand-back, with `PERSONA_PASSWORD` from Railway. So the trace is off exactly there and
// the project default (`retain-on-failure`) is untouched everywhere else — the tests themselves
// keep running on a live run, because the form is precisely what Task I10 has to prove on QA.
//
// Pinned here, in this file's style, because the conditional is one line inside a describe and a
// later edit — a tidy-up, a merge — could drop it with nothing failing. The config's own
// `trace: 'retain-on-failure'` is asserted alongside, since the override is only meaningful
// against that default.
// ---------------------------------------------------------------------------------------
describe('the form sign-in tests turn their trace off on a live run (round 2, ruling 1)', () => {
  /** The sign-in-form describe's own body, comments blanked — from its opening to the next
   *  top-level `test.describe(` in the file. */
  function formDescribeBody(): string {
    const smoke = withoutComments(readFileSync(SMOKE, 'utf8'));
    const at = smoke.indexOf("test.describe('the design\\'s own sign-in form");
    expect(at, 'the sign-in-form describe is gone or renamed — re-point this pin').toBeGreaterThan(-1);
    const rest = smoke.slice(at + 1);
    const next = rest.indexOf('\ntest.describe(');
    return rest.slice(0, next === -1 ? undefined : next);
  }

  const USE_TRACE = /^test\.use\(\{ trace: process\.env\.PW_APP_URL \? 'off' : 'retain-on-failure' \}\);$/m;

  it('carries a PW_APP_URL-conditional trace in smoke.spec.ts, at the top level', () => {
    const smoke = withoutComments(readFileSync(SMOKE, 'utf8'));
    expect(smoke, 'the live-run trace override is gone').toMatch(USE_TRACE);
    // TOP-LEVEL is not a preference: Playwright refuses `use({ trace })` inside a describe group
    // ("because it forces a new worker") and names this as the remedy. So the assertion is that it
    // sits before the first describe, where it governs the file — including the form tests.
    expect(smoke.search(USE_TRACE)).toBeLessThan(smoke.indexOf('test.describe('));
    expect(formDescribeBody(), 'and NOT inside the describe, which Playwright rejects outright').not.toMatch(/test\.use\(\{\s*trace/);
  });

  it('leaves the project default in place, which is what the override is measured against', () => {
    expect(withoutComments(readFileSync(CONFIG, 'utf8'))).toContain("trace: 'retain-on-failure'");
  });

  it('does not skip the tests on a live run — only their trace goes', () => {
    // The form is what Task I10 has to prove on QA, so `PW_APP_URL` must not gate the tests
    // themselves. (The reauth test's own `test.skip(!!process.env.PW_APP_URL, …)` is a different
    // describe and stays: it proves Vite's proxy, which a live deployment does not have.)
    expect(formDescribeBody()).not.toMatch(/test\.skip\([^)]*PW_APP_URL/);
  });

  it('still spends the three sign-in attempts it documents, live or not', () => {
    const body = formDescribeBody();
    // `(?<![.\w])`, not `\b`: a dot is a word boundary, so `\btest\(` also counted the
    // `RegExp.prototype.test(e)` call inside the wrong-password case's console-error assertion.
    expect((body.match(/(?<![.\w])test\(/g) ?? []).length, 'three form tests, as ruled by I2').toBe(3);
  });
});
