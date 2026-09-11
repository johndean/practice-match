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

const LEVEL = { income: '860', growth: '160', econ: '050' };
const LABEL = { income: 'ZIP Code Tabulation Area', growth: 'Place (city/town)', econ: 'County' };
const METRIC = { income: 'median_hh_income', growth: 'population_growth_pct', econ: 'revenue_per_establishment' };

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
const ATTRIBUTION = {
  income: [TIGER, ACS5],
  growth: [TIGER, ACS5, ACS5_PRIOR],
  econ: [TIGER, CBP]
};

/** That collection in the endpoint's own shape. `state`, the two vintages and the attribution are
 *  the values the real endpoint sends for a cleared layer; the FEATURES are the design's. */
export function designBoundariesBody(layer) {
  const key = LEVEL[layer] ? layer : 'income';
  const set = designAreaSet(key);
  return JSON.stringify({
    type: 'FeatureCollection', cbsa_geoid: '12420', layer: key,
    metric_key: METRIC[key],
    summary_level: LEVEL[key], geo_label: LABEL[key],
    unit: key === 'growth' ? 'pct' : 'usd', state: 'enabled',
    boundary_vintage: '2023', value_vintage: key === 'econ' ? '2022' : '2019–2023',
    source_dataset: key === 'econ' ? 'cbp' : 'acs5',
    attribution: ATTRIBUTION[key],
    values_without_geometry: 0,
    features: set.features
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
