import { describe, expect, it, vi } from 'vitest';
import { BLANK_GIF, DECLINED_FIELDS, FIXTURE_TOKENS, FIXTURE_TOKEN_COUNT, FIXTURE_TOKEN_PREFIX, MEMO_FILE, NEEDS_REVIEW_INFO_REQUEST, NOTICES, PERSONAS, PERSONA_DEFAULT_PASSWORD, PERSONA_EMAIL, PERSONA_INVITE_PASSWORD, PERSONA_RESET_PASSWORD, appOrigin, appPlan, appTokenKind, assertExpectedApiFailuresObserved, consumeExpectedApiFailure, credentialsFor, driverFor, expectApiStatus, expiredFixtureToken, firstMapPaintBudgetMs, fixtureToken, forgetPersonaSession, isExpectedApiFailure, memoFileIsRotated, memoFileRead, memoFileCounter, memoFileRotate, memoFileSetCounter, memoFileUpdate, personaCredentials, personaFor, personaSession, personaSessionMemo, personaSessionMemos, isStaleMemoFile, isExpectedSignInFailure401, listingsStubUrl, matchesListings, collectionStubUrls, collectionStubBody, newListingBody, submitStubUrl, WIZARD_LISTING_ID, sellerPageBody, referenceMe, referenceOrigin, referencePersona, referenceScreen, referenceUrl, runId, THROWAWAY_EMAIL_PATTERN, throwawayEmail } from './harness';
import { designListingsBody } from './design-listings.mjs';
import { designSellerPageBody, designSellerRows } from './design-seller-listings.mjs';
import { P } from '../src/logic.js';
import type { Page } from '@playwright/test';
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
// ---------------------------------------------------------------------------------------
// I4 (review round 1) — the one sanctioned stub in this suite, and its remote disarm.
//
// Spec D6 lets `prepare()` answer `/api/listings` with the DESIGN's own fixtures so the pixel
// and DOM oracles keep comparing the app against the design. Two things a global constraint
// rests on were previously enforced by an untested `if` and a comment: that the stub is NEVER
// armed against a remote target, and that it answers the collection endpoint on the APP origin
// and nothing else — not the photo route, not the reference server.
// ---------------------------------------------------------------------------------------
describe('the design-fixture listings stub (spec D6, review I4)', () => {
  it('is disarmed for a remote target — there the real, seeded API answers', () => {
    expect(listingsStubUrl({ PW_APP_URL: 'https://qa.foundation.vin' } as NodeJS.ProcessEnv)).toBeNull();
    expect(listingsStubUrl({ PW_APP_URL: 'https://qa.foundation.vin', PW_APP_PORT: '5473' } as NodeJS.ProcessEnv)).toBeNull();
  });

  it('is the local app origin\'s collection endpoint otherwise, on the port the run uses', () => {
    expect(listingsStubUrl({ PW_APP_PORT: '5473' } as NodeJS.ProcessEnv)).toBe('http://localhost:5473/api/listings');
    expect(listingsStubUrl({} as NodeJS.ProcessEnv)).toBe('http://localhost:5173/api/listings');
  });

  it('matches the collection endpoint and its query, and nothing else', () => {
    const base = 'http://localhost:5473/api/listings';
    expect(matchesListings(base, base)).toBe(true);
    expect(matchesListings(`${base}?limit=200`, base)).toBe(true);
    expect(matchesListings(`${base}?limit=200&cursor=abc`, base)).toBe(true);
    // The photo route is the real server's — an anonymised or unpublished listing's photographs
    // are exactly what its guard exists for, and the design's fixtures request none.
    expect(matchesListings(`${base}/abc/photos/1`, base)).toBe(false);
    expect(matchesListings(`${base}x`, base)).toBe(false);
    // The reference is a static prototype with no API at all; it keeps its fixture path.
    expect(matchesListings('http://localhost:5474/api/listings', base)).toBe(false);
  });

  it('serves every design fixture as one complete page', () => {
    const body = JSON.parse(designListingsBody()) as { items: unknown[]; next_cursor: string | null };
    expect(body.items).toHaveLength((P as unknown as unknown[]).length);
    expect(body.next_cursor, 'the stub is one page — a cursor would send load.ts round again').toBeNull();
  });
});

