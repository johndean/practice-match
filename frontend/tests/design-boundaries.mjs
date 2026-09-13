// The design-fixture stub for the boundary endpoint, in the D6 stub's own shape and for the same
// reason (A-SL2, as re-ruled by A-SL23 (2)).
//
// Thirteen approved states mount a map, and with the `market` adapter present the app draws what
// the API answered and NOTHING else — so the oracle has to ANSWER, through the success path, with
// the design's own polygons. It is DERIVED from the design's own `areaSet`, exactly as
// `design-seller-listings.mjs` is derived from `state.sellerListings` and `design-listings.mjs`
// from `P`, so the reference and the app cannot draw different geometry: ONE implementation
// assigns the design's figures to the design's polygons, and this reads it out of the exported
// class rather than repeating it.
//
// `designAreaSet` therefore runs against the design's OWN `P` — the module-level fixture array
// `logic.js` exports — because the app's own boot has by then replaced `P` in the BROWSER, not in
// this Node process. That is the point: the oracle's answer is the design's, whatever the app's
// listings happen to be.
import { Component, MARKETS } from '../src/logic.js';

/** The design's own raw FeatureCollection for one fill layer. */
export function designAreaSet(layer) {
  return new Component({}).areaSet(layer);
}

// `income` draws the CENSUS TRACT since 2026-09-12; `growth` and `econ` keep their coarser
// geography because growth cannot be computed at tract level across the 2010->2020 boundary
// change (plan D12). `households` and `pets` joined income at the tract and `competition` the
// ZCTA on 2026-09-12 (D-L1) — the design's own fixture carries no ZCTAs at all, so competition's
// answer here is an EMPTY collection, which is exactly what `areaSet('competition')` gives the
// reference: the oracle answers what the design draws, including when that is nothing.
// `app.api.market.SHADING` is the source and
// `tests/census/test_design_shading_labels.py` pins the design against it.
const LEVEL = { income: '140', growth: '160', econ: '050', households: '140', pets: '140', competition: '860' };
const LABEL = { income: 'Census tract', growth: 'Place (city/town)', econ: 'County', households: 'Census tract', pets: 'Census tract', competition: 'ZIP Code Tabulation Area' };
const METRIC = { income: 'median_hh_income', growth: 'population_growth_pct', econ: 'revenue_per_establishment', households: 'households', pets: 'pet_households_est', competition: 'establishments' };

// `dataset_registry.attribution_text`, verbatim from `migrations/017_census_registry.sql` — the
// strings `app/api/market.py` reads out of the registry and never composes, because attribution is
// legally load-bearing. Boundaries first, then the value datasets sorted, exactly as the route
// assembles them (`[tiger_cb] + sorted({source} | {acs5_prior} if growth)`), so `growth` carries
// three and the other two carry two. Nothing in the app reads these; the oracle carries them so
// that Task 11's parity run compares the same SHAPE the live route sends.
const TIGER = 'Boundaries: U.S. Census Bureau, TIGER/Line Cartographic Boundary Files 2023';
const ACS5 = 'Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019\u20132023';
const ACS5_PRIOR = 'Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2014\u20132018';
const CBP = 'Source: U.S. Census Bureau, County Business Patterns, 2022';
const ZBP = 'Source: U.S. Census Bureau, ZIP Code Business Patterns, 2022';
const ATTRIBUTION = {
  income: [TIGER, ACS5],
  growth: [TIGER, ACS5, ACS5_PRIOR],
  econ: [TIGER, CBP],
  households: [TIGER, ACS5],
  pets: [TIGER, ACS5],
  competition: [TIGER, ZBP]
};
// `geo_metric.unit`, per layer — the three counts are counts, and a count served as `usd` or
// `pct` is a wrong reading of the number (`app.api.market.UNIT`).
const UNIT = { income: 'usd', econ: 'usd', growth: 'pct', households: 'count', pets: 'count', competition: 'count' };
const SOURCE = { income: 'acs5', growth: 'acs5', econ: 'cbp', households: 'acs5', pets: 'acs5', competition: 'zbp' };

/**
 * The ground a set of features covers: `[minLng, minLat, maxLng, maxLat]`, or `null` for a
 * collection with no coordinates at all (the design carries no ZCTAs, so `competition` is empty).
 */
