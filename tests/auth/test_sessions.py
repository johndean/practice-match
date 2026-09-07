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
    S.revoke_all_cache(redis, aid, S.revoke_all(conn, aid))
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
    loaded_at = S._now_us(redis)
    stale = S._load(conn, h)                                        # read BEFORE the change
    assert stale is not None and stale.state == "active"
    with conn.cursor() as cur:
        cur.execute("UPDATE account SET state='suspended' WHERE id=%s", (aid,))
    S.invalidate_account(redis, aid)
    S._cache_set(redis, stale, loaded_at)                           # … the racing writer arrives late
    assert redis.exists(f"session:{h}") == 0                        # refused, nothing stale is cached
    assert redis.exists(f"account:{aid}:invalidated")
    assert 0 < redis.ttl(f"account:{aid}:invalidated") <= S.CACHE_TTL
    p = S.resolve(conn, redis, raw)                                 # the next request re-reads Postgres
    assert p is not None and p.state == "suspended"


def test_a_principal_read_before_a_sign_out_is_never_cached_after_it(conn, redis, monkeypatch):
    """NEW-1, fix round 3: round 2's tombstone covered `invalidate_account` but not
    `revoke()`, so ordinary sign-out kept the whole 60 s stale-principal window. A member
    on a shared computer clicks Sign out while a second tab has a request in flight whose
    principal read landed a moment earlier; that request finishes, re-caches the
    principal, and the revoked session id resolves to an active member with full roles
    for another minute without Postgres ever being consulted.

    The interleaving is injected at the `_load` seam so the whole thing runs through the
    real `resolve`: read the principal, sign out, then let the cache write arrive."""
    aid = _member(conn)
    raw = S.create(conn, redis, aid, None, None)
    h = S.hash_id(raw)
    redis.delete(f"session:{h}")                                    # force the cache-miss path
    real_load, fired = S._load, []

    def _load_then_sign_out(c, hh):
        p = real_load(c, hh)                                        # … principal read from Postgres
        if p is not None and not fired:
            fired.append(True)
            S.revoke_cache(redis, *S.revoke(conn, raw))             # … member signs out
        return p

    monkeypatch.setattr(S, "_load", _load_then_sign_out)
    assert S.resolve(conn, redis, raw) is not None                  # this request finishes with what it read
    assert fired
    assert redis.exists(f"session:{h}") == 0                        # but nothing stale is left behind …
    assert S.resolve(conn, redis, raw) is None                      # … so the next request sees the sign-out


def test_a_session_created_after_a_rotation_is_cached_at_once(conn, redis):
    """NEW-3, fix round 3: round 2's tombstone was a bare EXISTS, so for 60 s after any
    invalidation NOTHING could be cached for that account — including the brand-new
    session issued microseconds later by the rotation itself. Every request from the
    member who just changed their password read Postgres, against I3's 20 ms /api/me
    budget. A timestamped tombstone only outranks principals read BEFORE it."""
    aid = _member(conn)
    S.create(conn, redis, aid, None, None)
    S.revoke_all_cache(redis, aid, S.revoke_all(conn, aid))         # password change rotates every session …
    raw = S.create(conn, redis, aid, None, None)                    # … and issues a new one
    h = S.hash_id(raw)
    assert redis.exists(f"session:{h}")                             # cached at once, not in 60 s
    assert 0 < redis.ttl(f"session:{h}") <= S.CACHE_TTL
    assert redis.sismember(f"account:{aid}:sessions", h)
    assert S.resolve(conn, redis, raw) is not None


def test_the_set_reauth_race_demands_step_up_again_rather_than_granting_it(conn, redis, monkeypatch):
    """The same interleaving against `set_reauth`, recorded because it is the one case
    that needs no tombstone: the racing writer caches a principal that LACKS the re-auth
    stamp, so step-up is demanded a second time. Annoying, never a bypass. A tombstone
    here would only trade that for a Postgres read; the dangerous direction — a stale
    principal CARRYING a stamp it no longer has — cannot happen, because the stamp only
    ever appears after the write it belongs to."""
    aid = _member(conn)
    raw = S.create(conn, redis, aid, None, None)
    h = S.hash_id(raw)
    redis.delete(f"session:{h}")
    real_load, fired = S._load, []

    def _load_then_reauth(c, hh):
        p = real_load(c, hh)                                        # reauth_at is still None here
        if p is not None and not fired:
            fired.append(True)
            S.set_reauth(conn, redis, p)                            # … the member re-authenticates
        return p

    monkeypatch.setattr(S, "_load", _load_then_reauth)
    S.resolve(conn, redis, raw)
    assert fired
    p = S.resolve(conn, redis, raw)
    assert p is not None and p.reauth_at is None                    # step-up will be demanded again
    with conn.cursor() as cur:
        cur.execute("SELECT reauth_at FROM session WHERE id_hash=%s", (h,)); assert cur.fetchone()[0] is not None


