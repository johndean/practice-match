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
import { clusterIcon, clusterize, pill } from '../map/markers.js';
import { createEngine } from '../map/create';

const props = defineProps({
  markers: { type: Array, default: () => [] }, activeId: { type: String, default: null }, hoverId: { type: String, default: null },
  onSelect: { type: Function, default: null }, onClusterClick: { type: Function, default: null },
  center: { type: Array, default: () => [30.31, -97.75] }, zoom: { type: Number, default: 10 }, dimmed: { type: Array, default: () => [] }, resizeKey: { type: String, default: '' }
});
const host = ref(null);
const status = ref('loading');
const z = ref(props.zoom);
let engine = null;
let offMove = null;

onMounted(async () => {
  try {
    const e = await createEngine();
    if (!host.value || engine) return;
    await e.mount(host.value, { center: props.center, zoom: props.zoom, basemap: 'map', zoomControl: 'bottomright', scaleControl: false, groups: ['layer'] });
    engine = e;
    offMove = e.onMove((_c, zoom) => { z.value = zoom; });
    status.value = 'ready';
    draw();
  } catch { status.value = 'error'; }
});
onBeforeUnmount(() => { if (offMove) offMove(); if (engine) { engine.destroy(); engine = null; } });

function draw() {
  if (!engine) return;
  engine.clear('layer');
  clusterize(props.markers, z.value).forEach((entry) => {
    if (entry.kind === 'cluster') {
      engine.marker([entry.lat, entry.lng], { html: clusterIcon(entry.count), size: [44, 44], anchor: [22, 22],
        onClick: () => { engine.setView([entry.lat, entry.lng], Math.max(z.value + 2, 11)); if (props.onClusterClick) props.onClusterClick(entry.ids); } }, 'layer');
    } else {
      const m = entry.m;
      const active = m.id === props.activeId || m.id === props.hoverId;
      engine.marker([m.lat, m.lng], { html: pill(m.priceLabel, active, props.dimmed.indexOf(m.id) > -1), size: [70, 26], anchor: [35, 13], zIndexOffset: active ? 1000 : 0,
        onClick: () => props.onSelect && props.onSelect(m.id) }, 'layer');
    }
  });
}

watch([() => props.markers, () => props.activeId, () => props.hoverId, z, status, () => props.dimmed], draw, { deep: true });
watch(() => props.resizeKey, () => { if (engine) engine.show(); });
watch([() => props.center && props.center[0], () => props.center && props.center[1], () => props.zoom, status], () => { if (engine && props.center) engine.setView(props.center, props.zoom, true); });
</script>
