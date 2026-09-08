"""Task I5d — the Admin "Launch sign-ups" read surface.

`client` here is `tests/api/conftest.py`'s: it speaks over `https://qa.foundation.vin`, which is
what `check_origin_and_csrf` compares against. `member(roles=..., state=...)` returns
`(account_id, cookies, headers)`; `auth_headers(cookies, headers)` turns those into a literal
`Cookie` header (httpx 0.28 deprecates per-request `cookies=`, and `-W error` makes that a failure).
"""
import csv
import inspect
import io
from datetime import UTC, datetime, timedelta

import pytest

from app.api.admin_signups import MAX_LIST
from app.auth import sessions as S
from app.auth import tokens as T
from app.config import settings
from app.mail import templates as TP
from tests.api.conftest import auth_headers

SIGNUPS = "/api/admin/signups"
LAUNCH = "/api/admin/signups/launch-mail"


def seed(conn, n, *, prefix="S", source="coming-soon", consent="coming-soon-v1", mailed=False):
    """`n` sign-ups a minute apart, newest last, so the list's DESC order and the keyset cursor
    both have something to be wrong about.

    `prefix` because `interest_signup.email_normalised` is UNIQUE: a test that seeds twice must
    give the second batch its own addresses or the second INSERT raises."""
    ids = []
    with conn.cursor() as cur:
        for i in range(n):
            cur.execute(
                "INSERT INTO interest_signup (email, email_normalised, consent_version, source, created_at, launch_mailed_at) "
                "VALUES (%s,%s,%s,%s, now() - (%s || ' minutes')::interval, %s) RETURNING id",
                (f"{prefix}{i}@x.test", f"{prefix.lower()}{i}@x.test", consent, source, n - i,
                 datetime.now(UTC) if mailed else None))
            ids.append(cur.fetchone()[0])
    return ids


@pytest.fixture
def staff_headers(member):
    _, cookies, headers = member(roles=("staff",))
    return auth_headers(cookies, headers)


@pytest.fixture
def buyer_headers(member):
    _, cookies, headers = member(roles=("buyer",))
    return auth_headers(cookies, headers)


async def test_the_list_is_newest_first_with_the_stored_address_and_the_mailed_stamp(client, conn, staff_headers):
    seed(conn, 3)
    r = await client.get(SIGNUPS, headers=staff_headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["email"] for i in items] == ["S2@x.test", "S1@x.test", "S0@x.test"]   # newest first
    assert items[0]["source"] == "coming-soon" and items[0]["consent_version"] == "coming-soon-v1"
    assert items[0]["launch_mailed_at"] is None


async def test_the_counts_describe_the_whole_table_and_the_current_filter(client, conn, staff_headers):
    seed(conn, 2, mailed=True)
    seed(conn, 3, prefix="P", source="partner-page")
    counts = (await client.get(SIGNUPS, headers=staff_headers)).json()["counts"]
    assert counts["total"] == 5 and counts["launch_mailed"] == 2 and counts["not_mailed"] == 3
    assert counts["by_source"] == {"coming-soon": 2, "partner-page": 3}
    assert counts["by_consent_version"] == {"coming-soon-v1": 5}
    assert counts["filtered"] == 5
    filtered = (await client.get(f"{SIGNUPS}?source=partner-page", headers=staff_headers)).json()
    assert [i["source"] for i in filtered["items"]] == ["partner-page"] * 3
    assert filtered["counts"]["filtered"] == 3 and filtered["counts"]["total"] == 5


async def test_a_filter_value_that_is_in_no_row_is_a_422_naming_the_values_that_are(client, conn, staff_headers):
    """F10's rule, with D-I5d-6's twist: the allowed set is the data, not a hard-coded enum, so a
    future `source` needs no code change and a typo still reads as "no such filter"."""
    seed(conn, 1)
    r = await client.get(f"{SIGNUPS}?source=comingsoon", headers=staff_headers)
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "BAD_FILTER" and "coming-soon" in body["message"]


async def test_a_bad_consent_version_filter_is_also_a_422_naming_the_values_that_are(client, conn, staff_headers):
    """`_check_filters`' second branch — `source` and `consent_version` are checked independently,
    so a bad `consent_version=` must be caught even when `source=` is fine (or absent)."""
    seed(conn, 1)
    r = await client.get(f"{SIGNUPS}?consent_version=nope", headers=staff_headers)
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "BAD_FILTER" and "coming-soon-v1" in body["message"]


