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
import { type ApiRequestRow, type DesignRequestRow, toDesignRow } from './buyer';

/** What `logic.js` sees as `this.props.sellerRequests`. */
export interface SellerRequestsAdapter {
  inbox(): Promise<DesignRequestRow[]>;
  decide(id: string, action: 'approve' | 'deny', level?: string, reason?: string): Promise<DesignRequestRow>;
  revoke(id: string): Promise<DesignRequestRow>;
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
    decide: async (id, action, level, reason) =>
      toDesignRow(
        await send<ApiRequestRow>(fetchFn, 'POST', `/api/seller/requests/${id}/decide`, {
          action,
          ...(level ? { disclosure_level: level } : {}),
          ...(reason ? { reason } : {})
        })
      ),
    revoke: async (id) => toDesignRow(await send<ApiRequestRow>(fetchFn, 'POST', `/api/seller/requests/${id}/revoke`, {}))
  };
}
