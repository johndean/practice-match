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
  // A-S5 ruling 4: three approved states deliberately provoke a real 400 from the API, and
  // Chromium logs every 4xx subresource as a console error. `expectApiStatus` arms ONE status at
  // a time from the state's own steps; everything else still fails here, at the cause.
  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    if (consumeExpectedApiFailure(page, m.text())) return;
    throw new Error(`console.error: ${m.text()}`);
  });
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
 * The password the reset flows SET (A-S5 ruling 3), and therefore the one `verified@` has for the
 * rest of a run once any of them has run. Built exactly as the constant above is — a documented
 * test-only phrase on an RFC 6761 `.test` address that `seed_persona.py` refuses to write on
 * production, and long enough for the privileged floor (14) as well as the ordinary one (12).
 *
 * `POST /api/auth/password/reset` rotates the password AND revokes every session, and `verified@`
 * is also `gate-apply`'s screenshot persona (A-S4) — so the run records the rotation in its own
 * memo file and `personaCredentials('verified')` answers with this from then on. The seed writes
 * the default back at the start of the next run.
 */
export const PERSONA_RESET_PASSWORD = 'design-persona-second-lantern-77';

/** The password the accept-invite flows set on `invited@` — a third documented constant, because
 *  that account starts with no usable one at all and the design's own card is what gives it one.
 *  Fourteen characters or more: the invite card says staff passwords are, and a future invite may
 *  land on an account the server treats as privileged. */
export const PERSONA_INVITE_PASSWORD = 'design-persona-third-lantern-93';

/**
 * The reviewer's question `scripts/seed_persona.py` writes on `needs-review@`'s open application
 * (`NEEDS_REVIEW_INFO_REQUEST`), and the seeded answers on `declined@`'s declined one
 * (`DECLINED_FIELDS`). Both are ONE fact in two languages — `tests/test_docs.py` pins them equal —
 * because the oracle renders them: the answer card's note reaches the reference through A9.1's
 * `startAnswerNote`, and the re-apply form is filled with these values on both targets (A-S5
 * ruling 2), while `account-flows.spec.ts` proves the APP got them from the API.
 */
export const NEEDS_REVIEW_INFO_REQUEST = 'Which practice do you work at now, and in what role?';
export const DECLINED_FIELDS = {
  name: 'Declined Applicant, DVM',
  school_year: 'Texas A&M, 2012',
  license_state: 'TX',
  employer: 'Hill Country Veterinary Clinic',
  intent: 'Exploring ownership within two years.',
  affirm: true
} as const;

/**
 * The five outcomes that end on the SIGN-IN card with a message (spec §3's notice slot), and the
 * spec's own copy for each. The reference is handed the text through `startNotice`; the app
 * performs the flow and `logic.js` produces the text — so the pixel gate compares the spec's copy
 * against what the code actually says, and `account-flows.spec.ts` asserts it a third time.
 */
export const NOTICES = {
  verified: 'Your address is verified. Sign in to complete your access request.',
  'reset-sent': 'If that address has an account, a reset link is on its way. It is valid for 1 hour.',
  'password-updated': 'Password updated. Sign in with your new password.',
  'invite-set': 'Your password is set. Sign in with your email and the password you just chose.',
  'invite-expired': 'This invitation link is no longer valid. Ask the VIN Foundation for a new one.'
} as const;
export type NoticeKey = keyof typeof NOTICES;

/**
 * The single-use fixture tokens `scripts/seed_persona.py` inserts, twelve per purpose, recreated
 * every run. `tests/test_docs.py` pins these constants against the script's own `FIXTURE_TOKENS`
 * and `FIXTURE_TOKEN_PREFIX`, so the two never drift out of the one shape a raw token is allowed
 * to look like. They are documented test constants, not secrets: the accounts are `.test` and the
 * seed refuses to run against production.
 */
export const FIXTURE_TOKEN_PREFIX = 'fixture-';
export const FIXTURE_TOKEN_COUNT = 12;
export const FIXTURE_TOKENS = { verify: 'fixture-verify-', reset: 'fixture-reset-', invite: 'fixture-invite-' } as const;
export type FixtureTokenKind = keyof typeof FIXTURE_TOKENS;

