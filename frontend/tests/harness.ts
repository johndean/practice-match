import { request as apiRequest, type BrowserContext, type Page } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Deterministic rendering on both targets: no basemap tiles (markers still draw
// over the blank canvas), fonts loaded, pointer parked, animations settled.
const VENDOR = join(fileURLToPath(new URL('.', import.meta.url)), '../../docs/design-reference/design_handoff_practice_match_v3/vendor');
// support.js loads React/ReactDOM/Babel from unpkg with SRI; MarketMapV3.jsx (loaded by the
// reference's Browse/Listing/Market screens) separately loads Leaflet from
// unpkg the same SRI-pinned way — all five must be vendored or the map screens never boot.
const VENDORED: Record<string, { file: string; type: string }> = {
  'https://unpkg.com/react@18.3.1/umd/react.production.min.js': { file: 'react.production.min.js', type: 'text/javascript' },
  'https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js': { file: 'react-dom.production.min.js', type: 'text/javascript' },
  'https://unpkg.com/@babel/standalone@7.29.0/babel.min.js': { file: 'babel.min.js', type: 'text/javascript' },
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css': { file: 'leaflet.css', type: 'text/css' },
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js': { file: 'leaflet.js', type: 'text/javascript' }
};

// 1×1 fully transparent GIF, used for the stubbed basemap tiles and to answer the
// reference's pre-hydration image-slot noise below. It MUST be transparent, not merely
// blank-looking: MarketMapV3.jsx:190 puts the Esri label tiles in `shadowPane` (z-index
// 500), deliberately ABOVE the community mosaic in the overlay pane (z-index 400), so an
// opaque stub paints 24 solid squares over the C5/C7 shading and the zero-tolerance gate
// compares two unshaded maps. The previous constant
// (R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==) carried no Graphic Control Extension
// and was therefore opaque white — harmless under V2, which drew nothing beneath the
// labels. Guarded by harness.test.ts (controller ruling 2026-09-07). With a transparent
// tile the basemap area is Leaflet's own #ddd rather than white, on both targets.
export const BLANK_GIF = Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7', 'base64');

export async function prepare(page: Page): Promise<void> {
  page.on('pageerror', (e) => { throw new Error(`page error: ${e.message}`); });
  page.on('console', (m) => { if (m.type() === 'error') throw new Error(`console.error: ${m.text()}`); });
  // ---------------------------------------------------------------------------------------
  // B2 (A-I8.2): suppress the design runtime's re-fetch of its own document, on the REFERENCE
  // ORIGIN ONLY. `support.js`'s `boot()` guards that re-fetch on `window.__resources`
  // (support.js:158), and the re-fetch is what breaks the oracle:
  //
  //   1. the bundle's `<image-slot>` elements upgrade on the RAW, pre-hydration DOM, where `src`
  //      is still the literal unresolved `{{ … }}` text, and `_render` marks them `data-filled`;
  //   2. `boot()` then reads `dc.innerHTML` as the template — now carrying that attribute — so
  //      React holds it as a prop;
  //   3. the re-fetch hands `updateHtml` the RAW text template, which has no `data-filled`, and
  //      React removes the attribute it no longer has in props. `image-slot.css`'s
  //      `:host([data-filled]) .ring{display:none}` then stops applying and the dashed
  //      PLACEHOLDER RING is drawn over the practice photo.
  //
  // The jump-bar entry avoided this by accident — the gate screen has no `<image-slot>` at all, so
  // there was nothing mounted for `updateHtml` to strip, and the Browse slot was created by the
  // click afterwards from the clean template. `startScreen` mounts the screen on the first commit
  // instead, inside the window the re-fetch closes, and whether a given slot survives is a race
  // (`browse` lost it every time; `detail` and `interest-modal` happened to win).
  //
  // Skipping the re-fetch leaves the template as the DOM-parsed one and every slot rendered by the
  // element itself: `data-filled` present wherever there is a real `src`, absent where there is
  // not — which is exactly what the app's own port does. Guarded by `placeholderRings` below and
  // asserted in the reference project (reference-baselines.spec.ts).
  // ---------------------------------------------------------------------------------------
  await page.addInitScript((refOrigin) => {
    if (location.origin === refOrigin) (window as unknown as { __resources?: unknown }).__resources = {};
  }, referenceOrigin());
  // Fulfilling (not aborting) the basemap tiles: an aborted <img> request logs its own
  // "Failed to load resource: net::ERR_FAILED" console error in Chromium, which the error
  // gate above would then fail the test on. A blank tile gives the same deterministic,
  // offline-safe result the comment above promises (no basemap imagery, markers still draw
  // over the blank canvas) without that side effect.
  await page.route(/arcgisonline\.com/, (route) => route.fulfill({ status: 200, contentType: 'image/gif', body: BLANK_GIF }));
  // The reference runtime loads React/Babel/Leaflet from unpkg with SRI hashes; serve the
  // vendored identical bytes so the suite is deterministic and offline-safe (same hashes →
  // SRI passes). An abort() here would fail the error gate the same way the tile fix above
  // does, so anything else under unpkg.com is fulfilled with a blank response, not aborted.
  await page.route('https://unpkg.com/**', (route) => {
    const v = VENDORED[route.request().url()];
    return route.fulfill(v ? { path: join(VENDOR, v.file), contentType: v.type } : { status: 200, contentType: 'text/plain', body: '' });
  });
  // Reference-only, harmless noise: the design tool's <image-slot> custom element
  // (image-slot.js) upgrades on the raw, pre-hydration DOM — before the dc-runtime's
  // first React render replaces it — and requests its own literal, unresolved "{{ expr }}"
  // placeholder text as an image URL, plus a `.image-slots.state.json` sidecar probe. Both
  // 404 on any host but the design tool's own editor and never recur once React mounts;
  // neither occurs on the Vue app (compiled bindings, no raw-text DOM phase; see
  // ImageSlot.vue's `v-if="src"`). Answer them rather than let this artifact of the
  // reference's own runtime trip the error gate.
  await page.route(/%7B%7B|\.image-slots\.state\.json$/, (route) => {
    const url = route.request().url();
    return route.fulfill(
      url.endsWith('.image-slots.state.json')
        ? { status: 200, contentType: 'application/json', body: '{}' }
        : { status: 200, contentType: 'image/gif', body: BLANK_GIF }
    );
  });
}

/**
 * Loads the target's root and waits for the design to have rendered.
 *
 * It waits for the design's `<header>` — one element, declared exactly once, the first thing
 * inside `<sc-if value="{{ isDesktop }}">`, `position: sticky` at a fixed 74 px height. It waited
 * for the jump bar's `Access` button until amendment A6.1 removed the bar (A-I8.1).
 *
 * PRECISELY: it is present on every screen of both targets, signed in or out, IN THE DESKTOP
 * PRESENTATION — the phone frame the design draws for `viewport: mobile` has no `<header>` at all
 * (review round 1, M6). That is not a gap, because this function always loads `/` and the viewport
 * prop is never set on it: every state boots at the desktop presentation and only then does
 * `reach()` ask for the phone frame, through `?props=` on the reference or `?viewport=mobile` on
 * the app. The two narrow viewports (`header-1000`, `header-1100`) are still the desktop
 * presentation, just narrower, so the header is there.
 *
 * NOT the header's brand text, which was the obvious candidate: `subBrandTextStyle` is
 * `display: none` below 1050 px, so `header-1000` would wait forever. Nor the logo `img`, whose
 * box collapses to zero — and `visible` with it — if the asset ever 404s.
 */
export async function booted(page: Page): Promise<void> {
  await page.goto('/');
  await page.locator('header').first().waitFor({ state: 'visible' });
}

export async function settle(page: Page): Promise<void> {
  await page.evaluate(() => (document as Document & { fonts: FontFaceSet }).fonts.ready);
  await page.mouse.move(0, 0);
  await page.waitForTimeout(600);
}

export async function click(page: Page, text: string): Promise<void> {
  await page.getByText(text, { exact: true }).first().click();
}

export function btn(page: Page, name: RegExp) {
  return page.getByRole('button', { name }).first();
}

// ---------------------------------------------------------------------------------------
// The one state whose capture a page scroll can move.
//
// App.vue has exactly ONE `position: fixed` element — the interest modal's overlay
// (`position: fixed; inset: 0; z-index: 900; … place-items: center`). Everything else on all
// 28 approved states is in normal flow, and a fullPage screenshot captures flow content
// whole regardless of where the page happens to be scrolled. A fixed element is different:
// it is composited at the offset it PAINTS at, so a page scrolled by N pixels puts the whole
// overlay — backdrop and the dialog centred inside it — N pixels down the screenshot while
// the dimmed content behind it does not move.
//
// That is what failed CI on the vin-swe runner at fa17a91 (`interest-modal`, 23,441 pixels,
// 1 %), and only there: comparing that run's own expected/actual pair pixel by pixel, the
// actual aligns with the expected EXACTLY at dy = +5 and dx = 0 (zero mismatching samples
// across the dialog) — a pure translation, nothing reflowed, no animation mid-flight (the
// runner's log even says "captured a stable screenshot"). The backdrop's top edge sits at
// y = 0 in one and y = 5 in the other, its bottom edge at 939 and 943.
//
// The scroll comes from the click itself: Playwright scrolls a target into view before
// clicking it, and the listing page is ~20 px taller on the Linux runner than on darwin
// (2375 vs 2355 for the same commit, font metrics), which is enough to push "I'm interested"
// past the fold and scroll the page a few pixels first. Reproduced on darwin by scrolling
// 5 px by hand before the capture: 23,608 pixels, the same failure.
//
// So the capture is pinned instead of hoped for: scroll back to the top, then hold until the
// overlay's own box has been identical across two consecutive animation frames with the page
// still at the top. Nothing is relaxed and no tolerance moves — the screenshot is simply
// taken from the one viewport position the design's centred dialog is drawn for.
export async function atTop(page: Page, selector: string): Promise<void> {
  await page.locator(selector).first().waitFor({ state: 'visible' });
  await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: 'instant' as ScrollBehavior }));
  await page.waitForFunction(
    (sel) =>
      new Promise<boolean>((resolve) => {
        const el = document.querySelector(sel);
        if (!el) return resolve(false);
        const a = el.getBoundingClientRect();
        requestAnimationFrame(() =>
          requestAnimationFrame(() => {
            const b = el.getBoundingClientRect();
            resolve(window.scrollY === 0 && a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height);
          })
        );
      }),
    selector
  );
}

