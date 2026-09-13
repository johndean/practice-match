/**
 * `GET /api/admin/listings` → the approved design's Listings table (Task SL8; D24 and John's
 * standing rule, verbatim: "every Admin tab must show real database data, never dummy rows").
 *
 * The M6 pattern `frontend/src/admin/users.ts` established: a pure mapping from the API payload
 * to the rows the design's own template already renders — `cell()` and `A()`, copied VERBATIM from
 * `src/logic.js`'s `adminVals()` a second time (independently of `admin/users.ts`'s own copy, so a
 * drift on either side fails on its own rather than one copy silently covering for the other) —
 * with `toListingRows` doing for the Listings tab what `toUserRows` does for Users.
 *
 * **A status backed by no column never comes back from REAL data, and that is the point
 * (A-SL24 (4)).** The design's own fifth `sets.listings.rows` fixture shows a "Flagged" pill and
 * an "Investigate" action describing an abuse-report table that does not exist: `listing.status`
 * has no `flagged` value, and inventing one is out of scope (spec §13) — so `PILLS`/`ACTIONS`
 * below, keyed by the six values `listing.status` really has, can never route a live
 * `ListingItem` to it, and `listings.test.ts` proves exactly that with `ListingItem`-shaped rows.
 * The frozen `admin-listings` pixel/DOM capture is a SEPARATE concern this limit does not reach:
 * its own oracle fixture (`frontend/tests/design-admin-listings.mjs`) carries all FIVE of the
 * design's rows, "Flagged" included, through the `DesignListingRow` union arm below — which
 * copies a row's own `pill`/`pillStyle` and action styles verbatim rather than deriving them from
 * `PILLS`/`ACTIONS`, so it represents a status backed by no column exactly as easily as one
 * backed by five, and the capture keeps its hash.
 *
 * **The reviewer's prompt for `state` and `market` (D12) reuses an existing seam.** `admin/users.ts`'s
 * `UsersUi` has `needsNote(action)` for the decline note; `ListingsUi` below carries the very same
 * method, for the identical reason (`admin_listings.NOTE_REQUIRED` also gates one action on one
 * free-text field), plus `needsFields(action)`, in the same shape and the same place, for the two
 * fields a FIRST publish needs. No new markup: a proper admin field editor is Rev 3 (spec §14 item
 * 6); until then the reviewer is asked the way `describe()` (`src/listings/seller.ts`) already
 * asks a seller to caption a photograph — the browser's own prompt.
 */
import { csrfToken } from '../auth/api';
import { money } from '../listings/seller';

export interface ActionButton { label: string; go: () => Promise<void>; style: string }

export interface Cell {
  hasMain: boolean; main: string;
  hasSub: boolean; sub: string;
  hasPill: boolean; pill: string; pillStyle: string;
  hasActions: boolean; actions: ActionButton[];
}

/** Verbatim from logic.js's `adminVals()`, `go` excepted (see the module note): the design's own
 *  is a prototype no-op, and here it is the decision. */
export function A(label: string, tone: string | undefined, go: () => Promise<void>): ActionButton {
  return {
    label,
    go,
    style: 'font-family: var(--rf-display); font-size: 12px; font-weight: 500; letter-spacing: .03em; text-transform: uppercase; padding: 7px 12px; border-radius: 6px; cursor: pointer; border: 1px solid ' +
      (tone === 'primary' ? 'var(--color-blue)' : 'var(--border-subtle)') + '; color: ' +
      (tone === 'primary' ? 'var(--color-white)' : tone === 'danger' ? '#494949' : 'var(--color-navy)') + '; background: ' +
      (tone === 'primary' ? 'var(--color-blue)' : 'var(--color-white)') + ';'
  };
}

