import { can } from '../auth/can';
import type { Me } from '../auth/me';
import type { Permission } from '../auth/permissions';

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

// The ONE route -> permission table (amendment A-I7). Not a `meta.perm` on each route in
// routes.ts: every route renders the same `App` component, so a twin there would be a second
// copy of this and one more thing to drift. The permission is the one the API guards the same
// screen's data with, so the client hides exactly what the server would refuse.
export const ROUTE_PERMS: Record<string, Permission> = { browse: 'page.browse', detail: 'listing.read', requests: 'request.read_own', seller: 'page.seller', admin: 'page.admin' };

function permFor(patch: Partial<RoutedState>): Permission | null {
  if (!patch.screen || patch.screen === 'gate') return null;
  // Browse V3 (spec D3): Browse Practices is ONE screen, so the route permission keys on
  // `patch.screen` alone — there is no browseMode to branch on. The market-data column
  // inside the screen checks can('market.read') itself, honouring MARKET_DATA_PUBLIC.
  return ROUTE_PERMS[patch.screen] ?? null;
}

// The prototype's go(): a member screen requested while signed out shows the gate
// (sign-in tab) and the request is remembered until auth flips true. With a context, the
// permission matrix has the second say: a signed-in visitor who does not hold the route's
// permission gets the `unavailable` gate instead, and nothing is remembered — there is no
// later moment at which the same account would be allowed in.
export function guard(state: RoutedState & { auth?: boolean }, patch: Partial<RoutedState>, ctx?: { me: Me | null; marketDataPublic?: boolean }): { apply: Partial<RoutedState>; pending: Partial<RoutedState> | null } {
  const perm = permFor(patch);
  if (!perm) return { apply: patch, pending: null };
  if (!state.auth) return { apply: { screen: 'gate', gate: 'signin' } as Partial<RoutedState>, pending: patch };
  if (ctx && !can(perm, ctx.me, { marketDataPublic: ctx.marketDataPublic })) return { apply: { screen: 'gate', gate: 'unavailable' } as Partial<RoutedState>, pending: null };   // A-I7: no context -> the prototype's rule
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
