import { can } from '../auth/can';
import type { Me } from '../auth/me';
import type { Permission } from '../auth/permissions';

export type Screen = 'gate' | 'browse' | 'detail' | 'requests' | 'seller' | 'admin';
export interface RoutedState { screen: string; detailId?: string; adminTab?: string; gate?: string; auth?: boolean; gateToken?: string }
export interface RouteTarget { path: string; query: Record<string, string> }
interface RouteLike { path: string; params: Record<string, unknown>; query: Record<string, unknown> }

const ADMIN_TABS = ['users', 'listings', 'activity', 'data'] as const;

// The five account pages (Task S2): each is a gate sub-state, not its own screen — the gate
// column is what varies. Kept as one bare-path table both ways so a route added here can
// never drift between the route -> state and state -> route directions.
const GATE_ROUTES: Record<string, string> = { '/signup': 'signup', '/forgot': 'forgot', '/verify': 'verify', '/reset': 'reset', '/accept-invite': 'invite' };
const GATE_PATHS: Record<string, string> = Object.fromEntries(Object.entries(GATE_ROUTES).map(([p, g]) => [g, p]));

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
    // A token, if any, is captured once into state (gateToken) and never written back to
    // the address bar — every gate value, new or old, maps to its bare path only.
    // `Object.hasOwn` (review Minor 5): `s.gate` is visitor/URL-derived, so an unguarded
    // `GATE_PATHS[s.gate]` would read through `Object.prototype` for a value like
    // `"constructor"` — unreachable today (no code produces such a gate value) but a hazard
    // worth retiring rather than arguing away.
    default: return { path: (s.screen === 'gate' && s.gate && Object.hasOwn(GATE_PATHS, s.gate) ? GATE_PATHS[s.gate] : '') || '/', query: {} };
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
  // `Object.hasOwn`, not `to.path in GATE_ROUTES` (review Minor 5): `to.path` comes straight
  // off the URL, so an unguarded `in` reads through `Object.prototype` for a path like
  // `/constructor`. Every real route starts with `/` and vue-router's own catch-all would
  // 404 anything else first, so this is unreachable today — retired anyway.
  if (Object.hasOwn(GATE_ROUTES, to.path)) return { screen: 'gate', gate: GATE_ROUTES[to.path], gateToken: typeof to.query.token === 'string' ? to.query.token : '' };
  return { screen: 'gate' };
}

// The ONE route -> permission table (amendment A-I7). Not a `meta.perm` on each route in
// routes.ts: every route renders the same `App` component, so a twin there would be a second
// copy of this and one more thing to drift. The permission is the one the API guards the same
// screen's data with, so the client hides exactly what the server would refuse.
export const ROUTE_PERMS: Record<string, Permission> = { browse: 'page.browse', detail: 'listing.read', requests: 'request.read_own', seller: 'page.seller', admin: 'page.admin' };

// The prototype's go(): a member screen requested while signed out shows the gate
// (sign-in tab) and the request is remembered until auth flips true. With a context, the
// permission matrix has the second say: a signed-in visitor who does not hold the route's
// permission gets the `unavailable` gate instead, and nothing is remembered — there is no
// later moment at which the same account would be allowed in.
//
// FAIL-CLOSED (A-I7.2, review Important 1). The three branches are asked in this order for a
// reason: any screen that is not the gate is a MEMBER route, whether or not ROUTE_PERMS names
// it, so a route added to routes.ts and forgotten here stays behind the sign-in gate rather
// than becoming reachable while signed out. Only the permission CHECK depends on the table.
//
// `ctx` carries the principal and nothing else (A-I7.2, review Minor 1). MARKET_DATA_PUBLIC has
// no bearing on a route permission — no ROUTE_PERMS value is `market.read`, since Browse V3
// (spec D3) is ONE screen guarded by `page.browse` and the market-data COLUMN inside it calls
// `can('market.read', me, { marketDataPublic })` for itself in I8.
export function guard(state: RoutedState & { auth?: boolean }, patch: Partial<RoutedState>, ctx?: { me: Me | null }): { apply: Partial<RoutedState>; pending: Partial<RoutedState> | null } {
  if (!patch.screen || patch.screen === 'gate') return { apply: patch, pending: null };
  if (!state.auth) return { apply: { screen: 'gate', gate: 'signin' } as Partial<RoutedState>, pending: patch };
  const perm = ROUTE_PERMS[patch.screen];
  if (ctx && perm && !can(perm, ctx.me)) return { apply: { screen: 'gate', gate: 'unavailable' } as Partial<RoutedState>, pending: null };   // A-I7: no context -> the prototype's rule
  return { apply: patch, pending: null };
}

// Task ADMIN-GATE (D-C53, 2026-09-13): the same question, asked of a screen the STATE has already
// moved to rather than of a route that was requested.
//
// `guard()` above is consulted on the route → state side only, and the design's own header nav
// never goes that way: `go()` sets `state.screen` directly, and the state → route watcher's own
// `router.push` sets `settling`, which is exactly the flag the composable's `afterEach` reads to
// skip `apply()`. So a buyer clicking "VIN Foundation Admin" reached the admin shell with the
// matrix never asked (`admin-tabs-audit.md`, "Router bypass" — the single cause of John's four
// admin screenshots).
//
// It DELEGATES to `guard` rather than re-asking the matrix, so there is exactly one statement of
// what a screen needs: with `auth` true, `guard`'s signed-out branch cannot fire, so the only way
// its answer can be the gate is the permission refusal — which is what makes reading `apply.screen`
// sound here. The signed-out case is deliberately NOT this function's: `go()` already sends a
// signed-out visitor to the sign-in gate, and `apply()` is where a deep link is remembered.
export function refusedScreen(state: RoutedState & { auth?: boolean }, ctx: { me: Me | null }): Partial<RoutedState> | null {
  if (!state.auth || state.screen === 'gate') return null;
  const g = guard(state, { screen: state.screen }, ctx);
  return g.apply.screen === 'gate' ? g.apply : null;
}

export function needsPatch(state: RoutedState, patch: Partial<RoutedState>): boolean {
  return Object.entries(patch).some(([k, v]) => (state as unknown as Record<string, unknown>)[k] !== v);
}

export function sameLocation(a: RouteTarget, b: { path: string; query: Record<string, unknown> }): boolean {
  if (a.path !== b.path) return false;
  const ak = Object.keys(a.query), bk = Object.keys(b.query);
  return ak.length === bk.length && ak.every((k) => String(a.query[k]) === String(b.query[k]));
}
