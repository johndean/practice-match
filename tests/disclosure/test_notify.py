# tests/disclosure/test_notify.py
"""Ruling D-C62 (2026-09-21, `docs/superpowers/specs/2026-09-21-disclosure-notifications-ruling.md`):
a buyer is told when their disclosure access opens, closes or is refused. `app.disclosure.notify`
is the one function `app/api/seller_requests.py` calls, inside the SAME transaction as the
decision it just wrote and the audit row that follows it, after `app.disclosure.requests.decide`/
`.revoke` return.

THE PRIVACY RULE this whole family exists to prove: composed from
`app.disclosure.access.authorized_capabilities`, asked fresh AFTER the decision, never from the
listing row directly. A denied or revoked request holds no active grant at all — that function's
own SQL matches `status = 'APPROVED'` alone — so `access_denied`/`access_revoked` can never carry
the practice's REAL name BY CONSTRUCTION, not merely because this module chooses not to pass one.

Ruling 1 (2026-09-21, on reading the first draft) gives both a `name` param too — a buyer with
several outstanding requests could not otherwise tell WHICH was declined — and
`_buyer_facing_name` is the only thing that ever fills it, through the identical gate
`app.api.listings.serialise` computes for the listing payload itself.

**THAT GATE BECAME `named = name_disclosed OR "IDENTITY" in capabilities` UNDER RULING D-C66 (John,
2026-09-24), and four cases below are RE-KEYED OR INVERTED because of it rather than edited until
they passed.** It was `and` until then, and under `and` a denial or a revoke could never carry the
real name by construction: neither status can produce the `'APPROVED'` row
`authorized_capabilities` requires, so `capabilities` was always `frozenset()` and the `and` always
took the fallback. Under `or` the listing's own CEILING alone answers for those two statuses — an
open one names the practice, which discloses nothing, because an open ceiling is the seller
publishing that name to every signed-in buyer, this one included, before and after the decision.
The spec's privacy rule ("a notification must never disclose what the decision withheld") is still
structural and is still proved here: `capabilities` is `frozenset()` for both statuses, so what the
mail carries is a fact about the LISTING and never about this request.

This module is not in D-C66's own file list. It is changed under the A27.5 rule — a release must
not make a statement false by its own act — because leaving the `and` here would have mailed
"additional access to Austin Veterinary" to a buyer who then clicks through to the practice's real
name, on all twenty-nine QA seeds.
"""
from __future__ import annotations

from contextlib import closing
from uuid import uuid4

import pytest

from app.disclosure import notify as N
from app.disclosure import requests as req


def _account(conn, email: str) -> str:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,'x','active') RETURNING id", (email,))
        return str(cur.fetchone()[0])


def _listing(conn, seller_id: str | None, *, name: str = "Test Practice", name_disclosed: bool = False) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, name_disclosed, city, state, area, type, market, source,"
            " seller_id, status, zip, est, price, sqft)"
            " VALUES (%s,%s,%s,'Austin','TX','Austin','Small animal','Austin, TX','seller',%s,'published',"
            " '78701',1990,1000000,2500)"
            " RETURNING id",
            (f"test-{uuid4().hex}", name, name_disclosed, seller_id),
        )
        return str(cur.fetchone()[0])


def _pending_request(conn, listing_id: str, buyer_id: str, seller_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO request (listing_id, buyer_user_id, seller_user_id) VALUES (%s,%s,%s) RETURNING id",
            (listing_id, buyer_id, seller_id),
        )
        return str(cur.fetchone()[0])


