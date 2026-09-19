# Per-Buyer Disclosure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single global "show identifiable content" switch that today discloses a listing's confidential facts to *every* signed-in buyer at once with a real buyer-and-listing authorization relationship, so a seller can approve one buyer's access request without opening the listing to anyone else — making the five pieces of copy the wizard-step audit found (finding 4, `.superpowers/sdd/2026-09-09-image-identifiability-protection/wizard-step-audit.md`) literally true.

**Architecture:** One new table (`request`, migration 096, previously reserved for this exact concept by the unbuilt A43 "Requests" family — `docs/MIGRATIONS.md`, `docs/superpowers/specs/2026-09-13-admin-control-surface-design.md` §5) records a buyer's access request against a listing and, once decided, the disclosure level a seller granted. A new small module, `app/disclosure/access.py`, is the **one function** every confidential-resource route calls to ask "does this buyer currently hold this capability for this listing" — it reads the request table and ANDs the answer against the listing's own pre-existing global flags, which keep their present meaning as publication ceilings (directive §8, §24) rather than becoming the authorization mechanism themselves. The three routes that already serve confidential content (`GET /api/listings`, `GET /api/listings/{id}`, `GET /api/listings/{id}/photos/{n}`, and `GET /api/seller/listings/{id}/documents/{id}`) each grow one extra, server-side check through that function; two new small route files (`app/api/requests.py`, `app/api/seller_requests.py`) let a buyer ask and a seller decide. Existing permissions (`request.create`, `request.read_own`, `request.answer_own` — already in `app/auth/permissions.py`, unused until now) gate who may reach the routes at all; the buyer-and-listing-specific decision is enforced in the handler, the same pattern `app/api/seller_listings.py:18` already uses for listing ownership ("Ownership is enforced HERE, not in the matrix").

