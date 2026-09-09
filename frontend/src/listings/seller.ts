/**
 * The prototype's `listings` adapter — the seam `logic.js`'s own Continue, Edit, Add files,
 * Continue-to-the-next-step, Submit for review and Pause/Republish/Withdraw handlers call through
 * (design amendment family A16, spec 2026-09-08 D23).
 *
 * It exists as its own module, rather than inline in `app.setup.js`, for the reason `auth`'s does:
 * `app.setup.js` is copied verbatim into `App.vue` by `npm run gen:app` and is therefore outside
 * the coverage gate, so logic written there has no unit tests. Everything the design's script
 * cannot express — the API's shapes, the two pure mappings onto the design's own row and wizard
 * state, the file dialog — lives here, with tests.
 *
 * Every request follows `src/auth/api.ts`'s conventions exactly: same-origin with cookies,
 * `X-CSRF-Token` on state changes only, `Content-Type: application/json` only where a JSON body
 * exists (never on a multipart POST, where the browser must set the boundary), and a refusal
 * unwrapped from the A5 envelope `{"error": {"code", "message"}}`.
 */
import { csrfToken } from '../auth/api';
import stepFields from './step-fields.json';

/** A refusal, carrying the code the server chose (`src/auth/api.ts`'s `AuthError`, same reason:
 *  a caller branches on the code and renders the message, which is the server's own prose). */
export class ListingError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'ListingError';
    this.code = code;
  }
}

/** One `listing_asset` row, as every asset route answers it. */
export interface ApiAsset {
  id: string;
  kind: string;
  name: string;
  content_type: string;
  byte_size: number;
}

/** A document, with the route that reads it back under D19's lock. */
export interface ApiDocument extends ApiAsset { url: string }

/** A photograph tile, in `listing.photos`' own order: the seller's caption (A-SL20), the seed
 *  inventory's caption for a seeded photograph, or `''` where the photograph has never been
 *  described — the design's own slot name by position is what fills that in (amendment A16.4). */
export interface ApiPhoto { id: string; name: string }

/** The OWNER's own truth, exactly as `app/api/seller_listings.py::serialise_draft` sends it: the
 *  keys are the wizard's (`state.w` in logic.js:204), not the columns'. */
export interface Draft {
  id: string;
  slug: string | null;
  status: string;
  name: string | null;
  type: string | null;
  est: number | null;
  ownership: string | null;
  city: string | null;
  zip: string | null;
  price: number | null;
  rev: number | null;
  docs: number | null;
  rooms: number | null;
  sqft: number | null;
  hours: string | null;
  desc: string | null;
  bldg: string | null;
  facilityType: string | null;
  facility: string | null;
  anon: boolean;
  revBand: boolean;
  docsLocked: boolean;
  state: string | null;
  market: string | null;
  area: string | null;
  decline_reason: string | null;
  submitted_at: string | null;
  updated_at: string;
  assets: ApiAsset[];
  photos: ApiPhoto[];
  documents: ApiDocument[];
}

/** One row of the design's own dashboard table (logic.js:206-211 — `sellerVals` reads exactly
 *  these four, plus the id the actions need). */
export interface DashboardRow {
  id: string;
  status: string;
  title: string;
  meta: string;
  note: string;
}

/**
 * One of the DESIGN's own dashboard fixture rows, as `frontend/tests/design-seller-listings.mjs`
 * serves them (A-SL2, as re-ruled by A-SL23 (2)).
 *
 * `seller-dash` is one of the thirteen frozen screens and its four rows are the design's own
 * `sellerListings`. Until A-SL23 the app reached them through a FAILURE — the oracle answered the
 * collection with a body carrying no `items`, `list()` rejected, and the design's fixtures stood
 * in — which made a frozen capture depend on an answer the real API cannot give, and showed a
 * REAL seller four invented listings whenever their own load failed (SL7 review, Critical-2). The
 * app now renders what the API answered and nothing else, so the oracle has to ANSWER with the
 * design's four rows, through the success path.
 *
 * Their prose is not constructible from any column and A-SL2 recorded why: "Live since August 24 ·
 * 34 views, 2 requests" needs a view count and a request count this slice does not have, and
 * "Draft started August 30" needs a creation date `serialise_draft` does not carry. So the row
 * carries the three fields itself, and `toDashboardRow` takes them where a row has them. This is
 * `design-listings.mjs`'s `name: null` in the other direction — a value the real endpoint never
 * sends, carried by the stub so that the DESIGN's own words are what the oracle compares.
 */
