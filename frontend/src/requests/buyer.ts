/**
 * The buyer-facing access-request adapter (per-buyer-disclosure directive §6), wiring the
 * interest modal and the "My Requests" screen (`frontend/src/logic.js`'s own `sendInterest` and
 * `reqList`) to the real `POST /api/requests` / `GET /api/requests/mine` (Task 5 of
 * `docs/superpowers/plans/2026-09-18-per-buyer-disclosure.md`).
 *
 * App-only code, in `frontend/src/market/boundaries.ts`'s idiom — an injectable `fetchFn`,
 * defaulted to the real `fetch` — rather than in `frontend/src/listings/seller.ts`'s: that file
 * calls the global `fetch` directly, hard-coded to an `/api/seller` prefix, and declares no
 * fetcher type or parameter of any kind (`makeListingsAdapter()` takes zero arguments). Task 14's
 * own brief asked to "check that file's real exported fetcher type name" before writing this
 * import; the answer, read from the file, is that no such export exists there at all. This module
 * follows `market/boundaries.ts` instead, which the plan's own Task 14 text separately names as
 * this module's precedent ("app-only ... exactly like frontend/src/market/boundaries.ts") and
 * which already carries the injectable, testable shape (`fetchFn: typeof fetch`) a mockable
 * "fetcher" needs.
 *
 * The reference and the Claude Design preview receive no adapter at all and keep the design's own
 * `s.requests` fixture untouched — A16.1's "adapter presence, never data" rule, applied here by
 * `frontend/src/app.setup.js`'s own default factory for this prop, exactly as `listings`/`market`
 * carry no `data-props` entry of their own.
 */
import { csrfToken } from '../auth/api';

/** One `request` row, exactly as `app/disclosure/requests.py::_row` serialises it. A buyer's own
 *  reads (`GET /api/requests/mine`, the response `POST /api/requests` answers) never carry
 *  `seller_user_id` — `app/api/requests.py`'s `_BUYER_HIDDEN` — which is why that field is not
 *  declared here at all; a seller's own inbox row (`./seller.ts`) is the same shape plus it AND
 *  `buyer_name` — directive §5's "buyer identity": `app.disclosure.requests.list_inbox` alone
 *  joins the requesting buyer's own account row for it, falling back to that account's email where
 *  it has no display name set. A buyer's own reads have no business naming the buyer to
 *  themselves, so neither carries this field, which is why it is declared OPTIONAL here rather
 *  than moved to a second, seller-only interface — one row shape still serves both readers,
 *  `toDesignRow` below included. */
export interface ApiRequestRow {
  id: string;
  listing_id: string;
  buyer_user_id: string;
  buyer_name?: string;
  status: 'PENDING' | 'APPROVED' | 'DENIED' | 'REVOKED';
  message: string | null;
  requested_disclosure_level: string;
  approved_disclosure_level: string | null;
  requested_at: string;
  reviewed_at: string | null;
  denial_reason: string | null;
}

/** The design's own row shape — `logic.js`'s `s.requests` fixture (`id`, `pid`, `buyer`,
 *  `status`, `msg`, `reply`, `when`) — read by the seller inbox (`sellerVals`), the buyer's own
 *  list (`renderVals`'s `reqList`) and the detail screen's `sent`/`req`/`unlocked` (`detail()`).
 *  One shape serves both sides: `buyer_user_id` is present on both a buyer's own rows and a
 *  seller's inbox rows (only `seller_user_id` is buyer-hidden), so carrying it here invents
 *  nothing for either reader. */
export interface DesignRequestRow {
  id: string;
  pid: string;
  buyer: string;
  status: 'pending' | 'accepted' | 'declined' | 'revoked';
  msg: string;
  // Optional, never absent-means-hidden: the design's own fixture omits it outright for a PENDING
  // row (`logic.js`'s `r1`), and `toDesignRow`'s design-shaped arm defaults a missing one to `''`
  // on its way out, exactly as `hasReply: !!r.reply` (`logic.js`'s `reqList`) already treats both
  // the same way.
  reply?: string;
  when: string;
}

/** The design's own FOUR-word vocabulary (`logic.js`'s `sellerVals`/`detail`/`reqList`:
 *  `"pending"` | `"accepted"` | `"declined"` | `"revoked"`), never the API's bare enum values
 *  directly. Until A53 (John's ruling, 2026-09-19) `REVOKED` collapsed onto `"declined"` — the
 *  plan's own documented default at the time ("What needs a design ruling from John, and what is
 *  buildable now", 2026-09-18-per-buyer-disclosure.md), honest but not a sentence written for the
 *  case. A53 composed the fourth word and the surfaces that read it (`frontend/tests/design-
 *  amendments.ts`'s `A53_2`-`A53_6`), so this function now serves it: a revoked grant is
 *  DIFFERENT from a flatly denied one — the buyer once had access and lost it — and the seller's
 *  own re-read inbox row (`./seller.ts` shares this function) needs to say so about its own
 *  action too, rather than reading "You declined this request" about a request it approved. */
export function toDesignStatus(status: ApiRequestRow['status']): DesignRequestRow['status'] {
  return status === 'APPROVED' ? 'accepted' : status === 'PENDING' ? 'pending' : status === 'REVOKED' ? 'revoked' : 'declined';
}

