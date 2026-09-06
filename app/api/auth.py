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

import hashlib
import uuid
from contextlib import closing
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast
from uuid import UUID

import psycopg2.extensions
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.interest import client_ip as rate_limit_subject

# Two client-IP readers, one rule: `deps.client_ip` returns None when there is no valid address (it
# feeds `session.ip`, an `inet` column, where "unknown" would be a cast error), and `interest`'s
# never-None wrapper around it is what a rate-limit subject needs. `normalise` is the project's one
# email rule — see `_address` for why this module reuses it instead of `pydantic.EmailStr`.
from app.api.interest import normalise
from app.auth import audit, labels, limits
from app.auth import passwords as P
from app.auth import sessions as S
from app.auth import tokens as T
from app.auth.deps import AuthError, Unauthenticated, client_ip, require
from app.cache import sync_redis
from app.config import settings
from app.db import sync_conn
from app.mail.outbox import enqueue

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
LOCKOUT_LIMIT, LOCKOUT_WINDOW_S = limits.SIGNIN_EMAIL
REFUSED_STATES = ("suspended", "revoked")
RESETTABLE_STATES = ("verified", "active")   # spec §3: "verified+" — a suspended account has no way back in
DEVICE_MEMORY = timedelta(days=90)
# An address that cannot have been signed up. `account.email` is NOT NULL, so no row can ever carry
# it, which is what lets `signin` and `password/forgot` answer their uniform 401/202 for an input
# that could never be an address instead of a 422 (one distinguishable outcome traded for another)
# or a 500 (fix round 1, Critical 2).
NO_MATCH = ""
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
    # No `max_length` on an ADDRESS. pydantic-core's length check raises on a string carrying a lone
    # surrogate, which turned `signin` and `password/forgot` into a 422 for an input that must get
    # their uniform 401/202 — one distinguishable outcome traded for another (fix round 1, Critical
    # 2 / Minor 1). `normalise` caps the address at 254 characters with an A5 body of its own, so
    # nothing is lost; the password keeps its bound, where an over-long value is neither an
    # existence oracle nor something `P.validate` should be handed unbounded.
    email: str
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
    email: str   # see `Creds.email`


Self = Annotated[S.Principal, Depends(REQUIRE_SELF)]


def set_session_cookies(response: Response, raw: str) -> None:
    """`pm_session` is HttpOnly (script must never read it); `pm_csrf` deliberately is NOT — the app
    reads it to echo the double-submit value back in `X-CSRF-Token` (`deps.check_origin_and_csrf`)."""
    response.set_cookie("pm_session", raw, httponly=True, secure=True, samesite="lax", path="/", max_age=COOKIE_MAX_AGE)
    response.set_cookie("pm_csrf", T.new_secret(CSRF_BYTES)[0], httponly=False, secure=True, samesite="lax", path="/", max_age=COOKIE_MAX_AGE)


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie("pm_session", path="/", httponly=True, secure=True, samesite="lax")
    response.delete_cookie("pm_csrf", path="/", secure=True, samesite="lax")


def _normalised(email: str) -> tuple[str, str] | None:
    """(as typed and trimmed, lookup key), or None for anything that is not an address this app can
    store or look up.

    `app.api.interest.normalise` is the project's one email rule — already reviewed, already tested
    against control characters, bidi overrides and NFKC spoofing — reused rather than re-stated
    here. It is also why this module needs no `pydantic.EmailStr`: that would pull in a new runtime
    dependency (`email-validator`), which is John's to approve, and would answer a malformed address
    with FastAPI's `{"detail": [...]}` envelope instead of decision A5's. It is stricter than
    `EmailStr` on NFKC, forbidden characters and length, and looser on RFC domain form (`a@b..co`
    passes) — recorded here as accepted (fix round 1, Minor 8): the consequence of the looser half
    is a dead `account` row and a bounce, not a security property.

    One rejection is added on top of it (fix round 1, Critical 2): a value that cannot be encoded to
    UTF-8. A lone surrogate survives NFKC and every character class `normalise` forbids, and
    psycopg2 raises `UnicodeEncodeError` before any SQL is sent — a 500 from `ServerErrorMiddleware`,
    which sits outside the security-headers middleware, on endpoints that must answer uniformly."""
    parsed = normalise(email)
    if parsed is None:
        return None
    try:
        parsed[0].encode()
    except UnicodeEncodeError:
        return None
    return parsed