async def test_the_cursor_pages_without_dropping_a_row_when_timestamps_tie(client, conn, staff_headers):
    """F3, in this table. `now()` is transaction time, so a bulk import ties every row's
    `created_at`; a cursor carrying only the timestamp drops every tied row and then reports the
    list complete."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version) "
                    "SELECT 'T'||i||'@x.test', 't'||i||'@x.test', 'coming-soon-v1' FROM generate_series(1,6) i")
    seen, cursor = [], None
    for _ in range(6):
        page = (await client.get(f"{SIGNUPS}?limit=2" + (f"&cursor={cursor}" if cursor else ""), headers=staff_headers)).json()
        seen += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 6 and len(set(seen)) == 6 and cursor is None


async def test_a_malformed_cursor_is_a_422_not_a_500(client, conn, staff_headers):
    seed(conn, 1)
    r = await client.get(f"{SIGNUPS}?cursor=nonsense", headers=staff_headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_CURSOR"


async def test_a_malformed_cursor_is_rejected_before_any_connection_is_opened(client, conn, staff_headers, monkeypatch):
    """L4 (I5d.3 review): `_keyset(cursor)` must run before `sync_conn()` opens anything, so a
    malformed cursor's 422 costs no query. The spy still calls through to the real connection —
    it only counts — so it cannot itself break a code path that legitimately needs one."""
    import app.api.admin_signups as AS

    calls = []
    real_sync_conn = AS.sync_conn

    def spy():
        calls.append(1)
        return real_sync_conn()

    monkeypatch.setattr(AS, "sync_conn", spy)
    r = await client.get(f"{SIGNUPS}?cursor=nonsense", headers=staff_headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_CURSOR"
    assert calls == []


async def test_limit_is_capped(client, conn, staff_headers):
    """M2 (I5d.3 review): seeding only 3 rows and asserting 3 come back proves nothing about the
    cap — that assertion holds whether `MAX_LIST` is 200, a different number, or does not exist.
    Seeding past the cap is what pins it, and `next_cursor` proves the 201st row is still
    reachable rather than dropped."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version) "
                    "SELECT 'L'||i||'@x.test', 'l'||i||'@x.test', 'coming-soon-v1' FROM generate_series(1, %s) i",
                    (MAX_LIST + 1,))
    r = await client.get(f"{SIGNUPS}?limit=100000", headers=staff_headers)
    assert r.status_code == 200
    assert len(r.json()["items"]) == MAX_LIST          # 200, not 201 and not 100000
    assert r.json()["next_cursor"] is not None          # …and the 201st row is still reachable


async def test_the_export_is_not_capped_at_max_list(client, conn, staff_headers):
    """L1 (I5d.3 review): `_csv_rows` must pass `MAX_EXPORT`, not `MAX_LIST`, as `LIST_SQL`'s
    LIMIT — a regression that swapped them would silently truncate the launch list at 200 rows
    under a 200 OK, which nothing else here would catch (every other CSV test exports at most
    three rows)."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version) "
                    "SELECT 'X'||i||'@x.test', 'x'||i||'@x.test', 'coming-soon-v1' FROM generate_series(1, %s) i",
                    (MAX_LIST + 1,))
    body = (await client.get("/api/admin/signups.csv", headers=staff_headers)).content.decode("utf-8")
    assert len(list(csv.reader(io.StringIO(body)))) == MAX_LIST + 2   # header + MAX_LIST+1 rows


async def test_a_filter_against_an_empty_table_names_the_special_message(client, conn, staff_headers):
    """L2 (I5d.3 review): the `(no sign-ups yet)` arm of `BadFilter`'s message — every other
    filter test seeds at least one row first, so `', '.join(known) or '(no sign-ups yet)'`'s
    `or` branch never ran. Coverage.py does not treat that `or` as a line-arc branch, which is
    why the module's 100% branch figure did not already prove this arm was exercised."""
    r = await client.get(f"{SIGNUPS}?source=anything", headers=staff_headers)
    assert r.status_code == 422
    assert r.json()["error"]["message"] == "source must be one of (no sign-ups yet)"