def test_resolve_prunes_the_index_when_the_session_no_longer_resolves(conn, redis):
    """O1, fix round 3: the account index only ever shrank on `revoke()`. A session that
    simply expired left its 64-char hash behind for the index's full 30 days, and any
    sign-in reset that TTL — so a regular signer-in accumulated dead members without
    limit. `resolve` knows the hash is dead and the row still says whose it is: prune."""
    aid = _member(conn)
    raw = S.create(conn, redis, aid, None, None)
    h = S.hash_id(raw)
    assert redis.sismember(f"account:{aid}:sessions", h)
    with conn.cursor() as cur:
        cur.execute("UPDATE session SET expires_at = now() - interval '1 day' WHERE id_hash=%s", (h,))
    redis.delete(f"session:{h}")                                    # past the cache, onto Postgres
    assert S.resolve(conn, redis, raw) is None
    assert not redis.sismember(f"account:{aid}:sessions", h)


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
    """Split in two in I5c fix round 2 (re-review O2): `revoke` deleted the cached principal and
    stamped the tombstone INSIDE the caller's transaction, which left the last pre-commit Redis
    mutation of session state in the app — between the stamp and the commit a concurrent `resolve`
    of the same cookie read `revoked_at IS NULL`, outranked the stamp and re-cached a live
    principal, so a signed-out cookie kept working for up to `CACHE_TTL`. `revoke` is Postgres
    only now and names the session (and its account) for `revoke_cache` to clear afterwards."""
    aid = _member(conn)
    raw = S.create(conn, redis, aid, None, None)
    assert S.resolve(conn, redis, raw) is not None
    h = S.hash_id(raw)

    assert S.revoke(conn, raw) == (h, aid)                  # the DB half: the hash and the owner
    with conn.cursor() as cur:
        cur.execute("SELECT revoked_at IS NOT NULL FROM session WHERE id_hash = %s", (h,))
        assert cur.fetchone() == (True,)
    assert redis.exists(f"session:{h}") and redis.exists(f"session:{h}:revoked") == 0  # cache untouched

    S.revoke_cache(redis, h, aid)
    assert S.resolve(conn, redis, raw) is None
    assert 0 < redis.ttl(f"session:{h}:revoked") <= S.CACHE_TTL
    # I5, fix round 1: revoke() deleted session:{h} but left {h} in the account index, so
    # every later invalidate_account paid a round trip for a session that no longer exists.
    assert not redis.sismember(f"account:{aid}:sessions", S.hash_id(raw))


def test_revoking_an_unknown_session_id_is_a_no_op(conn, redis):
    """revoke() reads the owning account back from the UPDATE so it can prune the index (I5); a raw
    id that matches no row names no account, and `revoke_cache` must not try to prune one. The
    tombstone is still stamped: it costs nothing and keeps the pair total (O2)."""
    unknown = "not-a-session-id-anyone-ever-issued"
    h, account_id = S.revoke(conn, unknown)
    assert (h, account_id) == (S.hash_id(unknown), None)
    S.revoke_cache(redis, h, account_id)
    assert redis.exists(f"session:{h}:revoked")


# --- I5c fix round 1, concern 2: the two halves of `revoke_all`, and what each one owns ---


def test_revoke_all_writes_postgres_only_and_names_the_sessions_it_ended(conn, redis):
    """The DB half. It returns the id hashes it revoked — the set `revoke_all_cache` clears once
    the caller's transaction has committed — and it touches Redis not at all, which is what makes
    the ordering the caller's to get right rather than this function's to get wrong."""
    aid = _member(conn)
    first, second = S.create(conn, redis, aid, None, None), S.create(conn, redis, aid, None, None)
    hashes = {S.hash_id(first), S.hash_id(second)}

    revoked = S.revoke_all(conn, aid)
    assert revoked == hashes
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM session WHERE account_id=%s AND revoked_at IS NULL", (aid,))
        assert cur.fetchone()[0] == 0
    # Redis is untouched: both principals are still cached, and no tombstone has been stamped.
    assert all(redis.exists(f"session:{h}") for h in hashes)
    assert redis.exists(f"account:{aid}:invalidated") == 0

    # ...and a second call has nothing left to revoke, which is the empty-set path.
    assert S.revoke_all(conn, aid) == frozenset()


