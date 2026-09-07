import { router } from './router/routes';
import './styles/tokens.css';
import './styles/global.css';
import { useMe } from './auth/me';
import { bootstrap } from './bootstrap';

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
// `.then`, not top-level await: Vite's default build target is `modules` (es2020), where esbuild
// refuses top-level await outright.
void useMe().load().catch(() => null).then(() => bootstrap(router, '#app'));
