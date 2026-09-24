/**
 * `GET /api/admin/requests` → the approved design's Requests table (Task ADMIN-REQUESTS, spec
 * `docs/superpowers/specs/2026-09-21-request-oversight-thread-design.md`, "Two prerequisites" for
 * ruling D-C63's staff oversight thread — which this module does NOT build, per that spec's own
 * scope note).
 *
 * `admin/users.ts`'s own M6 pattern, applied one tab over: a pure mapping from the API payload to
 * the rows the design's own template already renders, with `cell()` copied VERBATIM from
 * `src/logic.js`'s `adminVals()` — a FOURTH independent copy, alongside `admin/listings.ts`'s,
 * `admin/users.ts`'s and `admin/data_sources.ts`'s own, so a drift on any one side fails on its
 * own rather than one copy silently covering for another.
 *
 * **This tab has NO Action column at all.** The design's own `columns` for the "activity" tab are
 * `["Request", "Practice", "Status", "Age"]` — Users and Listings both carry a fifth, `"Decision"`/
 * `"Action"`, and this one does not, because staff does not DECIDE a disclosure request: the
 * seller does, through `app/api/seller_requests.py::decide_request`. So `toRequestRows` below
 * produces four `Cell`s per row and none of them ever carries an action, and there is no
 * reload-after-decision seam for this module to wire the way `admin/users.ts`'s `list(reload)`
 * does — `AdminRequestsAdapter.list()` takes no argument.
 *
 * **What this module deliberately does not render.** The design's own footnote on this tab
 * (`sets.activity.footnote`) says "Message contents are visible only in an abuse investigation,
 * and every such view is logged" — `app/api/admin_requests.py` does not serve `request.message` at
 * all, for exactly that reason, so there is nothing here to withhold a second time. The Request
 * column's sub-line instead names the disclosure LEVEL asked for (or, once a seller has decided,
 * the level actually granted) — real data the route does serve, and the one fact this column can
 * state without opening a door the design's own prose says is investigation-only.
 */
import { LEVEL_LABEL, orderedCapabilities } from '../disclosure/capabilities';

export interface Cell {
  hasMain: boolean; main: string;
  hasSub: boolean; sub: string;
  hasPill: boolean; pill: string; pillStyle: string;
  hasActions: boolean; actions: never[];
}

/** Verbatim from logic.js's `adminVals()`, narrowed to the shape this tab ever uses: `actions` is
 *  always empty here (module note), so the fourth `cell()` parameter is never passed and its
 *  `never[]` type documents that rather than merely defaulting it. */
export function cell(main: string | null, sub?: string | null, pill?: string | null, pillTone?: string | null): Cell {
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
    hasActions: false, actions: []
  };
}


/** `request.status`'s own CHECK constraint (`migrations/096_request.sql`), pinned by equality in
 *  `tests/test_docs.py` against `app/api/admin_requests.py::STATUSES`. `[label, tone]` per value:
 *  PENDING/APPROVED/DENIED take the design's OWN three words and tones off its "activity" fixture
 *  (rows 1-3: "Awaiting seller" warn, "Engaged" ok, "Declined" bad); REVOKED has no design fixture
 *  to read a word from — A53's own precedent one surface over (the seller inbox pill) gives a
 *  revoked row its OWN word, "Revoked", never collapsed onto "Declined" — and takes the same `bad`
 *  tone as Declined, since neither means the buyer is currently disclosed to. */
export const STATUS_PILL: Record<string, [string, string]> = {
  PENDING: ['Awaiting seller', 'warn'],
  APPROVED: ['Engaged', 'ok'],
  DENIED: ['Declined', 'bad'],
  REVOKED: ['Revoked', 'bad']
};

/** MOVED to `frontend/src/disclosure/capabilities.ts` under ruling D-C67 (2026-09-24), which gave
 *  these words a second reader — the seller's own per-capability chooser — and re-exported here so
 *  every existing importer of this module reads the same one table rather than a second copy of
 *  it. */
export { LEVEL_LABEL } from '../disclosure/capabilities';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/** "September 3" from an ISO timestamp — `admin/users.ts::formatDate`'s own shape, UTC and never
 *  `Date#toLocaleDateString`, for the reason that module records: the runtime's own locale must
 *  not move the day the API actually stamped. */