export async function waitMap(page: Page): Promise<void> {
  await page.locator('.leaflet-container').first().waitFor({ state: 'visible' });
  await page.waitForTimeout(700); // Leaflet setView + marker layer
}

// ---------------------------------------------------------------------------------------
// The design persona's sign-in (amendment A-I7) — the real API, reached through Vite's `/api`
// proxy. `scripts/seed_persona.py` upserts this account (roles buyer + seller + staff + admin,
// state `active`) and the `api` web server in tests/targets.ts runs it before serving, so the
// credential below is all this needs.
//
// The password default MIRRORS that script's `DEFAULT_PASSWORD`, and
// `tests/test_docs.py::test_the_playwright_persona_password_default_matches_seed_persona` pins
// the two equal — a drift would otherwise surface as a 401 in whichever test happened to run
// first. It is a documented test-only constant, not a secret: the account is
// `design@practice-match.test` (RFC 6761 `.test`, never deliverable) and seed_persona.py
// refuses to run against production at all.
// ---------------------------------------------------------------------------------------
export const PERSONA_EMAIL = 'design@practice-match.test';
export const PERSONA_DEFAULT_PASSWORD = 'design-persona-quiet-lantern-42';

/**
 * The six seeded accounts, each as the `/api/me` payload `logic.js`'s A5.4 bootstrap reads
 * (`scripts/seed_persona.py` writes them; `tests/test_docs.py` pins these strings against
 * `app.auth.labels.role_label` / `initials` for each persona's grants, in both languages).
 *
 * Three MEMBERS, all Dr. Rachel Mendes of the StartUp Club, differing only in what they may
 * open — because since A5.4 the account menu renders the account's TRUE label, so the account
 * decides what the design's own header must say. John's rule for this wave is that the design's
 * copy does not change, so the account is chosen to fit the design rather than the reverse
 * (A-I8.2): `buyer` reproduces the fixture's "Approved buyer · StartUp Club" letter for letter,
 * which is what keeps the nineteen buyer-family states on their existing pixels.
 *
 * Three APPLICANTS, one per gate state the "Prototype — access states" shortcuts used to reach
 * before A6.2 removed them. They hold no grants, so `role_label` gives them "Applicant".
 *
 * Each entry is ONE line on purpose: `tests/test_docs.py` reads them without a TypeScript parser
 * and pins every field against `labels.role_label` / `labels.initials` and `seed_persona.py`'s own
 * constants. Keep the shape, or that pin stops seeing them.
 */
