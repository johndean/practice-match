// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Component, ECON_K, MARKETS, P, VETS } from './logic.js';
import { STEP_FIELDS, makeListingsAdapter } from './listings/seller';

let c: any;
beforeEach(() => { c = new Component({}); });

describe('logic.js — characterisation of the approved prototype (file untouched)', () => {
  it('starts signed out on the sign-in gate with the design defaults', () => {
    expect(c.state).toMatchObject({ screen: 'gate', gate: 'signin', auth: false, viewport: 'desktop', mobileTab: 'list', adminTab: 'users', detailId: 'p1', sellerView: 'dash' });
    expect(c.state, 'A6.3: no demo credentials survive the launch removal').toMatchObject({ email: '', pw: '' });
  });

  it('go() refuses navigation while signed out and returns to the sign-in gate', () => {
    c.setState({ screen: 'browse', userMenu: true });
    c.go('requests')();
    expect(c.state).toMatchObject({ screen: 'gate', gate: 'signin', userMenu: false, auth: false });
  });

  // The launch-removal list, executed (amendments A6.1–A6.6). Every affordance below used to be
  // the harness's way into a state and the prototype's way of faking a member; `reach()` and the
  // seeded accounts replaced all of them in commit 1, and the design lost them in commit 3.
  it('the prototype jump bar no longer exists — no jumpTo, no jumps, no viewport toggle (A6.1/A6.4/A6.6)', () => {
    expect(c.jumpTo, 'the jump bar\'s handler').toBeUndefined();
    const v = c.renderVals();
    expect(v.jumps, 'the array the bar rendered from').toBeUndefined();
    expect(v.showPrototypeBar, 'the flag its sc-if read').toBeUndefined();
    expect(v.viewportLabel, 'the "Mobile view" / "Desktop view" label (A6.6)').toBeUndefined();
    expect(v.toggleViewport, 'the handler that button called (A6.6)').toBeUndefined();
    // `isDesktop` reads the same `s.viewport` and STAYS: the phone frame is still reachable
    // through the `startViewport` prop until a responsive design exists (D-I8-7).
    expect(v.isDesktop).toBe(true);
  });

  it('the "Prototype — access states" shortcuts no longer exist (A6.2/A6.5)', () => {
    expect(c.renderVals().gateStates).toBeUndefined();
  });

  it('the demo credentials and the pre-filled application are empty (A6.3)', () => {
    expect(c.state).toMatchObject({ email: '', pw: '' });
    expect(c.state.apply).toEqual({ name: '', vin: '', grad: '', state: '', employer: '', intent: '', affirm: false, error: '' });
    // …and sign-out does not put a masked password back.
    c.setState({ auth: true, screen: 'browse' });
    c.renderVals().signOut();
    expect(c.state.pw).toBe('');
  });

  it('go() navigates once signed in', () => {
    c.setState({ auth: true, screen: 'browse' });
    c.go('seller')();
    expect(c.state.screen).toBe('seller');
  });

  it('renderVals exposes the four nav items with the design labels, plus the signed-in flags', () => {
    const v = c.renderVals();
    expect(v.nav.map((n: any) => n.label)).toEqual(['Browse Practices', 'My Requests', 'List a Practice', 'VIN Foundation Admin']);
    expect(v.signedIn).toBe(false);
    expect(v.signedOut).toBe(true);
  });

  it('adminVals renders the four tabs and switches the row set with adminTab', () => {
    expect(c.adminVals().tabs.map((t: any) => t.label)).toEqual(['Users', 'Listings', 'Requests', 'Data Sources']);
    c.setState({ adminTab: 'data' });
    const a = c.adminVals();
    expect(a.columns).toEqual(['Dataset', 'Source and license', 'Status', 'Action']);
    expect(a.rows).toHaveLength(5);
    expect(a.footnote).toContain('No dataset reaches production until its license is recorded here');
  });

  it('setListingStatus changes exactly the targeted seller listing', () => {
    c.setListingStatus('s1', 'paused');
    expect(c.state.sellerListings.map((l: any) => [l.id, l.status])).toEqual([['s1', 'paused'], ['s2', 'in_review'], ['s3', 'draft'], ['s4', 'paused']]);
  });

  it('filters: activeFilterCount counts non-default filters and filtered() never grows', () => {
    const all = c.filtered().length;
    expect(c.activeFilterCount()).toBe(0);
    c.setState({ f: { ...c.state.f, doctors: '1' } });
    expect(c.activeFilterCount()).toBe(1);
    expect(c.filtered().length).toBeLessThanOrEqual(all);
  });

  it('money() formats the way the seller cards show it', () => {
    expect(c.money(1450000)).toBe('$1.45M');
    expect(c.money(860000)).toBe('$860K');
  });

  it('mobileVals exposes the market-data sheet and no peek card (C13)', () => {
    const mob = c.renderVals().mob;
    expect(typeof mob.openSheet).toBe('function');
    expect(typeof mob.closeSheet).toBe('function');
    expect(mob.sheetOpen).toBe(false);
    expect(typeof mob.layerLabel).toBe('string');
    expect(Array.isArray(mob.basemaps)).toBe(true);
    expect(mob).not.toHaveProperty('hasPeek');
    expect(mob).not.toHaveProperty('peek');
  });

  // A2 (spec D17, John: "resolve this"). Root cause: the mobile results card's `open` set
  // `browseSel`, which C13 left nothing to read (the peek card it once opened is gone), so
  // the tap was a no-op. `open` now navigates to the detail — the same navigation C13's
  // second pin tap performs (`mobileVals.selectMarker`, above).
  it('the mobile results card\'s open() navigates to the detail (A2 — was a dead browseSel/activeId no-op)', () => {
    const first = c.renderVals().results[0];
    expect(first.open).toBeInstanceOf(Function);
    first.open();
    expect(c.state).toMatchObject({ screen: 'detail', detailId: 'p1' });
    expect(c.state).not.toHaveProperty('browseSel');
  });

  // A2.3 (zero-gaps review, spec D8/D12: a dead mapping is dead code). `hasBrowseSel`,
  // `closeBrowseSel` and `bsel` all read or wrote the same orphaned `browseSel` key — C13
  // removed the peek card that was their only reader in the template, and nothing else
  // referenced any of the three (verified: zero matches for `hasBrowseSel`/`bsel`/
  // `closeBrowseSel` outside the design's own script). Deleted outright, not merely renamed.
  it('renderVals no longer exposes the orphaned browseSel helpers (A2.3)', () => {
    const v = c.renderVals();
    expect(v).not.toHaveProperty('hasBrowseSel');
    expect(v).not.toHaveProperty('closeBrowseSel');
    expect(v).not.toHaveProperty('bsel');
    // isBrowse is a DIFFERENT, still-vestigial-but-untouched key (app-generated.test.ts pins
    // it separately) — this asserts A2.3 did not reach past its own three names.
    expect(v).toHaveProperty('isBrowse', false);
  });

  // A28.2-A28.4 (John, 2026-09-11, ruling D-C44), the same dead-code rule again — this time on
  // orphans the DESIGN itself left behind rather than ones an amendment created. `layerHelp`,
  // `fillRows` and `overlayRows` were V3's "GROUP 1 / GROUP 2" rows for the panel V3 replaced
  // with `md.layerChoices`, retained by the design's own comment as legacy and read by no
  // template on either target; `drive5`/`drive10` were layer-default flags only those rows read.
  // Deleting them removes the last "drive time" strings in the product (D-C39's real target).
  it('marketVals no longer exposes the legacy panel\'s orphan rows (A28.2-A28.4)', () => {
    const md = c.marketVals(c.filtered());
    expect(md).not.toHaveProperty('layerHelp');
    expect(md).not.toHaveProperty('fillRows');
    expect(md).not.toHaveProperty('overlayRows');
    // …and nothing the family did not name went with them: the compact control V3 made
    // canonical, and the legend the design still draws, are untouched.
    expect(md).toHaveProperty('layerChoices');
    expect(md).toHaveProperty('legend');
    // A28.4: the two drive-band flags leave the defaults and the four LIVE members stay, with
    // their values. Read through `symbols` — `SYMBOL_KEYS.filter((k) => layers[k] && ...)` — which
    // is what actually consumes them, so all three of `pets: false`, `households: false` and
    // `competition: true` are pinned by one literal. (`practices`, the fourth, is not a symbol
    // key; the design reads it only from the deleted row, and it stays in the defaults.)
    expect(md.symbols, 'A28.4 changed a layer default it was not given').toEqual(['competition']);
  });

  // A2.5 (zero-gaps review, same dead-code rule as A2.3: a dead handler is dead code). The
  // top-level `selectMarker` A2.4 trimmed is never wired to any template prop — App.vue's
  // only `on-select` binding is `v.mob?.selectMarker`, the mobileVals one (`logic.js:972`) —
  // so it is deleted outright. This supersedes A2.4's characterisation of its trimmed body:
  // that test is retired here, in the same commit that removes the property it pinned.
  it('the top-level selectMarker is gone; only the wired mobileVals one remains (A2.5)', () => {
    const v = c.renderVals();
    expect(v).not.toHaveProperty('selectMarker');
    expect(typeof v.mob.selectMarker).toBe('function');
  });

  // C13 (unchanged by A2.5 — pinned here at the unit level for the first time, alongside the
  // sibling handler's deletion, so the suite proves the deletion did not disturb it): tapping
  // an already-selected pin a second time opens the detail; selecting a different id only
  // updates the selection. `renderVals()` is re-derived between taps because `mobileVals`
  // closes over `this.state` at call time, exactly as the real Vue render does.
  it('mobileVals.selectMarker opens the detail on a second tap of the same pin (C13)', () => {
    c.renderVals().mob.selectMarker('p2');
    expect(c.state).toMatchObject({ activeId: 'p2' });
    expect(c.state.screen).not.toBe('detail');

    c.renderVals().mob.selectMarker('p2');
    expect(c.state).toMatchObject({ screen: 'detail', detailId: 'p2' });
  });

  // ---------------------------------------------------------------------------------------
  // A5.4 (amendment A-I8 / A-I8.1) — the bootstrap reads the account the app loaded from
  // `/api/me` before mount, and the `startGate` prototype prop.
  //
  // `props.me` is the ONE hook the real session reaches the approved prototype through: the
  // app passes `useMe().me.value` (loaded by `main.ts` before `bootstrap()`), the reference
  // and the Claude Design preview pass nothing, and the fixture path is unchanged for them.
  // The mapping is the spec's account lifecycle: `active` is a member, `pending` and
  // `needs_review` are waiting on staff, `declined` was refused, `verified` has an address
  // but has not applied yet (D-I8-5 rider). `unverified` is deliberately NOT mapped — it has
  // nowhere to go until I8c's "check your email" screen exists, so it falls through to the
  // sign-in gate rather than to an invented state.
  //
  // A deep link pending in `useStateRouteSync` is applied by that watcher the instant `auth`
  // flips, exactly as the fixture sign-in did (router/useStateRouteSync.test.ts pins it).
  // ---------------------------------------------------------------------------------------
  const ACTIVE = { id: 'a1', email: 'design@practice-match.test', name: 'Dr. Rachel Mendes', role: 'VIN Foundation admin · StartUp Club', initials: 'RM', state: 'active', roles: ['admin'], affiliation_label: 'StartUp Club' };

  it('componentDidMount with an active account signs in and lands on Browse, taking the header strings from /api/me (A5.4)', () => {
    const c2: any = new Component({ me: ACTIVE });
    c2.componentDidMount();
    expect(c2.state).toMatchObject({ auth: true, screen: 'browse', email: 'design@practice-match.test' });
    expect(c2.state.me).toEqual({ name: 'Dr. Rachel Mendes', role: 'VIN Foundation admin · StartUp Club', initials: 'RM' });
    // Only the three the header and account menu render — never the whole payload, which
    // carries `roles` and `state` the design has no place for.
    expect(Object.keys(c2.state.me).sort()).toEqual(['initials', 'name', 'role']);
  });

  it('componentDidMount maps pending and needs_review to the "under review" gate (A5.4)', () => {
    for (const state of ['pending', 'needs_review']) {
      const c2: any = new Component({ me: { ...ACTIVE, state } });
      c2.componentDidMount();
      expect(c2.state, state).toMatchObject({ screen: 'gate', gate: 'pending', auth: false });
      expect(c2.renderVals().status.title, state).toBe('Your request is under review');
    }
  });

  it('componentDidMount maps declined to the "not granted" gate and verified to the application gate (A5.4)', () => {
    const declined: any = new Component({ me: { ...ACTIVE, state: 'declined' } });
    declined.componentDidMount();
    expect(declined.state).toMatchObject({ screen: 'gate', gate: 'rejected', auth: false });
    expect(declined.renderVals().status.title).toBe('Access was not granted');

    const verified: any = new Component({ me: { ...ACTIVE, state: 'verified' } });
    verified.componentDidMount();
    expect(verified.state).toMatchObject({ screen: 'gate', gate: 'apply', auth: false });
    expect(verified.renderVals().gateApply).toBe(true);
  });

  // `unverified` used to be here too: A5.4 left it unmapped because I8c's "check your email"
  // card did not exist, and "absent beats faked" forbade inventing one. Task S4 built the card,
  // A8.3b maps the state, and the landing is pinned by its own case in the A-S4 block below —
  // so this case keeps the half that is still true.
  it('componentDidMount leaves a visitor with no account at all on the sign-in gate (A5.4)', () => {
    for (const props of [{ me: null }, {}]) {
      const c2: any = new Component(props);
      c2.componentDidMount();
      expect(c2.state, JSON.stringify(props)).toMatchObject({ screen: 'gate', gate: 'signin', auth: false });
    }
  });

  it('componentDidMount honours the startGate prototype prop, which is how the reference reaches a gate state (A5.4/A5.6)', () => {
    for (const gate of ['signin', 'apply', 'pending', 'rejected']) {
      const c2: any = new Component({ startGate: gate });
      c2.componentDidMount();
      expect(c2.state, gate).toMatchObject({ screen: 'gate', gate, auth: false });
    }
    // The empty default is a no-op, so a reference request that names no gate renders the
    // design's own default rather than being forced onto one.
    const none: any = new Component({ startGate: '' });
    none.componentDidMount();
    expect(none.state).toMatchObject({ screen: 'gate', gate: 'signin' });
  });

  it('an account wins over startGate when both are given, and startViewport is applied either way (A5.4)', () => {
    const c2: any = new Component({ startGate: 'pending', startViewport: 'mobile', me: ACTIVE });
    c2.componentDidMount();
    expect(c2.state).toMatchObject({ auth: true, screen: 'browse', viewport: 'mobile' });
  });

  // Review round 1, I1. A5.4's `active` branch used to set `screen: "browse"` unconditionally,
  // which silently overrode `startScreen` — so the REFERENCE, whose only screen driver is that
  // prop, could not be signed in and put on a named screen at the same time. (The harness worked
  // around it by clicking the design's header nav, which was an undeclared deviation from the
  // ruled A-I8.2 and is now deleted.) A set `startScreen` wins; the app never passes it, so
  // nothing about the app changes — it still lands on Browse and lets the router's pending deep
  // link move it.
  it('a set startScreen wins over the account\'s landing screen, so the reference can be signed in AND placed (A5.4, I1)', () => {
    for (const screen of ['browse', 'detail', 'requests', 'seller', 'admin']) {
      const c2: any = new Component({ startScreen: screen, me: ACTIVE });
      c2.componentDidMount();
      expect(c2.state, screen).toMatchObject({ auth: true, screen, email: ACTIVE.email });
      expect(c2.state.me, screen).toEqual({ name: ACTIVE.name, role: ACTIVE.role, initials: ACTIVE.initials });
    }
  });

  it('with no startScreen — the app\'s case — an active account still lands on Browse (A5.4, I1)', () => {
    for (const props of [{ me: ACTIVE }, { me: ACTIVE, startScreen: '' }, { me: ACTIVE, startScreen: 'gate' }]) {
      const c2: any = new Component(props);
      c2.componentDidMount();
      expect(c2.state, JSON.stringify(props)).toMatchObject({ auth: true, screen: 'browse' });
    }
  });

  it('startScreen still signs the prototype in without any account, exactly as the design shipped it', () => {
    const c2: any = new Component({ startScreen: 'admin' });
    c2.componentDidMount();
    expect(c2.state).toMatchObject({ screen: 'admin', auth: true });
  });

  // ---------------------------------------------------------------------------------------
  // A5.1 / A5.3 (amendment A-I8) — sign-in and sign-out through the `auth` adapter.
  //
  // `this.props.auth` is the prototype's second hook (the first is `props.me`): the app passes
  // the real `/api/auth/*` client, the reference and the Claude Design preview pass nothing and
  // keep the design's fixture path byte for byte. The adapter here is a plain fake OBJECT, never
  // a module mock — `logic.js` is a verbatim port and the point is to exercise IT, through the
  // same seam the app uses.
  //
  // `signIn` returns the adapter's promise so a caller (and this suite) can await the settled
  // state; the design's own button ignores the return value, exactly as it ignored the fixture
  // path's `undefined`.
  // ---------------------------------------------------------------------------------------
  const ME = { email: 'buyer@practice-match.test', name: 'Dr. Rachel Mendes', role: 'Approved buyer · StartUp Club', initials: 'RM', state: 'active', roles: ['buyer'] };

  /** Records what the prototype asked for, and answers however the case wants. */
  function fakeAuth(answers: { signIn?: () => Promise<unknown>; signOut?: () => Promise<unknown> } = {}) {
    const calls: string[] = [];
    return {
      calls,
      signIn: (email: string, password: string) => { calls.push(`signIn(${email},${password})`); return (answers.signIn ?? (() => Promise.resolve(ME)))(); },
      signOut: () => { calls.push('signOut()'); return (answers.signOut ?? (() => Promise.resolve({ status: 'signed_out' })))(); }
    };
  }

  it('signIn() calls the adapter with the typed credential and takes the header strings from its answer (A5.1)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.setState({ email: 'buyer@practice-match.test', pw: 'a-password' });

    await c2.renderVals().signIn();

    expect(auth.calls).toEqual(['signIn(buyer@practice-match.test,a-password)']);
    expect(c2.state).toMatchObject({ auth: true, screen: 'browse', formError: '', email: 'buyer@practice-match.test' });
    expect(c2.state.me).toEqual({ name: 'Dr. Rachel Mendes', role: 'Approved buyer · StartUp Club', initials: 'RM' });
  });

  it('signIn() shows the server\'s own refusal message and stays on the gate, signed out (A5.1)', async () => {
    const auth = fakeAuth({ signIn: () => Promise.reject(new Error('Too many attempts. Try again later.')) });
    const c2: any = new Component({ auth });
    c2.setState({ email: 'buyer@practice-match.test', pw: 'wrong' });

    await c2.renderVals().signIn();

    // The API's wording, not ours: `INVALID_CREDENTIALS` and `RATE_LIMITED` want different copy
    // and the message is the server's prose to render (src/auth/api.ts).
    expect(c2.state).toMatchObject({ formError: 'Too many attempts. Try again later.', auth: false, screen: 'gate' });
  });

  it('signIn() falls back to its own wording when the refusal carries none (A5.1)', async () => {
    for (const rejection of [new Error(''), undefined]) {
      const c2: any = new Component({ auth: fakeAuth({ signIn: () => Promise.reject(rejection) }) });
      c2.setState({ email: 'e', pw: 'p' });
      await c2.renderVals().signIn();
      expect(c2.state.formError).toBe('Sign-in failed.');
    }
  });

  it('signIn() validates the empty form before it spends a request (A5.1 / A7.2)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.setState({ email: '', pw: '' });

    await c2.renderVals().signIn();

    expect(auth.calls, 'an empty form must not reach the API — it is a rate-limited endpoint').toEqual([]);
    expect(c2.state.auth).toBe(false);
    expect(c2.state.formError, 'A7.2: the API authenticates an email address').toBe('Enter both your email and password.');
  });

  it('signOut() ends the session through the adapter and then resets the prototype (A5.3)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth, me: { ...ME } });
    c2.componentDidMount();
    expect(c2.state.auth).toBe(true);

    await c2.renderVals().signOut();

    expect(auth.calls).toEqual(['signOut()']);
    expect(c2.state).toMatchObject({ auth: false, screen: 'gate', gate: 'signin', userMenu: false, interest: 'closed' });
  });

  it('signOut() resets even when the API refuses, so a failure cannot strand a member signed in (A5.3)', async () => {
    const auth = fakeAuth({ signOut: () => Promise.reject(new Error('network')) });
    const c2: any = new Component({ auth, me: { ...ME } });
    c2.componentDidMount();

    await c2.renderVals().signOut();

    expect(c2.state).toMatchObject({ auth: false, screen: 'gate' });
  });

  it('without an auth prop the design\'s own fixture path runs, unchanged (A5.1 / A5.3)', async () => {
    const c2: any = new Component({});
    c2.setState({ email: 'anything', pw: 'anything' });
    c2.renderVals().signIn();
    expect(c2.state).toMatchObject({ screen: 'browse', formError: '', auth: true });

    await c2.renderVals().signOut();
    expect(c2.state).toMatchObject({ auth: false, screen: 'gate', gate: 'signin' });
  });

  // A4 (spec D21, John: "if user clicks + Compare that action closes the 'What this means'
  // card, and when X Compare is clicked it closes the compare and the card appears again").
  // insightOpen already requires a value layer, an undismissed member and a wide-enough map
  // column (mapW >= 810, hence vw: 1440 here); A4 adds "and Compare is not open". Before A4,
  // toggleCompare had no effect on insightOpen at all.
  it('insightOpen hides while Compare is open and returns when Compare closes; dismissInsight wins regardless (A4, spec D21)', () => {
    c.setState({ vw: 1440 });
    expect(c.renderVals().md.insightOpen).toBe(true);

    c.renderVals().md.toggleCompare();
    expect(c.state.mdCompareOpen).toBe(true);
    expect(c.renderVals().md.insightOpen).toBe(false);

    c.renderVals().md.toggleCompare();
    expect(c.state.mdCompareOpen).toBe(false);
    expect(c.renderVals().md.insightOpen).toBe(true);

    c.renderVals().md.dismissInsight();
    expect(c.renderVals().md.insightOpen).toBe(false);
    c.renderVals().md.toggleCompare();
    expect(c.renderVals().md.insightOpen).toBe(false);
  });

  // A10 (John, 2026-09-08): the sign-in card's second gate point gets new copy. A literal
  // script edit, like A3 — `gatePoints[1]` in renderVals()'s return. Points 1 and 3 are
  // untouched. A10's text was superseded the same day by A10.2, which this now asserts.
  it("the sign-in card's second gate point reads John's revised wording (A10 → A10.2, 2026-09-08)", () => {
    const points = c.renderVals().gatePoints;
    expect(points[0].title).toBe('Approved members only');
    expect(points[1].title).toBe('Sellers control what buyers can see');
    expect(points[1].body).toBe('The property is accurately mapped, but financial information, and floor plans are only shared with the seller’s approval.');
    expect(points[2].title).toBe('One clear next step');
  });
});