/** Verbatim from logic.js's `adminVals()`. */
export function cell(main: string | null, sub?: string | null, pill?: string | null, pillTone?: string | null, actions?: ActionButton[] | null): Cell {
  const tones: Record<string, string[]> = {
    ok: ['#ffffff', '#003a70', '#003a70'], warn: ['#003a70', '#deecf7', '#deecf7'],
    bad: ['#494949', '#ffffff', '#494949'], info: ['#003a70', '#ffffff', '#339dde'],
    mute: ['#494949', '#f5f5f5', '#d4dde5']
  };
  const t = tones[pillTone ?? ''] || tones.mute;
  return {
    hasMain: !!main, main: main || '', hasSub: !!sub, sub: sub || '',
    hasPill: !!pill, pill: pill || '',
    pillStyle: 'display: inline-block; font-size: 11.5px; font-weight: 500; padding: 4px 11px; border-radius: 999px; color: ' + t[0] + '; background: ' + t[1] + '; border: 1px solid ' + t[2] + ';',
    hasActions: !!actions, actions: actions || []
  };
}

/** `app/api/admin_listings.py`'s `DECISIONS` keys — the reviewer's decisions, by their API names. */
export type Action = 'publish' | 'decline' | 'unpublish';

// ---------------------------------------------------------------------------------------
// The next three constants are JSON, on ONE LINE each and double-quoted, exactly as
// `admin/users.ts`'s own three are — `tests/test_docs.py::test_the_admin_listings_table_matches_
// the_api` parses them out of this file and compares them with `app/api/admin_listings.py`:
// `NOTE_REQUIRED` against its namesake, every action in `ACTIONS[status]` against `DECISIONS`
// (the design shows a legal SUBSET), and `PILLS`'s keys against `STATUSES` (a subset there too —
// the design pictures three of the six real statuses; A-SL24 (4)).
// ---------------------------------------------------------------------------------------

/** `admin_listings.decide_listing` refuses `decline` with `NOTE_REQUIRED` when the reason is blank. */
export const NOTE_REQUIRED: readonly Action[] = ["decline"];

// The buttons the tab offers, per status — every one of them a decision `DECISIONS` really allows
// (`tests/test_docs.py::test_the_admin_listings_table_matches_the_api` pins that both ways).
//
// A39, ruling 3 (D-C53): `publish` has ALWAYS been legal from `declined` and `paused`, and the
// tab's own footnote promises that unpublishing is "immediate and reversible" — a promise nothing
// on the screen could keep, because the design pictures no button on either row. The design's own
// primary Publish button appears there now; no new control is composed, and nothing else moves.
// A status with no entry here offers no button at all.
export const ACTIONS: Record<string, Action[]> = { "in_review": ["publish", "decline"], "published": ["unpublish"], "paused": ["publish"], "declined": ["publish"] };

const LABEL: Record<Action, string> = { publish: 'Publish', decline: 'Reject', unpublish: 'Unpublish' };
const TONE: Partial<Record<Action, string>> = { publish: 'primary', decline: 'danger' };

// GONE, by ruling 4 (D-C53, 2026-09-13), which SUPERSEDES A-SL33 (3): "Edit" (on the design's
// Published row) and "Contact seller" (on its Paused row) were kept here as the design's own
// inert buttons, on the reasoning that dropping them changed what the approved table renders.
// John's standing rule for this surface is now the other way round — "every action renders only
// if it calls a working route with a real status transition and an audit row; a button that does
// nothing is removed" — and neither has a route, a transition or an audit row: the admin field
// editor and member-to-member messaging are spec items, not omissions this tab can paper over
// with a control that answers a click by doing nothing. The REFERENCE and the frozen
// `admin-listings` capture are untouched: both render the design's own fixture rows through
// `DesignListingRow`, which copies every label and style verbatim and never consults this module's
// tables (see that interface's note), so no approved state moves.