**Tech Stack:** FastAPI + psycopg2 (sync) on the existing `app/api/*` pattern; PostgreSQL migration via `scripts/migrate.py`'s numbered-ledger convention; pytest + the existing `tests/api/conftest.py` fixtures (`member`, `api_client`, `signed_in`, `audit_rows`) for every test in this plan — no new test library. Frontend wiring (Task 14) reuses the existing TypeScript adapter idiom (`frontend/src/listings/seller.ts`) and the design's own amendment-free "adapter present → real rows" ternary (A16.1/A17.1's mechanism) — no design amendment, no new screen.

## Global Constraints

- **Fail closed (directive §19).** A missing authorization record, an expired grant, a DB miss, or any ambiguity means NOT AUTHORIZED. No function in this plan may default to "assume approved."
- **Server-side only (directive §12).** Every confidential field or byte is gated in the route handler or in a function it calls before the response is built — never in a header, a query flag, or trusted client state.
- **The global switches are not deleted and are not the authorization mechanism (directive §8, §24).** `location_disclosed`, `name_disclosed`, `rev_disclosed`, `documents_disclosed` (`migrations/016_listing.sql`) and `identifiable_content_visibility` (`migrations/040_listing_identifiable_content_visibility.sql`) keep exactly their present meaning — see "What each existing flag still means" below — and this plan adds the per-buyer grant **beside** them, never folds them together.
- **One authorization function (directive §12, §18).** `app/disclosure/access.py`'s `authorized_capabilities`/`has_capability` is the only code in the repository that reads the `request` table to answer "is this buyer authorized." No route re-implements the question.
- **Disclosure levels are explicit permissions, not a boolean (directive §16).** Six named capabilities (`IDENTITY`, `EXACT_LOCATION`, `UNREDACTED_IMAGES`, `FINANCIALS`, `FLOOR_PLANS`, `FULL_CONFIDENTIAL`), reusing this project's own vocabulary — see "Where disclosure levels live" below.
- **No second copy of the RBAC matrix (CLAUDE.md's A16.23/A40 lesson).** Buyer-listing authorization is a resource-ownership question, not a role question, and does not go in `app/auth/permissions.py`. The four existing `request.*` permissions already there are reused unchanged.
- **The five pieces of copy in `frontend/src/logic.js` (finding 4) are not edited.** They already describe the behavior this plan builds; verifying that is part of Task 14, not a rewrite.
- **Surgical diffs.** No unrelated refactor rides along. Two pre-existing, unrelated defects the research below surfaced — the wizard's single `anon` checkbox conflating name and location disclosure (finding 1), and the revenue-range display slot that has never existed (finding 3) — are explicitly **not** touched by this plan.
- **No inline `HTTPException`.** Every refusal in every new or modified route uses the existing `Refusal`/`_refused` pattern (`app/api/seller_listings.py:201-206,647-650`) or `_error(code, message, status)` (`app/api/listings.py:135`), so the response body is always `{"error": {"code", "message"}}`, never FastAPI's default envelope.
- **Every guard is a module-level `require(...)` constant used through `Depends`, never wrapped** (the route-guard/audit-drift tests resolve a permission by the guard object's identity, `app.auth.deps.permission_of`).
- **Verification gate before any deploy** is the one in CLAUDE.md — this plan does not change it, and Task 14's frontend work still owes `npm run typecheck && npm run build && npm test` plus the visual/DOM/smoke oracles green with **zero** re-based approved states (it touches no template).

---

## What each existing global flag still means (directive §8, §24)

None of these five columns is touched, renamed, or given a new meaning. Each becomes a **ceiling**: a seller-set precondition that must be true before *any* buyer can ever receive the confidential value, checked **in addition to**, never instead of, the new per-buyer grant.

| Flag | Column | Still means | New AND-condition |
|---|---|---|---|
| `location_disclosed` | `migrations/016_listing.sql:23` | "The seller permits the exact street/zip/phone/coordinates to be disclosed to *any* buyer at all." Read at `app/api/listings.py:363,452-459`. | A buyer additionally needs the `EXACT_LOCATION` capability. When false, no buyer — approved or not — ever receives it (unchanged from today). |
| `name_disclosed` | `016:25` | "The seller permits the real practice name (and slug) to be disclosed at all." Read at `listings.py:364,401-404`. | Needs `IDENTITY`. |
| `rev_disclosed` | referenced at `listings.py:411` (`row.get("rev_disclosed")`) | "The seller permits the exact revenue figure to be disclosed at all," as distinct from the design's still-unbuilt range display (finding 3 — untouched, out of scope). | Needs `FINANCIALS`. |
| `documents_disclosed` | written at `app/api/seller_listings.py:341`, read back into the seller's own draft view at `:533`, reserved at `:1631-1641` | "The seller permits financial statements, floor plans and other uploaded documents to be disclosed at all." | Needs `FINANCIALS` (a `kind='financials'` document) or `FLOOR_PLANS` (`kind='floor_plan'`) or `FULL_CONFIDENTIAL` (`kind` in `('equipment','other')` — see Task 9). |
| `identifiable_content_visibility` | `migrations/040_listing_identifiable_content_visibility.sql`, `'SHOW'`/`'NOT_SHOW'` | Exactly what the image-identifiability sub-project built it for: whether an unredacted derivative may ever be shown to **anyone**, independent of who is buying. Read by `app/privacy/delivery.py::buyer_variant`. | Needs `UNREDACTED_IMAGES`. Under `NOT_SHOW` no buyer, however approved, ever receives the unredacted derivative — it is a hard veto, not a default that a grant overrides, which is the safest reading of "the safest privacy state is the default" applied one level up. |

A useful, deliberate side effect of the AND: toggling any ceiling flag back off (e.g. a seller who re-enables anonymity) *immediately* closes that dimension for every buyer, including ones already approved, with no need to touch their `request` row. This is not required by directive §15 (which is about revoking one buyer) but it falls out of the design for free and is worth the one sentence recording it, because it means a seller has both a per-buyer control (revoke) and a global panic button (the ceiling flags they already have) and the two compose correctly.

## Where disclosure levels live, and why not in `app/auth/permissions.py`

**Beside the matrix, not in it.** `app/auth/permissions.py`'s `MATRIX` answers exactly one question — "which **roles** may reach this **route**" — and CLAUDE.md records two real incidents (A16.23, A40) caused by a second, unsynchronized copy of that exact role→permission mapping appearing somewhere else in the codebase. Per-buyer disclosure is a different question: "does *this specific account* hold a grant against *this specific listing row*." That is a resource-ownership check, and this codebase already has a precedent for exactly that shape, stated in so many words at `app/api/seller_listings.py:18`: *"Ownership is enforced HERE, not in the matrix (D7). `listing.manage_own` says a seller may manage listings; `seller_id = principal.account_id` says which."* Disclosure levels are `app/disclosure/access.py`'s answer to "which listing, which buyer, which level" in exactly that spirit — a second, unrelated fact from the same role check, never a competing statement of it. The four `request.*` entries that already exist in `MATRIX` (`request.create`, `request.read_own`, `request.answer_own`, `request.oversee` — `app/auth/permissions.py:22,24,38`) are the correct, and sufficient, RBAC layer: they answer "may this role reach a request route at all," and the handler answers "may this account act on *this* request/listing," exactly the two-layer split ownership checks already use everywhere else in this codebase.

`request.oversee` (staff/admin) is **not used by this plan** — no route in this plan needs it. It was reserved for A43's admin Requests tab (`docs/superpowers/specs/2026-09-13-admin-control-surface-design.md` §5's `GET /api/admin/requests`), which the per-buyer-disclosure directive does not ask for (§13 lists only buyer and seller routes plus the confidential-content routes) and which this plan deliberately leaves to that family.

## What needs a design ruling from John, and what is buildable now

This product's UI is generated from the approved V3 design bundle through the amendment mechanism, and CLAUDE.md forbids inventing screens. Everything in Tasks 1–13 is pure API/data work and needs no design ruling at all. Task 14 wires the **existing** interest modal, "My Requests" screen, and seller-dashboard inbox (all already drawn in `frontend/src/logic.js`, all already reachable at approved states `interest-modal`, `requests`, `seller-dash` — `frontend/tests/screens.ts:309-311`) to the real API using the established "adapter present → real data, adapter absent → design fixture" idiom (A16.1/A17.1) — no template edit, no amendment, no re-based baseline. Two things the directive asks for have **no element in the design at all** and are out of scope for Task 14 pending John's ruling:

1. **A "Revoke" control on an already-approved row in the seller's inbox (directive §5).** The existing seller-dash inbox fixture (`frontend/src/logic.js:1674,1711-1712`) draws exactly two actions on a pending request — `accept`/`decline` — and no third action for a request already in the `accepted` state. There is no button, icon, or layout in V3 for this. Composing one needs the same "compose from V3's own elements under your approval" process John already used for A41–A47 (`docs/superpowers/specs/2026-09-13-admin-control-surface-design.md` §1's rule 1). Task 14 wires accept/decline only; revoke is reachable **today, from Task 6's API**, by any HTTP client (`curl`, a future admin tool, or John's own testing) — it is not blocked on a screen, only on a *seller-facing button for it*.
2. **A distinct "revoked" treatment on the buyer's side (My Requests, the detail page's `sentLabel`/`sentNote`, `frontend/src/logic.js:1855-1856`).** The design has three states for a buyer's own request — not sent, pending, accepted, declined — and no fourth for "was accepted, now revoked." Task 14 defaults a `REVOKED` request to the same pill/copy as `DENIED` ("declined") for the buyer's view, which is honest (the buyer is, in fact, no longer authorized) but not a bespoke sentence. This default needs no new design element and ships as part of Task 14; a distinct "your access was revoked" sentence, if John wants one, is a literal-copy amendment for a later, separate task.

Two more items are **judgment calls this plan makes rather than leaves blocked**, recorded here so John can rule differently if he disagrees: (a) V1 ships a single, binary request/grant — a buyer's request and a seller's approval both default to `FULL_CONFIDENTIAL` (matching the *existing* design's binary accept/decline, and the seller inbox's "Financial packet unlocked" reply text, `logic.js:1711`) — while the data model and the API (Tasks 1–6) fully support a finer per-level request/grant for a future screen that lets a buyer ask for, or a seller grant, exactly one capability; (b) a document whose `kind` is `'equipment'` or `'other'` (i.e., every document uploaded today — the wizard has no kind picker, `migrations/031_listing_asset.sql:16-17`) requires the broadest grant, `FULL_CONFIDENTIAL`, to read (Task 9) — the fail-closed reading of an undifferentiated document, not a narrower guess.

---

## File Structure

| File | Responsibility |
|---|---|
| `migrations/096_request.sql` (new) | The `request` table: one row per buyer-listing access request/grant, its status machine, and the indexes/constraints that make the authorization lookup O(1) and the "one active request per pair" rule a database invariant rather than an application promise. |
| `docs/MIGRATIONS.md` (modify) | Claim 096 in the ledger, in the same commit as the migration file, per the ledger's own rule. |
| `app/disclosure/__init__.py` (new) | Empty; makes `app/disclosure` a package, matching `app/privacy/`, `app/census/`. |
| `app/disclosure/levels.py` (new) | The disclosure-level vocabulary: the six capability names, what `FULL_CONFIDENTIAL` covers, and the document-kind→capability mapping. Pure constants and pure functions, no I/O. |
| `app/disclosure/access.py` (new) | **The one authorization function.** Reads the `request` table and returns the capability set a buyer currently holds for a listing, or refuses to answer (fail closed) for every ambiguous input. No writes. |
| `app/disclosure/requests.py` (new) | The request lifecycle: create, list-mine, list-inbox, decide (approve/deny), revoke. All writes to the `request` table live here; routes are thin wrappers around this module. **Audit rows are written at the ROUTE, not here** (controller ruling, 2026-09-18): `app.auth.audit.write` takes the `request` object and reads the IP, user-agent and request id off it, and this module has no request — auditing here would silently drop the three fields a disclosure investigation most needs. Tasks 5 and 6's sections are correct; this cell said otherwise and was wrong. |
| `app/api/requests.py` (new) | Buyer-facing routes: `POST /api/requests`, `GET /api/requests/mine`, `GET /api/requests/{id}`. |
| `app/api/seller_requests.py` (new) | Seller-facing routes: `GET /api/seller/requests`, `POST /api/seller/requests/{id}/decide`, `POST /api/seller/requests/{id}/revoke`. |
| `app/privacy/delivery.py` (modify) | `buyer_variant` grows an `authorized: bool` parameter (Task 7) — stays a pure function. |
| `app/api/listings.py` (modify) | `_photo_urls`/`get_listing_photo` compute and pass `authorized` (Task 7); `serialise`/`list_listings`/`get_listing` compute and apply capabilities for name/location/revenue/documents (Tasks 8-9); `_SELECT` gains `documents_disclosed`. |
| `app/api/seller_listings.py` (modify) | `read_document`'s reserved buyer arm is completed (Task 9). |
| `app/auth/limits.py` (modify) | Two new rate-limit tuples, `ACCESS_REQUEST_CREATE` and `ACCESS_REQUEST_DECIDE`, in the existing `(limit, window_s)` shape. |
| `app/main.py` (modify) | Mounts the two new routers inside the existing `site_mode == "app"` block. |
| `scripts/verify-deploy.sh` (modify) | Two new probes (coming-soon 404, anonymous 401) for the two new routers, matching the existing per-router probe pattern (`:206-212`). |
| `tests/disclosure/__init__.py`, `tests/disclosure/test_levels.py`, `tests/disclosure/test_access.py`, `tests/disclosure/test_access_properties.py`, `tests/disclosure/test_requests.py` (new) | Unit and property tests for the two new pure/near-pure modules. |
| `tests/api/test_requests.py`, `tests/api/test_seller_requests.py` (new) | HTTP-level tests for the four new/decision routes. |
| `tests/api/test_disclosure_isolation.py` (new) | Task 11 (the critical two-buyer test), Task 12 (the full acceptance matrix), Task 13 (IDOR). Kept as one file because all three share the same fixtures (two buyers, one seller, one listing) and reviewing them together is exactly reviewing "does per-buyer disclosure hold." |
| `tests/privacy/test_delivery.py` (modify) | Extends the existing parametrized matrix with the new `authorized` dimension (Task 7). |
| `frontend/src/requests/buyer.ts`, `frontend/src/requests/seller.ts` (new) | Adapters, in `frontend/src/listings/seller.ts`'s idiom, translating real API rows into the shape the design's fixture code already reads. |
| `frontend/src/App.vue`, `frontend/src/main.ts` (modify) | Wire the two new adapters through as props, the same way `listings`/`market` adapters are wired today. |

---

## Task 1: The `request` table

**Files:**
- Create: `migrations/096_request.sql`
- Modify: `docs/MIGRATIONS.md`
- Create: `tests/disclosure/__init__.py`
- Test: `tests/disclosure/test_request_table.py`

**Interfaces:**
- Produces: table `request` with columns `id, listing_id, buyer_user_id, seller_user_id, message, status, requested_disclosure_level, approved_disclosure_level, requested_at, reviewed_at, reviewed_by, denial_reason, expires_at, created_at, updated_at`; unique index `request_one_active_per_buyer_listing_uq` on `(listing_id, buyer_user_id) WHERE status IN ('PENDING','APPROVED')`; indexes `request_seller_inbox_idx (seller_user_id, status, requested_at DESC)` and `request_buyer_mine_idx (buyer_user_id, requested_at DESC)`. Every later task's SQL is written against exactly this shape.

- [ ] **Step 1: Write the failing test**

```python
# tests/disclosure/test_request_table.py
"""The `request` table itself (directive 4, 18, 23): the columns, the status machine's CHECK
constraints, and the one-active-row-per-(listing, buyer) invariant the authorization lookup in
Task 3 depends on being true in the database, not merely in application code."""
from __future__ import annotations

from uuid import uuid4

import psycopg2
import pytest


def _account(conn, email: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO account (email, password_hash, state) VALUES (%s,'x','active') RETURNING id",
            (email,),
        )
        return str(cur.fetchone()[0])


def _listing(conn, seller_id: str | None) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, seller_id, status)"
            " VALUES (%s,'Test Practice','Austin','TX','Austin','Small animal','Austin, TX','seller',%s,'published')"
            " RETURNING id",
            (f"test-{uuid4().hex}", seller_id),
        )
        return str(cur.fetchone()[0])


def test_a_pending_request_can_be_inserted_with_only_the_required_fields(conn) -> None:
    seller = _account(conn, "seller@example.org")
    buyer = _account(conn, "buyer@example.org")
    listing = _listing(conn, seller)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO request (listing_id, buyer_user_id, seller_user_id) VALUES (%s,%s,%s) RETURNING status, requested_disclosure_level",
            (listing, buyer, seller),
        )
        status, level = cur.fetchone()
    assert (status, level) == ("PENDING", "FULL_CONFIDENTIAL")


def test_a_buyer_cannot_be_the_listing_s_own_seller(conn) -> None:
    seller = _account(conn, "seller2@example.org")
    listing = _listing(conn, seller)
    with pytest.raises(psycopg2.errors.CheckViolation):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO request (listing_id, buyer_user_id, seller_user_id) VALUES (%s,%s,%s)",
                (listing, seller, seller),
            )


def test_only_one_active_request_per_listing_and_buyer(conn) -> None:
    seller = _account(conn, "seller3@example.org")
    buyer = _account(conn, "buyer3@example.org")
    listing = _listing(conn, seller)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO request (listing_id, buyer_user_id, seller_user_id) VALUES (%s,%s,%s)", (listing, buyer, seller))
    with pytest.raises(psycopg2.errors.UniqueViolation):
        with conn.cursor() as cur:
            cur.execute("INSERT INTO request (listing_id, buyer_user_id, seller_user_id) VALUES (%s,%s,%s)", (listing, buyer, seller))


def test_a_second_request_is_allowed_once_the_first_is_denied(conn) -> None:
    seller = _account(conn, "seller4@example.org")
    buyer = _account(conn, "buyer4@example.org")
    reviewer = _account(conn, "staff4@example.org")
    listing = _listing(conn, seller)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO request (listing_id, buyer_user_id, seller_user_id) VALUES (%s,%s,%s) RETURNING id",
            (listing, buyer, seller),
        )
        first_id = cur.fetchone()[0]
        cur.execute(
            "UPDATE request SET status = 'DENIED', reviewed_at = now(), reviewed_by = %s WHERE id = %s",
            (reviewer, first_id),
        )
        # No UniqueViolation: a DENIED row is outside the partial index's WHERE clause.
        cur.execute("INSERT INTO request (listing_id, buyer_user_id, seller_user_id) VALUES (%s,%s,%s)", (listing, buyer, seller))


def test_status_is_restricted_to_the_four_named_values(conn) -> None:
    seller = _account(conn, "seller5@example.org")
    buyer = _account(conn, "buyer5@example.org")
    listing = _listing(conn, seller)
    with pytest.raises(psycopg2.errors.CheckViolation):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO request (listing_id, buyer_user_id, seller_user_id, status) VALUES (%s,%s,%s,'accepted')",
                (listing, buyer, seller),
            )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/disclosure/test_request_table.py -v`
Expected: every test fails with `psycopg2.errors.UndefinedTable: relation "request" does not exist` — the table has not been created yet.

- [ ] **Step 3: Write the migration**

```sql
-- migrations/096_request.sql
-- Per-buyer disclosure (spec 2026-09-18, directive §4, §16, §18): the buyer/listing
-- authorization relationship the wizard-step audit's finding 4 found missing entirely. Claims the
-- number and the name reserved for A43's unbuilt "Requests" family
-- (docs/superpowers/specs/2026-09-13-admin-control-surface-design.md §5); this table's shape is a
-- superset of that spec's draft (PENDING/APPROVED/DENIED/REVOKED rather than
-- pending/accepted/declined, and the disclosure-level columns directive §4/§16 require), so a
-- later A43 admin-tab build reads this table rather than a second, competing one.
--
-- `request_event` (also reserved by that spec) is deliberately NOT created here: every status
-- transition below already writes an `audit_log` row (target_type='request'; Tasks 5/6), and a
-- per-request history view can read that the way the admin Users/Listings "History" tabs already
-- do, rather than duplicating the trail in a second table nothing else would keep in sync.
CREATE TABLE request (
  id                        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_id                uuid        NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  buyer_user_id             uuid        NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  -- Denormalised from listing.seller_id at creation (directive §4 names it explicitly, and it is
  -- what makes the seller's inbox query -- Task 4's `list_inbox` -- an index-only lookup rather
  -- than a join on every read). This product has no listing-ownership-transfer feature, so there
  -- is no path by which this could drift from listing.seller_id after the row is written.
  seller_user_id            uuid        NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  message                   text,
  status                    text        NOT NULL DEFAULT 'PENDING'
                                        CHECK (status IN ('PENDING','APPROVED','DENIED','REVOKED')),
  requested_disclosure_level text       NOT NULL DEFAULT 'FULL_CONFIDENTIAL'
                                        CHECK (requested_disclosure_level IN
                                          ('IDENTITY','EXACT_LOCATION','UNREDACTED_IMAGES','FINANCIALS','FLOOR_PLANS','FULL_CONFIDENTIAL')),
  approved_disclosure_level text        CHECK (approved_disclosure_level IN
                                          ('IDENTITY','EXACT_LOCATION','UNREDACTED_IMAGES','FINANCIALS','FLOOR_PLANS','FULL_CONFIDENTIAL')),
  requested_at              timestamptz NOT NULL DEFAULT now(),
  reviewed_at               timestamptz,
  reviewed_by               uuid        REFERENCES account(id) ON DELETE SET NULL,
  denial_reason             text,
  -- Directive §4: "where applicable". Nothing in this plan writes it (no design surface asks a
  -- seller for an expiry); the authorization check in Task 3 honours it if a later feature does.
  expires_at                timestamptz,
  created_at                timestamptz NOT NULL DEFAULT now(),
  updated_at                timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT request_seller_is_not_buyer_ck CHECK (buyer_user_id <> seller_user_id),
  -- One-directional (not a bidirectional `=`): a REVOKED row keeps its approved_disclosure_level
  -- and its original reviewed_at/reviewed_by for history, so "has all three fields" must not imply
  -- "is APPROVED right now" or a revoked row would fail this the moment it is revoked.
  CONSTRAINT request_approved_needs_decision_ck CHECK (
    status <> 'APPROVED' OR (approved_disclosure_level IS NOT NULL AND reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)),
  CONSTRAINT request_denied_needs_review_ck CHECK (status <> 'DENIED' OR (reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)),
  CONSTRAINT request_pending_has_no_decision_ck CHECK (
    status <> 'PENDING' OR (reviewed_at IS NULL AND reviewed_by IS NULL AND approved_disclosure_level IS NULL))
);
-- Directive §23: the authorization check (Task 3) is one indexed lookup on exactly this key. The
-- partial WHERE is what makes "one active request per (listing, buyer)" a database invariant
-- rather than an application promise -- safe to add here because this is a brand-new table with no
-- existing rows, unlike `account`'s one-open-application invariant (CLAUDE.md's A36 note), which
-- could not add a partial unique index without first auditing every row already on QA/production.
CREATE UNIQUE INDEX request_one_active_per_buyer_listing_uq ON request (listing_id, buyer_user_id) WHERE status IN ('PENDING','APPROVED');
CREATE INDEX request_seller_inbox_idx ON request (seller_user_id, status, requested_at DESC);
CREATE INDEX request_buyer_mine_idx  ON request (buyer_user_id, requested_at DESC);
```

- [ ] **Step 4: Claim the migration number in the ledger**

Edit `docs/MIGRATIONS.md`'s row for `096` from `*(reserved — A43, the Requests build)*` to:

```
| 096 | `096_request.sql` | `docs/per-buyer-disclosure-plan` | the buyer/listing access-request table (supersedes A43's draft shape — see the migration's own header comment) |
```

Update "Next free" if this plan is executed after another branch has since claimed 097.

- [ ] **Step 5: Run the migration and the test**

Run: `poetry run python scripts/migrate.py && poetry run pytest tests/disclosure/test_request_table.py -v`
Expected: PASS, all five tests.

- [ ] **Step 6: Commit**

```bash
git add migrations/096_request.sql docs/MIGRATIONS.md tests/disclosure/__init__.py tests/disclosure/test_request_table.py
git commit -m "feat(disclosure): the request table — one row per buyer/listing access request"
```

---

## Task 2: The disclosure-level vocabulary

**Files:**
- Create: `app/disclosure/__init__.py`
- Create: `app/disclosure/levels.py`
- Test: `tests/disclosure/test_levels.py`

**Interfaces:**
- Consumes: nothing (pure module, no DB, no imports from this plan's other files).
- Produces: `CAPABILITIES: frozenset[str]`, `REQUESTABLE_LEVELS: frozenset[str]`, `covers(level: str | None) -> frozenset[str]`, `capability_for_document_kind(kind: str) -> str`. Task 3 imports `covers`; Tasks 5/6 import `REQUESTABLE_LEVELS`; Task 9 imports `capability_for_document_kind`.

- [ ] **Step 1: Write the failing test**

```python
# tests/disclosure/test_levels.py
"""The disclosure-level vocabulary (directive §16): six named capabilities, what
FULL_CONFIDENTIAL covers, and which capability an uploaded document's `kind` requires."""
from __future__ import annotations

from app.disclosure import levels


def test_the_five_specific_capabilities_are_each_self_covering() -> None:
    for capability in ("IDENTITY", "EXACT_LOCATION", "UNREDACTED_IMAGES", "FINANCIALS", "FLOOR_PLANS"):
        assert levels.covers(capability) == frozenset({capability})


def test_full_confidential_covers_every_specific_capability() -> None:
    assert levels.covers("FULL_CONFIDENTIAL") == levels.CAPABILITIES


def test_no_level_and_an_unknown_level_cover_nothing() -> None:
    assert levels.covers(None) == frozenset()
    assert levels.covers("NOT_A_LEVEL") == frozenset()


def test_requestable_levels_is_the_five_capabilities_plus_full_confidential() -> None:
    assert levels.REQUESTABLE_LEVELS == levels.CAPABILITIES | frozenset({"FULL_CONFIDENTIAL"})
    assert "PUBLIC" not in levels.REQUESTABLE_LEVELS  # nothing is ever requested/granted FOR the public tier — it needs no grant


def test_document_kind_maps_to_its_own_capability() -> None:
    assert levels.capability_for_document_kind("floor_plan") == "FLOOR_PLANS"
    assert levels.capability_for_document_kind("financials") == "FINANCIALS"


def test_an_undifferentiated_document_kind_requires_the_broadest_grant() -> None:
    # directive §19, applied to the one case the product cannot yet classify (D18 — no kind
    # picker exists, so every wizard upload is 'other' today).
    assert levels.capability_for_document_kind("equipment") == "FULL_CONFIDENTIAL"
    assert levels.capability_for_document_kind("other") == "FULL_CONFIDENTIAL"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/disclosure/test_levels.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.disclosure'`.

- [ ] **Step 3: Write the minimal implementation**

```python
# app/disclosure/__init__.py
```

```python
# app/disclosure/levels.py
"""The disclosure-level vocabulary (directive §16): explicit named permissions rather than one
giant boolean, reusing this product's own document-kind vocabulary (`migrations/031_listing_asset.sql`)
where it already has an equivalent. Pure constants and pure functions -- no I/O, no imports from
elsewhere in this plan, so this module is safe for every other one to depend on."""
from __future__ import annotations

CAPABILITIES: frozenset[str] = frozenset({"IDENTITY", "EXACT_LOCATION", "UNREDACTED_IMAGES", "FINANCIALS", "FLOOR_PLANS"})

# What `request.approved_disclosure_level`/`requested_disclosure_level` may hold (migration 096's
# own CHECK, restated here so Python and the database cannot silently drift apart -- Task 5/6's
# routes validate an incoming level against this set before it ever reaches SQL).
REQUESTABLE_LEVELS: frozenset[str] = CAPABILITIES | frozenset({"FULL_CONFIDENTIAL"})

_COVERAGE: dict[str, frozenset[str]] = {capability: frozenset({capability}) for capability in CAPABILITIES}
_COVERAGE["FULL_CONFIDENTIAL"] = CAPABILITIES


def covers(level: str | None) -> frozenset[str]:
    """Every capability an approved grant of `level` includes. `frozenset()` for `None` (no grant
    at all) and for anything not in `REQUESTABLE_LEVELS` -- fail closed on an unrecognised value
    rather than raising, because this is read on the hot authorization path and an unrecognised
    level (a future migration adding one Python does not know about yet) must deny, not 500."""
    return _COVERAGE.get(level or "", frozenset())


# D18: the approved wizard step 6 has no document-kind picker, so every upload today is 'other'.
# The two kinds a seller CAN already send (the API accepts them; nothing sends them yet) map to
# their own capability; anything else -- 'equipment', 'other', and any kind added later that this
# table has not been taught -- requires the broadest grant, which is the fail-closed reading of an
# undifferentiated document (directive §19).
_DOCUMENT_CAPABILITY: dict[str, str] = {"floor_plan": "FLOOR_PLANS", "financials": "FINANCIALS"}
DEFAULT_DOCUMENT_CAPABILITY = "FULL_CONFIDENTIAL"


def capability_for_document_kind(kind: str) -> str:
    return _DOCUMENT_CAPABILITY.get(kind, DEFAULT_DOCUMENT_CAPABILITY)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/disclosure/test_levels.py -v`
Expected: PASS, all six tests.

- [ ] **Step 5: Commit**

```bash
git add app/disclosure/__init__.py app/disclosure/levels.py tests/disclosure/test_levels.py
git commit -m "feat(disclosure): the six-capability disclosure-level vocabulary"
```

---

## Task 3: The authorization boundary — `app/disclosure/access.py`

This is the security boundary. Every later task that serves a confidential value calls into this module and nothing else; Task 10's property test is the proof that it fails closed on every input, not just the three or four examples below.

**Files:**
- Create: `app/disclosure/access.py`
- Test: `tests/disclosure/test_access.py`

**Interfaces:**
- Consumes: `app.disclosure.levels.covers`.
- Produces:
  - `authorized_capabilities(conn: Any, *, listing_id: str, seller_id: str | None, buyer_account_id: str | None) -> frozenset[str]`
  - `has_capability(conn: Any, *, listing_id: str, seller_id: str | None, buyer_account_id: str | None, capability: str) -> bool`
  - `authorized_capabilities_bulk(conn: Any, *, buyer_account_id: str | None, listings: Sequence[tuple[str, str | None]]) -> dict[str, frozenset[str]]` — keyed by `listing_id`.

  Tasks 7, 8, 9 call `has_capability`; Task 8's list route calls `authorized_capabilities_bulk`. No later task queries the `request` table directly.

- [ ] **Step 1: Write the failing test**

```python
# tests/disclosure/test_access.py
"""The one function every confidential-resource route calls (directive §12, §18). Deliberately
does NOT fold in the pre-existing global ceiling flags (location_disclosed, etc.) -- those stay
exactly where they already are, in `serialise`/`buyer_variant`/`read_document`, ANDed with this
function's answer at the call site (directive §8: "separate these concepts"). What this function
owns is the buyer/listing grant, and only that."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.disclosure.access import authorized_capabilities, authorized_capabilities_bulk, has_capability


def _account(conn, email: str) -> str:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,'x','active') RETURNING id", (email,))
        return str(cur.fetchone()[0])


def _listing(conn, seller_id: str | None) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, seller_id, status)"
            " VALUES (%s,'Test Practice','Austin','TX','Austin','Small animal','Austin, TX','seller',%s,'published') RETURNING id",
            (f"test-{uuid4().hex}", seller_id),
        )
        return str(cur.fetchone()[0])


def _request(conn, listing_id, buyer_id, seller_id, *, status="PENDING", level=None, expires_at=None):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO request (listing_id, buyer_user_id, seller_user_id, status, approved_disclosure_level,"
            " reviewed_at, reviewed_by, expires_at)"
            " VALUES (%s,%s,%s,%s,%s, CASE WHEN %s <> 'PENDING' THEN now() END, CASE WHEN %s <> 'PENDING' THEN %s END, %s)",
            (listing_id, buyer_id, seller_id, status, level, status, status, seller_id, expires_at),
        )


def test_no_request_at_all_grants_nothing(conn) -> None:
    seller, buyer = _account(conn, "s1@x.org"), _account(conn, "b1@x.org")
    listing = _listing(conn, seller)
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset()


def test_a_pending_request_grants_nothing(conn) -> None:
    seller, buyer = _account(conn, "s2@x.org"), _account(conn, "b2@x.org")
    listing = _listing(conn, seller)
    _request(conn, listing, buyer, seller, status="PENDING")
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset()


def test_an_approved_request_grants_exactly_what_it_covers(conn) -> None:
    seller, buyer = _account(conn, "s3@x.org"), _account(conn, "b3@x.org")
    listing = _listing(conn, seller)
    _request(conn, listing, buyer, seller, status="APPROVED", level="EXACT_LOCATION")
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset({"EXACT_LOCATION"})
    assert has_capability(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer, capability="EXACT_LOCATION")
    assert not has_capability(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer, capability="FINANCIALS")


def test_full_confidential_grants_every_capability(conn) -> None:
    seller, buyer = _account(conn, "s4@x.org"), _account(conn, "b4@x.org")
    listing = _listing(conn, seller)
    _request(conn, listing, buyer, seller, status="APPROVED", level="FULL_CONFIDENTIAL")
    from app.disclosure.levels import CAPABILITIES
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == CAPABILITIES


def test_a_denied_request_grants_nothing(conn) -> None:
    seller, buyer = _account(conn, "s5@x.org"), _account(conn, "b5@x.org")
    listing = _listing(conn, seller)
    _request(conn, listing, buyer, seller, status="DENIED")
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset()


def test_a_revoked_request_grants_nothing_even_though_the_level_column_is_still_set(conn) -> None:
    seller, buyer = _account(conn, "s6@x.org"), _account(conn, "b6@x.org")
    listing = _listing(conn, seller)
    _request(conn, listing, buyer, seller, status="REVOKED", level="FULL_CONFIDENTIAL")
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset()


def test_an_expired_approval_grants_nothing(conn) -> None:
    seller, buyer = _account(conn, "s7@x.org"), _account(conn, "b7@x.org")
    listing = _listing(conn, seller)
    _request(conn, listing, buyer, seller, status="APPROVED", level="FULL_CONFIDENTIAL", expires_at="2000-01-01T00:00:00Z")
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset()


def test_no_buyer_at_all_grants_nothing(conn) -> None:
    seller = _account(conn, "s8@x.org")
    listing = _listing(conn, seller)
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=None) == frozenset()


def test_a_grant_on_one_listing_does_not_leak_to_another(conn) -> None:
    seller, buyer = _account(conn, "s9@x.org"), _account(conn, "b9@x.org")
    listing_x, listing_y = _listing(conn, seller), _listing(conn, seller)
    _request(conn, listing_x, buyer, seller, status="APPROVED", level="FULL_CONFIDENTIAL")
    assert authorized_capabilities(conn, listing_id=listing_y, seller_id=seller, buyer_account_id=buyer) == frozenset()


def test_bulk_matches_the_single_lookup_for_every_listing_in_one_extra_query(conn) -> None:
    seller, buyer = _account(conn, "s10@x.org"), _account(conn, "b10@x.org")
    listing_x, listing_y = _listing(conn, seller), _listing(conn, seller)
    _request(conn, listing_x, buyer, seller, status="APPROVED", level="IDENTITY")
    result = authorized_capabilities_bulk(conn, buyer_account_id=buyer, listings=[(listing_x, seller), (listing_y, seller)])
    assert result[listing_x] == frozenset({"IDENTITY"})
    assert result[listing_y] == frozenset()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/disclosure/test_access.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.disclosure.access'`.

- [ ] **Step 3: Write the minimal implementation**

```python
# app/disclosure/access.py
"""The one function every confidential-resource route calls (directive §12, §18, §19).

Reads ONLY the `request` table's current, active grant for a (listing, buyer) pair. Deliberately
does not know about `location_disclosed`, `identifiable_content_visibility` or any other ceiling
flag -- those are a SEPARATE, pre-existing concern (directive §8) checked at each call site beside
this function's answer, never inside it, so the two questions ("did the seller ever permit this at
all" and "did the seller approve THIS buyer") cannot be quietly merged back into one boolean by a
future edit that does not know they must stay apart.

Fails closed (directive §19): every branch below that cannot prove a specific capability is
authorized returns/omits it. There is no "assume yes" branch anywhere in this file."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.disclosure.levels import covers

_ACTIVE_GRANT_SQL = (
    "SELECT approved_disclosure_level FROM request"
    " WHERE listing_id = %s AND buyer_user_id = %s AND status = 'APPROVED'"
    "   AND (expires_at IS NULL OR expires_at > now())"
)


def authorized_capabilities(conn: Any, *, listing_id: str, seller_id: str | None, buyer_account_id: str | None) -> frozenset[str]:
    """Every capability `buyer_account_id` currently holds for `listing_id` — the ceiling flags are
    NOT applied here (see module docstring); this is the grant alone."""
    if buyer_account_id is None or (seller_id is not None and str(buyer_account_id) == str(seller_id)):
        return frozenset()
    with conn.cursor() as cur:
        cur.execute(_ACTIVE_GRANT_SQL, (listing_id, buyer_account_id))
        row = cur.fetchone()
    return covers(row[0]) if row is not None else frozenset()


def has_capability(conn: Any, *, listing_id: str, seller_id: str | None, buyer_account_id: str | None, capability: str) -> bool:
    return capability in authorized_capabilities(conn, listing_id=listing_id, seller_id=seller_id, buyer_account_id=buyer_account_id)


def authorized_capabilities_bulk(
    conn: Any, *, buyer_account_id: str | None, listings: Sequence[tuple[str, str | None]]
) -> dict[str, frozenset[str]]:
    """`authorized_capabilities` for many listings in ONE extra query (directive §23) — the shape
    the paginated list route (Task 8) needs. `listings` is `(listing_id, seller_id)` pairs; the
    result is keyed by `listing_id` (str) and always has one entry per input pair, `frozenset()`
    for every listing with no active grant."""
    result: dict[str, frozenset[str]] = {listing_id: frozenset() for listing_id, _seller_id in listings}
    if buyer_account_id is None or not listings:
        return result
    ids = [listing_id for listing_id, seller_id in listings if seller_id is None or str(seller_id) != str(buyer_account_id)]
    if not ids:
        return result
    with conn.cursor() as cur:
        cur.execute(
            "SELECT listing_id, approved_disclosure_level FROM request"
            " WHERE listing_id = ANY(%s) AND buyer_user_id = %s AND status = 'APPROVED'"
            "   AND (expires_at IS NULL OR expires_at > now())",
            (ids, buyer_account_id),
        )
        for listing_id, level in cur.fetchall():
            result[str(listing_id)] = covers(level)
    return result
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/disclosure/test_access.py -v`
Expected: PASS, all ten tests.

- [ ] **Step 5: Commit**

```bash
git add app/disclosure/access.py tests/disclosure/test_access.py
git commit -m "feat(disclosure): authorized_capabilities — the one buyer/listing grant lookup"
```

---

## Task 4: The request lifecycle — `app/disclosure/requests.py`

**Files:**
- Create: `app/disclosure/requests.py`
- Test: `tests/disclosure/test_requests.py`

**Interfaces:**
- Consumes: `app.disclosure.levels.REQUESTABLE_LEVELS`; `app.api.listings.Refusal`-shaped exception (see Step 3 — this module raises the SAME `Refusal` class `app/api/seller_listings.py` already defines and imports, so every route's existing `_refused` handler renders it with no new code).
- Produces:
  - `create(conn: Any, *, listing_id: str, buyer_account_id: str, message: str | None, requested_disclosure_level: str = "FULL_CONFIDENTIAL") -> dict[str, Any]`
  - `get_one(conn: Any, *, request_id: str, buyer_account_id: str) -> dict[str, Any]`
  - `list_mine(conn: Any, *, buyer_account_id: str) -> list[dict[str, Any]]`
  - `list_inbox(conn: Any, *, seller_account_id: str) -> list[dict[str, Any]]`
  - `decide(conn: Any, *, request_id: str, seller_account_id: str, action: str, disclosure_level: str | None, reason: str | None) -> dict[str, Any]`
  - `revoke(conn: Any, *, request_id: str, seller_account_id: str) -> dict[str, Any]`

  Every dict has the same shape: `{id, listing_id, buyer_user_id, seller_user_id, message, status, requested_disclosure_level, approved_disclosure_level, requested_at, reviewed_at, reviewed_by, denial_reason, expires_at}`. Tasks 5 and 6's routes call these and JSON-serialise the result directly.

- [ ] **Step 1: Write the failing test**

```python
# tests/disclosure/test_requests.py
"""The request lifecycle (directive §5, §6, §15, §18). One test per transition and per refusal —
every refusal is a `Refusal`, so a route can catch it exactly as every other route in this
codebase already catches one."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.api.listings import Refusal
from app.disclosure import requests as req


def _account(conn, email: str, state: str = "active") -> str:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,'x',%s) RETURNING id", (email, state))
        return str(cur.fetchone()[0])


def _listing(conn, seller_id: str | None, status: str = "published") -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, seller_id, status)"
            " VALUES (%s,'Test Practice','Austin','TX','Austin','Small animal','Austin, TX','seller',%s,%s) RETURNING id",
            (f"test-{uuid4().hex}", seller_id, status),
        )
        return str(cur.fetchone()[0])


def test_create_defaults_to_a_pending_full_confidential_request(conn) -> None:
    seller, buyer = _account(conn, "s1@x.org"), _account(conn, "b1@x.org")
    listing = _listing(conn, seller)
    row = req.create(conn, listing_id=listing, buyer_account_id=buyer, message="Tell me more")
    assert row["status"] == "PENDING" and row["requested_disclosure_level"] == "FULL_CONFIDENTIAL" and row["seller_user_id"] == seller


def test_create_refuses_a_listing_with_no_seller(conn) -> None:
    listing = _listing(conn, None)  # a seed listing
    buyer = _account(conn, "b2@x.org")
    with pytest.raises(Refusal) as exc:
        req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    assert exc.value.code == "NO_SELLER"


def test_create_refuses_a_seller_requesting_their_own_listing(conn) -> None:
    seller = _account(conn, "s3@x.org")
    listing = _listing(conn, seller)
    with pytest.raises(Refusal) as exc:
        req.create(conn, listing_id=listing, buyer_account_id=seller, message=None)
    assert exc.value.code == "SELF_REQUEST"


def test_create_refuses_an_unpublished_listing(conn) -> None:
    seller, buyer = _account(conn, "s4@x.org"), _account(conn, "b4@x.org")
    listing = _listing(conn, seller, status="draft")
    with pytest.raises(Refusal) as exc:
        req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    assert exc.value.code == "NOT_FOUND"


def test_create_refuses_a_second_pending_request_for_the_same_pair(conn) -> None:
    seller, buyer = _account(conn, "s5@x.org"), _account(conn, "b5@x.org")
    listing = _listing(conn, seller)
    req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    with pytest.raises(Refusal) as exc:
        req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    assert exc.value.code == "ALREADY_REQUESTED"


def test_create_refuses_an_unrecognised_disclosure_level(conn) -> None:
    seller, buyer = _account(conn, "s6@x.org"), _account(conn, "b6@x.org")
    listing = _listing(conn, seller)
    with pytest.raises(Refusal) as exc:
        req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None, requested_disclosure_level="EVERYTHING")
    assert exc.value.code == "BAD_LEVEL"


def test_list_mine_is_scoped_to_the_calling_buyer(conn) -> None:
    seller = _account(conn, "s7@x.org")
    buyer_a, buyer_b = _account(conn, "ba7@x.org"), _account(conn, "bb7@x.org")
    listing = _listing(conn, seller)
    req.create(conn, listing_id=listing, buyer_account_id=buyer_a, message=None)
    assert len(req.list_mine(conn, buyer_account_id=buyer_a)) == 1
    assert req.list_mine(conn, buyer_account_id=buyer_b) == []


def test_list_inbox_is_scoped_to_the_calling_seller(conn) -> None:
    seller_a, seller_b = _account(conn, "sa8@x.org"), _account(conn, "sb8@x.org")
    buyer = _account(conn, "b8@x.org")
    listing = _listing(conn, seller_a)
    req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    assert len(req.list_inbox(conn, seller_account_id=seller_a)) == 1
    assert req.list_inbox(conn, seller_account_id=seller_b) == []


def test_decide_approve_defaults_the_level_to_what_was_requested(conn) -> None:
    seller, buyer = _account(conn, "s9@x.org"), _account(conn, "b9@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None, requested_disclosure_level="IDENTITY")
    decided = req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    assert decided["status"] == "APPROVED" and decided["approved_disclosure_level"] == "IDENTITY" and decided["reviewed_by"] == seller


def test_decide_deny_records_the_reason(conn) -> None:
    seller, buyer = _account(conn, "s10@x.org"), _account(conn, "b10@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    decided = req.decide(conn, request_id=created["id"], seller_account_id=seller, action="deny", disclosure_level=None, reason="Not a good fit")
    assert decided["status"] == "DENIED" and decided["denial_reason"] == "Not a good fit"


def test_decide_refuses_a_request_belonging_to_a_different_seller(conn) -> None:
    seller, other_seller, buyer = _account(conn, "s11@x.org"), _account(conn, "o11@x.org"), _account(conn, "b11@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    with pytest.raises(Refusal) as exc:
        req.decide(conn, request_id=created["id"], seller_account_id=other_seller, action="approve", disclosure_level=None, reason=None)
    assert exc.value.status == 404  # a request that is not yours should not be confirmed to exist


def test_decide_refuses_a_request_that_is_not_pending(conn) -> None:
    seller, buyer = _account(conn, "s12@x.org"), _account(conn, "b12@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    with pytest.raises(Refusal) as exc:
        req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    assert exc.value.code == "STATE"


def test_revoke_turns_an_approved_request_into_revoked(conn) -> None:
    seller, buyer = _account(conn, "s13@x.org"), _account(conn, "b13@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    revoked = req.revoke(conn, request_id=created["id"], seller_account_id=seller)
    assert revoked["status"] == "REVOKED"


def test_revoke_refuses_a_request_that_was_never_approved(conn) -> None:
    seller, buyer = _account(conn, "s14@x.org"), _account(conn, "b14@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    with pytest.raises(Refusal) as exc:
        req.revoke(conn, request_id=created["id"], seller_account_id=seller)
    assert exc.value.code == "STATE"


def test_a_buyer_may_re_request_after_a_denial(conn) -> None:
    seller, buyer = _account(conn, "s15@x.org"), _account(conn, "b15@x.org")
    listing = _listing(conn, seller)
    first = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=first["id"], seller_account_id=seller, action="deny", disclosure_level=None, reason=None)
    second = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    assert second["id"] != first["id"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/disclosure/test_requests.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.disclosure.requests'`.

- [ ] **Step 3: Write the minimal implementation**

```python
# app/disclosure/requests.py
"""The request lifecycle: create, list, decide, revoke (directive §5, §6, §15). Every write here
goes through exactly one of these six functions; the two route files (Tasks 5, 6) are thin HTTP
wrappers that resolve a Principal, call one of these, and render the result or the Refusal it
raised. Reuses `app.api.listings.Refusal` rather than declaring a second exception type, so every
route's EXISTING `_refused`/`_error` rendering already knows how to answer one (Global Constraint:
no inline HTTPException)."""
from __future__ import annotations

from typing import Any

from app.api.listings import Refusal
from app.disclosure.levels import REQUESTABLE_LEVELS

_COLUMNS = (
    "id, listing_id, buyer_user_id, seller_user_id, message, status, requested_disclosure_level,"
    " approved_disclosure_level, requested_at, reviewed_at, reviewed_by, denial_reason, expires_at"
)


def _row(cur) -> dict[str, Any]:
    names = [d[0] for d in cur.description]
    values = cur.fetchone()
    return {name: (str(value) if name.endswith("_id") or name == "id" else value) for name, value in zip(names, values, strict=True)}


def create(conn: Any, *, listing_id: str, buyer_account_id: str, message: str | None,
          requested_disclosure_level: str = "FULL_CONFIDENTIAL") -> dict[str, Any]:
    if requested_disclosure_level not in REQUESTABLE_LEVELS:
        raise Refusal("BAD_LEVEL", f"disclosure_level must be one of {', '.join(sorted(REQUESTABLE_LEVELS))}.", 400)
    with conn.cursor() as cur:
        cur.execute("SELECT seller_id FROM listing WHERE id = %s AND status = 'published'", (listing_id,))
        found = cur.fetchone()
        if found is None:
            raise Refusal("NOT_FOUND", "No such listing.", 404)
        seller_id = found[0]
        if seller_id is None:
            raise Refusal("NO_SELLER", "This listing has no seller account to request access from.", 422)
        if str(seller_id) == str(buyer_account_id):
            raise Refusal("SELF_REQUEST", "You cannot request access to your own listing.", 422)
        try:
            cur.execute(
                f"INSERT INTO request (listing_id, buyer_user_id, seller_user_id, message, requested_disclosure_level)"
                f" VALUES (%s,%s,%s,%s,%s) RETURNING {_COLUMNS}",
                (listing_id, buyer_account_id, seller_id, message, requested_disclosure_level),
            )
        except Exception as exc:  # psycopg2.errors.UniqueViolation — the partial index (migration 096)
            if type(exc).__name__ == "UniqueViolation":
                raise Refusal("ALREADY_REQUESTED", "You already have a pending or approved request for this listing.", 409) from exc
            raise
        return _row(cur)


def get_one(conn: Any, *, request_id: str, buyer_account_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM request WHERE id = %s AND buyer_user_id = %s", (request_id, buyer_account_id))
        if cur.fetchone() is None:
            raise Refusal("NOT_FOUND", "No such request.", 404)
        cur.execute(f"SELECT {_COLUMNS} FROM request WHERE id = %s AND buyer_user_id = %s", (request_id, buyer_account_id))
        return _row(cur)


def list_mine(conn: Any, *, buyer_account_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM request WHERE buyer_user_id = %s ORDER BY requested_at DESC", (buyer_account_id,))
        names = [d[0] for d in cur.description]
        return [{name: (str(value) if name.endswith("_id") or name == "id" else value) for name, value in zip(names, row, strict=True)}
                for row in cur.fetchall()]


def list_inbox(conn: Any, *, seller_account_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM request WHERE seller_user_id = %s ORDER BY requested_at DESC", (seller_account_id,))
        names = [d[0] for d in cur.description]
        return [{name: (str(value) if name.endswith("_id") or name == "id" else value) for name, value in zip(names, row, strict=True)}
                for row in cur.fetchall()]


def _owned_pending_or_approved(conn: Any, *, request_id: str, seller_account_id: str, required_status: str) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM request WHERE id = %s AND seller_user_id = %s", (request_id, seller_account_id))
        found = cur.fetchone()
    if found is None:
        raise Refusal("NOT_FOUND", "No such request.", 404)  # seller_listings.py:18's rule: not yours, not found
    if found[0] != required_status:
        raise Refusal("STATE", f"This request is {found[0].lower()}, not {required_status.lower()}.", 409)


def decide(conn: Any, *, request_id: str, seller_account_id: str, action: str,
          disclosure_level: str | None, reason: str | None) -> dict[str, Any]:
    _owned_pending_or_approved(conn, request_id=request_id, seller_account_id=seller_account_id, required_status="PENDING")
    with conn.cursor() as cur:
        if action == "approve":
            cur.execute("SELECT requested_disclosure_level FROM request WHERE id = %s", (request_id,))
            level = disclosure_level or cur.fetchone()[0]
            if level not in REQUESTABLE_LEVELS:
                raise Refusal("BAD_LEVEL", f"disclosure_level must be one of {', '.join(sorted(REQUESTABLE_LEVELS))}.", 400)
            cur.execute(
                f"UPDATE request SET status = 'APPROVED', approved_disclosure_level = %s, reviewed_at = now(),"
                f" reviewed_by = %s, updated_at = now() WHERE id = %s RETURNING {_COLUMNS}",
                (level, seller_account_id, request_id),
            )
        elif action == "deny":
            cur.execute(
                f"UPDATE request SET status = 'DENIED', denial_reason = %s, reviewed_at = now(),"
                f" reviewed_by = %s, updated_at = now() WHERE id = %s RETURNING {_COLUMNS}",
                (reason, seller_account_id, request_id),
            )
        else:
            raise Refusal("BAD_ACTION", "action must be 'approve' or 'deny'.", 400)
        return _row(cur)


def revoke(conn: Any, *, request_id: str, seller_account_id: str) -> dict[str, Any]:
    _owned_pending_or_approved(conn, request_id=request_id, seller_account_id=seller_account_id, required_status="APPROVED")
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE request SET status = 'REVOKED', updated_at = now() WHERE id = %s RETURNING {_COLUMNS}",
            (request_id,),
        )
        return _row(cur)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/disclosure/test_requests.py -v`
Expected: PASS, all fifteen tests. (If `UniqueViolation` catching fails to trigger, confirm `import psycopg2.errors` is not required — the `type(exc).__name__` check is deliberate so this module does not need a psycopg2 import solely for one `except` clause; if this proves fragile in review, replace with `except psycopg2.errors.UniqueViolation` directly — either is acceptable, but pick one and do not leave both.)

- [ ] **Step 5: Commit**

```bash
git add app/disclosure/requests.py tests/disclosure/test_requests.py
git commit -m "feat(disclosure): the request lifecycle — create, list, decide, revoke"
```

---

## Task 5: Buyer routes — `app/api/requests.py`

**Files:**
- Create: `app/api/requests.py`
- Modify: `app/auth/limits.py`
- Modify: `app/main.py`
- Modify: `scripts/verify-deploy.sh`
- Test: `tests/api/test_requests.py`

**Interfaces:**
- Consumes: `app.disclosure.requests.{create, get_one, list_mine}`; `app.auth.deps.require`; `app.auth.audit.write`; `app.auth.limits.hit`; the `member`/`api_client`/`signed_in`/`audit_rows` fixtures from `tests/api/conftest.py`.
- Produces: `router` (an `APIRouter(prefix="/api")`), mounted as `requests_router` in `app/main.py`. Routes: `POST /api/requests`, `GET /api/requests/mine`, `GET /api/requests/{request_id}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_requests.py
"""POST /api/requests, GET /api/requests/mine, GET /api/requests/{id} (directive §6, §13)."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest


async def _seller_listing(conn, client, headers) -> str:
    """A published listing owned by whoever `headers` signs in as."""
    response = await client.post("/api/seller/listings", headers=headers)
    listing_id = response.json()["id"]
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status = 'published', name = 'Test Practice', city = 'Austin',"
                    " state = 'TX', zip = '78701', est = 2010, price = 1000000, sqft = 3000 WHERE id = %s", (listing_id,))
    return listing_id


@pytest.mark.asyncio
async def test_a_buyer_can_request_access(client, conn, member) -> None:
    from tests.api.conftest import auth_headers
    _sid, s_cookies, s_hdr = member(("seller",), email="seller1@example.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _seller_listing(conn, client, seller_headers)
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer1@example.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    response = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id, "message": "Tell me more"})
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "PENDING"


@pytest.mark.asyncio
async def test_a_buyer_cannot_request_access_to_their_own_listing(client, conn, member) -> None:
    from tests.api.conftest import auth_headers
    _sid, s_cookies, s_hdr = member(("seller",), email="seller2@example.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _seller_listing(conn, client, seller_headers)
    response = await client.post("/api/requests", headers=seller_headers, json={"listing_id": listing_id})
    assert response.status_code == 422 and response.json()["error"]["code"] == "SELF_REQUEST"


@pytest.mark.asyncio
async def test_a_second_request_while_one_is_pending_is_refused(client, conn, member) -> None:
    from tests.api.conftest import auth_headers
    _sid, s_cookies, s_hdr = member(("seller",), email="seller3@example.org")
    listing_id = await _seller_listing(conn, client, auth_headers(s_cookies, s_hdr))
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer3@example.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id})
    response = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id})
    assert response.status_code == 409 and response.json()["error"]["code"] == "ALREADY_REQUESTED"


@pytest.mark.asyncio
async def test_get_mine_only_shows_the_signed_in_buyer_s_own_requests(client, conn, member) -> None:
    from tests.api.conftest import auth_headers
    _sid, s_cookies, s_hdr = member(("seller",), email="seller4@example.org")
    listing_id = await _seller_listing(conn, client, auth_headers(s_cookies, s_hdr))
    _a, a_cookies, a_hdr = member(("buyer",), email="buyera4@example.org")
    _b, b_cookies, b_hdr = member(("buyer",), email="buyerb4@example.org")
    a_headers, b_headers = auth_headers(a_cookies, a_hdr), auth_headers(b_cookies, b_hdr)
    await client.post("/api/requests", headers=a_headers, json={"listing_id": listing_id})
    mine_a = await client.get("/api/requests/mine", headers=a_headers)
    mine_b = await client.get("/api/requests/mine", headers=b_headers)
    assert len(mine_a.json()) == 1 and mine_b.json() == []


@pytest.mark.asyncio
async def test_get_one_refuses_a_request_that_belongs_to_another_buyer(client, conn, member) -> None:
    from tests.api.conftest import auth_headers
    _sid, s_cookies, s_hdr = member(("seller",), email="seller5@example.org")
    listing_id = await _seller_listing(conn, client, auth_headers(s_cookies, s_hdr))
    _a, a_cookies, a_hdr = member(("buyer",), email="buyera5@example.org")
    _b, b_cookies, b_hdr = member(("buyer",), email="buyerb5@example.org")
    a_headers, b_headers = auth_headers(a_cookies, a_hdr), auth_headers(b_cookies, b_hdr)
    created = await client.post("/api/requests", headers=a_headers, json={"listing_id": listing_id})
    response = await client.get(f"/api/requests/{created.json()['id']}", headers=b_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_creating_a_request_writes_an_audit_row(client, conn, member, audit_rows) -> None:
    from tests.api.conftest import auth_headers
    _sid, s_cookies, s_hdr = member(("seller",), email="seller6@example.org")
    listing_id = await _seller_listing(conn, client, auth_headers(s_cookies, s_hdr))
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer6@example.org")
    await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr), json={"listing_id": listing_id})
    rows = [r for r in audit_rows() if r["action"] == "access.requested"]
    assert len(rows) == 1 and rows[0]["target_type"] == "request"


@pytest.mark.asyncio
async def test_an_unauthenticated_caller_is_refused(client) -> None:
    response = await client.post("/api/requests", json={"listing_id": str(uuid4())})
    assert response.status_code == 401
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/api/test_requests.py -v`
Expected: FAIL — every test either 404s (no such route) or errors, since `app/api/requests.py` does not exist and no router is mounted.

- [ ] **Step 3: Add the rate-limit tuples**

In `app/auth/limits.py`, beside the existing `LISTING_*` tuples:

```python
# Directive §6: a buyer contacting a seller is a meaningful, infrequent action — generous enough
# that a genuine buyer never notices it, tight enough that scripted spam against every listing in
# a market does. Matches LISTING_SUBMIT's rate exactly (one submission-weight action per window).
ACCESS_REQUEST_CREATE = (20, 3600)
# A seller deciding on many requests in one sitting should not be throttled — matches LISTING_PATCH.
ACCESS_REQUEST_DECIDE = (240, 3600)
```

- [ ] **Step 4: Write the route file**

```python
# app/api/requests.py
"""Buyer-facing access-request routes (directive §6, §13). Guarded by the existing `request.create`
/`request.read_own` permissions (`app/auth/permissions.py:22`); the buyer/listing-specific decision
(is this MY request) is enforced in `app.disclosure.requests`, the same split
`app/api/seller_listings.py:18` already uses for listing ownership."""
from __future__ import annotations

from contextlib import closing
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.listings import Refusal, _error
from app.auth import audit
from app.auth import sessions as S
from app.auth.deps import require
from app.auth.limits import ACCESS_REQUEST_CREATE, hit
from app.cache import sync_redis
from app.db import sync_conn
from app.disclosure import requests as req

router = APIRouter(prefix="/api")

REQUIRE_REQUEST_CREATE = require("request.create")
REQUIRE_REQUEST_READ_OWN = require("request.read_own")
Requester = Annotated[S.Principal, Depends(REQUIRE_REQUEST_CREATE)]
OwnRequestReader = Annotated[S.Principal, Depends(REQUIRE_REQUEST_READ_OWN)]


def _refused(exc: Refusal) -> JSONResponse:
    return _error(exc.code, exc.message, exc.status)


@router.post("/requests", status_code=201)
async def create_request(request: Request, principal: Requester) -> JSONResponse:
    hit(sync_redis(), "request:create", str(principal.account_id), *ACCESS_REQUEST_CREATE)
    body: dict[str, Any] = await request.json()
    listing_id = body.get("listing_id")
    if not listing_id:
        return _error("BAD_REQUEST", "listing_id is required.", 400)
    try:
        with closing(sync_conn()) as conn, conn:
            row = req.create(
                conn, listing_id=listing_id, buyer_account_id=str(principal.account_id),
                message=body.get("message"), requested_disclosure_level=body.get("disclosure_level", "FULL_CONFIDENTIAL"),
            )
            audit.write(conn, actor=principal, action="access.requested", target_type="request",
                       target_id=row["id"], after={"listing_id": listing_id, "level": row["requested_disclosure_level"]},
                       request=request)
    except Refusal as exc:
        return _refused(exc)
    return JSONResponse(row, status_code=201)


@router.get("/requests/mine")
async def list_my_requests(principal: OwnRequestReader) -> JSONResponse:
    with closing(sync_conn()) as conn, conn:
        return JSONResponse(req.list_mine(conn, buyer_account_id=str(principal.account_id)))


@router.get("/requests/{request_id}")
async def get_my_request(request_id: str, principal: OwnRequestReader) -> JSONResponse:
    try:
        with closing(sync_conn()) as conn, conn:
            return JSONResponse(req.get_one(conn, request_id=request_id, buyer_account_id=str(principal.account_id)))
    except Refusal as exc:
        return _refused(exc)
```

- [ ] **Step 5: Mount the router**

In `app/main.py`, add the import beside the other `app.api.*` imports:

```python
from app.api.requests import router as requests_router
```

and inside the `if settings.site_mode == "app":` block, beside `app.include_router(listings_router)`:

```python
        app.include_router(requests_router)
```

- [ ] **Step 6: Add the deploy probes**

In `scripts/verify-deploy.sh`, beside the existing `/api/listings`/`/api/seller/listings` probes (`:206-212`, coming-soon 404 block) add:

```bash
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$BASE/api/requests/mine")
  [[ "$code" == "404" ]] || { echo "FAIL: /api/requests/mine answered $code in coming-soon mode (expected 404 - the requests surface must not be mounted before launch)" >&2; exit 1; }
```

and beside the anonymous-401 block (`:223-224`):

```bash
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$BASE/api/requests/mine")
  [[ "$code" == "401" ]] || { echo "FAIL: /api/requests/mine answered $code to an anonymous caller (expected 401 - the requests surface must be guarded by request.read_own)" >&2; exit 1; }
```

- [ ] **Step 7: Run the tests**

Run: `poetry run pytest tests/api/test_requests.py -v && bash tests/scripts/test_verify_deploy_sh.sh`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/api/requests.py app/auth/limits.py app/main.py scripts/verify-deploy.sh tests/api/test_requests.py
git commit -m "feat(disclosure): buyer routes — POST /api/requests, GET /api/requests/mine and /{id}"
```

---

## Task 6: Seller routes — `app/api/seller_requests.py`

**Files:**
- Create: `app/api/seller_requests.py`
- Modify: `app/main.py`
- Modify: `scripts/verify-deploy.sh`
- Test: `tests/api/test_seller_requests.py`

**Interfaces:**
- Consumes: `app.disclosure.requests.{list_inbox, decide, revoke}`; `app.auth.limits.ACCESS_REQUEST_DECIDE`.
- Produces: `router` (`APIRouter(prefix="/api/seller")`), mounted as `seller_requests_router`. Routes: `GET /api/seller/requests`, `POST /api/seller/requests/{request_id}/decide`, `POST /api/seller/requests/{request_id}/revoke`.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_seller_requests.py
"""GET /api/seller/requests, POST .../decide, POST .../revoke (directive §5, §14, §15)."""
from __future__ import annotations

import pytest

from tests.api.conftest import auth_headers


async def _pair(conn, client, member, seller_email: str, buyer_email: str):
    _sid, s_cookies, s_hdr = member(("seller",), email=seller_email)
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing = await client.post("/api/seller/listings", headers=seller_headers)
    listing_id = listing.json()["id"]
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status = 'published' WHERE id = %s", (listing_id,))
    _bid, b_cookies, b_hdr = member(("buyer",), email=buyer_email)
    buyer_headers = auth_headers(b_cookies, b_hdr)
    created = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id})
    return seller_headers, buyer_headers, listing_id, created.json()["id"]


@pytest.mark.asyncio
async def test_a_seller_sees_requests_against_their_own_listings(client, conn, member) -> None:
    seller_headers, _buyer_headers, _listing_id, _request_id = await _pair(conn, client, member, "s1@x.org", "b1@x.org")
    response = await client.get("/api/seller/requests", headers=seller_headers)
    assert response.status_code == 200 and len(response.json()) == 1


@pytest.mark.asyncio
async def test_a_different_seller_does_not_see_it(client, conn, member) -> None:
    _seller_headers, _buyer_headers, _listing_id, _request_id = await _pair(conn, client, member, "s2@x.org", "b2@x.org")
    _oid, o_cookies, o_hdr = member(("seller",), email="other2@x.org")
    response = await client.get("/api/seller/requests", headers=auth_headers(o_cookies, o_hdr))
    assert response.json() == []


@pytest.mark.asyncio
async def test_approve_grants_the_requested_level_by_default(client, conn, member, audit_rows) -> None:
    seller_headers, _buyer_headers, _listing_id, request_id = await _pair(conn, client, member, "s3@x.org", "b3@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    assert response.status_code == 200 and response.json()["status"] == "APPROVED"
    assert any(r["action"] == "access.approved" for r in audit_rows())


@pytest.mark.asyncio
async def test_deny_is_final_until_a_new_request_is_made(client, conn, member) -> None:
    seller_headers, _buyer_headers, _listing_id, request_id = await _pair(conn, client, member, "s4@x.org", "b4@x.org")
    await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "deny", "reason": "no"})
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_a_different_seller_cannot_decide_on_it(client, conn, member) -> None:
    _seller_headers, _buyer_headers, _listing_id, request_id = await _pair(conn, client, member, "s5@x.org", "b5@x.org")
    _oid, o_cookies, o_hdr = member(("seller",), email="other5@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=auth_headers(o_cookies, o_hdr), json={"action": "approve"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_revoke_requires_a_prior_approval(client, conn, member) -> None:
    seller_headers, _buyer_headers, _listing_id, request_id = await _pair(conn, client, member, "s6@x.org", "b6@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/revoke", headers=seller_headers)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_revoke_after_approval_writes_an_audit_row(client, conn, member, audit_rows) -> None:
    seller_headers, _buyer_headers, _listing_id, request_id = await _pair(conn, client, member, "s7@x.org", "b7@x.org")
    await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    response = await client.post(f"/api/seller/requests/{request_id}/revoke", headers=seller_headers)
    assert response.status_code == 200 and response.json()["status"] == "REVOKED"
    assert any(r["action"] == "access.revoked" for r in audit_rows())


@pytest.mark.asyncio
async def test_a_buyer_role_alone_cannot_reach_the_inbox(client, member) -> None:
    _bid, b_cookies, b_hdr = member(("buyer",), email="b8@x.org")
    response = await client.get("/api/seller/requests", headers=auth_headers(b_cookies, b_hdr))
    assert response.status_code == 403
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/api/test_seller_requests.py -v`
Expected: FAIL — no such route.

- [ ] **Step 3: Write the route file**

```python
# app/api/seller_requests.py
"""Seller-facing access-request routes (directive §5, §13, §15). `request.answer_own` is
seller-only (`app/auth/permissions.py:24`); ownership of a SPECIFIC request is enforced inside
`app.disclosure.requests`, the seller_listings.py:18 split."""
from __future__ import annotations

from contextlib import closing
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.listings import Refusal, _error
from app.auth import audit
from app.auth import sessions as S
from app.auth.deps import require
from app.auth.limits import ACCESS_REQUEST_DECIDE, hit
from app.cache import sync_redis
from app.db import sync_conn
from app.disclosure import requests as req

router = APIRouter(prefix="/api/seller")

REQUIRE_REQUEST_ANSWER_OWN = require("request.answer_own")
Answerer = Annotated[S.Principal, Depends(REQUIRE_REQUEST_ANSWER_OWN)]


def _refused(exc: Refusal) -> JSONResponse:
    return _error(exc.code, exc.message, exc.status)


@router.get("/requests")
async def list_inbox(principal: Answerer) -> JSONResponse:
    with closing(sync_conn()) as conn, conn:
        return JSONResponse(req.list_inbox(conn, seller_account_id=str(principal.account_id)))


@router.post("/requests/{request_id}/decide")
async def decide_request(request_id: str, request: Request, principal: Answerer) -> JSONResponse:
    hit(sync_redis(), "request:decide", str(principal.account_id), *ACCESS_REQUEST_DECIDE)
    body: dict[str, Any] = await request.json()
    action = body.get("action")
    try:
        with closing(sync_conn()) as conn, conn:
            row = req.decide(
                conn, request_id=request_id, seller_account_id=str(principal.account_id), action=action,
                disclosure_level=body.get("disclosure_level"), reason=body.get("reason"),
            )
            audit.write(
                conn, actor=principal, action=f"access.{'approved' if action == 'approve' else 'denied'}",
                target_type="request", target_id=request_id,
                after={"status": row["status"], "level": row.get("approved_disclosure_level")}, request=request,
            )
    except Refusal as exc:
        return _refused(exc)
    return JSONResponse(row)


@router.post("/requests/{request_id}/revoke")
async def revoke_request(request_id: str, request: Request, principal: Answerer) -> JSONResponse:
    try:
        with closing(sync_conn()) as conn, conn:
            row = req.revoke(conn, request_id=request_id, seller_account_id=str(principal.account_id))
            audit.write(conn, actor=principal, action="access.revoked", target_type="request",
                       target_id=request_id, request=request)
    except Refusal as exc:
        return _refused(exc)
    return JSONResponse(row)
```

- [ ] **Step 4: Mount the router and add the deploy probes**

Same pattern as Task 5 Steps 5-6: import `from app.api.seller_requests import router as seller_requests_router` in `app/main.py`, mount it beside `seller_listings_router`, and add matching coming-soon-404 / anonymous-401 probes for `/api/seller/requests` in `scripts/verify-deploy.sh`.

- [ ] **Step 5: Run the tests**

Run: `poetry run pytest tests/api/test_seller_requests.py -v`
Expected: PASS, all eight tests.

- [ ] **Step 6: Commit**

```bash
git add app/api/seller_requests.py app/main.py scripts/verify-deploy.sh tests/api/test_seller_requests.py
git commit -m "feat(disclosure): seller routes — inbox, decide, revoke"
```

---

## Task 7: Image authorization — `buyer_variant` grows a buyer dimension

**Files:**
- Modify: `app/privacy/delivery.py`
- Modify: `app/api/listings.py` (`_photo_urls`, `get_listing_photo`)
- Modify: `tests/privacy/test_delivery.py`

**Interfaces:**
- Modifies: `buyer_variant(visibility: str, asset: PrivacyRow | None, entry: str, seed_sha: str | None = None, *, authorized: bool = False) -> Variant | None` — the new keyword-only parameter defaults to `False` so every existing caller that has not been updated yet still compiles (there are exactly two call sites in this codebase, both updated in this task) and so a future caller that forgets the parameter fails closed rather than open.
- Consumes: `app.disclosure.access.has_capability` (from `_photo_urls` and `get_listing_photo`, both in `app/api/listings.py`).

- [ ] **Step 1: Write the failing test**

```python
# Added to tests/privacy/test_delivery.py, beside the existing parametrized matrix
def test_show_without_authorization_falls_back_to_the_redacted_derivative_when_ready() -> None:
    row = _row("PUBLISHED", visible=True, redacted=True)
    got = buyer_variant("SHOW", row, str(row.asset_id), authorized=False)
    assert got == Variant(row.redacted_storage_key, "b" * 64, False)


def test_show_with_authorization_still_serves_the_display_variant() -> None:
    row = _row("PUBLISHED", visible=True, redacted=True)
    got = buyer_variant("SHOW", row, str(row.asset_id), authorized=True)
    assert got == Variant(row.display_storage_key, "d" * 64, False)


def test_not_show_never_serves_display_even_when_authorized() -> None:
    # directive §20: NOT_SHOW is the seller's own veto, and no buyer grant overrides it.
    row = _row("PUBLISHED", visible=True, redacted=True)
    got = buyer_variant("NOT_SHOW", row, str(row.asset_id), authorized=True)
    assert got == Variant(row.redacted_storage_key, "b" * 64, False)


def test_show_without_authorization_and_no_redacted_derivative_yet_is_a_404_not_a_fallback() -> None:
    # directive §19: never a fallback to something else.
    row = _row("PUBLISHED", visible=True, redacted=False)
    assert buyer_variant("SHOW", row, str(row.asset_id), authorized=False) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/privacy/test_delivery.py -k authoriz -v`
Expected: FAIL with `TypeError: buyer_variant() got an unexpected keyword argument 'authorized'`.

- [ ] **Step 3: Write the minimal implementation**

In `app/privacy/delivery.py`, replace `buyer_variant`'s signature and SHOW branch:

```python
def buyer_variant(visibility: str, asset: PrivacyRow | None, entry: str,
                  seed_sha: str | None = None, *, authorized: bool = False) -> Variant | None:
    """The one representation this caller may have, or None -- a 404 on the bytes route and a null
    slot in the JSON.

    `authorized` (directive §9, §20) is the caller's OWN pre-computed answer to "does this buyer
    hold the UNREDACTED_IMAGES capability for this listing" (`app.disclosure.access.has_capability`)
    -- this function stays pure and takes no connection, exactly as before; only the caller may ask
    the database anything. Defaults False (fail closed) so a caller that forgets the argument gets
    the redacted derivative, never the original.

    A seed entry is a PATH (it contains a "/") and has no asset row: it can only ever be served
    under SHOW, because no derivative of it exists to serve under NOT_SHOW (spec C.10). Seed
    entries are the 29 demo hospitals' own photographs, seeded by John, not a buyer's grant --
    `authorized` plays no role on this branch, matching every approved-state fixture's pixels."""
    if asset is None:
        if "/" in entry and visibility == "SHOW" and seed_sha is not None:
            return Variant(entry, seed_sha, True)
        return None
    if not asset.buyer_visible:
        return None
    if visibility == "SHOW" and authorized:
        if asset.processing_status in _SHOW_READY and asset.display_storage_key and asset.display_sha256:
            return Variant(asset.display_storage_key, asset.display_sha256)
        return None
    if asset.processing_status in _NOT_SHOW_READY and asset.redacted_storage_key and asset.redacted_sha256:
        return Variant(asset.redacted_storage_key, asset.redacted_sha256)
    return None
```

Note the restructure: NOT_SHOW's old branch and SHOW-without-authorization now converge on the SAME redacted-serving branch (both want "the redacted derivative if it is ready, else nothing"), which is what makes `test_not_show_never_serves_display_even_when_authorized` and the unauthorized-SHOW case share one code path rather than two copies of the same ready-check.

In `app/api/listings.py`:

```python
# _photo_urls gains a `authorized: bool` parameter, threaded from its one caller (Task 8's
# serialise, which computes it once per listing via has_capability/authorized_capabilities_bulk):
def _photo_urls(listing_id: str, photos: list[str | None], row: Mapping[str, Any], *, authorized: bool) -> list[str | None]:
    ...
    variant = buyer_variant(visibility, asset, entry, digests.get(entry), authorized=authorized)
    ...
```

```python
# get_listing_photo (the single-photo bytes route) resolves its OWN principal and asks the
# authorization module directly, since it is not called from serialise at all:
from app.disclosure.access import has_capability

@router.api_route("/listings/{listing_id}/photos/{n}", methods=["GET", "HEAD"])
async def get_listing_photo(listing_id: str, n: int, request: Request, principal: Reader) -> Response:
    with closing(sync_conn()) as conn, conn:
        found = _published_photos_and_visibility(conn, listing_id)  # extend this helper to also return seller_id
        if found is None:
            return _error("NOT_FOUND", "No such listing.", 404)
        photos, visibility, seller_id = found
        entry = photos[n - 1] if 1 <= n <= len(photos) else None
        if entry is None:
            return _error("NOT_FOUND", "No such photograph.", 404)
        authorized = has_capability(conn, listing_id=listing_id, seller_id=seller_id,
                                    buyer_account_id=str(principal.account_id), capability="UNREDACTED_IMAGES")
        variant = buyer_variant(visibility, _privacy_for(conn, listing_id, entry), entry,
                                seed_digests().get(entry), authorized=authorized)
        ...
```

Note `Reader` — this route changes from `dependencies=[Depends(REQUIRE_LISTING_READ)]` (discarding the principal) to capturing it as a parameter, exactly the change Task 8 makes to the other two routes; declare `Reader = Annotated[S.Principal, Depends(REQUIRE_LISTING_READ)]` once in `listings.py` in this task, ahead of Task 8, since this is the first of the three routes in that file to need it, and `app/api/seller_listings.py` already imports and re-defines its own copy from the SAME `REQUIRE_LISTING_READ` guard object — this task's `Reader` in `listings.py` and that one are two names for a `Depends` wrapping the identical guard, which is what keeps `deps.permission_of` resolving both to one permission.

- [ ] **Step 4: Run the tests**

Run: `poetry run pytest tests/privacy/test_delivery.py -v`
Expected: PASS — the original 176-cell matrix plus the four new tests, all 180 green.

- [ ] **Step 5: Commit**

```bash
git add app/privacy/delivery.py app/api/listings.py tests/privacy/test_delivery.py
git commit -m "feat(disclosure): buyer_variant grows an authorized dimension for unredacted images"
```

---

## Task 8: Listing-detail authorization — name, exact location, revenue

**Files:**
- Modify: `app/api/listings.py` (`serialise`, `list_listings`, `get_listing`, `_SELECT`)
- Test: `tests/api/test_listings_disclosure.py` (new)

**Interfaces:**
- Modifies: `serialise(row: Mapping[str, Any], now: datetime, community: Mapping[str, Any] | None = None, *, capabilities: frozenset[str] = frozenset()) -> dict[str, Any]`.
- Consumes: `app.disclosure.access.{authorized_capabilities, authorized_capabilities_bulk}`.

This is the riskiest task in the plan (see the report at the end) because `serialise` is called from both the highest-traffic route (`list_listings`) and the detail route, and neither route currently captures the calling principal at all.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_listings_disclosure.py
"""Directive §11 (exact location), the IDENTITY capability, and §1's FINANCIALS example, on the
two routes that already exist: the paginated list and the single-listing read. Task 11 owns the
full end-to-end approve/see-it/revoke/lose-it story; this file is the field-level unit proof that
`serialise` itself applies capabilities correctly, on both routes, including the LIST route's bulk
path (directive §23)."""
from __future__ import annotations

import pytest

from tests.api.conftest import auth_headers


async def _published_seller_listing(conn, client, headers, **overrides) -> str:
    listing = await client.post("/api/seller/listings", headers=headers)
    listing_id = listing.json()["id"]
    fields = {"status": "published", "name": "Real Practice Name", "city": "Austin", "state": "TX",
              "zip": "78701", "street": "123 Main St", "phone": "5125551234", "est": 2010,
              "price": 1000000, "rev": 500000, "sqft": 3000, "location_disclosed": False,
              "name_disclosed": False, "rev_disclosed": False, **overrides}
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE listing SET {set_clause} WHERE id = %s", (*fields.values(), listing_id))
    return listing_id


@pytest.mark.asyncio
async def test_an_unapproved_buyer_sees_the_anonymised_name_even_when_the_ceiling_is_open(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s1@x.org")
    listing_id = await _published_seller_listing(conn, client, auth_headers(s_cookies, s_hdr), name_disclosed=True)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b1@x.org")
    response = await client.get(f"/api/listings/{listing_id}", headers=auth_headers(b_cookies, b_hdr))
    assert response.json()["name"] != "Real Practice Name"


@pytest.mark.asyncio
async def test_an_approved_identity_grant_reveals_the_real_name(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s2@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers, name_disclosed=True)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b2@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    created = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id, "disclosure_level": "IDENTITY"})
    await client.post(f"/api/seller/requests/{created.json()['id']}/decide", headers=seller_headers, json={"action": "approve"})
    response = await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)
    assert response.json()["name"] == "Real Practice Name"


@pytest.mark.asyncio
async def test_an_identity_grant_does_not_also_reveal_location_or_revenue(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s3@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers, name_disclosed=True, location_disclosed=True, rev_disclosed=True)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b3@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    created = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id, "disclosure_level": "IDENTITY"})
    await client.post(f"/api/seller/requests/{created.json()['id']}/decide", headers=seller_headers, json={"action": "approve"})
    body = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert body["name"] == "Real Practice Name" and body["street"] is None and body["rev"] is None


