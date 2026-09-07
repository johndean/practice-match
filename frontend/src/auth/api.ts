/**
 * The `/api/auth/*` client. Every request is same-origin with cookies, every refusal carries the
 * server's own code, and the shapes here are the API's, not a translation of it (spec decision
 * A5: an error body is always `{"error": {"code", "message"}}`).
 */
import type { Me } from './me';

/** Everything but `signin` and `me` answers `{status}` — the string is the API's own wording. */
export interface Status { status: string }

/**
 * A refusal, carrying the code the server chose. Callers branch on `code`, never on the message:
 * `INVALID_CREDENTIALS` and `RATE_LIMITED` are both 4xx on the same form and want different copy,
 * and the message is the server's prose to render, not an identifier.
 */
export class AuthError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'AuthError';
    this.code = code;
  }
}

/**
 * The `pm_csrf` cookie. It is the ONE session cookie `app/api/auth.py` deliberately leaves
 * readable (`httponly=False`), because the double-submit value has to be echoed back in
 * `X-CSRF-Token` for `deps.check_origin_and_csrf` to accept a state change.
 */
export function csrfToken(cookie: string = document.cookie): string {
  const match = /(?:^|;\s*)pm_csrf=([^;]*)/.exec(cookie);
  return match ? decodeURIComponent(match[1]) : '';
}

function call(method: 'GET' | 'POST', path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = {};
  // Reads are never checked (`check_origin_and_csrf` returns early on GET/HEAD/OPTIONS), so the
  // header goes on state changes only — which is also where an empty value would be refused.
  if (method !== 'GET') headers['X-CSRF-Token'] = csrfToken();
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  return fetch(`/api${path}`, {
    method,
    credentials: 'same-origin',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body)
  });
}

async function failure(res: Response): Promise<AuthError> {
  // A body that is not the A5 shape at all — a proxy's HTML 502, say — must still become an
  // AuthError rather than a SyntaxError from deep inside the client.
  const body = (await res.json().catch(() => null)) as { error?: { code?: string; message?: string } } | null;
  const error = body?.error;
  return new AuthError(error?.code ?? 'UNKNOWN', error?.message ?? `HTTP ${res.status}`);
}

async function payload<T>(res: Response): Promise<T> {
  if (!res.ok) throw await failure(res);
  return (await res.json()) as T;
}

/**
 * The flags the client has to honour — today just `MARKET_DATA_PUBLIC` (A-I7.2).
 *
 * Public, and public by nature: the flag is a statement ABOUT anonymous visitors, so requiring a
 * credential to read it would be circular. It throws like every other read; `useMe().load()` is
 * where the fail-closed default lives, because that is the caller that has to keep rendering.
 */
export async function config(): Promise<{ market_data_public: boolean }> {
  return payload<{ market_data_public: boolean }>(await call('GET', '/config'));
}

/** 200 + the `/api/me` payload, and the `pm_session` / `pm_csrf` cookies with it. */
export async function signIn(email: string, password: string): Promise<Me> {
  return payload<Me>(await call('POST', '/auth/signin', { email, password }));
}

/** 202 either way: a new address and one already registered are indistinguishable by design. */
export async function signUp(email: string, password: string): Promise<Status> {
  return payload<Status>(await call('POST', '/auth/signup', { email, password }));
}

export async function verify(token: string): Promise<Status> {
  return payload<Status>(await call('POST', '/auth/verify', { token }));
}

/**
 * A fresh 24 h verification link for the SIGNED-IN account that has not confirmed its address
 * (A-S4.1). No body: the session names the account, which is the whole reason this exists —
 * `signUp` needs the password, and somebody who reached the "Check your email" card by signing in
 * as an unverified account has none in hand.
 *
 * 403 `FORBIDDEN` from `verified` onward (and for `suspended`/`revoked`), which the caller renders
 * as the server's own message like every other refusal.
 */
export async function resendVerification(): Promise<Status> {
  return payload<Status>(await call('POST', '/auth/verify/resend'));
}

/** 202 either way, same as `signUp` — a registered and an unregistered address must read alike. */
export async function forgot(email: string): Promise<Status> {
  return payload<Status>(await call('POST', '/auth/password/forgot', { email }));
}

export async function reset(token: string, password: string): Promise<Status> {
  return payload<Status>(await call('POST', '/auth/password/reset', { token, password }));
}

export async function acceptInvite(token: string, password: string): Promise<Status> {
  return payload<Status>(await call('POST', '/auth/accept-invite', { token, password }));
}

/** The buyer or seller application. 202 + the row it created. */
export async function apply(kind: string, fields: Record<string, unknown>): Promise<{ id: string; status: string }> {
  return payload<{ id: string; status: string }>(await call('POST', '/applications', { kind, fields }));
}

/** One row of `/api/applications/me` — the applicant's current or a past application. */
export interface ApplicationRow {
  id: string;
  kind: string;
  status: string;
  info_request: string | null;
  answer: string | null;
  fields: Record<string, unknown>;
  decision_note: string | null;
}

export interface ApplicationsMe { current: ApplicationRow | null; history: ApplicationRow[] }

/** The applicant's reply to an admin's `info_request` on their current application. */
export async function answer(applicationId: string, answer: string): Promise<Status> {
  return payload<Status>(await call('POST', `/applications/${encodeURIComponent(applicationId)}/answer`, { answer }));
}

export async function applicationsMe(): Promise<ApplicationsMe> {
  return payload<ApplicationsMe>(await call('GET', '/applications/me'));
}

/**
 * Who the visitor is, or null.
 *
 * 401 is an ANSWER here, not a failure — it is how a signed-out visitor is reported, and it is
 * also what a revoked or expired session answers. Every other status still throws, so a broken
 * API is never quietly read as "signed out" (which would send a member to the gate).
 */
export async function me(): Promise<Me | null> {
  const res = await call('GET', '/me');
  if (res.status === 401) return null;
  return payload<Me>(res);
}

export async function signOut(): Promise<Status> {
  return payload<Status>(await call('POST', '/auth/signout'));
}

/** Step-up for `permissions.REAUTH` — stamps `session.reauth_at`, which `deps.require` reads. */
export async function reauth(password: string): Promise<Status> {
  return payload<Status>(await call('POST', '/auth/reauth', { password }));
}