// `[label, tone]` per `listing.status`, all six of them (A39, ruling 5). The design pictures three
// — In review, Published and Paused — and `draft`, `withdrawn` and `declined` used to render the
// COLUMN's own key, muted, so a reviewer read `withdrawn` where every other row read English.
// John ruled the three words and the mute tone, which is the tone `cell()` itself gives a pill it
// has no tone for. `toListingRows`'s `??` fallback below still stands for a seventh value nobody
// has added here yet.
export const PILLS: Record<string, [string, string]> = { "in_review": ["In review", "warn"], "published": ["Published", "ok"], "paused": ["Paused", "info"], "draft": ["Draft", "mute"], "withdrawn": ["Withdrawn", "mute"], "declined": ["Declined", "mute"] };

/** The design's own bldg wording (logic.js's fixture rows), by the WIZARD's word — which is what
 *  `serialise_draft` answers `bldg` as (`BLDG_OUT`), never the column's own "Separate". */
const BLDG_SUB: Record<string, string> = {
  Included: 'building included', 'Available separately': 'building available separately', Leased: 'building leased'
};

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/** A deterministic "September 1" from an ISO timestamp — never `Date#toLocaleDateString`, which
 *  reads the RUNTIME's locale (the same lesson `seller.ts`'s `grouped()` records for thousands
 *  separators, A-SL23 (6) m1) — and UTC, so the reviewer's own browser offset cannot move the
 *  day the API actually stamped. */
function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

/**
 * One row of `GET /api/admin/listings`'s `items`, narrowed to what the table reads. The payload
 * carries the seller's whole draft (`app/api/seller_listings.py::serialise_draft`) plus
 * `seller_id`/`seller_name` and — since A39 — `listed_at` and the latest status change; a
 * structural interface means the real item is assignable without restating it.
 */
export interface ListingItem {
  id: string; status: string; name: string | null; type: string | null; city: string | null;
  price: number | null; rev: number | null; docs: number | null; bldg: string | null;
  state: string | null; seller_name: string | null; submitted_at: string | null;
  /** Stamped at the FIRST publish and never again (`admin_listings.decide_listing`), so it is the
   *  date a buyer has seen — never `updated_at`, which a re-save moves. */
  listed_at: string | null;
  /** The latest `audit_log` row that put this listing in the status it is in now: when, and the
   *  actor's own `actor_role`. Both null where no decision has ever named this status. */
  status_changed_at: string | null;
  status_changed_by: string | null;
  /** The words of the latest decline (`serialise_draft`, A-SL19 (9), Info-3). */
  decline_reason: string | null;
}

/** Whether the audit row's `actor_role` reads as the LISTING'S OWN SELLER rather than a reviewer.
 *
 *  Two doors reach `paused` — the seller's `POST /api/seller/listings/{id}/status` and the
 *  reviewer's `unpublish` — and ruling 5 names `actor_role` as what tells them apart. It is the
 *  comma-joined role list `app/auth/audit.py` writes, prefixed `token:` for a CI token and written
 *  `legacy:operator` for the operator secret, which holds no account at all.
 *
 *  THE ONE CASE IT CANNOT SETTLE, recorded rather than hidden: an account that holds `seller` AND
 *  `staff` (John's own all-roles persona does) pausing its own listing is written exactly as a
 *  reviewer unpublishing somebody else's, and this reads it as the reviewer. The unambiguous
 *  discriminator is the audit ACTION, which names the route the decision came through; the ruling
 *  names the role, so the role is what this reads. */
function bySeller(actorRole: string | null): boolean {
  const held = (actorRole ?? '').replace(/^token:/, '').split(',');
  return held.includes('seller') && !held.includes('staff') && !held.includes('admin');
}

/** The "Listing" cell's own sub-line: what last happened to this listing, in the design's own
 *  words (A39, ruling 5). Every row used to read "Submitted <date>" — the only date the payload
 *  carried — so a listing published in March and one paused yesterday both reported the day their
 *  seller pressed Submit, and the design's own "Published August 24" and "Paused by seller
 *  August 12" had no producer at all. Null where the date behind a line is absent: absent beats
 *  faked (D24), and an undated row keeps the design's own empty sub-line. */