export const PERSONAS = {
  design: { email: 'design@practice-match.test', name: 'Dr. Rachel Mendes', role: 'VIN Foundation admin · StartUp Club', initials: 'RM', state: 'active', roles: ['admin', 'buyer', 'seller', 'staff'] },
  buyer: { email: 'buyer@practice-match.test', name: 'Dr. Rachel Mendes', role: 'Approved buyer · StartUp Club', initials: 'RM', state: 'active', roles: ['buyer'] },
  seller: { email: 'seller@practice-match.test', name: 'Dr. Rachel Mendes', role: 'Approved buyer and seller · StartUp Club', initials: 'RM', state: 'active', roles: ['buyer', 'seller'] },
  pending: { email: 'pending@practice-match.test', name: 'Pending Applicant', role: 'Applicant', initials: 'PA', state: 'pending', roles: [] },
  needsReview: { email: 'needs-review@practice-match.test', name: 'Applicant Under Review', role: 'Applicant', initials: 'AR', state: 'needs_review', roles: [] },
  declined: { email: 'declined@practice-match.test', name: 'Declined Applicant', role: 'Applicant', initials: 'DA', state: 'declined', roles: [] }
} as const;

export type PersonaKey = keyof typeof PERSONAS;

/** The credential `POST /api/auth/signin` is given. Pure, so harness.test.ts can pin it. */
export function personaCredentials(persona: PersonaKey = 'design', env: NodeJS.ProcessEnv = process.env): { email: string; password: string } {
  return { email: PERSONAS[persona].email, password: env.PERSONA_PASSWORD ?? PERSONA_DEFAULT_PASSWORD };
}

