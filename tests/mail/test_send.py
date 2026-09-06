import json
from datetime import timedelta

import httpx
import pytest

from app.config import settings
from app.mail import outbox as OB
from app.mail import resend_client as RC
from app.mail import tasks as MT


def _queue(conn, to="a@example.org", key="k1"):
    OB.enqueue(conn, to=to, template="verify_email", params={"link": "https://qa.foundation.vin/verify?token=t"}, idempotency_key=key)


def test_send_due_posts_once_with_idempotency_and_marks_sent(conn, monkeypatch):
    calls = []
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req); return httpx.Response(200, json={"id": "re_123"})
    monkeypatch.setattr(settings, "resend_api_key", "re_test"); monkeypatch.setattr(settings, "email_allowlist", "a@example.org"); monkeypatch.setattr(settings, "environment", "qa")
    monkeypatch.setattr(MT, "_http", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    _queue(conn)
    assert MT.send_due() == {"sent": 1, "suppressed": 0, "failed": 0, "retried": 0}
    assert MT.send_due() == {"sent": 0, "suppressed": 0, "failed": 0, "retried": 0}
    assert len(calls) == 1 and calls[0].headers["Idempotency-Key"] == "k1" and calls[0].headers["Authorization"] == "Bearer re_test"
    body = json.loads(calls[0].content)
    assert body["from"] == "VIN Foundation — Practice Match <no-reply@foundation.vin>" and body["to"] == ["a@example.org"] and body["reply_to"] == settings.mail_reply_to
    with conn.cursor() as cur:
        cur.execute("SELECT status, provider_id, attempts FROM email_outbox"); assert cur.fetchone() == ("sent", "re_123", 1)


def test_qa_allowlist_suppresses_everyone_else(conn, monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "re_test"); monkeypatch.setattr(settings, "email_allowlist", "john@example.org"); monkeypatch.setattr(settings, "environment", "qa")
    monkeypatch.setattr(MT, "_http", lambda: httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(500))))
    _queue(conn, to="stranger@example.org")
    assert MT.send_due() == {"sent": 0, "suppressed": 1, "failed": 0, "retried": 0}
    monkeypatch.setattr(settings, "email_allowlist", "")            # an EMPTY list outside production sends to nobody (R5)
    _queue(conn, to="john@example.org", key="k-empty")
    assert MT.send_due() == {"sent": 0, "suppressed": 1, "failed": 0, "retried": 0}


def test_failure_backs_off_then_fails_and_suppressed_addresses_are_refused(conn, monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "re_test"); monkeypatch.setattr(settings, "email_allowlist", ""); monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(MT, "_http", lambda: httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(500, json={"message": "boom"}))))
    _queue(conn)
    # Spec §5: "retries at 1 min, 10 min, 1 h, 6 h, then failed" — so FIVE failures, the first four
    # of them re-queued with BACKOFF[attempt-1] and only the fifth terminal (controller ruling,
    # 2026-09-07: the spec governs where the brief's own code and test disagreed).
    for attempt in range(1, len(MT.BACKOFF) + 2):
        with conn.cursor() as cur:
            cur.execute("UPDATE email_outbox SET next_attempt_at = now()")
        MT.send_due()
        with conn.cursor() as cur:
            cur.execute("SELECT status, attempts, EXTRACT(EPOCH FROM next_attempt_at - now()) FROM email_outbox"); status, n, secs = cur.fetchone()
        assert n == attempt, (attempt, n)
        if attempt <= len(MT.BACKOFF):
            assert status == "queued" and abs(float(secs) - MT.BACKOFF[attempt - 1]) < 5, (attempt, status, secs)
        else:
            assert status == "failed", (attempt, status)
    assert MT.send_due() == {"sent": 0, "suppressed": 0, "failed": 0, "retried": 0}   # a `failed` row is never picked up again
    with conn.cursor() as cur:
        cur.execute("INSERT INTO email_suppression (email, reason) VALUES ('bounced@example.org','bounce')")
    _queue(conn, to="bounced@example.org", key="k2")
    assert MT.send_due() == {"sent": 0, "suppressed": 1, "failed": 0, "retried": 0}
    # F7: Admin (I7) must be able to tell a hard-bounce refusal from a QA allowlist refusal.
    with conn.cursor() as cur:
        cur.execute("SELECT last_error FROM email_outbox WHERE to_email='bounced@example.org'")
        assert cur.fetchone() == (MT.REASON_SUPPRESSED,)
    assert MT.REASON_SUPPRESSED != MT.REASON_NOT_ALLOWLISTED


