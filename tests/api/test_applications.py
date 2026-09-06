"""Task I5, Step 1 — the buyer and seller applications.

Two adaptations of the brief's literal Step 1 code, both forced by choices already made and
reviewed in this repository rather than by anything this task decides:

* **`headers=auth_headers(cookies, hdr)`, never `cookies=`.** httpx 0.28 emits a
  `DeprecationWarning` for the per-request `cookies=` argument, and the suite's `-W error` gate
  turns that into a failure; `tests/api/conftest.py::auth_headers` is the helper every I4 test
  already uses for exactly this.
* **Refusals carry decision A5's `{"error": {"code", "message"}}` envelope,** which means the
  endpoints raise `app.auth.deps.AuthError` subclasses rather than bare `HTTPException`s — a bare
  one renders `{"detail": ...}` and `r.json()["error"]` would be a KeyError. The brief's own
  assertions (`r.json()["error"]["message"]`) require it.
"""
from __future__ import annotations

import json

from tests.api.conftest import auth_headers

FIELDS = {"name": "Rachel Mendes, DVM", "vin_member_id": "", "school_year": "Texas A&M, 2014", "license_state": "TX",
          "employer": "Relief veterinarian", "intent": "Buy within 18 months.", "affirm": True}
SELLER_FIELDS = {"practice_name": "Cedar Park Animal Hospital", "ownership_attestation": True, "license_state": "TX"}


async def test_verified_account_applies_once_and_flags_are_hints(client, conn, member, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "consolidator_keywords", "consolidator,hospital group")
    aid, cookies, hdr = member((), state="verified", email="app@mailinator.com")
    r = await client.post("/api/applications", headers=auth_headers(cookies, hdr),
                          json={"kind": "buyer", "fields": {**FIELDS, "employer": "Regional director, 14-hospital group"}})
    assert r.status_code == 202 and r.json()["status"] == "pending"
    with conn.cursor() as cur:
        cur.execute("SELECT state FROM account WHERE id=%s", (aid,)); assert cur.fetchone() == ("pending",)
        cur.execute("SELECT flags, status FROM application"); flags, status = cur.fetchone()
    assert set(flags) == {"disposable_domain", "employer_keyword"} and status == "pending"
    assert (await client.post("/api/applications", headers=auth_headers(cookies, hdr),
                              json={"kind": "buyer", "fields": FIELDS})).status_code == 409
    with conn.cursor() as cur:
        cur.execute("SELECT template FROM email_outbox"); assert [row[0] for row in cur.fetchall()] == ["application_received"]


async def test_required_fields_and_affirmation(client, conn, member):
    _aid, cookies, hdr = member((), state="verified")
    r = await client.post("/api/applications", headers=auth_headers(cookies, hdr),
                          json={"kind": "buyer", "fields": {**FIELDS, "intent": "", "affirm": False}})
    assert r.status_code == 422 and "intent" in r.json()["error"]["message"] and "affirm" in r.json()["error"]["message"]


async def test_seller_application_requires_the_buyer_role(client, conn, member):
    _aid, cookies, hdr = member(("buyer",))
    ok = await client.post("/api/applications", headers=auth_headers(cookies, hdr), json={"kind": "seller", "fields": SELLER_FIELDS})
    assert ok.status_code == 202
    _aid2, cookies2, hdr2 = member((), state="verified", email="nobuyer@example.org")
    assert (await client.post("/api/applications", headers=auth_headers(cookies2, hdr2),
                              json={"kind": "seller", "fields": {}})).status_code == 403


# --- supplemental (not in the brief's Step 1 — John's 100 % line-AND-branch ruling) ---


async def test_a_seller_application_leaves_the_account_active_and_queues_its_own_template(client, conn, member):
    """A seller applies from an ALREADY approved buyer account: `account.state` must stay `active`
    (moving it to `pending` would strip every role on the next request), and the outbox row is the
    seller template, not the buyer one."""
    aid, cookies, hdr = member(("buyer",), email="seller-apply@example.org")
    assert (await client.post("/api/applications", headers=auth_headers(cookies, hdr),
                              json={"kind": "seller", "fields": SELLER_FIELDS})).status_code == 202
    with conn.cursor() as cur:
        cur.execute("SELECT state FROM account WHERE id=%s", (aid,)); assert cur.fetchone() == ("active",)
        cur.execute("SELECT template FROM email_outbox"); assert [row[0] for row in cur.fetchall()] == ["seller_application_received"]
        cur.execute("SELECT action, target_type FROM audit_log WHERE action='application.submit'")
        assert cur.fetchone() == ("application.submit", "application")


async def test_a_seller_application_states_its_own_required_fields(client, conn, member):
    _aid, cookies, hdr = member(("buyer",), email="seller-missing@example.org")
    r = await client.post("/api/applications", headers=auth_headers(cookies, hdr),
                          json={"kind": "seller", "fields": {"practice_name": "Cedar Park Animal Hospital"}})
    assert r.status_code == 422
    message = r.json()["error"]["message"]
    assert "license_state" in message and "ownership_attestation" in message


async def test_an_unknown_kind_is_refused_before_anything_is_written(client, conn, member):
    _aid, cookies, hdr = member((), state="verified", email="kind@example.org")
    r = await client.post("/api/applications", headers=auth_headers(cookies, hdr), json={"kind": "landlord", "fields": FIELDS})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_KIND"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM application"); assert cur.fetchone()[0] == 0


