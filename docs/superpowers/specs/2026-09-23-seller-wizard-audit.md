# Audit — the seller "Create a listing" wizard, all eight steps

**2026-09-23, commissioned by John** after a walkthrough on QA surfaced three defects in three
consecutive steps. Four independent auditors covered steps 1–2, 3–4, 5–6 and 7–8, each required to
establish per control: what the UI promises, what is collected, what is stored, what is served to a
buyer, and whether validation matches. Every finding carries `file:line`. **No fixes are proposed —
this establishes what is true so the scope can be ruled.**

The wizard has never had the end-to-end treatment D-C53 gave the admin tabs. This is that pass.

---

## 1. The pattern

Across all eight steps one shape recurs: **a privacy control promises a redacted VIEW, and the
implementation only ever WITHHOLDS.** The data behind it is either never collected, never served,
or served to nobody regardless of approval. Around that sit three smaller families — data fabricated
on the buyer's screen, capability built and left unreachable, and fields with no validation at any
layer.

---

## 2. Severe — a seller is told something false about their own listing

**S1. Three of four step-7 toggles are labelled for the state they do not produce.**
`anon` and `revBand` are labelled "…until I approve a buyer" (`frontend/src/logic.js:1758`, `:1759`).
Turning them ON closes the ceiling, and `app/api/listings.py:502,508,556` ANDs every ceiling with the
per-buyer capability. A grant never writes a ceiling — the only runtime writers are the wizard's own
`columns_for` (`app/api/seller_listings.py:339,341,343,349`) — so **ON means hidden from everybody,
permanently; approval changes nothing.** Meanwhile OFF already delivers what the ON label promises,
because an unapproved buyer's capability set is empty (`app/disclosure/access.py:32-38`). The labels
are attached to the wrong switch position.

**S2. Submit reports success when the server refused.** `frontend/src/logic.js:1838-1840` uses
`promise && this.setState(...)`; a Promise is always truthy, so the state change runs unconditionally
and synchronously. **Proved by running the real `logic.js` against a rejecting adapter**: the seller
lands on "Submitted — Your listing is with the VIN Foundation" while the refusal text is computed
into a slot the `isDone` template never renders (`frontend/src/App.vue:1364-1376`), and a fabricated
`in_review` row persists in their dashboard because `reloadListings()` never runs on the failure path.
Every server refusal is affected — `INCOMPLETE`, `PHOTOS_NOT_READY`, `409 STATE`, rate limits.
`frontend/src/logic.test.ts:3552` asserts the computed value and passes; the slot is unrendered.

**S3. No revenue range exists anywhere in the product.** `"$2M – $2.5M"` (`logic.js:1753`) is literal
help text and occurs exactly once. `app/api/listings.py:557` serves `None`; `money(null)` renders
`"—"`. With the toggle ON the exact figure is released to **nobody, ever**. With it OFF the figure
still needs a `FINANCIALS` grant. Both states are mislabelled, and the step-8 preview repeats the
false promise to the seller ("Range shown to buyers", `logic.js:1828`).

**S4. Step 2 promises "an approximate map pin"; the ON state draws no pin at all.** `anon` defaults ON
(`logic.js:263`, `:1474`). `_point` returns `None` for both coordinates when the ceiling is shut
(`app/api/listings.py:447-452`), and `md.practices` drops any listing without a finite point
(`logic.js:819`). The practice is **absent from the map entirely** while remaining in the results rail.
The approximate point the copy describes does exist server-side, on a route the buyer client never
calls (`app/api/market.py:621-623`).

---

## 3. Severe — a buyer is shown data that does not exist

**S5. "Parking: On-site" is a hard-coded literal on every listing.** `frontend/src/logic.js:1932`.
No field, no column, no question — `parking` appears nowhere in `migrations/`, `app/api/` or
`frontend/src/listings/`.

**S6. A row labelled "Facility type" is computed from a different field.** `logic.js:1930` reads
`bldg`, not `facility_type`. A seller answering "Medical park", "Strip or plaza" or "Other" is
published to buyers as **"Standalone building"**. `facility_type` is collected, validated and stored
(`migrations/030:27`) and appears in no `_SELECT` in `app/api/listings.py`.

