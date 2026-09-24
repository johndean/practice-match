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
  decisions always answers `frozenset()`. Ruling 1 (2026-09-21, on reading the first draft) gives
  `access_denied`/`access_revoked` (`app/mail/templates.py`) a `name` param too -- a buyer with
  several outstanding requests could not otherwise tell WHICH was declined -- and
  `_buyer_facing_name` below is the ONLY place either template's `name` is filled.

  **WHAT THAT GUARANTEES CHANGED SHAPE UNDER RULING D-C66 (2026-09-24) and is stated again rather
  than left as it was.** Until then the guarantee was structural: neither status can produce the
  `'APPROVED'` row `authorized_capabilities` requires, so `capabilities` was always `frozenset()`
  and the `and` gate could only ever yield the anonymised label. D-C66 joins the two halves with
  `or`, so a denial or a revoke on a listing whose seller left the name ceiling OPEN now names the
  practice. That is not a disclosure: an open ceiling means every signed-in buyer already reads
  that name on the listing page, this one included, before and after the decision. The privacy
  rule the spec states -- "a notification must never disclose what the decision withheld" -- is
  still structural, because `capabilities` is still `frozenset()` for both statuses and the
  CEILING alone answers, which is a fact about the listing rather than about this request.
* `_buyer_facing_name` mirrors `app.api.listings.serialise`'s own two-part gate
  (`named = name_disclosed or "IDENTITY" in capabilities`) rather than trusting either half
  alone: the listing's `name_disclosed` ceiling (directive §8's "did the seller ever permit this
  at all") and this buyer's own `IDENTITY` capability (directive §8's "did the seller approve
  THIS buyer") are two separate questions, and the answer is yes if EITHER says so -- an open
  ceiling is the seller publishing the name, and a grant releases it whether or not they have.
  Falls back to the design's own anonymised label (`app.api.listings.anonymised_name`) when
  neither is open.

  **THE JOIN WAS `and` UNTIL RULING D-C66 (John, 2026-09-24), and this module is not in that
  ruling's own file list: it is here under the A27.5 rule, because the ruling makes this copy
  of the gate disagree with the one it mirrors BY ITS OWN ACT.** With `and`, a buyer approved
  for `FINANCIALS` on a listing whose name ceiling the seller had left open -- which is all
  twenty-nine QA seeds -- would be mailed "additional access to Austin Veterinary" and then
  click through to a page headed with the practice's real name. The two must answer one question
  once. The direction is deliberately NOT a privacy widening on its own: `or` here can only ever
  name a practice `serialise` would already have named for the same buyer, because both read the
  same column and the same capability set.
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

from typing import Any, cast

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
    own `named = name_disclosed or "IDENTITY" in capabilities` gate (D-C66, 2026-09-24; it was
    `and` until then, see the module docstring), asked fresh here rather than assumed from the
    caller. Reading `capabilities` AFTER the decision is what makes this safe for
    `access_denied`/`access_revoked` too, now that ruling 1 (2026-09-21) reuses it there: neither
    status can produce an `'APPROVED'` row for `authorized_capabilities` to match, so `capabilities`
    is always `frozenset()` and the CEILING alone decides for those two -- a shut one gives the
    anonymised label, an open one gives the name the buyer can already read on the listing page.
    This docstring anticipated exactly that reuse before either caller existed, and reading it
    fresh per call -- rather than trusting a value the caller already had -- is what proved it
    sound."""
    with conn.cursor() as cur:
        cur.execute("SELECT name, name_disclosed, area FROM listing WHERE id = %s", (listing_id,))
        row = cur.fetchone()
    # UNGUARDED, and that is measured rather than careless. `request.listing_id` is
    # `NOT NULL REFERENCES listing(id) ON DELETE CASCADE` (migrations/096_request.sql:15) and this
    # runs inside the decide transaction holding that request row, so the listing cannot be
    # absent: a concurrent delete would have to cascade THIS REQUEST away first, and it cannot
    # while the row is held. A `row is None` arm here was dead code that no test could reach
    # honestly, and the bundle's own rule is to delete such a branch rather than defend a state
    # the schema forbids — a guard nobody can exercise reads as "this can happen" and it cannot.
    name, name_disclosed, area = cast("tuple[Any, Any, Any]", row)
    capabilities = authorized_capabilities(conn, listing_id=listing_id, seller_id=seller_id, buyer_account_id=buyer_account_id)
    if bool(name_disclosed) or "IDENTITY" in capabilities:
        return str(name)
    return anonymised_name(str(area))


def _requested_on(value: Any) -> str:
    """The date the BUYER made the request, in the admin tab's own "August 12" style. Their own
    act, so it discloses nothing about the seller or the listing."""
    return f"{value:%B} {value.day}"


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
    # John's ruling of 2026-09-21, on reading the first draft: a denial that names nothing leaves a
    # buyer with several outstanding requests unable to tell WHICH was declined. Every template now
    # carries the label and the date, and both are safe BY CONSTRUCTION rather than by judgement:
    #
    #   * the label is `_buyer_facing_name`, the same capability-gated function all three now share.
    #     For DENIED and REVOKED `authorized_capabilities` can only answer `frozenset()` -- neither
    #     status produces an `'APPROVED'` row for it to match -- so those two provably receive the
    #     anonymised label and never the practice's real name. That is the reuse this helper's own
    #     docstring anticipated and proved sound before any caller existed.
    #   * the anonymised label is what the buyer ALREADY sees on the listing card before asking for
    #     anything, so it discloses nothing a refusal could be said to have withheld.
    #   * the date is the buyer's OWN act. It cannot disclose anything about the seller.
    name = _buyer_facing_name(conn, listing_id=listing_id, seller_id=row.get("seller_user_id"), buyer_account_id=row["buyer_user_id"])
    requested = _requested_on(row["requested_at"])
    params: dict[str, Any]
    if template == "access_approved":
        params = {"name": name, "link": f"{settings.link_base_url}/practices/{listing_id}"}
    else:
        params = {"name": name, "requested": requested, "link": f"{settings.link_base_url}/requests"}
    enqueue(conn, to=to, template=template, params=params, idempotency_key=f"{row['id']}:{template}")
