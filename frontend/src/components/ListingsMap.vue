<template>
  <div style="position: absolute; inset: 0; background: #f5f5f5;">
    <div ref="host" style="position: absolute; inset: 0;"></div>
    <div
      v-if="status !== 'ready'"
      style="position: absolute; inset: 0; display: grid; place-items: center; background: #f5f5f5; text-align: center; padding: 24px; font-family: ProximaNova, Arial, Helvetica, sans-serif;"
    >
      <div v-if="status === 'loading'" style="font-size: 13px; font-weight: 500; color: var(--color-steel);">Loading map…</div>
      <div v-else style="max-width: 300px;">
        <div style="font-family: ProximaNova, Arial, Helvetica, sans-serif; font-size: 16px; font-weight: 700; color: var(--color-navy);">Map unavailable</div>
        <p style="font-size: 13px; color: var(--color-steel); line-height: 1.5;">The map service could not be reached. Results are still listed on the left, and location filters continue to work.</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { BASEMAPS, LABEL_TILES, clusterIcon, clusterize, loadLeaflet, pill } from '../lib/leaflet.js';

const props = defineProps({
  markers: { type: Array, default: () => [] },
  activeId: { type: String, default: null },
  hoverId: { type: String, default: null },
  onSelect: { type: Function, default: null },
  onClusterClick: { type: Function, default: null },
  center: { type: Array, default: () => [30.31, -97.75] },
  zoom: { type: Number, default: 10 },
  dimmed: { type: Array, default: () => [] },
  resizeKey: { type: String, default: '' }
});

const host = ref(null);
const status = ref('loading');
const z = ref(props.zoom);
let map = null;
let layer = null;

onMounted(() => {
  loadLeaflet()
    .then((L) => {
      if (!host.value || map) return;
      map = L.map(host.value, { center: props.center, zoom: props.zoom, zoomControl: false, attributionControl: true });
      L.tileLayer(BASEMAPS.map.url, { attribution: BASEMAPS.map.attribution, maxZoom: 18 }).addTo(map);
      // The gray canvas carries almost no labels — Esri's matching reference layer supplies them.
      L.tileLayer(LABEL_TILES, { maxZoom: 18, pane: 'shadowPane' }).addTo(map);
      L.control.zoom({ position: 'bottomright' }).addTo(map);
      layer = L.layerGroup().addTo(map);
      map.on('zoomend', () => { z.value = map.getZoom(); });
      status.value = 'ready';
      setTimeout(() => map.invalidateSize(), 60);
      draw();
    })
    .catch(() => { status.value = 'error'; });
});

onBeforeUnmount(() => {
  if (map) { map.remove(); map = null; }
});

function draw() {
  const L = window.L;
  if (!L || !map || !layer) return;
  layer.clearLayers();
  clusterize(props.markers, z.value).forEach((entry) => {
    if (entry.kind === 'cluster') {
      const icon = L.divIcon({ html: clusterIcon(entry.count), className: '', iconSize: [44, 44], iconAnchor: [22, 22] });
      L.marker([entry.lat, entry.lng], { icon })
        .on('click', () => {
          map.setView([entry.lat, entry.lng], Math.max(z.value + 2, 11));
          if (props.onClusterClick) props.onClusterClick(entry.ids);
        })
        .addTo(layer);
    } else {
      const m = entry.m;
      const active = m.id === props.activeId || m.id === props.hoverId;
      const icon = L.divIcon({
        html: pill(m.priceLabel, active, props.dimmed.indexOf(m.id) > -1),
        className: '',
        iconSize: [70, 26],
        iconAnchor: [35, 13]
      });
      L.marker([m.lat, m.lng], { icon, zIndexOffset: active ? 1000 : 0 })
        .on('click', () => props.onSelect && props.onSelect(m.id))
        .addTo(layer);
    }
  });
}

watch([() => props.markers, () => props.activeId, () => props.hoverId, z, status, () => props.dimmed], draw, { deep: true });

watch(() => props.resizeKey, () => {
  if (!map) return;
  setTimeout(() => map.invalidateSize(), 80);
});

watch([() => props.center && props.center[0], () => props.center && props.center[1], () => props.zoom, status], () => {
  if (!map || !props.center) return;
  map.setView(props.center, props.zoom, { animate: true });
});
</script>