/**
 * Where the design server answers — the SAME expression `playwright.config.ts` hands the
 * `reference` project for its baseURL, pinned against it in harness.test.ts. `prepare()` needs it
 * to scope the template-refetch guard (B2) to the reference and keep it away from the app.
 */
export function referenceOrigin(env: NodeJS.ProcessEnv = process.env): string {
  return `http://localhost:${Number(env.PW_REF_PORT) || 5174}`;
}

// ---------------------------------------------------------------------------------------
// The persona memo, on disk (A-I8.2).
//
// Playwright shuts the worker process down after a test failure and starts a new one, and the
// in-memory memo went with it: every later failing test spent another of `SIGNIN_IP`'s thirty
// attempts per IP per 15 minutes, so a run with a handful of real failures collapsed into a wall
// of `429 RATE_LIMITED` that buried the first one (measured on this branch: 44 reported failures,
// about twenty of them real).
//
// The file lives directly under `frontend/test-results/`, which Playwright clears at the start of
// every run — so it is RUN-SCOPED by construction, and a session from a previous run can never be
// re-used. The read/merge halves are pure so harness.test.ts can pin them without a filesystem.
// ---------------------------------------------------------------------------------------
/**
 * ONE anchor: the source tree (review round 1, M3). Playwright's own clearing of `test-results/`
 * is anchored to the CWD it was launched from, so it only lines up with this path when the suite
 * is run from `frontend/` — which is why the file also carries a run stamp below rather than
 * trusting the directory to have been emptied.
 */
export const MEMO_FILE = join(fileURLToPath(new URL('.', import.meta.url)), '..', 'test-results', '.persona-sessions.json');

/**
 * THIS process's start time, in epoch milliseconds. Computed once, at module load: `process.uptime()`
 * advances, so recomputing it per call would give a different id every call and the memo file would
 * never be readable at all.
 */
const PROCESS_STARTED_AT = Date.now() - Math.round(process.uptime() * 1000);

/**
 * Which RUN a memo file belongs to (round 2, ruling 2).
 *
 * Playwright forks its workers from the runner process, so `process.ppid` is the same for every
 * worker of one run — but pids are REUSED, so a stale file from a much earlier run could in
 * principle be adopted by a later run that happened to draw the same pid. The start time is
 * carried alongside it, and a reused pid then never matches. No `globalSetup` and no config change.
 *
 * The directory clearing is still the first guard: Playwright empties `test-results/` at run start
 * (see MEMO_FILE for the one case where that path and its clearing disagree).
 */
