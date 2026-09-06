"""Spec §3. Every response that could reveal whether an email exists is identical for both cases.

Two shapes here are deliberate and load-bearing:

* **Refusals are `app.auth.deps.AuthError` subclasses, not bare `HTTPException`s.** FastAPI renders an
  ordinary `HTTPException` as `{"detail": ...}`; decision A5's body is `{"error": {"code", "message"}}`
  and the ONE handler that produces it is registered by `deps.install(app)` for `AuthError`. A bare
  `HTTPException(401, detail={"error": ...})` would have shipped `{"detail": {"error": ...}}`.
* **Connections are opened with `closing(sync_conn()) as conn, conn`,** exactly as
  `app.auth.deps._session_principal` does: psycopg2's own `with conn:` is the TRANSACTION manager and
  commits WITHOUT closing, so `with sync_conn() as conn:` alone leaks a connection per request.
  psycopg2 2.9 opens a real transaction there even though `sync_conn()` sets `autocommit`, which is
  what makes each endpoint atomic — and what means a refusal raised INSIDE the block rolls back
  everything the request wrote. That is the behaviour wanted everywhere but one place: `signin`
  raises its 401 outside the block, so the audit row a failure burst writes survives the refusal.
"""
from __future__ import annotations

import unicodedata
from contextlib import closing
from datetime import timedelta
from typing import Annotated, Any, cast
from uuid import UUID

import psycopg2.extensions
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

# Two client-IP readers, one rule: `deps.client_ip` returns None when there is no valid address (it
# feeds `session.ip`, an `inet` column, where "unknown" would be a cast error), and `interest`'s
# never-None wrapper around it is what a rate-limit subject needs. `normalise` is the project's one
# email rule — see `_address` for why this module reuses it instead of `pydantic.EmailStr`.
from app.api.interest import MAX_EMAIL_LEN, normalise
from app.api.interest import client_ip as rate_limit_subject
from app.auth import audit, labels, limits
from app.auth import passwords as P
from app.auth import sessions as S
from app.auth import tokens as T
from app.auth.deps import AuthError, client_ip, require
from app.cache import sync_redis
from app.config import settings
from app.db import sync_conn
from app.mail.outbox import enqueue
from app.ratelimit import bucket_key

router = APIRouter(prefix="/api")

# Hoisted to module-level constants, never wrapped in another callable: the route-guard and audit
# drift tests (tests/auth/test_permissions.py) resolve a route's permission by the guard's OBJECT
# IDENTITY, and a fresh `require(...)` per route would still resolve — but a wrapper would not.
REQUIRE_SELF = require("account.self")

VERIFY_TTL = timedelta(hours=24)
RESET_TTL = timedelta(hours=1)
COOKIE_MAX_AGE = int(S.ABSOLUTE.total_seconds())
CSRF_BYTES = 16
# The failure count that earns an audit row. Counted in its own Redis window, keyed through
# `ratelimit.bucket_key` like every other subject the auth endpoints count, so an address enters
# Redis only as a truncated SHA-256 pseudonym (app/ratelimit.py's stated policy) rather than as the
# raw `fails:<email>` key.
FAILURE_BURST = 5
FAILS_WINDOW_S = limits.SIGNIN_EMAIL[1]   # the same window the per-address lockout uses
MAX_PASSWORD_IN = 1024  # above policy MAX_LEN, so an over-long password gets the policy message, not a schema error
MAX_TOKEN_IN = 512


class InvalidCredentials(AuthError):
    """Spec §3's single answer for a wrong password, an unknown address, a suspended account and a
    revoked one — byte-identical in all four cases, after the same Argon2id work (`P.DUMMY_HASH`)."""

    status = 401
    code = "INVALID_CREDENTIALS"
    message = "Email or password is incorrect."


class TokenInvalid(AuthError):
    status = 400
    code = "TOKEN_INVALID"
    message = "This link is invalid or has expired."


class EmailInvalid(AuthError):
    status = 422
    code = "EMAIL_INVALID"
    message = "Enter a valid email address."


class PasswordPolicy(AuthError):
    """The only refusal here that carries a per-case message: the policy's own words are what tells
    somebody how to pick a password that will be accepted."""

    status = 422
    code = "PASSWORD_POLICY"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__()


class Creds(BaseModel):
    email: str = Field(max_length=MAX_EMAIL_LEN)
    password: str = Field(max_length=MAX_PASSWORD_IN)


