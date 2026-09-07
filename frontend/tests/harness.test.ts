import { describe, expect, it } from 'vitest';
import { BLANK_GIF, MEMO_FILE, PERSONAS, PERSONA_DEFAULT_PASSWORD, PERSONA_EMAIL, appOrigin, appPlan, driverFor, forgetPersonaSession, memoFileRead, memoFileUpdate, personaCredentials, personaFor, personaSession, personaSessionMemo, personaSessionMemos, referenceMe, referenceOrigin, referenceUrl, runId } from './harness';
import { resolveTargets as resolveTargetsForRef } from './targets';
import { resolveTargets } from './targets';

// The stubbed basemap tile must be TRANSPARENT, not merely blank-looking (controller ruling
// 2026-09-07). MarketMapV3.jsx:190 adds the Esri label tile layer with `pane: "shadowPane"`
// — z-index 500, above the community mosaic's overlay pane at 400 — so an opaque stub paints
// a solid square over every mosaic cell and `npm run test:visual` then compares two unshaded
// maps at zero tolerance while proving nothing about C5/C7.
//
// Two commonly-pasted "1×1 blank GIF" strings differ by ONE character and both survive a
// naive check: `…AAIBRAA7` paints colour index 0 (the transparent one) and `…AAIBTAA7`
// paints index 1 (opaque white) while still DECLARING transparency in its Graphic Control
// Extension. Round 1's test asserted only the declaration, so the second string passed it
// and re-blinded the mosaic (review L1). So this file asserts three independent things: the
// exact bytes, the GCE's transparent-colour flag, and — the one a typo cannot fake — that
// the single pixel's LZW code IS the index the GCE nominates as transparent. The end-to-end
// half of the guard lives in visual.spec.ts, which samples the rendered map for the design's
// own ramp colours.

/** The canonical 1×1 fully transparent GIF. Any change to the constant must be deliberate. */
const KNOWN_GOOD = 'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

interface Gif {
  /** The Graphic Control Extension's packed flags and nominated transparent index. */
  gce: { flags: number; transparentIndex: number } | null;
  /** The colour-table index the image's first (and here only) pixel actually paints. */
  painted: number | null;
}

/** The first LZW code after the clear code — i.e. what the first pixel is painted with. */
function firstPaintedCode(bytes: number[], minCodeSize: number): number | null {
  const width = minCodeSize + 1;
  const clear = 1 << minCodeSize;
  let bit = 0;
  const read = (): number | null => {
    let v = 0;
    for (let n = 0; n < width; n++, bit++) {
      const byte = bytes[bit >> 3];
      if (byte === undefined) return null;
      v |= ((byte >> (bit & 7)) & 1) << n; // GIF packs LZW codes least-significant bit first
    }
    return v;
  };
  const first = read();
  return first === clear ? read() : first;
}

/** Walks the GIF's real block structure, so a future swap has to survive the same check. */
function parseGif(gif: Buffer): Gif {
  expect(gif.subarray(0, 6).toString('latin1')).toBe('GIF89a'); // GIF87a has no GCE at all
  const packed = gif[10];
  // Logical screen descriptor is 7 bytes after the 6-byte header; a global colour table, when
  // present (bit 7), follows it with 2^(N+1) three-byte entries where N is the low 3 bits.
  let i = 13 + (packed & 0x80 ? 3 * (1 << ((packed & 0x07) + 1)) : 0);
  let gce: Gif['gce'] = null;
  while (i < gif.length) {
    const block = gif[i];
    if (block === 0x3b) break;                                  // trailer
    if (block === 0x21) {                                       // extension
      // <introducer><label><blockSize><packed><delay lo><delay hi><transparent index>
      if (gif[i + 1] === 0xf9) gce = { flags: gif[i + 3], transparentIndex: gif[i + 6] };
      i += 3 + gif[i + 2];
      while (gif[i] !== 0x00) i += gif[i] + 1;                  // remaining data sub-blocks
      i += 1;
      continue;
    }
    if (block === 0x2c) {                                       // image descriptor
      const local = gif[i + 9];
      let j = i + 10 + (local & 0x80 ? 3 * (1 << ((local & 0x07) + 1)) : 0);
      const minCodeSize = gif[j];
      j += 1;
      const data: number[] = [];
      while (gif[j] !== 0x00) {
        for (let k = 1; k <= gif[j]; k++) data.push(gif[j + k]);
        j += gif[j] + 1;
      }
      return { gce, painted: firstPaintedCode(data, minCodeSize) };
    }
    break;
  }
  return { gce, painted: null };
}