async def test_the_list_needs_signups_read(client, conn, buyer_headers):
    seed(conn, 1)
    assert (await client.get(SIGNUPS, headers=buyer_headers)).status_code == 403
    assert (await client.get(SIGNUPS)).status_code == 401


async def test_the_list_is_reachable_before_launch_per_d_i5d_5(dist, redis, monkeypatch):
    """M1 (I5d.3 review): D-I5d-5's unconditional mount had no test — nothing would fail if the
    `app.include_router(admin_signups_router)` line were later moved inside the `site_mode ==
    "app"` block. `401`, not `404`, is the proof: the route exists and only refuses for lack of a
    credential — `require(...)` runs at all, which it could not if `not_found_router`'s catch-all
    had already answered. Contrasted with `/api/admin/users`, which stays absent in coming-soon
    mode, so the mount really is selective rather than everything having quietly become reachable."""
    import httpx
    from httpx import ASGITransport

    from app.config import settings
    from app.main import create_app
    from tests.api.conftest import ORIGIN

    monkeypatch.setattr(settings, "site_mode", "coming_soon")
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url=ORIGIN) as c:
        signups = await c.get(SIGNUPS)
        users = await c.get("/api/admin/users")
    assert signups.status_code == 401
    assert users.status_code == 404


async def test_reading_the_list_writes_no_audit_row(client, conn, staff_headers):
    """The C2 rule: this list is polled by a screen, and `audit_log`'s triggers refuse DELETE."""
    seed(conn, 1)
    await client.get(SIGNUPS, headers=staff_headers)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log WHERE action LIKE 'signups.%'")
        assert cur.fetchone()[0] == 0


# --- the CSV export ---------------------------------------------------------------------------

async def test_the_export_is_rfc4180_utf8_with_a_header_row_and_one_row_per_signup(client, conn, staff_headers):
    seed(conn, 2)
    r = await client.get("/api/admin/signups.csv", headers=staff_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv") and "charset=utf-8" in r.headers["content-type"]
    assert r.headers["content-disposition"].startswith('attachment; filename="practice-match-signups-')
    body = r.content.decode("utf-8")
    assert not body.startswith("﻿"), "no BOM (D-I5d-7): it would make the first header cell '\\ufeffid'"
    assert "\r\n" in body and body.endswith("\r\n")
    rows = list(csv.reader(io.StringIO(body)))
    assert rows[0] == ["id", "email", "source", "consent_version", "created_at", "launch_mailed_at"]
    assert [r[1] for r in rows[1:]] == ["S1@x.test", "S0@x.test"]
    assert len(rows) == 3


async def test_the_export_quotes_a_comma_and_doubles_an_embedded_quote(client, conn, staff_headers):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version, source) "
                    """VALUES ('a@x.test', 'a@x.test', 'coming-soon-v1', 'campaign,"spring"')""")
    body = (await client.get("/api/admin/signups.csv", headers=staff_headers)).content.decode("utf-8")
    assert '"campaign,""spring"""' in body
    assert list(csv.reader(io.StringIO(body)))[1][2] == 'campaign,"spring"'


