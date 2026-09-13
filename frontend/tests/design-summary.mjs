// The design-fixture stub for the metro SUMMARY endpoint (Task SNAP; ruling D-C50 as revised,
// 2026-09-12), in `design-boundaries.mjs`'s own shape and for exactly the same reason.
//
// Two approved states open the Market snapshot strip, and with the `market` adapter present the
// app prints what `GET /api/markets/{cbsa}/summary` answered and nothing else — so the oracle has
// to ANSWER, through the success path, with the DESIGN's own distribution. It is DERIVED from the
// design's own `summarySet()`, which is itself measured over the polygons `areaSet` draws, so the
// reference (no adapter, `summarySet()` directly) and the app (adapter, this) describe ONE
// distribution: one implementation quantiles the design's figures and this reads it out of the
// exported class rather than repeating it.
//
// `summarySet` therefore runs against the design's OWN `P` — the module-level fixture array
// `logic.js` exports — because the app's own boot has by then replaced `P` in the BROWSER, not in
// this Node process. That is the point: the oracle's answer is the design's, whatever the app's
// listings happen to be.
import { Component } from '../src/logic.js';

/** The design's own summary rows, keyed by layer. */
export function designSummarySet() {
  return new Component({}).summarySet();
}

// `app.api.market.SHADING`, `BOUNDARY_METRIC` and `UNIT`, exactly as `design-boundaries.mjs`
// carries them — `tests/census/test_design_shading_labels.py` pins the design against the same
// source, so a geography that moves on the server fails there rather than silently here.
const LEVEL = { income: '140', growth: '160', econ: '050', households: '140', pets: '140', competition: '860' };
const UNIT = { income: 'usd', econ: 'usd', growth: 'pct', households: 'count', pets: 'count', competition: 'count' };
const SOURCE = { income: 'acs5', growth: 'acs5', econ: 'cbp', households: 'acs5', pets: 'acs5', competition: 'zbp' };
const TIGER = 'Boundaries: U.S. Census Bureau, TIGER/Line Cartographic Boundary Files 2023';
const ACS5 = 'Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023';
const ACS5_PRIOR = 'Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2014–2018';
const CBP = 'Source: U.S. Census Bureau, County Business Patterns, 2022';
const ZBP = 'Source: U.S. Census Bureau, ZIP Code Business Patterns, 2022';

/**
 * That distribution in the endpoint's own shape. `state`, the vintages and the attribution are the
 * values the real route sends for a cleared layer; the FIGURES are the design's.
 *
 * `count` is the design's own polygon count for that layer's geography and `no_data` is the rest,
 * so the route's partition (`count == with_value + suppressed + no_data`) holds here too — a stub
 * that broke it would let a reader of `with_value` alone pass a gate the real route would fail.
 * `suppressed` is 0: the design's boundary fixture carries no suppressed polygon at all.
 * `competition` answers with NOTHING — the fixture holds no ZCTAs — which is exactly what
 * `areaSet('competition')` gives the reference, and it is what puts A21.2n/o's "no value and no
 * bars" posture inside an approved state.
 */
export function designSummaryBody(cbsa = '12420') {
  const rows = designSummarySet();
  const design = new Component({});
  return JSON.stringify({
    cbsa_geoid: cbsa,
    boundary_vintage: '2023',
    attribution: [TIGER, ACS5, ACS5_PRIOR, CBP, ZBP],
    layers: Object.keys(rows).map((k) => {
      const count = design.areaSet(k).features.length;
      return {
        layer: k, summary_level: LEVEL[k], geo_label: rows[k].geo_label, unit: UNIT[k], state: 'enabled',
        count, with_value: rows[k].with_value, suppressed: 0, no_data: count - rows[k].with_value,
        median: rows[k].median, quantiles: rows[k].quantiles,
        value_vintage: SOURCE[k] === 'acs5' ? '2019–2023' : '2022',
        source_dataset: SOURCE[k]
      };
    })
  });
}
