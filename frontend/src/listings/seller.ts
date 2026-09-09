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

/** One step-6 tile: the badge the design draws and the name under it. */
export interface WizardAsset { kind: string; name: string; id: string }

/** What Continue, Edit and every save hand back to the design's script. */
export interface WizardDraft { w: Record<string, string | boolean>; assets: WizardAsset[] }

export type StatusAction = 'pause' | 'republish' | 'withdraw';

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

/**
 * A draft as the design's dashboard row.
 *
 * A-SL22 (3): `decline_reason` is the note under the DECLINED pill and nowhere else. The reason
 * survives a later publish (A-SL19's addendum), so a published listing that was once declined
 * still reads "Live · visible in search" rather than the old refusal.
 */
export function toDashboardRow(d: Draft): DashboardRow {
  // The design's own two shapes: "Small animal practice — Cedar Park" for a listing that has a
  // community, and "Untitled listing" (logic.js:209) for one that does not yet.
  const title = d.city ? `${d.type || 'Small animal'} practice — ${d.city}` : 'Untitled listing';
  // logic.js:1645's own meta line — money · doctors · square feet — with a part left out where
  // the seller has not given the figure. "Price to be set" is the design's own words for a
  // listing with no asking price (the submit handler, logic.js:1236).
  const parts = [d.price ? money(d.price) : 'Price to be set'];
  if (d.docs) parts.push(`${d.docs} ${d.docs === 1 ? 'doctor' : 'doctors'}`);
  if (d.sqft) parts.push(`${d.sqft.toLocaleString()} sq ft`);
  return {
    id: d.id,
    status: d.status,
    title,
    meta: parts.join(' · '),
    note: (d.status === 'declined' && d.decline_reason) || NOTE[d.status] || NOTE.draft
  };
}

/** The columns the design's fields edit as text: a number is rendered into the input, and an
 *  absent column becomes the empty string the design's own initial `w` holds (logic.js:204). */
const TEXT_FIELDS = ['name', 'type', 'est', 'ownership', 'city', 'zip', 'price', 'rev', 'docs',
  'rooms', 'sqft', 'hours', 'desc', 'bldg', 'facilityType', 'facility', 'state'] as const;

/**
 * A draft as the wizard's own `state.w`.
 *
 * The API already answers in the wizard's key names (`serialise_draft`'s docstring), so this is a
 * projection and a spelling change, not a translation: every value becomes what the design's own
 * `<input>` holds, and the three disclosure switches keep the design's polarity (on means HIDE).
 */
export function toWizardState(d: Draft): Record<string, string | boolean> {
  const w: Record<string, string | boolean> = {};
  for (const key of TEXT_FIELDS) {
    const value = d[key];
    w[key] = value == null ? '' : String(value);
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
  patch(id: string, step: number, fields: Record<string, unknown>): Promise<WizardDraft>;
  upload(id: string, file: File): Promise<ApiAsset>;
  document(id: string, file: File, kind?: string): Promise<ApiAsset>;
  caption(id: string, assetId: string, text: string): Promise<WizardDraft>;
  remove(id: string, assetId: string): Promise<void>;
  reorder(id: string, ids: string[]): Promise<WizardDraft>;
  submit(id: string): Promise<WizardDraft>;
  setStatus(id: string, action: StatusAction): Promise<WizardDraft>;
  pick(): Promise<File | null>;
  describe(): string;
}

const ACTIONS: StatusAction[] = ['pause', 'republish', 'withdraw'];

export function makeListingsAdapter(): ListingsAdapter {
  return {
    /**
     * The dashboard's rows. One page of 200 — the endpoint's own `MAX_LIST`, and far past what
     * one seller holds — so the dashboard never shows a truncated list without saying so.
     *
     * A body that is not a page REJECTS rather than answering `[]`: under A-SL22 (1) a loaded
     * empty array is a real answer that empties the dashboard, so "there was no answer" cannot be
     * spelled the same way. That is A-L6.2 (1)'s ruled shape — the design's own fixtures stay
     * whenever `items` is not an array — expressed where the caller can act on it.
     */
    list: async () => {
      const page = await json<{ items?: unknown }>('GET', '/listings?limit=200');
      if (!Array.isArray(page.items)) throw new ListingError('BAD_ANSWER', 'The listings could not be read.');
      return (page.items as Draft[]).map(toDashboardRow);
    },
    create: async () => (await json<{ id: string }>('POST', '/listings')).id,
    get: async (id) => toWizardDraft(await json<Draft>('GET', `/listings/${id}`)),
    patch: async (id, step, fields) => toWizardDraft(await json<Draft>('PATCH', `/listings/${id}?step=${step}`, fields)),
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
     * The design's "Add files" button, wired to a real file dialog.
     *
     * The dialog is the browser's, not a design element: the approved step 6 has no file input of
     * its own and inventing one is forbidden (spec §14 item 7 asks Rev 3 for the whole control
     * set). Resolves with `null` when the seller dismisses it, so the caller uploads nothing.
     */
    pick: () => new Promise<File | null>((resolve) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/jpeg,image/png,image/webp';
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
    describe: () => window.prompt('What does this photograph show?')?.trim() ?? ''
  };
}