@pytest.mark.asyncio
async def test_a_full_confidential_grant_with_the_ceiling_closed_still_withholds_the_field(client, conn, member) -> None:
    # directive §8/§24: the ceiling flag ANDs with the grant, in both directions.
    _sid, s_cookies, s_hdr = member(("seller",), email="s4@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers, location_disclosed=False)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b4@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    created = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id})
    await client.post(f"/api/seller/requests/{created.json()['id']}/decide", headers=seller_headers, json={"action": "approve"})
    body = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert body["street"] is None  # location_disclosed is still false; FULL_CONFIDENTIAL cannot override it


@pytest.mark.asyncio
async def test_the_list_route_applies_capabilities_per_listing_in_one_extra_query(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s5@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_x = await _published_seller_listing(conn, client, seller_headers, name_disclosed=True)
    listing_y = await _published_seller_listing(conn, client, seller_headers, name_disclosed=True)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b5@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    created = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_x, "disclosure_level": "IDENTITY"})
    await client.post(f"/api/seller/requests/{created.json()['id']}/decide", headers=seller_headers, json={"action": "approve"})
    items = {row["id"]: row for row in (await client.get("/api/listings", headers=buyer_headers)).json()["items"]}
    assert items[listing_x]["name"] == "Real Practice Name"
    assert items[listing_y]["name"] != "Real Practice Name"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/api/test_listings_disclosure.py -v`
Expected: FAIL on every "approved" test — today, approving changes nothing because `serialise` never reads the grant at all; the first test (unapproved) may already pass, which is expected (it is the baseline the others build on).

- [ ] **Step 3: Write the minimal implementation**

Add `documents_disclosed` to `_SELECT`, and thread capabilities through both routes:

```python
# app/api/listings.py — serialise gains capabilities
def serialise(row: Mapping[str, Any], now: datetime, community: Mapping[str, Any] | None = None,
             *, capabilities: frozenset[str] = frozenset()) -> dict[str, Any]:
    ...
    disclosed = bool(row["location_disclosed"]) and "EXACT_LOCATION" in capabilities
    named = bool(row["name_disclosed"]) and "IDENTITY" in capabilities
    ...
    "rev": row["rev"] if row.get("rev_disclosed") and "FINANCIALS" in capabilities else None,
    ...
