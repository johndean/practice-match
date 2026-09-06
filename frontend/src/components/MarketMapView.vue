<template>
  <div style="position: absolute; inset: 0; background: #f5f5f5;">
    <div ref="host" style="position: absolute; inset: 0;"></div>

    <div
      v-if="status === 'ready'"
      style="position: absolute; right: 12px; top: 16px; z-index: 500; display: flex; flex-direction: column; gap: 4px;"
    >
      <div style="display: flex; flex-direction: column; background: #fff; border: 1px solid #d4dde5; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,58,112,.16); width: 132px;">
        <div v-if="props.onBasemap" style="display: flex; padding: 3px; gap: 2px;">
          <button
            v-for="k in BASEMAP_KEYS"
            :key="k"
            :aria-pressed="props.basemap === k"
            :style="basemapTabStyle(k)"
            @click="props.onBasemap(k)"
          >{{ k === 'map' ? 'Map' : 'Satellite' }}</button>
        </div>
        <span v-if="props.onBasemap" style="height: 1px; background: #e6e6e6;"></span>
        <div style="display: flex;">
          <button :style="stackBtn" aria-label="Zoom in" @click="engine && engine.zoomIn()">+</button>
          <span style="width: 1px; background: #e6e6e6;"></span>
          <button :style="stackBtn" aria-label="Zoom out" @click="engine && engine.zoomOut()">−</button>
        </div>
      </div>
    </div>

    <div
      v-if="status !== 'ready'"
      style="position: absolute; inset: 0; display: grid; place-items: center; background: #f5f5f5; text-align: center; padding: 24px; font-family: ProximaNova, Arial, Helvetica, sans-serif;"
    >
      <div v-if="status === 'loading'" style="font-size: 13px; font-weight: 500; color: #494949;">Loading map…</div>
      <div v-else style="max-width: 320px;">
        <div style="font-size: 17px; font-weight: 700; color: #003a70;">Map unavailable</div>
        <p style="font-size: 13px; color: #494949; line-height: 1.6;">The map service could not be reached. Listings on the right are unaffected, and every market layer is still readable as a table in Market snapshot.</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { practiceCallout, practicePin } from '../map/markers.js';
import { MOSAIC_STEP, mosaicBbox, mosaicCells } from '../map/mosaic.js';
import { createEngine } from '../map/create';

const props = defineProps({
  practices: { type: Array, default: () => [] }, communities: { type: Array, default: () => [] },
  activeLayer: { type: String, default: null }, basemap: { type: String, default: 'map' },
  onBasemap: { type: Function, default: null }, activeId: { type: String, default: null },
  onSelect: { type: Function, default: null }, onArea: { type: Function, default: null },
  center: { type: Array, default: () => [30.31, -97.75] }, zoom: { type: Number, default: 10 },
  driveCenter: { type: Array, default: null }, showDrive: { type: Boolean, default: false },
  resizeKey: { type: String, default: '' }, recenterKey: { type: Number, default: 0 }
});
const host = ref(null);
const status = ref('loading');
let engine = null;

const BASEMAP_KEYS = ['map', 'satellite'];
const stackBtn = 'width: auto; height: 32px; display: grid; place-items: center; padding: 0; background: none; border: 0; cursor: pointer; font-family: ProximaNova, Arial, Helvetica, sans-serif; font-size: 17px; font-weight: 500; color: #003a70; line-height: 1; flex: 1;';
const basemapTabStyle = (k) =>
  'flex: 1; height: 28px; border: 0; border-radius: 5px; cursor: pointer; font-family: ProximaNova, Arial, Helvetica, sans-serif; font-size: 12px; font-weight: 500; line-height: 1; color: ' +
  (props.basemap === k ? '#003a70' : '#7a8590') + '; background: ' + (props.basemap === k ? '#deecf7' : 'transparent') + ';';

onMounted(async () => {
  try {
    const e = await createEngine();
    if (!host.value || engine) return;
    // C11: zoomControl:false, attributionControl:true (attribution is legally load-bearing),
    // and NO scale control — Leaflet pins it bottom-right, directly under V3's Layers button.
    await e.mount(host.value, { center: props.center, zoom: props.zoom, basemap: props.basemap, zoomControl: false, scaleControl: false, groups: ['overlay', 'pins'] });
    engine = e;
    // The merged watcher below has `status` among its deps, so flipping it here IS the initial
    // draw — exactly MarketMapV3.jsx's shape, whose effects run at mount, bail on
    // `!mapRef.current`, and run once when status flips. Calling drawOverlay()/drawPins()
    // here as well (the V2 shape this file carried) built every layer twice per mount.
    status.value = 'ready';
  } catch { status.value = 'error'; }
});
onBeforeUnmount(() => { if (engine) { engine.destroy(); engine = null; } });