function extentOf(features) {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  const walk = (c) => {
    if (typeof c[0] === 'number') { w = Math.min(w, c[0]); e = Math.max(e, c[0]); s = Math.min(s, c[1]); n = Math.max(n, c[1]); return; }
    c.forEach(walk);
  };
  features.forEach((f) => { if (f.geometry && f.geometry.coordinates) walk(f.geometry.coordinates); });
  return Number.isFinite(w) ? [w, s, e, n] : null;
}

function shift(geometry, dx, dy) {
  const walk = (c) => (typeof c[0] === 'number' ? [c[0] + dx, c[1] + dy] : c.map(walk));
  return { ...geometry, coordinates: walk(geometry.coordinates) };
}

/**
 * The design's own polygons, carried to the ground the request ASKED about when they are not
 * already under it.
 *
 * `GET /api/markets/{cbsa}/boundaries` is bbox-scoped and METRO-AGNOSTIC — `_BOUNDARY_SQL`
 * filters on summary level, vintage and `ST_Intersects(geom, bbox)` and never on the CBSA, so the
 * path segment picks the whole-metro fallback box, the cache key and the 404 and nothing else. A
 * member who pans clean off the selected metro therefore keeps getting real polygons, which is
 * the continuity `smoke.spec.ts` asserts and the reason ADAPT-STALE-2's client-side "is this box
 * inside the metro?" guard was withdrawn. A stub that answered the same Austin geometry whatever
 * it was asked could not tell that behaviour from a blank map.
 *
 * TRANSLATED, never invented: it is the design's own `areaSet` geometry, moved so its centre sits
 * at the centre of the box. And only when it has to be — where the design's polygons already
 * INTERSECT the requested box the collection is returned untouched, which is every box any
 * approved state ever looks at (they are all over Austin, which is where the fixture is), so no
 * capture moves. A request with no bbox is the whole metro and is never translated.
 */
function underBox(features, bbox) {
  if (!bbox || !features.length) return features;
  const box = String(bbox).split(',').map(Number);
  if (box.length !== 4 || !box.every(Number.isFinite)) return features;
  const at = extentOf(features);
  if (at === null) return features;
  const [w, s, e, n] = box;
  if (!(w > at[2] || e < at[0] || s > at[3] || n < at[1])) return features;   // already under the box
  const dx = (w + e) / 2 - (at[0] + at[2]) / 2;
  const dy = (s + n) / 2 - (at[1] + at[3]) / 2;
  return features.map((f) => ({ ...f, geometry: f.geometry ? shift(f.geometry, dx, dy) : f.geometry }));
}

/** That collection in the endpoint's own shape. `state`, the two vintages and the attribution are
 *  the values the real endpoint sends for a cleared layer; the FEATURES are the design's, under
 *  the ground `bbox` named (see `underBox`).
 *
 *  @param {string} layer
 *  @param {string | null} bbox the request's own `bbox` parameter, or `null` for the whole metro
 */
export function designBoundariesBody(layer, bbox = null) {
  const key = LEVEL[layer] ? layer : 'income';
  const set = designAreaSet(key);
  return JSON.stringify({
    type: 'FeatureCollection', cbsa_geoid: '12420', layer: key,
    metric_key: METRIC[key],
    summary_level: LEVEL[key], geo_label: LABEL[key],
    unit: UNIT[key], state: 'enabled',
    boundary_vintage: '2023', value_vintage: SOURCE[key] === 'acs5' ? '2019–2023' : '2022',
    source_dataset: SOURCE[key],
    attribution: ATTRIBUTION[key],
    values_without_geometry: 0,
    // The delivery tolerance the route used, in degrees. 0.0 is "the exact outline was served",
    // which is what every metro-zoom viewport measured gets; the route only coarsens when the
    // composed body would otherwise exceed MAX_BODY_BYTES and be refused.
    simplified_deg: 0,
    features: underBox(set.features, bbox)
  });
}

/** `/api/markets`, from the design's OWN market catalogue: the adapter resolves a metro by name
 *  before it asks for a boundary, and the design's default is "Austin, TX". The geoids are the
 *  real CBSA codes for the design's own four metros, so a reader of a captured request sees the
 *  same identifier the live route takes. */
const CBSA = { 'Austin, TX': '12420', 'Sacramento, CA': '40900', 'Orlando, FL': '36740', 'Atlanta, GA': '12060' };

export function designMarketsBody() {
  return JSON.stringify(Object.keys(MARKETS).map((name, i) => ({
    cbsa_geoid: CBSA[name] ?? String(90000 + i),
    name, center: MARKETS[name].center, zoom: MARKETS[name].zoom
  })));
}
