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

## Task 8: The disclosure toggles say what they do (S1, S3, S4, S7, design, A58.7)

**RUN THIS TASK LAST** — it rewrites approved design copy and depends on what Tasks 1-7 make true.

**Findings S1, S3, S4, S7.** Three of four step-7 toggles are labelled for the state they do not
produce; no revenue range exists; step 2 promises a map pin the ON state never draws; `docsLocked`'s
help describes the opposite of its behaviour.

**Required:** every toggle's label and help state what the code does. Two candidate directions, and
the implementer must STOP and surface rather than choose:
* **(a) Correct the copy** — cheapest, truthful, and the toggles remain permanent suppressors.
* **(b) Make the behaviour match the copy** — ceilings become per-buyer releasable, which is a change
  to `app/api/listings.py`'s ceiling-AND-grant and therefore to the 2026-09-18 directive.

This is John's ruling to make. Prepare both, recommend, and stop.

- [ ] **Step 1:** enumerate every affected string with its current behaviour, in the report file.
- [ ] **Step 2:** STOP and surface to the controller for John's ruling before any edit.