// ===========================================================================================
// A-S4 (Task S4) — the account screens, composed from the V3 gate card.
//
// Everything below drives the REAL `Component` through the same two hooks the app uses:
// `props.auth` (the adapter Task I8a introduced, here a plain fake OBJECT with `vi.fn()`
// methods — never a module mock) and `props.me`. Without an adapter every one of these paths
// falls back to the prototype's own fixture transition, which is what keeps the REFERENCE — a
// bare design file with no API — rendering each new state for the pixel oracle.
//
// The copy asserted here is the spec's §3 table, letter for letter
// (`docs/superpowers/specs/2026-09-07-account-screens-design.md`).
// ===========================================================================================
describe('logic.js — the account screens (A7.3/A7.4, A8.1–A8.8)', () => {
  const ACCOUNT = { id: 'a1', email: 'buyer@practice-match.test', name: 'Dr. Rachel Mendes', role: 'Approved buyer · StartUp Club', initials: 'RM', state: 'active', roles: ['buyer'] };

  /** The adapter, as `logic.js` sees it: every account call, each answering how the case needs. */
  function fakeAuth(over: Record<string, unknown> = {}) {
    return Object.assign({
      signIn: vi.fn(() => Promise.resolve(ACCOUNT)),
      signOut: vi.fn(() => Promise.resolve({ status: 'signed_out' })),
      signUp: vi.fn(() => Promise.resolve({ status: 'check_email' })),
      verify: vi.fn(() => Promise.resolve({ status: 'verified' })),
      forgot: vi.fn(() => Promise.resolve({ status: 'check_email' })),
      reset: vi.fn(() => Promise.resolve({ status: 'reset' })),
      acceptInvite: vi.fn(() => Promise.resolve({ status: 'invited' })),
      apply: vi.fn(() => Promise.resolve({ id: 'app-1', status: 'pending' })),
      answer: vi.fn(() => Promise.resolve({ status: 'pending' })),
      applicationsMe: vi.fn(() => Promise.resolve({ current: null, history: [] })),
      resendVerification: vi.fn(() => Promise.resolve({ status: 'check_email' }))
    }, over) as any;
  }
  /** What `src/auth/api.ts` throws: the server's own `code` and its own prose. */
  const authError = (code: string, message: string) => Object.assign(new Error(message), { code });
  const typed = (v: any) => ({ target: { value: v } });

  // -----------------------------------------------------------------------------------------
  // A8.1 — the notice slot, the sign-out-first rule, and where "Request access" leads
  // -----------------------------------------------------------------------------------------
  it('the sign-in card\'s message box shows a notice as well as a refusal, through the same slot (A8.1)', () => {
    const c2: any = new Component({});
    expect(c2.renderVals().form).toMatchObject({ error: false, errorText: '' });
    c2.setState({ formNotice: 'Password updated. Sign in with your new password.' });
    expect(c2.renderVals().form).toMatchObject({ error: true, errorText: 'Password updated. Sign in with your new password.' });
    c2.setState({ formError: 'Email or password is incorrect.' });
    expect(c2.renderVals().form.errorText, 'a refusal wins over a standing notice').toBe('Email or password is incorrect.');
  });

  it('goApply opens sign-up for an anonymous visitor on the app, and the application form for an account (A8.1)', () => {
    const anon: any = new Component({ auth: fakeAuth() });
    anon.renderVals().goApply();
    expect(anon.state.gate).toBe('signup');

    const member: any = new Component({ auth: fakeAuth() });
    member.setState({ auth: true });
    member.renderVals().goApply();
    expect(member.state.gate).toBe('apply');

    const reference: any = new Component({});
    reference.renderVals().goApply();
    expect(reference.state.gate, 'the reference has no adapter and keeps the design\'s own path').toBe('apply');
  });

  it('goForgot and goSignup open their cards and clear any standing message (A8.1)', () => {
    const c2: any = new Component({});
    c2.setState({ formError: 'nope', formNotice: 'sent' });
    c2.renderVals().goForgot();
    expect(c2.state).toMatchObject({ gate: 'forgot', formError: '', formNotice: '' });
    c2.setState({ formError: 'nope', formNotice: 'sent' });
    c2.renderVals().goSignup();
    expect(c2.state).toMatchObject({ gate: 'signup', formError: '', formNotice: '' });
  });

  it('the status cards\' "Sign in" ends the session first, so it never shows a signed-in header behind the card (A8.1, spec §4.3)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.setState({ auth: true, gate: 'unavailable', screen: 'gate', formNotice: 'stale' });
    await c2.renderVals().goSignin();
    expect(auth.signOut).toHaveBeenCalledTimes(1);
    expect(c2.state).toMatchObject({ gate: 'signin', screen: 'gate', formNotice: '' });
  });

  // Fix round 1, Important 1. A5.4 never sets `auth` for an applicant — `pending`, `needs_review`,
  // `declined` and `unverified` all land on a gate card with `auth: false` — so a `s.auth &&` guard
  // meant the status cards' "Sign in" signed nobody out except on the `unavailable` card, and those
  // four states could not end their session at all. A LOADED ACCOUNT is the evidence a session
  // exists, whatever the prototype's own flag says.
  it('the status cards\' "Sign in" signs an APPLICANT out too, who never had the auth flag set (A8.1)', async () => {
    for (const state of ['pending', 'needs_review', 'declined', 'unverified']) {
      const auth = fakeAuth();
      const c2: any = new Component({ auth, me: { ...ACCOUNT, state } });
      c2.componentDidMount();
      expect(c2.state.auth, state).toBe(false);

      await c2.renderVals().goSignin();

      expect(auth.signOut, `${state}: an applicant must be able to end their session`).toHaveBeenCalledTimes(1);
      expect(c2.state, state).toMatchObject({ gate: 'signin', screen: 'gate' });
    }
  });

  it('the answer card\'s "Sign out" link signs a needs_review applicant out for the same reason (A8.5)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth, me: { ...ACCOUNT, state: 'needs_review' } });
    c2.componentDidMount();
    expect(c2.state.auth).toBe(false);

    await c2.renderVals().goSignOut();

    expect(auth.signOut).toHaveBeenCalledTimes(1);
    expect(c2.state).toMatchObject({ auth: false, gate: 'signin', screen: 'gate' });
  });

  // Fix round 1 re-review, ruled deliberate: the widened guard also means the forgot / reset /
  // invite cards' "Back to sign in" ends an ACTIVE member's session, where the narrow `s.auth &&`
  // guard would only have done so from a status card. That is coherent and is kept — arriving at
  // the sign-in card means signing in as SOMEBODY, so whoever is there now is on their way out —
  // and it is the same rule on every card rather than a rule that depends on which one you came
  // from. Pinned here so it can never become an accident.
  it('"Back to sign in" ends an active member\'s session too, from a reset link as much as from a status card (A8.1)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth, me: { ...ACCOUNT, state: 'active' } });
    c2.setState({ screen: 'gate', gate: 'reset', gateToken: 'raw-reset-token' });
    c2.componentDidMount();
    expect(c2.state, 'A8.3a keeps the member on the reset page').toMatchObject({ screen: 'gate', gate: 'reset' });

    await c2.renderVals().goSignin();

    expect(auth.signOut).toHaveBeenCalledTimes(1);
    expect(c2.state).toMatchObject({ gate: 'signin', screen: 'gate', formNotice: '' });
  });

  it('goSignin still shows the card when the sign-out call fails, and spends no request when nobody is signed in (A8.1)', async () => {
    const failing = fakeAuth({ signOut: vi.fn(() => Promise.reject(new Error('network'))) });
    const c2: any = new Component({ auth: failing });
    c2.setState({ auth: true, gate: 'rejected' });
    await c2.renderVals().goSignin();
    expect(c2.state).toMatchObject({ gate: 'signin', screen: 'gate' });

    const anon = fakeAuth();
    const c3: any = new Component({ auth: anon });
    c3.setState({ gate: 'forgot' });
    c3.renderVals().goSignin({ preventDefault: () => undefined });
    expect(anon.signOut, 'a signed-out visitor must not spend a sign-out call').not.toHaveBeenCalled();
    expect(c3.state.gate).toBe('signin');
  });

  it('goSignOut on the answer card ends the session and returns to the sign-in card (A8.5, spec §4.3)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.setState({ auth: true, gate: 'answer' });
    await c2.renderVals().goSignOut({ preventDefault: () => undefined });
    expect(auth.signOut).toHaveBeenCalledTimes(1);
    expect(c2.state).toMatchObject({ auth: false, gate: 'signin', screen: 'gate' });

    const reference: any = new Component({});
    reference.setState({ auth: true, gate: 'answer' });
    reference.renderVals().goSignOut();
    expect(reference.state).toMatchObject({ auth: false, gate: 'signin' });
  });

  // -----------------------------------------------------------------------------------------
  // A8.2 — the new state fields
  // -----------------------------------------------------------------------------------------
  it('the new gate state starts empty, alongside the design\'s own fields (A8.2)', () => {
    const c2: any = new Component({});
    expect(c2.state).toMatchObject({ formNotice: '', gateToken: '' });
    expect(c2.state.signup).toEqual({ email: '', pw: '', error: '' });
    expect(c2.state.forgot).toEqual({ email: '', error: '' });
    expect(c2.state.reset).toEqual({ pw: '', pw2: '', error: '' });
    expect(c2.state.invite).toEqual({ pw: '', pw2: '', error: '' });
    expect(c2.state.answer).toEqual({ text: '', error: '', applicationId: '', note: '' });
  });

  // -----------------------------------------------------------------------------------------
  // A8.5 — sign-up
  // -----------------------------------------------------------------------------------------
  it('submitSignup posts the credentials and lands on "check your email" (A8.5, spec §3 row 1)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.renderVals().setSignupEmail(typed('new@practice-match.test'));
    c2.renderVals().setSignupPw(typed('a-long-enough-password'));
    expect(c2.renderVals().signupForm).toMatchObject({ email: 'new@practice-match.test', pw: 'a-long-enough-password', error: false });

    await c2.renderVals().submitSignup();

    expect(auth.signUp).toHaveBeenCalledWith('new@practice-match.test', 'a-long-enough-password');
    expect(c2.state).toMatchObject({ gate: 'check-email', email: 'new@practice-match.test' });
  });

  it('submitSignup shows the server\'s own refusal on the card, and its own wording when the refusal carries none (A8.5)', async () => {
    for (const [rejection, shown] of [[authError('PASSWORD_POLICY', 'That password has appeared in a breach.'), 'That password has appeared in a breach.'], [new Error(''), 'Sign-up failed.'], [undefined, 'Sign-up failed.']] as const) {
      const c2: any = new Component({ auth: fakeAuth({ signUp: vi.fn(() => Promise.reject(rejection)) }) });
      c2.renderVals().setSignupEmail(typed('new@practice-match.test'));
      c2.renderVals().setSignupPw(typed('short'));
      c2.renderVals().goSignup();
      await c2.renderVals().submitSignup();
      expect(c2.state.gate, 'a refusal keeps the visitor on the form').toBe('signup');
      expect(c2.renderVals().gateSignup).toBe(true);
      expect(c2.renderVals().signupForm).toMatchObject({ error: true, errorText: shown });
    }
  });

  it('submitSignup refuses an empty form before it spends a rate-limited request (A8.5)', () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.renderVals().submitSignup();
    expect(auth.signUp).not.toHaveBeenCalled();
    expect(c2.renderVals().signupForm.errorText).toBe('Enter both your email and password.');
  });

  it('without an adapter submitSignup takes the prototype\'s fixture transition (A8.5)', () => {
    const c2: any = new Component({});
    c2.renderVals().setSignupEmail(typed('new@practice-match.test'));
    c2.renderVals().setSignupPw(typed('a-long-enough-password'));
    c2.renderVals().submitSignup();
    expect(c2.state.gate).toBe('check-email');
  });

  // -----------------------------------------------------------------------------------------
  // A8.4 — the four status cards
  // -----------------------------------------------------------------------------------------
  it('the check-email card names the address, states the 24-hour life and re-posts the sign-up (A8.4, spec §3 row 2)', () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.setState({ gate: 'check-email', signup: { email: 'new@practice-match.test', pw: 'a-long-enough-password', error: '' } });
    const v = c2.renderVals();
    expect(v.gateStatus).toBe(true);
    expect(v.status.kicker).toBe('Almost there');
    expect(v.status.title).toBe('Check your email');
    expect(v.status.body).toBe('We sent a verification link to new@practice-match.test. It is valid for 24 hours. Open it to confirm your address, then sign in to complete your access request.');
    expect(v.status.meta).toEqual([{ k: 'Sent to', v: 'new@practice-match.test' }, { k: 'Link valid for', v: '24 hours' }]);
    expect(v.status.primary.label).toBe('Send it again');
    v.status.primary.go();
    expect(auth.signUp).toHaveBeenCalledWith('new@practice-match.test', 'a-long-enough-password');
  });

  // Fix round 1: this used to re-post the SIGN-UP with an empty password for a visitor who reached
  // the card by signing in, which the API's uniform 202 answered without issuing anything — the
  // card claimed to have sent a link that never existed. `POST /api/auth/verify/resend` (A-S4.1)
  // is the endpoint that needs no password, and this is the branch that calls it.
  it('"Send it again" for an account that ARRIVED BY SIGNING IN re-sends through the session, with no password (A8.4/A-S4.1)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth, me: { ...ACCOUNT, state: 'unverified', email: 'unverified@practice-match.test' } });
    c2.componentDidMount();
    expect(c2.state).toMatchObject({ gate: 'check-email', email: 'unverified@practice-match.test' });
    const v = c2.renderVals();
    expect(v.status.body).toContain('unverified@practice-match.test');

    await v.status.primary.go();

    expect(auth.resendVerification).toHaveBeenCalledTimes(1);
    expect(auth.signUp, 'there is no password in hand to sign up with').not.toHaveBeenCalled();
  });

  it('"Send it again" re-posts the SIGN-UP when the visitor got here by signing up, since it holds the password (A8.4)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.setState({ gate: 'check-email', signup: { email: 'new@practice-match.test', pw: 'a-long-enough-password', error: '' } });

    await c2.renderVals().status.primary.go();

    expect(auth.signUp).toHaveBeenCalledWith('new@practice-match.test', 'a-long-enough-password');
    expect(auth.resendVerification, 'no session exists yet — the account has never signed in').not.toHaveBeenCalled();
  });

  it('a refused "Send it again" is swallowed on both branches: the card has nowhere to put a message (A8.4)', async () => {
    for (const over of [{ signUp: vi.fn(() => Promise.reject(new Error('nope'))) }, { resendVerification: vi.fn(() => Promise.reject(new Error('nope'))) }]) {
      const auth = fakeAuth(over);
      const c2: any = new Component({ auth, me: 'resendVerification' in over ? { ...ACCOUNT, state: 'unverified' } : null });
      c2.setState({ gate: 'check-email', signup: { email: 'x@y.test', pw: 'resendVerification' in over ? '' : 'a-long-enough-password', error: '' } });
      await c2.renderVals().status.primary.go();
      expect(c2.state.gate).toBe('check-email');
    }
  });

  it('"Send it again" is a no-op on the reference, which has no adapter to post through (A8.4)', () => {
    const c2: any = new Component({});
    c2.setState({ gate: 'check-email' });
    expect(() => c2.renderVals().status.primary.go()).not.toThrow();
    expect(c2.state.gate).toBe('check-email');
  });

  it('the expired-link and not-available cards carry the spec\'s copy and their own next step (A8.4, spec §3 rows 3b/5c/8)', () => {
    const expect_ = (gate: string, kicker: string, title: string, body: string, label: string) => {
      const c2: any = new Component({});
      c2.setState({ gate });
      const v = c2.renderVals();
      expect(v.gateStatus, gate).toBe(true);
      expect(v.status, gate).toMatchObject({ kicker, title, body, meta: [] });
      expect(v.status.primary.label, gate).toBe(label);
      v.status.primary.go();
      return c2.state;
    };
    expect(expect_('verify-expired', 'Link expired', 'This link is no longer valid', 'Verification links work once and expire after 24 hours. Request a new one with the same email and password.', 'Request a new link').gate).toBe('signup');
    expect(expect_('reset-expired', 'Link expired', 'This link is no longer valid', 'Reset links work once and expire after 1 hour.', 'Request a new link').gate).toBe('forgot');
    expect(expect_('unavailable', 'Access', 'This page is not available to your account', 'Your approved access does not include this page. If you think it should, write to the VIN Foundation from the address on your account.', 'Back to Browse Practices').screen).toBe('browse');
  });

  // -----------------------------------------------------------------------------------------
  // A8.5 — forgot
  // -----------------------------------------------------------------------------------------
  it('submitForgot asks for the link and returns to the sign-in card with the notice (A8.5, spec §3 rows 4a/4b)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.renderVals().setForgotEmail(typed('verified@practice-match.test'));
    expect(c2.renderVals().forgotForm).toMatchObject({ email: 'verified@practice-match.test', error: false });

    await c2.renderVals().submitForgot();

    expect(auth.forgot).toHaveBeenCalledWith('verified@practice-match.test');
    expect(c2.state).toMatchObject({ gate: 'signin', formNotice: 'If that address has an account, a reset link is on its way. It is valid for 1 hour.' });
    expect(c2.renderVals().form.errorText).toBe('If that address has an account, a reset link is on its way. It is valid for 1 hour.');
  });

  it('submitForgot refuses an empty address, shows the server\'s refusal, and works with no adapter (A8.5)', async () => {
    const auth = fakeAuth();
    const empty: any = new Component({ auth });
    empty.renderVals().submitForgot();
    expect(auth.forgot).not.toHaveBeenCalled();
    expect(empty.renderVals().forgotForm.errorText).toBe('Enter your email.');

    for (const [rejection, shown] of [[authError('RATE_LIMITED', 'Too many requests. Try again later.'), 'Too many requests. Try again later.'], [new Error(''), 'Request failed.']] as const) {
      const c2: any = new Component({ auth: fakeAuth({ forgot: vi.fn(() => Promise.reject(rejection)) }) });
      c2.renderVals().setForgotEmail(typed('verified@practice-match.test'));
      await c2.renderVals().submitForgot();
      expect(c2.renderVals().forgotForm).toMatchObject({ error: true, errorText: shown });
    }

    const reference: any = new Component({});
    reference.renderVals().setForgotEmail(typed('verified@practice-match.test'));
    reference.renderVals().submitForgot();
    expect(reference.state).toMatchObject({ gate: 'signin', formNotice: 'If that address has an account, a reset link is on its way. It is valid for 1 hour.' });
  });

  // -----------------------------------------------------------------------------------------
  // A8.5 — reset
  // -----------------------------------------------------------------------------------------
  it('submitReset checks the two passwords match before it spends the single-use token (A8.5, spec §3 row 5a)', () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.renderVals().submitReset();
    expect(c2.renderVals().resetForm.errorText).toBe('Enter your new password twice.');

    c2.renderVals().setResetPw(typed('a-long-enough-password'));
    c2.renderVals().setResetPw2(typed('a-different-password'));
    c2.renderVals().submitReset();
    expect(auth.reset, 'a mismatch must not burn the token').not.toHaveBeenCalled();
    expect(c2.renderVals().resetForm).toMatchObject({ error: true, errorText: 'The two passwords do not match.' });
  });

  it('submitReset posts the held token and returns to the sign-in card with the notice (A8.5, spec §3 row 5b)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.setState({ gate: 'reset', gateToken: 'raw-reset-token' });
    c2.renderVals().setResetPw(typed('a-long-enough-password'));
    c2.renderVals().setResetPw2(typed('a-long-enough-password'));

    await c2.renderVals().submitReset();

    expect(auth.reset).toHaveBeenCalledWith('raw-reset-token', 'a-long-enough-password');
    expect(c2.state).toMatchObject({ gate: 'signin', gateToken: '', formNotice: 'Password updated. Sign in with your new password.' });
    // Fix round 1: the token was cleared and the plaintext passwords were not, so they sat in
    // `state` — and in every Vue devtools snapshot of it — for the rest of the session.
    expect(c2.state.reset, 'the new password must not outlive the request that set it').toEqual({ pw: '', pw2: '', error: '' });
  });

  it('a used or expired reset token shows the expired card; any other refusal stays on the form (A8.5, spec §3 row 5c)', async () => {
    const expired: any = new Component({ auth: fakeAuth({ reset: vi.fn(() => Promise.reject(authError('TOKEN_INVALID', 'This link is invalid or has expired.'))) }) });
    expired.setState({ gate: 'reset', gateToken: 'spent-token' });
    expired.renderVals().setResetPw(typed('a-long-enough-password'));
    expired.renderVals().setResetPw2(typed('a-long-enough-password'));
    await expired.renderVals().submitReset();
    expect(expired.state).toMatchObject({ gate: 'reset-expired', gateToken: '' });

    for (const [rejection, shown] of [[authError('PASSWORD_POLICY', 'Pick a longer password.'), 'Pick a longer password.'], [new Error(''), 'Reset failed.']] as const) {
      const c2: any = new Component({ auth: fakeAuth({ reset: vi.fn(() => Promise.reject(rejection)) }) });
      c2.setState({ gate: 'reset', gateToken: 't' });
      c2.renderVals().setResetPw(typed('a-long-enough-password'));
      c2.renderVals().setResetPw2(typed('a-long-enough-password'));
      await c2.renderVals().submitReset();
      expect(c2.state.gate).toBe('reset');
      expect(c2.renderVals().resetForm).toMatchObject({ error: true, errorText: shown });
    }
  });

  it('without an adapter submitReset shows the notice, which is how the reference reaches that state (A8.5)', () => {
    const c2: any = new Component({});
    c2.setState({ gate: 'reset' });
    c2.renderVals().setResetPw(typed('x'));
    c2.renderVals().setResetPw2(typed('x'));
    c2.renderVals().submitReset();
    expect(c2.state).toMatchObject({ gate: 'signin', formNotice: 'Password updated. Sign in with your new password.' });
    expect(c2.state.reset).toEqual({ pw: '', pw2: '', error: '' });
  });

  // -----------------------------------------------------------------------------------------
  // A8.5 — accept invite
  // -----------------------------------------------------------------------------------------
  it('submitInvite sets the staff password and returns to the sign-in card with the notice (A8.5, spec §3 rows 6a/6b)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.setState({ gate: 'invite', gateToken: 'raw-invite-token' });
    c2.renderVals().setInvitePw(typed('a-long-enough-staff-password'));
    c2.renderVals().setInvitePw2(typed('a-long-enough-staff-password'));
    expect(c2.renderVals().inviteForm).toMatchObject({ pw: 'a-long-enough-staff-password', pw2: 'a-long-enough-staff-password', error: false });

    await c2.renderVals().submitInvite();

    expect(auth.acceptInvite).toHaveBeenCalledWith('raw-invite-token', 'a-long-enough-staff-password');
    expect(c2.state).toMatchObject({ gate: 'signin', gateToken: '', formNotice: 'Your password is set. Sign in with your email and the password you just chose.' });
    expect(c2.state.invite, 'the new password must not outlive the request that set it').toEqual({ pw: '', pw2: '', error: '' });
  });

  it('a spent invitation lands on the sign-in card with its own notice; any other refusal stays on the form (A8.5, spec §3 row 6a)', async () => {
    const spent: any = new Component({ auth: fakeAuth({ acceptInvite: vi.fn(() => Promise.reject(authError('TOKEN_INVALID', 'This link is invalid or has expired.'))) }) });
    spent.setState({ gate: 'invite', gateToken: 'spent-token' });
    spent.renderVals().setInvitePw(typed('a-long-enough-staff-password'));
    spent.renderVals().setInvitePw2(typed('a-long-enough-staff-password'));
    await spent.renderVals().submitInvite();
    expect(spent.state).toMatchObject({ gate: 'signin', gateToken: '', formNotice: 'This invitation link is no longer valid. Ask the VIN Foundation for a new one.' });

    for (const [rejection, shown] of [[authError('PASSWORD_POLICY', 'Staff passwords are at least 14 characters.'), 'Staff passwords are at least 14 characters.'], [new Error(''), 'Could not set the password.']] as const) {
      const c2: any = new Component({ auth: fakeAuth({ acceptInvite: vi.fn(() => Promise.reject(rejection)) }) });
      c2.setState({ gate: 'invite', gateToken: 't' });
      c2.renderVals().setInvitePw(typed('a-long-enough-staff-password'));
      c2.renderVals().setInvitePw2(typed('a-long-enough-staff-password'));
      await c2.renderVals().submitInvite();
      expect(c2.state.gate).toBe('invite');
      expect(c2.renderVals().inviteForm).toMatchObject({ error: true, errorText: shown });
    }
  });

  it('submitInvite checks both fields and the match first, and works with no adapter (A8.5)', () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.renderVals().submitInvite();
    expect(c2.renderVals().inviteForm.errorText).toBe('Enter your new password twice.');
    c2.renderVals().setInvitePw(typed('one-password'));
    c2.renderVals().setInvitePw2(typed('another-password'));
    c2.renderVals().submitInvite();
    expect(auth.acceptInvite, 'a mismatch must not burn the invitation').not.toHaveBeenCalled();
    expect(c2.renderVals().inviteForm.errorText).toBe('The two passwords do not match.');

    const reference: any = new Component({});
    reference.setState({ gate: 'invite' });
    reference.renderVals().setInvitePw(typed('x'));
    reference.renderVals().setInvitePw2(typed('x'));
    reference.renderVals().submitInvite();
    expect(reference.state).toMatchObject({ gate: 'signin', formNotice: 'Your password is set. Sign in with your email and the password you just chose.' });
    expect(reference.state.invite).toEqual({ pw: '', pw2: '', error: '' });
  });

  // -----------------------------------------------------------------------------------------
  // A8.5 — the applicant's answer
  // -----------------------------------------------------------------------------------------
  it('submitAnswer sends the reply against the application id and lands on the pending card (A8.5, spec §3 row 7)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.setState({ gate: 'answer', answer: { text: '', error: '', applicationId: 'app-9', note: 'Which practice do you work at now, and in what role?' } });
    expect(c2.renderVals().answerForm.note).toBe('Which practice do you work at now, and in what role?');
    c2.renderVals().setAnswer(typed('I am an associate at Cedar Park Animal Hospital.'));

    await c2.renderVals().submitAnswer();

    expect(auth.answer).toHaveBeenCalledWith('app-9', 'I am an associate at Cedar Park Animal Hospital.');
    expect(c2.state.gate).toBe('pending');
  });

  it('submitAnswer refuses an empty reply, shows the server\'s refusal, and falls back with no adapter (A8.5)', async () => {
    const auth = fakeAuth();
    const empty: any = new Component({ auth });
    empty.setState({ gate: 'answer' });
    empty.renderVals().submitAnswer();
    expect(auth.answer).not.toHaveBeenCalled();
    expect(empty.renderVals().answerForm.errorText).toBe('Write your answer first.');

    for (const [rejection, shown] of [[authError('CONFLICT', 'This application has already been answered.'), 'This application has already been answered.'], [new Error(''), 'Could not send your answer.']] as const) {
      const c2: any = new Component({ auth: fakeAuth({ answer: vi.fn(() => Promise.reject(rejection)) }) });
      c2.setState({ gate: 'answer' });
      c2.renderVals().setAnswer(typed('My answer.'));
      await c2.renderVals().submitAnswer();
      expect(c2.state.gate).toBe('answer');
      expect(c2.renderVals().answerForm).toMatchObject({ error: true, errorText: shown });
    }

    const reference: any = new Component({});
    reference.setState({ gate: 'answer' });
    reference.renderVals().setAnswer(typed('My answer.'));
    reference.renderVals().submitAnswer();
    expect(reference.state.gate).toBe('pending');
  });

  // -----------------------------------------------------------------------------------------
  // A8.6 — the application itself now reaches the API
  // -----------------------------------------------------------------------------------------
  it('submitApply posts the application with the API\'s own field names and lands on the pending card (A8.6)', async () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.setState({ gate: 'apply', apply: { name: 'Jane Doe, DVM', vin: '12345', grad: 'Texas A&M, 2014', state: 'TX', employer: 'Cedar Park Animal Hospital', intent: 'Buying', affirm: true, error: '' } });

    await c2.renderVals().submitApply();

    expect(auth.apply).toHaveBeenCalledWith('buyer', { name: 'Jane Doe, DVM', vin_member_id: '12345', school_year: 'Texas A&M, 2014', license_state: 'TX', employer: 'Cedar Park Animal Hospital', intent: 'Buying', affirm: true });
    expect(c2.state.gate).toBe('pending');
  });

  it('a refused application stays on the form with the server\'s message; the reference keeps the fixture transition (A8.6)', async () => {
    const filled = { name: 'Jane Doe, DVM', vin: '', grad: 'Texas A&M, 2014', state: '', employer: '', intent: 'Buying', affirm: false, error: '' };
    for (const [rejection, shown] of [[authError('CONFLICT', 'An application is already open.'), 'An application is already open.'], [new Error(''), 'Your request could not be sent.']] as const) {
      const c2: any = new Component({ auth: fakeAuth({ apply: vi.fn(() => Promise.reject(rejection)) }) });
      c2.setState({ gate: 'apply', apply: { ...filled } });
      await c2.renderVals().submitApply();
      expect(c2.state.gate).toBe('apply');
      expect(c2.renderVals().apply.error).toBe(shown);
    }

    const auth = fakeAuth();
    const incomplete: any = new Component({ auth });
    incomplete.setState({ gate: 'apply' });
    incomplete.renderVals().submitApply();
    expect(auth.apply, 'the design\'s own required-field check runs first').not.toHaveBeenCalled();

    const reference: any = new Component({});
    reference.setState({ gate: 'apply', apply: { ...filled } });
    reference.renderVals().submitApply();
    expect(reference.state.gate).toBe('pending');
  });

  // -----------------------------------------------------------------------------------------
  // A8.3 — the bootstrap
  // -----------------------------------------------------------------------------------------
  it('componentDidMount lands an unverified account on the check-email card, carrying its address (A8.3)', () => {
    const c2: any = new Component({ me: { ...ACCOUNT, state: 'unverified', email: 'unverified@practice-match.test' } });
    c2.componentDidMount();
    expect(c2.state).toMatchObject({ screen: 'gate', gate: 'check-email', email: 'unverified@practice-match.test', auth: false });
    expect(c2.renderVals().status.title).toBe('Check your email');
  });

  it('componentDidMount takes a needs_review account to the answer card with the reviewer\'s question (A8.3)', async () => {
    const auth = fakeAuth({ applicationsMe: vi.fn(() => Promise.resolve({ current: { id: 'app-9', info_request: 'Which practice do you work at now, and in what role?', fields: {} }, history: [] })) });
    const c2: any = new Component({ auth, me: { ...ACCOUNT, state: 'needs_review' } });
    c2.componentDidMount();
    // Synchronously it is the "under review" card A5.4 already mapped; the answer card arrives
    // with the application, so a slow API never leaves the visitor on a blank screen.
    expect(c2.state).toMatchObject({ screen: 'gate', gate: 'pending' });
    await Promise.resolve(); await Promise.resolve();
    expect(c2.state).toMatchObject({ screen: 'gate', gate: 'answer' });
    expect(c2.state.answer).toMatchObject({ applicationId: 'app-9', note: 'Which practice do you work at now, and in what role?' });
    expect(c2.renderVals().gateAnswer).toBe(true);
  });

  // Two cases, not one loop over `expect(['pending','answer']).toContain(…)` — which was true of
  // BOTH outcomes and could therefore never fail (fix round 1, Important 2). Each asserts the one
  // gate its own outcome must produce, so the other outcome fails it.
  it('a needs_review account whose application cannot be read stays on the "under review" card (A8.3)', async () => {
    for (const applicationsMe of [vi.fn(() => Promise.reject(new Error('offline'))), vi.fn(() => Promise.resolve({ current: null, history: [] }))]) {
      const c2: any = new Component({ auth: fakeAuth({ applicationsMe }), me: { ...ACCOUNT, state: 'needs_review' } });
      c2.componentDidMount();
      await Promise.resolve(); await Promise.resolve();
      expect(c2.state.gate, 'a failed or empty lookup must leave A5.4\'s synchronous card in place').toBe('pending');
      expect(c2.renderVals().gateAnswer).toBe(false);
    }
  });

  it('a needs_review account whose application IS read moves to the answer card, note or no note (A8.3)', async () => {
    const c2: any = new Component({ auth: fakeAuth({ applicationsMe: vi.fn(() => Promise.resolve({ current: { id: 'app-9', info_request: null, fields: {} }, history: [] })) }), me: { ...ACCOUNT, state: 'needs_review' } });
    c2.componentDidMount();
    await Promise.resolve(); await Promise.resolve();
    expect(c2.state.gate).toBe('answer');
    // The note is the empty string, never `null`, when the reviewer left no question.
    expect(c2.state.answer).toMatchObject({ applicationId: 'app-9', note: '' });
  });

  it('componentDidMount pre-fills the application form from a declined account\'s own answers (A8.3, spec §3 "re-apply")', async () => {
    const fields = { name: 'Jane Doe, DVM', vin_member_id: '12345', school_year: 'Texas A&M, 2014', license_state: 'TX', employer: 'Cedar Park Animal Hospital', intent: 'Buying', affirm: true };
    const c2: any = new Component({ auth: fakeAuth({ applicationsMe: vi.fn(() => Promise.resolve({ current: { id: 'app-8', info_request: null, fields }, history: [] })) }), me: { ...ACCOUNT, state: 'declined' } });
    c2.componentDidMount();
    expect(c2.state).toMatchObject({ screen: 'gate', gate: 'rejected' });
    await Promise.resolve(); await Promise.resolve();
    expect(c2.state.apply).toEqual({ name: 'Jane Doe, DVM', vin: '12345', grad: 'Texas A&M, 2014', state: 'TX', employer: 'Cedar Park Animal Hospital', intent: 'Buying', affirm: true, error: '' });
    // …and the declined card's own "Reply with more information" opens that pre-filled form.
    c2.renderVals().status.primary.go();
    expect(c2.state.gate).toBe('apply');
  });

  it('a declined account with no application row, empty fields or a failed lookup leaves the form empty (A8.3)', async () => {
    const empty = { name: '', vin: '', grad: '', state: '', employer: '', intent: '', affirm: false, error: '' };
    for (const applicationsMe of [vi.fn(() => Promise.resolve({ current: null, history: [] })), vi.fn(() => Promise.resolve({ current: { id: 'a', info_request: null, fields: null }, history: [] })), vi.fn(() => Promise.resolve({ current: { id: 'a', info_request: null, fields: {} }, history: [] })), vi.fn(() => Promise.reject(new Error('offline')))]) {
      const c2: any = new Component({ auth: fakeAuth({ applicationsMe }), me: { ...ACCOUNT, state: 'declined' } });
      c2.componentDidMount();
      await Promise.resolve(); await Promise.resolve();
      expect(c2.state.apply).toEqual(empty);
    }
  });

  it('the reference, which has no adapter, never asks for an application at all (A8.3)', async () => {
    for (const state of ['needs_review', 'declined']) {
      const c2: any = new Component({ me: { ...ACCOUNT, state } });
      c2.componentDidMount();
      await Promise.resolve(); await Promise.resolve();
      expect(c2.state.gate, state).toBe(state === 'declined' ? 'rejected' : 'pending');
    }
  });

  it('the startNotice prototype prop puts the reference on the sign-in card with the message, which is how the five notice states are photographed (A8.3/A8.8)', () => {
    const c2: any = new Component({ startNotice: 'Your address is verified. Sign in to complete your access request.' });
    c2.componentDidMount();
    expect(c2.state).toMatchObject({ screen: 'gate', gate: 'signin' });
    expect(c2.renderVals().form).toMatchObject({ error: true, errorText: 'Your address is verified. Sign in to complete your access request.' });
  });

  // A9.1 (controller amendment A-S5, 2026-09-08). The applicant's question is a rendered element
  // fed only by `applicationsMe()`, which the reference never calls — it has no adapter — so the
  // oracle's two targets differed by one line of 13 px text and the card's height, and no
  // `?props=` value could close the gap. `startAnswerNote` is that value, by the same mechanism
  // A8.8b gave the sign-in notices: declared in the design's own `data-props`, read once by
  // `componentDidMount`, and never passed by the app (which reaches the note by fetching it).
  it('the startAnswerNote prototype prop puts the applicant\'s question on the answer card, which is how gate-answer is photographed (A9.1)', () => {
    const c2: any = new Component({ startGate: 'answer', startAnswerNote: 'Which practice do you work at now, and in what role?' });
    c2.componentDidMount();
    expect(c2.state).toMatchObject({ screen: 'gate', gate: 'answer' });
    expect(c2.renderVals().gateAnswer).toBe(true);
    expect(c2.renderVals().answerForm.note).toBe('Which practice do you work at now, and in what role?');
    // It writes ONLY the note: the answer text, the error and the application id are the
    // applicant's own and are not props (the reference never submits).
    expect(c2.state.answer).toEqual({ text: '', error: '', applicationId: '', note: 'Which practice do you work at now, and in what role?' });
  });

  it('without startAnswerNote the answer card renders no note at all, so the 28 approved states cannot move (A9.1)', () => {
    for (const props of [{ startGate: 'answer' }, { startGate: 'answer', startAnswerNote: '' }, {}]) {
      const c2: any = new Component(props);
      c2.componentDidMount();
      expect(c2.state.answer.note, JSON.stringify(props)).toBe('');
      expect(c2.renderVals().answerForm.note, JSON.stringify(props)).toBe('');
    }
  });

  it('startAnswerNote never overrides the note the APP fetched — the app passes none (A9.1)', async () => {
    const c2: any = new Component({ auth: fakeAuth({ applicationsMe: vi.fn(() => Promise.resolve({ current: { id: 'app-9', info_request: 'What is your current role?', fields: {} }, history: [] })) }), me: { ...ACCOUNT, state: 'needs_review' } });
    c2.componentDidMount();
    await Promise.resolve(); await Promise.resolve();
    expect(c2.state).toMatchObject({ gate: 'answer' });
    expect(c2.state.answer).toMatchObject({ applicationId: 'app-9', note: 'What is your current role?' });
  });

  it('a /verify landing posts its token on arrival and shows the notice, or the expired card (A8.3, spec §3 rows 3a/3b)', async () => {
    const auth = fakeAuth();
    const ok: any = new Component({ auth });
    ok.setState({ screen: 'gate', gate: 'verify', gateToken: 'raw-verify-token' });
    ok.componentDidMount();
    expect(auth.verify).toHaveBeenCalledWith('raw-verify-token');
    await Promise.resolve(); await Promise.resolve();
    expect(ok.state).toMatchObject({ gate: 'signin', gateToken: '', formNotice: 'Your address is verified. Sign in to complete your access request.' });

    const spent: any = new Component({ auth: fakeAuth({ verify: vi.fn(() => Promise.reject(authError('TOKEN_INVALID', 'This link is invalid or has expired.'))) }) });
    spent.setState({ screen: 'gate', gate: 'verify', gateToken: 'spent-token' });
    spent.componentDidMount();
    await Promise.resolve(); await Promise.resolve();
    expect(spent.state).toMatchObject({ gate: 'verify-expired', gateToken: '' });
    expect(spent.renderVals().status.title).toBe('This link is no longer valid');

    // The reference has no adapter: nothing is posted, so a token-bearing `verify` gate simply
    // stays put — which is why the oracle photographs `verify-expired` and the notice, not `verify`.
    const reference: any = new Component({});
    reference.setState({ gate: 'verify', gateToken: 't' });
    reference.componentDidMount();
    expect(reference.state.gate).toBe('verify');
  });

  // A-S4 (controller ruling, 2026-09-08). A bare `/verify` — no `?token=` — used to POST an
  // EMPTY token and take the server's own 400 on a rate-limited endpoint, which is both a wasted
  // request and a console error on a route a signed-out visitor can simply type. There is nothing
  // to verify without a token, and the card that says so already exists.
  it('a /verify landing with no token shows the expired card without spending a request (A8.3)', () => {
    const auth = fakeAuth();
    const c2: any = new Component({ auth });
    c2.setState({ screen: 'gate', gate: 'verify', gateToken: '' });
    c2.componentDidMount();
    expect(auth.verify, 'a token-less link must not reach a rate-limited endpoint').not.toHaveBeenCalled();
    expect(c2.state).toMatchObject({ screen: 'gate', gate: 'verify-expired' });
    expect(c2.renderVals().status.title).toBe('This link is no longer valid');

    // …and a token-bearing one still posts, on the very same mount.
    const withToken: any = new Component({ auth: fakeAuth() });
    withToken.setState({ screen: 'gate', gate: 'verify', gateToken: 'raw-verify-token' });
    withToken.componentDidMount();
    expect(withToken.props.auth.verify).toHaveBeenCalledWith('raw-verify-token');

    // The reference has no adapter and still needs the expired card for a token-less landing.
    const reference2: any = new Component({});
    reference2.setState({ screen: 'gate', gate: 'verify', gateToken: '' });
    reference2.componentDidMount();
    expect(reference2.state.gate).toBe('verify-expired');
  });

  it('a token-bearing gate wins over the active-account redirect, so a member following a reset or invitation link still sees that page (A8.3, S2 review rider)', async () => {
    for (const gate of ['verify', 'reset', 'invite']) {
      const c2: any = new Component({ auth: fakeAuth(), me: { ...ACCOUNT, state: 'active' } });
      c2.setState({ screen: 'gate', gate, gateToken: 'raw-token' });
      c2.componentDidMount();
      expect(c2.state, gate).toMatchObject({ screen: 'gate', gate, auth: false });
    }
    // …and `verify` then resolves to the sign-in card with its notice, still on the gate screen.
    const verifying: any = new Component({ auth: fakeAuth(), me: { ...ACCOUNT, state: 'active' } });
    verifying.setState({ screen: 'gate', gate: 'verify', gateToken: 'raw-token' });
    verifying.componentDidMount();
    await Promise.resolve(); await Promise.resolve();
    expect(verifying.state).toMatchObject({ screen: 'gate', gate: 'signin', formNotice: 'Your address is verified. Sign in to complete your access request.' });
    // Every other gate value leaves A5.4's redirect exactly as it was.
    const member: any = new Component({ auth: fakeAuth(), me: { ...ACCOUNT, state: 'active' } });
    member.componentDidMount();
    expect(member.state).toMatchObject({ auth: true, screen: 'browse' });
  });

  // -----------------------------------------------------------------------------------------
  // A8.4/A8.5 — the flags the new blocks render from
  // -----------------------------------------------------------------------------------------
  it('each new gate value lights exactly one card, and only on the gate screen (A8.4/A8.5)', () => {
    const flags = ['gateSignin', 'gateApply', 'gateStatus', 'gateSignup', 'gateForgot', 'gateReset', 'gateInvite', 'gateAnswer'];
    const expected: Record<string, string[]> = {
      signin: ['gateSignin'], apply: ['gateApply'], pending: ['gateStatus'], rejected: ['gateStatus'],
      signup: ['gateSignup'], 'check-email': ['gateStatus'], 'verify-expired': ['gateStatus'],
      forgot: ['gateForgot'], reset: ['gateReset'], 'reset-expired': ['gateStatus'], invite: ['gateInvite'],
      answer: ['gateAnswer'], unavailable: ['gateStatus']
    };
    // Fix round 1: `gateCheckEmail` was computed and read by no template — check-email renders
    // through the card A8.4 fills, like the other three status states. The bundle's own dead-code
    // rule (A2.3, A6.6) applies to a mapping nothing reads.
    expect(new Component({}).renderVals()).not.toHaveProperty('gateCheckEmail');
    for (const [gate, on] of Object.entries(expected)) {
      const c2: any = new Component({});
      c2.setState({ screen: 'gate', gate });
      const v = c2.renderVals();
      expect(flags.filter((f) => v[f]).sort(), gate).toEqual([...on].sort());
      // …and nothing renders once the visitor is off the gate screen.
      c2.setState({ screen: 'browse' });
      const off = c2.renderVals();
      expect(flags.filter((f) => off[f]), `${gate} off the gate screen`).toEqual([]);
    }
  });

  // -----------------------------------------------------------------------------------------
  // A12 — the design reads a listing's own name and photographs (Seed Listings, John 2026-09-08:
  // "Eighteen demo hospitals with real addresses and photos replace the design's fixture
  // practices on QA"). Five literal script edits, so the SEEDED data reaches the title slot and
  // the photo slots the design already had; the design's own fixtures carry neither key, so both
  // fallbacks still fire and every approved state keeps its pixels. Both halves are pinned here.
  // -----------------------------------------------------------------------------------------
  const SEEDED = {
    id: 'abc-animal-hospital', area: 'Cedar Park', type: 'Small animal', market: 'Austin, TX',
    name: 'ABC Animal Hospital',
    photos: ['/api/listings/a1/photos/1', '/api/listings/a1/photos/2']
  };

  it('a listing that carries a name renders it in the title slot (A12.1)', () => {
    expect(c.practiceName(SEEDED)).toBe('ABC Animal Hospital');
  });

  it('a listing that carries photographs fills the hero, the thumbnail and the photo slots (A12.2–A12.5)', () => {
    expect(c.heroSrc(SEEDED)).toBe('/api/listings/a1/photos/1');
    // A12.5, revised on the L6 ruling: the design's own `thumbSrc` is a SECOND VIEW of the
    // practice (the parking photograph, which reads at small sizes where the wide street view
    // does not), so a seeded listing takes its second photograph where it has one.
    expect(c.thumbSrc(SEEDED)).toBe('/api/listings/a1/photos/2');
    expect(c.thumbSrc({ ...SEEDED, photos: ['/api/listings/a1/photos/1'] })).toBe('/api/listings/a1/photos/1');
    const slots = c.photoSet(SEEDED);
    expect(slots.map((s: any) => s.src)).toEqual(['/api/listings/a1/photos/1', '/api/listings/a1/photos/2', '', '', '', '']);
    expect(slots.map((s: any) => s.hasSrc)).toEqual([true, true, false, false, false, false]);
    expect(slots.map((s: any) => s.noSrc)).toEqual([false, false, true, true, true, true]);
    // The design's own six captions, order and placeholder text are untouched — only the name
    // inside the placeholder is now the listing's.
    expect(slots.map((s: any) => s.caption)).toEqual([
      'Exterior — street view', 'Reception and waiting', 'Exam room', 'Treatment area', 'Surgery suite', 'Boarding and runs'
    ]);
    expect(slots[0].placeholder).toBe('ABC Animal Hospital — Exterior — street view');
    expect(slots[0].id).toBe('ph-abc-animal-hospital-exterior');
  });

  // A-L10 (John, 2026-09-09: "match the description"). The caption under each photograph is the
  // DESIGN's own fixed slot caption, so a slot whose hospital has no truthful photograph must
  // stay EMPTY rather than borrow the next one — `photos` is positional and the API now sends a
  // JSON `null` for such a slot. Nothing in the design changes: this is the proof that the
  // design's own expressions already render a null slot as the placeholder they render an absent
  // one as, which is why A-L10 needed no amendment.
  it('a null photo slot renders the design\'s own placeholder and never shifts the others (A-L10)', () => {
    const url1 = '/api/listings/a1/photos/1';
    const url3 = '/api/listings/a1/photos/3';
    const gappy = { ...SEEDED, photos: [url1, null, url3, null, null, null] };
    const slots = c.photoSet(gappy);
    expect(slots.map((s: any) => s.src)).toEqual([url1, '', url3, '', '', '']);
    expect(slots.map((s: any) => s.hasSrc)).toEqual([true, false, true, false, false, false]);
    expect(slots.map((s: any) => s.noSrc)).toEqual([false, true, false, true, true, true]);
    // The exam room is still under "Exam room" — the whole point: slot 3 did not slide up to 2.
    expect(slots.map((s: any) => s.caption)).toEqual([
      'Exterior — street view', 'Reception and waiting', 'Exam room', 'Treatment area', 'Surgery suite', 'Boarding and runs'
    ]);
    expect(slots[1].placeholder).toBe('ABC Animal Hospital — Reception and waiting');
    expect(c.heroSrc(gappy)).toBe(url1);
    // A12.5's `p.photos[1] || p.photos[0]`: a null second view falls back to the first, so the
    // card thumbnail is a photograph rather than a broken image.
    expect(c.thumbSrc(gappy)).toBe(url1);
  });

  // -----------------------------------------------------------------------------------------
  // A15 — every uploaded photograph renders, with its OWN description (A-L11; John, 2026-09-09:
  // "HAS FAILED and wiped out all the images - if the logic is trying to match and failing then
  // surface all images uploaded and have the user articulate what it is and render ALL images -
  // what was 9 images now are only showing 3 after this hotfix!!!").
  //
  // The design renders six FIXED captions per practice, so a photograph could only ever be
  // captioned truthfully by being placed in the slot whose caption describes it — which is why
  // A-L10 rendered only 73 of the 195 images in John's folders. A15 makes a photograph carry its
  // own description (`p.photoCaptions[i]`, the API's `photo_captions`) with the design's fixed
  // slot caption as the FALLBACK, and appends a tile for every photograph past the sixth. The
  // design's fixtures carry NEITHER key — `p2`'s three photographs are the `SRC` map, keyed by
  // slot id, not `p.photos` — so both guards are falsey and every approved state is untouched.
  // -----------------------------------------------------------------------------------------
  const ELEVEN = Array.from({ length: 11 }, (_, n) => `/api/listings/a1/photos/${n + 1}`);
  const DEFAULT_CAPTIONS = [
    'Exterior — street view', 'Reception and waiting', 'Exam room', 'Treatment area',
    'Surgery suite', 'Boarding and runs'
  ];

  it('renders one tile per photograph, past the design\'s six slots (A15.3)', () => {
    const tiles = c.photoSet({ ...SEEDED, photos: ELEVEN });
    expect(tiles).toHaveLength(11);
    expect(tiles.map((t: any) => t.index)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]);
    expect(tiles.map((t: any) => t.src)).toEqual(ELEVEN);
    expect(tiles.map((t: any) => t.hasSrc)).toEqual(Array(11).fill(true));
    expect(tiles.map((t: any) => t.noSrc)).toEqual(Array(11).fill(false));
    // The first six keep the design's own slot ids; the rest are namespaced to the listing too,
    // so a tile of one hospital can never collide with a tile of another.
    expect(tiles.slice(0, 6).map((t: any) => t.id)).toEqual([
      'ph-abc-animal-hospital-exterior', 'ph-abc-animal-hospital-lobby', 'ph-abc-animal-hospital-exam',
      'ph-abc-animal-hospital-treatment', 'ph-abc-animal-hospital-surgery', 'ph-abc-animal-hospital-kennel'
    ]);
    expect(tiles.slice(6).map((t: any) => t.id)).toEqual([
      'ph-abc-animal-hospital-extra1', 'ph-abc-animal-hospital-extra2', 'ph-abc-animal-hospital-extra3',
      'ph-abc-animal-hospital-extra4', 'ph-abc-animal-hospital-extra5'
    ]);
  });

  it('a photograph past the sixth reads "Photo N" until somebody describes it (A15.3)', () => {
    const tiles = c.photoSet({ ...SEEDED, photos: ELEVEN });
    expect(tiles.map((t: any) => t.caption)).toEqual([
      ...DEFAULT_CAPTIONS, 'Photo 7', 'Photo 8', 'Photo 9', 'Photo 10', 'Photo 11'
    ]);
    expect(tiles[6].placeholder).toBe('ABC Animal Hospital — Photo 7');
    expect(tiles[0].placeholder).toBe('ABC Animal Hospital — Exterior — street view');
  });

  it('a photograph\'s own description wins over the design\'s fixed slot caption (A15.1/A15.2)', () => {
    const captions = [
      'Exterior — front entrance', 'Interior — reception lobby', 'Interior — exam room',
      'Interior — treatment area', 'Interior — surgery suite', 'Interior — kennels',
      'Interior — pharmacy counter', 'Interior — laboratory', 'Exterior — parking',
      'Interior — corridor', 'Exterior — signage'
    ];
    const tiles = c.photoSet({ ...SEEDED, photos: ELEVEN, photoCaptions: captions });
    expect(tiles.map((t: any) => t.caption)).toEqual(captions);
    expect(tiles.map((t: any) => t.placeholder)).toEqual(captions.map((cap) => `ABC Animal Hospital — ${cap}`));
  });

  it('a photograph with no description of its own keeps the design\'s caption (A15.1/A15.2)', () => {
    // `null` at a position, and a list shorter than the photographs: both are "nobody has said
    // what this shows", and both must land on the design's own caption rather than on nothing.
    const tiles = c.photoSet({ ...SEEDED, photos: ELEVEN, photoCaptions: [null, 'Interior — reception lobby', ''] });
    expect(tiles.map((t: any) => t.caption)).toEqual([
      'Exterior — street view', 'Interior — reception lobby', 'Exam room', 'Treatment area',
      'Surgery suite', 'Boarding and runs', 'Photo 7', 'Photo 8', 'Photo 9', 'Photo 10', 'Photo 11'
    ]);
    expect(tiles[0].placeholder).toBe('ABC Animal Hospital — Exterior — street view');
  });

  it('the design\'s own p2 practice takes the same two rules (A15.1/A15.3)', () => {
    const p2 = { id: 'p2', area: 'Round Rock', type: 'Small animal', photos: ELEVEN,
      photoCaptions: [null, null, null, null, null, null, 'Interior — pharmacy counter'] };
    const tiles = c.photoSet(p2);
    expect(tiles).toHaveLength(11);
    // SRC still wins for the three the design ships, exactly as A12.2 left it.
    expect(tiles.slice(0, 3).map((t: any) => t.src)).toEqual([
      '/assets/photos/round-rock-exterior-street.webp',
      '/assets/photos/round-rock-exterior-side.webp',
      '/assets/photos/round-rock-exterior-parking.jpeg'
    ]);
    expect(tiles[0].caption).toBe('Exterior — street view');
    expect(tiles[6].caption).toBe('Interior — pharmacy counter');
    expect(tiles[7].caption).toBe('Photo 8');
    expect(tiles[6].id).toBe('ph-p2-extra1');
    expect(tiles.map((t: any) => t.index)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]);
  });

  it('A15 leaves heroSrc and thumbSrc exactly where A12 put them', () => {
    const many = { ...SEEDED, photos: ELEVEN, photoCaptions: ['a', 'b', 'c'] };
    expect(c.heroSrc(many)).toBe('/api/listings/a1/photos/1');
    expect(c.thumbSrc(many)).toBe('/api/listings/a1/photos/2');
  });

  // The other half, and the reason every approved state keeps its pixels: a practice with no
  // `name` and no `photos` — which is every fixture the design ships, and every row the D6 stub
  // returns — renders exactly what it rendered before A12.
  it('a design fixture practice renders exactly as it did before A12 — the fixture name map wins', () => {
    expect(c.practiceName({ id: 'p1', area: 'Cedar Park' })).toBe('Cedar Park Animal Hospital');
    expect(c.practiceName({ id: 'g4', area: 'Peachtree City' })).toBe('Peachtree Equine');
    expect(c.practiceName({ id: 'zz', area: 'Nowhere' })).toBe('Nowhere Veterinary');
  });

  it('a design fixture practice renders exactly as it did before A12 — the p2 assets and the empty slots', () => {
    const p1 = { id: 'p1', area: 'Cedar Park', type: 'Small animal' };
    const p2 = { id: 'p2', area: 'Round Rock', type: 'Small animal' };
    expect(c.heroSrc(p1)).toBe('');
    expect(c.thumbSrc(p1)).toBe('');
    expect(c.heroSrc(p2)).toBe('/assets/photos/round-rock-exterior-street.webp');
    expect(c.thumbSrc(p2)).toBe('/assets/photos/round-rock-exterior-parking.jpeg');
    expect(c.photoSet(p1).map((s: any) => [s.src, s.hasSrc, s.noSrc])).toEqual(Array(6).fill(['', false, true]));
    expect(c.photoSet(p2).map((s: any) => s.src)).toEqual([
      '/assets/photos/round-rock-exterior-street.webp',
      '/assets/photos/round-rock-exterior-side.webp',
      '/assets/photos/round-rock-exterior-parking.jpeg',
      '', '', ''
    ]);
    expect(c.photoSet(p2).map((s: any) => s.hasSrc)).toEqual([true, true, true, false, false, false]);
    expect(c.photoSet(p2).map((s: any) => s.noSrc)).toEqual([false, false, false, true, true, true]);
  });

  // N1 (re-review): the A12.6/A12.7 block below pushes a practice into the SHARED module-level
  // `P` from a hook, so those hooks belong to a nested `describe` of their own. This case is the
  // guard, and it sits in the OUTER block where nothing may have touched `P`: it fails the moment
  // a hook leaks out of its block again. 21 is the design's own fixture count — the nine Austin
  // practices of `logic.js`'s `P` literal plus the twelve its `.forEach` pushes for the other
  // three markets.
  it('the shared fixture array is untouched in this block — no test hook leaks out of its own (N1)', () => {
    const fixtures = P as unknown as Array<{ id: string }>;
    expect(fixtures).toHaveLength(21);
    expect(fixtures.map((x) => x.id)).not.toContain('seed-1');
  });

  // N1 (re-review): NESTED, so the hooks below reach only the two cases that need them. Held in
  // the outer block they pushed an extra practice into the shared `P` for all of its tests — the
  // very order-sensitivity M4's structural push/pop was meant to remove. The guard above proves
  // they stay in.
  describe('A12.6 / A12.7 — a listing with no community figures', () => {
    // -----------------------------------------------------------------------------------------
    // A12.6 / A12.7 — the detail tolerates the community figures the API does not have yet
    // (L6 ruling, 2026-09-08). D4 leaves `pop`, `growth`, `income` and `hh` null for every seeded
    // listing until the Census plan supplies them, and `renderVals()` computes `detail()` on EVERY
    // render — so an unguarded `p.growth.replace(...)` is not a blank card, it is a blank APP.
    // -----------------------------------------------------------------------------------------
    const NULL_FIGURES = {
      id: 'seed-1', area: 'Plano', type: 'Small animal', market: 'Austin, TX', price: 465000,
      rev: 700000, docs: 1, rooms: 3, sqft: 2400, bldg: 'Leased', lat: 33.0, lng: -96.7, est: 1987,
      listed: '3 days ago', status: 'published', pop: null, growth: null, income: null, hh: null,
      note: 'Demo listing seeded by the VIN Foundation.', staff: '1 DVM', hours: 'Mon–Fri 8–6',
      services: 'Wellness', facility: 'Suite', ownership: 'Sole proprietor',
      name: 'ABC Animal Hospital', photos: ['/api/listings/seed-1/photos/1', '/api/listings/seed-1/photos/2']
    };

    // M4 (review round 1): the push and the pop are STRUCTURAL, so the shared module-level `P` is
    // restored even if an assertion throws — a `finally` inside one case leaves the suite
    // order-sensitive the moment anything moves outside its `try`.
    beforeEach(() => { (P as unknown as unknown[]).push(NULL_FIGURES); });
    afterEach(() => {
      const p = P as unknown as Array<{ id: string }>;
      const at = p.findIndex((x) => x.id === 'seed-1');
      if (at > -1) p.splice(at, 1);
    });

    it('every screen renders for a listing whose four community figures are null (A12.6/A12.7)', () => {
      const screens: Array<Record<string, unknown>> = [
        { auth: false, screen: 'gate', gate: 'signin' },
        { auth: true, screen: 'browse' },
        { auth: true, screen: 'browse', viewport: 'mobile', mobileTab: 'list' },
        { auth: true, screen: 'browse', viewport: 'mobile', mobileTab: 'map' },
        { auth: true, screen: 'requests' },
        { auth: true, screen: 'seller' },
        { auth: true, screen: 'admin' },
        { auth: true, screen: 'detail' }
      ];
      for (const patch of screens) {
        const c2: any = new Component({});
        c2.setState({ ...patch, detailId: 'seed-1' });
        expect(() => c2.renderVals(), JSON.stringify(patch)).not.toThrow();
      }
      // …and the four figures compute without throwing, which is all A12.6/A12.7 promised: the
      // populated grid is NOT the design's empty state, and this assertion used to say it was
      // (final review I1). What the member must actually SEE is the case below.
      const c3: any = new Component({});
      c3.setState({ auth: true, screen: 'detail', detailId: 'seed-1' });
      expect(c3.renderVals().d.demo.map((f: any) => [f.k, f.v, f.sub])).toEqual([
        ['Population', null, 'Community, 2023'],
        ['Growth', '', ''],
        ['Median income', null, 'Household, 2023'],
        ['Households', '', 'In the community']
      ]);
    });

    // A12.10 / A12.11 (final review I1): the design HAS an empty state — the dashed
    // "Community data unavailable for this location" card — and `p.id === "p8"` could only ever
    // reach it for one design fixture. A seeded listing rendered the populated four-tile grid
    // with every value blank, under the Census attribution, which reads as attributing an empty
    // panel to the Bureau.
    it('a listing with no community figures reaches the design’s own empty state (A12.10/A12.11)', () => {
      const c5: any = new Component({});
      c5.setState({ auth: true, screen: 'detail', detailId: 'seed-1' });
      const d = c5.renderVals().d;
      expect(d.noDemo, 'the dashed "Community data unavailable" card must render').toBe(true);
      expect(d.hasDemo, 'the populated four-tile grid must not').toBe(false);
    });

    /** The Overview section's "General location" row — the design's second printing of the state. */
    const generalLocation = (d: any) =>
      d.sections.find((sec: any) => sec.title === 'Overview').rows.find((r: any) => r.k === 'General location').v;

    // A12.8 / A12.9 (final review C1): the detail's subtitle and its Overview "General location"
    // row printed a hard-coded ", TX". Every design fixture is in the Austin metro, so the
    // literal was right for all twenty-one of them; the eighteen seeded hospitals span seven
    // states, and thirteen of them would have told a stakeholder they are in Texas. The design's
    // own `stateOf(market)` helper is what the Browse card and the docked panel already call.
    it('the detail names the listing’s OWN state, not Texas (A12.8/A12.9)', () => {
      const denver = { ...NULL_FIGURES, id: 'seed-2', area: 'Denver', market: 'Denver, CO' };
      (P as unknown as unknown[]).push(denver);
      try {
        const c6: any = new Component({});
        // `s.market` stays the design's default: the detail names the LISTING's state
        // (`p.market`), not the metro the member happens to be browsing.
        c6.setState({ auth: true, screen: 'detail', detailId: 'seed-2' });
        const d = c6.renderVals().d;
        expect(d.subtitle).toBe('Denver, CO · Established 1987');
        expect(generalLocation(d)).toBe('Denver, CO');
      } finally {
        const arr = P as unknown as Array<{ id: string }>;
        const at = arr.findIndex((x) => x.id === 'seed-2');
        if (at > -1) arr.splice(at, 1);
      }
    });

    it('an Austin fixture still reads ", TX" — which is why no approved state moves (A12.8/A12.9)', () => {
      const c7: any = new Component({});
      c7.setState({ auth: true, screen: 'detail', detailId: 'p1' });
      const d = c7.renderVals().d;
      expect(d.subtitle).toBe('Cedar Park, TX · Established 1998');
      expect(generalLocation(d)).toBe('Cedar Park, TX');
    });

    it('a design fixture practice still renders its community figures exactly as before (A12.6/A12.7)', () => {
      const c4: any = new Component({});
      c4.setState({ auth: true, screen: 'detail', detailId: 'p1' });
      expect(c4.renderVals().d.demo.map((f: any) => [f.k, f.v])).toEqual([
        ['Population', '81,900'],
        ['Growth', '+14.2%'],
        ['Median income', '$118,400'],
        ['Households', '27,600']
      ]);
    });
  });
});

