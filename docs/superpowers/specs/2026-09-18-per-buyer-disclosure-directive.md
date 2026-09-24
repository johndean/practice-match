# PRACTICE MATCH — DECISION: PER-BUYER DISCLOSURE IS THE INTENDED PRODUCT

**John, 2026-09-18. Recorded verbatim. This is the ruling on the wizard audit's Question 3
("Is per-buyer disclosure the real product?") and it overturns the cheaper option the
controller offered — rewriting the copy to describe the global switch. It does NOT.**

The intended Practice Match product behavior is CONFIRMED: **PER-BUYER DISCLOSURE.**

---

## AMENDED 2026-09-24 — RULING D-C66: THE CEILING IS THE PUBLIC DEFAULT, NOT A SECOND LOCK

**John, 2026-09-24, on Task 8 of the seller-wizard repair plan
(`docs/superpowers/plans/2026-09-23-seller-wizard-repair.md`): CORRECT THE BEHAVIOUR, NOT THE COPY.
The listing-wide ceilings become per-buyer releasable.**

**What was built from this directive, and what it did.** §3, §8 and §18 below were implemented as
*ceiling AND grant*: `app/api/listings.py::serialise` read `bool(row["location_disclosed"]) and
"EXACT_LOCATION" in capabilities`, and its two siblings for the name and the revenue, while
`app/api/seller_listings.py::read_document` ANDed `documents_disclosed` in front of
`has_capability`. Read against the seller's own four switches, that makes the product say the
opposite of what its labels say. The four step-7 toggles all SHUT a ceiling, and three of them
promise release on approval in as many words — "Keep practice name and address hidden **until I
approve a buyer**", "Release revenue as a range **until I approve a buyer**", "Keep floor plans and
financial packet locked / Buyers see the document titles and can ask for access". A seller who
ticked any of them and then approved a buyer released **nothing at all**: `False and anything` is
False, whatever the seller decided afterwards. The one toggle that behaved as promised was
`showIdentifiable`, whose `NOT_SHOW` + `UNREDACTED_IMAGES` path (`app/privacy/delivery.py`) was
built as a genuine per-buyer gate, and it is the shape the other three now follow.

**The ruling.** The seller's flag is the PUBLIC DEFAULT and the buyer's grant RELEASES on top of it:
*ceiling OR grant*. A seller who leaves a ceiling OPEN is publishing that field to every signed-in
buyer, which is what the toggle's own off position has always meant and what this product did
before this directive ANDed a grant in front of it. A seller who SHUTS a ceiling is publishing to
nobody until they approve someone — the promise the label makes.

**WHAT THAT SUPERSEDES, quoted rather than deleted.** Each sentence below stays in place in its own
section, with a supersession note beside it:

* §3, "A listing-level global boolean must NOT be sufficient to authorize confidential disclosure."
* §8, "**GLOBAL VISIBILITY is NOT BUYER AUTHORIZATION.** Separate these concepts."
* §11, "Exact location is confidential unless explicitly authorized. The public listing may use
  generalized location, market area, city/region, approximate map representation."
* §18, "Do not create a global field such as `listing.confidentiality_approved = true` and use that
  as the sole authorization mechanism."

**WHAT IT DOES NOT SUPERSEDE, and this is the half that matters most.** §19 (FAIL CLOSED) is
strengthened, not relaxed, and the reason is structural: under AND, a bug that wrongly handed a
buyer a capability still met a shut ceiling; under OR the capability set is the ONLY thing standing
between a listing and disclosure. Every producer of that set still answers `frozenset()` for an
absent buyer, a missing row and an unknown level, and the no-grant answer is re-proved field by
field rather than inherited (`tests/api/test_listings_disclosure.py`).

