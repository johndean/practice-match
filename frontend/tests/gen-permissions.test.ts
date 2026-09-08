import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const FRONTEND = join(fileURLToPath(new URL('.', import.meta.url)), '..');

// John's ruling #5, verbatim (2026-09-08): "The permission-table regeneration command must fail
// closed/refuse to run when any of the four required test-environment settings are missing. It
// must never silently generate an empty permission file." `gen:permissions` used to fall back to
// `${VAR:-default}` for all four, so an empty environment quietly regenerated the twin against
// someone's local Postgres/Redis instead of refusing — this is the pin that keeps it refusing.
describe('gen:permissions fails closed on the four required test-environment settings (I12, ruling #5)', () => {
  const REQUIRED = ['DATABASE_URL', 'REDIS_URL', 'ENVIRONMENT', 'API_SECRET_KEY'] as const;
  const pkg = JSON.parse(readFileSync(join(FRONTEND, 'package.json'), 'utf8')) as { scripts: Record<string, string> };
  const script = pkg.scripts['gen:permissions'];

  it('requires each of the four settings via bash\'s ${VAR:?…}, which aborts on unset OR empty', () => {
    for (const name of REQUIRED) {
      expect(script, `${name} is not required with \${${name}:?…}`).toMatch(new RegExp(`\\$\\{${name}:\\?[^}]+\\}`));
    }
  });

  it('carries no ${VAR:-default} fallback for any of the four — a silent default is exactly what the ruling forbids', () => {
    for (const name of REQUIRED) {
      expect(script, `${name} still carries a :-default`).not.toMatch(new RegExp(`\\$\\{${name}:-`));
    }
    expect(script).not.toContain(':-');
  });

  it('still writes to a .new file and moves it into place, so a refusal never touches the committed twin', () => {
    expect(script).toContain('> frontend/src/auth/permissions.ts.new && mv frontend/src/auth/permissions.ts.new frontend/src/auth/permissions.ts');
  });

  it('still runs the emitter with --ts, unconditionally on the four settings holding', () => {
    expect(script).toContain('poetry run python -m app.auth.permissions --ts');
  });
});