export function runId(ppid: number = process.ppid, startedAt: number = PROCESS_STARTED_AT): string {
  return `${ppid}-${startedAt}`;
}

/** The file's contents with one persona's jar set, or removed when `cookies` is null. A write from
 *  a different run than the file was stamped with starts a fresh object: the previous run's jars
 *  name sessions that may since have been revoked, and re-adding one would run every later test as
 *  the wrong account with no failure anywhere near the cause. */
export function memoFileUpdate(existing: string | null, persona: string, cookies: unknown[] | null, run: string): string {
  let sessions: Record<string, unknown[]> = {};
  const held = parseMemoFile(existing);
  if (held && held.run === run) sessions = held.sessions;
  if (cookies) sessions[persona] = cookies; else delete sessions[persona];
  return JSON.stringify({ run, sessions });
}

/** One persona's jar for THIS run, or null. An absent, corrupt, wrong-shaped or foreign-run file
 *  is simply "no memo": this is a cache, and failing the run over it would be worse than signing
 *  in again. */
export function memoFileRead(existing: string | null, persona: string, run: string): unknown[] | null {
  const held = parseMemoFile(existing);
  if (!held || held.run !== run) return null;
  const jar = held.sessions[persona];
  return Array.isArray(jar) ? jar : null;
}

function parseMemoFile(existing: string | null): { run: string; sessions: Record<string, unknown[]> } | null {
  if (!existing) return null;
  try {
    const parsed: unknown = JSON.parse(existing);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    const { run, sessions } = parsed as { run?: unknown; sessions?: unknown };
    if (typeof run !== 'string' || !sessions || typeof sessions !== 'object' || Array.isArray(sessions)) return null;
    return { run, sessions: sessions as Record<string, unknown[]> };
  } catch {
    return null;
  }
}

const readMemoFileText = (): string | null => (existsSync(MEMO_FILE) ? readFileSync(MEMO_FILE, 'utf8') : null);

function writeMemoFile(persona: PersonaKey, cookies: PersonaCookies | null): void {
  mkdirSync(dirname(MEMO_FILE), { recursive: true });
  writeFileSync(MEMO_FILE, memoFileUpdate(readMemoFileText(), persona, cookies, runId()));
}

/**
 * One sign-in per worker process, memoised.
 *
 * `app/auth/limits.py`'s `SIGNIN_IP = (30, 900)` is counted on EVERY attempt per IP —
 * `app/api/auth.py` calls `limits.hit` BEFORE it checks the credential — so signing in once per
 * screen state would answer 429 after the thirtieth, in whichever test happened to be running.
 * The first call spends the one attempt and keeps the cookies it produced; every later call
 * re-adds them to the new context instead.
 *
 * It memoises only a jar that actually holds `pm_session` (review M4). Memoising on
 * `memo === null` alone meant an EMPTY jar counted as "signed in", so every later call would
 * re-add nothing and the whole run would proceed anonymous — with no failure anywhere near the
 * cause. Throwing here puts it at the cause.
 *
 * Pure: the memo is passed in and handed back, and both context operations are arguments, which
 * is what lets harness.test.ts pin the budget without a browser.
 */
export async function personaSession<C extends { name: string }>(
  memo: C[] | null,
  jar: { cookies: () => Promise<C[]>; addCookies: (cookies: C[]) => Promise<void> },
  signIn: () => Promise<void>
): Promise<C[]> {
  if (memo === null) {
    await signIn();
    const cookies = await jar.cookies();
    if (!cookies.some((cookie) => cookie.name === 'pm_session')) {
      throw new Error(`persona sign-in left no pm_session cookie on the context (got: ${cookies.map((c) => c.name).join(', ') || 'nothing'})`);
    }
    return cookies;
  }
  await jar.addCookies(memo);
  return memo;
}

export type PersonaCookies = Awaited<ReturnType<BrowserContext['cookies']>>;

/**
 * Where the persona signs in — the SAME expression `playwright.config.ts` hands `resolveTargets`
 * for the `app` project's baseURL, pinned against it both ways in harness.test.ts.
 *
 * It has to be computed rather than read off the page: the sign-in below runs in a STANDALONE
 * request context, which has no project `use.baseURL` of its own, and Playwright exposes no
 * public getter for a browser context's.
 */
