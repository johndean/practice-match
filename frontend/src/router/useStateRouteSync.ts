import { watch } from 'vue';
import type { Router } from 'vue-router';
import { guard, needsPatch, routeToPatch, sameLocation, stateToRoute, type RoutedState } from './sync';

interface StatefulComponent { state: RoutedState; setState(patch: Partial<RoutedState>): void }

// Route → state first (so a deep link is honoured before the state → route watcher can
// rewrite the URL), then state → route. A member route requested while signed out shows
// the gate, keeps the URL, and is applied the moment the fixture sign-in flips auth.
export function useStateRouteSync(c: StatefulComponent, router: Router): void {
  let pending: Partial<RoutedState> | null = null;
  const apply = (to: { path: string; params: Record<string, unknown>; query: Record<string, unknown> }) => {
    const g = guard(c.state, routeToPatch(to));
    pending = g.pending;
    if (needsPatch(c.state, g.apply)) c.setState(g.apply);
  };
  apply(router.currentRoute.value);
  router.afterEach((to) => apply(to));
  watch(() => c.state.auth, (auth) => {
    if (auth && pending) { const p = pending; pending = null; c.setState(p); }
  });
  watch(
    () => stateToRoute(c.state),
    (loc) => {
      if (pending) return;                       // keep the deep link visible while the gate is shown
      const cur = router.currentRoute.value;
      if (sameLocation(loc, cur)) return;
      if (loc.path === cur.path) router.replace(loc); else router.push(loc);
    },
    { deep: true }
  );
}
