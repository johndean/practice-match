export type Screen = 'gate' | 'browse' | 'detail' | 'requests' | 'seller' | 'admin';
export interface RoutedState { screen: string; detailId?: string; adminTab?: string; gate?: string; auth?: boolean }
export interface RouteTarget { path: string; query: Record<string, string> }
interface RouteLike { path: string; params: Record<string, unknown>; query: Record<string, unknown> }

const ADMIN_TABS = ['users', 'listings', 'activity', 'data'] as const;

export function stateToRoute(s: RoutedState): RouteTarget {
  switch (s.screen) {
    case 'browse': return { path: '/browse', query: {} };
    case 'detail': return { path: `/practices/${s.detailId || 'p1'}`, query: {} };
    case 'requests': return { path: '/requests', query: {} };
    case 'seller': return { path: '/seller', query: {} };
    case 'admin': {
      const tab = s.adminTab || 'users';
      return { path: '/admin', query: tab === 'users' ? {} : { tab } };
    }
    default: return { path: '/', query: {} };
  }
}

function pick<T extends string>(v: unknown, allowed: readonly T[], fallback: T): T {
  return (allowed as readonly string[]).includes(String(v)) ? (v as T) : fallback;
}

export function routeToPatch(to: RouteLike): Partial<RoutedState> {
  // Any legacy ?tab= is ignored: Browse Practices is one screen in V3, so /browse,
  // /browse?tab=market and /browse?tab=listings all land here and the URL settles to
  // /browse without a second navigation. Old links and bookmarks must not 404 or loop.
  if (to.path === '/browse') return { screen: 'browse' };
  if (to.path.startsWith('/practices/') && typeof to.params.id === 'string') return { screen: 'detail', detailId: to.params.id };
  if (to.path === '/requests') return { screen: 'requests' };
  if (to.path === '/seller') return { screen: 'seller' };
  if (to.path === '/admin') return { screen: 'admin', adminTab: pick(to.query.tab, ADMIN_TABS, 'users') };
  return { screen: 'gate' };
}

// The prototype's go(): a member screen requested while signed out shows the gate
// (sign-in tab) and the request is remembered until auth flips true.
export function guard(state: RoutedState & { auth?: boolean }, patch: Partial<RoutedState>): { apply: Partial<RoutedState>; pending: Partial<RoutedState> | null } {
  if (patch.screen && patch.screen !== 'gate' && !state.auth) return { apply: { screen: 'gate', gate: 'signin' } as Partial<RoutedState>, pending: patch };
  return { apply: patch, pending: null };
}

export function needsPatch(state: RoutedState, patch: Partial<RoutedState>): boolean {
  return Object.entries(patch).some(([k, v]) => (state as unknown as Record<string, unknown>)[k] !== v);
}

export function sameLocation(a: RouteTarget, b: { path: string; query: Record<string, unknown> }): boolean {
  if (a.path !== b.path) return false;
  const ak = Object.keys(a.query), bk = Object.keys(b.query);
  return ak.length === bk.length && ak.every((k) => String(a.query[k]) === String(b.query[k]));
}
