# Seller listing lifecycle — Design

**Status:** requested by John Dean 2026-09-08, after he opened Edit on a seeded hospital and found the wizard empty. Sub-project "Seller listing lifecycle" (Wave 2b). Decisions below apply as defaults unless John changes them. Numbered `D1`…`D24`; the design-bundle amendments this needs are the new family **A13**.

---

## 1. Purpose

John's finding, verbatim:

> "none of the existing Photes and Documents are being render4ed in the "EDIT" of an existing listing by hospital across all the data seeded on and also none of the actual inputs are appearing in the PREVIEW and SUBMIT, it appears to be stubs and not functional, this gap must be corrected and the UX true"

John's rulings of the same evening, verbatim, binding on everything below:

> **Storage:** Use object storage as the production architecture now; do not build a Postgres-bytea architecture intended for a later swap.
> **Ownership:** Assign all eighteen QA seed listings to `seller@practice-match.test`, with real `seller_id` ownership.
> **Documents:** Seller uploads immediately; preserve the existing staff/seller approval gating and 'Locked — seller approval' behavior. No new approval workflow in this slice.
> **Photos:** Keep the existing 4-photo seller-upload cap.
> **Published edits:** Editing a published listing re-enters review and removes it from the market until approved again, consistent with the approved design.
> **Release:** Ship seller-wizard read + write capability together. Do not release a read-only intermediate 'Edit shows the truth' feature.

And his standing rule for the admin surface: **every Admin tab shows real database data, never dummy rows.**

The gap is not the copy and not the screens. The eight wizard steps, the preview card, the "Saved automatically" promise, the submitted card and the seller dashboard's Continue/Edit/Pause/Republish/Withdraw/View actions are all approved design and all stay exactly as drawn. The gap is that nothing behind them persists. This spec is the persistence.

**In scope:** listing ownership; the draft → in_review → published lifecycle including the declined and withdrawn ends; a write API for the wizard; photo and document upload on object storage; the preview rendered from the real draft; submit; the review queue behind Admin › Listings; the seller dashboard reading the seller's own listings; the eighteen seeded hospitals owned by the seller persona.

**Out of scope:** §13.

---

## 2. What is true today

Every line quoted here is **design**, ported byte-for-byte through the D15 engine — `frontend/src/logic.js` is the bundle's own `<script data-dc-script>` block and `frontend/tests/app-generated.test.ts` pins it byte for byte (its "logic.js is the design script block, ported verbatim" block). So none of it can be hand-edited; §9 is how it changes.

**2.1 The wizard binds, but to nothing that outlives the tab.**
`state.w` (`frontend/src/logic.js:204`) is the whole model: `{ name, type, est, city, zip, anon, price, rev, revBand, docs, rooms, sqft, bldg, facility, desc, photos, ownership, hours, facilityType, docsLocked }`. `setW` (`:1159`) is a real two-way binding — `App.vue:1165`'s `:value="(fd?.value) ?? ''" @input="fd?.set"` is a live handler, and `app.setup.js:64` makes `state` reactive — so typing *does* move the preview within one visit. Nothing writes it anywhere.

| Step | Title | Fields | Where | Persisted |
|---|---|---|---|---|
| 1 | Practice basics | `name`, `type`, `est`, `ownership` | `logic.js:1174` | no |
| 2 | Location and privacy | `city`, `zip`, toggle `anon` | `:1175` | no |
| 3 | Financials | `price`, `rev`, toggle `revBand` | `:1176` | no |
| 4 | Practice details | `docs`, `rooms`, `sqft`, `hours`, `desc` | `:1177` | no |
| 5 | Property | `bldg`, `facilityType`, `facility` | `:1178` | no |
| 6 | Photos and documents | — | `:1179`; the strip is a literal, `:1188` | no |
| 7 | Disclosure settings | toggles `anon`, `revBand`, `docsLocked` | `:1180–1183` | no |
| 8 | Preview and submit | reads `w` | `:1221–1232` | no |

**2.2 Edit and Continue never load anything.** Both handlers are `setState({ sellerView: "wizard", step: 1 })` and nothing else — Continue at `logic.js:1130`, Edit at `:1131`. `w` stays at its empty initial value, so every `w.x || "—"` in `previewRows` (`:1221–1232`) renders an em dash. That is John's screenshot exactly.

**2.3 Step 6 is a literal.** `const uploads = [{ kind: "Photo", name: "Exterior.jpg" }, …].slice(0, 3 + (w.photos || 0))` (`logic.js:1188`); `w.photos` is a counter capped at 1 by `addPhoto` (`:1201`), and "Add files" is `@click="v.wiz?.addPhoto"` (`App.vue:1203`). There is no `<input type=file>`, no `File`, no `FormData`, no upload route, no storage. The tiles are drawn at `App.vue:1206–1211` and render `kind` and `name` only — no `<img>`.

**2.4 Submit is an array push.** `logic.js:1236` sets `wizSubmitted: true` and prepends one synthetic row to `state.sellerListings`. No network call. The footer promises "Saved automatically" (`:1210`, rendered at `App.vue:1223`) and the submitted card promises "You can keep editing while it waits; edits after publication go through the same short review" (`App.vue:1259`). Neither promise is kept by anything.

**2.5 There is no write API and no owner column.** The listing surface is three GETs, all `require("listing.read")`: `app/api/listings.py:231`, `:337`, `:346`. `migrations/016_listing.sql` has `source ∈ {seed, seller}` and no column naming a person. `scripts/seed_listings.py` writes eighteen `source='seed'` rows with no owner.

**2.6 The seller dashboard is the design's four Austin fixtures.** `sellerVals()` (`logic.js:1119`) maps `state.sellerListings` (`:206–211`) — *Cedar Park*, *Bastrop*, *Untitled listing*, *Buda*. `frontend/src/listings/load.ts` replaces only `P` and `MARKETS` at boot (`applyListings`, called from `main.ts`), so on QA the seller sees four fixtures matching none of the eighteen hospitals. The View action on a published row hard-codes `detailId: "p1"` (`logic.js:1134`).

**2.7 Admin › Listings is five hard-coded rows** (`logic.js:1058–1069`, the rows at `:1063–1067`) with `go: () => {}` no-ops (`:1022`). That is the one thing here that contradicts a standing rule rather than merely being unbuilt.

**2.8 Documents are not modelled anywhere.** The buyer detail's four rows — "Exterior and interior photos · 9 images", "Floor plan · PDF · 1 page", "Three-year financial summary", "Equipment list" — are a literal at `logic.js:1286–1290`, and their lock pill reads `unlocked`, which is `state.requests` fixture data (`:1244`).

**2.9 The disclosure model is already double-booked.** Step 2's toggle and step 7's first toggle both write `w.anon` (`logic.js:1175`, `:1181`), while the server models `location_disclosed` and `name_disclosed` as deliberately independent facts — `app/api/listings.py:171–175` says so in as many words ("Do not 'fix' this by making one flag imply the other", A-L5.2). `docs/design-reference/requests/2026-09-08-rev3-listing-disclosure-controls.md` is the request that closes it.