export function appOrigin(env: NodeJS.ProcessEnv = process.env): string {
  return env.PW_APP_URL ?? `http://localhost:${Number(env.PW_APP_PORT) || 5173}`;
}

/**
 * One sign-in, in a standalone request context, and the cookies it produced.
 *
 * Standalone — `request.newContext()`, not `page.request` — because it is deliberately OUTSIDE
 * any browser context, and therefore outside the Playwright trace (re-review). `trace:
 * 'retain-on-failure'` plus the CI job's `frontend/test-results` artifact upload means a failing
 * run's trace is published; a sign-in made through `page.request` would have put the persona
 * password in it, and the plan's QA step runs with a real `PERSONA_PASSWORD`.
 *
 * Sign-in is the one state-changing call that needs neither `X-CSRF-Token` nor a matching
 * `Origin`: `deps.check_origin_and_csrf` only enforces those on a request that ALREADY carries a
 * cookie session.
 */
export async function personaSignIn(persona: PersonaKey = 'design', baseURL = appOrigin()): Promise<PersonaCookies> {
  const api = await apiRequest.newContext({ baseURL });
  try {
    const response = await api.post('/api/auth/signin', { data: personaCredentials(persona) });
    if (!response.ok()) throw new Error(`${persona} persona sign-in failed: ${response.status()} ${await response.text()}`);
    return (await api.storageState()).cookies;
  } finally {
    await api.dispose();
  }
}

/**
 * Ends a session `personaSignIn` opened — also standalone, so it works from a `finally` even when
 * the page it was used from is broken.
 *
 * `POST /api/auth/signout` IS origin/CSRF-checked, so it presents the double-submit token from
 * the jar and an `Origin` equal to the host it posts to (which `deps.check_origin_and_csrf`
 * compares against `str(request.url)`).
 *
 * Returns the status, so a caller can PROVE the session ended rather than hope: the API answers
 * 200 only after `sessions.revoke` has committed and the cache entry is gone. 0 means there was
 * no double-submit token in the jar and nothing was attempted.
 */
export async function personaSignOut(cookies: PersonaCookies, baseURL = appOrigin()): Promise<number> {
  const csrf = cookies.find((cookie) => cookie.name === 'pm_csrf');
  if (!csrf) return 0;                                 // no double-submit token: nothing to sign out with
  const api = await apiRequest.newContext({
    baseURL,
    storageState: { cookies, origins: [] },
    extraHTTPHeaders: { 'X-CSRF-Token': csrf.value, Origin: baseURL }
  });
  try {
    return (await api.post('/api/auth/signout')).status();
  } finally {
    await api.dispose();
  }
}

/**
 * One memo PER PERSONA, per worker process (A-I8). A-I7 had a single memo because there was a
 * single account; four personas need four, or the second persona's sign-in would be skipped in
 * favour of the first one's cookies and every later test would run as the wrong account — with
 * no failure anywhere near the cause.
 *
 * THE BUDGET. `app/auth/limits.py`'s `SIGNIN_IP = (30, 900)` counts EVERY attempt per IP, wrong
 * credentials included (`app/api/auth.py` calls `limits.hit` before it checks the password). A
 * full `app`-project run spends: one per persona that any state signs in as — `buyer`, `seller`,
 * `design`, `pending`, `declined` (`needsReview` is seeded and exported for Task I8b, and no
 * approved state uses it yet) — plus the reauth test's own standalone session, plus the three
 * form sign-ins in `smoke.spec.ts` (the successful one, the deliberately wrong password, and the
 * one the sign-out test consumes). Nine of thirty, with the memo and this file keeping it there
 * however many workers the run gets through.
 *
 * The wrong password also counts toward `SIGNIN_EMAIL`'s ten failures per address per 15 minutes —
 * for `buyer@` only, and one of ten.
 */
export const personaSessionMemos: Record<PersonaKey, { cookies: PersonaCookies | null }> = {
  design: { cookies: null }, buyer: { cookies: null }, seller: { cookies: null },
  pending: { cookies: null }, needsReview: { cookies: null }, declined: { cookies: null }
};

/**
 * The design persona's memo — the same object as `personaSessionMemos.design`, kept under its
 * A-I7 name because that is what `forgetPersonaSession()`'s no-argument form clears and what
 * `signInAsPersona` spends. Exported so that default can be exercised without test-only code in
 * the production path (re-review).
 */
