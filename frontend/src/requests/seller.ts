/**
 * The seller-facing access-request adapter (per-buyer-disclosure directive §5), wiring the
 * seller dashboard's own buyer-request inbox (`frontend/src/logic.js`'s `sellerVals`) to the real
 * `GET /api/seller/requests` / `POST /api/seller/requests/{id}/decide` /
 * `POST /api/seller/requests/{id}/revoke` (Task 6 of
 * `docs/superpowers/plans/2026-09-18-per-buyer-disclosure.md`).
 *
 * `./buyer.ts`'s own idiom exactly — an injectable `fetchFn` defaulted to the real `fetch`
 * (`market/boundaries.ts`'s shape, not `listings/seller.ts`'s; see that file's own doc comment
 * for why). `ApiRequestRow`/`DesignRequestRow`/`toDesignRow` are imported from `./buyer` rather
 * than redeclared: a seller's inbox row and a buyer's own row are ONE fact
 * (`app/api/requests.py::_serialisable`'s own `for_buyer` flag reads the SAME row two ways), and
 * this side never hides `seller_user_id` at all — a seller reading their own inbox is not
 * learning anything about themselves.
 *
 * `revoke` was wired here (Task 6) before the button that calls it existed: the plan's own "What
 * needs a design ruling from John" section was explicit that only the SELLER-FACING BUTTON for
 * revoke was out of scope for Task 14 — V3 drew no third action on an already-accepted inbox
 * row, and composing one needed John's ruling the way A41–A47 needed his for the admin spec —
 * never the adapter method, which nothing should leave unreachable from TypeScript merely
 * because its caller had not been composed yet. A53 (John's ruling, 2026-09-19) composed that
 * button (`frontend/tests/design-amendments.ts`'s `A53_1`/`A53_3`), so `logic.js`'s own
 * `sellerVals` now wires `revoke` beside `accept`/`decide`.
 */
import { csrfToken } from '../auth/api';
import { openChoiceDrawer } from '../admin/noteDrawer';
import { capabilityOptions } from '../disclosure/capabilities';
import { type ApiRequestRow, type DesignRequestRow, toDesignRow } from './buyer';

/** What `logic.js` sees as `this.props.sellerRequests`. */
export interface SellerRequestsAdapter {
  inbox(): Promise<DesignRequestRow[]>;
  /**
   * Approve or deny. `capabilities` is the SET the seller chose (ruling D-C67, John, 2026-09-24):
   *
   * * an ARRAY — including the EMPTY one — is sent as `disclosure_capabilities` and is stored
   *   exactly as it stands;
   * * `undefined` sends no set at all, which is the API's own default arm: the level the BUYER
   *   asked for, which every request defaults to `FULL_CONFIDENTIAL`.
   *
   * The test below is `!== undefined` rather than truthiness, and the reason is MEASURED rather
   * than inherited from the server's own `is None`: an empty array is TRUTHY in JavaScript, so the
   * two spellings agree about `[]` and a test asserting otherwise would pass against both. What
   * they disagree about is `null`, which is exactly the value `chooseAccess` answers when the
   * seller dismisses the drawer — under truthiness a caller who forwarded it would send NO set and
   * be given the buyer's own `FULL_CONFIDENTIAL` ask; under `!== undefined` it reaches the route as
   * `disclosure_capabilities: null` and is REFUSED (`app/api/seller_requests.py` tells absent from
   * null deliberately). One spelling fails open on a caller's mistake and the other fails closed.
   */
  decide(id: string, action: 'approve' | 'deny', capabilities?: string[], reason?: string): Promise<DesignRequestRow>;
  revoke(id: string): Promise<DesignRequestRow>;
  /**
   * Asks the seller WHICH capabilities this buyer receives, and answers the ones they ticked, or
   * `null` if they dismissed the drawer without deciding. Writes nothing: the design chains this
   * into `decide`, which is the seam `listings.describe`/`listings.confirmRemove` established —
   * the ask is app-only, the write is the route, and the DESIGN chains them (A58.6e/A58.6f).
   *
   * `held` pre-ticks what the buyer already holds, so the CHANGE path starts from the truth rather
   * than from blank; `title` is the word on the button that opened it, `openNoteDrawer`'s own rule.
   */
  chooseAccess(buyer: string, held: string[], title: string): Promise<string[] | null>;
}

/** A refusal, carrying the server's own code — `./buyer.ts`'s own `RequestError`, kept as its own
 *  copy rather than imported: `frontend/src/admin/listings.ts` and `frontend/src/admin/users.ts`
 *  already establish that two sides of one API surface keep independent copies of this shape in
 *  this codebase, "so a drift on either side fails on its own rather than one copy silently
 *  covering for the other" (`admin/listings.ts`'s own doc comment). */
export class RequestError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'RequestError';
    this.code = code;
  }
}

async function refusal(res: Response): Promise<RequestError> {
  const body = (await res.json().catch(() => null)) as { error?: { code?: string; message?: string } } | null;
  const error = body?.error;
  return new RequestError(error?.code ?? 'UNKNOWN', error?.message ?? `HTTP ${res.status}`);
}

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

export function makeSellerRequestsAdapter(fetchFn: typeof fetch = globalThis.fetch.bind(globalThis)): SellerRequestsAdapter {
  return {
    inbox: async () => (await send<ApiRequestRow[]>(fetchFn, 'GET', '/api/seller/requests')).map(toDesignRow),
    decide: async (id, action, capabilities, reason) =>
      toDesignRow(
        await send<ApiRequestRow>(fetchFn, 'POST', `/api/seller/requests/${id}/decide`, {
          action,
          // `!== undefined`, never truthiness — see `SellerRequestsAdapter.decide`'s own doc
          // comment. An empty array is a decision and must reach the server as one.
          ...(capabilities !== undefined ? { disclosure_capabilities: capabilities } : {}),
          ...(reason ? { reason } : {})
        })
      ),
    revoke: async (id) => toDesignRow(await send<ApiRequestRow>(fetchFn, 'POST', `/api/seller/requests/${id}/revoke`, {})),
    chooseAccess: (buyer, held, title) =>
      openChoiceDrawer({
        title,
        subtitle: buyer,
        // The WIZARD STEP 7 blurb, verbatim (`src/logic.js`'s `byStep[7].blurb`): step 7 is where
        // this product already asks a seller this question, and D-C67 asks it one buyer wider.
        intro: 'You decide what an approved buyer sees before you have spoken to them.',
        options: capabilityOptions(),
        selected: held,
        submitLabel: title
      })
  };
}
