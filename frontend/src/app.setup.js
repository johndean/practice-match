import { computed, onMounted, onUnmounted, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { Component } from './logic.js';
import MarketMapView from './components/MarketMapView.vue';
import ImageSlot from './components/ImageSlot.vue';
import { useStateRouteSync } from './router/useStateRouteSync';

// Prototype-only props. `prototypeBar` must be false in production.
const props = defineProps({
  prototypeBar: { type: Boolean, default: import.meta.env.VITE_ENVIRONMENT !== 'production' },
  startScreen: { type: String, default: 'gate' },
  startViewport: { type: String, default: 'desktop' },
  // V3 C10: three named palettes — `distinct` (default), `cool`, `colorblind`.
  layerPalette: { type: String, default: 'distinct' }
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