def test_missing_api_key_is_a_hard_failure_not_a_silent_queue(conn, monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", None)
    _queue(conn)
    with pytest.raises(RuntimeError, match="RESEND_API_KEY"):
        MT.send_due()


# --- supplemental (not in the brief's Step 1 — the retention rulings, the lease, and branches) ---


def test_the_real_http_client_is_built_with_bounded_timeouts():
    """`_http` is monkeypatched away in every test above, so without this the ONE line that decides
    how long a black-holed provider can pin a worker slot would never run."""
    with MT._http() as http:
        assert isinstance(http, httpx.Client)
        assert http.timeout.connect == 5.0 and http.timeout.read == 20.0


def test_resend_client_opens_its_own_connection_when_it_is_not_given_one():
    client = RC.ResendClient("re_key")
    try:
        assert isinstance(client.http, httpx.Client) and client.http.timeout.connect == 5.0
    finally:
        client.http.close()


def test_resend_error_carries_the_status_and_a_truncated_body():
    exc = RC.ResendError(422, "x" * 900)
    assert exc.status == 422 and str(exc).startswith("resend 422: ") and len(str(exc)) < 250


def test_a_sent_row_keeps_no_link_and_is_purged_once_the_token_would_have_expired(conn, monkeypatch):
    """The I4 review ruling (fix round 1, Minor 4): `email_outbox.params` is the ONE place the raw
    verify/reset token exists in the database — `email_token` stores only a hash — so the row must
    stop carrying it the moment it is finished with, and stop existing once the token has expired."""
    monkeypatch.setattr(settings, "resend_api_key", "re_test"); monkeypatch.setattr(settings, "email_allowlist", "a@example.org"); monkeypatch.setattr(settings, "environment", "qa")
    monkeypatch.setattr(MT, "_http", lambda: httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"id": "re_p"}))))
    _queue(conn)
    assert MT.send_due() == {"sent": 1, "suppressed": 0, "failed": 0, "retried": 0}
    with conn.cursor() as cur:
        cur.execute("SELECT params FROM email_outbox"); assert cur.fetchone() == ({},)

    assert MT.purge_outbox() == {"purged": 0}                       # still inside the token's own TTL
    with conn.cursor() as cur:
        cur.execute("UPDATE email_outbox SET sent_at = now() - interval '25 hours'")
    assert MT.purge_outbox() == {"purged": 1}


def test_a_suppressed_row_keeps_no_link_either(conn, monkeypatch):
    """Same reasoning, the other terminal state: on QA a non-allowlisted sign-up's row is never
    sent, and there is no argument for it holding a live token for ever."""
    monkeypatch.setattr(settings, "resend_api_key", "re_test"); monkeypatch.setattr(settings, "email_allowlist", ""); monkeypatch.setattr(settings, "environment", "qa")
    monkeypatch.setattr(MT, "_http", lambda: httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"id": "re_x"}))))
    _queue(conn, to="stranger@example.org")
    assert MT.send_due() == {"sent": 0, "suppressed": 1, "failed": 0, "retried": 0}
    with conn.cursor() as cur:
        cur.execute("SELECT status, params, last_error FROM email_outbox"); status, params, error = cur.fetchone()
    assert (status, params) == ("suppressed", {}) and error == MT.REASON_NOT_ALLOWLISTED


def test_a_claimed_row_is_leased_so_a_second_worker_leaves_it_alone(conn):
    """The claim and the lease are one statement, which is what lets the sender give its connection
    back BEFORE it calls Resend (`app.mail.tasks` module note). A second drain in the same minute
    must therefore see nothing, or the same verification email goes out twice."""
    _queue(conn)
    first = OB.due(conn)
    assert [row["to"] for row in first] == ["a@example.org"]
    assert first[0]["params"] == {"link": "https://qa.foundation.vin/verify?token=t"} and first[0]["key"] == "k1"
    assert OB.due(conn) == []
    with conn.cursor() as cur:
        cur.execute("SELECT EXTRACT(EPOCH FROM next_attempt_at - now()) FROM email_outbox")
        assert abs(float(cur.fetchone()[0]) - OB.LEASE_S) < 5


def test_purge_sessions_removes_expired_revoked_and_idle_rows_and_keeps_live_ones(conn):
    """Spec §7's nightly purge. Written here rather than in the auth tests because this is the task
    that schedules it (`mail.purge_sessions`)."""
    from app.auth import passwords as P

    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('s@example.org',%s,'active') RETURNING id", (P.hash_password("orbit-lantern-quiet-42"),))
        account_id = cur.fetchone()[0]
        for name, expires, revoked, seen in (
            ("live", "now() + interval '1 day'", "NULL", "now()"),
            ("expired", "now() - interval '1 minute'", "NULL", "now()"),
            ("long-revoked", "now() + interval '1 day'", "now() - interval '31 days'", "now()"),
            ("idle", "now() + interval '1 day'", "NULL", "now() - interval '15 days'"),
        ):
            cur.execute(f"INSERT INTO session (id_hash, account_id, expires_at, revoked_at, last_seen_at) VALUES (%s,%s,{expires},{revoked},{seen})",
                        (name, account_id))
    assert MT.purge_sessions() == {"purged": 3}
    with conn.cursor() as cur:
        cur.execute("SELECT id_hash FROM session"); assert cur.fetchall() == [("live",)]


