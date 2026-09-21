# app/disclosure/notify.py
"""Ruling D-C62 (2026-09-21, `docs/superpowers/specs/2026-09-21-disclosure-notifications-ruling.md`):
"a buyer is told when their disclosure access opens, closes or is refused." Reuses the outbox
(`app.mail.outbox.enqueue`) and template renderer (`app.mail.templates`) account-application
decisions already mail through (`app/api/admin_users.py::decide`), one subsystem over.

`notify_decision` is the ONE function `app/api/seller_requests.py` calls, inside the SAME
transaction that writes the decision and its audit row -- `conn` here is that caller's connection,
never one opened here, so a decision and its mail commit or roll back TOGETHER.

THE PRIVACY RULE (the spec's own words): "A notification must never disclose what the decision
withheld." Every value below is composed from `app.disclosure.access.authorized_capabilities`,
asked FRESH after the decision, never from the listing row directly:

* Deny and revoke leave the buyer with NO active grant for this listing at all --
  `authorized_capabilities`'s own `_ACTIVE_GRANT_SQL` matches `status = 'APPROVED'` alone, and a
  denied or revoked request is never in that status -- so asking it after either of those two
  decisions always answers `frozenset()`. `access_denied`/`access_revoked`
  (`app/mail/templates.py`) declare no `name` param at all, so there is nowhere for the practice's
  identity to go even if a future edit tried to pass one; the practice's real name can only ever
  reach `access_approved`, and only through `_buyer_facing_name` below.
* `_buyer_facing_name` mirrors `app.api.listings.serialise`'s own two-part gate
  (`named = name_disclosed and "IDENTITY" in capabilities`) rather than trusting either half
  alone: the listing's `name_disclosed` ceiling (directive §8's "did the seller ever permit this
  at all") and this buyer's own `IDENTITY` capability (directive §8's "did the seller approve
  THIS buyer") are two separate questions, and a request-level grant can no more override a
  closed ceiling than a seller's global disclosure can stand in for a buyer this specific seller
  never approved. Falls back to the design's own anonymised label
  (`app.api.listings.anonymised_name`) whenever either half is closed.
* None of the three templates ever carries a financial figure, a document title or an exact
  location -- `access_approved` says access opened and links to the listing; the product is where
  confidential content is read, not the mailbox.
* The SELLER is never mailed here (they performed the act) -- this module looks up only the
  buyer's own account.

Idempotency is `<request_id>:<template>`: each of the three statuses is reachable from a given
`request` row AT MOST ONCE -- `app.disclosure.requests.decide` refuses a request that is not
`PENDING` (`_owned_pending_or_approved`'s own `STATE` refusal), and `.revoke` is equally final -- so
the pair can never legitimately repeat for the same row, and a caller that somehow reached this
twice for the same decision collides on the outbox's own `idempotency_key` UNIQUE constraint
(`ON CONFLICT DO NOTHING`) rather than mailing the buyer twice."""
from __future__ import annotations

from typing import Any

from app.api.listings import anonymised_name
from app.config import settings
from app.disclosure.access import authorized_capabilities
from app.mail.outbox import enqueue

#: `app.disclosure.requests`'s own three terminal statuses (`request.status`'s CHECK constraint,
#: `migrations/096_request.sql`), each mapped to the ONE template it earns.
TEMPLATE_FOR_STATUS: dict[str, str] = {
    "APPROVED": "access_approved",
    "DENIED": "access_denied",
    "REVOKED": "access_revoked",
}


def _buyer_facing_name(conn: Any, *, listing_id: str, seller_id: str | None, buyer_account_id: str) -> str:
    """The practice's real name, or the design's own anonymised fallback -- `app.api.listings`'s
    own `named = name_disclosed and "IDENTITY" in capabilities` gate, asked fresh here rather than
    assumed from the caller. Reading `capabilities` AFTER the decision is what makes this safe for
    `access_denied`/`access_revoked` too, should a future caller ever reuse it there: neither
    status can produce an `'APPROVED'` row for `authorized_capabilities` to match, so `capabilities`
    is always `frozenset()` and the fallback is the only value either could ever receive."""
    with conn.cursor() as cur:
        cur.execute("SELECT name, name_disclosed, area FROM listing WHERE id = %s", (listing_id,))
        row = cur.fetchone()
    if row is None:
        return "a listing"
    name, name_disclosed, area = row
    capabilities = authorized_capabilities(conn, listing_id=listing_id, seller_id=seller_id, buyer_account_id=buyer_account_id)
    if bool(name_disclosed) and "IDENTITY" in capabilities:
        return str(name)
    return anonymised_name(str(area))


def notify_decision(conn: Any, *, row: dict[str, Any]) -> None:
    """Enqueues the one mail `row["status"]` earns. `row` is whatever
    `app.disclosure.requests.decide`/`.revoke` just returned -- already carrying `status`,
    `listing_id`, `buyer_user_id` and `seller_user_id` (`app/disclosure/requests.py::_COLUMNS`).
    Never commits: the caller's own `with conn:` block does that, together with the decision and
    its audit row."""
    template = TEMPLATE_FOR_STATUS[row["status"]]
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id = %s", (row["buyer_user_id"],))
        found = cur.fetchone()
    if found is None:  # pragma: no cover - buyer_user_id is NOT NULL REFERENCES account(id)
        return
    to = found[0]
    listing_id = row["listing_id"]
    params: dict[str, Any]
    if template == "access_approved":
        name = _buyer_facing_name(conn, listing_id=listing_id, seller_id=row.get("seller_user_id"), buyer_account_id=row["buyer_user_id"])
        params = {"name": name, "link": f"{settings.link_base_url}/practices/{listing_id}"}
    else:
        params = {"link": f"{settings.link_base_url}/requests"}
    enqueue(conn, to=to, template=template, params=params, idempotency_key=f"{row['id']}:{template}")