export interface DesignRow { id: string; status: string; title: string; meta: string; note: string }

/** One step-6 tile: the badge the design draws and the name under it. */
export interface WizardAsset { kind: string; name: string; id: string }

/** What Continue, Edit and every save hand back to the design's script. */
export interface WizardDraft { w: Record<string, string | boolean>; assets: WizardAsset[] }

export type StatusAction = 'pause' | 'republish' | 'withdraw';

/**
 * Which of the wizard's fields belong to which step — the ADAPTER's half of ruling D10.
 *
 * `app/api/seller_listings.py`'s own `STEP_FIELDS` is the other half, in these same wizard key
 * names, and `columns_for` maps them to columns and refuses anything else: the whitelist is
 * "one-directional and total ... because the wizard sends one step at a time and a mis-sent field
 * means the adapter and this table disagree — which is a bug to see, not to absorb". The design's
 * handlers hand `patch()` the WHOLE `w` (A16.6's Continue, A16.15's Save and exit, A16.18's rail)
 * and always have, so the projection has to happen here. Sending `w` unfiltered made every
 * Continue `400 step 1 does not accept anon, bldg, city, …`, and not one field a seller typed was
 * ever written (round-2 re-review, CRITICAL-B; A-SL26 (1) rules the fix here rather than
 * loosening D10).
 *
 * Both tables live in ONE data file, `./step-fields.json`, that both sides read without parsing
 * anything: this module imports it, and `tests/api/test_seller_listings.py` `json.load`s it and
 * compares it to `columns_for`'s own whitelist step by step, and `requiredNumeric` to this
 * module's own `(MONEY_FIELDS + INT_FIELDS) - OPTIONAL_NUMERIC` — so neither side can drift
 * without a failure naming the other, and no formatting of a TypeScript literal can ever be
 * mistaken for drift (round-3 re-review INFO-K, fixed at source by the A-SL27 addendum; the pin
 * used to regex this literal out of this file).
 *
 * Steps 6 and 8 are absent, exactly as they are absent from the API's table: step 6's photographs
 * and documents are saved one upload at a time and step 8 is the preview, so neither takes a field
 * and `columns_for` refuses both outright. `patch()` re-reads the draft for those rather than
 * writing. `photos` — the design's own fake photograph counter — and `state` — the reviewer's, at
 * the first publish (spec Q2) — live in `w` and belong to no step.
 */
export const STEP_FIELDS: Readonly<Record<number, readonly string[]>> = stepFields.steps;

/**
 * The numbers the API refuses a blank for — `est` and `price`, every money or integer field that is
 * not in `OPTIONAL_NUMERIC`, whose blank the API takes as "clear it". The design's own step guards
 * make the seller type both before Continue will advance; Save and exit and the step rail have no
 * guard and save whatever step the seller is on, half-filled, so `patch()`'s partial mode leaves a
 * blank one out rather than sending `""` and being refused (round-3 re-review MAJOR-D, A-SL27 (2)).
 * Same data file, same two-way pin: the Python side derives this list from its own tables.
 */
export const REQUIRED_NUMERIC: readonly string[] = stepFields.requiredNumeric;

/** One page of the seller's own listings, as `GET /api/seller/listings` answers it. */
interface ListingsPage { items?: unknown; next_cursor?: string | null }

/** The endpoint's own `MAX_LIST`, and far past what one seller holds. */
const PAGE_LIMIT = 200;

/**
 * The same stop `src/listings/load.ts` puts on the same loop, for the same reason: a server that
 * answers with the cursor it was given would otherwise spin for ever, and this read happens inside
 * `componentDidMount`. Twenty pages of two hundred is 4 000 listings for one seller.
 */
export const MAX_PAGES = 20;

