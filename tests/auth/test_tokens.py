from datetime import timedelta

from app.auth import tokens as T


def _account(conn, email="t@x.io", state="verified"):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,'h',%s) RETURNING id", (email, state)); return cur.fetchone()[0]


def test_email_token_is_single_use_purpose_bound_and_expiring(conn):
    aid = _account(conn)
    raw = T.issue_email_token(conn, aid, "verify", timedelta(hours=24))
    with conn.cursor() as cur:
        cur.execute("SELECT token_hash FROM email_token"); assert cur.fetchone()[0] == T.hash(raw) and raw not in T.hash(raw)
    assert T.consume_email_token(conn, raw, "reset") is None          # wrong purpose
    assert T.consume_email_token(conn, raw, "verify") == aid
    assert T.consume_email_token(conn, raw, "verify") is None         # used
    old = T.issue_email_token(conn, aid, "reset", timedelta(hours=-1))
    assert T.consume_email_token(conn, old, "reset") is None          # expired


def test_api_token_round_trip_role_expiry_and_revocation(conn):
    admin = _account(conn, "a@x.io", "active")
    raw = T.issue_api_token(conn, name="k6-qa", role="buyer", created_by=admin, ttl=timedelta(days=90))
    assert raw.startswith("pm_")
    p = T.verify_api_token(conn, raw)
    assert p is not None and p.role == "buyer" and p.name == "k6-qa"
    assert T.verify_api_token(conn, raw[:-1] + ("a" if raw[-1] != "a" else "b")) is None
    with conn.cursor() as cur:
        cur.execute("UPDATE api_token SET revoked_at = now()")
    assert T.verify_api_token(conn, raw) is None


# Coverage-only, per John's 100 %-coverage ruling (2026-09-06) — not in the brief's Step 1.
def test_verify_api_token_rejects_a_malformed_raw_token(conn):
    assert T.verify_api_token(conn, "not-a-token-at-all") is None
