"""Task I5d — the Admin "Launch sign-ups" read surface.

`client` here is `tests/api/conftest.py`'s: it speaks over `https://qa.foundation.vin`, which is
what `check_origin_and_csrf` compares against. `member(roles=..., state=...)` returns
`(account_id, cookies, headers)`; `auth_headers(cookies, headers)` turns those into a literal
`Cookie` header (httpx 0.28 deprecates per-request `cookies=`, and `-W error` makes that a failure).
"""
import csv
import io
from datetime import UTC, datetime

import pytest

from tests.api.conftest import auth_headers

SIGNUPS = "/api/admin/signups"


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


async def test_limit_is_capped(client, conn, staff_headers):
    seed(conn, 3)
    r = await client.get(f"{SIGNUPS}?limit=100000", headers=staff_headers)
    assert r.status_code == 200 and len(r.json()["items"]) == 3


async def test_the_list_needs_signups_read(client, conn, buyer_headers):
    seed(conn, 1)
    assert (await client.get(SIGNUPS, headers=buyer_headers)).status_code == 403
    assert (await client.get(SIGNUPS)).status_code == 401


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
