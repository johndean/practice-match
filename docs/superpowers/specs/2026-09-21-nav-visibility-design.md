# Ruling D-C61 — no link may lead to a refusal

**John, 2026-09-21**, on seeing every nav link rendered for every account:

> where is the permission page matrix so VIN FOUNDATION admin can define by roles what links are
> acutally visible to each user and role? Right now all the links are visible to everyone, and
> shows message not accessible to the user, seems logical if we know that why are we even showing
> the link to begin with???

Brainstormed with him the same day. He ruled **both, in that order**: hide the doors now, and
design the admin-editable Permissions tab as its own later spec. This document is the first half.

## THE PRINCIPLE, which is narrower and better than "hide what is not granted"

**No link may lead to a refusal.** A link is either HIDDEN, because nothing useful sits behind it
for this viewer, or it LEADS SOMEWHERE REAL. "Show it and refuse the click" is the state this
ruling removes; "hide it and leave the viewer no route" is not automatically the answer, and for
one link John ruled explicitly that it is the wrong answer.

## Why this was not already done — it was built, measured and HELD

`A40.1` and `A40.2` are **reserved ids that were deliberately never written** (CLAUDE.md's A40
paragraph). The work existed: a `perms` adapter over the generated matrix, `perm: "page.admin"` on
the header's admin row, `perm: "page.seller"` on "List a Practice", the nav array filtered through
it. It was implemented, MEASURED, and pulled, because

> the ORACLE cannot be told what the app knows … the filter moved 28 of the 58 approved states and
> SEVEN of `baseline-manifest.json`'s thirteen frozen hashes … Until that is ruled the door is
> still SHOWN to a buyer and the router refuses the click.

So the honest answer to John's question is: because hiding it re-bases half the visual baselines
and nobody had ruled the cost worth paying. **He has now ruled it.**

## What each link does, by viewer

| Link | Visible to | Destination |
|---|---|---|
| **VIN Foundation Admin** | `page.admin` holders (staff, admin) only | the admin shell |
| **List a Practice** | **everyone, signed in or out** | dashboard · sign-up · explanation card |

**"List a Practice" is deliberately NOT hidden**, against the general principle's first arm and on
John's explicit ruling. The reasoning is recorded because it is not obvious: under **D-C59** a
seller signs up separately (`seller.apply` is `frozenset()`), so a prospective seller is someone
with NO account or no roles — and hiding this link would remove the last in-product signpost that
selling exists at all. It stays visible and stops refusing.

Its three arms:

1. **Signed out** → the seller sign-up card, which already exists (A8's family).
2. **Signed-in buyer** → a NEW gate card: selling needs its own account, with a link to seller
   sign-up. They stay signed in and nothing is destroyed. John rejected both alternatives —
   jumping straight to sign-up ("reads as a bug"), and adding a sign-out action ("puts a
   destructive-feeling action on an explanatory screen", and a second account can be created in
   another tab anyway).
3. **Seller or admin** → the seller dashboard, unchanged (`page.seller`; D-C54's superset gives
   `admin` the same).

## Composition, inventing nothing

The new card is composed from **the V3 gate card's own elements** — the A8 pattern, which built
thirteen cards (sign-up, check-email, verify-expired, forgot, reset, accept-invite,
applicant-answer, re-apply and the rest) out of that one card. No new element, colour or class.

## The cost, stated before the work starts

- The nav filter re-bases **28 of the 58 approved states** and **7 of the 13 frozen hashes**
  (`detail`, `requests`, `seller-dash`, the four `wizard-*`). Those are RULED re-pins under this
  ruling — the A18/A38 mechanism — and must be MEASURED (the A33 method) rather than predicted.
- It needs one more **declared prototype prop** so the reference can be told what the app knows
  about the signed-in account; A16.11a's own mechanism, and the same reason A9 and A54 each needed
  one. The reference is driven by `?props=` alone and receives no adapter.
- The new gate card appends one approved state; an addition, not a re-base.
- Amendment family: **A55** (A54 is taken by ruling D-C60, the same day).

## The Permissions tab — John's standing requirement, 2026-09-21

> "the implementation of the permission matrix/tab is longterm requirement by role and by user"

Recorded as a REQUIREMENT, not a deferral to be forgotten. Two things in it, and the second is the
larger: **by role** is the matrix as it exists today made editable; **by user** is a per-account
override on top of it, which the codebase has no concept of anywhere — `effective_roles` resolves
an account to its ROLES and the matrix maps roles to permissions, so there is no seam for "this
one account, differently". That is a schema change, a resolution-order rule (does a user grant add
to its role's, or replace it?), and a new answer to "why can this person do that?" for every audit.

Neither half is in this ruling. When it is designed, the honest scope is below.

## Out of scope, and explicitly deferred to its own spec

The **Permissions tab** — a screen where a VIN Foundation admin edits role → permission at
runtime. It does not exist, and CLAUDE.md records a "Permissions tab John deferred on 2026-09-07".
`GET /api/admin/permissions` (`app/api/admin_users.py:889`) is READ-ONLY, and the matrix itself is
Python (`app/auth/permissions.py`) generated into TypeScript by `npm run gen:permissions` — nothing
writes it at runtime. Making it editable means a new table, a write route, cache invalidation, an
audit trail and a re-auth gate, because editing permissions is the most security-sensitive write in
the product. **Nothing in this ruling changes who holds what** — only which doors are drawn.