// ---------------------------------------------------------------------------------------
// The adapter-present paths of amendment family A16 (fix round 2, controller amendment
// A-SL25). The re-review's ⚠️ was exact: `src/logic.js` is outside the coverage gate, the
// oracle only ever drove the no-adapter arms, and nothing in the tree executed a wizard or a
// dashboard handler with `this.props.listings` set — so Critical-A (a newly created listing
// showing the design's three fixture photographs, and saying "Photos attached 3" on the submit
// screen) was invisible to all four gates. These are characterisation cases for the arms the
// oracle cannot reach, in the same shape as the ones above: construct the design's own
// Component, hand it an adapter, drive the design's own handlers.
// ---------------------------------------------------------------------------------------
describe('logic.js — the seller adapter paths (A16, A-SL25)', () => {
  /** A `WizardDraft` as `src/listings/seller.ts`'s `get`/`patch`/`caption` hand one back. */
  const DRAFT = {
    w: { name: 'ABC Animal Hospital', type: 'Mixed', est: '1998', city: 'Bastrop', zip: '78602' },
    assets: [{ kind: 'Photo', name: 'Reception, looking in', id: 'as-1' }]
  };

  /** Every method the design's script reaches through `this.props.listings`, each resolving
   *  unless the test overrides it. `vi.fn()` so a case can assert what was NOT called. */
  function adapter(over: Record<string, unknown> = {}): any {
    return {
      list: vi.fn().mockResolvedValue([]),
      create: vi.fn().mockResolvedValue('new-1'),
      get: vi.fn().mockResolvedValue(DRAFT),
      patch: vi.fn().mockResolvedValue(DRAFT),
      submit: vi.fn().mockResolvedValue(DRAFT),
      setStatus: vi.fn().mockResolvedValue(DRAFT),
      attach: vi.fn().mockResolvedValue(DRAFT),
      ...over
    };
  }

  const ROWS = [{ id: 's1', status: 'published', title: 'T', meta: 'M', note: 'N' }];
  /** Drains the microtask queue. `setListingStatus` and the wizard's `submit` are the design's
   *  own handlers and return no promise — the design never had one to return — so a test that
   *  reads the state after them has to wait for the chain rather than for a value. A macrotask
   *  turn drains every `.then` behind it, which is precisely what Major-B's unhandled rejection
   *  would surface in: vitest fails the file on one. */
  const flush = () => new Promise((r) => setTimeout(r, 0));
  /** The design's own initial wizard state, read from the prototype rather than repeated. */
  const initialW = () => new Component({}).state.w;

  // --- Critical-A -----------------------------------------------------------------------
  it('a newly created listing shows NO photographs and says so on the submit screen', async () => {
    // The defect this round exists to remove: `startWizard` left `wizAssets` unset, A16.4's
    // ternary took the DESIGN's four-item literal, and the design's step rail jumps straight to
    // step 6 or step 8 with no patch — so the seller was shown "Exterior.jpg", "Lobby.jpg" and
    // "Treatment.jpg" on a listing that has no photographs at all, and "Photos attached 3" on
    // the screen they read immediately before Submit for review.
    const api = adapter({ get: vi.fn().mockResolvedValue({ w: {}, assets: [] }) });
    const c2: any = new Component({ listings: api });
    c2.setState({ auth: true, screen: 'seller' });
    await c2.renderVals().startWizard();
    expect(c2.state.editingId).toBe('new-1');
    expect(c2.wizardVals().uploads, 'the design\'s three fixture photographs must not appear').toEqual([]);
    c2.setState({ step: 8 });
    const photos = c2.wizardVals().previewRows.filter((r: any) => r.k === 'Photos attached');
    expect(photos.map((r: any) => r.v)).toEqual(['0']);
  });

  it('the tile source keys on the ADAPTER, not on wizAssets — no value of it reaches the design\'s literal', () => {
    // A-SL25 (1), A16.1's own rule applied to the wizard: with an adapter present the design's
    // fixture tiles are unreachable whatever the state holds.
    const c2: any = new Component({ listings: adapter() });
    c2.setState({ auth: true, screen: 'seller', sellerView: 'wizard', step: 6, wizAssets: undefined });
    expect(c2.wizardVals().uploads).toEqual([]);
    // …and with no adapter the design's own path is untouched, which is the reference.
    expect(new Component({}).wizardVals().uploads).toEqual([
      { kind: 'Photo', name: 'Exterior.jpg' },
      { kind: 'Photo', name: 'Lobby.jpg' },
      { kind: 'Photo', name: 'Treatment.jpg' }
    ]);
  });

  // --- A16.14, create -------------------------------------------------------------------
  it('Create a listing creates, reads the new draft back and opens THAT', async () => {
    const api = adapter();
    const c2: any = new Component({ listings: api });
    c2.setState({ auth: true, screen: 'seller' });
    await c2.renderVals().startWizard();
    expect(api.create).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledWith('new-1');
    expect(c2.state).toMatchObject({ sellerView: 'wizard', step: 1, editingId: 'new-1', wizErr: '', creating: false });
    expect(c2.state.wizAssets).toEqual(DRAFT.assets);
    expect(c2.state.w).toEqual({ ...initialW(), ...DRAFT.w });
  });

  it('a refused create opens the wizard on nothing at all, with the server\'s message', async () => {
    const api = adapter({ create: vi.fn().mockRejectedValue(new Error('Too many requests.')) });
    const c2: any = new Component({ listings: api });
    c2.setState({ auth: true, screen: 'seller', editingId: 'old-9', wizAssets: [{ kind: 'Photo', name: 'x', id: 'a' }], w: { ...initialW(), city: 'Cedar Park' } });
    await c2.renderVals().startWizard();
    expect(c2.state).toMatchObject({ sellerView: 'wizard', step: 1, editingId: null, wizErr: 'Too many requests.', creating: false });
    expect(c2.state.wizAssets).toEqual([]);
    expect(c2.state.w).toEqual(initialW());
  });

  it('a refused READ of the just-created listing lands in the same arm', async () => {
    const api = adapter({ get: vi.fn().mockRejectedValue(new Error('That listing could not be read.')) });
    const c2: any = new Component({ listings: api });
    c2.setState({ auth: true, screen: 'seller' });
    await c2.renderVals().startWizard();
    expect(c2.state).toMatchObject({ editingId: null, wizErr: 'That listing could not be read.', creating: false });
    expect(c2.state.wizAssets).toEqual([]);
  });

  // --- Minor-B ---------------------------------------------------------------------------
  it('a second press while the create is in flight creates nothing more', async () => {
    // The guard is stronger than this case can show, and the reason is the seam (round-2
    // re-review, Info-H): `app.setup.js` wraps the state in Vue's `reactive()` and `renderVals()`
    // closes over `const s = this.state` — the reactive object itself, not a snapshot — so
    // `s.creating` reads the LIVE value at click time and the guard holds with no re-render
    // between two presses. Calling `renderVals()` afresh per press models a re-render, which is
    // the weaker property; the stronger one belongs to the adapter seam, not to this file.
    let release: (id: string) => void = () => {};
    const api = adapter({ create: vi.fn().mockReturnValue(new Promise<string>((r) => { release = r; })) });
    const c2: any = new Component({ listings: api });
    c2.setState({ auth: true, screen: 'seller' });
    const first = c2.renderVals().startWizard();
    expect(c2.state.creating).toBe(true);
    c2.renderVals().startWizard();
    c2.renderVals().startWizard();
    expect(api.create).toHaveBeenCalledTimes(1);
    release('new-1');
    await first;
    expect(c2.state.creating).toBe(false);
    // …and the flag clears, so the next listing can be created.
    await c2.renderVals().startWizard();
    expect(api.create).toHaveBeenCalledTimes(2);
  });

  // --- Major-A ---------------------------------------------------------------------------
  it('a refused Edit never leaves the previous listing live under the wizard', async () => {
    const api = adapter({ get: vi.fn().mockRejectedValue(new Error('That listing could not be opened.')) });
    const c2: any = new Component({ listings: api });
    c2.setState({
      auth: true, screen: 'seller', myListings: ROWS,
      editingId: 'other-9', wizAssets: [{ kind: 'Photo', name: 'x', id: 'a' }], w: { ...initialW(), city: 'Cedar Park' }
    });
    const edit = c2.sellerVals().listings[0].actions.filter((a: any) => a.label === 'Edit')[0];
    await edit.go();
    expect(c2.state).toMatchObject({ sellerView: 'wizard', step: 1, editingId: null, wizErr: 'That listing could not be opened.' });
    expect(c2.state.wizAssets, 'the other listing\'s photographs must not survive').toEqual([]);
    expect(c2.state.w, 'nor its fields').toEqual(initialW());
  });

  it('Edit opens the row\'s own draft through the same setter Create does', async () => {
    const api = adapter();
    const c2: any = new Component({ listings: api });
    c2.setState({ auth: true, screen: 'seller', myListings: ROWS });
    await c2.sellerVals().listings[0].actions.filter((a: any) => a.label === 'Edit')[0].go();
    expect(api.get).toHaveBeenCalledWith('s1');
    expect(c2.state).toMatchObject({ sellerView: 'wizard', step: 1, editingId: 's1', wizErr: '' });
    expect(c2.state.wizAssets).toEqual(DRAFT.assets);
    expect(c2.state.w).toEqual({ ...initialW(), ...DRAFT.w });
  });

  // --- Major-B ----------------------------------------------------------------------------
  it('a refused reload after a successful transition rejects nowhere and empties the rows', async () => {
    const api = adapter({ list: vi.fn().mockRejectedValue(new Error('Too many requests.')) });
    const c2: any = new Component({ listings: api });
    c2.setState({ auth: true, screen: 'seller', myListings: ROWS });
    c2.setListingStatus('s1', 'withdrawn');
    await flush();
    expect(api.setStatus).toHaveBeenCalledWith('s1', 'withdraw');
    expect(c2.state.myListings, 'A16.9\'s own answer to a load that failed').toEqual([]);
  });

  it('a refused reload after Submit rejects nowhere and empties the rows', async () => {
    const api = adapter({ list: vi.fn().mockRejectedValue(new Error('Too many requests.')) });
    const c2: any = new Component({ listings: api });
    c2.setState({ auth: true, screen: 'seller', sellerView: 'wizard', step: 8, editingId: 'a3f1', myListings: ROWS });
    c2.wizardVals().submit();
    await flush();
    expect(api.submit).toHaveBeenCalledWith('a3f1');
    expect(c2.state.wizSubmitted, 'the design\'s own Submitted card still appears at once').toBe(true);
    expect(c2.state.myListings).toEqual([]);
  });

  // --- Info-B -----------------------------------------------------------------------------
  it('with an adapter and no listing behind the wizard, Add files does nothing at all', () => {
    const api = adapter();
    const c2: any = new Component({ listings: api });
    c2.setState({ auth: true, screen: 'seller', sellerView: 'wizard', step: 6, editingId: null });
    c2.wizardVals().addPhoto();
    expect(api.attach, 'nothing to upload onto').not.toHaveBeenCalled();
    expect(c2.state.w.photos, 'and the design\'s fake counter is never bumped behind an adapter').toBe(0);
  });
});

