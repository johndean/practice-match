import { router } from './router/routes';
import './styles/tokens.css';
import './styles/global.css';
import { useMe } from './auth/me';
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
// the design's fixtures being swapped underneath them. `loadListings` never rejects: a refusal
// (the anonymous 401 at the gate), an outage or a deadline leaves the design's fixtures in place
// and the app mounts on them.
//
// `.then`, not top-level await: Vite's default build target is `modules` (es2020), where esbuild
// refuses top-level await outright.
void Promise.all([
  useMe().load().catch(() => null),
  loadListings(globalThis.fetch.bind(globalThis), P as unknown as Practice[], MARKETS as unknown as Markets)
]).then(() => bootstrap(router, '#app'));
