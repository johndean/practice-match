# Ruling D-C63 — a staff oversight thread on a disclosure request

**John, 2026-09-21:**

> add a reviewer-only note field with option to be visible to Seller or Buyer or BOTH

Brainstormed the same day. He ruled the note attaches to a **disclosure request** — the one place
both parties exist and where staff already hold `request.oversee` — that **the parties can reply**,
and that it is **in-app only, no email**.

## Two prerequisites, because the surface this lives on is not wired

1. **`request.oversee` has ZERO call sites.** It is declared in `app/auth/permissions.py:52` and
   enforced nowhere. There is no admin API for disclosure requests at all: `app/api/requests.py`
   is the buyer's, `app/api/seller_requests.py` is the seller's inbox, and nothing lets staff see
   across both.
2. **The Admin > Requests tab is fixture-only.** V3 DOES draw it — `admin-requests` is one of the
   thirteen frozen screens, so the surface exists as approved design — but nothing feeds it. `A37`
   is reserved for exactly this and `loadAdmin` already holds a line open for it. This is A36's
   precedent applied one tab over.

## The audience model — John ruled the most flexible and most dangerous option

Offered three, he chose **a shared room in which staff can also post privately**. Recorded plainly:
this is per-MESSAGE audience, the model with the most ways to leak, and the parties are
adversarial by construction — a mis-scoped message leaks a negotiating position, not a widget.

It is therefore held to the standard the per-buyer disclosure work set: **ONE authorization
function**, swept as a property over generated states, with an IDOR suite against it. No route
filters messages on its own.

`request_message`: the request, the author, the body, `created_at`, and `visible_to`, a set drawn
from `{seller, buyer}`. The rule is one sentence — **staff read everything; an author reads their
own; anyone else reads a message only if their party is in `visible_to`.** Empty is the default
and the fail-closed state, so a bug that loses the audience HIDES a message rather than broadcasts
it.

| Staff post | `visible_to` |
|---|---|
| internal | `{}` |
| to the seller | `{seller}` |
| to the buyer | `{buyer}` |
| to both | `{seller, buyer}` |

A seller's reply is `{}` (staff only) or `{buyer}`; a buyer's is `{}` or `{seller}`.

## Recorded risk

With no notification (his ruling), a staff note may sit unseen for days. Right for a first cut;
the first thing to revisit if these turn out to be time-sensitive. Contrast D-C62, where he ruled
that disclosure DECISIONS do mail.
