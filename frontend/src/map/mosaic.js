// Community mosaic geometry, ported verbatim from the approved prototype's MarketMapV3.jsx
// (mosaicCells, lines 57-95). Presentation logic, not engine logic, so it lives beside
// markers.js rather than inside an engine.
//
// GEOMETRY NOTE, from the reference's own header: the prototype has no ZCTA boundary file,
// so community areas are approximated as the cells nearest each community's centroid,
// clipped to the metro bounding box. Cells are contiguous and non-overlapping, which is what
// area shading requires, but they are NOT real Census boundaries — the UI labels them
// "approximate community areas". Production loads tiger_cb ZCTA polygons per the Census Data
// Source Specification (Sub-project 3) and drops this approximation.
//
// This is "community mosaic shading" (spec D5). The word "choropleth" is reserved for the
// Census plan's Phase C server-generated tract-level vector tiles, which are a different
// thing at a different granularity.

export const MOSAIC_STEP = 0.0055;
export const BBOX_PAD_LAT = 0.13;
export const BBOX_PAD_LNG = 0.15;

/** MarketMapV3.jsx:239-246 — the metro extent, padded so shading reaches past the outermost community. */
export function mosaicBbox(sites) {
  const lats = sites.map((c) => c.lat);
  const lngs = sites.map((c) => c.lng);
  return {
    minLat: Math.min.apply(null, lats) - BBOX_PAD_LAT,
    maxLat: Math.max.apply(null, lats) + BBOX_PAD_LAT,
    minLng: Math.min.apply(null, lngs) - BBOX_PAD_LNG,
    maxLng: Math.max.apply(null, lngs) + BBOX_PAD_LNG
  };
}

/**
 * Each cell is assigned the class of its nearest community centroid, which yields crisp
 * finite boundaries rather than overlapping discs. This is spatial ASSIGNMENT of existing
 * community data, not interpolation, and not new data.
 */
export function mosaicCells(sites, bbox, step) {
  const out = [];
  for (let lat = bbox.minLat; lat < bbox.maxLat; lat += step) {
    for (let lng = bbox.minLng; lng < bbox.maxLng; lng += step) {
      const cLat = lat + step / 2, cLng = lng + step / 2;
      let best = null, bestD = Infinity;
      for (let i = 0; i < sites.length; i++) {
        const s = sites[i];
        const dLat = s.lat - cLat;
        const dLng = (s.lng - cLng) * Math.cos((cLat * Math.PI) / 180);
        const d = dLat * dLat + dLng * dLng;
        if (d < bestD) { bestD = d; best = s; }
      }
      // Drop cells too far from every community rather than shading empty country.
      if (!best || bestD > 0.016) continue;
      out.push({ site: best, bounds: [[lat, lng], [lat + step, lng + step]] });
    }
  }
  return out;
}
