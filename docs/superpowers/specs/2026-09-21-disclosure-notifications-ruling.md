# Ruling D-C62 — a buyer is told when their access opens, closes or is refused

**John, 2026-09-21**, on being shown that nothing notifies a buyer:

> how does the seller notifiy the buyer of access to floorplan, financials, etc? is this the
> mechanism?

It was not, and nothing was. He ruled: **email on grant, deny and revoke.**

## The hole, measured

`app/api/seller_requests.py` and `app/disclosure/requests.py` contain **no `enqueue`, no outbox
call and no mail of any kind**. A seller clicks Accept, the request flips to `APPROVED`, the
buyer's view genuinely changes — real name, exact pin, exact revenue, unmasked photographs,
downloadable documents — and the buyer learns this **only if they happen to return and look**, at
which point `logic.js` tells them "Seller accepted your request".

So a seller could release their financials to someone who never found out. That is the central
loop of the product — ask, grant, read — and the grant was silent.

The machinery was already there and already used one surface over: account application decisions
mail the applicant (`application_approved`, `application_declined`, `application_info_requested`,
`app/mail/templates.py`) through an outbox with retries, suppression and idempotency keys.
Disclosure decisions were simply never wired to it.

## THE PRIVACY RULE, which is the part that can go wrong

**A notification must never disclose what the decision withheld.**

- On **deny**, the buyer was refused. If the listing's identity is confidential
  (`name_disclosed` false) the mail **must not name the practice**, or the refusal itself leaks the
  identity the seller just declined to give. Same for the exact location and any document title
  the buyer is not authorized for.
- On **revoke**, access has ENDED. The mail must not re-state what they can no longer see.
- On **grant**, the buyer is authorized — but the mail still carries no financial figures, no
  document contents and no attachment. It says access opened and links to the listing; the product
  is where confidential content is read, not the mailbox.
- The seller's own identity is never added to a buyer's mail (`_BUYER_HIDDEN`'s rule).

The safe construction is that each template is composed from what `authorized_capabilities` says
the buyer may see AFTER the decision, not before it — the same one function every other surface
reads. A template that needs a listing name must ask, not assume.

## Scope

Three templates and three enqueue points, in the routes that already write the decision and its
audit row, inside the same transaction. No new table. Idempotency keyed on the request and the
decision so a retried decision cannot mail twice.

**Not in scope:** any notification to the SELLER (they performed the act), and any notification
for the staff oversight thread — John ruled that one in-app only (D-C63).