// ---------------------------------------------------------------------------------------
// The design's own Continue and Save-and-exit, driven against the REAL adapter over a stubbed
// `fetch` (fix round 3, controller amendment A-SL26). The suite above hands `logic.js` a fake
// adapter, which proves what the handlers do with an answer but not what they ASK FOR — and what
// they asked for was every one of `w`'s 21 keys on a step that accepts four. `columns_for`'s
// whitelist is total and one-directional (ruling D10), so the first Continue was
// `400 step 1 does not accept anon, bldg, city, …` and not one field the seller typed was ever
// written; Save and exit took the same refusal and its arm deliberately keeps the seller in the
// wizard, so they were trapped on the step (round-2 re-review, CRITICAL-B). Nothing could see it:
// `logic.js` is outside the coverage gate, the adapter's own test was handed a pre-filtered body,
// pytest calls the endpoint with correct bodies, and the four `wizard-*` captures reach steps 7
// and 8 through the design's step rail, which patches nothing.
// ---------------------------------------------------------------------------------------
describe('logic.js — what Continue actually sends (A-SL26)', () => {
  interface Sent { url: string; method: string; body: unknown }

  /** The network boundary, recording every request; `seller.test.ts`'s own stub, widened. The
   *  answer may depend on the request (a create answers an id, every read the draft), and a
   *  `status` outside 2xx makes every answer a refusal in the A5 envelope. */
  function record(answer: unknown | ((url: string, method: string) => unknown), status = 200): Sent[] {
    const sent: Sent[] = [];
    vi.stubGlobal('fetch', (url: string, init: { method: string; body?: string }) => {
      sent.push({ url, method: init.method, body: init.body === undefined ? undefined : JSON.parse(init.body) });
      const body = typeof answer === 'function' ? (answer as (u: string, m: string) => unknown)(url, init.method) : answer;
      return Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) });
    });
    return sent;
  }

  /** A `serialise_draft` payload — every key the adapter's `Draft` declares. */
  const draft = (over: Record<string, unknown> = {}) => ({
    id: 'a3f1', slug: 'listing-a3f1', status: 'draft',
    name: null, type: null, est: null, ownership: null, city: null, zip: null,
    price: null, rev: null, docs: null, rooms: null, sqft: null, hours: null, desc: null,
    bldg: null, facilityType: null, facility: null, anon: true, revBand: false, docsLocked: true,
    state: null, market: null, area: null, decline_reason: null, submitted_at: null,
    updated_at: '2026-09-09T00:00:00Z', assets: [], photos: [], documents: [], ...over
  });

  /** A component on the wizard, with the REAL adapter and a listing behind it. */
  function onStep(step: number): any {
    const c2: any = new Component({ listings: makeListingsAdapter() });
    c2.setState({
      auth: true, screen: 'seller', sellerView: 'wizard', step, editingId: 'a3f1',
      // Every field the design's own steps validate before they advance, so `next()` reaches the
      // request rather than stopping at one of the design's three guards (logic.js:1253-1255).
      w: { ...c2.state.w, name: 'ABC Animal Hospital', est: '1998', city: 'Bastrop', zip: '78602', price: '860000', rev: '700000', state: 'TX' }
    });
    return c2;
  }

  beforeEach(() => { document.cookie = 'pm_csrf=tok'; });
  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = 'pm_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
  });

  it('Continue sends exactly the step\'s own fields, on every step that has any', async () => {
    for (const [step, keys] of Object.entries(STEP_FIELDS)) {
      const c2 = onStep(Number(step));
      const sent = record(draft());
      await c2.wizardVals().next();
      expect(sent.map((r) => r.method), `step ${step}`).toEqual(['PATCH']);
      expect(sent[0].url, `step ${step}`).toBe(`/api/seller/listings/a3f1?step=${step}`);
      expect(Object.keys(sent[0].body as object).sort(), `step ${step}`).toEqual([...keys].sort());
      expect(c2.state.wizErr, `step ${step}`).toBe('');
      expect(c2.state.step, `step ${step}`).toBe(Math.min(8, Number(step) + 1));
      vi.unstubAllGlobals();
    }
  });

  it('Continue on step 6 advances without a PATCH — its assets were saved on upload', async () => {
    const c2 = onStep(6);
    const sent = record(draft({ photos: [{ id: 'as-1', name: 'Reception' }] }));
    await c2.wizardVals().next();
    expect(sent.map((r) => r.method)).toEqual(['GET']);
    expect(c2.state.step).toBe(7);
    expect(c2.state.wizErr).toBe('');
    expect(c2.state.wizAssets).toEqual([{ kind: 'Photo', name: 'Reception', id: 'as-1' }]);
  });

  it('Save and exit on step 6 leaves the wizard without a PATCH', async () => {
    const c2 = onStep(6);
    const sent = record(draft());
    await c2.renderVals().exitWizard();
    expect(sent.map((r) => r.method)).toEqual(['GET', 'GET']);   // the re-read, then the reload
    expect(c2.state.sellerView).toBe('dash');
    expect(c2.state.wizErr).toBe('');
  });

  it('Save and exit on a field step saves that step, then leaves', async () => {
    const c2 = onStep(3);
    const sent = record(draft());
    await c2.renderVals().exitWizard();
    expect(sent[0].method).toBe('PATCH');
    expect(sent[0].url).toBe('/api/seller/listings/a3f1?step=3');
    expect(Object.keys(sent[0].body as object).sort()).toEqual(['price', 'rev', 'revBand']);
    expect(c2.state.sellerView).toBe('dash');
  });

  // -------------------------------------------------------------------------------------------
  // A-SL27, the round-3 re-review: the same wire, watched on the paths the three fixtures above
  // never took — a listing the seller has JUST CREATED (every column null), a save that is not
  // Continue, and the step rail.
  // -------------------------------------------------------------------------------------------
  describe('a created listing, Save and exit, and the step rail (A-SL27)', () => {
    /** A component on the seller dashboard with the REAL adapter, and a network that answers a
     *  create with an id and every read with a BARE draft — what `serialise_draft` really sends
     *  for a row `create` has just inserted: every column null, the three switches at the table's
     *  defaults. `onStep()` above seeds `w` from the design's literal; this is the one path that
     *  seeds it from the API. */
    async function created(): Promise<{ c2: any; sent: Sent[] }> {
      const c2: any = new Component({ listings: makeListingsAdapter() });
      c2.setState({ auth: true, screen: 'seller', sellerView: 'dash', myListings: [] });
      const sent = record((url: string, method: string) => (method === 'POST' && url === '/api/seller/listings'
        ? { id: 'new-1' }
        : draft({ id: 'new-1', revBand: true })));
      await c2.renderVals().startWizard();
      return { c2, sent };
    }

    it('a listing the seller just created opens on the design\'s own four defaults, not on blanks (CRITICAL-C)', async () => {
      const { c2 } = await created();
      expect(c2.state.editingId).toBe('new-1');
      expect(c2.state.step).toBe(1);
      // The API answered null for all four; the design's literal is what the wizard shows.
      expect(c2.state.w).toMatchObject({ type: 'Small animal', ownership: 'Sole proprietor', bldg: 'Included', facilityType: 'Standalone' });
      expect(c2.wizardVals().fields.map((f: { value: unknown }) => f.value)).toEqual(['', 'Small animal', '', 'Sole proprietor']);
      // …and what the API DID answer is taken as it is: the switches, in the table's own polarity.
      expect(c2.state.w).toMatchObject({ anon: true, revBand: true, docsLocked: true });
    });

    it('the first Continue of that listing PATCHes the design\'s default enums, on step 1 and on step 5 (CRITICAL-C)', async () => {
      const { c2, sent } = await created();
      // The seller types what the design's own step-1 guard requires and presses Continue.
      c2.setW('name')('ABC Animal Hospital');
      c2.setW('est')('1998');
      await c2.wizardVals().next();
      const first = sent.filter((r) => r.method === 'PATCH');
      expect(first).toHaveLength(1);
      expect(first[0].url).toBe('/api/seller/listings/new-1?step=1');
      expect(first[0].body, 'never "" for an enum').toEqual({ name: 'ABC Animal Hospital', type: 'Small animal', est: '1998', ownership: 'Sole proprietor' });
      expect(c2.state.step).toBe(2);
      expect(c2.state.wizErr).toBe('');

      c2.setState({ step: 5 });
      await c2.wizardVals().next();
      const fifth = sent.filter((r) => r.method === 'PATCH')[1];
      expect(fifth.url).toBe('/api/seller/listings/new-1?step=5');
      expect(fifth.body).toEqual({ bldg: 'Included', facilityType: 'Standalone', facility: '' });
      expect(c2.state.step).toBe(6);
    });

    it('Save and exit on step 1 with the year still blank saves without it, and leaves (MAJOR-D)', async () => {
      const { c2, sent } = await created();
      c2.setW('name')('ABC Animal Hospital');
      await c2.renderVals().exitWizard();
      const patch = sent.filter((r) => r.method === 'PATCH');
      expect(patch).toHaveLength(1);
      expect(patch[0].url).toBe('/api/seller/listings/new-1?step=1');
      expect(patch[0].body, 'the blank required number is left out, not sent as ""').toEqual({ name: 'ABC Animal Hospital', type: 'Small animal', ownership: 'Sole proprietor' });
      expect(c2.state.sellerView).toBe('dash');
      expect(c2.state.wizErr).toBe('');
    });

    it('Save and exit on step 3 with the asking price still blank saves without it, and leaves (MAJOR-D)', async () => {
      const { c2, sent } = await created();
      c2.setState({ step: 3 });
      await c2.renderVals().exitWizard();
      const patch = sent.filter((r) => r.method === 'PATCH');
      expect(patch[0].url).toBe('/api/seller/listings/new-1?step=3');
      expect(patch[0].body).toEqual({ rev: '', revBand: true });
      expect(c2.state.sellerView).toBe('dash');
    });

    it('a genuine refusal of Save and exit still keeps the seller in the wizard, with the message (A-SL23 (3))', async () => {
      const c2 = onStep(2);
      record({ error: { code: 'BAD_REQUEST', message: 'zip must be text.' } }, 400);
      await c2.renderVals().exitWizard();
      expect(c2.state.sellerView).toBe('wizard');
      expect(c2.state.wizErr).toBe('zip must be text.');
    });

    it('the step rail saves the step it leaves before it moves (MAJOR-E, A16.18)', async () => {
      const c2 = onStep(5);
      c2.setW('facility')('Two surgical suites');
      const sent = record(draft({ photos: [{ id: 'as-1', name: 'Reception' }] }));
      await c2.wizardVals().steps[5].go();
      expect(sent.map((r) => r.method)).toEqual(['PATCH']);
      expect(sent[0].url).toBe('/api/seller/listings/a3f1?step=5');
      expect(sent[0].body).toEqual({ bldg: 'Included', facilityType: 'Standalone', facility: 'Two surgical suites' });
      expect(c2.state.step).toBe(6);
      expect(c2.state.wizErr).toBe('');
      expect(c2.state.wizAssets, 'the tiles come from the answer, as Continue\'s do').toEqual([{ kind: 'Photo', name: 'Reception', id: 'as-1' }]);
    });

    it('the rail saves in partial mode, so leaving a half-filled step 1 by the rail is not a refusal (MAJOR-D/E)', async () => {
      const { c2, sent } = await created();
      c2.setW('name')('ABC Animal Hospital');
      await c2.wizardVals().steps[2].go();
      const patch = sent.filter((r) => r.method === 'PATCH');
      expect(patch[0].url).toBe('/api/seller/listings/new-1?step=1');
      expect(patch[0].body).toEqual({ name: 'ABC Animal Hospital', type: 'Small animal', ownership: 'Sole proprietor' });
      expect(c2.state.step).toBe(3);
    });

    it('a refused rail save keeps the seller on the step they were typing on, with the message (MAJOR-E)', async () => {
      const c2 = onStep(4);
      record({ error: { code: 'BAD_REQUEST', message: 'sqft is larger than this listing can hold.' } }, 422);
      await c2.wizardVals().steps[6].go();
      expect(c2.state.step).toBe(4);
      expect(c2.state.wizErr).toBe('sqft is larger than this listing can hold.');
    });

    it('the rail off step 6 or step 8 re-reads and moves — no PATCH, since neither step has a field (MAJOR-E)', async () => {
      for (const from of [6, 8]) {
        const c2 = onStep(from);
        const sent = record(draft());
        await c2.wizardVals().steps[0].go();
        expect(sent.map((r) => [r.method, r.url]), `from step ${from}`).toEqual([['GET', '/api/seller/listings/a3f1']]);
        expect(c2.state.step, `from step ${from}`).toBe(1);
        vi.unstubAllGlobals();
      }
    });

    // --- MAJOR-F (round-4 re-review), A-SL29 (1): Back is the rail's twin --------------------
    it('Back saves the step it leaves before it moves (MAJOR-F, A16.19)', async () => {
      // Round 3 said the rail was "the ONE navigation control that silently discards work"; it was
      // wrong by one control. Type on step 5 → Back → step 4 → Save and exit lost step 5, under the
      // same "Saved automatically" chrome. Same shape as A16.18: partial mode, Continue's own arm.
      const c2 = onStep(5);
      c2.setW('facility')('Two surgical suites');
      const sent = record(draft({ photos: [{ id: 'as-1', name: 'Reception' }] }));
      await c2.wizardVals().back();
      expect(sent.map((r) => r.method)).toEqual(['PATCH']);
      expect(sent[0].url).toBe('/api/seller/listings/a3f1?step=5');
      expect(sent[0].body).toEqual({ bldg: 'Included', facilityType: 'Standalone', facility: 'Two surgical suites' });
      expect(c2.state.step).toBe(4);
      expect(c2.state.wizErr).toBe('');
      expect(c2.state.wizAssets).toEqual([{ kind: 'Photo', name: 'Reception', id: 'as-1' }]);
    });

    it('Back saves in partial mode, and on step 1 it saves and stays (MAJOR-F)', async () => {
      const { c2, sent } = await created();
      c2.setW('name')('ABC Animal Hospital');
      await c2.wizardVals().back();
      const patch = sent.filter((r) => r.method === 'PATCH');
      expect(patch).toHaveLength(1);
      expect(patch[0].url).toBe('/api/seller/listings/new-1?step=1');
      expect(patch[0].body, 'the blank year is left out').toEqual({ name: 'ABC Animal Hospital', type: 'Small animal', ownership: 'Sole proprietor' });
      expect(c2.state.step, 'the design\'s own Math.max(1, step - 1)').toBe(1);
    });

    it('a refused Back save keeps the seller on the step they were typing on, with the message (MAJOR-F)', async () => {
      const c2 = onStep(4);
      record({ error: { code: 'BAD_REQUEST', message: 'sqft must be a number.' } }, 400);
      await c2.wizardVals().back();
      expect(c2.state.step).toBe(4);
      expect(c2.state.wizErr).toBe('sqft must be a number.');
    });

    it('Back off step 6 or step 8 re-reads and moves — no PATCH, since neither step has a field (MAJOR-F)', async () => {
      for (const from of [6, 8]) {
        const c2 = onStep(from);
        const sent = record(draft());
        await c2.wizardVals().back();
        expect(sent.map((r) => [r.method, r.url]), `from step ${from}`).toEqual([['GET', '/api/seller/listings/a3f1']]);
        expect(c2.state.step, `from step ${from}`).toBe(from - 1);
        vi.unstubAllGlobals();
      }
    });

    it('without an adapter Back is the design\'s own move, and spends no request (MAJOR-F)', () => {
      const plain: any = new Component({});
      plain.setState({ auth: true, screen: 'seller', sellerView: 'wizard', step: 5, wizErr: 'x' });
      const sent = record(draft());
      plain.wizardVals().back();
      expect(plain.state.step).toBe(4);
      expect(plain.state.wizErr).toBe('');
      expect(sent).toEqual([]);
    });

    it('without an adapter the rail is the design\'s own move, and spends no request (MAJOR-E)', () => {
      const plain: any = new Component({});
      plain.setState({ auth: true, screen: 'seller', sellerView: 'wizard', step: 2, wizErr: 'x' });
      const sent = record(draft());
      plain.wizardVals().steps[6].go();
      expect(plain.state.step).toBe(7);
      expect(plain.state.wizErr).toBe('');
      expect(sent).toEqual([]);
    });

    it('every field of the design\'s `w` except photos is saved by some step; the two switches step 7 repeats belong to two (INFO-J)', () => {
      // The pin was one-directional: `photos` and `state` were asserted absent from every step,
      // but nothing said the other nineteen keys were each PRESENT in one. A twentieth field added
      // to `w` by a later amendment would have been silently un-saveable, every gate green.
      const w = Object.keys(new Component({}).state.w).filter((key) => key !== 'photos');
      const count = (key: string) => Object.values(STEP_FIELDS).filter((keys) => keys.includes(key)).length;
      for (const key of w) expect(count(key), `${key} is saved by no step`).toBeGreaterThanOrEqual(1);
      // `anon` and `revBand` are the design's own repeats — step 7's disclosure settings re-offer
      // step 2's and step 3's switch — so each is saved from exactly two steps; every other key
      // from exactly one. The ruling's "exactly one" is true of every key the design does not
      // deliberately repeat; the two it does are pinned by name so a third cannot appear unnoticed.
      expect(w.filter((key) => count(key) !== 1).sort()).toEqual(['anon', 'revBand']);
      expect(count('anon')).toBe(2);
      expect(count('revBand')).toBe(2);
    });
  });

  // ---------------------------------------------------------------------------------------
  // A-SL30 (3), on the round-5 re-review's Info-15: A16.18/A16.19 made the rail and Back save the
  // step they leave; two doors out of the wizard still did not — the header nav (`go`) and Sign
  // out, both under the same "Saved automatically" chrome. A16.20a/A16.20b are the rail's shape at
  // both doors: partial mode, Continue's own single rejection arm, no PATCH on steps 6/8. Sign out
  // is a genuine exception (A-SL30 (3)'s own ruling): it ATTEMPTS the save and ends the session
  // regardless of the answer, because a session end is the seller's explicit act and must never be
  // held hostage to one.
  // ---------------------------------------------------------------------------------------
  describe('leaving the wizard by header navigation or signing out also saves the step (A-SL30 (3), Info-15)', () => {
    it('go() saves the step it leaves before it navigates (A16.20a)', async () => {
      const c2 = onStep(5);
      c2.setW('facility')('Two surgical suites');
      const sent = record(draft({ photos: [{ id: 'as-1', name: 'Reception' }] }));
      await c2.go('browse')();
      expect(sent.map((r) => r.method)).toEqual(['PATCH']);
      expect(sent[0].url).toBe('/api/seller/listings/a3f1?step=5');
      expect(sent[0].body).toEqual({ bldg: 'Included', facilityType: 'Standalone', facility: 'Two surgical suites' });
      expect(c2.state.screen).toBe('browse');
      expect(c2.state.wizErr).toBe('');
      expect(c2.state.wizAssets).toEqual([{ kind: 'Photo', name: 'Reception', id: 'as-1' }]);
    });

    it('a refused go() save keeps the seller in the wizard, with the message (A16.20a)', async () => {
      const c2 = onStep(4);
      record({ error: { code: 'BAD_REQUEST', message: 'sqft must be a number.' } }, 400);
      await c2.go('browse')();
      expect(c2.state.screen).toBe('seller');
      expect(c2.state.sellerView).toBe('wizard');
      expect(c2.state.wizErr).toBe('sqft must be a number.');
    });

    it('go() off step 6 or step 8 re-reads and moves — no PATCH, since neither step has a field (A16.20a)', async () => {
      for (const from of [6, 8]) {
        const c2 = onStep(from);
        const sent = record(draft());
        await c2.go('browse')();
        expect(sent.map((r) => [r.method, r.url]), `from step ${from}`).toEqual([['GET', '/api/seller/listings/a3f1']]);
        expect(c2.state.screen, `from step ${from}`).toBe('browse');
        vi.unstubAllGlobals();
      }
    });

    it('go() navigates at once when the wizard is not open, whatever the adapter (A16.20a)', () => {
      const c2: any = new Component({ listings: makeListingsAdapter() });
      c2.setState({ auth: true, screen: 'browse', sellerView: 'dash' });
      const sent = record(draft());
      c2.go('seller')();
      expect(c2.state.screen).toBe('seller');
      expect(sent).toEqual([]);
    });

    it('go() navigates at once when the wizard is open but nothing is being edited (A16.20a)', () => {
      const c2: any = new Component({ listings: makeListingsAdapter() });
      c2.setState({ auth: true, screen: 'seller', sellerView: 'wizard', editingId: null });
      const sent = record(draft());
      c2.go('browse')();
      expect(c2.state.screen).toBe('browse');
      expect(sent).toEqual([]);
    });

    it('without an adapter go() is the design\'s own move, and spends no request (A16.20a)', () => {
      const plain: any = new Component({});
      plain.setState({ auth: true, screen: 'seller', sellerView: 'wizard', editingId: 'a3f1' });
      const sent = record(draft());
      plain.go('browse')();
      expect(plain.state.screen).toBe('browse');
      expect(sent).toEqual([]);
    });

    it('signOut attempts to save the step the wizard is on, then signs out regardless of the answer (A16.20b)', async () => {
      const c2 = onStep(5);
      c2.setW('facility')('Two surgical suites');
      const sent = record(draft());
      await c2.renderVals().signOut();
      expect(sent.map((r) => r.method)).toEqual(['PATCH']);
      expect(sent[0].url).toBe('/api/seller/listings/a3f1?step=5');
      expect(sent[0].body).toEqual({ bldg: 'Included', facilityType: 'Standalone', facility: 'Two surgical suites' });
      expect(c2.state.auth).toBe(false);
      expect(c2.state.screen).toBe('gate');
      expect(c2.state.sellerView).toBe('dash');
    });

    it('a refused signOut save still signs out — a session end is never held hostage to a save (A16.20b)', async () => {
      const c2 = onStep(5);
      record({ error: { code: 'BAD_REQUEST', message: 'sqft must be a number.' } }, 400);
      await c2.renderVals().signOut();
      expect(c2.state.auth).toBe(false);
      expect(c2.state.screen).toBe('gate');
      expect(c2.state.sellerView).toBe('dash');
    });

    it('signOut off step 6 or step 8 re-reads and still signs out — no PATCH (A16.20b)', async () => {
      for (const from of [6, 8]) {
        const c2 = onStep(from);
        const sent = record(draft());
        await c2.renderVals().signOut();
        expect(sent.map((r) => [r.method, r.url]), `from step ${from}`).toEqual([['GET', '/api/seller/listings/a3f1']]);
        expect(c2.state.auth, `from step ${from}`).toBe(false);
        vi.unstubAllGlobals();
      }
    });

    it('signOut outside the wizard signs out with no save attempt (A16.20b)', async () => {
      const c2: any = new Component({ listings: makeListingsAdapter() });
      c2.setState({ auth: true, screen: 'browse', sellerView: 'dash' });
      const sent = record(draft());
      await c2.renderVals().signOut();
      expect(sent).toEqual([]);
      expect(c2.state.auth).toBe(false);
    });

    it('signOut with the wizard open but nothing being edited signs out with no save attempt (A16.20b)', async () => {
      const c2: any = new Component({ listings: makeListingsAdapter() });
      c2.setState({ auth: true, screen: 'seller', sellerView: 'wizard', editingId: null });
      const sent = record(draft());
      await c2.renderVals().signOut();
      expect(sent).toEqual([]);
      expect(c2.state.auth).toBe(false);
    });

    it('without an adapter signOut is the design\'s own move, and spends no request (A16.20b)', async () => {
      const plain: any = new Component({});
      plain.setState({ auth: true, screen: 'seller', sellerView: 'wizard', editingId: 'a3f1' });
      const sent = record(draft());
      await plain.renderVals().signOut();
      expect(sent).toEqual([]);
      expect(plain.state.auth).toBe(false);
    });
  });

  // ---------------------------------------------------------------------------------------
  // A-SL25 (10) / SL7b: the step-6 tile re-describes an EXISTING photograph, seeded ones
  // included, by clicking it — the design's own `prompt`-based describe flow SL7 wired for
  // upload, now wired to the tile too. ONE chained promise, one rejection arm into `wizErr`
  // (A-SL23 (4)'s `attach` shape), routed by the tile's own `source`: `caption()` for an asset,
  // the positional route for a seed entry. Photographs only; a document tile has no handler.
  // ---------------------------------------------------------------------------------------
  describe('the step-6 tile re-describes an existing photograph on click (A-SL25 (10), A16.21/A16.22)', () => {
    it('an asset-backed tile\'s describe writes through caption(), and refreshes the tiles (A16.21)', async () => {
      const c2 = onStep(6);
      c2.setState({ wizAssets: [{ kind: 'Photo', name: 'Reception', id: 'as-1', source: 'asset' }] });
      const sent = record(draft({ photos: [{ id: 'as-1', name: 'The lobby', source: 'asset' }] }));
      vi.stubGlobal('prompt', vi.fn().mockReturnValue('The lobby'));
      await c2.wizardVals().uploads[0].describe();
      expect(sent.map((r) => [r.method, r.url])).toEqual([['PATCH', '/api/seller/listings/a3f1/assets/as-1']]);
      expect(sent[0].body).toEqual({ caption: 'The lobby' });
      expect(c2.state.wizAssets).toEqual([{ kind: 'Photo', id: 'as-1', name: 'The lobby', source: 'asset' }]);
      expect(c2.state.wizErr).toBe('');
      vi.unstubAllGlobals();
    });

    it('a seed-backed tile\'s describe writes through the positional route, by its own position (A16.21)', async () => {
      const c2 = onStep(6);
      c2.setState({ wizAssets: [{ kind: 'Photo', name: 'Exterior — front', id: 'a/3.webp', source: 'seed', position: 3 }] });
      const sent = record(draft({ photos: [{ id: 'a/3.webp', name: 'The exam room', source: 'seed', position: 3 }] }));
      vi.stubGlobal('prompt', vi.fn().mockReturnValue('The exam room'));
      await c2.wizardVals().uploads[0].describe();
      expect(sent.map((r) => [r.method, r.url])).toEqual([['PATCH', '/api/seller/listings/a3f1/photos/3']]);
      expect(sent[0].body).toEqual({ caption: 'The exam room' });
      expect(c2.state.wizAssets).toEqual([{ kind: 'Photo', id: 'a/3.webp', name: 'The exam room', source: 'seed', position: 3 }]);
      vi.unstubAllGlobals();
    });

    it('a refused re-caption sets wizErr and leaves the tiles as they were (A16.21)', async () => {
      const c2 = onStep(6);
      c2.setState({ wizAssets: [{ kind: 'Photo', name: 'Reception', id: 'as-1', source: 'asset' }] });
      record({ error: { code: 'BAD_REQUEST', message: 'caption is too long.' } }, 400);
      vi.stubGlobal('prompt', vi.fn().mockReturnValue('x'));
      await c2.wizardVals().uploads[0].describe();
      expect(c2.state.wizErr).toBe('caption is too long.');
      expect(c2.state.wizAssets).toEqual([{ kind: 'Photo', name: 'Reception', id: 'as-1', source: 'asset' }]);
      vi.unstubAllGlobals();
    });

    it('a document tile has no describe handler (photographs only, A16.21)', () => {
      const c2 = onStep(6);
      c2.setState({ wizAssets: [{ kind: 'PDF', name: 'Floor plan.pdf', id: 'd1' }] });
      expect(c2.wizardVals().uploads[0].describe).toBeNull();
    });

    it('a tile has no describe handler when there is no listing to save it to (A16.21)', () => {
      const c2: any = new Component({ listings: makeListingsAdapter() });
      c2.setState({
        auth: true, screen: 'seller', sellerView: 'wizard', step: 6, editingId: null,
        wizAssets: [{ kind: 'Photo', name: 'x', id: 'as-1', source: 'asset' }]
      });
      expect(c2.wizardVals().uploads[0].describe).toBeNull();
    });

    it('without an adapter the design\'s own fixture tiles carry no describe handler (A16.21)', () => {
      const plain: any = new Component({});
      plain.setState({ auth: true, screen: 'seller', sellerView: 'wizard', step: 6 });
      expect(plain.wizardVals().uploads[0].describe).toBeUndefined();
    });
  });
});

describe('A13 — the metro dropdown', () => {
  const MARKET_KEYS = ['Austin, TX', 'Sacramento, CA', 'Orlando, FL', 'Atlanta, GA'];
  // M4 (review, round 1): the cases below that arm real `document` listeners through
  // `componentDidMount`. Unmounting only on the happy path leaves a listener bound to a dead
  // component for the rest of the FILE the moment an assertion fails, so the teardown is
  // unconditional here. `componentWillUnmount` is a no-op on a component that never mounted.
  afterEach(() => { c.componentWillUnmount(); });

  it('starts closed, with the four markets and Austin selected', () => {
    const v = c.renderVals();
    expect(v.marketMenuOpen).toBe(false);
    expect(v.marketTriggerLabel).toBe('Austin, TX metro');
    expect(v.marketOptions.map((o: any) => o.label)).toEqual(MARKET_KEYS.map((m) => `${m} metro`));
    expect(v.marketOptions.map((o: any) => o.selected)).toEqual([true, false, false, false]);
    expect(v.marketCaretStyle).toContain('rotate(0deg)');
    expect(v.marketFieldStyle).toContain('border: 1px solid var(--border-subtle)');
  });

  it('the trigger opens the menu and seeds the highlight on the current market', () => {
    c.renderVals().toggleMarketMenu();
    expect(c.state.marketMenu).toBe(true);
    expect(c.state.marketMenuAt).toBe(0);
    const v = c.renderVals();
    expect(v.marketMenuOpen).toBe(true);
    expect(v.marketCaretStyle).toContain('rotate(180deg)');
    expect(v.marketFieldStyle).toContain('border: 1px solid var(--vf-accent)');
  });

  it('the trigger closes the menu again (the design\'s own toggle contract)', () => {
    c.renderVals().toggleMarketMenu();
    c.renderVals().toggleMarketMenu();
    expect(c.state.marketMenu).toBe(false);
  });

  it('ArrowDown opens a closed menu, then walks and wraps; ArrowUp wraps the other way', () => {
    const key = (k: string) => { const e = { key: k, preventDefault: vi.fn() }; c.renderVals().marketMenuKeys(e); return e; };
    expect(key('ArrowDown').preventDefault).toHaveBeenCalled();
    expect(c.state).toMatchObject({ marketMenu: true, marketMenuAt: 0 });
    key('ArrowDown'); expect(c.state.marketMenuAt).toBe(1);
    key('ArrowDown'); key('ArrowDown'); key('ArrowDown'); expect(c.state.marketMenuAt).toBe(0);
    key('ArrowUp'); expect(c.state.marketMenuAt).toBe(3);
  });

  it('Home and End jump to the ends, and do nothing while the menu is closed', () => {
    const key = (k: string) => { const e = { key: k, preventDefault: vi.fn() }; c.renderVals().marketMenuKeys(e); return e; };
    expect(key('End').preventDefault).not.toHaveBeenCalled();
    expect(c.state.marketMenu).toBeFalsy();
    c.renderVals().toggleMarketMenu();
    key('End'); expect(c.state.marketMenuAt).toBe(3);
    key('Home'); expect(c.state.marketMenuAt).toBe(0);
  });

  it('Enter chooses the highlighted market and leaves Space to the button while closed', () => {
    const key = (k: string) => { const e = { key: k, preventDefault: vi.fn() }; c.renderVals().marketMenuKeys(e); return e; };
    expect(key('Enter').preventDefault).not.toHaveBeenCalled();   // closed: the native click opens it
    expect(key('Tab').preventDefault).not.toHaveBeenCalled();     // an unhandled key is left alone
    c.renderVals().toggleMarketMenu();
    key('ArrowDown');
    // I1 (review, round 1): the Enter branch itself, on an OPEN menu — the path the ruling's
    // "normal dropdown" most obviously implies. Before this line `e.key === "Enter"` was only
    // ever evaluated false, because the two Enter presses above happen while the menu is closed.
    expect(key('Enter').preventDefault).toHaveBeenCalled();
    expect(c.state.market).toBe('Sacramento, CA');
    // Reopening seeds the highlight on the market just chosen, so Space takes that one — the same
    // branch, the other key. (The review's suggested second `ArrowDown` here would have walked on
    // to Orlando: `toggleMarketMenu` seeds from the CURRENT market, not from the top.)
    c.renderVals().toggleMarketMenu();
    expect(c.state.marketMenuAt).toBe(1);
    expect(key(' ').preventDefault).toHaveBeenCalled();
    expect(c.state.market).toBe('Sacramento, CA');
  });

  it('choosing an option calls setMarket with the SAME payload the <select> produced', () => {
    vi.useFakeTimers();
    c.renderVals().toggleMarketMenu();
    c.renderVals().marketOptions[2].go();
    expect(c.state).toMatchObject({
      market: 'Orlando, FL', activeId: null, hoverId: null, loading: true,
      marketMenu: false, marketMenuAt: -1
    });
    vi.advanceTimersByTime(320);
    expect(c.state.loading).toBe(false);
    vi.useRealTimers();
    // the map, the rail and the pins all read `market` — the contract the <select> had
    expect(c.renderVals().mapCenter).toEqual([28.52, -81.36]);
    expect(c.renderVals().marketLabel).toBe('Orlando, FL metro · within 40 miles');
  });

  it('setMarket still accepts a change EVENT, the way setF does (V3:1907)', () => {
    c.setMarket({ target: { value: 'Atlanta, GA' } });
    expect(c.state.market).toBe('Atlanta, GA');
  });

  it('the selected row is accented, the highlighted row takes the design\'s hover grey, the rest are plain', () => {
    c.renderVals().toggleMarketMenu();
    c.setState({ marketMenuAt: 2 });
    const rows = c.renderVals().marketOptions;
    expect(rows[0].rowStyle).toContain('background: var(--vf-accent-bg)');
    expect(rows[0].rowStyle).toContain('font-weight: 800');
    expect(rows[2].rowStyle).toContain('background: var(--vf-neutral)');
    expect(rows[1].rowStyle).toContain('background: none');
    expect(rows[0].tickStyle).toContain('opacity: 1');
    expect(rows[1].tickStyle).toContain('opacity: 0');
  });

  it('Escape closes the menu; a keydown that is not Escape, and a keydown while closed, do not', () => {
    c.componentDidMount();
    c.renderVals().toggleMarketMenu();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }));
    expect(c.state.marketMenu).toBe(true);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(c.state).toMatchObject({ marketMenu: false, marketMenuAt: -1 });
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));  // no-op, and no throw
    expect(c.state.marketMenu).toBe(false);
    c.componentWillUnmount();
  });

  it('a pointerdown outside closes the menu; one inside the field does not', () => {
    const host = document.createElement('div');
    const inside = document.createElement('button');
    host.appendChild(inside);
    document.body.appendChild(host);
    try {
      c.componentDidMount();
      c.renderVals().marketMenuRef(host);
      // M3 (review, round 1): a pointerdown while the menu is CLOSED takes the handler's own
      // early exit — the branch nothing reached before.
      document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
      expect(c.state.marketMenu).toBeFalsy();
      c.renderVals().toggleMarketMenu();
      inside.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
      expect(c.state.marketMenu).toBe(true);
      document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
      expect(c.state).toMatchObject({ marketMenu: false, marketMenuAt: -1 });
      // …and with no node recorded yet, an outside click still closes rather than throwing
      c.renderVals().marketMenuRef(null);
      c.renderVals().toggleMarketMenu();
      document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
      expect(c.state.marketMenu).toBe(false);
    } finally {
      host.remove();
    }
  });

  it('componentWillUnmount removes both document listeners it added', () => {
    const add = vi.spyOn(document, 'addEventListener');
    const remove = vi.spyOn(document, 'removeEventListener');
    c.componentDidMount();
    c.componentWillUnmount();
    expect(add.mock.calls.filter(([t]) => t === 'pointerdown' || t === 'keydown')).toHaveLength(2);
    expect(remove.mock.calls.filter(([t]) => t === 'pointerdown' || t === 'keydown')).toHaveLength(2);
    add.mockRestore();
    remove.mockRestore();
  });

  it('the orphaned setMarket render key is gone (the dead-code rule, A2.3/A2.5)', () => {
    expect(c.renderVals().setMarket, 'nothing in the template reads it once the <select> goes').toBeUndefined();
    expect(typeof c.setMarket, 'it lives on the class now, beside setF').toBe('function');
  });

  // I2 (review, round 1; ruled A13.6/A13.7): the two render-value orphans the <select> left
  // behind, deleted under the same dead-code rule A2.2–A2.5 applied to the `browseSel` helpers.
  it('the orphaned `market` render key and the option rows\' orphaned `v` are gone (A13.6/A13.7)', () => {
    const v = c.renderVals();
    expect(v.market, '`{{ market }}` left the template with the <select>').toBeUndefined();
    for (const o of v.marketOptions) {
      expect(o.v, 'the rows read label/selected/go/rowStyle/tickStyle/optId, never v').toBeUndefined();
    }
    // …and what the rows DO read is all still there.
    expect(Object.keys(v.marketOptions[0]).sort()).toEqual(['go', 'label', 'optId', 'rowStyle', 'selected', 'tickStyle']);
  });

  // I3 (review, round 1, ruled): the highlight has to be announceable and visible once the
  // seeded metro list is longer than the panel (Q5). Every row carries an id, the listbox names
  // the highlighted one, and moving the highlight scrolls that row into view.
  it('aria-activedescendant follows the arrow-key highlight', () => {
    const key = (k: string) => { c.renderVals().marketMenuKeys({ key: k, preventDefault: vi.fn() }); };
    // Round 3: the attribute moved to the TRIGGER, which is rendered on every Browse screen — so
    // while the menu is shut it must name nothing at all, rather than the "market-opt--1" that a
    // closed `marketMenuAt` of -1 would spell. Null, so React and Vue both omit the attribute.
    expect(c.renderVals().marketActiveId, 'a closed menu has no active descendant').toBeNull();
    c.renderVals().toggleMarketMenu();
    expect(c.renderVals().marketOptions.map((o: any) => o.optId))
      .toEqual(['market-opt-0', 'market-opt-1', 'market-opt-2', 'market-opt-3']);
    expect(c.renderVals().marketActiveId).toBe('market-opt-0');
    key('ArrowDown');
    expect(c.renderVals().marketActiveId).toBe('market-opt-1');
    key('End');
    expect(c.renderVals().marketActiveId).toBe('market-opt-3');
    key('Home');
    expect(c.renderVals().marketActiveId).toBe('market-opt-0');
  });

  it('moving the highlight scrolls the highlighted row into view, and copes when it is not in the DOM', () => {
    // m5 (final review, ruled): the rows are resolved through the field the component recorded,
    // so they have to hang off it here rather than off the document.
    const host = document.createElement('div');
    document.body.appendChild(host);
    const rows = MARKET_KEYS.map((_, i) => {
      const b = document.createElement('button');
      b.id = `market-opt-${i}`;
      (b as any).scrollIntoView = vi.fn();       // jsdom implements no scrollIntoView of its own
      host.appendChild(b);
      return b;
    });
    try {
      const key = (k: string) => { c.renderVals().marketMenuKeys({ key: k, preventDefault: vi.fn() }); };
      c.renderVals().marketMenuRef(host);
      c.renderVals().toggleMarketMenu();
      key('ArrowDown');
      expect((rows[1] as any).scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' });
      key('End');
      expect((rows[3] as any).scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' });
      // a row that cannot scroll is left alone rather than thrown at…
      delete (rows[0] as any).scrollIntoView;
      key('Home');
      expect(c.state.marketMenuAt).toBe(0);
    } finally {
      rows.forEach((b) => b.remove());
      host.remove();
    }
    // …and so is a highlight whose row is not in the document at all (the app before first paint)
    const c2: any = new Component({});
    c2.renderVals().toggleMarketMenu();
    c2.renderVals().marketMenuKeys({ key: 'ArrowDown', preventDefault: vi.fn() });
    expect(c2.state.marketMenuAt).toBe(1);
  });

  // N3 (re-review, ruled): OPENING has to scroll too. `toggleMarketMenu` and the
  // Arrow-on-a-closed-menu branch seed the highlight while the panel is still unrendered, so
  // there is no row to scroll to yet; the scroll therefore hangs off the panel's own mount —
  // the design's own callback-ref idiom (`md.compareMenuRef`) — and runs on both targets at the
  // moment the rows exist. Without it, a seeded market list longer than the panel opens scrolled
  // to the top with the active row off-screen, which is the Q5 case I3 exists for.
  it('opening the menu scrolls the highlighted row into view', () => {
    const host = document.createElement('div');
    document.body.appendChild(host);
    const rows = MARKET_KEYS.map((_, i) => {
      const b = document.createElement('button');
      b.id = `market-opt-${i}`;
      (b as any).scrollIntoView = vi.fn();
      host.appendChild(b);
      return b;
    });
    const panel = document.createElement('div');
    host.appendChild(panel);
    try {
      c.renderVals().marketMenuRef(host);
      c.setState({ market: 'Orlando, FL' });              // index 2 — a non-zero highlight
      c.renderVals().toggleMarketMenu();
      expect(c.state.marketMenuAt).toBe(2);
      c.renderVals().marketPanelRef(panel);               // the panel mounts, and the rows exist
      expect((rows[2] as any).scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' });
      expect((rows[0] as any).scrollIntoView).not.toHaveBeenCalled();
      // unmount hands the ref null, which must not scroll anything or throw
      c.renderVals().marketPanelRef(null);
      expect((rows[2] as any).scrollIntoView).toHaveBeenCalledTimes(1);
    } finally {
      rows.forEach((b) => b.remove());
      panel.remove();
      host.remove();
    }
  });

  // m5 (final review, ruled): `market-opt-N` is an id this component mints, and it is looked up
  // inside the field the component recorded — not across the whole document. There is one Browse
  // toolbar today, so `document.getElementById` was right today; the neighbouring code
  // (`this._marketMenuEl`, `this._giveMenuEl`, `setMarket`'s own `host.querySelector`) is scoped,
  // and a second instance or a panel caught mid-transition is the case that made it wrong.
  it('the scroll is scoped to the metro field: a row of the same id elsewhere is left alone', () => {
    const host = document.createElement('div');
    const stray = document.createElement('button');
    stray.id = 'market-opt-1';
    (stray as any).scrollIntoView = vi.fn();
    document.body.append(host, stray);
    try {
      c.renderVals().marketMenuRef(host);
      c.renderVals().toggleMarketMenu();
      c.renderVals().marketMenuKeys({ key: 'ArrowDown', preventDefault: vi.fn() });
      expect(c.state.marketMenuAt, 'the highlight still moves').toBe(1);
      expect((stray as any).scrollIntoView,
        'a row outside the field the component recorded is not this menu\'s row').not.toHaveBeenCalled();
    } finally {
      host.remove();
      stray.remove();
    }
  });

  // m4 (final review, ruled): Tab is the third way out of a dropdown the keyboard can now enter,
  // and A14.7 gave the Give menu exactly this on exactly this reasoning — two dropdowns shipping
  // in one branch with different dismissal sets is the inconsistency the whole-branch review
  // exists to catch. `relatedTarget` is where focus is GOING: anywhere inside the field (the
  // trigger, another row) is a move within the control, and `null` is the browser leaving the
  // document altogether — a window blur, which must close nothing.
  it('Tab out of the menu closes it; moving focus within the field, or out of the document, does not', () => {
    const host = document.createElement('div');
    const trigger = document.createElement('button');
    const row = document.createElement('button');
    host.append(trigger, row);
    const outside = document.createElement('button');
    document.body.append(host, outside);
    try {
      c.componentDidMount();
      c.renderVals().marketMenuRef(host);
      // Closed: the handler's own early exit.
      row.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: outside }));
      expect(c.state.marketMenu).toBeFalsy();
      c.renderVals().toggleMarketMenu();
      row.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: trigger }));
      expect(c.state.marketMenu, 'a move within the control is not a dismissal').toBe(true);
      row.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: null }));
      expect(c.state.marketMenu, 'the window losing focus must not close the menu').toBe(true);
      row.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: outside }));
      expect(c.state).toMatchObject({ marketMenu: false, marketMenuAt: -1 });
      // …and with no field recorded, a focusout out of the control still closes rather than throwing.
      c.renderVals().marketMenuRef(null);
      c.renderVals().toggleMarketMenu();
      row.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: outside }));
      expect(c.state.marketMenu).toBe(false);
    } finally {
      host.remove();
      outside.remove();
    }
  });

  // Round 4 (ruled): a choice unmounts the row the pointer or the keyboard was on, and without
  // this focus lands on <body> — a keyboard user is dropped out of the control they were driving.
  // A native <select> leaves focus on itself; so does the design's own listbox, whose rows sit
  // inside the trigger's own card. Focus goes back to the trigger, whichever way the choice came.
  describe('focus returns to the trigger after a choice', () => {
    const field = () => {
      const host = document.createElement('div');
      const trigger = document.createElement('button');
      trigger.setAttribute('aria-haspopup', 'listbox');
      host.appendChild(trigger);
      document.body.appendChild(host);
      const spy = vi.spyOn(trigger, 'focus');
      return { host, trigger, spy };
    };

    it('after a mouse choice on an option row', () => {
      const { host, spy } = field();
      try {
        c.renderVals().marketMenuRef(host);
        c.renderVals().toggleMarketMenu();
        c.renderVals().marketOptions[2].go();
        expect(c.state.market).toBe('Orlando, FL');
        expect(spy, 'the row it was on has just been unmounted').toHaveBeenCalled();
      } finally {
        host.remove();
      }
    });

    it('after Enter on the keyboard', () => {
      const { host, spy } = field();
      try {
        c.renderVals().marketMenuRef(host);
        c.renderVals().toggleMarketMenu();
        c.renderVals().marketMenuKeys({ key: 'ArrowDown', preventDefault: vi.fn() });
        c.renderVals().marketMenuKeys({ key: 'Enter', preventDefault: vi.fn() });
        expect(c.state.market).toBe('Sacramento, CA');
        expect(spy).toHaveBeenCalled();
      } finally {
        host.remove();
      }
    });

    it('and copes with no field recorded, and with a field that holds no trigger', () => {
      c.renderVals().marketOptions[1].go();                 // no ref yet — must not throw
      expect(c.state.market).toBe('Sacramento, CA');
      const bare = document.createElement('div');
      document.body.appendChild(bare);
      try {
        c.renderVals().marketMenuRef(bare);
        c.renderVals().marketOptions[3].go();
        expect(c.state.market).toBe('Atlanta, GA');
      } finally {
        bare.remove();
      }
    });
  });

  // M2 (review, round 1, ruled): `Object.keys(MARKETS).indexOf(s.market)` is -1 whenever the
  // current market is not one MARKETS holds — the shape Seed Listings can produce, since
  // `applyListings` DELETES a market with no listings left (`listings/load.ts`). Unclamped,
  // opening the menu seeded `marketMenuAt: -1` and Enter/Space then called `setMarket(keys[-1])`,
  // i.e. `setMarket(undefined)`.
  //
  // The handlers are taken from a render made while the market was still valid, and the market is
  // moved afterwards: that is the real sequence (the fixtures render, then the API's rows replace
  // MARKETS in place), and it is also the only way to reach the branch — `renderVals()` reads
  // `MARKETS[s.market || "Austin, TX"].center` on every render, so a re-render with an unknown
  // market throws there long before the highlight is computed. See the report's Q5 note.
  it('a market MARKETS no longer holds clamps the highlight to the first row', () => {
    const v = c.renderVals();
    c.setState({ market: 'Nowhere, ZZ' });
    v.toggleMarketMenu();
    expect(c.state.marketMenuAt, 'indexOf returned -1 and was not clamped').toBe(0);
    v.marketMenuKeys({ key: 'Enter', preventDefault: vi.fn() });
    expect(c.state.market, 'setMarket(keys[-1]) === setMarket(undefined)').toBe('Austin, TX');
  });

  it('ArrowUp with a market MARKETS no longer holds starts from the first row too', () => {
    const v = c.renderVals();
    c.setState({ market: 'Nowhere, ZZ' });
    v.marketMenuKeys({ key: 'ArrowUp', preventDefault: vi.fn() });   // opens, seeds the highlight
    expect(c.state).toMatchObject({ marketMenu: true, marketMenuAt: 0 });
    v.marketMenuKeys({ key: 'ArrowUp', preventDefault: vi.fn() });   // …then wraps to the end
    expect(c.state.marketMenuAt).toBe(3);
  });
});