function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** Whole days between `iso` and now, floored — never fractional ("6.3 days"), and never negative
 *  (a clock skew of a few seconds between this browser and the server that stamped `requested_at`
 *  must not read "-1 days"). */
function ageDays(iso: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / DAY_MS));
}

function plural(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? '' : 's'}`;
}

/**
 * One row of `GET /api/admin/requests`'s `items`, narrowed to what the table reads. A structural
 * interface, so the real payload is assignable without restating the fields this tab does not
 * print (`app/api/admin_requests.py` serves more: `listing_id`, `buyer_user_id`, `seller_user_id`,
 * kept here anyway because a caller may need them even though no cell reads them directly).
 */
export interface AdminRequestItem {
  id: string;
  status: string;
  requested_disclosure_level: string;
  /** The SET the seller released (`request.approved_capabilities`, migration 097) — one name, five
   *  names, or the empty array a seller who approved and released nothing leaves behind. `null`
   *  while no decision has been taken, or where the decision was a refusal. */
  approved_capabilities: string[] | null;
  requested_at: string;
  reviewed_at: string | null;
  listing_id: string;
  listing_name: string | null;
  listing_type: string | null;
  listing_city: string | null;
  buyer_user_id: string;
  buyer_name: string;
  seller_user_id: string;
  seller_name: string;
}

/**
 * One of the DESIGN's own `sets.activity.rows` fixtures, as `frontend/tests/design-admin-requests.mjs`
 * serves them — `admin/users.ts`'s `DesignUserRow` applied to `admin-requests`, one of the thirteen
 * frozen screens. The fixture carries every one of the design's own WORDS AND STYLES directly, read
 * straight off `adminVals()`'s own computed cells — `pillStyle` included — rather than a tone NAME
 * this module would have to re-derive: the `.mjs` fixture files touch only `logic.js`, never a
 * TypeScript module, and a style string copied verbatim off the design's own computed output can
 * never drift from it.
 */
export interface DesignRequestRow {
  id: string;
  request: string; requestSub: string;
  practice: string; practiceSub: string;
  pill: string; pillStyle: string;
  age: string; ageSub: string;
}

/** The badge: every request still `PENDING` — the one status still waiting on a seller to act —
 *  over the WHOLE table, as `app/api/admin_requests.py::queue_counts` serves it beside `items`. */
export interface AdminRequestCounts { pending: number; total: number }

interface QueuePage { items?: unknown; next_cursor?: string | null; counts?: unknown }

/** The counts, or null where the answer carried none this table can read — an older API, a shape
 *  nobody has seen, or the explicit `counts: null` the route serves on every page past the first
 *  (the count describes the whole table, so a paging caller already holds it). `admin/users.ts`'s
 *  own `countsOf` shape and its own reason: `!= null`, not `!== undefined`, because a JSON `null`
 *  passes an undefined test and `null.pending` throws inside the loader. */
export function countsOf(body: QueuePage): AdminRequestCounts | null {
  const counts = body.counts as AdminRequestCounts | null | undefined;
  return counts != null && typeof counts.pending === 'number' && typeof counts.total === 'number' ? counts : null;
}

/** Given/approved disclosure level, or requested — the module note's own choice for what the
 *  Request column's sub-line names, since the raw message is never served at all. */
function levelLine(item: AdminRequestItem): string {
  // `!= null`, never truthiness: an APPROVED row whose seller released NOTHING carries `[]`, which
  // is a real decision and must read as one rather than falling back to what the buyer asked for
  // (D-C67's own fail-closed rule, on the surface that merely reports it).
  const approved = item.status === 'APPROVED' && item.approved_capabilities != null;
  if (approved) {
    // A LIST, not the seller inbox's SENTENCE: this is a table cell, so it keeps this tab's own
    // Title-case register (`LEVEL_LABEL`) and joins with commas, where `capabilityPhrase` is
    // lower-case and ends in "and" because it is read inside a sentence one surface over.
    // No fallback: `orderedCapabilities` answers only names `LEVEL_LABEL` has a word for. The
    // `?? level` on the REQUESTED line below stays, because that column carries whatever the API
    // serves and an unrecognised level there is a real possibility rather than a dead branch.
    const names = orderedCapabilities(item.approved_capabilities).map((name) => LEVEL_LABEL[name]);
    return names.length === 0 ? 'Approved: nothing released' : `Approved: ${names.join(', ')}`;
  }
  const level = item.requested_disclosure_level;
  return `Requested: ${LEVEL_LABEL[level] ?? level}`;
}

/** The practice's own name, or `admin/listings.ts`'s own `type practice — city` composed label, or
 *  its own "Untitled listing" fallback — the identical idiom, applied to this tab's own fields. */
function practiceLabel(item: AdminRequestItem): string {
  const label = item.listing_city && item.listing_type ? `${item.listing_type} practice — ${item.listing_city}` : null;
  return item.listing_name || label || 'Untitled listing';
}

/** The Age column: whole days since the request, and — only for a request a seller has actually
 *  decided — when. No fabricated narrative ("Reminder sent", "Packet released"): the design's own
 *  four fixture rows carry one, but no real feature backs any of the three phrases the design
 *  invented for it, and D-C53's "zero-fake-data" rule is what this column follows instead. */
function ageCell(item: AdminRequestItem): Cell {
  const days = plural(ageDays(item.requested_at), 'day');
  return cell(days, item.reviewed_at === null ? null : `Reviewed ${formatDate(item.reviewed_at)}`);
}

/**
 * Exactly the shape of `sets.<tab>.rows` in `adminVals()` — an array of cell arrays
 * (`admin/users.ts`'s own Important-3 note: `set.rows.map((cells, i) => ({ cells, style }))` is
 * what wraps them with the grid, so returning anything else would lose `style` and re-flow the
 * table at `maxDiffPixels: 0`). `admin-requests` IS one of the thirteen frozen screens, so this
 * function IS reached by the pixel oracle — through the `DesignRequestRow` arm, which is where
 * every one of its captured pixels comes from.
 */
export function toRequestRows(items: (AdminRequestItem | DesignRequestRow)[]): Cell[][] {
  return items.map((item) => {
    if ('request' in item) {
      return [
        cell(item.request, item.requestSub),
        cell(item.practice, item.practiceSub),
        { ...cell(null, null, item.pill), pillStyle: item.pillStyle },
        cell(item.age, item.ageSub)
      ];
    }
    const [pill, tone] = STATUS_PILL[item.status] ?? [item.status, 'mute'];
    return [
      cell(item.buyer_name, levelLine(item)),
      cell(practiceLabel(item), item.seller_name),
      cell(null, null, pill, tone),
      ageCell(item)
    ];
  });
}

/** One page of the queue, and far past what any real one holds — `admin/users.ts`'s own
 *  `PAGE_LIMIT`/`MAX_PAGES` shape and reason: a server that answers with the cursor it was given
 *  would otherwise spin for ever. 200 is `admin_requests.MAX_LIST`, so a page is never short of
 *  what was asked for. */
const PAGE_LIMIT = 200;
const MAX_PAGES = 20;

/** What `logic.js` sees as `this.props.adminRequests`. No `reload` argument, unlike
 *  `AdminUsersAdapter.list(reload)`: this tab has no per-row decision that could need one
 *  (module note). */
export interface AdminRequestsAdapter {
  list(): Promise<{ rows: Cell[][]; counts: AdminRequestCounts | null }>;
}

export function makeAdminRequestsAdapter(): AdminRequestsAdapter {
  return {
    list: async () => {
      // NO `X-CSRF-Token` and NO `Content-Type`: this is a read — `admin/data_sources.ts`'s own
      // rule (`check_origin_and_csrf` returns early on GET/HEAD/OPTIONS, so both would be refused
      // on an empty value in any case).
      const items: (AdminRequestItem | DesignRequestRow)[] = [];
      let counts: AdminRequestCounts | null = null;
      let cursor: string | null = null;
      for (let page = 0; page < MAX_PAGES; page++) {
        const query = `/api/admin/requests?limit=${PAGE_LIMIT}${cursor === null ? '' : `&cursor=${encodeURIComponent(cursor)}`}`;
        const res = await fetch(query, { method: 'GET', credentials: 'same-origin' });
        if (!res.ok) throw new Error('the request queue could not be read');
        const body = (await res.json()) as QueuePage;
        if (!Array.isArray(body.items)) throw new Error('the request queue answered no items');
        items.push(...(body.items as (AdminRequestItem | DesignRequestRow)[]));
        if (counts === null) counts = countsOf(body);
        cursor = body.next_cursor ?? null;
        if (cursor === null) break;
      }
      return { rows: toRequestRows(items), counts };
    }
  };
}
