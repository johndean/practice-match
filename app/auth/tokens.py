from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import cast
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


def issue_api_token(conn: psycopg2.extensions.connection, *, name: str, role: str, created_by: UUID, ttl: timedelta) -> str:
    secret, h = new_secret()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO api_token (name, role, token_hash, created_by, expires_at) VALUES (%s,%s,%s,%s, now() + %s::interval) RETURNING id",
                    (name, role, h, created_by, ttl))
        # RETURNING id on a just-inserted row always yields exactly one row.
        tid = cast("tuple[UUID]", cur.fetchone())[0]
    return f"pm_{tid}.{secret}"


def verify_api_token(conn: psycopg2.extensions.connection, raw: str) -> ApiPrincipal | None:
    if not raw.startswith("pm_") or "." not in raw:
        return None
    tid, secret = raw[3:].split(".", 1)
    with conn.cursor() as cur:
        cur.execute("""UPDATE api_token SET last_used_at = now()
                        WHERE id::text = %s AND token_hash = %s AND revoked_at IS NULL AND expires_at > now()
                        RETURNING id, name, role""", (tid, hash(secret)))
        row = cur.fetchone()
    return ApiPrincipal(*row) if row else None