// ---------------------------------------------------------------------------------------
// A14 — the header's Give button IS vinfoundation.org's Give dropdown (John, 2026-09-08:
// "the Give button must be identical to the https://vinfoundation.org/ where the button is an
// actual drop down (match button design pixel-by-pixel)"). Every literal asserted below was
// measured on the live site on 2026-09-08; the plan's measurement table names the stylesheet and
// the selector each one came from. The three mechanisms the live site has NO counterpart for —
// Escape, outside-click and Arrow/Home/End movement — are John's ruling, not measurement, and are
// characterised here branch by branch exactly as A13's are.
// ---------------------------------------------------------------------------------------
describe('A14 — the Give dropdown', () => {
  // A13's rule, for A13's reason: three cases below arm real `document` listeners through
  // `componentDidMount`, and a failed assertion would otherwise leave one bound to a dead
  // component for the rest of the file. `componentWillUnmount` is a no-op if nothing mounted.
  afterEach(() => { c.componentWillUnmount(); });

  /** The four links, wired to real anchors, so `giveFocus` has something to move focus between. */
  const rowEls = () => {
    const els = [0, 1, 2, 3].map(() => {
      const a = document.createElement('a');
      a.href = '#';
      document.body.appendChild(a);
      return a;
    });
    c.renderVals().giveLinks.forEach((g: any, i: number) => g.ref(els[i]));
    return els;
  };
  const prevent = () => { /* the handlers call it; nothing here needs to observe it */ };

  it('starts closed, and the trigger carries the live pill in its idle colours', () => {
    const v = c.renderVals();
    expect(v.giveMenuOpen).toBe(false);
    expect(v.giveButtonStyle).toContain('background: #339dde');
    expect(v.giveButtonStyle).toContain('border-radius: 10px');
    expect(v.giveButtonStyle).toContain('padding: 2px 22px');
    expect(v.giveButtonStyle).toContain('font-size: 18px');
    expect(v.giveButtonStyle).toContain('line-height: 24.3px');
    // John's ruling: Montserrat 600, self-hosted, scoped to this control and its menu.
    expect(v.giveButtonStyle).toContain("font-family: 'Montserrat', var(--rf-display)");
    expect(v.giveButtonStyle).toContain('font-weight: 600');
    // Closed, the underline is scaled to the hover variable, which is unset until :hover.
    expect(v.giveUnderlineStyle).toContain('transform: scaleX(var(--rf-give-underline, 0))');
    expect(v.giveUnderlineStyle).toContain('top: calc(100% + 4.34px)');
    expect(v.giveUnderlineStyle).toContain('height: 3px');
    expect(v.giveUnderlineStyle).toContain('background: #339dde');
  });

  it('the trigger opens and closes it, and opening closes the other two header menus', () => {
    c.setState({ auth: true, screen: 'browse', navMenu: true, userMenu: true });
    c.renderVals().toggleGiveMenu();
    expect(c.state).toMatchObject({ giveMenu: true, navMenu: false, userMenu: false });
    const open = c.renderVals();
    expect(open.giveMenuOpen).toBe(true);
    expect(open.giveButtonStyle).toContain('background: #07386f');   // the live hover/open navy
    expect(open.giveUnderlineStyle).toContain('transform: scaleX(1)');
    open.toggleGiveMenu();
    expect(c.state.giveMenu).toBe(false);
  });

  it('carries John\'s four links, in his order, with his hrefs and no target', () => {
    const rows = c.renderVals().giveLinks;
    expect(rows.map((g: any) => g.label)).toEqual(['Annual Fund', 'Cor Group', 'Legacy Giving', 'Dr. Sophia Yin Memorial Fund']);
    expect(rows.map((g: any) => g.href)).toEqual([
      'https://vinfoundation.org/give/',
      'https://vinfoundation.org/cor/',
      'https://vinfoundation.org/legacy-giving/',
      'https://vinfoundation.org/resources/dr-sophia-yin-memorial-fund/'
    ]);
    for (const g of rows) {
      expect(g.rowStyle).toContain('font-size: 14px');
      expect(g.rowStyle).toContain('padding: 8px 20px');
      expect(g.rowStyle).toContain('border-left: 8px solid transparent');
      expect(g.rowStyle).toContain('color: #07386f');
      expect(g.rowStyle).toContain("font-family: 'Montserrat', var(--rf-display)");
      expect(g.rowStyle).toContain('text-decoration: none');   // beats the design's own a:hover underline
    }
    // The rows carry exactly what the markup reads — no orphan keys (the A2.3/A13.6 rule).
    expect(Object.keys(rows[0]).sort()).toEqual(['href', 'keys', 'label', 'pick', 'ref', 'rowStyle']);
  });

  it('choosing a link closes the menu', () => {
    c.setState({ giveMenu: true });
    c.renderVals().giveLinks[2].pick();
    expect(c.state.giveMenu).toBe(false);
  });

  it('Escape closes it and returns focus to the trigger; Escape while closed is a no-op', () => {
    const btn = document.createElement('button');
    document.body.appendChild(btn);
    try {
      c.componentDidMount();
      c.renderVals().giveButtonRef(btn);
      c.setState({ giveMenu: true });
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
      expect(c.state.giveMenu).toBe(false);
      expect(document.activeElement).toBe(btn);
      btn.blur();
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));   // no-op, no throw
      expect(c.state.giveMenu).toBe(false);
      // A non-Escape key never closes anything.
      c.setState({ giveMenu: true });
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }));
      expect(c.state.giveMenu).toBe(true);
      // …and with no trigger recorded, Escape still closes rather than throwing.
      c.renderVals().giveButtonRef(null);
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
      expect(c.state.giveMenu).toBe(false);
    } finally {
      btn.remove();
    }
  });

  it('a pointerdown outside closes it; one inside the wrapper does not', () => {
    const host = document.createElement('div');
    const inside = document.createElement('a');
    host.appendChild(inside);
    document.body.appendChild(host);
    try {
      c.componentDidMount();
      c.renderVals().giveMenuRef(host);
      // The closed menu takes the handler's own early exit — the branch nothing else reaches.
      document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
      expect(c.state.giveMenu).toBeFalsy();
      c.setState({ giveMenu: true });
      inside.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
      expect(c.state.giveMenu, 'a click inside the menu must not dismiss it').toBe(true);
      document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
      expect(c.state.giveMenu).toBe(false);
      // …and with no wrapper recorded, an outside click still closes rather than throwing.
      c.renderVals().giveMenuRef(null);
      c.setState({ giveMenu: true });
      document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
      expect(c.state.giveMenu).toBe(false);
    } finally {
      host.remove();
    }
  });

  // C1 (review round 1, ruled). The app's `setState` runs its callback SYNCHRONOUSLY
  // (`dc-logic.js`: `Object.assign(this.state, next); if (typeof cb === "function") cb();`) and
  // Vue re-renders in a later microtask, so an ArrowDown that opened the menu and then focused a
  // row inside the callback found `sc-if` unmounted, no row refs called, and focus left on the
  // trigger — while the REFERENCE's React `setState` fires post-commit and worked. Two runtimes,
  // two behaviours, and no gate can see it: the 45 states are captured by mouse and `screens.ts`
  // presses no keys. The fix is A13's own mount-ref idiom (`marketPanelRef`, its round 5): the
  // keys seed a PENDING index and the panel's callback ref spends it when the elements exist.
  //
  // So this case must not pre-wire the refs. It reproduces the app's real order — the handler
  // first, against nothing, then the rows arriving, then the panel mounting — and it is the order
  // that makes it RED against the code before the fix.
  it('ArrowDown from the trigger opens it on the first link, ArrowUp on the last — at panel mount, not at keypress', () => {
    const panel = document.createElement('div');
    document.body.appendChild(panel);
    const els = [0, 1, 2, 3].map(() => { const a = document.createElement('a'); a.href = '#'; document.body.appendChild(a); return a; });
    try {
      // 1. the keypress, with the menu shut and NOT ONE row rendered — the app's real state here
      c.renderVals().giveMenuKeys({ key: 'ArrowDown', preventDefault: prevent });
      expect(c.state.giveMenu, 'the menu opens on the keypress, as before').toBe(true);
      expect(document.activeElement, 'there is nothing to focus yet — the panel has not mounted').not.toBe(els[0]);
      // 2. Vue commits: the rows' refs run, then the panel's (children before parent, both
      //    runtimes), and THAT is when the pending index is spent.
      c.renderVals().giveLinks.forEach((g: any, i: number) => g.ref(els[i]));
      c.renderVals().givePanelRef(panel);
      expect(document.activeElement, 'ArrowDown opens on the first link').toBe(els[0]);
      // 3. the same for ArrowUp, which opens on the LAST link
      c.setState({ giveMenu: false });
      c.renderVals().giveLinks.forEach((g: any) => g.ref(null));
      c.renderVals().giveMenuKeys({ key: 'ArrowUp', preventDefault: prevent });
      expect(document.activeElement, 'still nothing to focus').not.toBe(els[3]);
      c.renderVals().giveLinks.forEach((g: any, i: number) => g.ref(els[i]));
      c.renderVals().givePanelRef(panel);
      expect(document.activeElement, 'ArrowUp opens on the last link').toBe(els[3]);
      // A key that is neither arrow leaves it alone (Enter/Space is the button's own click).
      c.setState({ giveMenu: false });
      c.renderVals().giveMenuKeys({ key: 'Enter', preventDefault: prevent });
      expect(c.state.giveMenu).toBe(false);
      // Already open, the panel already mounted: the arrows move focus there and then.
      c.setState({ giveMenu: true });
      els[3].focus();
      c.renderVals().giveMenuKeys({ key: 'ArrowDown', preventDefault: prevent });
      expect(document.activeElement).toBe(els[0]);
    } finally {
      els.forEach((e) => e.remove());
      panel.remove();
    }
  });

  // The other half of C1: the pending index is the KEYBOARD's, so a menu opened with the mouse
  // must mount with focus left exactly where the pointer put it. A ref that focused on every
  // mount would drag a mouse user into the list, and would re-steal focus on every re-render
  // while the menu is open.
  it('a mouse-opened menu does not steal focus when the panel mounts, and the ref is spent once', () => {
    const panel = document.createElement('div');
    document.body.appendChild(panel);
    const els = rowEls();
    const outside = document.createElement('button');
    document.body.appendChild(outside);
    try {
      outside.focus();
      c.renderVals().toggleGiveMenu();
      c.renderVals().givePanelRef(panel);
      expect(document.activeElement, 'a click opened it — focus belongs to the pointer').toBe(outside);
      // …and a keyboard open is spent exactly once: a re-render's second ref call is inert.
      c.setState({ giveMenu: false });
      c.renderVals().giveMenuKeys({ key: 'ArrowDown', preventDefault: prevent });
      c.renderVals().givePanelRef(panel);
      expect(document.activeElement).toBe(els[0]);
      outside.focus();
      c.renderVals().givePanelRef(panel);
      expect(document.activeElement, 'the pending index was spent on the first mount').toBe(outside);
      // Unmount hands the ref null, which must not focus anything or throw.
      els[0].blur();
      c.renderVals().givePanelRef(null);
      expect(document.activeElement).toBe(outside);
      // …and a stale index cannot survive into a later MOUSE open: an arrow that opened the menu
      // and was then dismissed before the panel ever mounted leaves an index nothing spent.
      c.setState({ giveMenu: false });
      c.renderVals().giveMenuKeys({ key: 'ArrowUp', preventDefault: prevent });   // opens, seeds an index
      expect(c.state.giveMenuAt, 'the arrow seeded a pending index the panel never spent').toBe(-1);
      c.renderVals().toggleGiveMenu();                                            // shut with the pointer
      c.renderVals().toggleGiveMenu();                                            // re-opened with the pointer
      outside.focus();
      c.renderVals().givePanelRef(panel);
      expect(document.activeElement, 'a pointer open must never inherit a keyboard\'s pending index').toBe(outside);
    } finally {
      els.forEach((e) => e.remove());
      outside.remove();
      panel.remove();
    }
  });

  it('opening from the trigger closes the other two header menus too', () => {
    const els = rowEls();
    try {
      c.setState({ auth: true, screen: 'browse', navMenu: true, userMenu: true });
      c.renderVals().giveMenuKeys({ key: 'ArrowDown', preventDefault: prevent });
      expect(c.state).toMatchObject({ giveMenu: true, navMenu: false, userMenu: false });
    } finally {
      els.forEach((e) => e.remove());
    }
  });

  it('the arrows wrap at both ends inside the menu, and Home/End jump', () => {
    const els = rowEls();
    try {
      const rows = c.renderVals().giveLinks;
      rows.forEach((g: any, i: number) => g.ref(els[i]));
      rows[3].keys({ key: 'ArrowDown', preventDefault: prevent });
      expect(document.activeElement, 'past the last link, focus wraps to the first').toBe(els[0]);
      rows[0].keys({ key: 'ArrowUp', preventDefault: prevent });
      expect(document.activeElement, 'before the first link, focus wraps to the last').toBe(els[3]);
      rows[2].keys({ key: 'End', preventDefault: prevent });
      expect(document.activeElement).toBe(els[3]);
      rows[2].keys({ key: 'Home', preventDefault: prevent });
      expect(document.activeElement).toBe(els[0]);
      rows[1].keys({ key: 'x', preventDefault: prevent });
      expect(document.activeElement, 'an unhandled key changes nothing').toBe(els[0]);
      // A detached row (Vue has unmounted the menu) is skipped rather than focused…
      rows.forEach((g: any) => g.ref(null));
      rows[0].keys({ key: 'ArrowDown', preventDefault: prevent });   // no throw
      expect(document.activeElement).toBe(els[0]);
    } finally {
      els.forEach((e) => e.remove());
    }
    // …and so is a component whose rows have never been rendered at all.
    const fresh: any = new Component({});
    fresh.renderVals().giveLinks[0].keys({ key: 'Home', preventDefault: prevent });   // no throw
    expect(fresh.state.giveMenu).toBeFalsy();
  });

  // m2 (review round 1, ruled). Escape and outside-click were the two dismissals John's ruling
  // named; Tab is the third way out of a menu a keyboard can now enter, and without this it left
  // the panel open behind the focus ring. `relatedTarget` is where focus is GOING: anywhere inside
  // the wrapper — the trigger, another row — is a move within the control, and `null` is the
  // browser leaving the document altogether, which is not a dismissal either.
  it('Tab out of the menu closes it; moving focus within the control, or out of the document, does not', () => {
    const host = document.createElement('div');
    const trigger = document.createElement('button');
    const row = document.createElement('a');
    row.href = '#';
    host.append(trigger, row);
    const outside = document.createElement('button');
    document.body.append(host, outside);
    try {
      c.componentDidMount();
      c.renderVals().giveMenuRef(host);
      // Closed: the handler's own early exit.
      row.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: outside }));
      expect(c.state.giveMenu).toBeFalsy();
      // Open, and focus moves from a row to the trigger — still inside the control.
      c.setState({ giveMenu: true });
      row.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: trigger }));
      expect(c.state.giveMenu, 'a move within the control is not a dismissal').toBe(true);
      // Focus leaving the document entirely (relatedTarget null) is not a dismissal either.
      row.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: null }));
      expect(c.state.giveMenu, 'the window losing focus must not close the menu').toBe(true);
      // Tab out: focus lands on something outside the wrapper.
      row.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: outside }));
      expect(c.state.giveMenu).toBe(false);
      // …and with no wrapper recorded, a focusout out of the control still closes rather than throwing.
      c.renderVals().giveMenuRef(null);
      c.setState({ giveMenu: true });
      row.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: outside }));
      expect(c.state.giveMenu).toBe(false);
    } finally {
      host.remove();
      outside.remove();
    }
  });

  it('componentWillUnmount removes all three document listeners trackMenuDismiss added', () => {
    const add = vi.spyOn(document, 'addEventListener');
    const remove = vi.spyOn(document, 'removeEventListener');
    c.componentDidMount();
    c.componentWillUnmount();
    const kinds = (calls: unknown[][]) => calls.map(([t]) => t).filter((t) => t === 'pointerdown' || t === 'keydown' || t === 'focusout').sort();
    expect(kinds(add.mock.calls)).toEqual(['focusout', 'keydown', 'pointerdown']);
    expect(kinds(remove.mock.calls)).toEqual(['focusout', 'keydown', 'pointerdown']);
    add.mockRestore();
    remove.mockRestore();
  });

  // m6 (final review, ruled): Home and End moved the highlight on the metro trigger and inside
  // the Give menu, but not on the Give TRIGGER — the one element a keyboard user starts from.
  // They behave as they do on the metro trigger: only while the menu is open, because with it
  // shut there is no list for an end to be an end of.
  it('Home and End work on the Give trigger, as they do on the metro trigger, and only while open', () => {
    const els = rowEls();
    try {
      c.renderVals().giveMenuKeys({ key: 'Home', preventDefault: prevent });
      expect(c.state.giveMenu, 'a shut menu is not opened by Home').toBeFalsy();
      expect(document.activeElement, 'and focus has not moved into it').not.toBe(els[0]);
      c.setState({ giveMenu: true });
      c.renderVals().giveMenuKeys({ key: 'End', preventDefault: prevent });
      expect(document.activeElement, 'End on the trigger goes to the last link').toBe(els[3]);
      c.renderVals().giveMenuKeys({ key: 'Home', preventDefault: prevent });
      expect(document.activeElement, 'Home on the trigger goes back to the first').toBe(els[0]);
    } finally {
      els.forEach((e) => e.remove());
    }
  });

  // m7 (final review, ruled): "opening me closes you" was one-directional. `toggleGiveMenu` and
  // the arrow-open cleared the other two header menus; nothing cleared Give, and neither Give nor
  // the metro listbox cleared the other. The global `pointerdown` and `focusout` listeners covered
  // a pointer and a Tab, but a pure-keyboard user could hold two menus open at once and then shut
  // both with one Escape. The toggles enforce the invariant themselves now, in both directions.
  it('opening any other menu closes Give, and opening Give closes the metro listbox too', () => {
    c.setState({ auth: true, screen: 'browse', giveMenu: true });
    c.renderVals().toggleNavMenu();
    expect(c.state.giveMenu, 'the nav menu closes Give').toBe(false);
    c.setState({ giveMenu: true, navMenu: false });
    c.renderVals().toggleUserMenu();
    expect(c.state.giveMenu, 'the account menu closes Give').toBe(false);
    c.setState({ giveMenu: true, userMenu: false });
    c.renderVals().toggleMarketMenu();
    expect(c.state.giveMenu, 'the metro listbox closes Give').toBe(false);
    // …and the other way: Give closes the metro listbox as well as the two header menus, by the
    // pointer path and by the arrow-key path, which are the two ways into it.
    c.setState({ marketMenu: true, marketMenuAt: 2, navMenu: true, userMenu: true, giveMenu: false });
    c.renderVals().toggleGiveMenu();
    expect(c.state).toMatchObject({ giveMenu: true, marketMenu: false, marketMenuAt: -1, navMenu: false, userMenu: false });
    c.setState({ giveMenu: false, marketMenu: true, marketMenuAt: 2, navMenu: true, userMenu: true });
    c.renderVals().giveMenuKeys({ key: 'ArrowDown', preventDefault: prevent });
    expect(c.state).toMatchObject({ giveMenu: true, marketMenu: false, marketMenuAt: -1, navMenu: false, userMenu: false });
  });

  it('A13\'s metro dismissals are unchanged by A14\'s branches', () => {
    // The two closures are shared. A Give branch that is inert while `giveMenu` is falsy must
    // leave the metro menu's Escape and outside-click behaving exactly as A13 left them.
    c.componentDidMount();
    c.setState({ marketMenu: true, marketMenuAt: 2, giveMenu: false });
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(c.state).toMatchObject({ marketMenu: false, marketMenuAt: -1 });
    c.setState({ marketMenu: true, marketMenuAt: 2 });
    document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
    expect(c.state).toMatchObject({ marketMenu: false, marketMenuAt: -1 });
  });
});

// ---------------------------------------------------------------------------------------
// A19 — the photo lightbox (John, 2026-09-09: "the images/photos should be clickable and they
// expand and have < > to view all images larger with simple X to close"). The design shows a
// photograph at 168 px in the detail grid and at 232 px in the Browse docked panel and enlarges
// neither. The lightbox is composed from the interest modal's scrim, the panel's own prev/next
// arrows, its close button and its two pills; every branch of the state machine is new and
// every branch is covered here. `p2` (Round Rock) is the design's own three-photograph fixture.
// ---------------------------------------------------------------------------------------
describe('A19 — the photo lightbox', () => {
  afterEach(() => { c.componentWillUnmount(); });

  const P2 = { pid: 'p2', at: 'ph-p2-exterior' };
  /** A mounted, focusable stand-in for a tile's hit-target — what `closeLightbox` hands focus back to. */
  const opener = () => { const b = document.createElement('button'); document.body.appendChild(b); return b; };
  /** Round Rock's tiles, through the detail's own render values. */
  const p2Photos = () => { c.setState({ detailId: 'p2' }); return c.renderVals().d.photos; };

  it('starts closed and exposes nothing the template would render (A19.1/A19.3)', () => {
    expect(c.state).toMatchObject({ lightbox: null, lightboxFocus: false });
    const lb = c.renderVals().lightbox;
    expect(lb).toMatchObject({ open: false, src: '', caption: '', counter: '', label: '', multiple: false });
    // No orphan keys (the A2.3/A13.6 dead-code rule): every key has a reader in A19.8's block.
    expect(Object.keys(lb).sort()).toEqual(['backdrop', 'caption', 'close', 'counter', 'label', 'multiple', 'next', 'open', 'prev', 'ref', 'src']);
  });

  it('a filled tile carries an opener and its own label; an empty tile carries neither (A19.4)', () => {
    const photos = p2Photos();
    expect(photos.map((ph: any) => typeof ph.open)).toEqual(['function', 'function', 'function', 'undefined', 'undefined', 'undefined']);
    expect(photos[0].openLabel).toBe('Expand photo: Exterior — street view');
    expect(photos[1].openLabel).toBe('Expand photo: Exterior — side elevation');
    // The empty tile is the design's own object, untouched.
    expect(Object.keys(photos[3]).sort()).toEqual(['caption', 'hasSrc', 'id', 'index', 'noSrc', 'placeholder', 'src']);
    // Cedar Park (p1), the `detail` state's listing, has no photograph and therefore no hit-target —
    // which is why that frozen baseline cannot move.
    c.setState({ detailId: 'p1' });
    expect(c.renderVals().d.photos.every((ph: any) => ph.open === undefined && ph.openLabel === undefined)).toBe(true);
  });

  it('opening records the opener, names the photograph and closes the three header menus — not the metro one (A19.2)', () => {
    const btn = opener();
    try {
      c.setState({ navMenu: true, userMenu: true, giveMenu: true, marketMenu: true, marketMenuAt: 1 });
      p2Photos()[1].open({ currentTarget: btn });
      expect(c.state).toMatchObject({ lightbox: { pid: 'p2', at: 'ph-p2-exterior2' }, lightboxFocus: true, navMenu: false, userMenu: false, giveMenu: false });
      // The metro listbox is shut by its own pointerdown/focusout closures before a tile click can
      // land, so `openLightbox` does not name it — which is what keeps design-amendments.test.ts's
      // "exactly six sites" pin on `marketMenu: false, marketMenuAt: -1` true.
      expect(c.state).toMatchObject({ marketMenu: true, marketMenuAt: 1 });
      expect(c._lightboxOpener).toBe(btn);
      expect(c.renderVals().lightbox).toMatchObject({
        open: true, src: '/assets/photos/round-rock-exterior-side.webp', caption: 'Exterior — side elevation',
        counter: '2/3', label: 'Photograph 2 of 3', multiple: true
      });
    } finally { btn.remove(); }
  });

  it('the docked panel opens the photograph its carousel is showing, so "N of M" equals its counter (A19.5)', () => {
    c.setState({ screen: 'browse', mdSel: 'p2', mdPhoto: 2 });
    const photos = c.renderVals().md.panel.photos;
    expect(photos.counter).toBe('3/3');
    expect(photos.openLabel).toBe('Expand photo: Exterior — parking and signage');
    photos.open(undefined);
    expect(c.state.lightbox).toEqual({ pid: 'p2', at: 'ph-p2-exterior3' });
    expect(c.renderVals().lightbox.label).toBe('Photograph 3 of 3');
    // Cedar Park has no photograph: `hasAny` is false, so the template mounts no hit-target there.
    c.setState({ mdSel: 'p1', mdPhoto: 0 });
    expect(c.renderVals().md.panel.photos.hasAny).toBe(false);
  });

  it('stepping wraps at both ends; a slot id the set no longer carries reads as the first (A19.2)', () => {
    c.setState({ lightbox: P2 });
    const step = (d: number) => { c.stepLightbox(d); return c.state.lightbox.at; };
    expect(step(1)).toBe('ph-p2-exterior2');
    expect(step(1)).toBe('ph-p2-exterior3');
    expect(step(1), 'past the last photograph, wraps to the first').toBe('ph-p2-exterior');
    expect(step(-1), 'before the first, wraps to the last').toBe('ph-p2-exterior3');
    c.setState({ lightbox: { pid: 'p2', at: 'ph-p2-gone' } });
    expect(c.renderVals().lightbox.label).toBe('Photograph 1 of 3');
    expect(step(1)).toBe('ph-p2-exterior2');
  });

  it('one photograph never steps and hides the arrows; nothing open never steps (A19.2)', () => {
    const one = { id: 'lb-one', area: 'Elgin', type: 'Small animal', photos: ['/api/listings/lb/photos/1'] };
    (P as unknown as Array<{ id: string }>).push(one);
    try {
      c.setState({ lightbox: { pid: 'lb-one', at: 'ph-lb-one-exterior' } });
      expect(c.renderVals().lightbox).toMatchObject({ open: true, multiple: false, counter: '1/1', label: 'Photograph 1 of 1' });
      c.stepLightbox(1);
      expect(c.state.lightbox.at).toBe('ph-lb-one-exterior');
      c.setState({ lightbox: null });
      c.stepLightbox(1);
      expect(c.state.lightbox).toBeNull();
    } finally {
      const fixtures = P as unknown as Array<{ id: string }>;
      fixtures.splice(fixtures.findIndex((x) => x.id === 'lb-one'), 1);   // structural restore (N1)
    }
  });

  it('a lightbox that names a listing with no photograph, or no listing, renders nothing (A19.2)', () => {
    c.setState({ lightbox: { pid: 'p1', at: 'ph-p1-exterior' } });
    expect(c.renderVals().lightbox.open).toBe(false);
    expect(c.lightboxPhotos()).toEqual([]);
    c.setState({ lightbox: { pid: 'no-such-listing', at: 'x' } });
    expect(c.lightboxPhotos()).toEqual([]);
  });

  it('closing clears the state and returns focus to the opener; with no opener recorded it just closes (A19.2)', () => {
    const btn = opener();
    try {
      p2Photos()[0].open({ currentTarget: btn });
      c.renderVals().lightbox.close();
      expect(c.state).toMatchObject({ lightbox: null, lightboxFocus: false });
      expect(document.activeElement).toBe(btn);
      expect(c._lightboxOpener).toBeNull();
      btn.blur();
      p2Photos()[0].open(undefined);          // no event, no opener
      expect(c._lightboxOpener).toBeNull();
      c.closeLightbox();                       // no throw; focus is left where it was
      expect(c.state.lightbox).toBeNull();
      expect(document.activeElement).not.toBe(btn);
    } finally { btn.remove(); }
  });

  it('the mount ref spends lightboxFocus exactly once, one macrotask deferred, and a Next or Prev re-render must not re-steal focus (A19.2)', () => {
    // Live-browser finding (Step 10): Chromium silently drops a focus() call made synchronously
    // while a just-mounted node has not yet had layout/style committed — the JSDOM unit
    // environment has no such restriction, so only a real Chromium run surfaces it. Deferred one
    // macrotask, the design's own setTimeout idiom (2 pristine uses). This deferral is the
    // mount-ref's own (A19.2, a just-mounted node) and is unaffected by A-LB3, which removed the
    // DIFFERENT setTimeout A19.10 once carried — deferring focus back INTO an already-mounted
    // dialog from a focusout, which does not hold in real Chromium for the reason characterised
    // below.
    vi.useFakeTimers();
    const box = document.createElement('div'); box.tabIndex = -1; document.body.appendChild(box);
    try {
      p2Photos()[0].open(undefined);
      c.renderVals().lightbox.ref(box);
      expect(c.state.lightboxFocus, 'the flag is spent synchronously; only the focus() call is deferred').toBe(false);
      expect(c._lightboxEl).toBe(box);
      expect(document.activeElement, 'not yet — the focus() call is queued, not run').not.toBe(box);
      vi.advanceTimersByTime(0);
      expect(document.activeElement).toBe(box);
      box.blur();
      // Both runtimes call the OLD ref with null and the NEW one with the element on every render
      // (renderVals mints a new function each pass): the handle follows, the focus does not.
      c.renderVals().lightbox.ref(null);
      expect(c._lightboxEl).toBeNull();
      c.renderVals().lightbox.ref(box);
      expect(c._lightboxEl).toBe(box);
      vi.advanceTimersByTime(0);
      expect(document.activeElement).not.toBe(box);
    } finally { box.remove(); vi.useRealTimers(); }
  });

  it('the backdrop closes only when the click lands on the scrim itself (A19.2)', () => {
    const scrim = document.createElement('div'); const inner = document.createElement('img');
    c.setState({ lightbox: P2 });
    c.renderVals().lightbox.backdrop({ target: inner, currentTarget: scrim });
    expect(c.state.lightbox, 'a click on the photograph or inside the dialog must not close it').toEqual(P2);
    c.renderVals().lightbox.backdrop({ target: scrim, currentTarget: scrim });
    expect(c.state.lightbox).toBeNull();
  });

  it('Escape closes and ArrowLeft/ArrowRight step through the armed document listener; other keys are not swallowed (A19.9)', () => {
    const btn = opener();
    try {
      c.componentDidMount();
      p2Photos()[0].open({ currentTarget: btn });
      const press = (key: string) => { const e = new KeyboardEvent('keydown', { key, cancelable: true }); document.dispatchEvent(e); return e.defaultPrevented; };
      expect(press('ArrowRight')).toBe(true);
      expect(c.state.lightbox.at).toBe('ph-p2-exterior2');
      expect(press('ArrowLeft')).toBe(true);
      expect(c.state.lightbox.at).toBe('ph-p2-exterior');
      expect(press('a')).toBe(false);
      expect(c.state.lightbox).toEqual(P2);
      expect(press('Escape')).toBe(true);
      expect(c.state.lightbox).toBeNull();
      expect(document.activeElement).toBe(btn);
      c.componentWillUnmount();
    } finally { btn.remove(); }
  });

  it('Tab from the last control wraps to the first; Shift+Tab from the first, or from the container itself, wraps to the last (A-LB3, A19.9)', () => {
    // A-LB3: the focusout-based trap (A19.10) did not hold in real Chromium — a null
    // relatedTarget cannot tell "the window blurred" from "focus left the dialog's own tabbable
    // set". Tab is handled here instead, deterministically, by DOM position: no timer, no
    // relatedTarget, one code path for both directions.
    const box = document.createElement('div'); box.tabIndex = -1;
    const closeBtn = document.createElement('button'); closeBtn.setAttribute('aria-label', 'Close photo');
    const prevBtn = document.createElement('button'); prevBtn.setAttribute('aria-label', 'Previous photo');
    const nextBtn = document.createElement('button'); nextBtn.setAttribute('aria-label', 'Next photo');
    box.append(closeBtn, prevBtn, nextBtn);
    document.body.appendChild(box);
    const press = (shiftKey = false) => { const e = new KeyboardEvent('keydown', { key: 'Tab', shiftKey, cancelable: true }); document.dispatchEvent(e); return e.defaultPrevented; };
    try {
      c.componentDidMount();
      c.setState({ lightbox: P2 });
      c._lightboxEl = box;

      // The container case: right after opening, focus is on the dialog itself (the mount-ref
      // idiom) — Shift+Tab from there must reach the LAST control directly.
      box.focus();
      expect(press(true)).toBe(true);
      expect(document.activeElement).toBe(nextBtn);

      // Forward: last control wraps to the first.
      nextBtn.focus();
      expect(press()).toBe(true);
      expect(document.activeElement).toBe(closeBtn);

      // Backward: first control wraps to the last.
      closeBtn.focus();
      expect(press(true)).toBe(true);
      expect(document.activeElement).toBe(nextBtn);

      // A move in the middle of the cycle is not intercepted — no preventDefault, no forced
      // focus — so the browser's own default Tab action is left alone.
      prevBtn.focus();
      expect(press()).toBe(false);
      expect(press(true)).toBe(false);

      c.componentWillUnmount();
    } finally { box.remove(); }
  });

  it('with one photograph, Tab and Shift+Tab both keep focus on the sole control (Close) (A-LB3, A19.9)', () => {
    const one = { id: 'lb-one', area: 'Elgin', type: 'Small animal', photos: ['/api/listings/lb/photos/1'] };
    (P as unknown as Array<{ id: string }>).push(one);
    const box = document.createElement('div'); box.tabIndex = -1;
    const closeBtn = document.createElement('button'); closeBtn.setAttribute('aria-label', 'Close photo');
    box.appendChild(closeBtn);
    document.body.appendChild(box);
    const press = (shiftKey = false) => { const e = new KeyboardEvent('keydown', { key: 'Tab', shiftKey, cancelable: true }); document.dispatchEvent(e); return e.defaultPrevented; };
    try {
      c.componentDidMount();
      c.setState({ lightbox: { pid: 'lb-one', at: 'ph-lb-one-exterior' } });
      c._lightboxEl = box;
      closeBtn.focus();
      expect(press()).toBe(true);
      expect(document.activeElement).toBe(closeBtn);
      expect(press(true)).toBe(true);
      expect(document.activeElement).toBe(closeBtn);
      c.componentWillUnmount();
    } finally {
      box.remove();
      const fixtures = P as unknown as Array<{ id: string }>;
      fixtures.splice(fixtures.findIndex((x) => x.id === 'lb-one'), 1);   // structural restore (N1)
    }
  });

  it('Tab does nothing while the lightbox is closed, and nothing if no dialog element is mounted yet (A-LB3, A19.9)', () => {
    const press = (shiftKey = false) => { const e = new KeyboardEvent('keydown', { key: 'Tab', shiftKey, cancelable: true }); document.dispatchEvent(e); return e.defaultPrevented; };
    c.componentDidMount();
    expect(c.state.lightbox).toBeNull();
    expect(press()).toBe(false);
    c.setState({ lightbox: P2 });
    expect(c._lightboxEl).toBeFalsy();   // no ref has run yet
    expect(press()).toBe(false);
    c.componentWillUnmount();
  });

  it('with the lightbox closed, A13\'s and A14\'s dismissals are unchanged by A19\'s branches (A19.9)', () => {
    c.componentDidMount();
    c.setState({ marketMenu: true, marketMenuAt: 2, giveMenu: true, lightbox: null });
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
    expect(c.state).toMatchObject({ marketMenu: true, marketMenuAt: 2, giveMenu: true });   // arrows mean nothing while closed
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(c.state).toMatchObject({ marketMenu: false, marketMenuAt: -1, giveMenu: false });
    const give = document.createElement('div'); const away = document.createElement('button');
    document.body.append(give, away);
    try {
      c.renderVals().giveMenuRef(give);
      c.setState({ giveMenu: true });
      give.dispatchEvent(new FocusEvent('focusout', { relatedTarget: away, bubbles: true }));
      expect(c.state.giveMenu, 'Tab out of the Give menu still closes it').toBe(false);
    } finally { give.remove(); away.remove(); }
    c.componentWillUnmount();
  });

  it('the focusout closure no longer treats an open lightbox specially — A19.10\'s trap is removed (A-LB3)', () => {
    // A-LB3 (2026-09-09, ruling on fix round 1's NEEDS_CONTEXT): the focusout-based trap this
    // test used to characterise (deferring `box.focus()` one macrotask whenever a non-null
    // `relatedTarget` left the dialog) was found not to hold in real Chromium and is removed
    // entirely — a null `relatedTarget` cannot distinguish "the window blurred" from "focus left
    // the dialog's own tabbable set", and no threshold fixes that. Tab is instead handled
    // deterministically in the keydown closure (A19.9, characterised above). This closure is now
    // A13.8's own output, unchanged, whether the lightbox is open or not.
    const box = document.createElement('div'); box.tabIndex = -1;
    const inside = document.createElement('button'); box.appendChild(inside);
    const away = document.createElement('button');
    document.body.append(box, away);
    try {
      c.componentDidMount();
      c.setState({ lightbox: P2 });
      c.renderVals().lightbox.ref(box);
      inside.focus();
      inside.dispatchEvent(new FocusEvent('focusout', { relatedTarget: away, bubbles: true }));
      // No pull-back, deferred or otherwise: the removed trap must not intervene.
      expect(document.activeElement, 'the removed focusout trap must not pull focus back into the dialog').not.toBe(box);
      expect(c.state.lightbox, 'a focusout must not close the lightbox either — only Escape/backdrop/X do that').toEqual(P2);
      // The give/market dismissal logic A13.8/A14.7 own is untouched by A19 either way, and now
      // runs unconditionally on every focusout — lightbox open or not — exactly as it did before
      // A19 ever existed: no early return gates it on `this.state.lightbox` any more.
      c.setState({ giveMenu: true });
      const give = document.createElement('div');
      document.body.appendChild(give);
      try {
        c.renderVals().giveMenuRef(give);
        inside.dispatchEvent(new FocusEvent('focusout', { relatedTarget: away, bubbles: true }));
        expect(c.state.giveMenu, 'the Give dismissal runs even with the lightbox open now — A13.8\'s own behaviour, restored').toBe(false);
      } finally { give.remove(); }
      c.componentWillUnmount();
    } finally { box.remove(); away.remove(); }
  });

  it('go() and signOut clear it — a screen change closes the lightbox (A19.11/A19.12)', async () => {
    c.setState({ auth: true, lightbox: P2, lightboxFocus: true });
    c.go('browse')();
    expect(c.state).toMatchObject({ screen: 'browse', lightbox: null, lightboxFocus: false });
    c.setState({ lightbox: P2, lightboxFocus: true });
    await c.renderVals().signOut();
    expect(c.state).toMatchObject({ screen: 'gate', auth: false, lightbox: null, lightboxFocus: false });
  });

  it('componentWillUnmount still removes the three document listeners — A19 added none', () => {
    const add = vi.spyOn(document, 'addEventListener');
    const remove = vi.spyOn(document, 'removeEventListener');
    c.componentDidMount();
    c.componentWillUnmount();
    const ours = (calls: unknown[][]) => calls.filter(([t]) => t === 'pointerdown' || t === 'keydown' || t === 'focusout');
    expect(ours(add.mock.calls)).toHaveLength(3);
    expect(ours(remove.mock.calls)).toHaveLength(3);
    add.mockRestore(); remove.mockRestore();
  });

  // A21.3d — the detail's Growth row splits the API string to extract the vintage
  describe('Growth row string splitting (A21.3d, Task B8)', () => {
    it('extracts percentage and vintage from growth strings', () => {
      const originalGrowth = P[0].growth;
      c.setState({ auth: true, detailId: 'p1' });
      const testCases = [
        { growth: '+14.2% since 2015', expectedValue: '+14.2%', expectedSub: 'Since 2015' },
        { growth: '+11.6% since 2018', expectedValue: '+11.6%', expectedSub: 'Since 2018' },
        { growth: null, expectedValue: '', expectedSub: '' },
        { growth: '+9%', expectedValue: '+9%', expectedSub: '' },
      ];

      for (const testCase of testCases) {
        (P[0] as any).growth = testCase.growth;
        c.setState({ detailId: 'p1' });
        const detail = c.detail.call(c);
        const growthRow = detail.demo.find((row: any) => row.k === 'Growth');
        expect(growthRow.v, `Growth value for "${testCase.growth}"`).toBe(testCase.expectedValue);
        expect(growthRow.sub, `Growth sub for "${testCase.growth}"`).toBe(testCase.expectedSub);
      }
      (P[0] as any).growth = originalGrowth;
    });
  });
});

