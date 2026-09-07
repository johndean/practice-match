import { watch } from 'vue';
import type { Router } from 'vue-router';
import { useMe } from '../auth/me';
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
  // Every navigation this composable itself issues to correct the URL — apply()'s settle
  // branch below, AND the state → route watcher's own replace/push further down (review
  // Important 1) — is self-caused: vue-router's `afterEach` fires for it exactly as for any
  // visitor-driven one (confirmed against vue-router 4's source, `pushWithRedirect` →
  // `triggerAfterEach(to, from, failure)` — it runs even when the navigation resolves as a
  // NAVIGATION_DUPLICATED or NAVIGATION_CANCELLED failure; the one path that defers it is a
  // redirecting navigation guard, which this app has none of). Left unguarded, that second
  // `afterEach` call re-runs `apply()` against the URL this composable just wrote, re-derives
  // a patch from it (`routeToPatch`'s `gateToken: ''` for a bare path is correct for a
  // GENUINE bare visit — that contract does not change here), and clobbers whatever the first
  // pass just captured (S2 fix round: a `/verify?token=T` visit lost its `gateToken` the
  // instant the address bar settled to the bare `/verify`).
  //
  // `settleWith` is the ONE place either site issues such a navigation, so both are marked by
  // the SAME flag — and it refuses to issue an OVERLAPPING second one while the first is still
  // in flight. That refusal is load-bearing, not merely tidy: a plain "set the flag, clear it
  // in the afterEach it causes" pattern applied independently at BOTH sites still loses the
  // token, because the two sites' navigations can genuinely overlap. Trace (review Important
  // 1, `router.push('/reset?token=X')` mid-session): apply()'s settle starts a `replace` to
  // the bare `/reset`; because that ALSO changes `state.gate`/`gateToken`, the watcher wakes
  // (it was never asleep here — this is mid-session, not the cold-load path the four A-S2
  // proofs cover) and, reading a not-yet-updated `currentRoute` still holding the old query,
  // computes the SAME bare `/reset` and — if it independently set its own flag and fired its
  // own `replace` — would issue a SECOND navigation to that identical target. vue-router
  // treats the second as superseding the first, cancels it, and STILL fires `afterEach` for
  // the cancelled one (confirmed above) — consuming a boolean meant for the real, still-
  // in-flight second navigation and leaving ITS OWN eventual `afterEach` unguarded, right back
  // to the original bug. Refusing the second call instead of racing it sidesteps this
  // entirely: while a self-caused navigation is in flight, nothing but vue-router's and Vue's
  // own internal microtasks run, so `c.state` cannot have changed — whatever the second caller
  // would navigate to is necessarily the SAME location the first is already headed to, and
  // skipping it changes nothing (identity-keying the flag by target, the other approach
  // considered, does NOT fix this: the review noted the two calls target the same location, so
  // a key would not tell them apart either). The `.finally` remains the second guard, for
  // whatever navigation outcome does not reach `afterEach` at all (the redirect-guard case
  // above, or any future one) — without it a firing that never happened would leave `settling`
  // stuck `true` and silently swallow the next GENUINE navigation (falsified in
  // useStateRouteSync.test.ts with a minimal stub router — the real router cannot produce that
  // outcome to test against).
  let settling = false;
  const settleWith = (navigate: () => Promise<unknown>) => {
    if (settling) return;
    settling = true;
    navigate().finally(() => { settling = false; });
  };
  const apply = (to: { path: string; params: Record<string, unknown>; query: Record<string, unknown> }) => {
    // A-I7's hand-over, executed by A-I8: the principal is read AT THE POINT OF THE CALL, not
    // captured once — `useMe().me.value` changes when the visitor signs in or out, and a
    // captured `null` would refuse every member route for the rest of the session.
    const g = guard(c.state, routeToPatch(to), { me: useMe().me.value });
    pending = g.pending;
    if (needsPatch(c.state, g.apply)) c.setState(g.apply);
    // A stale in-session URL (e.g. a legacy ?tab= link visited via router.push while already
    // signed in and already on the target screen) resolves, via routeToPatch, to a patch
    // that never differs from state — needsPatch is false above, no setState fires, and the
    // state → route watcher (which only reacts to state CHANGES) never gets a chance to
    // settle it. Settle it here instead, by comparing what the current state resolves to
    // against the URL actually navigated to. Skipped while a gate is pending: the URL must
    // stay exactly as the visitor typed it until auth arrives (the watcher's own bail).
    if (!pending) {
      const loc = stateToRoute(c.state);
      if (!sameLocation(loc, to)) settleWith(() => router.replace(loc));
    }
  };
  apply(router.currentRoute.value);
  router.afterEach((to) => {
    if (settling) { settling = false; return; }   // a self-caused settle's own afterEach: not a real navigation to re-apply
    apply(to);
  });
  watch(
    () => ({ auth: c.state.auth, loc: stateToRoute(c.state) }),
    () => {
      if (pending) {
        if (!c.state.auth) return;                  // keep the deep link visible while the gate is shown
        const p = pending; pending = null;
        // The remembered link is permission-checked HERE, not only where it was typed (review
        // round 1, G): the principal is unknowable at the moment a signed-out visitor asks for a
        // route and knowable the moment auth arrives, so this is the only place the matrix can
        // have its say over a deep link. `guard` with `auth` true returns either the patch itself
        // or the `unavailable` gate, and `pending` in neither case — so nothing is remembered a
        // second time and the URL settles instead of being held open forever.
        const g = guard(c.state, p, { me: useMe().me.value });
        if (needsPatch(c.state, g.apply)) {
          const before = stateToRoute(c.state);
          c.setState(g.apply);
          // Return only when applying it MOVED the route: that move is what retriggers this
          // watcher, which then navigates from the settled state rather than a transitional one.
          // A refusal does not move it — the state was already showing a gate and stays on one,
          // so `stateToRoute` is `/` before and after and no retrigger would ever come — and the
          // URL still says the route that was just refused. Fall through and settle it here.
          if (!sameLocation(before, stateToRoute(c.state))) return;
        }
      }
      const loc = stateToRoute(c.state);
      const cur = router.currentRoute.value;
      if (sameLocation(loc, cur)) return;
      settleWith(() => (loc.path === cur.path ? router.replace(loc) : router.push(loc)));
    },
    { deep: true }
  );
}
