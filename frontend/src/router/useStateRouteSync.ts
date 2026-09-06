import { watch } from 'vue';
import type { Router } from 'vue-router';
import { guard, needsPatch, routeToPatch, sameLocation, stateToRoute, type RoutedState } from './sync';

interface StatefulComponent { state: RoutedState; setState(patch: Partial<RoutedState>): void }

// Route → state first (so a deep link is honoured before the state → route watcher can
// rewrite the URL), then state → route. A member route requested while signed out shows
// the gate, keeps the URL, and is applied the moment the fixture sign-in flips auth.
//
// The state → route side is ONE watcher, not two. It used to be an `auth` watcher (which
// cleared `pending` and reapplied it) plus a separate route watcher (which bailed `if
// (pending) return`, trusting the auth watcher to have already cleared it). That relied on
// the auth watcher always running first — but both belong to the same component, so Vue's
// scheduler runs them in TRIGGER order, not registration order, and dc-logic.js's
// `setState()` is `Object.assign(state, patch)`, which sets keys in the patch object's own
// order. The real signIn() pattern is `{ screen: "browse", formError: "", auth: true }` —
// `screen` before `auth` — so the route watcher was triggered (and ran) first, while
// `pending` was still set, and bailed permanently (a same-value reapply of `pending`
// afterwards never re-triggers anything, so the bail was never revisited).
// One watcher, tracking both `auth` and the computed route, closes that gap: whichever
// property changes, the same callback runs, consumes `pending` the instant auth is true,
// and — if applying it actually changed the state — returns to let the reactive retrigger
// recompute the ROUTE from the settled state (never a transitional one); if applying it was
// a no-op (the state already agreed, e.g. Browse, where V3 has nothing left to disagree
// about), it falls through and navigates immediately, since no further retrigger would ever
// come.
export function useStateRouteSync(c: StatefulComponent, router: Router): void {
  let pending: Partial<RoutedState> | null = null;
  const apply = (to: { path: string; params: Record<string, unknown>; query: Record<string, unknown> }) => {
    const g = guard(c.state, routeToPatch(to));
    pending = g.pending;
    if (needsPatch(c.state, g.apply)) c.setState(g.apply);
  };
  apply(router.currentRoute.value);
  router.afterEach((to) => apply(to));
  watch(
    () => ({ auth: c.state.auth, loc: stateToRoute(c.state) }),
    () => {
      if (pending) {
        if (!c.state.auth) return;                  // keep the deep link visible while the gate is shown
        const p = pending; pending = null;
        if (needsPatch(c.state, p)) { c.setState(p); return; }   // let the settled state retrigger this watcher
      }
      const loc = stateToRoute(c.state);
      const cur = router.currentRoute.value;
      if (sameLocation(loc, cur)) return;
      if (loc.path === cur.path) router.replace(loc); else router.push(loc);
    },
    { deep: true }
  );
}
