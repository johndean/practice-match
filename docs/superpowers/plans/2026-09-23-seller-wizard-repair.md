# Seller wizard repair — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Make every control in the seller wizard do what it says, and collect what the disclosure
capabilities need in order to deliver anything.

**Source of requirements:** `docs/superpowers/specs/2026-09-23-seller-wizard-audit.md` (findings
S1-S11, U1-U4, §6). Every task cites its finding id.

**Ruling:** John, 2026-09-23 — "implement full seller wizard audit". Recorded as **D-C65**.

**Architecture:** Two kinds of change, and they must not be interleaved.
* **DESIGN changes** edit `frontend/tests/design-amendments.ts` under ONE family id, **A58**, and
  regenerate. Amendment entries collide if two agents write them, so every design task runs
  SEQUENTIALLY and no two design tasks are ever dispatched at once.
* **APP-ONLY changes** edit `app/**` or `frontend/src/{listings,admin,auth,router,market,requests}/**`,
  which the reference never renders and which carry no amendment (A52's ruling).

## Global Constraints

- **TDD, RED first.** Every task writes a failing test, watches it fail for the right reason, then
  implements. `superpowers:test-driven-development`.
- **100% line and branch coverage** on both suites. `npm test` is `vitest run --coverage`.
- **`logic.js` is GENERATED.** Never hand-edit it, `App.vue`, `pseudo.css` or `app.setup.js`. Edit
  `frontend/tests/design-amendments.ts` and run `npm run gen:design && npm run gen:app && npm run gen:logic`.
- **AMEND-GUARD.** An entry that rewrites a line another entry introduced must carry the literal
  token `consumes <id>` in its docstring.
- **Amendment family is A58** — verified free across every local and origin branch on 2026-09-23.
  Each entry needs a `LOCAL_AMENDMENTS.md` row and a CLAUDE.md paragraph.
- **Re-basing is MEASURED, never predicted** (the A33 method): regenerate baselines cold before and
  after, diff all PNG and DOM hashes, and report the actual set. `baseline-manifest.json`'s thirteen
  frozen hashes must not move unless the task says otherwise.
- **Backend gate:** `docker compose -f docker-compose.dev.yml up -d`, then ruff, both strict mypy
  passes, pytest at 100%. Export `DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match`.
- **No fabricated data.** A control renders only if it completes (D-C53 §1 rule 3).

---

## Task 1: Submit tells the truth (S2, design, A58.1)

**Finding S2.** `frontend/src/logic.js:1838-1840` uses `promise && this.setState(...)`. A Promise is
always truthy, so the seller is shown "Submitted" even when the server refused, and a fabricated
`in_review` row persists because `reloadListings()` never runs on the failure path.

**Required behaviour, exactly:**
- **No adapter** (reference, Claude Design preview): flips to Submitted synchronously with the
  optimistic row, EXACTLY as today. Approved states depend on this; their pixels must not move.
- **Adapter + success:** flips to Submitted, then `reloadListings()`.
- **Adapter + refusal:** does NOT flip. Stays on the preview with `wizErr` set. This also makes the
  refusal visible, because `App.vue` renders `wiz.errorText` inside `isPreview` but not inside `isDone`.

**Files:** `frontend/tests/design-amendments.ts` (+ `.test.ts`), `frontend/src/logic.test.ts`,
`docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md`, `CLAUDE.md`; regenerated
`.dc.html`, `logic.js`, `App.vue`, `pseudo.css`, `app.setup.js`.

- [ ] **Step 1: RED.** In `frontend/src/logic.test.ts`, drive `wizardVals().submit()` with a
      rejecting `listings.submit` and assert `wizSubmitted === false` and the preview still renders.
      Watch it fail.
- [ ] **Step 2:** Write A58.1 in `design-amendments.ts`, consuming A16.7's line.
- [ ] **Step 3:** `npm run gen:design && npm run gen:app && npm run gen:logic`.
- [ ] **Step 4: GREEN.** Re-run; add the no-adapter case and the success case.
- [ ] **Step 5:** Measure re-basing cold before/after; report the actual moved set.
- [ ] **Step 6:** `LOCAL_AMENDMENTS.md` row + CLAUDE.md paragraph. Commit.

---

## Task 2: The buyer's Property block stops fabricating (S5, S6, design, A58.2-A58.3)

**Finding S5.** `logic.js:1932` — `{ k: "Parking", v: "On-site" }` is a literal on every listing.
No field, no column, never asked. **Remove the row.**

**Finding S6.** `logic.js:1930` — a row labelled "Facility type" computed from `bldg`. Read the
listing's OWN `facilityType`; render NO row when it is absent (absent beats faked). The API half is
Task 5 — until it lands the value is undefined, so the row must disappear rather than fall back.

**Files:** as Task 1.

- [ ] **Step 1: RED.** Assert no Parking row exists, and that the Facility type row is absent when
      `facilityType` is undefined and reads the listing's own value when present.
- [ ] **Step 2:** A58.2 (delete the Parking row) and A58.3 (the facility-type row), both consuming
      their pristine lines.
- [ ] **Step 3-6:** regenerate, GREEN, measure re-basing, ledger + CLAUDE.md, commit.

**Outcome, measured (2026-09-23/24), correcting this task's own stated premise.** The premise this
task was dispatched on — that `detail` **and `mobile-detail`** both render the Property block — is
WRONG about the second, and the correction is recorded here rather than left for the next reader to
rediscover: `v.d?.sections` has exactly ONE reader in `App.vue` (the desktop detail screen), so the
phone frame renders no `sections` block at all and has never drawn the Property block. It cannot
move for this change, and it did not.

FOUR approved states move, each in BOTH oracles — `detail`, `detail-lightbox`, `detail-lightbox-next`
and `interest-modal`, exactly the four captures that reach the desktop detail screen. The node-level
DOM diff on `detail` is two removals of 121 lines each and ZERO additions (the two row `<div>`s),
with "Building status" and "Approximate square feet" surviving once each. `App.vue` and
`pseudo.css` regenerate byte for byte, the edits being script-only.

ONE of `baseline-manifest.json`'s thirteen frozen hashes therefore moves, `detail`
(`5facf0be…` → `af98330e…`), and it is RE-PINNED under **ruling D-C65** (John, 2026-09-24, on the
measurement: the two rows were fabricated, so removing them is the correction and the approved
screenshot must follow) — the A18/A34/A38/A53/A55/A57 mechanism. The other twelve are unmoved,
re-hashed from the PNGs after the write rather than inferred from the test passing. That is the
"unless the task says otherwise" of the global constraint above, spent once and recorded.

---

## Task 3: No buyer-facing string ever reads "null" (S8, design, A58.4)

**Finding S8.** `logic.js:1886` `p.docs + " full-time equivalent"`, `:1920` `p.docs + " FTE"`,
`:824`/`:2504` `p.docs + " doctors"`, `:1918` `p.services + "."` — each prints the word `null`.

**Required:** each reads as absent rather than as the word null. Use the design's own idiom for an
absent value (`money()` returns an em dash; the key-fact grid omits a row). Do NOT invent copy.

- [ ] **Step 1: RED.** For each of the four, assert the rendered string contains no `"null"` when the
      field is null. Watch all four fail.
- [ ] **Step 2:** A58.4a-d.
- [ ] **Step 3-6:** regenerate, GREEN, measure, ledger, commit.

---

## Task 4: `facility_type` is served (S6 backend, app-only)

**Finding S6.** The column is collected, validated and stored (`migrations/030:27`) and appears in no
`_SELECT` in `app/api/listings.py`. Serve it as `facilityType` on the listing payload and map it in
`frontend/src/listings/load.ts`'s `ApiListing`/`toPractice`.

**Ungated** — it is a building shape, not an identity fact, and the audit found no ruling gating it.

**Files:** `app/api/listings.py`, `frontend/src/listings/load.ts` (+ `.test.ts`),
`tests/api/test_listings*.py`, `docs/integrations/market-data-api.md` if it lists payload fields.

- [ ] **Step 1: RED** on both sides: a pytest asserting the field is served, a vitest asserting
      `toPractice` carries it.
- [ ] **Step 2:** implement. **Step 3:** GREEN, both suites at 100%. **Step 4:** commit.

---

## Task 5: `zip` and `est` are validated (§6, app-only)

**Finding §6.** `zip` accepts `banana` — truthiness client-side, `_text` server-side, no CHECK. A
nonsense ZIP silently places the practice at a city centroid. `est` accepts year 7 and 999999999;
the only bound is `INT_MAX`.

**Required:** `zip` must be a US ZIP (5 digits, optionally +4) — refuse `422` naming the field. `est`
must be within a plausible range; take the bounds from the data rather than inventing them (the
Browse "Year established" filter's own buckets, `logic.js:2283`, are the product's existing
vocabulary). Validate server-side in `app/api/seller_listings.py`; the client guard may follow but
the server is the gate.

- [ ] **Step 1: RED** — pytest driving `banana`, `7`, `999999999` through `patch_step`.
- [ ] **Step 2:** implement in `_text`'s caller / a new `_zip`, and bound `est`.
- [ ] **Step 3:** GREEN at 100%. Check no existing fixture uses an invalid zip
      (`tests/api/test_seller_listings.py:279,323,655` use `zip='7'` — they must be updated, not
      worked around). **Step 4:** commit.

---

## Task 6: The street address is collected (S9, design + app)

**Finding S9.** `EXACT_LOCATION` is a live, requestable, approvable capability whose approval
delivers `street: null` and `phone: null`, because no step collects either. The 2026-09-08 spec
deferred "the exact-location switch and the street field it needs" together; the 2026-09-18 directive
shipped the capability without the prerequisite.

**Required:** step 2 gains a street field and a telephone field. Both REQUIRED to submit — the
address is what `EXACT_LOCATION` exists to release, and a listing that cannot deliver it makes the
capability a lie. The privacy toggle continues to govern DISPLAY only.

**This is the largest task.** It touches `STEP_FIELDS`, `step-fields.json`, the design's step-2
fields array, `_complete_enough`, and `listing_submittable_ck`. The six existing wizard-created
listings on QA have no street — they must not be broken by a new NOT NULL constraint; enforce at
submit, not in the schema.

- [ ] **Step 1: RED** — pytest: a draft with no street refuses at submit; a PATCH of step 2 with a
      street stores it; `GET /api/listings/{id}` with an EXACT_LOCATION grant serves it.
- [ ] **Step 2:** the API half (`STEP_FIELDS[2]`, `columns_for`, `_complete_enough`).
- [ ] **Step 3:** the design half — A58.5, step 2's fields array, composed from the step's own
      `text()` idiom. Regenerate.
- [ ] **Step 4:** GREEN both suites, measure re-basing (step-2 captures WILL move — that is ruled).
- [ ] **Step 5:** ledger + CLAUDE.md. Commit.

---

## Task 7: Photo management reaches the UI (U1, U2, design + app)

**Finding U1/U2.** `reorder_photos` and `delete_asset` are built, tested, rate-limited and audited,
with ZERO callers. `photos[0]` IS the buyer-facing hero, so reordering is choosing the cover.
Step 6 offers one action per photograph: a `window.prompt`.

**Required, in this order of value:**
1. **Delete** a photograph or document (the adapter's `remove` already exists).
2. **Reorder**, with position 1 labelled as the cover — the design's own words for what it is.
3. Replace the caption `window.prompt` with `frontend/src/admin/noteDrawer.ts` (A54's drawer, app-only,
   carries no amendment).

**Constraint:** ruling A-SL37/D-SL25 blocks reordering or deleting a SEEDED photograph until
seed-to-asset conversion lands. Respect it — the control must not offer what the API will refuse.

- [ ] **Step 1: RED** — vitest on the step-6 tile map: a delete control exists and calls
      `listings.remove`; a reorder control calls `listings.reorder`; neither renders for a seeded row.
- [ ] **Step 2:** the adapter wiring in `frontend/src/listings/seller.ts`.
- [ ] **Step 3:** the design half — A58.6, composed from V3's own elements. Regenerate.
- [ ] **Step 4:** GREEN, measure re-basing, ledger, commit.

---

## Task 8: The disclosure toggles say what they do (S1, S3, S4, S7, design + app)

**RUN THIS TASK BEFORE 9, 10 AND 11** — it sets the disclosure model those three build on, and it
depends on what Tasks 1-7 made true. It is the last of the original set, not the last of the plan.

**RULED BY JOHN, 2026-09-24 — D-C66: CORRECT THE BEHAVIOUR, not the copy.** The ceilings become
per-buyer releasable. This knowingly changes the 2026-09-18 per-buyer disclosure directive's
ceiling-AND-grant, and that directive must be amended in the same release rather than left
contradicted.

**Why this is the right direction and not merely the bigger one:** the labels have ALWAYS promised
release on approval ("Keep practice name and address hidden **until I approve a buyer**",
`frontend/src/logic.js:1757`; "Release revenue as a range **until I approve a buyer**", `:1758`).
The behaviour is what diverged from the promise, so correcting the behaviour honours what every
seller was told, while correcting the copy would have ratified a narrower product than the one they
were sold. (Those two line numbers moved during Tasks 1-7 and are re-measured as of `047db60`;
`docsLocked` is now `:1759`. `logic.js` is generated — read them, never edit them.)

**The precedent is already in the codebase.** `showIdentifiable` is the one toggle of the four that
works as a genuine per-buyer gate: `NOT_SHOW` + no grant serves the redacted derivative, `NOT_SHOW`
+ `UNREDACTED_IMAGES` serves the display variant (`app/privacy/delivery.py:80-86`). Tasks here make
`anon`, `revBand` and `docsLocked` behave the way it already does. Follow that shape rather than
inventing one.

**Required behaviour, per toggle:**
| Toggle | Unapproved buyer | Buyer granted the matching capability |
|---|---|---|
| `anon` ON | anonymised name, no street/zip/phone, no pin | name, street, zip, phone, exact point — via `IDENTITY` / `EXACT_LOCATION` |
| `revBand` ON | no revenue figure | the exact figure — via `FINANCIALS` |
| `docsLocked` ON | document TITLES visible, bytes refused | titles and bytes — via the document's own capability |
| `showIdentifiable` OFF | redacted derivative | display variant — via `UNREDACTED_IMAGES` (already correct, do not change) |

### The shape of the change: AND becomes OR

Every ceiling term in `serialise` (`app/api/listings.py`) today reads *ceiling AND grant*. Measured
at `047db60`, the three that change are:

```python
disclosed = ceiling and "EXACT_LOCATION" in capabilities          # ceiling = bool(row["location_disclosed"])
named     = bool(row["name_disclosed"]) and "IDENTITY" in capabilities
"rev": row["rev"] if row.get("rev_disclosed") and "FINANCIALS" in capabilities else None
```

Under D-C66 the ceiling becomes the PUBLIC DEFAULT and the grant RELEASES on top of it, so each
becomes *ceiling OR grant*. A seller who leaves a ceiling open is publishing to everyone (unchanged);
a seller who shuts it is publishing to nobody until they approve a buyer (the promise the label makes).

**THE TRAP — the pin.** `_point(row["lat"], exact=disclosed, ceiling=ceiling)` takes the ceiling as a
SEPARATE argument from `disclosed`, and returns `None` whenever `ceiling` is false. Flip `disclosed`
to OR and leave `ceiling` alone and a granted buyer gets the street, postcode and telephone number
but **still no pin** — three quarters of the table's first row, which reads as done. The `ceiling`
argument must take the same OR. A25's "no point, no pin" is a different guard (`value is None`, for a
listing with no coordinates at all) and stays exactly as it is.

### `docsLocked` — and the one comment that will mislead you

The brief this task was first written from said `_documents` "returns `[]` before it queries". That is
true only of the CEILING-SHUT branch, and the rest of that function is already right: with the ceiling
OPEN, titles are served to an unapproved buyer UNCAPPED, and an ungranted buyer sees a generic label
(`"Financial packet"` / `"Floor plan"`, `_DOCUMENT_LABEL`) in place of the seller's own filename,
because a filename like `123_Main_St_Floor_Plan.pdf` would publish the address straight past
`location_disclosed` (security review, 2026-09-19). **That control is correct, is not part of D-C66,
and must survive this task unchanged.**

So the only change on the list side is that `ceiling_open` stops gating the LIST: under D-C66 titles
are visible whether or not `docsLocked` is on. Expect a cost, and note it rather than hide it — today a
locked listing runs no query at all, and after this it runs one per single-listing read.

**On the bytes route (`app/api/seller_listings.py:1850-1856`), read the docstring above it before you
touch it.** It records a real past incident: a round of that module once let disclosure and "published"
stand in for authorization alone, and any signed-in member could download a seller's documents the
moment one ceiling flag flipped. D-C66 removes `bool(disclosed)` from that `and` chain. **That is not
the same change and you must be able to say why:** the incident removed the GRANT, this removes the
CEILING and keeps `has_capability` and `status == "published"` exactly where they are. If your diff
weakens or short-circuits `has_capability`, you have reproduced the incident — stop.

### SAFETY — the one thing that must not be got wrong

This ruling makes data MORE reachable than it is today, and the AND→OR flip moves where the risk
lives. Under AND, a bug that wrongly added a capability still met a shut ceiling. Under OR, the
capability set is the ONLY thing standing between a listing and disclosure — its blast radius grows,
so re-prove its fail-closed behaviour rather than inheriting it.

Verified present at `047db60` and to be kept: `authorized_capabilities` returns `frozenset()` for an
absent buyer and for a missing row (`app/disclosure/access.py:36`, `:40`); `authorized_capabilities_bulk`
seeds every listing to `frozenset()` before it queries (`:54`); `covers()` returns `frozenset()` for an
unknown or absent level (`app/disclosure/levels.py:26`); `capability_for_document_kind` falls back to
`FULL_CONFIDENTIAL`, the broadest grant, for any kind the table has not been taught
(`app/disclosure/levels.py:34-39`). Add no path where a missing value reads as permission.

**Not in scope:** the buyer's document list is four hard-coded fixtures with no reader for the real
`documents[]` (finding S7). Wiring that is its own task; note it in the report.

**Files:** `app/api/listings.py` (the three ceiling terms, `_point`'s `ceiling` argument, `_documents`'
list gate), `app/api/seller_listings.py` (the bytes route's ceiling term),
`docs/superpowers/specs/2026-09-18-per-buyer-disclosure-directive.md` (amended, with the ruling
recorded), `frontend/tests/design-amendments.ts` if any copy still misstates the corrected behaviour,
plus tests both sides.

- [ ] **Step 1: RED** — pytest per toggle, and per FIELD within `anon` (name, street, zip, phone AND
      the pin are five separate assertions, not one): ceiling shut + no grant hides; ceiling shut +
      matching grant RELEASES. The second assertion is the one that fails today. Watch each fail.
- [ ] **Step 2:** change the ceiling terms, one toggle at a time, keeping fail-closed. Run the suite
      between toggles so you know which change moved which test.
- [ ] **Step 3:** amend the 2026-09-18 directive to record D-C66, quote what it supersedes, and say
      why. Do not delete the superseded sentence — supersede it in place.
- [ ] **Step 4:** re-read every step-7 and step-2 label against the new behaviour; correct only what is
      still false. Measure re-basing the A33 way.
- [ ] **Step 5:** full gates both sides; report the measured re-basing and the fail-closed proof —
      including one test that proves a buyer with NO grant still sees nothing after the flip.

---

## Task 9: The seller grants per buyer, per capability (D-C67, design + app)

**RULED BY JOHN, 2026-09-24 — D-C67: "all toggles must be fully functional and SELLER must be able
to manage it all and per seller."** Read with D-C66: the ceilings become per-buyer releasable, and
the seller is the one who decides, per buyer, what is released.

**RUN AFTER TASK 8** — D-C66 makes the ceilings releasable; this gives the seller the control that
chooses what a given buyer receives. Before Task 8 there is nothing to choose between.

**The gap, measured.** The server and the adapter already support it and no control uses it:
* `app/disclosure/requests.py::decide` takes `disclosure_level` and writes
  `approved_disclosure_level` (`:137-150`).
* `frontend/src/requests/seller.ts:31` types it — `decide(id, action, level?, reason?)`.
* The design never passes it (`frontend/src/logic.js`'s Accept sends no level), so `decide` falls
  back to the REQUESTED level, which `app/api/requests.py:170` defaults to `FULL_CONFIDENTIAL` —
  **all five capabilities, on every approval.**
* `app/disclosure/levels.py` already models the five (`IDENTITY`, `EXACT_LOCATION`,
  `UNREDACTED_IMAGES`, `FINANCIALS`, `FLOOR_PLANS`) and `covers()` already maps a level to its set.

**Required:** on an inbox row awaiting a decision, the seller chooses WHICH capabilities this buyer
receives, and approves that set. The existing all-five path stays reachable as one choice, not the
only one.

**Composition — invent nothing.** Compose from V3's own elements, the A8/A41-A47 process. The
interest modal's scrim, title, error slot and primary/secondary pair is the established shell
(`frontend/src/admin/noteDrawer.ts` is the worked precedent and carries no amendment); step 7's own
checkbox-and-help rows are the established shape for a set of disclosure choices. Do not invent a
new control, a new colour or new copy for a capability — `app/auth/labels.py` and the step-7 labels
already name these things in the product's voice.

**Fail closed, and this is the whole risk of the task:** an approval that names no capability grants
NOTHING, never everything. The set the seller ticked is the set stored; an empty set is a refusal to
release, not a silent `FULL_CONFIDENTIAL`. `covers()` returning `frozenset()` for an unknown level is
the existing precedent — keep it.

**Also required:** the seller must be able to SEE what a given buyer currently holds, on the row,
and to narrow it later. Withdraw (A53/A57) already removes everything; narrowing is the new half.

- [ ] **Step 1: RED** — pytest: approving with a named subset stores exactly that subset; approving
      with an empty set releases nothing; a buyer holding only `FINANCIALS` gets the revenue and NOT
      the address. The last one is the proof D-C66 and this task meet correctly.
- [ ] **Step 2:** the adapter half — pass the chosen level through `decide`.
- [ ] **Step 3:** the design half — the chooser on the inbox row, composed from V3's own elements.
      Next free amendment id in family A58.
- [ ] **Step 4:** the row shows what the buyer holds now.
- [ ] **Step 5:** full gates both sides; measured re-basing; fail-closed proof stated explicitly.

---

## Task 10: Every disclosable datum has a control, and every surface honours it (D-C68)

**RULED BY JOHN, 2026-09-24 — D-C68: "this applies to every view, address, pricing, images, etc."**
Read with D-C66 (ceilings become per-buyer releasable) and D-C67 (the seller chooses per buyer):
the seller's control covers EVERY disclosable datum, and EVERY buyer-facing surface obeys the same
answer.

**RUN AFTER TASKS 8 AND 9.** Those build the mechanism; this completes its coverage.

### Part A — the coverage gap, measured

`app/disclosure/levels.py:8` models five capabilities: `IDENTITY`, `EXACT_LOCATION`,
`UNREDACTED_IMAGES`, `FINANCIALS`, `FLOOR_PLANS`. Measured against `app/api/listings.py`'s
serialiser, these are served with **no gate of any kind**:

`price` (:557) · `type`, `est` (:558-559) · `city`, `state`, `area` (:552) · `hours` (:556) ·
`docs`, `rooms`, `sqft`, `bldg` (:558-559) · `ownership` (:611) · `services` (:601) ·
`facilityType` (Task 4)

**`price` is the one that is not merely an omission.** The audit recorded it as deliberate — "Asking
price is public by design and promises nothing else … no privacy control is offered for it on step 3
or step 7, and none is implied" — so gating it is a NEW product decision, not a repair, and it has
consequences the implementer must NOT absorb silently:

* **The Browse card and the results rail are built around a price.** A listing with no price shows
  what? The design has no treatment for it. Absent beats faked, so the row/card must degrade to
  something the design already draws, or this needs John's ruling on new copy.
* **The price filter leaks the same way revenue does.** Finding S11: `null / 1000 === 0` puts a
  hidden revenue inside "Under $1M". A hidden price will do exactly the same to "Under $500K" unless
  the filter is fixed in the same change. **Fix the filter in this task or the fix creates the leak
  it is meant to close.**
* **Sort by price** has the same exposure.

`services` and `hours` are the other two that matter — finding S10: they are published verbatim to
every member while the image pipeline feeds those same strings to the redactor that scrubs signage
off photographs. A free-text field is where a seller defeats their own anonymity.

**Deliverable for Part A:** propose the capability set that covers every disclosable datum, name
which existing capability each field joins or which new one it needs, and STOP for John's ruling
before adding any new capability. Adding a capability changes `REQUESTABLE_LEVELS`, the buyer's
request surface and the seller's chooser, so it is his call, not an implementer's.

### Part B — every surface honours the same answer

The audit found the surfaces already diverge, and the mechanism is the reason:

* `frontend/src/listings/load.ts:22` fetches `/api/listings?limit=200` and **nothing else**. The
  single-listing route — the only caller of `_documents` — is never requested by the app, so the
  detail screen is rendered from the LIST payload.
* Consequently the buyer's document list is four hard-coded fixtures (`logic.js:1891-1896`) and
  `documents[]` has no reader at all (finding S7).

**Required:** one served answer, honoured by every surface a buyer can reach — Browse card, results
rail, docked panel, detail, interest modal and the phone frame. A datum hidden by the seller must be
hidden on all of them, and a datum released to a buyer must appear on all of them.

- [ ] **Step 1:** enumerate every buyer-facing surface and every disclosable datum it renders, as a
      matrix, from the code. This is measurement, not design.
- [ ] **Step 2: RED** — one test per (datum × surface) that a hidden datum is absent and a granted
      datum is present. The matrix from Step 1 is the test list.
- [ ] **Step 3:** STOP and surface the Part A proposal for John's ruling before implementing any new
      capability.
- [ ] **Step 4:** implement, fail closed throughout.
- [ ] **Step 5:** full gates, measured re-basing, and the price-filter leak proved closed.

---

## Task 11: The buyer's screens DRAW the released address (S9, second half)

**Found by Task 6, measured not assumed:** `p.street` and `p.phone` occur **ZERO** times in
`frontend/src/logic.js`, and `frontend/src/listings/load.ts::toPractice` copies neither onto the
design's `Practice`. Task 6 closed S9's DATA gap — an approved buyer's payload now carries the real
street and telephone — but **no screen shows either**. The detail's "General location" row is still
`p.area + ", " + stateOf(p.market)` (`logic.js:1902`).

So `EXACT_LOCATION` today: the seller supplies an address, the seller approves a buyer, the API
serves it to that buyer, and the buyer sees the same city they saw before. The capability is
honest on the wire and invisible on the screen.

**RUN AFTER TASK 8** — D-C66 changes when the address is released, and this draws what is released.

**Required:** the detail screen shows the street and the telephone when the payload carries them,
and shows today's area-and-state line when it does not. Absent beats faked: no placeholder, no
"address withheld" copy unless John rules one.

**This is a NEW ELEMENT in the approved design**, so it takes the A41-A47 composition process:
compose from V3's own declarations, invent no new row style, colour or copy. The Community Context
card's own ` · `-joined label-and-value idiom and the key-fact grid are the two existing shapes.
Family A58, next free sub-id.

- [ ] **Step 1: RED** — a vitest that `toPractice` carries `street`/`phone`, and a logic test that
      the detail renders them when present and renders today's line when absent.
- [ ] **Step 2:** `load.ts` — copy both onto `Practice`, omitting the key when absent (the
      `facilityType` precedent from Task 4).
- [ ] **Step 3:** the design half, composed from V3's own elements.
- [ ] **Step 4:** measured re-basing; the states that render the detail WILL move and `detail` is a
      frozen hash — report it, do not re-pin without saying so.