def _lookup_key(email: str) -> str:
    """The address as `signup` stores it, for a lookup that must answer the same way whatever
    arrives. Anything `_normalised` rejects becomes `NO_MATCH`, which matches no row — so a
    malformed address is answered by the ordinary "no such account" path rather than by a 422 or a
    500, either of which would be a distinguishable outcome on the two endpoints whose whole purpose
    is that they are not."""
    parsed = _normalised(email)
    return parsed[1] if parsed else NO_MATCH


def _address(email: str) -> tuple[str, str]:
    """(as typed and trimmed, lookup key) for an address being STORED, or a 422."""
    parsed = _normalised(email)
    if parsed is None:
        raise EmailInvalid
    return parsed


def _pseudonym(subject: str) -> str:
    """A subject's truncated SHA-256 — the construction `app.ratelimit.bucket_key` already uses for
    every address that enters Redis. Not an anonymisation (a dictionary attack reverses it): it
    keeps attacker-supplied text, possibly nobody's address, out of a table whose triggers refuse
    UPDATE and DELETE (fix round 1, Minor 5)."""
    return hashlib.sha256(subject.encode()).hexdigest()[:16]


def _outbox_key() -> str:
    """A fresh idempotency key. Never a prefix of a live secret: the keys used to embed `token[:8]`
    of a verify/reset token and `raw[:8]` of a newly issued SESSION id, in a table the I6 sender and
    any future admin outbox screen read (fix round 1, Minor 3)."""
    return uuid.uuid4().hex


def _floor(pw: str, *, privileged: bool) -> None:
    """The length and strength floor. Microseconds, and the only half of the policy that needs to
    know whether the account is privileged — which for a reset is only knowable from the database."""
    try:
        P.validate(pw, privileged=privileged)
    except P.PasswordPolicyError as e:
        raise PasswordPolicy(str(e)) from None


async def _screen(pw: str) -> None:
    """The half of the policy that needs NO database: the ordinary floor and the breach screen.

    Always called before a connection is opened. `is_pwned_async`, never the blocking `is_pwned`: it
    is a 2 s-timeout network call, and holding a Postgres transaction across it parks a backend
    idle-in-transaction for the whole timeout (fix round 1, Important 5)."""
    _floor(pw, privileged=False)
    if await P.is_pwned_async(pw):
        raise PasswordPolicy("That password has appeared in a data breach. Choose another.")


def _session_only(principal: S.Principal) -> S.Principal:
    """Spec §3's Auth column for sign-out, sign-out-everywhere, re-auth and password change is
    "session + CSRF". `account.self` is granted to every non-anonymous role, so an api token passed
    all four — and `deps.check_origin_and_csrf` returns early for a non-session principal, so
    neither the double-submit nor the Origin check applied. A leaked long-lived CI token could hold
    its creating admin signed out of every device (fix round 1, Important 2). The refusal is the
    generic anonymous 401: nothing about the credential is disclosed."""
    if principal.kind != "session":
        raise Unauthenticated
    return principal


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