def test_the_lease_outlasts_the_worst_case_batch():
    """F2. The lease is what keeps a second worker off a row that is still being sent; if it can
    expire while the FIRST worker is still working through the batch it protects, beat re-claims the
    tail every 60 s and two `mark()`s race the ladder's `attempts`. The worst case is the whole
    batch timing out — `limit` requests, each paying its connect and read timeout — so the constants
    are pinned to each other here rather than left to drift apart in three different modules."""
    worst_case_s = OB.DUE_LIMIT * (RC.TIMEOUT.connect + RC.TIMEOUT.read)
    assert OB.LEASE_S >= worst_case_s + 300, (OB.LEASE_S, worst_case_s)


def test_one_unexpected_provider_response_burns_its_own_attempt_and_never_stops_the_batch(conn, monkeypatch):
    """F4. `ResendClient.send` reads `r.json()["id"]`: a 2xx whose body is an interposed proxy's HTML
    raises JSONDecodeError, and a 2xx JSON without `id` raises KeyError. Neither is a `ResendError`
    nor an `httpx.HTTPError`, so both used to escape `send_due()` — abandoning the rest of the
    claimed batch and leaving the offending row `queued` with no `attempts`, no `last_error` and no
    route to `failed`. Since `due()` orders by id, that row was then claimed FIRST on every
    subsequent tick, so the whole outbox stalled behind it, indefinitely, with nothing in the table
    to say why."""
    monkeypatch.setattr(settings, "resend_api_key", "re_test"); monkeypatch.setattr(settings, "environment", "production")

    def handler(req: httpx.Request) -> httpx.Response:
        to = json.loads(req.content)["to"][0]
        if to == "html@example.org":
            return httpx.Response(200, text="<html>a proxy said hello</html>")
        if to == "noid@example.org":
            return httpx.Response(200, json={"object": "email"})
        return httpx.Response(200, json={"id": "re_ok"})

    monkeypatch.setattr(MT, "_http", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    for i, to in enumerate(("html@example.org", "noid@example.org", "good@example.org")):
        _queue(conn, to=to, key=f"poison-{i}")

    assert MT.send_due() == {"sent": 1, "suppressed": 0, "failed": 0, "retried": 2}
    with conn.cursor() as cur:
        cur.execute("SELECT to_email, status, attempts, last_error FROM email_outbox ORDER BY id")
        rows = {r[0]: r[1:] for r in cur.fetchall()}
    assert rows["good@example.org"][:2] == ("sent", 1), "the batch continued past the poison rows"
    for to, exception in (("html@example.org", "JSONDecodeError"), ("noid@example.org", "KeyError")):
        status, attempts, error = rows[to]
        assert (status, attempts) == ("queued", 1), (to, status, attempts)
        assert exception in error, (to, error)


def test_the_session_purge_follows_the_resolvers_windows_rather_than_a_copy(conn, monkeypatch):
    """F8. The purge duplicated `interval '30 days'` / `interval '14 days'` as SQL literals, so
    changing `app.auth.sessions` would have left the nightly job quietly disagreeing with the
    resolver about which sessions still exist — sessions the resolver refuses but the purge keeps,
    or the reverse. The constants are passed in now, which this proves by moving them: with a
    one-day idle window, a two-day-idle session must go."""
    from app.auth import sessions as S

    assert (S.ABSOLUTE, S.IDLE) == (timedelta(days=30), timedelta(days=14))   # the shipped windows, pinned
    monkeypatch.setattr(S, "IDLE", timedelta(days=1))
    monkeypatch.setattr(S, "ABSOLUTE", timedelta(days=2))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('w@example.org','x','active') RETURNING id")
        account_id = cur.fetchone()[0]
        for name, revoked, seen in (("live", "NULL", "now()"),
                                    ("idle-2-days", "NULL", "now() - interval '2 days'"),
                                    ("revoked-3-days", "now() - interval '3 days'", "now()")):
            cur.execute(f"INSERT INTO session (id_hash, account_id, expires_at, revoked_at, last_seen_at) "
                        f"VALUES (%s,%s, now() + interval '10 days', {revoked}, {seen})", (name, account_id))
    assert MT.purge_sessions() == {"purged": 2}
    with conn.cursor() as cur:
        cur.execute("SELECT id_hash FROM session"); assert cur.fetchall() == [("live",)]