def _outbox_row(conn, to_email: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT template, params, idempotency_key FROM email_outbox WHERE to_email = %s", (to_email,))
        row = cur.fetchone()
    assert row is not None, f"no outbox row addressed to {to_email!r}"
    return {"template": row[0], "params": row[1], "key": row[2]}


def _rendered(conn, to_email: str) -> str:
    """The template + HTML/text bodies actually rendered for the one outbox row addressed to
    `to_email` — the shape a real mailbox would receive, not just the raw params dict."""
    from app.mail import templates as TP

    row = _outbox_row(conn, to_email)
    r = TP.render(row["template"], row["params"], base_url="https://qa.foundation.vin")
    return row["template"] + "\n" + r.subject + "\n" + r.text + "\n" + r.html


def _emails(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT to_email FROM email_outbox")
        return [r[0] for r in cur.fetchall()]


# --- grant, deny, revoke each enqueue their own mail, to the buyer alone -----------------------


def test_approve_enqueues_access_approved_to_the_buyer(conn) -> None:
    seller, buyer = _account(conn, "s-grant1@x.org"), _account(conn, "b-grant1@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (buyer,))
        buyer_email = cur.fetchone()[0]
    listing = _listing(conn, seller)
    request_id = _pending_request(conn, listing, buyer, seller)
    row = req.decide(conn, request_id=request_id, seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    N.notify_decision(conn, row=row)
    outbox = _outbox_row(conn, buyer_email)
    assert outbox["template"] == "access_approved"
    assert outbox["params"]["link"].endswith(f"/practices/{listing}")


def test_deny_enqueues_access_denied_to_the_buyer(conn) -> None:
    seller, buyer = _account(conn, "s-deny1@x.org"), _account(conn, "b-deny1@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (buyer,))
        buyer_email = cur.fetchone()[0]
    listing = _listing(conn, seller)
    request_id = _pending_request(conn, listing, buyer, seller)
    row = req.decide(conn, request_id=request_id, seller_account_id=seller, action="deny", disclosure_level=None, reason="Not a fit")
    N.notify_decision(conn, row=row)
    outbox = _outbox_row(conn, buyer_email)
    assert outbox["template"] == "access_denied"


def test_revoke_enqueues_access_revoked_to_the_buyer(conn) -> None:
    seller, buyer = _account(conn, "s-revoke1@x.org"), _account(conn, "b-revoke1@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (buyer,))
        buyer_email = cur.fetchone()[0]
    listing = _listing(conn, seller)
    request_id = _pending_request(conn, listing, buyer, seller)
    req.decide(conn, request_id=request_id, seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    row = req.revoke(conn, request_id=request_id, seller_account_id=seller)
    N.notify_decision(conn, row=row)
    outbox = _outbox_row(conn, buyer_email)
    assert outbox["template"] == "access_revoked"


def test_no_mail_is_ever_addressed_to_the_seller(conn) -> None:
    """The seller performed the act; spec's own scope line: "Not in scope: any notification to
    the SELLER.\""""
    seller, buyer = _account(conn, "s-noseller@x.org"), _account(conn, "b-noseller@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (seller,))
        seller_email = cur.fetchone()[0]
    listing = _listing(conn, seller)
    request_id = _pending_request(conn, listing, buyer, seller)
    row = req.decide(conn, request_id=request_id, seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    N.notify_decision(conn, row=row)
    assert seller_email not in _emails(conn)


# --- THE PRIVACY RULE: deny and revoke can never name the practice ------------------------------


def test_a_denial_on_a_confidential_listing_never_names_the_practice_anywhere_in_the_rendered_mail(conn) -> None:
    seller, buyer = _account(conn, "s-priv1@x.org"), _account(conn, "b-priv1@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (buyer,))
        buyer_email = cur.fetchone()[0]
    listing = _listing(conn, seller, name="Highly Confidential Veterinary Clinic", name_disclosed=False)
    request_id = _pending_request(conn, listing, buyer, seller)
    row = req.decide(conn, request_id=request_id, seller_account_id=seller, action="deny", disclosure_level=None, reason="No thanks")
    N.notify_decision(conn, row=row)
    rendered = _rendered(conn, buyer_email)
    assert "Highly Confidential Veterinary Clinic" not in rendered


def test_a_revocation_never_names_the_practice_either(conn) -> None:
    seller, buyer = _account(conn, "s-priv2@x.org"), _account(conn, "b-priv2@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (buyer,))
        buyer_email = cur.fetchone()[0]
    # RE-KEYED UNDER D-C66: the ceiling is SHUT. It was OPEN, with a FULL_CONFIDENTIAL grant
    # before the revoke -- "the most permissive case there is" -- because under `and` a revoked
    # request held no active grant and the name could not reach the mail whatever the ceiling said.
    # Under `or` an open ceiling names the practice, and correctly: it is published to every
    # signed-in buyer. What this case is actually about -- a revoked grant carries nothing of its
    # own into the mail -- can only be seen where the ceiling is shut, so that is where it now is.
    listing = _listing(conn, seller, name="Revoked Practice Name", name_disclosed=False)
    request_id = _pending_request(conn, listing, buyer, seller)
    req.decide(conn, request_id=request_id, seller_account_id=seller, action="approve", disclosure_level="FULL_CONFIDENTIAL", reason=None)
    row = req.revoke(conn, request_id=request_id, seller_account_id=seller)
    N.notify_decision(conn, row=row)
    rendered = _rendered(conn, buyer_email)
    assert "Revoked Practice Name" not in rendered


def test_a_denied_or_revoked_decision_always_composes_the_anonymised_label_never_the_real_name(conn) -> None:
    """Ruling 1 (John, 2026-09-21, on reading the first draft): a denial or revoke now composes a
    `name` param too -- a buyer with several outstanding requests could not otherwise tell WHICH
    was declined -- so the structural half of the privacy rule moves from "no `name` key at all" to
    "the `name` key can only ever hold the ANONYMISED label". Proved here at the COMPOSER'S own
    output, not only at the rendered body (`test_a_denial_on_a_confidential_listing_never_names_the_
    practice_anywhere_in_the_rendered_mail`/`test_a_revocation_never_names_the_practice_either`
    above cover that half and are unchanged by this ruling): the listing is given its own real,
    DISCLOSED name and even a FULL_CONFIDENTIAL grant before the revoke -- the most permissive case
    there is -- and `params["name"]` is still `app.api.listings.anonymised_name`'s label and never
    the string stored in `listing.name`. Proved by perturbation in the implementation report
    (`_buyer_facing_name` edited to return the raw `name` unconditionally, this test re-run, the
    real failure captured, then reverted) rather than carried in the suite as a standing
    monkeypatch, since it is `authorized_capabilities` answering `frozenset()` for these two
    statuses -- not this test -- that makes the real name unreachable."""
    from app.api.listings import anonymised_name

    seller, buyer = _account(conn, "s-shape1@x.org"), _account(conn, "b-shape1@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (buyer,))
        buyer_email = cur.fetchone()[0]
    # RE-KEYED UNDER D-C66, same reason as the case above: `name_disclosed` was True here to make
    # the point that even the most permissive listing could not leak through a denial or a revoke.
    # The ceiling is what answers for those two statuses now, so the permissive half of that claim
    # moves to `test_a_denial_or_a_revoke_on_a_published_name_carries_the_name_the_buyer_can`
    # `_already_read` below and this case keeps the half it was really built to hold: the COMPOSER
    # can only ever emit the anonymised label where the seller has not published the name.
    listing = _listing(conn, seller, name="Shape Pin Clinic", name_disclosed=False)
    expected_label = anonymised_name("Austin")  # `_listing()`'s own fixed `area`
    request_id = _pending_request(conn, listing, buyer, seller)

    denied = req.decide(conn, request_id=request_id, seller_account_id=seller, action="deny", disclosure_level=None, reason=None)
    N.notify_decision(conn, row=denied)
    denied_params = _outbox_row(conn, buyer_email)["params"]
    assert set(denied_params) == {"name", "requested", "link"}
    assert denied_params["name"] == expected_label
    assert denied_params["name"] != "Shape Pin Clinic"

    with conn.cursor() as cur:
        cur.execute("DELETE FROM email_outbox WHERE to_email = %s", (buyer_email,))
    request_id2 = _pending_request(conn, listing, buyer, seller)
    req.decide(conn, request_id=request_id2, seller_account_id=seller, action="approve", disclosure_level="FULL_CONFIDENTIAL", reason=None)
    revoked = req.revoke(conn, request_id=request_id2, seller_account_id=seller)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM email_outbox WHERE to_email = %s", (buyer_email,))
    N.notify_decision(conn, row=revoked)
    revoked_params = _outbox_row(conn, buyer_email)["params"]
    assert set(revoked_params) == {"name", "requested", "link"}
    assert revoked_params["name"] == expected_label
    assert revoked_params["name"] != "Shape Pin Clinic"


# --- a grant names the practice only when BOTH the ceiling and the capability are open ----------


def test_a_grant_on_a_disclosed_listing_with_identity_names_the_practice(conn) -> None:
    seller, buyer = _account(conn, "s-name1@x.org"), _account(conn, "b-name1@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (buyer,))
        buyer_email = cur.fetchone()[0]
    listing = _listing(conn, seller, name="Blue Sky Veterinary Clinic", name_disclosed=True)
    request_id = _pending_request(conn, listing, buyer, seller)
    row = req.decide(conn, request_id=request_id, seller_account_id=seller, action="approve",
                     disclosure_level="FULL_CONFIDENTIAL", reason=None)
    N.notify_decision(conn, row=row)
    outbox = _outbox_row(conn, buyer_email)
    assert outbox["params"]["name"] == "Blue Sky Veterinary Clinic"


def test_a_grant_that_does_not_cover_identity_uses_the_generic_fallback(conn) -> None:
    """**RE-KEYED UNDER D-C66 (2026-09-24): the ceiling moves open -> shut.** This case read "the
    ceiling is open, but THIS request was approved for `FINANCIALS` alone -- `IDENTITY` was never
    granted -- so the name must not appear even though `name_disclosed` is true." Under `or` an
    open ceiling names the practice on its own and correctly, because it is published to every
    signed-in buyer; the claim this case exists for -- one capability does not confer another --
    is only visible where the ceiling is shut."""
    seller, buyer = _account(conn, "s-name2@x.org"), _account(conn, "b-name2@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (buyer,))
        buyer_email = cur.fetchone()[0]
    listing = _listing(conn, seller, name="Financials Only Clinic", name_disclosed=False)
    request_id = _pending_request(conn, listing, buyer, seller)
    row = req.decide(conn, request_id=request_id, seller_account_id=seller, action="approve",
                     disclosure_level="FINANCIALS", reason=None)
    N.notify_decision(conn, row=row)
    outbox = _outbox_row(conn, buyer_email)
    assert outbox["params"]["name"] != "Financials Only Clinic"
    assert "Financials Only Clinic" not in _rendered(conn, buyer_email)


def test_a_grant_on_a_confidential_listing_names_the_practice_to_the_buyer_it_was_granted_to(conn) -> None:
    """**INVERTED UNDER D-C66 (2026-09-24). This is the ruling, in the mailbox.**

    It used to be called `test_a_grant_on_a_confidential_listing_uses_the_generic_fallback_even_at_
    full_confidential` and asserted that a `FULL_CONFIDENTIAL` grant could not name a listing whose
    own `name_disclosed` ceiling was shut -- "the seller never agreed to be named at all, and a
    request-level grant cannot override that". Read from the seller's side that is: they tick "Keep
    practice name and address hidden UNTIL I APPROVE A BUYER", they approve a buyer, and the buyer
    is told about "Austin Veterinary". D-C66 makes the ceiling the PUBLIC DEFAULT and the grant the
    release, so the buyer the seller approved is told which practice they were approved for -- the
    same name `app/api/listings.py::serialise` now serves them on the listing page, which is the
    whole reason this gate is a mirror of that one.

    The fallback has not gone anywhere: it is what a buyer with NO grant gets on the same listing,
    which the two denial/revoke cases above prove on a shut ceiling."""
    seller, buyer = _account(conn, "s-name3@x.org"), _account(conn, "b-name3@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (buyer,))
        buyer_email = cur.fetchone()[0]
    listing = _listing(conn, seller, name="Anonymous By Choice Clinic", name_disclosed=False)
    request_id = _pending_request(conn, listing, buyer, seller)
    row = req.decide(conn, request_id=request_id, seller_account_id=seller, action="approve",
                     disclosure_level="FULL_CONFIDENTIAL", reason=None)
    N.notify_decision(conn, row=row)
    assert _outbox_row(conn, buyer_email)["params"]["name"] == "Anonymous By Choice Clinic"
    assert "Anonymous By Choice Clinic" in _rendered(conn, buyer_email)


def test_a_denial_or_a_revoke_on_a_published_name_carries_the_name_the_buyer_can_already_read(conn) -> None:
    """The other side of D-C66 in the mailbox, and the reason the three cases above could move
    their ceilings without losing anything: with the ceiling OPEN the practice's name is published
    to every signed-in buyer, so a denial that names it discloses nothing the recipient could not
    read on the listing page a second earlier. `capabilities` is still `frozenset()` here -- a
    denied request holds no grant -- so what the mail carries is a fact about the LISTING, which is
    exactly what the spec's privacy rule ("never disclose what the decision withheld") permits."""
    seller, buyer = _account(conn, "s-name4@x.org"), _account(conn, "b-name4@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (buyer,))
        buyer_email = cur.fetchone()[0]
    listing = _listing(conn, seller, name="Published Name Clinic", name_disclosed=True)
    request_id = _pending_request(conn, listing, buyer, seller)
    denied = req.decide(conn, request_id=request_id, seller_account_id=seller, action="deny",
                        disclosure_level=None, reason=None)
    N.notify_decision(conn, row=denied)
    assert _outbox_row(conn, buyer_email)["params"]["name"] == "Published Name Clinic"


# --- idempotency: a retried decision cannot mail twice ------------------------------------------


def test_calling_notify_decision_twice_for_the_same_row_enqueues_once(conn) -> None:
    seller, buyer = _account(conn, "s-idem1@x.org"), _account(conn, "b-idem1@x.org")
    listing = _listing(conn, seller)
    request_id = _pending_request(conn, listing, buyer, seller)
    row = req.decide(conn, request_id=request_id, seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    N.notify_decision(conn, row=row)
    N.notify_decision(conn, row=row)  # a retried caller handed the SAME row a second time
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM email_outbox WHERE template = 'access_approved'")
        assert cur.fetchone()[0] == 1


def test_the_idempotency_key_is_derived_from_the_request_and_the_decision(conn) -> None:
    seller, buyer = _account(conn, "s-idem2@x.org"), _account(conn, "b-idem2@x.org")
    listing = _listing(conn, seller)
    request_id = _pending_request(conn, listing, buyer, seller)
    row = req.decide(conn, request_id=request_id, seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    N.notify_decision(conn, row=row)
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (buyer,))
        buyer_email = cur.fetchone()[0]
    outbox = _outbox_row(conn, buyer_email)
    assert request_id in outbox["key"] and "access_approved" in outbox["key"]


# --- the decision and its mail share one transaction ---------------------------------------------


def test_a_decision_and_its_mail_share_one_transaction(conn, monkeypatch) -> None:
    """`app/api/seller_requests.py` opens ONE transaction and calls `req.decide` then
    `notify.notify_decision` inside it, `app/api/admin_users.py`'s own shape for account
    decisions. Reproduced here at the same two primitives (a real `sync_conn()` transaction, the
    real `req.decide`) with `notify_decision` made to raise: the request's own status write must
    roll back WITH it, or a decision could commit with no mail at all."""
    from app.db import sync_conn

    seller, buyer = _account(conn, "s-tx1@x.org"), _account(conn, "b-tx1@x.org")
    listing = _listing(conn, seller)
    request_id = _pending_request(conn, listing, buyer, seller)

    def _boom(conn, *, row):
        raise RuntimeError("simulated failure after the decision write")

    monkeypatch.setattr(N, "notify_decision", _boom)

    with pytest.raises(RuntimeError), closing(sync_conn()) as tx, tx:
        row = req.decide(tx, request_id=request_id, seller_account_id=seller, action="approve",
                         disclosure_level=None, reason=None)
        N.notify_decision(tx, row=row)

    with conn.cursor() as cur:
        cur.execute("SELECT status FROM request WHERE id=%s", (request_id,))
        assert cur.fetchone()[0] == "PENDING", "the decision must not survive a mail failure in the same transaction"
        cur.execute("SELECT count(*) FROM email_outbox")
        assert cur.fetchone()[0] == 0
