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
the practice's real name BY CONSTRUCTION, not merely because this module chooses not to pass one.
Only `access_approved` can ever receive one, and only when the listing's own `name_disclosed`
ceiling is open AND the approved level covers `IDENTITY` — the identical two-part gate
`app.api.listings.serialise` computes for the listing payload itself
(`named = name_disclosed and "IDENTITY" in capabilities`).
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
    # Ceiling OPEN and a FULL_CONFIDENTIAL grant -- the most permissive case there is -- and the
    # name must STILL never reach the revoke mail, because a revoked request holds no active grant.
    listing = _listing(conn, seller, name="Revoked Practice Name", name_disclosed=True)
    request_id = _pending_request(conn, listing, buyer, seller)
    req.decide(conn, request_id=request_id, seller_account_id=seller, action="approve", disclosure_level="FULL_CONFIDENTIAL", reason=None)
    row = req.revoke(conn, request_id=request_id, seller_account_id=seller)
    N.notify_decision(conn, row=row)
    rendered = _rendered(conn, buyer_email)
    assert "Revoked Practice Name" not in rendered


def test_a_denied_or_revoked_decision_never_composes_a_name_param_at_all(conn) -> None:
    """The structural half of the privacy rule, at the COMPOSER'S output rather than at the
    template renderer: `notify_decision`'s params for a deny or a revoke are EXACTLY `{"link": …}`
    -- no `name` key, whatever value it might hold -- so a future edit cannot leak a name through
    this door even by adding one to a template's own param list later. Proved by perturbation in
    the implementation report (`app/disclosure/notify.py`'s `else` branch edited to also compose
    one, this test re-run, the real failure captured, then reverted) rather than carried in the
    suite as a standing monkeypatch, since the params dict itself -- not only the rendered mail --
    is what a future reader must never be able to smuggle a name into."""
    seller, buyer = _account(conn, "s-shape1@x.org"), _account(conn, "b-shape1@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (buyer,))
        buyer_email = cur.fetchone()[0]
    listing = _listing(conn, seller, name="Shape Pin Clinic", name_disclosed=True)
    request_id = _pending_request(conn, listing, buyer, seller)

    denied = req.decide(conn, request_id=request_id, seller_account_id=seller, action="deny", disclosure_level=None, reason=None)
    N.notify_decision(conn, row=denied)
    assert set(_outbox_row(conn, buyer_email)["params"]) == {"link"}

    with conn.cursor() as cur:
        cur.execute("DELETE FROM email_outbox WHERE to_email = %s", (buyer_email,))
    request_id2 = _pending_request(conn, listing, buyer, seller)
    req.decide(conn, request_id=request_id2, seller_account_id=seller, action="approve", disclosure_level="FULL_CONFIDENTIAL", reason=None)
    revoked = req.revoke(conn, request_id=request_id2, seller_account_id=seller)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM email_outbox WHERE to_email = %s", (buyer_email,))
    N.notify_decision(conn, row=revoked)
    assert set(_outbox_row(conn, buyer_email)["params"]) == {"link"}


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
    """The ceiling is open, but THIS request was approved for `FINANCIALS` alone -- `IDENTITY` was
    never granted -- so the name must not appear even though `name_disclosed` is true."""
    seller, buyer = _account(conn, "s-name2@x.org"), _account(conn, "b-name2@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (buyer,))
        buyer_email = cur.fetchone()[0]
    listing = _listing(conn, seller, name="Financials Only Clinic", name_disclosed=True)
    request_id = _pending_request(conn, listing, buyer, seller)
    row = req.decide(conn, request_id=request_id, seller_account_id=seller, action="approve",
                     disclosure_level="FINANCIALS", reason=None)
    N.notify_decision(conn, row=row)
    outbox = _outbox_row(conn, buyer_email)
    assert outbox["params"]["name"] != "Financials Only Clinic"
    assert "Financials Only Clinic" not in _rendered(conn, buyer_email)


def test_a_grant_on_a_confidential_listing_uses_the_generic_fallback_even_at_full_confidential(conn) -> None:
    """The capability is open (`FULL_CONFIDENTIAL` covers `IDENTITY`) but the listing's OWN
    ceiling, `name_disclosed`, is closed -- the seller never agreed to be named at all, and a
    request-level grant cannot override that (directive §8's "two questions... must stay apart")."""
    seller, buyer = _account(conn, "s-name3@x.org"), _account(conn, "b-name3@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id=%s", (buyer,))
        buyer_email = cur.fetchone()[0]
    listing = _listing(conn, seller, name="Anonymous By Choice Clinic", name_disclosed=False)
    request_id = _pending_request(conn, listing, buyer, seller)
    row = req.decide(conn, request_id=request_id, seller_account_id=seller, action="approve",
                     disclosure_level="FULL_CONFIDENTIAL", reason=None)
    N.notify_decision(conn, row=row)
    assert "Anonymous By Choice Clinic" not in _rendered(conn, buyer_email)


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
