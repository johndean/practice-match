import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const CONFIG = join(fileURLToPath(new URL('.', import.meta.url)), '../vite.config.ts');
const TARGET = 'http://localhost:${process.env.PW_API_PORT || 8017}';

// ---------------------------------------------------------------------------------------
// Amendment A-I7.2 (review Important 2). The Vite dev server proxies `/api` to the real
// FastAPI app the `app` Playwright project signs into, and it must NOT rewrite the Host header.
//
// `app.auth.deps.check_origin_and_csrf` compares the browser's `Origin` against
// `settings.origins` PLUS `str(request.url)` — and with `ALLOWED_ORIGINS` unset, which is how
// `tests/targets.ts` runs the api server, `str(request.url)` is the only allowed origin. It is
// built from the Host header. `changeOrigin: true` would make the API see
// `http://localhost:<PW_API_PORT>` while the browser still sends `http://localhost:5173`, so
// every state-changing call the app makes would be refused with `ORIGIN`.
//
// Pinned twice, because neither pin alone is enough. The persona proof in `smoke.spec.ts` makes
// a real state-changing call through the proxy (`POST /api/auth/reauth`) — the behavioural half,
// which needs a browser, Postgres and Redis. This is the deterministic half: it runs inside
// `npm test` in milliseconds and names the decision. Exactly the pairing
// `tests/playwright-config.test.ts` uses for `--disable-partial-raster`, for the same reason —
// a silent deletion that no other gate in this task can catch (sign-in and `GET /api/me` are
// both exempt from the origin/CSRF path).
// ---------------------------------------------------------------------------------------

/**
 * `src` with every comment blanked, so a mention of a key inside prose cannot count as code.
 *
 * String and template literals are STEPPED OVER, not blanked: the proxy target is a template
 * literal containing `http://`, and a scanner that did not know about quotes would read those
 * two slashes as the start of a line comment and blank the rest of the line — which is exactly
 * what the first draft of this file did.
 */
function withoutComments(src: string): string {
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
      i += 1;
      while (i < src.length && src[i] !== quote) i += src[i] === '\\' ? 2 : 1;
      i = Math.min(i + 1, src.length);
      continue;
    }
    i += 1;
  }
  return out.join('');
}

describe('vite.config.ts pins the /api proxy', () => {
  const src = readFileSync(CONFIG, 'utf8');
  const code = withoutComments(src);

  it('proxies /api to the api web server on PW_API_PORT, default 8017', () => {
    expect(code, 'vite.config.ts no longer declares a proxy for /api — the app project has no API to reach').toMatch(/proxy\s*:\s*\{\s*'\/api'\s*:/);
    expect(
      code,
      `vite.config.ts's /api proxy no longer targets \`${TARGET}\`. tests/targets.ts starts uvicorn ` +
      `on PW_API_PORT (default 8017) and the two must name the same port, or every /api call in ` +
      `the app project reaches nothing.`
    ).toContain(TARGET);
  });

  it('does NOT set changeOrigin, so the Host header stays the browser\'s', () => {
    expect(
      code,
      'vite.config.ts now sets changeOrigin on the /api proxy. That rewrites the Host header, so ' +
      'app.auth.deps.check_origin_and_csrf builds a DIFFERENT origin from str(request.url) than ' +
      'the Origin the browser sent, and every cookie-session state change from the app is ' +
      'refused with ORIGIN. Sign-in and GET /api/me are exempt from that path, so this would ' +
      'pass every other gate in Task I7 and surface only when I8 first POSTs from the app. ' +
      'Remove it, or record the ruling that added it (A-I7.2, review Important 2).'
    ).not.toMatch(/changeOrigin/);
  });

  it('keeps the dev server on the port the app project targets', () => {
    expect(code).toMatch(/port\s*:\s*5173/);
    expect(code).toMatch(/strictPort\s*:\s*true/);
  });
});