/**
 * `logic.js`'s own `money()` (logic.js:251), ported value for value.
 *
 * A port rather than an import: `money` is a method on the prototype's `Component` and this
 * mapping is a pure function that must not construct one. `seller.test.ts` pins every branch of
 * the copy against the original, so the two cannot drift.
 */
export function money(n: number | null): string {
  if (n == null || (n as unknown) === '') return '—';
  if (n >= 1000000) return '$' + (n / 1000000).toFixed(n >= 10000000 ? 0 : 2).replace(/\.00$/, '') + 'M';
  return '$' + Math.round(n / 1000) + 'K';
}

/**
 * The note under each dashboard row, one per lifecycle state.
 *
 * A-SL2: the design's four fixtures carry prose no column supplies — "Live since August 24 · 34
 * views, 2 requests" needs a view count and a request count that do not exist in this slice — so
 * the mapping writes the SHORTEST HONEST version of each state instead. Absent beats faked: no
 * count is invented, and every word here is the design's own vocabulary for that state.
 */
const NOTE: Record<string, string> = {
  published: 'Live · visible in search',
  in_review: 'Submitted · awaiting VIN Foundation review',
  draft: 'Draft',
  paused: 'Paused by you · hidden from search',
  declined: 'Declined · edit and re-submit',
  withdrawn: 'Withdrawn'
};

/** A whole number with the design's own thousands separator.
 *
 *  A-SL23 (6) m1, on the SL7 review's Minor-1: `Number.toLocaleString()` with no locale reads the
 *  BROWSER's, so `4200` rendered `4.200` on a seller set to de-DE and `4 200` on fr-FR while the
 *  design's own fixture — and the pixel oracle — say `4,200`. Every other value in this mapping is
 *  a deterministic port of the design's own `money()`; this one is too.
 */
