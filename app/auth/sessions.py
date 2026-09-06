"""Server-side sessions with a Redis principal cache that is deleted, never waited out, on any change (spec §3, S4)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, cast
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


def _principal(row: tuple[Any, ...], h: str) -> Principal:
    """(account_id, state, reauth_at, roles) -> Principal. One mapper for both readers of
    those four columns: `_load`'s SELECT and `create`'s INSERT ... RETURNING."""
    return Principal(row[0], row[1], frozenset(row[3]), row[2], "session", h)


def _load(conn: psycopg2.extensions.connection, h: str) -> Principal | None:
    with conn.cursor() as cur:
        cur.execute("""SELECT s.account_id, a.state, s.reauth_at,
                              COALESCE((SELECT array_agg(role) FROM role_grant g WHERE g.account_id = s.account_id AND g.revoked_at IS NULL), '{}')
                         FROM session s JOIN account a ON a.id = s.account_id
                        WHERE s.id_hash = %s AND s.revoked_at IS NULL AND s.expires_at > now()
                          AND s.last_seen_at > now() - %s""", (h, IDLE))
        row = cur.fetchone()
    return _principal(row, h) if row else None


def _account_tombstone(account_id: UUID) -> str:
    return f"account:{account_id}:invalidated"


def _session_tombstone(h: str) -> str:
    return f"session:{h}:revoked"


def _now_us(r: redis_sync.Redis) -> int:
    """The REDIS server clock, in microseconds. One clock owns both sides of the tombstone
    comparison — the same principle M4 applied to Postgres expiries, for the same reason:
    a reader and a revoker on two API containers must order against each other, not
    against their own drifting local clocks."""
    secs, micros = cast("tuple[int, int]", r.time())
    return secs * 1_000_000 + micros


def _tombstoned_since(r: redis_sync.Redis, account_id: UUID, h: str, loaded_at: int) -> bool:
    """True when this session was signed out, or its account invalidated, at or after the
    instant the principal was read from Postgres — i.e. the caller is holding a principal
    that a change has already overtaken. Tombstones live exactly as long as a cache entry
    could have (CACHE_TTL), so nothing older than the cache can be missed."""
    stamps = cast("list[bytes | None]", r.mget(_account_tombstone(account_id), _session_tombstone(h)))
    for stamp in stamps:
        if stamp is not None and int(stamp) >= loaded_at:
            return True
    return False


def _cache_set(r: redis_sync.Redis, p: Principal, loaded_at: int) -> None:
    h = cast(str, p.session_hash)  # only ever called with a Principal freshly loaded/cached for a session, never None
    # A principal read from Postgres BEFORE a sign-out or an invalidation can still arrive
    # here after it — the read already happened, so no ordering can stop it (I4, NEW-1).
    # Timestamped rather than a bare EXISTS so the reverse case stays fast: a session
    # created AFTER a rotation is cached at once instead of reading Postgres for a minute
    # (NEW-3). One EXTRA round trip on the cache-MISS path; a cache hit never reaches here.
    if _tombstoned_since(r, p.account_id, h, loaded_at):
        return
    index = f"account:{p.account_id}:sessions"
    # Index FIRST, principal second (I4): a concurrent invalidate_account reads the index
    # to find what to delete, so a principal that is written before it is indexed can be
    # missed entirely and then survive the full CACHE_TTL — the account is suspended but
    # keeps its state and roles for another minute.
    r.sadd(index, h)
    # The index cannot outlive the sessions it points at: without this it never expired
    # and grew one dead 64-char hash per sign-in, forever (I5).
    r.expire(index, int(ABSOLUTE.total_seconds()))
    r.set(f"session:{h}", json.dumps({"a": str(p.account_id), "s": p.state, "r": sorted(p.roles), "re": p.reauth_at.isoformat() if p.reauth_at else None}), ex=CACHE_TTL)


def create(conn: psycopg2.extensions.connection, r: redis_sync.Redis, account_id: UUID, ip: str | None, ua: str | None) -> str:
    raw, h = tokens.new_secret()
    # Before the INSERT, so a rotation's own revoke_all cannot outrank the session it is
    # rotating TO (NEW-3): that tombstone was stamped earlier than this instant.
    loaded_at = _now_us(r)
    with conn.cursor() as cur:
        # The INSERT returns the principal's own four columns, so there is no second read
        # of a row we just wrote and no impossible "not found" case to branch on or assert
        # away (concern 4, round 2). `AS s` matters: unqualified `account_id` inside the
        # roles subquery would bind to role_grant's OWN account_id and match every row.
        # now() + interval, not the app clock: `expires_at` is read back as
        # `expires_at > now()`, so one clock must own both ends (M4).
        cur.execute("""INSERT INTO session AS s (id_hash, account_id, expires_at, ip, user_agent)
                            VALUES (%s,%s, now() + %s::interval,%s,%s)
                         RETURNING s.account_id,
                                   (SELECT a.state FROM account a WHERE a.id = s.account_id),
                                   s.reauth_at,
                                   COALESCE((SELECT array_agg(g.role) FROM role_grant g WHERE g.account_id = s.account_id AND g.revoked_at IS NULL), '{}')""",
                    (h, account_id, ABSOLUTE, ip, ua))
        # INSERT ... RETURNING on a single-row VALUES always yields exactly one row.
        row = cast("tuple[Any, ...]", cur.fetchone())
    _cache_set(r, _principal(row, h), loaded_at)
    return raw


def resolve(conn: psycopg2.extensions.connection, r: redis_sync.Redis, raw: str) -> Principal | None:
    h = hash_id(raw)
    # redis-py's sync/async command mixins share one ResponseT stub (Awaitable[Any] | Any); this client is sync.
    cached = cast("bytes | str | None", r.get(f"session:{h}"))
    if cached:
        d = json.loads(cached)
        return Principal(UUID(d["a"]), d["s"], frozenset(d["r"]), datetime.fromisoformat(d["re"]) if d["re"] else None, "session", h)
    # The clock is read BEFORE Postgres: any sign-out or invalidation stamped at or after
    # this instant must outrank the principal we are about to read (NEW-1).
    loaded_at = _now_us(r)
    p = _load(conn, h)
    if p:
        _cache_set(r, p, loaded_at)
        return p
    _prune_index(conn, r, h)
    return None


def _prune_index(conn: psycopg2.extensions.connection, r: redis_sync.Redis, h: str) -> None:
    """A session id that no longer resolves — expired, idle, revoked — used to keep its
    64-char hash in the account index for the index's full 30 days, and every later
    sign-in reset that TTL, so a regular signer-in accumulated dead members without limit
    (O1). Only `revoke()` ever pruned. The row still records whose session it was, so the
    dead member can go now, on the one path that has just proved it is dead."""
    with conn.cursor() as cur:
        cur.execute("SELECT account_id FROM session WHERE id_hash = %s", (h,))
        row = cur.fetchone()
    if row:
        r.srem(f"account:{row[0]}:sessions", h)


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
        cur.execute("UPDATE session SET revoked_at = now() WHERE id_hash = %s RETURNING account_id", (h,))
        row = cur.fetchone()
    r.delete(f"session:{h}")
    # Sign-out carries the same race invalidate_account does: a request that read this
    # principal a moment ago may still be on its way to _cache_set (NEW-1).
    r.set(_session_tombstone(h), _now_us(r), ex=CACHE_TTL)
    if row:
        r.srem(f"account:{row[0]}:sessions", h)  # prune the index too, not just the cached principal (I5)


def invalidate_account(r: redis_sync.Redis, account_id: UUID) -> None:
    key = f"account:{account_id}:sessions"
    members = cast("set[bytes | str]", r.smembers(key))
    # Index FIRST, members second (I4): a `_cache_set` racing this then re-creates the
    # index around its own session instead of having its SADD wiped a moment later, so
    # the next invalidation can still find it.
    r.delete(key)
    if members:  # one DELETE for every cached principal, not one round trip each (M10)
        r.delete(*(f"session:{h.decode() if isinstance(h, bytes) else h}" for h in members))
    # Lives exactly as long as a cache entry could have, so an in-flight reader that
    # already loaded a pre-change principal cannot install it behind us (I4). The stamp is
    # what keeps that from also blocking principals read AFTER this point (NEW-3).
    r.set(_account_tombstone(account_id), _now_us(r), ex=CACHE_TTL)


def revoke_all(conn: psycopg2.extensions.connection, r: redis_sync.Redis, account_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE session SET revoked_at = now() WHERE account_id = %s AND revoked_at IS NULL", (account_id,))
    invalidate_account(r, account_id)