class TokenIn(BaseModel):
    token: str = Field(max_length=MAX_TOKEN_IN)


class ResetIn(BaseModel):
    token: str = Field(max_length=MAX_TOKEN_IN)
    password: str = Field(max_length=MAX_PASSWORD_IN)


class ChangeIn(BaseModel):
    current: str = Field(max_length=MAX_PASSWORD_IN)
    new: str = Field(max_length=MAX_PASSWORD_IN)


class PasswordIn(BaseModel):
    password: str = Field(max_length=MAX_PASSWORD_IN)


class EmailIn(BaseModel):
    email: str = Field(max_length=MAX_EMAIL_LEN)


Self = Annotated[S.Principal, Depends(REQUIRE_SELF)]


def set_session_cookies(response: Response, raw: str) -> None:
    """`pm_session` is HttpOnly (script must never read it); `pm_csrf` deliberately is NOT — the app
    reads it to echo the double-submit value back in `X-CSRF-Token` (`deps.check_origin_and_csrf`)."""
    response.set_cookie("pm_session", raw, httponly=True, secure=True, samesite="lax", path="/", max_age=COOKIE_MAX_AGE)
    response.set_cookie("pm_csrf", T.new_secret(CSRF_BYTES)[0], httponly=False, secure=True, samesite="lax", path="/", max_age=COOKIE_MAX_AGE)


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie("pm_session", path="/", httponly=True, secure=True, samesite="lax")
    response.delete_cookie("pm_csrf", path="/", secure=True, samesite="lax")


def _lookup_key(email: str) -> str:
    """The address as `signup` stores it, for a lookup that must answer the same way whatever
    arrives: NFKC-normalised (so a composed and a decomposed spelling are one address, M2), trimmed
    and lower-cased. `account.email` is `citext`, so this matches the stored as-typed casing.

    Deliberately NOT a validation: an address that could never have been signed up simply matches no
    row, and `signin`/`password/forgot` then answer their uniform 401/202 for it — a malformed
    address must not be a distinguishable outcome."""
    return unicodedata.normalize("NFKC", email).strip().lower()


def _address(email: str) -> tuple[str, str]:
    """(as typed and trimmed, lookup key) for an address being STORED, or a 422.

    `app.api.interest.normalise` is the project's one email rule — already reviewed, already tested
    against control characters, bidi overrides and NFKC spoofing — reused rather than re-stated
    here. It is also why this module needs no `pydantic.EmailStr`: that would pull in a new runtime
    dependency (`email-validator`), which is John's to approve, and would answer a malformed address
    with FastAPI's `{"detail": [...]}` envelope instead of decision A5's."""
    parsed = normalise(email)
    if parsed is None:
        raise EmailInvalid
    return parsed


async def _policy(pw: str, *, privileged: bool) -> None:
    try:
        P.validate(pw, privileged=privileged)
    except P.PasswordPolicyError as e:
        raise PasswordPolicy(str(e)) from None
    # `is_pwned_async`, never the blocking `is_pwned`: it is a 2 s-timeout network call, and on the
    # event loop every other request would queue behind a degraded HIBP for that full timeout.
    if await P.is_pwned_async(pw):
        raise PasswordPolicy("That password has appeared in a data breach. Choose another.")


def _link(path: str, token: str) -> str:
    return f"{settings.link_base_url}{path}?token={token}"


def _password_hash_of(conn: psycopg2.extensions.connection, account_id: UUID) -> str | None:
    """The stored hash, or None when the principal names no account row — which the LEGACY operator
    principal (`deps.LEGACY_ADMIN`) does: it passes `account.self` but has no password to confirm,
    and reading `[0]` off the missing row would have been a 500 on a credential path."""
    with conn.cursor() as cur:
        cur.execute("SELECT password_hash FROM account WHERE id=%s", (account_id,))
        row = cur.fetchone()
    return cast("str", row[0]) if row else None


def _email_of(conn: psycopg2.extensions.connection, account_id: UUID) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (account_id,))
        # Only ever called for an account this request has already read or written.
        return cast("tuple[str]", cur.fetchone())[0]