def me_payload(conn: psycopg2.extensions.connection, principal: S.Principal) -> dict[str, Any] | None:
    """The design's persona strings, computed from the matrix rather than stored: `role` and
    `initials` are what the header and the account menu render.

    None when the principal names no `account` row. That is true for session and api-token
    principals — a session joins the account and a token's `created_by` is a real foreign key — and
    false for `deps.LEGACY_ADMIN`, the synthetic id the operator bearer resolves to."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, email, display_name, state, affiliation_label FROM account WHERE id=%s", (principal.account_id,))
        row = cur.fetchone()
    if row is None:
        return None
    roles = sorted(principal.roles)
    return {"id": str(row[0]), "email": row[1], "name": row[2] or "", "role": labels.role_label(frozenset(roles), row[4]),
            "initials": labels.initials(row[2] or ""), "state": row[3], "roles": roles, "affiliation_label": row[4]}


@router.post("/auth/signup", status_code=202)
async def signup(body: Creds, request: Request) -> dict[str, str]:
    """Uniform: a new address and an address already registered get the same 202, the same body and
    — since fix round 1's Critical 1 — the same commit-level work. Only the new one is created; both
    queue exactly one outbox row, so the COMMIT pays a WAL flush either way."""
    r = sync_redis()
    limits.hit(r, "signup:ip", rate_limit_subject(request), *limits.SIGNUP_IP)
    as_typed, key = _address(body.email)
    limits.hit(r, "signup:email", key, *limits.SIGNUP_EMAIL)
    # Screened and hashed BEFORE any connection: the breach screen is a 2 s-timeout network call and
    # the hash is ~97 ms, neither of which may be held across an open transaction.
    await _screen(body.password)
    hashed = await P.hash_async(body.password)
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,%s,'unverified') ON CONFLICT (email) DO NOTHING RETURNING id", (as_typed, hashed))
            row = cur.fetchone()
        if row:
            token = T.issue_email_token(conn, row[0], "verify", VERIFY_TTL)
            enqueue(conn, to=as_typed, template="verify_email", params={"link": _link("/verify", token)}, idempotency_key=_outbox_key())
        else:
            # The address is already registered, so its OWNER is told somebody tried to sign up as
            # them — equal work, and the only useful thing to do with the attempt. Addressed to the
            # normalised form the caller supplied: `account.email` is citext, so it is the same
            # mailbox as the stored row, differing at most in case.
            enqueue(conn, to=as_typed, template="account_exists", params={}, idempotency_key=_outbox_key())
    return {"status": "check_email"}


@router.post("/auth/verify")
async def verify(body: TokenIn, request: Request) -> dict[str, str]:
    limits.hit(sync_redis(), "verify:ip", rate_limit_subject(request), *limits.TOKEN_IP)
    with closing(sync_conn()) as conn, conn:
        account_id = T.consume_email_token(conn, body.token, "verify")
        if not account_id:
            raise TokenInvalid
        with conn.cursor() as cur:
            cur.execute("UPDATE account SET state='verified' WHERE id=%s AND state='unverified'", (account_id,))
    return {"status": "verified"}


def _unfamiliar_device(conn: psycopg2.extensions.connection, account_id: UUID, ip: str | None, ua: str | None) -> bool:
    """True when this account has no session from the same `(ip, user_agent)` pair inside
    `DEVICE_MEMORY`. Read BEFORE the new session is written, or it would always match itself."""
    with conn.cursor() as cur:
        cur.execute("""SELECT NOT EXISTS (SELECT 1 FROM session
                                           WHERE account_id = %s AND created_at > now() - %s::interval
                                             AND ip IS NOT DISTINCT FROM %s::inet
                                             AND user_agent IS NOT DISTINCT FROM %s::text)""",
                    (account_id, DEVICE_MEMORY, ip, ua))
        return cast("tuple[bool]", cur.fetchone())[0]


@router.post("/auth/signin")
async def signin(body: Creds, request: Request, response: Response) -> dict[str, Any]:
    r = sync_redis()
    ip = client_ip(request)
    ua = request.headers.get("user-agent")
    key = _lookup_key(body.email)
    # CHECKED, not counted: spec §3's lockout is ten FAILURES per address per 15 minutes, so this
    # attempt is counted only if the credential turns out to be wrong (fix round 1, Important 1).
    #
    # `NO_MATCH` is exempt (fix round 2, NEW-3): every malformed address normalises to the same
    # empty key, so counting them together locked ONE shared bucket for every caller in the window,
    # from any source IP. The per-IP limiter below still bounds the caller, and skipping the
    # per-address one discloses nothing — an address's malformedness is knowable client-side.
    if key:
        limits.check(r, "signin:email", key, LOCKOUT_LIMIT, LOCKOUT_WINDOW_S)
    limits.hit(r, "signin:ip", rate_limit_subject(request), *limits.SIGNIN_IP)
    with closing(sync_conn()) as lookup, lookup, lookup.cursor() as cur:
        cur.execute("""SELECT a.id, a.password_hash, a.state,
                              EXISTS (SELECT 1 FROM role_grant g WHERE g.account_id = a.id AND g.role IN ('staff','admin') AND g.revoked_at IS NULL)
                         FROM account a WHERE a.email = %s""", (key,))
        row = cur.fetchone()
    # The connection is RELEASED before the Argon2id hop. Holding it would park a Postgres backend
    # idle-in-transaction for ~97 ms per sign-in, which a burst turns into connection exhaustion
    # (fix round 1, Important 5). The verify runs for an unknown address too, against a hash of the
    # same cost: without it the 401 for "no such account" comes back in microseconds and the one for
    # "wrong password" in ~100 ms, which is an account-enumeration oracle whatever the body says.
    ok = await P.verify_async(body.password, row[1] if row else P.DUMMY_HASH)
    rehash: str | None = None
    if ok and row is not None and P.needs_rehash(row[1]):
        rehash = await P.hash_async(body.password)

    if row is None or not ok or row[2] in REFUSED_STATES:
        with closing(sync_conn()) as conn, conn:
            # 0 for `NO_MATCH`, so a burst of malformed addresses neither fills a shared bucket nor
            # writes an audit row identifying nothing but the pseudonym of the empty string (NEW-3).
            fails = limits.count_failure(r, "signin:email", key, LOCKOUT_WINDOW_S) if key else 0
            if fails == FAILURE_BURST:
                audit.write(conn, actor=None, action="signin.failure_burst", target_type="account",
                            target_id=row[0] if row else _pseudonym(key), request=request)
            if ok and row is not None:
                # Spec §3: a suspended or revoked account gets the generic 401 AND an audit row —
                # the compensating control for a deliberately uninformative refusal, and exactly the
                # signal an admin who has just suspended somebody wants to see (Important 3).
                audit.write(conn, actor=None, action="signin.refused_state", target_type="account",
                            target_id=row[0], reason=row[2], request=request)
        # Outside the transaction block ON PURPOSE: raising inside it would roll those rows back
        # together with the refusal, so the one record of the attempt would never exist.
        raise InvalidCredentials

    account_id, privileged = row[0], row[3]
    with closing(sync_conn()) as conn, conn:
        if rehash is not None:
            with conn.cursor() as cur:
                cur.execute("UPDATE account SET password_hash=%s WHERE id=%s", (rehash, account_id))
        # Only staff and admin: spec §3 lists `signin_new_device` among the compensating controls
        # for the roles that have no second factor (fix round 1, Minor 12).
        new_device = privileged and _unfamiliar_device(conn, account_id, ip, ua)
        raw = S.create(conn, r, account_id, ip, ua)
        with conn.cursor() as cur:
            cur.execute("UPDATE account SET last_sign_in_at=now() WHERE id=%s", (account_id,))
        if new_device:
            enqueue(conn, to=_email_of(conn, account_id), template="signin_new_device",
                    params={"ip": ip, "user_agent": ua, "when": datetime.now(UTC).isoformat()}, idempotency_key=_outbox_key())
        limits.clear(r, "signin:email", key, LOCKOUT_WINDOW_S)
        set_session_cookies(response, raw)
        # `S.create` has just written and cached this principal, so this resolves from Redis, and
        # the account row it reads is the one this transaction is holding.
        return cast("dict[str, Any]", me_payload(conn, cast("S.Principal", S.resolve(conn, r, raw))))


@router.post("/auth/signout")
async def signout(request: Request, response: Response, principal: Self) -> dict[str, str]:
    _session_only(principal)
    # `_session_only` guarantees a session principal, which can only exist because this cookie
    # resolved; `or ""` keeps the handler total if that ever stops being true, since hashing the
    # empty string matches no row. (It replaces `request.cookies["pm_session"]`, which was a
    # KeyError — a 500 — for the bearer callers the guard now refuses outright.)
    raw = request.cookies.get("pm_session") or ""
    with closing(sync_conn()) as conn, conn:
        S.revoke(conn, sync_redis(), raw)
    clear_session_cookies(response)
    return {"status": "signed_out"}


@router.post("/auth/signout-all")
async def signout_all(response: Response, principal: Self) -> dict[str, str]:
    _session_only(principal)
    with closing(sync_conn()) as conn, conn:
        S.revoke_all(conn, sync_redis(), principal.account_id)
    clear_session_cookies(response)
    return {"status": "signed_out"}


@router.post("/auth/password/forgot", status_code=202)
async def forgot(body: EmailIn, request: Request) -> dict[str, str]:
    """Uniform: a known address and an unknown one get the same 202 and the same body; only a
    `verified` or `active` account is emailed. `unverified` is excluded because a reset link would
    be a way to take over an address whose owner has never proved they hold it; `suspended` and
    `revoked` because neither may be signed into (spec §3's "verified+", fix round 1, Minor 7)."""
    r = sync_redis()
    key = _lookup_key(body.email)
    limits.hit(r, "forgot:ip", rate_limit_subject(request), *limits.FORGOT_IP)
    if key:   # `NO_MATCH` is exempt — see `signin` (fix round 2, NEW-3)
        limits.hit(r, "forgot:email", key, *limits.FORGOT_EMAIL)
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM account WHERE email=%s AND state = ANY(%s)", (key, list(RESETTABLE_STATES)))
            row = cur.fetchone()
        if row:
            with conn.cursor() as cur:
                # One live reset link per account: issuing a new one retires the last, so a link
                # mailed an hour ago cannot still be used after its owner asked for another.
                cur.execute("UPDATE email_token SET used_at = now() WHERE account_id=%s AND purpose='reset' AND used_at IS NULL", (row[0],))
            token = T.issue_email_token(conn, row[0], "reset", RESET_TTL)
            enqueue(conn, to=_email_of(conn, row[0]), template="password_reset", params={"link": _link("/reset", token)},
                    idempotency_key=_outbox_key())
    return {"status": "check_email"}


@router.post("/auth/password/reset")
async def reset(body: ResetIn, request: Request) -> dict[str, str]:
    limits.hit(sync_redis(), "reset:ip", rate_limit_subject(request), *limits.TOKEN_IP)
    # Screened and hashed before the connection; the PRIVILEGED floor is re-checked inside, because
    # only the database knows whether this account is staff (Important 5).
    await _screen(body.password)
    hashed = await P.hash_async(body.password)
    with closing(sync_conn()) as conn, conn:
        account_id = T.consume_email_token(conn, body.token, "reset")
        if not account_id:
            raise TokenInvalid
        with conn.cursor() as cur:
            cur.execute("SELECT EXISTS (SELECT 1 FROM role_grant WHERE account_id=%s AND role IN ('staff','admin') AND revoked_at IS NULL)", (account_id,))
            privileged = cast("tuple[bool]", cur.fetchone())[0]
        # A policy refusal here rolls the token consumption back with it, so a link is never burnt
        # by a password the policy was always going to reject.
        _floor(body.password, privileged=privileged)
        with conn.cursor() as cur:
            cur.execute("UPDATE account SET password_hash=%s WHERE id=%s", (hashed, account_id))
        # Every other session goes: a reset is what somebody who has LOST the account does.
        S.revoke_all(conn, sync_redis(), account_id)
        audit.write(conn, actor=None, action="password.reset", target_type="account", target_id=account_id, request=request)
        enqueue(conn, to=_email_of(conn, account_id), template="password_changed", params={}, idempotency_key=_outbox_key())
    return {"status": "reset"}


@router.post("/auth/password/change")
async def change(body: ChangeIn, request: Request, response: Response, principal: Self) -> dict[str, str]:
    """Supplying the current password IS the re-authentication spec §3's Auth column asks for here;
    `account.self` is deliberately not in `permissions.REAUTH`, and `POST /api/auth/reauth` is for
    the REAUTH permissions (Revoke, licence decisions, engine activation, role grants) rather than a
    prerequisite for this route (fix round 1, Minor 9)."""
    _session_only(principal)
    r = sync_redis()
    with closing(sync_conn()) as lookup, lookup:
        current = _password_hash_of(lookup, principal.account_id)
    # Released before both Argon2id hops and the breach screen (Important 5). `principal.roles` is
    # already known, so the privileged floor needs no database either.
    if current is None or not await P.verify_async(body.current, current):
        raise InvalidCredentials
    _floor(body.new, privileged=bool(principal.roles & {"staff", "admin"}))
    await _screen(body.new)
    hashed = await P.hash_async(body.new)
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE account SET password_hash=%s WHERE id=%s", (hashed, principal.account_id))
        # Every session is revoked and THIS one re-issued, so the person who made the change stays
        # signed in and everybody else is turned out.
        S.revoke_all(conn, r, principal.account_id)
        raw = S.create(conn, r, principal.account_id, client_ip(request), request.headers.get("user-agent"))
        set_session_cookies(response, raw)
        audit.write(conn, actor=principal, action="password.change", target_type="account", target_id=principal.account_id, request=request)
        enqueue(conn, to=_email_of(conn, principal.account_id), template="password_changed", params={}, idempotency_key=_outbox_key())
    return {"status": "changed"}


@router.post("/auth/reauth")
async def reauth(body: PasswordIn, principal: Self) -> dict[str, str]:
    """Step-up for `permissions.REAUTH` actions: stamps `session.reauth_at`, which `deps.require`
    then reads (and which expires after `deps.REAUTH_WINDOW`)."""
    _session_only(principal)
    with closing(sync_conn()) as lookup, lookup:
        current = _password_hash_of(lookup, principal.account_id)
    if current is None or not await P.verify_async(body.password, current):
        raise InvalidCredentials
    with closing(sync_conn()) as conn, conn:
        S.set_reauth(conn, sync_redis(), principal)
    return {"status": "reauthenticated"}


@router.get("/me")
async def me(principal: Self) -> dict[str, Any]:
    with closing(sync_conn()) as conn, conn:
        payload = me_payload(conn, principal)
    # None for a principal that names no `account` row — `deps.LEGACY_ADMIN`, the synthetic id the
    # `API_SECRET_KEY` bearer resolves to. Reading `[0]` off the missing row was a 500 carrying no
    # security headers, on the one credential the plan keeps alive until I9 (fix round 1, Important 4).
    if payload is None:
        raise Unauthenticated
    return payload
