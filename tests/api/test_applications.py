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
        cur.execute("SELECT action, target_type FROM audit_log WHERE action='applications.submit'")
        assert cur.fetchone() == ("applications.submit", "application")


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


async def test_applications_me_returns_the_open_row_and_the_history(client, conn, member):
    """Reshaped in I5c from "the latest row per kind" to `{current, history}` (brief Step 3): the
    applicant's own screen needs the row it can ACT on (answer, or re-apply behind it) and the
    closed rows behind it, and `kind` now travels on each entry rather than being the key."""
    _aid, cookies, hdr = member((), state="verified", email="mine@example.org")
    assert (await client.get("/api/applications/me", headers=auth_headers(cookies))).json() == {"current": None, "history": []}
    await client.post("/api/applications", headers=auth_headers(cookies, hdr), json={"kind": "buyer", "fields": FIELDS})
    with conn.cursor() as cur:
        cur.execute("UPDATE application SET status='needs_review', info_request='Which practice?'")
    body = (await client.get("/api/applications/me", headers=auth_headers(cookies))).json()
    assert set(body) == {"current", "history"} and body["history"] == []
    assert body["current"]["kind"] == "buyer"
    assert body["current"]["status"] == "needs_review" and body["current"]["info_request"] == "Which practice?"
    assert body["current"]["submitted_at"] and body["current"]["answer"] is None


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
    assert (await client.get("/api/applications/me", headers=bearer)).json() == {"current": None, "history": []}


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


# --- Task I5c: the applicant's path back (John's ruling, 2026-09-07) ---
#
# The brief's Step 1 names fixtures that do not exist here (`needs_review_applicant`,
# `pending_applicant`, `declined_applicant`, `other_session`, `buyer_application_body`). They are
# built from `member` + the real staff decision endpoint instead — going through
# `POST /api/admin/users/{id}/decide` rather than UPDATE-ing the row by hand is what makes
# `info_request`, `decision_note` and the account state actually match what a reviewer produces.
# The brief's assertions are reproduced exactly.


async def _open_application(client, member, email, kind="buyer", fields=None):
    """A verified account with one open buyer application: `(account_id, cookies, headers, app_id)`."""
    aid, cookies, hdr = member((), state="verified", email=email)
    r = await client.post("/api/applications", headers=auth_headers(cookies, hdr),
                          json={"kind": kind, "fields": fields or FIELDS})
    assert r.status_code == 202, r.text
    return aid, cookies, hdr, r.json()["id"]


async def _decide(client, staff, account_id, action, note):
    scookies, shdr = staff
    r = await client.post(f"/api/admin/users/{account_id}/decide", headers=auth_headers(scookies, shdr),
                          json={"action": action, "note": note})
    assert r.status_code == 200, r.text
    return r


def _staff(member, email="staff-i5c@example.org"):
    _sid, scookies, shdr = member(("staff",), email=email)
    return scookies, shdr


