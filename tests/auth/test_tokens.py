from datetime import datetime, timedelta
from uuid import UUID

from app.auth import tokens as T


def _account(conn, email="t@x.io", state="verified"):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,'h',%s) RETURNING id", (email, state)); return cur.fetchone()[0]


def test_email_token_is_single_use_purpose_bound_and_expiring(conn):
    aid = _account(conn)
    raw = T.issue_email_token(conn, aid, "verify", timedelta(hours=24))
    with conn.cursor() as cur:
        cur.execute("SELECT token_hash FROM email_token"); assert cur.fetchone()[0] == T.hash(raw)
        # M9, fix round 1: `raw not in T.hash(raw)` is a substring test against a 64-char
        # hex digest — true for essentially any input. What matters is that the RAW token
        # is nowhere in the table: only its digest is at rest.
        cur.execute("SELECT count(*) FROM email_token WHERE token_hash = %s", (raw,)); assert cur.fetchone()[0] == 0
    assert T.consume_email_token(conn, raw, "reset") is None          # wrong purpose
    consumed = T.consume_email_token(conn, raw, "verify")
    # I9, fix round 1: the signature says `-> uuid | None`, and psycopg2 only honours that
    # once app.db's register_uuid() has run in this process. It is registered at the seam
    # that needs it (tests/conftest.py imports app.db at module level), not by a
    # side-effect import inside app/auth/tokens.py — so this holds as the FIRST test of a
    # fresh process, with no other module having pulled app.db in first.
    assert consumed == aid and isinstance(consumed, UUID)
    assert T.consume_email_token(conn, raw, "verify") is None         # used
    old = T.issue_email_token(conn, aid, "reset", timedelta(hours=-1))
    assert T.consume_email_token(conn, old, "reset") is None          # expired


def test_api_token_round_trip_role_expiry_and_revocation(conn):
    admin = _account(conn, "a@x.io", "active")
    raw = T.issue_api_token(conn, name="k6-qa", role="buyer", created_by=admin, ttl=timedelta(days=90))
    assert raw.startswith("pm_")
    secret = raw.split(".", 1)[1]
    with conn.cursor() as cur:
        # M9, fix round 1: neither the presented token nor its secret half is stored.
        cur.execute("SELECT count(*) FROM api_token WHERE token_hash IN (%s, %s)", (raw, secret)); assert cur.fetchone()[0] == 0
        cur.execute("SELECT last_used_at FROM api_token"); assert cur.fetchone()[0] is None
    p = T.verify_api_token(conn, raw)
    assert p is not None and p.role == "buyer" and p.name == "k6-qa"
    with conn.cursor() as cur:
        # M8, fix round 1: a successful verify stamps last_used_at — unasserted, a
        # verify_api_token that never wrote it passed the whole suite.
        cur.execute("SELECT last_used_at FROM api_token"); assert cur.fetchone()[0] is not None
    assert T.verify_api_token(conn, raw[:-1] + ("a" if raw[-1] != "a" else "b")) is None
    with conn.cursor() as cur:
        cur.execute("UPDATE api_token SET revoked_at = now()")
    assert T.verify_api_token(conn, raw) is None


class _SkewedClock(datetime):
    """The app container's clock, 90 s ahead of Postgres."""

    @classmethod
    def now(cls, tz=None):
        return datetime.now(tz) + timedelta(seconds=90)


def test_expiries_follow_the_database_clock_not_the_app_clock(conn, monkeypatch):
    """M4, fix round 1: expiries were written as `datetime.now(UTC) + ttl` from the app
    clock but read back as `expires_at > now()` against the DB clock. 90 s of drift made
    every 24 h verification link 24 h + 90 s. One clock must own both ends, so the ttl is
    now an interval added by Postgres — skewing the app clock must change nothing.
    `raising=False`: after the fix these modules no longer consult `datetime` for an
    expiry at all, which is exactly the point."""
    aid = _account(conn)
    monkeypatch.setattr(T, "datetime", _SkewedClock, raising=False)
    T.issue_email_token(conn, aid, "verify", timedelta(hours=24))
    T.issue_api_token(conn, name="k6", role="buyer", created_by=aid, ttl=timedelta(days=90))
    with conn.cursor() as cur:
        cur.execute("SELECT expires_at - now() FROM email_token"); email_ttl = cur.fetchone()[0]
        cur.execute("SELECT expires_at - now() FROM api_token"); api_ttl = cur.fetchone()[0]
    assert abs(email_ttl - timedelta(hours=24)) < timedelta(seconds=5)
    assert abs(api_ttl - timedelta(days=90)) < timedelta(seconds=5)


# Coverage-only, per John's 100 %-coverage ruling (2026-09-06) — not in the brief's Step 1.
def test_verify_api_token_rejects_a_malformed_raw_token(conn):
    assert T.verify_api_token(conn, "not-a-token-at-all") is None