function statusLine(item: ListingItem): string | null {
  if (item.status === 'published') return item.listed_at === null ? null : `Published ${formatDate(item.listed_at)}`;
  if (item.status === 'paused') {
    return item.status_changed_at === null ? null
      : `${bySeller(item.status_changed_by) ? 'Paused by seller' : 'Unpublished by reviewer'} ${formatDate(item.status_changed_at)}`;
  }
  // The declined row's own line is the REASON, which is the one thing its seller is owed and the
  // one thing the reviewer needs to see beside the pill.
  if (item.status === 'declined' && item.decline_reason !== null) return item.decline_reason;
  return item.submitted_at === null ? null : `Submitted ${formatDate(item.submitted_at)}`;
}

/**
 * One of the DESIGN's own `sets.listings.rows` fixtures (minus the excluded fifth, A-SL24 (4)),
 * as `frontend/tests/design-admin-listings.mjs` serves them — the `seller-dash`/`design-seller-
 * listings.mjs` precedent (A-SL2, re-ruled A-SL23 (2)) applied to `admin-listings`, one of the
 * thirteen frozen screens.
 *
 * `admin-listings`'s four rows are NOT reproducible by feeding raw numbers through this module's
 * own derivation: the design's hand-set prose ("$1.2M revenue") and this module's own `money()`
 * port ("$1.20M" — a legitimate, deterministic difference, not a bug) would never match byte for
 * byte. So the fixture carries every one of the design's own WORDS AND STYLES directly, read
 * straight off `adminVals()`'s own computed cells — `pillStyle` and each action's `style` included
 * — rather than tone NAMES this module would have to re-derive: the `.mjs` fixture files touch
 * only `logic.js` (never a TypeScript module, on either side of the D6 stub), and a style string
 * copied verbatim off the design's own computed output can never drift from it, unlike a tone name
 * chosen to reproduce one.
 */
export interface DesignListingRow {
  id: string; title: string; titleSub: string; seller: string; figures: string;
  pill: string; pillStyle: string; actions: { label: string; style: string }[];
}

export interface ListingsUi {
  /** Prompts the reviewer for the reason `decline` requires; null when they cancel or leave it
   *  blank. Same shape as `UsersUi.needsNote` (`frontend/src/admin/users.ts`). */
  needsNote(action: Action): Promise<string | null>;
  /** Prompts the reviewer for `state` and `market` — D12's two fields, asked only when this
   *  listing has never been published before (`item.state === null`; a republish needs neither,
   *  and the API ignores them past the first publish). Null when either prompt is cancelled. */
  needsFields(action: Action): Promise<{ state: string; market: string } | null>;
  /** The decision itself — `POST /api/admin/listings/:id/decide`. */
  decide(item: ListingItem, action: Action, note: string, fields: { state: string; market: string } | null): Promise<void>;
}

function decision(item: ListingItem, action: Action, ui: ListingsUi): () => Promise<void> {
  return async () => {
    let note = '';
    if (NOTE_REQUIRED.includes(action)) {
      const given = await ui.needsNote(action);
      // Cancelled, or blank: `decide_listing` refuses a blank reason on `decline`, so an empty
      // prompt is not a decision and there is nothing to send.
      if (given === null || given.trim() === '') return;
      note = given;
    }
    let fields: { state: string; market: string } | null = null;
    if (action === 'publish' && item.state === null) {
      fields = await ui.needsFields(action);
      // Cancelled: a first publish needs both, so there is nothing to send yet.
      if (fields === null) return;
    }
    await ui.decide(item, action, note, fields);
  };
}

