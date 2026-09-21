// The design-fixture stub for the ADMIN REQUESTS queue — `design-admin-users.mjs`'s own shape
// applied to `admin-requests`, Task ADMIN-REQUESTS.
//
// `admin-requests` is one of CLAUDE.md's thirteen frozen screens and its rows are the design's
// own `sets.activity.rows`, all FOUR of them. This tab has no Action column at all (`columns`
// is `["Request", "Practice", "Status", "Age"]`), so unlike `design-admin-users.mjs`/
// `design-admin-listings.mjs` there is no `actions` array on a row at all.
//
// DERIVED, never hand-copied: the four rows come straight off `adminVals()`'s own COMPUTED cells
// (`main`, `sub`, `pill`, `pillStyle`), and the badge comes off the design's own `tabs[2].count`
// (the "activity" tab is the third of the four). This file touches only `logic.js`, exactly as
// `design-admin-users.mjs` does — no TypeScript module, on either side of the D6 stub — so a
// `DesignRequestRow` carries whole STYLE STRINGS rather than a tone name this file would have
// had to re-derive by importing `admin/requests.ts`'s own `cell()` back into itself.
import { Component } from '../src/logic.js';

/** The design's own Requests ("activity") tab, computed exactly as the reference renders it. */
function designRequestsTab() {
  const c = new Component({});
  c.setState({ adminTab: 'activity' });
  return c.adminVals();
}

/** All four rows, as `toRequestRows`'s `DesignRequestRow` union arm expects. */
export function designAdminRequestRows() {
  return designRequestsTab().rows.map((r) => r.cells).map((cells, i) => ({
    id: `admin-request-fixture-${i + 1}`,
    request: cells[0].main, requestSub: cells[0].sub,
    practice: cells[1].main, practiceSub: cells[1].sub,
    pill: cells[2].pill, pillStyle: cells[2].pillStyle,
    age: cells[3].main, ageSub: cells[3].sub
  }));
}

/**
 * The badge, from the design's own tab literal rather than from a number written here: the
 * Requests tab reads `count: "2"` (`tabs[2]`, the third of the four). `total` is the four rows
 * themselves.
 */
export function designAdminRequestCounts() {
  const rows = designAdminRequestRows();
  return { pending: Number(designRequestsTab().tabs[2].count), total: rows.length };
}

/** Those four rows as one complete page of `GET /api/admin/requests`, counts included. */
export function designAdminRequestsBody() {
  return JSON.stringify({ items: designAdminRequestRows(), next_cursor: null, counts: designAdminRequestCounts() });
}
