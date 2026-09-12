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
import { createEngine } from '../map/create';
import { publish } from '../map/viewport';

const props = defineProps({
  practices: { type: Array, default: () => [] }, communities: { type: Array, default: () => [] },
  // A24: the drawable FeatureCollection `md.areas` produces — colour, label and tip per feature,
  // all decided in logic.js. `communities` STAYS: the design's own fixture path derives the
  // figures from it, so a change to it IS a change to the polygons.
  areas: { type: Object, default: null },
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
// The bbox wiring (2026-09-12). `GET /api/markets/{cbsa}/boundaries` takes a `bbox` and the
// adapter never sent one, so it always asked for the whole metro envelope — every screen paying
// for the whole of New York when it can see a fifth of it. This component holds the only map, so
// it is the only thing that can say what the member is looking at; `src/map/viewport.ts` carries
// it to `src/market/boundaries.ts`. Measured: New York's first view is 7,470 tracts against the
// 5,935 of its own CBSA envelope at the design's smaller preview size — the box is not a
// shortcut around a cap (the caps were re-measured for tracts the same day), it is how the
// answer stays the size of the screen.
//
// `onMove` is the engine's own `moveend zoomend` subscription — the events Leaflet fires when
// the map has SETTLED, which is the only view worth asking the API about.
let offMove = null;
// A32 (2026-09-12): the next publish is a PROGRAMMATIC recentre's, and must notify even if the
// snapped box is where it already was. A metro change sets a new centre and issues no boundary
// request of its own — `setMarket` marks the shading pending and waits for the settled-view
// listener — and two metro centres can snap to the same 1/8-tile cell, 32 CSS px at zoom 10; the
// map would then sit on `mdAreas: null` for ever, with no request in flight and nothing that
// would ever make one. Armed by the recentre watcher and spent by the `moveend` Leaflet fires for
// that `setView`, so a USER pan — which arms nothing — keeps the module's "same box, say nothing"
// rule exactly as it was.
let recentring = false;
function publishViewport() {
  if (!engine) return;
  const b = engine.getBounds();
  if (!b) return;
  const force = recentring;
  recentring = false;
  publish({ w: b[0][1], s: b[0][0], e: b[1][1], n: b[1][0], zoom: engine.getZoom() }, { force });
}

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
    offMove = e.onMove(publishViewport);
    publishViewport();
    // The merged watcher below has `status` among its deps, so flipping it here IS the initial
    // draw — exactly MarketMapV3.jsx's shape, whose effects run at mount, bail on
    // `!mapRef.current`, and run once when status flips. Calling drawOverlay()/drawPins()
    // here as well (the V2 shape this file carried) built every layer twice per mount.
    status.value = 'ready';
  } catch { status.value = 'error'; }
});
// A torn-down map leaves NO box behind: `null` is how the adapter is told there is nothing to
// shade, rather than being left holding the last view of a map that no longer exists.
onBeforeUnmount(() => {
  if (offMove) { offMove(); offMove = null; }
  if (engine) { engine.destroy(); engine = null; publish(null); }
});

watch([() => props.basemap, status], () => { if (engine) engine.setBase(props.basemap); });
watch([() => props.center && props.center[0], () => props.center && props.center[1], () => props.zoom, () => props.recenterKey, status], (now, was) => {
  if (!engine || !props.center) return;
  // The flag follows the VIEW, not the watcher. `recenterKey` and `status` are dependencies too,
  // and `resetView` bumps the key to re-apply the metro's own centre and zoom — on a map the
  // member has not moved that is a setView to where the map already is, and forcing a
  // notification for it would buy six boundary requests (twelve on a wide screen) for a box that
  // has not changed. A bump AFTER a pan moves the box and notifies on its own merits; a bump
  // after no pan has nothing to reload. `was` is only undefined if this ever became an immediate
  // watcher, and not arming is the conservative answer there too.
  if (was && (now[0] !== was[0] || now[1] !== was[1] || now[2] !== was[2])) recentring = true;
  engine.setView(props.center, props.zoom, true);
});
watch(() => props.resizeKey, () => { if (engine) engine.show(); });

// C7 drive-time ring + A24 community boundary shading.
function drawOverlay() {
  if (!engine) return;
  engine.clear('overlay');
  if (props.showDrive && props.driveCenter) {
    engine.ring(props.driveCenter, 8000, { color: '#003a70', weight: 1.5, dashArray: '4 4', fill: false, interactive: false }, 'overlay');
  }
  if (!props.activeLayer || !props.areas || !props.areas.features.length) return;
  engine.geoJson(
    props.areas,
    (f) => ({ fillColor: f.properties.color, fillOpacity: 0.5, stroke: false, interactive: true }),
    'overlay',
    (f) => ({ html: f.properties.tip, sticky: true, className: 'rf-tip' }),
    (f) => props.onArea && props.onArea(f.properties.name)
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
// The merged dep list is deliberately a superset of the reference's area effect, so that one
// callback owns both draws; the OVERLAY REBUILD is then gated on the reference's own five
// area-effect deps, compared the way React compares them (`communities` by identity, the rest
// by value). The pins redraw on every trigger, and always after an overlay redraw, so the
// pane order still holds: clearing and refilling the pins group alone moves the pins to the
// end of the shared panes, and a skipped overlay has not moved at all.
//
// A pin or card SELECTION still rebuilds the polygon layer and that cost is the DESIGN's:
// selecting moves `driveCenter` (logic.js:508) and `showDrive` (:707), so the reference re-runs
// its area effect too. Both now carry amendment A25's finite-coordinate test, so selecting a
// listing whose seller withheld the location moves NEITHER — the rebuild is correctly skipped
// and only the pins redraw. What no longer rebuilds the polygon layer is a trigger that leaves
// all six untouched — `practices` and `activeId` (`s.mdSel`, logic.js:361) are the two the
// superset added (review I1, ruling 2026-09-07).
let lastArea = null;
function areaChanged() {
  const next = [props.areas, props.communities, props.activeLayer, props.showDrive, props.driveCenter && props.driveCenter[0], status.value];
  const changed = lastArea === null || next.some((d, i) => !Object.is(d, lastArea[i]));
  lastArea = next;
  return changed;
}

watch(
  [() => props.areas, () => props.communities, () => props.activeLayer, () => props.showDrive, () => props.driveCenter && props.driveCenter[0],
    () => props.practices, () => props.activeId, status],
  () => { if (areaChanged()) drawOverlay(); drawPins(); },
  { deep: true }
);
</script>