def me_payload(conn: psycopg2.extensions.connection, principal: S.Principal) -> dict[str, Any]:
    """The design's persona strings, computed from the matrix rather than stored: `role` and
    `initials` are what the header and the account menu render."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, email, display_name, state, affiliation_label FROM account WHERE id=%s", (principal.account_id,))
        # A principal only exists because its account row does (sessions._load joins it).
        row = cast("tuple[Any, ...]", cur.fetchone())
    roles = sorted(principal.roles)
    return {"id": str(row[0]), "email": row[1], "name": row[2] or "", "role": labels.role_label(frozenset(roles), row[4]),
            "initials": labels.initials(row[2] or ""), "state": row[3], "roles": roles, "affiliation_label": row[4]}


@router.post("/auth/signup", status_code=202)
async def signup(body: Creds, request: Request) -> dict[str, str]:
    """Uniform: a new address and an address already registered get the same 202 and the same body.
    Only the new one is written, and only the new one is emailed."""
    r = sync_redis()
    limits.hit(r, "signup:ip", rate_limit_subject(request), *limits.SIGNUP_IP)
    as_typed, key = _address(body.email)
    limits.hit(r, "signup:email", key, *limits.SIGNUP_EMAIL)
    await _policy(body.password, privileged=False)
    hashed = await P.hash_async(body.password)
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,%s,'unverified') ON CONFLICT (email) DO NOTHING RETURNING id", (as_typed, hashed))
            row = cur.fetchone()
        if row:
            token = T.issue_email_token(conn, row[0], "verify", VERIFY_TTL)
            enqueue(conn, to=as_typed, template="verify_email", params={"link": _link("/verify", token)}, idempotency_key=f"{row[0]}:verify_email:{token[:8]}")
    return {"status": "check_email"}


@router.post("/auth/verify")
async def verify(body: TokenIn) -> dict[str, str]:
    with closing(sync_conn()) as conn, conn:
        account_id = T.consume_email_token(conn, body.token, "verify")
        if not account_id:
            raise TokenInvalid
        with conn.cursor() as cur:
            cur.execute("UPDATE account SET state='verified' WHERE id=%s AND state='unverified'", (account_id,))
    return {"status": "verified"}


@router.post("/auth/signin")
async def signin(body: Creds, request: Request, response: Response) -> dict[str, Any]:
    r = sync_redis()
    ip = client_ip(request)
    key = _lookup_key(body.email)
    limits.hit(r, "signin:email", key, *limits.SIGNIN_EMAIL)
    limits.hit(r, "signin:ip", rate_limit_subject(request), *limits.SIGNIN_IP)
    fails_key = bucket_key("signin:fails", key, FAILS_WINDOW_S)
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, password_hash, state FROM account WHERE email=%s", (key,))
            row = cur.fetchone()
        # The verify runs for an unknown address too, against a hash of the same cost: without it
        # the 401 for "no such account" comes back in microseconds and the one for "wrong password"
        # in ~100 ms, which is an account-enumeration oracle whatever the body says.
        ok = await P.verify_async(body.password, row[1] if row else P.DUMMY_HASH)
        if row and ok and row[2] not in ("suspended", "revoked"):
            if P.needs_rehash(row[1]):
                with conn.cursor() as cur:
                    cur.execute("UPDATE account SET password_hash=%s WHERE id=%s", (await P.hash_async(body.password), row[0]))
            raw = S.create(conn, r, row[0], ip, request.headers.get("user-agent"))
            with conn.cursor() as cur:
                cur.execute("UPDATE account SET last_sign_in_at=now() WHERE id=%s", (row[0],))
            r.delete(fails_key)
            set_session_cookies(response, raw)
            # `S.create` has just written and cached this principal, so this resolves from Redis.
            return me_payload(conn, cast("S.Principal", S.resolve(conn, r, raw)))
        with r.pipeline(transaction=True) as pipe:
            pipe.incr(fails_key)
            pipe.expire(fails_key, FAILS_WINDOW_S)
            fails, _ = pipe.execute()
        if int(fails) == FAILURE_BURST:
            audit.write(conn, actor=None, action="signin.failure_burst", target_type="account", target_id=key, request=request)
    # Outside the transaction block ON PURPOSE: raising inside it would roll the audit row back
    # together with the refusal, so the one record of a burst of failed attempts would never exist.
    raise InvalidCredentials


@router.post("/auth/signout")
async def signout(request: Request, response: Response, principal: Self) -> dict[str, str]:
    raw = request.cookies.get("pm_session")
    with closing(sync_conn()) as conn, conn:
        # None for a caller authenticated by an api token or the legacy operator bearer: there is no
        # session to revoke, and clearing the cookies is still the right (empty) answer.
        if raw is not None:
            S.revoke(conn, sync_redis(), raw)
    clear_session_cookies(response)
    return {"status": "signed_out"}


@router.post("/auth/signout-all")
async def signout_all(response: Response, principal: Self) -> dict[str, str]:
    with closing(sync_conn()) as conn, conn:
        S.revoke_all(conn, sync_redis(), principal.account_id)
    clear_session_cookies(response)
    return {"status": "signed_out"}


@router.post("/auth/password/forgot", status_code=202)
async def forgot(body: EmailIn) -> dict[str, str]:
    """Uniform: a known address and an unknown one get the same 202 and the same body; only a known,
    reachable account is emailed. `unverified` is excluded because a reset link would be a way to
    take over an address whose owner has never proved they hold it; `revoked` because it is gone."""
    r = sync_redis()
    key = _lookup_key(body.email)
    limits.hit(r, "forgot:email", key, *limits.FORGOT_EMAIL)
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM account WHERE email=%s AND state NOT IN ('unverified','revoked')", (key,))
            row = cur.fetchone()
        if row:
            token = T.issue_email_token(conn, row[0], "reset", RESET_TTL)
            enqueue(conn, to=_email_of(conn, row[0]), template="password_reset", params={"link": _link("/reset", token)},
                    idempotency_key=f"{row[0]}:password_reset:{token[:8]}")
    return {"status": "check_email"}


@router.post("/auth/password/reset")
async def reset(body: ResetIn, request: Request) -> dict[str, str]:
    with closing(sync_conn()) as conn, conn:
        account_id = T.consume_email_token(conn, body.token, "reset")
        if not account_id:
            raise TokenInvalid
        with conn.cursor() as cur:
            cur.execute("SELECT EXISTS (SELECT 1 FROM role_grant WHERE account_id=%s AND role IN ('staff','admin') AND revoked_at IS NULL)", (account_id,))
            privileged = cast("tuple[bool]", cur.fetchone())[0]
        await _policy(body.password, privileged=privileged)
        with conn.cursor() as cur:
            cur.execute("UPDATE account SET password_hash=%s WHERE id=%s", (await P.hash_async(body.password), account_id))
        # Every other session goes: a reset is what somebody who has LOST the account does.
        S.revoke_all(conn, sync_redis(), account_id)
        audit.write(conn, actor=None, action="password.reset", target_type="account", target_id=account_id, request=request)
        enqueue(conn, to=_email_of(conn, account_id), template="password_changed", params={}, idempotency_key=f"{account_id}:password_changed:{body.token[:8]}")
    return {"status": "reset"}


@router.post("/auth/password/change")
async def change(body: ChangeIn, request: Request, response: Response, principal: Self) -> dict[str, str]:
    r = sync_redis()
    with closing(sync_conn()) as conn, conn:
        current = _password_hash_of(conn, principal.account_id)
        if current is None or not await P.verify_async(body.current, current):
            raise InvalidCredentials
        await _policy(body.new, privileged=bool(principal.roles & {"staff", "admin"}))
        with conn.cursor() as cur:
            cur.execute("UPDATE account SET password_hash=%s WHERE id=%s", (await P.hash_async(body.new), principal.account_id))
        # Every session is revoked and THIS one re-issued, so the person who made the change stays
        # signed in and everybody else is turned out.
        S.revoke_all(conn, r, principal.account_id)
        raw = S.create(conn, r, principal.account_id, client_ip(request), request.headers.get("user-agent"))
        set_session_cookies(response, raw)
        audit.write(conn, actor=principal, action="password.change", target_type="account", target_id=principal.account_id, request=request)
        enqueue(conn, to=_email_of(conn, principal.account_id), template="password_changed", params={}, idempotency_key=f"{principal.account_id}:password_changed:{raw[:8]}")
    return {"status": "changed"}


@router.post("/auth/reauth")
async def reauth(body: PasswordIn, principal: Self) -> dict[str, str]:
    """Step-up for `permissions.REAUTH` actions: stamps `session.reauth_at`, which `deps.require`
    then reads (and which expires after `deps.REAUTH_WINDOW`)."""
    with closing(sync_conn()) as conn, conn:
        current = _password_hash_of(conn, principal.account_id)
        if current is None or not await P.verify_async(body.password, current):
            raise InvalidCredentials
        S.set_reauth(conn, sync_redis(), principal)
    return {"status": "reauthenticated"}


@router.get("/me")
async def me(principal: Self) -> dict[str, Any]:
    with closing(sync_conn()) as conn, conn:
        return me_payload(conn, principal)
