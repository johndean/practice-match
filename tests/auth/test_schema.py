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
        # append-only; triggers must refuse UPDATE, DELETE and TRUNCATE for ANY role (Task I1 ruling;
        # TRUNCATE added fix round 1, C2 — neither the REVOKEs nor a FOR EACH ROW trigger catch it).
        with pytest.raises(psycopg2.errors.RaiseException):
            cur.execute("UPDATE audit_log SET reason = 'tamper' WHERE id = %s", (aid,))
        with pytest.raises(psycopg2.errors.RaiseException):
            cur.execute("DELETE FROM audit_log WHERE id = %s", (aid,))
        with pytest.raises(psycopg2.errors.RaiseException):
            cur.execute("TRUNCATE audit_log")
        cur.execute("SELECT count(*) FROM audit_log WHERE id = %s", (aid,))
        assert cur.fetchone() == (1,)


def test_session_and_token_tables_store_hashes_only(conn):
    assert "id_hash" in cols(conn, "session") and "id" not in cols(conn, "session")
    assert "token_hash" in cols(conn, "email_token") and "token_hash" in cols(conn, "api_token")


# I6, fix round 1: most of §2's contract had no assertion at all — a later migration or
# a hand-edit could change any index, cascade, citext column, timestamptz column or
# CHECK below with the rest of this suite still green. These are cheap; the foundation
# nine tasks build on this schema.


def test_indexes_exist(conn):
    """§8's /api/admin/users budget and the outbox due-scan rest on two of these."""
    with conn.cursor() as cur:
        cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
        names = {r[0] for r in cur.fetchall()}
    assert {"session_account_idx", "application_queue_idx", "email_outbox_due_idx", "audit_log_target_idx"} <= names


def test_account_delete_cascades_to_child_rows(conn):
    """§2's retention purge: deleting an account must not leave orphaned session/
    token/application/role_grant rows behind."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('cascade@x.io','h','active') RETURNING id")
        (aid,) = cur.fetchone()
        cur.execute("INSERT INTO session (id_hash, account_id, expires_at) VALUES ('sh1', %s, now() + interval '1 day')", (aid,))
        cur.execute(
            "INSERT INTO email_token (account_id, purpose, token_hash, expires_at) VALUES (%s,'verify','th1', now() + interval '1 day')", (aid,)
        )
        cur.execute("INSERT INTO application (account_id, kind, fields) VALUES (%s,'buyer','{}')", (aid,))
        cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'buyer',%s)", (aid, aid))
        cur.execute("DELETE FROM account WHERE id = %s", (aid,))
        for table in ("session", "email_token", "application", "role_grant"):
            cur.execute(f"SELECT count(*) FROM {table} WHERE account_id = %s", (aid,))
            assert cur.fetchone() == (0,), table


def test_outbox_and_suppression_email_are_citext(conn):
    """S7: a bounced address must suppress a later send regardless of case."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO email_outbox (to_email, template, params, idempotency_key) VALUES ('Case@Example.com','verify_email','{}','k-citext')"
        )
        cur.execute("SELECT id FROM email_outbox WHERE to_email = 'case@example.com'")
        assert cur.fetchone() is not None
        cur.execute("INSERT INTO email_suppression (email, reason) VALUES ('Bounced@Example.com','bounce')")
        cur.execute("SELECT email FROM email_suppression WHERE email = 'bounced@example.com'")
        assert cur.fetchone() is not None


def test_every_at_column_is_timestamptz(conn):
    tables = ["account", "session", "email_token", "application", "role_grant", "api_token", "email_outbox", "email_suppression", "audit_log"]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name ~ '(^|_)at$' AND table_name = ANY(%s)",
            (tables,),
        )
        rows = cur.fetchall()
    assert len(rows) == 22, rows  # every *_at/at column across the nine identity tables — a fixed, known count
    for table_name, column_name, data_type in rows:
        assert data_type == "timestamp with time zone", f"{table_name}.{column_name} is {data_type}"


def test_purpose_role_status_checks_are_constrained(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('chk@x.io','h','active') RETURNING id")
        (aid,) = cur.fetchone()
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("INSERT INTO email_token (account_id, purpose, token_hash, expires_at) VALUES (%s,'teleport','th2', now())", (aid,))
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("INSERT INTO api_token (name, role, token_hash, created_by, expires_at) VALUES ('x','wizard','tk1', %s, now())", (aid,))
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                "INSERT INTO email_outbox (to_email, template, params, idempotency_key, status) VALUES ('a@b.co','t','{}','k-status','teleported')"
            )
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("INSERT INTO application (account_id, kind, fields, status) VALUES (%s,'buyer','{}','teleported')", (aid,))