// ---------------------------------------------------------------------------------------
// A-SL2, as re-ruled by A-SL23 (2) — the two collection endpoints the oracle answers ITSELF,
// and both answers are now REAL pages.
//
// Same rule as the D6 stub above and the same reason it is pinned (review I4): the `if` that
// disarms it against a remote target is all that stands between the oracle's fixtures and a QA
// parity run, and an untested `if` is how it comes back.
// ---------------------------------------------------------------------------------------
describe('the seller and admin collection stubs (A-SL2, A-SL23 (2))', () => {
  it('is disarmed for a remote target — there the real, seeded API answers', () => {
    expect(collectionStubUrls({ PW_APP_URL: 'https://qa.foundation.vin' } as NodeJS.ProcessEnv)).toEqual([]);
    expect(collectionStubUrls({ PW_APP_URL: 'https://qa.foundation.vin', PW_APP_PORT: '5473' } as NodeJS.ProcessEnv)).toEqual([]);
    expect(submitStubUrl({ PW_APP_URL: 'https://qa.foundation.vin' } as NodeJS.ProcessEnv)).toBeNull();
  });

  it('names both collections on the local app origin, on the port the run uses', () => {
    expect(collectionStubUrls({ PW_APP_PORT: '5473' } as NodeJS.ProcessEnv))
      .toEqual(['http://localhost:5473/api/seller/listings', 'http://localhost:5473/api/admin/listings']);
    expect(collectionStubUrls({} as NodeJS.ProcessEnv))
      .toEqual(['http://localhost:5173/api/seller/listings', 'http://localhost:5173/api/admin/listings']);
  });

  it('serves every design seller fixture as one complete page (A-SL23 (2))', () => {
    // The frozen `seller-dash` capture used to depend on the app FAILING to read this endpoint —
    // a body with no `items`, which the real API cannot send. It answers now, and the app renders
    // what it answered: the design's own four rows, through the success path.
    const body = JSON.parse(collectionStubBody('http://localhost:5473/api/seller/listings')) as
      { items: unknown[]; next_cursor: string | null };
    expect(body.items).toEqual(designSellerRows());
    expect(body.items).toHaveLength(4);
    expect(body.next_cursor, 'the stub is one page — a cursor would send list() round again').toBeNull();
    expect(collectionStubBody('http://localhost:5473/api/seller/listings')).toBe(designSellerPageBody());
  });

  it('answers the admin collection with an empty page, never with no page at all', () => {
    // Nothing fetches it yet — it is armed for Task SL8 — but an ERROR-shaped answer is what
    // A-SL23 (2) took out of this harness, so this one is a page with no rows on it.
    expect(JSON.parse(collectionStubBody('http://localhost:5473/api/admin/listings')))
      .toEqual({ items: [], next_cursor: null });
  });

  it('answers Create a listing with one new id, for the four wizard captures (A-SL23 (1))', () => {
    expect(JSON.parse(newListingBody())).toEqual({ id: WIZARD_LISTING_ID });
    expect(submitStubUrl({ PW_APP_PORT: '5473' } as NodeJS.ProcessEnv))
      .toBe(`http://localhost:5473/api/seller/listings/${WIZARD_LISTING_ID}/submit`);
  });

  it('the empty-dashboard body is a REAL page with no rows on it (A-SL17)', () => {
    expect(JSON.parse(sellerPageBody([]))).toEqual({ items: [], next_cursor: null });
    expect(JSON.parse(sellerPageBody([{ id: 'x' }]))).toEqual({ items: [{ id: 'x' }], next_cursor: null });
  });
});

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
// Controller ruling, 2026-09-08. `smoke.spec.ts`'s "first map paint within budget" test hard-coded
// 1500ms — a LOCAL budget (the app served from localhost) — and asserted it against a REMOTE
// target too. The suite ran twice against QA (PW_APP_URL=https://qa.foundation.vin, from Indonesia
// to a US region) on 2026-09-08 and this one test failed both times at 1842ms while every other
// test passed: the number was measuring the network, not the app. The ruling is to keep measuring
// against remote targets with an honest, documented remote budget rather than skip the test —
// `firstMapPaintBudgetMs` is that budget, selected by whether `PW_APP_URL` is set.
describe('firstMapPaintBudgetMs (controller ruling 2026-09-08 — the QA proof measured the network, not the app)', () => {
  it('is 1500ms locally, when PW_APP_URL is unset', () => {
    expect(firstMapPaintBudgetMs({})).toBe(1500);
  });

  it('is 3000ms against a remote target, when PW_APP_URL is set', () => {
    expect(firstMapPaintBudgetMs({ PW_APP_URL: 'https://qa.foundation.vin' })).toBe(3000);
  });

  it('treats an empty PW_APP_URL as unset — the local budget applies', () => {
    expect(firstMapPaintBudgetMs({ PW_APP_URL: '' })).toBe(1500);
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
  it('are the ten accounts scripts/seed_persona.py writes', () => {
    expect(Object.keys(PERSONAS)).toEqual(['design', 'buyer', 'seller', 'pending', 'needsReview', 'declined', 'verified', 'unverified', 'invited', 'verifyMe']);
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

  it('give the four applicants their states and no roles', () => {
    expect(PERSONAS.pending.state).toBe('pending');
    expect(PERSONAS.needsReview.state).toBe('needs_review');
    expect(PERSONAS.declined.state).toBe('declined');
    // A-S4 (Task S4): `verified@` is an address that has been confirmed and has never applied.
    // A5.4's bootstrap lands it on the Request Access card, which is how the APP now reaches
    // `gate-apply` — the design's own "Request access" link sends an anonymous visitor to the
    // sign-up card since A8.1c, so the link is no longer that state's way in. S3 seeded it.
    expect(PERSONAS.verified.state).toBe('verified');
    expect(PERSONAS.verified.email).toBe('verified@practice-match.test');
    // `labels.initials("Verified Applicant")` — the seed's display name for the account.
    expect(PERSONAS.verified.initials).toBe('VA');
    // A-S5 (Task S5): the last two identity states — see the block of its own further down.
    expect(PERSONAS.unverified.state).toBe('unverified');
    expect(PERSONAS.invited.state, 'invited@ is `verified`; what it lacks is a password').toBe('verified');
    for (const key of ['pending', 'needsReview', 'declined', 'verified', 'unverified', 'invited', 'verifyMe'] as const) {
      expect(PERSONAS[key].roles).toEqual([]);
      expect(PERSONAS[key].role, 'labels.role_label with no grants and no affiliation').toBe('Applicant');
    }
  });

  it('present the one documented password, whichever persona is asked for — bar the invited one', () => {
    for (const key of Object.keys(PERSONAS) as (keyof typeof PERSONAS)[]) {
      // `invited@` is the exception the seed built on purpose: no usable password at all, so
      // asking for one throws rather than hands back a credential that cannot work (A-S5).
      if (key === 'invited') { expect(() => personaCredentials(key, {})).toThrow(); continue; }
      expect(personaCredentials(key, {})).toEqual({ email: PERSONAS[key].email, password: PERSONA_DEFAULT_PASSWORD });
      expect(personaCredentials(key, { PERSONA_PASSWORD: 'from-railway' }).password).toBe('from-railway');
    }
  });

  it('memoise one session EACH, so ten personas spend at most ten of SIGNIN_IP\'s thirty attempts', () => {
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

  // FIVE since A8.8b declared `startNotice`: the sentence this pins — "named on every request, so
  // no state inherits a value another state set" — is only true of a prop the payload actually
  // carries, and `startNotice` is the one that decides whether the sign-in card shows a message.
  // It is always `''` until Task S5 gives `reach()` a `notice` option; naming it is what stops a
  // notice state, once S5 adds one, leaking into the next capture.
  it('always serves the design at "/" and names all seven injectable prototype props on every request', () => {
    const url = referenceUrl();
    expect(url.startsWith('/?props=')).toBe(true);
    expect(props(url)).toEqual({ startScreen: 'gate', startGate: '', startViewport: 'desktop', me: null, startNotice: '', startAnswerNote: '', startMyListings: null });
  });

  it('names the screen and hands over that state\'s own account, for every member family', () => {
    expect(props(referenceUrl({ screen: 'browse' }))).toEqual({ startScreen: 'browse', startGate: '', startViewport: 'desktop', me: PERSONAS.buyer, startNotice: '', startAnswerNote: '', startMyListings: null });
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
    expect(appPlan({ screen: 'browse' })).toEqual({ persona: 'buyer', url: '/browse' });
    expect(appPlan({ screen: 'detail' })).toEqual({ persona: 'buyer', url: '/practices/p1' });
    expect(appPlan({ screen: 'requests' })).toEqual({ persona: 'buyer', url: '/requests' });
    expect(appPlan({ screen: 'seller' })).toEqual({ persona: 'seller', url: '/seller' });
    expect(appPlan({ screen: 'admin' })).toEqual({ persona: 'design', url: '/admin' });
  });

  it('signs nobody in for the sign-in gate: that is what an anonymous visitor sees', () => {
    expect(appPlan()).toEqual({ persona: null, url: '/' });
    expect(appPlan({ gate: 'signin' })).toEqual({ persona: null, url: '/' });
  });

  // A-S4: the design's own "Request access" link used to be this state's way in on the app.
  // A8.1c makes that link open the SIGN-UP card for an anonymous visitor — correct product
  // behaviour, since an applicant needs an account first — so the application gate is reached
  // the way the spec says a verified address reaches it: by being one. Nothing is clicked on
  // any state any more, so `appPlan` no longer carries a click at all.
  it('reaches the application gate by signing in as an address that is verified and has not applied', () => {
    expect(appPlan({ gate: 'apply', persona: 'verified' })).toEqual({ persona: 'verified', url: '/' });
  });

  // A-S5 restores ONE click, for `gate-reapply` alone: a declined account reaches the application
  // form through its own card. Every other state is still an account and a route.
  it('carries no click for any state but the declined account\'s re-apply', () => {
    for (const target of [{}, { gate: 'signin' as const }, { gate: 'apply' as const, persona: 'verified' as const }, { screen: 'browse' as const }]) {
      expect(appPlan(target), JSON.stringify(target)).not.toHaveProperty('click');
    }
  });

  it('reaches the two status gates by signing in as an account actually in that state', () => {
    expect(appPlan({ gate: 'pending', persona: 'pending' })).toEqual({ persona: 'pending', url: '/' });
    expect(appPlan({ gate: 'rejected', persona: 'declined' })).toEqual({ persona: 'declined', url: '/' });
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

  // Round 3, ruling 2. The id is minted ONCE PER RUN by `tests/global-setup.ts` and read from the
  // environment, because the environment is the only thing every worker of a run inherits from the
  // runner. Round 2 derived it from the worker's own start time, which was stable inside a GREEN
  // run (one worker process) and changed on every worker restart — and a restart is the only case
  // this file exists for, since Playwright starts a new worker after each test failure.
  it('reads the run id the runner minted, so every worker of one run agrees on it', () => {
    expect(runId({ PW_RUN_ID: 'f4c1e0a2-9b7d-4e51-8a2c-6d0f1b3e5a7c' })).toBe('f4c1e0a2-9b7d-4e51-8a2c-6d0f1b3e5a7c');
    expect(runId({ PW_RUN_ID: 'a' })).not.toBe(runId({ PW_RUN_ID: 'b' }));
  });

  it('has no run id outside a Playwright run, and then keeps no memo at all', () => {
    // A vitest process, or `playwright test` with the globalSetup removed. "No memo" is the safe
    // reading: the in-memory memo still spends one sign-in per persona per worker, and nothing is
    // shared with a run it does not belong to.
    expect(runId({})).toBe('');
    expect(memoFileRead(memoFileUpdate(null, 'buyer', [C('pm_session')], ''), 'buyer', ''), 'an unstamped file is nobody\'s memo').toBeNull();
  });

  it('ignores and replaces a memo file another run stamped', () => {
    const stale = memoFileUpdate(null, 'buyer', [C('pm_session')], 'run-A');
    expect(memoFileRead(stale, 'buyer', 'run-A'), 'sanity: its own run reads it').not.toBeNull();
    expect(memoFileRead(stale, 'buyer', 'run-B'), 'another run: no memo').toBeNull();
    const fresh = memoFileUpdate(stale, 'buyer', [C('pm_session')], 'run-B');
    expect(JSON.parse(fresh).run).toBe('run-B');
    expect(memoFileRead(fresh, 'buyer', 'run-A'), 'and run A cannot read the replacement').toBeNull();
  });

  // The decision `tests/global-setup.ts` makes, as a pure function. It runs in the RUNNER, before
  // any worker, and removes a file a DIFFERENT run left behind — so a run never starts by adopting
  // a session that may since have been revoked, whatever cwd Playwright was launched from (its own
  // clearing of `test-results/` is anchored there; MEMO_FILE is not).
  it('isStaleMemoFile: only a file that cannot be shown to be this run\'s is stale', () => {
    const mine = memoFileUpdate(null, 'buyer', [C('pm_session')], 'run-A');
    expect(isStaleMemoFile(mine, 'run-A'), 'this run\'s own file survives — a restarted worker needs it').toBe(false);
    expect(isStaleMemoFile(mine, 'run-B')).toBe(true);
    expect(isStaleMemoFile(null, 'run-A'), 'nothing there to delete').toBe(false);
    expect(isStaleMemoFile('{ not json', 'run-A'), 'unreadable cannot be shown to be ours').toBe(true);
    expect(isStaleMemoFile(mine, ''), 'no run id at all: keep nothing').toBe(true);
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
    // `appOrigin()`/`referenceOrigin()` with NO argument — the same environment lookup
    // `driverFor`'s own default parameter uses (`appUrl = appOrigin()`, harness.ts). `appOrigin({})`
    // pins the constant `http://localhost:5173` regardless of the real environment, so under
    // `PW_APP_PORT` this URL and driverFor's internal default disagreed and the test failed for a
    // reason unrelated to what it is meant to pin (I12, housekeeping).
    expect(driverFor(`${appOrigin()}/browse`)).toBe('app');
    expect(driverFor(`${referenceOrigin()}/`)).toBe('reference');
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
    expect(referenceOrigin({})).not.toBe(resolveTargets({}, { app: 5173, ref: 5174, cs: 5175, api: 8017 }).baseURL);
  });
});

// ---------------------------------------------------------------------------------------
// signin-form.spec.ts's wrong-password case deliberately provokes a 401 and filters the one
// console line Chromium logs for it out of the errors the test otherwise fails on. Chromium's
// wording differs by transport: HTTP/1.1 (Vite's dev proxy — every local and CI run) carries a
// reason phrase, "Failed to load resource: the server responded with a status of 401
// (Unauthorized)"; HTTP/2 (a live deployment, e.g. PW_APP_URL=https://qa.foundation.vin) has no
// reason phrase at the protocol level, so Chromium logs "… a status of 401 ()" instead.
// Matching `/401 \(Unauthorized\)/` — the original filter — missed the second form, so the
// deliberate 401 leaked through and failed the test only on a live run. Matching the status
// code alone, word-bounded, recognises the line under both transports without swallowing an
// unrelated status that happens to share the digits.
// ---------------------------------------------------------------------------------------
describe('isExpectedSignInFailure401 — the sign-in form\'s deliberate 401, across transports', () => {
  it('matches the HTTP/1.1 console line (a reason phrase present, via Vite\'s dev proxy)', () => {
    expect(isExpectedSignInFailure401('Failed to load resource: the server responded with a status of 401 (Unauthorized)')).toBe(true);
  });

  it('matches the HTTP/2 console line (no reason phrase — a live QA/production run)', () => {
    expect(isExpectedSignInFailure401('Failed to load resource: the server responded with a status of 401 ()')).toBe(true);
  });

  it('does not match an unrelated console error', () => {
    expect(isExpectedSignInFailure401('Failed to load resource: the server responded with a status of 429 (Too Many Requests)')).toBe(false);
  });

  it('is word-bounded: a status code that merely contains "401" is not mistaken for it', () => {
    expect(isExpectedSignInFailure401('Failed to load resource: the server responded with a status of 4010 (Bogus)')).toBe(false);
    expect(isExpectedSignInFailure401('some other line mentioning 14010 in passing')).toBe(false);
  });

  it('does not match an ordinary page error unrelated to any HTTP status', () => {
    expect(isExpectedSignInFailure401('pageerror: TypeError: something failed')).toBe(false);
  });
});

// ---------------------------------------------------------------------------------------
// Task S5 (controller amendment A-S5) — the fifteen account-screen states.
//
// Everything below is the DECISION half of `reach()`: which account, which URL, which fixture
// token, which prototype prop. All of it is pure so the run's whole rate-limit and token budget
// can be counted here, without a browser and without spending either.
// ---------------------------------------------------------------------------------------
describe('the three identity personas (A-S5)', () => {
  it('names the accounts scripts/seed_persona.py seeds for the account screens', () => {
    expect(PERSONAS.unverified).toEqual({ email: 'unverified@practice-match.test', name: 'Unverified Applicant', role: 'Applicant', initials: 'UA', state: 'unverified', roles: [] });
    expect(PERSONAS.verified).toMatchObject({ email: 'verified@practice-match.test', state: 'verified' });
    expect(PERSONAS.invited).toEqual({ email: 'invited@practice-match.test', name: 'Invited Staff', role: 'Applicant', initials: 'IS', state: 'verified', roles: [] });
    // A-S5.2: the tenth account. It exists only to own the verify tokens — consuming one confirms
    // its account for good, and `unverified@` has to survive every capture unconfirmed.
    expect(PERSONAS.verifyMe).toEqual({ email: 'verify-me@practice-match.test', name: 'Verify Fixture', role: 'Applicant', initials: 'VF', state: 'unverified', roles: [] });
  });

  // The seed hashes a secret it generates fresh and keeps nowhere, precisely so the shared
  // persona password does not open this account: the invite token is the only way in. Asking for
  // a credential that cannot exist is a bug in the caller, and it says so where the caller is.
  it('personaCredentials refuses the invited account, which has no usable password', () => {
    expect(() => personaCredentials('invited')).toThrow(/invited@practice-match\.test/);
    expect(() => credentialsFor('invited', false)).toThrow(/token/i);
  });

  // …until the run accepts an invitation for it, which is the moment it HAS one. That is the same
  // fact the rotation flag records for `verified@`, and the same mechanism records it.
  it('credentialsFor hands back the invited account\'s password once this run has set one', () => {
    expect(credentialsFor('invited', true, {})).toEqual({ email: 'invited@practice-match.test', password: PERSONA_INVITE_PASSWORD });
    expect(PERSONA_INVITE_PASSWORD.length, 'the invite card says staff passwords are at least 14').toBeGreaterThanOrEqual(14);
    expect(PERSONA_INVITE_PASSWORD).not.toBe(PERSONA_RESET_PASSWORD);
  });

  it('credentialsFor hands back the documented default until the run rotates it, then the new one', () => {
    expect(credentialsFor('verified', false, {})).toEqual({ email: 'verified@practice-match.test', password: PERSONA_DEFAULT_PASSWORD });
    expect(credentialsFor('verified', true, {})).toEqual({ email: 'verified@practice-match.test', password: PERSONA_RESET_PASSWORD });
    // PERSONA_PASSWORD still wins for the un-rotated case (the live QA run), and cannot win for
    // the rotated one: the password the reset SET is the one the account now has.
    expect(credentialsFor('buyer', false, { PERSONA_PASSWORD: 'from-railway' }).password).toBe('from-railway');
    expect(credentialsFor('verified', true, { PERSONA_PASSWORD: 'from-railway' }).password).toBe(PERSONA_RESET_PASSWORD);
  });

  it('the two documented passwords differ, or the rotation would prove nothing', () => {
    expect(PERSONA_RESET_PASSWORD).not.toBe(PERSONA_DEFAULT_PASSWORD);
    expect(PERSONA_RESET_PASSWORD.length, 'the server floor is 12, and 14 for a privileged account').toBeGreaterThanOrEqual(14);
  });
});

describe('fixture tokens — twelve per purpose, single use, spent in order (A-S5)', () => {
  it('mirrors the seed script\'s documented pattern exactly', () => {
    expect(FIXTURE_TOKEN_PREFIX).toBe('fixture-');
    expect(FIXTURE_TOKENS).toEqual({ verify: 'fixture-verify-', reset: 'fixture-reset-', invite: 'fixture-invite-' });
    expect(FIXTURE_TOKEN_COUNT).toBe(12);
    for (const prefix of Object.values(FIXTURE_TOKENS)) expect(prefix.startsWith(FIXTURE_TOKEN_PREFIX)).toBe(true);
  });

  it('numbers them 01…12, zero-padded, as the seed inserts them', () => {
    expect(fixtureToken('verify', 1)).toBe('fixture-verify-01');
    expect(fixtureToken('reset', 9)).toBe('fixture-reset-09');
    expect(fixtureToken('invite', 12)).toBe('fixture-invite-12');
  });

  it('refuses to invent a thirteenth, naming the purpose and the seed', () => {
    expect(() => fixtureToken('verify', 13)).toThrow(/verify/);
    expect(() => fixtureToken('verify', 13)).toThrow(/seed_persona/);
    expect(() => fixtureToken('reset', 0)).toThrow();
  });

  // The expired cards and the invite-expired notice need a token the seed NEVER created, so the
  // real endpoint answers its real 400. It has to look like a fixture token and be none of them.
  it('the expired token is of the documented shape and is not one of the twelve', () => {
    expect(expiredFixtureToken('verify')).toBe('fixture-verify-expired');
    for (const kind of ['verify', 'reset', 'invite'] as const) {
      const all = Array.from({ length: FIXTURE_TOKEN_COUNT }, (_, i) => fixtureToken(kind, i + 1));
      expect(all).not.toContain(expiredFixtureToken(kind));
      expect(expiredFixtureToken(kind).startsWith(FIXTURE_TOKENS[kind])).toBe(true);
    }
  });

  // The counter lives in the run's own memo file beside the persona jars, so a worker Playwright
  // restarts after a failure continues the sequence instead of re-spending token 01 — which is
  // single-use and already gone.
  it('the run-scoped counter advances once per take and survives a restarted worker', () => {
    // The take is a read, a decision and a write — the shape `takeCounter` uses (M8).
    let file: string | null = null;
    const take = (name: string) => { const n = memoFileCounter(file, name, 'run-A') + 1; file = memoFileSetCounter(file, name, n, 'run-A'); return n; };
    expect([take('verify'), take('verify'), take('verify')]).toEqual([1, 2, 3]);
    expect(take('reset'), 'each purpose counts on its own').toBe(1);
    // A restarted worker reads the same file and carries on.
    expect(memoFileCounter(file, 'verify', 'run-A')).toBe(3);
    expect(take('verify')).toBe(4);
  });

  it('another run\'s counters are never inherited, and neither are its jars', () => {
    const previous = memoFileSetCounter(memoFileUpdate(null, 'buyer', [{ name: 'pm_session', value: 'x' }], 'run-old'), 'verify', 7, 'run-old');
    expect(memoFileCounter(previous, 'verify', 'run-new'), 'a fresh run starts at zero').toBe(0);
    expect(memoFileRead(memoFileSetCounter(previous, 'verify', 1, 'run-new'), 'buyer', 'run-new')).toBeNull();
  });

  it('taking a counter leaves this run\'s persona jars alone', () => {
    const withJar = memoFileUpdate(null, 'buyer', [{ name: 'pm_session', value: 'x' }], 'run-A');
    const after = memoFileSetCounter(withJar, 'verify', 1, 'run-A');
    expect(memoFileRead(after, 'buyer', 'run-A')).toEqual([{ name: 'pm_session', value: 'x' }]);
    expect(memoFileCounter(after, 'verify', 'run-A')).toBe(1);
  });

  // M14 (review round 1): the default run id is `randomUUID()` (hex and hyphens), but an outer
  // harness may set `PW_RUN_ID` to a CI value carrying `/`, `:` or a space — which would make the
  // live sign-up 422 with nothing pointing at the cause.
  it('a run id that is not email-safe is sanitised rather than pasted into the local part', () => {
    expect(throwawayEmail('signup', 'a/b:c d', 1)).toBe('e2e-a-b-c-d-signup-1@example.org');
    expect(throwawayEmail('forgot', 'refs/heads/feat#3', 2)).toBe('e2e-refs-heads-feat-3-forgot-2@example.org');
    // The default shape is already safe and must survive untouched.
    expect(throwawayEmail('signup', '0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0', 1)).toBe('e2e-0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0-signup-1@example.org');
    // Fix round 2, M4: `purpose` is sanitised by the same class. Both call sites pass a literal
    // today, but a caller with a space or a slash would mint an address the seed's restoration
    // pattern does NOT match — and the account would then stay on QA for ever, which is the exact
    // leak round 1 was ruled to close.
    expect(throwawayEmail('sign up', 'run-A', 1)).toBe('e2e-run-A-sign-up-1@example.org');
    expect(throwawayEmail('forgot/again', 'run-A', 2)).toBe('e2e-run-A-forgot-again-2@example.org');
    for (const address of [throwawayEmail('signup', 'a/b:c d', 1), throwawayEmail('forgot', '', 3)]) {
      expect(address.split('@')[0], 'every local part is RFC-safe').toMatch(/^[A-Za-z0-9._-]+$/);
    }
  });

  // Fix round 1, ruling 4 (2026-09-08): the seed now DELETES these accounts on every restoration,
  // so the shape they are recognised by has to be one string, shared — `scripts/seed_persona.py`
  // mirrors `THROWAWAY_EMAIL_PATTERN` and `tests/test_docs.py` pins the two equal. A pattern that
  // drifted wider than the addresses this function makes would delete somebody else's account.
  it('every address it makes matches the one pattern the seed deletes by, and nothing else does', () => {
    const shape = new RegExp(THROWAWAY_EMAIL_PATTERN);
    for (const address of [
      throwawayEmail('signup', '0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0', 1),
      throwawayEmail('forgot', 'a/b:c d', 12),
      throwawayEmail('signup', '', 3),
      throwawayEmail('sign up', 'run-A', 1)                    // M4: an unsanitised purpose would escape it
    ]) expect(address, address).toMatch(shape);
    for (const other of [
      'e2e-run-signup-1@example.org.uk',
      'e2e-run-signup-1@evil.example.org',
      'not-e2e-run-signup-1@example.org',
      'buyer@practice-match.test',
      'someone@example.org'
    ]) expect(other, other).not.toMatch(shape);
  });

  it('a throwaway address is distinct per take, so FORGOT_EMAIL is never the binding limit', () => {
    const a = throwawayEmail('forgot', 'run-A', 1);
    const b = throwawayEmail('forgot', 'run-A', 2);
    expect(a).not.toBe(b);
    for (const address of [a, b]) {
      expect(address).toMatch(/^e2e-run-A-forgot-\d+@example\.org$/);
      expect(address, 'never a real mailbox: example.org is RFC 2606 reserved').toContain('@example.org');
    }
  });
});

// ---------------------------------------------------------------------------------------
// M4 (review round 1): the rotation is recorded only once the API has CONFIRMED it.
//
// `submitNotice` types two passwords, clicks the design's own button, and waits for the notice the
// spec says that outcome produces. Recording the rotation before that wait means a submit the API
// REFUSED — a spent token, a policy refusal — still writes `rotated` to the run's memo and forgets
// a live session for a password change that never happened: the test fails at the wait, and every
// later sign-in as that account 401s a long way from the cause. The notice IS the confirmation.
//
// Driven through a stub page, in an isolated module instance so the module-level rotation set and
// persona memos this touches cannot leak into the rest of this file.
// ---------------------------------------------------------------------------------------
describe('submitNotice records a rotation only after the API confirms it (M4)', () => {
  const stubPage = (waitFor: () => Promise<void>) => ({
    getByLabel: () => ({ fill: async () => {} }),
    getByRole: () => ({ click: async () => {} }),
    getByText: () => ({ first: () => ({ waitFor }) })
  }) as unknown as Page;

  const freshHarness = async () => { vi.resetModules(); return import('./harness'); };

  it('a submit the API refused leaves the memo un-rotated and the session intact', async () => {
    const h = await freshHarness();
    const jar = [{ name: 'pm_session', value: 'still-live' }] as unknown as NonNullable<typeof h.personaSessionMemos.verified.cookies>;
    h.personaSessionMemos.verified.cookies = jar;

    await expect(h.submitNotice(stubPage(() => Promise.reject(new Error('the notice never appeared'))), 'password-updated'))
      .rejects.toThrow(/never appeared/);

    expect(h.personaSessionMemos.verified.cookies, 'a session that is still live must not be forgotten').toBe(jar);
    expect(h.personaCredentials('verified', {}).password, 'the password did not change, so the run must not think it did')
      .toBe(h.PERSONA_DEFAULT_PASSWORD);
  });

  it('a submit the API accepted records the rotation and drops the session it revoked', async () => {
    const h = await freshHarness();
    h.personaSessionMemos.verified.cookies = [{ name: 'pm_session', value: 'about-to-be-revoked' }] as unknown as NonNullable<typeof h.personaSessionMemos.verified.cookies>;

    await h.submitNotice(stubPage(() => Promise.resolve()), 'password-updated');

    expect(h.personaSessionMemos.verified.cookies, 'the reset revoked every session this account had').toBeNull();
    expect(h.personaCredentials('verified', {}).password).toBe(h.PERSONA_RESET_PASSWORD);
  });

  it('the same holds for an accepted invitation, which is the other password this run sets', async () => {
    const h = await freshHarness();
    expect(() => h.personaCredentials('invited', {})).toThrow();
    await h.submitNotice(stubPage(() => Promise.resolve()), 'invite-set');
    expect(h.personaCredentials('invited', {}).password).toBe(h.PERSONA_INVITE_PASSWORD);
  });

  it('an invitation the API REFUSED sets no password at all — the notice says so', async () => {
    const h = await freshHarness();
    await h.submitNotice(stubPage(() => Promise.resolve()), 'invite-expired');
    expect(() => h.personaCredentials('invited', {}), 'a dead link set nothing').toThrow();
  });
});

describe('the rotation flag — a reset changes verified@\'s password for the rest of the run (A-S5)', () => {
  // `POST /api/auth/password/reset` rotates the password AND revokes every session, and
  // `verified@` is also `gate-apply`'s screenshot persona (A-S4). Without this the memoised jar
  // would name a revoked session and every later capture would run anonymous, with no failure
  // anywhere near the cause.
  it('is off until set, on afterwards, and scoped to the run and the persona', () => {
    expect(memoFileIsRotated(null, 'verified', 'run-A')).toBe(false);
    const rotated = memoFileRotate(null, 'verified', 'run-A');
    expect(memoFileIsRotated(rotated, 'verified', 'run-A')).toBe(true);
    expect(memoFileIsRotated(rotated, 'buyer', 'run-A'), 'one account\'s reset is not another\'s').toBe(false);
    expect(memoFileIsRotated(rotated, 'verified', 'run-B'), 'the seed restores the password next run').toBe(false);
  });

  it('setting it twice is the same as setting it once, and it keeps the run\'s jars', () => {
    const jar = memoFileUpdate(null, 'buyer', [{ name: 'pm_session', value: 'x' }], 'run-A');
    const once = memoFileRotate(jar, 'verified', 'run-A');
    const twice = memoFileRotate(once, 'verified', 'run-A');
    expect(memoFileIsRotated(twice, 'verified', 'run-A')).toBe(true);
    expect(memoFileRead(twice, 'buyer', 'run-A')).toEqual([{ name: 'pm_session', value: 'x' }]);
  });
});

describe('referenceUrl for the fifteen account states (A-S5)', () => {
  const props = (url: string) => JSON.parse(decodeURIComponent(new URL(url, 'http://x').searchParams.get('props')!));

  it('reaches the four form cards and the three status cards through startGate alone', () => {
    for (const gate of ['signup', 'forgot', 'reset', 'invite', 'verify-expired', 'reset-expired'] as const) {
      expect(props(referenceUrl({ gate })), gate).toEqual({ startScreen: 'gate', startGate: gate, startViewport: 'desktop', me: null, startNotice: '', startAnswerNote: '', startMyListings: null });
    }
  });

  // The check-email card prints the address it wrote to, and the app has a session to take it
  // from — so the reference is handed the same account, exactly as the two status gates are.
  it('hands the unverified account over for the check-email card, which prints its address', () => {
    expect(props(referenceUrl({ gate: 'check-email', persona: 'unverified' }))).toMatchObject({ startGate: 'check-email', me: PERSONAS.unverified });
  });

  // Measured against the real Component: `startGate` is applied BEFORE the account branch, and a
  // `needs_review` account maps to the "under review" card — so passing `me` here would put the
  // reference on the wrong card. Nothing is lost: an applicant's `auth` is false on both targets,
  // and the gate screen's header is driven by `auth` alone.
  it('withholds the account for the answer card, and carries the note through A9.1\'s prop', () => {
    const p = props(referenceUrl({ gate: 'answer', persona: 'needsReview', note: NEEDS_REVIEW_INFO_REQUEST }));
    expect(p).toEqual({ startScreen: 'gate', startGate: 'answer', startViewport: 'desktop', me: null, startNotice: '', startAnswerNote: NEEDS_REVIEW_INFO_REQUEST, startMyListings: null });
  });

  // The app captures this one SIGNED IN — a buyer who deep-linked a route their access does not
  // include — and no `me` can buy `auth: true` on a gate screen (an active account overrides the
  // gate and lands on Browse). `startScreen` sets `auth`; `startGate` then puts it back on the
  // gate; and the design's own fixture identity is, letter for letter, `buyer@`'s computed label.
  it('buys the signed-in header for the unavailable card through startScreen, with no account', () => {
    expect(props(referenceUrl({ gate: 'unavailable', persona: 'buyer' }))).toEqual({ startScreen: 'browse', startGate: 'unavailable', startViewport: 'desktop', me: null, startNotice: '', startAnswerNote: '', startMyListings: null });
    expect(referenceScreen({ gate: 'unavailable', persona: 'buyer' })).toBe('browse');
    expect(referencePersona({ gate: 'unavailable', persona: 'buyer' })).toBeNull();
  });

  // The declined account's re-apply: `startGate: 'apply'` puts the reference straight on the
  // form, and `me` is withheld for the same reason as the answer card — a declined account maps
  // back to its own card.
  it('withholds the account for the declined re-apply, whose card the reference skips', () => {
    expect(props(referenceUrl({ gate: 'apply', persona: 'declined' }))).toMatchObject({ startGate: 'apply', me: null });
    expect(props(referenceUrl({ gate: 'apply', persona: 'verified' })), 'the ordinary application gate is unchanged').toMatchObject({ startGate: 'apply', me: PERSONAS.verified });
  });

  it('drives the five notice states through startNotice, with the spec\'s own copy', () => {
    for (const key of Object.keys(NOTICES) as Array<keyof typeof NOTICES>) {
      expect(props(referenceUrl({ gate: 'signin', notice: key })), key).toEqual({ startScreen: 'gate', startGate: 'signin', startViewport: 'desktop', me: null, startNotice: NOTICES[key], startAnswerNote: '', startMyListings: null });
    }
  });

  it('the five notice texts are the spec\'s §3 copy, letter for letter', () => {
    expect(NOTICES).toEqual({
      verified: 'Your address is verified. Sign in to complete your access request.',
      'reset-sent': 'If that address has an account, a reset link is on its way. It is valid for 1 hour.',
      'password-updated': 'Password updated. Sign in with your new password.',
      'invite-set': 'Your password is set. Sign in with your email and the password you just chose.',
      'invite-expired': 'This invitation link is no longer valid. Ask the VIN Foundation for a new one.'
    });
  });
});

describe('appPlan for the fifteen account states — real routes, real tokens (A-S5)', () => {
  it('opens the two public forms at their own routes, signed in as nobody', () => {
    expect(appPlan({ gate: 'signup' })).toEqual({ persona: null, url: '/signup' });
    expect(appPlan({ gate: 'forgot' })).toEqual({ persona: null, url: '/forgot' });
  });

  it('carries a fixture token into the reset and invite forms, which render without spending it', () => {
    expect(appPlan({ gate: 'reset' }, 'fixture-reset-03')).toEqual({ persona: null, url: '/reset?token=fixture-reset-03' });
    expect(appPlan({ gate: 'invite' }, 'fixture-invite-03')).toEqual({ persona: null, url: '/accept-invite?token=fixture-invite-03' });
    expect(appTokenKind({ gate: 'reset' })).toBe('reset');
    expect(appTokenKind({ gate: 'invite' })).toBe('invite');
  });

  it('uses a token no seed created for the expired cards, so the real endpoint answers its real 400', () => {
    expect(appPlan({ gate: 'verify-expired' })).toEqual({ persona: null, url: '/verify?token=fixture-verify-expired' });
    expect(appPlan({ gate: 'reset-expired' })).toEqual({ persona: null, url: '/reset?token=fixture-reset-expired' });
    expect(appTokenKind({ gate: 'verify-expired' }), 'an unseeded token spends none of the twelve').toBeNull();
    expect(appTokenKind({ gate: 'reset-expired' })).toBeNull();
  });

  it('reaches the check-email and answer cards by BEING an account in that state', () => {
    expect(appPlan({ gate: 'check-email', persona: 'unverified' })).toEqual({ persona: 'unverified', url: '/' });
    expect(appPlan({ gate: 'answer', persona: 'needsReview', note: 'anything' })).toEqual({ persona: 'needsReview', url: '/' });
  });

  it('reaches the unavailable card by deep-linking a route the account may not open', () => {
    expect(appPlan({ gate: 'unavailable', persona: 'buyer' })).toEqual({ persona: 'buyer', url: '/admin' });
  });

  it('reaches the re-apply form through the declined card\'s own primary button', () => {
    expect(appPlan({ gate: 'apply', persona: 'declined' })).toEqual({ persona: 'declined', url: '/', click: 'Reply with more information' });
    expect(appPlan({ gate: 'apply', persona: 'verified' }), 'a verified address lands on the form with no click').toEqual({ persona: 'verified', url: '/' });
  });

  it('drives each notice state through the real flow that produces it', () => {
    expect(appPlan({ gate: 'signin', notice: 'verified' }, 'fixture-verify-05')).toEqual({ persona: null, url: '/verify?token=fixture-verify-05' });
    expect(appPlan({ gate: 'signin', notice: 'reset-sent' })).toEqual({ persona: null, url: '/forgot' });
    expect(appPlan({ gate: 'signin', notice: 'password-updated' }, 'fixture-reset-05')).toEqual({ persona: null, url: '/reset?token=fixture-reset-05' });
    expect(appPlan({ gate: 'signin', notice: 'invite-set' }, 'fixture-invite-05')).toEqual({ persona: null, url: '/accept-invite?token=fixture-invite-05' });
    expect(appPlan({ gate: 'signin', notice: 'invite-expired' })).toEqual({ persona: null, url: '/accept-invite?token=fixture-invite-expired' });
  });

  // The whole run's token budget, counted here rather than discovered at token thirteen.
  it('spends three verify, five reset and five invite tokens of the twelve seeded per purpose', () => {
    const perRun = [
      // visual.spec.ts and dom.spec.ts each drive every state once…
      ...[{ gate: 'reset' as const }, { gate: 'invite' as const }, { gate: 'signin' as const, notice: 'verified' as const },
        { gate: 'signin' as const, notice: 'password-updated' as const }, { gate: 'signin' as const, notice: 'invite-set' as const }],
      ...[{ gate: 'reset' as const }, { gate: 'invite' as const }, { gate: 'signin' as const, notice: 'verified' as const },
        { gate: 'signin' as const, notice: 'password-updated' as const }, { gate: 'signin' as const, notice: 'invite-set' as const }],
      // …and account-flows.spec.ts consumes one of each purpose in its live flows.
      { gate: 'signin' as const, notice: 'verified' as const }, { gate: 'signin' as const, notice: 'password-updated' as const }, { gate: 'signin' as const, notice: 'invite-set' as const }
    ];
    const spent = { verify: 0, reset: 0, invite: 0 };
    for (const target of perRun) { const kind = appTokenKind(target); if (kind) spent[kind] += 1; }
    expect(spent).toEqual({ verify: 3, reset: 5, invite: 5 });
    for (const n of Object.values(spent)) expect(n).toBeLessThanOrEqual(FIXTURE_TOKEN_COUNT);
  });
});

// ---------------------------------------------------------------------------------------
// The console-error allow-list (A-S5 ruling 4).
//
// Three states deliberately provoke `TOKEN_INVALID` — a real 400 — and Chromium logs every 4xx
// subresource as a console error `prepare()` otherwise fails the test on. The exemption is one
// status per arming, consumed by exactly one matching line, and it must actually be CONSUMED:
// an allowance nobody used means the state stopped provoking the failure it exists to show.
// ---------------------------------------------------------------------------------------
describe('expectApiStatus — a per-page, per-status allowance, never a blanket exemption (A-S5)', () => {
  // `appOrigin()`/`referenceOrigin()` with NO argument (I12 review round 1): `expectApiStatus` and
  // `consumeExpectedApiFailure` call `driverFor(page.url())` with no second argument either, so
  // `driverFor`'s own default (`appUrl = appOrigin()`) reads the REAL environment. Freezing this
  // mock page's URL to the `{}` default (`localhost:5173`) while `driverFor` compares it against
  // whatever `PW_APP_PORT` actually holds is the same drift the `driverFor` describe above fixed.
  const appPage = () => ({ url: () => `${appOrigin()}/` }) as unknown as Page;
  const referencePage = () => ({ url: () => `${referenceOrigin()}/` }) as unknown as Page;
  const line = (status: number) => `Failed to load resource: the server responded with a status of ${status} (Bad Request)`;

  it('consumes exactly one matching console error per arming', () => {
    const page = appPage();
    expectApiStatus(page, 400);
    expect(consumeExpectedApiFailure(page, line(400)), 'the armed one is allowed').toBe(true);
    expect(consumeExpectedApiFailure(page, line(400)), 'a second 400 is not covered by one arming').toBe(false);
  });

  it('never allows a status that was not armed', () => {
    const page = appPage();
    expectApiStatus(page, 400);
    expect(consumeExpectedApiFailure(page, line(429))).toBe(false);
    expect(consumeExpectedApiFailure(page, 'pageerror: TypeError: something failed')).toBe(false);
  });

  it('allows nothing at all on a page that armed nothing', () => {
    expect(consumeExpectedApiFailure(appPage(), line(400))).toBe(false);
  });

  it('arms nothing on the reference, which has no API to fail', () => {
    const page = referencePage();
    expectApiStatus(page, 400);
    expect(consumeExpectedApiFailure(page, line(400))).toBe(false);
    expect(() => assertExpectedApiFailuresObserved(page), 'and so has nothing to be unobserved').not.toThrow();
  });

  it('fails when an armed allowance was never used — a dead exemption hides a broken state', () => {
    const page = appPage();
    expectApiStatus(page, 400);
    expect(() => assertExpectedApiFailuresObserved(page)).toThrow(/400/);
    expect(() => assertExpectedApiFailuresObserved(page)).toThrow(/never/i);
  });

  it('passes once every armed allowance has been consumed, and re-arms cleanly', () => {
    const page = appPage();
    expectApiStatus(page, 400);
    consumeExpectedApiFailure(page, line(400));
    expect(() => assertExpectedApiFailuresObserved(page)).not.toThrow();
    expectApiStatus(page, 400);
    expect(() => assertExpectedApiFailuresObserved(page)).toThrow(/400/);
  });

  it('isExpectedApiFailure is the sign-in filter generalised, and 401 still goes through it', () => {
    expect(isExpectedApiFailure(400, line(400))).toBe(true);
    expect(isExpectedApiFailure(400, 'Failed to load resource: the server responded with a status of 400 ()')).toBe(true);
    expect(isExpectedApiFailure(400, line(4001)), 'word-bounded').toBe(false);
    expect(isExpectedSignInFailure401('Failed to load resource: the server responded with a status of 401 ()')).toBe(true);
  });
});

describe('the seeded application data the oracle types back (A-S5 ruling 2)', () => {
  it('DECLINED_FIELDS is the seed script\'s row, which is what the re-apply form is pre-filled with', () => {
    expect(DECLINED_FIELDS).toEqual({
      name: 'Declined Applicant, DVM',
      school_year: 'Texas A&M, 2012',
      license_state: 'TX',
      employer: 'Hill Country Veterinary Clinic',
      intent: 'Exploring ownership within two years.',
      affirm: true
    });
  });

  it('NEEDS_REVIEW_INFO_REQUEST is the reviewer\'s question the seed writes', () => {
    expect(NEEDS_REVIEW_INFO_REQUEST).toBe('Which practice do you work at now, and in what role?');
  });
});