/** The nth seeded token for a purpose, 1-based. Pure, so the budget is countable without spending
 *  it; past twelve it throws rather than invent a token the seed never inserted — which the API
 *  would answer with a 400 far from the cause. */
export function fixtureToken(kind: FixtureTokenKind, n: number): string {
  if (!Number.isInteger(n) || n < 1 || n > FIXTURE_TOKEN_COUNT) {
    throw new Error(`fixture ${kind} token ${n} does not exist: scripts/seed_persona.py inserts ${FIXTURE_TOKEN_COUNT} per purpose per run, and this run has spent them all`);
  }
  return `${FIXTURE_TOKENS[kind]}${String(n).padStart(2, '0')}`;
}

/** A token of the documented shape that NO seed ever created, so the real endpoint answers its
 *  real 400 — which is how the two expired cards and the invite-expired notice are reached. */
export function expiredFixtureToken(kind: FixtureTokenKind): string {
  return `${FIXTURE_TOKENS[kind]}expired`;
}

/** A throwaway address for the live sign-up and forgot flows — RFC 2606 `example.org`, never
 *  deliverable, distinct per run AND per take so `FORGOT_EMAIL` (3/h/address) and `SIGNUP_EMAIL`
 *  (3/day/address) are never the binding limit. Pure; `nextThrowawayEmail` takes the counter. */
export function throwawayEmail(purpose: string, run: string, n: number): string {
  return `e2e-${run || 'local'}-${purpose}-${n}@example.org`;
}

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
  declined: { email: 'declined@practice-match.test', name: 'Declined Applicant', role: 'Applicant', initials: 'DA', state: 'declined', roles: [] },
  // A-S4 (Task S4): an address that is confirmed and has never applied. A5.4's bootstrap lands it
  // on the Request Access card, which is how the APP reaches `gate-apply` now that A8.1c sends an
  // anonymous visitor's "Request access" click to the sign-up card instead. Seeded by Task S3.
  verified: { email: 'verified@practice-match.test', name: 'Verified Applicant', role: 'Applicant', initials: 'VA', state: 'verified', roles: [] },
  // A-S5 (Task S5): the two remaining identity states. `unverified@` is where the check-email card
  // and the resend flow start; `invited@` is a `verified` account with NO usable password — the
  // seed hashes a secret it generates fresh and keeps nowhere, so the invite token is the only way
  // in, and `personaCredentials('invited')` throws rather than hand back a credential that cannot
  // work.
  unverified: { email: 'unverified@practice-match.test', name: 'Unverified Applicant', role: 'Applicant', initials: 'UA', state: 'unverified', roles: [] },
  invited: { email: 'invited@practice-match.test', name: 'Invited Staff', role: 'Applicant', initials: 'IS', state: 'verified', roles: [] },
  // A-S5.2 (S-1): the tenth account, and the one nothing ever signs in as. `POST /api/auth/verify`
  // confirms its account for good, so the twelve `verify` fixture tokens belong to THIS one rather
  // than to `unverified@` — which `gate-check-email` and the resend flow need to still be
  // unverified after every capture. It is named here because the harness is where the seeded
  // fixtures are mirrored, and `tests/test_docs.py` pins the address against the seed.
  verifyMe: { email: 'verify-me@practice-match.test', name: 'Verify Fixture', role: 'Applicant', initials: 'VF', state: 'unverified', roles: [] }
} as const;

export type PersonaKey = keyof typeof PERSONAS;

/**
 * The credential `POST /api/auth/signin` is given, as a PURE function of whether this run has
 * already rotated that account's password (A-S5 ruling 3) — so harness.test.ts can pin both arms
 * without a filesystem.
 *
 * `PERSONA_PASSWORD` (the live QA run's real secret, from Railway) overrides the documented
 * default and cannot override the ROTATED value: after a reset the account has the password the
 * reset set, whatever the environment holds.
 */
