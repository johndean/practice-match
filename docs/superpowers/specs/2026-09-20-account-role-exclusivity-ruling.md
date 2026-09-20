# Ruling D-C59 — buyer and seller are never the same account

**John, 2026-09-20, verbatim:**

> a buyer can not be a seller and a seller can not be a buyer - we will always keep accounts
> separate and if the edge case exists then then the user will have to have 2 accounts

**Ruled on the same day**, on the controller's finding that the running system contradicts this in
five places: **a seller signs up separately.** `seller.apply` moves off `buyer`; a seller registers
a fresh account and applies as a seller from it, the way a buyer already applies. Anyone who
genuinely needs both keeps two accounts.

`admin` is untouched. The ruling names buyer and seller; D-C54 deliberately made `admin` a
structural superset of `seller` (`page.seller`, `seller.apply`), and that stands.

## What contradicted the ruling when it was made (measured 2026-09-20, main at `1dba8e9`)

1. **Nothing enforced it.** `role_grant` (migration 011) has one CHECK, on the role NAME. No
   constraint, trigger or application code stopped an account holding both.
2. **The product manufactured the outlawed account by construction.** `app/auth/permissions.py`:
   `"seller.apply": frozenset({"buyer"})` — the ONLY route to becoming a seller was to be an
   approved buyer first, and approval ADDS `seller` beside `buyer` rather than replacing it
   (`app/api/applications.py`: "moving it to `pending` would strip every role on the next
   request"). So every seller on the platform was a buyer+seller account.
3. **The header had composed copy for it.** `app/auth/labels.py`: `elif {"buyer", "seller"} <=
   roles: base = "Approved buyer and seller"`.
4. **The matrix granted sellers the buyer's own acts**: `request.create` and `request.read_own`
   are both `frozenset({"buyer", "seller"})`.
5. **The QA personas held both**: `seller@practice-match.test` is `buyer + seller`;
   `design@practice-match.test` holds all four roles.

## The mechanism, measured rather than designed from scratch

A BUYER application is gated on ACCOUNT STATE — `BUYER_APPLY_STATES = ("verified", "declined")`.
A SELLER application was gated on a PERMISSION, and that permission is what created the defect.
The two become symmetrical: a seller application is gated on the same states, from an account that
has confirmed its email and holds no role yet.

**A permission cannot do this job and that is measured, not assumed**: `effective_roles` returns
`{"applicant"}` for a non-active account and `roles | {"applicant"}` for an active one, so EVERY
account holds `applicant` and it discriminates nothing. State is the only honest gate.

## Known cost, stated before the work started

`seller@`'s header renders "Approved buyer and seller · StartUp Club" today, and that header is on
`seller-dash` and the four `wizard-*` screens — **five of `baseline-manifest.json`'s thirteen
frozen hashes**. Dropping `buyer` from that persona re-bases them. That is a RULED re-pin under
this ruling, the A18/A38 mechanism, and must be MEASURED (the A33 method) rather than predicted.

## Open

Whether existing production or QA accounts already hold both roles, and what is done with them, is
a DATA question this ruling does not answer. Nothing here migrates an existing account's roles.