```

```python
# list_listings — one bulk capability lookup, computed AFTER the page is fetched and BEFORE the
# list comprehension that calls serialise (directive §23: one extra query for the whole page).
from app.disclosure.access import authorized_capabilities, authorized_capabilities_bulk

@router.get("/listings")
async def list_listings(request: Request, principal: Reader) -> Response:
    ...
    with closing(sync_conn()) as conn, conn:
        page = ...  # unchanged
        caps = authorized_capabilities_bulk(
            conn, buyer_account_id=str(principal.account_id),
            listings=[(str(row["id"]), row.get("seller_id")) for row in page],
        )
        community_data = community_rows(conn, [str(row["id"]) for row in page], active=active, registry=registry)
    return JSONResponse({
        ...,
        "items": [serialise(row, now, community=community_data.get(str(row["id"])),
                            capabilities=caps[str(row["id"])]) for row in page],
    })
```

```python
# get_listing — one single-listing capability lookup.
@router.get("/listings/{listing_id}")
async def get_listing(listing_id: str, principal: Reader) -> Response:
    with closing(sync_conn()) as conn, conn:
        row = _published(conn, listing_id)
    if row is None:
        return _error("NOT_FOUND", "No such listing.", 404)
    now = datetime.now(UTC)
    with closing(sync_conn()) as conn, conn:
        ...  # active/registry, unchanged
        community_data = community_rows(conn, [str(row["id"])], active=active, registry=registry)
        caps = authorized_capabilities(conn, listing_id=str(row["id"]), seller_id=row.get("seller_id"),
                                       buyer_account_id=str(principal.account_id))
    return JSONResponse(serialise(row, now, community=community_data.get(str(row["id"])), capabilities=caps))
