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
    # M7, fix round 1: the cache TTL was never asserted, so CACHE_TTL = 999999 passed the
    # whole suite — which would turn "revocation effective on the next request" into
    # "effective in eleven days".
    assert S.CACHE_TTL == 60
    assert 0 < redis.ttl(f"session:{S.hash_id(raw)}") <= S.CACHE_TTL
    # I5, fix round 1: the per-account index had no TTL and was pruned only by deleting
    # the whole key, so a daily signer-in accumulated thousands of dead 64-char hashes in
    # Redis forever. It must not outlive the absolute session lifetime.
    assert 0 < redis.ttl(f"account:{aid}:sessions") <= S.ABSOLUTE.total_seconds()
    with conn.cursor() as cur:
        # M9, fix round 1: only the digest of the session id is ever at rest.
        cur.execute("SELECT count(*) FROM session WHERE id_hash = %s", (raw,)); assert cur.fetchone()[0] == 0
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


def test_invalidation_racing_a_cache_write_leaves_no_stale_principal(conn, redis):
    """I4, fix round 1: `_cache_set` wrote `session:{h}` and only THEN added {h} to the
    account index, while `invalidate_account` read the index before deleting the member
    keys. An invalidation arriving in that gap saw an empty index, deleted nothing, and
    the just-written principal survived the full 60 s cache TTL — staff suspend an
    abusive account and it keeps `state='active'` and its roles for another minute,
    which is exactly the window S4 exists to close.

    The interleaving is forced here: the moment `_cache_set` performs its `SET`, the
    account is invalidated. With the ordering fixed (SADD then SET, and the index
    deleted before its members) that invalidation cannot miss the session."""
    aid = _member(conn)
    real_set = redis.set
    fired = []

    def _set_then_invalidate(*args: object, **kwargs: object) -> object:
        out = real_set(*args, **kwargs)
        if not fired:
            fired.append(True)
            S.invalidate_account(redis, aid)
        return out

    redis.set = _set_then_invalidate
    try:
        raw = S.create(conn, redis, aid, None, None)
    finally:
        del redis.set
    assert fired, "the interleaving never happened — the test proves nothing"
    h = S.hash_id(raw)
    assert redis.exists(f"session:{h}") == 0               # no principal survived …
    assert redis.ttl(f"session:{h}") < 0                   # … and none is sitting on a TTL


class _RecordingCursor:
    def __init__(self, cur, log):
        self._cur, self._log = cur, log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self._cur.__exit__(*exc)

    def execute(self, sql, params=None):
        self._log.append(sql)
        return self._cur.execute(sql, params)

    def fetchone(self):
        return self._cur.fetchone()


class _RecordingConn:
    """Records every statement the code under test executes through this connection."""

    def __init__(self, real):
        self._real, self.statements = real, []

    def cursor(self):
        return _RecordingCursor(self._real.cursor(), self.statements)


def test_create_builds_its_principal_from_the_insert_itself(conn, redis):
    """Concern 4, fix round 2: `create()` inserted the row and then SELECTed it straight
    back, which needed an `if p:`/`assert` for a case that cannot happen — an unreachable
    branch propped up by a runtime assertion that `python -O` would strip. The INSERT now
    RETURNS the columns the principal is built from, through the same row mapper `_load`
    uses, so there is no Optional, no assert, and no second round trip to the database."""
    aid = _member(conn)
    with conn.cursor() as cur:                                      # a second member, with a role of its own
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('other@x.io','h','active') RETURNING id")
        other = cur.fetchone()[0]
        cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'staff',%s)", (other, other))
    rec = _RecordingConn(conn)
    raw = S.create(rec, redis, aid, "203.0.113.5", "UA")
    assert len(rec.statements) == 1, f"create() must issue exactly one statement, got {rec.statements}"
    assert rec.statements[0].lstrip().upper().startswith("INSERT")
    assert "RETURNING" in rec.statements[0].upper()
    # …and what it cached is exactly what a fresh read of the same session yields.
    cached = S.resolve(conn, redis, raw)
    redis.delete(f"session:{S.hash_id(raw)}")
    assert cached == S.resolve(conn, redis, raw)
    assert cached is not None and cached.account_id == aid and cached.state == "active"
    assert cached.roles == frozenset({"buyer"}) and cached.reauth_at is None and cached.kind == "session"


def test_a_principal_read_before_an_invalidation_is_never_cached_after_it(conn, redis):
    """I4, fix round 2 — closing the window rather than narrowing it. Round 1 fixed the
    orderings, but a request that had ALREADY read its principal from Postgres before
    staff suspended the account could still reach `_cache_set` afterwards and install
    that pre-change principal for the full 60 s. No ordering can prevent that: the read
    is already done. `invalidate_account` therefore leaves a tombstone that lives exactly
    as long as a cache entry could have, and `_cache_set` declines while it is there —
    those requests re-read Postgres instead."""
    aid = _member(conn)
    raw = S.create(conn, redis, aid, None, None)
    h = S.hash_id(raw)
    stale = S._load(conn, h)                                        # read BEFORE the change
    assert stale is not None and stale.state == "active"
    with conn.cursor() as cur:
        cur.execute("UPDATE account SET state='suspended' WHERE id=%s", (aid,))
    S.invalidate_account(redis, aid)
    S._cache_set(redis, stale)                                      # … the racing writer arrives late
    assert redis.exists(f"session:{h}") == 0                        # refused, nothing stale is cached
    assert redis.exists(f"account:{aid}:invalidated")
    assert 0 < redis.ttl(f"account:{aid}:invalidated") <= S.CACHE_TTL
    p = S.resolve(conn, redis, raw)                                 # the next request re-reads Postgres
    assert p is not None and p.state == "suspended"


