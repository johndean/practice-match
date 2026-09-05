<template>
  <div style="position: absolute; inset: 0; background: #f5f5f5;">
    <div ref="host" style="position: absolute; inset: 0;"></div>

    <div
      v-if="status === 'ready'"
      style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); z-index: 500; display: flex; flex-direction: column; gap: 4px;"
    >
      <button :style="ctrlBtn" aria-label="Zoom in" @click="map && map.zoomIn()">
        <img src="/assets/icons/zoom-in-disc.svg" alt="" width="28" height="28" :style="ctrlIcon" />
      </button>
      <button :style="ctrlBtn" aria-label="Zoom out" @click="map && map.zoomOut()">
        <img src="/assets/icons/sub-zoom-out-disc.svg" alt="" width="28" height="28" :style="ctrlIcon" />
      </button>
      <button :style="ctrlBtn + 'margin-top: 6px;'" aria-label="Recenter" @click="map && map.setView(props.center, props.zoom)">
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
import { BASEMAPS, LABEL_TILES, dot, loadLeaflet, pricePin } from '../lib/leaflet.js';

const props = defineProps({
  practices: { type: Array, default: () => [] },
  communities: { type: Array, default: () => [] },
  layers: { type: Object, default: () => ({}) },
  valueLayer: { type: String, default: null },
  basemap: { type: String, default: 'map' },
  activeId: { type: String, default: null },
  onSelect: { type: Function, default: null },
  center: { type: Array, default: () => [30.31, -97.75] },
  zoom: { type: Number, default: 10 },
  driveCenter: { type: Array, default: null },
  resizeKey: { type: String, default: '' }
});

const host = ref(null);
const status = ref('loading');
let map = null;
let tile = null;
let labels = null;
let overlay = null;
let pins = null;

const ctrlBtn = 'width: 32px; height: 32px; display: grid; place-items: center; background: none; border: 0; border-radius: 999px; cursor: pointer; padding: 0; filter: drop-shadow(0 1px 3px rgba(0,58,112,.3));';
const ctrlIcon = 'display: block; opacity: .85;';

onMounted(() => {
  loadLeaflet()
    .then((L) => {
      if (!host.value || map) return;
      map = L.map(host.value, { center: props.center, zoom: props.zoom, zoomControl: false, attributionControl: true });
      tile = L.tileLayer(BASEMAPS[props.basemap].url, { attribution: BASEMAPS[props.basemap].attribution, maxZoom: 18 }).addTo(map);
      // The gray canvas carries almost no labels — Esri's matching reference layer supplies them.
      labels = L.tileLayer(LABEL_TILES, { maxZoom: 18, pane: 'shadowPane' });
      if (props.basemap === 'map') labels.addTo(map);
      overlay = L.layerGroup().addTo(map);
      pins = L.layerGroup().addTo(map);
      L.control.scale({ imperial: true, metric: false, position: 'bottomright' }).addTo(map);
      status.value = 'ready';
      setTimeout(() => map.invalidateSize(), 60);
      drawOverlay();
      drawPins();
    })
    .catch(() => { status.value = 'error'; });
});

onBeforeUnmount(() => {
  if (map) { map.remove(); map = null; }
});

watch([() => props.basemap, status], () => {
  const L = window.L;
  if (!L || !map || !tile) return;
  const cfg = BASEMAPS[props.basemap] || BASEMAPS.map;
  tile.setUrl(cfg.url);
  if (labels) {
    if (props.basemap === 'map') labels.addTo(map);
    else map.removeLayer(labels);
  }
  tile.options.attribution = cfg.attribution;
  if (map.attributionControl._update) map.attributionControl._update();
});

watch([() => props.center && props.center[0], () => props.center && props.center[1], () => props.zoom, status], () => {
  if (!map || !props.center) return;
  map.setView(props.center, props.zoom, { animate: true });
});

watch(() => props.resizeKey, () => {
  if (!map) return;
  setTimeout(() => map.invalidateSize(), 80);
});

// Drive-time rings + community data bubbles
function drawOverlay() {
  const L = window.L;
  if (!L || !map || !overlay) return;
  overlay.clearLayers();
  const hub = props.driveCenter || props.center;

  if (props.layers.drive10 && hub) {
    L.circle(hub, { radius: 16000, stroke: false, fillColor: '#339dde', fillOpacity: 0.16, interactive: false }).addTo(overlay);
  }
  if (props.layers.drive5 && hub) {
    L.circle(hub, { radius: 8000, stroke: false, fillColor: '#003a70', fillOpacity: 0.2, interactive: false }).addTo(overlay);
  }

  if (props.valueLayer) {
    props.communities.forEach((c) => {
      const v = c.values[props.valueLayer];
      if (v == null) return;
      const size = 16 + Math.round(v.t * 30);
      L.marker([c.lat, c.lng], {
        icon: L.divIcon({ html: dot(size, v.color), className: '', iconSize: [size, size], iconAnchor: [size / 2, size / 2] }),
        interactive: true
      })
        .bindTooltip(c.name + ' — ' + v.label, { direction: 'top', offset: [0, -6] })
        .addTo(overlay);
    });
  }

  if (props.layers.competition) {
    props.communities.forEach((c) => {
      const n = c.vets || 0;
      if (!n) return;
      const size = 8 + Math.min(n, 14);
      L.marker([c.lat + 0.012, c.lng + 0.012], {
        icon: L.divIcon({ html: dot(size, 'rgba(120,86,190,.75)', 'rgba(255,255,255,.9)'), className: '', iconSize: [size, size], iconAnchor: [size / 2, size / 2] }),
        interactive: true
      })
        .bindTooltip(c.name + ' — ' + n + ' veterinary establishments', { direction: 'top', offset: [0, -6] })
        .addTo(overlay);
    });
  }
}

// Practice price pins
function drawPins() {
  const L = window.L;
  if (!L || !map || !pins) return;
  pins.clearLayers();
  if (!props.layers.practices) return;
  props.practices.forEach((p) => {
    const active = p.id === props.activeId;
    L.marker([p.lat, p.lng], {
      icon: L.divIcon({ html: pricePin(p.priceLabel, active), className: '', iconSize: [72, 26], iconAnchor: [36, 13] }),
      zIndexOffset: active ? 1000 : 0
    })
      .on('click', () => props.onSelect && props.onSelect(p.id))
      .addTo(pins);
  });
}

watch(
  [
    () => props.communities,
    () => props.layers.drive5,
    () => props.layers.drive10,
    () => props.layers.competition,
    () => props.valueLayer,
    () => props.driveCenter && props.driveCenter[0],
    status
  ],
  drawOverlay,
  { deep: true }
);

watch([() => props.practices, () => props.activeId, () => props.layers.practices, status], drawPins, { deep: true });
</script>