**S7. The buyer's document list is four fixtures.** `logic.js:1891-1896` renders "Exterior and
interior photos", "Floor plan", "Three-year financial summary", "Equipment list" regardless of what
was uploaded. The API's real `documents[]` has no frontend reader, and the route that computes it
(`GET /api/listings/{id}`) is never called — the app fetches only the list route
(`frontend/src/listings/load.ts:22`). **`docsLocked` therefore changes no pixel a buyer sees**, and
its help text ("Buyers see the document titles and can ask for access") is false in the ON state,
where `_documents` returns `[]` before querying (`app/api/listings.py:412-413`).

**S8. Step 4 prints the word `null` to buyers.** No validation exists at any layer for step 4, and
four fields are string-concatenated: `"null full-time equivalent"` (`logic.js:1886`), `"null FTE"`
(`:1920`), `"null doctors"` (`:824`, `:2504`), `"null."` (`:1918`). `sqft` is protected only because
migration 034 was written after it crashed Browse.

---

## 4. Severe — privacy promises the data cannot keep

**S9. `EXACT_LOCATION` delivers null.** `street` and `phone` are never collected by any step and
never written by any route — `app/api/seller_listings.py:128` says so outright, and the only writer
in the repository is `scripts/seed_listings.py`. An approved buyer receives `street: null`,
`phone: null` beside `location_disclosed: true`. The 2026-09-08 spec deferred "the exact-location
switch and the street field it needs" together (`:337`); the 2026-09-18 directive then shipped the
capability without the prerequisite. **Unclosed prerequisite, not a deliberate no-op.** What the grant
actually delivers is coordinates that stop being rounded — to a **ZIP-code centroid**
(`app/census/geocode.py:289,432-435`).

**S10. Free text defeats the anonymity the same wizard promises.** `services` and `hours` are served
to every member with no ceiling and no capability term (`app/api/listings.py:601`, `:556`) — the only
fields on either step with no gate. The image-identifiability spec feeds those same strings into the
token matcher that scrubs signage from photographs
(`docs/superpowers/specs/2026-09-09-image-identifiability-protection-design.md:236`). **The product
redacts these words from images while publishing them as prose.** No ruling exists.

**S11. A hidden revenue silently becomes "Under $1M".** `logic.js:1463` computes `p.rev / 1000`, and
`null / 1000` is `0`. A listing whose revenue the seller chose to hide is **not** excluded from the
*Gross revenue: Under $1M* filter — it is shown inside it. An inference leak created by the redaction.

---

## 5. Built and unreachable

**U1. Photo management.** A complete backend exists — `reorder_photos`
(`app/api/seller_listings.py:1307`, row-locked, permutation-checked, rate-limited, audited, tested)
and `delete_asset` (`:1520`), both typed and implemented in the adapter
(`frontend/src/listings/seller.ts:427-428,530-531`). `logic.js` calls nine adapter methods; neither is
among them. **Zero callers outside their own unit tests.**

**There is no "cover photo" by name — ten literal-string history searches return zero commits — but
the concept is live**: `heroSrc = photos[0]`, `thumbSrc = photos[1] || photos[0]`
(`logic.js:1243,1248`), over an ordered `photos jsonb` array (`migrations/016:46`) whose migration
states there is deliberately no `position` column because "two homes for one fact is how orders
drift" (`031:9-12`). **Reordering that array is choosing the cover.** Nothing in the product can.

This is a documented deferral, not drift: `docs/decisions/2026-09-05-image-slot-editor-removed.md`
records John removing the design tool's editor and promises "Permissioned photo management … replaces
the design tool's editor entirely"; the missing controls are named at
`docs/superpowers/specs/2026-09-08-seller-listing-lifecycle-design.md:209,346` and
`docs/superpowers/plans/2026-09-08-seller-listing-lifecycle.md:2032`. The server half was built; the
UI half never was.

**U2. Step 6 offers exactly one action per photograph** — `window.prompt('What does this photograph
show?')` (`frontend/src/listings/seller.ts:461`), never anything richer (`git log -S` returns the one
commit that introduced it). No delete, no reorder, no set-as-cover, no per-tile menu. "Drag photos and
documents here" is a false promise — no drop handler exists anywhere. "Add files" picks **one** file
per click (`seller.ts:546-553`, no `multiple`).