async def test_an_unverified_account_cannot_apply_to_buy(client, conn, member):
    """Spec §6: the buyer application opens at `verified`. `unverified` is refused with the same
    409 a duplicate gets — the state is the caller's own and discloses nothing."""
    _aid, cookies, hdr = member((), state="unverified", email="unverified@example.org")
    r = await client.post("/api/applications", headers=auth_headers(cookies, hdr), json={"kind": "buyer", "fields": FIELDS})
    assert r.status_code == 409 and r.json()["error"]["code"] == "STATE"


async def test_an_over_large_fields_object_is_refused_by_the_schema(client, conn, member):
    _aid, cookies, hdr = member((), state="verified", email="big@example.org")
    r = await client.post("/api/applications", headers=auth_headers(cookies, hdr),
                          json={"kind": "buyer", "fields": {**FIELDS, "intent": "x" * 40_000}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
    r2 = await client.post("/api/applications", headers=auth_headers(cookies, hdr),
                           json={"kind": "buyer", "fields": {**FIELDS, **{f"extra_{i}": "y" for i in range(60)}}})
    assert r2.status_code == 422 and r2.json()["error"]["code"] == "INVALID_REQUEST"


async def test_a_second_seller_application_while_one_is_open_is_refused(client, conn, member):
    """The duplicate guard, on the kind that can reach it: a seller applies from an account that
    stays `active`, so the state check above lets the second submission through to here (a second
    BUYER application is stopped one step earlier — the account is `pending` by then)."""
    _aid, cookies, hdr = member(("buyer",), email="twice@example.org")
    assert (await client.post("/api/applications", headers=auth_headers(cookies, hdr),
                              json={"kind": "seller", "fields": SELLER_FIELDS})).status_code == 202
    again = await client.post("/api/applications", headers=auth_headers(cookies, hdr),
                              json={"kind": "seller", "fields": SELLER_FIELDS})
    assert again.status_code == 409 and again.json()["error"]["code"] == "STATE"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM application"); assert cur.fetchone()[0] == 1


async def test_applications_me_returns_the_latest_row_per_kind(client, conn, member):
    _aid, cookies, hdr = member((), state="verified", email="mine@example.org")
    assert (await client.get("/api/applications/me", headers=auth_headers(cookies))).json() == {}
    await client.post("/api/applications", headers=auth_headers(cookies, hdr), json={"kind": "buyer", "fields": FIELDS})
    with conn.cursor() as cur:
        cur.execute("UPDATE application SET status='needs_review', info_request='Which practice?'")
    body = (await client.get("/api/applications/me", headers=auth_headers(cookies))).json()
    assert set(body) == {"buyer"}
    assert body["buyer"]["status"] == "needs_review" and body["buyer"]["info_request"] == "Which practice?"
    assert body["buyer"]["submitted_at"]


async def test_flags_are_empty_when_nothing_matches_and_when_no_keywords_are_configured(client, conn, member, monkeypatch):
    from app.auth import flags
    from app.config import settings

    monkeypatch.setattr(settings, "consolidator_keywords", "")
    assert flags.compute({"employer": "Regional director, 14-hospital group"}, "someone@example.org") == []
    monkeypatch.setattr(settings, "consolidator_keywords", " , consolidator , ")
    assert flags.compute({}, "someone@example.org") == []
    assert flags.compute({"employer": "VetCo Consolidator Group"}, "someone@example.org") == ["employer_keyword"]
    assert flags.compute({}, "someone@mailinator.com") == ["disposable_domain"]


async def test_the_legacy_operator_bearer_names_no_account_and_cannot_apply(client, conn):
    """`deps.LEGACY_ADMIN` is a synthetic id with no `account` row (it is the `API_SECRET_KEY`
    bearer, alive until Task I9). It passes `account.self`, so without a check the INSERT would be
    a foreign-key violation — a 500 on a credential path. The refusal is the generic 401, for
    either kind: "you have no account here" outranks "you are not a buyer"."""
    from app.config import settings

    bearer = {"Authorization": f"Bearer {settings.api_secret_key}"}
    for kind, fields in (("buyer", FIELDS), ("seller", SELLER_FIELDS)):
        r = await client.post("/api/applications", headers=bearer, json={"kind": kind, "fields": fields})
        assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED"), kind
    assert (await client.get("/api/applications/me", headers=bearer)).json() == {}


# The vendored blocklist, pinned the way `tests/auth/test_passwords.py` pins `top100k.txt`: a
# silent swap of a list the review screen depends on fails the suite instead of passing quietly.
LIST_SHA256 = "d3a8b8550c2edd25fe8fb9de07e30d9451dfb9ff5cfbd6bc8b984e3e26ce2389"
LIST_COMMIT = "b4c9e0b23f1bc9c4799d957a1cbb99fe8e339301"
LIST_LINES = 8737


def test_the_disposable_domain_list_is_vendored_with_its_provenance():
    import hashlib
    from pathlib import Path

    from app.auth import flags

    raw = flags.DATA.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == LIST_SHA256
    assert len(raw.decode("utf-8").splitlines()) == LIST_LINES
    assert "mailinator.com" in flags._disposable()
    provenance = (Path(flags.DATA).parent / "PROVENANCE.md").read_text(encoding="utf-8")
    assert "disposable_domains.txt" in provenance and LIST_SHA256 in provenance and LIST_COMMIT in provenance
    assert json.dumps(sorted(flags._disposable()))  # a plain frozenset of str, nothing exotic
