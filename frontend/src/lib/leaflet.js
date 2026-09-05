// Leaflet loader + basemap tile configuration, ported verbatim from the approved prototype.
// Marker HTML builders moved to src/map/markers.js (Map-engines spec §11.1) — this file and
// src/map/engines/* are the only places that touch Leaflet or window.L.

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
export const BASEMAPS = {
  map: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles \u00a9 Esri"
  },
  satellite: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Imagery \u00a9 Esri, Maxar, Earthstar Geographics"
  }
};

export const LABEL_TILES =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}";
