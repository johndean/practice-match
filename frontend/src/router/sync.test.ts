import { describe, it, expect } from 'vitest';
import { stateToRoute, routeToPatch, guard, needsPatch, sameLocation } from './sync';

const base = { screen: 'gate', detailId: 'p1', adminTab: 'users' };

describe('stateToRoute', () => {
  it('maps gate to /', () => expect(stateToRoute(base)).toEqual({ path: '/', query: {} }));
  it('maps browse to /browse with no query — V3 has one Browse screen, not two tabs', () =>
    expect(stateToRoute({ ...base, screen: 'browse' })).toEqual({ path: '/browse', query: {} }));
  it('maps detail to /practices/:id', () =>
    expect(stateToRoute({ ...base, screen: 'detail', detailId: 'p7' })).toEqual({ path: '/practices/p7', query: {} }));
  it('maps requests and seller', () => {
    expect(stateToRoute({ ...base, screen: 'requests' }).path).toBe('/requests');
    expect(stateToRoute({ ...base, screen: 'seller' }).path).toBe('/seller');
  });
  it('maps admin tabs, omitting the default users tab', () => {
    expect(stateToRoute({ ...base, screen: 'admin' })).toEqual({ path: '/admin', query: {} });
    expect(stateToRoute({ ...base, screen: 'admin', adminTab: 'data' })).toEqual({ path: '/admin', query: { tab: 'data' } });
  });
  it('treats an undefined detailId as p1', () =>
    expect(stateToRoute({ ...base, screen: 'detail', detailId: undefined })).toEqual({ path: '/practices/p1', query: {} }));
  it('treats an undefined adminTab as users', () =>
    expect(stateToRoute({ ...base, screen: 'admin', adminTab: undefined })).toEqual({ path: '/admin', query: {} }));
});

describe('routeToPatch', () => {
  const r = (path: string, query: Record<string, unknown> = {}, params: Record<string, unknown> = {}) => ({ path, query, params });
  it('/ → gate', () => expect(routeToPatch(r('/'))).toEqual({ screen: 'gate' }));
  it('/browse → browse', () => expect(routeToPatch(r('/browse'))).toEqual({ screen: 'browse' }));
  it('/browse?tab=market → browse, the legacy query silently ignored', () =>
    expect(routeToPatch(r('/browse', { tab: 'market' }))).toEqual({ screen: 'browse' }));
  it('/browse?tab=listings → browse, the legacy query silently ignored', () =>
    expect(routeToPatch(r('/browse', { tab: 'listings' }))).toEqual({ screen: 'browse' }));
  it('/browse?tab=bogus → browse', () => expect(routeToPatch(r('/browse', { tab: 'bogus' }))).toEqual({ screen: 'browse' }));
  it('a legacy /browse?tab= URL settles without a redirect loop: the state it produces routes back to a bare /browse', () => {
    const patch = routeToPatch(r('/browse', { tab: 'market' }));
    const target = stateToRoute({ ...base, ...patch });
    expect(target).toEqual({ path: '/browse', query: {} });
    expect(routeToPatch(r(target.path, target.query))).toEqual(patch);   // fixed point: no second navigation
  });
  it('/practices/p3 → detail p3', () => expect(routeToPatch(r('/practices/p3', {}, { id: 'p3' }))).toEqual({ screen: 'detail', detailId: 'p3' }));
  it('/admin?tab=activity → admin activity', () => expect(routeToPatch(r('/admin', { tab: 'activity' }))).toEqual({ screen: 'admin', adminTab: 'activity' }));
  it('/admin?tab=nope → users', () => expect(routeToPatch(r('/admin', { tab: 'nope' }))).toEqual({ screen: 'admin', adminTab: 'users' }));
  it('unknown path → gate', () => expect(routeToPatch(r('/whatever'))).toEqual({ screen: 'gate' }));
  it('round-trips every screen', () => {
    for (const s of [
      { ...base, screen: 'browse' },
      { ...base, screen: 'detail', detailId: 'g4' },
      { ...base, screen: 'requests' }, { ...base, screen: 'seller' },
      { ...base, screen: 'admin', adminTab: 'listings' }
    ]) {
      const loc = stateToRoute(s);
      const params = loc.path.startsWith('/practices/') ? { id: loc.path.split('/')[2] } : {};
      expect({ ...s, ...routeToPatch({ ...loc, params }) }).toEqual(s);
    }
  });
});

describe('guard (the prototype\'s go() semantics)', () => {
  it('sends a signed-out visitor to the gate and remembers the intended route', () =>
    expect(guard({ ...base, auth: false }, { screen: 'browse' }))
      .toEqual({ apply: { screen: 'gate', gate: 'signin' }, pending: { screen: 'browse' } }));
  it('applies member routes directly when signed in', () =>
    expect(guard({ ...base, auth: true }, { screen: 'admin', adminTab: 'data' })).toEqual({ apply: { screen: 'admin', adminTab: 'data' }, pending: null }));
  it('never guards the gate itself', () =>
    expect(guard({ ...base, auth: false }, { screen: 'gate' })).toEqual({ apply: { screen: 'gate' }, pending: null }));
});

describe('needsPatch / sameLocation', () => {
  it('needsPatch is false when state already matches', () =>
    expect(needsPatch({ ...base, screen: 'browse' }, { screen: 'browse' })).toBe(false));
  it('needsPatch is true on any difference', () =>
    expect(needsPatch(base, { screen: 'browse' })).toBe(true));
  it('sameLocation compares path and query', () => {
    expect(sameLocation({ path: '/browse', query: { tab: 'market' } }, { path: '/browse', query: { tab: 'market' } })).toBe(true);
    expect(sameLocation({ path: '/browse', query: {} }, { path: '/browse', query: { tab: 'market' } })).toBe(false);
  });
});