// ---------------------------------------------------------------------------------------
// A23 — collapsing the Market data card closes both its menus (John, 2026-09-10, Task MD1:
// "the collapse widget top left expand/collapse is disconnected to the drop down").
//
// Exactly ONE of the card's two menus escaped the collapse, and it is the one John reported:
// the layer menu's panel (App.vue:475-476) is `position: absolute; left: 16px; top: 118px;
// z-index: 620` and sits OUTSIDE both of the card's `v-if="v.md?.legendOpen"` templates
// (:382-410 and :413-472, the card div closing at :411), so nothing unmounted it. The
// comparison listbox never floated: its panel (:434-435) is nested inside the second
// `legendOpen` template in normal flow (`margin-top: 6px`) and has always unmounted with the
// card. `mdCompareMenu` is cleared all the same, for a weaker and different reason — a menu
// left open in state reappears already-open when the card is expanded again, which is its own
// surprise.
//
// The one edit is `toggleLegend`'s single `setState`, and it clears UNCONDITIONALLY: the same
// call runs on expand as on collapse. The four quadrants below — {menu open, menu closed} ×
// {collapsing, expanding} — are one `it` each, because Vitest abandons an `it` at its first
// failed expect and cases sharing an `it` are unreachable under any single mutation.
// ---------------------------------------------------------------------------------------
describe('A23 — the Market data card collapse closes its menus (Task MD1)', () => {
  /** The card's own render values, read AFTER the state under test is in place: `toggleLegend`
   *  closes over the `s` of the `renderVals()` call that produced it. */
  const md = () => {
    c.setState({ auth: true, screen: 'browse', mdValue: 'income' });
    return c.renderVals().md;
  };

  // Quadrant 1 — a menu is open and the card is EXPANDED; collapsing must clear it. This is the
  // defect John reported, and the layer menu is the one that actually floated.
  it('both menus open, card expanded → collapsing clears both (A23, quadrant 1)', () => {
    c.setState({ mdLegendOff: false, mdLayerMenu: true, mdCompareMenu: true });
    md().toggleLegend();
    expect(c.state).toMatchObject({ mdLegendOff: true, mdLayerMenu: false, mdCompareMenu: false });
  });

  it('only the layer menu open, card expanded → collapsing clears it (A23, quadrant 1)', () => {
    c.setState({ mdLegendOff: false, mdLayerMenu: true, mdCompareMenu: false });
    md().toggleLegend();
    expect(c.state).toMatchObject({ mdLegendOff: true, mdLayerMenu: false, mdCompareMenu: false });
  });

  it('only the compare menu open, card expanded → collapsing clears it (A23, quadrant 1)', () => {
    c.setState({ mdLegendOff: false, mdLayerMenu: false, mdCompareMenu: true });
    md().toggleLegend();
    expect(c.state).toMatchObject({ mdLegendOff: true, mdLayerMenu: false, mdCompareMenu: false });
  });

  // Quadrant 2 — both menus closed and the card COLLAPSED; expanding must not resurrect either.
  it('both menus closed, card collapsed → expanding opens neither (A23, quadrant 2)', () => {
    c.setState({ mdLegendOff: true, mdLayerMenu: false, mdCompareMenu: false });
    md().toggleLegend();
    expect(c.state).toMatchObject({ mdLegendOff: false, mdLayerMenu: false, mdCompareMenu: false });
  });

  // Quadrant 3 — a menu is open and the card is COLLAPSED; expanding must clear it too. Nothing
  // else pins this: a narrower implementation that clears on collapse only —
  // `mdLayerMenu: s.mdLegendOff === true ? s.mdLayerMenu : false` — passes every quadrant above.
  // The clear is unconditional, and this is the case that says so.
  it('a menu open, card collapsed → EXPANDING clears it as well: the clear is unconditional (A23, quadrant 3)', () => {
    c.setState({ mdLegendOff: true, mdLayerMenu: true, mdCompareMenu: true });
    md().toggleLegend();
    expect(c.state).toMatchObject({ mdLegendOff: false, mdLayerMenu: false, mdCompareMenu: false });
  });

  // Quadrant 4 — both menus closed and the card EXPANDED; collapsing must not open either. The
  // guard against `toggleLegend` copying `toggleLayerMenu`'s own idiom (logic.js:564,
  // `mdLayerMenu: !s.mdLayerMenu`) instead of clearing.
  it('both menus closed, card expanded → collapsing opens neither (A23, quadrant 4)', () => {
    c.setState({ mdLegendOff: false, mdLayerMenu: false, mdCompareMenu: false });
    md().toggleLegend();
    expect(c.state).toMatchObject({ mdLegendOff: true, mdLayerMenu: false, mdCompareMenu: false });
  });

  // The design's own way of closing each menu, unchanged by A23 and characterised here so the
  // amendment cannot quietly take it away. Note what is NOT here: neither menu has an Escape or
  // an outside-click dismissal. `trackMenuDismiss` (logic.js:228-286) reads only `state.giveMenu`,
  // `state.marketMenu` and `state.lightbox`, so A13's metro listbox and A14's Give menu have
  // those affordances and these two do not. That gap is real, OUT OF SCOPE for A23 and owed a
  // ruling from John — recorded at the end of the A-MD1 paragraph in
  // docs/superpowers/plans/2026-09-08-metro-dropdown.md.
  it('choosing a layer closes the layer menu (logic.js:580) — its only dismissal', () => {
    const v = md();
    v.toggleLayerMenu();
    expect(c.state.mdLayerMenu).toBe(true);
    c.renderVals().md.layerOptions[1].go();
    expect(c.state.mdLayerMenu).toBe(false);
  });

  it('choosing a comparison metric closes the compare menu (logic.js:626) — its only dismissal', () => {
    const v = md();
    v.toggleCompareMenu();
    expect(c.state.mdCompareMenu).toBe(true);
    c.renderVals().md.compareOptions[1].go();
    expect(c.state.mdCompareMenu).toBe(false);
  });
});

// ------------------------------------------------------------------------------------------
// Task B10 — the docked panel stops fabricating (D-C31), and the card says which area it
// describes (D-C32).
//
// F-9: these cases live HERE, in the characterisation suite, and their fixtures are
// `communities()`' OWN output rather than a hand-written object. The round before this one wrote
// `{ pop: 100000, …, econ_k: 500 }` for its "full figures" case — `marketPanel` reads `c.econ`,
// not `c.econ_k`, and never sees `pets` at all — so the "full" case exercised the same absent
// branches the "empty" one did and could not tell them apart.
//
// F-8: every case asserts the CONTENT of what is rendered, not the absence of a substring. A
// mutation probe on the previous round reverted all eleven guards one at a time and caught ten:
// the three `oppTiles` survived, because with the guard removed they read `Median` / `Flat` /
// `Lean` — no "undefined", no "NaN", and `on` false for all three, so every assertion still held.
// `toEqual(['', '', ''])` on the labels is what catches it.
// ------------------------------------------------------------------------------------------
describe('A21 — a figure the API does not have renders as nothing, never as zero (Task B10)', () => {
  const AUSTIN = 'Austin, TX';
  const austin = () => (P as unknown as Record<string, unknown>[]).filter((x) => x.market === AUSTIN && x.status === 'published');

  /** Run `body` with the four community strings and the two market-data figures REMOVED from
   *  `targets` — which is exactly the row `GET /api/listings` serves for a listing the Census
   *  cannot describe (six nulls, `community_label` null). Everything is put back afterwards, so
   *  the fixtures the rest of this file characterises are untouched. */
  function without(targets: Record<string, unknown>[], body: () => void): void {
    const vets = VETS as unknown as Record<string, number>;
    const econ = ECON_K as unknown as Record<string, number>;
    const saved = targets.map((t) => ({
      t, pop: t.pop, growth: t.growth, income: t.income, hh: t.hh,
      v: vets[t.id as string], e: econ[t.id as string]
    }));
    for (const t of targets) {
      t.pop = null; t.growth = null; t.income = null; t.hh = null;
      delete vets[t.id as string];
      delete econ[t.id as string];
    }
    try { body(); } finally {
      for (const s of saved) {
        s.t.pop = s.pop; s.t.growth = s.growth; s.t.income = s.income; s.t.hh = s.hh;
        if (s.v !== undefined) vets[s.t.id as string] = s.v;
        if (s.e !== undefined) econ[s.t.id as string] = s.e;
      }
    }
  }

  const commFor = (id: string) => c.communities().filter((x: any) => x.id === id)[0];
  const panelFor = (listing: any) => c.marketPanel(listing, commFor(listing.id), c.communities(), AUSTIN);

  // ---- F-1, the root cause -----------------------------------------------------------------

  it('communities() yields undefined — not 0 — for every figure the API did not send (A21.1c)', () => {
    const p = austin()[0];
    without([p], () => {
      const comm = commFor(p.id as string);
      expect(comm).toMatchObject({ id: p.id, name: p.area });
      for (const k of ['pop', 'hh', 'income', 'growth', 'pets', 'econ', 'vets']) {
        expect(comm[k], `communities().${k} for a listing with no figures`).toBeUndefined();
      }
    });
  });

  it('…and keeps every figure it did send, parsed exactly as the design parsed it', () => {
    const comm = commFor(austin()[0].id as string);
    for (const k of ['pop', 'hh', 'income', 'growth', 'pets', 'econ', 'vets']) {
      expect(typeof comm[k], `communities().${k} for a listing with figures`).toBe('number');
    }
    // The design's own arithmetic, unchanged: pets is 57 % of households, econ is thousands.
    expect(comm.pets).toBe(Math.round(comm.hh * 0.57));
  });

  // ---- F-2/F-3/F-8, the panel's Insights tab -----------------------------------------------

  it('the four overview tiles carry no value and no dangling unit (A21.2d, F-2)', () => {
    const p = austin()[0];
    without([p], () => {
      expect(panelFor(p).overviewTiles).toEqual([
        { v: undefined, k: 'Population', sub: undefined },
        { v: undefined, k: 'Households', sub: 'ACS 5-year' },
        { v: undefined, k: 'Median Income', sub: undefined },
        { v: undefined, k: 'Est. Pet Households', sub: 'derived estimate' }
      ]);
    });
  });

  it('…and carry the design’s own values and sub-lines when the figures are there', () => {
    const tiles = panelFor(austin()[0]).overviewTiles;
    expect(tiles.map((t: any) => t.k)).toEqual(['Population', 'Households', 'Median Income', 'Est. Pet Households']);
    for (const t of tiles) {
      expect(typeof t.v).toBe('string');
      expect(t.v).not.toContain('undefined');
      expect(t.v).not.toContain('NaN');
      expect(typeof t.sub).toBe('string');
    }
    expect(tiles[0].sub).toMatch(/^[+-]?\d+\.\d% \(5 yrs\)$/);
    expect(tiles[2].sub).toMatch(/^[+-]?\d+% vs US$/);
  });

  it('the competition row shows no count, no ratio, no verdict and NO BARS (A21.2c/f/j/m, F-3)', () => {
    const p = austin()[0];
    without([p], () => {
      const panel = panelFor(p);
      expect(panel.compEstab).toBeUndefined();
      expect(panel.compPer10k).toBeUndefined();
      expect(panel.compLevel).toBeUndefined();
      // Three bars painted at the floor are a reading, not an absence.
      expect(panel.compBars).toEqual([]);
    });
  });

  it('…and shows all three, with three bars, when the figures are there', () => {
    const panel = panelFor(austin()[0]);
    expect(panel.compEstab).toMatch(/^\d+$/);
    expect(panel.compPer10k).toMatch(/^\d+\.\d$/);
    expect(panel.compLevel).toMatch(/^(Low|Moderate|High) Competition$/);
    expect(panel.compBars).toHaveLength(3);
  });

  // F-8's own case: the guard the mutation probe could not catch. With A21.2e reverted these
  // three labels read 'Median', 'Flat' and 'Lean' — no "undefined", no "NaN", `on` false for all
  // three — so only an assertion on the CONTENT fails.
  it('the three opportunity tiles carry NO verdict — not "Median", not "Flat", not "Lean" (A21.2e)', () => {
    const p = austin()[0];
    without([p], () => {
      const tiles = panelFor(p).oppTiles;
      expect(tiles.map((t: any) => t.label)).toEqual(['', '', '']);
      expect(tiles.map((t: any) => t.sub)).toEqual(['Affluence', 'Population Growth', 'Sector Payroll']);
      // …and every one of them is drawn in the design's own "off" grey, not its navy.
      expect(tiles.map((t: any) => t.labelStyle.includes('#8d99a6'))).toEqual([true, true, true]);
    });
  });

  it('…and carry one of the design’s own verdicts when the figures are there', () => {
    const tiles = panelFor(austin()[0]).oppTiles;
    expect(tiles.map((t: any) => t.label)).toEqual([
      expect.stringMatching(/^(High|Above avg\.|Median)$/),
      expect.stringMatching(/^(Strong|Steady|Flat)$/),
      expect.stringMatching(/^(Strong|Typical|Lean)$/)
    ]);
  });

  it('the opportunity score is omitted entirely — a composite of unknowns is not a score (A21.2g/h/k/l)', () => {
    const p = austin()[0];
    without([p], () => {
      const panel = panelFor(p);
      expect(panel.score).toBeUndefined();
      expect(panel.scoreLabel).toBeUndefined();
      expect(panel.scoreRing).toBeUndefined();
    });
    const full = panelFor(austin()[0]);
    expect(full.score).toMatch(/^\d+$/);
    expect(full.scoreLabel).toMatch(/^(Attractive|Balanced|Challenging)$/);
    expect(full.scoreRing).toContain('conic-gradient');
  });

  it('nothing the panel renders is ever "undefined", "NaN" or a zeroed figure', () => {
    const p = austin()[0];
    without([p], () => {
      // The whole object, because these four can never be a static label of the design's own.
      const rendered = JSON.stringify(panelFor(p));
      for (const banned of ['undefined', 'NaN', '$0K', '0.0%', '% (5 yrs)', '% vs US']) {
        expect(rendered, `the panel renders "${banned}" for a listing with no figures`).not.toContain(banned);
      }
    });
  });

  it('…and no verdict of any kind reaches a field the panel INTERPOLATES', () => {
    const p = austin()[0];
    without([p], () => {
      const panel = panelFor(p);
      // Exactly the fields `App.vue` renders as data on the Insights tab. Static labels — the
      // tiles' `k`, the opportunity tiles' `sub`, the words "Median Income" among them — are not
      // in this list, which is why the previous round's whole-object substring scan was both a
      // false positive on "Median" and blind to the `oppTiles` verdicts it was written to catch.
      const interpolated = [
        ...panel.overviewTiles.flatMap((t: any) => [t.v, t.sub]),
        ...panel.oppTiles.map((t: any) => t.label),
        panel.compEstab, panel.compPer10k, panel.compLevel, panel.score, panel.scoreLabel
      ].filter((x: unknown) => x !== undefined && x !== '');
      // Two static sub-lines survive: they describe the SOURCE, not a figure.
      expect(interpolated).toEqual(['ACS 5-year', 'derived estimate']);
    });
  });

  // ---- F-4, the panel reaches the design's own unavailable card ----------------------------

  it('the panel reaches the design’s own "Community data unavailable" card (A21.4a, A-C31 (2))', () => {
    const p = austin()[0];
    without([p], () => {
      expect(panelFor(p).hasDemo).toBe(false);
      expect(panelFor(p).noDemo).toBe(true);
    });
    expect(panelFor(austin()[0]).hasDemo).toBe(true);
    expect(panelFor(austin()[0]).noDemo).toBe(false);
  });

  // ---- F-5, the card says which area it describes (D-C32) ----------------------------------

  it('the panel’s Insights heading KEEPS its name and the area goes to its own sub-line (A27.6, D-C42)', () => {
    const p = austin()[0];
    // A27.3 (D-C39): the default loses the parenthetical it could not support. The band is an
    // 8 km straight-line buffer, not a routed drive time, and this heading sat over PLACE-band
    // figures on all but one listing.
    //
    // A27.6 (D-C42, John, 2026-09-11): and the heading is now that default ALWAYS. A21.5a let
    // `communityLabel` REPLACE it, so on QA — where D-C38 gives 28 of 29 listings a label — the
    // words "Market Overview" appeared nowhere and A27.3's own correction was invisible. The
    // geography moves to a sub-line beneath the heading, which is what every other place on this
    // card already does with it (A21.5b, A21.5c, A27.1, A27.2).
    expect(panelFor(p).overviewTitle).toBe('Market Overview');
    expect(panelFor(p).hasOverviewScope).toBe(false);
    expect(panelFor(p).overviewScope).toBe('');
    (p as any).communityLabel = 'Within about 5 miles of the practice';
    try {
      expect(panelFor(p).overviewTitle, 'the label replaced the heading again').toBe('Market Overview');
      expect(panelFor(p).hasOverviewScope).toBe(true);
      expect(panelFor(p).overviewScope).toBe('Within about 5 miles of the practice');
    } finally { delete (p as any).communityLabel; }
  });

  it('the panel’s Population tile names the geography its GROWTH sub-line came from (A27.8, D-C48)', () => {
    // D-C48 (John, 2026-09-11, on the whole-branch review). A27.7 puts ONE geography sub-line
    // above the whole four-tile grid, and the Population tile's sub-line is not a population
    // figure at all — it is GROWTH, which is place-level (`serve.py`'s `growth_scope`) and reads
    // −1.5% for the whole of Dallas. So a city number sat under a caption describing a ring on
    // 28 of 29 QA listings: the defect D-C38 removed, one card over. John ruled it is named on
    // the tile, the way the detail card's own Growth tile already names it (A27.2).
    const p = austin()[0];
    // The design's own fixtures carry no `growthScope`, so the null branch is the design's own
    // sub-line byte for byte — which is what keeps every approved Browse state where it is.
    const withoutScope = panelFor(p).overviewTiles[0].sub;
    expect(withoutScope).toMatch(/^[+-]?\d+\.\d% \(5 yrs\)$/);
    const value = panelFor(p).overviewTiles[0].v;

    (p as any).growthScope = 'Dallas';
    try {
      expect(panelFor(p).overviewTiles[0].sub).toBe(withoutScope + ' \u00b7 Dallas');
      // The VALUE is the ring's population and is untouched: D-C48 labels the sub-line, it
      // changes no figure. And the three tiles the heading sub-line DOES describe keep theirs.
      expect(panelFor(p).overviewTiles[0].v).toBe(value);
      expect(panelFor(p).overviewTiles[1].sub).toBe('ACS 5-year');
      expect(panelFor(p).overviewTiles[3].sub).toBe('derived estimate');
    } finally { delete (p as any).growthScope; }
  });

  it('…and a Population tile with no growth figure names nothing, scope or no scope (A27.8)', () => {
    // A21.2d's own rule, which D-C48 must not weaken: no figure, no sub-line. A geography with
    // no number beside it is a caption for something that is not there.
    const p = austin()[0];
    (p as any).growthScope = 'Dallas';
    try {
      without([p], () => {
        expect(panelFor(p).overviewTiles[0].sub).toBe(undefined);
      });
    } finally { delete (p as any).growthScope; }
  });

  it('the detail’s Community Context names the area in all three places (A21.5b/c/d)', () => {
    const p = austin()[0];
    c.setState({ auth: true, detailId: p.id });
    const before = c.detail();
    expect(before.demo[0].sub).toBe('Community, 2023');
    expect(before.demo[3].sub).toBe('In the community');
    expect(before.demoScope).toBe('Figures describe the community around the practice, not the practice itself.');

    (p as any).communityLabel = 'Within about 5 miles of the practice';
    try {
      const after = c.detail();
      expect(after.demo[0].sub).toBe('Within about 5 miles of the practice');
      expect(after.demo[3].sub).toBe('Within about 5 miles of the practice');
      expect(after.demoScope).toBe('Figures describe the area within about 5 miles of the practice, not the practice itself.');
      // The Census attribution itself is legally load-bearing and is not part of this sentence.
      expect(after.demoScope).not.toContain('Census');
    } finally { delete (p as any).communityLabel; }
  });

  // ---- D-C38, per-figure geography: the two tiles A21.5b/c could not reach ------------------
  //
  // THE HONEST MEASURE, which these cases exist to hold: only THREE of the card's four tiles gain
  // neighbourhood detail. Population, Households and Median income follow the catchment; the
  // Growth tile keeps its city-or-county figure and gains an honest label and nothing else,
  // because `population_growth_pct` cannot vary below place-or-county until the 2010->2020 tract
  // crosswalk is loaded. Nothing here is "per-neighbourhood market data".

  it('the Growth tile names the geography its own figure was measured at (A27.2)', () => {
    const p = austin()[0];
    c.setState({ auth: true, detailId: p.id });
    // The design's own fixtures carry no `growthScope`, so the null branch is A21.3d's output
    // unchanged — which is what keeps `detail` on its frozen hash.
    expect(c.detail().demo[1].sub).toBe('Since 2015');
    // Read BEFORE the scope arrives. `expect(x).toBe(x)` was the assertion here and it compared
    // the post-change value with itself — a tautology no change to A27.2 could ever fail.
    const valueWithoutScope = c.detail().demo[1].v;

    // 'Dallas', the name TIGER itself gives (D-C41). The API composes no "City of " prefix, so a
    // fixture carrying one asserts a value the backend cannot emit.
    (p as any).growthScope = 'Dallas';
    try {
      expect(c.detail().demo[1].sub).toBe('Dallas \u00b7 since 2015');
      // The VALUE is untouched: D-C38 labels this figure, it does not change it.
      expect(c.detail().demo[1].v).toBe(valueWithoutScope);
    } finally { delete (p as any).growthScope; }
  });

  it('…and a growth figure with no vintage still names its geography, alone (A27.2)', () => {
    const p = austin()[0];
    const growth = (p as any).growth;
    c.setState({ auth: true, detailId: p.id });
    (p as any).growth = '+1.2%';
    try {
      // A21.3d renders "" for a figure that carries no " since " — the sub-line must not become
      // "Dallas · since " with nothing after it.
      expect(c.detail().demo[1].sub).toBe('');
      (p as any).growthScope = 'Orange County';
      expect(c.detail().demo[1].sub).toBe('Orange County');
      delete (p as any).growthScope;
    } finally { (p as any).growth = growth; }
  });

  it('the Median income tile carries the approximate qualifier when the API sends one (A27.1)', () => {
    const p = austin()[0];
    c.setState({ auth: true, detailId: p.id });
    expect(c.detail().demo[2].sub).toBe('Household, 2023');

    (p as any).incomeNote = 'Within about 5 miles of the practice \u00b7 approximate';
    try {
      expect(c.detail().demo[2].sub).toBe('Within about 5 miles of the practice \u00b7 approximate');
    } finally { delete (p as any).incomeNote; }
  });

  // ---- F-6, the Market data strip cards ----------------------------------------------------

  it('a strip card whose metro has no figure keeps its title, source and link and shows no value (A21.2n/o)', () => {
    c.setState({ auth: true, screen: 'browse', market: AUSTIN });
    without(austin(), () => {
      const cards = c.renderVals().md.stripCards;
      expect(cards.length).toBeGreaterThan(0);
      for (const card of cards) {
        expect(card.value, `${card.title} still prints a median of zeros`).toBeUndefined();
        expect(card.bars, `${card.title} still draws bars from zeros`).toEqual([]);
        expect(card.title.length).toBeGreaterThan(0);
        expect(card.src.length).toBeGreaterThan(0);
        expect(card.linkLabel.length).toBeGreaterThan(0);
        expect(card.valueNote).toBe('metro median');
      }
    });
  });

  it('…and prints the metro median over the DEFINED values only when some are missing', () => {
    c.setState({ auth: true, screen: 'browse', market: AUSTIN });
    const all = c.renderVals().md.stripCards;
    const households = all.filter((x: any) => x.title === 'Households')[0];
    const nine = austin();
    // Drop the two lowest-household communities: a median over nine becomes a median over seven,
    // and the old `num(raw)` coercion would instead have pushed two ZEROS to the bottom of the
    // sort and moved the median the other way.
    const byHh = nine.slice().sort((a, b) => Number(String(a.hh).replace(/[^0-9]/g, '')) - Number(String(b.hh).replace(/[^0-9]/g, '')));
    without(byHh.slice(0, 2), () => {
      const card = c.renderVals().md.stripCards.filter((x: any) => x.title === 'Households')[0];
      expect(card.bars, 'one bar per community that HAS the figure').toHaveLength(7);
      expect(card.value).not.toBe(households.value);
      expect(card.value).not.toContain('0K0');
    });
  });

  // ---- F-7, the Compare rows ---------------------------------------------------------------

  it('a compare row for a community with no figure carries no bar (A21.2p)', () => {
    c.setState({ auth: true, screen: 'browse', market: AUSTIN, mdValue: 'income', mdCompare: 'growth' });
    const before = c.renderVals().md.compareRows;
    expect(before.length).toBeGreaterThan(1);
    for (const r of before) {
      expect(r.aStyle).toContain('background:');
      expect(r.bStyle).toContain('background:');
    }
    const p = austin()[0];
    without([p], () => {
      const rows = c.renderVals().md.compareRows;
      const mine = rows.filter((r: any) => r.name === p.area)[0];
      expect(mine.aStyle, 'a minimum-width bar drawn from a zero implies a lowest reading').toBeUndefined();
      expect(mine.bStyle).toBeUndefined();
      // …and every other row is untouched.
      for (const r of rows.filter((x: any) => x.name !== p.area)) {
        expect(r.aStyle).toContain('background:');
        expect(r.bStyle).toContain('background:');
      }
    });
  });
});