def _one(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


async def test_applicant_answers_and_resubmits(client, conn, member):
    aid, cookies, hdr, app_id = await _open_application(client, member, "answer@example.org")
    await _decide(client, _staff(member), aid, "request_info", "Which practice?")
    assert (await client.get("/api/applications/me", headers=auth_headers(cookies))).json()["current"]["info_request"] == "Which practice?"

    r = await client.post(f"/api/applications/{app_id}/answer", headers=auth_headers(cookies, hdr),
                          json={"answer": "Cedar Park Animal Hospital, 2 DVMs"})
    assert r.status_code == 200 and r.json() == {"status": "pending"}
    assert (await client.get("/api/me", headers=auth_headers(cookies))).json()["state"] == "pending"

    status, answer, answered_at, resubmitted_at = _one(
        conn, "SELECT status, answer, answered_at, resubmitted_at FROM application WHERE id=%s", (app_id,))
    assert status == "pending" and answer.startswith("Cedar Park")
    assert answered_at is not None and resubmitted_at is not None

    assert _one(conn, "SELECT target_id, target_type FROM audit_log WHERE action='applications.answer'") == (app_id, "application")
    template, key = _one(conn, "SELECT template, idempotency_key FROM email_outbox ORDER BY id DESC LIMIT 1")
    assert template == "application_received" and key.endswith(f":{app_id}:2")


async def test_answer_requires_needs_review_and_ownership(client, conn, member):
    _pending_aid, pcookies, phdr, pending_id = await _open_application(client, member, "still-pending@example.org")
    assert (await client.post(f"/api/applications/{pending_id}/answer", headers=auth_headers(pcookies, phdr),
                              json={"answer": "x"})).status_code == 409

    nr_aid, _nrcookies, _nrhdr, nr_id = await _open_application(client, member, "asked@example.org")
    await _decide(client, _staff(member), nr_aid, "request_info", "Which practice?")
    # Somebody else's application, in the one status that WOULD accept an answer: a uniform 404,
    # never a 403 — the design's non-enumeration stance (spec §3/A5).
    other = await client.post(f"/api/applications/{nr_id}/answer", headers=auth_headers(pcookies, phdr), json={"answer": "x"})
    assert other.status_code == 404 and other.json()["error"]["code"] == "NOT_FOUND"
    assert _one(conn, "SELECT status FROM application WHERE id=%s", (nr_id,)) == ("needs_review",)


async def test_declined_applicant_reapplies(client, conn, member):
    aid, cookies, hdr, old_id = await _open_application(client, member, "declined@example.org")
    await _decide(client, _staff(member), aid, "decline", "Not enough detail.")

    r = await client.post("/api/applications", headers=auth_headers(cookies, hdr), json={"kind": "buyer", "fields": FIELDS})
    assert r.status_code == 202 and r.json()["id"] != old_id
    assert (await client.get("/api/me", headers=auth_headers(cookies))).json()["state"] == "pending"

    body = (await client.get("/api/applications/me", headers=auth_headers(cookies))).json()
    assert [h["status"] for h in body["history"]] == ["declined"] and body["current"]["status"] == "pending"
    assert body["history"][0]["decision"] == "decline" and body["history"][0]["reason"] == "Not enough detail."
    assert body["history"][0]["decided_at"]
    assert _one(conn, "SELECT target_id FROM audit_log WHERE action='applications.reapply'") == (r.json()["id"],)
    assert _one(conn, "SELECT count(*) FROM application WHERE account_id=%s", (aid,)) == (2,)


async def test_one_open_application_per_account(client, conn, member):
    _aid, cookies, hdr, _app_id = await _open_application(client, member, "one-open@example.org")
    assert (await client.post("/api/applications", headers=auth_headers(cookies, hdr),
                              json={"kind": "buyer", "fields": FIELDS})).status_code == 409


# --- supplemental (not in the brief's Step 1 — John's 100 % line-AND-branch ruling) ---


async def test_the_open_application_rule_is_per_account_not_per_kind(client, conn, member):
    """`decide` acts on the account's latest OPEN application whatever its kind, so two open rows
    of different kinds would make a staff decision ambiguous. One open row per ACCOUNT (spec
    §Lifecycle, amended 2026-09-07), not one per kind as the check read before I5c."""
    aid, cookies, hdr = member(("buyer",), email="cross-kind@example.org")
    with conn.cursor() as cur:
        cur.execute("INSERT INTO application (account_id, kind, fields, status) VALUES (%s,'buyer',%s,'needs_review')",
                    (aid, json.dumps(FIELDS)))
    r = await client.post("/api/applications", headers=auth_headers(cookies, hdr),
                          json={"kind": "seller", "fields": SELLER_FIELDS})
    assert r.status_code == 409 and r.json()["error"]["code"] == "STATE"


async def test_a_second_round_of_questions_gets_its_own_email_cause(client, conn, member):
    """The idempotency key is `{account}:{template}:{application}:{n}`; a second re-submission of
    the SAME row must not collide with the first, or the applicant's second confirmation is
    silently dropped by `ON CONFLICT DO NOTHING`."""
    aid, cookies, hdr, app_id = await _open_application(client, member, "twice-asked@example.org")
    staff = _staff(member)
    for n, answer in ((2, "Cedar Park Animal Hospital"), (3, "Two DVMs, one practice")):
        await _decide(client, staff, aid, "request_info", "More, please.")
        r = await client.post(f"/api/applications/{app_id}/answer", headers=auth_headers(cookies, hdr), json={"answer": answer})
        assert r.status_code == 200
        assert _one(conn, "SELECT idempotency_key FROM email_outbox ORDER BY id DESC LIMIT 1")[0].endswith(f":{app_id}:{n}")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM email_outbox WHERE template='application_received'")
        assert cur.fetchone()[0] == 3  # the original submission plus two re-submissions
        cur.execute("SELECT count(*) FROM audit_log WHERE action='applications.answer'")
        assert cur.fetchone()[0] == 2


async def test_a_blank_answer_is_refused_and_leaves_the_row_under_review(client, conn, member):
    """Staff asked a question; whitespace is not an answer, and must not put the row back in the
    queue as though one had been given."""
    aid, cookies, hdr, app_id = await _open_application(client, member, "blank@example.org")
    await _decide(client, _staff(member), aid, "request_info", "Which practice?")
    r = await client.post(f"/api/applications/{app_id}/answer", headers=auth_headers(cookies, hdr), json={"answer": "   "})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
    assert _one(conn, "SELECT status FROM application WHERE id=%s", (app_id,)) == ("needs_review",)
    long = await client.post(f"/api/applications/{app_id}/answer", headers=auth_headers(cookies, hdr), json={"answer": "y" * 4_001})
    assert long.status_code == 422 and long.json()["error"]["code"] == "INVALID_REQUEST"


async def test_an_unknown_application_id_is_the_same_404(client, conn, member):
    from uuid import uuid4
    _aid, cookies, hdr, _app_id = await _open_application(client, member, "unknown-app@example.org")
    r = await client.post(f"/api/applications/{uuid4()}/answer", headers=auth_headers(cookies, hdr), json={"answer": "x"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


async def test_the_legacy_operator_bearer_names_no_account_and_cannot_answer(client, conn):
    """`deps.LEGACY_ADMIN` passes `account.self` and names no `account` row (Task I9 deletes it).
    The refusal is the generic 401, exactly as it is for submitting."""
    from uuid import uuid4

    from app.config import settings
    r = await client.post(f"/api/applications/{uuid4()}/answer", headers={"Authorization": f"Bearer {settings.api_secret_key}"},
                          json={"answer": "x"})
    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


async def test_applications_me_falls_back_to_the_latest_closed_row_when_nothing_is_open(client, conn, member):
    """No open row: `current` is the newest row there is (the approved buyer application), and the
    rows behind it are the history — a row is never in both."""
    aid, cookies, hdr, buyer_id = await _open_application(client, member, "closed-only@example.org")
    staff = _staff(member)
    await _decide(client, staff, aid, "request_info", "Which practice?")
    await client.post(f"/api/applications/{buyer_id}/answer", headers=auth_headers(cookies, hdr), json={"answer": "Cedar Park"})
    await _decide(client, staff, aid, "approve", "")
    seller = await client.post("/api/applications", headers=auth_headers(cookies, hdr), json={"kind": "seller", "fields": SELLER_FIELDS})
    assert seller.status_code == 202
    await _decide(client, staff, aid, "decline", "Not this year.")

    body = (await client.get("/api/applications/me", headers=auth_headers(cookies))).json()
    assert body["current"]["id"] == seller.json()["id"] and body["current"]["kind"] == "seller" and body["current"]["status"] == "declined"
    assert [(h["kind"], h["status"], h["decision"]) for h in body["history"]] == [("buyer", "approved", "approve")]
    assert body["history"][0]["answer"] == "Cedar Park"


async def test_a_seller_answer_leaves_the_account_active_and_queues_the_seller_template(client, conn, member):
    """A seller application reaches `needs_review` from an account that stays `active` (the
    decision table's seller override). Answering it must not move the account to `pending` — that
    would strip the buyer role on the very next request."""
    aid, cookies, hdr = member(("buyer",), email="seller-answer@example.org")
    r = await client.post("/api/applications", headers=auth_headers(cookies, hdr), json={"kind": "seller", "fields": SELLER_FIELDS})
    assert r.status_code == 202
    app_id = r.json()["id"]
    await _decide(client, _staff(member), aid, "request_info", "Which practice?")
    assert _one(conn, "SELECT status FROM application WHERE id=%s", (app_id,)) == ("needs_review",)

    answered = await client.post(f"/api/applications/{app_id}/answer", headers=auth_headers(cookies, hdr),
                                 json={"answer": "Cedar Park Animal Hospital"})
    assert answered.status_code == 200 and answered.json() == {"status": "pending"}
    me = (await client.get("/api/me", headers=auth_headers(cookies))).json()
    assert me["state"] == "active" and me["roles"] == ["buyer"]
    template, key = _one(conn, "SELECT template, idempotency_key FROM email_outbox ORDER BY id DESC LIMIT 1")
    assert template == "seller_application_received" and key.endswith(f":{app_id}:2")


async def test_every_applicant_audit_action_is_in_the_applications_namespace(client, conn, member):
    """Controller ruling, 2026-09-07 (concern 3): `application.submit` was the odd singular beside
    I5c's `applications.answer` and `applications.reapply`, so an auditor grepping `audit_log` for
    this area needed two spellings. Renamed while it is free — Wave 2a has never been deployed and
    every scratch database is rebuilt from migrations, so no audit row anywhere carries the old
    name, and none ever will."""
    aid, cookies, hdr, _app_id = await _open_application(client, member, "namespace@example.org")
    await _decide(client, _staff(member), aid, "decline", "Not enough detail.")
    assert (await client.post("/api/applications", headers=auth_headers(cookies, hdr),
                              json={"kind": "buyer", "fields": FIELDS})).status_code == 202
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT action FROM audit_log WHERE target_type='application' ORDER BY action")
        assert [x[0] for x in cur.fetchall()] == ["applications.reapply", "applications.submit"]
        cur.execute("SELECT count(*) FROM audit_log WHERE action LIKE 'application.%'")
        assert cur.fetchone()[0] == 0, "the singular namespace is gone, not merely joined"
