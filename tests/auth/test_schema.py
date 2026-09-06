import psycopg2
import pytest


def cols(conn, table):
    with conn.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position", (table,))
        return [r[0] for r in cur.fetchall()]


def test_account_email_is_citext_unique_any_domain(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('Jane@Gmail.com','h','unverified')")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('jane@gmail.com','h','unverified')")
    assert {"id", "email", "password_hash", "state", "display_name", "affiliation_label", "created_at", "last_sign_in_at"} <= set(cols(conn, "account"))


def test_account_state_is_constrained(conn):
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('a@b.co','h','sleeping')")


def test_one_active_grant_per_role(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('m@x.io','h','active') RETURNING id"); aid = cur.fetchone()[0]
        cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'buyer',%s)", (aid, aid))
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'buyer',%s)", (aid, aid))
        cur.execute("UPDATE role_grant SET revoked_at = now() WHERE account_id=%s", (aid,))
        cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'buyer',%s)", (aid, aid))   # re-grant after revocation is fine


def test_role_and_application_kind_are_constrained(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('r@x.io','h','active') RETURNING id"); aid = cur.fetchone()[0]
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'wizard',%s)", (aid, aid))
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("INSERT INTO application (account_id, kind, fields) VALUES (%s,'landlord','{}')", (aid,))


def test_outbox_idempotency_and_audit_is_append_only(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO email_outbox (to_email, template, params, idempotency_key) VALUES ('a@b.co','verify_email','{}','k1')")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute("INSERT INTO email_outbox (to_email, template, params, idempotency_key) VALUES ('a@b.co','verify_email','{}','k1')")
        cur.execute("INSERT INTO audit_log (action, target_type) VALUES ('probe', 'probe') RETURNING id")
        (aid,) = cur.fetchone()
        # The connecting role is a superuser on compose and on Railway, so ACLs alone cannot enforce
        # append-only; the trigger must refuse both statements for ANY role (Task I1 ruling).
        with pytest.raises(psycopg2.errors.RaiseException):
            cur.execute("UPDATE audit_log SET reason = 'tamper' WHERE id = %s", (aid,))
        with pytest.raises(psycopg2.errors.RaiseException):
            cur.execute("DELETE FROM audit_log WHERE id = %s", (aid,))
        cur.execute("SELECT count(*) FROM audit_log WHERE id = %s", (aid,))
        assert cur.fetchone() == (1,)


def test_session_and_token_tables_store_hashes_only(conn):
    assert "id_hash" in cols(conn, "session") and "id" not in cols(conn, "session")
    assert "token_hash" in cols(conn, "email_token") and "token_hash" in cols(conn, "api_token")
