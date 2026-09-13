// Leaflet loader + marker renderers, ported verbatim from the approved prototype.
// Marker HTML is intentionally inline-styled: Leaflet divIcons live outside the app
// stylesheet scope, so the approved values must travel with the markup.

// Leaflet is bundled from npm (same 1.9.4 the prototype loaded from unpkg) so
// production has no third-party runtime script dependency. Same exported API.
import * as Leaflet from "leaflet";
import "leaflet/dist/leaflet.css";

export function loadLeaflet() {
  if (!window.L) window.L = Leaflet;
  return Promise.resolve(window.L);
}

// Esri basemaps. NOTE: the OSM Foundation tile servers were rejected during design —
// their usage policy blocks embedded application traffic and returns 403 placeholder
// tiles. Keep attribution visible (see the Census Data Source Specification).
//
// A35 (ruling D-C52, 2026-09-13): `maxNativeZoom` is the last level each SERVICE is actually
// cached to, not a display limit. Esri publishes the gray Canvas basemaps to Level 16 in North
// America and answers HTTP 200 with a 2,521-byte "Map data not yet available" JPEG past it;
// World_Imagery is real to z19 everywhere probed (0.3 m, Esri's published US floor) and deeper in
// some metros, which is not knowable client-side. The satellite credit is the service's own
// current `copyrightText`, taken verbatim — it names Vantor where this file used to say Maxar.
export const BASEMAPS = {
  map: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    maxNativeZoom: 16,
    attribution: "Tiles \u00a9 Esri"
  },
  satellite: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    maxNativeZoom: 19,
    attribution: "Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community"
  }
};

export const LABEL_TILES =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}";