async def test_a_field_that_would_be_a_spreadsheet_formula_is_neutralised(client, conn, staff_headers):
    """D-I5d-7. `app/api/interest.py`'s EMAIL_RE accepts an address beginning with `=` or `+`, so
    this is a real value this table can hold, not a hypothetical. The untransformed value stays
    available from the JSON list, which is the source of truth."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version) "
                    "VALUES ('=1+1@x.test', '=1+1@x.test', 'coming-soon-v1')")
    body = (await client.get("/api/admin/signups.csv", headers=staff_headers)).content.decode("utf-8")
    assert list(csv.reader(io.StringIO(body)))[1][1] == "'=1+1@x.test"
    listed = (await client.get(SIGNUPS, headers=staff_headers)).json()["items"][0]
    assert listed["email"] == "=1+1@x.test"


async def test_the_export_honours_the_same_filters_as_the_list(client, conn, staff_headers):
    seed(conn, 2)
    seed(conn, 1, prefix="P", source="partner-page")
    body = (await client.get("/api/admin/signups.csv?source=partner-page", headers=staff_headers)).content.decode("utf-8")
    assert len(list(csv.reader(io.StringIO(body)))) == 2      # header + one row


async def test_the_export_needs_signups_export_and_leaves_exactly_one_audit_row(client, conn, staff_headers, buyer_headers):
    seed(conn, 3)
    assert (await client.get("/api/admin/signups.csv", headers=buyer_headers)).status_code == 403
    await client.get("/api/admin/signups.csv?source=coming-soon", headers=staff_headers)
    with conn.cursor() as cur:
        cur.execute("SELECT action, target_type, after FROM audit_log WHERE action = 'signups.export'")
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "interest_signup" and rows[0][2] == {"source": "coming-soon", "consent_version": None}


# --- the launch mail --------------------------------------------------------------------------


@pytest.fixture
def admin_headers(member, conn, redis):
    """An admin whose session confirmed its password a moment ago — `signups.notify` is in REAUTH.

    The cache drop is not optional: `sessions.Principal` carries `reauth_at` and is cached for 60 s,
    so a bare UPDATE would leave `deps.require` reading the pre-update principal and answering
    `403 REAUTH_REQUIRED` to a session the test has just freshened."""
    account_id, cookies, headers = member(roles=("admin",))
    with conn.cursor() as cur:
        cur.execute("UPDATE session SET reauth_at = now() WHERE account_id = %s", (account_id,))
    S.invalidate_account(redis, account_id)
    return auth_headers(cookies, headers)


@pytest.fixture
def admin_token_headers(member, conn):
    """A bearer credential carrying `admin` — the containment case for D-I5d-2. Minted through
    `app.auth.tokens.issue_api_token` exactly as `tests/api/test_admin_users.py`'s token cases do;
    there is no shared fixture for it, so this is its own."""
    account_id, _cookies, _headers = member(roles=("admin",))
    issued = T.issue_api_token(conn, name="i5d-test", role="admin", created_by=account_id, ttl=timedelta(days=1))
    return {"Authorization": f"Bearer {issued.raw}"}


@pytest.fixture
def launch_mail_approved(monkeypatch):
    """Controller amendment A-I5d.4: the real production defaults are `TP.LAUNCH_COPY_APPROVED =
    False` and an unset `VIN_FOUNDATION_POSTAL_ADDRESS` — either one alone refuses a REAL send
    with its own 409 before the handler does anything else (a dry run is exempt from both, the same
    way it is exempt from `NOT_LAUNCHED` — D-I5d-5's "the count is readable, the message is not
    sendable"). These tests exercise the queuing/stamping/audit behaviour with both of John's
    approvals given; `test_the_launch_mail_refuses_a_real_send_while_*` below prove the refusal on
    the untouched defaults."""
    monkeypatch.setattr(TP, "LAUNCH_COPY_APPROVED", True)
    monkeypatch.setattr(settings, "vin_foundation_postal_address", "123 Main St, Sacramento, CA 95814")


async def test_a_dry_run_counts_without_queuing_or_stamping_anything(client, conn, admin_headers):
    seed(conn, 4)
    r = await client.post(LAUNCH, json={"dry_run": True}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"dry_run": True, "selected": 4, "queued": 0, "already_mailed": 0,
                        "not_mailed": 4, "remaining": 4}
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM email_outbox")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM interest_signup WHERE launch_mailed_at IS NOT NULL")
        assert cur.fetchone()[0] == 0


async def test_dry_run_is_the_default_so_a_bodyless_call_sends_nothing(client, conn, admin_headers):
    seed(conn, 2)
    r = await client.post(LAUNCH, json={}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["dry_run"] is True and r.json()["queued"] == 0


async def test_a_real_send_queues_one_row_per_signup_and_stamps_each_one(client, conn, admin_headers, launch_mail_approved):
    seed(conn, 3)
    r = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    assert r.json() == {"dry_run": False, "selected": 3, "queued": 3, "already_mailed": 0,
                        "not_mailed": 3, "remaining": 0}
    with conn.cursor() as cur:
        cur.execute("SELECT to_email, template, params, idempotency_key FROM email_outbox ORDER BY id")
        rows = cur.fetchall()
        cur.execute("SELECT count(*) FROM interest_signup WHERE launch_mailed_at IS NULL")
        assert cur.fetchone()[0] == 0
    assert {r[1] for r in rows} == {"launch_announcement"}
    assert sorted(r[0] for r in rows) == ["S0@x.test", "S1@x.test", "S2@x.test"]
    # A-I5d.4: the CAN-SPAM address travels in the enqueued params, alongside the link — read at
    # send time from whatever `email_outbox.params` actually holds, not re-read from `settings` by
    # the worker, so a row already queued keeps the address that was configured when it was queued.
    assert all(r[2] == {"link": settings.link_base_url, "postal_address": settings.vin_foundation_postal_address}
              for r in rows)
    assert all(r[3].endswith(":launch_announcement:1") for r in rows)


async def test_sending_twice_mails_nobody_twice(client, conn, admin_headers, launch_mail_approved):
    """The whole point of `launch_mailed_at` (D-I5d-4). The outbox's own unique key cannot carry
    this: `purge_outbox` deletes delivered rows 24 hours after they are sent, so the second call
    would find no conflict."""
    seed(conn, 3)
    await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM email_outbox")            # the day after: purge_outbox has run
    second = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    assert second.json() == {"dry_run": False, "selected": 0, "queued": 0, "already_mailed": 3,
                             "not_mailed": 0, "remaining": 0}
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM email_outbox")
        assert cur.fetchone()[0] == 0


async def test_a_signup_added_after_the_send_still_gets_the_message(client, conn, admin_headers, launch_mail_approved):
    seed(conn, 2)
    await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    seed(conn, 1, prefix="L")                              # someone signs up an hour after launch
    r = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    assert r.json()["queued"] == 1 and r.json()["already_mailed"] == 2


async def test_the_batch_is_capped_and_remaining_says_how_many_are_left(client, conn, admin_headers, monkeypatch, launch_mail_approved):
    from app.api import admin_signups as AS

    monkeypatch.setattr(AS, "MAX_LAUNCH_BATCH", 2)
    seed(conn, 5)
    r = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    assert r.json()["selected"] == 2 and r.json()["queued"] == 2 and r.json()["remaining"] == 3


async def test_the_launch_mail_is_refused_while_the_site_is_still_coming_soon(client, conn, admin_headers, monkeypatch, launch_mail_approved):
    monkeypatch.setattr(settings, "site_mode", "coming_soon")
    seed(conn, 2)
    r = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_LAUNCHED"
    # ...and the dry run still answers, which is the point of D-I5d-5: the count is readable on
    # production before the flip, the message is not sendable.
    dry = await client.post(LAUNCH, json={"dry_run": True}, headers=admin_headers)
    assert dry.status_code == 200 and dry.json()["not_mailed"] == 2


async def test_the_launch_mail_needs_signups_notify_and_a_fresh_password(client, conn, member, staff_headers):
    seed(conn, 1)
    assert (await client.post(LAUNCH, json={"dry_run": True}, headers=staff_headers)).status_code == 403
    _, cookies, headers = member(roles=("admin",))                 # never re-authenticated
    r = await client.post(LAUNCH, json={"dry_run": True}, headers=auth_headers(cookies, headers))
    assert r.status_code == 403 and r.json()["error"]["code"] == "REAUTH_REQUIRED"


async def test_no_api_token_can_ever_send_the_launch_mail(client, conn, admin_token_headers):
    """D-I5d-2. A leaked `admin` api token must not be able to mail the whole launch list. It has
    no password to confirm, so the re-auth gate is permanent, and the refusal says which of the two
    it is rather than the generic 403."""
    seed(conn, 1)
    r = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_token_headers)
    assert r.status_code == 403 and r.json()["error"]["code"] == "REAUTH_TOKEN"


async def test_the_send_writes_one_audit_row_naming_the_counts(client, conn, admin_headers, launch_mail_approved):
    seed(conn, 2)
    await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    with conn.cursor() as cur:
        cur.execute("SELECT action, target_type, after, reason FROM audit_log WHERE action = 'signups.notify'")
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "signups.notify" and rows[0][1] == "interest_signup"
    assert rows[0][2] == {"selected": 2, "queued": 2, "already_mailed": 0, "not_mailed": 2}
    assert rows[0][3] == "send"


async def test_a_dry_run_is_audited_too_and_says_so(client, conn, admin_headers):
    seed(conn, 2)
    await client.post(LAUNCH, json={"dry_run": True}, headers=admin_headers)
    with conn.cursor() as cur:
        cur.execute("SELECT reason, after FROM audit_log WHERE action = 'signups.notify'")
        reason, after = cur.fetchone()
    assert reason == "dry_run" and after["queued"] == 0


async def test_nothing_here_talks_to_resend(client, conn, admin_headers, launch_mail_approved):
    """Spec §5: never a network call on the request path. The endpoint writes an outbox row and
    returns; the Celery `mail.send` task is the only thing in the codebase that opens an HTTP
    client. Asserted on the module's SOURCE — it must import neither the Resend client nor httpx —
    and on the row it leaves, which is `queued` with no provider id."""
    import app.api.admin_signups as AS

    source = inspect.getsource(AS)
    assert "resend_client" not in source and "import httpx" not in source
    seed(conn, 1)
    await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    with conn.cursor() as cur:
        cur.execute("SELECT status, provider_id FROM email_outbox")
        assert cur.fetchone() == ("queued", None)


async def test_a_row_already_in_the_outbox_is_stamped_but_not_queued_twice(client, conn, admin_headers, launch_mail_approved):
    """The crash-recovery case the handler's own docstring names: a prior attempt got as far as
    writing this signup's outbox row but crashed before the `launch_mailed_at` UPDATE landed in
    the SAME transaction. `enqueue`'s `ON CONFLICT DO NOTHING` is what keeps THIS call from writing
    a second outbox row for it — `queued` does not count a row it did not create — while the stamp
    still lands, because `launch_mailed_at` is set for the whole batch regardless of which rows in
    it were newly enqueued. There is no state in which the row stays half-mailed."""
    [signup_id] = seed(conn, 1)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO email_outbox (to_email, template, params, idempotency_key) VALUES (%s,%s,%s,%s)",
                    ("S0@x.test", "launch_announcement", "{}", f"{signup_id}:launch_announcement:1"))
    r = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    assert r.json() == {"dry_run": False, "selected": 1, "queued": 0, "already_mailed": 0,
                        "not_mailed": 1, "remaining": 0}
    with conn.cursor() as cur:
        cur.execute("SELECT launch_mailed_at IS NOT NULL FROM interest_signup WHERE id = %s", (signup_id,))
        assert cur.fetchone()[0] is True
        cur.execute("SELECT count(*) FROM email_outbox WHERE idempotency_key = %s", (f"{signup_id}:launch_announcement:1",))
        assert cur.fetchone()[0] == 1


async def test_the_launch_mail_refuses_a_real_send_while_the_copy_is_not_approved(client, conn, admin_headers):
    """Controller amendment A-I5d.4: John's ruling was "COPY NOT YET APPROVED. Do not send." —
    checked BEFORE the postal-address setting and before `SITE_MODE`, so this fires even though
    neither of those is configured either. The dry run answers regardless (D-I5d-5's "the count is
    readable, the message is not sendable")."""
    seed(conn, 2)
    r = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "LAUNCH_COPY_NOT_APPROVED"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM email_outbox")
        assert cur.fetchone()[0] == 0
    dry = await client.post(LAUNCH, json={"dry_run": True}, headers=admin_headers)
    assert dry.status_code == 200 and dry.json()["not_mailed"] == 2


async def test_the_launch_mail_refuses_a_real_send_while_the_postal_address_is_unset(client, conn, admin_headers, monkeypatch):
    """The second of A-I5d.4's two gates: the copy is approved but nobody has set
    `VIN_FOUNDATION_POSTAL_ADDRESS`, so the CAN-SPAM footer would have nothing to print. Refused by
    name rather than sent with a blank line — John's ruling: "Do not invent the address." """
    monkeypatch.setattr(TP, "LAUNCH_COPY_APPROVED", True)
    seed(conn, 2)
    r = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "LAUNCH_MAIL_NOT_CONFIGURED"
    assert "VIN_FOUNDATION_POSTAL_ADDRESS" in r.json()["error"]["message"]
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM email_outbox")
        assert cur.fetchone()[0] == 0
