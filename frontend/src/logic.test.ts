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

  // A2.4. The top-level `selectMarker` (distinct from `mobileVals.selectMarker`, which C13
  // already fixed) is never wired to any template prop, but it still wrote the dead
  // `browseSel` key alongside the live `activeId` key on every call. Per the ruling, the
  // dead key is dropped and the live key is kept — the handler itself is untouched otherwise.
  it('the top-level selectMarker keeps setting activeId but drops the dead browseSel key (A2.4)', () => {
    const v = c.renderVals();
    expect(typeof v.selectMarker).toBe('function');
    v.selectMarker('p2');
    expect(c.state).toMatchObject({ activeId: 'p2' });
    expect(c.state).not.toHaveProperty('browseSel');
  });
});