**2.10 What the gates pin.** Approved wizard/seller states are `seller-dash`, `wizard-step-1`, `wizard-step-7`, `wizard-preview`, `wizard-done` (`frontend/tests/screens.ts:158–162`), all four wizard states entering through *Create a listing* (`screens.ts:22`) and never through Edit. **Step 6 has neither a pixel baseline nor a DOM oracle.** `wizard-preview`'s approved baseline *is* a screen of em dashes — a brand-new listing with nothing typed — and stays correct after every change below. The app project stubs `/api/listings` in the browser from the design's own `P` (`frontend/tests/harness.ts`'s `listingsStubUrl` and its `page.route` block, `frontend/tests/design-listings.mjs`), which is spec 2026-09-06 D6: the oracle's data is the design's fixtures, and the API path is proved by tests instead.

---

## 3. The lifecycle

**D2.** `listing.status` already carries five of the six values needed (`migrations/016_listing.sql`): `draft`, `in_review`, `published`, `paused`, `withdrawn`. `declined` is missing from the CHECK and is added in `017`.

```
draft ──submit──► in_review ──approve──► published ──edit+save──► in_review ──► …
  ▲                  │                      │  ▲
  │                  └──decline──► declined │  └──republish── paused ◄──pause / unpublish
  └──(edit)──────────────────────────┘      │
                        declined ──edit+submit──► in_review
  any state except withdrawn ──withdraw──► withdrawn (terminal)
```

| Status | The owning seller may | Staff/admin may | A buyer sees |
|---|---|---|---|
| `draft` | edit every field, upload, delete an asset, submit, withdraw | nothing — it is not in the queue | nothing |
| `in_review` | keep editing (the design's own promise, `App.vue:1259`), withdraw | publish · decline | nothing |
| `published` | edit → **saving re-enters review** (John's ruling); pause; withdraw | unpublish (→ `paused`) | everything the disclosure flags allow |
| `paused` | republish (→ `published`, no re-review — the design's footnote calls unpublishing "immediate and reversible", `logic.js:1061`); withdraw | publish | nothing |
| `declined` | edit and re-submit; withdraw | publish on re-submission | nothing |
| `withdrawn` | nothing — terminal (`logic.js:1061`: "withdrawn listings keep their history for reporting but no longer appear in search") | reporting only | nothing |

**D3 — a published edit leaves the market the moment it is saved.** John's ruling, and it needs no new code on the read side: `GET /api/listings` filters `status = 'published'` (`app/api/listings.py:282`) and `GET /api/listings/{id}` does the same (`:320`), so the transition alone removes it. The first `PATCH` that changes any field of a `published` listing moves it to `in_review`, stamps `submitted_at`, drops the listings cache (D16) and writes an audit row. Subsequent PATCHes in the same review cycle do not re-transition.

**D4 — every transition writes an `audit_log` row** (`migrations/014_audit_log.sql`, append-only by trigger), `target_type='listing'`, `target_id` the listing id, `before`/`after` carrying `{status}`. Seller transitions too, not only staff ones: the design's admin footnote promises "who changed what and when" and the Rev 3 request repeats it.

---

## 4. Ownership and permissions

**D5 — `seller_id uuid REFERENCES account(id)`, nullable.** The identity spec already named the predicate — "Scope predicates ride with `*_own` permissions (`listing.seller_id = me`, `request.buyer_id = me`)" (`docs/superpowers/specs/2026-09-05-identity-access-email-design.md`) — and it was never built. Nullable because a production seed row belongs to the VIN Foundation, not to a person; on QA the seeder fills it (§11).

**D6 — no new permission is needed, and none is added.** All four already exist in `app/auth/permissions.py`: `listing.manage_own` (seller, `:24`), `listing.read` (members, `:19`), `listing.review` and `listing.publish` (staff/admin, `:38`). `tests/auth/test_permissions.py::test_matrix_matches_the_spec_table` pins the matrix against the identity spec's table, so adding a row would mean amending that spec; nothing here requires it.

**D7 — scope is enforced in the handler, not in the matrix.** `listing.manage_own` says *a seller may manage listings*; `seller_id = <principal.account_id>` says *which*. Every seller route resolves the row and refuses a non-owner with the `_error` envelope's `404 NOT_FOUND` (not 403 — a listing that is not yours should not be confirmed to exist). Staff and admin read every listing through `listing.review`; only staff and admin publish or decline.

**D8 — `listing.publish` joins `AUDITED`; `REAUTH` is unchanged; `listing.review` and `listing.manage_own` stay out of `AUDITED`.**
- `listing.publish` is a staff decision of exactly the class `users.decide` is, and `users.decide` is audited (`permissions.py:49`). Adding it obliges the decide handler to call `audit.write(` in its **own body** — `tests/auth/test_permissions.py::test_audited_permissions_are_written_by_their_handlers` reads `inspect.getsource(route.endpoint)`, so delegating to a helper reads as unaudited.
- The handler writes `action="listing.publish"` on **every** branch (publish, decline, unpublish), with the branch and the reason in `after`/`reason`. That satisfies `test_every_audited_action_is_named_after_a_permission` exactly, with nothing to add to `MULTI_ACTION_PERMISSIONS` or `CASCADED_ACTIONS`.
- `listing.review` stays out for the reason `users.review` is out (`permissions.py:26–31`): auditing a list that a tab polls writes one row per poll into a table whose triggers refuse DELETE.
- `listing.manage_own` stays out because the wizard's autosave rides on it; one row per step per keystroke-batch into an append-only table is the same slow leak. The seller's transition endpoints still write their own rows (`listing.submit`, `listing.pause`, `listing.republish`, `listing.withdraw`) — these name no permission by design, exactly like `applications.submit`/`answer`/`reapply`, and are outside the drift test's reach for the same documented reason (`tests/auth/test_permissions.py::test_the_applicant_facing_audit_actions_name_no_permission_and_are_not_watched`). A test in `tests/api/test_seller_listings.py` asserts that on purpose rather than leaving it to be noticed.
- `REAUTH` is untouched: publishing a listing is not in the class of revoke / role grant / token mint / licence decision (`permissions.py:44`).

`tests/auth/test_matrix.py` generates its rows from the running app, so every new route is picked up with no edit to that file — which is the point of it.

---

## 5. The API surface

**D9 — two new modules, disjoint URL spaces, mounted in `app` mode only.**
`app/api/seller_listings.py` (prefix `/api/seller`) and `app/api/admin_listings.py` (prefix `/api/admin`), both included inside `main.py`'s `if settings.site_mode == "app":` block (`app/main.py:76–89`) beside `listings_router`, for the reason recorded there: they are member endpoints, and `scripts/verify-deploy.sh production` asserts "member endpoints absent" behind the Coming Soon page. That script gains a probe for each.

The seller surface is `/api/seller/listings…`, **not** `/api/listings/mine`: Starlette matches in registration order, and `/api/listings/{listing_id}` (`app/api/listings.py:337`) would shadow `/api/listings/mine` unless the routers were mounted in a particular order — a trap nobody should have to remember. Disjoint prefixes remove it.

Shapes that are load-bearing and copied from `app/api/listings.py` and `app/api/admin_users.py`:
- **every guard is a module-level constant used through `Depends`, never wrapped** (`listings.py:72`, `admin_users.py:63–70`) — the route-guard and audit tests resolve a permission by the guard object's identity;
- **every refusal this code raises uses `_error(code, message, status)`** — decision A5's body (`listings.py:90`), never a bare `HTTPException`, and query parameters are parsed by hand rather than through `Query(ge=…)` so a bad value gets the same envelope;
- **connections are `with closing(sync_conn()) as conn, conn:`** (`listings.py:293`), because psycopg2's `with conn:` commits without closing;
- state changes go through `require(...)`, which enforces Origin and the CSRF double-submit for a cookie session (`app/auth/deps.py:308`, `:342`).

| Route | Guard + scope | Notes |
|---|---|---|
| `GET /api/seller/listings` | `listing.manage_own` ∧ `seller_id = me` | Every status. The dashboard's source. Keyset-paged in the shape `/api/admin/users` uses; `MAX_LIST` 200. |
| `POST /api/seller/listings` | `listing.manage_own` | Creates a `draft` owned by `me`, `source='seller'`, all four disclosure flags **false** (the table's defaults). Returns `{id}`. Called once, when *Create a listing* is first clicked. |
| `GET /api/seller/listings/{id}` | `listing.manage_own` ∧ owner, **or** `listing.review` | The wizard's read for Edit. Serialised by `serialise_draft` (D11) — no disclosure blanking, nulls preserved, plus `assets[]`. |
| `PATCH /api/seller/listings/{id}` | `listing.manage_own` ∧ owner ∧ status ≠ `withdrawn` | One call per step, the step's whitelisted field set only (D10). Applies D3's published→in_review transition. Drops the listings cache (D16). |
| `POST /api/seller/listings/{id}/photos` | same | multipart, one file. Refuses past four (D14). Re-encoded to WebP (D15). Returns the asset. |
| `PATCH /api/seller/listings/{id}/photos` | same | Reorder: body is the full ordered list of asset ids. Order is user-visible — `photoSet` fills slots by index and `thumbSrc` takes photo 2 (A12.2–A12.5). |
| `DELETE /api/seller/listings/{id}/assets/{asset_id}` | same | Photo or document. Removes the row, the object and (for a photo) the entry in `listing.photos`, in one transaction. |
| `POST /api/seller/listings/{id}/documents` | same | multipart, one file, `kind ∈ {floor_plan, financials, equipment, other}` defaulting to `other` (D18). |
| `GET /api/seller/listings/{id}/documents/{asset_id}` | `listing.read` ∧ (owner ∨ staff/admin) | The lock the design draws (D19). |
| `POST /api/seller/listings/{id}/submit` | `listing.manage_own` ∧ owner ∧ status ∈ {draft, declined, in_review} | → `in_review`. Re-validates the three rules the design already enforces client-side (`logic.js:1215–1217`). Audited; enqueues `listing_submitted`. |
| `POST /api/seller/listings/{id}/status` | same | `pause` · `republish` · `withdraw` — the dashboard's own buttons (`logic.js:958`). Audited. |
| `GET /api/admin/listings` | `listing.review` | The review queue and the Admin › Listings tab's source; `?status=` filter, keyset-paged like `/api/admin/users`. |
| `POST /api/admin/listings/{id}/decide` | `listing.publish` | `action ∈ {publish, decline, unpublish}`; `reason` required for `decline` (the `NOTE_REQUIRED` pattern, `admin_users.py:109`); `state` and `market` required on the first `publish` (D12). Audited from the handler's own body. Enqueues `listing_published` / `listing_declined`. |

**D10 — the per-step field sets, and the four mappings the design forces.** A `PATCH` accepts only the step's own fields; anything else is `400 BAD_REQUEST`.

| Step | Accepted | Columns |
|---|---|---|
| 1 | `name`, `type`, `est`, `ownership` | same names |
| 2 | `city`, `zip`, `anon` | `city`, `zip`, `name_disclosed`, `location_disclosed` (D20) |
| 3 | `price`, `rev`, `revBand` | `price`, `rev`, `rev_disclosed` (inverted) |
| 4 | `docs`, `rooms`, `sqft`, `hours`, `desc` | `docs`, `rooms`, `sqft`, `hours`, **`services`** |
| 5 | `bldg`, `facilityType`, `facility` | `bldg`, **`facility_type`** (new), `facility` |
| 7 | `anon`, `revBand`, `docsLocked` | the four disclosure columns (D20) |

The four mappings, each forced by the approved design and each a trap:
1. **`desc` is the `services` column.** The step-4 textarea is `area("desc", "Services offered", …)` (`logic.js:1177`); `note` is the overview prose the seeder writes, not this.
2. **`bldg` needs a value map.** The select offers "Included" / "Available separately" / "Leased" (`logic.js:1178`); the column's CHECK allows `'Included' | 'Leased' | 'Separate'` (`016_listing.sql`). "Available separately" → `Separate`, and the reverse on read.
3. **`type` gains `'Other'`.** The step-1 select offers it (`logic.js:1174`) and the CHECK does not allow it. `017` adds it: the approved design offers the value, so the column must hold it. An `Other` listing matches only the Browse type filter's "Any", which is honest.
4. **`facilityType` has no column.** `017` adds `facility_type text`. Nothing reads it yet — it is the seller's answer to an approved question, and dropping an answer on the floor is what "the UX true" means here.

Money and integer fields arrive as the strings the design's text inputs produce ("1,450,000"): the API strips `,`, `$` and spaces and refuses anything else with `400 BAD_REQUEST`. The wizard's own `previewRows` prefixes `"$"` (`logic.js:1224`), so the stored value is the bare number.

**D11 — two serialisers, and the buyer's one is not touched.** `serialise` (`app/api/listings.py:166`) keeps its exact behaviour: it is the buyer contract, it applies the disclosure blanking, and every published-listing pixel depends on it. A new `serialise_draft(row, assets)` in `app/api/seller_listings.py` returns the owner's own truth — every column unblanked, nulls preserved, plus `assets: [{id, kind, name, content_type, byte_size}]`. The wizard reads only the draft serialiser; buyers read only `serialise`. That is what keeps the zero-regression claim on the read surface a fact rather than a hope.

**D12 — `state` and `market` are supplied at review, not by the seller.** `listing.state` and `listing.market` are `NOT NULL` today and the approved design's step 2 collects **city and ZIP only** (`logic.js:1175`); `market` is what `stateOf()` splits for the state label (`logic.js:805`) and what the Browse market filter pages on (`listing_page_idx`). There is no field for either and inventing one is forbidden. So: `017` drops `NOT NULL` from `name`, `city`, `state`, `area`, `type` and `market`, and two CHECK constraints replace it —

```sql
CHECK (status IN ('draft','withdrawn')
       OR (name IS NOT NULL AND city IS NOT NULL AND zip IS NOT NULL
           AND type IS NOT NULL AND est IS NOT NULL AND price IS NOT NULL))   -- submittable
CHECK (status <> 'published'
       OR (state IS NOT NULL AND market IS NOT NULL AND area IS NOT NULL))    -- publishable
```

— so the database, not a code path, is what guarantees `serialise` never meets a null it cannot render. `area` is set from the city on the step-2 PATCH; `state` and `market` come in on the first `publish` decision, which is what a review is for. The Admin table has no field editor, so the reviewer is prompted for them the way the Users tab already prompts for a decline note (`frontend/src/admin/users.ts`'s `needsNote(action)`) — an existing UI seam, no new markup. A proper admin field editor is Rev 3 (§14).

**D13 — the slug.** `slug` stays `NOT NULL UNIQUE` (nothing about the seeder's `ON CONFLICT (slug)` changes). A draft is created with `slug = 'listing-' || id`; on first publish it is rewritten to the name in slug form **plus the first eight characters of the id**, so a seller's practice named "ABC Animal Hospital" can never collide with the seed slug of the same name and can never make the next `seed_listings.py --reset` refuse (exit 5, `scripts/seed_listings.py:105`). Task L6 keys off `id`, never `slug` (`listings.py:39`), so nothing downstream cares.

**D16 — cache invalidation is mandatory.** `app/api/listings.py:266–271` already writes the requirement down: "Wave 2b's seller edits are the point at which this needs a real invalidation (drop the `listings:v1:*` keys on write) … because a disclosure flag turned OFF must stop reaching buyers at once". Every write here that can change a published payload — PATCH, submit, status, decide, photo upload/reorder/delete — drops every `listings:v1:*` key by `scan_iter` after the transaction commits, never before it (the ordering `admin_users.py` learned in I5c fix round 1). The key shape is unchanged, so the D6 comment stays true.

**D17 — rate limits, in `app/auth/limits.py`'s existing shape** (`hit()` over `bucket_key`, so the subject enters Redis only as a truncated SHA-256): `LISTING_PATCH = (240, 3600)`, `LISTING_UPLOAD = (40, 3600)`, `LISTING_SUBMIT = (20, 3600)`, all keyed on the account id. Generous enough that a seller working through eight steps never meets them, tight enough that a script cannot fill a bucket.

---

## 6. Storage

**D14 — object storage now, on the bucket and the abstraction already ruled.** John: "Use object storage as the production architecture now; do not build a Postgres-bytea architecture intended for a later swap." The bucket is already approved per environment for Sub-project 3 — Census plan `docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md`, ruling **A-C1 ¶7** ("Bucket approved — `practice-match-data` is created separately per environment … A2's `ObjectStore` is real, tests use moto") — and this sub-project reuses it under a `listings/` prefix. The settings names are Task A2's, unchanged: `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, all optional on `Settings` (`app/config.py`). No second storage layer, no second secret, no `MEDIA_BACKEND` switch.

`ObjectStore` does not exist in the tree yet — Census Task A2 has not been executed. Whichever sub-project lands first writes it; this one must not write a twin. **Controller amendment A-SL1 to the Census plan, Task A2:** the module's path becomes `app/storage.py` rather than `app/census/storage.py`, because two sub-projects now depend on it and a shared abstraction should not carry one of their names. Everything else about Task A2 — the constructor `ObjectStore(endpoint_url, bucket, access_key, secret_key, region='auto')`, `put_immutable`/`get`/`exists`, `from_settings(settings) -> ObjectStore | None` returning `None` (with a logged warning, never a crash) when unconfigured, and the three moto tests — is taken verbatim. This sub-project adds exactly one method, `delete(key) -> bool`, which the Census archive never calls: an asset object is written once and only ever deleted, so `put_immutable`'s never-overwrite guarantee is preserved (a "replace" is a new asset id and a new key).

**Keys.** `listings/{listing_id}/photos/{asset_id}.webp` and `listings/{listing_id}/documents/{asset_id}{ext}`. Private bucket, no object ACL, nothing public anywhere.

**D15 — reads are proxied through the API, not signed URLs.** Four reasons, in order of weight:
1. **The permission decision is per request.** A signed URL outlives the decision that minted it: a document would stay readable after the listing was unpublished, the request withdrawn or the account suspended. Every read here is a live check against `listing_asset`, the listing's status and the caller's principal.
2. **The buyer photo URL does not change.** `serialise` emits `/api/listings/{id}/photos/{n}` (`listings.py:207`) and the route already exists (`:346`) with a permission guard and `Cache-Control: private, max-age=86400`. Keeping it means the frontend, the design and the pixel oracles see nothing at all — no amendment, no baseline move, no new URL shape in `toPractice`.
3. **One `if`, both arms tested.** `listing.photos` stays the ordered array of strings it is; for a `source='seed'` row an entry is a relative path resolved under `PHOTOS_ROOT` by the existing `photo_file()`, which already refuses anything escaping the root (`listings.py:153–163`); for a seller row it is an asset uuid resolved through `listing_asset` and `ObjectStore.get`. `listing.photos` remains the single home of photo *order*, so `listing_asset` carries no `position` column and there is no dual truth to keep in step.
4. **Egress is bounded.** Photos are ≤ 250 KB by construction and documents are seller-supplied packets read a handful of times. If that ever stops being true, a redirect to a short-lived signed URL can be added *behind the same route*, changing no URL and no UI.

**Normalisation is part of the upload, not a nicety.** `scripts/prepare_photos.py`'s rules move into `app/media/encode.py` and are reused verbatim: EXIF-transpose, flatten alpha, ≤ 1600 px long edge (`MAX_PHOTOS`, `MAX_EDGE_PX`, `MAX_BYTES` at `prepare_photos.py:32–34`), the quality ladder `(82, 72, 62, 52, 44, 20)` with the 1100 px fallback step (`:38–39`), ≤ 250 KB WebP out, SHA-256 recorded, and — load-bearing here rather than merely tidy — **every piece of metadata stripped**. A seller's phone photograph carries GPS EXIF, and a listing with `location_disclosed = false` whose photograph leaks its coordinates breaks the promise the sign-in card makes in John's own words (amendment A10.2: "Sellers control what buyers can see"). The seeder keeps its own copy of the script; the shared module is imported by both, and `tests/scripts/test_prepare_photos.py` keeps proving the pipeline.

**Limits and sniffing.** Photos: `image/jpeg`, `image/png`, `image/webp` (the pipeline's own `IMAGE_SUFFIXES`), ≤ 15 MB in. Documents: `application/pdf`, `text/csv`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, ≤ 25 MB, **content sniffed rather than trusted** (`%PDF-`, `PK\x03\x04`, decodable text), stored as uploaded, served `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`. Six documents per listing.

---

## 7. Photographs and documents

**D18 — the four photo cap holds, and the document kinds are the design's own three plus `other`.** John: "Keep the existing 4-photo seller-upload cap" — the seed pipeline's `MAX_PHOTOS = 4` (`prepare_photos.py:32`) becomes the API's cap too, enforced server-side; the fifth upload is `409 PHOTO_LIMIT` in the `_error` envelope, surfaced through the wizard's single error slot (`logic.js:1197`, `App.vue:1216–1218`). Document kinds are `floor_plan`, `financials`, `equipment` — the design's own three document rows (`logic.js:1288–1290`) — plus `other`, which is what the wizard sends because **the approved design has no control for choosing a kind**. Step 6 offers exactly one button (`App.vue:1203`) and a strip of badge tiles (`:1206–1211`): no kind picker, no delete control, no reorder control, no progress state. The kind picker is Rev 3 (§14); the API takes `kind` today so that Rev 3 needs no API change.

The tile badge (`u.kind`) is "Photo" for an image and "PDF" for a PDF — the design's own two values (`logic.js:1188`) — and the uppercased extension ("CSV", "XLSX") otherwise. That is a new value in an existing slot, the same class of change as A12 putting a real hospital name into `practiceName`; it is not new markup.

**D19 — the lock behaviour is preserved exactly, and no approval workflow is added.** John: "Seller uploads immediately; preserve the existing staff/seller approval gating and 'Locked — seller approval' behavior. No new approval workflow in this slice." So: an upload is live to its owner the instant it lands; `GET /api/seller/listings/{id}/documents/{asset_id}` serves it to the owner and to staff/admin and to nobody else, which is precisely "Locked — seller approval" as the design draws it (`logic.js:1288–1290`). The unlock — a buyer with an **accepted request** — is the requests sub-project's own transition and is written here only as the place it will attach: one additional arm on the same guard, when a `request` table exists. Until then a member who is neither owner nor staff gets `403 LOCKED`.

**D21 — the buyer detail's four document rows are not rewired in this slice.** They stay the literal at `logic.js:1286–1290`. Rewiring them would move the `detail` and `mobile-detail` oracles, both of which are frozen by the Census ruling A-C1 ¶3 ("no move, no rebaseline in this pass"), and it would need a "no document provided" state that the approved design does not have. John's finding was about Edit, Preview and Submit; this is the boundary that keeps the change surgical and the promise in his ruling ("preserve the existing … behavior") literally true. Routed to Rev 3 with the copy conflicts in §14.

---

## 8. Disclosure mapping

**D20 — `w.anon` sets both name and location; the server keeps them independent.**

| Design switch | Where | Column | Default |
|---|---|---|---|
| "Show only the community, not the street address" | step 2, `logic.js:1175` | `location_disclosed` **and** `name_disclosed` (inverted) | hidden |
| "Keep practice name and address hidden until I approve a buyer" | step 7, `logic.js:1181` | the same two, inverted | hidden |
| "Show revenue as a range instead of an exact figure" / "Release revenue as a range…" | steps 3 and 7, `:1176`, `:1182` | `rev_disclosed` (inverted) | range |
| "Keep floor plans and financial packet locked" | step 7, `:1183` | `documents_disclosed` (inverted) | locked |

The design's step-7 label names *both* the practice name and the address, so `anon = true` → both flags false, `anon = false` → both true. That is the Rev 3 request's own default (name off, exact location off) and the only reading the approved copy supports. The API takes the four columns **independently**, so Rev 3's split into four switches needs no API change — and `app/api/listings.py:171–175`'s rule survives untouched: the server still permits the independent combinations, the wizard simply cannot express them yet.

**Spelling matters here.** `listing.docs` is the **doctor count** (`016_listing.sql`; the step-4 field is `text("docs", "Doctors (full-time equivalent)")`, `logic.js:1177`). The document flag is therefore spelled `documents_disclosed` in full and never `docs_disclosed`.

**D22 — `serialise` blanks `rev` when `rev_disclosed` is false**, in the same place and the same way it blanks street, ZIP, phone and name (`listings.py:176–207`). The design's own `money()` renders a null as "—" (`logic.js:251–252`), so no design change is needed and no screen moves. Every seed sets all four flags true (as D8/A-L5 already set the other two), so nothing John sees on QA changes. `documents_disclosed` is enforced only on the document read route (D19), because D21 leaves the detail's document rows alone. The "$2M – $2.5M" band the design's help text promises (`logic.js:1176`) has **no slot** on the buyer detail, which renders one figure (`logic.js:1281`) — Rev 3 (§14).

---

## 9. The frontend contract

**D23 — wiring is a ruled amendment family plus a re-port, and every approved state stays pixel-identical against the design's own fixtures.**

`logic.js` and `App.vue` are never hand-edited. The change lands as amendment family **A13** in `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html`, one `Amendment { id, date, ruling, find, replace, count }` per literal edit in `frontend/tests/design-amendments.ts`, one row per amendment in `LOCAL_AMENDMENTS.md`, then `npm run gen:design && npm run gen:app`. `design-amendments.test.ts` proves pristine + amendments == the amended file byte for byte and pins the set both ways. The precedent is exact: **A5** wired sign-in through the `auth` adapter and **A12** made `practiceName`/`photoSet`/`heroSrc`/`thumbSrc` read a listing's own `name` and `photos` — the same shape of change, in the same functions' neighbourhood.

**The adapter.** `frontend/src/listings/seller.ts` exports `makeListingsAdapter(api)` with `list()`, `create()`, `get(id)`, `patch(id, step, fields)`, `upload(id, file)`, `remove(id, assetId)`, `reorder(id, ids)`, `submit(id)`, `setStatus(id, action)`. It is declared in `app.setup.js` as the prop `listings`, exactly as `auth` is (`app.setup.js:52`), and for the same recorded reason: `app.setup.js` is copied verbatim into `App.vue` and sits outside the coverage gate, so the logic lives in a module with unit tests. It needs **no** entry in the design's `data-props`: the prop-parity gate is one-directional — `app-generated.test.ts:33` requires the setup to declare every prop the *design* declares, not the reverse — which is why `auth` never needed one either.

**Every A13 edit keeps the design's own path when no adapter is passed**, which is A5.1's rule and what keeps the reference target on its pixels.

| Id | Target | What changes |
|---|---|---|
| A13.1 | `sellerVals()`'s `listings:` source (`logic.js:1127`) | rows come from the loaded listings, with `s.sellerListings` kept as the fallback (A12's `NAMES[p.id]` pattern) |
| A13.2 | Continue / Edit (`:1130`, `:1131`) | `go` hydrates `w` from the fetched draft and records the id being edited |
| A13.3 | View (`:1134`) | `detailId: l.id` instead of the hard-coded `"p1"` |
| A13.4 | `uploads` (`:1188`) | the listing's real assets, the four-item literal kept as the no-adapter fallback |
| A13.5 | `addPhoto` (`:1201`) | opens a real file picker through the adapter; with no adapter the design's counter runs unchanged |
| A13.6 | `next` (`:1214–1219`) | after the design's own validation, PATCH the step's fields; a refusal lands in `wizErr`, the design's own error slot |
| A13.7 | `submit` (`:1236`) | POST submit through the adapter, then the design's own `setState` |
| A13.8 | `setListingStatus` (`:958`) | pause / republish / withdraw through the adapter |
| A13.9 | `componentDidMount` | loads the seller's listings when the account holds `page.seller` — the five-line shape of A5.4 |
| A13.10 | `statusPill` (`:946–955`) | a `declined` entry; without it a declined row falls through `map[status] \|\| map.draft` and reads "Draft" (open question 1) |

**The preview renders the draft through the same values the buyer sees.** `previewRows` (`logic.js:1221–1232`) is not re-derived from a second source: the PATCHed row is read back, put through `toPractice` (`frontend/src/listings/load.ts:123`) exactly as a buyer's listing is, and the ten rows read from that. "Preview — this is what an approved buyer sees" then becomes literally true, a switch flipped in step 7 visibly blanks a row in step 8, and "Photos attached" (`:1230`) is the real asset count.

**The pixel budget, screen by screen.**
- `wizard-step-1`, `wizard-step-7`, `wizard-preview`, `wizard-done` all enter through *Create a listing* (`screens.ts:22`), so a hydration path that only fires on Edit moves none of them. A fresh draft is empty, so `wizard-preview` stays the approved screen of em dashes.
- **Step 6 has no baseline and no DOM oracle**, so the upload work moves nothing. (It should get one once the design has a real state to freeze — Rev 3.)
- **`seller-dash` is the one screen at risk.** It *is* an oracle, so `GET /api/seller/listings` must be stubbed in `frontend/tests/harness.ts` with the design's own four `sellerListings` fixtures, exactly as `/api/listings` is stubbed from `P` today (`listingsStubUrl` + the `page.route` block, `design-listings.mjs`), and the write routes stubbed with 200s so the app project never depends on a database write for a pixel. That is spec 2026-09-06 **D6** applied unchanged: the design's fixture rows remain the oracle's data, and the API path is proved by pytest, vitest and a flow spec instead. Do that and `frontend/tests/baseline-manifest.json` does not move at all.
- The stub is never armed against a remote target (`PW_APP_URL`), so the QA parity run still exercises the real, seeded API — which is the whole point of that run.

---

## 10. The admin side

**D24 — Admin › Listings reads the real table.** John's standing rule: every Admin tab shows real database data, never dummy rows. `frontend/src/admin/listings.ts` follows the M6 pattern `frontend/src/admin/users.ts` already established — a pure mapping module *outside* `logic.js` producing exactly the `cell()` / `A()` row shapes the design's table renders, with those two helpers copied verbatim from `adminVals()` and a unit test comparing them against that file's own output, so the table cannot silently restyle. Columns stay the design's: Listing · Seller and figures · Status · Action (`logic.js:1059`). Actions are the design's own buttons — Publish, Reject, Unpublish, Edit, Contact seller — wired to `POST /api/admin/listings/{id}/decide` where a decision exists and left as the design's no-op where it does not.

**What is not wired, and why.** The fifth fixture row's "Flagged" pill and its Investigate action (`logic.js:1067`) describe an abuse-report table that does not exist; `listing.status` has no `flagged` value and inventing one is out of scope. The Requests tab is Wave 2b's requests sub-project. The Data Sources tab keeps its licence gate untouched (CLAUDE.md, legally load-bearing). Until the flag table exists, `GET /api/admin/listings` returns real rows and the Flagged row simply is not among them — absent beats faked.

**Mail.** Three templates through the existing outbox → Celery → Resend pipeline (`app/mail/`): `listing_submitted` (to the seller, on submit), `listing_published` and `listing_declined` (to the seller, carrying the reviewer's reason). `EMAIL_ALLOWLIST` keeps QA from reaching a real person, as it does for every other template.

---

## 11. Seeding the eighteen

**D25 — ownership lives in `scripts/seed_listings.py`, so a re-seed keeps it.** John: "Assign all eighteen QA seed listings to `seller@practice-match.test`, with real `seller_id` ownership."

- A module constant `SEED_OWNER_EMAIL = "seller@practice-match.test"` — the persona `scripts/seed_persona.py:100` already creates with roles `buyer + seller`, and which QA already has (`DEPLOY.md`'s persona step) — with `--owner <email>` to override and `--no-owner` to seed unowned.
- The seeder resolves the address to an `account.id` once, before the transaction. **If the account does not exist, `seller_id` stays NULL and the run says so on stdout** — not a refusal, because production has no persona accounts (`PERSONA_PASSWORD` is never set there, A-S6.1) and production must still be seedable.
- On a `--production` run the default owner is **not** applied at all unless `--owner` is passed explicitly. A demo persona must never own a production row.
- `seller_id` joins the `UPSERT`'s insert list *and* its `DO UPDATE SET` (`seed_listings.py:74–99`), so a re-seed re-asserts ownership; the existing `WHERE listing.source = 'seed'` scope means a real seller's row is still never touched, and the collision pre-flight (`:105`) still refuses the whole import if another source owns a seed slug.
- `DEPLOY.md` §"Seeding the demo hospitals (QA)" gains the one line about ownership and the order (persona first, then listings).

**D26 — the seed photographs stay in `seeds/` and keep being served from disk.** They are committed, SHA-256-inventoried, immutable, already in the image (`Dockerfile:55`, 3.7 MB / 72 files) and already served by a guarded route (`listings.py:75`, `:346`). Copying them into the bucket would create a second copy to keep in step with the repository and would make a fresh environment's demo depend on a bucket having been populated. Object storage holds **only what sellers upload**. The one place the two meet is the wizard's step-6 tile name: for a seed photograph it is the caption from `seeds/hospitals/photos/index.json` ("Exterior — front view", "Exterior — entrance view", …) rather than the filename `1.webp`, which is what makes Edit on a seeded hospital read the way John expects. For a seller upload it is the uploaded filename.

---

## 12. Tests and gates

Test-first, no exceptions (standing rule).

**Backend — 100 % lines and branches, `-W error`, as CI runs it.**
- `tests/test_listing_schema.py` extended: the new columns, the widened `status` and `type` CHECKs, the two new constraints, the `listing_asset` table and its indexes. `017` is a **new file**; an applied migration is never edited in place.
- `tests/api/test_seller_listings.py`: create → per-step PATCH → submit; the four field mappings of D10; owner scoping (a second seller gets 404 on every route); status guards (a withdrawn listing refuses every write); D3's published→in_review on save; the whitelist refusing an off-step field; every refusal asserted as an `{"error": {...}}` body, never `{"detail": ...}`; the audit-action test of D8.
- `tests/api/test_listing_assets.py` with **moto**: upload, the WebP re-encode and the metadata strip, the four-photo refusal, reorder, delete (row + object + `listing.photos`), the sniffing refusals, the document lock (owner 200 / staff 200 / other member 403 / anonymous 401), and `ObjectStore.from_settings → None` leaving uploads refused with a clear message rather than crashing.
- `tests/api/test_admin_listings.py`: the queue, the three decide branches, `reason` required on decline, `state`/`market` required on first publish, one audit row per decision with `action="listing.publish"`.
- `tests/scripts/test_seed_listings.py`: ownership assigned, re-assigned on re-seed, left NULL when the account is absent, never applied by default under `--production`, and a seller row still untouched.
- `tests/auth/test_permissions.py` and `test_matrix.py` need no edits and must stay green — they generate their rows from the running app, which is the check that the new routes are guarded and audited correctly.
- Cache invalidation asserted directly: a PATCH drops `listings:v1:*`, and it happens after the commit.
- Per-worktree `DATABASE_URL` for pytest and for Playwright; `db_ready` migrates whatever database it is pointed at, and the shared dev database is not it.

**Frontend — 100 %, vitest.**
- `frontend/src/listings/seller.test.ts` for the adapter (every method, every failure path).
- `frontend/src/admin/listings.test.ts` comparing the mapping module's `cell()`/`A()` output against `logic.js`'s `adminVals()` own output, as `users.test.ts` does.
- `frontend/tests/design-amendments.test.ts` proves A13 applies cleanly and that `LOCAL_AMENDMENTS.md` carries one row per amendment, count and ids pinned both ways.
- `frontend/tests/app-generated.test.ts` unchanged and green: `logic.js` still byte-identical to the amended design's script block, `app.setup.js` still declaring every prop the design declares.

**Oracles.**
- `npm run test:visual:baselines` regenerates from the amended V3, then `npm run test:e2e` (visual + DOM + smoke) at `maxDiffPixels: 0`. The 43 approved states, `baseline-manifest.json` unmoved.
- A new `frontend/tests/listing-flows.spec.ts` — value assertions, not pixels, in the shape of `account-flows.spec.ts` — drives the real API with **no** stub: sign in as the seller persona, open Edit on a seeded hospital, assert the practice name, year, city, ZIP, price, revenue, doctors, rooms, square feet and property status are the seeded values; assert step 6 lists that hospital's four photographs by caption; assert step 8's preview shows them instead of dashes; then create a listing, upload a photograph and a PDF, submit, approve it as `design@`, and assert it appears on Browse.

**The gate before production is CLAUDE.md's four, all of them**, and the hand-back is a forwardable summary plus screenshots of the live screens plus the one-line engineer's note.

---

## 13. Non-goals

- **Requests and messaging** — the buyer's request, the seller's accept/decline, and therefore the unlock of a document to an approved buyer. Wave 2b's own sub-project; D19 names the single guard arm it will attach to.
- **The buyer detail's document rows** (D21) and any change to `detail` / `mobile-detail`, which A-C1 ¶3 freezes.
- **Abuse flagging** — no `flagged` status, no report table, no Investigate action.
- **Geocoding a seller listing.** The approved step 2 collects city and ZIP only (`logic.js:1175`), so a seller listing has no street to geocode; `geom` stays NULL, and with `location_disclosed` defaulting false `serialise` nulls the point for every buyer anyway (`listings.py:204–205`). The exact-location switch and the street field it needs are Rev 3's.
- **Census market figures per listing** — the Census sub-project's Phase B.
- **Production seeding**, and any production data at all: production runs `coming_soon`.
- **Photo captions in the UI**, admin field editing, and a bulk upload — none has a slot in the approved design.

## 14. Routed to Rev 3 (not invented here)

Each of these is a place the approved design has no slot. They are written into `docs/design-reference/requests/2026-09-08-rev3-listing-disclosure-controls.md` as additional items rather than guessed at:

1. **Step 6's missing controls** — a document-kind picker, a delete control, a reorder affordance, an upload progress/error state, and a photo thumbnail. Today: one "Add files" button and a badge tile (`App.vue:1203`, `:1206–1211`).
2. **The four disclosure switches** the Rev 3 request already describes, which is what splits `w.anon` into its two real facts.
3. **A revenue *range* rendering on the buyer detail.** The wizard promises "$2M – $2.5M" (`logic.js:1176`); the detail renders one figure (`logic.js:1281`).
4. **The document rows as real documents**, with a "not provided" state — the precondition for lifting D21.
5. **Two copy conflicts on a frozen screen**, recorded and unchanged: the detail says "9 images" and "+6 more photos" (`logic.js:1287`, `:1274`) while the cap is four. Same class as the Census plan's four copy conflicts; resolves with a rebaseline ruling, not by editing a frozen screen now.
6. **An admin field editor** for `state` and `market` (D12), replacing the reviewer prompt.
7. **A pixel baseline and DOM oracle for step 6**, once it has a real approved state.

---

## 15. Decisions

| Id | Decision |
|---|---|
| D1 | One release. Read and write ship together; there is no read-only "Edit shows the truth" intermediate (John's ruling). |
| D2 | The lifecycle is `draft → in_review → published`, with `paused`, `declined` and terminal `withdrawn`; `017` adds `declined` to the status CHECK. |
| D3 | Saving an edit to a `published` listing moves it to `in_review` and off the market at once; the existing published-only read filters do the removing. |
| D4 | Every transition, seller-initiated included, writes an append-only `audit_log` row with `target_type='listing'`. |
| D5 | `listing.seller_id uuid REFERENCES account(id)`, nullable; indexed `(seller_id, updated_at DESC)`. |
| D6 | No new permission. `listing.manage_own`, `listing.read`, `listing.review`, `listing.publish` already exist and suffice. |
| D7 | Ownership scope is enforced in the handler (`seller_id = me`); a non-owner gets 404, not 403. |
| D8 | `listing.publish` joins `AUDITED` and its handler writes `action="listing.publish"` on every branch; `listing.review` and `listing.manage_own` stay out; `REAUTH` is unchanged. |
| D9 | Two new routers, `app/api/seller_listings.py` (`/api/seller`) and `app/api/admin_listings.py` (`/api/admin`), mounted in `site_mode == "app"` only; disjoint prefixes so nothing shadows `/api/listings/{id}`. |
| D10 | `PATCH` is per step and whitelisted; the four forced mappings are `desc→services`, `bldg` value map, `type` gains `'Other'`, new `facility_type`. |
| D11 | Two serialisers: the buyer's `serialise` is untouched; a new `serialise_draft` returns the owner's unblanked truth plus `assets[]`. |
| D12 | `state` and `market` are supplied by the reviewer on first publish; `017` relaxes six NOT NULLs and adds a submittable and a publishable CHECK. |
| D13 | A draft's slug is `listing-<id>`, rewritten on publish to the name plus the first eight characters of the id, so a seller slug can never collide with a seed slug. |
| D14 | Object storage now: the already-approved `practice-match-data` bucket under a `listings/` prefix, Task A2's `ObjectStore` and its four `S3_*` settings, moved to `app/storage.py` by controller amendment A-SL1 and gaining only `delete()`. |
| D15 | Reads are proxied through the API, not signed URLs; the buyer photo route and its URL shape do not change. |
| D16 | Every write drops `listings:v1:*` after the commit. |
| D17 | Per-account write rate limits in `app/auth/limits.py`'s existing shape. |
| D18 | The four-photo cap holds; document kinds are `floor_plan`/`financials`/`equipment`/`other`, with the wizard sending `other` until Rev 3 gives it a picker. |
| D19 | Seller uploads are live immediately; a document reads to owner and staff only — the existing "Locked — seller approval" behaviour, with no new approval workflow. |
| D20 | `w.anon` sets `name_disclosed` and `location_disclosed` together; the API keeps all four flags independent so Rev 3's split needs no API change. `documents_disclosed`, never `docs_disclosed`. |
| D21 | The buyer detail's four document rows are not rewired; `detail` and `mobile-detail` stay frozen. |
| D22 | `serialise` blanks `rev` when `rev_disclosed` is false; `money()` already renders a null as "—", so no screen moves and every seed sets the flag true. |
| D23 | Frontend wiring is amendment family **A13** plus `gen:design`/`gen:app`, with an app-only `listings` adapter prop; the design's fixtures stay the oracle's data (D6) and `seller-dash` is stubbed so no baseline moves. |
| D24 | Admin › Listings reads the real table through the M6 mapping-module pattern; unbuilt rows are absent rather than faked. |
| D25 | Seed ownership lives in `scripts/seed_listings.py` (constant + `--owner`), re-asserted on every re-seed, NULL when the account is absent, never defaulted on production. |
| D26 | Seed photographs stay in `seeds/` and are served from disk; object storage holds only seller uploads; the step-6 tile name is the seed caption or the uploaded filename. |

---

## 16. Open questions

1. **The declined pill's copy.** `statusPill` has no `declined` entry, so a declined row would read "Draft" (`logic.js:946–955`). *Default:* the label "Declined" in the `bad` tone, alongside the existing five.
2. **Who supplies `state` and `market`.** *Default:* the reviewer, prompted at publish (D12), with an admin field editor in Rev 3. The alternative is a state field in the wizard's step 2, which is a Rev 3 design change to an approved screen.
3. **The document allow-list beyond PDF.** The design names a spreadsheet ("Equipment list · Spreadsheet", `logic.js:1290`) but only ever shows the badges "Photo" and "PDF". *Default:* allow PDF, CSV and XLSX, badging the last two with the uppercased extension.
4. **A warning before an edit takes a published listing off the market.** The ruling settles the behaviour, not whether the seller is told first; the design has no confirm dialog. *Default:* no confirm, and the design's copy unchanged — the submitted card already says edits after publication go through the same review.
5. **The bucket's name.** A-C1 ¶7 says `practice-match-data` per environment; the plan's Task A2 step 4 creates `practice-match-data-qa` and `practice-match-data-prod`. *Default:* the plan's step-4 spelling, since it is what the command creates; `S3_BUCKET` is set per environment either way, so nothing in code depends on the answer.

---

## 17. For the demo tonight — nothing changes

No code changes are proposed or made before John rules, and nothing here is deployed before he says the demo is over. Tonight the wizard behaves exactly as the approved prototype does: steps 1–5 and 7 accept typing and the preview reflects it within the visit; Edit opens a blank form; step 6 shows three placeholder tiles; Submit adds a row that lives until the page is refreshed; the dashboard shows the design's four Austin fixtures rather than the eighteen hospitals. That is a prototype being honest about being a prototype.

---

## 18. Estimate

One release, one spec → plan → implementer → review-rounds → four-part gate → QA deploy → click-through loop. The three slices below are the *work*, not three releases; days are working days for one implementer plus the review loop.

| Slice | Contents | Days |
|---|---|---|
| **(a) Ownership and the read path** | `017_listing_owner_and_assets.sql` (columns, widened CHECKs, relaxed NOT NULLs, the two new constraints, `listing_asset`); ownership in `seed_listings.py`; `GET /api/seller/listings` and `GET /api/seller/listings/{id}` with `serialise_draft`; the caption resolver; `frontend/src/listings/seller.ts`; harness stubs; A13.1–A13.4 + `LOCAL_AMENDMENTS.md`; schema and endpoint tests at 100 % branches | **3–4** |
| **(b) Writes and storage** | `app/storage.py` (`ObjectStore` per Task A2 + `delete`, moto tests) and the two buckets provisioned; `app/media/encode.py` from `prepare_photos.py`; `POST /api/seller/listings`, per-step `PATCH`, photo upload/reorder/delete, document upload and the locked read; cache invalidation and rate limits on every write; A13.5–A13.6; autosave and error surfacing through the design's single `wizErr` slot | **5–7** |
| **(c) Submit, review, publish, Admin live** | submit and status transitions with their guards and audit rows; `GET /api/admin/listings`; `POST /api/admin/listings/{id}/decide`; three mail templates through the outbox; `frontend/src/admin/listings.ts` on the M6 pattern with its comparison test; A13.7–A13.10; `listing-flows.spec.ts`; the full gate, QA deploy and click-through | **4–5** |

**Total 12–16 working days**, shipped as one release. Shipping together saves roughly a day of duplicated gate, deploy and hand-back overhead against three separate releases, and object storage costs roughly a day back against the rejected bytea plan — while removing the swap that plan would have owed later. Nothing here is blocked on Rev 3: every item in §14 is a slot the approved design does not have, and none of them is on the path from "Edit is empty" to "Edit shows the truth and Submit saves it".

---

**Controller notes (2026-09-08, before John's review).** Open question 5 is settled: the bucket is `practice-match-data` in every environment (John's ruling 7; Railway buckets are environment-scoped, so no `-qa`/`-prod` suffix — the Census plan's Task A2 step 4 is corrected to this spelling; QA's bucket already exists under that name). Defaults proposed for the other four, pending John: Q1 "Declined" with the `bad` tone; Q2 the reviewer supplies `state` and `market` at publish (the eighteen already carry them); Q3 PDF, CSV and XLSX with the extension badge; Q4 no confirm dialog (the design has none). This spec awaits John's review before the plan is written (brainstorming gate).
