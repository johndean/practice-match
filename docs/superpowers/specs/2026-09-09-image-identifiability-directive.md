<!-- John's implementation directive, 2026-09-09 ~15:30 WITA, verbatim and unedited. It is the
     source of `2026-09-09-image-identifiability-protection-design.md` and of
     `../plans/2026-09-09-image-identifiability-protection.md`. Section 23 forbids a claim this
     file itself quotes in order to forbid it, which is why `tests/test_docs.py`'s copy test
     exempts this path by name. -->

# IMPLEMENTATION DIRECTIVE (John, 2026-09-09 — verbatim)
## Automatic Image Identifiability Protection — SHOW / NOT SHOW

You are implementing a production-grade privacy/de-identification system for the marketplace image-upload workflow.

DO NOT redesign the product.
DO NOT introduce unnecessary UI complexity.
DO NOT ask me to manually perform technical privacy checks.
DO NOT implement a partial version.
DO NOT stop after creating the UI.
DO NOT assume that scanning one image is sufficient.

The implementation must be complete across the ENTIRE image-upload lifecycle.

==================================================
1. CORE PRODUCT BEHAVIOR
==================================================

Every image uploaded to a listing MUST pass through the identifiability-processing pipeline.

The seller should have ONE simple listing-level control:

    IDENTIFIABLE IMAGE CONTENT

    [ SHOW ]   [ NOT SHOW ]

Meaning:

SHOW
- Buyers are allowed to see identifiable content in uploaded images.
- Original image may be displayed to buyers, subject to all other marketplace rules.

NOT SHOW
- Buyers MUST NOT see identifiable hospital/practice content.
- The buyer-facing image MUST be the automatically redacted derivative.
- The original image MUST NEVER be exposed through the buyer-facing image URL, API response, thumbnail, gallery, download endpoint, metadata, cache, or alternate image representation.

DEFAULT:
    NOT SHOW

The safest privacy state is the default.

==================================================
2. CRITICAL REQUIREMENT: APPLY TO ALL IMAGES
==================================================

The SHOW / NOT SHOW setting applies to EVERY image associated with the listing.

This includes:

- primary image
- gallery images
- additional uploaded images
- reordered images
- replaced images
- newly added images
- images uploaded in multiple upload sessions
- images uploaded from mobile
- images uploaded from desktop
- images uploaded through API/import workflows
- edited/reprocessed images
- thumbnails
- responsive image derivatives
- preview images
- future images added after initial publication

There must be NO path through which an image can bypass privacy processing.

DO NOT implement:
    "scan the first image"

DO NOT implement:
    "scan images only when seller clicks NOT SHOW"

DO NOT implement:
    "scan images currently visible in the gallery"

ALL uploaded images must be scanned and processed.

==================================================
3. IDENTIFIABLE CONTENT DEFINITION
==================================================

When NOT SHOW is selected, identify and redact content that could reasonably identify the veterinary hospital/practice.

Detect at minimum:

TEXT
- hospital name
- veterinary practice name
- practice name fragments
- phone numbers
- street addresses
- websites
- domains
- email addresses
- social media handles
- QR codes where they resolve to identifying information
- business names
- branded slogans
- signage
- building directories
- certificates displaying practice identity
- business cards
- documents containing practice identity

VISUAL BRANDING
- hospital logos
- practice logos
- branded signage
- branded wall graphics
- branded uniforms
- branded vehicles
- branded equipment where the branding identifies the practice
- distinctive practice-specific graphics

CONTEXTUAL IDENTIFIERS
- exterior hospital signage
- street/building signage that identifies the location
- recognizable business directory information
- identifying documents
- combinations of otherwise innocuous clues that materially identify the hospital

The objective is NOT merely:

    "hide text"

The objective is:

    "prevent the buyer from reasonably identifying the hospital/practice from the image."

==================================================
4. DETECTION PIPELINE
==================================================

Implement a layered detection pipeline.

STEP 1 — Image validation
- validate file type
- validate dimensions
- normalize orientation
- normalize processing representation
- reject corrupt/unprocessable images
- preserve original immutable source

STEP 2 — OCR
Run OCR against EVERY image.

Capture:
- recognized text
- confidence
- bounding boxes
- page/image coordinates
- detected URLs
- phone numbers
- addresses
- email addresses

STEP 3 — Seller/listing identity matching
Compare OCR results against all known listing identity information, including:
- hospital/practice name
- alternate names
- abbreviations
- seller-provided practice name
- website/domain
- phone
- address
- city
- state
- other explicitly supplied identifying metadata

