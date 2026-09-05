<template>
  <div style="position: absolute; inset: 0; background: #f5f5f5;">
    <div ref="host" style="position: absolute; inset: 0;"></div>

    <div
      v-if="status === 'ready'"
      style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); z-index: 500; display: flex; flex-direction: column; gap: 4px;"
    >
      <button :style="ctrlBtn" aria-label="Zoom in" @click="engine && engine.zoomIn()">
        <img src="/assets/icons/zoom-in-disc.svg" alt="" width="28" height="28" :style="ctrlIcon" />
      </button>
      <button :style="ctrlBtn" aria-label="Zoom out" @click="engine && engine.zoomOut()">
        <img src="/assets/icons/sub-zoom-out-disc.svg" alt="" width="28" height="28" :style="ctrlIcon" />
      </button>
      <button :style="ctrlBtn + 'margin-top: 6px;'" aria-label="Recenter" @click="engine && engine.setView(props.center, props.zoom)">
        <img src="/assets/icons/sub-recenter-disc.svg" alt="" width="28" height="28" :style="ctrlIcon" />
      </button>
    </div>

    <div
      v-if="status !== 'ready'"
      style="position: absolute; inset: 0; display: grid; place-items: center; background: #f5f5f5; text-align: center; padding: 24px; font-family: ProximaNova, Arial, Helvetica, sans-serif;"
    >
      <div v-if="status === 'loading'" style="font-size: 13px; font-weight: 500; color: var(--vf-text);">Loading map…</div>
      <div v-else style="max-width: 320px;">
        <div style="font-family: ProximaNova, Arial, Helvetica, sans-serif; font-size: 17px; font-weight: 700; color: var(--vf-navy);">Map unavailable</div>
        <p style="font-size: 13px; color: var(--vf-text); line-height: 1.6;">The map service could not be reached. Listings and market figures on the right are unaffected, and every data layer remains available as a table.</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { dot, pricePin } from '../map/markers.js';
import { createEngine } from '../map/create';

const props = defineProps({
  practices: { type: Array, default: () => [] }, communities: { type: Array, default: () => [] }, layers: { type: Object, default: () => ({}) },
  valueLayer: { type: String, default: null }, basemap: { type: String, default: 'map' }, activeId: { type: String, default: null },
  onSelect: { type: Function, default: null }, center: { type: Array, default: () => [30.31, -97.75] }, zoom: { type: Number, default: 10 },
  driveCenter: { type: Array, default: null }, resizeKey: { type: String, default: '' }
});
const host = ref(null);
const status = ref('loading');
let engine = null;
const ctrlBtn = 'width: 32px; height: 32px; display: grid; place-items: center; background: none; border: 0; border-radius: 999px; cursor: pointer; padding: 0; filter: drop-shadow(0 1px 3px rgba(0,58,112,.3));';
const ctrlIcon = 'display: block; opacity: .85;';

onMounted(async () => {
  try {
    const e = await createEngine();
    if (!host.value || engine) return;
    await e.mount(host.value, { center: props.center, zoom: props.zoom, basemap: props.basemap, zoomControl: false, scaleControl: true, groups: ['overlay', 'pins'] });
    engine = e;
    status.value = 'ready';
    drawOverlay();
    drawPins();
  } catch { status.value = 'error'; }
});
onBeforeUnmount(() => { if (engine) { engine.destroy(); engine = null; } });

watch([() => props.basemap, status], () => { if (engine) engine.setBase(props.basemap); });
watch([() => props.center && props.center[0], () => props.center && props.center[1], () => props.zoom, status], () => { if (engine && props.center) engine.setView(props.center, props.zoom, true); });
watch(() => props.resizeKey, () => { if (engine) engine.show(); });

// Drive-time rings + community data bubbles
function drawOverlay() {
  if (!engine) return;
  engine.clear('overlay');
  const hub = props.driveCenter || props.center;
  if (props.layers.drive10 && hub) engine.circle(hub, 16000, { fillColor: '#339dde', fillOpacity: 0.16 }, 'overlay');
  if (props.layers.drive5 && hub) engine.circle(hub, 8000, { fillColor: '#003a70', fillOpacity: 0.2 }, 'overlay');
  if (props.valueLayer) {
    props.communities.forEach((c) => {
      const v = c.values[props.valueLayer];
      if (v == null) return;
      const size = 16 + Math.round(v.t * 30);
      engine.marker([c.lat, c.lng], { html: dot(size, v.color), size: [size, size], anchor: [size / 2, size / 2], tooltip: c.name + ' — ' + v.label, interactive: true }, 'overlay');
    });
  }
  if (props.layers.competition) {
    props.communities.forEach((c) => {
      const n = c.vets || 0;
      if (!n) return;
      const size = 8 + Math.min(n, 14);
      engine.marker([c.lat + 0.012, c.lng + 0.012], { html: dot(size, 'rgba(120,86,190,.75)', 'rgba(255,255,255,.9)'), size: [size, size], anchor: [size / 2, size / 2], tooltip: c.name + ' — ' + n + ' veterinary establishments', interactive: true }, 'overlay');
    });
  }
}

// Practice price pins
function drawPins() {
  if (!engine) return;
  engine.clear('pins');
  if (!props.layers.practices) return;
  props.practices.forEach((p) => {
    const active = p.id === props.activeId;
    engine.marker([p.lat, p.lng], { html: pricePin(p.priceLabel, active), size: [72, 26], anchor: [36, 13], zIndexOffset: active ? 1000 : 0, onClick: () => props.onSelect && props.onSelect(p.id) }, 'pins');
  });
}

// MarketMap.jsx's effects 5 (overlay) and 6 (pins), as ONE ordered watcher. React runs
// every effect whose deps changed in declaration order on each commit, so the overlay's
// markers are always re-added to Leaflet's shared markerPane before the price pins and the
// pins therefore paint on top. Two separate Vue watchers cannot promise that: they are
// queued in the order their props are written during the parent's re-render (the design
// template lists `practices` before `communities`), which put the pins first and let the
// community bubbles repaint over them.
watch(
  [() => props.communities, () => props.layers.drive5, () => props.layers.drive10, () => props.layers.competition, () => props.valueLayer, () => props.driveCenter && props.driveCenter[0],
    () => props.practices, () => props.activeId, () => props.layers.practices, status],
  () => { drawOverlay(); drawPins(); },
  { deep: true }
);
</script>
