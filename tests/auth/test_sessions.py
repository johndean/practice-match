import uuid
from datetime import UTC, datetime, timedelta

from app.auth import sessions as S


def _member(conn, roles=("buyer",), state="active"):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('m@x.io','h',%s) RETURNING id", (state,)); aid = cur.fetchone()[0]
        for r in roles:
            cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,%s,%s)", (aid, r, aid))
    return aid


def test_uuid_columns_come_back_as_uuid_objects(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('u@x.io','h','active')")
        cur.execute("SELECT id FROM account WHERE email='u@x.io'")
        row = cur.fetchone()
    assert isinstance(row[0], uuid.UUID)


def test_create_resolve_and_cache(conn, redis):
    aid = _member(conn)
    raw = S.create(conn, redis, aid, "203.0.113.5", "UA")
    p = S.resolve(conn, redis, raw)
    assert p and p.account_id == aid and p.state == "active" and p.roles == frozenset({"buyer"}) and p.kind == "session"
    assert redis.exists(f"session:{S.hash_id(raw)}") and redis.sismember(f"account:{aid}:sessions", S.hash_id(raw))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM session")                          # cached principal still resolves within the TTL …
    assert S.resolve(conn, redis, raw) is not None
    S.invalidate_account(redis, aid)                                # … until the account is invalidated
    assert S.resolve(conn, redis, raw) is None


def test_revocation_is_effective_on_the_next_request(conn, redis):
    aid = _member(conn)
    raw = S.create(conn, redis, aid, None, None)
    assert S.resolve(conn, redis, raw)
    S.revoke_all(conn, redis, aid)
    assert S.resolve(conn, redis, raw) is None
    raw2 = S.create(conn, redis, aid, None, None)
    with conn.cursor() as cur:
        cur.execute("UPDATE account SET state='suspended' WHERE id=%s", (aid,))
    S.invalidate_account(redis, aid)
    p = S.resolve(conn, redis, raw2)
    assert p is not None and p.state == "suspended"                # resolves, but no permission check will pass


def test_expiry_touch_and_reauth(conn, redis):
    aid = _member(conn)
    raw = S.create(conn, redis, aid, None, None)
    h = S.hash_id(raw)
    with conn.cursor() as cur:
        cur.execute("UPDATE session SET last_seen_at = now() - interval '15 days' WHERE id_hash=%s", (h,))
    redis.delete(f"session:{h}")
    assert S.resolve(conn, redis, raw) is None                      # idle expiry
    raw = S.create(conn, redis, aid, None, None); h = S.hash_id(raw)
    p = S.resolve(conn, redis, raw)
    S.touch(conn, p); S.touch(conn, p)
    with conn.cursor() as cur:
        cur.execute("SELECT last_seen_at, reauth_at FROM session WHERE id_hash=%s", (h,)); seen, reauth = cur.fetchone()
    assert reauth is None and datetime.now(UTC) - seen < timedelta(seconds=5)
    S.set_reauth(conn, redis, p)
    assert S.resolve(conn, redis, raw).reauth_at is not None


# Coverage-only, per John's 100 %-coverage ruling (2026-09-06) — not in the brief's Step 1.
def test_revoke_a_single_session(conn, redis):
    aid = _member(conn)
    raw = S.create(conn, redis, aid, None, None)
    assert S.resolve(conn, redis, raw) is not None
    S.revoke(conn, redis, raw)
    assert S.resolve(conn, redis, raw) is None
