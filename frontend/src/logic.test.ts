// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Component } from './logic.js';

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
});