/**
 * Exactly the shape of `sets.<tab>.rows` in `adminVals()` — an array of cell arrays (review
 * Important 3 on `admin/users.ts`, the same reason applies here: `set.rows.map((cells, i) => ({
 * cells, style }))` is what wraps them with the grid, so returning anything else would lose
 * `style` and re-flow the table at `maxDiffPixels: 0`). `admin-listings` IS one of the thirteen
 * frozen screens, so this function IS reached by the pixel oracle — through the `DesignListingRow`
 * arm, which is where every one of its captured pixels comes from (see that interface's note).
 */
export function toListingRows(items: (ListingItem | DesignListingRow)[], ui: ListingsUi): Cell[][] {
  return items.map((item) => {
    if ('title' in item) {
      return [
        cell(item.title, item.titleSub),
        cell(item.seller, item.figures),
        { ...cell(null, null, item.pill), pillStyle: item.pillStyle },
        cell(null, null, null, null, item.actions.map((a) => ({ label: a.label, style: a.style, go: () => Promise.resolve() })))
      ];
    }
    const [pill, tone] = PILLS[item.status] ?? [item.status, 'mute'];
    const title = item.city ? `${item.type || 'Small animal'} practice — ${item.city}` : 'Untitled listing';
    const figures: string[] = [item.price != null ? `${money(item.price)} asking` : 'Asking price not set'];
    if (item.rev != null) figures.push(`${money(item.rev)} revenue`);
    if (item.docs != null) figures.push(`${item.docs} ${item.docs === 1 ? 'doctor' : 'doctors'}`);
    if (item.bldg) figures.push(BLDG_SUB[item.bldg] ?? item.bldg.toLowerCase());
    // The design's own words, from its own Paused row — and true of all five unpublished statuses:
    // `GET /api/listings` serves `status = 'published'` alone, and the footnote above the table has
    // always said so while the rows said it on one status out of six.
    if (item.status !== 'published') figures.push('hidden from search');
    const actions = (ACTIONS[item.status] ?? []).map((action) => A(LABEL[action], TONE[action], decision(item, action, ui)));
    return [
      cell(title, statusLine(item)),
      cell(item.seller_name, figures.join(' · ')),
      cell(null, null, pill, tone),
      cell(null, null, null, null, actions.length ? actions : null)
    ];
  });
}

/** One page of the review queue, and far past what the eighteen seeded hospitals plus a run's own
 *  test listings hold — `src/listings/seller.ts`'s own `PAGE_LIMIT`/`MAX_PAGES` shape and reason:
 *  a server that answers with the cursor it was given would otherwise spin for ever. */
const PAGE_LIMIT = 200;
const MAX_PAGES = 20;

/** One page of `GET /api/admin/listings` as it arrives. `counts` is the whole TABLE's, beside
 *  `items` rather than inside them (`admin_signups`'s own envelope), so every page carries it. */
interface QueueBody { items?: unknown; next_cursor?: string | null; counts?: { in_review?: unknown } }

