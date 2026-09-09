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

// The buttons the approved design shows, per status — a legal SUBSET of `DECISIONS`, not all of
// it: the API also allows `publish` from `declined` and `paused`, which the design's own In
// review / Published rows do not offer (its Paused row offers "Contact seller" instead, a no-op
// the design has never wired — spec §14). A status with no entry here offers no button at all.
export const ACTIONS: Record<string, Action[]> = { "in_review": ["publish", "decline"], "published": ["unpublish"] };

const LABEL: Record<Action, string> = { publish: 'Publish', decline: 'Reject', unpublish: 'Unpublish' };
const TONE: Partial<Record<Action, string>> = { publish: 'primary', decline: 'danger' };

// `[label, tone]` for the three of `STATUSES` the design's own rows picture (its In review,
// Published and Paused rows); `draft`, `withdrawn` and `declined` have no ruled label, so they
// show the state key, muted — absent beats faked, `toListingRows`'s own fallback below.
export const PILLS: Record<string, [string, string]> = { "in_review": ["In review", "warn"], "published": ["Published", "ok"], "paused": ["Paused", "info"] };

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
 * `seller_id`/`seller_name`; a structural interface means the real item is assignable without
 * restating it.
 */
export interface ListingItem {
  id: string; status: string; name: string | null; type: string | null; city: string | null;
  price: number | null; rev: number | null; docs: number | null; bldg: string | null;
  state: string | null; seller_name: string | null; submitted_at: string | null;
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
    const actions = ACTIONS[item.status];
    const title = item.city ? `${item.type || 'Small animal'} practice — ${item.city}` : 'Untitled listing';
    const figures: string[] = [item.price != null ? `${money(item.price)} asking` : 'Asking price not set'];
    if (item.rev != null) figures.push(`${money(item.rev)} revenue`);
    if (item.docs != null) figures.push(`${item.docs} ${item.docs === 1 ? 'doctor' : 'doctors'}`);
    if (item.bldg) figures.push(BLDG_SUB[item.bldg] ?? item.bldg.toLowerCase());
    return [
      cell(title, item.submitted_at ? `Submitted ${formatDate(item.submitted_at)}` : null),
      cell(item.seller_name, figures.join(' · ')),
      cell(null, null, pill, tone),
      cell(null, null, null, null, actions ? actions.map((action) => A(LABEL[action], TONE[action], decision(item, action, ui))) : null)
    ];
  });
}

/** One page of the review queue, and far past what the eighteen seeded hospitals plus a run's own
 *  test listings hold — `src/listings/seller.ts`'s own `PAGE_LIMIT`/`MAX_PAGES` shape and reason:
 *  a server that answers with the cursor it was given would otherwise spin for ever. */
const PAGE_LIMIT = 200;
const MAX_PAGES = 20;

interface QueuePage { items?: unknown; next_cursor?: string | null }

async function send(method: string, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (method !== 'GET') headers['X-CSRF-Token'] = csrfToken();
  const res = await fetch(`/api/admin${path}`, {
    method, credentials: 'same-origin', headers,
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  return res;
}

/** What `logic.js` sees as `this.props.adminListings`. */
export interface AdminListingsAdapter {
  list(): Promise<Cell[][]>;
}

/**
 * The concrete `ListingsUi`: the browser's own prompts, standing in for the field editor Rev 3
 * owns (spec §14 item 6) — the same stopgap `describe()` (`src/listings/seller.ts`) already uses
 * for a photograph's caption. A refusal is swallowed into a blunt `alert`, because this tab has no
 * `wizErr`-shaped surface of its own to render one into and D24's ask is the real data, not a new
 * error banner.
 */
function windowUi(): ListingsUi {
  return {
    needsNote: async (action) => window.prompt(`Why is this listing being ${action === 'decline' ? 'rejected' : action}?`),
    needsFields: async () => {
      const state = window.prompt('Two-letter state code (e.g. TX) — this listing has never been published before:');
      if (state === null) return null;
      const market = window.prompt('Metro, exactly as the buyer detail should show it (e.g. "Austin, TX"):');
      if (market === null) return null;
      return { state, market };
    },
    // No reload after a successful decide: `admin/users.ts`'s own `decision()` — the pattern this
    // mirrors — does not refresh its table either, because neither Users nor Listings has been
    // wired to a live component before this task. Recorded rather than built past scope: a
    // reviewer sees the queue settle on the next full load, exactly as today's Admin tabs do.
    decide: async (item, action, note, fields) => {
      const res = await send('POST', `/listings/${item.id}/decide`, { action, reason: note, ...(fields ?? {}) });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
        window.alert(body?.error?.message ?? `That listing could not be ${action === 'decline' ? 'rejected' : action}ed.`);
      }
    }
  };
}

export function makeAdminListingsAdapter(): AdminListingsAdapter {
  return {
    list: async () => {
      const ui = windowUi();
      // Real production rows are `ListingItem`-shaped; the pixel oracle's harness answers this
      // very endpoint with `DesignListingRow`-shaped ones instead (the module note explains why).
      // `toListingRows` reads either.
      const items: (ListingItem | DesignListingRow)[] = [];
      let cursor: string | null = null;
      for (let page = 0; page < MAX_PAGES; page++) {
        const query = `/listings?limit=${PAGE_LIMIT}${cursor === null ? '' : `&cursor=${encodeURIComponent(cursor)}`}`;
        const res = await send('GET', query);
        if (!res.ok) throw new Error('the review queue could not be read');
        const body = (await res.json()) as QueuePage;
        if (!Array.isArray(body.items)) throw new Error('the review queue answered no items');
        items.push(...(body.items as (ListingItem | DesignListingRow)[]));
        cursor = body.next_cursor ?? null;
        if (cursor === null) break;
      }
      return toListingRows(items, ui);
    }
  };
}
