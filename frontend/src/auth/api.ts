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

/** The buyer or seller application. 202 + the row it created. */
export async function apply(kind: string, fields: Record<string, unknown>): Promise<{ id: string; status: string }> {
  return payload<{ id: string; status: string }>(await call('POST', '/applications', { kind, fields }));
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