export function credentialsFor(persona: PersonaKey, rotated: boolean, env: NodeJS.ProcessEnv = process.env): { email: string; password: string } {
  const set = ROTATED_PASSWORD[persona];
  if (rotated && set) return { email: PERSONAS[persona].email, password: set };
  if (persona === 'invited') {
    throw new Error('invited@practice-match.test has no usable password: the seed hashes a secret it keeps nowhere, and the invite fixture token is the only way in until this run accepts an invitation for it');
  }
  return { email: PERSONAS[persona].email, password: env.PERSONA_PASSWORD ?? PERSONA_DEFAULT_PASSWORD };
}

/** What each account's password BECOMES once this run has set one on it — a reset for `verified@`,
 *  an accepted invitation for `invited@`. No other persona has a flow that changes its password. */
const ROTATED_PASSWORD: Partial<Record<PersonaKey, string>> = {
  verified: PERSONA_RESET_PASSWORD,
  invited: PERSONA_INVITE_PASSWORD
};

/** `credentialsFor`, reading this run's rotation flag off the memo file. */
export function personaCredentials(persona: PersonaKey = 'design', env: NodeJS.ProcessEnv = process.env): { email: string; password: string } {
  return credentialsFor(persona, rotatedMemo.has(persona) || memoFileIsRotated(readMemoFileText(), persona, runId()), env);
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
 * Which RUN a memo file belongs to (round 3, ruling 2) — the id `tests/global-setup.ts` mints once
 * in the runner process and every worker inherits through the environment.
 *
 * The environment is the only channel that works: a worker-local value (round 2 used the process
 * start time) is stable inside a GREEN run, where there is one worker, and different in every
 * worker Playwright starts after a test failure — which is the only case the memo file exists for.
 *
 * Empty outside a Playwright run — a vitest process, or `playwright test` with the globalSetup
 * removed. `writeMemoFile` then keeps no file and `memoFileRead` finds none, so the in-memory memo
 * does its usual one-sign-in-per-persona-per-worker job and nothing is ever shared with a run it
 * does not belong to.
 */
export function runId(env: NodeJS.ProcessEnv = process.env): string {
  return env.PW_RUN_ID ?? '';
}

/**
 * Whether a memo file must be deleted before the run starts — the decision `global-setup.ts` makes,
 * as a pure function so it can be pinned without a filesystem.
 *
 * Stale means "cannot be shown to belong to this run": another run's stamp, an unreadable file, or
 * no run id at all. Only THIS run's own file survives, because a restarted worker needs it.
 */
export function isStaleMemoFile(existing: string | null, run: string): boolean {
  if (existing === null) return false;                 // nothing to delete
  const held = parseMemoFile(existing);
  return !run || !held || held.run !== run;
}

/** The file's contents with one persona's jar set, or removed when `cookies` is null. A write from
 *  a different run than the file was stamped with starts a fresh object: the previous run's jars
 *  name sessions that may since have been revoked, and re-adding one would run every later test as
 *  the wrong account with no failure anywhere near the cause. */
export function memoFileUpdate(existing: string | null, persona: string, cookies: unknown[] | null, run: string): string {
  const held = memoFor(existing, run);
  if (cookies) held.sessions[persona] = cookies; else delete held.sessions[persona];
  return JSON.stringify({ run, ...held });
}

/**
 * The next value of a run-scoped counter, and the file that records it (A-S5).
 *
 * Two things need one. The FIXTURE TOKENS are single-use — spending `01` twice gets a 400 from a
 * token the seed did emit but the first capture already burnt — and the THROWAWAY ADDRESSES must
 * differ per take or three `forgot` captures would spend `FORGOT_EMAIL`'s three per hour on one
 * address. Both live beside the persona jars, in the run's own file, so a worker Playwright
 * restarts after a failure carries on rather than starting over.
 */
export function memoFileTakeCounter(existing: string | null, name: string, run: string): { n: number; contents: string } {
  const held = memoFor(existing, run);
  const n = (held.counters[name] ?? 0) + 1;
  held.counters[name] = n;
  return { n, contents: JSON.stringify({ run, ...held }) };
}

/** Records that this run has rotated a persona's password — see `PERSONA_RESET_PASSWORD`. */
export function memoFileRotate(existing: string | null, persona: string, run: string): string {
  const held = memoFor(existing, run);
  if (!held.rotated.includes(persona)) held.rotated.push(persona);
  return JSON.stringify({ run, ...held });
}

/** Whether THIS run has rotated that persona's password. A foreign or absent file means no: the
 *  seed writes the documented default back at the start of every run. */
export function memoFileIsRotated(existing: string | null, persona: string, run: string): boolean {
  if (!run) return false;
  const held = parseMemoFile(existing);
  return !!held && held.run === run && held.rotated.includes(persona);
}

/** This run's memo, or a fresh empty one — the single place "a foreign run's file is not ours"
 *  is decided for jars, counters and the rotation flag alike. */
function memoFor(existing: string | null, run: string): Omit<HeldMemo, 'run'> {
  const held = parseMemoFile(existing);
  return held && held.run === run
    ? { sessions: held.sessions, counters: held.counters, rotated: held.rotated }
    : { sessions: {}, counters: {}, rotated: [] };
}

/** One persona's jar for THIS run, or null. An absent, corrupt, wrong-shaped or foreign-run file
 *  is simply "no memo": this is a cache, and failing the run over it would be worse than signing
 *  in again. */
export function memoFileRead(existing: string | null, persona: string, run: string): unknown[] | null {
  if (!run) return null;                               // no run id: nothing can be shown to be ours
  const held = parseMemoFile(existing);
  if (!held || held.run !== run) return null;
  const jar = held.sessions[persona];
  return Array.isArray(jar) ? jar : null;
}

interface HeldMemo { run: string; sessions: Record<string, unknown[]>; counters: Record<string, number>; rotated: string[] }

function parseMemoFile(existing: string | null): HeldMemo | null {
  if (!existing) return null;
  try {
    const parsed: unknown = JSON.parse(existing);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    const { run, sessions, counters, rotated } = parsed as { run?: unknown; sessions?: unknown; counters?: unknown; rotated?: unknown };
    if (typeof run !== 'string' || !sessions || typeof sessions !== 'object' || Array.isArray(sessions)) return null;
    // `counters` and `rotated` are A-S5's additions and are DEFAULTED rather than required: a
    // file written before they existed is still this run's memo, and the whole point of the file
    // is to be a cache that never fails a run over its own shape.
    return {
      run,
      sessions: sessions as Record<string, unknown[]>,
      counters: counters && typeof counters === 'object' && !Array.isArray(counters) ? { ...(counters as Record<string, number>) } : {},
      rotated: Array.isArray(rotated) ? rotated.filter((r): r is string => typeof r === 'string') : []
    };
  } catch {
    return null;
  }
}

const readMemoFileText = (): string | null => (existsSync(MEMO_FILE) ? readFileSync(MEMO_FILE, 'utf8') : null);

/**
 * The in-process half of the run-scoped counters. The file is authoritative across workers; this
 * is what keeps a single worker correct when there is no run id to write a file under (a vitest
 * process, or `playwright test` with the globalSetup removed). The two are combined with `max`,
 * so neither a missing file nor a stale read can hand the same token out twice.
 */
const counterMemo: Record<string, number> = {};

function takeCounter(name: string): number {
  const run = runId();
  const fromFile = run ? memoFileTakeCounter(readMemoFileText(), name, run) : null;
  const n = Math.max(fromFile?.n ?? 0, (counterMemo[name] ?? 0) + 1);
  counterMemo[name] = n;
  if (run) {
    mkdirSync(dirname(MEMO_FILE), { recursive: true });
    // Re-serialise from the value actually taken, so the `max` above is what the file records.
    let contents = readMemoFileText();
    for (let i = memoFileTakeCounter(contents, name, run).n; i <= n; i++) contents = memoFileTakeCounter(contents, name, run).contents;
    writeFileSync(MEMO_FILE, contents ?? memoFileTakeCounter(null, name, run).contents);
  }
  return n;
}

/** The next unspent fixture token of a purpose, for THIS run. Throws past twelve (see
 *  `fixtureToken`), naming the purpose and the seed. */
export function nextFixtureToken(kind: FixtureTokenKind): string {
  return fixtureToken(kind, takeCounter(`token:${kind}`));
}

/** The next throwaway address for a live flow — distinct per run and per take. */
export function nextThrowawayEmail(purpose: string): string {
  return throwawayEmail(purpose, runId(), takeCounter(`email:${purpose}`));
}

/**
 * Records that a reset has just changed a persona's password, and drops the session it revoked
 * with it (A-S5 ruling 3). BOTH halves matter: the memoised jar names a session
 * `POST /api/auth/password/reset` has revoked, and re-adding it to the next context would run
 * every later capture anonymous with no failure anywhere near the cause.
 */
export function personaPasswordRotated(persona: PersonaKey): void {
  const run = runId();
  if (run) {
    mkdirSync(dirname(MEMO_FILE), { recursive: true });
    writeFileSync(MEMO_FILE, memoFileRotate(readMemoFileText(), persona, run));
  }
  rotatedMemo.add(persona);
  forgetPersonaSession(persona);
}

/** The in-process half of the rotation flag, for the same reason `counterMemo` exists. */
const rotatedMemo = new Set<PersonaKey>();

function writeMemoFile(persona: PersonaKey, cookies: PersonaCookies | null): void {
  const run = runId();
  if (!run) return;                                    // outside a Playwright run there is no run to scope a file to
  mkdirSync(dirname(MEMO_FILE), { recursive: true });
  writeFileSync(MEMO_FILE, memoFileUpdate(readMemoFileText(), persona, cookies, run));
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
 * `design`, `pending`, `declined` and, since A-S4, `verified` (`needsReview` is seeded and exported
 * for Task I8b, and no approved state uses it yet) — plus the reauth test's own standalone session,
 * plus the three form sign-ins in `signin-form.spec.ts` (the successful one, the deliberately wrong
 * password, and one the sign-out test consumes). TEN of thirty, with the memo and this file keeping
 * it there however many workers the run gets through.
 *
 * The wrong password also counts toward `SIGNIN_EMAIL`'s ten failures per address per 15 minutes —
 * for `buyer@` only, and one of ten.
 */
export const personaSessionMemos: Record<PersonaKey, { cookies: PersonaCookies | null }> = {
  design: { cookies: null }, buyer: { cookies: null }, seller: { cookies: null },
  pending: { cookies: null }, needsReview: { cookies: null }, declined: { cookies: null },
  verified: { cookies: null }, unverified: { cookies: null }, invited: { cookies: null },
  verifyMe: { cookies: null }
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

export type ReachGate = 'signin' | 'apply' | 'pending' | 'rejected' | 'signup' | 'check-email'
  | 'verify-expired' | 'forgot' | 'reset' | 'reset-expired' | 'invite' | 'answer' | 'unavailable';

export interface ReachTarget {
  /** The prototype screen. Anything but `gate` needs a session on the app. */
  screen?: 'gate' | 'browse' | 'detail' | 'requests' | 'seller' | 'admin';
  /** Which gate state, when `screen` is the gate — every value `startGate` declares (A8.8a). */
  gate?: ReachGate;
  /** `mobile` asks for the prototype's own 390×800 phone frame, not a browser resize. */
  viewport?: 'desktop' | 'mobile';
  /** Overrides the persona the app signs in as. The reference ignores it — it has no session. */
  persona?: PersonaKey;
  /** One of the five outcomes that land on the sign-in card with a message (spec §3's notice
   *  slot). The reference is handed `NOTICES[key]` through `startNotice`; the app performs the
   *  real flow that produces it. */
  notice?: NoticeKey;
  /** The reviewer's question on the applicant-answer card. The app fetches it; the reference is
   *  handed it through A9.1's `startAnswerNote` (A-S5) — there is no other way in. */
  note?: string;
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
 *  the same header. `null` only where the app signs nobody in either — the sign-in gate (the
 *  application gate joined the signed-in states in A-S4). A5.4 reads it and, since review round 1's
 *  I1, leaves a set `startScreen` in charge of
 *  WHICH screen — so one navigation puts the reference exactly where the app's deep link puts the
 *  app, with no clicking in between. */
export function referenceMe(persona: PersonaKey | null): (typeof PERSONAS)[PersonaKey] | null {
  return persona ? PERSONAS[persona] : null;
}

/**
 * `gate-reapply`: a DECLINED account reaching the application form. It is the one state whose two
 * targets take a different number of steps — on the app the account clicks through its own card,
 * on the reference `startGate: 'apply'` puts it straight there — and the one place `me` has to be
 * withheld from a state that names a persona, because a `declined` account maps the gate back to
 * its own card (measured against the real `Component`).
 */
const isReapply = (target: ReachTarget): boolean => target.gate === 'apply' && target.persona === 'declined';

/**
 * The gates the APP captures SIGNED IN. Only `unavailable`: a member who deep-links a route their
 * access does not include. No `me` can buy `auth: true` on a gate screen — an `active` account
 * overrides the gate and lands on Browse (pinned in logic.test.ts) — so the reference sets `auth`
 * the only other way A5.4 offers, `startScreen`, and `startGate` then puts it back on the gate.
 * `state.me` stays the design's own fixture identity, which by the A-I8.2 invariant is
 * letter-for-letter `buyer@`'s computed label: the account the app captures this state as.
 */
const SIGNED_IN_GATES = new Set<ReachGate>(['unavailable']);

/** The `startScreen` the reference is given — `browse` where the capture must be signed in. */
export function referenceScreen(target: ReachTarget = {}): NonNullable<ReachTarget['screen']> {
  return target.gate && SIGNED_IN_GATES.has(target.gate) ? 'browse' : (target.screen ?? 'gate');
}

/**
 * The account the reference is given, or null. Withheld for the three gates where an account
 * would override the gate the state IS: `unavailable` (an active account lands on Browse),
 * `answer` (a `needs_review` account maps to the "under review" card) and the declined re-apply.
 * Nothing is lost — an applicant's `auth` is false on both targets and the gate screen's header is
 * driven by `auth` alone, while `unavailable`'s identity comes from the design's own fixture.
 */
export function referencePersona(target: ReachTarget = {}): PersonaKey | null {
  if (isReapply(target) || target.gate === 'answer' || (target.gate && SIGNED_IN_GATES.has(target.gate))) return null;
  return personaFor(target);
}

/**
 * The reference's entry: the design at `/` — the runtime resolves its own relative assets against
 * it — with all six prototype props named on every request, so no state inherits a value another
 * state set.
 */
export function referenceUrl(target: ReachTarget = {}): string {
  return `/?props=${encodeURIComponent(JSON.stringify({
    startScreen: referenceScreen(target),
    startGate: target.gate ?? '',
    startViewport: target.viewport ?? 'desktop',
    me: referenceMe(referencePersona(target)),
    // A8.8b / A9.1: the two message props. Always named, so a notice or a note cannot leak from
    // one capture into the next.
    startNotice: target.notice ? NOTICES[target.notice] : '',
    startAnswerNote: target.note ?? ''
  }))}`;
}

/** The app's route per gate value that has one of its own (spec §5's five public pages, plus the
 *  member route whose refusal IS the `unavailable` state). A gate absent from this table is reached
 *  by BEING an account in that state, at `/`. */
const GATE_ROUTE: Partial<Record<ReachGate, (token: string) => string>> = {
  signup: () => '/signup',
  forgot: () => '/forgot',
  // A token the seed never created, so the real endpoint answers its real 400 and the card is the
  // API's own verdict rather than a state the harness asserted into being.
  'verify-expired': () => `/verify?token=${expiredFixtureToken('verify')}`,
  'reset-expired': () => `/reset?token=${expiredFixtureToken('reset')}`,
  // The forms render from the token in the URL and SPEND it only on submit, which these two
  // states never do — but the counter still advances, because a token in a URL has been handed to
  // the API and the next capture must not gamble on it having been left unused.
  reset: (token) => `/reset?token=${token}`,
  invite: (token) => `/accept-invite?token=${token}`,
  unavailable: () => '/admin'
};

/** The URL each notice state's REAL flow starts at. The submit itself is `submitNotice`. */
const NOTICE_ROUTE: Record<NoticeKey, (token: string) => string> = {
  verified: (token) => `/verify?token=${token}`,
  'reset-sent': () => '/forgot',
  'password-updated': (token) => `/reset?token=${token}`,
  'invite-set': (token) => `/accept-invite?token=${token}`,
  'invite-expired': () => `/accept-invite?token=${expiredFixtureToken('invite')}`
};

const GATE_TOKEN: Partial<Record<ReachGate, FixtureTokenKind>> = { reset: 'reset', invite: 'invite' };
const NOTICE_TOKEN: Record<NoticeKey, FixtureTokenKind | null> = {
  verified: 'verify', 'reset-sent': null, 'password-updated': 'reset', 'invite-set': 'invite', 'invite-expired': null
};

/** Which seeded fixture token a target's APP entry takes, or null. Pure, so the run's whole token
 *  budget is countable in harness.test.ts without spending one. */
export function appTokenKind(target: ReachTarget = {}): FixtureTokenKind | null {
  if (target.notice) return NOTICE_TOKEN[target.notice];
  return (target.gate && GATE_TOKEN[target.gate]) ?? null;
}

/** The app's plan for a target: which account to be, which URL to open, and — for `gate-reapply`
 *  alone — which of the design's own buttons to press on arrival.
 *
 *  The `click` field went away in A-S4 when the last state that needed one stopped needing it, and
 *  comes back here for exactly one: a declined account reaches the application form through its own
 *  card's "Reply with more information", which is the route spec §3 describes and the only one the
 *  app has.
 *
 *  Pure: the fixture token is passed IN, because taking one writes to the run's memo file and this
 *  function is pinned by unit tests that must spend nothing. */
export function appPlan(target: ReachTarget = {}, token = ''): { persona: PersonaKey | null; url: string; click?: string } {
  if (target.notice) return { persona: null, url: NOTICE_ROUTE[target.notice](token) };
  const route = target.gate && GATE_ROUTE[target.gate];
  if (route) return { persona: personaFor(target), url: route(token) };
  const screen = target.screen ?? 'gate';
  return {
    persona: personaFor(target),
    url: ROUTE[screen] + (target.viewport === 'mobile' ? '?viewport=mobile' : ''),
    ...(isReapply(target) ? { click: 'Reply with more information' } : {})
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
  const kind = appTokenKind(target);
  const plan = appPlan(target, kind ? nextFixtureToken(kind) : '');
  if (plan.persona) await signInAs(page, plan.persona, plan.url);
  else await page.goto(plan.url);
  await mounted(page);
  if (plan.click) await click(page, plan.click);
  if (target.gate === 'reset-expired') await submitPasswordForm(page, PERSONA_RESET_PASSWORD);
  if (target.notice) await submitNotice(page, target.notice);
}

/** The design's own two-password form — the reset and invite cards share it byte for byte. */
async function submitPasswordForm(page: Page, pw: string): Promise<void> {
  await page.getByLabel('New password', { exact: true }).fill(pw);
  await page.getByLabel('Confirm password', { exact: true }).fill(pw);
  await page.getByRole('button', { name: 'Save password', exact: true }).click();
}

/**
 * Waits until every `expectApiStatus` arming has been consumed, then asserts it.
 *
 * Chromium delivers a console event asynchronously, so the card the 4xx produces can be visible a
 * few milliseconds before the line arrives. The ASSERTION is the pure one above; this only decides
 * when to make it, and it fails through that same assertion when the line never comes.
 */
export async function settleExpectedApiFailures(page: Page, timeoutMs = 5_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while ((armedApiFailures.get(page)?.length ?? 0) > 0 && Date.now() < deadline) await page.waitForTimeout(50);
  assertExpectedApiFailuresObserved(page);
}

/**
 * The APP half of a notice state: the real flow the spec says produces that message.
 *
 * `verified` needs nothing — the `/verify` landing posts its token on arrival (A8.3b) — and the
 * other four submit one of the design's own forms. Nothing here asserts the outcome: the pixel and
 * DOM oracles do that against the reference, and `account-flows.spec.ts` asserts the copy.
 */
async function submitNotice(page: Page, key: NoticeKey): Promise<void> {
  if (key === 'reset-sent') {
    await page.getByLabel('Email', { exact: true }).fill(nextThrowawayEmail('forgot'));
    await page.getByRole('button', { name: 'Send reset link', exact: true }).click();
  } else if (key === 'password-updated') {
    await submitPasswordForm(page, PERSONA_RESET_PASSWORD);
    // The reset revoked every session `verified@` had and changed its password: the run has to
    // know both, or `gate-apply`'s next capture runs anonymous (A-S5 ruling 3).
    personaPasswordRotated('verified');
  } else if (key === 'invite-set' || key === 'invite-expired') {
    await submitPasswordForm(page, PERSONA_INVITE_PASSWORD);
    // Only the ACCEPTED one: an invitation the API refused set no password and revoked nothing.
    if (key === 'invite-set') personaPasswordRotated('invited');
  }
  await page.getByText(NOTICES[key], { exact: true }).first().waitFor({ state: 'visible' });
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

/**
 * True for the one console line Chromium logs for `signin-form.spec.ts`'s wrong-password
 * case, which deliberately provokes a 401 and needs to recognise its own line rather than
 * fail on it. Chromium's wording differs by transport: HTTP/1.1 (Vite's dev proxy — every
 * local and CI run) carries a reason phrase, "Failed to load resource: the server responded
 * with a status of 401 (Unauthorized)"; HTTP/2 (a live deployment, e.g.
 * `PW_APP_URL=https://qa.foundation.vin`) has no reason phrase at the protocol level, so
 * Chromium logs "… a status of 401 ()" instead. Matching `/401 \(Unauthorized\)/` — the
 * original filter — missed the second form, so the deliberate 401 leaked through the filter
 * and failed the test only on a live run (found running the parity suite against QA). Matched
 * on the status code alone, word-bounded so a status that merely CONTAINS "401" (e.g. a 4010)
 * is not mistaken for it, and any other console error still fails the test as before.
 */
export function isExpectedApiFailure(status: number, message: string): boolean {
  return new RegExp(`status of ${status}\\b`).test(message);
}

/** `isExpectedApiFailure(401, …)` under the name signin-form.spec.ts has always called it. */
export function isExpectedSignInFailure401(message: string): boolean {
  return isExpectedApiFailure(401, message);
}

// ---------------------------------------------------------------------------------------
// The per-page console-error allow-list (controller amendment A-S5, ruling 4).
//
// Three approved states deliberately provoke `TOKEN_INVALID` — a real 400 — and Chromium logs
// every 4xx subresource as a console error, which `prepare()`'s gate otherwise fails the test on.
// The exemption is deliberately small and deliberately noisy:
//
//   * ONE status per arming, consumed by exactly ONE matching line — a second 400 still fails;
//   * armed from the STATE's own steps, so nothing is exempt run-wide;
//   * armed only on the APP: the reference has no API and must never be exempted from anything;
//   * and an arming nobody consumed is itself a FAILURE (`assertExpectedApiFailuresObserved`),
//     because a dead exemption means the state quietly stopped provoking the 4xx it exists to show.
//
// It lives here rather than in visual.spec.ts/dom.spec.ts because those two are not S5's files —
// and this is the better seam anyway: the fact "this state provokes a 400" belongs beside the
// state, in screens.ts, not in every spec that drives it.
// ---------------------------------------------------------------------------------------
const armedApiFailures = new WeakMap<Page, number[]>();
const observedApiFailures = new WeakMap<Page, number[]>();

/** Allows exactly one console error for `status` on this page. A no-op on the reference. */
export function expectApiStatus(page: Page, status: number): void {
  if (driverFor(page.url()) !== 'app') return;
  armedApiFailures.set(page, [...(armedApiFailures.get(page) ?? []), status]);
}

/** Whether this console line answers an arming — and if so, spends it. */
export function consumeExpectedApiFailure(page: Page, message: string): boolean {
  const armed = armedApiFailures.get(page);
  if (!armed) return false;
  const at = armed.findIndex((status) => isExpectedApiFailure(status, message));
  if (at < 0) return false;
  const [status] = armed.splice(at, 1);
  observedApiFailures.set(page, [...(observedApiFailures.get(page) ?? []), status]);
  return true;
}

/** Throws unless every armed allowance was actually used. */
export function assertExpectedApiFailuresObserved(page: Page): void {
  const armed = armedApiFailures.get(page) ?? [];
  if (armed.length === 0) return;
  throw new Error(
    `expectApiStatus armed ${armed.join(', ')} and the page never logged it: this state is supposed to `
    + 'provoke that failure, so an allowance nobody used means it stopped doing so'
  );
}