def test_revoke_all_cache_without_keep_sweeps_even_a_session_created_afterwards(conn, redis):
    """The Redis half, and the reason `keep` is not optional in practice. The sweep is by ACCOUNT
    (re-review O1), so with no `keep` it takes the replacement a rotation issued a microsecond
    earlier along with everything else — which is exactly why `app.api.auth.change` passes its new
    session's hash. The account tombstone is stamped either way: it is what stops a principal read
    before the commit from being installed after it."""
    aid = _member(conn)
    doomed = S.create(conn, redis, aid, None, None)
    h = S.hash_id(doomed)
    revoked = S.revoke_all(conn, aid)
    replacement = S.create(conn, redis, aid, None, None)
    sh = S.hash_id(replacement)

    S.revoke_all_cache(redis, aid, revoked)                    # no `keep`

    assert redis.exists(f"session:{h}") == 0                   # the revoked principal is gone …
    assert redis.exists(f"session:{h}:revoked")                # … and tombstoned, like a sign-out
    assert 0 < redis.ttl(f"session:{h}:revoked") <= S.CACHE_TTL
    assert redis.sismember(f"account:{aid}:sessions", h) == 0
    assert redis.exists(f"session:{sh}") == 0                  # and so is the replacement, uncached
    assert S.resolve(conn, redis, doomed) is None
    # It still WORKS — the row is live, so the next request re-reads Postgres and re-caches it.
    assert S.resolve(conn, redis, replacement) is not None
    assert 0 < redis.ttl(f"account:{aid}:invalidated") <= S.CACHE_TTL


def test_revoke_all_cache_with_nothing_revoked_still_stamps_the_account_tombstone(conn, redis):
    """An account with no live session — a reset for somebody who was never signed in. There is no
    principal to drop, but the tombstone still has to be stamped: a request that read this
    account's principal before the commit must not be able to install it afterwards."""
    aid = _member(conn)
    assert S.revoke_all(conn, aid) == frozenset()
    S.revoke_all_cache(redis, aid, frozenset())
    assert 0 < redis.ttl(f"account:{aid}:invalidated") <= S.CACHE_TTL


# --- I5c fix round 2 (re-review observations O1, O2, O5) ---


def test_revoke_all_cache_leaves_no_cached_principal_behind_at_all(conn, redis):
    """O1, zero residue. `revoke_all` only matches rows with `revoked_at IS NULL`, so a session
    that was ALREADY signed out — or whose row the nightly purge has since deleted — is not in the
    set it returns, and clearing only that set left its cached principal alive for the rest of its
    60 s TTL. `deps.current_principal` returns a cache hit BEFORE any expiry or state check, so
    that cookie went on working, with its cached state and roles, through a suspension.

    `revoke_all_cache` sweeps the account index (minus `keep`) as well as the hashes it is given,
    so nothing of the account's survives the call."""
    aid = _member(conn)
    signed_out, purged, live = (S.create(conn, redis, aid, None, None) for _ in range(3))
    for raw in (signed_out, purged, live):
        assert redis.exists(f"session:{S.hash_id(raw)}")

    with conn.cursor() as cur:
        cur.execute("UPDATE session SET revoked_at = now() WHERE id_hash = %s", (S.hash_id(signed_out),))
        cur.execute("DELETE FROM session WHERE id_hash = %s", (S.hash_id(purged),))

    revoked = S.revoke_all(conn, aid)
    assert revoked == frozenset({S.hash_id(live)})  # the other two are not `revoked_at IS NULL` rows
    S.revoke_all_cache(redis, aid, revoked)

    for raw in (signed_out, purged, live):
        assert redis.exists(f"session:{S.hash_id(raw)}") == 0, raw
        assert redis.exists(f"session:{S.hash_id(raw)}:revoked"), raw
        assert redis.sismember(f"account:{aid}:sessions", S.hash_id(raw)) == 0, raw
    assert redis.exists(f"account:{aid}:sessions") == 0


def test_revoke_all_cache_keeps_the_session_the_caller_just_created(conn, redis):
    """O1's other half. The sweep must not take the rotation's replacement with it: `keep` is the
    hashes the caller created inside the same transaction. NEW-3's guarantee — cached AND indexed
    at once, not in 60 s — has to survive a whole-index sweep."""
    aid = _member(conn)
    doomed = S.create(conn, redis, aid, None, None)
    revoked = S.revoke_all(conn, aid)
    survivor = S.create(conn, redis, aid, None, None)
    kept = S.hash_id(survivor)

    S.revoke_all_cache(redis, aid, revoked, keep={kept})

    assert redis.exists(f"session:{S.hash_id(doomed)}") == 0
    assert redis.exists(f"session:{kept}")
    assert redis.sismember(f"account:{aid}:sessions", kept)
    assert redis.exists(f"session:{kept}:revoked") == 0     # never tombstoned
    assert S.resolve(conn, redis, survivor) is not None and S.resolve(conn, redis, doomed) is None


