# The VIN Foundation Admin control surface — composed from V3's own elements

**Status:** design for John's approval (2026-09-13). Ruling D-C53 ("all the admin tabs must be factual and fully functional, zero-gaps, zero-fake data, everything must be surfaced and wired to UX") and John's decision the same day: *compose them from V3's own elements under your approval, how the eight account screens were built* (the A8 precedent). Ruling D-C54 (the admin role holds every permission) is in force.

**What this spec covers:** the surfaces the backend has and the V3 design never drew. **What it does not cover:** the wiring of the four tabs V3 already draws — Users (A36), Data Sources (A38), Listings (A39) are in flight as wiring tasks; ADMIN-GATE (A40) shipped in 0.1.23.

**Source of truth for every element below:** `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html` plus the ruled amendments. Nothing here introduces a token, size, weight or colour the design does not already carry. Every composition is a set of literal edits in `frontend/tests/design-amendments.ts` with its own family id, one `LOCAL_AMENDMENTS.md` row per entry, and an oracle so the approved states keep their pixels.

---

## 1. The rules every composition obeys

1. **Reference open first, port verbatim, absent beats faked** (CLAUDE.md). A composition reuses an element that exists in V3, in the declarations V3 gives it, in the place V3's own idiom would put it. The eight account screens (A8) are the proof this works.
2. **Real data or no rows.** With an adapter present, a surface renders what the API answered or nothing — never a fixture (A16.1/A17.1). The reference and the Claude Design preview pass no adapter and keep V3's fixtures.
3. **An action renders only if it completes.** A button calls a real route with a real transition and an audit row, or it is not drawn (D-C53).
4. **Step-up before harm.** Every action in `REAUTH` (`licence.decide`, `engine.activate`, `roles.grant`, `tokens.manage`, `users.revoke`, `signups.notify`) passes through the re-authentication dialog (§3). The API already refuses these without a fresh password; the design gets the element that lets a person supply one.
5. **Every view of sensitive content is logged**, as the Requests footer already promises: the route writes `audit_log` before it answers.
6. **The frozen thirteen.** Four admin screens are frozen hashes. A composition ADDS elements behind adapter presence or a new tab, so the four captures keep their pixels through the oracle stub; where a ruling deliberately moves one (the hidden doors, §8), the re-pin is named and recorded, the A18 mechanism.

## 2. The admin shell gains one tab: **Settings**

John: "where are the settings?" The settings-shaped writes exist as scattered admin actions: dataset licence decisions, activating a Census vintage (`engine.activate`), the public-market-data flag (`MARKET_DATA_PUBLIC`), the launch mail (`signups.notify`), API tokens (`tokens.manage`). None has a screen.