async function send(method: string, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (method !== 'GET') headers['X-CSRF-Token'] = csrfToken();
  const res = await fetch(`/api/admin${path}`, {
    method, credentials: 'same-origin', headers,
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  return res;
}

/** What one read of the queue answers: the rows the design's own table renders, and the number
 *  its tab badges — keyed by the TAB the number belongs to, because `s.adminCounts` is one object
 *  the other three tabs put their own badge in beside this one. */
export interface QueuePage { rows: Cell[][]; counts: { listings: number } }

/** What `logic.js` sees as `this.props.adminListings`. */
export interface AdminListingsAdapter {
  list(): Promise<QueuePage>;
  /** Register what to do when a decision the API ACCEPTED lands (A39, ruling 2). The adapter does
   *  not write state: it says a decision landed, and the host re-reads the queue through its own
   *  one loader — `loadAdmin` (A40.3), which calls `list()` above — so the rows, the pills, the
   *  buttons and the badge all settle by the single path that ever writes them. */
  onDecision(reload: () => unknown): void;
}

/**
 * The concrete `ListingsUi`: the browser's own prompts, standing in for the field editor Rev 3
 * owns (spec §14 item 6) — the same stopgap `describe()` (`src/listings/seller.ts`) already uses
 * for a photograph's caption. A refusal is swallowed into a blunt `alert`, because this tab has no
 * `wizErr`-shaped surface of its own to render one into and D24's ask is the real data, not a new
 * error banner.
 */
function windowUi(decided: () => Promise<void>): ListingsUi {
  return {
    // `decision()`'s only call is guarded by `NOTE_REQUIRED.includes(action)`, and `NOTE_REQUIRED`
    // is `["decline"]` alone (D24), so `action` here is always `'decline'` — no ternary, unlike
    // `decide`'s own wording below, which really is asked for every action.
    needsNote: async () => window.prompt('Why is this listing being rejected?'),
    needsFields: async () => {
      const state = window.prompt('Two-letter state code (e.g. TX) — this listing has never been published before:');
      if (state === null) return null;
      const market = window.prompt('Metro, exactly as the buyer detail should show it (e.g. "Austin, TX"):');
      if (market === null) return null;
      return { state, market };
    },
    // A39, ruling 2: THE TABLE REFRESHES. This used to end here, with the decided draft the route
    // answers thrown away and a note recording that as deliberate scope — so the pill, the buttons
    // and the badge all stood until the reviewer reloaded the page, which is what made a reviewer
    // press Publish a second time on a listing that was already published.
    decide: async (item, action, note, fields) => {
      const res = await send('POST', `/listings/${item.id}/decide`, { action, reason: note, ...(fields ?? {}) });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
        // SL9: was `'rejected'` here, doubling the suffix below into "rejecteded" — the ternary
        // gives the ROOT VERB the trailing "ed" attaches to (`publish`/`unpublish` already are one).
        window.alert(body?.error?.message ?? `That listing could not be ${action === 'decline' ? 'reject' : action}ed.`);
        // Nothing moved, so there is nothing to re-read.
        return;
      }
      await decided();
    }
  };
}

export function makeAdminListingsAdapter(): AdminListingsAdapter {
  // Whoever is rendering this queue, or nobody — the reference passes no adapter at all, and a
  // unit test may call `list()` with no host behind it. A decision still lands either way; what a
  // registered host buys is the table settling without a reload.
  let reload: (() => unknown) | null = null;
  return {
    list: async () => {
      const ui = windowUi(async () => { if (reload !== null) await reload(); });
      // Real production rows are `ListingItem`-shaped; the pixel oracle's harness answers this
      // very endpoint with `DesignListingRow`-shaped ones instead (the module note explains why).
      // `toListingRows` reads either.
      const items: (ListingItem | DesignListingRow)[] = [];
      let cursor: string | null = null;
      // Every page carries the same table-wide counts, so the last one read wins and the loop
      // always makes at least one request — there is no "no page at all" to answer for.
      let badge = 0;
      for (let page = 0; page < MAX_PAGES; page++) {
        const query = `/listings?limit=${PAGE_LIMIT}${cursor === null ? '' : `&cursor=${encodeURIComponent(cursor)}`}`;
        const res = await send('GET', query);
        if (!res.ok) throw new Error('the review queue could not be read');
        const body = (await res.json()) as QueueBody;
        if (!Array.isArray(body.items)) throw new Error('the review queue answered no items');
        // Refused rather than defaulted, for `items`' own reason: a badge that quietly reads 0 is
        // indistinguishable from "no listing is waiting for a reviewer".
        if (typeof body.counts?.in_review !== 'number') throw new Error('the review queue answered no counts');
        badge = body.counts.in_review;
        items.push(...(body.items as (ListingItem | DesignListingRow)[]));
        cursor = body.next_cursor ?? null;
        if (cursor === null) break;
      }
      return { rows: toListingRows(items, ui), counts: { listings: badge } };
    },
    onDecision: (fn) => { reload = fn; }
  };
}