function grouped(n: number): string {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * A draft as the design's dashboard row.
 *
 * A-SL22 (3): `decline_reason` is the note under the DECLINED pill and nowhere else. The reason
 * survives a later publish (A-SL19's addendum), so a published listing that was once declined
 * still reads "Live · visible in search" rather than the old refusal.
 *
 * A row that already carries the three presentational fields is taken AS IT STANDS — see
 * `DesignRow`. That arm is the oracle's; every row the real endpoint sends takes the other one.
 */
export function toDashboardRow(d: Draft | DesignRow): DashboardRow {
  if ('title' in d) return { id: d.id, status: d.status, title: d.title, meta: d.meta, note: d.note };
  // The design's own two shapes: "Small animal practice — Cedar Park" for a listing that has a
  // community, and "Untitled listing" (logic.js:209) for one that does not yet.
  const title = d.city ? `${d.type || 'Small animal'} practice — ${d.city}` : 'Untitled listing';
  // logic.js:1645's own meta line — money · doctors · square feet — with a part left out where
  // the seller has not given the figure. "Price to be set" is the design's own words for a
  // listing with no asking price (the submit handler, logic.js:1236).
  const parts = [d.price ? money(d.price) : 'Price to be set'];
  if (d.docs) parts.push(`${d.docs} ${d.docs === 1 ? 'doctor' : 'doctors'}`);
  if (d.sqft) parts.push(`${grouped(d.sqft)} sq ft`);
  return {
    id: d.id,
    status: d.status,
    title,
    meta: parts.join(' · '),
    note: (d.status === 'declined' && d.decline_reason) || NOTE[d.status] || NOTE.draft
  };
}

/** The columns the design's fields edit as text: a number is rendered into the input, and a NULL
 *  column is left out, so that the design's own initial `w` (logic.js:204) supplies the value. */
const TEXT_FIELDS = ['name', 'type', 'est', 'ownership', 'city', 'zip', 'price', 'rev', 'docs',
  'rooms', 'sqft', 'hours', 'desc', 'bldg', 'facilityType', 'facility', 'state'] as const;

/**
 * A draft as the wizard's own `state.w`.
 *
 * The API already answers in the wizard's key names (`serialise_draft`'s docstring), so this is a
 * projection and a spelling change, not a translation: every value becomes what the design's own
 * `<input>` holds, and the three disclosure switches keep the design's polarity (on means HIDE).
 *
 * A null column is OMITTED, not spelled `""` (round-3 re-review CRITICAL-C, A-SL27 (1)). `openDraft`
 * lays this over the design's own initial literal, and a listing the seller has just created
 * holds NULL in `type`, `ownership`, `bldg` and `facility_type` — `create` inserts none of them.
 * Turned into `""` here, those four replaced the design's "Small animal", "Sole proprietor",
 * "Included" and "Standalone" with blank selects, and the first Continue of the first listing sent
 * `""` where `columns_for` wants one of the enum's values: `400 type must be one of Small animal,
 * …`. Left out, the design's default stands — exactly as the prototype shows it — and the first
 * Continue PATCHes it. The API never answers `""` for a text column (`_text` stores a blank as
 * NULL), so nothing is lost by the distinction; a number can be 0, and 0 is kept.
 */
export function toWizardState(d: Draft): Record<string, string | boolean> {
  const w: Record<string, string | boolean> = {};
  for (const key of TEXT_FIELDS) {
    const value = d[key];
    if (value != null) w[key] = String(value);
  }
  w.anon = d.anon;
  w.revBand = d.revBand;
  w.docsLocked = d.docsLocked;
  return w;
}

/** The badge the design draws on a step-6 tile: "Photo" for a photograph (logic.js:1188), and a
 *  document's own uppercased extension for the three kinds D18/Q3 allows. */
function badge(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot > -1 ? name.slice(dot + 1).toUpperCase() : 'PDF';
}

function toWizardDraft(d: Draft): WizardDraft {
  return {
    w: toWizardState(d),
    // Photographs first, in `listing.photos`' order, then the documents: the design's own literal
    // list is ordered the same way, and A16.4's name fallback counts photo tiles by position.
    assets: [
      ...d.photos.map((p) => ({ kind: 'Photo', name: p.name, id: p.id })),
      ...d.documents.map((doc) => ({ kind: badge(doc.name), name: doc.name, id: doc.id }))
    ]
  };
}

async function refusal(res: Response): Promise<ListingError> {
  // A body that is not the A5 shape at all — a proxy's HTML 502, say — must still become a
  // ListingError rather than a SyntaxError from deep inside the client.
  const body = (await res.json().catch(() => null)) as { error?: { code?: string; message?: string } } | null;
  const error = body?.error;
  return new ListingError(error?.code ?? 'UNKNOWN', error?.message ?? `HTTP ${res.status}`);
}

async function send(method: string, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = {};
  // Reads are never checked (`check_origin_and_csrf` returns early on GET/HEAD/OPTIONS), so the
  // header goes on state changes only.
  if (method !== 'GET') headers['X-CSRF-Token'] = csrfToken();
  // Never on a FormData body: the browser owns the multipart boundary.
  if (body !== undefined && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const res = await fetch(`/api/seller${path}`, {
    method,
    credentials: 'same-origin',
    headers,
    body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body)
  });
  if (!res.ok) throw await refusal(res);
  return res;
}

async function json<T>(method: string, path: string, body?: unknown): Promise<T> {
  return (await (await send(method, path, body)).json()) as T;
}

const upload = async (path: string, file: File, fields: Record<string, string> = {}): Promise<ApiAsset> => {
  const form = new FormData();
  form.append('file', file);
  for (const [name, value] of Object.entries(fields)) form.append(name, value);
  return (await (await send('POST', path, form)).json()) as ApiAsset;
};

/** What `logic.js` sees as `this.props.listings`. */
export interface ListingsAdapter {
  list(): Promise<DashboardRow[]>;
  create(): Promise<string>;
  get(id: string): Promise<WizardDraft>;
  patch(id: string, step: number, fields: Record<string, unknown>, partial?: boolean): Promise<WizardDraft>;
  upload(id: string, file: File): Promise<ApiAsset>;
  document(id: string, file: File, kind?: string): Promise<ApiAsset>;
  caption(id: string, assetId: string, text: string): Promise<WizardDraft>;
  attach(id: string): Promise<WizardDraft | null>;
  remove(id: string, assetId: string): Promise<void>;
  reorder(id: string, ids: string[]): Promise<WizardDraft>;
  submit(id: string): Promise<WizardDraft>;
  setStatus(id: string, action: StatusAction): Promise<WizardDraft>;
  pick(): Promise<File | null>;
  describe(): string;
}

const ACTIONS: StatusAction[] = ['pause', 'republish', 'withdraw'];

/** The three types the API takes as a DOCUMENT (`DOCUMENT_TYPES`, spec D18/Q3). Anything the file
 *  dialog can return that is NOT one of these is a photograph, which is the only other thing the
 *  design's single "Add files" button can add. */
const DOCUMENT_TYPES = ['application/pdf', 'text/csv',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'];

/** Everything "Add files" may hand back: the three photograph types the API re-encodes, then the
 *  three document types it stores as they are. */
const ACCEPT = ['image/jpeg', 'image/png', 'image/webp', ...DOCUMENT_TYPES].join(',');

export function makeListingsAdapter(): ListingsAdapter {
  const adapter: ListingsAdapter = {
    /**
     * The dashboard's rows — every one of them, following `next_cursor` to the end (A-SL23 (7)
     * I1). One page of `PAGE_LIMIT` is what a seller has today; a seller with 201 listings used to
     * lose the rest in silence, which is the one failure mode a dashboard must not have.
     *
     * A body that is not a page REJECTS rather than answering `[]`: under A-SL22 (1) a loaded
     * empty array is a real answer that empties the dashboard, so "there was no answer" cannot be
     * spelled the same way. That is A-L6.2 (1)'s ruled shape, as narrowed by A-SL22 (1) — the
     * design's own fixtures stay whenever `items` is not an array, where A-L6.2 (1) itself said
     * "not a NON-EMPTY array" — expressed where the caller can act on it.
     */
    list: async () => {
      const rows: DashboardRow[] = [];
      let cursor: string | null = null;
      for (let page = 0; page < MAX_PAGES; page++) {
        const query = `/listings?limit=${PAGE_LIMIT}${cursor === null ? '' : `&cursor=${encodeURIComponent(cursor)}`}`;
        const body: ListingsPage = await json<ListingsPage>('GET', query);
        if (!Array.isArray(body.items)) throw new ListingError('BAD_ANSWER', 'The listings could not be read.');
        rows.push(...(body.items as (Draft | DesignRow)[]).map(toDashboardRow));
        cursor = body.next_cursor ?? null;
        if (cursor === null) break;
      }
      return rows;
    },
    create: async () => (await json<{ id: string }>('POST', '/listings')).id,
    get: async (id) => toWizardDraft(await json<Draft>('GET', `/listings/${id}`)),
    /**
     * One step, saved. The caller hands the whole of `state.w` — that is what the design's own
     * Continue and Save and exit do — and only the step's own fields go on the wire (D10,
     * A-SL26 (1)). A key `w` does not carry is left out rather than sent as `undefined`:
     * `JSON.stringify` drops it either way, and the API reads a missing field as "unchanged".
     *
     * A step with no fields is not written at all: `columns_for` refuses steps 6 and 8 whatever
     * the body, step 6's assets are already stored one upload at a time, and step 8 is the
     * preview. The draft is RE-READ instead, so the caller still gets the tiles it renders (A16.6
     * writes `wizAssets` from this answer) and the seller is neither refused nor trapped.
     *
     * `partial` is the mode of a save that is NOT Continue — Save and exit (A16.15) and the step
     * rail (A16.18). Continue runs behind the design's own guards, which make the seller type the
     * year and the asking price before it will advance; those two saves have no guard and write
     * whatever step the seller is on, half-filled, and a draft is incomplete by nature. So in
     * partial mode a blank REQUIRED number is left out — the API reads a missing field as
     * "unchanged" — rather than sent as `""` and refused with `est must be a number.`, which held
     * the seller in the wizard behind the button labelled *Save* (round-3 re-review MAJOR-D,
     * A-SL27 (2)). Every other blank still goes: an optional number's blank CLEARS it (A-SL13 M1),
     * and a text field's blank is stored as NULL. Continue's full mode sends everything as it is.
     */
    patch: async (id, step, fields, partial = false) => {
      const keys = STEP_FIELDS[step];
      if (keys === undefined) return adapter.get(id);
      const body: Record<string, unknown> = {};
      for (const key of keys) {
        if (partial && fields[key] === '' && REQUIRED_NUMERIC.includes(key)) continue;
        body[key] = fields[key];
      }
      return toWizardDraft(await json<Draft>('PATCH', `/listings/${id}?step=${step}`, body));
    },
    upload: (id, file) => upload(`/listings/${id}/photos`, file),
    // D18: the approved step 6 has no kind picker, so the wizard sends `other` until Rev 3 gives
    // it one — the API takes the field today so that picker needs no API change.
    document: (id, file, kind = 'other') => upload(`/listings/${id}/documents`, file, { kind }),
    caption: async (id, assetId, text) =>
      toWizardDraft(await json<Draft>('PATCH', `/listings/${id}/assets/${assetId}`, { caption: text })),
    remove: async (id, assetId) => { await send('DELETE', `/listings/${id}/assets/${assetId}`); },
    reorder: async (id, ids) => toWizardDraft(await json<Draft>('PATCH', `/listings/${id}/photos`, { ids })),
    submit: async (id) => toWizardDraft(await json<Draft>('POST', `/listings/${id}/submit`)),
    setStatus: async (id, action) => {
      // Refused HERE rather than by the server: the three are the design's own dashboard buttons
      // (logic.js:958) and a fourth is a programming error, not a seller's mistake.
      if (!ACTIONS.includes(action)) throw new ListingError('BAD_ACTION', `${action} is not one of ${ACTIONS.join(', ')}.`);
      return toWizardDraft(await json<Draft>('POST', `/listings/${id}/status`, { action }));
    },
    /**
     * The file dialog behind "Add files", offering everything the API accepts (A-SL23 (6) m7).
     *
     * The dialog is the browser's, not a design element: the approved step 6 has no file input of
     * its own and inventing one is forbidden (spec §14 item 7 asks Rev 3 for the whole control
     * set). Resolves with `null` when the seller dismisses it, so the caller uploads nothing.
     */
    pick: () => new Promise<File | null>((resolve) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = ACCEPT;
      input.addEventListener('change', () => resolve(input.files && input.files[0] ? input.files[0] : null));
      input.addEventListener('cancel', () => resolve(null));
      input.click();
    }),
    /**
     * "have the user articulate what it is" — John's ruling, A-SL20 — asked through the browser's
     * own prompt for the same reason `pick()` uses the browser's own file dialog: the approved
     * step 6 has no caption field and the design is not invented against. An empty answer leaves
     * the photograph undescribed, and the design's own slot name by position is what it reads as.
     */
    describe: () => window.prompt('What does this photograph show?')?.trim() ?? '',
    /**
     * The whole of "Add files": choose a file, put it where its type belongs, and hand back the
     * draft the tiles are drawn from. ONE promise, so ONE rejection handler covers all four steps
     * (A-SL23 (4), on the SL7 review's Major-3: the caption's rejection used to be a SIBLING of
     * the upload's fulfilment, so a 429 on `LISTING_PATCH` escaped unhandled, `wizErr` stayed
     * empty and the photograph the seller had just uploaded never appeared — they would upload it
     * again).
     *
     * A photograph is uploaded and then DESCRIBED (A-SL20, John: "have the user articulate what
     * it is"), which answers with the refreshed draft. A document is not: it has no caption in
     * this schema — `PATCH …/assets/{id}` is `kind = 'photo'` only — and its own filename is the
     * design's vocabulary for a document tile (`Floor plan.pdf`), so the draft is re-read
     * instead. `kind` stays the API's default `other`: the approved step 6 has no kind picker and
     * Rev 3 owns one (spec §14).
     *
     * Resolves with `null` when the seller dismisses the dialog — nothing was added, so there is
     * nothing to redraw.
     */
    attach: async (id) => {
      const file = await adapter.pick();
      if (file === null) return null;
      if (DOCUMENT_TYPES.includes(file.type)) {
        await adapter.document(id, file);
        return adapter.get(id);
      }
      const asset = await adapter.upload(id, file);
      return adapter.caption(id, asset.id, adapter.describe());
    }
  };
  return adapter;
}