/** `logic.js`'s own fixture date style ("Aug 29", `logic.js`'s `requests` literal) — an EXPLICIT
 *  locale, never the bare `toLocaleDateString()` `frontend/src/listings/seller.ts`'s `grouped()`
 *  already carries a comment warning against (A-SL23 (6) m1): unlocaled, it reads the BROWSER's
 *  own locale rather than this design's, so the same request would print a different date on a
 *  buyer's or seller's machine set to a different one. */
export function formatWhen(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * The one place an API row becomes the design's own row. Shared by both sides — `./seller.ts`
 * imports it rather than redeclaring it — because a seller's inbox row and a buyer's own row are
 * ONE fact read from two doors (`app/api/requests.py::_serialisable`'s own `for_buyer` flag), and
 * the status vocabulary and the date format are each one fact too.
 *
 * `reply` is the seller's own free text where the API has any — `denial_reason`, written only on
 * a `deny` (`app/disclosure/requests.py::decide`) — and empty otherwise. The design's own
 * `hasReply: !!r.reply` (`logic.js`'s `reqList`) already renders nothing for an empty one, so a
 * still-PENDING row, or an APPROVED one (the schema has no free-text "reply" for an approval at
 * all — directive §17 forbids inventing copy, and a fabricated one-line grant message would be
 * exactly that), is handed nothing rather than a sentence nobody wrote.
 *
 * `msg` guards a null `message` the same way: the design's own template quotes it
 * UNCONDITIONALLY (`"“" + r.msg + "”"`, `logic.js`'s `sellerVals`), and a request with no
 * message — the API allows one (`app/api/requests.py::create_request`); the interest modal's OWN
 * client-side validation never sends one (`sendInterest`'s `if (!s.interestMsg.trim())` guard) —
 * must not read literally "“null”" for a row reached some other way.
 *
 * `row` may ALREADY be design-shaped (carries `pid`, never `listing_id`) — the e2e oracle's own
 * stub (`frontend/tests/design-requests.mjs`) hands back `logic.js`'s own `s.requests` fixture
 * rows verbatim so the three frozen screens that read them keep their pixels, exactly the union
 * `frontend/src/listings/seller.ts`'s `toDashboardRow` already takes for `DesignRow` (that
 * entry's own doc comment names the identical reason, one screen over: the design's row prose —
 * here, an ACCEPTED row's own reply, "Happy to share. Financial packet unlocked — call me next
 * week." — is not constructible from any column the real schema has, since `denial_reason` exists
 * only for a DENIED row). A row already carrying the design's own words is taken as it stands;
 * every row the real endpoint sends takes the other arm. */
export function toDesignRow(row: ApiRequestRow | DesignRequestRow): DesignRequestRow {
  if ('pid' in row) return { ...row, reply: row.reply || '' };
  return {
    id: row.id,
    pid: row.listing_id,
    // `buyer_name` is the seller inbox's own served identity (directive §5) and is absent on a
    // buyer's own reads (`ApiRequestRow`'s own doc comment) — where it is absent, this keeps the
    // UUID it has always shown rather than inventing a name.
    buyer: row.buyer_name || row.buyer_user_id,
    status: toDesignStatus(row.status),
    msg: row.message || '',
    reply: row.denial_reason || '',
    when: formatWhen(row.requested_at)
  };
}

/** What `logic.js` sees as `this.props.requests`. */
export interface BuyerRequestsAdapter {
  create(listingId: string, message?: string, level?: string): Promise<DesignRequestRow>;
  mine(): Promise<DesignRequestRow[]>;
}

/** A refusal, carrying the server's own code (`src/listings/seller.ts`'s `ListingError`, same
 *  reason: a caller branches on the code and renders the server's own prose). */
export class RequestError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'RequestError';
    this.code = code;
  }
}

/** A body that is not the A5 envelope at all — a proxy's HTML 502, say — must still become a
 *  `RequestError` rather than a `SyntaxError` from deep inside the caller. */
async function refusal(res: Response): Promise<RequestError> {
  const body = (await res.json().catch(() => null)) as { error?: { code?: string; message?: string } } | null;
  const error = body?.error;
  return new RequestError(error?.code ?? 'UNKNOWN', error?.message ?? `HTTP ${res.status}`);
}

/** Every request follows `src/auth/api.ts`'s conventions exactly, `src/listings/seller.ts`'s own
 *  reason (this module's own doc comment): same-origin with cookies, `X-CSRF-Token` on state
 *  changes only (reads are never checked — `check_origin_and_csrf` returns early on GET/HEAD/
 *  OPTIONS), and `Content-Type: application/json` only where a JSON body exists. */
async function send<T>(fetchFn: typeof fetch, method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (method !== 'GET') headers['X-CSRF-Token'] = csrfToken();
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetchFn(path, {
    method,
    credentials: 'same-origin',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!res.ok) throw await refusal(res);
  return (await res.json()) as T;
}

export function makeBuyerRequestsAdapter(fetchFn: typeof fetch = globalThis.fetch.bind(globalThis)): BuyerRequestsAdapter {
  return {
    create: async (listingId, message, level) =>
      toDesignRow(
        await send<ApiRequestRow>(fetchFn, 'POST', '/api/requests', {
          listing_id: listingId,
          ...(message ? { message } : {}),
          ...(level ? { disclosure_level: level } : {})
        })
      ),
    mine: async () => (await send<ApiRequestRow[]>(fetchFn, 'GET', '/api/requests/mine')).map(toDesignRow)
  };
}
