import { computed, onMounted, onUnmounted, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { Component } from './logic.js';
import MarketMapView from './components/MarketMapView.vue';
import ImageSlot from './components/ImageSlot.vue';
import * as api from './auth/api';
import { useMe } from './auth/me';
import { useStateRouteSync } from './router/useStateRouteSync';

// Prototype-only props. `prototypeBar` must be false in production.
//
// D-I8-2: `prototypeBar`, `startScreen`, `startViewport` and `startGate` stay DECLARED — the
// design declares them and `tests/app-generated.test.ts` requires this file to declare
// everything the design does — but the app never PASSES the first three. Nothing renders
// App.vue with props (every route renders it bare), so a declaration's default IS what the
// prototype sees, and these defaults are what make the app the app rather than the preview.
const props = defineProps({
  prototypeBar: { type: Boolean, default: import.meta.env.VITE_ENVIRONMENT !== 'production' },
  startScreen: { type: String, default: 'gate' },
  // D-I8-7: the "Mobile view" toggle lived in the jump bar and left with it (A6.1), and no
  // responsive design exists yet, so the prototype's 390×800 phone frame is reached through
  // the URL instead — `?viewport=mobile`. Read once, at setup, because that is when the
  // prototype's own `componentDidMount` consumes it; `useStateRouteSync` then settles the URL
  // to the screen's canonical path, which drops the query and leaves the viewport as it is.
  startViewport: { type: String, default: () => (new URLSearchParams(window.location.search).get('viewport') === 'mobile' ? 'mobile' : 'desktop') },
  // A5.6: the reference reaches a gate state through this (injected by the reference server's
  // `?props=`). The app never passes it — it signs in as a real account instead, and A5.4 maps
  // that account's state to the gate.
  startGate: { type: String, default: '' },
  // V3 C10: three named palettes — `distinct` (default), `cool`, `colorblind`.
  layerPalette: { type: String, default: 'distinct' },
  // A5.1 / A5.3: the real `/api/auth/*` client, as the prototype's `auth` adapter — the seam the
  // design's own Sign in and Sign out handlers call through. The reference and the Claude Design
  // preview pass nothing and keep the design's fixture path, which is what keeps the two targets
  // on the same pixels. `signOut` also clears the loaded account, so the header cannot outlive
  // the session it names. Nothing in the template reads `auth`; only `logic.js` does.
  auth: {
    type: Object,
    default: () => ({ signIn: api.signIn, signOut: () => api.signOut().then(() => useMe().clear()) })
  },
  // A5.4: the signed-in account, or null. `main.ts` awaits `useMe().load()` before
  // `bootstrap()`, so this is populated on the FIRST render and the prototype's
  // `componentDidMount` can put the visitor where the account lifecycle says they belong.
  // `renderVals()` returns its own `me` (the header strings, from state), which wins in `v`
  // below — this prop is read by the prototype's bootstrap, not by the template.
  me: { type: Object, default: () => useMe().me.value }
});

// The approved prototype logic runs verbatim; `state` is made reactive so that
// renderVals() re-evaluates exactly like the original render pass.
const c = new Component(props);
c.state = reactive(c.state);
useStateRouteSync(c, useRouter());
const v = computed(() => ({ ...props, ...c.renderVals() }));
const __s = (x) => (x == null || typeof x === 'boolean' || typeof x === 'object') ? null : String(x);
const __arr = (x) => (Array.isArray(x) ? x : []);

onMounted(() => c.componentDidMount && c.componentDidMount());
onUnmounted(() => c.componentWillUnmount && c.componentWillUnmount());