// -------------------------------------------------------------------------------------------
// A25 — Task MP1. A published listing whose seller has not disclosed its location is served
// `lat: null, lng: null` (`app/api/listings.py`'s `serialise`; `location_disclosed` defaults
// FALSE in `migrations/016_listing.sql`, so the nulls are the default, not an edge case). It
// reached `engine.marker([p.lat, p.lng], …)` unguarded, and Leaflet 1.9.4's `toLatLng` returns
// `null` for `[null, null]` — the array branch is gated on `typeof a[0] !== 'object'` and
// `typeof null === 'object'` — so `Marker._latlng` was null and `_setPos` read `.lat` off it.
// One listing was enough: the `forEach` has no try/catch, so pin drawing stopped there for every
// later listing, and the poisoned layer re-threw from inside Leaflet's own event loop on every
// zoom pass.
//
// John's ruling: the listing KEEPS ITS PLACE in the results and does not get a pin. The four
// production edits, each named on the case that fails without it:
//   A25.1  `practices:` filters to listings with a finite point   (the pin list)
//   A25.2  `driveCenter` falls back to the metro centre           (the second leg into Leaflet)
//   A25.3  `communities:` filters the same way                    (the mosaic's own bbox)
//   A25.6  `showDrive` takes the same test                        (fix round 1: A25.2 restored
//          the else-branch, which made the drive-time ring paintable around the metro centre
//          for a listing whose seller withheld the location — a false statement, not an
//          omission. No point, no ring.)
// -------------------------------------------------------------------------------------------
describe('A25 — a listing with no coordinates keeps its place and gets no pin (Task MP1)', () => {
  const AUSTIN = 'Austin, TX';
  const austin = () => (P as unknown as Record<string, unknown>[]).filter((x) => x.market === AUSTIN && x.status === 'published');

  /** Run `body` with `targets`' coordinates set to `lat`/`lng` — the row `GET /api/listings`
   *  serves for a published listing whose location is undisclosed. Everything is put back
   *  afterwards, so the fixtures the rest of this file characterises are untouched. */
  function at(targets: Record<string, unknown>[], lat: unknown, lng: unknown, body: () => void): void {
    const saved = targets.map((t) => ({ t, lat: t.lat, lng: t.lng }));
    for (const t of targets) { t.lat = lat; t.lng = lng; }
    try { body(); } finally { for (const s of saved) { s.t.lat = s.lat; s.t.lng = s.lng; } }
  }

  it('A25.1 — the pin list drops it, and the rail, the count and the order keep it', () => {
    const p = austin()[0];
    const before = c.marketVals(c.filtered());
    at([p], null, null, () => {
      const md = c.marketVals(c.filtered());
      // The map skips it: not at [0, 0], not at the metro centre, not at all.
      expect(md.practices.map((x: any) => x.id)).not.toContain(p.id);
      expect(md.practices).toHaveLength(before.practices.length - 1);
      for (const pin of md.practices) {
        expect(Number.isFinite(pin.lat), `pin ${pin.id} carries a non-finite lat`).toBe(true);
        expect(Number.isFinite(pin.lng), `pin ${pin.id} carries a non-finite lng`).toBe(true);
      }
      // …and the rail does not: same rows, same order, same count, same headline.
      expect(md.mdResults.map((r: any) => r.name)).toEqual(before.mdResults.map((r: any) => r.name));
      expect(md.mdHeadline).toBe(before.mdHeadline);
      expect(md.showingLabel).toBe(before.showingLabel);
    });
  });

  it('A25.1 — a NaN or an undefined point is skipped too, not only a null', () => {
    const p = austin()[0];
    for (const [lat, lng] of [[NaN, NaN], [undefined, undefined], [30.5, null]] as [unknown, unknown][]) {
      at([p], lat, lng, () => {
        expect(c.marketVals(c.filtered()).practices.map((x: any) => x.id)).not.toContain(p.id);
      });
    }
  });

  it('A25.2 — driveCenter falls back to the metro centre when the selection has no point', () => {
    const p = austin()[0];
    at([p], null, null, () => {
      c.setState({ mdSel: p.id });
      const md = c.marketVals(c.filtered());
      expect(md.driveCenter).toEqual(MARKETS[AUSTIN].center);
      expect(md.driveCenter).not.toEqual([null, null]);
    });
  });

  it('A25.2 — …and is still the selection’s own point when it has one', () => {
    const p = austin()[0];
    c.setState({ mdSel: p.id });
    expect(c.marketVals(c.filtered()).driveCenter).toEqual([p.lat, p.lng]);
  });

  it('A25.3 — the map’s community list drops it, so the mosaic bbox stays the metro’s', () => {
    const p = austin()[0];
    const before = c.marketVals(c.filtered());
    const box = (comms: any[]) => [Math.min(...comms.map((x) => x.lat)), Math.max(...comms.map((x) => x.lat)),
      Math.min(...comms.map((x) => x.lng)), Math.max(...comms.map((x) => x.lng))];
    at([p], null, null, () => {
      const md = c.marketVals(c.filtered());
      expect(md.communities.map((x: any) => x.name)).not.toContain(p.area);
      expect(md.communities).toHaveLength(before.communities.length - 1);
      // `mosaicBbox` is Math.min/Math.max over these lats and lngs, and `null` coerces to 0:
      // one unlocated community stretched the metro box to the equator and the prime meridian,
      // which is 100 million mosaic cells — a hung tab, not a missing shape.
      const [minLat, maxLat, minLng, maxLng] = box(md.communities);
      expect(minLat).toBeGreaterThan(29); expect(maxLat).toBeLessThan(31);
      expect(minLng).toBeLessThan(-97); expect(maxLng).toBeLessThan(-97);
    });
  });

  it('A25.3 — …and the strip cards still count its figures, because a figure is not a point', () => {
    const p = austin()[0];
    const before = c.marketVals(c.filtered());
    at([p], null, null, () => {
      const md = c.marketVals(c.filtered());
      // The premise, asserted rather than assumed (fix round 1, Minor-3): the MAP's list really
      // did lose the unlocated community. Without this the case only discriminates because
      // dropping one of nine values happens to move a median.
      expect(md.communities.length, 'the map list did not shrink, so this control proves nothing')
        .toBeLessThan(c.communities().length);
      expect(md.stripCards.map((s: any) => s.value)).toEqual(before.stripCards.map((s: any) => s.value));
    });
  });

  // Fix round 1, Important-1 (controller ruling, 2026-09-10: "no point, no ring"). `showDrive` is
  // `!!sel` with no coordinate term, and `MarketMapView.vue:91` draws the C7 drive-time ring on
  // `showDrive && driveCenter`. Before A25.2 that path threw inside `L.circle([null, null])` and
  // no ring ever appeared; after it the else-branch became PAINTABLE, so selecting an unlocated
  // listing drew a dashed circle around the middle of Austin. That is worse than the missing pin
  // it replaced: a missing pin omits, a ring centred on a place the practice is not ASSERTS
  // something false. A25.6 gives `showDrive` the same finite-coordinate test the pin list uses.
  //
  // A28.1 (D-C44, 2026-09-11) moved that circle from 16 km to 8 km and changed nothing here: the
  // discriminator is the BOOLEAN, not the radius, so this case is as live after the ruling as
  // before it — verified by perturbation, `showDrive: !!sel` still fails it.
  it('A25.6 — no point, no ring: showDrive is false when the selection has no point', () => {
    const p = austin()[0];
    at([p], null, null, () => {
      c.setState({ mdSel: p.id });
      const md = c.marketVals(c.filtered());
      expect(md.showDrive, 'an 8 km drive-time ring was painted around the metro centre').toBe(false);
      // …and A25.2's fallback is still what it was: the ring is off, not aimed somewhere else.
      expect(md.driveCenter).toEqual(MARKETS[AUSTIN].center);
    });
  });

  it('A25.6 — …and a selection that HAS a point still gets its ring, on its own point', () => {
    const p = austin()[0];
    c.setState({ mdSel: p.id });
    const md = c.marketVals(c.filtered());
    expect(md.showDrive).toBe(true);
    expect(md.driveCenter).toEqual([p.lat, p.lng]);
  });

  // ---- the two panel defects closed in the same task ---------------------------------------

  it('A25.4 — the panel’s last-resort community renders nothing, never a zero (D-C31)', () => {
    const sel = austin()[0];
    // Reached with no community of its own AND an empty community list: the one place left in
    // the panel where a zero stood in for an absence.
    const panel = c.marketPanel(sel, null, [], AUSTIN);
    expect(panel.overviewTiles).toEqual([
      { v: undefined, k: 'Population', sub: undefined },
      { v: undefined, k: 'Households', sub: 'ACS 5-year' },
      { v: undefined, k: 'Median Income', sub: undefined },
      { v: undefined, k: 'Est. Pet Households', sub: 'derived estimate' }
    ]);
    expect(panel.compEstab).toBeUndefined();
    expect(panel.oppTiles.map((t: any) => t.label)).toEqual(['', '', '']);
  });

  it('A25.5 — the panel and the detail agree about p8, the design’s own unavailable fixture', () => {
    const p8 = (P as unknown as Record<string, unknown>[]).filter((x) => x.id === 'p8')[0];
    const comms = c.communities();
    const panel = c.marketPanel(p8, comms.filter((x: any) => x.id === 'p8')[0], comms, AUSTIN);
    c.setState({ detailId: 'p8' });
    const detail = c.detail();
    expect(detail.hasDemo, 'the design’s own fixture for "Community data unavailable"').toBe(false);
    expect(panel.hasDemo, 'the panel showed a full profile for the listing whose detail says the data is unavailable').toBe(detail.hasDemo);
    expect(panel.noDemo).toBe(detail.noDemo);
  });

  it('A25.5 — …and every other design fixture still shows its figures on both', () => {
    const comms = c.communities();
    for (const p of austin().filter((x) => x.id !== 'p8')) {
      const panel = c.marketPanel(p, comms.filter((x: any) => x.id === p.id)[0], comms, AUSTIN);
      expect(panel.hasDemo, `the panel hid ${p.id}'s figures`).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------------------
// A26 — the Browse filter bar's five native <select>s become in-design dropdowns (John,
// 2026-09-11: "the dropdown 'more filters' is correct implementation while everything else on
// the filter bar is implemented incorrectly and not using the site design, this must be
// corrected"). The SECOND report about this toolbar row: the metro picker immediately to their
// left was the first, fixed as A13, whose idiom this family reuses rather than inventing a
// second one.
//
// Where A13 converted ONE control, A26 converts five in one `.map()` body, so the unit under
// characterisation is the loop, not the instance: one state slot (`fMenu`/`fMenuAt`), one open
// path, one set of closures, five instances. The cases below are A13's own
// (logic.test.ts:2153-2573) applied to that shape, plus the two things multiplicity adds — that
// a highlight can never paint on a sibling, and that opening one instance closes the others.
// ---------------------------------------------------------------------------------------
describe('A26 — the Browse filter dropdowns', () => {
  const KEYS = ['type', 'price', 'revenue', 'doctors', 'building'];
  // A13's own unconditional teardown (M4, review round 1): the cases here arm real `document`
  // listeners through `componentDidMount`, and unmounting only on the happy path leaves one bound
  // to a dead component for the rest of the FILE the moment an assertion fails.
  afterEach(() => { c.componentWillUnmount(); });

  const filters = () => c.renderVals().filters;
  const byKey = (k: string) => filters()[KEYS.indexOf(k)];

  it('the five toolbar filters are dropdowns, closed, each labelled and showing its own choice', () => {
    const fl = filters();
    expect(fl).toHaveLength(5);
    expect(fl.map((f: any) => f.aria)).toEqual(['Practice type', 'Asking price', 'Gross revenue', 'Doctors', 'Property']);
    expect(fl.map((f: any) => f.open)).toEqual([false, false, false, false, false]);
    expect(fl.map((f: any) => f.triggerLabel)).toEqual([
      'Practice type: Any', 'Asking price: Any', 'Gross revenue: Any', 'Doctors: Any', 'Property: Any'
    ]);
    expect(fl.map((f: any) => f.listId)).toEqual(KEYS.map((k) => `f-listbox-${k}`));
    // A13's rule (V3 marketActiveId): a shut menu has no active descendant, and null is what
    // both renderers omit the attribute for — a string would spell a dead id.
    expect(fl.map((f: any) => f.activeId)).toEqual([null, null, null, null, null]);
    expect(fl[0].caretStyle).toContain('rotate(0deg)');
  });

  it('the trigger reproduces the <select>\'s own box, plus only what a label and a chevron need', () => {
    const style = filters()[0].style;
    // Every declaration the <select> carried (V3 `filters[].style`), byte for byte…
    expect(style).toContain('height: 40px; padding: 0 13px; font-size: 13px; font-weight: 500; color: var(--color-navy); background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 6px; cursor: pointer;');
    // …and the three the OS popup never needed because it drew its own arrow.
    expect(style.startsWith('display: inline-flex; align-items: center; gap: 8px; ')).toBe(true);
    // The chosen-value box is the design's own second state, unchanged.
    c.setF('type')('Mixed');
    expect(byKey('type').style).toContain('background: var(--rf-band)');
    expect(byKey('type').style).toContain('border: 1px solid var(--color-blue)');
  });

  it('the trigger opens its own dropdown and seeds the highlight on the current choice', () => {
    filters()[0].toggle();
    expect(c.state).toMatchObject({ fMenu: 'type', fMenuAt: 0 });
    const fl = byKey('type');
    expect(fl.open).toBe(true);
    expect(fl.caretStyle).toContain('rotate(180deg)');
    expect(fl.activeId).toBe('f-opt-type-0');
    expect(byKey('price').open, 'a sibling must not open with it').toBe(false);
  });

  it('the trigger closes it again (the design\'s own toggle contract)', () => {
    filters()[0].toggle();
    byKey('type').toggle();
    expect(c.state).toMatchObject({ fMenu: null, fMenuAt: -1 });
  });

  it('one slot: opening a second dropdown closes the first, with nothing to forget', () => {
    filters()[0].toggle();
    byKey('revenue').toggle();
    expect(c.state.fMenu).toBe('revenue');
    expect(byKey('type').open).toBe(false);
    expect(byKey('revenue').open).toBe(true);
  });

  it('the highlight is guarded by the key, so a stale index can never paint on a sibling', () => {
    filters()[3].toggle();                     // Doctors, four options
    c.setState({ fMenuAt: 3 });
    expect(byKey('doctors').options[3].rowStyle).toContain('background: var(--vf-neutral)');
    // The same index on a CLOSED sibling paints nothing — `hi` is keyed on fMenu, not on the index
    expect(byKey('revenue').options[3].rowStyle).toContain('background: none');
    expect(byKey('revenue').activeId).toBe(null);
  });

  it('the selected row is accented, the highlighted row takes the design\'s hover grey, the rest are plain', () => {
    filters()[1].toggle();                     // Asking price
    c.setState({ fMenuAt: 2 });
    const rows = byKey('price').options;
    expect(rows[0].rowStyle).toContain('background: var(--vf-accent-bg)');
    expect(rows[0].rowStyle).toContain('font-weight: 800');
    expect(rows[2].rowStyle).toContain('background: var(--vf-neutral)');
    expect(rows[1].rowStyle).toContain('background: none');
    expect(rows[0].tickStyle).toContain('opacity: 1');
    expect(rows[1].tickStyle).toContain('opacity: 0');
    expect(rows.map((r: any) => r.optId)).toEqual([0, 1, 2, 3, 4].map((i) => `f-opt-price-${i}`));
  });

  it('choosing an option produces exactly the transition the <select>\'s onChange did', () => {
    vi.useFakeTimers();
    filters()[1].toggle();
    byKey('price').options[2].go();
    expect(c.state.f).toMatchObject({ price: '500-1000' });
    expect(c.state).toMatchObject({ loading: true, fMenu: null, fMenuAt: -1 });
    vi.advanceTimersByTime(320);
    expect(c.state.loading).toBe(false);
    vi.useRealTimers();
    // …and the trigger now says what the closed <select> would have displayed.
    expect(byKey('price').triggerLabel).toBe('$500K – $1M');
    expect(byKey('price').options[2].selected).toBe(true);
    // the rail reads `f` — the contract the <select> had
    expect(c.renderVals().resultHeadline).toBe(c.renderVals().resultHeadline);
    expect(c.activeFilterCount()).toBe(1);
  });

  it('setF still accepts a change EVENT, so the design\'s own setter contract is untouched', () => {
    c.setF('doctors')({ target: { value: '2' } });
    expect(c.state.f.doctors).toBe('2');
    expect(byKey('doctors').triggerLabel).toBe('2 or more');
  });

  it('ArrowDown opens a closed dropdown, then walks and wraps; ArrowUp wraps the other way', () => {
    const key = (k: string) => { const e = { key: k, preventDefault: vi.fn() }; byKey('doctors').keys(e); return e; };
    expect(key('ArrowDown').preventDefault).toHaveBeenCalled();
    expect(c.state).toMatchObject({ fMenu: 'doctors', fMenuAt: 0 });
    key('ArrowDown'); expect(c.state.fMenuAt).toBe(1);
    key('ArrowDown'); key('ArrowDown'); key('ArrowDown'); expect(c.state.fMenuAt).toBe(0);
    key('ArrowUp'); expect(c.state.fMenuAt).toBe(3);
  });

  it('Home and End jump to the ends, and do nothing while the dropdown is closed', () => {
    const key = (k: string) => { const e = { key: k, preventDefault: vi.fn() }; byKey('type').keys(e); return e; };
    expect(key('End').preventDefault).not.toHaveBeenCalled();
    expect(c.state.fMenu).toBeFalsy();
    byKey('type').toggle();
    key('End'); expect(c.state.fMenuAt).toBe(5);
    key('Home'); expect(c.state.fMenuAt).toBe(0);
  });

  it('Enter and Space choose the highlighted option; a closed dropdown leaves both to the button', () => {
    const key = (k: string) => { const e = { key: k, preventDefault: vi.fn() }; byKey('building').keys(e); return e; };
    expect(key('Enter').preventDefault).not.toHaveBeenCalled();   // closed: the native click opens it
    expect(key('Tab').preventDefault).not.toHaveBeenCalled();     // an unhandled key is left alone
    byKey('building').toggle();
    key('ArrowDown');
    expect(key('Enter').preventDefault).toHaveBeenCalled();
    expect(c.state.f.building).toBe('Included');
    // Reopening seeds the highlight on the option just chosen, so Space takes that one.
    byKey('building').toggle();
    expect(c.state.fMenuAt).toBe(1);
    expect(key(' ').preventDefault).toHaveBeenCalled();
    expect(c.state.f.building).toBe('Included');
  });

  it('Escape closes it; a keydown that is not Escape, and one while closed, do not', () => {
    c.componentDidMount();
    filters()[0].toggle();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }));
    expect(c.state.fMenu).toBe('type');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(c.state).toMatchObject({ fMenu: null, fMenuAt: -1 });
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));  // no-op, and no throw
    expect(c.state.fMenu).toBe(null);
  });

  it('a pointerdown outside closes it; one inside its own wrapper does not', () => {
    const host = document.createElement('div');
    const inside = document.createElement('button');
    host.appendChild(inside);
    document.body.appendChild(host);
    try {
      c.componentDidMount();
      byKey('type').hostRef(host);
      // A13's M3: a pointerdown while every dropdown is CLOSED takes the handler's early exit.
      document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
      expect(c.state.fMenu).toBeFalsy();
      byKey('type').toggle();
      inside.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
      expect(c.state.fMenu).toBe('type');
      document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
      expect(c.state).toMatchObject({ fMenu: null, fMenuAt: -1 });
      // …and with no node recorded, an outside click still closes rather than throwing
      byKey('type').hostRef(null);
      byKey('type').toggle();
      document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
      expect(c.state.fMenu).toBe(null);
    } finally {
      host.remove();
    }
  });

  it('Tab out closes it, and a window blur (null relatedTarget) does not', () => {
    const host = document.createElement('div');
    const inside = document.createElement('button');
    const away = document.createElement('button');
    host.appendChild(inside);
    document.body.appendChild(host);
    document.body.appendChild(away);
    try {
      c.componentDidMount();
      byKey('price').hostRef(host);
      byKey('price').toggle();
      inside.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: null }));
      expect(c.state.fMenu, 'a window blur dismisses nothing (A19/A-LB3)').toBe('price');
      inside.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: inside }));
      expect(c.state.fMenu, 'a move INSIDE the control is not a move out of it').toBe('price');
      inside.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: away }));
      expect(c.state).toMatchObject({ fMenu: null, fMenuAt: -1 });
    } finally {
      host.remove();
      away.remove();
    }
  });

  describe('focus returns to the trigger after a choice', () => {
    const field = () => {
      const host = document.createElement('div');
      const trigger = document.createElement('button');
      trigger.setAttribute('aria-haspopup', 'listbox');
      host.appendChild(trigger);
      document.body.appendChild(host);
      return { host, spy: vi.spyOn(trigger, 'focus') };
    };

    it('after a mouse choice on an option row', () => {
      const { host, spy } = field();
      try {
        byKey('revenue').hostRef(host);
        byKey('revenue').toggle();
        byKey('revenue').options[1].go();
        expect(c.state.f.revenue).toBe('u1000');
        expect(spy, 'the row it was on has just been unmounted').toHaveBeenCalled();
      } finally {
        host.remove();
      }
    });

    it('after Enter on the keyboard', () => {
      const { host, spy } = field();
      try {
        byKey('revenue').hostRef(host);
        byKey('revenue').toggle();
        byKey('revenue').keys({ key: 'ArrowDown', preventDefault: vi.fn() });
        byKey('revenue').keys({ key: 'Enter', preventDefault: vi.fn() });
        expect(c.state.f.revenue).toBe('u1000');
        expect(spy).toHaveBeenCalled();
      } finally {
        host.remove();
      }
    });

    it('and copes with no wrapper recorded, and with one that holds no trigger', () => {
      byKey('revenue').options[2].go();                 // no ref yet — must not throw
      expect(c.state.f.revenue).toBe('1000-2500');
      const bare = document.createElement('div');
      document.body.appendChild(bare);
      try {
        byKey('revenue').hostRef(bare);
        byKey('revenue').options[3].go();
        expect(c.state.f.revenue).toBe('o2500');
      } finally {
        bare.remove();
      }
    });
  });

  describe('the panel\'s own mount ref scrolls the highlight into view (A13/A14 C1)', () => {
    it('spends the index the arrow keys seeded, which a setState callback could not', () => {
      const host = document.createElement('div');
      const row = document.createElement('button');
      row.id = 'f-opt-type-3';
      host.appendChild(row);
      document.body.appendChild(host);
      const spy = vi.fn();
      (row as unknown as { scrollIntoView: unknown }).scrollIntoView = spy;
      try {
        byKey('type').hostRef(host);
        byKey('type').keys({ key: 'ArrowDown', preventDefault: vi.fn() });
        c.setState({ fMenuAt: 3 });
        byKey('type').panelRef(host);
        expect(spy).toHaveBeenCalledWith({ block: 'nearest' });
      } finally {
        host.remove();
      }
    });

    it('and does nothing on unmount, on a row that cannot scroll, or with no wrapper', () => {
      expect(() => byKey('type').panelRef(null)).not.toThrow();
      const host = document.createElement('div');
      const row = document.createElement('button');
      row.id = 'f-opt-type-0';
      host.appendChild(row);
      document.body.appendChild(host);
      try {
        (row as unknown as { scrollIntoView: unknown }).scrollIntoView = undefined;
        byKey('type').hostRef(host);
        expect(() => byKey('type').panelRef(host)).not.toThrow();
        byKey('type').hostRef(null);
        expect(() => c.scrollFilterOption('type', 0)).not.toThrow();
      } finally {
        host.remove();
      }
    });
  });

  // ---------------------------------------------------------------------------------------
  // The edges that cross the family boundary. Inside the family the invariant is structural
  // (one slot), so only these need writing down.
  // ---------------------------------------------------------------------------------------
  describe('the cross-menu edges', () => {
    it('opening a filter dropdown closes the four overlay menus m7 governs', () => {
      c.setState({ navMenu: true, userMenu: true, giveMenu: true, marketMenu: true, marketMenuAt: 2 });
      filters()[0].toggle();
      expect(c.state).toMatchObject({
        fMenu: 'type', navMenu: false, userMenu: false, giveMenu: false, marketMenu: false, marketMenuAt: -1
      });
    });

    it('…and so does opening one with an arrow key, which is the family\'s SAME open path', () => {
      c.setState({ giveMenu: true, marketMenu: true, marketMenuAt: 2 });
      byKey('price').keys({ key: 'ArrowUp', preventDefault: vi.fn() });
      expect(c.state).toMatchObject({ fMenu: 'price', giveMenu: false, marketMenu: false, marketMenuAt: -1 });
    });

    it('each of the six existing open paths closes an open filter dropdown', () => {
      const v = () => c.renderVals();
      const open = () => { filters()[0].toggle(); expect(c.state.fMenu).toBe('type'); };
      for (const [name, fire] of [
        ['toggleNavMenu', () => v().toggleNavMenu()],
        ['toggleUserMenu', () => v().toggleUserMenu()],
        ['toggleGiveMenu', () => v().toggleGiveMenu()],
        ['the Give arrow-open', () => v().giveMenuKeys({ key: 'ArrowDown', preventDefault: vi.fn() })],
        ['toggleMarketMenu', () => v().toggleMarketMenu()],
        ['the metro arrow-open', () => v().marketMenuKeys({ key: 'ArrowDown', preventDefault: vi.fn() })]
      ] as [string, () => void][]) {
        c.setState({ navMenu: false, userMenu: false, giveMenu: false, marketMenu: false });
        open();
        fire();
        expect(c.state, `${name} left a filter dropdown latched`).toMatchObject({ fMenu: null, fMenuAt: -1 });
      }
    });

    it('the More-filters popover is the parent, not a peer: its toggle shuts a dropdown in both directions', () => {
      filters()[0].toggle();
      c.renderVals().toggleMore();                       // opening the popover shuts the toolbar dropdown
      expect(c.state).toMatchObject({ moreFilters: true, fMenu: null, fMenuAt: -1 });
      filters()[0].toggle();
      c.renderVals().toggleMore();                       // and closing it cannot leave a child latched
      expect(c.state).toMatchObject({ moreFilters: false, fMenu: null, fMenuAt: -1 });
    });

    it('navigating away cannot leave a dropdown latched, on any of go()\'s three arms', () => {
      c.setState({ auth: false });
      filters()[0].toggle();
      c.go('browse')();                                   // arm 1: signed out
      expect(c.state).toMatchObject({ screen: 'gate', fMenu: null, fMenuAt: -1 });
      c.setState({ auth: true });
      filters()[0].toggle();
      c.go('browse')();                                   // arm 2: no wizard draft to save
      expect(c.state).toMatchObject({ screen: 'browse', fMenu: null, fMenuAt: -1 });
    });

    it('…including go()\'s third arm, the one that saves a wizard step first', async () => {
      const patch = vi.fn().mockResolvedValue({ assets: [] });
      const w: any = new Component({ listings: { patch } });
      w.setState({ auth: true, sellerView: 'wizard', editingId: 'L1', step: 2 });
      w.renderVals().filters[0].toggle();
      expect(w.state.fMenu).toBe('type');
      await w.go('browse')();
      expect(patch).toHaveBeenCalled();
      expect(w.state).toMatchObject({ screen: 'browse', fMenu: null, fMenuAt: -1 });
    });
  });
});

// ---------------------------------------------------------------------------------------
// A26 Task F2 — the three dropdowns inside the "More filters" popover (A26.3, A26.11).
//
// John called "More filters" the CORRECT implementation, so his words do not reach the three
// under it — the user's experience does. A native `<select>`'s popup is an operating-system
// window and renders above the popover's own `z-index: 700`, so converting only the toolbar
// five would have put the dark menu he photographed on top of his own exemplar, one click
// deeper, rather than removed it.
//
// The same `.map()` shape, the same state slot and the same class members as the five: three
// more instances, no new machinery. What is characterised here is only what multiplicity
// ACROSS the two loops adds — that the eight keys are disjoint, so one slot still identifies
// exactly one dropdown; that `value:`'s `|| "Any"` guard (which the toolbar's map body never
// had, because `f` is seeded with the five toolbar keys and NOT with these three) survives
// into the trigger's label; and that the popover is these three's PARENT rather than their
// peer, so it closes them without them closing it.
// ---------------------------------------------------------------------------------------
describe('A26 (F2) — the three dropdowns inside "More filters"', () => {
  const KEYS = ['est', 'ownership', 'sqft'];
  // A13's own unconditional teardown (M4): these cases arm real `document` listeners through
  // `componentDidMount`, and unmounting only on the happy path leaves one bound to a dead
  // component for the rest of the file the moment an assertion fails.
  afterEach(() => { c.componentWillUnmount(); });

  const more = () => c.renderVals().moreFilters;
  const byKey = (k: string) => more()[KEYS.indexOf(k)];
  const filters = () => c.renderVals().filters;

  it('the three are dropdowns, closed, each keeping the design\'s own caption as its label', () => {
    const mf = more();
    expect(mf).toHaveLength(3);
    expect(mf.map((m: any) => m.label)).toEqual(['Year established', 'Ownership structure', 'Facility size']);
    expect(mf.map((m: any) => m.open)).toEqual([false, false, false]);
    expect(mf.map((m: any) => m.listId)).toEqual(KEYS.map((k) => `f-listbox-${k}`));
    expect(mf.map((m: any) => m.activeId)).toEqual([null, null, null]);
    expect(mf[0].caretStyle).toContain('rotate(0deg)');
  });

  it('the `|| "Any"` guard survives: `f` never seeds these three, and the trigger still reads the design\'s first option', () => {
    // The design's own state literal carries the FIVE toolbar keys and none of these three, so
    // `s.f.est` is undefined on first render. The `<select>`'s render value guarded that with
    // `|| "Any"`; the trigger label is derived from the same guarded value, so an unset filter
    // shows the design's own first option rather than a blank box.
    expect(c.state.f.est).toBeUndefined();
    expect(more().map((m: any) => m.triggerLabel)).toEqual(['Any year', 'Any structure', 'Any size']);
    expect(more().map((m: any) => m.options[0].selected)).toEqual([true, true, true]);
  });

  it('the trigger opens its own dropdown and seeds the highlight on the current choice', () => {
    c.setF('ownership')('Sole');
    byKey('ownership').toggle();
    expect(c.state).toMatchObject({ fMenu: 'ownership', fMenuAt: 1 });
    expect(byKey('ownership').open).toBe(true);
    expect(byKey('ownership').activeId).toBe('f-opt-ownership-1');
    expect(byKey('ownership').caretStyle).toContain('rotate(180deg)');
    expect(byKey('est').open, 'a sibling must not open with it').toBe(false);
  });

  it('ONE slot across BOTH loops: the eight keys are disjoint, so opening either closes the other', () => {
    filters()[0].toggle();
    expect(c.state.fMenu).toBe('type');
    byKey('sqft').toggle();
    expect(c.state.fMenu).toBe('sqft');
    expect(filters()[0].open, 'a toolbar dropdown stayed open behind a popover one').toBe(false);
    filters()[2].toggle();
    expect(c.state.fMenu).toBe('revenue');
    expect(byKey('sqft').open, 'a popover dropdown stayed open behind a toolbar one').toBe(false);
  });

  it('the highlight is guarded by the key here too, so a stale index cannot paint on a sibling', () => {
    byKey('est').toggle();
    c.setState({ fMenuAt: 2 });
    expect(byKey('est').options[2].rowStyle).toContain('background: var(--vf-neutral)');
    expect(byKey('sqft').options[2].rowStyle).toContain('background: none');
    expect(byKey('sqft').activeId).toBe(null);
  });

  it('choosing an option produces exactly the transition the <select>\'s onChange did', () => {
    vi.useFakeTimers();
    byKey('est').toggle();
    byKey('est').options[1].go();
    expect(c.state.f).toMatchObject({ est: 'pre1995' });
    expect(c.state).toMatchObject({ loading: true, fMenu: null, fMenuAt: -1 });
    vi.advanceTimersByTime(320);
    expect(c.state.loading).toBe(false);
    vi.useRealTimers();
    expect(byKey('est').triggerLabel).toBe('Before 1995');
    expect(byKey('est').options[1].selected).toBe(true);
    // …and the popover's own count pill, which reads the same three keys, has moved with it.
    expect(c.renderVals().moreCount).toBe(1);
    expect(c.renderVals().hasMoreCount).toBe(true);
  });

  it('the keyboard set is the toolbar\'s: arrows walk and wrap, Home/End jump, Enter chooses, and a closed one is left to the button', () => {
    const key = (k: string) => { const e = { key: k, preventDefault: vi.fn() }; byKey('sqft').keys(e); return e; };
    expect(key('Home').preventDefault, 'a closed dropdown leaves Home to the button').not.toHaveBeenCalled();
    expect(key('ArrowDown').preventDefault).toHaveBeenCalled();
    expect(c.state).toMatchObject({ fMenu: 'sqft', fMenuAt: 0 });
    key('ArrowUp'); expect(c.state.fMenuAt, 'four options, wrapping backwards from the first').toBe(3);
    key('ArrowDown'); expect(c.state.fMenuAt).toBe(0);
    key('End'); expect(c.state.fMenuAt).toBe(3);
    key('Home'); expect(c.state.fMenuAt).toBe(0);
    key('ArrowDown');
    expect(key('Enter').preventDefault).toHaveBeenCalled();
    expect(c.state.f.sqft).toBe('u3000');
  });

  it('the three shared dismissal closures reach these three as well — no fourth listener', () => {
    const host = document.createElement('div');
    const inside = document.createElement('button');
    const away = document.createElement('button');
    host.appendChild(inside);
    document.body.appendChild(host);
    document.body.appendChild(away);
    try {
      c.componentDidMount();
      byKey('ownership').hostRef(host);
      byKey('ownership').toggle();
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
      expect(c.state, 'Escape (A26.6)').toMatchObject({ fMenu: null, fMenuAt: -1 });
      byKey('ownership').toggle();
      inside.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
      expect(c.state.fMenu, 'a pointerdown INSIDE its own wrapper is not outside it').toBe('ownership');
      document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
      expect(c.state, 'outside click (A26.5)').toMatchObject({ fMenu: null, fMenuAt: -1 });
      byKey('ownership').toggle();
      inside.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: null }));
      expect(c.state.fMenu, 'a window blur dismisses nothing (A19/A-LB3)').toBe('ownership');
      inside.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: away }));
      expect(c.state, 'Tab out (A26.7)').toMatchObject({ fMenu: null, fMenuAt: -1 });
    } finally {
      host.remove();
      away.remove();
    }
  });

  it('focus returns to the trigger after a choice, through this instance\'s own wrapper', () => {
    const host = document.createElement('div');
    const trigger = document.createElement('button');
    trigger.setAttribute('aria-haspopup', 'listbox');
    host.appendChild(trigger);
    document.body.appendChild(host);
    const spy = vi.spyOn(trigger, 'focus');
    try {
      byKey('sqft').hostRef(host);
      byKey('sqft').toggle();
      byKey('sqft').options[2].go();
      expect(c.state.f.sqft).toBe('3000-5000');
      expect(spy, 'the row it was on has just been unmounted').toHaveBeenCalled();
    } finally {
      host.remove();
    }
  });

  it('the panel\'s own mount ref scrolls the highlight into view for these three too (A13/A14 C1)', () => {
    const host = document.createElement('div');
    const row = document.createElement('button');
    row.id = 'f-opt-est-2';
    host.appendChild(row);
    document.body.appendChild(host);
    const spy = vi.fn();
    (row as unknown as { scrollIntoView: unknown }).scrollIntoView = spy;
    try {
      byKey('est').hostRef(host);
      byKey('est').keys({ key: 'ArrowDown', preventDefault: vi.fn() });
      c.setState({ fMenuAt: 2 });
      byKey('est').panelRef(host);
      expect(spy).toHaveBeenCalledWith({ block: 'nearest' });
    } finally {
      host.remove();
    }
  });

  it('opening one of the three closes the four overlay menus, and leaves its own parent popover open', () => {
    c.renderVals().toggleMore();
    expect(c.state.moreFilters).toBe(true);
    c.setState({ navMenu: true, userMenu: true, giveMenu: true, marketMenu: true, marketMenuAt: 2 });
    byKey('est').toggle();
    expect(c.state).toMatchObject({
      fMenu: 'est', navMenu: false, userMenu: false, giveMenu: false, marketMenu: false, marketMenuAt: -1
    });
    expect(c.state.moreFilters, 'the popover is the PARENT of this dropdown, not a peer').toBe(true);
  });

  it('closing the popover cannot leave a child latched behind an unmounted parent (A26.4)', () => {
    c.renderVals().toggleMore();
    byKey('ownership').toggle();
    expect(c.state).toMatchObject({ moreFilters: true, fMenu: 'ownership' });
    c.renderVals().toggleMore();
    expect(c.state).toMatchObject({ moreFilters: false, fMenu: null, fMenuAt: -1 });
  });

  it('navigating away cannot leave one of the three latched either (A26.9)', () => {
    c.setState({ auth: true });
    byKey('sqft').toggle();
    c.go('browse')();
    expect(c.state).toMatchObject({ screen: 'browse', fMenu: null, fMenuAt: -1 });
  });
});

