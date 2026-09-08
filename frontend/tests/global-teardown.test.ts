import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { teardownReseed } from './global-teardown';

/** The default export's body, comment lines stripped so a commented-out call cannot satisfy a
 *  pin — the same source-text idiom `playwright-config.test.ts` uses on the config's own keys. */
function defaultExportOf(file: string): string {
  const source = readFileSync(fileURLToPath(new URL(`./${file}`, import.meta.url)), 'utf8')
    .replace(/^\s*(\/\/|\*|\/\*).*$/gm, '');
  const at = source.indexOf('export default function');
  expect(at, `${file} has a default export`).toBeGreaterThan(-1);
  return source.slice(at);
}

// ---------------------------------------------------------------------------------------
// Fix round 1, ruling 1 (2026-09-08). John's sentence has two halves and `globalSetup` only met
// the first: "every DOM/visual run begins from a known baseline" AND "shared QA fixtures must not
// be left in a mutated state after a live QA run". Reseeding before the next run makes each run
// deterministic; it does not put QA back for the human who opens it afterwards. So a REMOTE run
// reseeds at both ends, through the same planner and the same script — no second copy of the
// decision, and nothing new for a local run, whose fixtures the `api` web server reseeds on its
// next start anyway.
//
// A failure here is REPORTED, never swallowed: `execFileSync` throws on a non-zero exit and this
// module does not catch it, so Playwright fails the run. A teardown that quietly gave up would
// leave QA mutated and say nothing — the exact state the ruling is about.
// ---------------------------------------------------------------------------------------
describe('global teardown (S7 fix round 1)', () => {
  const REMOTE = {
    PW_APP_URL: 'https://qa.foundation.vin',
    DATABASE_URL: 'postgresql://user:pw@host:5432/railway',
    PERSONA_PASSWORD: 'not-the-default',
    API_SECRET_KEY: 'not-the-default-either',
    ENVIRONMENT: 'qa',
    REDIS_URL: 'redis://user:pw@host:6379/0'
  };

  it('is a no-op on a local run', () => {
    const calls: string[] = [];
    expect(teardownReseed({}, (file) => { calls.push(file); })).toBe(false);
    expect(calls).toEqual([]);
  });

  it('runs the seed exactly once after a remote run', () => {
    const calls: { file: string; args: readonly string[] }[] = [];
    expect(teardownReseed(REMOTE, (file, args) => { calls.push({ file, args }); })).toBe(true);
    expect(calls).toEqual([{ file: 'poetry', args: ['run', 'python', 'scripts/seed_persona.py'] }]);
  });

  it('reports a failed reseed rather than swallowing it', () => {
    expect(() => teardownReseed(REMOTE, () => { throw new Error('Command failed: poetry run python scripts/seed_persona.py'); }))
      .toThrow('Command failed: poetry run python scripts/seed_persona.py');
  });

  // Fix round 2, I2: the default export is what Playwright calls, and nothing imported it.
  it('is what the default export does — the line the whole "after" half hangs on', () => {
    expect(defaultExportOf('global-teardown.ts')).toContain('teardownReseed(process.env);');
  });

  it('refuses, through the same planner, a remote run that cannot reseed', () => {
    expect(() => teardownReseed({ PW_APP_URL: REMOTE.PW_APP_URL, DATABASE_URL: 'x' }, () => undefined))
      .toThrow("a remote run must reseed the target's fixtures first; missing: PERSONA_PASSWORD, API_SECRET_KEY, ENVIRONMENT, REDIS_URL");
  });
});