```

`_SELECT` gains `documents_disclosed` in the same column list `location_disclosed`/`name_disclosed`/`rev_disclosed` already sit in (`listings.py:100-101`), so `row.get("documents_disclosed")` is available for Task 9 without a second query.

Both routes change from `dependencies=[Depends(REQUIRE_LISTING_READ)]` (or no guard parameter at all) to `principal: Reader` — the module-level `Reader = Annotated[S.Principal, Depends(REQUIRE_LISTING_READ)]` Task 7 declared.

- [ ] **Step 4: Run the tests**

Run: `poetry run pytest tests/api/test_listings_disclosure.py -v`
Expected: PASS, all five tests.

- [ ] **Step 5: Run the full existing listings suite to prove no regression**

Run: `poetry run pytest tests/api/test_listings.py tests/census/ -v`
Expected: PASS — `community_rows`/pagination/filtering behavior is unchanged; only the disclosure fields' gating condition grew a second term.

- [ ] **Step 6: Commit**

```bash
git add app/api/listings.py tests/api/test_listings_disclosure.py
git commit -m "feat(disclosure): serialise applies per-buyer capabilities to name, location, revenue"
```

---

## Task 9: Document authorization — the listing's document list and `read_document`'s reserved arm

**Files:**
- Modify: `app/api/listings.py` (`serialise` — add a `documents` array)
- Modify: `app/api/seller_listings.py` (`read_document`)
- Test: `tests/api/test_documents_disclosure.py` (new)

**Interfaces:**
- Modifies: `serialise(...)`'s return payload gains `"documents": list[dict]` (each `{id, name, kind, content_type}`), sourced from `listing_asset WHERE kind <> 'photo'`, always present regardless of authorization (existence is public — directive §2's "other explicitly public content", and the existing design fixture already shows a locked row's title to every buyer, `frontend/src/logic.js:1873-1878`).
- Modifies: `read_document`'s `allowed` boolean in `app/api/seller_listings.py`.

This closes finding 9 (the buyer detail page's document list was 100% hard-coded fixture data, per the wizard-step audit) as a **necessary** side effect: directive §13's "GET authorized documents" is untestable end to end unless an authorized buyer has a real way to discover which asset ids exist to fetch. It is not a drive-by fix of an unrelated defect — it is the minimum needed to make this task's own acceptance criterion reachable through the real API.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_documents_disclosure.py
"""directive §10, §13: the listing's document list is real (closing finding 9 as a prerequisite),
and reading one is gated on capability, not on `documents_disclosed`/`status` alone (the exact gap
`app/api/seller_listings.py`'s own comment at :1616-1631 names)."""
from __future__ import annotations

import pytest

from tests.api.conftest import auth_headers


async def _listing_with_a_financial_document(conn, client, seller_headers) -> tuple[str, str]:
    listing = await client.post("/api/seller/listings", headers=seller_headers)
    listing_id = listing.json()["id"]
    upload = await client.post(
        f"/api/seller/listings/{listing_id}/documents", headers=seller_headers,
        content=b'%PDF-1.4 test', headers_extra=None,
    ) if False else None  # see note below on multipart upload — written out fully in the real test file
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing_asset (listing_id, kind, name, content_type, size_bytes, storage_key, sha256)"
            " VALUES (%s,'financials','Three-year summary.pdf','application/pdf',100,%s,%s) RETURNING id",
            (listing_id, f"listings/{listing_id}/documents/test.pdf", "0" * 64),
        )
        asset_id = str(cur.fetchone()[0])
        cur.execute("UPDATE listing SET status = 'published', documents_disclosed = true WHERE id = %s", (listing_id,))
    return listing_id, asset_id


@pytest.mark.asyncio
async def test_the_listing_payload_lists_documents_by_existence_for_every_buyer(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s1@x.org")
    listing_id, asset_id = await _listing_with_a_financial_document(conn, client, auth_headers(s_cookies, s_hdr))
    _bid, b_cookies, b_hdr = member(("buyer",), email="b1@x.org")
    body = (await client.get(f"/api/listings/{listing_id}", headers=auth_headers(b_cookies, b_hdr))).json()
    assert any(d["id"] == asset_id and d["kind"] == "financials" for d in body["documents"])


@pytest.mark.asyncio
async def test_an_unapproved_buyer_cannot_fetch_the_document_bytes(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s2@x.org")
    listing_id, asset_id = await _listing_with_a_financial_document(conn, client, auth_headers(s_cookies, s_hdr))
    _bid, b_cookies, b_hdr = member(("buyer",), email="b2@x.org")
    response = await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=auth_headers(b_cookies, b_hdr))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_an_approved_financials_grant_can_fetch_the_financial_document(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s3@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, asset_id = await _listing_with_a_financial_document(conn, client, seller_headers)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b3@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    created = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id, "disclosure_level": "FINANCIALS"})
    await client.post(f"/api/seller/requests/{created.json()['id']}/decide", headers=seller_headers, json={"action": "approve"})
    response = await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=buyer_headers)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_an_identity_grant_does_not_also_unlock_the_financial_document(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s4@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, asset_id = await _listing_with_a_financial_document(conn, client, seller_headers)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b4@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    created = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id, "disclosure_level": "IDENTITY"})
    await client.post(f"/api/seller/requests/{created.json()['id']}/decide", headers=seller_headers, json={"action": "approve"})
    response = await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=buyer_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_owner_and_staff_arms_are_unchanged(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s5@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, asset_id = await _listing_with_a_financial_document(conn, client, seller_headers)
    assert (await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=seller_headers)).status_code == 200
    _tid, t_cookies, t_hdr = member(("staff",), email="staff5@x.org")
    assert (await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=auth_headers(t_cookies, t_hdr))).status_code == 200
```

