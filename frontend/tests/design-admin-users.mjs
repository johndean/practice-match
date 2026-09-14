// The design-fixture stub for the ADMIN USERS queue — `design-admin-listings.mjs`'s own shape
// applied to `admin-users`, Task A36.
//
// `admin-users` is one of CLAUDE.md's thirteen frozen screens and its rows are the design's own
// `sets.users.rows`, all FOUR of them. Two of the four are unreachable from a real payload BY
// CONSTRUCTION, which is why this fixture carries the design's own words rather than feeding
// numbers through `toUserRows`'s live derivation:
//
//   * Dr. Alan Cho's NEEDS-REVIEW row offers "Request info", and `app/api/admin_users.py`'s
//     `TRANSITIONS` allows that decision from `pending` ONLY — so `ACTIONS.needs_review` cannot
//     produce it and a real row never will (the controller's ruling on the design's own
//     placement: the state machine is not widened to match a prototype's button).
//   * Dr. Rachel Mendes's row shows REVOKE, which the live table does not render at all until a
//     re-authentication dialog exists (ruling 6) — the `admin/listings.ts` "Flagged"/Investigate
//     split exactly: a limit on the LIVE mapping, never on this oracle-only fixture, whose whole
//     job is reproducing the design's pixels regardless of what a real response could contain.
//
// `DesignUserRow` does not run through `PILLS`/`ACTIONS` at all: it carries a row's own
// `pill`/`pillStyle` and action styles verbatim, so it represents a button set no state machine
// backs exactly as easily as one it does.
//
// DERIVED, never hand-copied: the four rows come straight off `adminVals()`'s own COMPUTED cells
// (`main`, `sub`, `pill`, `pillStyle`, and each action's `label`/`style`), and the badge comes off
// the design's own `tabs[0].count`. This file touches only `logic.js`, exactly as
// `design-admin-listings.mjs` does — no TypeScript module, on either side of the D6 stub — so a
// `DesignUserRow` carries whole STYLE STRINGS rather than a tone name this file would have had to
// re-derive by importing `admin/users.ts`'s own `cell()`/`A()` back into itself.
import { Component } from '../src/logic.js';

/** The design's own Users tab, computed exactly as the reference renders it. */
function designUsersTab() {
  const c = new Component({});
  c.setState({ adminTab: 'users' });
  return c.adminVals();
}

/** All four rows, as `toUserRows`'s `DesignUserRow` union arm expects. */
export function designAdminUserRows() {
  return designUsersTab().rows.map((r) => r.cells).map((cells, i) => ({
    account_id: `admin-user-fixture-${i + 1}`,
    applicant: cells[0].main, applicantSub: cells[0].sub,
    affiliation: cells[1].main, intent: cells[1].sub,
    pill: cells[2].pill, pillStyle: cells[2].pillStyle,
    actions: cells[3].actions.map((a) => ({ label: a.label, style: a.style }))
  }));
}

/**
 * The badge, from the design's own tab literal rather than from a number written here: the Users
 * tab reads `count: "3"` and the design's four rows hold exactly three undecided applications
 * (two Pending and one Needs review), which is the OPEN queue the API counts. `total` is the four
 * rows themselves. Read this way, a change to the design's own literal moves the oracle with it.
 */
export function designAdminUserCounts() {
  const rows = designAdminUserRows();
  return { open: Number(designUsersTab().tabs[0].count), total: rows.length };
}

/** Those four rows as one complete page of `GET /api/admin/users`, counts included. */
export function designAdminUsersBody() {
  return JSON.stringify({ items: designAdminUserRows(), next_cursor: null, counts: designAdminUserCounts() });
}