def test_revoke_all_cache_costs_the_same_whatever_the_session_count(conn, redis):
    """O5, the counterpart to `test_invalidate_account_is_one_round_trip_per_call`: the tombstone
    `SET`s were issued one per session, so an account with N devices paid N round trips. Every
    mutation travels in ONE pipeline now, so the cost is constant — the index read, the clock, and
    a single batch — rather than growing with the number of sessions."""
    aid = _member(conn)
    raws = [S.create(conn, redis, aid, None, None) for _ in range(4)]
    revoked = S.revoke_all(conn, aid)

    direct: list[str] = []
    pipelines: list[object] = []
    real = {name: getattr(redis, name) for name in ("set", "delete", "srem", "pipeline")}

    def _spy(name):
        def _call(*a: object, **kw: object) -> object:
            (pipelines if name == "pipeline" else direct).append(name)
            return real[name](*a, **kw)
        return _call

    for name in real:
        setattr(redis, name, _spy(name))
    try:
        S.revoke_all_cache(redis, aid, revoked)
        assert direct == [], f"every mutation belongs in the pipeline, not direct: {direct}"
        assert len(pipelines) == 1
    finally:
        for name in real:
            delattr(redis, name)

    for raw in raws:
        assert redis.exists(f"session:{S.hash_id(raw)}") == 0
        assert 0 < redis.ttl(f"session:{S.hash_id(raw)}:revoked") <= S.CACHE_TTL
    assert 0 < redis.ttl(f"account:{aid}:invalidated") <= S.CACHE_TTL




def test_revoke_cache_is_one_batch_so_the_delete_and_the_stamp_cannot_separate(conn, redis):
    """P1 (re-review 2). `revoke_cache` was the one cache half that was neither batched nor
    atomic: `DELETE`, then `TIME`, then the tombstone `SET`, then `SREM` — three mutating round
    trips, and the delete and the stamp were separable. A racing `_cache_set` that had already
    passed its own tombstone check could land its `SET` in the gap between them and leave a stale
    principal for up to `CACHE_TTL`. The general form of that race is inherent (an in-flight reader
    whose Postgres read precedes the change, accepted in I4/NEW-1); the GAP is not.

    Same shape as `revoke_all_cache`'s counterpart: nothing mutating reaches the client directly,
    and there is exactly one batch."""
    aid = _member(conn)
    raw = S.create(conn, redis, aid, None, None)
    h, account_id = S.revoke(conn, raw)

    direct: list[str] = []
    pipelines: list[object] = []
    real = {name: getattr(redis, name) for name in ("set", "delete", "srem", "pipeline")}

    def _spy(name):
        def _call(*a: object, **kw: object) -> object:
            (pipelines if name == "pipeline" else direct).append(name)
            return real[name](*a, **kw)
        return _call

    for name in real:
        setattr(redis, name, _spy(name))
    try:
        S.revoke_cache(redis, h, account_id)
        assert direct == [], f"every mutation belongs in the one MULTI, not direct: {direct}"
        assert len(pipelines) == 1
    finally:
        for name in real:
            delattr(redis, name)

    assert redis.exists(f"session:{h}") == 0
    assert 0 < redis.ttl(f"session:{h}:revoked") <= S.CACHE_TTL
    assert redis.sismember(f"account:{aid}:sessions", h) == 0
    assert S.resolve(conn, redis, raw) is None


def test_revoke_cache_of_an_unknown_session_is_still_one_batch(conn, redis):
    """The no-account arm of the same batch: nothing to prune from an index, so the `MULTI` carries
    the delete and the stamp only — still one round trip, still atomic."""
    unknown = "not-a-session-id-anyone-ever-issued"
    h, account_id = S.revoke(conn, unknown)
    assert account_id is None

    pipelines: list[object] = []
    real_pipeline = redis.pipeline

    def _spy(*a: object, **kw: object) -> object:
        pipelines.append("pipeline")
        return real_pipeline(*a, **kw)

    redis.pipeline = _spy
    try:
        S.revoke_cache(redis, h, account_id)
        assert len(pipelines) == 1
    finally:
        del redis.pipeline
    assert 0 < redis.ttl(f"session:{h}:revoked") <= S.CACHE_TTL