(The real test file writes `_listing_with_a_financial_document` using a direct SQL insert as shown, rather than the commented-out multipart upload sketch above — inserting the row directly is simpler and matches the style `tests/api/conftest.py`'s own `_seed_registry` already uses for fixture setup that does not need to exercise the upload route itself.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/api/test_documents_disclosure.py -v`
Expected: FAIL — `documents` is not a key in the listing payload yet, and the approved-grant tests get 403 (the `_disclosed`/`_status` arm is still unused).

- [ ] **Step 3: Write the minimal implementation**

In `app/api/listings.py`, add a documents loader and thread it into `serialise` for the single-listing route only (the paginated list never renders documents):

```python
def _documents(conn: Any, listing_id: str) -> list[dict[str, Any]]:
    """Every non-photo asset's PUBLIC metadata (directive §2: existence is public; access is not).
    Called once per single-listing read — never from the list route, which has no document UI."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, kind, content_type FROM listing_asset WHERE listing_id = %s AND kind <> 'photo' ORDER BY created_at", (listing_id,))
        return [{"id": str(r[0]), "name": r[1], "kind": r[2], "content_type": r[3]} for r in cur.fetchall()]
```

`serialise` gains `documents: list[dict[str, Any]] | None = None` and includes it under a `"documents"` key (`[]` when `None`, matching the design's own "renders nothing extra for an absent list" idiom); `get_listing` calls `_documents(conn, str(row["id"]))` and passes it. `list_listings` does not.

In `app/api/seller_listings.py`, complete the reserved arm exactly where the previous team's comment said it would be added (`:1616-1650`):

```python
from app.disclosure.access import has_capability
from app.disclosure.levels import capability_for_document_kind

@router.get("/listings/{listing_id}/documents/{asset_id}")
async def read_document(listing_id: str, asset_id: str, principal: Reader) -> Response:
    """... (docstring updated: the buyer-with-an-accepted-request arm below is what the module's
    own prior comment reserved this exact location for.)"""
    try:
        parsed_asset = _asset_uuid(asset_id, "document")
        parsed_listing = _asset_uuid(listing_id, "document")
        with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT a.content_type, a.storage_key, a.kind, l.seller_id, l.documents_disclosed, l.status"
                        " FROM listing_asset a JOIN listing l ON l.id = a.listing_id"
                        " WHERE a.id = %s AND a.listing_id = %s AND a.kind <> 'photo'",
                        (parsed_asset, parsed_listing))
            found = cur.fetchone()
        if found is None:
            raise Refusal("NOT_FOUND", "No such document.", 404)
        content_type, key, kind, seller_id, disclosed, status = found
        allowed = (
            seller_id == principal.account_id
            or P.allowed("listing.review", principal)
            or (disclosed and status == "published"
                and has_capability(conn, listing_id=listing_id, seller_id=seller_id,
                                   buyer_account_id=str(principal.account_id),
                                   capability=capability_for_document_kind(kind)))
        )
        if not allowed:
            raise Refusal("LOCKED", "This document is locked until the seller approves access.", 403)
        store = store_for_request()
        content = _fetch(store, key)
        if content is None:
            raise Refusal("NOT_FOUND", "No such document.", 404)
    except Refusal as exc:
        return _refused(exc)
    return Response(content=content, media_type=content_type, headers=DOCUMENT_HEADERS)
```

The `conn` used inside `has_capability` is the SAME connection already open in the `with` block (moving `has_capability`'s call inside it, or reopening — since `conn` closes at the end of the `with closing(...)` block, restructure so the `allowed` computation happens INSIDE the `with conn.cursor()` block's enclosing `with closing(sync_conn()) as conn, conn:`, before the cursor closes; the code above assumes that restructuring, which is a small, mechanical reordering of the existing `with` nesting, not a new connection).

- [ ] **Step 4: Run the tests**

Run: `poetry run pytest tests/api/test_documents_disclosure.py -v`
Expected: PASS, all five tests.

- [ ] **Step 5: Run the full existing seller_listings and listings suites**

Run: `poetry run pytest tests/api/test_seller_listings.py tests/api/test_listings.py -v`
Expected: PASS — owner and staff document access is unchanged (`test_the_owner_and_staff_arms_are_unchanged` proves this directly).

- [ ] **Step 6: Commit**

```bash
git add app/api/listings.py app/api/seller_listings.py tests/api/test_documents_disclosure.py
git commit -m "feat(disclosure): the buyer-with-an-accepted-request arm read_document has reserved since D19"
```

---

## Task 10: The fail-closed property — generated authorization states

Per-buyer-disclosure directive §19 states a **property** ("if authorization cannot be determined: deny"), not three examples. This task sweeps the full state space `authorized_capabilities` can be asked about, the same exhaustive-enumeration idiom `tests/privacy/test_delivery.py` already uses (`itertools.product` over every cell, `176` cases) — chosen deliberately over adding a new property-testing library (`hypothesis` is not a dependency of this project; `pyproject.toml` has none), so this test uses the project's own established style for "prove a property over every state" rather than introducing a parallel testing convention.

**Files:**
- Create: `tests/disclosure/test_access_properties.py`

**Interfaces:**
- Consumes: `app.disclosure.access.authorized_capabilities`, `app.disclosure.levels.{covers, REQUESTABLE_LEVELS}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/disclosure/test_access_properties.py
"""The fail-closed PROPERTY (directive §19), swept over every reachable state rather than checked
by example. Every one of the four axes below is exhaustively enumerated and crossed
(4 statuses x 2 expiry states x 7 levels-or-none x 2 buyer-is-seller states = 112 cases); the
assertion is the single soundness statement the whole authorization boundary rests on:

    a capability is granted if, and only if, status == APPROVED, the grant has not expired,
    the buyer is not the listing's own seller, and the level covers that capability.

This is the CONTRAPOSITIVE of "assume approved": for every one of the 112 rows that is not exactly
(APPROVED, not-expired, buyer != seller, level covers X), the result must be `False` for
capability X, with no exceptions carved out by a special case."""
from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.disclosure.access import authorized_capabilities
from app.disclosure.levels import CAPABILITIES, REQUESTABLE_LEVELS, covers

STATUSES = ("PENDING", "APPROVED", "DENIED", "REVOKED")
EXPIRIES = ("none", "future", "past")
LEVELS = (None, *sorted(REQUESTABLE_LEVELS))
BUYER_IS_SELLER = (False, True)


def _account(conn, email: str) -> str:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,'x','active') RETURNING id", (email,))
        return str(cur.fetchone()[0])


def _listing(conn, seller_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, seller_id, status)"
            " VALUES (%s,'Test','Austin','TX','Austin','Small animal','Austin, TX','seller',%s,'published') RETURNING id",
            (f"prop-{uuid4().hex}", seller_id),
        )
        return str(cur.fetchone()[0])


def _expiry(kind: str) -> str | None:
    now = datetime.now(UTC)
    return {"none": None, "future": (now + timedelta(days=1)).isoformat(), "past": (now - timedelta(days=1)).isoformat()}[kind]


@pytest.mark.parametrize(
    ("status", "expiry", "level", "buyer_is_seller"),
    list(itertools.product(STATUSES, EXPIRIES, LEVELS, BUYER_IS_SELLER)),
)
def test_the_grant_soundness_property_holds_for_every_generated_state(
    conn, status: str, expiry: str, level: str | None, buyer_is_seller: bool
) -> None:
    seller = _account(conn, f"seller-{uuid4().hex}@x.org")
    buyer = seller if buyer_is_seller else _account(conn, f"buyer-{uuid4().hex}@x.org")
    listing = _listing(conn, seller)
    if buyer_is_seller and status != "PENDING":
        pytest.skip("the buyer-is-seller CHECK constraint refuses a non-pending self-row; covered by test_access.py")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO request (listing_id, buyer_user_id, seller_user_id, status, approved_disclosure_level,"
            " reviewed_at, reviewed_by, expires_at)"
            " VALUES (%s,%s,%s,%s,%s, CASE WHEN %s <> 'PENDING' THEN now() END, CASE WHEN %s <> 'PENDING' THEN %s END, %s)",
            (listing, buyer, seller, status, level, status, status, seller, _expiry(expiry)),
        )
    got = authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer)
    should_be_authorized = status == "APPROVED" and expiry != "past" and not buyer_is_seller
    expected = covers(level) if should_be_authorized else frozenset()
    assert got == expected, f"status={status} expiry={expiry} level={level} buyer_is_seller={buyer_is_seller}"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/disclosure/test_access_properties.py -v`
Expected: before Task 3 exists this fails on the import; after Task 3, it should already PASS (Task 3's implementation was written to this exact contract). If it does NOT already pass here, that is this task doing its job — it means Task 3's implementation has a branch this exhaustive sweep reaches that the eight hand-picked examples in `test_access.py` did not, and Step 3 below is fixing `app/disclosure/access.py`, not the test.

- [ ] **Step 3: Fix `app/disclosure/access.py` if the property found a gap, otherwise confirm no change is needed**

If Step 2 already passes, this step is: run the full property file once more with `-p no:randomly` and record in the commit message that zero of the 112 cases required a code change, which is itself the evidence the property holds. If it fails, the most likely gap is the CHECK constraints on `request` allowing a state Task 3's SQL did not anticipate (e.g. a REVOKED row with `expires_at` in the past — already-handled since the SQL filters on `status = 'APPROVED'` before ever looking at `expires_at`) — fix `authorized_capabilities`'s SQL or the `covers()` call, never the test's expected-value formula, since that formula IS directive §19 restated.

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/disclosure/test_access_properties.py -v`
Expected: PASS, all 112 (minus the skipped buyer-is-seller/non-pending combinations, which the database itself refuses to represent) cases green.

- [ ] **Step 5: Commit**

```bash
git add tests/disclosure/test_access_properties.py
git commit -m "test(disclosure): sweep the fail-closed property over every generated authorization state"
```

---

## Task 11: The critical two-buyer security test (directive §7)

This is the literal reproduction of John's own acceptance test, word for word: two buyer accounts, one seller approves buyer A only, buyer A gets the confidential information, buyer B does not. It is the single test whose failure means this plan has not delivered per-buyer disclosure.

**Files:**
- Create: `tests/api/test_disclosure_isolation.py`

**Interfaces:**
- Consumes: every route from Tasks 5-9, over real HTTP through `client`/`member` (`tests/api/conftest.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_disclosure_isolation.py
"""directive §7, verbatim: "Create two test buyer accounts: BUYER A, BUYER B. Seller approves
BUYER A. Expected: BUYER A receives the approved confidential information; BUYER B continues
receiving the redacted/public information. This test MUST pass." Exercised over the SAME three
surfaces the directive names: listing detail (name/location/revenue), the photo route
(unredacted images), and the document route (financial packet) — because "the confidential
information" is not one field, and a fix that only closed one surface would still fail this test's
own spirit even while passing a narrower version of it."""
from __future__ import annotations

import pytest

from tests.api.conftest import auth_headers


async def _seller_listing_with_everything_confidential(conn, client, seller_headers) -> tuple[str, str]:
    """A published listing with its name/location/revenue ceilings open, one financial document,
    and `identifiable_content_visibility = 'SHOW'` — every one of directive §7's "confidential
    information" surfaces reachable in one fixture."""
    listing = await client.post("/api/seller/listings", headers=seller_headers)
    listing_id = listing.json()["id"]
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing SET status = 'published', name = 'Highland Park Veterinary', city = 'Dallas',"
            " state = 'TX', zip = '75205', street = '4200 Preston Rd', phone = '2145551234', est = 2005,"
            " price = 2000000, rev = 900000, sqft = 4000, location_disclosed = true, name_disclosed = true,"
            " rev_disclosed = true, documents_disclosed = true, identifiable_content_visibility = 'SHOW'"
            " WHERE id = %s", (listing_id,),
        )
        cur.execute(
            "INSERT INTO listing_asset (listing_id, kind, name, content_type, size_bytes, storage_key, sha256)"
            " VALUES (%s,'financials','Financial packet.pdf','application/pdf',100,%s,%s) RETURNING id",
            (listing_id, f"listings/{listing_id}/documents/packet.pdf", "1" * 64),
        )
        asset_id = str(cur.fetchone()[0])
    return listing_id, asset_id


@pytest.mark.asyncio
async def test_buyer_a_approved_buyer_b_is_not_receives_the_confidential_information_only_a_gets(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="dallas-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, asset_id = await _seller_listing_with_everything_confidential(conn, client, seller_headers)

    _aid, a_cookies, a_hdr = member(("buyer",), email="buyer-a@x.org")
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-b@x.org")
    a_headers, b_headers = auth_headers(a_cookies, a_hdr), auth_headers(b_cookies, b_hdr)

    # BOTH buyers request — before any decision, both see the SAME redacted/public listing.
    before_a = (await client.get(f"/api/listings/{listing_id}", headers=a_headers)).json()
    before_b = (await client.get(f"/api/listings/{listing_id}", headers=b_headers)).json()
    assert before_a["name"] != "Highland Park Veterinary" and before_b["name"] != "Highland Park Veterinary"
    assert before_a["street"] is None and before_b["street"] is None

    request_a = await client.post("/api/requests", headers=a_headers, json={"listing_id": listing_id})
    request_b = await client.post("/api/requests", headers=b_headers, json={"listing_id": listing_id})

    # SELLER APPROVES BUYER A ONLY.
    approve = await client.post(f"/api/seller/requests/{request_a.json()['id']}/decide", headers=seller_headers, json={"action": "approve"})
    assert approve.status_code == 200 and approve.json()["status"] == "APPROVED"

    # BUYER A receives the approved confidential information — every surface.
    after_a = (await client.get(f"/api/listings/{listing_id}", headers=a_headers)).json()
    assert after_a["name"] == "Highland Park Veterinary"
    assert after_a["street"] == "4200 Preston Rd"
    assert after_a["rev"] == 900000
    assert any(d["id"] == asset_id for d in after_a["documents"])
    photo_a = await client.get(f"/api/listings/{listing_id}/photos/1", headers=a_headers)
    document_a = await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=a_headers)
    assert document_a.status_code == 200

    # BUYER B — request B is still PENDING, never decided — continues receiving the
    # redacted/public information on every one of the same surfaces.
    after_b = (await client.get(f"/api/listings/{listing_id}", headers=b_headers)).json()
    assert after_b["name"] != "Highland Park Veterinary", "BUYER B must not see the real name after BUYER A alone is approved"
    assert after_b["street"] is None, "BUYER B must not see the exact address after BUYER A alone is approved"
    assert after_b["rev"] is None, "BUYER B must not see the exact revenue after BUYER A alone is approved"
    document_b = await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=b_headers)
    assert document_b.status_code == 403, "BUYER B must not be able to fetch the financial document after BUYER A alone is approved"

    # SELLER REVOKES BUYER A — A must immediately lose the access the same decide/read round trip granted.
    revoke = await client.post(f"/api/seller/requests/{request_a.json()['id']}/revoke", headers=seller_headers)
    assert revoke.status_code == 200 and revoke.json()["status"] == "REVOKED"
    after_revoke = (await client.get(f"/api/listings/{listing_id}", headers=a_headers)).json()
    assert after_revoke["name"] != "Highland Park Veterinary", "BUYER A must lose access immediately on revoke"
    document_a_after_revoke = await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=a_headers)
    assert document_a_after_revoke.status_code == 403
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/api/test_disclosure_isolation.py -v`
Expected: on a checkout with Tasks 1-9 already applied, this should PASS — it exercises no new code, only the composition of everything already built. If this plan is being executed strictly task-by-task and Tasks 1-9 are genuinely done first, treat "Step 2" here as the confirmation run rather than a red bar; if any assertion fails, that is a real defect in one of Tasks 1-9's implementations, to be fixed in the module the failing assertion names (never by weakening this test).

- [ ] **Step 3: N/A — no new implementation code**

This task is pure composition of Tasks 1-9's own contracts; there is nothing to implement here beyond the test itself.

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/api/test_disclosure_isolation.py -v`
Expected: PASS. This is the test to paste into the final report's item 13 (directive §26).