§10 and §12 (documents) are likewise NOT relaxed, and the document bytes are the one place this
ruling is asymmetric. There the ceiling is **removed** from the authorization chain rather than
ORed into it: `read_document` keeps `status == "published"` and `has_capability` exactly as they
are, so an APPROVED, unexpired, capability-matched grant is still the only thing that opens a
document. ORing `documents_disclosed` in there would rebuild an incident this codebase has already
had once — one ceiling flag flipped, every signed-in member downloading a seller's financial packet
(`tests/api/test_listing_assets.py::test_a_non_owner_member_cannot_read_a_document_however_disclosure_and_status_are_set`
is that incident's own pin and still passes unchanged). What DOES change for documents is the
TITLES: `app/api/listings.py::_documents` no longer returns `[]` for a locked listing, because
hiding the titles made §17's own preserved copy ("Buyers see the document titles and can ask for
access") describe a screen the server could not produce.

§7's two-buyer test and §21's acceptance matrix are unchanged as REQUIREMENTS and move house as
FIXTURES: they are now exercised on a listing whose ceilings are SHUT, because that is where a
per-buyer grant is the whole answer. On a ceiling-open listing Buyer B is no longer "redacted" —
the seller published to them on purpose.

---

## AMENDED 2026-09-24 — RULING D-C67: THE SELLER CHOOSES WHICH CAPABILITIES, PER BUYER

**John, 2026-09-24, verbatim: "all toggles must be fully functional and SELLER must be able to
manage it all and per seller."** Ruled the same day as D-C66 above and read with it: D-C66 makes
the ceilings releasable, and this gives the seller the control that chooses WHAT a given buyer
receives.

**What D-C66 left, measured.** Every access request is created `FULL_CONFIDENTIAL`
(`app/api/requests.py`; the interest modal sends no level), the seller inbox's "Share more" passed
no level to `decide`, and `decide` fell back to the requested one. So the day D-C66 made the grant
live, ONE CLICK of Accept released the practice name, the street, the postcode, the telephone, the
exact map pin, the unredacted photographs, the financial packet and the floor plans together — and
the seller could not release less.

**What §16 below could not express, and this amends.** That section models disclosure as one named
LEVEL per grant, and §18 states authorization as `listing_id + buyer_user_id + disclosure_level +
status`. Implemented faithfully, `request.approved_disclosure_level` held exactly one of six
values — so six of the thirty-two subsets of the five capabilities were storable and the other
twenty-six, the empty one included, were not. The product's own accepted-row sentence, "You released
the financial packet and floor plan to this buyer.", describes a grant of TWO that no column could
hold. **The grant is a SET of capabilities.** `migrations/097_request_approved_capabilities.sql`
replaces that column with `approved_capabilities text[]`; §16's six names are unchanged and
`FULL_CONFIDENTIAL` keeps its meaning as the umbrella a BUYER may ask for, never a capability a
grant stores. §18's own sentence reads `disclosure_level` as the set from here.

**FAIL CLOSED is where the risk of this amendment lives, and §19 is strengthened again.** An
approval that names NO capability grants NOTHING — never everything. The empty set is a real,
stored decision (`'{}'`, distinct from the `NULL` of a row with no decision at all) and
`app.disclosure.levels.granted` has no default arm to fall through to. The tempting bug is a falsy
test on the chosen set collapsing to the requested level; the API refuses an explicit `null` for
the same reason rather than reading it as "absent".

**Narrowing is part of the control, not a second feature.** `decide`'s approve arm accepts an
already-APPROVED row, so a seller who released three capabilities can release one without
withdrawing the buyer's access entirely and making them ask again. §15 (revocation) is unchanged:
ending access altogether is still `revoke`, with its own status, audit action and mail.

**ONE THING THIS AMENDMENT DOES NOT DO, recorded rather than left to be found.** A narrowing sends
the buyer NO notification. D-C62's own ruled sentence covers access that "opens, closes or is
refused" and names no fourth case; `access_approved` reads "Sign in to see what is newly
available", which is false of a narrowing, and `access_revoked` reads "has ended your previously
approved access", which is false of a grant that still carries three capabilities. A
narrowed-access notification is NEW COPY and is John's to rule on. The outbox's own idempotency key
(`<request_id>:<template>`) is what makes the second decision silent rather than wrong.

---

Do NOT rewrite the five pieces of copy to describe a global disclosure switch.

The product is a permissioned veterinary-practice marketplace in which a seller controls
disclosure of confidential listing information to individual buyers.

The current global switch is an implementation gap and must be replaced/extended to support
the promised per-buyer approval model.

## 1. REQUIRED PRODUCT BEHAVIOR
A seller listing begins in a protected/redacted state. A buyer can: discover the listing; view
the permitted public/redacted information; express interest; request access to additional
confidential information. The seller receives the buyer's access request. The seller can approve
or deny that specific buyer. Approval applies ONLY to that buyer. Approval MUST NOT globally
disclose the information to all buyers.

## 2. DISCLOSURE LEVELS
Preserve the existing disclosure model.
Public/default: generalized listing information; permitted market information;
approximate/generalized location; redacted listing images; other explicitly public content.
Seller-approved confidential information may include: exact practice identity; exact location;
unredacted listing images; financial packet; floor plans; detailed practice information; other
seller-designated confidential documents.
Do not expose confidential information merely because the listing exists.

## 3. ACCESS CONTROL MODEL
Create an explicit buyer/listing authorization relationship. Conceptually: listing, buyer,
access_request, access_grant, disclosure_level. The authorization must be evaluated against BOTH
the listing AND the authenticated buyer. A listing-level global boolean must NOT be sufficient to
authorize confidential disclosure.

> **SUPERSEDED IN PART by D-C66 (2026-09-24), for the three listing-level ceilings
> `name_disclosed`, `location_disclosed` and `rev_disclosed` only.** A ceiling the seller has left
> OPEN now IS sufficient, because leaving it open is the seller publishing that field — the
> sentence above was read as "a shut ceiling also blocks a grant", which made approval release
> nothing. The authorization is still evaluated against BOTH: the listing says what is public and
> the grant says what else THIS buyer gets. For document BYTES the original sentence stands
> unchanged and is if anything stricter — see §10 and the amendment note at the head of this file.

## 4. ACCESS REQUEST TABLE
Create the necessary persistent data model. At minimum support: access_request_id, listing_id,
buyer_user_id, seller_user_id, requested_at, status, reviewed_at, reviewed_by, denial_reason where
applicable, approved_disclosure_level, expires_at where applicable, created_at, updated_at.
Statuses should distinguish at minimum: PENDING, APPROVED, DENIED, REVOKED.
Use the existing Practice Match database conventions rather than creating an unrelated persistence
architecture.

## 5. SELLER WORKFLOW
Seller dashboard must provide a buyer-access area. For each request show: buyer identity; request
date; listing; requested disclosure level; current status; approve action; deny action; revoke
action when already approved. Seller approval must be explicit. Do not automatically approve buyers.

## 6. BUYER WORKFLOW
Before approval: buyer sees only information authorized for public/redacted access, and may request
additional information. After seller approval: buyer sees ONLY the disclosure level explicitly
granted to that buyer. Another buyer who has not been approved must continue seeing the
redacted/public version.

## 7. CRITICAL SECURITY TEST
Create two test buyer accounts: BUYER A, BUYER B. Seller approves BUYER A.
Expected: BUYER A receives the approved confidential information; BUYER B continues receiving the
redacted/public information. **This test MUST pass.** If BUYER B can see the confidential
information after BUYER A is approved, the implementation is incorrect.

## 8. GLOBAL SWITCH
The existing global SHOW/NOT SHOW functionality must NOT be used as the authorization mechanism for
buyer-specific confidential disclosure. Determine what the existing global switch currently
controls. If it controls publication/redaction of listing assets, preserve that functionality where
appropriate. However: **GLOBAL VISIBILITY is NOT BUYER AUTHORIZATION.** Separate these concepts.

> **SUPERSEDED IN PART by D-C66 (2026-09-24).** Global visibility is not buyer authorization and
> never becomes it — but under D-C66 it is not its OPPOSITE either. An open ceiling is a decision
> to publish; a shut one is a decision to wait for an approval, not a veto over one. The two
> concepts stay separate and are now combined with OR rather than AND.

## 9. IMAGE DISCLOSURE
Preserve the existing requirement: all uploaded listing images default to NOT SHOW. Original assets
remain private. Buyers receive only the appropriate redacted derivative until disclosure is
authorized. Seller authorization must be enforced server-side. If a seller authorizes unredacted
images for Buyer A: Buyer A may receive the authorized version; Buyer B must continue receiving only
the permitted redacted version. Direct access to the original asset URL must NOT bypass
authorization.

## 10. FINANCIAL DOCUMENTS
Apply the same authorization model to financial packets, financial statements and supporting
financial documents. Do not expose the original/private document merely because the buyer knows its
URL. Every document request must verify: authenticated user + listing + buyer-specific disclosure
authorization + authorized disclosure level.

## 11. EXACT LOCATION
Exact location is confidential unless explicitly authorized. The public listing may use generalized
location, market area, city/region, approximate map representation. After seller approval for Buyer
A: Buyer A may receive the authorized exact location; Buyer B must continue seeing only the
public/generalized location. Do not expose exact coordinates through an unauthenticated API response
even if the frontend hides them.

> **SUPERSEDED IN PART by D-C66 (2026-09-24), and NARROWLY — this section keeps more than the
> other three.** What changes is the ADDRESS: a seller who leaves the `anon` ceiling open is
> publishing the street, the postcode and the telephone number to every signed-in buyer, and a
> seller who shuts it releases those three to a buyer they approve. What does NOT change is the
> sentence's own subject. **Exact COORDINATES still require the grant, in every case**: the middle
> tier this section asked for — a released listing serving an ungranted buyer a point rounded to 2
> decimal places, about 1.1 km — stands exactly as built on 2026-09-19, and `app/api/listings.py`
> now reads `ceiling = location_disclosed OR the grant` (is there a pin at all) beside
> `exact = the grant alone` (how precise it is), which are two questions and not one.
>
> That split was got WRONG once and the record is kept rather than tidied: the first pass of
> D-C66's own task collapsed the two into one expression, deleting this tier, and the controller
> overruled it the same day (fix round 1). **The reason the tier stands is the ruling's own scope**
> — D-C66 asked that a ceiling become releasable per buyer, it did not ask that an ungranted buyer
> be shown a finer point than before, and a change that widens disclosure past what its ruling
> asked for is out of scope by construction. A second reason was offered at the time and is WRONG:
> that the tier matters most for a listing whose `street` is NULL, the pin being its only location
> signal. Measured, such a listing is not pinless — `app/census/geocode.py` falls back to the ZCTA
> centroid, and then to the place or county centroid, for exactly the city-and-ZIP listing a real
> seller creates. That argument is recorded here, and in `app/api/listings.py::_point`, so nobody
> reinstates it. `tests/api/test_geo_wire.py` carries the same note.
> The second half of this section — Buyer A approved, Buyer B still public — is unchanged.

## 12. API SECURITY
This must be enforced server-side. Do NOT rely on hidden frontend fields, CSS, disabled buttons,
JavaScript-only checks, client-side route guards or obscured URLs.
For every confidential resource request: (1) authenticate user; (2) identify buyer; (3) identify
listing; (4) retrieve buyer/listing authorization; (5) verify authorization status; (6) verify
disclosure level; (7) return only authorized content. Otherwise return an appropriate authorization
response.

## 13. ROUTES
Audit the existing routes and add the minimum required routes for:
Buyer: POST access request; GET request status.
Seller: GET incoming requests; POST approve; POST deny; POST revoke.
Confidential content: GET authorized listing details; GET authorized images; GET authorized
documents.
Use the application's existing API conventions. Do not expose a route that returns confidential
listing information without performing the authorization check.

## 14. AUDIT LOG
Record important disclosure events. At minimum: access requested; access approved; access denied;
access revoked; confidential image viewed/downloaded where the existing audit model supports it;
confidential document accessed; exact-location disclosure; financial-document disclosure.
Store: user, listing, action, timestamp, disclosure level, relevant resource.
Do not log confidential document contents unnecessarily.

## 15. REVOCATION
Seller must be able to revoke a previously granted buyer's access. After revocation, Buyer A must
immediately lose authorization to retrieve the confidential resource through protected APIs. Do not
rely solely on frontend state. Previously downloaded files cannot technically be recalled; do not
claim otherwise. The system must prevent subsequent authorized retrieval.

## 16. DISCLOSURE LEVELS
Implement disclosure as explicit permissions rather than one giant boolean. For example: PUBLIC,
IDENTITY, EXACT_LOCATION, UNREDACTED_IMAGES, FINANCIALS, FLOOR_PLANS, FULL_CONFIDENTIAL.
Use the actual Practice Match terminology if equivalent concepts already exist. Do not create
redundant permission systems.

> **AMENDED IN PART by D-C67 (2026-09-24): a grant is a SET of these, not one of them.** The names
> above are unchanged and no new permission system is created — the amendment is only that
> `request.approved_capabilities` (migration 097) holds however many of the five the seller chose,
> including none, where `approved_disclosure_level` held exactly one of six. `FULL_CONFIDENTIAL`
> keeps its place as the umbrella a BUYER may request and `app.disclosure.levels.covers()` keeps
> mapping it to the five; it is never stored as a capability, because a stored umbrella would be a
> second spelling of a set the array already states plainly.

## 17. COPY
The existing five pieces of copy promising buyer-specific disclosure are CORRECT. Preserve them or
make only the minimum wording changes necessary to accurately describe the implemented workflow.
The product promise should remain conceptually: seller approval of a buyer controls disclosure to
THAT BUYER. Do not change the copy to imply "Once the seller enables disclosure, everyone can see
it."

## 18. DATA MODEL INTEGRITY
Do not create a global field such as `listing.confidentiality_approved = true` and use that as the
sole authorization mechanism. Authorization must include the buyer identity. Conceptually:
`listing_id + buyer_user_id + disclosure_level + status` must determine authorization.

> **AMENDED by D-C67 (2026-09-24) for the third term alone.** `disclosure_level` is the SET of
> capabilities the seller released to this buyer (`approved_capabilities`, migration 097). Every
> other term, and the rule that authorization must include the buyer identity, is unchanged.

> **SUPERSEDED IN PART by D-C66 (2026-09-24), for this section's FIRST sentence alone.** No such
> field was created; the pre-existing per-field ceilings are what that sentence was implemented
> against. Under D-C66 an OPEN ceiling is a sufficient authorization for the three fields it names,
> because it is a publication decision rather than an authorization record. What the sentence
> forbids — a global flag standing in for a buyer's own grant, so that ONE switch discloses to
> everyone something the seller meant to release to one person — is still forbidden, and is exactly
> why the document bytes route keeps its grant and drops its ceiling instead.
>
> The rest of this section is UNTOUCHED and remains binding: "Authorization must include the buyer
> identity. Conceptually: `listing_id + buyer_user_id + disclosure_level + status` must determine
> authorization." D-C66 widens what the LISTING publishes; it takes nothing out of what an
> authorization record has to be.

## 19. FAIL CLOSED
If authorization cannot be determined: DENY ACCESS. Never assume approval, default to public
confidential data, return original assets, expose exact coordinates or expose financial documents.
A missing authorization record means NOT AUTHORIZED.

## 20. EXISTING IMAGE SECURITY
Preserve the existing image architecture: NOT SHOW by default; all uploaded images remain protected;
redacted derivatives are the buyer-facing default; seller confirmation is required before
disclosure. Server-side authorization must determine which derivative/version a buyer receives. Do
not expose the original storage path through frontend configuration.

## 21. ACCEPTANCE TEST MATRIX
```
                 Buyer A       Buyer B
No approval       REDACTED      REDACTED
A approved        APPROVED      REDACTED
A revoked         REDACTED      REDACTED
B approved        REDACTED      APPROVED
Both approved     APPROVED      APPROVED
```
Also test: unauthenticated user → public information only. Authenticated buyer without approval →
public/redacted only. Buyer with partial approval → only approved disclosure level. Seller → may
manage access for their own listings. Buyer A cannot manipulate IDs to obtain Buyer B's
authorization. Buyer A cannot alter listing_id to obtain another listing's confidential data. Direct
asset URL without authorization → denied.

## 22. IDOR / AUTHORIZATION TESTING
Explicitly test for insecure direct object references. Attempt: Buyer A requesting Buyer B's access
record; Buyer A requesting another listing's confidential resource; Buyer A modifying another
buyer's request; Buyer A changing listing_id in a confidential-resource request.
Expected: ALL DENIED.

## 23. PERFORMANCE
Do not introduce a database query explosion. Authorization checks should use indexed fields such as
listing_id, buyer_user_id, status. Add appropriate indexes and constraints.

## 24. MIGRATION
Inspect existing global visibility fields. Do NOT simply delete them. Determine whether they are
still required for publication, image redaction, seller confirmation or listing-level default
visibility. If they remain useful, retain them for their correct purpose. Add buyer-specific
authorization alongside them.

## 25. FINAL IMPLEMENTATION REQUIREMENT
This is not a copy-editing task. Implement the actual product behavior promised by the existing
copy. The final system must demonstrate:
Seller creates listing → listing is public/redacted → Buyer A requests confidential access → seller
reviews request → seller approves Buyer A → Buyer A receives authorized disclosure → Buyer B remains
redacted → seller can revoke Buyer A → Buyer A loses subsequent access.
The authorization must be enforced server-side.

## 26. FINAL REPORT
After implementation report: (1) existing global disclosure implementation; (2) new buyer-specific
authorization model; (3) database tables/fields added; (4) routes added/changed; (5) server-side
authorization points; (6) image authorization behavior; (7) financial-document authorization
behavior; (8) exact-location authorization behavior; (9) approval/rejection/revocation workflow;
(10) audit logging; (11) migration handling for existing listings; (12) automated tests; (13)
two-buyer isolation test results.

**Do not tell me that the copy should be rewritten to match the existing global switch.
The intended product is PER-BUYER DISCLOSURE. Build the subsystem required to make the existing
product promise true.**