watch([() => props.basemap, status], () => { if (engine) engine.setBase(props.basemap); });
watch([() => props.center && props.center[0], () => props.center && props.center[1], () => props.zoom, () => props.recenterKey, status], () => { if (engine && props.center) engine.setView(props.center, props.zoom, true); });
watch(() => props.resizeKey, () => { if (engine) engine.show(); });

// C7 drive-time ring + C5 community mosaic shading.
function drawOverlay() {
  if (!engine) return;
  engine.clear('overlay');
  if (props.showDrive && props.driveCenter) {
    engine.ring(props.driveCenter, 16000, { color: '#003a70', weight: 1.5, dashArray: '4 4', fill: false, interactive: false }, 'overlay');
  }
  if (!props.activeLayer || !props.communities.length) return;
  const bbox = mosaicBbox(props.communities);
  mosaicCells(props.communities, bbox, MOSAIC_STEP).forEach(({ site, bounds }) => {
    const v = site.values[props.activeLayer];
    if (v == null) return;
    engine.rectangle(bounds, { fillColor: v.color, fillOpacity: 0.5, stroke: false, interactive: true }, 'overlay',
      { html: tipHtml(site, v), sticky: true, className: 'rf-tip' },
      () => props.onArea && props.onArea(site.name));
  });
}

function tipHtml(site, v) {
  return (
    '<div style="font-family:ProximaNova,Arial,Helvetica,sans-serif;min-width:150px">' +
      '<div style="font-size:12.5px;font-weight:800;color:#003a70">' + site.name + '</div>' +
      '<div style="font-size:11px;color:#494949;margin-top:3px">' + (site.metricName || '') + '</div>' +
      '<div style="font-size:15px;font-weight:800;color:#003a70;margin-top:1px">' + v.label + '</div>' +
      '<div style="font-size:10px;color:#767676;margin-top:5px">' + (site.sourceNote || '') + '</div>' +
    '</div>'
  );
}

// C6 practice pins: the selected practice's callout stays open on the map, and the map pans
// just far enough to bring both pin and callout inside the viewport.
function drawPins() {
  if (!engine) return;
  engine.clear('pins');
  props.practices.forEach((p) => {
    const selected = p.id === props.activeId;
    const handle = engine.marker([p.lat, p.lng], {
      html: practicePin(p.priceLabel, selected), size: [78, 34], anchor: [39, 34],
      zIndexOffset: selected ? 1000 : 0, keyboard: true, title: p.name + ' — ' + p.priceLabel,
      tooltip: { html: practiceCallout(p), direction: 'top', offset: [0, selected ? -22 : -34], className: 'rf-callout', permanent: selected, opacity: 1 },
      onClick: () => props.onSelect && props.onSelect(p.id)
    }, 'pins');
    if (selected) {
      handle.openTooltip();
      engine.panInside([p.lat, p.lng], [48, 110]);
    }
  });
}

// MarketMapV3.jsx's area effect and pin effect, as ONE ordered watcher. React runs every
// effect whose deps changed in declaration order on each commit, so the overlay's layers are
// always re-added to Leaflet's shared panes before the practice pins and the pins therefore
// paint on top. Two separate Vue watchers cannot promise that: they are queued in the order
// their props are written during the parent's re-render (the design template lists
// `practices` before `communities`), which put the pins first and let the shading repaint
// over them.
//
// The merged dep list is deliberately a superset of the reference's area effect: the overlay
// now also redraws when only `practices` or `activeId` change, which React would not do.
// That over-trigger is the price of the guarantee — clearing and re-adding both groups in
// one callback is the only way to fix their relative pane order — and it is safe because
// both draws are idempotent full rebuilds of their own layer group.
watch(
  [() => props.communities, () => props.activeLayer, () => props.showDrive, () => props.driveCenter && props.driveCenter[0],
    () => props.practices, () => props.activeId, status],
  () => { drawOverlay(); drawPins(); },
  { deep: true }
);
</script>