Support:
- exact matching
- case-insensitive matching
- punctuation normalization
- whitespace normalization
- OCR error tolerance
- partial matching
- common OCR substitutions
- abbreviation matching

STEP 4 — Vision-based analysis
Use an image-capable vision model where available to identify non-text visual identity signals.

The vision analysis MUST NOT replace OCR.

It supplements OCR.

STEP 5 — Identity risk aggregation
Combine:
- OCR results
- identity matching
- phone/address/URL detection
- visual branding detection
- logo detection
- signage detection
- contextual evidence

Produce a structured detection result.

==================================================
5. REDACTION
==================================================

For NOT SHOW:

Generate a buyer-safe derivative image.

Use irreversible/opaque redaction rather than relying solely on Gaussian blur.

The underlying identifiable pixels must not remain recoverable from the buyer-facing derivative.

Every detected identifying region must be represented by a redaction bounding box or polygon.

Where necessary, expand the redaction region sufficiently to prevent surrounding pixels from reconstructing the identifying information.

Do NOT crop away important image content unnecessarily.

Preserve:
- image dimensions/aspect ratio where possible
- useful veterinary/medical content
- visual quality
- composition

while removing identifying content.

==================================================
6. IMPORTANT: IMAGE-LEVEL STATUS
==================================================

Every image MUST have an explicit privacy-processing state.

Use a state machine such as:

UPLOADED
    ↓
PROCESSING
    ↓
SCANNED
    ↓
REDACTION_GENERATED
    ↓
READY_FOR_REVIEW
    ↓
SELLER_CONFIRMED
    ↓
PUBLISHED

Error states must also exist:

PROCESSING_FAILED
REDACTION_FAILED
REVIEW_REQUIRED
REPROCESS_REQUIRED

No image may silently fall through the state machine.

==================================================
7. LISTING-LEVEL PRIVACY STATE
==================================================

The listing must have a single authoritative setting:

    identifiable_content_visibility

Allowed values:

    SHOW
    NOT_SHOW

Default:

    NOT_SHOW

Do not create contradictory per-image privacy settings unless absolutely required by the existing architecture.

The listing-level setting is the authoritative buyer-facing policy.

==================================================
8. SHOW BEHAVIOR
==================================================

If:

    identifiable_content_visibility = SHOW

then:
- buyer may receive/display the original image
- image processing may still occur for detection/audit purposes
- the original remains the canonical source
- the UI must clearly communicate that identifiable content may be visible

IMPORTANT:

Selecting SHOW does NOT mean:
- skip scanning
- skip processing
- skip audit logging
- skip validation

Every image is still processed.

==================================================
9. NOT SHOW BEHAVIOR
==================================================

If:

    identifiable_content_visibility = NOT_SHOW

then:

- buyer MUST receive the redacted derivative
- buyer MUST NOT receive the original
- buyer MUST NOT receive an original thumbnail
- buyer MUST NOT receive original image metadata that exposes identity
- buyer MUST NOT receive an original download URL
- buyer MUST NOT receive an original CDN URL
- buyer MUST NOT receive an original through an API response
- buyer MUST NOT receive an original through an alternate endpoint

The backend must enforce this.

Do NOT rely solely on frontend hiding.

==================================================
10. SELLER REVIEW
==================================================

After automatic processing, present a SIMPLE review experience.

Example:

    Identifiable content

    [ SHOW ] [ NOT SHOW ]

For NOT SHOW, show:

    We've automatically hidden information
    that could identify the hospital.

    Review your images before publishing.

Display the processed gallery.

The seller can:

    ✓ Looks good

or:

    + Hide something

The seller must be able to manually draw/select an additional redaction region if the system missed something.

Allow:
- add mask
- remove unnecessary mask where appropriate
- review every image
- navigate through all images

Do NOT force the seller to understand technical detection results.

==================================================
11. ZERO-BYPASS PUBLISHING GATE
==================================================

Publishing MUST be blocked until:

1. Every uploaded image has completed processing.
2. Every image has a valid privacy state.
3. If NOT_SHOW is selected:
   - every image has a buyer-safe derivative
   - every image is available for seller review
   - seller explicitly confirms the result
4. No image is in:
   - PROCESSING
   - PROCESSING_FAILED
   - REDACTION_FAILED
   - REVIEW_REQUIRED
5. The final listing privacy state is persisted server-side.

