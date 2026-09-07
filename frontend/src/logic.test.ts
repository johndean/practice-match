// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import { Component } from './logic.js';

let c: any;
beforeEach(() => { c = new Component({}); });

describe('logic.js — characterisation of the approved prototype (file untouched)', () => {
  it('starts signed out on the sign-in gate with the design defaults', () => {
    expect(c.state).toMatchObject({ screen: 'gate', gate: 'signin', auth: false, viewport: 'desktop', mobileTab: 'list', adminTab: 'users', detailId: 'p1', sellerView: 'dash' });
  });

  it('go() refuses navigation while signed out and returns to the sign-in gate', () => {
    c.setState({ screen: 'browse', userMenu: true });
    c.go('requests')();
    expect(c.state).toMatchObject({ screen: 'gate', gate: 'signin', userMenu: false, auth: false });
  });

  it('jumpTo() (the prototype jump bar) signs in and navigates; jumpTo("gate") signs out', () => {
    c.jumpTo('admin')();
    expect(c.state).toMatchObject({ screen: 'admin', auth: true, interest: 'closed', userMenu: false, gate: 'signin' });
    c.jumpTo('gate')();
    expect(c.state).toMatchObject({ screen: 'gate', auth: false });
  });

  it('go() navigates once signed in', () => {
    c.jumpTo('browse')();
    c.go('seller')();
    expect(c.state.screen).toBe('seller');
  });

  it('renderVals exposes the four nav items and six jumps with the design labels, plus the signed-in flags', () => {
    const v = c.renderVals();
    expect(v.nav.map((n: any) => n.label)).toEqual(['Browse Practices', 'My Requests', 'List a Practice', 'VIN Foundation Admin']);
    expect(v.jumps.map((j: any) => j.label)).toEqual(['Access', 'Browse', 'Listing', 'Requests', 'Seller', 'Admin']);
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

  it('componentDidMount leaves an unverified account, and no account at all, on the sign-in gate (A5.4)', () => {
    for (const props of [{ me: { ...ACTIVE, state: 'unverified' } }, { me: null }, {}]) {
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

  it('startScreen still signs the prototype in without any account, exactly as the design shipped it', () => {
    const c2: any = new Component({ startScreen: 'admin' });
    c2.componentDidMount();
    expect(c2.state).toMatchObject({ screen: 'admin', auth: true });
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