**Composition.** A fifth tab in the admin tab row (the row's own `adminTabs` element gains one entry — the same shape as the four), rendering the Data Sources table idiom: `LABEL · sub-line · status pill · action`. Rows:

| Row | Sub-line (live) | Pill | Action (REAUTH) |
|---|---|---|---|
| Market data visible to anonymous visitors | `MARKET_DATA_PUBLIC` value and who last changed it (audit) | On / Off | Turn on / Turn off |
| Census data vintage | active vintages per dataset (`active_vintage`), last load | Active | Activate <vintage> (only when a newer load exists) |
| Launch mail to sign-ups | count of sign-ups, last send (`signups` + outbox) | Sent <date> / Not sent | Send |
| API tokens | count of live tokens, last used | — | Manage (opens §6's token list) |

The pill uses the design's three pill tones (dark = active/on, outline = off/not sent); the action is the Users tab's primary/secondary button pair. **Recommendation:** ship rows 1–3 with A41; row 4 with §6.

**Alternatives considered:** (a) leave these as API-only operations run from a terminal — rejected: John's ask is a screen; (b) fold them into Data Sources — rejected: two of the four are not datasets.

## 3. The re-authentication dialog

**Composition.** The interest modal's scrim and box (`z-index 1100`, the A19 precedent) holding the sign-in card's own password field and its primary button relabelled "Confirm", the sign-in card's `formError` slot for a wrong password, and the docked panel's 38 px close control. Opens from any REAUTH action; on success re-issues the action with the fresh credential; Escape and outside-click cancel (A13/A14's dismissal closures). No new element, no new copy beyond "Confirm your password to continue" — the sign-in card's own sentence pattern.

**Where it is used:** Users → Revoke (and Suspend if ruled REAUTH — today it is not); Data Sources → licence decision (§4); Settings (§2); tokens (§6).

**Alternative rejected:** `window.prompt` — takes a password unmasked; refused by the A36 brief.

## 4. The licence decision on Data Sources

The registry's only real write is `POST /data-sources/{key}/license` (REAUTH). V3's "Assign review" / "Open question" buttons have no backing and are removed by A38.

**Composition.** On an `unresolved` or `blocked` row, the Users tab's Approve/Decline pair relabelled **Clear** / **Block**, each opening the re-auth dialog (§3) with the sign-in card's text field beneath the password field for the mandatory note ("why", stored in `license_audit`). The row's pill and sub-line update from the returned row. **Esri rows:** registered `unresolved` by A38; John or the Foundation clears them here — the one decision record.

## 5. Requests — the data model, the four surfaces, the admin tab

There is NO request table and NO route anywhere in the product; the buyer's "I'm interested", My Requests, the seller inbox and the admin tab are all in-memory fixtures. This is a build. **Decisions:**

- **Model:** `request(id, listing_id, buyer_account_id, message, status pending|accepted|declined, created_at, decided_at, decided_by)` + `request_event(request_id, at, actor_role, kind)`; statuses are V3's own three; the design's fourth pill "Review" and the "volume pattern flagged automatically" row are NOT built (no detector exists) — oracle-only fixture, like the Flagged listing.
- **Routes:** `POST /api/requests` (buyer; the interest modal's real submit), `GET /api/requests/mine` (buyer, My Requests), `GET /api/seller/requests` + `POST /api/seller/requests/{id}/decide` (seller inbox, accept/decline; **accept releases the document packet** — the deferred arm in `seller_listings.py` is built here so the seller's "Share more" sentence becomes true), `GET /api/admin/requests` (staff: requester, listing, seller, status, age, last event — **no message content**), `GET /api/admin/requests/{id}/message` (`abuse.investigate`, REAUTH, writes an audit row per view).
- **Admin tab composition:** the existing Requests table with real rows; the Request column's paraphrase sub-line is OMITTED (the footer forbids staff seeing content); "Reminder sent" is omitted (no reminder job); the footer's promise gets its element: a secondary "Open message (logged)" button on each row, visible to `abuse.investigate` holders, opening the message in the interest modal's box after the re-auth dialog.
- **Interest modal literals** ("License state: Texas", "VIN Foundation status: Approved buyer") become served: `/api/me` gains `license_state` (from the latest application) and the role label; the row is dropped when absent.
- **Badge:** requests in `pending` older than 48 h (awaiting seller) — the design's "Awaiting seller" reading.

**Alternative rejected:** wiring the admin tab to a minimal table and leaving buyer/seller surfaces as fixtures — D-C53 says everything wired.

## 6. Drill-down: user detail, listing detail, tokens, audit

The API has `GET /users/{id}`, `GET /listings/{id}`, `GET /audit`, token routes. V3 has no detail view on the admin screens.

**Composition.** The docked panel's OWN idiom: clicking a Users or Listings row opens the Browse docked panel's shell (`PRACTICE DETAIL` header, tabs, the key-fact grid, the CTA) anchored right, with tabs **Overview · History · Access** for a user (application fields, decisions with decider and date, role grants with granted-by, the audit rows for that target) and **Overview · History** for a listing (status changes with actor and date, decline reason, photographs' privacy state once P9 lands). "Access" carries the grants list and, for admins, the design's Approve/Decline pair relabelled **Grant role** / **Revoke role** (REAUTH). Tokens live under Settings → Manage as the Users table idiom (name · created · last used · Revoke). **Recommendation:** build user detail first (A42), listing detail second (A43).

**Alternative rejected:** inline row expansion — V3 has no expanding-row element; the docked panel is its one detail idiom.

## 7. Permissions — the matrix, visible

`GET /api/admin/permissions` serves the 6 × 33 matrix plus the token facts. Deferred by John on 2026-09-07 for want of a design.

**Composition.** A read-only matrix under Settings (a sixth row "Permissions" whose action opens it), rendered as the Data Sources table: one row per action (its key and the plain sentence the matrix module documents), one column per role holding the design's pill (dark = allowed, outline = denied), and a legend line "admin holds every permission (D-C54); step-up required for: …". **Grants are edited on the user's Access tab (§6), not here** — the matrix is policy, grants are people.

**Alternative rejected:** an editable matrix — policy lives in `app/auth/permissions.py` under test; editing it live would make the generated frontend matrix stale.

## 8. The two doors, and the seller application

- **Hidden doors (A40.1/A40.2, held in 0.1.23).** A buyer sees "VIN Foundation Admin" and "List a Practice" and is refused. Ruling recommended: hide a door the account cannot open. Cost: a ninth declared prototype prop `startRoles` (A16.11's mechanism) so the reference can render a buyer's two doors, and a ruled re-pin of the seven frozen non-Browse captures the persona split moves. **John decides.**
- **A buyer cannot apply to sell anywhere.** `seller.apply` is a real permission and route; V3 has no screen. Composition: the access-request card (the base A8 composed nine screens from) with the seller intent fields (practice name, city, ZIP, intended timing), reached from "List a Practice" for a buyer, submitting to the existing route; the staff decision arrives on the Users tab as a seller application ("Seller applicant" marker, A36). **John decides whether this ships before or after the admin tabs.**

## 9. Families, order, gates

| Family | Composition | After |
|---|---|---|
| A41 | Settings tab (§2 rows 1–3) + the re-auth dialog (§3) | A36/A38/A39 merge |
| A42 | Licence decision on Data Sources (§4) | A41 |
| A43 | Requests (§5): model, routes, four surfaces, admin tab | A41 |
| A44 | User detail + Access (§6) | A41 |
| A45 | Listing detail (§6) | A44 |
| A46 | Permissions matrix view (§7) + tokens under Settings | A41 |
| A40.1/A40.2 + `startRoles` | Hidden doors (§8) | John's ruling |
| A47 | Seller application screen (§8) | John's ruling |

Every task: strict TDD; backend 100 % line+branch; frontend 100 %; zero-pixel oracle with the frozen thirteen proved unmoved (or re-pinned by ruling); AMEND-GUARD and citation gates; review + scoped re-reviews; CI green on the pushed SHA before any deploy; QA click-through as the staff persona AND an admin-only persona (D-C54's lesson) AND the buyer persona.

## 10. Open questions for John (each with the recommendation)

1. Hide the two doors a buyer cannot open? — **Yes** (re-pin seven frozen screens; ninth prototype prop).
2. Ship the seller-application screen (§8) before or after the admin tabs? — **After A43** (Requests), since a seller without requests has less to do.
3. Suspend: step-up like Revoke, or not? — **Not** (reversible; the API does not require it).
4. The pets 0.57 factor: a registry row with a source and licence, or a methodology note? — **A methodology note** in the layer caveat; no row (it is not a dataset).
5. Satellite imagery while its registry row is `unresolved`: gate the toggle on the registry, or clear Esri's row? — **The Foundation clears or blocks the Esri rows on the Data Sources tab (§4)**; until then the toggle stays as shipped, and the board says so.
