# Seller Listing Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the approved seller wizard true. A seller's eight steps, their photographs and documents, the preview, Submit, the dashboard's Continue / Edit / Pause / Republish / Withdraw / View actions and the VIN Foundation's review of what they submit all persist — against a real `seller_id`, on object storage, through a `draft → in_review → published` lifecycle with `paused`, `declined` and terminal `withdrawn` — and the eighteen seeded QA hospitals become `seller@practice-match.test`'s own listings so that opening **Edit** on one shows the hospital instead of eight screens of em dashes. No screen changes: every pixel of the approved design stays where it is.

**Architecture:** Seven artefacts, in dependency order. (1) `migrations/030_listing_owner_and_status.sql` puts `seller_id` on `listing`, widens the `status` and `type` CHECKs, relaxes the six `NOT NULL`s the wizard cannot fill and replaces them with a *submittable* and a *publishable* CHECK; `migrations/031_listing_asset.sql` adds the asset table. (2) `app/storage.py` is the shared `ObjectStore` (Census Task A2's class, moved here by controller amendment **A-SL1**, plus `delete()`), and `app/media/encode.py` lifts `scripts/prepare_photos.py`'s normalisation rules so a seller's phone photograph loses its GPS EXIF on the way in. (3) `app/api/seller_listings.py` (`/api/seller`) is the wizard's own surface — create, read, per-step PATCH, photo upload/reorder/delete, document upload and the locked document read, submit, and the dashboard's three status transitions. (4) `app/api/admin_listings.py` (`/api/admin`) is the review queue and the three decisions. (5) `scripts/seed_listings.py` gains ownership, so a re-seed re-asserts it, and the committed seed photographs become the wizard's step-6 tiles by caption. (6) The frontend wiring is a **ruled D15 amendment family** against the design bundle plus two mapping modules outside `logic.js` (`frontend/src/listings/seller.ts`, `frontend/src/admin/listings.ts`) — `logic.js`, `App.vue` and `app.setup.js` are generated, never hand-edited. (7) The oracles keep running against the design's own fixtures (spec 2026-09-06 **D6**), so `frontend/tests/baseline-manifest.json` does not move by one byte and the API path is proved by pytest, vitest and a value-assertion flow spec instead.

**Tech Stack:** PostgreSQL 16 + PostGIS 3.5 · FastAPI + psycopg2 (`app.db.sync_conn`) · Redis (`app.cache.sync_redis`) for the listings cache and `app.auth.limits` · boto3 against the approved `practice-match-data` bucket, `moto[s3]` in tests, `boto3-stubs[s3]` for `mypy --strict` · Pillow (already a main dependency) for the WebP pipeline · Celery + the existing `app/mail` outbox → Resend pipeline · Vue 3 + TypeScript 6 · Vitest 3 · Playwright 1.63.

**Branch:** worktree `feat/seller-lifecycle` cut from `main`. See **Per-worktree environment** at the foot of this plan for its database, Redis and Playwright ports — this machine runs six other worktrees and they must not share a database.

---

## Global Constraints

Every task's requirements implicitly include this section.

### John's approval, verbatim

> **"SPEC APPROVED. Cut the implementation plan with the four stated defaults: Declined dashboard pill; reviewer supplies state + metro at publish; documents limited to PDF/CSV/XLSX; and no confirmation dialog before an edit takes a published listing off-market."**
> — John Dean, 2026-09-08 ~23:20 WITA, on `docs/superpowers/specs/2026-09-08-seller-listing-lifecycle-design.md`

And the rulings the spec is built on, verbatim (spec §1):

> **Storage:** Use object storage as the production architecture now; do not build a Postgres-bytea architecture intended for a later swap.
> **Ownership:** Assign all eighteen QA seed listings to `seller@practice-match.test`, with real `seller_id` ownership.
> **Documents:** Seller uploads immediately; preserve the existing staff/seller approval gating and 'Locked — seller approval' behavior. No new approval workflow in this slice.
> **Photos:** Keep the existing 4-photo seller-upload cap.
> **Published edits:** Editing a published listing re-enters review and removes it from the market until approved again, consistent with the approved design.
> **Release:** Ship seller-wizard read + write capability together. Do not release a read-only intermediate 'Edit shows the truth' feature.

And his standing rule for the admin surface: **every Admin tab shows real database data, never dummy rows.**

### The spec's decisions, verbatim (`docs/superpowers/specs/2026-09-08-seller-listing-lifecycle-design.md` §15)

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

**Two of those decisions are overtaken by facts on the ground and are corrected by controller amendments below, not by an implementer's judgement:** D2/D12's migration number `017` (**A-SL3**) and D23's family id `A13` (**A-SL4**).

### The spec's four approved defaults (§16, ruled by John)

1. **Q1 — the declined pill.** `statusPill` gains a `declined` entry, label **"Declined"**, tone `bad` (`["Declined", "#494949", "#ffffff", "#494949"]`, the exact triple `withdrawn` uses).
2. **Q2 — `state` and `market`.** The reviewer supplies them at the first `publish`; there is no wizard field and inventing one is forbidden.
3. **Q3 — the document allow-list.** PDF, CSV and XLSX only, the last two badged with the uppercased extension.
4. **Q4 — no confirmation dialog** before an edit takes a published listing off-market. The design has none, and the submitted card already says edits after publication go through the same review.

### Controller amendments (binding; read before Task SL1)

**A-SL1 (from the spec, §6/D14) — `ObjectStore` lives in `app/storage.py`, and this plan must not write a twin.**
The Census plan's Task A2 (`docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md`) writes `ObjectStore`. Two sub-projects now depend on it, so the module's path becomes **`app/storage.py`** rather than `app/census/storage.py`. Everything else about Task A2 is taken verbatim: the constructor `ObjectStore(endpoint_url, bucket, access_key, secret_key, region='auto')`, `put_immutable` / `get` / `exists`, `from_settings(settings) -> ObjectStore | None` returning `None` with a logged warning (never a crash) when unconfigured, and the moto tests. **This plan adds exactly one method, `delete(key) -> bool`.** Task **SL2** is written so that either landing order works — see its Step 0, which branches on whether `app/storage.py` already exists — and `app/storage.py` is the one owner of the class in both orders. The four settings are Task A2's, unchanged: `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, all optional on `Settings`. The bucket is `practice-match-data` in every environment (Railway buckets are environment-scoped; the spec's controller note settles open question 5, and QA's bucket already exists under that name).

**A-SL2 — the two frozen Admin/seller oracles keep the design's own rows, and the stub is empty rather than round-tripped.**
`seller-dash` and `admin-listings` are both among CLAUDE.md's **thirteen frozen screens**, both are approved states in `frontend/tests/screens.ts`, and both get a pixel baseline *and* a node-for-node DOM snapshot. Spec §9 asks for `GET /api/seller/listings` to be stubbed "with the design's own four `sellerListings` fixtures". **That round-trip is not constructible** and this amendment rules the alternative:
- the design's seller rows carry prose no column can produce — `note: "Live since August 24 · 34 views, 2 requests"` needs a view count and a request count that do not exist in this slice;
- the design's fifth Admin Listings row is `Flagged` / `Investigate`, and D24 says outright that `listing.status` has no `flagged` value and inventing one is out of scope.
So: **the harness stubs both collection endpoints with `{"items": [], "next_cursor": null}`, and the amendment family keeps the design's own literal rows whenever `items` is not a non-empty array.** That is controller amendment **A-L6.2 (1)**'s ruled shape applied unchanged ("`loadListings` returns `false` and the design's fixtures stay whenever `items` is not a non-empty array"), it makes the design's fixture rows the oracle's data exactly as spec 2026-09-06 D6 requires, and it moves neither hash. The real mapping is proved by vitest (against the design's own `adminVals()` / `sellerVals()` output) and by `frontend/tests/listing-flows.spec.ts` against the real, seeded API. **Open question 1 for the controller** (see Pre-flight) is the one thing this leaves: what a real seller with zero listings should see.

**A-SL3 — the migration numbers are `030` and `031`, not `017`.**
The spec was written before the Census branch numbered its own. `.worktrees/feat-census-data-layer/migrations/` already holds `017_census_registry.sql`, `018_census_geo.sql` and `019_census_measures.sql` (Census plan Task A1). `scripts/migrate.py` applies `[0-9][0-9][0-9]_*.sql` in name order through a ledger, and **an applied migration is never edited in place** (MEMORY: "Local DB migration hazard"). This plan therefore takes the next two free numbers:
- `migrations/030_listing_owner_and_status.sql` — `seller_id`, `facility_type`, the widened `status` and `type` CHECKs, the six relaxed `NOT NULL`s, the submittable and publishable CHECKs, the `(seller_id, updated_at DESC)` index;
- `migrations/031_listing_asset.sql` — the `listing_asset` table and its indexes.

Two files rather than one because they are two reviewable units with two different failure modes, and because a `listing_asset` table that references `listing` reads better after the `listing` change than inside it. Wherever the spec says "`017`", read "`030`/`031`". If the Census branch has NOT merged when this branch cuts, the numbers still stand: `030`/`031` are free either way and taking them cannot collide.

**A-SL4 — the amendment family id is DERIVED at branch time, never typed from memory.**
The spec names family **A13**. `.worktrees/feat-design-dropdowns` is already adding `A13.1`–`A13.5` and pins `toHaveLength(87)`; a second family may follow it. `frontend/tests/design-amendments.test.ts` pins the set **both ways** — an explicit `AMENDMENT_IDS` array *and* a numeric `toHaveLength(…)` — so a stale id or a stale count is a hard failure, not a warning. Task **SL7 Step 0** therefore *computes* the next free family integer from the tree and the plan's literals are renumbered in one `sed`. Throughout this plan the family is written **`A15`**, which is what it will be if `feat/design-dropdowns` lands `A13` and one more family lands `A14`; **do not hard-code 15, 87 or any other count from this document** — every number that a test pins is read off the branch at the moment it is written.

**A-SL5 — the release number is decided at hand-back, not here.**
`main` is at `0.1.3` (`pyproject.toml:3`, `frontend/package.json:4`, kept in lockstep by `tests/test_versions.py`). The Census release takes `0.1.4`. Whether this branch is `0.1.4` or `0.1.5` depends on which merges first, so Task **SL9 Step 4** reads `main`'s version at hand-back and bumps by exactly one patch in lockstep. No task before SL9 touches either file.

### The programme's standing rules

- **(a) 100 % lines AND branches, backend.** Every task's local gate is `poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100`, exactly as `.github/workflows/quality.yml` runs it. `scripts/` is in scope because Task SL6 changes `scripts/seed_listings.py`.
- **(b) 100 % lines, branches, functions and statements, frontend.** `cd frontend && npx vitest run --coverage`. The documented `coverage.exclude` list in `frontend/vite.config.ts` is **not widened**: `frontend/src/listings/seller.ts` and `frontend/src/admin/listings.ts` are covered at 100 %.
- **(c) No suppressions.** No `# pragma: no cover`, no `# noqa`, no `# type: ignore`, no `@ts-expect-error`, no `@ts-nocheck`, no `assert` as control flow in production code.
- **(d) `poetry run mypy app --strict` — 0 errors; `poetry run ruff check app tests scripts` — 0 findings**, on ruff's default set plus `extend-select = ["I", "RUF"]`, no ignores added. `boto3-stubs[s3]` is a dev dependency precisely so the storage module type-checks strictly rather than being excused.
- **(e) Every route is guarded or in `PUBLIC_ROUTES`.** `tests/auth/test_permissions.py::test_every_route_is_guarded_or_public` walks `create_app()`. This plan adds twelve guarded routes and **adds nothing to `PUBLIC_ROUTES`**.
- **(f) `require(...)` is hoisted to a module-level constant and never wrapped.** `app.auth.deps.permission_of` is keyed by object identity; a wrapper makes the guard unreadable and fails the build.
- **(g) An AUDITED permission's handler calls `audit.write(` in its OWN body.** `tests/auth/test_permissions.py::test_audited_permissions_are_written_by_their_handlers` reads `inspect.getsource(route.endpoint)`; delegating to a helper reads as unaudited. `listing.publish` joins `AUDITED` in Task SL5 and its handler writes on every branch.
- **(h) No new secret, and no secret in git.** `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` are set in Railway per service per environment and appear in `.env.example` and `DEPLOY.md` as **names with placeholder values only**. `gitleaks detect` stays at 0 findings. The persona password lives in the operator's macOS Keychain and never in Railway (A-S6.2, `docs/superpowers/plans/2026-09-08-account-screens.md`).
- **(i) Every new setting is documented.** `tests/test_docs.py::test_every_setting_is_documented_in_env_example_and_deploy_md` requires a row in **both** `.env.example` and `DEPLOY.md` for every field on `Settings`. Whichever of this plan and the Census plan adds the four `S3_*` fields also adds the eight rows.
- **(j) Every new Python script is in CI's strict-mypy list.** `tests/test_docs.py::test_ci_strict_mypy_covers_every_python_script` pins `.github/workflows/quality.yml`'s script list against the tree. This plan adds no new `scripts/*.py`, but it does add `app/storage.py` and `app/media/encode.py`, which are inside `mypy app --strict` already — confirm, do not assume, in SL2 Step 5.
- **(k) The pixel gate is the arbiter, at zero tolerance.** `frontend/tests/playwright.config.ts` stays at `maxDiffPixels: 0` beside `threshold: 0.1`. `frontend/tests/baseline-manifest.json` must not move: the thirteen frozen screens are `detail`, `mobile-detail`, `mobile-list`, `requests`, `seller-dash`, `wizard-step-1`, `wizard-step-7`, `wizard-preview`, `wizard-done`, `admin-users`, `admin-listings`, `admin-requests`, `admin-data-sources`. **Five of them are this plan's own screens.** A moved hash is this plan leaking into the design's pixels — stop and diff, never rebaseline.
- **(l) `logic.js`, `App.vue`, `app.setup.js` and `frontend/src/generated/pseudo.css` are GENERATED.** Every UI wiring change is a D15 amendment in `frontend/tests/design-amendments.ts` plus a row in `LOCAL_AMENDMENTS.md`, then `npm run gen:design && npm run gen:app`. `frontend/tests/app-generated.test.ts` pins `logic.js` byte-for-byte against the amended design's `<script data-dc-script>` block and requires `app.setup.js` to declare every prop the design declares. A hand edit to any of the four is a STOP.
- **(m) Surgical diffs.** The change contains the ask and nothing else. No drive-by refactors, no reformatting, no removal of a function or feature while doing unrelated work.
- **(n) Deviations STOP.** Any divergence from this plan or the spec — a `find` string that does not match, a baseline hash that moves, a coverage arm no request can reach — **stops work and is reported to the controller**, who batches it to John (MEMORY: "Deviations must be vetted"). Do not improvise a substitute, do not widen a tolerance, do not relax a bound.
- **(o) QA first, then production.** `scripts/deploy.sh QA` → click-through on https://qa.foundation.vin → `scripts/deploy.sh production` → `scripts/verify-deploy.sh production`. Before ANY Railway action run `railway status` and read back **Project: Practice Match**. Production runs `SITE_MODE=coming_soon` and is **never seeded** by this sub-project.
- **(p) Conventional commits, explicit pathspecs, both remotes.** Every commit names its files (`git add <path> …`), never `git add -A`. Every commit message carries the trailer:

  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  ```

  Pushed to both `origin` (vin-swe/practice-match) and `production` (johndean/practice-match) when the branch is handed back.
- **(q) The suite clock.** CI's backend job is `timeout-minutes: 30`. The moto tests and the WebP ladder are the only slow additions; keep every image fixture under 200 × 200 except the two that must exceed `MAX_EDGE_PX`, and never sleep in a test.

---

## Preconditions

This plan does not start until every check below passes **in the `feat/seller-lifecycle` worktree**. Verify each by running it, not by memory; a failing check is a **STOP**, not something to work around.

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-seller-lifecycle"

# --- the identity surface this plan builds on (Wave 2a, merged) ---
grep -n "^def require(perm: str)" app/auth/deps.py                       # 342
grep -n "^def write(" app/auth/audit.py                                  # 43
grep -n "^def hit(" app/auth/limits.py                                   # 59
grep -n '"listing.manage_own"' app/auth/permissions.py                   # 24 — seller
grep -n '"listing.review": _STAFF, "listing.publish": _STAFF' app/auth/permissions.py   # 38
grep -n "^AUDITED = frozenset" app/auth/permissions.py                   # 49 — SL5 adds ONE name here
grep -n "^ADMINISTRATIVE = frozenset" app/auth/permissions.py            # derived; unchanged by this plan

# --- the listing read surface (Seed Listings, merged) ---
grep -n "^def _error" app/api/listings.py                                # 90
grep -n "^REQUIRE_LISTING_READ = require" app/api/listings.py            # 73
grep -n "^def serialise" app/api/listings.py                             # 166
grep -n "^def photo_file" app/api/listings.py                            # 152
grep -n 'listings:v1:' app/api/listings.py                               # the cache key this plan must invalidate
grep -n "app.include_router(listings_router)" app/main.py                # inside `if settings.site_mode == "app":`
ls migrations/016_listing.sql

# --- the fixtures the tests name (do NOT invent a `scratch_db`) ---
grep -n "^def scratch_dsn\|^def conn\|^def redis" tests/conftest.py      # 103 / 134 / 147
grep -n "^def member\|^async def client\|^def auth_headers" tests/api/conftest.py   # 71 / 59 / 26

# --- the seeder and the persona ---
grep -n "^def seed(" scripts/seed_listings.py
grep -n "seller@practice-match.test" scripts/seed_persona.py
ls seeds/hospitals.json seeds/hospitals/photos/index.json

# --- the design gates ---
ls frontend/tests/baseline-manifest.json frontend/tests/design-amendments.ts
grep -c "^| A" docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md
node -e "import('./frontend/tests/design-amendments.ts')" 2>/dev/null || true   # the family/count derivation lives in SL7 Step 0
```

**Migration numbers — check, do not assume (A-SL3).**

```bash
ls migrations/                                    # 001,002,010–016 on main
ls ../feat-census-data-layer/migrations/          # + 017,018,019 on the Census branch
```

Expected: `030` and `031` are free in both trees. If they are not, **STOP** and report — renumbering an applied migration is forbidden and the fix is the controller's.

**The `ObjectStore` landing order — check, then choose the arm (A-SL1).**

```bash
ls app/storage.py 2>/dev/null && echo "Census A2 landed first — SL2 takes the REBASE arm" \
                              || echo "this plan writes it — SL2 takes the GREENFIELD arm"
```

**Coverage baseline, on the untouched branch, before Task SL1:**

```bash
docker compose -f docker-compose.dev.yml up -d
poetry install
DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_seller \
  poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
cd frontend && npm ci && npx vitest run --coverage && npm run build && cd ..
```

Expected: both PASS. If the backend gate fails on the untouched branch, **STOP and report** — Task SL1's own gate would otherwise fail for a reason that has nothing to do with this plan, and lowering the floor is not an option (Global Constraint (a)).

**The oracle baseline, before Task SL7** (so a later move is provably this plan's):

```bash
cd frontend && npm run test:visual:baselines && npm run test:e2e && cd ..
git -C . diff --stat frontend/tests/baseline-manifest.json     # expect: no output
```

---

## File Structure

| File | Kind | Responsibility | Task |
|---|---|---|---|
| `migrations/030_listing_owner_and_status.sql` | migration (new) | `seller_id`, `facility_type`, widened `status`/`type` CHECKs, six relaxed NOT NULLs, the submittable + publishable CHECKs, the owner index | SL1 |
| `migrations/031_listing_asset.sql` | migration (new) | `listing_asset` (photos and documents), its two indexes | SL1 |
| `tests/test_listing_schema.py` | test (modify) | the contract for both migrations | SL1 |
| `app/storage.py` | module (new **or** rebase) | `ObjectStore` — Census Task A2's class at its A-SL1 path, plus `delete()` | SL2 |
| `tests/test_storage.py` | test (new) | moto: put/get/exists/delete, `from_settings → None` | SL2 |
| `app/media/__init__.py`, `app/media/encode.py` | module (new) | `prepare_photos.py`'s normalisation rules, shared: EXIF-transpose, alpha flatten, ≤ 1600 px, quality ladder, ≤ 250 KB, **every** metadatum stripped | SL2 |
| `tests/media/test_encode.py` | test (new) | the ladder, the ceilings, the strip (against fixtures that really carry EXIF/GPS/ICC) | SL2 |
| `scripts/prepare_photos.py` | script (modify) | imports `app.media.encode` instead of its own copy; behaviour byte-identical | SL2 |
| `app/api/seller_listings.py` | router (new) | `/api/seller/listings…` — create, list, get, per-step PATCH, assets, submit, status | SL3, SL4, SL5 |
| `app/api/admin_listings.py` | router (new) | `/api/admin/listings` and `/decide` | SL5 |
| `app/main.py` | modify | both routers inside the `site_mode == "app"` block | SL3, SL5 |
| `app/auth/permissions.py` | modify | `listing.publish` joins `AUDITED` — one name, nothing else | SL5 |
| `app/auth/limits.py` | modify | `LISTING_PATCH`, `LISTING_UPLOAD`, `LISTING_SUBMIT` | SL3 |
| `app/api/listings.py` | modify | `serialise` blanks `rev` (D22); the photo route's seller arm (D15 ¶3); the cache-drop helper the writers call | SL3, SL4 |
| `app/mail/templates.py` (+ the three bodies) | modify | `listing_submitted`, `listing_published`, `listing_declined` | SL5 |
| `tests/api/test_seller_listings.py` | test (new) | the wizard's whole surface, owner scoping, status guards, D3, the audit-namespace assertion | SL3, SL5 |
| `tests/api/test_listing_assets.py` | test (new) | moto: upload, re-encode, strip, cap, reorder, delete, sniffing, the document lock | SL4 |
| `tests/api/test_admin_listings.py` | test (new) | the queue, the three decide branches, `reason`/`state`/`market`, one audit row per decision | SL5 |
| `scripts/seed_listings.py` | script (modify) | `SEED_OWNER_EMAIL`, `--owner`, `--no-owner`, ownership in the UPSERT both ways, the `--production` rule | SL6 |
| `tests/scripts/test_seed_listings.py` | test (modify) | ownership assigned / re-asserted / NULL / never defaulted on production / a seller row untouched | SL6 |
| `frontend/src/listings/seller.ts` (+ `.test.ts`) | module (new) | the adapter: `list/create/get/patch/upload/remove/reorder/submit/setStatus` | SL7 |
| `frontend/tests/design-amendments.ts` | modify | the new family (id derived — A-SL4) | SL7, SL8 |
| `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html` | regenerate | `npm run gen:design` writes it from pristine + amendments | SL7, SL8 |
| `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md` | modify | one row per amendment | SL7, SL8 |
| `frontend/src/logic.js`, `src/App.vue`, `src/generated/pseudo.css` | **regenerate only** | `npm run gen:app` | SL7, SL8 |
| `frontend/src/app.setup.js` | modify | the `listings` prop, exactly as `auth` is passed | SL7 |
| `frontend/tests/harness.ts` (+ `harness.test.ts`) | modify | the two empty-collection stubs (A-SL2) | SL7, SL8 |
| `frontend/src/admin/listings.ts` (+ `.test.ts`) | module (new) | the M6 mapping for Admin › Listings | SL8 |
| `frontend/tests/listing-flows.spec.ts` | spec (new) | value assertions against the real API — Edit on a seeded hospital, upload, submit, approve, Browse | SL8 |
| `.env.example`, `DEPLOY.md`, `CLAUDE.md` | modify | the four `S3_*` rows, the seeding order, the launch-removal paragraph | SL9 |
| `scripts/verify-deploy.sh` (+ `tests/scripts/test_verify_deploy.sh`) | modify | one probe per new surface | SL9 |
| `pyproject.toml`, `frontend/package.json` | modify | boto3 / moto / boto3-stubs; the lockstep version bump at hand-back | SL2, SL9 |

---

### Task SL1: `listing` grows an owner, a lifecycle and an asset table — **1 day**

**Files:**
- Create: `migrations/030_listing_owner_and_status.sql`
- Create: `migrations/031_listing_asset.sql`
- Modify: `tests/test_listing_schema.py`
- Unchanged: `scripts/migrate.py` (both files are single transactional DDL; no `CREATE INDEX CONCURRENTLY`, no `BEGIN`/`COMMIT` — the runner wraps each file and its ledger row in one transaction)

**Interfaces:**
- Consumes: `migrations/016_listing.sql` (the table), `migrations/010_accounts.sql` (`account(id)`), `tests/conftest.py`'s `conn` fixture.
- Produces, on `listing`: `seller_id uuid REFERENCES account(id) ON DELETE SET NULL`, `facility_type text`, `rev_disclosed boolean NOT NULL DEFAULT false`, `documents_disclosed boolean NOT NULL DEFAULT false`; `status` widened with `declined`; `type` widened with `Other`; `NOT NULL` dropped from `name`, `city`, `state`, `area`, `type`, `market`; constraints `listing_submittable_ck` and `listing_publishable_ck`; index `listing_owner_idx (seller_id, updated_at DESC)`.
- Produces, new: table `listing_asset (id uuid, listing_id uuid, kind text, name text, content_type text, byte_size bigint, sha256 text, storage_key text, created_at timestamptz)` with `listing_asset_listing_idx` and `listing_asset_kind_idx`. Tasks SL3–SL6 write and read exactly these names.

> **Why `rev_disclosed` and `documents_disclosed` are added here and the spec's D20 table does not say so.** D20 names "the four disclosure columns" and D11 says a new draft is created with "all four disclosure flags **false** (the table's defaults)"; `016_listing.sql` has only two of the four (`location_disclosed`, `name_disclosed`). The other two are added by this migration, and **existing seed rows are backfilled to `true` in the same file** — D22: "Every seed sets all four flags true … so nothing John sees on QA changes." Without the backfill, the moment `030` applies to QA the eighteen hospitals' revenue figures would blank on the buyer detail, which is a regression this plan would have caused between two of its own tasks.

> **Why `ON DELETE SET NULL` and not `RESTRICT`.** D5 says the column is nullable "because a production seed row belongs to the VIN Foundation, not to a person". A listing outlives the account that made it — `withdrawn` rows "keep their history for reporting" (`logic.js:1061`) — and the audit trail of who did what is in `audit_log`, which carries no foreign key of its own. `RESTRICT` would make deleting an account impossible while any listing it ever owned survives, which is not the behaviour the lifecycle table describes.

> **Why two CHECKs instead of application-level validation.** D12: "the database, not a code path, is what guarantees `serialise` never meets a null it cannot render." `serialise` interpolates `row["area"]` into `anonymised_name` and `toPractice` calls `p.sqft.toLocaleString()`; a published row with a null `area` or `market` is a blank app, not a blank field (that is exactly what A12.6/A12.7 had to repair for the community figures). The CHECKs are cheap and they are the only thing that survives a future writer this plan does not know about.

- [ ] **Step 1: Write the failing schema-contract additions**

Append to `tests/test_listing_schema.py` — and **edit `EXPECTED_COLUMNS` in place**, adding the four new entries and flipping the six relaxed columns to nullable:

```python
# --- Seller listing lifecycle (spec 2026-09-08, D2/D5/D10/D12/D20; migrations 020 + 021) ---
#
# EXPECTED_COLUMNS above gains four rows and flips six. The six were NOT NULL because every
# seeded hospital has them; the approved wizard's step 2 collects a city and a ZIP and nothing
# else (logic.js:1175), so a draft cannot have a state, a market or an area, and `state`/`market`
# arrive from the reviewer at the first publish (D12). The two CHECK constraints below are what
# replaces the NOT NULLs — a draft may be empty, a submitted listing may not, a published listing
# has everything `serialise` interpolates.

EXPECTED_ASSET_COLUMNS: dict[str, tuple[str, bool]] = {
    "id": ("uuid", False),
    "listing_id": ("uuid", False),
    "kind": ("text", False),
    "name": ("text", False),
    "content_type": ("text", False),
    "byte_size": ("bigint", False),
    "sha256": ("text", False),
    "storage_key": ("text", False),
    "created_at": ("timestamp with time zone", False),
}


def test_listing_asset_has_exactly_the_contracted_columns(conn: Any) -> None:
    found = {
        name: (dtype, nullable == "YES")
        for name, dtype, nullable in _rows(
            conn,
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'listing_asset'",
        )
    }
    assert found == EXPECTED_ASSET_COLUMNS


def test_declined_and_other_are_now_legal_and_the_old_refusals_still_are_not(conn: Any) -> None:
    """D2 adds `declined` to the status CHECK; D10 adds `Other` to the type CHECK — the approved
    step-1 select offers it (logic.js:1174) and a column that cannot hold an answer the design
    collects is the bug, not the answer."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, status, est, price, zip)"
            " VALUES ('sl-declined','A','X','TX','X','Other','X, TX','seller','declined',1998,100,'78613')"
        )
    for status, ptype in (("live", "Other"), ("declined", "Aquatic")):
        with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                "INSERT INTO listing (slug, name, city, state, area, type, market, source, status, est, price, zip)"
                " VALUES (%s,'A','X','TX','X',%s,'X, TX','seller',%s,1998,100,'78613')",
                (f"sl-bad-{status}-{ptype}", ptype, status),
            )


def test_a_draft_may_be_almost_empty(conn: Any) -> None:
    """The wizard creates the row before step 1 is filled in (D9's POST), so a draft carries a slug,
    a source and nothing else. `listing-<id>` is D13's placeholder slug."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, source, status) VALUES ('listing-draft','seller','draft')"
            " RETURNING name, city, state, area, type, market, seller_id, rev_disclosed, documents_disclosed"
        )
        assert cur.fetchone() == (None, None, None, None, None, None, None, False, False)


def test_a_withdrawn_listing_may_also_be_empty_and_nothing_else_may(conn: Any) -> None:
    """`listing_submittable_ck`, both ways. `withdrawn` is terminal and reachable from `draft`, so
    an abandoned empty draft must still be withdrawable (logic.js:1061)."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing (slug, source, status) VALUES ('listing-gone','seller','withdrawn')")
    for status in ("in_review", "published", "paused", "declined"):
        with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("INSERT INTO listing (slug, source, status) VALUES (%s,'seller',%s)", (f"sl-empty-{status}", status))


def test_a_published_listing_must_carry_what_serialise_interpolates(conn: Any) -> None:
    """`listing_publishable_ck` (D12). `serialise` builds the anonymised name from `area` and the
    Browse market filter pages on `market`; `stateOf(market)` names the state on the detail."""
    submittable = ("A", "Cedar Park", "78613", "Small animal", 1998, 1_450_000)
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "INSERT INTO listing (slug, source, status, name, city, zip, type, est, price)"
            " VALUES ('sl-nopublish','seller','published',%s,%s,%s,%s,%s,%s)", submittable
        )
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, source, status, name, city, zip, type, est, price, state, market, area)"
            " VALUES ('sl-publish','seller','published',%s,%s,%s,%s,%s,%s,'TX','Austin, TX','Cedar Park')", submittable
        )


def test_seller_id_references_account_and_survives_its_deletion(conn: Any) -> None:
    """D5: nullable, because a production seed row belongs to the VIN Foundation and not to a
    person; `ON DELETE SET NULL` because a withdrawn listing keeps its history after the account
    that made it is gone."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('sl-owner@example.org','x','active') RETURNING id")
        owner = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO listing (slug, source, status, seller_id) VALUES ('sl-owned','seller','draft',%s)", (owner,)
        )
        cur.execute("DELETE FROM account WHERE id = %s", (owner,))
        cur.execute("SELECT seller_id FROM listing WHERE slug = 'sl-owned'")
        assert cur.fetchone() == (None,)


def test_the_owner_and_asset_indexes_exist(conn: Any) -> None:
    """`(seller_id, updated_at DESC)` is the dashboard's key (D5); the asset indexes are the
    wizard's step-6 read and the document lock's lookup."""
    listing_defs = [d for (d,) in _rows(conn, "SELECT indexdef FROM pg_indexes WHERE tablename = 'listing'")]
    assert any("listing_owner_idx" in d for d in listing_defs), listing_defs
    asset_defs = [d for (d,) in _rows(conn, "SELECT indexdef FROM pg_indexes WHERE tablename = 'listing_asset'")]
    assert any("listing_asset_listing_idx" in d for d in asset_defs), asset_defs
    assert any("listing_asset_kind_idx" in d for d in asset_defs), asset_defs


def test_an_asset_dies_with_its_listing_and_its_kind_is_checked(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing (slug, source, status) VALUES ('sl-assets','seller','draft') RETURNING id")
        listing_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO listing_asset (listing_id, kind, name, content_type, byte_size, sha256, storage_key)"
            " VALUES (%s,'photo','1.webp','image/webp',1024,'abc','listings/x/photos/y.webp')", (listing_id,)
        )
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "INSERT INTO listing_asset (listing_id, kind, name, content_type, byte_size, sha256, storage_key)"
            " VALUES (%s,'video','1.mp4','video/mp4',1024,'abc','listings/x/videos/y.mp4')", (listing_id,)
        )
    with conn.cursor() as cur:
        cur.execute("DELETE FROM listing WHERE id = %s", (listing_id,))
        cur.execute("SELECT count(*) FROM listing_asset WHERE listing_id = %s", (listing_id,))
        assert cur.fetchone() == (0,)


def test_a_storage_key_is_claimed_once(conn: Any) -> None:
    """One object, one row. A duplicate key would make `delete()` orphan a live asset."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing (slug, source, status) VALUES ('sl-keys','seller','draft') RETURNING id")
        listing_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO listing_asset (listing_id, kind, name, content_type, byte_size, sha256, storage_key)"
            " VALUES (%s,'photo','1.webp','image/webp',1,'a','listings/dup.webp')", (listing_id,)
        )
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO listing_asset (listing_id, kind, name, content_type, byte_size, sha256, storage_key)"
                " VALUES (%s,'photo','2.webp','image/webp',1,'b','listings/dup.webp')", (listing_id,)
            )


def test_the_seeded_disclosure_backfill_is_in_the_migration_not_in_the_seeder(conn: Any) -> None:
    """D22: "every seed sets all four flags true … so nothing John sees on QA changes". A row that
    already existed when 020 applied is a seeded hospital, and its revenue must not blank between
    two tasks of this plan. New rows still default to false — sellers hide by default."""
    with conn.cursor() as cur:
        cur.execute("SELECT column_default FROM information_schema.columns"
                    " WHERE table_name='listing' AND column_name IN ('rev_disclosed','documents_disclosed')")
        assert sorted(cur.fetchall()) == [("false",), ("false",)]
    assert "WHERE source = 'seed'" in (MIGRATIONS / "030_listing_owner_and_status.sql").read_text()
```

Add at the top of the file, beside the existing imports:

```python
from pathlib import Path

import psycopg2
import pytest

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
poetry run pytest tests/test_listing_schema.py -v
```
Expected: FAIL. `test_listing_asset_has_exactly_the_contracted_columns` fails with `found == {}` (no such table); `test_a_draft_may_be_almost_empty` fails with `psycopg2.errors.NotNullViolation: null value in column "name"`; `test_listing_has_exactly_the_contracted_columns` fails on the four missing columns.

- [ ] **Step 3: Write `migrations/030_listing_owner_and_status.sql`**

```sql
-- Seller listing lifecycle (spec 2026-09-08; D2, D5, D10, D12, D20, D22).
--
-- The listing table was written for eighteen seeded hospitals, every one of them complete. It now
-- has to hold a SELLER'S OWN listing from the moment they click "Create a listing", which is a row
-- with a slug and nothing else, and to carry that row through draft -> in_review -> published with
-- paused, declined and terminal withdrawn beside it.
--
-- Migration numbers: the spec says "017". 017-019 were taken by the Census branch's Task A1 while
-- this spec was being written, and an applied migration is never renumbered — controller amendment
-- A-SL3.
--
-- Nothing here is destructive: three ADD COLUMNs, two CHECK swaps, six DROP NOT NULLs, two new
-- CHECKs, one index, and one backfill of the rows that already exist.

-- D5. Nullable: a production seed row belongs to the VIN Foundation, not to a person, and
-- `scripts/seed_listings.py --production` never assigns a demo persona (D25). ON DELETE SET NULL:
-- a withdrawn listing keeps its history for reporting after the account that made it is gone, and
-- who did what lives in audit_log, which carries no foreign key either.
ALTER TABLE listing ADD COLUMN seller_id uuid REFERENCES account(id) ON DELETE SET NULL;

-- D10 mapping 4. The approved step-5 select asks "Facility type" (Standalone / Strip or plaza /
-- Medical park / Other, logic.js:1178) and there was nowhere to put the answer. Nothing reads it
-- yet; dropping a seller's answer to an approved question on the floor is the opposite of "the UX
-- true".
ALTER TABLE listing ADD COLUMN facility_type text;

-- D20. The other two of the four disclosure flags. Sellers hide by default, exactly as
-- location_disclosed and name_disclosed do; the wizard's step-3 and step-7 switches are INVERTED
-- against these (`revBand` on means rev_disclosed false).
ALTER TABLE listing ADD COLUMN rev_disclosed      boolean NOT NULL DEFAULT false;
ALTER TABLE listing ADD COLUMN documents_disclosed boolean NOT NULL DEFAULT false;

-- D22, and the reason this is in the migration rather than in the seeder: every row that exists
-- when this file applies is one of the eighteen demo hospitals, which show everything (A-L5 already
-- set the other two flags true in seeds/hospitals.json). Without this line, applying 020 to QA
-- would blank eighteen revenue figures on the buyer detail until the next re-seed.
UPDATE listing SET rev_disclosed = true, documents_disclosed = true WHERE source = 'seed';

-- D2. `declined` is the sixth status: a reviewer's refusal that the seller may edit and re-submit.
ALTER TABLE listing DROP CONSTRAINT listing_status_check;
ALTER TABLE listing ADD  CONSTRAINT listing_status_check
  CHECK (status IN ('draft','in_review','published','paused','withdrawn','declined'));

-- D10 mapping 3. The approved step-1 select offers "Other" (logic.js:1174). An `Other` listing
-- matches only the Browse type filter's "Any", which is honest.
ALTER TABLE listing DROP CONSTRAINT listing_type_check;
ALTER TABLE listing ADD  CONSTRAINT listing_type_check
  CHECK (type IN ('Small animal','Mixed','Large animal','Emergency','Specialty','Other'));

-- D12. Six NOT NULLs a draft cannot satisfy. The approved step 2 collects a city and a ZIP and
-- nothing else, so `state`, `market` and `area` cannot come from the seller: `area` is derived from
-- the city on the step-2 PATCH and `state`/`market` are supplied by the reviewer at the first
-- publish (John's ruled default, spec §16 Q2).
ALTER TABLE listing ALTER COLUMN name   DROP NOT NULL;
ALTER TABLE listing ALTER COLUMN city   DROP NOT NULL;
ALTER TABLE listing ALTER COLUMN state  DROP NOT NULL;
ALTER TABLE listing ALTER COLUMN area   DROP NOT NULL;
ALTER TABLE listing ALTER COLUMN type   DROP NOT NULL;
ALTER TABLE listing ALTER COLUMN market DROP NOT NULL;

-- ...and what replaces them. The DATABASE guarantees serialise() never meets a null it cannot
-- render, rather than one code path promising it.
--
-- Submittable: everything the approved wizard's own client-side validation demands before step 8
-- (logic.js:1215-1217 — name and est; city and zip; price and either rev or the range option),
-- plus the type its step-1 select always has a value for. A draft may be empty; so may a withdrawn
-- listing, because withdrawing an abandoned draft is a legal move and terminal.
ALTER TABLE listing ADD CONSTRAINT listing_submittable_ck
  CHECK (status IN ('draft','withdrawn')
         OR (name IS NOT NULL AND city IS NOT NULL AND zip IS NOT NULL
             AND type IS NOT NULL AND est IS NOT NULL AND price IS NOT NULL));

-- Publishable: the three the buyer surface dereferences. `area` builds the anonymised name
-- (app/api/listings.py's anonymised_name), `market` is what the Browse filter pages on and what
-- `stateOf(market)` splits for the detail's state label (A12.8/A12.9), and `state` is the row's own.
ALTER TABLE listing ADD CONSTRAINT listing_publishable_ck
  CHECK (status <> 'published'
         OR (state IS NOT NULL AND market IS NOT NULL AND area IS NOT NULL));

-- D5. The seller dashboard's only query: this owner's listings, most recently touched first.
CREATE INDEX listing_owner_idx ON listing (seller_id, updated_at DESC);
```

- [ ] **Step 4: Write `migrations/031_listing_asset.sql`**

```sql
-- Seller listing lifecycle (spec 2026-09-08; D14, D15, D18, D19). A seller's uploaded photographs
-- and documents.
--
-- The BYTES live in object storage under `listings/{listing_id}/…` (D14); this table is the row
-- that says which object, whose, what kind and how big — so every read is a live permission
-- decision against the listing's status and the caller's principal rather than a signed URL that
-- outlives the decision that minted it (D15).
--
-- There is deliberately NO `position` column. `listing.photos` stays the ordered array of strings
-- it already is, and it remains the single home of photo ORDER (D15 reason 3): for a source='seed'
-- row an entry is a relative path under PHOTOS_ROOT, for a seller row it is an asset id. Two homes
-- for one fact is how orders drift.
CREATE TABLE listing_asset (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_id   uuid        NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  -- 'photo' plus D18's four document kinds. The approved step 6 has no kind picker, so the wizard
  -- sends 'other'; the API takes `kind` today so that Rev 3's picker needs no API change.
  kind         text        NOT NULL
                           CHECK (kind IN ('photo','floor_plan','financials','equipment','other')),
  -- What the wizard's step-6 tile shows under the badge: the uploaded filename for a seller upload
  -- (D26). Never a path — the path is `storage_key`.
  name         text        NOT NULL,
  content_type text        NOT NULL,
  byte_size    bigint      NOT NULL,
  -- Of the STORED bytes: a photograph's re-encoded WebP, a document's own bytes.
  sha256       text        NOT NULL,
  -- `listings/{listing_id}/photos/{id}.webp` or `listings/{listing_id}/documents/{id}{ext}`.
  -- UNIQUE because put_immutable never overwrites: one object, one row, and a delete that could
  -- orphan a live asset is impossible.
  storage_key  text        NOT NULL UNIQUE,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- The wizard's step-6 read and the asset list on every draft GET.
CREATE INDEX listing_asset_listing_idx ON listing_asset (listing_id, created_at);
-- The document lock's lookup: this listing's documents, or this listing's photographs.
CREATE INDEX listing_asset_kind_idx    ON listing_asset (listing_id, kind);
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
poetry run pytest tests/test_listing_schema.py -v
git diff --stat scripts/migrate.py     # expect: no output — the runner is untouched
poetry run pytest tests/test_migrate.py -q
```
Expected: PASS. `tests/test_migrate.py` green and the runner's diff empty — `030` and `031` apply through the existing ledger with no new runner behaviour.

- [ ] **Step 6: Run the full backend gate**

```bash
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
```
Expected: 0 findings, 0 errors, 100 %.

- [ ] **Step 7: Commit**

```bash
git add migrations/030_listing_owner_and_status.sql migrations/031_listing_asset.sql tests/test_listing_schema.py
git commit -m "feat(db): listing gains an owner, a lifecycle and an asset table

Spec 2026-09-08 D2/D5/D10/D12/D20/D22. seller_id (nullable, ON DELETE SET NULL),
facility_type, and the two missing disclosure flags with a backfill so the eighteen
seeded hospitals keep showing their revenue. status gains 'declined', type gains
'Other', and the six NOT NULLs a draft cannot satisfy are replaced by a submittable
and a publishable CHECK so the database — not a code path — is what guarantees
serialise() never meets a null it cannot render. listing_asset holds the row behind
every uploaded object; listing.photos stays the single home of photo order.

Migrations 020/021, not the spec's 017: the Census branch took 017-019 (A-SL3).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

**Controller amendment A-SL9 (2026-09-09; ruling on SL1's NEEDS_CONTEXT).** `listing_submittable_ck` (D12) rejected the seed-listings test helper `_plant()`, which had been inserting a `published` row without `zip`/`est`/`price` since the Seed Listings sub-project. The check stands; the helper plants a complete row (test-only change, in SL1's scope because SL1's migration is what invalidates it); `scripts/seed_listings.py` stays SL6's. The brief's three stray `020`/`021` comment references are `030`/`031` (A-SL5).

---

**Controller amendment A-SL10 (2026-09-09; Task SL2 under the Census branch's A2 and A-C2).** The Census branch has already built the shared storage layer (commit 9c9c819: `app/storage.py` with `put/get/delete/exists/list` and `from_settings`, `tests/test_storage.py`, the four optional `S3_*` settings with their `.env.example`/DEPLOY.md rows, `boto3` main + `moto[s3]`/`boto3-stubs[s3]` dev, `poetry.lock`). Rather than a twin, the controller cherry-picks 9c9c819 onto `feat/seller-lifecycle` at the SL2 boundary (identical content merges cleanly when both branches land; conflicts, if any, in the docs rows are resolved keeping both sides). SL2 therefore: does NOT recreate `app/storage.py`, `tests/test_storage.py`, the settings, or the boto3/moto deps; builds `app/media/encode.py` (+ tests) and points `scripts/prepare_photos.py` at it; moves `pillow` to the main group (A-SL6); and calls the archive through `exists(key)` then `put(key, data, content_type)` — there is no `put_immutable`. The brief's mentions of `app/census/storage.py` and `put_immutable` are superseded by this paragraph.

---

### Task SL2: `app/storage.py` and `app/media/encode.py` — **1.5 days**

**Files:**
- Create **or rebase onto**: `app/storage.py` (see Step 0)
- Create: `tests/test_storage.py`
- Create: `app/media/__init__.py`, `app/media/encode.py`
- Create: `tests/media/__init__.py`, `tests/media/test_encode.py`
- Modify: `scripts/prepare_photos.py` (imports the shared module; behaviour unchanged)
- Modify: `app/config.py` (the four `S3_*` settings — **only if the Census branch has not already added them**)
- Modify: `pyproject.toml` (`boto3` main, `moto[s3]` + `boto3-stubs[s3]` dev, and **`pillow` moves from dev to main** — see the ruling below)
- Modify: `.env.example`, `DEPLOY.md` (the four rows — Global Constraint (i); **only if** SL2 is what adds the settings)

**Interfaces:**
- Produces `app.storage.ObjectStore` — **Census Task A2's signatures, verbatim** (A-SL1): `ObjectStore(endpoint_url, bucket, access_key, secret_key, region="auto")` positionally, `put_immutable(key: str, data: bytes, content_type: str) -> bool` (**`False`** when the key is taken — it never overwrites and never raises), `get(key) -> bytes | None`, `exists(key) -> bool`, `from_settings(settings) -> ObjectStore | None`; **plus this sub-project's one addition**, `delete(key) -> bool`.
- Produces `app.media.encode` with `MAX_PHOTOS`, `MAX_EDGE_PX`, `MAX_BYTES`, `QUALITY_LADDER`, `FALLBACK_EDGE_PX`, `IMAGE_SUFFIXES`, and `encode_webp(data: bytes) -> tuple[bytes, str] | None` returning the WebP bytes and their SHA-256, or `None` when nothing in the ladder fits.
- Consumed by: SL4 (every upload), the Census plan's Phase A archive (`put_immutable` only).

> **RULING — Pillow moves to the main dependency group, and `pyproject.toml`'s comment saying it must not is corrected in the same commit.** The comment reads: *"The seed photograph pipeline only (scripts/prepare_photos.py, run once by hand). The API serves already-encoded WebP bytes off disk and never opens an image, so this must NOT move to the main group — the runtime image is built with `poetry install --only main`."* Both of its premises stop being true here. D15's "**Normalisation is part of the upload, not a nicety**" puts the encoder on the request path: the API opens a seller's uploaded image, EXIF-transposes it, strips every metadatum and re-encodes it to WebP before a byte reaches storage. Stripping GPS EXIF from a phone photograph is what keeps the promise the sign-in card makes in John's own words (A10.2, "Sellers control what buyers can see"), so it cannot be deferred to a hand-run script. The comment is replaced with the reason it moved and a pointer to this task. **This is a recorded deviation from an existing in-tree decision, not an implementer's judgement** — it is listed in Pre-flight and must be read back to the controller in the hand-back with the image-size delta from `docker images`.

- [ ] **Step 0: Decide the arm — greenfield or rebase (A-SL1)**

```bash
ls app/storage.py 2>/dev/null && echo REBASE || echo GREENFIELD
git log --oneline -1 -- app/storage.py 2>/dev/null
```

- **GREENFIELD** (no `app/storage.py`): write Steps 1–4 as below. The class is Census Task A2's verbatim, at the A-SL1 path, plus `delete()`.
- **REBASE** (the Census branch landed first): **do not rewrite the file.** Read it, confirm the constructor is `ObjectStore(endpoint_url, bucket, access_key, secret_key, region='auto')` and that `put_immutable` / `get` / `exists` / `from_settings` are present with A2's semantics, then add **only** `delete()` and **only** its two tests (Step 2's `test_delete_removes_an_object…` pair). Add nothing to `app/config.py`, `.env.example`, `DEPLOY.md` or `pyproject.toml`'s boto3 lines — A2 owns them. Skip to Step 5.
  If the file exists at `app/census/storage.py` instead, that branch has not applied A-SL1: **STOP and report** — moving another branch's module is the controller's call, not this task's.

- [ ] **Step 1: Write the failing storage tests**

Create `tests/test_storage.py`:

```python
"""`app.storage.ObjectStore` (spec 2026-09-08 D14; Census Task A2 + controller amendment A-SL1).

The bucket is `practice-match-data`, one per environment, under a `listings/` prefix here and a
`census/` prefix in the Census plan's Phase A — which is why the module is `app/storage.py` and not
either sub-project's own package (A-SL1). Every test runs against moto: no network, no credentials,
no bucket to provision before the suite runs.
"""
from __future__ import annotations

from typing import Any

import boto3
import pytest
from moto import mock_aws

from app.storage import ObjectStore

BUCKET = "practice-match-data"


@pytest.fixture
def store() -> Any:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        # Positional, exactly as Census Task A2 declares the constructor (A-SL1: "taken verbatim").
        yield ObjectStore(None, BUCKET, "k", "s", "us-east-1")


def test_put_immutable_writes_once_and_never_overwrites(store: ObjectStore) -> None:
    """Census A2's own test, verbatim in behaviour: `True` on the write, `False` on the second
    attempt, and the first bytes survive. A "replace" in the UI is a new asset id and therefore a
    new key, which is what lets `listing_asset.storage_key` be UNIQUE and `delete` be safe."""
    assert store.put_immutable("listings/a/photos/b.webp", b"one", "image/webp") is True
    assert store.put_immutable("listings/a/photos/b.webp", b"two", "image/webp") is False
    assert store.get("listings/a/photos/b.webp") == b"one"
    assert store.exists("listings/a/photos/b.webp") is True


def test_get_and_exists_answer_for_an_absent_key(store: ObjectStore) -> None:
    assert store.get("listings/nope.webp") is None
    assert store.exists("listings/nope.webp") is False


def test_delete_removes_an_object_and_reports_it(store: ObjectStore) -> None:
    """The one method this sub-project adds (A-SL1). An asset object is written once and only ever
    deleted, so `put_immutable`'s never-overwrite guarantee survives."""
    assert store.put_immutable("listings/a/documents/c.pdf", b"%PDF-1.7", "application/pdf") is True
    assert store.delete("listings/a/documents/c.pdf") is True
    assert store.exists("listings/a/documents/c.pdf") is False


def test_delete_of_an_absent_key_is_false_and_not_an_error(store: ObjectStore) -> None:
    """A DELETE route that has already removed the row must not 500 because a retry found no
    object. The row is the record; the object is the payload."""
    assert store.delete("listings/a/documents/gone.pdf") is False


def test_from_settings_is_none_when_unconfigured_and_says_so(caplog: Any) -> None:
    """Census A2, verbatim: `None` with a logged warning, never a crash. An environment with no
    bucket must still boot, serve every read and refuse an upload with a clear message (SL4)."""
    from app.config import Settings

    unset = Settings(database_url="postgresql://x", redis_url="redis://x", environment="test", api_secret_key="x")
    with caplog.at_level("WARNING"):
        assert ObjectStore.from_settings(unset) is None
    assert "not configured" in caplog.text


def test_from_settings_builds_a_store_when_configured() -> None:
    from app.config import Settings

    configured = Settings(database_url="postgresql://x", redis_url="redis://x", environment="test",
                          api_secret_key="x", s3_endpoint_url="https://s3.example.test", s3_bucket=BUCKET,
                          s3_access_key_id="k", s3_secret_access_key="s")
    built = ObjectStore.from_settings(configured)
    assert built is not None and built.bucket == BUCKET


def test_a_client_error_that_is_not_a_missing_key_is_re_raised(store: ObjectStore) -> None:
    """A2's arms, kept: only 404/NoSuchKey/NotFound answer `None`/`False`. A permissions failure or
    a wrong endpoint must surface as the 500 it is, not as "there is no such photograph"."""
    from botocore.exceptions import ClientError

    def boom(**_: Any) -> None:
        raise ClientError({"Error": {"Code": "AccessDenied"}}, "HeadObject")

    store._s3.head_object = boom   # noqa: SLF001 — the arm under test is inside the class
    with pytest.raises(ClientError):
        store.exists("listings/a/photos/b.webp")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
poetry run pytest tests/test_storage.py -v
```
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'moto'` before the dependency is added, then `ModuleNotFoundError: No module named 'app.storage'` after it.

- [ ] **Step 3: Add the dependencies**

```bash
poetry add 'boto3>=1.35'
poetry add --group dev 'moto[s3]>=5.0' 'boto3-stubs[s3]>=1.35'
```

> Census Task A2's `poetry add` line is `boto3 pyshp shapely`. **Take `boto3` only** — `pyshp` and
> `shapely` are that sub-project's TIGER shapefile reader and have no consumer here. `boto3-stubs[s3]`
> is not in A2's list and is added here because Global Constraint (d) forbids the `# type: ignore`
> that `mypy app --strict` would otherwise need on every boto3 call.

Then edit `pyproject.toml` by hand for the Pillow move — **delete** the dev-group entry and its three-line comment, and add to `[project].dependencies`:

```toml
  # The photograph pipeline, on the REQUEST PATH since the seller listing lifecycle (spec
  # 2026-09-08 D15): `app/media/encode.py` EXIF-transposes, flattens, resizes, strips every
  # metadatum and re-encodes a seller's upload to WebP before a byte reaches object storage.
  # Stripping a phone photograph's GPS is what keeps "Sellers control what buyers can see" true
  # for a listing whose location is undisclosed, so it cannot wait for a hand-run script — which
  # is why this is a MAIN dependency now and no longer dev-only (`scripts/prepare_photos.py`
  # imports the same module). Controller ruling, Task SL2.
  "pillow>=11.0",
```

- [ ] **Step 4: Write `app/storage.py`**

```python
"""Object storage — one small abstraction over the approved `practice-match-data` bucket.

Census Task A2's class, at the path controller amendment **A-SL1** moved it to: two sub-projects
now depend on it (the Census raw-payload archive under `census/`, a seller's photographs and
documents under `listings/`) and a shared abstraction should not carry one of their names. Every
signature below is A2's, unchanged — `put_immutable` returns a BOOL and never raises on a taken
key. The one addition is `delete`, which the Census archive never calls.

**Immutable by construction.** An asset object is written once and only ever deleted — a "replace"
in the UI is a new asset id and therefore a new key — so `listing_asset.storage_key` can be UNIQUE
and `delete` can never orphan a live row.

**Unconfigured is not a crash.** `from_settings` returns `None` with a logged warning when the
bucket or its credentials are unset, so an environment with no bucket boots, serves every read and
refuses only the uploads (`app/api/seller_listings.py` turns that `None` into a clear 503).

Nothing here is public: the bucket is private, no object ACL is set, and every read is proxied by
an API route that makes the permission decision per request (D15). There are no signed URLs in
this codebase and adding one is a design decision, not an optimisation.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from app.config import Settings

log = logging.getLogger(__name__)

# The three codes an S3-compatible store uses for "no such key". Anything else — AccessDenied, a
# wrong endpoint, a throttle — is re-raised: answering `None` to those would report a permissions
# failure to a buyer as "there is no such photograph".
_MISSING = ("404", "NoSuchKey", "NotFound")


class ObjectStore:
    def __init__(self, endpoint_url: str | None, bucket: str, access_key: str, secret_key: str, region: str = "auto") -> None:
        self.bucket = bucket
        self._s3: Any = boto3.client(
            "s3", endpoint_url=endpoint_url, region_name=region,
            aws_access_key_id=access_key, aws_secret_access_key=secret_key,
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> ObjectStore | None:
        """The store this environment is configured for, or `None`.

        `None` is a legitimate state: QA and production have the bucket, a developer's machine and
        a fresh test database do not, and neither should fail to boot over it."""
        if not (settings.s3_bucket and settings.s3_access_key_id and settings.s3_secret_access_key):
            log.warning("[storage] object storage is not configured (S3_BUCKET / S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY) — uploads and the raw archive are disabled")
            return None
        return cls(settings.s3_endpoint_url, settings.s3_bucket, settings.s3_access_key_id, settings.s3_secret_access_key)

    def exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _MISSING:
                return False
            raise

    def put_immutable(self, key: str, data: bytes, content_type: str) -> bool:
        """Writes `data` at `key`; `False` — never an exception — when the key is already taken."""
        if self.exists(key):
            return False
        self._s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return True

    def get(self, key: str) -> bytes | None:
        try:
            content: bytes = self._s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _MISSING:
                return None
            raise
        return content

    def delete(self, key: str) -> bool:
        """Removes the object; `False` when there was nothing there. The row is the record and the
        object is the payload, so a retried DELETE that finds no object is a success, not a 500.
        (The one method this sub-project adds to Task A2's class — A-SL1.)"""
        if not self.exists(key):
            return False
        self._s3.delete_object(Bucket=self.bucket, Key=key)
        return True
```

Add to `app/config.py`'s `Settings`, immediately after `mail_reply_to` (**GREENFIELD arm only**). Four fields, not A2's six: `census_api_key` and `census_contact_email` belong to the Census plan and are added by it — this task must not take names it has no consumer for.

```python
    # Object storage (spec 2026-09-08 D14; Census plan Task A2, ruling A-C1 ¶7). The bucket is
    # `practice-match-data`, created per Railway environment; a seller's photographs and documents
    # live under `listings/` and the Census archive under `census/`. All four are optional so that
    # a service without them still boots — `ObjectStore.from_settings` returns None with a warning
    # and the upload routes refuse with a clear message, rather than the whole api failing to start
    # over a capability most requests never touch.
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
```

- [ ] **Step 5: Run the storage tests to verify they pass**

```bash
poetry run pytest tests/test_storage.py -v
poetry run mypy app --strict     # boto3-stubs[s3] is why this is 0 errors and not 12
```
Expected: PASS, 7 tests (GREENFIELD) or PASS with the two `delete` tests added (REBASE). mypy 0 errors.

- [ ] **Step 6: Write the failing encoder tests**

Create `tests/media/__init__.py` (empty) and `tests/media/test_encode.py`:

```python
"""`app.media.encode` — `scripts/prepare_photos.py`'s rules, shared (spec 2026-09-08 D15).

The rules do not change: EXIF-transpose, flatten alpha onto white, <= MAX_EDGE_PX on the long edge,
the quality ladder, the FALLBACK_EDGE_PX step, <= MAX_BYTES out, every metadatum stripped. What
changes is WHERE they live — the API needs them on the request path, and a second copy would drift.
`tests/scripts/test_prepare_photos.py` keeps proving the seed pipeline end to end against this
module; these tests prove the module itself, including the arms the seed corpus never reaches.
"""
from __future__ import annotations

import io

from PIL import Image

from app.media import encode


def _jpeg(width: int, height: int, *, exif: bool = False) -> bytes:
    image = Image.new("RGB", (width, height), (120, 30, 30))
    buffer = io.BytesIO()
    if exif:
        data = Image.Exif()
        data[0x0112] = 6                    # Orientation: rotate 90 CW
        data[0x8825] = {1: "N", 2: (30.0, 16.0, 0.0)}   # GPS IFD — the one that must never survive
        image.save(buffer, "JPEG", exif=data.tobytes())
    else:
        image.save(buffer, "JPEG")
    return buffer.getvalue()


def test_the_constants_are_the_seed_pipelines_own() -> None:
    """A drift here silently changes what a seller's photograph becomes AND what the committed seed
    photographs would be re-encoded to."""
    assert (encode.MAX_PHOTOS, encode.MAX_EDGE_PX, encode.MAX_BYTES) == (4, 1600, 250_000)
    assert encode.QUALITY_LADDER == (82, 72, 62, 52, 44, 20)
    assert encode.FALLBACK_EDGE_PX == 1100
    assert encode.IMAGE_SUFFIXES == (".jpg", ".jpeg", ".png", ".webp")


def test_a_photograph_comes_back_as_webp_within_both_ceilings() -> None:
    out = encode.encode_webp(_jpeg(3000, 2000))
    assert out is not None
    data, digest = out
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    assert len(data) <= encode.MAX_BYTES
    assert max(Image.open(io.BytesIO(data)).size) <= encode.MAX_EDGE_PX
    assert len(digest) == 64 and digest == encode.sha256_hex(data)


def test_every_metadatum_is_stripped_and_the_fixture_really_carried_some() -> None:
    """The load-bearing half of D15: a seller's phone photograph carries GPS EXIF, and a listing
    with `location_disclosed = false` whose photograph leaks its coordinates breaks the promise the
    sign-in card makes (A10.2). The second assertion is what stops this passing vacuously."""
    source = _jpeg(800, 600, exif=True)
    assert Image.open(io.BytesIO(source)).getexif(), "the fixture must really carry EXIF"
    out = encode.encode_webp(source)
    assert out is not None
    result = Image.open(io.BytesIO(out[0]))
    assert not result.getexif()
    assert result.info.get("icc_profile") is None
    assert result.info.get("exif") is None


def test_exif_orientation_is_applied_rather_than_recorded() -> None:
    """Orientation 6 means "rotate 90°". Stripping the tag without applying it would turn every
    portrait phone photograph on its side."""
    out = encode.encode_webp(_jpeg(800, 400, exif=True))
    assert out is not None
    assert Image.open(io.BytesIO(out[0])).size == (400, 800)


def test_transparency_is_flattened_onto_white() -> None:
    """WebP can carry alpha; the design's tiles and the buyer gallery are drawn on white, and a
    transparent PNG uploaded as a photograph would render as a hole."""
    image = Image.new("RGBA", (40, 40), (255, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    out = encode.encode_webp(buffer.getvalue())
    assert out is not None
    assert Image.open(io.BytesIO(out[0])).convert("RGBA").getpixel((0, 0)) == (255, 255, 255, 255)


def test_the_ladder_gives_up_rather_than_writing_an_oversized_file(monkeypatch: object) -> None:
    """The arm no real photograph reaches, and the one 100 % branch coverage needs a named test
    for: with the ceiling at a byte, every quality and the fallback edge still overshoot and the
    encoder returns None. SL4 turns that into a 422, never a stored file that breaks the budget."""
    import pytest

    monkeypatch.setattr(encode, "MAX_BYTES", 1)   # type: ignore[attr-defined]
    assert encode.encode_webp(_jpeg(1200, 900)) is None
    del pytest


def test_bytes_that_are_not_an_image_are_refused_rather_than_raised() -> None:
    """SL4's sniffing runs first, but the encoder is the last line: a `.jpg` that is a zip file
    must be a refusal the route can render, not a `PIL.UnidentifiedImageError` 500."""
    assert encode.encode_webp(b"PK\x03\x04not an image at all") is None
```

- [ ] **Step 7: Run the encoder tests to verify they fail**

```bash
poetry run pytest tests/media/test_encode.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.media'`.

- [ ] **Step 8: Write `app/media/encode.py`, and make `scripts/prepare_photos.py` import it**

Create `app/media/__init__.py` (empty) and `app/media/encode.py`:

```python
"""Photograph normalisation — `scripts/prepare_photos.py`'s rules, on the request path.

Spec 2026-09-08 D15: "Normalisation is part of the upload, not a nicety." Every rule here was
already the seed pipeline's; this module is where they now live so that the seeder and the API
apply exactly the same ones, and `tests/scripts/test_prepare_photos.py` keeps proving them end to
end against the committed corpus.

METADATA STRIPPING IS THE POINT, not tidiness. A seller's phone photograph carries GPS EXIF, and a
listing with `location_disclosed = false` whose photograph leaks its coordinates breaks the promise
John's own words make on the sign-in card (amendment A10.2, "Sellers control what buyers can see").
Pillow's `save` writes no EXIF, ICC profile or XMP unless asked, and this module never asks — but
orientation must be APPLIED before it is discarded (`ImageOps.exif_transpose`), or every portrait
photograph ships on its side.
"""
from __future__ import annotations

import hashlib
import io

from PIL import Image, ImageOps, UnidentifiedImageError

# The seed pipeline's own values (scripts/prepare_photos.py). Four per listing is John's ruling,
# restated for the API in D18; 1600 px and 250 KB are what keep the buyer gallery quick on a phone.
MAX_PHOTOS = 4
MAX_EDGE_PX = 1600
MAX_BYTES = 250_000
# Tried in order; the first that fits under MAX_BYTES wins.
QUALITY_LADDER = (82, 72, 62, 52, 44, 20)
# One more step for a photograph that will not fit at any quality at MAX_EDGE_PX: shrink, then walk
# the ladder again. A visibly smaller photograph beats a refused upload.
FALLBACK_EDGE_PX = 1100
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _flattened(image: Image.Image) -> Image.Image:
    """Orientation applied, alpha composited onto white, mode RGB. Not `convert("RGB")` alone:
    that drops the alpha channel by discarding it, so a transparent pixel becomes black."""
    upright = ImageOps.exif_transpose(image) or image
    if upright.mode in ("RGBA", "LA", "P"):
        rgba = upright.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.split()[-1])
        return canvas
    return upright.convert("RGB")


def _within(image: Image.Image, edge: int) -> Image.Image:
    if max(image.size) <= edge:
        return image
    scale = edge / max(image.size)
    return image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)


def encode_webp(data: bytes) -> tuple[bytes, str] | None:
    """`data` as WebP bytes and their SHA-256, or `None` when nothing in the ladder fits.

    `None` rather than an exception for BOTH failure modes — bytes that are not an image, and an
    image that will not fit — because the caller is an HTTP route and both are the caller's 422,
    not a 500."""
    try:
        opened = Image.open(io.BytesIO(data))
        flattened = _flattened(opened)
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    for edge in (MAX_EDGE_PX, FALLBACK_EDGE_PX):
        candidate = _within(flattened, edge)
        for quality in QUALITY_LADDER:
            buffer = io.BytesIO()
            candidate.save(buffer, "WEBP", quality=quality, method=6)
            out = buffer.getvalue()
            if len(out) <= MAX_BYTES:
                return out, sha256_hex(out)
    return None
```

In `scripts/prepare_photos.py`, delete its private copies of the five constants and its own encode
loop and import them instead — **the behaviour must not change**:

```python
from app.media.encode import (
    FALLBACK_EDGE_PX,
    IMAGE_SUFFIXES,
    MAX_BYTES,
    MAX_EDGE_PX,
    MAX_PHOTOS,
    QUALITY_LADDER,
    encode_webp,
    sha256_hex,
)
```

> **The script runs as `python scripts/prepare_photos.py`, which puts `scripts/` on `sys.path[0]` and the repository root nowhere** (the executability gap Task L4 found for `seed_listings.py`). It is run by hand from the repository root, so `app` resolves — but prove it rather than assume it: `tests/scripts/test_prepare_photos.py` gains a subprocess test that runs the file from a different working directory, exactly as `test_the_module_runs_as_a_bare_script_from_any_working_directory` does for the seeder. If it fails, the fix is the two-line `sys.path` preamble that script already needs, **not** moving the encoder back.

- [ ] **Step 9: Run both suites and the seed pipeline's own**

```bash
poetry run pytest tests/media/test_encode.py tests/test_storage.py tests/scripts/test_prepare_photos.py -v
```
Expected: PASS. `test_prepare_photos.py` must be green **unchanged apart from the new subprocess test** — that is the proof the rules moved rather than changed.

- [ ] **Step 10: Documentation rows for the four settings (GREENFIELD arm only)**

`tests/test_docs.py::test_every_setting_is_documented_in_env_example_and_deploy_md` requires a `^#?\s*NAME=` line in `.env.example` **and** the name present in `DEPLOY.md`. Add to `.env.example`:

```bash
# Object storage for seller uploads and the Census archive (spec 2026-09-08 D14). The bucket is
# `practice-match-data`, created per Railway environment. Unset locally: ObjectStore.from_settings
# logs a warning and the upload routes refuse; everything else works.
S3_ENDPOINT_URL=
S3_BUCKET=
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=
```

and, in `DEPLOY.md`'s environment-variable table, four rows in the table's own shape:

```markdown
| `S3_ENDPOINT_URL` | api, worker | Railway bucket endpoint | Object-storage endpoint. Empty for AWS S3 proper; set for a Railway/S3-compatible bucket. |
| `S3_BUCKET` | api, worker | `practice-match-data` | The approved bucket, one per environment (A-C1 ¶7). Seller uploads under `listings/`, the Census archive under `census/`. |
| `S3_ACCESS_KEY_ID` | api, worker | *(secret)* | Set in Railway only. Never in git, chat or a CI log. |
| `S3_SECRET_ACCESS_KEY` | api, worker | *(secret)* | Set in Railway only. Never in git, chat or a CI log. |
```

- [ ] **Step 11: Full backend gate**

```bash
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run mypy scripts/migrate.py scripts/bootstrap_admin.py scripts/seed_persona.py scripts/reset_rate_limits.py scripts/prepare_photos.py scripts/seed_listings.py --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
```
Expected: all green at 100 %. If `app/media/encode.py` reports an uncovered branch, the missing case is named in Step 6 — add the named test, never a pragma.

- [ ] **Step 12: Confirm the image still builds, and record its size**

```bash
docker build -t pm-sl2 . && docker images pm-sl2 --format '{{.Size}}'
```
Expected: a successful build. Record the size beside `main`'s in the hand-back — Pillow moving to the main group is the one thing in this plan that grows the runtime image, and the number belongs in the note rather than in a claim that it is small.

- [ ] **Step 13: Commit**

```bash
git add app/storage.py app/media/__init__.py app/media/encode.py tests/test_storage.py tests/media/__init__.py tests/media/test_encode.py \
        scripts/prepare_photos.py tests/scripts/test_prepare_photos.py app/config.py pyproject.toml poetry.lock .env.example DEPLOY.md
git commit -m "feat(storage): shared ObjectStore and the photograph pipeline on the request path

Spec 2026-09-08 D14/D15; controller amendment A-SL1 puts Census Task A2's ObjectStore
at app/storage.py, because two sub-projects depend on it, and this one adds only
delete(). app/media/encode.py is scripts/prepare_photos.py's own rules, unchanged and
now shared: EXIF-transpose, flatten, <= 1600 px, the (82,72,62,52,44,20) ladder with
the 1100 px fallback, <= 250 KB WebP, and every metadatum stripped — a phone
photograph's GPS must not survive an upload to a listing whose location is undisclosed.

Pillow moves from the dev group to main: the encoder is on the request path now, so
the runtime image needs it. The comment that said otherwise is corrected in place.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

**Controller amendment A-SL12 (2026-09-09; rulings on the SL2 review — APPROVED, 2 Medium, 2 Low; closed at source in a round after SL3, single writer).** M1 — `encode_webp` catches `PIL.Image.DecompressionBombError` (and sets an explicit `Image.MAX_IMAGE_PIXELS` bound as a module constant) so it keeps its "None, never an exception" contract; tested with an oversized synthetic image. M2 — the test fixture is typed `pytest.MonkeyPatch`; the `# type: ignore[attr-defined]` (a suppression, forbidden by Global Constraint (c)) and the dead `import pytest`/`del pytest` pair go. L3 — `ObjectStore.delete()` returns `bool` per A-SL1: fixed on the CENSUS branch in A3's fix round (A-C3b) and cherry-picked here so both copies stay byte-identical; nothing on this branch edits `app/storage.py` directly. L4 — accepted: seed-corpus byte-identity is asserted structurally (the script calls the shared encoder) plus synthetic fixtures; the raw sources live only on John's machine. SL4's dispatch carries the M1 note (the upload route must not assume the encoder never raises until M1 lands).

---

### Task SL3: `app/api/seller_listings.py` — create, list, read and the per-step PATCH — **2.5 days**

**Files:**
- Create: `app/api/seller_listings.py`
- Create: `tests/api/test_seller_listings.py`
- Modify: `app/main.py` (mount inside the `site_mode == "app"` block)
- Modify: `app/auth/limits.py` (the three constants)
- Modify: `app/api/listings.py` (`serialise` blanks `rev` — D22; `drop_list_cache()` — D16; both consumed here)

**Interfaces:**
- Produces `GET /api/seller/listings`, `POST /api/seller/listings`, `GET /api/seller/listings/{id}`, `PATCH /api/seller/listings/{id}`.
- Produces `serialise_draft(row, assets) -> dict` and `STEP_FIELDS`, `BLDG_IN`, `BLDG_OUT` — the names SL7's adapter tests and SL4/SL5 import.
- Produces `app.api.listings.drop_list_cache(redis) -> int` (D16) and `app.auth.limits.LISTING_PATCH / LISTING_UPLOAD / LISTING_SUBMIT` (D17).
- Consumes: `app.auth.deps.require`, `app.auth.limits.hit`, `app.db.sync_conn`, `app.cache.sync_redis`, `app.api.listings._error`.

> **Why `/api/seller/listings…` and not `/api/listings/mine` (D9).** Starlette matches in registration order and `/api/listings/{listing_id}` is already mounted, so `/api/listings/mine` would resolve to the buyer's detail route with `listing_id="mine"` unless the routers were included in one particular order — a trap nobody should have to remember and nothing would catch until a member saw a 404. Disjoint prefixes remove it, and `tests/api/test_seller_listings.py::test_the_seller_prefix_does_not_collide_with_the_buyer_detail_route` proves it rather than asserting it in prose.

> **Why a non-owner gets 404 and not 403 (D7).** A 403 confirms the listing exists. Ownership is not in the matrix — `listing.manage_own` says *a seller may manage listings*, and `seller_id = <principal.account_id>` says *which* — so the scope check is the handler's, and its refusal must not leak the existence of somebody else's practice.

- [ ] **Step 1: Write the failing endpoint tests**

Create `tests/api/test_seller_listings.py`:

```python
"""The seller wizard's own surface (spec 2026-09-08 D7-D13, D16, D17).

Fixtures are `tests/api/conftest.py`'s: `client` (base URL https://qa.foundation.vin, so the Origin
check passes), `member(roles=..., state=..., email=...) -> (account_id, cookies, headers)`, and the
root `conn`/`redis`. There is no migrated `scratch_db` fixture — `conn` is the scratch database with
every migration applied and `settings.database_url` pointed at it.
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.api.conftest import auth_headers


def _seller(member: Any) -> tuple[Any, dict[str, str], dict[str, str]]:
    return member(roles=("buyer", "seller"), email="sl-seller@example.org")


async def _create(client: Any, cookies: dict[str, str], headers: dict[str, str]) -> str:
    response = await client.post("/api/seller/listings", headers=auth_headers(cookies, headers))
    assert response.status_code == 201, response.text
    listing_id: str = response.json()["id"]
    return listing_id


async def test_a_seller_creates_a_draft_owned_by_themselves_with_every_flag_off(client: Any, conn: Any, member: Any) -> None:
    """D9's POST: one call, when *Create a listing* is first clicked. D11: `source='seller'` and all
    four disclosure flags false — the table's own defaults, so a seller hides by default."""
    account_id, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    with conn.cursor() as cur:
        cur.execute("SELECT seller_id, source, status, slug, location_disclosed, name_disclosed,"
                    " rev_disclosed, documents_disclosed FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (account_id, "seller", "draft", f"listing-{listing_id}", False, False, False, False)


async def test_a_buyer_may_not_create_a_listing(client: Any, conn: Any, member: Any) -> None:
    """`listing.manage_own` is the `seller` role's alone (permissions.py:24) — the matrix does this,
    not the handler, and this is the test that says so."""
    _, cookies, headers = member(roles=("buyer",), email="sl-buyer@example.org")
    response = await client.post("/api/seller/listings", headers=auth_headers(cookies, headers))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_an_anonymous_caller_gets_the_generic_401(client: Any, conn: Any) -> None:
    response = await client.post("/api/seller/listings", headers={"Origin": "https://qa.foundation.vin"})
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}


async def test_the_seller_prefix_does_not_collide_with_the_buyer_detail_route(client: Any, conn: Any, member: Any) -> None:
    """D9's whole reason. `/api/listings/mine` would have been swallowed by
    `/api/listings/{listing_id}`; `/api/seller/listings` cannot be."""
    from app.main import create_app

    paths = {getattr(route, "path", "") for route in create_app().routes}
    assert "/api/seller/listings" in paths
    assert not any(path.startswith("/api/listings/") and path.endswith("/mine") for path in paths)


async def test_the_dashboard_lists_only_this_sellers_listings_in_every_status(client: Any, conn: Any, member: Any) -> None:
    """D9's GET. Every status, newest-touched first — `listing_owner_idx`'s own order."""
    mine, cookies, headers = _seller(member)
    other, other_cookies, other_headers = member(roles=("buyer", "seller"), email="sl-other@example.org")
    first = await _create(client, cookies, headers)
    second = await _create(client, cookies, headers)
    await _create(client, other_cookies, other_headers)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='withdrawn' WHERE id=%s", (first,))
    response = await client.get("/api/seller/listings", headers=auth_headers(cookies, headers))
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [second, first]
    assert {item["status"] for item in body["items"]} == {"draft", "withdrawn"}
    assert body["next_cursor"] is None
    assert other is not mine


async def test_a_non_owner_gets_404_on_every_single_listing_route(client: Any, conn: Any, member: Any) -> None:
    """D7: 404, never 403 — a listing that is not yours should not be confirmed to exist."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    _, thief_cookies, thief_headers = member(roles=("buyer", "seller"), email="sl-thief@example.org")
    signed = auth_headers(thief_cookies, thief_headers)
    for response in (
        await client.get(f"/api/seller/listings/{listing_id}", headers=signed),
        await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "Theirs"}, headers=signed),
    ):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_a_listing_id_that_is_not_a_uuid_is_a_404_not_a_422(client: Any, conn: Any, member: Any) -> None:
    _, cookies, headers = _seller(member)
    response = await client.get("/api/seller/listings/not-a-uuid", headers=auth_headers(cookies, headers))
    assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"


async def test_staff_read_any_draft_through_listing_review(client: Any, conn: Any, member: Any) -> None:
    """D9's GET, second arm: the reviewer opens the draft the seller submitted."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    _, staff_cookies, staff_headers = member(roles=("staff",), email="sl-staff@example.org")
    response = await client.get(f"/api/seller/listings/{listing_id}", headers=auth_headers(staff_cookies, staff_headers))
    assert response.status_code == 200 and response.json()["id"] == listing_id


async def test_each_step_writes_its_own_fields_and_the_four_forced_mappings(client: Any, conn: Any, member: Any) -> None:
    """D10, the whole table. `desc` is the `services` column, `bldg` takes a value map, `type`
    accepts 'Other', and `facilityType` lands in the new `facility_type`."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)

    async def patch(step: int, fields: dict[str, Any]) -> Any:
        return await client.patch(f"/api/seller/listings/{listing_id}?step={step}", json=fields, headers=signed)

    assert (await patch(1, {"name": "Hill Country Animal Hospital", "type": "Other", "est": "1998", "ownership": "Multi-doctor LLC"})).status_code == 200
    assert (await patch(2, {"city": "Cedar Park", "zip": "78613", "anon": True})).status_code == 200
    assert (await patch(3, {"price": "1,450,000", "rev": "$2,100,000", "revBand": True})).status_code == 200
    assert (await patch(4, {"docs": "3", "rooms": "5", "sqft": "4,200", "hours": "Mon-Fri 7:30-6", "desc": "Wellness, dentistry"})).status_code == 200
    assert (await patch(5, {"bldg": "Available separately", "facilityType": "Medical park", "facility": "Corner lot"})).status_code == 200

    with conn.cursor() as cur:
        cur.execute("SELECT name, type, est, ownership, city, zip, area, name_disclosed, location_disclosed,"
                    " price, rev, rev_disclosed, docs, rooms, sqft, hours, services, bldg, facility_type, facility"
                    " FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (
            "Hill Country Animal Hospital", "Other", 1998, "Multi-doctor LLC", "Cedar Park", "78613", "Cedar Park",
            False, False, 1_450_000, 2_100_000, False, 3, 5, 4200, "Mon-Fri 7:30-6", "Wellness, dentistry",
            "Separate", "Medical park", "Corner lot",
        )


async def test_step_seven_writes_the_four_disclosure_columns_inverted(client: Any, conn: Any, member: Any) -> None:
    """D20. The design's three switches are all "hide this"; the columns are all "show this"."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=7",
                                  json={"anon": False, "revBand": False, "docsLocked": False},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT name_disclosed, location_disclosed, rev_disclosed, documents_disclosed FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (True, True, True, True)


async def test_a_field_from_another_step_is_refused(client: Any, conn: Any, member: Any) -> None:
    """D10: "A `PATCH` accepts only the step's own fields; anything else is `400 BAD_REQUEST`.""" ""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "A", "price": "10"},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"
    assert "price" in response.json()["error"]["message"]


@pytest.mark.parametrize("step", ["6", "8", "0", "9", "one", ""])
async def test_only_the_six_field_steps_accept_a_patch(client: Any, conn: Any, member: Any, step: str) -> None:
    """Step 6 is uploads and step 8 is the preview; neither has a field set, and a typo'd `?step=`
    must not silently write nothing and answer 200."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step={step}", json={},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 400 and response.json()["error"]["code"] == "BAD_REQUEST"


@pytest.mark.parametrize(("raw", "stored"), [("1,450,000", 1_450_000), ("$2,100,000", 2_100_000), (" 900000 ", 900_000), ("0", 0)])
async def test_money_arrives_as_the_string_the_design_produces(client: Any, conn: Any, member: Any, raw: str, stored: int) -> None:
    """D10's last paragraph. The wizard's own `previewRows` prefixes "$", so the stored value is the
    bare number and the API strips `,`, `$` and spaces."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=3", json={"price": raw},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT price FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (stored,)


@pytest.mark.parametrize("raw", ["1.45m", "twelve", "-5", "1,4x0", "", "1e6"])
async def test_a_number_that_is_not_one_is_refused_in_the_envelope(client: Any, conn: Any, member: Any, raw: str) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=3", json={"price": raw},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 400
    assert set(response.json()) == {"error"}, "never FastAPI's {'detail': ...}"


@pytest.mark.parametrize(("field", "value"), [("type", "Aquatic"), ("ownership", "Cooperative")])
async def test_a_select_value_the_design_does_not_offer_is_refused(client: Any, conn: Any, member: Any, field: str, value: str) -> None:
    """The enum is the approved design's own option list (logic.js:1174), checked before the
    database sees it, so a CheckViolation can never become a 500."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={field: value},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 400 and response.json()["error"]["code"] == "BAD_REQUEST"


async def test_saving_a_published_listing_takes_it_off_the_market_at_once(client: Any, conn: Any, member: Any) -> None:
    """D3, John's ruling. The first PATCH that changes a field of a published listing moves it to
    in_review, stamps nothing else, and the existing published-only read filter does the removing."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "A", "type": "Small animal", "est": "1998"}, headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=2", json={"city": "Cedar Park", "zip": "78613"}, headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=3", json={"price": "1000000"}, headers=signed)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='published', state='TX', market='Austin, TX', area='Cedar Park' WHERE id=%s", (listing_id,))
    assert (await client.get(f"/api/listings/{listing_id}", headers=signed)).status_code == 200

    assert (await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"rooms": "6"}, headers=signed)).status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT status, submitted_at IS NOT NULL FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == ("in_review", True)
    assert (await client.get(f"/api/listings/{listing_id}", headers=signed)).status_code == 404

    # ...and a second PATCH in the same review cycle does not re-transition or re-stamp (D3).
    with conn.cursor() as cur:
        cur.execute("SELECT submitted_at FROM listing WHERE id=%s", (listing_id,))
        stamped = cur.fetchone()[0]
    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"rooms": "7"}, headers=signed)
    with conn.cursor() as cur:
        cur.execute("SELECT status, submitted_at FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == ("in_review", stamped)


async def test_a_published_edit_writes_one_audit_row_naming_no_permission(client: Any, conn: Any, member: Any) -> None:
    """D4/D8: seller transitions are audited too, and they name no permission by design — exactly
    like `applications.submit`. `tests/auth/test_permissions.py` cannot see them (the route is
    guarded by `listing.manage_own`, which is not in AUDITED), so this asserts it on purpose."""
    from app.api import seller_listings as SL
    from app.auth import permissions as PM

    assert SL.EDIT_ACTION == "listing.edit" and SL.EDIT_ACTION not in PM.MATRIX
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='published', name='A', city='C', zip='7', type='Small animal',"
                    " est=1998, price=1, state='TX', market='Austin, TX', area='C' WHERE id=%s", (listing_id,))
    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"rooms": "6"}, headers=auth_headers(cookies, headers))
    with conn.cursor() as cur:
        cur.execute("SELECT action, before, after FROM audit_log WHERE target_type='listing' AND target_id=%s", (str(listing_id),))
        assert cur.fetchall() == [("listing.edit", {"status": "published"}, {"status": "in_review"})]


async def test_a_withdrawn_listing_refuses_every_write(client: Any, conn: Any, member: Any) -> None:
    """The lifecycle table's last row: withdrawn is terminal, and the seller may do nothing."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='withdrawn' WHERE id=%s", (listing_id,))
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "A"},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 409 and response.json()["error"]["code"] == "STATE"


async def test_the_draft_serialiser_returns_the_owners_unblanked_truth(client: Any, conn: Any, member: Any) -> None:
    """D11. `serialise` is the buyer contract and is untouched; this one keeps nulls, applies no
    disclosure blanking, maps `bldg` back to the design's own wording and carries `assets`."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "Hill Country", "type": "Small animal", "est": "1998"}, headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=5", json={"bldg": "Available separately"}, headers=signed)
    body = (await client.get(f"/api/seller/listings/{listing_id}", headers=signed)).json()
    assert body["name"] == "Hill Country"       # not blanked, though name_disclosed is false
    assert body["bldg"] == "Available separately"   # the design's wording, not the column's 'Separate'
    assert body["city"] is None and body["price"] is None    # nulls preserved, never "" or 0
    assert body["assets"] == []
    assert body["anon"] is True and body["revBand"] is True and body["docsLocked"] is True


async def test_a_patch_drops_every_listings_cache_key_after_the_commit(client: Any, conn: Any, redis: Any, member: Any) -> None:
    """D16, and the ordering `admin_users.py` learned in I5c fix round 1: the drop happens AFTER the
    transaction commits, never before, or a concurrent read re-caches the pre-write payload."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    redis.set("listings:v1:::50", b'{"items": []}')
    redis.set("listings:v1:Austin, TX::50", b'{"items": []}')
    redis.set("session:keep-me", b"x")
    await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "A"}, headers=auth_headers(cookies, headers))
    assert redis.get("listings:v1:::50") is None
    assert redis.get("listings:v1:Austin, TX::50") is None
    assert redis.get("session:keep-me") == b"x"


async def test_the_patch_rate_limit_is_per_account_and_refuses_in_the_envelope(client: Any, conn: Any, redis: Any, member: Any, monkeypatch: Any) -> None:
    """D17. Generous enough that a seller working through eight steps never meets it; the test
    lowers it rather than sending 241 requests."""
    from app.api import seller_listings as SL

    monkeypatch.setattr(SL, "LISTING_PATCH", (2, 3600))
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    for _ in range(2):
        assert (await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "A"}, headers=signed)).status_code == 200
    refused = await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "A"}, headers=signed)
    assert refused.status_code == 429 and refused.json()["error"]["code"] == "RATE_LIMITED"


async def test_serialise_blanks_rev_when_the_flag_is_off_and_keeps_it_when_it_is_on(conn: Any) -> None:
    """D22, on the BUYER serialiser — the one behavioural change this plan makes to it. `money()`
    renders a null as "—" already (logic.js:251), so no screen moves; every seed sets the flag true
    (020's backfill), so nothing John sees on QA changes."""
    from datetime import UTC, datetime

    from app.api.listings import serialise

    row = {
        "id": "11111111-1111-1111-1111-111111111111", "slug": "s", "name": "N", "street": None, "city": "C",
        "state": "TX", "zip": None, "phone": None, "hours": None, "status": "published",
        "location_disclosed": True, "name_disclosed": True, "lat": None, "lng": None, "area": "C",
        "type": "Small animal", "market": "Austin, TX", "price": 1, "rev": 2_100_000, "docs": None,
        "rooms": None, "sqft": None, "bldg": None, "est": None, "listed_at": datetime.now(UTC),
        "note": None, "staff": None, "services": None, "facility": None, "ownership": None, "photos": [],
        "rev_disclosed": False,
    }
    assert serialise(row, datetime.now(UTC))["rev"] is None
    assert serialise({**row, "rev_disclosed": True}, datetime.now(UTC))["rev"] == 2_100_000
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
poetry run pytest tests/api/test_seller_listings.py -q
```
Expected: FAIL — every request 404s (`{"error": {"code": "NOT_FOUND", ...}}` from `not_found_router`'s catch-all) because the router does not exist, and `test_serialise_blanks_rev…` fails with `KeyError: 'rev_disclosed'`.

- [ ] **Step 3: Add the rate limits and the cache drop**

In `app/auth/limits.py`, after `FORGOT_IP, TOKEN_IP`:

```python
# Seller listing lifecycle (spec 2026-09-08 D17), all keyed on the ACCOUNT id: generous enough that
# a seller working through eight steps and four photographs never meets one, tight enough that a
# script cannot fill a bucket. `LISTING_PATCH` is the autosave — the design's own "Saved
# automatically" fires once per step, not per keystroke, so 240/hour is four hours of continuous work.
LISTING_PATCH, LISTING_UPLOAD, LISTING_SUBMIT = (240, 3600), (40, 3600), (20, 3600)
```

In `app/api/listings.py`, beside `LIST_TTL_S`, add the invalidation the module's own comment has been asking for since Task L5 — **and replace that comment's last paragraph with what is now true**:

```python
LIST_CACHE_PREFIX = "listings:v1:"


def drop_list_cache(cache: Any) -> int:
    """Every `listings:v1:*` key, dropped; the number removed.

    Spec 2026-09-08 D16, which is this module's own review-round-2 M4 requirement made real: a
    disclosure flag turned OFF must stop reaching buyers AT ONCE, not within the 60 s TTL. Every
    writer in `app/api/seller_listings.py` and `app/api/admin_listings.py` calls this AFTER its
    transaction commits — the ordering `admin_users.py` learned in I5c fix round 1 — because
    dropping the key while the write is uncommitted leaves a window in which a concurrent read
    re-caches the pre-write payload for the full TTL.

    `scan_iter`, not `keys`: the cache is small but a blocking KEYS on a shared Railway Redis is a
    stall every other consumer pays for. The prefix is the key shape's own, so a v2 key scheme
    cannot be silently missed — it would not match, and the test that plants two keys would fail.
    """
    removed = 0
    for key in cache.scan_iter(match=f"{LIST_CACHE_PREFIX}*"):
        cache.delete(key)
        removed += 1
    return removed
```

and in `serialise`, one line changes — D22:

```python
        "price": row["price"], "rev": row["rev"] if row.get("rev_disclosed") else None,
        "docs": row["docs"], "rooms": row["rooms"],
```

with `rev_disclosed` added to `_SELECT`'s column list beside `name_disclosed`. (`row.get`, not `row[...]`: `serialise` is called directly by tests and by Wave 2b's admin views with rows from other drivers, exactly as `photo_list`'s docstring records — a row without the key means "not disclosed", which is the safe direction.)

- [ ] **Step 4: Write `app/api/seller_listings.py`**

```python
"""The seller wizard's own surface (spec 2026-09-08, D7-D13, D16, D17).

Eight approved steps, a preview and a Submit that the design has drawn since V2 and that nothing
has ever persisted. This module is that persistence, and nothing about the screens changes.

Shapes copied from `app/api/listings.py` and `app/api/admin_users.py`, all load-bearing:

* **Every guard is a module-level constant used through `Depends`, never wrapped** — the route-guard
  and audit drift tests resolve a permission by the guard object's IDENTITY (`deps.permission_of`).
* **Every refusal uses `_error(code, message, status)`** — decision A5's body, imported from
  `app.api.listings` rather than copied, because two copies is how two envelopes appear. Query
  parameters are parsed by hand for the same reason: `Query(ge=...)` answers FastAPI's
  `{"detail": [...]}`, which is not the envelope the frontend's `AuthError` reads.
* **Connections are `with closing(sync_conn()) as conn, conn:`** — psycopg2's `with conn:` commits
  without closing.

**Ownership is enforced HERE, not in the matrix (D7).** `listing.manage_own` says a seller may
manage listings; `seller_id = principal.account_id` says which. A non-owner gets 404, never 403 — a
listing that is not yours should not be confirmed to exist.

**`listing.manage_own` is deliberately NOT in `permissions.AUDITED` (D8):** the wizard's autosave
rides on it, and one audit row per step per keystroke-batch into a table whose triggers refuse
DELETE is a slow leak. The transitions still write their own rows, under action names that name no
permission BY DESIGN — exactly like `applications.submit`/`answer`/`reapply`, and outside the drift
test's reach for the same documented reason. `tests/api/test_seller_listings.py` asserts that on
purpose rather than leaving it to be noticed.
"""
from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.api.listings import _error, drop_list_cache
from app.auth import audit
from app.auth import sessions as S
from app.auth.deps import require
from app.auth.limits import LISTING_PATCH, hit
from app.cache import sync_redis
from app.db import sync_conn

router = APIRouter(prefix="/api/seller")

# Hoisted, never wrapped (Global Constraint (f)).
REQUIRE_MANAGE_OWN = require("listing.manage_own")
REQUIRE_REVIEW = require("listing.review")
Owner = Annotated[S.Principal, Depends(REQUIRE_MANAGE_OWN)]

MAX_LIST = 200
DEFAULT_LIMIT = 50
MAX_TEXT = 4_000
# The transitions the SELLER's own routes write. They name no permission by design — `account.self`
# does the same for `applications.submit`/`answer`/`reapply` — so the AST drift test never sees
# them and there is no list to add them to. One namespace, so an auditor greps `listing.` once.
EDIT_ACTION = "listing.edit"

# --- D10: the per-step whitelist, and the four mappings the approved design forces ---------------
#
# 1. `desc` is the `services` column. Step 4's textarea is `area("desc", "Services offered", ...)`
#    (logic.js:1177); `note` is the overview prose the seeder writes, not this.
# 2. `bldg` needs a value map: the select offers "Available separately" and the column's CHECK
#    allows 'Separate'.
# 3. `type` accepts 'Other' — the step-1 select offers it and migration 020 widened the CHECK.
# 4. `facilityType` had no column at all; 020 adds `facility_type`.
STEP_FIELDS: dict[int, tuple[str, ...]] = {
    1: ("name", "type", "est", "ownership"),
    2: ("city", "zip", "anon"),
    3: ("price", "rev", "revBand"),
    4: ("docs", "rooms", "sqft", "hours", "desc"),
    5: ("bldg", "facilityType", "facility"),
    7: ("anon", "revBand", "docsLocked"),
}
# The design's own option lists (logic.js:1174, :1178), checked here so a CheckViolation from the
# database can never become a 500.
TYPES = ("Small animal", "Mixed", "Large animal", "Emergency", "Specialty", "Other")
OWNERSHIPS = ("Sole proprietor", "Two-doctor partnership", "Multi-doctor LLC", "Other")
FACILITY_TYPES = ("Standalone", "Strip or plaza", "Medical park", "Other")
BLDG_IN = {"Included": "Included", "Available separately": "Separate", "Leased": "Leased"}
BLDG_OUT = {value: key for key, value in BLDG_IN.items()}
MONEY_FIELDS = ("price", "rev")
INT_FIELDS = ("est", "docs", "rooms", "sqft")

_COLUMNS = """id, slug, name, city, zip, state, area, market, type, est, ownership, price, rev,
              docs, rooms, sqft, hours, services, bldg, facility_type, facility, status,
              location_disclosed, name_disclosed, rev_disclosed, documents_disclosed,
              photos, seller_id, submitted_at, created_at, updated_at"""


class Refusal(Exception):
    """A refusal the route renders through `_error`. Carries the envelope, never a status alone."""

    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _number(field: str, raw: object) -> int:
    """A money or integer field as the design's text inputs produce it ("1,450,000", "$2,100,000").

    D10's last paragraph: strip `,`, `$` and spaces, refuse anything else. Not `int(float(x))` — a
    seller typing "1.45m" must be told, not silently given a practice worth one dollar."""
    if isinstance(raw, int) and not isinstance(raw, bool):
        cleaned = str(raw)
    elif isinstance(raw, str):
        cleaned = raw.replace(",", "").replace("$", "").replace(" ", "")
    else:
        raise Refusal("BAD_REQUEST", f"{field} must be a number.", 400)
    if not cleaned.isdecimal():
        raise Refusal("BAD_REQUEST", f"{field} must be a number.", 400)
    return int(cleaned)


def _text(field: str, raw: object) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise Refusal("BAD_REQUEST", f"{field} must be text.", 400)
    if len(raw) > MAX_TEXT:
        raise Refusal("BAD_REQUEST", f"{field} is too long.", 400)
    return raw.strip() or None


def _one_of(field: str, raw: object, allowed: tuple[str, ...]) -> str:
    value = _text(field, raw)
    if value not in allowed:
        raise Refusal("BAD_REQUEST", f"{field} must be one of {', '.join(allowed)}.", 400)
    return value


def _flag(field: str, raw: object) -> bool:
    if not isinstance(raw, bool):
        raise Refusal("BAD_REQUEST", f"{field} must be true or false.", 400)
    return raw


def columns_for(step: int, body: dict[str, Any]) -> dict[str, Any]:
    """The step's fields as database columns, or a `Refusal`.

    The whitelist is one-directional and total: a field from another step is a 400 rather than a
    silent no-op, because the wizard sends one step at a time and a mis-sent field means the
    adapter and this table disagree — which is a bug to see, not to absorb."""
    if step not in STEP_FIELDS:
        raise Refusal("BAD_REQUEST", f"step must be one of {', '.join(str(s) for s in sorted(STEP_FIELDS))}.", 400)
    stray = sorted(set(body) - set(STEP_FIELDS[step]))
    if stray:
        raise Refusal("BAD_REQUEST", f"step {step} does not accept {', '.join(stray)}.", 400)
    out: dict[str, Any] = {}
    for field, raw in body.items():
        if field in MONEY_FIELDS or field in INT_FIELDS:
            out[field] = _number(field, raw)
        elif field == "type":
            out["type"] = _one_of("type", raw, TYPES)
        elif field == "ownership":
            out["ownership"] = _one_of("ownership", raw, OWNERSHIPS)
        elif field == "facilityType":
            out["facility_type"] = _one_of("facilityType", raw, FACILITY_TYPES)
        elif field == "bldg":
            out["bldg"] = BLDG_IN[_one_of("bldg", raw, tuple(BLDG_IN))]
        elif field == "desc":
            out["services"] = _text("desc", raw)
        elif field == "anon":
            # D20: the design's step-7 label names BOTH the practice name and the address, so one
            # switch sets both columns. The API keeps them independent, so Rev 3's split into four
            # switches needs no API change.
            shown = not _flag("anon", raw)
            out["name_disclosed"] = out["location_disclosed"] = shown
        elif field == "revBand":
            out["rev_disclosed"] = not _flag("revBand", raw)
        elif field == "docsLocked":
            out["documents_disclosed"] = not _flag("docsLocked", raw)
        else:
            out[field] = _text(field, raw)
    if step == 2 and "city" in out:
        # `area` is the card's own label and `serialise` interpolates it into the anonymised name.
        # The approved step 2 collects a city and a ZIP, so the city IS the area; `state` and
        # `market` come from the reviewer at the first publish (D12).
        out["area"] = out["city"]
    return out


def serialise_draft(row: dict[str, Any], assets: list[dict[str, Any]]) -> dict[str, Any]:
    """The OWNER's own truth (D11) — every column unblanked, nulls preserved, plus `assets[]`.

    Deliberately not `serialise`: that one is the BUYER contract, it applies the disclosure
    blanking, and every published-listing pixel depends on it. Two serialisers is what keeps the
    zero-regression claim on the read surface a fact rather than a hope.

    The keys are the wizard's own (`state.w` in logic.js:204), not the columns': the adapter hands
    this straight to `setW`, so `services` comes back as `desc`, `facility_type` as `facilityType`
    and `bldg` in the design's own wording."""
    return {
        "id": str(row["id"]), "status": row["status"],
        "name": row["name"], "type": row["type"], "est": row["est"], "ownership": row["ownership"],
        "city": row["city"], "zip": row["zip"],
        "price": row["price"], "rev": row["rev"],
        "docs": row["docs"], "rooms": row["rooms"], "sqft": row["sqft"], "hours": row["hours"],
        "desc": row["services"],
        "bldg": BLDG_OUT.get(row["bldg"]) if row["bldg"] else None,
        "facilityType": row["facility_type"], "facility": row["facility"],
        # The three switches, in the design's own polarity: on means HIDE.
        "anon": not row["name_disclosed"],
        "revBand": not row["rev_disclosed"],
        "docsLocked": not row["documents_disclosed"],
        "state": row["state"], "market": row["market"], "area": row["area"],
        "submitted_at": row["submitted_at"].isoformat() if row["submitted_at"] else None,
        "updated_at": row["updated_at"].isoformat(),
        "assets": assets,
    }


def _row(conn: Any, listing_id: str) -> dict[str, Any] | None:
    try:
        parsed = UUID(listing_id)
    except ValueError:
        return None
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM listing WHERE id = %s", (parsed,))
        found = cur.fetchone()
        if found is None:
            return None
        return dict(zip([d[0] for d in cur.description], found, strict=True))


def owned_row(conn: Any, listing_id: str, principal: S.Principal) -> dict[str, Any]:
    """The listing, or a 404 `Refusal` — for anything that is not this principal's (D7)."""
    row = _row(conn, listing_id)
    if row is None or row["seller_id"] != principal.account_id:
        raise Refusal("NOT_FOUND", "No such listing.", 404)
    return row


def assets_of(conn: Any, listing_id: Any) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, kind, name, content_type, byte_size FROM listing_asset"
                    " WHERE listing_id = %s ORDER BY created_at, id", (listing_id,))
        return [{"id": str(r[0]), "kind": r[1], "name": r[2], "content_type": r[3], "byte_size": r[4]}
                for r in cur.fetchall()]


def _refused(exc: Refusal) -> JSONResponse:
    return _error(exc.code, exc.message, exc.status)


@router.get("/listings", dependencies=[Depends(REQUIRE_MANAGE_OWN)])
async def list_mine(request: Request) -> Response:
    """The dashboard's source: every status, most recently touched first — `listing_owner_idx`'s
    own order. Keyset-paged in `/api/admin/users`'s shape."""
    principal = request.state.principal
    raw_limit = request.query_params.get("limit")
    if raw_limit is not None and not raw_limit.isdecimal():
        return _error("BAD_REQUEST", "Invalid limit.", 400)
    limit = min(max(int(raw_limit or DEFAULT_LIMIT), 1), MAX_LIST)
    cursor = request.query_params.get("cursor")
    keyset: tuple[str, UUID] | None = None
    if cursor is not None:
        at, separator, raw_id = cursor.partition("|")
        try:
            if not separator:
                raise ValueError(cursor)
            datetime.fromisoformat(at)
            keyset = (at, UUID(raw_id))
        except ValueError:
            return _error("BAD_REQUEST", "Invalid cursor.", 400)
    where = "seller_id = %s" + (" AND (updated_at, id) < (%s::timestamptz, %s::uuid)" if keyset else "")
    params: list[Any] = [principal.account_id, *(keyset or ())]
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM listing WHERE {where} ORDER BY updated_at DESC, id DESC LIMIT %s",
                        (*params, limit + 1))
            names = [d[0] for d in cur.description]
            rows = [dict(zip(names, r, strict=True)) for r in cur.fetchall()]
        page = rows[:limit]
        items = [serialise_draft(row, assets_of(conn, row["id"])) for row in page]
    more = len(rows) > limit
    last = page[-1] if more and page else None
    return JSONResponse({
        "items": items,
        "next_cursor": f"{last['updated_at'].astimezone(UTC).isoformat().replace('+00:00', 'Z')}|{last['id']}" if last else None,
    })


@router.post("/listings", status_code=201)
async def create(request: Request, principal: Owner) -> Response:
    """Called once, when *Create a listing* is first clicked.

    `slug = 'listing-' || id` (D13). It stays `NOT NULL UNIQUE`, nothing about the seeder's
    `ON CONFLICT (slug)` changes, and the first publish rewrites it to the name plus the first
    eight characters of the id — so a seller's "ABC Animal Hospital" can never collide with a seed
    slug of the same name and can never make `seed_listings.py` refuse (exit 5)."""
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute("INSERT INTO listing (slug, source, status, seller_id) VALUES ('', 'seller', 'draft', %s) RETURNING id",
                    (principal.account_id,))
        listing_id = cur.fetchone()[0]
        cur.execute("UPDATE listing SET slug = %s WHERE id = %s", (f"listing-{listing_id}", listing_id))
    return JSONResponse({"id": str(listing_id)}, status_code=201)


@router.get("/listings/{listing_id}")
async def read_one(listing_id: str, request: Request, principal: Owner) -> Response:
    """The wizard's read for Edit and Continue — and the reviewer's, through `listing.review`."""
    with closing(sync_conn()) as conn, conn:
        row = _row(conn, listing_id)
        if row is None:
            return _error("NOT_FOUND", "No such listing.", 404)
        if row["seller_id"] != principal.account_id:
            try:
                REQUIRE_REVIEW(request)
            except Exception:
                return _error("NOT_FOUND", "No such listing.", 404)
        return JSONResponse(serialise_draft(row, assets_of(conn, row["id"])))


@router.patch("/listings/{listing_id}")
async def patch_step(listing_id: str, request: Request, principal: Owner) -> Response:
    """One call per step, the step's whitelisted field set only (D10), applying D3's
    published -> in_review transition and dropping the listings cache after the commit (D16)."""
    hit(sync_redis(), "listing:patch", str(principal.account_id), *LISTING_PATCH)
    raw_step = request.query_params.get("step", "")
    body = await request.json() if await request.body() else {}
    if not isinstance(body, dict):
        return _error("BAD_REQUEST", "Body must be an object.", 400)
    try:
        step = int(raw_step) if raw_step.isdecimal() else -1
        columns = columns_for(step, body)
        with closing(sync_conn()) as conn, conn:
            row = owned_row(conn, listing_id, principal)
            if row["status"] == "withdrawn":
                raise Refusal("STATE", "A withdrawn listing can no longer be edited.", 409)
            # D3, John's ruling: the FIRST save to a published listing moves it to in_review and off
            # the market at once. `GET /api/listings` filters `status = 'published'`, so the
            # transition alone does the removing — no new code on the read side. Subsequent PATCHes
            # in the same review cycle do not re-transition, which is why this is `== 'published'`
            # and not `!= 'in_review'`.
            leaving_market = row["status"] == "published"
            assignments = ", ".join(f"{name} = %({name})s" for name in columns)
            sets = f"{assignments}, " if assignments else ""
            if leaving_market:
                sets += "status = 'in_review', submitted_at = now(), "
            with conn.cursor() as cur:
                cur.execute(f"UPDATE listing SET {sets}updated_at = now() WHERE id = %(id)s",
                            {**columns, "id": row["id"]})
            if leaving_market:
                audit.write(conn, actor=principal, action=EDIT_ACTION, target_type="listing",
                            target_id=row["id"], before={"status": "published"}, after={"status": "in_review"},
                            request=request)
            fresh = _row(conn, listing_id)
            payload = serialise_draft(fresh, assets_of(conn, row["id"])) if fresh else {}
    except Refusal as exc:
        return _refused(exc)
    # AFTER the commit (D16, and I5c fix round 1's ordering): a disclosure flag turned OFF must stop
    # reaching buyers at once, and dropping the key while the write was uncommitted would leave a
    # window in which a concurrent read re-cached the pre-write payload for the full TTL.
    drop_list_cache(sync_redis())
    return JSONResponse(payload)
```

In `app/main.py`, inside the existing `if settings.site_mode == "app":` block, immediately after `app.include_router(listings_router)`:

```python
        # Same gate again (spec 2026-09-08 D9): the seller wizard's surface is a MEMBER surface —
        # `listing.manage_own` is the seller role's — so behind the Coming Soon page it is absent
        # rather than merely guarded, and `scripts/verify-deploy.sh production` probes for its 404
        # beside the other four. Its prefix is `/api/seller`, disjoint from `/api/listings`, so
        # nothing here can shadow the buyer's `/api/listings/{listing_id}` whatever the order.
        app.include_router(seller_listings_router)
```

with `from app.api.seller_listings import router as seller_listings_router` beside the other router imports.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
poetry run pytest tests/api/test_seller_listings.py tests/api/test_listings.py tests/auth/ -q
```
Expected: PASS. `tests/auth/test_permissions.py` and `test_matrix.py` must be green **with no edits** — they generate their rows from the running app, which is the check that the four new routes are guarded and that none of them needs an audit row.

- [ ] **Step 6: Full backend gate, then commit**

```bash
poetry run ruff check app tests scripts && poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
git add app/api/seller_listings.py app/api/listings.py app/auth/limits.py app/main.py tests/api/test_seller_listings.py
git commit -m "feat(api): the seller wizard persists — create, list, read and a per-step PATCH

Spec 2026-09-08 D7-D13, D16, D17. /api/seller/listings, a prefix disjoint from
/api/listings so nothing can shadow the buyer detail route (D9). Ownership is the
handler's (seller_id = me) and a non-owner gets 404, not 403 — a listing that is not
yours should not be confirmed to exist. The PATCH is per step and whitelisted, with
the four mappings the approved design forces: desc->services, the bldg value map,
type gains 'Other', and facilityType finally has a column. Saving an edit to a
published listing moves it to in_review and off the market at once, and every write
drops listings:v1:* AFTER the commit.

serialise() blanks rev when rev_disclosed is false (D22); money() already renders a
null as an em dash, and 020 backfilled every seed to true, so no screen moves.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

**Controller amendment A-SL11 (2026-09-09; ruling on SL3's NEEDS_CONTEXT).** The spec's D3 stamps `listing.submitted_at` and SL3/SL5 read it, but no migration produced it — a plan gap. SL3 adds `migrations/032_listing_submitted_at.sql` (`ALTER TABLE listing ADD COLUMN submitted_at timestamptz;`; 032 is free in this tree and the Census worktree) and the `EXPECTED_COLUMNS` row, RED first. The staff read `GET /api/admin/listings/{id}` (A-SL8) is built in SL3 as the first route of `app/api/admin_listings.py`, which SL5 extends. The collision test uses the shared `walk_routes`. Gate-forced edits to the brief's verbatim code (two unreachable branches, `_one_of` typing, an unused import, supplemental `list_mine` tests) are accepted and recorded. For SL6: the seeder's UPSERT must write `rev_disclosed`/`documents_disclosed` on insert (030's backfill covers only pre-existing rows).

---

**Controller amendment A-SL13 (2026-09-09; rulings on the SL3 review — APPROVED, 3 Medium, 9 Low; closed at source in a fix round after SL4 lands, single writer; SL4 was warned not to inherit them).** M1 — D10's "refuse anything else" means garbage, not blanks: for OPTIONAL numeric fields an empty string clears the value (null); required fields keep refusing; SL7's autosave depends on it. M2 — a write that would violate `listing_submittable_ck` (blanking `name`/`city`/`zip` on a non-draft) is validated before the statement and refused in the envelope (`409 NOT_SUBMITTABLE`), never a 500. M3 — a malformed JSON body is `400 BAD_JSON` in the envelope. L1 — every write is owner-scoped in the SQL (`AND seller_id = %s`), not only reads. L2–L9 — closed exactly as the review specifies. D26's data path (photographs and documents in the seller's draft read) is built in SL4 with the asset routes.

---

### Task SL4: photographs and documents — upload, reorder, delete, and the locked read — **2.5 days**

**Files:**
- Modify: `app/api/seller_listings.py` (five routes)
- Modify: `app/api/listings.py` (`get_listing_photo` gains the seller arm — D15 reason 3)
- Create: `tests/api/test_listing_assets.py`

**Interfaces:**
- Produces `POST /api/seller/listings/{id}/photos`, `PATCH /api/seller/listings/{id}/photos`, `DELETE /api/seller/listings/{id}/assets/{asset_id}`, `POST /api/seller/listings/{id}/documents`, `GET /api/seller/listings/{id}/documents/{asset_id}`.
- Keys: `listings/{listing_id}/photos/{asset_id}.webp` and `listings/{listing_id}/documents/{asset_id}{ext}`.
- Consumes `app.storage.ObjectStore`, `app.media.encode`, `app.auth.limits.LISTING_UPLOAD`.

> **`listing.photos` stays the single home of photo ORDER (D15 reason 3), so `listing_asset` carries no `position` column.** For a `source='seed'` row an entry is a relative path resolved under `PHOTOS_ROOT` by the existing `photo_file()`; for a seller row it is an asset uuid resolved through `listing_asset` and `ObjectStore.get`. **One `if`, both arms tested.** Order is user-visible — `photoSet` fills the design's slots by index and `thumbSrc` takes photo 2 (A12.2–A12.5) — and two homes for one fact is how orders drift.

> **The buyer photo URL does not change (D15 reason 2).** `serialise` emits `/api/listings/{id}/photos/{n}` and the route already exists with a `listing.read` guard and `Cache-Control: private, max-age=86400`. Keeping it means the frontend, the design and the pixel oracles see nothing at all — no amendment, no baseline move, no new URL shape in `toPractice`.

> **Nothing about step 6's MARKUP changes.** The approved design offers one "Add files" button (`App.vue:1203`) and a strip of badge tiles (`:1206–1211`): no kind picker, no delete control, no reorder affordance, no progress state, no thumbnail. The API takes `kind`, accepts a reorder and accepts a delete **so that Rev 3 needs no API change**, and today only upload is reachable from the UI. Absent beats faked — §14 items 1 and 7.

- [ ] **Step 1: Write the failing asset tests**

Create `tests/api/test_listing_assets.py` — the file is long; these are its required test names and the assertions each must make. **Write every one; none may be dropped for time.**

```python
"""Seller uploads on object storage (spec 2026-09-08 D14, D15, D18, D19), against moto.

`_store` monkeypatches `app.api.seller_listings.store_for_request` to a moto-backed ObjectStore, so
no test needs credentials and none reaches the network. Every refusal is asserted as an
`{"error": {...}}` body, never `{"detail": ...}`.
"""
```

| Test | What it must assert |
|---|---|
| `test_a_photograph_is_re_encoded_to_webp_and_recorded` | 201; `listing_asset` row with `kind='photo'`, `content_type='image/webp'`, a 64-char `sha256`, `storage_key == f"listings/{id}/photos/{asset_id}.webp"`; the object in the store starts `RIFF`; `listing.photos` gained the asset id **as its last entry** |
| `test_an_uploaded_photograph_loses_its_gps` | the fixture really carries GPS EXIF (assert that first), the stored bytes carry none — the D15/A10.2 promise |
| `test_the_fifth_photograph_is_refused_with_the_photo_limit_code` | four succeed, the fifth is `409` `PHOTO_LIMIT`, `listing.photos` still has four, the store has four objects (nothing orphaned) |
| `test_a_photograph_that_is_not_an_image_is_refused` | `.jpg` carrying `PK\x03\x04` → `422` `BAD_IMAGE`, no row, no object |
| `test_a_photograph_over_fifteen_megabytes_is_refused_before_it_is_decoded` | `413` `TOO_LARGE`, and `app.media.encode.encode_webp` was never called (monkeypatched to raise) |
| `test_reorder_rewrites_listing_photos_and_nothing_else` | `PATCH .../photos` with the full ordered id list → 200, `listing.photos` in that order, no `listing_asset` row touched (`created_at` unchanged) |
| `test_reorder_refuses_a_list_that_is_not_exactly_this_listings_photos` | a missing id, an extra id, a duplicate and another listing's id are each `400` `BAD_REQUEST`; `listing.photos` unchanged |
| `test_delete_removes_the_row_the_object_and_the_photos_entry_in_one_transaction` | 204; the row gone, `store.exists` false, `listing.photos` shorter and still in order |
| `test_delete_of_another_listings_asset_is_a_404` | scoped by `listing_id`, not by asset id alone |
| `test_a_document_is_stored_as_uploaded_with_its_kind` | PDF → 201, `kind='other'` by default and `kind='floor_plan'` when sent, bytes byte-identical to the upload, key `listings/{id}/documents/{asset_id}.pdf` |
| `test_the_three_document_types_are_accepted_and_sniffed` | PDF (`%PDF-`), XLSX (`PK\x03\x04`), CSV (decodable text) all 201 |
| `test_a_document_whose_bytes_contradict_its_content_type_is_refused` | `application/pdf` carrying `MZ` → `422` `BAD_DOCUMENT`; a `.csv` of undecodable bytes likewise |
| `test_a_document_type_outside_the_allow_list_is_refused` | `image/svg+xml`, `application/zip`, `text/html` → `415` `UNSUPPORTED_TYPE` |
| `test_a_document_over_twenty_five_megabytes_is_refused` | `413` `TOO_LARGE` |
| `test_the_seventh_document_is_refused` | six succeed, the seventh is `409` `DOCUMENT_LIMIT` |
| `test_a_document_reads_to_its_owner_and_to_staff_and_to_nobody_else` | owner 200, staff 200, another member `403` `LOCKED`, anonymous `401` — D19's "Locked — seller approval", exactly as drawn |
| `test_a_document_read_carries_the_download_headers` | `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store` |
| `test_a_sellers_photograph_is_served_through_the_unchanged_buyer_route` | published seller listing, `GET /api/listings/{id}/photos/1` → 200 `image/webp` from the store; **the URL shape is the seed rows' own** |
| `test_a_seed_listings_photograph_still_comes_off_disk` | the other arm of D15 reason 3's single `if`, on a `source='seed'` row |
| `test_a_photo_entry_that_names_no_asset_is_a_404_not_a_500` | a hand-planted junk uuid in `listing.photos` |
| `test_uploads_are_refused_with_a_clear_message_when_storage_is_unconfigured` | `from_settings → None` → `503` `STORAGE_UNAVAILABLE`, message names the setting; **reads of existing seed photographs still work** |
| `test_the_upload_rate_limit_is_per_account` | `LISTING_UPLOAD` lowered by monkeypatch → `429` `RATE_LIMITED` |
| `test_every_asset_write_drops_the_listings_cache_after_the_commit` | upload, reorder and delete each clear `listings:v1:*` and leave `session:*` alone |

- [ ] **Step 2: Run to verify they fail**

```bash
poetry run pytest tests/api/test_listing_assets.py -q
```
Expected: FAIL — `404` from the catch-all on every upload path.

- [ ] **Step 3: Add the five routes to `app/api/seller_listings.py`**

```python
# --- Assets (D14, D15, D18, D19) -----------------------------------------------------------------
#
# Photographs are RE-ENCODED (app/media/encode.py) and documents are stored as uploaded. Both are
# read back through an API route, never a signed URL: the permission decision is per request, so a
# document stops being readable the moment the listing is unpublished or the account is suspended
# — which a URL minted an hour ago cannot express (D15 reason 1).
PHOTO_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_PHOTO_BYTES = 15 * 1024 * 1024
# D18/Q3, John's ruled default: PDF, CSV and XLSX. The design names a spreadsheet ("Equipment list ·
# Spreadsheet", logic.js:1290) and only ever shows the badges "Photo" and "PDF", so CSV and XLSX are
# badged with the uppercased extension — a new VALUE in an existing slot, the same class of change
# as A12 putting a real hospital name into `practiceName`, and not new markup.
DOCUMENT_TYPES = {
    "application/pdf": ".pdf",
    "text/csv": ".csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}
DOCUMENT_KINDS = ("floor_plan", "financials", "equipment", "other")
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_DOCUMENTS = 6
DOCUMENT_HEADERS = {"Content-Disposition": "attachment", "X-Content-Type-Options": "nosniff",
                    "Cache-Control": "private, no-store"}


def store_for_request() -> ObjectStore:
    """The configured store, or a `Refusal` the route renders as a 503.

    `from_settings` returning None is a legitimate state (a developer's machine, a fresh test
    database), and the API must keep serving every READ there — including the eighteen seed
    hospitals' photographs, which come off disk and need no bucket at all. Only the uploads stop,
    and they say why."""
    store = ObjectStore.from_settings(settings)
    if store is None:
        raise Refusal("STORAGE_UNAVAILABLE", "Uploads are unavailable: object storage is not configured (S3_BUCKET).", 503)
    return store


def _sniffed(content_type: str, data: bytes) -> bool:
    """Whether the BYTES agree with the declared type (D15's "content sniffed rather than trusted").

    A browser sets `Content-Type` from the file extension, and an extension is a claim the uploader
    controls. This is not a virus scan and does not pretend to be one; it is the cheap check that a
    thing stored as a PDF and served with `Content-Disposition: attachment` really is one."""
    if content_type == "application/pdf":
        return data.startswith(b"%PDF-")
    if content_type.endswith("spreadsheetml.sheet"):
        return data.startswith(b"PK\x03\x04")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


async def _upload_bytes(request: Request, limit: int) -> tuple[str, str, bytes]:
    """(filename, content_type, bytes) from a one-file multipart body, refusing an oversized one.

    Starlette buffers a large upload to a spooled temporary file, so the size check runs on what
    arrived rather than in memory — but it still runs BEFORE the decode, because handing a 40 MB
    "image" to Pillow is the expensive way to say no."""
    form = await request.form()
    field = form.get("file")
    if not hasattr(field, "filename") or not hasattr(field, "read"):
        raise Refusal("BAD_REQUEST", "A single `file` part is required.", 400)
    data = await field.read()          # type: ignore[union-attr]
    if len(data) > limit:
        raise Refusal("TOO_LARGE", f"The file is larger than {limit // (1024 * 1024)} MB.", 413)
    name = (getattr(field, "filename", "") or "file").rsplit("/", 1)[-1][:200]
    return name, getattr(field, "content_type", "") or "", data


@router.post("/listings/{listing_id}/photos", status_code=201)
async def upload_photo(listing_id: str, request: Request, principal: Owner) -> Response:
    hit(sync_redis(), "listing:upload", str(principal.account_id), *LISTING_UPLOAD)
    try:
        store = store_for_request()
        name, content_type, data = await _upload_bytes(request, MAX_PHOTO_BYTES)
        if content_type not in PHOTO_TYPES:
            raise Refusal("UNSUPPORTED_TYPE", f"A photograph must be one of {', '.join(PHOTO_TYPES)}.", 415)
        with closing(sync_conn()) as conn, conn:
            row = owned_row(conn, listing_id, principal)
            _writable(row)
            photos = photo_list(row["photos"])
            # John's ruling, restated in D18: "Keep the existing 4-photo seller-upload cap." The
            # seed pipeline's MAX_PHOTOS is the API's cap too, enforced server-side, and the fifth
            # upload is surfaced through the wizard's single error slot (logic.js:1197).
            if len(photos) >= MAX_PHOTOS:
                raise Refusal("PHOTO_LIMIT", f"A listing may carry {MAX_PHOTOS} photographs.", 409)
            encoded = encode_webp(data)
            if encoded is None:
                raise Refusal("BAD_IMAGE", "That file could not be read as a photograph.", 422)
            webp, digest = encoded
            with conn.cursor() as cur:
                cur.execute("INSERT INTO listing_asset (listing_id, kind, name, content_type, byte_size, sha256, storage_key)"
                            " VALUES (%s,'photo',%s,'image/webp',%s,%s,'') RETURNING id", (row["id"], name, len(webp), digest))
                asset_id = cur.fetchone()[0]
                key = f"listings/{row['id']}/photos/{asset_id}.webp"
                # The object goes in BEFORE the row is finalised and the transaction commits: a
                # committed row pointing at an object that was never written is a broken listing,
                # while an object with no row is a few kilobytes nothing reads. Fail in the
                # direction that leaves the database honest.
                store.put_immutable(key, webp, "image/webp")
                cur.execute("UPDATE listing_asset SET storage_key=%s WHERE id=%s", (key, asset_id))
                cur.execute("UPDATE listing SET photos = %s::jsonb, updated_at = now() WHERE id = %s",
                            (json.dumps([*photos, str(asset_id)]), row["id"]))
            payload = {"id": str(asset_id), "kind": "photo", "name": name,
                       "content_type": "image/webp", "byte_size": len(webp)}
    except Refusal as exc:
        return _refused(exc)
    drop_list_cache(sync_redis())
    return JSONResponse(payload, status_code=201)
```

The other four follow the same shape; write them out in full, each with the comment its decision earns:

- **`PATCH /listings/{id}/photos`** — body is `{"ids": [...]}`, the **full** ordered list; refuse anything that is not a permutation of `listing.photos` (`400 BAD_REQUEST`, naming which), then one `UPDATE listing SET photos = %s::jsonb`. Nothing in `listing_asset` moves — order lives in one place (D15 reason 3).
- **`DELETE /listings/{id}/assets/{asset_id}`** — one transaction: `DELETE FROM listing_asset WHERE id=%s AND listing_id=%s RETURNING storage_key, kind`; 404 when it returns nothing (so another listing's asset id is a 404, not a delete); for a photo also rewrite `listing.photos` without the id; then `store.delete(key)` **after** the commit, because an object left behind is recoverable and a row deleted for an object that survived is not. `204`.
- **`POST /listings/{id}/documents`** — `kind` from the form, defaulting to `other` (D18: the approved design has no kind picker); type in `DOCUMENT_TYPES`, `_sniffed`, `MAX_DOCUMENT_BYTES`, `MAX_DOCUMENTS`; stored as uploaded under `listings/{id}/documents/{asset_id}{ext}`.
- **`GET /listings/{id}/documents/{asset_id}`** — guarded by `require("listing.read")` (every member), then **owner ∨ staff/admin** in the handler; anyone else is `403 LOCKED`. That is precisely "Locked — seller approval" as the design draws it (`logic.js:1288–1290`), with no new approval workflow (John's ruling). **The buyer-with-an-accepted-request arm is the requests sub-project's**, and this is the guard it will attach to — one additional arm, when a `request` table exists. Served with `DOCUMENT_HEADERS`.

- [ ] **Step 4: The buyer photo route's seller arm — `app/api/listings.py` (D15 reason 3)**

```python
def _asset_bytes(conn: Any, listing_id: str, entry: str) -> bytes | None:
    """A seller-uploaded photograph's bytes, or None.

    The SECOND arm of `listing.photos`'s single `if` (spec 2026-09-08 D15 reason 3): a
    `source='seed'` entry is a relative path resolved under PHOTOS_ROOT by `photo_file`, and a
    seller entry is an asset uuid resolved here. Both arms are tested, and the URL the browser asks
    for is identical — which is why no amendment, no baseline and no `toPractice` field moves."""
    from app.storage import ObjectStore

    try:
        asset_id = UUID(entry)
    except ValueError:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT storage_key FROM listing_asset WHERE id=%s AND listing_id=%s AND kind='photo'",
                    (asset_id, UUID(listing_id)))
        found = cur.fetchone()
    if found is None:
        return None
    store = ObjectStore.from_settings(settings)
    return store.get(found[0]) if store is not None else None
```

and in `get_listing_photo`, between the `photos is None` refusal and `photo_file`:

```python
    entry = photos[n - 1] if 1 <= n <= len(photos) else None
    if entry is not None and "/" not in entry:
        # A seller's photograph: `listing.photos` holds the asset uuid, not a path. A seed entry
        # always contains a "/" (`<slug>/<n>.webp`), so the two are told apart by the value itself
        # rather than by a second query for the row's `source`.
        with closing(sync_conn()) as conn, conn:
            content = _asset_bytes(conn, listing_id, entry)
        if content is None:
            return _error("NOT_FOUND", "No such photograph.", 404)
        return Response(content=content, media_type="image/webp", headers={"Cache-Control": PHOTO_CACHE_CONTROL})
```

- [ ] **Step 5: GREEN, gate, commit**

```bash
poetry run pytest tests/api/test_listing_assets.py tests/api/test_listings.py -q
poetry run ruff check app tests scripts && poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
git add app/api/seller_listings.py app/api/listings.py tests/api/test_listing_assets.py
git commit -m "feat(api): seller photographs and documents on object storage

Spec 2026-09-08 D14/D15/D18/D19. Four photographs per listing (John's cap, enforced
server-side), re-encoded to WebP with every metadatum stripped — a phone photograph's
GPS must not reach a buyer of a listing whose location is undisclosed. Documents are
PDF, CSV and XLSX, content sniffed rather than trusted, stored as uploaded and served
attachment/nosniff/no-store to the owner and to staff and to nobody else: the design's
'Locked - seller approval', preserved exactly, with no new approval workflow.

Reads are proxied, never signed: the permission decision is per request. The buyer
photo route and its URL shape do not change - listing.photos gains one if, whose two
arms are a seed path under PHOTOS_ROOT and a seller asset id in the bucket.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

**Controller amendment A-SL15 (2026-09-09; rulings on SL4's report).** (1) **Assets are edits.** John's ruling — "editing a published listing re-enters review and removes it from the market until approved again" — covers adding, reordering or deleting a photograph or document: the asset routes apply D3 exactly as `patch_step` does (`published` → `in_review`, `submitted_at` stamped, the list cache dropped), in the same transaction; a draft or in-review listing is unaffected. (2) `Request.form()` is closed in `try/finally` on every multipart route (Starlette's `SpooledTemporaryFile` otherwise leaks under `-W error`) — recorded as the pattern for any future multipart route. (3) `python-multipart` is a runtime dependency (main group); SL9 confirms it reaches the image. (4) `serialise_draft` now carries `photos` (ordered, captioned from the upload filename or the seed inventory) and `documents` (with read URLs) — D26's data path; SL7's adapter reads them. (5) SL3's `patch_step` gets the same guarded `_json_body` (A-SL13 M3). (6) The two gate-forced departures (an `isinstance` check instead of `hasattr` + suppression; tests pointing `settings` at a moto bucket with an AWS-shaped endpoint) are accepted.

---

**Controller amendment A-SL14 (2026-09-09; SL5 pre-flight).** Task SL5's review routes EXTEND the existing `app/api/admin_listings.py` (the Seed Listings plan's admin read, already mounted and permission-gated) rather than creating a second admin listings module: the reviewer's publish/decline/request-changes handlers, the reviewer-supplied state + metro at publish (spec default), and the `listing.review` permission live beside the existing read, one module, one router, one audit vocabulary; tests extend `tests/api/test_admin_listings.py`.

**Controller amendment A-SL16 (2026-09-09; rulings on the SL4 review — NOT APPROVED, 1 High, 4 Medium, 10 Low; all closed in the combined SL3/SL4 fix round).** H1 — the upload size ceiling holds without `Content-Length`: file parts are read in bounded chunks and refused (413) the moment the running total exceeds the limit. M1 — no `storage_key` placeholder: the asset id and key are generated before the single insert. M2 — object-store failures are `503 STORAGE_UNAVAILABLE` refusals; a delete removes the object before the row and refuses if that fails. M3 — reorder and delete are rate-limited. M4 — the moto fixture mechanically prevents any network call. Lows: `documents_disclosed`/status read on the document route; content-type parameters stripped; the spec's literal `Content-Disposition: attachment` kept (ruled); Windows paths stripped from display names; RED evidence for every new test; a negative XLSX sniff test; the cache test proves ordering; one connection on the seller photo arm; the stale docstring; `seed_captions` catches `OSError` and `json.JSONDecodeError`.

**Controller amendment A-SL18 (2026-09-09 ~05:30 WITA; rulings on the SL3/SL4 scoped re-review — ALL ADDRESSED; 1 new Major, 3 Minor, 5 Info; closed in a second, short fix round).** (1) **Major-1 — documents stay owner-or-staff.** The round's `read_document` served a document to ANY signed-in member once `documents_disclosed` and `status = 'published'`; spec D19 and §5's route table allow only the owner and staff (`listing.review`) until the requests sub-project adds the buyer arm, so the read reverts to `owner ∨ staff` and `documents_disclosed` is recorded as the flag that arm will AND in — a test pins that a non-owner member is 404/403 exactly as before. (2) **Minor-1** — the stale comment describing the removed `Content-Length` pre-check goes. (3) **Minor-2** — JSON bodies on both PATCH routes are bounded (`MAX_JSON_BYTES = 64 * 1024`, module constant; over it → 413 `TOO_LARGE` in the envelope, read through the same bounded-stream helper so no unbounded body remains on the seller surface), tested at the boundary. (4) **Minor-3** — record-only by ruling: `delete_asset` deletes the object first, inside the row's `FOR UPDATE` transaction, so a failed object delete leaves the row (A-SL16); the lock spans two S3 round trips by that ordering; a plan line records it and nothing changes. (5) **Info** — the M1 drift test's tautological second assertion becomes a real one; `{"rev": null}` clears an optional numeric exactly as `""` does (null and blank are the same seller intent; tested for every `OPTIONAL_NUMERIC`); the moto network guard becomes a session-scoped autouse fixture in `tests/conftest.py` so no test in the suite can reach a real endpoint; `MULTIPART_OVERHEAD` charged against the whole envelope is accepted as a conservative bound and documented at the constant; the SL4 review's id slip is a ledger note only.

### Task SL5: submit, the seller's three transitions, and the VIN Foundation's review — **2.5 days**

**Files:**
- Modify: `app/api/seller_listings.py` (`POST .../submit`, `POST .../status`)
- Create: `app/api/admin_listings.py` (`GET /api/admin/listings`, `POST /api/admin/listings/{id}/decide`)
- Modify: `app/auth/permissions.py` (**one name** joins `AUDITED`)
- Modify: `app/main.py` (mount the admin router in the `app`-mode block)
- Modify: `app/mail/templates.py` **and** `app/mail/outbox.py` (three templates — **both** registries; `enqueue` raises `KeyError` on a template absent from the frozenset)
- Create: `tests/api/test_admin_listings.py`; Modify: `tests/api/test_seller_listings.py`, `tests/mail/test_templates.py`

**Interfaces:**
- `POST /api/seller/listings/{id}/submit` — `listing.manage_own` ∧ owner ∧ status ∈ {draft, declined, in_review} → `in_review`, `submitted_at = now()`, audit `listing.submit`, enqueue `listing_submitted`.
- `POST /api/seller/listings/{id}/status` — `{"action": "pause"|"republish"|"withdraw"}`, audit `listing.pause` / `listing.republish` / `listing.withdraw`.
- `GET /api/admin/listings?status=&cursor=&limit=` — `listing.review`, keyset-paged like `/api/admin/users`, `MAX_LIST` 200.
- `POST /api/admin/listings/{id}/decide` — `listing.publish`, `{"action": "publish"|"decline"|"unpublish", "reason": "", "state": "", "market": ""}`.

> **D8, and the one line it costs.** `listing.publish` joins `permissions.AUDITED` — it is a staff decision of exactly the class `users.decide` is, and `users.decide` is audited. That obliges the decide handler to call `audit.write(` **in its own body**: `test_audited_permissions_are_written_by_their_handlers` reads `inspect.getsource(route.endpoint)`, so delegating to a helper reads as unaudited. The handler writes `action="listing.publish"` on **every** branch — publish, decline and unpublish — with the branch and the reason in `after`/`reason`, which satisfies `test_every_audited_action_is_named_after_a_permission` exactly, with nothing to add to `MULTI_ACTION_PERMISSIONS` or `CASCADED_ACTIONS`.
> `listing.review` stays out for the reason `users.review` is out (`permissions.py:26–31`): auditing a list a tab polls writes one row per poll into a table whose triggers refuse DELETE and which has no retention path. `REAUTH` is untouched — publishing a listing is not in the class of revoke / role grant / token mint / licence decision.
> **`ADMINISTRATIVE` does not move**: it is derived from the matrix, `listing.publish` is already `_STAFF`, and `tests/auth/test_matrix.py`'s pinned 16-element set and `len == 16` stay true. No permission is added, so `npm run gen:permissions` is **not** run and `frontend/src/auth/permissions.ts` does not change.

> **D12 — the reviewer supplies `state` and `market` (John's ruled default Q2).** `listing.state` and `listing.market` were `NOT NULL` and the approved step 2 collects city and ZIP only; there is no field for either and inventing one is forbidden. `030`'s publishable CHECK is what makes this safe, and the Admin table has no field editor, so the reviewer is prompted for them **through the seam the Users tab already has** — `frontend/src/admin/users.ts`'s `needsNote(action)` — with no new markup. A proper admin field editor is Rev 3 (§14 item 6).

> **D13 — the slug is rewritten on the first publish** to `slugify(name) + "-" + str(id)[:8]`, so a seller's "ABC Animal Hospital" can never collide with the seed slug of the same name and can never make the next `seed_listings.py` run refuse (exit 5, its collision pre-flight). Only on the FIRST publish: a republished listing keeps the slug buyers may have bookmarked. `seed_listings.py` keys off `slug` and Task L6 keys off `id`, so nothing downstream cares either way.

- [ ] **Step 1: The failing transition tests** (append to `tests/api/test_seller_listings.py`)

Required names and assertions:

| Test | Asserts |
|---|---|
| `test_submit_moves_a_draft_into_review_and_stamps_it` | 200, `status='in_review'`, `submitted_at` set, one `listing.submit` audit row, one `listing_submitted` outbox row |
| `test_submit_re_validates_the_three_rules_the_design_enforces_client_side` | missing name/est → 422 `INCOMPLETE` naming the field; missing city/zip; missing price and no revenue and no range option — `logic.js:1215–1217`'s three, server-side |
| `test_submit_is_legal_from_draft_declined_and_in_review_and_from_nothing_else` | `paused`, `published`, `withdrawn` → `409 STATE` |
| `test_submit_is_idempotent_within_one_review_cycle` | a second submit does not re-stamp or write a second outbox row (the idempotency key is `{id}:listing_submitted:{submitted_at}`) |
| `test_pause_republish_and_withdraw_are_the_dashboards_own_three` | each moves the row, each writes its own audit action, `republish` needs no re-review (the design's footnote: unpublishing is "immediate and reversible") |
| `test_a_transition_from_an_illegal_state_is_409_and_changes_nothing` | pause from `draft`, republish from `published`, anything from `withdrawn` |
| `test_withdraw_is_terminal` | after withdraw, every seller route is `409 STATE` (and the row survives — "withdrawn listings keep their history for reporting") |
| `test_the_seller_transition_actions_name_no_permission_and_are_not_watched` | the four constants ∩ `PM.MATRIX` is empty; `("POST", "/api/seller/listings/{listing_id}/submit")` is **not** in the AUDITED-watched set; the route **is** in the `listing.manage_own`-guarded set — "not watched", not "not there", exactly as `test_the_applicant_facing_audit_actions_…` phrases it |
| `test_every_transition_drops_the_listings_cache_after_the_commit` | submit, pause, republish, withdraw |

- [ ] **Step 2: The failing admin tests** — create `tests/api/test_admin_listings.py`

| Test | Asserts |
|---|---|
| `test_the_queue_returns_every_listing_and_narrows_by_status` | `listing.review`; `?status=in_review`; a bad status is `422 BAD_FILTER` in the envelope, never `200 {"items": []}` |
| `test_the_queue_is_keyset_paged_and_walks_every_row_exactly_once` | `next_cursor` followed to null; a malformed cursor is `422 BAD_CURSOR` |
| `test_a_buyer_and_a_seller_cannot_read_the_queue` | 403 |
| `test_publish_needs_state_and_market_on_the_first_publish_and_not_after` | first publish without them → `422 FIELDS_REQUIRED` naming both; with them → 200, `status='published'`, `state`/`market` written, `area` untouched; a later republish needs neither |
| `test_publish_rewrites_the_slug_once_and_never_again` | `abc-animal-hospital-<8 hex>`; unpublish + publish keeps it |
| `test_decline_requires_a_reason` | blank → `422 NOTE_REQUIRED` (the `admin_users.py:109` pattern); with one → `status='declined'`, the reason on the audit row |
| `test_unpublish_moves_a_published_listing_to_paused` | and only from `published` |
| `test_every_decide_branch_writes_exactly_one_audit_row_named_after_the_permission` | three branches, `action == "listing.publish"` on each, `before`/`after` carrying `{status}` |
| `test_the_decide_handler_writes_its_own_audit_row` | `assert "audit.write(" in inspect.getsource(decide_listing)` — the drift test's own rule, asserted here so a refactor that moves it into a helper fails at the task that owns it |
| `test_publish_and_decline_enqueue_their_template_to_the_seller` | `listing_published` / `listing_declined`, `params={"reason": ...}`, one row each, the idempotency key including the decision |
| `test_a_decision_on_an_unowned_or_missing_listing_is_404` | staff see every listing, but a uuid that names none is `404 NOT_FOUND` |
| `test_every_decision_drops_the_listings_cache_after_the_commit` | all three branches |
| `test_the_matrix_and_route_guard_tests_still_pass_with_listing_publish_audited` | imports and runs nothing — it asserts `"listing.publish" in PM.AUDITED` and `PM.REAUTH` unchanged and `len(PM.ADMINISTRATIVE) == 16`, so the three pins that could have moved are named here too |

- [ ] **Step 3: `app/auth/permissions.py` — one name**

```python
AUDITED = frozenset({"users.view_detail", "users.decide", "users.revoke", "roles.grant", "tokens.manage", "licence.decide", "engine.activate", "abuse.investigate",
                     # Spec 2026-09-08 D8: publishing, declining or unpublishing a listing is a
                     # staff decision of exactly the class `users.decide` is, and the seller is
                     # entitled to "who changed what and when" (the design's admin footnote). The
                     # decide handler writes `action="listing.publish"` on every branch from its own
                     # body — `test_audited_permissions_are_written_by_their_handlers` reads the
                     # handler's source, so delegating would read as unaudited. `listing.review`
                     # stays OUT for the reason `users.review` is out (one row per poll of a tab),
                     # and `listing.manage_own` stays out because the wizard's autosave rides on it.
                     "listing.publish"})
```

- [ ] **Step 4: The three mail templates — BOTH registries**

`app/mail/outbox.py`'s `TEMPLATES` frozenset gains `"listing_submitted", "listing_published", "listing_declined"` (its docstring's count sentence updated to seventeen), **and** `app/mail/templates.py`'s `TEMPLATES` dict gains the three `Template(...)` entries. `enqueue` raises `KeyError` for a template that is not in the frozenset, and `tests/mail/test_templates.py` pins that every key renders and that no subject carries a placeholder — so a template added to one registry and not the other fails at the task that adds it. `EMAIL_ALLOWLIST` needs no change: `app/mail/tasks.py::allowlisted` is fail-closed outside production and already governs every template.

```python
    "listing_submitted": Template(
        subject="Your listing is with the VIN Foundation",
        text="Thank you — your listing has been submitted for review.\n\n"
             "A staff reviewer checks each listing before it goes live, usually within two business days. "
             "You can keep editing while it waits; edits after publication go through the same short review.",
        html=_p("Thank you — your listing has been submitted for review.")
             + _p("A staff reviewer checks each listing before it goes live, usually within two business days. "
                  "You can keep editing while it waits; edits after publication go through the same short review.", QUIET),
    ),
```

> **The copy is the approved design's own, verbatim** — the submitted card's subtitle and its paragraph (`App.vue:1256`, `:1259`). Nothing new is written: an email that promises something the screen does not is a second source of truth about the review.

`listing_published` and `listing_declined` follow, the second carrying `params=("reason",)` and rendering the reviewer's own note.

- [ ] **Step 5: Write the two handlers**

`POST /listings/{id}/submit` in `app/api/seller_listings.py`:

```python
SUBMIT_ACTION, PAUSE_ACTION, REPUBLISH_ACTION, WITHDRAW_ACTION = (
    "listing.submit", "listing.pause", "listing.republish", "listing.withdraw")
SUBMITTABLE_FROM = ("draft", "declined", "in_review")
# The dashboard's own three buttons (logic.js:958), each with the states the lifecycle table allows.
TRANSITIONS: dict[str, tuple[tuple[str, ...], str, str]] = {
    "pause":     (("published",), "paused", PAUSE_ACTION),
    # No re-review: the design's admin footnote calls unpublishing "immediate and reversible"
    # (logic.js:1061), and a pause the seller can undo is not a new listing.
    "republish": (("paused",), "published", REPUBLISH_ACTION),
    # Terminal, from anywhere but itself: "withdrawn listings keep their history for reporting but
    # no longer appear in search" (logic.js:1061).
    "withdraw":  (("draft", "in_review", "published", "paused", "declined"), "withdrawn", WITHDRAW_ACTION),
}
# The design's own client-side validation (logic.js:1215-1217), re-validated on the server because
# a client check is a courtesy and this one guards a CHECK constraint.
REQUIRED_TO_SUBMIT = (("name", "A practice name"), ("est", "A year established"),
                      ("city", "A city"), ("zip", "A ZIP code"), ("price", "An asking price"))
```

`POST /api/admin/listings/{id}/decide` in `app/api/admin_listings.py` — **the whole decision in one handler body**, `audit.write(` included, because the drift test reads `inspect.getsource(route.endpoint)`:

```python
router = APIRouter(prefix="/api/admin")

REQUIRE_LISTING_REVIEW = require("listing.review")
REQUIRE_LISTING_PUBLISH = require("listing.publish")
Publisher = Annotated[S.Principal, Depends(REQUIRE_LISTING_PUBLISH)]

MAX_LIST = 200
STATUSES = ("draft", "in_review", "published", "paused", "withdrawn", "declined")
# The three the design's own Listings tab offers (logic.js:1063-1067): Publish, Reject, Unpublish.
# Each names the states it is legal from, and the state it reaches.
DECISIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "publish": (("in_review", "declined", "paused"), "published"),
    "decline": (("in_review",), "declined"),
    "unpublish": (("published",), "paused"),
}
# `admin_users.py:109`'s pattern, one entry rather than four: a decline is a decision the seller is
# owed a reason for, and a blank one is a 422 rather than a row with an empty note.
NOTE_REQUIRED = ("decline",)
MAIL = {"publish": "listing_published", "decline": "listing_declined"}


class Decision(BaseModel):
    action: str = Field(max_length=32)
    reason: str = Field(default="", max_length=2_000)
    # D12: supplied by the reviewer at the FIRST publish, because the approved step 2 collects a
    # city and a ZIP and inventing a wizard field is forbidden.
    state: str = Field(default="", max_length=2)
    market: str = Field(default="", max_length=64)


def slug_for(name: str, listing_id: Any) -> str:
    """D13. The name in slug form plus the first eight characters of the id, so a seller's "ABC
    Animal Hospital" can never collide with the seed slug of the same name and can never make the
    next `seed_listings.py` run refuse (exit 5, its collision pre-flight)."""
    base = re.sub(r"[^a-z0-9]+", "-", (name or "listing").lower()).strip("-") or "listing"
    return f"{base[:80]}-{str(listing_id)[:8]}"


@router.post("/listings/{listing_id}/decide")
async def decide_listing(listing_id: str, body: Decision, request: Request, principal: Publisher) -> Response:
    """Publish, decline or unpublish (D12). Audited from THIS body on every branch — the drift test
    reads `inspect.getsource(route.endpoint)`, so delegating the write to a helper would read as
    unaudited (D8), and `action="listing.publish"` on all three branches is what satisfies
    `test_every_audited_action_is_named_after_a_permission` with nothing added to
    `MULTI_ACTION_PERMISSIONS`."""
    if body.action not in DECISIONS:
        return _error("BAD_REQUEST", f"action must be one of {', '.join(DECISIONS)}.", 400)
    if body.action in NOTE_REQUIRED and not body.reason.strip():
        return _error("NOTE_REQUIRED", "A reason is required to decline a listing.", 422)
    allowed_from, after = DECISIONS[body.action]
    try:
        parsed = UUID(listing_id)
    except ValueError:
        return _error("NOT_FOUND", "No such listing.", 404)
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, name, slug, state, market, seller_id FROM listing WHERE id=%s FOR UPDATE", (parsed,))
            row = cur.fetchone()
            if row is None:
                return _error("NOT_FOUND", "No such listing.", 404)
            before, name, slug, state, market, seller_id = row
            if before not in allowed_from:
                return _error("STATE", f"cannot {body.action} a listing in state {before}", 409)
            first_publish = body.action == "publish" and state is None
            if first_publish and not (body.state.strip() and body.market.strip()):
                # 020's publishable CHECK would refuse this anyway; answering it here means the
                # reviewer is told which two fields, in the envelope, instead of meeting a 500.
                return _error("FIELDS_REQUIRED", "state and market are required to publish this listing for the first time.", 422)
            sets = "status=%(status)s, updated_at=now()"
            params: dict[str, Any] = {"status": after, "id": parsed}
            if first_publish:
                sets += ", state=%(state)s, market=%(market)s, slug=%(slug)s"
                params |= {"state": body.state.strip(), "market": body.market.strip(), "slug": slug_for(name, parsed)}
            cur.execute(f"UPDATE listing SET {sets} WHERE id=%(id)s", params)
            cur.execute("SELECT email FROM account WHERE id=%s", (seller_id,))
            owner = cur.fetchone()
        template = MAIL.get(body.action)
        if template is not None and owner is not None:
            enqueue(conn, to=owner[0], template=template, params={"reason": body.reason},
                    idempotency_key=f"{parsed}:{template}:{before}->{after}")
        audit.write(conn, actor=principal, action="listing.publish", target_type="listing",
                    target_id=parsed, before={"status": before}, after={"status": after},
                    # Free text, and a staff member's own words — never a credential, the rule
                    # `admin_users.decide_route` records. `before`/`after` are redacted by
                    # `audit.write`; `reason` is not, so nothing but the decision and the note goes in.
                    reason=body.action if not body.reason.strip() else f"{body.action}: {body.reason}",
                    request=request)
    # AFTER the commit (D16): a publish must reach Browse at once and an unpublish must leave it at
    # once, and dropping the key while the write was uncommitted would re-cache the old payload.
    drop_list_cache(sync_redis())
    return JSONResponse({"id": str(parsed), "status": after})
```

and the mount, beside the others inside `if settings.site_mode == "app":`:

```python
        app.include_router(admin_listings_router)
```

- [ ] **Step 6: GREEN, gate, commit**

```bash
poetry run pytest tests/api tests/auth tests/mail -q
poetry run ruff check app tests scripts && poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
git add app/api/seller_listings.py app/api/admin_listings.py app/auth/permissions.py app/main.py \
        app/mail/templates.py app/mail/outbox.py tests/api/test_seller_listings.py tests/api/test_admin_listings.py tests/mail/test_templates.py
git commit -m "feat(api): submit, the seller's three transitions, and the VIN Foundation's review

Spec 2026-09-08 D2/D4/D8/D12/D13. listing.publish joins AUDITED and the decide handler
writes action=listing.publish on every branch from its own body; listing.review and
listing.manage_own stay out for the reasons users.review is out. The seller's own
transitions write listing.submit/pause/republish/withdraw, which name no permission by
design - exactly like applications.submit - and a test asserts that on purpose.

The reviewer supplies state and metro at the first publish (John's ruled default): the
approved step 2 collects a city and a ZIP and inventing a field is forbidden. The slug
is rewritten once on that first publish, so a seller listing can never collide with a
seed slug or make the next seeder run refuse.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

**Controller amendment A-SL19 (2026-09-09 ~08:40 WITA; rulings on the SL5 review — spec PASS with three gaps, NOT APPROVED: 3 Major, 6 Minor, 6 Info; closed in one fix round).** (1) **Major-1 — paused is published-but-hidden (D3).** Any wizard PATCH or asset write to a `paused` listing moves it to `in_review` and writes the `listing.edit` audit row exactly as an edit to a `published` one does; `resume` is legal only from an unedited `paused` state, otherwise `409 STATE`; tested (pause → edit → resume refused; the row is `in_review`). (2) **Major-2 — the reviewer's `state` and `market` are validated before any write**: `state` must be one of the USPS state codes (a module constant incl. DC), `market` must match `^[^,]{2,60}, [A-Z]{2}$` and its suffix must equal `state`; refusal is `422 BAD_FIELD` in the envelope; tested, including the "Phoenix, TX" case the review named. (3) **Major-3 — `listed_at` is stamped `now()` at FIRST publish only** (never on a re-publish after review); Browse sorts and pages on it, so an old draft published today lists today. Controller default on a point the spec is silent on — for John's vet. (4) **m1** — `409 STATE` is the transition-refusal code (the module's vocabulary); the dispatch's `INVALID_TRANSITION` is withdrawn. (5) **m2** — an unknown admin action is `422 BAD_ACTION` (as `/api/admin/users`). (6) **m3** — publish enqueues no `reason`; only `listing_declined` carries it. (7) **m4** — `GET /api/seller/listings` refuses a bad `limit`/`cursor` with `422 BAD_FILTER`/`BAD_CURSOR` like the admin routes. (8) **m5, m6** — record-only by ruling (uncoverable CHECK arm; a shared cursor helper when a fourth appears). (9) **Info-3** — `serialise_draft` carries `decline_reason` (the latest decline's reason, null otherwise) so SL7 can feed the design's per-listing `note`; **Info-4** — `/decide` returns the full `serialise_draft` of the decided listing (slug included). (10) **Concern 5 / Info-6** — one app-wide `RequestValidationError` handler renders Pydantic body errors in the A5 envelope as `422 BAD_BODY` (the `admin_users` decide route gains the same shape for free); `Decision` forbids unknown fields; tested on both routes. (11) Concerns 2, 3, 6, 7 ratified; Info-1, 2, 5 accepted as recorded (no new mail without John's copy approval).

**Controller amendment A-SL19 — addendum (2026-09-09 ~08:30).** Point (10) is satisfied by the EXISTING app-wide `RequestValidationError` handler (`app/auth/deps.py`, Task I4) whose envelope code is `INVALID_REQUEST`; the ruling's `BAD_BODY` rename is withdrawn (it would have changed sign-up, sign-in, applications and the webhook). `Decision` forbids unknown fields and both `/decide` routes are pinned to the envelope. `decline_reason` is "the latest decline" and survives a later publish — SL7 renders it under the Declined pill only. `listed_at` at first publish only (a republish keeps its original date) remains the controller's default for John's vet.

**Controller amendment A-SL20 (2026-09-09 ~08:10 WITA; John's ruling, verbatim: "if the logic is trying to match and failing then surface all images uploaded and have the user articulate what it is and render ALL images").** No photo cap anywhere: spec D18's four-photo cap is withdrawn, and D-L9 is closed by this ruling. Every uploaded photograph renders — positions 1–6 are the design's slots, positions 7+ render as extra tiles (design amendment A15, main hotfix A-L11) — and each photograph carries its OWN caption: `listing_asset` gains a seller-editable `caption` (the seller "articulates what it is" in the wizard's photo step), served alongside the URL exactly as the seed's `photo_captions` are (A-L11), with the design's fixed slot caption only as the fallback for an empty slot. Wizard tile names never come from filenames. SL6 carries the seeded photographs' captions through; SL7 adds caption editing and unlimited photos; SL4's cap constant and its tests move with this ruling.

### Task SL6: the eighteen become the seller persona's — **1 day**

**Files:**
- Modify: `scripts/seed_listings.py`
- Modify: `seeds/hospitals.json` (two keys per row — see below)
- Modify: `tests/scripts/test_seed_listings.py`, `tests/seeds/test_hospitals_json.py`
- Modify: `DEPLOY.md` (§"Seeding the demo hospitals (QA)" — the ownership line and the order)

**Interfaces:** `SEED_OWNER_EMAIL`, `--owner <email>`, `--no-owner`, `resolve_owner(conn, email) -> UUID | None`; `seed(dsn, *, reset=False, owner=...)`. **The exit codes do not change** — `tests/test_docs.py::test_deploy_md_exit_codes_match_seed_listings_returns` derives them from the `return N` statements and requires DEPLOY.md to list exactly `0, 2, 3, 4, 5`, so an absent persona must be a printed note, not a sixth code.

- [ ] **Step 1: Failing tests** (`tests/scripts/test_seed_listings.py`)

| Test | Asserts |
|---|---|
| `test_ownership_is_assigned_to_the_seller_persona_by_default` | with `seller@practice-match.test` present, all eighteen carry its `account.id` |
| `test_ownership_is_re_asserted_on_a_re_seed` | a hand-nulled `seller_id` comes back — `seller_id` is in the `DO UPDATE SET`, not only the insert list |
| `test_ownership_is_left_null_and_said_so_when_the_account_is_absent` | no persona → every `seller_id` NULL, exit 0, and stdout carries the line naming the address (production has no persona accounts and must still be seedable) |
| `test_the_default_owner_is_never_applied_on_a_production_run` | `ENVIRONMENT=production --production` → NULL unless `--owner` is passed explicitly; with `--owner` it is applied |
| `test_no_owner_seeds_unowned_even_when_the_persona_exists` | the `--no-owner` escape hatch |
| `test_a_sellers_own_listing_is_still_never_touched` | a planted `source='seller'` row survives both a plain import and `--reset`, `seller_id` intact |
| `test_the_disclosure_backfill_holds_for_a_freshly_seeded_row` | every seeded row has all four flags true — D22, now from the JSON rather than from `030`'s one-off backfill |

- [ ] **Step 2: The seeder**

```python
# D25, John's ruling: "Assign all eighteen QA seed listings to `seller@practice-match.test`, with
# real `seller_id` ownership." The persona `scripts/seed_persona.py` creates with roles buyer+seller
# (its ORACLE_PERSONAS loop), and which QA already has.
SEED_OWNER_EMAIL = "seller@practice-match.test"


def resolve_owner(conn: Any, email: str | None) -> UUID | None:
    """The account id to own these rows, or None.

    **Absent is not a refusal.** Production has no persona accounts — `PERSONA_PASSWORD` is never
    set there and `seed_persona.py` refuses production outright (A-S6.1/A-S6.2) — and production
    must still be seedable. So a missing account leaves `seller_id` NULL and the run SAYS SO on
    stdout, which is a line an operator can act on rather than an exit code that stops a deploy."""
    if email is None:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM account WHERE email = %s", (email,))
        found = cur.fetchone()
    if found is None:
        print(f"[seed] {email} does not exist here — seeding the listings unowned (seller_id NULL)")
        return None
    return cast("UUID", found[0])
```

`seller_id` joins the UPSERT's insert list **and** its `DO UPDATE SET` (`seller_id = EXCLUDED.seller_id`), so a re-seed re-asserts ownership; the existing `WHERE listing.source = 'seed'` scope means a real seller's row is still never touched, and the collision pre-flight still refuses the whole import if another source owns a seed slug.

In `main()`, after the production announcement:

```python
    # A demo persona must never own a production row. On a --production run the default is not
    # applied AT ALL unless --owner names an address explicitly (D25).
    if args.no_owner:
        owner_email = None
    elif args.owner:
        owner_email = args.owner
    elif environment.lower() == "production":
        owner_email = None
        print("[seed] production: no default owner (pass --owner to assign one)")
    else:
        owner_email = SEED_OWNER_EMAIL
```

- [ ] **Step 3: `seeds/hospitals.json` — two keys per row (D22)**

Every one of the eighteen gains `"rev_disclosed": true` and `"documents_disclosed": true`, beside the `"name_disclosed": true` A-L5 added, and `row_params`'s `keys` tuple and the JSON schema test in `tests/seeds/test_hospitals_json.py` require them. Migration `030`'s backfill covers the rows already in a database; **this** is what keeps a freshly seeded row right, and the two must not disagree.

- [ ] **Step 4: The wizard reads a seed hospital's photographs by caption (D26)**

`serialise_draft`'s `assets` for a `source='seed'` row are not `listing_asset` rows — those hospitals' photographs stay in `seeds/` and are served from disk (D26: object storage holds only what sellers upload). `assets_of` therefore gains a seed arm: when `listing_asset` is empty and `listing.photos` holds `<slug>/<n>.webp` paths, build the list from `seeds/hospitals/photos/index.json`, taking each entry's **caption** ("Exterior — front view") as the tile name rather than the filename `1.webp`. That is what makes Edit on a seeded hospital read the way John expects, and it is the one place the two storage stories meet.

- [ ] **Step 5: DEPLOY.md**

`test_deploy_md_documents_how_to_seed_qa` pins nine literal substrings **and the ordering of the two commands** (plain before `--reset`). Add the ownership line without disturbing either:

```markdown
Run `scripts/seed_persona.py` **first**: the eighteen are assigned to
`seller@practice-match.test` at seed time (spec 2026-09-08 D25), and if that account does not
exist yet the import still succeeds with `seller_id` NULL and says so on stdout. `--owner <email>`
overrides the default and `--no-owner` seeds unowned; on production the default is not applied at
all unless `--owner` is passed.
```

- [ ] **Step 6: GREEN, gate, commit**

```bash
poetry run pytest tests/scripts/test_seed_listings.py tests/seeds tests/test_docs.py -q
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
git add scripts/seed_listings.py seeds/hospitals.json tests/scripts/test_seed_listings.py tests/seeds/test_hospitals_json.py app/api/seller_listings.py DEPLOY.md
git commit -m "feat(seed): the eighteen demo hospitals belong to seller@practice-match.test

Spec 2026-09-08 D25/D26, John's ruling. Ownership lives in the seeder, in the UPSERT's
insert list AND its DO UPDATE SET, so a re-seed re-asserts it; --owner overrides,
--no-owner seeds unowned, an absent account leaves seller_id NULL and says so (production
has no persona accounts and must still be seedable), and a demo persona is never the
default on production. The seed photographs stay in seeds/ and are served from disk;
the wizard's step-6 tile shows the inventory's caption, which is what makes Edit on a
seeded hospital read the way John expects.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

**Controller amendment A-SL17 (2026-09-09; John's ruling ~05:00 WITA, verbatim intent) — UNBLOCKS Task SL7.** "Seller dashboard: EMPTY DASHBOARD. A real seller with zero listings should see the dashboard shell with no invented/sample listings. Add the empty-dashboard state to the approved visual/DOM oracle. Do not retain the four Austin fixture rows for a real zero-listing seller." Pre-flight for SL7: the design's `seller-dash` renders `sellerListings` (four Austin fixture rows) — the app must feed the seller's REAL listings (SL2's draft read) and an empty array for a zero-listing seller; the oracle gains a 46th state `seller-dash-empty` reached through the reference's `?props=` mechanism (a declared prototype prop or an existing one that empties the table — check whether the design already has an empty-table treatment; if the design renders nothing but the shell, that IS the state; no invented empty-state copy).

**Controller amendment A-SL21 (2026-09-09 ~09:15 WITA; ruling on SL6's NEEDS_CONTEXT — a data-ownership default for John's vet).** A seeded listing becomes the seller's own the moment the seller writes to it: the first seller write of any kind (a wizard PATCH, an asset upload/reorder/delete, a transition) flips `listing.source` from `'seed'` to `'seller'` in the same transaction, so the seeder's existing `WHERE source = 'seed'` scope never overwrites a seller-edited row, `status` can never be reset to `published` without review, and `--reset` never deletes it (nor cascades its assets). Untouched seeds remain refreshable. The seeder prints how many rows it skipped as seller-owned; `DEPLOY.md`'s seeding section and the runbook say so; tested (edit → re-seed leaves the row; untouched sibling refreshed; `--reset` keeps the edited row and its assets).

**Controller amendment A-SL22 (2026-09-09 ~09:35 WITA; SL7 pre-flight rulings — they override the brief's literals where the two differ).** (1) **Empty dashboard (A-SL17):** with the `listings` adapter present the dashboard renders the loaded array even when empty — `(s.myListings !== undefined ? s.myListings : s.sellerListings)`; the design's four fixtures show only with no adapter (the reference, the preview). A new declared prototype prop `startMyListings` (default undefined; injected per request from `?props=`, the `startNotice` mechanism) reaches the appended oracle state `seller-dash-empty`: the design's own markup with zero rows, no invented copy; the app never passes the prop. (2) **Photographs (A-SL20 + main's A15):** the wizard's photo step is uncapped; every uploaded photograph is listed from the draft; the seller writes a caption per photograph (`listing_asset.caption`, `PATCH …/assets/{assetId} {caption}`, served in `serialise_draft` and as `photo_captions` for published listings); tile names are the seller's captions, falling back to the design's slot name by position, never a filename. (3) **Dashboard `note` (A-SL19 + A-SL2):** `decline_reason` under the Declined pill only; otherwise column-derived prose; never invented counts. (4) Preview and Submit read the hydrated draft; the em dash only for a genuinely empty field. (5) API refusals render through the design's existing error surfaces; no invented banners. (6) The oracle's `baseline-manifest.json` moves only for the appended state. (7) Merge `main` first (A15, `photo_captions`, migration 024, template DB); the seller adapter family takes the next free id (A16).

### Task SL7: the wizard and the dashboard read and write the real API — **3 days**

**Files:**
- Create: `frontend/src/listings/seller.ts`, `frontend/src/listings/seller.test.ts`
- Modify: `frontend/tests/design-amendments.ts` (the new family), `frontend/tests/design-amendments.test.ts` (the id list and the two counts), `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md` (one row per amendment)
- Modify: `frontend/src/app.setup.js` (the `listings` prop), then **regenerate** `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html`, `frontend/src/logic.js`, `frontend/src/App.vue`, `frontend/src/generated/pseudo.css`
- Modify: `frontend/tests/harness.ts`, `frontend/tests/harness.test.ts` (the two empty-collection stubs — A-SL2)
- Modify: `CLAUDE.md` (the family/entry counts — `tests/test_docs.py` derives and pins them)

**Interfaces:** `makeListingsAdapter(api)` exporting `list()`, `create()`, `get(id)`, `patch(id, step, fields)`, `upload(id, file)`, `document(id, file, kind)`, `remove(id, assetId)`, `reorder(id, ids)`, `submit(id)`, `setStatus(id, action)`, plus `toDashboardRow(draft)` and `toWizardState(draft)` — the two pure mappings the amendments consume and the unit tests pin.

> **`logic.js`, `App.vue`, `app.setup.js` and `pseudo.css` are GENERATED (Global Constraint (l)).** Nothing in this task edits any of the four by hand. The change lands as amendment literals against the pristine bundle, then `npm run gen:design && npm run gen:app`. `frontend/tests/app-generated.test.ts` pins `logic.js` byte-for-byte against the amended design's `<script data-dc-script>` block; a hand edit fails it at the next run, which is the point.

> **The precedent is exact.** **A5** wired sign-in and sign-out through the `auth` adapter and put the account-on-load bootstrap into `componentDidMount`; **A12** made `practiceName` / `photoSet` / `heroSrc` / `thumbSrc` read a listing's own `name` and `photos`. Same shape of change, same functions' neighbourhood, same rule: **every edit keeps the design's own path when no adapter is passed** (A5.1's rule), which is what keeps the reference target on its pixels.

> **The adapter prop needs NO `data-props` entry.** The prop-parity gate is one-directional — `app-generated.test.ts` requires the setup to declare every prop the *design* declares, not the reverse — which is why `auth` never needed one either. So the pinned `data-props` key order (`$preview, prototypeBar, startScreen, startViewport, startGate, me, startNotice, startAnswerNote, layerPalette`) does not move, and **CLAUDE.md's "All seven prototype props stay declared" sentence stays true and unedited** (`tests/test_docs.py::test_claude_md_counts_the_seven_prototype_props_and_says_which_are_read`).

- [ ] **Step 0: Derive the family id and both counts from the tree (A-SL4). Do not type them from this plan.**

```bash
cd frontend
# The next free family integer. main is at A12; feat/design-dropdowns adds A13 (5 entries, count 87).
grep -o "id: 'A[0-9]*" tests/design-amendments.ts | sed "s/id: 'A//" | sort -n | uniq | tail -1
# The count this branch must pin AFTER the family is added:
grep -c "id: 'A[0-9]" tests/design-amendments.ts          # literal amendments today
grep -n "toHaveLength(" tests/design-amendments.test.ts | head -3   # today's pinned total
grep -c '^| A' ../docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md
```

This plan writes the family as **`A15`** — what it will be if `feat/design-dropdowns` lands `A13` and one more family lands `A14`. If the number the commands above return is different, renumber the plan's literals in one pass before writing any of them:

```bash
sed -i '' 's/A15\./A<N>./g' <your scratch copy of the literals>
```

and carry the same `<N>` through `AMENDMENT_IDS`, `LOCAL_AMENDMENTS.md` and the commit message. **Every numeric pin below is `<derived>`, never a literal from this document.**

- [ ] **Step 1: Write the failing adapter tests** — `frontend/src/listings/seller.test.ts`

Required names: `list() maps a draft to the design's own dashboard row shape`, `list() returns [] rather than throwing on a refusal`, `create() returns the new id`, `get() maps a draft to state.w's own key names`, `patch() sends only the step's fields and the step in the query`, `patch() surfaces the server's own message`, `upload() posts multipart with the CSRF header`, `document() defaults kind to other`, `remove()`, `reorder() sends the full ordered list`, `submit()`, `setStatus() sends the three actions and refuses a fourth`, `every method sends X-CSRF-Token on a state change and none on a read`, `a non-A5 body still becomes an Error with a message`. Coverage is 100/100/100/100 (`frontend/vite.config.ts`), so **every failure path needs its own test** — the module has no arm a test does not take.

The two pure mappings, pinned against the design's own values:

```ts
it("toDashboardRow renders the design's own three strings", () => {
  // The design's row is `{ title, meta, note, status }` (logic.js:206-211) and `sellerVals()`
  // reads exactly those four. `money()` is the design's own (logic.js:250) — "$1.45M", not
  // "$1,450,000" — so the mapping reproduces the fixture's spelling rather than inventing one.
  expect(toDashboardRow({
    id: 'a3f1…', status: 'published', name: 'Cedar Park Animal Hospital', city: 'Cedar Park',
    type: 'Small animal', price: 1_450_000, docs: 3, sqft: 4200, submitted_at: null, updated_at: '2026-09-08T10:00:00Z'
  })).toEqual({
    id: 'a3f1…', status: 'published',
    title: 'Small animal practice — Cedar Park',
    meta: '$1.45M · 3 doctors · 4,200 sq ft',
    note: 'Live · visible in search'
  });
});
```

> **The `note` column is the one thing the API cannot reproduce (A-SL2).** The design's four fixtures carry prose no column supplies — *"Live since August 24 · 34 views, 2 requests"* needs a view count and a request count that do not exist in this slice. The mapping writes the **shortest honest** version of each state's note ("Live · visible in search", "Submitted · awaiting VIN Foundation review", "Draft", "Paused by you · hidden from search", "Declined · edit and re-submit", "Withdrawn"), and the harness stub keeps the design's own four rows on the oracle so `seller-dash` does not move. Absent beats faked: no view count is invented.

- [ ] **Step 2: Write `frontend/src/listings/seller.ts`**

Following `frontend/src/auth/api.ts`'s conventions exactly — `fetch` with `credentials: 'same-origin'`, `X-CSRF-Token: csrfToken()` on every non-GET, `Content-Type: application/json` only when a JSON body exists (**never** on a multipart POST, where the browser must set the boundary), and a refusal unwrapped from `{"error": {"code", "message"}}` with the `'UNKNOWN'` / `` `HTTP ${res.status}` `` fallbacks.

- [ ] **Step 3: Write the amendment family** — `frontend/tests/design-amendments.ts`, after `A12_11`

```ts
// ---------------------------------------------------------------------------------------
// A15 — the seller wizard and dashboard read and write the real API (spec 2026-09-08 D23).
//
// The precedent is A5 (sign-in through the `auth` adapter) and A12 (the design reads a listing's
// own name and photographs): literal script edits, each of which KEEPS THE DESIGN'S OWN PATH when
// no adapter is passed. The reference and the Claude Design preview pass no `listings` prop and
// take the fixture path unchanged, which is what keeps both targets on the same pixels.
//
// None of these is markup. Step 6's controls, the four disclosure switches, a revenue range on
// the buyer detail, the document rows and an admin field editor are all Rev 3 (spec §14) — the
// approved design has no slot for any of them and inventing one is forbidden.
// ---------------------------------------------------------------------------------------
const SL = {
  date: '2026-09-08',
  ruling: 'none of the existing Photes and Documents are being render4ed in the "EDIT" of an existing listing by hospital across all the data seeded on and also none of the actual inputs are appearing in the PREVIEW and SUBMIT, it appears to be stubs and not functional, this gap must be corrected and the UX true'
};
```

> **The ruling string is John's own words, typo included.** `design-amendments.test.ts` compares each `LOCAL_AMENDMENTS.md` row's third column against the amendment's `ruling` **byte for byte**, and `feat/design-dropdowns`'s A13 already carries John's "acutal" verbatim for the same reason. Do not correct it.

```ts
/** A15.1 — the dashboard's rows come from the loaded listings, the design's four as the fallback
 *  (A12's `NAMES[p.id]` pattern, and A-L6.2 (1)'s rule: an empty or malformed answer never
 *  installs). `s.myListings` is written by A15.9's bootstrap and by A15.7's submit; it is absent
 *  until then, so the reference — which never loads any — renders the design's own four. */
const A15_1: Amendment = {
  id: 'A15.1', ...SL,
  find: '      listings: s.sellerListings.map((l) => {',
  replace: '      listings: (s.myListings && s.myListings.length ? s.myListings : s.sellerListings).map((l) => {',
  count: 1
};

/** A15.2 — Continue and Edit hydrate `w` from the fetched draft and record which listing is being
 *  edited. John's finding, exactly: both handlers were `setState({ sellerView: "wizard", step: 1 })`
 *  and nothing else, so `w` stayed at its empty initial value and every `w.x || "—"` in
 *  `previewRows` rendered an em dash. With no adapter the design's own path runs unchanged, which
 *  is why `wizard-step-1`'s baseline does not move. */
const A15_2: Amendment = {
  id: 'A15.2', ...SL,
  find: '        if (l.status === "draft") actions.push({ label: "Continue", go: () => this.setState({ sellerView: "wizard", step: 1 }) });\n'
    + '        else actions.push({ label: "Edit", go: () => this.setState({ sellerView: "wizard", step: 1 }) });',
  replace: '        const openWizard = () => {\n'
    + '          if (!this.props.listings) return this.setState({ sellerView: "wizard", step: 1 });\n'
    + '          return this.props.listings.get(l.id).then(\n'
    + '            (d) => this.setState((st) => ({ sellerView: "wizard", step: 1, wizErr: "", wizSubmitted: false, editingId: l.id, wizAssets: d.assets, w: Object.assign({}, st.w, d.w) })),\n'
    + '            (e) => this.setState({ sellerView: "wizard", step: 1, wizErr: (e && e.message) || "That listing could not be opened." })\n'
    + '          );\n'
    + '        };\n'
    + '        if (l.status === "draft") actions.push({ label: "Continue", go: openWizard });\n'
    + '        else actions.push({ label: "Edit", go: openWizard });',
  count: 1
};

/** A15.3 — View opens the listing the row is about. The design hard-coded `"p1"` because its four
 *  rows are fixtures with no listing behind them; a real row has an id. */
const A15_3: Amendment = {
  id: 'A15.3', ...SL,
  find: 'actions.push({ label: "View", go: () => this.setState({ screen: "detail", detailId: "p1" }) });',
  replace: 'actions.push({ label: "View", go: () => this.setState({ screen: "detail", detailId: l.id || "p1" }) });',
  count: 1
};

/** A15.4 — step 6's tiles are the listing's real assets; the design's four-item literal is the
 *  no-adapter fallback. `s.wizAssets` is set by A15.2's hydration and by an upload. The `.slice`
 *  stays on the FALLBACK only: a real listing's four photographs must not be truncated to three by
 *  the counter the design used to fake progress with. */
const A15_4: Amendment = {
  id: 'A15.4', ...SL,
  find: '    const uploads = [{ kind: "Photo", name: "Exterior.jpg" }, { kind: "Photo", name: "Lobby.jpg" }, { kind: "Photo", name: "Treatment.jpg" }, { kind: "PDF", name: "Floor plan.pdf" }].slice(0, 3 + (w.photos || 0));',
  replace: '    const uploads = s.wizAssets ? s.wizAssets : [{ kind: "Photo", name: "Exterior.jpg" }, { kind: "Photo", name: "Lobby.jpg" }, { kind: "Photo", name: "Treatment.jpg" }, { kind: "PDF", name: "Floor plan.pdf" }].slice(0, 3 + (w.photos || 0));',
  count: 1
};

/** A15.5 — "Add files" opens a real file picker. With no adapter the design's counter runs
 *  unchanged, so the reference's step 6 is byte-identical (it has no baseline either way — spec
 *  §14 item 7 asks Rev 3 for one). A refusal lands in `wizErr`, the design's own single error slot
 *  (logic.js:1197, App.vue:1216-1218) — the fifth photograph's `409 PHOTO_LIMIT` included. */
const A15_5: Amendment = {
  id: 'A15.5', ...SL,
  find: '      addPhoto: () => this.setState((st) => ({ w: Object.assign({}, st.w, { photos: Math.min((st.w.photos || 0) + 1, 1) }) })),',
  replace: '      addPhoto: () => {\n'
    + '        if (!this.props.listings || !s.editingId) return this.setState((st) => ({ w: Object.assign({}, st.w, { photos: Math.min((st.w.photos || 0) + 1, 1) }) }));\n'
    + '        return this.props.listings.pick().then((file) => (file ? this.props.listings.upload(s.editingId, file).then(\n'
    + '          () => this.props.listings.get(s.editingId).then((d) => this.setState({ wizAssets: d.assets, wizErr: "" })),\n'
    + '          (e) => this.setState({ wizErr: (e && e.message) || "That file could not be uploaded." })\n'
    + '        ) : null));\n'
    + '      },',
  count: 1
};

/** A15.6 — Continue saves the step. The design's own three validations are untouched and run
 *  FIRST (they must refuse before spending a request against a rate-limited endpoint, which is
 *  A5.1's rule for the sign-in form); only the advance is wrapped. A refusal lands in `wizErr` and
 *  the step does NOT advance, so the seller never walks past a field the server rejected. */
const A15_6: Amendment = {
  id: 'A15.6', ...SL,
  find: '        this.setState({ step: Math.min(8, step + 1), wizErr: "" });',
  replace: '        if (!this.props.listings || !s.editingId) return this.setState({ step: Math.min(8, step + 1), wizErr: "" });\n'
    + '        return this.props.listings.patch(s.editingId, step, w).then(\n'
    + '          (d) => this.setState({ step: Math.min(8, step + 1), wizErr: "", wizAssets: d.assets }),\n'
    + '          (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." })\n'
    + '        );',
  count: 1
};

/** A15.7 — Submit posts, then runs the design's own `setState` unchanged. The prepended row is the
 *  design's optimistic one; the reload that follows replaces it with the server's, so the
 *  "Submitted" card the design draws appears at once and the dashboard behind it is true. */
const A15_7: Amendment = {
  id: 'A15.7', ...SL,
  find: '      submit: () => this.setState({ wizSubmitted: true,',
  replace: '      submit: () => (this.props.listings && s.editingId\n'
    + '        ? this.props.listings.submit(s.editingId).then(() => this.props.listings.list().then((rows) => this.setState({ myListings: rows })), (e) => this.setState({ wizErr: (e && e.message) || "That could not be submitted." }))\n'
    + '        : Promise.resolve()) && this.setState({ wizSubmitted: true,',
  count: 1
};

/** A15.8 — Pause, Republish and Withdraw go through the adapter, then reload. The design's own
 *  optimistic `setState` is kept as the no-adapter path and as the immediate feedback. */
const A15_8: Amendment = {
  id: 'A15.8', ...SL,
  find: '  setListingStatus(id, status) {\n',
  replace: '  setListingStatus(id, status) {\n'
    + '    if (this.props.listings) {\n'
    + '      const action = status === "paused" ? "pause" : status === "withdrawn" ? "withdraw" : "republish";\n'
    + '      this.props.listings.setStatus(id, action).then(\n'
    + '        () => this.props.listings.list().then((rows) => this.setState({ myListings: rows })),\n'
    + '        (e) => this.setState({ wizErr: (e && e.message) || "That could not be changed." })\n'
    + '      );\n'
    + '    }\n',
  count: 1
};

/** A15.9 — the bootstrap loads the seller's own listings, in A5.4's own five-line shape and at the
 *  same seam. Gated on the account actually holding the seller role, so a buyer's session spends no
 *  request on an endpoint it would be refused from. */
const A15_9: Amendment = {
  id: 'A15.9', ...SL,
  find: '    else if (this.state.gate === "verify" && this.props.auth) this.props.auth.verify(this.state.gateToken).then(() => this.setState({ gate: "signin", gateToken: "", formNotice: "Your address is verified. Sign in to complete your access request." }), () => this.setState({ gate: "verify-expired", gateToken: "" }));\n  }',
  replace: '    else if (this.state.gate === "verify" && this.props.auth) this.props.auth.verify(this.state.gateToken).then(() => this.setState({ gate: "signin", gateToken: "", formNotice: "Your address is verified. Sign in to complete your access request." }), () => this.setState({ gate: "verify-expired", gateToken: "" }));\n'
    + '    if (this.props.listings && me && me.state === "active" && (me.roles || []).indexOf("seller") > -1) this.props.listings.list().then((rows) => this.setState({ myListings: rows }), () => {});\n'
    + '  }',
  count: 1
};

/** A15.10 — the `declined` pill (John's ruled default, spec §16 Q1: the label "Declined" in the
 *  `bad` tone). Without it a declined row falls through `map[status] || map.draft` and reads
 *  "Draft" — a seller told their listing is a draft when the VIN Foundation has declined it.
 *  The three colours are `withdrawn`'s own triple, which IS the `bad` tone in `adminVals`'s table
 *  (`bad: ["#494949", "#ffffff", "#494949"]`), so no colour is invented. Pixel-safe: no approved
 *  state has a declined listing — the design's four fixtures are published, in_review, draft and
 *  paused. */
const A15_10: Amendment = {
  id: 'A15.10', ...SL,
  find: '      withdrawn: ["Withdrawn", "#494949", "#ffffff", "#494949"]\n    };',
  replace: '      withdrawn: ["Withdrawn", "#494949", "#ffffff", "#494949"],\n'
    + '      declined: ["Declined", "#494949", "#ffffff", "#494949"]\n    };',
  count: 1
};
```

and both ends of the list:

```ts
export function amendments(): Amendment[] {
  return [... , A12_10, A12_11,
    A15_1, A15_2, A15_3, A15_4, A15_5, A15_6, A15_7, A15_8, A15_9, A15_10];
}
```

- [ ] **Step 4: `frontend/src/app.setup.js` — the prop, exactly as `auth` is passed**

```js
  // A15: the real /api/seller client, as the prototype's `listings` adapter — the seam the design's
  // own Continue, Edit, Add files, Continue-to-next-step, Submit and Pause/Republish/Withdraw
  // handlers call through. The reference and the Claude Design preview pass nothing and keep the
  // design's fixture path, which is what keeps the two targets on the same pixels. Nothing in the
  // template reads `listings`; only `logic.js` does.
  //
  // `src/listings/seller.ts`, not an object literal here, for the reason `auth` records: this file
  // is copied verbatim into App.vue and sits outside the coverage gate, so the logic lives in a
  // module with unit tests. It needs no `data-props` entry — the parity gate is one-directional.
  listings: { type: Object, default: () => makeListingsAdapter() },
```

- [ ] **Step 5: Regenerate, and read the diff before running anything**

```bash
cd frontend
npm run gen:design && npm run gen:app
git diff --stat ../docs/design-reference/design_handoff_practice_match_v3/'Practice Match V3.dc.html' src/logic.js src/App.vue src/generated/pseudo.css
```
Expected: the `.dc.html` and `logic.js` change; **`App.vue` changes only in its `<script setup>` block** (the setup file is pasted in verbatim) and `pseudo.css` **does not change at all**. A template diff means an amendment touched markup, which none of these does — **STOP and diff**.

- [ ] **Step 6: The oracle stubs (A-SL2)** — `frontend/tests/harness.ts`, in `prepare()` beside the D6 listings stub

```ts
  // ---------------------------------------------------------------------------------------
  // A-SL2 — the seller and admin COLLECTIONS answer an empty page on the oracle.
  //
  // `seller-dash` and `admin-listings` are two of the thirteen frozen screens, and their rows are
  // the design's own fixtures: four Austin listings whose notes carry a view count and a request
  // count no column supplies, and a fifth admin row whose "Flagged" pill names a status
  // `listing.status` does not have and which D24 refuses to invent. An empty page is therefore the
  // honest stub: amendments A15.1 and A16.1 keep the design's literal rows whenever `items` is not
  // a non-empty array — controller amendment A-L6.2 (1)'s ruled shape, applied unchanged — so the
  // oracle's data stays the design's own and neither hash moves.
  //
  // The API path is proved elsewhere: pytest for the endpoints, vitest for the two mappings, and
  // `listing-flows.spec.ts` against the real, seeded API with NO stub armed.
  //
  // NEVER against a remote target, for the same reason the listings stub is not.
  // ---------------------------------------------------------------------------------------
  const collections = emptyCollectionStubUrls();
  for (const href of collections) {
    await page.route((url) => url.href === href || url.href.startsWith(`${href}?`),
      (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{"items": [], "next_cursor": null}' }));
  }
```

```ts
/** The two collection endpoints the oracle answers empty, or `[]` on a remote target (A-SL2). */
export function emptyCollectionStubUrls(env: NodeJS.ProcessEnv = process.env): string[] {
  if (env.PW_APP_URL) return [];
  return ['/api/seller/listings', '/api/admin/listings'].map((path) => new URL(path, appOrigin(env)).href);
}
```

with `harness.test.ts` pinning both arms (armed locally, empty when `PW_APP_URL` is set) exactly as it pins `listingsStubUrl` — review I4's rule: an untested `if` is all that stands between a stub and a QA parity run.

- [ ] **Step 7: Update the pins that are DERIVED from the tree**

```bash
cd frontend
# design-amendments.test.ts: add the ten ids to AMENDMENT_IDS and set toHaveLength to the count
node -e "import('./tests/design-amendments.ts').then(m=>console.log(m.amendments().length))"
# LOCAL_AMENDMENTS.md: one row per amendment, ruling column byte-identical to `SL.ruling`
grep -c '^| A' ../docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md
# CLAUDE.md: `tests/test_docs.py` derives "N families, M entries" and "A1's 24 derived edits plus L literals"
cd .. && poetry run pytest tests/test_docs.py -k amendment -q
```

Update **CLAUDE.md**'s design-reference paragraph with the derived numbers and one sentence naming the family, in the shape the existing families are named. Do not guess: the test prints the numbers it expects.

- [ ] **Step 8: The full frontend gate, and the oracles**

```bash
cd frontend
npm run typecheck && npx vitest run --coverage && npm run build
npm run test:visual:baselines && npm run test:e2e
cd .. && git diff --stat frontend/tests/baseline-manifest.json
```
Expected: 100 % on all four metrics; the 43 approved states green at `maxDiffPixels: 0`; the DOM oracle green; **`baseline-manifest.json` diff empty**. A moved hash is this task leaking into the design's pixels — **stop and diff**, never rebaseline.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/listings/seller.ts frontend/src/listings/seller.test.ts frontend/src/app.setup.js frontend/src/App.vue frontend/src/logic.js \
        frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts frontend/tests/harness.ts frontend/tests/harness.test.ts \
        "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
        docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md CLAUDE.md
git commit -m "feat(frontend): the wizard reads the draft, writes each step and submits for real

Spec 2026-09-08 D23, John's finding. Ten ruled D15 amendments in A5's and A12's own
shape: Continue and Edit hydrate w from the fetched draft, step 6 lists the listing's
real assets, Add files opens a picker, Continue PATCHes the step, Submit posts, the
dashboard's three buttons transition, the bootstrap loads the seller's own listings and
statusPill finally has a Declined entry. Every edit keeps the design's own path when no
adapter is passed, so the reference is unmoved and all 43 approved states hold at zero
pixels. The design's fixtures stay the oracle's data (D6): the two collection endpoints
answer an empty page and the fallbacks render the design's own rows (A-SL2).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

**Controller amendment A-SL23 (2026-09-09 ~11:10 WITA; rulings on the SL7 review — spec PARTIAL 16/20, NOT APPROVED: 2 Critical, 4 Major, 8 Minor, 6 Info; closed in one fix round that FIRST merges `main` 0.1.7).** (0) **Merge `main` first** (A15 photo own-caption tiles, `photo_captions` + migration `090`, Census Phase A, the retired-string pin and the citation drift test): families A15 and A16 coexist in id order, every `find` still matches once, citations recomputed by the drift test, counts derived; `serialise` reads `listing_asset.caption` for a seller's published photographs so `photo_captions` is one contract for seeds and sellers (A-SL22 (2)'s deferred half). (1) **Critical-1 / Major-1 — "Create a listing" creates.** With the adapter present, `startWizard` calls `listings.create()`, sets the NEW `editingId`, an empty `w` and `wizAssets = []` before the first step renders; without an adapter the design's own path runs; the oracle's `prepare()` stubs `POST /api/seller/listings` for the four `wizard-*` captures (A-SL2's shape). (2) **Critical-2 — the app never shows the design's fixtures.** With an adapter present the dashboard renders the loaded rows, or ZERO rows — never the four Austin fixtures, whatever the API answers; a failed load renders zero rows and the design's existing error surface. The frozen `seller-dash` oracle state stays pixel-identical the honest way: the harness serves the design's four fixture rows as a REAL page of `/api/seller/listings` (the D6 / A-SL2 precedent — "serves every design fixture as one complete page"), so the app renders the same four rows as the reference through the success path; the "no page" error-path stub is removed; `seller-dash-empty` keeps its real empty page. (3) **Major-2** — "Save and exit" patches the current step, then exits. (4) **Major-3** — upload → caption → refresh is one chained promise; any rejection lands in `wizErr` and renders through the design's existing error surface; tiles refresh from the returned draft. (5) **Major-4** — a refused Pause / Republish / Withdraw renders its refusal in the row's own `note` (the design's field) and clears on the next successful load; recorded for John as a design gap (no dedicated surface). (6) **Minors** — m1 a deterministic thousands separator (a port of the design's `money()`); m2 reorder compares non-null positions (reachable or not); m3 a declined `describe()` leaves the design's slot caption by position — never a filename (A-SL20); m4 one date in the amendment rows and CLAUDE.md; m5 the two comments read "A-L6.2 (1), as narrowed by A-SL22 (1)"; m6 DEPLOY.md corrected; m7 documents: `accept` widened to PDF/CSV/XLSX and files routed to `document(id, file, kind)` by type (spec D18's three document types); m8 A16.7's comment matches its behaviour. (7) **Infos** — I1 `list()` follows the cursor to the end; I3 the plan's SL8 text takes the next free family id (A17); I5 `practiceName` for the unsaved wizard listing falls back to the design's own label; I2/I4/I6 accepted. (8) **Coverage of the delivered flow**: Task SL8 owns the Playwright flow spec (create → step → photograph + caption → submit → dashboard) against the stubbed API — SL8's brief gains it explicitly; SL7's round adds no flow spec. (9) Concerns 1, 2, 6, 7, 8 ratified as the review judged them (the merge resolutions stand; A16.12/A16.13 approved).

### Task SL8: Admin › Listings reads the real table — **1 day**

**Files:** create `frontend/src/admin/listings.ts` (+ `.test.ts`), `frontend/tests/listing-flows.spec.ts`; modify `frontend/tests/design-amendments.ts` (+ the test and `LOCAL_AMENDMENTS.md`), `frontend/tests/playwright.config.ts`, `frontend/tests/playwright-config.test.ts`.

> **D24 and John's standing rule: every Admin tab shows real database data, never dummy rows.** The tab exists in the approved design and so does its row shape, so this is a wiring change, not a screen. `frontend/src/admin/listings.ts` follows the M6 pattern `frontend/src/admin/users.ts` established — a pure mapping module *outside* `logic.js` producing exactly the `cell()` / `A()` row shapes the design's table renders, with those two helpers **copied verbatim** from `adminVals()` and a unit test comparing them against that file's own output, so the table cannot silently restyle. Columns stay the design's: **Listing · Seller and figures · Status · Action** (`logic.js:1059`). Actions are the design's own buttons — Publish, Reject, Unpublish, Edit, Contact seller — wired to `POST /api/admin/listings/{id}/decide` where a decision exists and left as the design's no-op where it does not.

> **The fifth fixture row does not come back, and that is the point.** Its "Flagged" pill and Investigate action describe an abuse-report table that does not exist; `listing.status` has no `flagged` value and inventing one is out of scope (spec §13). Until that table exists, `GET /api/admin/listings` returns real rows and the Flagged row simply is not among them — **absent beats faked**. `frontend/src/admin/listings.test.ts` therefore compares the mapping against **four** of `adminVals()`'s five own rows and names the fifth as excluded, with John's rule quoted.

> **The reviewer's prompt for `state` and `market` (D12) reuses an existing seam.** `frontend/src/admin/users.ts`'s `UsersUi` interface already has `needsNote(action)` for the decline note; `ListingsUi` gains `needsFields(action)` in the same shape and the same place. **No new markup** — a proper admin field editor is Rev 3 (§14 item 6).

- Steps mirror SL7's: RED unit test → the mapping module → one amendment (the `adminVals()` Listings `rows:` source, with the design's five literal rows kept as the no-data fallback, exactly as A16.1 does for the seller) → `gen:design && gen:app` → the derived pins → the gate. **The family id is DERIVED at branch time (A-SL4), never typed from this plan**: A16 is now the seller family in full (A16.1–A16.15), so SL8 takes the next free integer — A17 unless another branch has landed one first (A-SL23 (7) I3).
- `frontend/tests/listing-flows.spec.ts` is the **value-assertion** spec, in `account-flows.spec.ts`'s shape, with **no stub armed**: sign in as the seller persona, open **Edit** on a seeded hospital and assert the practice name, year, city, ZIP, price, revenue, doctors, rooms, square feet and property status are the seeded values; assert step 6 lists that hospital's four photographs **by caption**; assert step 8's preview shows them instead of dashes; then create a listing, upload a photograph and a PDF, submit, approve it as `design@` (supplying `state` and `market`), and assert it appears on Browse. Add it to the `app` project's `testMatch` alternation (`playwright.config.ts:80`) **and** to whatever `playwright-config.test.ts` pins about that line — `account-flows.spec.ts:23` says it pins both.
- The commit message names D24 and quotes John's standing rule.

---

### Task SL9: documents, the version, the gate, QA and the hand-back — **1 day**

**Implementer steps (1–4), in the worktree. The implementer never runs `railway`, `scripts/deploy.sh` or `git push` — controller amendment A-L7 (1), applied here unchanged.**

- [ ] **Step 1: `scripts/verify-deploy.sh` — one probe per new surface**

In the `coming_soon` branch, beside the four that are there, in the same shape, **before** the `echo "member endpoints absent OK"` line:

```bash
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$BASE/api/seller/listings")
  [[ "$code" == "404" ]] || { echo "FAIL: /api/seller/listings answered $code in coming-soon mode (expected 404 - the seller surface must not be mounted before launch)" >&2; exit 1; }
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$BASE/api/admin/listings")
  [[ "$code" == "404" ]] || { echo "FAIL: /api/admin/listings answered $code in coming-soon mode (expected 404 - the review queue must not be mounted before launch)" >&2; exit 1; }
```

and in the `app` branch, beside `/api/listings`'s 401 probe, the same for `/api/seller/listings`. `tests/scripts/test_verify_deploy.sh` gains the matching positive and negative cases.

- [ ] **Step 2: The docs sweep, RED first through `tests/test_docs.py` where a pin exists**

- **CLAUDE.md §Launch-removal list**, last sentence: *"Fixture data in `logic.js` … also stays — keep field names; the UI reads them — until the listings API replaces it (Seed Listings plan, D6)."* It now needs the seller half: `sellerListings` and the admin rows are **still** in the script and are still the D6 stub's source for the gates, but the app installs the seller's real listings and the real review queue over them at boot when the adapter is present. Write that, keep `test_claude_md_launch_removal_records_the_listings_boot_swap`'s pins satisfied, and add the new pin for this sentence.
- **CLAUDE.md §Layout**: `app/` gains `storage.py`, `media/encode.py`, `api/seller_listings.py`, `api/admin_listings.py`.
- **CLAUDE.md** design-reference paragraph: the derived family/entry counts (SL7 Step 7 and SL8 already move them; confirm here).
- **DEPLOY.md**: the four `S3_*` rows (SL2), the seeding-order line (SL6), and a new §"Object storage" paragraph naming the bucket and what lives under each prefix.
- **`.env.example`**: the four commented rows in the file's own shape.

- [ ] **Step 3: The full local gate — all four parts of CLAUDE.md's verification gate**

```bash
docker compose -f docker-compose.dev.yml up -d
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run mypy scripts/migrate.py scripts/bootstrap_admin.py scripts/seed_persona.py scripts/reset_rate_limits.py scripts/prepare_photos.py scripts/seed_listings.py --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
cd frontend && npm run typecheck && npx vitest run --coverage && npm run build
npm run test:visual:baselines && npm run test:e2e
cd .. && git diff --stat frontend/tests/baseline-manifest.json     # expect: no output
docker build -t pm-sl9 . && docker images pm-sl9 --format '{{.Size}}'
```

- [ ] **Step 4: Hand back to the controller** — the branch, the gate output, the image size beside `main`'s, and the two things this plan changed that were previously ruled otherwise (Pillow's group; the `note` column's prose). **Do not bump the version** — SL9 Step 5 is the controller's.

**Controller steps (5–9), from the main checkout after the branch merges.**

- [ ] **Step 5: The version, in lockstep, one patch (A-SL5)**

```bash
git checkout main && git pull origin main
grep -n '^version' pyproject.toml && grep -n '"version"' frontend/package.json
```
Bump both to `main`'s patch + 1 (`0.1.4` if the Census release has not landed, `0.1.5` if it has), run `poetry run pytest tests/test_versions.py -q`, commit.

- [ ] **Step 6: QA — migrate, seed, deploy**

```bash
railway status                                  # MUST print Project: Practice Match
scripts/deploy.sh QA
scripts/verify-deploy.sh QA
```
Then the seed, **locally against the QA PostGIS service's public URL**, per A-L7 ¶3 — `railway ssh` needs an SSH key this machine does not hold. Personas first, then listings, values in a subprocess environment and never printed; `PERSONA_PASSWORD` from the operator's macOS Keychain (`security find-generic-password -a PERSONA_PASSWORD -s practice-match-qa -w`), **never** from Railway (A-S6.2):

```bash
# seed_persona.py FIRST — the eighteen are assigned to seller@practice-match.test at seed time
ENVIRONMENT=qa DATABASE_URL=<QA public URL> REDIS_URL=<QA> API_SECRET_KEY=<QA> \
  PERSONA_PASSWORD="$(security find-generic-password -a PERSONA_PASSWORD -s practice-match-qa -w)" \
  poetry run python scripts/seed_persona.py
ENVIRONMENT=qa DATABASE_URL=<QA public URL> poetry run python scripts/seed_listings.py
# expect: "[seed] inserted 0, updated 18, removed 0" then "[seed] done - 18 listings"
```

- [ ] **Step 7: Click-through on https://qa.foundation.vin, signed in as the seller persona**

1. My Practice Listings shows **eighteen** rows, not the design's four Austin fixtures.
2. **Edit** on a seeded hospital: step 1 carries its real name, type and year — **John's finding, closed**.
3. Steps 2–5 carry the seeded city, ZIP, price, revenue, doctors, rooms, square feet and property status.
4. Step 6 lists that hospital's four photographs **by caption**, not "Exterior.jpg".
5. Step 8's preview shows those values, not em dashes, and "Photos attached" reads 4.
6. Change one field, Continue, reload the page, re-open Edit — the change is still there ("Saved automatically", kept).
7. Create a listing, upload a photograph and a PDF, submit; the Submitted card appears and the dashboard shows it **In VIN Foundation review**.
8. As `design@`: Admin › Listings shows **real rows**; publish the new listing supplying a state and a metro; it appears on Browse.
9. Decline another; the seller's dashboard pill reads **Declined**, not "Draft".
10. Edit the published one; it leaves Browse at once and re-enters review.
11. The photograph is served at `/api/listings/{id}/photos/1` signed in, and `401` anonymous.
12. **Screenshots of every screen named above**, for the hand-back.

- [ ] **Step 8: Production**

`scripts/deploy.sh production` then `scripts/verify-deploy.sh production`. Production stays `SITE_MODE=coming_soon` and is **never seeded** by this sub-project; the verify script's new probes are what prove the two new surfaces are absent behind the Coming Soon page.

- [ ] **Step 9: The hand-back** — a forwardable plain-language summary, the screenshots, and a one-line engineer's note with the risk, written to `.superpowers/sdd/2026-09-08-seller-listing-lifecycle/task-SL9-handback.md` (**never into this plan**). It must name, in John's language: what Edit shows now; that submitting and reviewing are real; that the eighteen belong to the seller persona; that photographs and documents are stored in the VIN Foundation's own bucket and are never public; and the four things deliberately **not** done — the buyer detail's document rows, the four separate disclosure switches, a revenue range on the detail, and step 6's delete/reorder/kind controls — each with its Rev 3 item number.

---

## Self-Review

Run against the spec with fresh eyes, per the writing-plans skill.

### 1. Spec coverage — every decision, the task that lands it, the test that proves it

| Spec item | Task | Test that proves it |
|---|---|---|
| D1 read and write ship together; no read-only intermediate | the whole plan | `listing-flows.spec.ts` drives Edit **and** upload **and** submit in one spec (SL8) |
| D2 the six-value lifecycle; `declined` added | SL1 | `test_declined_and_other_are_now_legal_and_the_old_refusals_still_are_not` |
| D3 a published edit re-enters review and leaves the market at once | SL3 | `test_saving_a_published_listing_takes_it_off_the_market_at_once` (both halves: the transition, and no re-transition on the second PATCH) |
| D4 every transition writes an `audit_log` row, seller ones included | SL3, SL5 | `test_a_published_edit_writes_one_audit_row_naming_no_permission`; `test_every_decide_branch_writes_exactly_one_audit_row_named_after_the_permission` |
| D5 `seller_id`, nullable, indexed `(seller_id, updated_at DESC)` | SL1 | `test_seller_id_references_account_and_survives_its_deletion`, `test_the_owner_and_asset_indexes_exist` |
| D6 no new permission | SL3, SL5 | `tests/auth/test_permissions.py::test_matrix_matches_the_spec_table` and `tests/auth/test_matrix.py`'s pinned 16-element `ADMINISTRATIVE`, both green **unedited** |
| D7 scope in the handler; a non-owner gets 404 | SL3 | `test_a_non_owner_gets_404_on_every_single_listing_route` |
| D8 `listing.publish` joins `AUDITED`; the handler writes its own row; `REAUTH` unchanged | SL5 | `test_the_decide_handler_writes_its_own_audit_row`, `test_the_matrix_and_route_guard_tests_still_pass_with_listing_publish_audited`, and `test_audited_permissions_are_written_by_their_handlers` green |
| D8 the seller's four actions name no permission and are not watched | SL5 | `test_the_seller_transition_actions_name_no_permission_and_are_not_watched` — the shape `test_the_applicant_facing_audit_actions_…` established |
| D9 two routers, disjoint prefixes, `app` mode only | SL3, SL5 | `test_the_seller_prefix_does_not_collide_with_the_buyer_detail_route`; `scripts/verify-deploy.sh`'s two new coming-soon probes (SL9) |
| D10 the per-step whitelist and the four forced mappings | SL3 | `test_each_step_writes_its_own_fields_and_the_four_forced_mappings`, `test_a_field_from_another_step_is_refused`, `test_only_the_six_field_steps_accept_a_patch` |
| D10 money as the design's strings | SL3 | `test_money_arrives_as_the_string_the_design_produces`, `test_a_number_that_is_not_one_is_refused_in_the_envelope` |
| D11 two serialisers; the buyer's untouched | SL3 | `test_the_draft_serialiser_returns_the_owners_unblanked_truth`; `tests/api/test_listings.py` green unedited but for D22's row |
| D12 six NOT NULLs relaxed; two CHECKs; the reviewer supplies `state`/`market` | SL1, SL5 | `test_a_draft_may_be_almost_empty`, `test_a_withdrawn_listing_may_also_be_empty_and_nothing_else_may`, `test_a_published_listing_must_carry_what_serialise_interpolates`, `test_publish_needs_state_and_market_on_the_first_publish_and_not_after` |
| D13 the slug, and no collision with a seed slug | SL3, SL5 | `test_a_seller_creates_a_draft_owned_by_themselves_…` (the `listing-<id>` form), `test_publish_rewrites_the_slug_once_and_never_again` |
| D14 object storage now, on the approved bucket, `ObjectStore` at `app/storage.py` + `delete` | SL2 | `tests/test_storage.py`, seven tests under moto |
| D15 proxied reads; the buyer photo URL unchanged; normalisation on the request path | SL2, SL4 | `test_a_sellers_photograph_is_served_through_the_unchanged_buyer_route`, `test_a_seed_listings_photograph_still_comes_off_disk`, `test_every_metadatum_is_stripped_and_the_fixture_really_carried_some` |
| D16 every write drops `listings:v1:*` after the commit | SL3, SL4, SL5 | `test_a_patch_drops_every_listings_cache_key_after_the_commit`, `test_every_asset_write_drops_…`, `test_every_transition_drops_…`, `test_every_decision_drops_…` |
| D17 the three rate limits | SL3, SL4 | `test_the_patch_rate_limit_is_per_account_and_refuses_in_the_envelope`, `test_the_upload_rate_limit_is_per_account` |
| D18 the four-photo cap; the four document kinds | SL4 | `test_the_fifth_photograph_is_refused_with_the_photo_limit_code`, `test_a_document_is_stored_as_uploaded_with_its_kind` |
| D18/Q3 PDF, CSV and XLSX only | SL4 | `test_the_three_document_types_are_accepted_and_sniffed`, `test_a_document_type_outside_the_allow_list_is_refused` |
| D19 live on upload; owner and staff only; no new workflow | SL4 | `test_a_document_reads_to_its_owner_and_to_staff_and_to_nobody_else`, `test_a_document_read_carries_the_download_headers` |
| D20 `w.anon` sets both; the four columns stay independent; `documents_disclosed` spelled in full | SL1, SL3 | `test_step_seven_writes_the_four_disclosure_columns_inverted`; the column names in `EXPECTED_COLUMNS` |
| D21 the buyer detail's document rows are not rewired | — | **no task touches `logic.js:1286–1290`**; `detail` and `mobile-detail` keep their frozen hashes (`baseline-manifest.test.ts`) |
| D22 `serialise` blanks `rev`; no screen moves; every seed true | SL1, SL3, SL6 | `test_serialise_blanks_rev_when_the_flag_is_off_and_keeps_it_when_it_is_on`, `test_the_seeded_disclosure_backfill_is_in_the_migration_not_in_the_seeder`, `test_the_disclosure_backfill_holds_for_a_freshly_seeded_row` |
| D23 amendment family + adapter prop; fixtures stay the oracle's data; no baseline moves | SL7 | `design-amendments.test.ts` (both count pins + the byte-for-byte equality), `app-generated.test.ts`, `baseline-manifest.test.ts`, `npm run test:e2e` at `maxDiffPixels: 0` |
| D23/Q1 the `declined` pill, label and tone | SL7 | amendment `A15.10`; `frontend/src/logic.test.ts` characterises `statusPill('declined')` |
| D24 Admin › Listings on real data; unbuilt rows absent | SL8 | `frontend/src/admin/listings.test.ts` against `adminVals()`'s own four rows, the fifth named as excluded |
| D25 seed ownership, re-asserted, NULL when absent, never defaulted on production | SL6 | the seven tests in `tests/scripts/test_seed_listings.py` |
| D26 seed photographs stay on disk; the tile shows the caption | SL4, SL6 | `test_a_seed_listings_photograph_still_comes_off_disk`; `listing-flows.spec.ts` asserts step 6's four captions |
| Q2 the reviewer supplies state + metro | SL5, SL8 | `test_publish_needs_state_and_market_on_the_first_publish_and_not_after`; `ListingsUi.needsFields` |
| Q4 no confirmation dialog | — | **no task adds one**; `wizard-*` and `seller-dash` keep their frozen hashes, which is the proof |
| §12 100 % backend and frontend | every task's gate step | `--cov=app --cov=scripts --cov-branch --cov-fail-under=100`; `npx vitest run --coverage` at 100/100/100/100 |
| §12 `listing-flows.spec.ts` against the real API, no stub | SL8 | the spec itself, and `emptyCollectionStubUrls` returning `[]` under `PW_APP_URL` |
| §13 non-goals | — | no task touches requests/messaging, the detail's document rows, abuse flagging, geocoding a seller listing, Census figures, or production data |

### 2. Gaps found, and what was done about each

**Closed inside the plan.**
1. **The spec's migration number `017` is taken.** The Census branch numbered 017–019 while the spec was being written. **A-SL3** takes 020/021 and says why; the Preconditions check both trees rather than trusting either.
2. **The spec's family id `A13` is taken.** `feat/design-dropdowns` has it. **A-SL4** derives the number at branch time; every count in this plan is `<derived>` and Step 0 of SL7 is the derivation.
3. **`rev_disclosed` and `documents_disclosed` do not exist.** D20 names "the four disclosure columns" and D11 says a new draft has all four false, but `016_listing.sql` has only two. SL1 adds them **and backfills every existing seed row to true in the same file**, because without that, applying `030` to QA would blank eighteen revenue figures on the buyer detail between two tasks of this plan.
4. **Pillow is a dev-only dependency, by an explicit in-tree decision.** D15 puts the encoder on the request path, which contradicts both premises of that decision's own comment. SL2 moves it and rewrites the comment, and the change is listed in Pre-flight, in the SL2 commit and in the hand-back with the measured image-size delta. **This is the one recorded deviation from a standing in-tree ruling.**
5. **Two mail registries, not one.** `enqueue` raises `KeyError` for a template absent from `app/mail/outbox.py`'s frozenset, and `app/mail/templates.py` holds the bodies. SL5 edits **both** and says so; editing one would pass every unit test and fail at the first submit on QA.
6. **`ObjectStore`'s signatures.** Census Task A2's `put_immutable` returns a **bool** and never raises; the constructor is positional; only 404/NoSuchKey/NotFound answer `None`. A-SL1 says "taken verbatim", so SL2's code and tests are A2's, not a re-imagining, and the REBASE arm forbids rewriting the file if the Census branch lands first.

**Escalated, not closed — Pre-flight question 1.** Spec §9 asks for `GET /api/seller/listings` to be stubbed "with the design's own four `sellerListings` fixtures". **That round-trip is not constructible**: the design's `note` column carries "Live since August 24 · 34 views, 2 requests", which needs a view count and a request count no column in this slice supplies, and the Admin tab's fifth row is a `Flagged` pill for a status D24 refuses to invent. **A-SL2** rules the alternative — an empty stub plus the ruled fallback, which is A-L6.2 (1) applied unchanged and moves no hash — and the residual question (what a *real* seller with zero listings should see) goes to the controller.

### 3. Placeholder scan

No "TBD", no "TODO", no "implement later", no "similar to Task N", no "add appropriate error handling", and **no deferred coverage**: every arm no request can reach has a **named** test in the task that writes it — `test_the_ladder_gives_up_rather_than_writing_an_oversized_file`, `test_bytes_that_are_not_an_image_are_refused_rather_than_raised`, `test_a_client_error_that_is_not_a_missing_key_is_re_raised`, `test_delete_of_an_absent_key_is_false_and_not_an_error`, `test_a_photo_entry_that_names_no_asset_is_a_404_not_a_500`, `test_uploads_are_refused_with_a_clear_message_when_storage_is_unconfigured`, `test_a_listing_id_that_is_not_a_uuid_is_a_404_not_a_422`.

Two places deliberately give a table of required test names and assertions rather than the bodies — SL4's twenty-three asset tests and SL5's twenty-two transition and admin tests. Each row names the test, the status code, the error code and the row or object it must check, which is the contract; the bodies are mechanical against the fixtures SL3 spells out in full. **No row may be dropped for time** — that sentence is in both tasks.

### 4. Type consistency, walked end to end

- `seller_id` is `uuid` in `030`, `principal.account_id` (a `UUID`) in every handler, and never a string: `owned_row` compares `row["seller_id"] != principal.account_id`, both UUIDs, so a str/UUID mismatch cannot silently 404 every request.
- `listing.photos` is `list[str]` throughout: `"<slug>/<n>.webp"` for a seed row, `str(asset_id)` for a seller row, and `"/api/listings/<id>/photos/<n>"` in the JSON. The boundary is `serialise`; the discriminator is `"/" in entry`, tested both ways.
- The wizard's key names are `state.w`'s (`logic.js:204`) on the wire — `desc`, `facilityType`, `anon`, `revBand`, `docsLocked` — and the columns' names in the database. `columns_for` is the only inbound translator and `serialise_draft` the only outbound one; `BLDG_IN` and `BLDG_OUT` are inverses of each other and a unit test asserts the round trip.
- `STEP_FIELDS`, `serialise_draft`, `columns_for`, `owned_row`, `assets_of`, `store_for_request`, `drop_list_cache`, `encode_webp`, `sha256_hex`, `ObjectStore` are the exact names the tests import.
- `makeListingsAdapter`, `toDashboardRow`, `toWizardState`, `emptyCollectionStubUrls` are the exact names the frontend tests import; `toDashboardRow`'s output is `{id, title, meta, note, status}` — the design's own `sellerListings` shape, letter for letter, which is what lets A15.1 be a one-expression swap.
- The audit action namespace is one: `listing.edit`, `listing.submit`, `listing.pause`, `listing.republish`, `listing.withdraw` (seller, naming no permission by design) and `listing.publish` (staff, naming its permission). An auditor greps `listing.` once.

---

## Pre-flight — every gate this plan touches

Read this before dispatching any task. Each row is a gate, what this plan does to it, and how it stays green.

| Gate | File | What this plan does | How it stays green |
|---|---|---|---|
| Byte-identical generated files | `frontend/tests/app-generated.test.ts` | changes `app.setup.js` (one prop) and, through amendments, `logic.js` | `npm run gen:design && npm run gen:app` in SL7/SL8; **no hand edit to any of the four** |
| Prop parity | same test, `:26–34` | adds a prop the **design does not declare** | the gate is one-directional; the pinned `data-props` key list does not move, and CLAUDE.md's "All seven prototype props" sentence stays true |
| Amendment set, pinned both ways | `frontend/tests/design-amendments.test.ts` `AMENDMENT_IDS` + `toHaveLength(<n>)` | adds eleven amendments in two families | SL7 Step 0 derives the numbers; SL7 Step 7 and SL8 update the id list, the count and `LOCAL_AMENDMENTS.md` together (a three-file change by design) |
| Pristine hash | same test, `:13` | **untouched** — the pristine bundle is never edited | the hash pin is the proof |
| Doubled blank lines | same test | no removal amendment here | the invariant holds by construction |
| A1's derived 24, the 29-heading census | same test | **untouched** — no template edit in either family | a template diff after `gen:app` is a STOP (SL7 Step 5) |
| `LOCAL_AMENDMENTS.md` rows == literals + 1 | `tests/test_docs.py::test_local_amendments_row_count_matches_design_amendments` | eleven new rows | derived, checked by the same command |
| CLAUDE.md's "N families, M entries" | `tests/test_docs.py::test_claude_md_amendment_family_and_entry_counts_match_design_amendments` | both numbers move | the test prints what it expects; SL7 Step 7 reads it rather than guessing |
| The thirteen frozen screens | `frontend/tests/baseline-manifest.json` + `.test.ts` | **five of them are this plan's own screens** — `seller-dash` and the four `wizard-*` | A-SL2's empty stubs + the ruled fallbacks; `git diff --stat` on the manifest is a gate step in SL7, SL8 and SL9 |
| Zero pixel tolerance | `frontend/tests/playwright.config.ts` | unchanged | `maxDiffPixels: 0` beside `threshold: 0.1`, never relaxed |
| 43 approved states | `frontend/tests/screens.ts`; `tests/test_docs.py::test_claude_md_approved_screen_count_matches_screens_ts` | **adds none** — step 6 has no approved state (Rev 3 §14 item 7) and `listing-flows.spec.ts` is not a screen | the count stays 43 and CLAUDE.md is not edited for it |
| The Playwright `app` project's `testMatch` | `playwright.config.ts:80` + `playwright-config.test.ts` | adds `listing-flows` to the alternation | SL8 edits **both**; a spec added to one only never runs |
| Every route guarded or public | `tests/auth/test_permissions.py::test_every_route_is_guarded_or_public` | adds twelve guarded routes | **nothing is added to `PUBLIC_ROUTES`** |
| Audited handlers write their own row | same file, `_unaudited` | `listing.publish` joins `AUDITED` | the decide handler calls `audit.write(` in its own body; `test_the_decide_handler_writes_its_own_audit_row` asserts it at source |
| Audited action names | `test_every_audited_action_is_named_after_a_permission` | writes `action="listing.publish"` on all three branches | it **is** a permission; nothing added to `MULTI_ACTION_PERMISSIONS` or `CASCADED_ACTIONS` |
| Guards hoisted, never wrapped | `_unresolvable` | four new module constants | `REQUIRE_MANAGE_OWN`, `REQUIRE_REVIEW`, `REQUIRE_PUBLISH`, and `listing.read` reused from `listings.py` |
| `ADMINISTRATIVE` / `REAUTH` pins | `tests/auth/test_matrix.py:148–153`, `:173–191` | **no permission is added**, and `REAUTH` is untouched | the 16-element set and `len == 16` stay true; `gen:permissions` is **not** run |
| Migration immutability + numbering | `scripts/migrate.py`, `tests/test_migrate.py` | two **new** files, `030`/`031` | no applied file is edited; neither contains `BEGIN`/`COMMIT`/`ROLLBACK` (`test_migration_files_never_manage_their_own_transaction` globs `migrations/*.sql`) |
| Fixtures | `tests/conftest.py` `scratch_dsn`/`conn`/`redis`; `tests/api/conftest.py` `client`/`member`/`auth_headers` | used by name | **there is no `scratch_db` fixture** in `tests/` and this plan invents none |
| CI strict-mypy script list | `.github/workflows/quality.yml:63`; `tests/test_docs.py:138`, `:30` | **adds no `scripts/*.py`** | the pinned joined substring is unchanged |
| Every setting documented | `tests/test_docs.py:107` | four new `S3_*` fields (SL2, greenfield arm) | rows in **both** `.env.example` and `DEPLOY.md`, in each file's own shape |
| `seed_listings.py` exit codes | `tests/test_docs.py:1333` | **adds none** — an absent persona is a printed note, not a code | `codes == [0, 2, 3, 4, 5]` still |
| DEPLOY.md seeding section | `test_deploy_md_documents_how_to_seed_qa` | one paragraph added | the nine pinned substrings and the plain-before-`--reset` ordering are not disturbed |
| CLAUDE.md launch-removal pins | `test_launch_removal_list_is_executed`, `test_claude_md_launch_removal_records_the_listings_boot_swap`, `test_claude_md_counts_the_seven_prototype_props_…` | one sentence extended (SL9) | RED first through the pin, then the edit |
| 100 % backend, lines and branches | `--cov=app --cov=scripts --cov-branch --cov-fail-under=100` | four new modules, one changed script | every unreachable-from-a-request arm has a named test (Self-Review §3) |
| 100 % frontend | `frontend/vite.config.ts` thresholds | two new `src/**` modules | **the exclude list is not widened**; every adapter failure path has its own test |
| Suite clock | CI backend `timeout-minutes: 30` | moto + the WebP ladder | fixtures ≤ 200 × 200 except the two that must exceed `MAX_EDGE_PX`; no sleeps |
| `-W error` | pytest | boto3/moto emit `DeprecationWarning` on some Python builds | if one fires, the fix is the dependency pin, **never** a filterwarnings entry (Global Constraint (c)) |
| Coming Soon absence | `scripts/verify-deploy.sh` + `tests/scripts/test_verify_deploy.sh` | two new member surfaces | two new 404 probes and their test cases (SL9 Step 1) |

### Open questions for the controller

Each has a default this plan implements; none blocks a task from starting.

1. **A real seller with zero listings sees the design's four Austin fixtures.** A-SL2 keeps the design's rows whenever `items` is not a non-empty array, which is what holds `seller-dash`'s frozen hash — and it is the ruled behaviour for `/api/listings` already (A-L6.2 (1)). But the seller dashboard *can* render an empty list without crashing, unlike Browse, so the alternative is honest: distinguish "not loaded" from "loaded, empty", show nothing, and **rebaseline `seller-dash` by ruling**. *Default:* the fixtures stay and no hash moves. *If John wants an empty dashboard*, it is one ruled amendment plus one baseline, and it should be decided before SL7 rather than after.
2. **Pillow moves to the main dependency group** (SL2), against an explicit in-tree comment saying it must not. The premise changed — D15 puts the encoder on the request path — but the decision was written down and is being reversed by an implementer's task. *Default:* move it, correct the comment, report the image-size delta in the hand-back. *Confirm this is the controller's call and not John's.*
3. **The dashboard's `note` column loses its view and request counts.** The design's fixture says "Live since August 24 · 34 views, 2 requests"; nothing in this slice counts a view or a request. *Default:* the mapping writes the shortest honest note per state and invents no number. *The alternative* is a view counter, which is a new table and a new spec.
4. **`ObjectStore`'s landing order.** If the Census branch merges first, SL2 takes the REBASE arm and adds only `delete()`. If it merges *after* this branch, the Census plan's Task A2 must be amended to consume `app/storage.py` rather than write `app/census/storage.py` — **A-SL1 already says so**, but the Census plan's own text still says `app/census/storage.py` and its Step 4 still creates `practice-match-data-qa`/`-prod`. *Ask:* should the controller edit the Census plan now, or does A-SL1 in this plan suffice as the record?
5. **`GET /api/seller/listings/{id}` re-invokes `REQUIRE_REVIEW(request)` inside the handler** for the staff arm, the way `admin_users.decide_route` re-invokes `REQUIRE_REVOKE(request)` for its revoke branch. That is an established pattern, but it means the route carries `listing.manage_own` as its *declared* guard while staff reach it under `listing.review`. `tests/auth/test_permissions.py` resolves the declared guard only, so this is correct and invisible — but it is a second permission on one route, and the controller may prefer a separate `GET /api/admin/listings/{id}` instead. *Default:* one route, two arms, as the spec's own table describes it.

---

## Per-worktree environment

This machine runs six other Practice Match worktrees. **They must not share a database, a Redis index or a port** — `db_ready` migrates whatever `DATABASE_URL` points at, and the shared dev database is not it (MEMORY: "Local DB migration hazard").

```bash
cd "/Users/johndean/Development/Practice Match"
git worktree add .worktrees/feat-seller-lifecycle -b feat/seller-lifecycle main

# The database this branch owns, created once, against the compose Postgres on 5433:
docker compose -f docker-compose.dev.yml up -d
psql "postgresql://pm:pm_dev_pw@localhost:5433/postgres" -c 'CREATE DATABASE practice_match_seller'
```

Every command in every task runs with this environment, and nothing in it is ever pointed at `practice_match`:

```bash
export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_seller
export REDIS_URL=redis://localhost:6380/7
export ENVIRONMENT=test
export API_SECRET_KEY=local_only_secret_change_me
# Playwright, so a parallel worktree's servers are never adopted by `reuseExistingServer`:
export PW_APP_PORT=5513
export PW_REF_PORT=5514
export PW_CS_PORT=5515
export PW_API_PORT=8357
```

| | This branch | Default (do not use here) |
|---|---|---|
| Postgres database | `practice_match_seller` on `localhost:5433` | `practice_match` |
| Redis index | `redis://localhost:6380/**7**` | `/0` |
| Vite app | **5513** | 5173 |
| Reference server | **5514** | 5174 |
| Coming Soon | **5515** | 5175 |
| uvicorn | **8357** | 8017 |

**Never set a global `RAILWAY_TOKEN`, and never run `railway up` — `scripts/deploy.sh` is the only path, and it must be given this worktree as `SOURCE_DIR`** (`scripts/deploy.sh QA .worktrees/feat-seller-lifecycle`), because the CLI resolves a worktree's `.git` pointer file back to the main checkout and would otherwise ship `main`'s tree (P14, `DEPLOY.md`). Those commands are the controller's, not an implementer's (A-L7 (1)).

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-09-08-seller-listing-lifecycle.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration. **REQUIRED SUB-SKILL:** `superpowers:subagent-driven-development`.

**2. Inline Execution** — execute tasks in this session with checkpoints. **REQUIRED SUB-SKILL:** `superpowers:executing-plans`.

**Which approach?**


---

**Controller amendments before execution (2026-09-08 ~00:05 WITA).** **A-SL5 — migration numbers.** The plan's `020`/`021` collided with the Census plan's reserved `020_license_audit.sql` (Task A8) and its `023`/`060`/`061`; this sub-project's migrations are `030_listing_owner_and_status.sql` and `031_listing_asset.sql` (applied above by substitution, 7+6 occurrences), a range no other plan claims; the runner applies unapplied files in name order, so `030`/`031` land after the Census files whenever both merge. **A-SL6 — Pillow to the main group** (open question 2): the request-path photo encoder needs it in the runtime image; the in-tree comment that kept it dev-only is superseded and rewritten in SL2 — the controller's call, recorded. **A-SL7 — the dashboard note** (open question 3): the shortest honest note per state, no invented counts; "34 views, 2 requests" leaves with the fixtures. **A-SL8 — the staff read** (open question 5): a separate `GET /api/admin/listings/{id}` guarded by `listing.review`, not one route with two permissions — one guard per route is what `tests/auth/test_permissions.py` models. Open question 4 is already settled by the Census plan's A-C2 (`app/storage.py`; bucket `practice-match-data` per environment). **Open question 1 is John's:** what a real seller with zero listings sees — proposed default: an empty dashboard (the design's shell with no rows and its existing empty copy if any; otherwise the rows simply absent), captured as a new approved oracle state under a ruling before SL7; the design's four Austin fixtures never render as if they were the seller's. Execution: worktree `feat/seller-lifecycle`, database `practice_match_seller`, Redis db 7, Playwright ports 5513/5514/5515/8357; SL1 may start now; SL7 waits for the answer to open question 1.