Never allow:

    AI_PASSED

to mean:

    READY_TO_PUBLISH

The seller confirmation is the final publication gate.

==================================================
12. BACKEND ENFORCEMENT
==================================================

The privacy rule MUST be enforced server-side.

Do not trust:
- frontend state
- browser state
- hidden fields
- JavaScript variables
- client-side image URLs

Every buyer-facing image request must resolve the authoritative listing privacy state.

Pseudo-rule:

IF listing.identifiable_content_visibility == NOT_SHOW
THEN return REDACTED_IMAGE_ONLY

IF listing.identifiable_content_visibility == SHOW
THEN return ORIGINAL_IMAGE

Never return both when NOT_SHOW is active.

==================================================
13. STORAGE ARCHITECTURE
==================================================

Maintain separate representations:

    ORIGINAL
    REDACTED

Original:
- private
- inaccessible to buyers
- not publicly indexed
- not exposed through client APIs
- retained according to existing retention policy

Redacted:
- buyer-safe
- CDN/public delivery permitted
- used for buyer gallery
- used for thumbnails
- used for previews
- used for downloads when NOT_SHOW is active

NEVER overwrite the original.

==================================================
14. CACHE / CDN / THUMBNAIL PROTECTION
==================================================

Audit every image delivery path.

Explicitly test:

- original image endpoint
- thumbnail endpoint
- responsive image endpoint
- CDN URL
- signed URL
- download endpoint
- gallery API
- listing API
- search results
- image preview
- social/share preview
- cached browser response
- preloaded image
- lazy-loaded image

When NOT_SHOW is active, every path must resolve to the redacted representation.

==================================================
15. TOGGLE UX
==================================================

Keep the UI extremely simple.

Preferred:

    Identifiable image content

    [ SHOW ] [ NOT SHOW ]

With:

    NOT SHOW
    Recommended

Do not expose:
- OCR controls
- AI confidence scores
- bounding boxes by default
- technical privacy settings
- model configuration
- API details
- redaction engine details

The complexity belongs behind the scenes.

==================================================
16. TOGGLE CHANGES
==================================================

If seller changes:

    SHOW → NOT_SHOW

the system must immediately require/verify that redacted derivatives exist for EVERY image.

If any image lacks a valid redacted derivative:

    block publication

and process the missing images.

If seller changes:

    NOT_SHOW → SHOW

do not delete the redacted derivatives.

Retain them for future switching back to NOT_SHOW.

If seller changes back:

    SHOW → NOT_SHOW

the system should be able to switch back without requiring unnecessary reprocessing if the redacted derivative is still valid.

==================================================
17. IMAGE ADDITIONS AFTER PUBLICATION
==================================================

This is a critical zero-gap requirement.

If:

    listing = NOT_SHOW

and seller uploads a NEW image after publication:

The new image MUST:

    upload
      ↓
    scan
      ↓
    detect
      ↓
    redact
      ↓
    review
      ↓
    confirm
      ↓
    become buyer-visible

The new image must NEVER temporarily appear to buyers in original form.

New images must default to:

    NOT PUBLISHED

until processing is complete.

==================================================
18. AUDIT TRAIL
==================================================

Persist an auditable record for each image:

- image_id
- listing_id
- original_asset_id
- redacted_asset_id
- processing_status
- processing_version
- OCR_detected
- detected_regions
- identity_matches
- redaction_regions
- detection_timestamp
- seller_review_status
- seller_confirmed
- seller_confirmation_timestamp
- seller_confirmation_user_id
- final_privacy_state

Do not store unnecessary sensitive data.

==================================================
19. FAILURE-SAFE DESIGN
==================================================

Privacy processing failures must fail CLOSED.

If processing fails:

DO NOT publish the original image when NOT_SHOW is selected.

Instead:

    PROCESSING FAILED
    → REVIEW REQUIRED
    → seller cannot publish affected image/listing

Never:

    processing failed
    → fallback to original
    → publish

That is prohibited.

==================================================
20. SECURITY REQUIREMENTS
==================================================

Audit the entire implementation for:

- IDOR
- unauthorized original-image access
- predictable asset URLs
- signed URL leakage
- API response leakage
- CDN leakage
- cached original images
- alternate image endpoints
- mobile API differences
- admin/user permission differences
- search-result image leakage
- thumbnail leakage
- download leakage

A buyer must never obtain the original image through an alternate route when NOT_SHOW is active.

==================================================
21. TESTING REQUIREMENTS
==================================================