export const personaSessionMemo = personaSessionMemos.design;

/**
 * Drops one persona's session — the in-memory memo AND its entry in the run's memo file — so the
 * next `signInAs` for it signs in again (A-I7.2, extended by A-I8.2).
 *
 * For I8's sign-out tests: a memo is the WHOLE context jar and never expires, so once a test signs
 * out, the memoised `pm_session` names a revoked session and re-adding it to the next context would
 * silently run every later test anonymous.
 */
export function forgetPersonaSession(persona: PersonaKey = 'design', clearFile: (p: PersonaKey) => void = (p) => writeMemoFile(p, null)): void {
  personaSessionMemos[persona].cookies = null;
  // Injected so harness.test.ts can ASSERT the file is cleared instead of writing into the real
  // `test-results/` while a unit suite runs — which it did, quietly deleting two personas' jars
  // from a Playwright run's memo and buying two needless sign-ins on the next one.
  clearFile(persona);
}

export async function signInAs(page: Page, persona: PersonaKey, url = '/'): Promise<void> {
  const context = page.context();
  const memo = personaSessionMemos[persona];
  // A restarted worker has an empty in-memory memo but the run's file is still there.
  if (memo.cookies === null) memo.cookies = memoFileRead(readMemoFileText(), persona, runId()) as PersonaCookies | null;
  memo.cookies = await personaSession<PersonaCookies[number]>(
    memo.cookies,
    { cookies: () => context.cookies(), addCookies: (cookies) => context.addCookies(cookies) },
    async () => { await context.addCookies(await personaSignIn(persona)); }
  );
  writeMemoFile(persona, memo.cookies);
  await page.goto(url);
}

/** `signInAs(page, 'design', url)` under its A-I7 name — the design persona is the member every
 *  screenshot of a member screen is taken as. */
export async function signInAsPersona(page: Page, url = '/'): Promise<void> {
  return signInAs(page, 'design', url);
}

// ---------------------------------------------------------------------------------------
// `reach()` — the one entry point for all 28 approved states (amendment A-I8).
//
// Until I8 both targets entered every state the same way, through the design's own PROTOTYPE
// affordances: the jump bar (`jump()`), the "Prototype — access states" shortcuts, and the
// jump bar's "Mobile view" toggle. A6.1/A6.2 take all three out of the design, so the entry
// has to differ by target while everything after it stays identical — which is what keeps one
// `steps` function in screens.ts honest for two targets:
//
//   REFERENCE  a static prototype: no session, no API. It enters through the design's OWN
//              prototype props, which tests/reference-server.mjs injects per request from
//              `?props=` (decision D-I8-3). `startGate` (A5.6) is the gate states' way in.
//   APP        a real session: `signInAs` posts to the real `/api/auth/signin` out of band,
//              the cookies go on the browser context, and the route is deep-linked.
//              `logic.js`'s A5.4 bootstrap turns the loaded account into the screen.
//
// The decisions are pure functions (`driverFor`, `personaFor`, `referenceMe`, `referenceUrl`,
// `appPlan`) so
// harness.test.ts can pin them without a browser.
// ---------------------------------------------------------------------------------------

export interface ReachTarget {
  /** The prototype screen. Anything but `gate` needs a session on the app. */
  screen?: 'gate' | 'browse' | 'detail' | 'requests' | 'seller' | 'admin';
  /** Which gate state, when `screen` is the gate. */
  gate?: 'signin' | 'apply' | 'pending' | 'rejected';
  /** `mobile` asks for the prototype's own 390×800 phone frame, not a browser resize. */
  viewport?: 'desktop' | 'mobile';
  /** Overrides the persona the app signs in as. The reference ignores it — it has no session. */
  persona?: PersonaKey;
}

/**
 * Which target `page` is on, from the origin it has already navigated to.
 *
 * Deliberately NOT a default: a page still on `about:blank` would be guessed as the reference,
 * which would drive an app-project run through the reference's driver and screenshot the wrong
 * target — and because the oracle is generated through the same driver, the pixel gate could not
 * see it. Every spec calls `booted()` before `steps()`; this is the assertion that says so.
 */
