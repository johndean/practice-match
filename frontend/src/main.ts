import { router } from './router/routes';
import './styles/tokens.css';
import './styles/global.css';
import { useMe } from './auth/me';
import { makeAuthAdapter } from './auth/adapter';
import * as api from './auth/api';
import { bootstrap } from './bootstrap';
import { loadListings } from './listings/load';
import type { Markets, Practice } from './listings/load';
// The ported prototype's fixture arrays. They are JavaScript with no declarations of their own,
// so each is cast once, here, at the single boundary where the two worlds meet; the shapes are
// pinned by src/listings/load.test.ts and by the visual gate.
import { MARKETS, P } from './logic.js';

// A5.4 / A-I8.1: `/api/config` and `/api/me` are read BEFORE the app mounts, so `App.vue`'s
// `me` prop is populated on the first render and the approved prototype's `componentDidMount`
// lands the visitor where the account lifecycle says they belong — rather than painting the
// sign-in gate and then moving off it, which the pixel gate would see as a different screen.
//
// The load is CAUGHT and the app mounts anyway. `api.me()` treats only 401 as "signed out" and
// throws for every other status (me.ts says why: a broken API must never be read as a signed-out
// visitor at the CLIENT layer), so an outage would otherwise reject here and leave a blank page —
// strictly worse than the gate, which is the screen an unidentified visitor belongs on. The flag
// half has already fail-closed inside `load()`.
//
// Seed Listings D6: the listings are read in the same breath, and installed into the prototype's
// own `P`/`MARKETS` arrays before the first paint — a member sees the seeded eighteen rather than
// the design's fixtures being swapped underneath them. A refusal (the anonymous 401 at the gate),
// an outage, a deadline and an empty or malformed catalogue all leave the design's fixtures in
// place and the app mounts on them (A-L6.2 (1)).
//
// The listings arm is CAUGHT like the account arm, for the same reason and against the same
// outcome: `applyListings` sits outside `loadListings`' own try, so a malformed row inside an
// otherwise well-formed 200 still throws out of it — and an uncaught rejection here means
// `bootstrap()` never runs and the member gets a blank page instead of the screen they belong on
// (review I2). The fixtures survive that throw too: `applyListings` maps every row before it
// clears anything.
//
// `.then`, not top-level await: Vite's default build target is `modules` (es2020), where esbuild
// refuses top-level await outright.
void Promise.all([
  useMe().load().catch(() => null),
  loadListings(globalThis.fetch.bind(globalThis), P as unknown as Practice[], MARKETS as unknown as Markets).catch(() => null)
]).then(() => {
  // A-L14: Create the auth adapter with the listings loader so it can re-read on interactive
  // sign-in. The loader, practices array, and markets object are passed so the adapter can
  // re-read the catalogue after a member signs in interactively.
  const auth = makeAuthAdapter(
    api,
    useMe(),
    loadListings,
    globalThis.fetch.bind(globalThis),
    P as unknown as Practice[],
    MARKETS as unknown as Markets
  );
  return bootstrap(router, '#app', auth);
});
