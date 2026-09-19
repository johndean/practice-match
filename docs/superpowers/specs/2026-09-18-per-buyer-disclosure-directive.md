# PRACTICE MATCH — DECISION: PER-BUYER DISCLOSURE IS THE INTENDED PRODUCT

**John, 2026-09-18. Recorded verbatim. This is the ruling on the wizard audit's Question 3
("Is per-buyer disclosure the real product?") and it overturns the cheaper option the
controller offered — rewriting the copy to describe the global switch. It does NOT.**

The intended Practice Match product behavior is CONFIRMED: **PER-BUYER DISCLOSURE.**

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