- [ ] **Step 5: Commit**

```bash
git add tests/api/test_disclosure_isolation.py
git commit -m "test(disclosure): the critical two-buyer isolation test (directive §7)"
```

---

## Task 12: The full acceptance matrix (directive §21)

**Files:**
- Modify: `tests/api/test_disclosure_isolation.py`

**Interfaces:**
- Consumes: the same routes as Task 11.

- [ ] **Step 1: Write the failing test**

```python
# Appended to tests/api/test_disclosure_isolation.py

MATRIX_ROWS = (
    # (a_approved, a_revoked, b_approved) -> (a_sees_real_name, b_sees_real_name)
    (False, False, False, False, False),   # No approval
    (True,  False, False, True,  False),   # A approved
    (True,  True,  False, False, False),   # A revoked
    (False, False, True,  False, True),    # B approved
    (True,  False, True,  True,  True),    # Both approved
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("a_approved", "a_revoked", "b_approved", "a_sees", "b_sees"), MATRIX_ROWS)
async def test_the_full_acceptance_matrix(client, conn, member, a_approved, a_revoked, b_approved, a_sees, b_sees) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email=f"matrix-seller-{a_approved}{a_revoked}{b_approved}@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, _asset_id = await _seller_listing_with_everything_confidential(conn, client, seller_headers)
    _aid, a_cookies, a_hdr = member(("buyer",), email=f"a-{a_approved}{a_revoked}{b_approved}@x.org")
    _bid, b_cookies, b_hdr = member(("buyer",), email=f"b-{a_approved}{a_revoked}{b_approved}@x.org")
    a_headers, b_headers = auth_headers(a_cookies, a_hdr), auth_headers(b_cookies, b_hdr)

    request_a = (await client.post("/api/requests", headers=a_headers, json={"listing_id": listing_id})).json()
    request_b = (await client.post("/api/requests", headers=b_headers, json={"listing_id": listing_id})).json()
    if a_approved:
        await client.post(f"/api/seller/requests/{request_a['id']}/decide", headers=seller_headers, json={"action": "approve"})
    if a_revoked:
        await client.post(f"/api/seller/requests/{request_a['id']}/revoke", headers=seller_headers)
    if b_approved:
        await client.post(f"/api/seller/requests/{request_b['id']}/decide", headers=seller_headers, json={"action": "approve"})

    body_a = (await client.get(f"/api/listings/{listing_id}", headers=a_headers)).json()
    body_b = (await client.get(f"/api/listings/{listing_id}", headers=b_headers)).json()
    assert (body_a["name"] == "Highland Park Veterinary") is a_sees
    assert (body_b["name"] == "Highland Park Veterinary") is b_sees


@pytest.mark.asyncio
async def test_an_unauthenticated_caller_gets_no_information_at_all(client, conn, member) -> None:
    # This product requires membership to browse at all (`page.browse`/`listing.read` are
    # `_MEMBERS`, `app/auth/permissions.py:19` — no anonymous carve-out, unlike `market.read`),
    # a decision this plan does not revisit. Directive §21's "unauthenticated -> public
    # information only" therefore means 401 here, not a redacted-but-served body: there is no
    # public tier below the signed-in-buyer redacted view in THIS product.
    _sid, s_cookies, s_hdr = member(("seller",), email="unauth-seller@x.org")
    listing_id, _asset_id = await _seller_listing_with_everything_confidential(conn, client, auth_headers(s_cookies, s_hdr))
    response = await client.get(f"/api/listings/{listing_id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_partial_approval_reveals_only_the_approved_level(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="partial-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, asset_id = await _seller_listing_with_everything_confidential(conn, client, seller_headers)
    _bid, b_cookies, b_hdr = member(("buyer",), email="partial-buyer@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    created = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id, "disclosure_level": "EXACT_LOCATION"})
    await client.post(f"/api/seller/requests/{created.json()['id']}/decide", headers=seller_headers, json={"action": "approve"})
    body = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert body["street"] == "4200 Preston Rd" and body["name"] != "Highland Park Veterinary" and body["rev"] is None
    document = await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=buyer_headers)
    assert document.status_code == 403


@pytest.mark.asyncio
async def test_a_seller_can_only_manage_access_for_their_own_listings(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="owner-seller@x.org")
    listing_id, _asset_id = await _seller_listing_with_everything_confidential(conn, client, auth_headers(s_cookies, s_hdr))
    _bid, b_cookies, b_hdr = member(("buyer",), email="owner-buyer@x.org")
    request_row = (await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr), json={"listing_id": listing_id})).json()
    _oid, o_cookies, o_hdr = member(("seller",), email="not-the-owner@x.org")
    response = await client.post(f"/api/seller/requests/{request_row['id']}/decide", headers=auth_headers(o_cookies, o_hdr), json={"action": "approve"})
    assert response.status_code == 404
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/api/test_disclosure_isolation.py -k matrix -v`
Expected: on top of Tasks 1-9, PASS immediately (same reasoning as Task 11 Step 2 — this is a composition test).

- [ ] **Step 3: N/A — no new implementation code**

- [ ] **Step 4: Run the full file**

Run: `poetry run pytest tests/api/test_disclosure_isolation.py -v`
Expected: PASS, all rows of the matrix plus the three extra bullets.

- [ ] **Step 5: Commit**

```bash
git add tests/api/test_disclosure_isolation.py
git commit -m "test(disclosure): the full acceptance matrix (directive §21)"
```

---

## Task 13: IDOR / adversarial authorization testing (directive §22)

**Files:**
- Create: `tests/api/test_disclosure_idor.py`

**Interfaces:**
- Consumes: the same routes as Tasks 11-12.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_disclosure_idor.py
"""directive §22, its four attempts named one test each. Every one of these already has a defense
built somewhere in Tasks 1-9 (the partial index, the seller_listings.py:18 404-not-403 rule, the
per-listing-scoped authorization query) — this file is what PROVES each defense actually holds
against the specific attack, rather than trusting that it does because the code "looks right"."""
from __future__ import annotations