**U3. Three more built-and-unread**: `facility_type` (stored, never served), `documents[]` (computed,
no reader), `geo_precision` (served, no reader) — the last is load-bearing, because
`docs/integrations/market-data-api.md:860` requires an "approximate community data" caption near the
pin and **that caption does not exist**, while every real seller listing resolves at ZIP precision.

**U4. The "Review" pill is a dead end.** `openPhotoReview` is never defined, its amendment A20.10 was
never written, and `app/privacy/record.py:378`'s `confirm()` — the only writer of `SELLER_CONFIRMED` —
has zero callers in `app/`. Read end to end this blocks submission under the default `NOT_SHOW`.
**NOT YET VERIFIED LIVE, and QA evidence cuts against it**: QA holds 27 published and 2 in_review
listings at `NOT_SHOW`. Needs a click-through before it is reported as user-facing.

---

## 6. No validation

- **Step 4: none at any layer.** `docs`, `rooms`, `hours`, `services` can all be NULL on a published
  listing (`seller_listings.py:177`; `_complete_enough` adds only `sqft`).
- **`zip` accepts `banana`** — truthiness client-side, `_text` server-side, no CHECK in the schema
  (`migrations/016:16`). A nonsense ZIP silently places the practice at a city centroid with no error.
- **`est` accepts year 7 and year 999999999** — the only bound is `INT_MAX`
  (`seller_listings.py:237`).
- **"Doctors (full-time equivalent)" cannot hold a fractional value** — `integer` column plus
  `isdecimal()` refuses `2.5`, the exact case the phrase exists for. A null `docs` then removes the
  listing from every doctors filter, because `null < 3` is `true` in JS (`logic.js:1439`).
- **The step rail bypasses the client guards entirely** (`logic.js:1796-1800`); the server catches it
  at submit, so this is UX inconsistency rather than a data hole.

---

## 7. What is correct

Recorded so the picture is not only negative.

- **The step-field whitelist is total, one-directional and pinned two-way.** A field from another step
  is a 400, never a silent no-op (`seller_listings.py:316-318`); `step-fields.json` is one data file
  both sides read.
- **Disclosure is enforced server-side in one place.** `serialise` is the only row→payload function,
  and the ceiling and the grant are ANDed rather than merged — `app/disclosure/access.py` explicitly
  forbids collapsing them. Fail-closed defaults hold throughout: capabilities default to the empty
  set, every ceiling column defaults to hidden.
- **`showIdentifiable` is a genuine per-buyer gate** — the one toggle of the four that works as
  advertised, with the safe state as its default (`migrations/040:4`).
- **The `revBand → rev_disclosed` polarity inversion is correct, documented and round-trips**
  (`seller_listings.py:341`, `:534`, `migrations/030:31`). The defect is downstream, not here.
- **Submit's server-side validation is sound and correctly ordered** — required columns, then the
  price/revenue pair, then `sqft`, then photographs, so a listing missing a price is never told it is
  waiting for a photograph (`seller_listings.py:1721-1773`). Everything wrong with Submit is client-side.
- **Every door out of the wizard saves first** — Continue, Back, the rail, header nav and Sign out.
- **The unbuilt photo routes are well built** — `reorder_photos` refuses a partial list because "a
  partial list would silently DELETE photographs"; `delete_asset` drops the object before the row,
  inside the transaction.
- **The privacy gate cannot be bypassed** — enforced at the route and by a database trigger calling
  the same SQL function (`migrations/042:22-32`).
- **The app never shows the design's fixtures** — the adapter-presence ternary renders the fetched
  draft or nothing.
- **The step-1 name promise holds** — "Never shown to buyers until you approve a request" is true even
  with `anon` OFF, by construction (`listings.py:504`).
- **No port drift** — the step-1 and step-2 configs are byte-identical between the approved design and
  the shipped script.

---

## 8. Two things this audit did not settle

1. **U4 (submit blocked by the photo-review gate)** is a static code reading. QA's 27 published and 2
   in_review `NOT_SHOW` listings suggest it does not bite universally. One click-through settles it.
2. **Whether any of this is drift or deferral.** Much of §5 is explicitly recorded as Rev 3 work in
   specs written at the time. The audit establishes the state; it does not judge which gaps were
   ruled and which were forgotten. That distinction is John's, and it decides the scope of any fix.
