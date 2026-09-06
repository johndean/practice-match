from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import NamedTuple, cast
from uuid import UUID

import psycopg2.extensions


def new_secret(nbytes: int = 32) -> tuple[str, str]:
    raw = secrets.token_urlsafe(nbytes)
    return raw, hash(raw)


def hash(raw: str) -> str:  # the module's own name for it; A-rules are not enabled
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_email_token(conn: psycopg2.extensions.connection, account_id: UUID, purpose: str, ttl: timedelta) -> str:
    raw, h = new_secret()
    with conn.cursor() as cur:
        # now() + interval, not the app clock: one clock owns both the write and the
        # `expires_at > now()` read, so container drift cannot lengthen a link (M4).
        cur.execute("INSERT INTO email_token (account_id, purpose, token_hash, expires_at) VALUES (%s,%s,%s, now() + %s::interval)",
                    (account_id, purpose, h, ttl))
    return raw


def consume_email_token(conn: psycopg2.extensions.connection, raw: str, purpose: str) -> UUID | None:
    with conn.cursor() as cur:
        cur.execute("""UPDATE email_token SET used_at = now()
                        WHERE token_hash = %s AND purpose = %s AND used_at IS NULL AND expires_at > now()
                        RETURNING account_id""", (hash(raw), purpose))
        row = cur.fetchone()
    return row[0] if row else None


@dataclass(frozen=True)
class ApiPrincipal:
    token_id: UUID
    name: str
    role: str
    created_by: UUID  # the account that minted it — the principal's real actor id (I3 fix round 1, Important 10)


class IssuedToken(NamedTuple):
    """What `issue_api_token` mints: the raw `pm_<uuid>.<secret>` value — shown once and never
    stored — beside the row id it was built from.

    The id is returned rather than left to be sliced back out of `raw` (I5 fix round 1, N5): its
    caller writes that id to `audit_log.target_id`, and `raw.split(".", 1)[0][3:]` hard-coded the
    `pm_` prefix length in a second place, where a change to the prefix would have silently started
    recording a mangled id on the one table that cannot be corrected."""

    raw: str
    token_id: UUID


def issue_api_token(conn: psycopg2.extensions.connection, *, name: str, role: str, created_by: UUID, ttl: timedelta) -> IssuedToken:
    secret, h = new_secret()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO api_token (name, role, token_hash, created_by, expires_at) VALUES (%s,%s,%s,%s, now() + %s::interval) RETURNING id",
                    (name, role, h, created_by, ttl))
        # RETURNING id on a just-inserted row always yields exactly one row.
        tid = cast("tuple[UUID]", cur.fetchone())[0]
    return IssuedToken(f"pm_{tid}.{secret}", tid)


def parse(raw: str) -> tuple[UUID, str] | None:
    """A presented api token split into `(token id, secret)`, or None when `raw` is not the
    `pm_<uuid>.<secret>` shape `issue_api_token` mints.

    Split out in I3 fix round 2 so a caller can refuse a malformed bearer BEFORE opening a
    database connection: an anonymous request carrying any `Authorization: Bearer …` header
    otherwise cost one un-pooled Postgres connect apiece, on every guarded route."""
    if not raw.startswith("pm_") or "." not in raw:
        return None
    tid, secret = raw[3:].split(".", 1)
    try:
        return UUID(tid), secret
    except ValueError:
        return None


def verify_api_token(conn: psycopg2.extensions.connection, raw: str) -> ApiPrincipal | None:
    parsed = parse(raw)
    if parsed is None:
        return None
    tid, secret = parsed
    with conn.cursor() as cur:
        # Joined to the creating account and fail-closed on its state (I3 fix round 1, Important
        # 10): a token is a delegation of somebody's authority, so suspending or revoking that
        # somebody must take the token with it. A CI token whose owner has left otherwise stays
        # fully capable for the rest of its 90 days.
        cur.execute("""UPDATE api_token t SET last_used_at = now()
                         FROM account a
                        WHERE a.id = t.created_by
                          AND t.id = %s AND t.token_hash = %s AND t.revoked_at IS NULL AND t.expires_at > now()
                          AND a.state NOT IN ('suspended', 'revoked')
                    RETURNING t.id, t.name, t.role, t.created_by""", (tid, hash(secret)))
        row = cur.fetchone()
    return ApiPrincipal(*row) if row else None