import pytest

from tests.api.conftest import auth_headers
from tests.api.test_disclosure_isolation import _seller_listing_with_everything_confidential


@pytest.mark.asyncio
async def test_buyer_a_cannot_read_buyer_b_s_access_record_by_guessing_its_id(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="idor1-seller@x.org")
    listing_id, _asset_id = await _seller_listing_with_everything_confidential(conn, client, auth_headers(s_cookies, s_hdr))
    _aid, a_cookies, a_hdr = member(("buyer",), email="idor1-a@x.org")
    _bid, b_cookies, b_hdr = member(("buyer",), email="idor1-b@x.org")
    a_headers, b_headers = auth_headers(a_cookies, a_hdr), auth_headers(b_cookies, b_hdr)
    request_b = (await client.post("/api/requests", headers=b_headers, json={"listing_id": listing_id})).json()
    response = await client.get(f"/api/requests/{request_b['id']}", headers=a_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_grant_on_one_listing_grants_nothing_on_a_second_confidential_listing(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="idor2-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_x, _ = await _seller_listing_with_everything_confidential(conn, client, seller_headers)
    listing_y, _ = await _seller_listing_with_everything_confidential(conn, client, seller_headers)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET name = 'Different Practice Y' WHERE id = %s", (listing_y,))
    _aid, a_cookies, a_hdr = member(("buyer",), email="idor2-a@x.org")
    buyer_headers = auth_headers(a_cookies, a_hdr)
    request_x = (await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_x})).json()
    await client.post(f"/api/seller/requests/{request_x['id']}/decide", headers=seller_headers, json={"action": "approve"})
    body_y = (await client.get(f"/api/listings/{listing_y}", headers=buyer_headers)).json()
    assert body_y["name"] != "Different Practice Y"


@pytest.mark.asyncio
async def test_a_second_seller_cannot_decide_on_or_revoke_a_request_against_a_listing_they_do_not_own(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="idor3-owner@x.org")
    owner_headers = auth_headers(s_cookies, s_hdr)
    listing_id, _asset_id = await _seller_listing_with_everything_confidential(conn, client, owner_headers)
    _bid, b_cookies, b_hdr = member(("buyer",), email="idor3-buyer@x.org")
    request_row = (await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr), json={"listing_id": listing_id})).json()
    _oid, o_cookies, o_hdr = member(("seller",), email="idor3-attacker@x.org")
    attacker_headers = auth_headers(o_cookies, o_hdr)
    decide = await client.post(f"/api/seller/requests/{request_row['id']}/decide", headers=attacker_headers, json={"action": "approve"})
    assert decide.status_code == 404
    await client.post(f"/api/seller/requests/{request_row['id']}/decide", headers=owner_headers, json={"action": "approve"})
    revoke = await client.post(f"/api/seller/requests/{request_row['id']}/revoke", headers=attacker_headers)
    assert revoke.status_code == 404


@pytest.mark.asyncio
async def test_a_grant_valid_for_one_listing_cannot_be_used_to_fetch_a_different_listing_s_document(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="idor4-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_x, _asset_x = await _seller_listing_with_everything_confidential(conn, client, seller_headers)
    listing_y, asset_y = await _seller_listing_with_everything_confidential(conn, client, seller_headers)
    _aid, a_cookies, a_hdr = member(("buyer",), email="idor4-a@x.org")
    buyer_headers = auth_headers(a_cookies, a_hdr)
    request_x = (await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_x})).json()
    await client.post(f"/api/seller/requests/{request_x['id']}/decide", headers=seller_headers, json={"action": "approve"})
    # Approved on X; asset_y genuinely belongs to Y. Pairing Y's own listing_id with its own
    # asset_id (the honest, matched pair) must still be refused — the grant does not carry over.
    response = await client.get(f"/api/seller/listings/{listing_y}/documents/{asset_y}", headers=buyer_headers)
    assert response.status_code == 403
    # And the pre-existing mismatched-pair IDOR guard (an asset that does NOT belong to the named
    # listing at all) must still hold too — a regression check on code this task did not write.
    mismatched = await client.get(f"/api/seller/listings/{listing_x}/documents/{asset_y}", headers=buyer_headers)
    assert mismatched.status_code == 404
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/api/test_disclosure_idor.py -v`
Expected: on top of Tasks 1-9, PASS (composition test, same as Tasks 11-12).

- [ ] **Step 3: N/A — no new implementation code**

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/api/test_disclosure_idor.py -v`
Expected: PASS, all four attempts denied.

- [ ] **Step 5: Commit**

```bash
git add tests/api/test_disclosure_idor.py
git commit -m "test(disclosure): IDOR / adversarial authorization tests (directive §22)"
```

---

## Task 14: Frontend wiring — the existing screens, wired to the real API

**Files:**
- Create: `frontend/src/requests/buyer.ts`
- Create: `frontend/src/requests/seller.ts`
- Modify: `frontend/src/App.vue`, `frontend/src/main.ts`
- Test: `frontend/src/requests/buyer.test.ts`, `frontend/src/requests/seller.test.ts`

**Interfaces:**
- Produces: `makeBuyerRequestsAdapter(fetcher): BuyerRequestsAdapter` with `{ create(listingId, message?, level?): Promise<Request>, mine(): Promise<Request[]> }`; `makeSellerRequestsAdapter(fetcher): SellerRequestsAdapter` with `{ inbox(): Promise<Request[]>, decide(id, action, level?, reason?): Promise<Request>, revoke(id): Promise<Request> }`, following `frontend/src/listings/seller.ts`'s adapter shape exactly (a factory taking the shared `fetcher`, returning plain async methods, no class).
- Consumes: nothing from the design bundle's own generated files — this is app-only code, exactly like `frontend/src/market/boundaries.ts` (A24.14-18's own "app-only adapter the reference never receives").

**CONTROLLER AMENDMENT (2026-09-19), correcting this paragraph as first written.** It read "This task does **not** touch `frontend/tests/design-amendments.ts`, add a `LOCAL_AMENDMENTS.md` row, or re-base any approved state," and the first two clauses are FALSE. The adapter files (`frontend/src/requests/*.ts`) and their instantiation in `main.ts`/`App.vue` really are app-only code needing no amendment — but the half of Step 3 that makes `logic.js` READ those adapters cannot be hand-written: `frontend/tests/app-generated.test.ts:77` asserts `src/logic.js === portLogic('Practice Match V3.dc.html')` byte for byte, under its own comment that "never hand-edit logic.js is enforceable rather than aspirational." So that half goes through the amendment engine — entries in `design-amendments.ts`, `npm run gen:design && gen:app && gen:logic`, and one `LOCAL_AMENDMENTS.md` row per entry — under family id **A52**, verified free across every checked-out branch on the day. THE THIRD CLAUSE STANDS and is the task's acceptance proof: a script-only amendment paints nothing, so zero approved states and none of `baseline-manifest.json`'s thirteen frozen hashes may move, MEASURED before and after (the A33 method) rather than reasoned. Confirm at Step 4.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/requests/buyer.test.ts
import { describe, expect, it, vi } from 'vitest';
import { makeBuyerRequestsAdapter } from './buyer';

describe('makeBuyerRequestsAdapter', () => {
  it('create() posts to /api/requests and returns the created row', async () => {
    const fetcher = vi.fn().mockResolvedValue({ id: 'r1', status: 'PENDING' });
    const adapter = makeBuyerRequestsAdapter(fetcher);
    const result = await adapter.create('listing-1', 'Tell me more');
    expect(fetcher).toHaveBeenCalledWith('/api/requests', {
      method: 'POST',
      body: { listing_id: 'listing-1', message: 'Tell me more' },
    });
    expect(result).toEqual({ id: 'r1', status: 'PENDING' });
  });

  it('mine() reads /api/requests/mine', async () => {
    const fetcher = vi.fn().mockResolvedValue([{ id: 'r1', status: 'APPROVED' }]);
    const adapter = makeBuyerRequestsAdapter(fetcher);
    const result = await adapter.mine();
    expect(fetcher).toHaveBeenCalledWith('/api/requests/mine', { method: 'GET' });
    expect(result).toEqual([{ id: 'r1', status: 'APPROVED' }]);
  });
});
```

```typescript
// frontend/src/requests/seller.test.ts
import { describe, expect, it, vi } from 'vitest';
import { makeSellerRequestsAdapter } from './seller';

describe('makeSellerRequestsAdapter', () => {
  it('inbox() reads /api/seller/requests', async () => {
    const fetcher = vi.fn().mockResolvedValue([{ id: 'r1', status: 'PENDING' }]);
    const adapter = makeSellerRequestsAdapter(fetcher);
    await adapter.inbox();
    expect(fetcher).toHaveBeenCalledWith('/api/seller/requests', { method: 'GET' });
  });

  it('decide() posts the action to .../decide', async () => {
    const fetcher = vi.fn().mockResolvedValue({ id: 'r1', status: 'APPROVED' });
    const adapter = makeSellerRequestsAdapter(fetcher);
    await adapter.decide('r1', 'approve');
    expect(fetcher).toHaveBeenCalledWith('/api/seller/requests/r1/decide', {
      method: 'POST',
      body: { action: 'approve' },
    });
  });

  it('revoke() posts to .../revoke', async () => {
    const fetcher = vi.fn().mockResolvedValue({ id: 'r1', status: 'REVOKED' });
    const adapter = makeSellerRequestsAdapter(fetcher);
    await adapter.revoke('r1');
    expect(fetcher).toHaveBeenCalledWith('/api/seller/requests/r1/revoke', { method: 'POST', body: {} });
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/requests/buyer.test.ts src/requests/seller.test.ts`
Expected: FAIL — `Cannot find module './buyer'` / `'./seller'`.

- [ ] **Step 3: Write the minimal implementation**

```typescript
// frontend/src/requests/buyer.ts
// The buyer-facing request adapter (directive §6). App-only: the reference and the Claude Design
// preview receive no adapter and keep the design's own `s.requests` fixture untouched
// (A16.1/A17.1's own rule for every adapter this codebase has added).
import type { Fetcher } from '../listings/seller'; // the shared fetcher type every adapter already uses

export interface RequestRow {
  id: string;
  listing_id: string;
  status: 'PENDING' | 'APPROVED' | 'DENIED' | 'REVOKED';
  message: string | null;
  requested_disclosure_level: string;
  approved_disclosure_level: string | null;
  requested_at: string;
}

export interface BuyerRequestsAdapter {
  create(listingId: string, message?: string, level?: string): Promise<RequestRow>;
  mine(): Promise<RequestRow[]>;
}

export function makeBuyerRequestsAdapter(fetcher: Fetcher): BuyerRequestsAdapter {
  return {
    create: (listingId, message, level) =>
      fetcher('/api/requests', {
        method: 'POST',
        body: { listing_id: listingId, ...(message ? { message } : {}), ...(level ? { disclosure_level: level } : {}) },
      }),
    mine: () => fetcher('/api/requests/mine', { method: 'GET' }),
  };
}
```

```typescript
// frontend/src/requests/seller.ts
import type { Fetcher } from '../listings/seller';
import type { RequestRow } from './buyer';

export interface SellerRequestsAdapter {
  inbox(): Promise<RequestRow[]>;
  decide(id: string, action: 'approve' | 'deny', level?: string, reason?: string): Promise<RequestRow>;
  revoke(id: string): Promise<RequestRow>;
}

export function makeSellerRequestsAdapter(fetcher: Fetcher): SellerRequestsAdapter {
  return {
    inbox: () => fetcher('/api/seller/requests', { method: 'GET' }),
    decide: (id, action, level, reason) =>
      fetcher(`/api/seller/requests/${id}/decide`, {
        method: 'POST',
        body: { action, ...(level ? { disclosure_level: level } : {}), ...(reason ? { reason } : {}) },
      }),
    revoke: (id) => fetcher(`/api/seller/requests/${id}/revoke`, { method: 'POST', body: {} }),
  };
}
```

Check `frontend/src/listings/seller.ts`'s actual exported fetcher type name before writing the import (`Fetcher` above is a placeholder for whatever that file's real exported type is called — read the file first; do not introduce a second, differently-named fetcher type).

In `frontend/src/App.vue` (or wherever `listings`/`market` adapters are currently instantiated and passed as props, per A16.1/A24.14's own wiring) and `frontend/src/main.ts`, add:

```typescript
const requests = makeBuyerRequestsAdapter(fetcher);
const sellerRequests = makeSellerRequestsAdapter(fetcher);
// passed as `props.requests` / `props.sellerRequests` beside the existing `props.listings`
```

`logic.js`'s own `componentDidMount` (A16.1's own idiom) then reads `this.props.requests`/`this.props.sellerRequests` presence to decide whether to call `loadRequests()`/`reloadInbox()` (mirroring A16.17's `reloadListings`) instead of using the static `s.requests` fixture array — this is a SCRIPT-ONLY change — meaning it edits the design's SCRIPT block rather than its template, so it paints no pixels — and it is therefore an A52 amendment entry with its own `LOCAL_AMENDMENTS.md` row, exactly as A16.1's own ternary is one. **The first draft of this sentence read "so it is not a `LOCAL_AMENDMENTS.md` entry any more than A16.1's own ternary is one" and inverted its own citation**: A16.1 and A40.3–A40.6 ARE amendment entries, and CLAUDE.md's "A40.3-A40.6 are SCRIPT-ONLY and paint nothing" says they move no pixels, never that they escape the ledger. Adding `this.props.requests`/`this.props.sellerRequests` also requires the `data-props` schema entry (the A16.11a / A20.4d mechanism), because `app-generated.test.ts:48` fails on any `this.props.X` that `app.setup.js` does not declare. Map the served `status` values onto the design's own three: `APPROVED → "accepted"`, `DENIED → "declined"`, `REVOKED → "declined"` (the documented, low-risk default from "What needs a design ruling" above), `PENDING → "pending"`.

- [ ] **Step 4: Run the tests, and confirm zero approved states move**

Run: `cd frontend && npx vitest run src/requests/ && npm run typecheck && npm run build && npm test`
Then: `npm run test:visual:baselines && npm run test:e2e`
Expected: all green; the visual/DOM oracle diff reports **zero** re-based states (this task must not move a single pixel — if it does, something reached the template, which was not the intent, and the diff must be inspected before proceeding).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/requests/ frontend/src/App.vue frontend/src/main.ts
git commit -m "feat(disclosure): wire the interest modal, My Requests and the seller inbox to the real API"
```

---

## Self-review notes (recorded, not a task)

Checked against every numbered directive section: §1 (Tasks 1-9), §2/§16 (Task 2), §3/§18 (Task 1's schema, Task 3), §4 (Task 1), §5 (Task 6, Task 14, the Revoke-button gap flagged), §6 (Task 5, Task 14), §7 (Task 11), §8/§24 ("What each existing flag still means"), §9 (Task 7), §10 (Task 9), §11 (Task 8), §12 (Task 3 + every route task), §13 (Tasks 5, 6; confidential-content routes are the pre-existing three, extended), §14 (folded into Tasks 5, 6, 7, 9's own audit writes — deliberately not logging every routine public/redacted read, recorded as a reasoned scope decision), §15 (Task 6's revoke route; Task 11 proves immediate loss of access; the "cannot recall a downloaded file" limit is stated plainly in this section's own prose and is not claimed otherwise anywhere in this plan), §17 (no copy edits — stated explicitly as a Global Constraint and verified as part of Task 14), §19 (Task 3 + Task 10's property sweep), §20 (Task 7 preserves the existing pipeline, only adds the AND-condition), §21 (Task 12), §22 (Task 13), §23 (Task 1's indexes, Task 3's bulk variant, Task 5/6's rate limits), §25 (Task 11 is exactly this demonstration end to end).

No placeholder steps remain — every code block above is complete, runnable code, not a description of code. Type/name consistency checked: `authorized_capabilities`/`has_capability`/`authorized_capabilities_bulk` (Task 3) are the only three names later tasks call, and Tasks 7-9 use exactly those three signatures; `Refusal`/`_refused` (Task 4 onward) is the one exception/rendering pair reused everywhere, never redeclared; the six capability names (`IDENTITY`, `EXACT_LOCATION`, `UNREDACTED_IMAGES`, `FINANCIALS`, `FLOOR_PLANS`, `FULL_CONFIDENTIAL`) and four statuses (`PENDING`, `APPROVED`, `DENIED`, `REVOKED`) are spelled identically in the migration's CHECK constraints, `levels.py`, and every test file above.