// ---------------------------------------------------------------------------------------
// A26.12–A26.14 — John's 2026-09-08 m7 ruling, restored (controller ruling on the A26 plan's
// Q2, 2026-09-11): "opening any one of the four menus closes the other three."
//
// Three of the twelve ordered directions among the four were never written. Give's own six
// were, which is why the gap survived a final review: Give and the metro listbox also carry
// global pointerdown/focusout dismissal, so their pointer paths were covered by accident,
// while `navMenu` and `userMenu` have no outside-click, Escape or Tab dismissal of any kind
// (D-F2 — reported, and deliberately NOT built here). Two mouse clicks reached the defect:
// open the account menu, click the metro trigger, and both stand open.
//
// The case below is exhaustive rather than three regression cases, because "at most one" is
// the invariant and enumerating the pairs is the only way to say so. A26's own five are proved
// by their `describe` above; this is the four the ruling names.
// ---------------------------------------------------------------------------------------
describe('A26 (Q2) — opening any one of the four menus closes the other three (m7, restored)', () => {
  afterEach(() => { c.componentWillUnmount(); });

  /** The four m7 menus, each with its own open path and its own "is it open" reader. The metro
   *  and Give each have a SECOND open path (the arrow keys), and both are included: A14's own
   *  m7 fix had to cover both of Give's, so the same is asked of the other three. */
  const MENUS: [string, (v: any) => void, (s: any) => boolean][] = [
    ['nav', (v) => v.toggleNavMenu(), (s) => !!s.navMenu],
    ['account', (v) => v.toggleUserMenu(), (s) => !!s.userMenu],
    ['Give (click)', (v) => v.toggleGiveMenu(), (s) => !!s.giveMenu],
    ['Give (arrow)', (v) => v.giveMenuKeys({ key: 'ArrowDown', preventDefault: vi.fn() }), (s) => !!s.giveMenu],
    ['metro (click)', (v) => v.toggleMarketMenu(), (s) => !!s.marketMenu],
    ['metro (arrow)', (v) => v.marketMenuKeys({ key: 'ArrowDown', preventDefault: vi.fn() }), (s) => !!s.marketMenu]
  ];

  it('every ordered pair of open paths leaves exactly one menu open', () => {
    const menuOf = (n: string) => n.replace(/ \(.*\)$/, '');
    let pairs = 0;
    for (const [firstName, openFirst, firstIsOpen] of MENUS) {
      for (const [secondName, openSecond, secondIsOpen] of MENUS) {
        // Same menu twice is the design's own TOGGLE contract, not a cross-close: the second
        // click shuts it, and the arrow keys on an already-open menu only move the highlight.
        if (menuOf(firstName) === menuOf(secondName)) continue;
        pairs++;
        c = new Component({});
        openFirst(c.renderVals());
        expect(firstIsOpen(c.state), `${firstName} did not open`).toBe(true);
        openSecond(c.renderVals());
        expect(secondIsOpen(c.state), `${secondName} did not open after ${firstName}`).toBe(true);
        const open = MENUS.filter(([, , isOpen]) => isOpen(c.state)).map(([n]) => n);
        // Give's two paths and the metro's two each read the same flag, so "one menu open" is
        // "at most two NAMES open, and both of them the same menu".
        const distinct = new Set(open.map((n) => n.replace(/ \(.*\)$/, '')));
        expect([...distinct], `${firstName} then ${secondName}: more than one menu is open`).toHaveLength(1);
      }
    }
    // Not a vacuous pass: six open paths over four menus (nav 1, account 1, Give 2, metro 2),
    // every ordered pair whose two paths belong to different menus — 26 of the 36.
    expect(pairs, 'the pair enumeration stopped matching').toBe(26);
  });

  it('and the highlight goes with the menu it belonged to, never left behind', () => {
    c.renderVals().toggleMarketMenu();
    expect(c.state.marketMenuAt).toBe(0);
    c.renderVals().toggleUserMenu();
    expect(c.state, 'A26.13').toMatchObject({ userMenu: true, marketMenu: false, marketMenuAt: -1 });
    c.renderVals().toggleMarketMenu();
    c.renderVals().toggleNavMenu();
    expect(c.state, 'A26.12').toMatchObject({ navMenu: true, marketMenu: false, marketMenuAt: -1 });
  });

  it('the two directions John\'s ruling named, each reachable with two mouse clicks', () => {
    // The account menu, then the metro trigger (the A26 ruling's section 8, verbatim).
    c.renderVals().toggleUserMenu();
    c.renderVals().toggleMarketMenu();
    expect(c.state, 'A26.14: the metro trigger left the account menu open').toMatchObject({ marketMenu: true, userMenu: false });
    // The collapsed-header nav menu, then the metro trigger — the same, at header-1000.
    c = new Component({});
    c.renderVals().toggleNavMenu();
    c.renderVals().toggleMarketMenu();
    expect(c.state, 'A26.14: the metro trigger left the nav menu open').toMatchObject({ marketMenu: true, navMenu: false });
  });
});

// ---------------------------------------------------------------------------------------
// A24 — real Census boundary polygons (John's rulings D-C34–D-C37, 2026-09-10) and D-C46's
// re-scaled growth breaks (2026-09-11). Every branch the amendment adds to the design's script
// is characterised here; `logic.js` itself is never hand-edited.
// ---------------------------------------------------------------------------------------
describe('A24 — real boundary polygons', () => {
  const fc = (features: unknown[]) => ({ type: 'FeatureCollection', features });
  const feat = (props: Record<string, unknown>) => ({
    type: 'Feature', geometry: null,
    properties: { geo_id: 'g', name: 'g', value: null, moe: null, suppressed: false, suppress_reason: null, band_ambiguous: false, ...props }
  });

  it('areaSet gives every polygon the value of the NEAREST community, at the ruled geography', () => {
    const set = c.areaSet('income');
    expect(set.features.length, 'the design fixture has no tract features').toBeGreaterThan(0);
    for (const f of set.features) {
      expect(f.properties.geo_id).toBe(f.id);
      expect(f.properties.moe).toBeNull();
      expect(f.properties.suppressed).toBe(false);
      expect(f.properties.band_ambiguous).toBe(false);
      expect(f.geometry).toBeTruthy();
    }
    // Every design community carries an income, so no tract comes out null on this layer.
    expect(set.features.every((f: any) => typeof f.properties.value === 'number')).toBe(true);
    // The three geographies are D-C35's, and each layer reads its OWN level — `growth` sees the
    // places and `econ` the counties, so a layer promoted into a finer slot fails here.
    expect(c.areaSet('growth').features.length).toBe(c.state.areas['160'].features.length);
    expect(c.areaSet('econ').features.length).toBe(c.state.areas['050'].features.length);
    expect(set.features.length).toBe(c.state.areas['140'].features.length);
  });

  it('areaSet returns a collection for every layer with a geography, and none for no layer at all', () => {
    // A24.24 (D-L1, 2026-09-12) INVERTS the half of this case that asserted `pets`, `households`
    // and `competition` had no geography: all three shade now. The two ACS counts take the tract,
    // beside income, and read the design's own tract fixture; `competition` takes the ZCTA, which
    // the design's fixture does not carry at all — so it is EMPTY on the reference path, and
    // empty is the honest answer there rather than a fabricated one.
    for (const k of ['households', 'pets']) expect(c.areaSet(k).features.length).toBe(c.state.areas['140'].features.length);
    expect(c.areaSet('competition').features, 'the design fixture carries no ZCTAs').toEqual([]);
    expect(c.areaSet(null).features).toEqual([]);
    expect(c.areaSet(undefined).features).toEqual([]);
  });

  // The nearest-community rule itself, on a fixture whose answer is knowable: two communities,
  // one far away, so every polygon must take the near one's figure.
  it('areaSet measures to the community centroid with the mosaic\'s own cos(lat) scaling', () => {
    const near = { id: 'n', name: 'Near', lat: 30.31, lng: -97.75, income: 111111 };
    const far = { id: 'f', name: 'Far', lat: 45.0, lng: -120.0, income: 222222 };
    c.communities = () => [far, near];
    expect(new Set(c.areaSet('income').features.map((f: any) => f.properties.value))).toEqual(new Set([111111]));
    // A community with no usable point is skipped, exactly as A25 skips it for a pin.
    c.communities = () => [{ id: 'x', name: 'X', lat: null, lng: null, income: 9 }];
    expect(c.areaSet('income').features.every((f: any) => f.properties.value === null)).toBe(true);
  });

  // Global Constraint (c), and a real trap: `num()` strips every character but digits and a dot,
  // so `num(-5.1)` is `5.1`. Routing a growth figure through it would paint a DECLINING place as
  // a growing one — silently, and only for the sign that D-C46 exists to make visible.
  it('a negative growth figure keeps its sign all the way to the fill', () => {
    c.communities = () => [{ id: 'd', name: 'Declining', lat: 30.31, lng: -97.75, growth: -5.1 }];
    const set = c.areaSet('growth');
    expect(set.features[0].properties.value).toBe(-5.1);
    const out = c.areaVals(set, 'growth');
    expect(out.features[0].properties.label).toBe('-5.1%');
    expect(out.features[0].properties.color, 'a decline took a growth band').toBe(c.bucket('growth', -5.1).color);
    expect(out.features[0].properties.color).not.toBe(c.bucket('growth', 5.1).color);
  });

  it('areaVals colours a measured value through bucket() and labels it through fmtMetric()', () => {
    const out = c.areaVals(fc([feat({ geo_id: '78704', name: 'ZCTA5 78704', value: 92150, moe: 6420 })]), 'income');
    expect(out.features[0].properties.color).toBe(c.bucket('income', 92150).color);
    expect(out.features[0].properties.label).toBe(c.fmtMetric('income', 92150));
    expect(out.features[0].properties.tip).toContain('ZCTA5 78704');
    expect(out.features[0].id).toBe('78704');
    // Nothing but a FeatureCollection is required of the caller: an absent one is empty, not a throw.
    expect(c.areaVals(null, 'income').features).toEqual([]);
    expect(c.areaVals({}, 'income').features).toEqual([]);
  });

  // Global Constraint (c) again: the producer's sentinel, measured rather than assumed. A MISSING
  // value is `value: null` with `suppressed: false` — that is what `_suppression(None, None)`
  // returns and what the endpoint will serialise — so a guard on `suppressed` alone would paint a
  // null as a measured figure.
  it('a null value takes the no-data class even though it is not suppressed', () => {
    const out = c.areaVals(fc([feat({ geo_id: '78745', name: 'ZCTA5 78745', value: null })]), 'income');
    expect(out.features[0].properties.color).toBe('#e6e6e6');
    expect(out.features[0].properties.label).toBe('No data');
    expect(out.features[0].properties.tip).toContain('No data for this area');
    // …and so does a SUPPRESSED value, which is a different state and the same class.
    const sup = c.areaVals(fc([feat({ value: 92150, suppressed: true, suppress_reason: 'high_moe' })]), 'income');
    expect(sup.features[0].properties.color).toBe('#e6e6e6');
    expect(sup.features[0].properties.suppressed).toBe(true);
    expect(sup.features[0].properties.suppressReason).toBe('high_moe');
  });

  it('the honesty lines are the contract\'s own wording, one per case', () => {
    const tip = (props: Record<string, unknown>, layer = 'income') =>
      c.areaVals(fc([feat(props)]), layer).features[0].properties.tip;
    expect(tip({ value: 1, suppressed: true, suppress_reason: 'no_moe' })).toContain('Estimate too imprecise to show at this geography');
    expect(tip({ value: 1, suppressed: true, suppress_reason: 'high_moe' })).toContain('Estimate too imprecise to show at this geography');
    expect(tip({ value: 1, suppressed: true, suppress_reason: 'source_flag' })).toContain('Not published for this county');
    expect(tip({ value: null })).toContain('No data for this area');
    expect(tip({ value: 92150, moe: 6420, band_ambiguous: true })).toContain('this margin spans two legend bands.');
    expect(tip({ value: 92150, moe: 6420, band_ambiguous: false })).not.toContain('spans two legend bands');
    expect(tip({ value: 12.4 }, 'growth')).toContain('No combined margin of error is published.');
    expect(tip({ value: 640000 }, 'econ')).toContain('a census of establishments, not a sample');
    // The tip's own shape, once: every line the reference's literal carries, in order, so a
    // trimmed inline style is caught here rather than only by a pixel that nothing captures.
    expect(tip({ value: 92150, moe: 6420 }).startsWith('<div style="font-family:ProximaNova,Arial,Helvetica,sans-serif;min-width:150px">')).toBe(true);
    expect(tip({ value: 92150, moe: 6420 })).toContain('<div style="font-size:10.5px;color:#494949;margin-top:4px">\u00b1 $6K</div>');
  });

  it('the legend names the geography and gains a No data row, for every layer that shades', () => {
    for (const [layer, label] of [['income', 'Census tract'], ['growth', 'Place (city/town)'], ['econ', 'County'],
      ['households', 'Census tract'], ['pets', 'Census tract']] as const) {
      c.state.mdValue = layer;
      const md = c.marketVals(P);
      const active = md.active;
      expect(active.hasGeo).toBe(true);
      expect(active.geoLine).toBe(label);
      // Review round 1, Important 1 — the assertion this case was MISSING, and the reason it
      // stepped over a layer that painted 503 of 503 polygons "No data" under a full four-class
      // ramp: `areaSet` read `best[layer]` while `communities()` names the field `hh` for
      // households and `vets` for competition, which the design's three OTHER readers alias. A
      // legend is a claim about what is drawn, so a case that checks the legend and never the
      // fill cannot see the exact lie A24.32 exists to prevent.
      expect(md.areas.features.length, `${layer}: no polygons at all`).toBeGreaterThan(0);
      expect(
        md.areas.features.filter((f: { properties: { value: number | null } }) => f.properties.value !== null).length,
        `${layer}: every polygon is valueless, so the ramp above describes nothing`
      ).toBeGreaterThan(0);
      expect(active.ramp[active.ramp.length - 1]).toEqual({ style: 'flex: 1; height: 9px; background: #e6e6e6;', label: 'No data' });
      // …and exactly one such row, appended, with the design's own classes ahead of it.
      expect(active.ramp.filter((r: { label: string }) => r.label === 'No data')).toHaveLength(1);
    }
    // A24.28: a shading layer with its OWN class breaks prints its own labels, not the design's
    // community-scale ones — a legend reading "< 10K" over a map cut at 1,000 households would be
    // the caption for a different map.
    c.state.mdValue = 'households';
    expect(c.marketVals(P).active.ramp.map((r: { label: string }) => r.label))
      .toEqual(['< 1,000', '1,000–1,500', '1,500–2,000', '> 2,000', 'No data']);
    c.state.mdValue = 'income';
    expect(c.marketVals(P).active.ramp.map((r: { label: string }) => r.label))
      .toEqual(['< $50K', '$50–75K', '$75–100K', '$100–150K', '> $150K', 'No data']);

    // A24.32 (review finding 5): zero polygons drawn, no ramp and no geography line. On the
    // reference path `competition` is the reachable case — the design's fixture has no ZCTAs —
    // and on the app it is any metro the API could not answer for, Bozeman included.
    c.state.mdValue = 'competition';
    const nothingDrawn = c.marketVals(P).active;
    expect(nothingDrawn.hasRamp, 'a ramp was printed over a map with no polygons').toBe(false);
    expect(nothingDrawn.hasGeo).toBe(false);

    // "No shading — practices only": no ramp at all, so no no-data row either.
    c.state.mdValue = null;
    const none = c.marketVals(P).active;
    expect(none.hasGeo).toBe(false);
    expect(none.ramp).toEqual([]);
  });

  it('md.areas is the drawable collection, taken through areaVals for the active layer', () => {
    c.state.mdValue = 'income';
    const md = c.marketVals(P);
    expect(md.areas.type).toBe('FeatureCollection');
    expect(md.areas.features.length).toBe(c.state.areas['140'].features.length);
    for (const f of md.areas.features) {
      expect(typeof f.properties.color).toBe('string');
      expect(typeof f.properties.tip).toBe('string');
    }
    // Every shading layer is handed its own polygons now (A24.24), and a layer the fixture has
    // no geography for is handed none rather than another layer's.
    c.state.mdValue = 'pets';
    expect(c.marketVals(P).areas.features.length).toBe(c.state.areas['140'].features.length);
    c.state.mdValue = 'competition';
    expect(c.marketVals(P).areas.features).toEqual([]);
  });

  // A24.25/A24.26: one classifier, two tables. The choropleth asks for the breaks measured over
  // the geography it paints; everything else on the screen keeps asking for the design's own.
  it('the choropleth classes a count against the tract-scale breaks and the cards against the city-scale ones', () => {
    // 1,480 households is an ordinary Census tract and an implausibly small city, and the two
    // tables say so: the design's own breaks put every US tract in one class, which was the
    // whole complaint.
    expect(c.bucket('households', 1480, true).t).not.toBe(c.bucket('households', 1480).t);
    expect(c.bucket('households', 1480).t, 'the design\'s own first class swallows every tract').toBe(0);
    expect(new Set([1, 1200, 1700, 2500].map((v) => c.bucket('households', v, true).color)).size).toBe(4);
    expect(new Set([1, 1200, 1700, 2500].map((v) => c.bucket('households', v).color)).size).toBe(1);
    // A layer with no area table of its own is classed identically either way.
    expect(c.bucket('income', 92150, true)).toEqual(c.bucket('income', 92150));
    // A24.29: a tract-scale count is not abbreviated to the thousand it shares with 500 others.
    expect(c.fmtMetric('households', 1446)).toBe('1,446');
    expect(c.fmtMetric('households', 27600), 'nothing at ten thousand or above moves').toBe('28K');
    expect(c.fmtMetric('competition', 7)).toBe('7');
  });

  // §15 (the stakeholder's own directive): a competition count states its geography on screen.
  it('a competition tip names what it counts and the geography it counts them in', () => {
    const tip = c.areaTip({ name: 'ZCTA5 78704', value: 7, moe: null, suppressed: false, suppress_reason: null, band_ambiguous: false }, 'competition', true);
    expect(tip).toContain('7 veterinary practices');
    expect(tip).toContain('within this ZIP Code Tabulation Area');
    expect(tip).toContain('authoritative geography');
    // §9: the modelled estimate says it is modelled, on the polygon as well as in the catalogue.
    const pets = c.areaTip({ name: 'Census Tract 11', value: 844, moe: null, suppressed: false, suppress_reason: null, band_ambiguous: false }, 'pets', true);
    expect(pets).toContain('Modelled estimate: households × 0.57. Not an observed count.');
    expect(pets, 'a derived estimate is never described as a count of anything').not.toContain('veterinary practices');
  });

  // D-C46 (John, 2026-09-11). Measured against ACS 2014-2018 -> 2019-2023 place populations; the
  // band below zero is the ruling's own point, so it is asserted as a band and not as a label.
  it('A24.13 — the growth breaks carry a band below zero, and a decline never shares a class with growth', () => {
    const band = (v: number) => c.bucket('growth', v).color;
    expect(band(-12)).toBe(band(-0.1));
    expect(band(-0.1), 'a decline is in the same class as a 9 % rise — D-C46\'s own defect').not.toBe(band(9));
    // Four distinct classes over the real range, which is what "still all one colour" was about.
    expect(new Set([band(-5), band(2), band(9), band(24)]).size).toBe(4);
    expect(band(0), 'zero is growth, not decline: the stop is inclusive upward').toBe(band(4.9));
    expect(band(15)).toBe(band(200));
  });
});

// ---------------------------------------------------------------------------------------
// A24.14-A24.18 — the `market` adapter. The seam A16 and A17 established, keyed on adapter
// PRESENCE and never on data (A16.1's shape, A-SL23 (2)). The design's own fixture is the
// AUSTIN metro carrying the design's own nine figures, so the one thing that must never happen
// is it being drawn over a real metro: every arm below ends either on the API's polygons or on
// none, and never on `areaSet`.
// ---------------------------------------------------------------------------------------
describe('A24 — the market adapter', () => {
  const FC = (ids: string[]) => ({
    type: 'FeatureCollection',
    features: ids.map((id) => ({
      type: 'Feature', id,
      properties: { geo_id: id, name: id.toUpperCase(), value: 60000, moe: null, suppressed: false, suppress_reason: null, band_ambiguous: false },
      geometry: null
    }))
  });
  const adapter = (areas: Record<string, unknown>) => ({ boundaries: () => Promise.resolve(areas) });
  const drawn = (comp: any) => comp.marketVals(P).areas.features.map((f: any) => f.properties.geo_id);

  it("with an adapter present the map draws the API's polygons and NEVER the design's fixture", async () => {
    const api = { income: FC(['x']) };
    const comp: any = new Component({ market: adapter(api) });
    comp.componentDidMount();
    await Promise.resolve();
    expect(comp.state.mdAreas).toBe(api);
    expect(drawn(comp)).toEqual(['x']);
  });

  it('an EMPTY answer empties the map — it does not fall back to the fixture', async () => {
    const comp: any = new Component({ market: adapter({}) });
    comp.componentDidMount();
    await Promise.resolve();
    expect(drawn(comp)).toEqual([]);
  });

  it('a REFUSED load empties the map too, and the rejection arm exists', async () => {
    const comp: any = new Component({ market: { boundaries: () => Promise.reject(new Error('404')) } });
    comp.componentDidMount();
    await Promise.resolve();
    await Promise.resolve();
    expect(comp.state.mdAreas).toEqual({});
    expect(drawn(comp)).toEqual([]);
  });

  it("with NO adapter the design's own fixture path runs, untouched", () => {
    const comp: any = new Component({});
    comp.componentDidMount();
    expect(comp.state.mdAreas).toBeNull();
    expect(comp.marketVals(P).areas.features.length).toBeGreaterThan(0);
  });

  it('changing the metro reloads the polygons for the metro chosen', async () => {
    const asked: string[] = [];
    const comp: any = new Component({ market: { boundaries: (n: string) => { asked.push(n); return Promise.resolve({}); } } });
    comp.componentDidMount();
    comp.setMarket('Sacramento, CA');
    expect(asked).toEqual(['Austin, TX', 'Sacramento, CA']);
  });

  it("a metro change CLEARS the previous metro's polygons before it asks, so no city is ever drawn over another", async () => {
    let settle: (v: unknown) => void = () => {};
    const comp: any = new Component({ market: { boundaries: () => new Promise((r) => { settle = r; }) } });
    comp.componentDidMount();
    settle({ income: FC(['austin'] ) });
    await Promise.resolve();
    expect(drawn(comp)).toEqual(['austin']);
    comp.setMarket('Sacramento, CA');
    expect(comp.state.mdAreas, 'Austin is off the map the instant Sacramento is asked for').toBeNull();
    expect(drawn(comp)).toEqual([]);
    settle({ income: FC(['sacramento']) });
    await Promise.resolve();
    expect(drawn(comp)).toEqual(['sacramento']);
  });

  it('an answer for a market the member has already left is DISCARDED, however late it lands', async () => {
    const pending: ((v: unknown) => void)[] = [];
    const comp: any = new Component({ market: { boundaries: () => new Promise((r) => pending.push(r)) } });
    comp.componentDidMount();          // asks for Austin
    comp.setMarket('Sacramento, CA');  // asks for Sacramento
    pending[1]({ income: FC(['sacramento']) });
    await Promise.resolve();
    expect(drawn(comp)).toEqual(['sacramento']);
    // Austin's answer arrives second. Last-write-wins would strand Austin's outlines over
    // Sacramento's map indefinitely; the guard drops it instead.
    pending[0]({ income: FC(['austin']) });
    await Promise.resolve();
    expect(drawn(comp)).toEqual(['sacramento']);
  });

  it("a late REJECTION for a market already left does not empty the market the member is on", async () => {
    const pending: { reject: (e: unknown) => void }[] = [];
    const comp: any = new Component({ market: { boundaries: () => new Promise((_r, reject) => pending.push({ reject })) } });
    comp.componentDidMount();
    comp.setMarket('Sacramento, CA');
    pending[1].reject(new Error('nope'));
    await Promise.resolve();
    await Promise.resolve();
    expect(comp.state.mdAreas).toEqual({});
    pending[0].reject(new Error('Austin, late'));
    await Promise.resolve();
    await Promise.resolve();
    expect(comp.state.mdAreas, "Austin's refusal is not Sacramento's") .toEqual({});
  });

  // -----------------------------------------------------------------------------------
  // A24.21-A24.23 (2026-09-12) — the map asks for the ground it is SHOWING. The route has taken
  // a `bbox` since Task 9 and the adapter never sent one, so every request was for the whole
  // metro envelope: 5,935 Census tracts in New York where the view holds 3,706. The caps were
  // re-measured for Census tracts the same day (`MAX_FEATURES = 12000`, `MAX_BODY_BYTES =
  // 6_000_000`), so the metro request is no longer refused — it is simply an answer nobody asked
  // for, and the box is what keeps it the size of the screen.
  //
  // The adapter's own `viewport()` is BOTH the box that is sent and the token an arriving answer
  // is checked against — one value, so the guard cannot drift from the request. An adapter
  // WITHOUT it (every case above, and any older build) keeps the whole-metro behaviour exactly.
  // -----------------------------------------------------------------------------------
  const viewportAdapter = (boxes: string[]) => {
    const calls: { market: string; bbox: string | null }[] = [];
    const subs: (() => void)[] = [];
    const pending: ((v: unknown) => void)[] = [];
    return {
      calls, pending,
      move: (box: string) => { boxes.unshift(box); subs.forEach((s) => s()); },
      unsubscribed: () => subs.length === 0,
      adapter: {
        viewport: () => boxes[0] ?? null,
        onViewport: (cb: () => void) => { subs.push(cb); return () => { subs.length = 0; }; },
        boundaries: (market: string, bbox: string | null) => {
          calls.push({ market, bbox });
          return new Promise((r) => pending.push(r));
        }
      }
    };
  };

  it('asks for NOTHING until a map has said what it is looking at — no doomed whole-metro request', () => {
    const a = viewportAdapter([]);
    const comp: any = new Component({ market: a.adapter });
    comp.componentDidMount();
    expect(a.calls).toEqual([]);
    expect(comp.state.mdAreas).toBeNull();
  });

  it('asks with the box the map published, the moment it publishes one', async () => {
    const a = viewportAdapter([]);
    const comp: any = new Component({ market: a.adapter });
    comp.componentDidMount();
    a.move('-74.2,40.1,-72.8,40.9');
    expect(a.calls).toEqual([{ market: 'Austin, TX', bbox: '-74.2,40.1,-72.8,40.9' }]);
    a.pending[0]({ income: FC(['tract-a']) });
    await Promise.resolve();
    expect(drawn(comp)).toEqual(['tract-a']);
  });

  it('KEEPS the polygons on screen while a pan reloads — a pan is not a metro change', async () => {
    const a = viewportAdapter([]);
    const comp: any = new Component({ market: a.adapter });
    comp.componentDidMount();
    a.move('box-1');
    a.pending[0]({ income: FC(['before']) });
    await Promise.resolve();
    a.move('box-2');
    expect(comp.state.mdAreas, 'the map went blank mid-pan').not.toBeNull();
    expect(drawn(comp)).toEqual(['before']);
    a.pending[1]({ income: FC(['after']) });
    await Promise.resolve();
    expect(drawn(comp)).toEqual(['after']);
  });

  it('DISCARDS an answer for a box the member has already panned off, the market guard extended', async () => {
    const a = viewportAdapter([]);
    const comp: any = new Component({ market: a.adapter });
    comp.componentDidMount();
    a.move('box-1');
    a.move('box-2');
    a.pending[1]({ income: FC(['box-2']) });
    await Promise.resolve();
    expect(drawn(comp)).toEqual(['box-2']);
    a.pending[0]({ income: FC(['box-1']) });
    await Promise.resolve();
    expect(drawn(comp), "box-1's answer landed on box-2's map").toEqual(['box-2']);
  });

  it('a metro change still CLEARS first, even with a viewport — one city is never drawn over another', () => {
    const a = viewportAdapter(['box-1']);
    const comp: any = new Component({ market: a.adapter });
    comp.componentDidMount();
    a.pending[0]({ income: FC(['austin']) });
    comp.setMarket('Sacramento, CA');
    expect(comp.state.mdAreas).toBeNull();
    expect(a.calls.map((c) => c.market)).toEqual(['Austin, TX', 'Sacramento, CA']);
  });

  it('unsubscribes on unmount, so a torn-down screen stops asking the API for boxes', () => {
    const a = viewportAdapter(['box-1']);
    const comp: any = new Component({ market: a.adapter });
    comp.componentDidMount();
    expect(a.unsubscribed()).toBe(false);
    comp.componentWillUnmount();
    expect(a.unsubscribed()).toBe(true);
    expect(() => comp.componentWillUnmount()).not.toThrow();
  });

  it('an adapter with no viewport at all keeps the whole-metro behaviour, unchanged', () => {
    const asked: unknown[] = [];
    const comp: any = new Component({ market: { boundaries: (n: string, b: unknown) => { asked.push([n, b]); return Promise.resolve({}); } } });
    comp.componentDidMount();
    expect(asked).toEqual([['Austin, TX', null]]);
  });

  // -----------------------------------------------------------------------------------
  // The three states Task 9's payload distinguishes, rendered. These property dicts are
  // `app/api/market._boundary_feature`'s own output, transcribed from the route (commit
  // `c466415`) rather than imagined: `value` is null BOTH when the geography has no row and
  // when its row is suppressed, and the two are told apart by `suppressed`/`suppress_reason`
  // on the same dict. `band_ambiguous` is orthogonal to both — the value is KEPT and a caveat
  // is added, never greyed (D-C36: "greying a measured figure is its own false statement").
  // -----------------------------------------------------------------------------------
  it('renders no-data, suppressed and band-ambiguous as three different things', () => {
    const props = [
      { geo_id: 'none', name: 'No row', value: null, moe: null, suppressed: false, suppress_reason: null, band_ambiguous: false },
      { geo_id: 'nomoe', name: 'No margin', value: null, moe: null, suppressed: true, suppress_reason: 'no_moe', band_ambiguous: false },
      { geo_id: 'highmoe', name: 'Wide margin', value: null, moe: 40000, suppressed: true, suppress_reason: 'high_moe', band_ambiguous: false },
      { geo_id: 'cascade', name: 'Cascaded', value: null, moe: null, suppressed: true, suppress_reason: 'input_suppressed', band_ambiguous: false },
      { geo_id: 'flag', name: 'Withheld', value: null, moe: null, suppressed: true, suppress_reason: 'source_flag', band_ambiguous: false },
      { geo_id: 'amb', name: 'Ambiguous', value: 92150, moe: 6420, suppressed: false, suppress_reason: null, band_ambiguous: true },
      { geo_id: 'plain', name: 'Measured', value: 92150, moe: 1200, suppressed: false, suppress_reason: null, band_ambiguous: false }
    ];
    const comp: any = new Component({});
    const out = comp.areaVals({ type: 'FeatureCollection', features: props.map((p) => ({ type: 'Feature', id: p.geo_id, properties: p, geometry: null })) }, 'income');
    const by = Object.fromEntries(out.features.map((f: any) => [f.properties.geo_id, f.properties]));

    // Every unmeasured polygon is DRAWN — never omitted, because a hole on a choropleth reads
    // as a park, a lake or the edge of the market (D-NS16).
    expect(out.features).toHaveLength(props.length);

    // One neutral class for all five unmeasured states, and a DIFFERENT sentence for each fact.
    const grey = by.none.color;
    for (const id of ['none', 'nomoe', 'highmoe', 'cascade', 'flag']) {
      expect(by[id].color, `${id} must take the no-data class`).toBe(grey);
      expect(by[id].label).toBe('No data');
    }
    expect(by.none.tip).toContain('No data for this area');
    // The three imprecision reasons share the contract's own wording; `input_suppressed` is a
    // cascade from a figure suppressed for imprecision, so it reads as imprecision too. It is
    // also unreachable on this endpoint today — only `median_hh_income` is suppressed here
    // (D-NS17) and `_suppression` emits `no_moe`/`high_moe` alone.
    for (const id of ['nomoe', 'highmoe', 'cascade']) {
      expect(by[id].tip).toContain('Estimate too imprecise to show at this geography');
    }
    expect(by.flag.tip).toContain('Not published for this county');
    expect(by.flag.tip).not.toContain('Estimate too imprecise');

    // Band-ambiguous is NOT greyed: the figure stands, and the caveat rides beside it.
    expect(by.amb.color).not.toBe(grey);
    expect(by.amb.color).toBe(by.plain.color);
    expect(by.amb.label).toBe('$92K');
    expect(by.amb.tip).toContain('this margin spans two legend bands');
    expect(by.plain.tip).not.toContain('spans two legend bands');
  });

  it("a blocked or disabled layer arrives with no features, so nothing of it is ever painted", async () => {
    // Verified against the route, not assumed: `app/api/market.py` fills `rows` only when
    // `state == "enabled"`, so a licence-blocked layer answers `features: []` with a
    // `blocked_reason`. "Blocked datasets never ship" therefore holds without the design
    // reading `state` at all — and if that ever changes, this case is where it shows.
    const comp: any = new Component({ market: { boundaries: () => Promise.resolve({
      income: { type: 'FeatureCollection', state: 'blocked', blocked_reason: 'licence refused', features: [] }
    }) } });
    comp.componentDidMount();
    await Promise.resolve();
    expect(comp.marketVals(P).areas.features).toEqual([]);
  });

  it('a layer the API did not answer for draws nothing rather than the fixture for that layer', async () => {
    const comp: any = new Component({ market: adapter({ income: FC(['x']) }) });
    comp.componentDidMount();
    await Promise.resolve();
    comp.state.mdValue = 'growth';
    expect(comp.marketVals(P).areas.features).toEqual([]);
    comp.state.mdValue = 'income';
    expect(drawn(comp)).toEqual(['x']);
  });
});