Create automated tests covering at minimum:

A. One image + NOT_SHOW
B. Multiple images + NOT_SHOW
C. 50+ images + NOT_SHOW
D. SHOW
E. SHOW → NOT_SHOW
F. NOT_SHOW → SHOW
G. New image added after publication
H. Processing failure
I. OCR failure
J. Vision detection failure
K. Redaction failure
L. Seller adds manual redaction
M. Seller attempts publication before processing completes
N. Original URL requested directly by buyer
O. Original thumbnail requested directly by buyer
P. Original download endpoint
Q. CDN URL
R. API response
S. Mobile client
T. Desktop client
U. Cached image
V. Multiple upload batches
W. Image replacement
X. Image deletion/re-upload
Y. Listing duplication/draft cloning
Z. Unauthorized seller attempting to change privacy state

For every NOT_SHOW test:

ASSERT buyer receives REDACTED representation.

ASSERT buyer cannot access ORIGINAL representation.

==================================================
22. ACCEPTANCE CRITERIA
==================================================

The implementation is NOT COMPLETE unless ALL of the following are true:

[ ] One simple SHOW / NOT SHOW control exists.
[ ] NOT_SHOW is the default.
[ ] The setting applies to every image in the listing.
[ ] Every image is automatically scanned.
[ ] OCR is performed on every image.
[ ] Seller identity data is matched against OCR.
[ ] Visual identity detection supplements OCR.
[ ] Identifying regions can be automatically redacted.
[ ] Redaction is irreversible in the buyer-facing derivative.
[ ] Seller can manually add a redaction.
[ ] Seller reviews the processed gallery.
[ ] Seller confirmation is mandatory for NOT_SHOW.
[ ] Publishing is blocked until all images are ready.
[ ] Processing failures fail closed.
[ ] Original images remain private.
[ ] Redacted images are used for buyer delivery.
[ ] Buyer APIs cannot leak originals.
[ ] Thumbnail APIs cannot leak originals.
[ ] CDN cannot leak originals.
[ ] Download endpoints cannot leak originals.
[ ] Newly uploaded images cannot bypass the workflow.
[ ] SHOW/NOT_SHOW state is enforced server-side.
[ ] Audit records exist.
[ ] Automated tests cover all critical paths.
[ ] Existing image-upload functionality remains intact.
[ ] Existing listing functionality remains intact.
[ ] No duplicate privacy controls create contradictory states.

==================================================
23. DO NOT CLAIM 100% AI DETECTION ACCURACY
==================================================

Do NOT document or advertise:

    "AI guarantees 100% that the hospital cannot be identified."

That claim is technically unjustifiable.

Instead, engineer for:

    maximum automated detection
    +
    deterministic processing
    +
    seller visual confirmation
    +
    mandatory publication gate
    +
    fail-closed security

The objective is a zero-bypass workflow, not a false claim of perfect AI perception.

==================================================
24. IMPLEMENTATION PROCESS
==================================================

Before changing code:

1. Inspect the complete existing upload architecture.
2. Identify every image upload path.
3. Identify every image storage path.
4. Identify every image transformation path.
5. Identify every image delivery endpoint.
6. Identify every listing publication path.
7. Identify existing seller review flows.
8. Identify existing image/gallery components.
9. Identify existing authentication/authorization.
10. Identify existing tests.

Then produce:

    A. Current-state audit
    B. Gap list
    C. Exact implementation plan
    D. File/component/API changes
    E. Data-model changes
    F. Processing pipeline
    G. Security model
    H. Test plan

DO NOT begin coding until you have mapped the existing architecture.

Then implement the COMPLETE solution.

After implementation:

1. Run all existing tests.
2. Run all new privacy tests.
3. Test every upload path.
4. Test every image delivery path.
5. Test SHOW and NOT_SHOW.
6. Test multi-image listings.
7. Test failure conditions.
8. Test authorization/security.
9. Verify no original image can leak when NOT_SHOW is active.
10. Fix every discovered issue.
11. Re-run the complete test suite.
12. Perform a final zero-gap audit against every requirement in this prompt.

FINAL OUTPUT MUST INCLUDE:

- files changed
- database/schema changes
- APIs/endpoints changed
- processing pipeline implemented
- privacy state machine
- security controls
- tests created
- tests executed
- test results
- known limitations
- explicit confirmation that every upload path and every buyer image-delivery path was audited

Do not say "implemented" unless the code, tests, security controls, and publication gates have actually been verified.
