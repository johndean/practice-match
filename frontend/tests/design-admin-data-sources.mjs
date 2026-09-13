// The design-fixture stub for the ADMIN DATA SOURCES registry — `design-admin-listings.mjs`'s
// precedent (A-SL2, re-ruled A-SL23 (2)) applied to `admin-data-sources`, Task A38.
//
// `admin-data-sources` is one of CLAUDE.md's thirteen frozen screens and its rows are the design's
// own `sets.data.rows`, all five of them as A38.4/A38.5 leave them — the pet-ownership and
// practice-location rows now carrying no action, because neither of their buttons called anything
// (controller ruling 18). With `frontend/src/admin/data_sources.ts`'s adapter the app's default,
// the frozen capture has to answer through the SAME success path `design-admin-listings.mjs`
// already proved for `admin-listings`: a REAL body of `GET /api/admin/data-sources`.
//
// DERIVED, never hand-copied: the five rows come straight off `adminVals()`'s own COMPUTED cells
// (`main`, `sub`, `pill`, `pillStyle`, and each action's `label`/`style`), not retyped here. This
// file touches only `logic.js` — no TypeScript module, on either side of the D6 stub — exactly as
// `design-admin-listings.mjs`, `design-seller-listings.mjs` and `design-wizard-draft.mjs` do, so a
// `DesignDataSourceRow` carries whole STYLE STRINGS rather than a tone name this file would have
// had to re-derive by importing `admin/data_sources.ts`'s own `cell()`/`A()` back into itself.
//
// `license_status` is derived from the row's OWN pill text, lower-cased: the design prints exactly
// the three words `dataset_registry.license_status`'s CHECK constraint allows — Cleared,
// Unresolved, Blocked — so the fixture speaks the registry's own vocabulary without a table here
// mapping one to the other. That is what makes the BADGE one rule rather than two: `notCleared`
// counts these rows exactly as it counts real ones, and its answer over the design's five is 2,
// which is the design's own literal count for this tab.
//
// The real endpoint answers a BARE ARRAY, ordered by `dataset_key` (`app/api/admin_data_sources.py
// ::list_data_sources` — no envelope, no cursor, the whole registry in one body), so this body is
// an array too. `toDataSourceRows` reads this shape verbatim: `dataset`/`datasetSub` become the
// "Dataset" cell's `main`/`sub`, `source`/`sourceSub` the "Source and license" cell's,
// `pill`/`pillStyle` are copied onto the status cell as they stand, and each action's own `style`
// likewise — so the app's LIVE table, built from the SAME `cell()`/`A()` `admin/data_sources.ts`
// copies verbatim from this very `adminVals()`, renders byte-identical pixels to what the
// reference (no adapter, `sets.data.rows` itself) already draws.
import { Component } from '../src/logic.js';

/** The design's own Data Sources rows, computed exactly as the reference renders them — five, in
 *  `sets.data.rows`' own order. */
function designDataSourceCells() {
  const c = new Component({});
  c.setState({ adminTab: 'data' });
  return c.adminVals().rows.map((r) => r.cells);
}

/** All five, as `toDataSourceRows`'s `DesignDataSourceRow` union arm expects. */
export function designAdminDataSourceRows() {
  return designDataSourceCells().map((cells, i) => ({
    dataset_key: `design-fixture-${i + 1}`,
    license_status: cells[2].pill.toLowerCase(),
    dataset: cells[0].main, datasetSub: cells[0].sub,
    source: cells[1].main, sourceSub: cells[1].sub,
    pill: cells[2].pill, pillStyle: cells[2].pillStyle,
    actions: cells[3].actions.map((a) => ({ label: a.label, style: a.style }))
  }));
}

/** Those five rows as the complete body of `GET /api/admin/data-sources`. */
export function designAdminDataSourcesBody() {
  return JSON.stringify(designAdminDataSourceRows());
}