export function driverFor(url: string, appUrl = appOrigin()): 'app' | 'reference' {
  if (!/^https?:\/\//.test(url)) throw new Error(`reach() needs a page that has already navigated (call booted() first); got ${url || 'about:blank'}`);
  return new URL(url).origin === new URL(appUrl).origin ? 'app' : 'reference';
}

/** The app's route per prototype screen — the same mapping `src/router/sync.ts` writes URLs with. */
const ROUTE: Record<NonNullable<ReachTarget['screen']>, string> = {
  gate: '/', browse: '/browse', detail: '/practices/p1', requests: '/requests', seller: '/seller', admin: '/admin'
};

/**
 * Which account a state is captured as (A-I8.2). The header shows the account's TRUE label since
 * A5.4, so the account decides what the design's own header must say — and the design's copy does
 * not change, so a BUYER serves every state whose header the fixture already describes, and the
 * account that can actually open the rest serves those.
 */
const SCREEN_PERSONA: Record<NonNullable<ReachTarget['screen']>, PersonaKey | null> = {
  gate: null, browse: 'buyer', detail: 'buyer', requests: 'buyer', seller: 'seller', admin: 'design'
};

export function personaFor(target: ReachTarget = {}): PersonaKey | null {
  return target.persona ?? SCREEN_PERSONA[target.screen ?? 'gate'];
}

/** The account handed to the REFERENCE: the same one the app signs in as, so both targets render
 *  the same header. `null` only where the app signs nobody in either (the sign-in and application
 *  gates). A5.4 reads it and, since review round 1's I1, leaves a set `startScreen` in charge of
 *  WHICH screen — so one navigation puts the reference exactly where the app's deep link puts the
 *  app, with no clicking in between. */
export function referenceMe(persona: PersonaKey | null): (typeof PERSONAS)[PersonaKey] | null {
  return persona ? PERSONAS[persona] : null;
}

/**
 * The reference's entry: the design at `/` — the runtime resolves its own relative assets against
 * it — with all four prototype props named on every request, so no state inherits a value another
 * state set.
 */
export function referenceUrl(target: ReachTarget = {}): string {
  return `/?props=${encodeURIComponent(JSON.stringify({
    startScreen: target.screen ?? 'gate',
    startGate: target.gate ?? '',
    startViewport: target.viewport ?? 'desktop',
    me: referenceMe(personaFor(target))
  }))}`;
}

/** The app's plan for a target: which account to be, which URL to open, and — for the one gate
 *  state the design reaches by a link rather than by an account — what to click after. */
export function appPlan(target: ReachTarget = {}): { persona: PersonaKey | null; url: string; click: string | null } {
  const screen = target.screen ?? 'gate';
  return {
    persona: personaFor(target),
    url: ROUTE[screen] + (target.viewport === 'mobile' ? '?viewport=mobile' : ''),
    // "Request access" is the design's own link on the sign-in card (`goApply`), not a prototype
    // shortcut, so it survives the launch removal and is the honest way onto that gate.
    click: screen === 'gate' && target.gate === 'apply' ? 'Request access' : null
  };
}

/** Waits for the target's own root to have rendered. The app mounts only after `useMe().load()`
 *  has answered, which can be after `load`, so `page.goto` returning is not enough on its own. */
async function mounted(page: Page): Promise<void> {
  await page.locator('#app > *, #dc-root > *').first().waitFor({ state: 'attached' });
}

/** Puts `page` on an approved state's entry point. Everything after this is identical clicks on
 *  both targets — see tests/screens.ts. */
export async function reach(page: Page, target: ReachTarget = {}): Promise<void> {
  if (driverFor(page.url()) === 'reference') {
    await page.goto(referenceUrl(target));
    return mounted(page);
  }
  const plan = appPlan(target);
  if (plan.persona) await signInAs(page, plan.persona, plan.url);
  else await page.goto(plan.url);
  await mounted(page);
  if (plan.click) await click(page, plan.click);
}

/**
 * The ids of any `<image-slot>` that has a real `src` but is still drawing its dashed placeholder
 * ring — the B2 symptom, read from the live shadow DOM rather than inferred from a pixel diff.
 * Empty is the only acceptable answer on either target.
 */
export async function placeholderRings(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll('image-slot[src]')]
      .filter((el) => {
        const ring = el.shadowRoot?.querySelector('.ring');
        return !ring || getComputedStyle(ring).display !== 'none';
      })
      .map((el) => el.id || '(no id)')
  );
}
