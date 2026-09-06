"""Server-side sessions with a Redis principal cache that is deleted, never waited out, on any change (spec §3, S4)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID

import psycopg2.extensions
import redis as redis_sync

from app.auth import tokens

IDLE, ABSOLUTE, CACHE_TTL, TOUCH_EVERY = timedelta(days=14), timedelta(days=30), 60, timedelta(minutes=5)


@dataclass(frozen=True)
class Principal:
    account_id: UUID
    state: str
    roles: frozenset[str]
    reauth_at: datetime | None
    kind: Literal["session", "token", "legacy"]
    session_hash: str | None = None


def hash_id(raw: str) -> str:
    return tokens.hash(raw)


def _load(conn: psycopg2.extensions.connection, h: str) -> Principal | None:
    with conn.cursor() as cur:
        cur.execute("""SELECT s.account_id, a.state, s.reauth_at,
                              COALESCE((SELECT array_agg(role) FROM role_grant g WHERE g.account_id = s.account_id AND g.revoked_at IS NULL), '{}')
                         FROM session s JOIN account a ON a.id = s.account_id
                        WHERE s.id_hash = %s AND s.revoked_at IS NULL AND s.expires_at > now()
                          AND s.last_seen_at > now() - %s""", (h, IDLE))
        row = cur.fetchone()
    return Principal(row[0], row[1], frozenset(row[3]), row[2], "session", h) if row else None


def _cache_set(r: redis_sync.Redis, p: Principal) -> None:
    h = cast(str, p.session_hash)  # only ever called with a Principal freshly loaded/cached for a session, never None
    r.set(f"session:{h}", json.dumps({"a": str(p.account_id), "s": p.state, "r": sorted(p.roles), "re": p.reauth_at.isoformat() if p.reauth_at else None}), ex=CACHE_TTL)
    r.sadd(f"account:{p.account_id}:sessions", h)


def create(conn: psycopg2.extensions.connection, r: redis_sync.Redis, account_id: UUID, ip: str | None, ua: str | None) -> str:
    raw, h = tokens.new_secret()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO session (id_hash, account_id, expires_at, ip, user_agent) VALUES (%s,%s,%s,%s,%s)",
                    (h, account_id, datetime.now(UTC) + ABSOLUTE, ip, ua))
    p = _load(conn, h)
    if p:
        _cache_set(r, p)
    return raw


def resolve(conn: psycopg2.extensions.connection, r: redis_sync.Redis, raw: str) -> Principal | None:
    h = hash_id(raw)
    # redis-py's sync/async command mixins share one ResponseT stub (Awaitable[Any] | Any); this client is sync.
    cached = cast("bytes | str | None", r.get(f"session:{h}"))
    if cached:
        d = json.loads(cached)
        return Principal(UUID(d["a"]), d["s"], frozenset(d["r"]), datetime.fromisoformat(d["re"]) if d["re"] else None, "session", h)
    p = _load(conn, h)
    if p:
        _cache_set(r, p)
    return p


def touch(conn: psycopg2.extensions.connection, p: Principal) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE session SET last_seen_at = now() WHERE id_hash = %s AND last_seen_at < now() - %s", (p.session_hash, TOUCH_EVERY))


def set_reauth(conn: psycopg2.extensions.connection, r: redis_sync.Redis, p: Principal) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE session SET reauth_at = now() WHERE id_hash = %s", (p.session_hash,))
    r.delete(f"session:{p.session_hash}")


def revoke(conn: psycopg2.extensions.connection, r: redis_sync.Redis, raw: str) -> None:
    h = hash_id(raw)
    with conn.cursor() as cur:
        cur.execute("UPDATE session SET revoked_at = now() WHERE id_hash = %s", (h,))
    r.delete(f"session:{h}")


def invalidate_account(r: redis_sync.Redis, account_id: UUID) -> None:
    key = f"account:{account_id}:sessions"
    for h in cast("set[bytes | str]", r.smembers(key)):
        r.delete(f"session:{h.decode() if isinstance(h, bytes) else h}")
    r.delete(key)


def revoke_all(conn: psycopg2.extensions.connection, r: redis_sync.Redis, account_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE session SET revoked_at = now() WHERE account_id = %s AND revoked_at IS NULL", (account_id,))
    invalidate_account(r, account_id)