def test_invalidate_account_is_one_round_trip_per_call(conn, redis):
    """M10, fix round 1: invalidate_account issued one DELETE per indexed session. Every
    sign-out-everywhere, suspension and role change on a busy account paid N round trips
    where one `DELETE k1 k2 …` does. The empty case (an account with nothing cached) must
    not call DELETE with no keys at all."""
    aid = _member(conn)
    raws = [S.create(conn, redis, aid, None, None) for _ in range(3)]
    deletes: list[tuple[object, ...]] = []
    real_delete = redis.delete

    def _counting_delete(*keys: object) -> object:
        deletes.append(keys)
        return real_delete(*keys)

    redis.delete = _counting_delete
    try:
        S.invalidate_account(redis, aid)
        assert len(deletes) == 2                           # the index, then all three members in ONE call
        assert deletes[0] == (f"account:{aid}:sessions",)
        assert set(deletes[1]) == {f"session:{S.hash_id(r)}" for r in raws}
        for raw in raws:
            assert redis.exists(f"session:{S.hash_id(raw)}") == 0

        deletes.clear()
        empty = uuid.uuid4()                               # an account with nothing cached
        S.invalidate_account(redis, empty)
        assert deletes == [(f"account:{empty}:sessions",)]  # never DELETE with an empty key list
    finally:
        del redis.delete


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
    # I6, fix round 1: the brief's version touched a session created milliseconds earlier,
    # so `last_seen_at` already equalled now(), both touches matched zero rows and the
    # assertion below was satisfied by the column default — `touch = lambda *a: None`
    # passed the whole suite. Back-date it far enough that a real write must move it, and
    # then prove the ≤ TOUCH_EVERY throttle in the other direction too.
    with conn.cursor() as cur:
        cur.execute("UPDATE session SET last_seen_at = now() - interval '10 minutes' WHERE id_hash=%s", (h,))
        cur.execute("SELECT last_seen_at FROM session WHERE id_hash=%s", (h,)); backdated = cur.fetchone()[0]
    S.touch(conn, p)
    with conn.cursor() as cur:
        cur.execute("SELECT last_seen_at FROM session WHERE id_hash=%s", (h,)); moved = cur.fetchone()[0]
    assert moved > backdated                                        # the write happened …
    S.touch(conn, p)
    with conn.cursor() as cur:
        cur.execute("SELECT last_seen_at, reauth_at FROM session WHERE id_hash=%s", (h,)); seen, reauth = cur.fetchone()
    assert seen == moved                                            # … and the second touch is throttled
    assert reauth is None and datetime.now(UTC) - seen < timedelta(seconds=5)
    S.set_reauth(conn, redis, p)
    assert S.resolve(conn, redis, raw).reauth_at is not None


class _SkewedClock(datetime):
    """The app container's clock, 90 s ahead of Postgres."""

    @classmethod
    def now(cls, tz=None):
        return datetime.now(tz) + timedelta(seconds=90)


def test_session_expiry_follows_the_database_clock_not_the_app_clock(conn, redis, monkeypatch):
    """M4, fix round 1: `expires_at` was written from the app clock and read back against
    the DB clock (`expires_at > now()`), so container drift silently lengthened the
    absolute session lifetime. `raising=False`: after the fix this module no longer
    consults `datetime` for an expiry at all, which is the point."""
    aid = _member(conn)
    monkeypatch.setattr(S, "datetime", _SkewedClock, raising=False)
    raw = S.create(conn, redis, aid, None, None)
    with conn.cursor() as cur:
        cur.execute("SELECT expires_at - now() FROM session WHERE id_hash=%s", (S.hash_id(raw),)); ttl = cur.fetchone()[0]
    assert abs(ttl - S.ABSOLUTE) < timedelta(seconds=5)


# Coverage-only, per John's 100 %-coverage ruling (2026-09-06) — not in the brief's Step 1.
def test_revoke_a_single_session(conn, redis):
    aid = _member(conn)
    raw = S.create(conn, redis, aid, None, None)
    assert S.resolve(conn, redis, raw) is not None
    S.revoke(conn, redis, raw)
    assert S.resolve(conn, redis, raw) is None
    # I5, fix round 1: revoke() deleted session:{h} but left {h} in the account index, so
    # every later invalidate_account paid a round trip for a session that no longer exists.
    assert not redis.sismember(f"account:{aid}:sessions", S.hash_id(raw))


def test_revoking_an_unknown_session_id_is_a_no_op(conn, redis):
    """revoke() now reads the owning account back from the UPDATE so it can prune the
    index (I5); a raw id that matches no row must simply do nothing."""
    S.revoke(conn, redis, "not-a-session-id-anyone-ever-issued")