describe('the stubbed basemap tile', () => {
  it('is a 1×1 GIF', () => {
    expect(BLANK_GIF.readUInt16LE(6)).toBe(1);
    expect(BLANK_GIF.readUInt16LE(8)).toBe(1);
  });

  it('is exactly the known-good transparent GIF, byte for byte', () => {
    expect(BLANK_GIF.toString('base64')).toBe(KNOWN_GOOD);
  });

  it('declares a transparent colour, so the label tiles cannot hide the mosaic', () => {
    const { gce } = parseGif(BLANK_GIF);
    expect(gce, 'the tile stub carries no Graphic Control Extension — it is opaque').not.toBeNull();
    expect(gce!.flags & 0x01, 'the GCE does not set the transparent-colour flag').toBe(1);
  });

  it('paints the index it nominates as transparent, not merely declares one', () => {
    const { gce, painted } = parseGif(BLANK_GIF);
    expect(painted, 'the tile paints no decodable colour index').not.toBeNull();
    expect(painted, 'the tile declares transparency but PAINTS another index — it renders opaque').toBe(gce!.transparentIndex);
  });

  it('rejects the opaque constant this replaced', () => {
    expect(parseGif(Buffer.from('R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==', 'base64')).gce).toBeNull();
  });

  it('rejects the one-character twin that declares transparency but paints white', () => {
    // The shipped string with R→T: the GCE still says "index 0 is transparent", but the
    // pixel is painted with index 1 (#ffffff). Round 1's assertions all passed on this.
    const twin = parseGif(Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBTAA7', 'base64'));
    expect(twin.gce!.flags & 0x01).toBe(1);
    expect(twin.painted).not.toBe(twin.gce!.transparentIndex);
  });
});

// ---------------------------------------------------------------------------------------
// Amendment A-I7. `signInAsPersona` itself needs a browser, so the two decisions inside it
// are pulled out as pure functions and pinned here: WHICH credential is presented, and how
// often the sign-in is actually spent.
//
// The second one is not a nicety. `app/auth/limits.py`'s `SIGNIN_IP = (30, 900)` is counted
// on EVERY attempt per IP — `app/api/auth.py` calls `limits.hit` before it checks the
// credential — so a suite that signed in once per screen state would answer 429 after the
// thirtieth and the run would fail somewhere unrelated to whatever it was testing. One
// sign-in per worker process, its cookies memoised and re-added to each new context, is the
// whole budget the `app` project spends.
// ---------------------------------------------------------------------------------------
describe('the design persona credentials (A-I7)', () => {
  it('are the seeded persona and the password scripts/seed_persona.py writes by default', () => {
    expect(PERSONA_EMAIL).toBe('design@practice-match.test');
    expect(PERSONA_DEFAULT_PASSWORD).toBe('design-persona-quiet-lantern-42');
    expect(personaCredentials('design', {})).toEqual({ email: PERSONA_EMAIL, password: PERSONA_DEFAULT_PASSWORD });
  });

  it('take PERSONA_PASSWORD from the environment whenever it is set, exactly as seed_persona.py does', () => {
    expect(personaCredentials('design', { PERSONA_PASSWORD: 'whatever-railway-holds' })).toEqual({
      email: PERSONA_EMAIL,
      password: 'whatever-railway-holds'
    });
  });
});

describe('personaSession spends one sign-in per worker process (A-I7)', () => {
  const C = (name: string) => ({ name, value: 'opaque' });
  const jar = (held: { name: string }[]) => {
    const added: { name: string }[][] = [];
    return { added, cookies: () => Promise.resolve(held), addCookies: (c: { name: string }[]) => { added.push(c); return Promise.resolve(); } };
  };

  it('signs in on the first call and memoises the cookies the context ended up holding', async () => {
    const j = jar([C('pm_session'), C('pm_csrf')]);
    let signIns = 0;
    const memo = await personaSession(null, j, () => { signIns += 1; return Promise.resolve(); });
    expect(memo.map((c) => c.name)).toEqual(['pm_session', 'pm_csrf']);
    expect(signIns).toBe(1);
    expect(j.added, 'nothing is re-added on the call that did the signing in').toEqual([]);
  });

  it('re-adds the memo on every later call instead of spending another attempt against SIGNIN_IP', async () => {
    const j = jar([]);
    let signIns = 0;
    const memo = await personaSession([C('pm_session'), C('pm_csrf')], j, () => { signIns += 1; return Promise.resolve(); });
    expect(memo.map((c) => c.name)).toEqual(['pm_session', 'pm_csrf']);
    expect(signIns, 'a second sign-in spends one of SIGNIN_IP\'s 30 attempts per 900 s for nothing').toBe(0);
    expect(j.added.map((batch) => batch.map((c) => c.name))).toEqual([['pm_session', 'pm_csrf']]);
  });

  // Review M4: memoising on `memo === null` alone meant an EMPTY jar counted as "signed in", so
  // every later call would re-add nothing and the whole run would proceed anonymous with no
  // failure anywhere near the cause. Only a jar that actually holds the session cookie is worth
  // remembering; anything else throws here, where the cause is.
  it('refuses to memoise a jar with no pm_session', async () => {
    await expect(personaSession(null, jar([C('pm_csrf')]), () => Promise.resolve())).rejects.toThrow(/pm_session/);
    await expect(personaSession(null, jar([]), () => Promise.resolve())).rejects.toThrow(/pm_session/);
  });
});

describe('forgetPersonaSession (A-I7.2, extended by A-I8.2)', () => {
  it('drops the persona it is named — the in-memory memo AND the run\'s file — and only that one', () => {
    personaSessionMemos.buyer.cookies = [{ name: 'pm_session' }] as never;
    personaSessionMemos.seller.cookies = [{ name: 'pm_session' }] as never;
    const cleared: string[] = [];
    forgetPersonaSession('buyer', (p) => cleared.push(p));
    expect(personaSessionMemos.buyer.cookies).toBeNull();
    expect(cleared, 'the file must be cleared too, or a restarted worker re-adds a revoked session').toEqual(['buyer']);
    expect(personaSessionMemos.seller.cookies, 'one persona\'s sign-out is not another\'s').not.toBeNull();
    personaSessionMemos.seller.cookies = null;
  });

  // Re-review: the DEFAULT argument — the real module memo, and the form I8 will actually call —
  // was never exercised, and tests/harness.ts is not coverage-measured, so nothing noticed.
  it('with no argument, clears the real module memo, so the next sign-in spends an attempt', async () => {
    personaSessionMemo.cookies = [
      { name: 'pm_session', value: 'stale-and-revoked', domain: 'localhost', path: '/', expires: -1, httpOnly: true, secure: true, sameSite: 'Lax' as const }
    ];
    const cleared: string[] = [];
    forgetPersonaSession(undefined, (p) => cleared.push(p));
    expect(personaSessionMemo.cookies).toBeNull();
    expect(cleared, 'the no-argument form is the design persona\'s').toEqual(['design']);

    let signIns = 0;
    const jar = { cookies: () => Promise.resolve([{ name: 'pm_session' }]), addCookies: () => Promise.resolve() };
    await personaSession(personaSessionMemo.cookies, jar, () => { signIns += 1; return Promise.resolve(); });
    expect(signIns, 'with the memo cleared, personaSession must sign in again rather than re-add a revoked session').toBe(1);
  });
});

// Where `personaSignIn` posts. It is the SAME expression playwright.config.ts hands
// `resolveTargets` for the `app` project's baseURL, and pinning the two together both ways is
// what keeps the standalone request context (which has no project `use.baseURL`) pointed at the
// server the browser is looking at.
describe('appOrigin (A-I7.2)', () => {
  const ports = { app: 5173, ref: 4174, cs: 4175, api: 8017 };
  it('is the app project\'s own baseURL, locally and against a live deployment', () => {
    expect(appOrigin({})).toBe(resolveTargets({}, ports).baseURL);
    expect(appOrigin({})).toBe('http://localhost:5173');
    const live = { PW_APP_URL: 'https://qa.foundation.vin' };
    expect(appOrigin(live)).toBe(resolveTargets(live, ports).baseURL);
  });
  it('honours PW_APP_PORT, exactly as playwright.config.ts does', () => {
    expect(appOrigin({ PW_APP_PORT: '4999' })).toBe('http://localhost:4999');
    expect(appOrigin({ PW_APP_PORT: 'not-a-port' })).toBe('http://localhost:5173');
  });
});

// ---------------------------------------------------------------------------------------
// `reach()` — the one entry point every approved state is driven through (amendment A-I8).
//
// Before I8 the harness entered each state through the design's own PROTOTYPE affordances:
// the jump bar for the member screens, the "Prototype — access states" shortcuts for the two
// status gates, and the jump bar's "Mobile view" toggle for the phone frame. A6.1/A6.2 take
// all three out of the design, so the two targets no longer share an entry: the reference is
// a static prototype with no session and gets there through the design's own props (injected
// by reference-server.mjs's `?props=`), and the app signs in as a real seeded account and
// deep-links the route. Everything AFTER the entry is the same clicks on both targets, which
// is what keeps one `steps` function honest for two targets.
//
// The three decisions inside `reach` are pure functions so they can be pinned without a
// browser: which target a page is on, what URL the reference needs, and what the app needs.
// ---------------------------------------------------------------------------------------
describe('PERSONAS — the /api/me payload of each seeded account (D-I8-4, A-I8.2)', () => {
  it('are the six accounts scripts/seed_persona.py writes', () => {
    expect(Object.keys(PERSONAS)).toEqual(['design', 'buyer', 'seller', 'pending', 'needsReview', 'declined']);
  });

  it('carry the /api/me fields logic.js reads, so the reference can be handed the same account', () => {
    for (const p of Object.values(PERSONAS)) {
      expect(Object.keys(p).sort()).toEqual(['email', 'initials', 'name', 'role', 'roles', 'state'].sort());
      expect(p.email, 'RFC 6761 `.test` only: never a deliverable address').toMatch(/@practice-match\.test$/);
    }
  });

  // The whole point of A-I8.2: the buyer's computed label IS the design's fixture text, so the
  // nineteen buyer-family states keep their pixels without the design's copy changing. The
  // Python side of this pin lives in tests/test_docs.py, against labels.role_label itself.
  it('give the buyer the design\'s own fixture label, and the other two members their true ones', () => {
    // The literal the design's own fixture carries. `tests/test_docs.py` is what pins it against
    // `labels.role_label({'buyer'}, 'StartUp Club')` and against the design file itself, in both
    // languages; this is the harness side of the same fact.
    expect(PERSONAS.buyer.role).toBe('Approved buyer · StartUp Club');
    expect(PERSONAS.seller.role).toBe('Approved buyer and seller · StartUp Club');
    expect(PERSONAS.design.role).toBe('VIN Foundation admin · StartUp Club');
    // One name and one set of initials across the whole suite: only `role` varies with what the
    // account may actually open.
    for (const key of ['design', 'buyer', 'seller'] as const) {
      expect(PERSONAS[key].name).toBe('Dr. Rachel Mendes');
      expect(PERSONAS[key].initials).toBe('RM');
      expect(PERSONAS[key].state).toBe('active');
    }
  });

  it('give the three applicants their states and no roles', () => {
    expect(PERSONAS.pending.state).toBe('pending');
    expect(PERSONAS.needsReview.state).toBe('needs_review');
    expect(PERSONAS.declined.state).toBe('declined');
    for (const key of ['pending', 'needsReview', 'declined'] as const) {
      expect(PERSONAS[key].roles).toEqual([]);
      expect(PERSONAS[key].role, 'labels.role_label with no grants and no affiliation').toBe('Applicant');
    }
  });

  it('present the one documented password, whichever persona is asked for', () => {
    for (const key of Object.keys(PERSONAS) as (keyof typeof PERSONAS)[]) {
      expect(personaCredentials(key, {})).toEqual({ email: PERSONAS[key].email, password: PERSONA_DEFAULT_PASSWORD });
      expect(personaCredentials(key, { PERSONA_PASSWORD: 'from-railway' }).password).toBe('from-railway');
    }
  });

  it('memoise one session EACH, so six personas spend at most six of SIGNIN_IP\'s thirty attempts', () => {
    expect(Object.keys(personaSessionMemos).sort()).toEqual(Object.keys(PERSONAS).sort());
    expect(personaSessionMemo, 'signInAsPersona\'s memo IS the design persona\'s (A-I7\'s budget, unchanged)').toBe(personaSessionMemos.design);
  });
});

// Which account each state is screenshotted as (A-I8.2). The header shows the truth since A5.4,
// so the account decides what the design's own header must say — and the design's copy does not
// change, so the account is chosen to fit the design: a BUYER for every state whose header the
// fixture already describes, and the account that can actually open the others for the rest.
describe('personaFor — the account a state is captured as (A-I8.2)', () => {
  it('signs nobody in for a gate state', () => {
    expect(personaFor()).toBeNull();
    expect(personaFor({ screen: 'gate' })).toBeNull();
    expect(personaFor({ gate: 'apply' })).toBeNull();
  });

  it('is the buyer for the whole buyer family — Browse, the listing and the requests', () => {
    for (const screen of ['browse', 'detail', 'requests'] as const) expect(personaFor({ screen })).toBe('buyer');
  });

  it('is the seller for the seller dashboard (and therefore the wizard, which starts there)', () => {
    expect(personaFor({ screen: 'seller' })).toBe('seller');
  });

  it('is the all-roles design persona for Admin, the only screens a buyer cannot open', () => {
    expect(personaFor({ screen: 'admin' })).toBe('design');
  });

  it('honours an explicit persona — the two status gates name their own', () => {
    expect(personaFor({ gate: 'pending', persona: 'pending' })).toBe('pending');
    expect(personaFor({ gate: 'rejected', persona: 'declined' })).toBe('declined');
    expect(personaFor({ screen: 'browse', persona: 'needsReview' })).toBe('needsReview');
  });
});

describe('referenceMe — the account the reference is handed (A5.7 / A-I8.2)', () => {
  it('is the same account the app signs in as, for every state that has one', () => {
    for (const key of Object.keys(PERSONAS) as (keyof typeof PERSONAS)[]) expect(referenceMe(key)).toBe(PERSONAS[key]);
  });

  it('is null exactly where the app signs nobody in either', () => {
    expect(referenceMe(null)).toBeNull();
    expect(referenceMe(personaFor({ gate: 'signin' }))).toBeNull();
    expect(referenceMe(personaFor({ gate: 'apply' }))).toBeNull();
  });
});

// ---------------------------------------------------------------------------------------
// The reference's entry. ONE navigation, no clicking: since review round 1's I1, A5.4 leaves a
// set `startScreen` in charge of which screen even when an account is injected, so the reference
// lands signed in AND on the named screen in a single goto — exactly where the app's deep link
// puts the app. (Before I1 the account's `active` branch overrode `startScreen` and the harness
// clicked the design's header nav to compensate: an undeclared deviation from the ruled A-I8.2,
// fixed at the root rather than worked around.)
// ---------------------------------------------------------------------------------------
describe('referenceUrl — the design\'s own props, injected per request (A-I8 / D-I8-3)', () => {
  const props = (url: string) => JSON.parse(decodeURIComponent(new URL(url, 'http://x').searchParams.get('props')!));

  it('always serves the design at "/" and names all four prototype props on every request', () => {
    const url = referenceUrl();
    expect(url.startsWith('/?props=')).toBe(true);
    expect(props(url)).toEqual({ startScreen: 'gate', startGate: '', startViewport: 'desktop', me: null });
  });

  it('names the screen and hands over that state\'s own account, for every member family', () => {
    expect(props(referenceUrl({ screen: 'browse' }))).toEqual({ startScreen: 'browse', startGate: '', startViewport: 'desktop', me: PERSONAS.buyer });
    expect(props(referenceUrl({ screen: 'detail' })).me).toEqual(PERSONAS.buyer);
    expect(props(referenceUrl({ screen: 'requests' })).me).toEqual(PERSONAS.buyer);
    expect(props(referenceUrl({ screen: 'seller' }))).toMatchObject({ startScreen: 'seller', me: PERSONAS.seller });
    expect(props(referenceUrl({ screen: 'admin' }))).toMatchObject({ startScreen: 'admin', me: PERSONAS.design });
  });

  it('hands over an applicant for the two status gates, where the account IS the state', () => {
    expect(props(referenceUrl({ gate: 'pending', persona: 'pending' }))).toMatchObject({ startScreen: 'gate', startGate: 'pending', me: PERSONAS.pending });
    expect(props(referenceUrl({ gate: 'rejected', persona: 'declined' }))).toMatchObject({ startGate: 'rejected', me: PERSONAS.declined });
  });

  it('signs nobody in for the sign-in and application gates', () => {
    expect(props(referenceUrl({ gate: 'signin' })).me).toBeNull();
    expect(props(referenceUrl({ gate: 'apply' })).me).toBeNull();
  });

  it('asks for the phone frame through startViewport, the only way left (D-I8-7)', () => {
    expect(props(referenceUrl({ screen: 'browse', viewport: 'mobile' })).startViewport).toBe('mobile');
    expect(props(referenceUrl({ screen: 'browse' })).startViewport).toBe('desktop');
  });

  it('is stable for the same target, so the runtime\'s re-fetch of location.href hits the same URL', () => {
    expect(referenceUrl({ screen: 'seller' })).toBe(referenceUrl({ screen: 'seller' }));
  });
});

describe('appPlan — a real session and a real route (A-I8, A-I8.2)', () => {
  it('signs the state\'s own persona in and deep-links its route', () => {
    expect(appPlan({ screen: 'browse' })).toEqual({ persona: 'buyer', url: '/browse', click: null });
    expect(appPlan({ screen: 'detail' })).toEqual({ persona: 'buyer', url: '/practices/p1', click: null });
    expect(appPlan({ screen: 'requests' })).toEqual({ persona: 'buyer', url: '/requests', click: null });
    expect(appPlan({ screen: 'seller' })).toEqual({ persona: 'seller', url: '/seller', click: null });
    expect(appPlan({ screen: 'admin' })).toEqual({ persona: 'design', url: '/admin', click: null });
  });

  it('signs nobody in for the sign-in gate: that is what an anonymous visitor sees', () => {
    expect(appPlan()).toEqual({ persona: null, url: '/', click: null });
    expect(appPlan({ gate: 'signin' })).toEqual({ persona: null, url: '/', click: null });
  });

  it('reaches the application gate by the design\'s own link, which no launch removal touches', () => {
    expect(appPlan({ gate: 'apply' })).toEqual({ persona: null, url: '/', click: 'Request access' });
  });

  it('reaches the two status gates by signing in as an account actually in that state', () => {
    expect(appPlan({ gate: 'pending', persona: 'pending' })).toEqual({ persona: 'pending', url: '/', click: null });
    expect(appPlan({ gate: 'rejected', persona: 'declined' })).toEqual({ persona: 'declined', url: '/', click: null });
  });

  it('asks for the phone frame through the URL query, the only way left (D-I8-7)', () => {
    expect(appPlan({ screen: 'browse', viewport: 'mobile' }).url).toBe('/browse?viewport=mobile');
    expect(appPlan({ screen: 'browse', viewport: 'desktop' }).url).toBe('/browse');
  });
});

// ---------------------------------------------------------------------------------------
// The memo survives a worker restart (A-I8.2).
//
// Playwright shuts the worker process down after a test failure and starts a new one, which used
// to take the in-memory persona memo with it: every later failing test spent another of
// `SIGNIN_IP`'s thirty attempts per IP per 15 minutes, and a run with a handful of real failures
// turned into a wall of `429 RATE_LIMITED` that buried the first one (measured: 44 reported
// failures, ~20 real). The jar is written to a file under `frontend/test-results/`, which
// Playwright clears at the start of every run, so it is run-scoped by construction.
// ---------------------------------------------------------------------------------------
describe('the persona memo file (A-I8.2, run-scoped by M3)', () => {
  const C = (name: string) => ({ name, value: 'opaque' });
  const RUN = 'run-4711';

  it('reads back what it wrote, per persona, within the same run', () => {
    const one = memoFileUpdate(null, 'buyer', [C('pm_session')], RUN);
    expect(memoFileRead(one, 'buyer', RUN)).toEqual([C('pm_session')]);
    expect(memoFileRead(one, 'design', RUN), 'one persona\'s jar is not another\'s').toBeNull();

    const two = memoFileUpdate(one, 'design', [C('pm_csrf')], RUN);
    expect(memoFileRead(two, 'buyer', RUN)).toEqual([C('pm_session')]);
    expect(memoFileRead(two, 'design', RUN)).toEqual([C('pm_csrf')]);
  });

  // M3. The file lives under `frontend/test-results/`, which Playwright clears at the start of a
  // run — but only when it is run from `frontend/`, because that cleanup is anchored to the CWD
  // while this file is anchored to the source tree. A stale file from a previous run would hold
  // cookies for a session that may since have been revoked, and every test in the new run would
  // then proceed as the wrong account with no failure anywhere near the cause. So the file is
  // stamped with the run it belongs to and a foreign stamp reads as "no memo".
  it('ignores every persona in a file stamped with a different run', () => {
    const previous = memoFileUpdate(memoFileUpdate(null, 'buyer', [C('pm_session')], 'run-old'), 'design', [C('pm_session')], 'run-old');
    for (const persona of ['buyer', 'design'] as const) {
      expect(memoFileRead(previous, persona, 'run-old'), 'sanity: its own run can read it').not.toBeNull();
      expect(memoFileRead(previous, persona, RUN), 'a fresh run must sign in again rather than re-add a stale session').toBeNull();
    }
  });

  it('discards the previous run\'s sessions when the new run writes its first one', () => {
    const previous = memoFileUpdate(null, 'design', [C('pm_session')], 'run-old');
    const fresh = memoFileUpdate(previous, 'buyer', [C('pm_session')], RUN);
    expect(memoFileRead(fresh, 'buyer', RUN)).toEqual([C('pm_session')]);
    expect(memoFileRead(fresh, 'design', RUN), 'the stale run\'s jars do not survive alongside the new one\'s').toBeNull();
    expect(JSON.parse(fresh).run).toBe(RUN);
  });

  it('drops a persona when handed null, leaving the others alone', () => {
    const both = memoFileUpdate(memoFileUpdate(null, 'buyer', [C('a')], RUN), 'design', [C('b')], RUN);
    const dropped = memoFileUpdate(both, 'buyer', null, RUN);
    expect(memoFileRead(dropped, 'buyer', RUN)).toBeNull();
    expect(memoFileRead(dropped, 'design', RUN)).toEqual([C('b')]);
  });

  it('treats an absent, corrupt or wrong-shaped file as no memo, rather than failing the run', () => {
    for (const bad of [null, '{ not json', '[]', '{"sessions":{"buyer":[]}}', '{"run":"' + RUN + '","sessions":"nope"}']) {
      expect(memoFileRead(bad, 'buyer', RUN), String(bad)).toBeNull();
    }
  });

  it('is one anchor — the source tree, not the cwd Playwright cleans relative to (M3)', () => {
    expect(MEMO_FILE.endsWith('/frontend/test-results/.persona-sessions.json'), MEMO_FILE).toBe(true);
  });

  // Round 2, ruling 2. The id was the runner pid alone, and pids are reused — so a stale file
  // from a much earlier run could in principle be adopted by a later run that happened to draw the
  // same pid. It now carries the process start time as well, so a reused pid never matches.
  it('identifies the run by the runner pid AND a process start time, so a reused pid cannot match', () => {
    expect(runId(4711, 1_700_000_000_000)).toBe('4711-1700000000000');
    expect(runId(4711, 1_700_000_000_001), 'the same pid, a different run').not.toBe(runId(4711, 1_700_000_000_000));
    expect(runId(4712, 1_700_000_000_000), 'a different runner, the same instant').not.toBe(runId(4711, 1_700_000_000_000));
  });

  it('yields one stable id within a process, because the start time is computed once and cached', () => {
    // `process.uptime()` advances, so recomputing it per call would give a different id every
    // time and the file would never be readable at all.
    expect(runId()).toBe(runId());
    expect(runId(), 'the defaults are this process\'s own runner and start time').toBe(`${process.ppid}-${runId().split('-')[1]}`);
    expect(Number(runId().split('-')[1]), 'a plausible epoch-ms start time').toBeGreaterThan(1_600_000_000_000);
  });

  it('ignores and replaces a memo file stamped by a reused pid from an earlier run', () => {
    const stale = memoFileUpdate(null, 'buyer', [C('pm_session')], runId(4711, 1_000));
    expect(memoFileRead(stale, 'buyer', runId(4711, 1_000)), 'sanity: its own run reads it').not.toBeNull();
    expect(memoFileRead(stale, 'buyer', runId(4711, 2_000)), 'the same pid, a later run: no memo').toBeNull();
    const fresh = memoFileUpdate(stale, 'buyer', [C('pm_session')], runId(4711, 2_000));
    expect(JSON.parse(fresh).run).toBe('4711-2000');
    expect(memoFileRead(fresh, 'buyer', runId(4711, 1_000)), 'and the earlier run cannot read the replacement').toBeNull();
  });
});

describe('driverFor — which target the page is on (A-I8)', () => {
  it('is the app for the app project\'s origin and the reference for anything else', () => {
    expect(driverFor('http://localhost:5173/', 'http://localhost:5173')).toBe('app');
    expect(driverFor('http://localhost:5173/practices/p1', 'http://localhost:5173')).toBe('app');
    expect(driverFor('http://localhost:5174/', 'http://localhost:5173')).toBe('reference');
    // The live-deployment mode: PW_APP_URL points the app project at QA and the reference server
    // still runs locally, so the two are told apart by origin either way.
    expect(driverFor('https://qa.foundation.vin/browse', 'https://qa.foundation.vin')).toBe('app');
    expect(driverFor('http://localhost:5174/', 'https://qa.foundation.vin')).toBe('reference');
  });

  it('defaults to the app project\'s own origin, which is what reach() relies on', () => {
    expect(driverFor(`${appOrigin({})}/browse`)).toBe('app');
    expect(driverFor(`${referenceOrigin({})}/`)).toBe('reference');
  });

  it('refuses a page that has not navigated, rather than guessing the reference', () => {
    // Guessing would drive an app-project run through the reference driver and screenshot the
    // wrong target — and because the oracle is generated through the same driver, the pixel gate
    // could not see it. `booted()` is what every spec calls first; this is what says so.
    expect(() => driverFor('about:blank', 'http://localhost:5173')).toThrow(/booted/);
    expect(() => driverFor('', 'http://localhost:5173')).toThrow(/booted/);
  });
});

describe('referenceOrigin — where the design server answers (A-I8.2 / B2)', () => {
  it('is the reference project\'s own baseURL, and honours PW_REF_PORT exactly as the config does', () => {
    expect(referenceOrigin({})).toBe('http://localhost:5174');
    expect(referenceOrigin({ PW_REF_PORT: '4174' })).toBe('http://localhost:4174');
    expect(referenceOrigin({ PW_REF_PORT: 'not-a-port' })).toBe('http://localhost:5174');
  });

  it('is never the app\'s origin, so the template-refetch guard cannot reach the app', () => {
    expect(referenceOrigin({})).not.toBe(appOrigin({}));
    expect(referenceOrigin({})).not.toBe(resolveTargetsForRef({}, { app: 5173, ref: 5174, cs: 5175, api: 8017 }).baseURL);
  });
});
