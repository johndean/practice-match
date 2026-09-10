# Automatic Image Identifiability Protection — SHOW / NOT SHOW — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved spec `docs/superpowers/specs/2026-09-09-image-identifiability-protection-design.md` (630 lines, sections 0/A–J) and nothing else: one listing-level control `identifiable_content_visibility` defaulting to `NOT_SHOW`, a layered per-image pipeline (validate → OCR → identity matching → vision → aggregation → opaque redaction) that runs on **every** photograph on **every** ingress, an explicit per-image state machine with four error states, a delivery resolver that decides the served representation server-side on every request, a publishing gate with a database trigger behind it, and a seller review experience composed from the approved design's own idioms through the D15 amendment engine.

**Architecture:** Three migrations (`040`–`042`) add the listing column, the `listing_asset_privacy` record and a fail-closed publish trigger; the upload route keeps its synchronous encode but now stores three objects per photograph (`original.{ext}`, `display.webp`, `redacted.webp`) under `listings/{listing_id}/photos/{asset_id}/` and publishes `media.process_photo` by name after the commit, so the api never imports an OCR, barcode or vision engine and the worker never serves bytes. Every buyer-facing byte and every buyer-facing URL is resolved by one pure function, `app/privacy/delivery.py::buyer_variant`, and every publication path calls one predicate, `app/privacy/gate.py::photos_not_ready`, with migration `042`'s trigger refusing whatever a route might miss.

**Tech Stack:** FastAPI + psycopg2 + Celery (prefork, `media` queue) + Redis · PostGIS/PostgreSQL DDL through `scripts/migrate.py`'s sha256 ledger · Pillow (`app/media/encode.py`, `app/media/redact.py`) · `rapidocr-onnxruntime` + `onnxruntime` (OCR) and `zxing-cpp` (2D symbols) behind typed adapters with stub engines in tests · the `anthropic` Python SDK behind `app/privacy/vision.py` · boto3 `ObjectStore` against Railway's `practice-match-data` bucket (moto in tests) · the design bundle's dc runtime on the reference side and Vue 3 + `frontend/scripts/convert-dc.mjs` on the app side · pytest, Vitest 3, Playwright.

**Branch:** worktree `.worktrees/feat-image-identifiability` on branch `feat/image-identifiability`, cut from `main` **after both merge preconditions below**. Implementers never push, deploy or run `railway`; the controller does those at hand-back.

---

## John's directive — the two sentences that govern every task

John, 2026-09-09 ~15:30 WITA, verbatim (`docs/superpowers/specs/2026-09-09-image-identifiability-directive.md`, committed by Task P1 §Step 8 as the source of record):

```
DEFAULT:
    NOT SHOW

The safest privacy state is the default.
```

```
There must be NO path through which an image can bypass privacy processing.
```

Everything below is one of those two made mechanical. The first is migration `040`'s `DEFAULT 'NOT_SHOW'`, the resolver's `else None`, and the four error states that never fall back to an original. The second is the count of ingress paths (nine, §A.1) and delivery paths (twelve, §A.4) that each have a named test in Task P13. John's third standing instruction, §23, is a constraint on prose rather than on code and is enforced by a test in Task P14: **nothing this sub-project writes may claim perfect or certain detection.**

### Where this sub-project sits

Its own sub-project — the spec, then this plan — executed in a worktree cut from `main` **after two merges**, both of which are **blockers to be filled with SHAs at dispatch**:

- [ ] **Merge precondition 1 — the seller listing lifecycle, Tasks SL7–SL9** of `2026-09-08-seller-listing-lifecycle.md` (branch `feat/seller-lifecycle`, read here at `2510278`). It supplies `listing_asset` (`migrations/030`–`033`), `app/storage.py`'s `ObjectStore`, `app/media/encode.py`, `app/api/seller_listings.py`, `app/api/admin_listings.py`, the wizard adapter `frontend/src/listings/seller.ts` and every publication route this design hooks into. On `main` today none of them exists (spec §A.0), so there is nothing to attach a pipeline to. **Merge SHA: __________ (fill at dispatch).**
- [ ] **Merge precondition 2 — the A19 photo lightbox** of `2026-09-09-photo-lightbox-and-arrows.md`. Its dialog is the seller's review viewer (spec §C.9 (c)): Task P12 extends A19's overlay rather than composing a second one. **Merge SHA: __________ (fill at dispatch).**

It lands **before** the map engines (`2026-09-05-practice-match-map-engines.md`) and before the roadmap's "Admin & seller controls" stage: the map engines change no image path, while every later seller-control screen must be built on a delivery layer that already refuses originals.

**Every `file:line` anchor below names its tree.** `MAIN` is `main` at `073aab8`; `BRANCH` is `.worktrees/feat-seller-lifecycle` at `2510278`, read with `git show 2510278:<path>` because that working tree carries another agent's uncommitted work (spec §A.9). After the two merges the shared files are longer than either tree, so **Task P1 Step 0 re-derives every anchor against the merge SHA by grepping for the quoted text, never by trusting a number.**

---

## Global Constraints

Every task's requirements implicitly include this section.

- **(a) The design file is never hand-edited.** `Practice Match V3.rev2.dc.html` (pristine) + `amendments()` == `Practice Match V3.dc.html`, produced by `npm run gen:design` and proved byte for byte by `frontend/tests/design-amendments.test.ts`. Every entry of this sub-project's family is `{ id, date: '2026-09-09', ruling, find, replace, count }`, and one row in `LOCAL_AMENDMENTS.md` quotes that `ruling` byte for byte. `logic.js` is re-ported by the python snippet; `App.vue` and `pseudo.css` are regenerated by `npm run gen:app`.
- **(b) Zero pixel tolerance, never relaxed.** `maxDiffPixels: 0` beside `threshold: 0.1` in `frontend/tests/playwright.config.ts` stays. Baselines regenerate from the amended design in the same run (`npm run test:visual:baselines`), so a ruled change is legal there; `frontend/tests/baseline-manifest.json` moves **exactly one row (`wizard-step-7`) in Task P11** and **zero rows in Task P12** — that is P12's acceptance criterion, not a nicety.
- **(c) Coverage, both sides.** Backend `poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100`, exactly as CI runs it. Frontend `cd frontend && npx vitest run --coverage` at 100 for lines, branches, functions and statements; `logic.js` is excluded from the measured set but every new branch in it is characterised in `frontend/src/logic.test.ts` regardless.
- **(d) Strict typing.** `poetry run mypy app --strict` and `poetry run mypy scripts/… --strict` (the `.github/workflows/quality.yml:63` list, which `scripts/reprocess_photos.py` joins in Task P8). `cd frontend && npm run typecheck`.
- **(e) No suppressions.** No `# type: ignore` that is not already in the tree for celery's untyped decorators, no `# pragma: no cover`, no `@ts-expect-error`, no `eslint-disable`, no widened tolerance, no widened `coverage.exclude`, no loosened rate limit. `poetry run ruff check app tests scripts` with the repository's existing rule set and no new ignores.
- **(f) Surgical diffs.** The spec and nothing else. No drive-by refactor of `seller_listings.py`, no reformatting, no renaming of an existing column, route or test, no removal of a function or a feature while doing unrelated work.
- **(g) Migrations `040`–`049` only.** Three files are used (`040`, `041`, `042`); `043`–`049` stay free for this sub-project's own future work. An applied migration is immutable (`DEPLOY.md`, the sha256 ledger) — a correction is a new file, never an edit. The carve-out is recorded as amendment **A-C12** in the Census plan (`docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md:42`, `:62`) and in `DEPLOY.md`'s numbering paragraph in the same commit as `040`. **`A-C12`, not `A-C10`:** `:42` already spends `A-C10` on the seller lifecycle's own `030`–`039` carve-out, and `A-C11` is spent twice in the same plan (`:2089`, `:2553`), so `A-C12` is the next free controller-amendment id on `main` at `073aab8` — re-derived by the grep in the Preconditions, never written from memory.
- **(h) Secrets live only in Railway.** `ANTHROPIC_API_KEY` is **worker only** — the api never reads it, `app/config.py` declares it optional so both services boot without it, and it is refused at the moment it is USED, naming the variable and never its value. It never appears in git, chat, a CI log, an exception message, an audit row or a test fixture — the same rule as `CENSUS_API_KEY`. `app/privacy/vision.py` logs the SDK's `_request_id` and the exception class and nothing else.
- **(i) No photograph leaves Railway** except to `api.anthropic.com`, from the worker, when `settings.anthropic_api_key` is set — the one egress this sub-project adds, recorded in `DEPLOY.md`'s outbound destinations. No OCR, barcode or vision engine makes a network call in the test suite (`-W error`, no model download, no binary fetch); the worker never fetches a barcode's payload; nothing seller-derived is ever written under `frontend/public` or any StaticFiles mount.
- **(j) The version bump is the controller's, at release.** `frontend/package.json` and `pyproject.toml` move in lockstep (`tests/test_versions.py`), one patch per release, in the release commit only, in merge order against the queued branches. No task here touches either version.
- **(k) The worktree, and its own everything.** `.worktrees/feat-image-identifiability`, cut from `main` after both merges, with Task P1 Step 0's environment. Its own database `practice_match_privacy`, its own Redis index `/9`, its own Playwright ports. `npm ci` in **both** `frontend/` and `coming-soon/` (node_modules are per checkout and `npm run build` builds both sites). **Never start a second `docker compose` stack** — the one on ports 5433/6380 is shared; a second stack would bind the same ports and silently adopt or fail. `lsof` the four Playwright ports before every Playwright run.
- **(l) Never `pkill` by substring and never `git stash`.** A substring kill reaches another worktree's Vite, reference server or uvicorn; `git stash` in a worktree loses another agent's work. Stop a named process by the PID `lsof` printed.
- **(m) Implementers never push, never deploy, never run `railway`.** No `git push`, no `scripts/deploy.sh`, no `railway status`/`variable`/`logs`/`ssh`. The controller performs the QA deploy, the click-through, the merge, the lockstep bump, the production deploy and `scripts/verify-deploy.sh production` at hand-back.
- **(n) Deviations STOP with `NEEDS_CONTEXT`.** A `find` that does not match with `count: 1` at its point of application; a frozen hash that moves where the plan did not predict it; a gate that would need relaxing; an anchor whose quoted text is absent after the merge; a spec sentence that contradicts the code as merged; a dependency that will not resolve. Stop, report `NEEDS_CONTEXT` naming the file, the expectation and what was actually found, and wait for a controller amendment. Do not improvise, do not widen a tolerance, do not add a suppression, do not invent UI.

---

## Preconditions

Verify by grep, not by memory. If any check fails, **STOP** — the merged tree is not what this plan was written against and the anchors must be re-derived.

```bash
cd "/Users/johndean/Development/Practice Match"
git rev-parse --short HEAD                                                  # the merge SHA both preconditions produced
git log --oneline -1 --grep="seller lifecycle" | head -1                    # precondition 1 present
grep -c "id: 'A19" frontend/tests/design-amendments.ts                      # precondition 2 present: A19's twelve literals
grep -rn "identifiable_content_visibility" app/ migrations/ frontend/src/   # nothing — this sub-project is unstarted
ls migrations/04*.sql 2>/dev/null                                           # nothing — 040-049 is free
grep -n "listing_asset" migrations/031_listing_asset.sql | head -2          # the table this design extends
grep -n "def upload_photo" app/api/seller_listings.py                       # the upload seam
grep -n "def _asset_bytes\|def get_listing_photo\|PHOTO_CACHE_CONTROL" app/api/listings.py
grep -n "include=\[" app/tasks/celery_app.py                                # mail + census only
grep -n -- "--queues=celery" scripts/start.sh                               # one queue today
grep -c "^| A" docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md
grep -c "^  { name: '" frontend/tests/screens.ts                            # the approved-state count to extend
```

Then the four numbers this plan derives rather than states, recorded in the worktree's scratch notes at Step 0 and used by Tasks P11 and P12:

```bash
# The next free amendment family id — by grep, never from memory (spec §C.9).
python3 - <<'PY'
import re, pathlib
ts = pathlib.Path("frontend/tests/design-amendments.ts").read_text()
fams = sorted({int(n) for n in re.findall(r"id: 'A(\d+)", ts)})
print("families present:", fams)
print("NEXT FREE FAMILY:", "A%d" % (max(fams) + 1))
print("literal entries:", len(re.findall(r"id: 'A(\d+)", ts)))
PY
grep -n "Array.from({ length:" frontend/tests/design-amendments.test.ts     # A1's derived count
grep -n "families, " CLAUDE.md | head -2                                    # the count sentence to rewrite
grep -n '"Eleven", "Twelve"' tests/test_docs.py                             # number_words: must reach the new family count
```

**Every `A20.x` id written in Tasks P11 and P12 is that derived id.** If the grep prints anything but `A20`, substitute it everywhere in those two tasks before writing a line — the ledger, not this document, is the authority.

Finally the baseline the gates start from:

```bash
docker compose -f docker-compose.dev.yml up -d      # the ONE shared stack; do not start a second
poetry install
cd frontend && npm ci && cd ../coming-soon && npm ci && cd ..
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
cd frontend && npm run typecheck && npm test && npm run build
```

All green before Task P1 Step 1. A red gate here is the merge's, not this plan's, and is reported as `NEEDS_CONTEXT`.

---

## File Structure

Every file this sub-project creates or modifies, its one responsibility, and the task that owns it. **⟳ = regenerated or re-ported, never hand-edited.**

| File | Kind | One responsibility | Task |
|---|---|---|---|
| `docs/superpowers/specs/2026-09-09-image-identifiability-directive.md` | create | John's directive, verbatim, as the committed source of record | P1 |
| `migrations/040_listing_identifiable_content_visibility.sql` | create | the listing column, its CHECK, its `NOT_SHOW` default and the path-entry backfill | P1 |
| `migrations/041_listing_asset_privacy.sql` | create | the per-photograph privacy record, its seven CHECKs and its two indexes | P1 |
| `migrations/042_listing_publish_photos_ready_trigger.sql` | create | `listing_photos_not_ready()` and the `BEFORE INSERT OR UPDATE OF status` backstop | P1 |
| `tests/test_listing_privacy_schema.py` | create | one schema test per column, per CHECK, per index and per trigger branch | P1 |
| `scripts/seed_listings.py` | modify | the UPSERT writes `identifiable_content_visibility = 'SHOW'` in the insert list AND in `DO UPDATE SET` (spec §C.10) — without it migration `042`'s trigger refuses every seeded row | P1 |
| `tests/scripts/test_seed_listings.py` | modify | one case pinning that `SHOW` on both halves of the UPSERT, and that a re-seed of an existing row keeps it | P1 |
| `DEPLOY.md` | modify | the `040`–`049` carve-out; `ANTHROPIC_API_KEY`, `PRIVACY_ENGINE_MODULE`, `CELERY_TASK_ALWAYS_EAGER` rows; outbound destinations; worker sizing; image-size delta; the corrected S3 wording; the runbook link | P1, P4, P6, P8, P14 |
| `docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md` | modify | amendment A-C12: `040`–`049` leaves the SP3-A range (`:42`, `:62`) | P1 |
| `app/privacy/__init__.py` | create | `PROCESSING_VERSION`, `PHOTO_EXT` and the three key builders | P2 |
| `app/privacy/record.py` | create | the privacy row: its dataclass, its INSERT, its reads, the claim, the reset rule and every state transition | P2, P3 |
| `app/api/seller_listings.py` | modify | the three-object upload, the magic-byte sniff, the threaded encode, the enqueue, the three-object delete, `showIdentifiable`, the flip, the gate at submit/status, the owner routes | P2, P9, P10, P12 |
| `tests/api/test_listing_assets.py` | modify | the upload's and delete's new object set; `_publish`'s privacy rows; `_SEED_INSERT`'s `SHOW`; the buyer-byte header pins re-recorded | P1, P2, P9 |
| `tests/conftest.py` | modify | the `store` moto fixture, its `BUCKET`/`ENDPOINT` constants and its `_intercepted_by_moto` guard, promoted out of `tests/api/test_listing_assets.py` so `tests/privacy/`, `tests/tasks/` and `tests/media/` can reach a bucket | P2 |
| `tests/api/conftest.py` | modify | the `seller`, `buyer` and `admin` signed-header fixtures and the `_draft` / `_jpeg_bytes` helpers every API suite below uses | P2 |
| `tests/privacy/__init__.py` | create | the package marker for the unit suites | P3 |
| `tests/privacy/test_record.py` | create | one case per legal transition and one per dead end | P3 |
| `app/privacy/ocr.py` | create | the typed OCR adapter — the only module that imports the OCR engine | P4 |
| `app/privacy/barcodes.py` | create | the typed 2D-symbol adapter — the only module that imports the barcode engine | P4 |
| `app/config.py` | modify | `privacy_engine_module`, `celery_task_always_eager`, `anthropic_api_key` and the test-only validator | P4, P6 |
| `.env.example` | modify | the three new variables, and the corrected S3 comment | P4, P6 |
| `pyproject.toml`, `poetry.lock` | modify | `rapidocr-onnxruntime`, `onnxruntime`, `zxing-cpp`, `anthropic` in the main group | P4, P6 |
| `Dockerfile` | modify | apt `libgl1 libglib2.0-0` beside `ca-certificates curl` | P4 |
| `tests/e2e/stub_engines.py` | create | the deterministic OCR and barcode engines the Playwright launcher loads | P4 |
| `tests/privacy/test_ocr.py`, `tests/privacy/test_barcodes.py` | create | the adapters' contracts, their failure modes and the stub seam | P4 |
| `app/privacy/identity.py` | create | normalisation, the OCR-substitution map, the six methods and the regex classes | P5 |
| `tests/privacy/test_identity.py` | create | the table-driven suite, including the OCR-error cases | P5 |
| `app/privacy/vision.py` | create | the Anthropic adapter: unavailable vs failed, bounded retries, redacted logging | P6 |
| `tests/privacy/test_vision.py` | create | every outcome of the adapter, and the log-redaction proof | P6 |
| `app/privacy/aggregate.py` | create | the region union, the expansion rules and the merge | P7 |
| `app/media/redact.py` | create | the opaque fill and the re-encode; the irreversibility properties | P7 |
| `tests/privacy/test_aggregate.py`, `tests/media/test_redact.py` | create | determinism, expansion, merge; per-pixel fill, dimensions, no metadata | P7 |
| `app/tasks/media.py` | create | `process_photo` and `sweep` — the only Celery entry points this adds | P8 |
| `app/tasks/celery_app.py` | modify | `include`, `task_routes`, the beat entry, the eager switch | P8 |
| `scripts/start.sh` | modify | `--queues=celery,media` | P8 |
| `scripts/reprocess_photos.py` | create | the operator's `--listing` / `--all-stale` staleness flag and enqueue | P8 |
| `tests/tasks/test_media.py`, `tests/scripts/test_reprocess_photos.py` | create | idempotency, the claim, the backoff ladder, the six sweeper rules, the operator script | P8 |
| `tests/test_celery.py`, `tests/scripts/test_start_sh.sh`, `.github/workflows/quality.yml` | modify | the widened registration/beat pins, the queue flag, the strict-mypy list | P8 |
| `tests/e2e/api_under_test.py`, `tests/e2e/test_api_under_test.py`, `frontend/tests/targets.ts`, `frontend/tests/targets.test.ts` | modify | the eager execution model and its two exports | P8 |
| `app/privacy/delivery.py` | create | `buyer_variant` — the one resolver, pure and total | P9 |
| `app/api/listings.py` | modify | the resolver in the bytes route and in `serialise`; `?v=`; `no-cache` + ETag; `seed_digests()`; the `visible_photos` aggregate | P9 |
| `app/api/admin_listings.py` | modify | the reviewer bytes route; the gate in `decide` | P9, P10 |
| `tests/privacy/test_delivery.py` | create | every (visibility × status × `buyer_visible` × key-present) cell | P9 |
| `tests/api/test_buyer_photo_delivery.py` | create | the §20 security matrix, path by path | P9 |
| `tests/api/test_listings.py`, `tests/perf/test_api_latency.py`, `tests/perf/test_query_plans.py`, `tests/test_storage.py`, `tests/test_static.py` | modify | the re-recorded header pins, the seller-arm budget, the new plan row, the presigning and static-fixture pins | P9 |
| `app/privacy/gate.py` | create | `photos_not_ready`, the two messages and the envelope's `photos` key | P10 |
| `tests/privacy/test_gate.py` | create | the predicate over every offender class | P10 |
| `tests/api/test_listing_privacy.py` | create | the scenario suite A–G, L–M, V–Z | P10, P12, P13 |
| `frontend/src/listings/step-fields.json` | modify | `showIdentifiable` under `"7"` | P10 |
| `tests/api/test_seller_listings.py`, `tests/api/test_admin_listings.py` | modify | the step-7 field, the flip, the gate at every publication path | P10 |
| `frontend/tests/design-amendments.ts` | modify | the family's entries — P11's nine, P12's six | P11, P12 |
| `frontend/tests/design-amendments.test.ts` | modify | `AMENDMENT_IDS`, the length pin, one case per surface | P11, P12 |
| `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html` | ⟳ | `npm run gen:design` | P11, P12 |
| `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md` | modify | one row per entry, in apply order, ruling quoted verbatim | P11, P12 |
| `frontend/src/logic.js` | ⟳ | re-ported by the python snippet | P11, P12 |
| `frontend/src/App.vue`, `frontend/src/generated/pseudo.css` | ⟳ | `npm run gen:app` | P11, P12 |
| `frontend/src/app.setup.js` | modify | the `startWizardPhotos` prototype prop declaration (prop parity) | P11 |
| `frontend/src/logic.test.ts` | modify | the family's characterisation block | P11, P12 |
| `frontend/src/listings/seller.ts`, `frontend/src/listings/seller.test.ts` | modify | the draft's new photo fields, and the four new adapter methods | P11, P12 |
| `frontend/tests/design-wizard-draft.mjs` | modify | the harness draft stub's `state: "review"` tiles | P11 |
| `frontend/tests/screens.ts`, `frontend/tests/reference-baselines.spec.ts` | modify | `wizard-step-6-photos`, `wizard-step-6-review`; `placeholderRings` | P11, P12 |
| `frontend/tests/baseline-manifest.json`, `frontend/tests/baseline-manifest.test.ts` | ⟳ / modify | one row re-pinned (`wizard-step-7`) with its reason | P11 |
| `CLAUDE.md` | modify | the family clause, the two derived counts, the approved-state count | P11, P12 |
| `docs/design-reference/requests/2026-09-08-rev3-listing-disclosure-controls.md` | modify | the fifth "What Rev 3 must design" item | P11 |
| `frontend/tests/listing-flows.spec.ts` | modify | the NOT_SHOW journey, the blocked Submit, scenarios O/S/T/U | P12, P13 |
| `docs/RUNBOOK-image-privacy.md` | create | the operator's page for a photograph that will not process | P14 |
| `tests/test_docs.py` | modify | the documentation pins and `test_the_identifiability_copy_makes_no_detection_claim` | P1, P4, P6, P8, P11, P14 |

---

## Pre-flight — every gate this change touches

| Gate | Where | What this plan does to it | Action |
|---|---|---|---|
| Backend coverage 100, branch, `-W error` | `poetry run pytest …` | eleven new `app/` modules and four new routes | every branch has a test in the task that writes it |
| Strict mypy | `poetry run mypy app --strict` | the engines ship no stubs; the adapters are the only importers and they cast at their own boundary once, with the reason in a comment | no new blanket ignore; celery's existing two are untouched |
| Strict mypy over scripts | `.github/workflows/quality.yml:63` | `scripts/reprocess_photos.py` joins the list | P8 edits the line and `tests/test_docs.py::test_ci_strict_mypy_covers_every_python_script` proves it |
| ruff, no ignores | `poetry run ruff check app tests scripts` | RUF001 refuses an en dash in a source literal — every new message uses a hyphen-minus | run it in every task |
| Migration ledger + immutability | `scripts/migrate.py`, `tests/test_migrate.py` | three new files, single transactional DDL, no `CREATE INDEX CONCURRENTLY`, no `BEGIN`/`COMMIT` | P1; never edit an applied file |
| Migration numbering paragraph | `DEPLOY.md`, `tests/test_docs.py::test_deploy_md_says_an_applied_migration_is_immutable` and the Migrations-section assertions | the `017`–`059` clause is rewritten to name `030`–`039`, `040`–`049` and SP3-A's remainder | P1, with the Census plan's `:42`/`:62` in the same commit |
| `cross-plan-deltas.test.ts` | reads the Census plan | the A-C12 edit changes text it reads | run `npx vitest run tests/cross-plan-deltas.test.ts` first in P1 |
| Route guard drift | `tests/auth/test_permissions.py::test_every_route_is_guarded_or_public` | six new routes | one module-level `require(...)` constant each, resolved by object identity |
| Audited-action drift | `::test_audited_permissions_are_written_by_their_handlers`, `::test_every_audited_action_is_named_after_a_permission` | `listing.privacy` is written by handlers guarded by `listing.manage_own`, which is **not** in `AUDITED` — the drift test never sees it, exactly as `listing.submit` and `listing.edit` are not seen | nothing is added to `AUDITED`, `MULTI_ACTION_PERMISSIONS` or `CASCADED_ACTIONS`; P10 records why |
| The decline-reason subquery | `seller_listings.py` `_COLUMNS` reads the latest `audit_log` row whose `after ->> 'status' = 'declined'` | a `listing.privacy` row that carried a `status` key would corrupt it | every `listing.privacy` `before`/`after` carries `identifiable_content_visibility` only; pinned by a test in P10 |
| Rate limits, unchanged | `app/auth/limits.py` | the new routes reuse `LISTING_PATCH` (confirm, masks) and `LISTING_UPLOAD` (reprocess); nothing is loosened | scenario C uses `scripts/reset_rate_limits.py` between batches, never a raised limit |
| Redis list cache | `drop_list_cache` after commit | every visibility change, confirmation, mask change and derivative completion drops it | P9, P10, P12; the `:733-806` spy pattern proves the ordering |
| Query plans | `tests/perf/test_query_plans.py::PLANS` | the buyer route's privacy join and the list route's `visible_photos` aggregate | P9 adds one `PLANS` row each and keeps `GET /api/listings` at one statement |
| Latency budgets | `tests/perf/test_api_latency.py::LISTINGS_BUDGET_MS` | `photo: 150` measures the seed arm only today | P9 adds a moto-backed seller-arm case under the same budget |
| Celery registration + beat set-equality | `tests/test_celery.py:37-38`, `:43-45` | `include` gains `app.tasks.media`; beat gains `media-sweep-5min` | P8 widens both pins in the same commit, through `conf.beat_schedule.update(...)` (A-C0 ¶2), never a second `beat_schedule=` kwarg |
| `start.sh` flag pin | `tests/scripts/test_start_sh.sh` | `--queues=celery,media` | P8 |
| Settings documentation | `tests/test_docs.py::test_every_setting_is_documented_in_env_example_and_deploy_md` | three new settings | P4 (two) and P6 (one), each with its `.env.example` and `DEPLOY.md` row in the same commit |
| Variable-names-only rule | `::test_claude_md_lists_variable_names_only`, `::test_working_docs_carry_the_railway_status_rule_and_the_key_handling_rule` | `ANTHROPIC_API_KEY` is named, never valued | P6, P14 |
| Amendment engine | `design-amendments.test.ts` (pristine hash, apply-order counts, the citation chase, the doubled-blank-line rule, the six metro-dismissal sites, the `out`/`down` closure substrings, the `<select>`/Montserrat/`View full listing`/`@font-face`/`role="menuitem"` counts, the display-heading census, the `font-family` walk) | one new family, appended last | P11 and P12 each run the whole file and read any failure to zero |
| `V3:<line>` citation freshness | `design-amendments.test.ts`'s citation case | P11 and P12 insert template and script lines, so citations below the first insertion go stale | recompute every row's `V3:<line>` in P11 Step 8 and again in P12 Step 7 |
| CLAUDE.md family/entry counts | `tests/test_docs.py::test_claude_md_amendment_family_and_entry_counts_match_design_amendments` | both counts move twice | derived by the Preconditions snippet; `number_words` extended if the family count outruns it |
| `LOCAL_AMENDMENTS.md` row count | `::test_local_amendments_row_count_matches_design_amendments` | `literal_count + 1` | rows appended last, in list order |
| CLAUDE.md approved-state count | `::test_claude_md_approved_screen_count_matches_screens_ts` | two states appended | count with `grep -c "^  { name: '" frontend/tests/screens.ts` and write that number |
| `app-generated.test.ts` | `logic.js` byte-identity, `App.vue`/`pseudo.css` byte-identity, Vue compile, **prop parity** | one new prototype prop, `startWizardPhotos` | P11 declares it in `app.setup.js` and the design in the same commit; the app never passes it |
| First-28-states order | `cross-plan-deltas.test.ts` `SCREENS.slice(0, 28)` | the two states are appended | append only |
| Visual + DOM oracle | `visual.spec.ts` at `maxDiffPixels: 0`, `dom.spec.ts` | `wizard-step-7` re-bases once; two states are added | P11 Step 9, P12 Step 8 |
| The thirteen frozen hashes | `baseline-manifest.json` / `.test.ts` | **P11: exactly `wizard-step-7`. P12: zero.** | P11 Step 9 re-pins with the reason in the header; anything else moved is a leak — STOP |
| Bundle budget | `bundle-budget.test.ts` | the dialog and the tiles grow the main bundle by well under 2 KB gz | `npm run build` before `vitest` |
| Sign-in budget | `harness.ts`, `tests/test_docs.py` | the two new states are seller-family and reuse the seller's session jar | unchanged; verify the trace count did not move |
| Image size | `docker images`, the commit body, `DEPLOY.md` | the OCR stack is the only dependency change in its commit | P4 measures before and after and quotes both, the `f454fe7` precedent |
| Honesty copy | `tests/test_docs.py::test_the_identifiability_copy_makes_no_detection_claim` | new | P14 writes it; every earlier task's prose already obeys it |
| Shared test fixtures | `tests/api/test_listing_assets.py`'s own `store` fixture; `tests/api/conftest.py` | the moto fixture is promoted to `tests/conftest.py` so three suites outside `tests/api/` can reach a bucket, and three signed-header fixtures are added | P2 Step 0, before any feature code; `tests/conftest.py::_no_stray_network`'s cross-reference to the guard moves with it |
| The api's import surface | new, `tests/api/test_import_surface.py` | the eager branch (A-IDP-2) names `app.tasks.media` inside a function | P8 Step 6 pins at run time that `create_app()` loads no engine wheel and no task module; the gate runs that file alone as well as in the suite |
| Retired numbers | `::test_no_tracked_text_file_cites_a_retired_number` | nothing written here spells either pattern | verified before every commit |
| Relative markdown links | `::test_relative_markdown_links_resolve` | `DEPLOY.md` gains a relative link to `docs/RUNBOOK-image-privacy.md`, and the runbook links back to the spec and to this plan (P14 Step 2) — those three links are the whole of what this pin covers here. Every path reference in THIS document is a backticked path and not a link, so the pin says nothing about them | P14 writes the three links; the check runs before every commit |

---

## The tasks

Fourteen, each ending in an independently testable deliverable and its own commit. `P1`–`P10` are backend and can be reviewed without a browser; `P11`–`P12` are the design amendments; `P13` is John's §21 scenario suite; `P14` is the documentation, the runbook and the hand-back.

---

## Controller amendment A-IDP-3 (2026-09-09 ~19:25 WITA; the targeted verification of the six blocking fixes — five VERIFIED, one PARTIAL, three deviations ratified)

**(1) The one real gap — a fourth writer of a published listing, and the lesson under it.** P1's Step 6b says "exactly three" writers must satisfy the new publish trigger; the verification found a fourth: `tests/api/test_listings.py`'s module-level `INSERT` template and its `_insert()` helper (line 24 and following) insert `status = 'published'` with `photos` holding seed PATH entries and no visibility column, so five of that file's tests would be refused by the trigger the plan itself adds. **The rule, and it is a rule rather than a list:** the trigger's readiness predicate treats a seed path entry — a photograph with no `listing_asset` row, served from disk — as ready under `SHOW` and NOT ready under `NOT_SHOW`, because a seed photograph has no redacted derivative and never silently gets one. Every writer that publishes a row carrying path photographs therefore sets `identifiable_content_visibility = 'SHOW'` explicitly, exactly as the seeder now does: `scripts/seed_listings.py` (both halves of its UPSERT), `tests/api/test_listings.py`'s template and `_insert()`, `tests/api/test_listing_assets.py`'s `_publish`, and anything else the enumeration finds. **P1 Step 6b is rewritten to ENUMERATE rather than assert:** it greps for `INSERT INTO listing` and for `status` set to `'published'` across `scripts/`, `tests/` and `app/`, lists every hit in the report with its disposition, and adds a `tests/test_docs.py` pin that fails when a new writer of a published listing row appears without a visibility value — so the next writer cannot be missed the way this one was. The claim "exactly three" is deleted; a count asserted in prose is exactly the kind of thing this programme has been caught by twice today.

**(2) The three deviations are RATIFIED as the fix pass proposed them**, each for the reason it gave and each verified: `buyer_variant` takes the seed digest as a fourth argument and `seed_digests()` lives in `app/api/listings.py` (the import cycle is real — `seller_listings` already imports from `listings` one way); `app/privacy/record.py` is a ninth module the spec's §C.5 list does not name (recorded as A-IDP-1, sound); and P14's honesty test scopes its patterns to Markdown prose with code fences and spans stripped, plus the three copy surfaces, because the unscoped form trips on the specification's own §H sentence and on `frontend/tests/capture-determinism.spec.ts` — the scoped form still bites where it must. A-IDP-2 (the eager branch through `apply_async`, behind a setting the config refuses outside `ENVIRONMENT=test`) is likewise ratified: celery 5.6.3's own source confirms `send_task` ignores `task_always_eager` while `apply_async` honours it.

**(3) The two cosmetic corrections:** the module count reads nine, not eight; and P9's `variant` field names the consumer that reads it (the review dialog's own state, P12) so no field is produced without a reader.

**(4) Everything else in the verification held:** the draft payload's six tile fields are produced and consumed under identical names; the buyer list aggregate joins `listing_asset` so a SHOW listing's photographs survive; `A-C12` is genuinely free where `A-C10` and `A-C11` are spent; and seven pytest snippets across six tasks match the merged suite's async idiom and its fixture names. **Execution remains blocked on the two merge preconditions** (the seller lifecycle branch and the photo lightbox branch), whose SHAs P1 Step 0 re-derives.

**Controller amendment A-IDP-4 (2026-09-10 ~04:45 WITA; John's ruling "Default → NOT SHOW, including all 18 seeds" — it overrules D-IDP-2 and spec §C.10, and this records what changes).** The plan, following the spec's C.10, had the seeder write `SHOW` for the eighteen demo hospitals and migration `040` back-fill `SHOW` onto every listing whose `photos` array holds a path entry, on the reasoning that a seed photograph has no asset row and therefore no derivative, so `NOT_SHOW` would hide it. John has ruled the other way, knowing that consequence: the seeds are listings like any other and start `NOT_SHOW`. **Five consequences, each binding on the task named:**
**(1) No `SHOW` is written for a seed anywhere (P1).** Migration `040` loses its `UPDATE … SET identifiable_content_visibility = 'SHOW'` statement entirely; `scripts/seed_listings.py`'s UPSERT does not name the column in either half (the column's own default applies); `tests/api/test_listing_assets.py`'s `_SEED_INSERT` and `_publish` do not name it either; the test `test_a_seed_path_entry_passes_under_show_and_is_an_offender_under_not_show` keeps its NOT_SHOW half and drops the premise that a seed is ever SHOW. Spec §C.10 is annotated as overruled, not rewritten.
**(2) The publish gate fires only on the transition INTO `published` (P1, migration `042`).** `WHEN (OLD.status IS DISTINCT FROM 'published' AND NEW.status = 'published')`. An update of a row that is already published — the seeder's `DO UPDATE SET` on a re-seed, a seller's partial save on a claimed hospital, a caption edit — is never refused by this trigger. Without this the ruling would make every seeded hospital un-editable and un-reseedable the moment `042` applied, which is the trap D-IDP-2's rationale described. Tests: a re-seed of a published seed row succeeds; a draft with an unprocessed photograph is refused at the moment it becomes published; a published row with an unprocessed photograph accepts an unrelated column update.
**(3) Seed photographs enter the one pipeline as assets (P2 for the shared helper, P8 for the seeder's use of it).** When `ObjectStore.from_settings(settings)` is not `None`, the seeder ingests each seed photograph exactly as an upload is ingested: the original bytes to the store under the upload key scheme, a `listing_asset` row, a privacy row in `UPLOADED`, and `process_photo(asset_id)` enqueued after the transaction commits — through the SAME function the upload route calls, so there is one pipeline and no seed-only code path to drift. The listing's `photos` entry becomes the asset reference in that slot; `source = 'seed'` on the listing is untouched, so the existing `WHERE listing.source = 'seed'` guard still protects a claimed hospital from a re-seed. Idempotent: a photograph whose sha256 already has an asset on that listing is not ingested twice (`seed_digests()` is the inventory). When no store is configured, the seeder leaves the path entries as they are and prints one plain line naming that fact — never a stack trace, never a silent success. The per-image `flags` in `seeds/hospitals/photos/index.json` are the EXPECTATION SET for this ingestion, under the flag-to-detector mapping recorded in A-IDP-7 (6).
**(4) The resolver does not change in principle (P9).** A path entry under `NOT_SHOW` has nothing servable and answers 404, which is the fail-closed rule the plan already had; `seed_digests()` and the `?v=` digest stay for the SHOW arm that no seed reaches today and for the oracle. What changes is only that this arm is now the seeds' actual state on QA until they are processed and confirmed.
**(5) The QA consequence, stated so nobody is surprised (P13 scenario, P14 runbook).** After this sub-project deploys, the eighteen hospitals show the design's empty photo slots until three things happen in order: the four `S3_*` variables are set on the QA worker (D-S3-QA2, John's), a re-seed ingests the 195 photographs and the worker processes them (OCR and the 2D-symbol scan offline in the worker, vision through the Anthropic API from the worker only — A-IDP-5), and the seller persona confirms each hospital's photographs in the wizard's review dialog (P12), because the directive makes seller confirmation part of the state machine and the seeds now follow it. John accepted this consequence in the ruling itself. P13 gains one scenario walking a seeded hospital from hidden to confirmed; P14's runbook gains the re-seed step after `S3_*`.

**Controller amendment A-IDP-5 (2026-09-10 ~04:45 WITA; John's four other rulings on this sub-project, verbatim, each already the plan's design and now confirmed rather than assumed).** "GO — Anthropic vision analysis" closes D-IDP-1: the vision adapter (P6) is the Anthropic API. "ANTHROPIC_API_KEY → Railway worker secret only" confirms Global Constraint (h): John sets it on the QA worker himself; the api never reads it; it is never in chat, git, a log or a report. "QA before production" confirms the release posture: this sub-project proves on QA and production waits for a separate word. "OCR → offline worker" confirms Global Constraint (i) and P4: OCR runs in the Celery media worker with the baked models, never on the request path and never off-platform. Nothing in the tasks changes for these four; they are recorded so that no later reviewer treats them as open.

**Controller amendment A-IDP-6 (2026-09-10 ~06:20 WITA; the seeder cannot insert a published seed under A-IDP-4 as first written — the gate narrows to the seller's transition).** A-IDP-4 (2) had migration `042` fire on the transition into `published` AND on a row inserted directly as `published`. Under NOT_SHOW a seed photograph is a path entry with no derivative, so it is "not ready" by the trigger's own definition — and `scripts/seed_listings.py` inserts every seed directly as `published`. On a fresh database the seeder would therefore be refused for all eighteen hospitals, and every test helper that inserts a published seed (`_SEED_INSERT` in two test modules) was refused the same way: that is what the first P1 gate's 98 failures were. The first fix attempt wrote `SHOW` (the breach A-IDP-4 forbids); the second demoted the helpers' rows to `draft`, which breaks every test that reads a PUBLISHED seed's photographs and hard-codes a parameterised status. Neither is the answer. **The ruling:** `042` fires **only on an UPDATE that moves a row into `published`** — `CREATE TRIGGER … BEFORE UPDATE OF status … WHEN (OLD.status IS DISTINCT FROM 'published' AND NEW.status = 'published')` — and not on INSERT at all. A direct INSERT as `published` exists on exactly one path, the seeder (and its test double), and the seeds' photographs are protected where it matters: at delivery, where a path entry under NOT_SHOW is unservable and answers 404 (A-IDP-4 (4)). The gate's purpose is the seller's publish transition, and that is exactly what it still guards. **What changes in P1:** the trigger loses its INSERT arm and gains the `WHEN` clause; `_SEED_INSERT` in `tests/api/test_listing_assets.py` and in `tests/api/test_seller_listings.py` keeps its ORIGINAL status (`'published'` / the `%(status)s` parameter) and names no visibility column; the A-IDP-4 (2) tests become: a re-seed of a published seed row succeeds; a draft with an unprocessed photograph is refused when it becomes published; a published row with an unprocessed photograph accepts an unrelated update; and one more that documents the choice — a direct INSERT as `published` with path-entry photographs is NOT refused, and (until P9 lands) the plan records that its photographs are hidden by the resolver. Nothing else in A-IDP-4 changes.

**Controller amendment A-IDP-7 (2026-09-10 ~20:15 WITA; John's ruling on the street numbers rendered into the Dallas seed photographs — a number worn as signage is part of the invented identity and is governed by the listing's one switch).** John, verbatim: *"the numbers are part of the hospital name and should be 'shown/not shown' too"*. He was answering the "4140" on the fascia beside the invented name ALPHA DALLAS VETERINARY SPECIALIST HOSPITAL, on a listing whose anchor address is `18770 Preston Rd` — an invented number beside an invented name. The ruling settles three things and no more. Such a number is **not** grounds to refuse a photograph from the seed set. It is **not** kept unconditionally either: under `NOT_SHOW` it is painted out of `redacted.webp` exactly as the name is (spec §C.5 step 6, `FILL = (0, 58, 112)`, "Never blur, pixelate or mosaic"), never withheld as a file. And the obligation is server-side (directive :404-411). It does **not** reach a real STREET NAME rendered beside the number; it does **not** reach a name that is not this listing's; and it does **not** assert that the pipeline already detects numbers — it creates a detection obligation that the specification does not discharge today, and closing that is what this amendment is for.

**The finding of fact that makes the mechanism what it is: the "one consistent invented number per hospital" premise is FALSE.** A second reading of the eleven Dallas folders contradicted the first reader's table, and the first reader quoted no file the second failed to open. Charlie's vertical number ends in a round hollow glyph in `charlie_dallas_01.png` and in a narrow stem in `charlie_dallas_03.png` and `charlie_dallas_11.png` — round versus stem survives that resolution whatever the digits turn out to be. Juliet reads `2211` on the keystone and the pilaster and `22113` on the glass door. Four hospitals — Beta `2101`, Echo `7210`, Foxtrot `5530`, Kilo `2420` — show a number exactly once each, and a single appearance cannot demonstrate consistency. Three — Delta, Indigo, Lima — show none at all. **A rendered number is therefore a property of an INDIVIDUAL IMAGE and never a per-hospital fact**, and John's ruling is discharged by **per-image detection plus the per-listing visibility switch, and by nothing else**: no column is added, no per-hospital number constant is introduced, and no listing's `street` is ever rewritten to match a sign. Because three hospitals render no number at all, no rule may assume one exists.

**Why nothing in the pipeline catches it today, on four independent paths.** The directive's content classes name "street addresses" (:99) and "street/building signage that identifies the location" (:125); neither is a bare number, and :125 is qualified by "that identifies the location". No regex class reaches it — `phone` needs ten digits, `zip` needs five, `address` needs a street-type token — so `4140` fires nothing, and Alpha's own anchor number `18770` would fire `zip` only by the accident of its length. The identity matcher cannot reach it for a prior reason: `identity_terms` builds its terms from `name/street/city/state/zip/phone/slug`, the prose fields' tokens, the email domain and the abbreviations, and a number belonging to no column is reachable by no threshold; `_informative` and `DISTINCTIVE = 5` refuse it twice over even if it were. And it is unrecorded rather than merely unfilled: `regions_for` iterates the lines that carry a match, so a line with neither an identity match nor a regex hit produces no `detected_regions` entry at all — it never reaches the seller's review outlines or the audit record, and the 8 px merge can only sweep it up by a neighbour's geometry. Vision is the one live path and it is unspecified for this case: the prompt carries the name, city and state only, the street is deliberately withheld and that withholding is pinned by `test_the_prompt_carries_the_name_city_and_state_and_never_the_phone_or_street`, and "could let a reader identify this specific practice" gives a model no basis to act on a number beside a fictional name. No test asserts a number is returned. **Unverified, and it must not be relied on.**

**Six consequences, each binding on the task named:**
**(1) The specification gains a seventh regex class, and its `address` arm is corrected (spec §C.5 step 2).** The class enumeration now reads: NANP phone, URL/domain, email, street address (a street number followed by a street-type token, **or** a bare `Suite|Ste` with no number in front of it), **premises number**, social handle, five-digit ZIP — each hit an identifying region regardless of matching. The `address` correction is a second finding of the same review: the spec's inline pattern put `Suite|Ste` behind a required `\d+\s+\w+\s+` prefix and so would not have matched "Suite 210", which the plan's own second arm had already been silently correcting. Unchanged beside the seventh class: the identity matcher's fields (§C.5 step 3), every 2D symbol under `NOT_SHOW` (§C.5 step 2b), and the vision `kind` enum (§C.5 step 4) — `signage` and `text` already cover a number, and widening the enum would churn `VISION_SCHEMA` and every fixture for nothing.
**(2) P5's interface line names it.** `REGEX_CLASSES: dict[str, re.Pattern[str]]` — `phone`, `url`, `email`, `address`, `premises_number`, `handle`, `zip`.
**(3) P5's Step 1 RED gains the rows the evidence actually holds.** Three positives in the regex-class parametrisation — `("4140", "premises_number")`, `("22113", "premises_number")` (Juliet's divergent string) and `("2101", "premises_number")` — and a negative parametrisation in the same block asserting **no** `premises_number` hit for `"EST. 2017"`, `"EXAM ROOM 1"`, `"24/7"`, `"Open 7 days"` and `"1"`. `MISSES` is deliberately not the place for these: its test excludes regex matches, and its `"(512) 555-9999"` row proves the two layers are separated, not that a foreign number escapes.
**(4) P5's Step 2 GREEN gains the pattern, and the two-step redefinition is folded away.** `"premises_number": re.compile(r"\A\s*\d{2,6}\s*\Z")` — WHOLE LINE, two to six digits, so an interior is not blanketed: "EST. 2017", "EXAM ROOM 1" and "24/7" carry other tokens and are not premises numbers, and where a number shares a line with the practice's own name the identity match already makes the whole line one region. The corrected `address` arm moves into the dict literal in the same edit, so the module has one definition of each class rather than a literal followed by a rebinding.
**(5) P6's prompt enumerates numbers.** The vision prompt's list of what to look for gains "street or building numbers". The prompt DATA is unchanged — `PROMPT_FACTS` stays name, city and state, and `test_the_prompt_carries_the_name_city_and_state_and_never_the_phone_or_street` stays exactly as written — and the `kind` enum is unchanged.
**(6) Under A-IDP-4 (3): `index.json`'s `flags` are the EXPECTATION SET for the seeds' first real ingestion.** A-IDP-4 (3) has the seeder ingest every seed photograph as a real asset through the one pipeline. The Dallas branch's per-image `flags` in `seeds/hospitals/photos/index.json` are what that ingestion is expected to produce, so the eleven Dallas hospitals become the pipeline's first real fixture instead of 119 images somebody re-reads by eye. The contract is this mapping, and it is the reason a flag is a testable expectation rather than a note beside the pipeline:

| seed flag | expected detector outcome |
|---|---|
| `own_business_name` | identity match on field `name` (`exact` / `substring` / `distinctive`) — spec §C.5 step 3 |
| `own_street_number` | regex class **`premises_number`** — spec §C.5 step 2 as amended here |
| `address_not_this_listing` | regex class `address` — spec §C.5 step 2 |
| `civic_signage` | vision `kind: signage`, expected NOT to identify the practice — spec §C.5 step 4 |
| `vehicle_no_legible_plate` | vision `kind: vehicle` — spec §C.5 step 4 |
| `certificates_text_unreadable` | vision `kind: document` — spec §C.5 step 4 |
| `composite` | none — a slot-placement fact only (`scripts/prepare_photos.py`) |

The seed flags are **not** made to match the detector class names word for word, and must not be: the spec's classes are detector OUTPUTS describing what a machine found, while the flags are human findings about a source image, and two of them — `own_business_name` and `own_street_number` — assert PROVENANCE ("this identity is the listing's own invention"), which no detector class can express and which is the whole reason those images stayed in the set. The flag vocabulary and the mapping's two-way pin are the seed branch's to write; this amendment fixes the contract they are written against.

**P2 onward owns, and must not be pulled forward by this amendment:** implementing `premises_number` in `app/privacy/identity.py` (P5); the vision prompt (P6); expansion, merge and fill (P7); `buyer_variant` and the delivery surface (P9); the wizard and the review dialog (P11/P12); and the QA proof that a seeded hospital's number is filled under `NOT_SHOW` and visible under `SHOW` (P13/P14). **Explicitly NOT authorised:** any per-photograph visibility control (directive :281, "Do not create contradictory per-image privacy settings"); any change to `buyer_variant`'s contract; any widening of the vision `kind` enum.

### Task P1: migrations `040`–`042`, the schema contract, and the Census range carve-out

**Files:**
- Create: `migrations/040_listing_identifiable_content_visibility.sql`
- Create: `migrations/041_listing_asset_privacy.sql`
- Create: `migrations/042_listing_publish_photos_ready_trigger.sql`
- Create: `tests/test_listing_privacy_schema.py`
- Create: `docs/superpowers/specs/2026-09-09-image-identifiability-directive.md` (John's directive, verbatim)
- Modify: `scripts/seed_listings.py` (the UPSERT's two halves), `tests/scripts/test_seed_listings.py`, `tests/api/test_listing_assets.py` (`_SEED_INSERT` and `_publish`)
- Modify: `DEPLOY.md` (the Migrations numbering paragraph), `docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md` (`:42` numbering line, `:62` D14 row)
- Unchanged: `scripts/migrate.py` — all three files are single transactional DDL

**Interfaces:**
- Consumes: `migrations/016_listing.sql` (`listing`), `migrations/030_listing_owner_and_status.sql` (`status`, the two publishability CHECKs), `migrations/031_listing_asset.sql` (`listing_asset(id)`), `migrations/010_accounts.sql` (`account(id)`), `tests/conftest.py`'s `conn` fixture.
- Produces, on `listing`: `identifiable_content_visibility text NOT NULL DEFAULT 'NOT_SHOW' CHECK (… IN ('SHOW','NOT_SHOW'))`.
- Produces, new table `listing_asset_privacy` with exactly these columns, spelled as every later task spells them: `asset_id`, `listing_id`, `processing_status`, `processing_version`, `attempts`, `last_error`, `original_storage_key`, `redacted_storage_key`, `redacted_sha256`, `confirmed_sha256`, `ocr`, `identity_matches`, `vision`, `detected_regions`, `redaction_regions`, `detection_at`, `seller_review_status`, `seller_confirmed`, `seller_confirmed_at`, `seller_confirmation_account_id`, `buyer_visible`, `final_privacy_state`, `reprocess_reason`, `reprocess_requested_at`, `reprocessed_at`, `created_at`, `updated_at`; CHECKs `lap_confirmed_ck`, `lap_stale_ck`, `lap_status_confirmed_ck`, `lap_visible_ready_ck`, `lap_ready_has_derivative_ck`, `lap_never_the_original_ck`; indexes `listing_asset_privacy_listing_idx`, `listing_asset_privacy_sweep_idx`.
- Produces, new SQL: `listing_photos_not_ready(l_id uuid, visibility text, photos jsonb) RETURNS TABLE (entry text, status text)` and trigger `listing_publish_photos_ready`.
- The eleven `processing_status` values and the three `reprocess_reason` values are the vocabulary every later task uses; nothing may add a twelfth without a new migration.

- [ ] **Step 0: the worktree, its environment, and the derived numbers**

```bash
cd "/Users/johndean/Development/Practice Match"
git worktree add .worktrees/feat-image-identifiability -b feat/image-identifiability <MERGE_SHA>
cd .worktrees/feat-image-identifiability
docker compose -f docker-compose.dev.yml up -d      # the ONE shared stack — never a second
psql "postgresql://pm:pm_dev_pw@localhost:5433/postgres" -c 'CREATE DATABASE practice_match_privacy'
```

Every command in every task runs with this environment exported, and nothing is ever pointed at `practice_match`, the shared dev database (`tests/conftest.py::db_ready` migrates whatever `DATABASE_URL` names, and `frontend/tests/targets.ts`'s api web server runs `migrate.py` + `reset_rate_limits.py` + `seed_persona.py` against it too; process env beats its defaults):

```bash
export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_privacy
export REDIS_URL=redis://localhost:6380/9
export ENVIRONMENT=test
export API_SECRET_KEY=local_only_secret_change_me
export PW_APP_PORT=5573 PW_REF_PORT=5574 PW_CS_PORT=5575 PW_API_PORT=8147
lsof -nP -iTCP:5573,5574,5575,8147 -sTCP:LISTEN || true    # expect nothing — `reuseExistingServer: !CI` would adopt any process it found
```

Redis `/9`: `targets.ts` defaults to `/0`, the metro plan used `/6`, the seller plan `/7`, the lightbox plan `/8`. Ports 5573–5575/8147 are this worktree's alone. Run the `lsof` line before **every** Playwright run, and stop a stray process by the PID it prints — never `pkill` by substring (Global Constraint (l)).

- [ ] `cd frontend && npm ci && cd ../coming-soon && npm ci && cd ..` (node_modules are per checkout; `npm run build` builds both sites).
- [ ] Run the Preconditions block. Record its four derived numbers — the next free family id, the literal-entry count, A1's derived count, the approved-state count — in `.worktrees/feat-image-identifiability/NOTES.derived` (git-ignored; it is a scratch note, never committed).
- [ ] Re-derive every `file:line` anchor this plan quotes, by grepping the quoted text against the merged tree, and record any that moved in the same note. An anchor whose text is absent is `NEEDS_CONTEXT`.

- [ ] **Step 1: RED — the schema contract for the listing column**

Create `tests/test_listing_privacy_schema.py`:

```python
"""The image-identifiability schema contract (spec 2026-09-09 §C.1, §C.3, §C.8; migrations 040-042).

`tests/test_listing_schema.py` owns `listing` and `listing_asset`; this file owns the column
migration 040 adds and the whole of `listing_asset_privacy`, so a change to either is a deliberate
edit here rather than a silent widening somewhere else."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import psycopg2
import pytest

VISIBILITIES = ("SHOW", "NOT_SHOW")

STATUSES = (
    "UPLOADED", "PROCESSING", "SCANNED", "REDACTION_GENERATED", "READY_FOR_REVIEW",
    "SELLER_CONFIRMED", "PUBLISHED", "PROCESSING_FAILED", "REDACTION_FAILED",
    "REVIEW_REQUIRED", "REPROCESS_REQUIRED",
)

EXPECTED_PRIVACY_COLUMNS: dict[str, tuple[str, bool]] = {
    "asset_id": ("uuid", False),
    "listing_id": ("uuid", False),
    "processing_status": ("text", False),
    "processing_version": ("integer", False),
    "attempts": ("integer", False),
    "last_error": ("text", True),
    "original_storage_key": ("text", False),
    "redacted_storage_key": ("text", True),
    "redacted_sha256": ("text", True),
    "confirmed_sha256": ("text", True),
    "ocr": ("jsonb", False),
    "identity_matches": ("jsonb", False),
    "vision": ("jsonb", False),
    "detected_regions": ("jsonb", False),
    "redaction_regions": ("jsonb", False),
    "detection_at": ("timestamp with time zone", True),
    "seller_review_status": ("text", False),
    "seller_confirmed": ("boolean", False),
    "seller_confirmed_at": ("timestamp with time zone", True),
    "seller_confirmation_account_id": ("uuid", True),
    "buyer_visible": ("boolean", False),
    "final_privacy_state": ("text", True),
    "reprocess_reason": ("text", True),
    "reprocess_requested_at": ("timestamp with time zone", True),
    "reprocessed_at": ("timestamp with time zone", True),
    "created_at": ("timestamp with time zone", False),
    "updated_at": ("timestamp with time zone", False),
}


def _rows(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def _listing(conn: Any, slug: str, *, status: str = "draft", photos: list[str] | None = None) -> Any:
    """A row complete enough for `listing_publishable_ck` (migration 030), because every trigger
    case below publishes one. `tests/api/test_listing_assets.py` builds the same shape."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, status,"
            " est, price, zip, photos)"
            " VALUES (%s,'A','X','TX','X','Other','X, TX','seller',%s,1998,100,'78613',%s::jsonb)"
            " RETURNING id",
            (slug, status, json.dumps(photos or [])),
        )
        return cur.fetchone()[0]


def _asset(conn: Any, listing_id: Any) -> Any:
    asset_id = uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing_asset (id, listing_id, kind, name, content_type, byte_size, sha256, storage_key)"
            " VALUES (%s,%s,'photo','a.webp','image/webp',10,'d',%s)",
            (asset_id, listing_id, f"listings/{listing_id}/photos/{asset_id}/display.webp"),
        )
    return asset_id


def _privacy(conn: Any, asset_id: Any, listing_id: Any, **overrides: Any) -> None:
    columns = {"asset_id": asset_id, "listing_id": listing_id, "processing_version": 1,
               "original_storage_key": f"listings/{listing_id}/photos/{asset_id}/original.jpg", **overrides}
    names = ", ".join(columns)
    holders = ", ".join(["%s"] * len(columns))
    with conn.cursor() as cur:
        cur.execute(f"INSERT INTO listing_asset_privacy ({names}) VALUES ({holders})", tuple(columns.values()))


def test_the_listing_carries_one_authoritative_visibility_defaulting_to_not_show(conn: Any) -> None:
    """Directive 7: "The listing must have a single authoritative setting ... Default: NOT_SHOW.
    The safest privacy state is the default." """
    listing_id = _listing(conn, "idp-default")
    assert _rows(conn, "SELECT identifiable_content_visibility FROM listing WHERE id = %s", (listing_id,)) == [("NOT_SHOW",)]
    for value in VISIBILITIES:
        with conn.cursor() as cur:
            cur.execute("UPDATE listing SET identifiable_content_visibility = %s WHERE id = %s", (value, listing_id))
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute("UPDATE listing SET identifiable_content_visibility = 'MAYBE' WHERE id = %s", (listing_id,))


def test_the_privacy_table_has_exactly_the_contracted_columns(conn: Any) -> None:
    found = {
        name: (dtype, nullable == "YES")
        for name, dtype, nullable in _rows(
            conn,
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns"
            " WHERE table_name = 'listing_asset_privacy'",
        )
    }
    assert found == EXPECTED_PRIVACY_COLUMNS
```

- [ ] `poetry run pytest tests/test_listing_privacy_schema.py -q -W error` — RED. Expected: `psycopg2.errors.UndefinedColumn: column "identifiable_content_visibility" of relation "listing" does not exist` on the first case and `assert {} == {...}` (an empty `found`) on the second.

- [ ] **Step 2: GREEN — `migrations/040`**

Create `migrations/040_listing_identifiable_content_visibility.sql`:

```sql
-- Image identifiability protection (spec 2026-09-09, D-IDP-14). John's directive 7: "The listing
-- must have a single authoritative setting ... Default: NOT_SHOW. The safest privacy state is the
-- default." Written by exactly one path: the owner's step-7 PATCH (app/api/seller_listings.py).
ALTER TABLE listing ADD COLUMN identifiable_content_visibility text NOT NULL DEFAULT 'NOT_SHOW'
  CHECK (identifiable_content_visibility IN ('SHOW','NOT_SHOW'));
-- D-IDP-2 (queued for John): a photograph that is a PATH entry is a seed photograph with no asset
-- row, which can only ever be served under SHOW -- claimed or not. `claim_from_seed` flips `source`
-- on the first seller write of any kind, so `WHERE source = 'seed'` would miss every demo hospital
-- a seller has edited and leave it with null slots and an unpublishable SEED_UNPROCESSED gate.
-- The path entry is the property that matters. Spec 2026-09-09 C.10.
UPDATE listing SET identifiable_content_visibility = 'SHOW'
 WHERE EXISTS (SELECT 1 FROM jsonb_array_elements_text(photos) AS e WHERE position('/' IN e) > 0);
```

- [ ] `poetry run pytest tests/test_listing_privacy_schema.py::test_the_listing_carries_one_authoritative_visibility_defaulting_to_not_show -q -W error` — GREEN (the `conn` fixture re-migrates into the scratch database).

- [ ] **Step 3: GREEN — `migrations/041`**

Create `migrations/041_listing_asset_privacy.sql`, exactly the spec's §D DDL:

```sql
-- One privacy record per photograph (directive 6 and 18; spec 2026-09-09 C.3). Documents carry no
-- row (D19): they are owner-and-staff only today and are out of redaction scope.
CREATE TABLE listing_asset_privacy (
  asset_id                      uuid PRIMARY KEY REFERENCES listing_asset(id) ON DELETE CASCADE,
  listing_id                    uuid NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  processing_status             text NOT NULL DEFAULT 'UPLOADED'
    CHECK (processing_status IN ('UPLOADED','PROCESSING','SCANNED','REDACTION_GENERATED','READY_FOR_REVIEW',
                                 'SELLER_CONFIRMED','PUBLISHED','PROCESSING_FAILED','REDACTION_FAILED',
                                 'REVIEW_REQUIRED','REPROCESS_REQUIRED')),
  processing_version            integer NOT NULL,
  attempts                      integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  last_error                    text,                                   -- a reason code, never bytes
  original_storage_key          text NOT NULL UNIQUE,                   -- listings/{l}/photos/{a}/original.{ext}
  redacted_storage_key          text UNIQUE,                            -- listings/{l}/photos/{a}/redacted.webp
  redacted_sha256               text,
  confirmed_sha256              text,                                   -- the derivative the confirmation covers
  ocr                           jsonb NOT NULL DEFAULT '{}'::jsonb,
  identity_matches              jsonb NOT NULL DEFAULT '[]'::jsonb,
  vision                        jsonb NOT NULL DEFAULT '{"status": "pending"}'::jsonb,
  detected_regions              jsonb NOT NULL DEFAULT '[]'::jsonb,
  redaction_regions             jsonb NOT NULL DEFAULT '[]'::jsonb,
  detection_at                  timestamptz,
  seller_review_status          text NOT NULL DEFAULT 'pending'
    CHECK (seller_review_status IN ('pending','looks_good','edited')),
  seller_confirmed              boolean NOT NULL DEFAULT false,
  seller_confirmed_at           timestamptz,
  seller_confirmation_account_id uuid REFERENCES account(id) ON DELETE SET NULL,
  buyer_visible                 boolean NOT NULL DEFAULT false,
  final_privacy_state           text CHECK (final_privacy_state IN ('SHOW','NOT_SHOW')),
  -- Staleness is a FLAG, never a state (spec C.4, D-IDP-16): a ready row goes on serving its
  -- current derivative while the in-place re-run replaces it, so a processing-version bump can
  -- never blank a published listing.
  reprocess_reason              text CHECK (reprocess_reason IN ('VERSION','IDENTITY_CHANGED','OPERATOR')),
  reprocess_requested_at        timestamptz,
  reprocessed_at                timestamptz,
  created_at                    timestamptz NOT NULL DEFAULT now(),
  updated_at                    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT lap_confirmed_ck   CHECK ((NOT seller_confirmed)
                                       OR (seller_confirmed_at IS NOT NULL AND final_privacy_state IS NOT NULL
                                           AND confirmed_sha256 IS NOT NULL AND confirmed_sha256 = redacted_sha256)),
  CONSTRAINT lap_stale_ck       CHECK ((reprocess_reason IS NULL) = (reprocess_requested_at IS NULL)),
  CONSTRAINT lap_status_confirmed_ck CHECK (processing_status <> 'SELLER_CONFIRMED' OR seller_confirmed),
  CONSTRAINT lap_visible_ready_ck CHECK ((NOT buyer_visible)
                                       OR processing_status IN ('READY_FOR_REVIEW','SELLER_CONFIRMED','PUBLISHED')),
  CONSTRAINT lap_ready_has_derivative_ck CHECK (
    processing_status NOT IN ('REDACTION_GENERATED','READY_FOR_REVIEW','SELLER_CONFIRMED','PUBLISHED')
    OR redacted_storage_key IS NOT NULL),
  CONSTRAINT lap_never_the_original_ck CHECK (redacted_storage_key IS DISTINCT FROM original_storage_key)
);
CREATE INDEX listing_asset_privacy_listing_idx ON listing_asset_privacy (listing_id, processing_status);
CREATE INDEX listing_asset_privacy_sweep_idx   ON listing_asset_privacy (processing_status, updated_at);
```

- [ ] `poetry run pytest tests/test_listing_privacy_schema.py -q -W error` — both cases GREEN.

- [ ] **Step 4: RED — one case per CHECK, per index and per cascade**

Append to `tests/test_listing_privacy_schema.py`:

```python
@pytest.mark.parametrize("status", STATUSES)
def test_every_contracted_status_is_legal_and_a_twelfth_is_not(conn: Any, status: str) -> None:
    listing_id = _listing(conn, f"idp-status-{status.lower()}")
    asset_id = _asset(conn, listing_id)
    ready = status in ("REDACTION_GENERATED", "READY_FOR_REVIEW", "SELLER_CONFIRMED", "PUBLISHED")
    extra: dict[str, Any] = {}
    if ready:
        extra["redacted_storage_key"] = f"listings/{listing_id}/photos/{asset_id}/redacted.webp"
        extra["redacted_sha256"] = "b" * 64
    if status == "SELLER_CONFIRMED":
        extra |= {"seller_confirmed": True, "seller_confirmed_at": datetime.now(UTC), "final_privacy_state": "NOT_SHOW",
                  "confirmed_sha256": "b" * 64}
    _privacy(conn, asset_id, listing_id, processing_status=status, **extra)


def test_an_unknown_status_is_refused(conn: Any) -> None:
    listing_id = _listing(conn, "idp-status-bad")
    asset_id = _asset(conn, listing_id)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _privacy(conn, asset_id, listing_id, processing_status="AI_PASSED")


def test_a_confirmation_must_cover_the_derivative_that_is_served(conn: Any) -> None:
    """lap_confirmed_ck. "Confirmed" and "confirmed against a derivative other than the one served"
    are mutually exclusive AT THE DATABASE, so spec C.1's "confirmed under NOT_SHOW against the
    derivative it serves" is a column comparison rather than an inference."""
    listing_id = _listing(conn, "idp-confirm")
    asset_id = _asset(conn, listing_id)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _privacy(conn, asset_id, listing_id, processing_status="SELLER_CONFIRMED", seller_confirmed=True,
                 seller_confirmed_at=datetime.now(UTC), final_privacy_state="NOT_SHOW",
                 redacted_storage_key=f"listings/{listing_id}/photos/{asset_id}/redacted.webp",
                 redacted_sha256="b" * 64, confirmed_sha256="c" * 64)


def test_visibility_requires_readiness_and_readiness_requires_a_derivative(conn: Any) -> None:
    """lap_visible_ready_ck and lap_ready_has_derivative_ck: no row can claim visibility without
    readiness, or readiness without a derivative."""
    listing_id = _listing(conn, "idp-visible")
    asset_id = _asset(conn, listing_id)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _privacy(conn, asset_id, listing_id, processing_status="PROCESSING", buyer_visible=True)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _privacy(conn, asset_id, listing_id, processing_status="READY_FOR_REVIEW")


def test_the_redacted_key_is_never_the_original(conn: Any) -> None:
    """lap_never_the_original_ck -- the invariant spec C.4 states last: nothing ever writes
    redacted_storage_key := original_storage_key."""
    listing_id = _listing(conn, "idp-never")
    asset_id = _asset(conn, listing_id)
    key = f"listings/{listing_id}/photos/{asset_id}/original.jpg"
    with pytest.raises(psycopg2.errors.CheckViolation):
        _privacy(conn, asset_id, listing_id, processing_status="READY_FOR_REVIEW",
                 redacted_storage_key=key, redacted_sha256="b" * 64)


def test_a_stale_flag_and_its_timestamp_travel_together(conn: Any) -> None:
    """lap_stale_ck."""
    listing_id = _listing(conn, "idp-stale")
    asset_id = _asset(conn, listing_id)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _privacy(conn, asset_id, listing_id, reprocess_reason="VERSION")


def test_deleting_the_asset_deletes_its_privacy_row(conn: Any) -> None:
    listing_id = _listing(conn, "idp-cascade")
    asset_id = _asset(conn, listing_id)
    _privacy(conn, asset_id, listing_id)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM listing_asset WHERE id = %s", (asset_id,))
    assert _rows(conn, "SELECT 1 FROM listing_asset_privacy WHERE asset_id = %s", (asset_id,)) == []


def test_both_indexes_exist_under_their_contracted_names(conn: Any) -> None:
    found = {name for (name,) in _rows(
        conn, "SELECT indexname FROM pg_indexes WHERE tablename = 'listing_asset_privacy'")}
    assert {"listing_asset_privacy_listing_idx", "listing_asset_privacy_sweep_idx"} <= found
```

- [ ] `poetry run pytest tests/test_listing_privacy_schema.py -q -W error` — GREEN; `041` already satisfies them. (These are contract tests over DDL that Step 3 wrote; their value is that a later migration cannot relax a CHECK without turning one of them red.)

- [ ] **Step 5: RED — the trigger backstop**

Append:

```python
def test_a_direct_publish_of_a_listing_with_an_unprocessed_photograph_raises(conn: Any) -> None:
    """Directive 11's fail-closed backstop. `tests/api/test_listing_assets.py`'s own `_publish`
    helper is a bare UPDATE and demonstrates that the DATABASE used to accept a publish regardless
    of asset state; migration 042 is what refuses it -- by any route, by a test helper, by hand."""
    listing_id = _listing(conn, "idp-trigger")
    asset_id = _asset(conn, listing_id)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET photos = %s::jsonb WHERE id = %s", (json.dumps([str(asset_id)]), listing_id))
    _privacy(conn, asset_id, listing_id, processing_status="UPLOADED")
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.RaiseException) as caught:
        cur.execute("UPDATE listing SET status = 'published' WHERE id = %s", (listing_id,))
    assert "PHOTOS_NOT_READY" in str(caught.value)


def test_a_flagged_ready_photograph_also_refuses_a_new_publication(conn: Any) -> None:
    """A stale row is an offender at the gate ('STALE'): a NEW publication waits for its in-place
    re-run. An EXISTING publication is untouched -- proved by the third case below."""
    listing_id = _listing(conn, "idp-trigger-stale")
    asset_id = _asset(conn, listing_id)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET photos = %s::jsonb WHERE id = %s", (json.dumps([str(asset_id)]), listing_id))
    _privacy(conn, asset_id, listing_id, processing_status="SELLER_CONFIRMED", seller_confirmed=True,
             seller_confirmed_at=datetime.now(UTC), final_privacy_state="NOT_SHOW", confirmed_sha256="b" * 64,
             redacted_storage_key=f"listings/{listing_id}/photos/{asset_id}/redacted.webp",
             redacted_sha256="b" * 64, reprocess_reason="VERSION", reprocess_requested_at=datetime.now(UTC))
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.RaiseException):
        cur.execute("UPDATE listing SET status = 'published' WHERE id = %s", (listing_id,))


def test_the_trigger_fires_on_status_alone_and_lets_an_already_published_row_be_touched(conn: Any) -> None:
    """`BEFORE INSERT OR UPDATE OF status`, guarded by `OLD.status <> 'published'` -- so a published
    listing whose photograph later goes stale is not frozen out of every other UPDATE."""
    listing_id = _listing(conn, "idp-trigger-touch")
    asset_id = _asset(conn, listing_id)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET photos = %s::jsonb WHERE id = %s", (json.dumps([str(asset_id)]), listing_id))
    _privacy(conn, asset_id, listing_id, processing_status="PUBLISHED", buyer_visible=True,
             redacted_storage_key=f"listings/{listing_id}/photos/{asset_id}/redacted.webp",
             redacted_sha256="b" * 64)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status = 'published' WHERE id = %s", (listing_id,))
        cur.execute("UPDATE listing_asset_privacy SET reprocess_reason = 'VERSION',"
                    " reprocess_requested_at = now(), updated_at = now() WHERE asset_id = %s", (asset_id,))
        cur.execute("UPDATE listing SET updated_at = now() WHERE id = %s", (listing_id,))


def test_a_seed_path_entry_passes_under_show_and_is_an_offender_under_not_show(conn: Any) -> None:
    """Spec C.10: a seed photograph has no asset row and can only ever be served under SHOW."""
    listing_id = _listing(conn, "idp-seed", photos=["round-rock/1.webp"])
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET identifiable_content_visibility = 'SHOW' WHERE id = %s", (listing_id,))
        cur.execute("UPDATE listing SET status = 'published' WHERE id = %s", (listing_id,))
        cur.execute("UPDATE listing SET status = 'paused' WHERE id = %s", (listing_id,))
        cur.execute("UPDATE listing SET identifiable_content_visibility = 'NOT_SHOW' WHERE id = %s", (listing_id,))
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.RaiseException):
        cur.execute("UPDATE listing SET status = 'published' WHERE id = %s", (listing_id,))
    assert _rows(conn, "SELECT status FROM listing_photos_not_ready(%s, 'NOT_SHOW', %s::jsonb)",
                 (listing_id, json.dumps(["round-rock/1.webp"]))) == [("SEED_UNPROCESSED",)]
```

- [ ] `poetry run pytest tests/test_listing_privacy_schema.py -q -W error` — RED with `psycopg2.errors.UndefinedFunction: function listing_photos_not_ready(uuid, unknown, jsonb) does not exist` and, on the first three, no exception raised at all (`DID NOT RAISE`).

- [ ] **Step 6: GREEN — `migrations/042`**

Create `migrations/042_listing_publish_photos_ready_trigger.sql`:

```sql
-- The fail-closed backstop for directive 11: a listing cannot become `published` -- by any route, by
-- a test helper, by hand -- while a photograph is not ready. The routes evaluate the same predicate
-- first and answer 422 PHOTOS_NOT_READY with the offenders; this refuses whatever they missed.
CREATE OR REPLACE FUNCTION listing_photos_not_ready(l_id uuid, visibility text, photos jsonb)
RETURNS TABLE (entry text, status text) LANGUAGE sql STABLE AS $$
  WITH entries AS (SELECT e FROM jsonb_array_elements_text(photos) AS t(e) WHERE e IS NOT NULL)
  SELECT e, 'SEED_UNPROCESSED' FROM entries WHERE position('/' IN e) > 0 AND visibility = 'NOT_SHOW'
  UNION ALL
  SELECT e, coalesce(p.processing_status, 'NO_PRIVACY_ROW')
    FROM entries LEFT JOIN listing_asset_privacy p ON p.asset_id::text = e AND p.listing_id = l_id
   WHERE position('/' IN e) = 0
     AND (p.asset_id IS NULL
          OR (visibility = 'NOT_SHOW' AND (p.processing_status NOT IN ('SELLER_CONFIRMED','PUBLISHED')
                                           OR p.redacted_storage_key IS NULL))
          OR (visibility = 'SHOW' AND p.processing_status NOT IN ('READY_FOR_REVIEW','SELLER_CONFIRMED','PUBLISHED')))
  UNION ALL
  SELECT e, 'STALE'
    FROM entries JOIN listing_asset_privacy p ON p.asset_id::text = e AND p.listing_id = l_id
   WHERE p.reprocess_reason IS NOT NULL
$$;

CREATE OR REPLACE FUNCTION listing_publish_requires_ready_photos() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status = 'published' AND (TG_OP = 'INSERT' OR OLD.status <> 'published') THEN
    IF EXISTS (SELECT 1 FROM listing_photos_not_ready(NEW.id, NEW.identifiable_content_visibility, NEW.photos)) THEN
      RAISE EXCEPTION 'PHOTOS_NOT_READY' USING ERRCODE = 'P0001';
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER listing_publish_photos_ready BEFORE INSERT OR UPDATE OF status
  ON listing FOR EACH ROW EXECUTE FUNCTION listing_publish_requires_ready_photos();
```

The trigger fires on `status` alone: a published row gaining a photograph leaves `published` in the same transaction (`take_off_market`, A-SL15), and a visibility flip on a published row re-enters review (D3), so neither write can ever MAKE a row published.

- [ ] `poetry run pytest tests/test_listing_privacy_schema.py -q -W error` — GREEN, every case.

- [ ] **Step 6b: the three existing publishers the trigger now refuses.** `042` is a backstop with no exceptions, so every path that puts a listing with photographs into `published` has to satisfy it. There are exactly three in the merged tree, and all three are fixed here, at source, in this commit. Find them by grep before fixing any of them, and STOP with `NEEDS_CONTEXT` if the grep finds a fourth:

```bash
# Every place a `listing` row is written outside `app/`. Read each hit for a `published` status
# together with a non-empty `photos`: that pair is what 042 refuses.
grep -rn --include=*.py -E "INSERT INTO listing[ (]|UPDATE listing SET" scripts/ tests/ \
  | grep -v tests/test_listing_privacy_schema.py
```

At `2510278` that prints three: `scripts/seed_listings.py`'s `UPSERT`, and `tests/api/test_listing_assets.py`'s `_SEED_INSERT` and `_publish`. A fourth is `NEEDS_CONTEXT`.

**(1) `scripts/seed_listings.py`'s UPSERT** (BRANCH `:115-147`) inserts `status` from `seeds/hospitals.json`, and all eighteen records are `published`. It does not name `identifiable_content_visibility`, so the row takes `040`'s `DEFAULT 'NOT_SHOW'`; every `photos` entry is a path (`<slug>/<n>.webp`), so `listing_photos_not_ready` returns `SEED_UNPROCESSED` and the trigger raises `PHOTOS_NOT_READY` on the very first insert. A fresh `python scripts/seed_listings.py` — DEPLOY.md's QA runbook and `scripts/start.sh`'s `seed` role — would exit non-zero, and `tests/scripts/test_seed_listings.py` (50 cases) and `tests/perf/test_api_latency.py::test_listings_p95_within_budget` (which calls `SL.seed(..., reset=True)`, BRANCH `:365`) would go red with it. Spec §C.10 is what fixes it: the seeder writes `SHOW` explicitly, in **both** halves of the UPSERT, under its existing `WHERE listing.source = 'seed'` scope so a row a seller has claimed is never rewritten.

In `UPSERT`'s insert column list, beside `status`:

```
  slug, name, street, city, state, zip, phone, hours, status, identifiable_content_visibility,
  location_disclosed, name_disclosed,
```

in its `VALUES`, beside `%(status)s`:

```
  %(status)s, 'SHOW', %(location_disclosed)s, %(name_disclosed)s,
```

and in `DO UPDATE SET`, beside `status = EXCLUDED.status` (the D22/D25 rule the block's own comment already states — a value that only landed on an INSERT would never land at all, because the eighteen already exist on QA):

```
  status = EXCLUDED.status, identifiable_content_visibility = EXCLUDED.identifiable_content_visibility,
```

A literal `'SHOW'` and not a parameter: it is the SEEDER's decision (D-IDP-2), not a field of `seeds/hospitals.json`, and the spec says the file gains no key. Two cases in `tests/scripts/test_seed_listings.py`, in that file's own style:

```python
def test_the_seeder_writes_show_because_a_seed_photograph_has_no_asset_row(conn: Any) -> None:
    """D-IDP-2, and the reason migration 042's trigger lets the eighteen publish at all: a seed
    photograph is a PATH entry with no `listing_asset` row and therefore no derivative, so SHOW is
    the only state under which it can honestly be served (spec C.10)."""
    SL.seed(conn, reset=True)
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT identifiable_content_visibility FROM listing WHERE source = 'seed'")
        assert [r[0] for r in cur.fetchall()] == ["SHOW"]


def test_a_re_seed_writes_show_on_the_update_half_as_well(conn: Any) -> None:
    """The eighteen already exist on QA, so a value that only landed on the INSERT would never land."""
    SL.seed(conn, reset=True)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET identifiable_content_visibility = 'NOT_SHOW'"
                    " WHERE source = 'seed'")
    SL.seed(conn)                                    # no reset: the UPSERT's DO UPDATE half
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT identifiable_content_visibility FROM listing WHERE source = 'seed'")
        assert [r[0] for r in cur.fetchall()] == ["SHOW"]
```

**(2) `tests/api/test_listing_assets.py::_SEED_INSERT`** (BRANCH `:41-47`) inserts a `published` row with a `photos` array of paths and no visibility column — the same refusal, for the same reason. Add the column to its list and `'SHOW'` to its `VALUES`:

```python
_SEED_INSERT = """
INSERT INTO listing (slug, name, street, city, state, zip, hours, status, location_disclosed,
                     name_disclosed, area, type, market, est, price, source, photos,
                     identifiable_content_visibility)
VALUES (%(slug)s, 'Demo Hospital', '1 Main St', 'Austin', 'TX', '78701', '24/7', 'published',
        true, true, 'Austin', 'Small animal', 'Austin, TX', 1998, 1450000, 'seed', %(photos)s::jsonb,
        'SHOW')
RETURNING id
"""
```

**(3) `tests/api/test_listing_assets.py::_publish`** (BRANCH `:132-138`) is a bare UPDATE that sets the ten columns migration `030`'s two CHECKs need. **Keep every one of them** — `listing_publishable_ck` (`030:78-80`) wants `state`, `market` and `area`, and `listing_submittable_ck` (`030:70-73`) wants `name`, `city`, `zip`, `type`, `est` and `price` for every status but `draft`/`withdrawn` — and add the privacy rows `042` now wants of each photograph. Dropping a column here would trade one refusal for another:

```python
def _publish(conn: Any, listing_id: Any) -> None:
    """The draft, made publishable: 030's two CHECKs want the wizard's own fields plus the three
    the reviewer supplies at the first publish (D12) — the original ten columns, unchanged — and
    migration 042 now also wants a ready privacy row for every photograph (spec 2026-09-09 C.8).
    A helper that could publish an unprocessed photograph would be a hole in exactly the gate this
    sub-project exists to close."""
    with conn.cursor() as cur:
        cur.execute("SELECT jsonb_array_elements_text(photos) FROM listing WHERE id = %s", (listing_id,))
        for (entry,) in cur.fetchall():
            if "/" in entry:                      # a seed path entry: no asset row, SHOW only
                continue
            cur.execute(
                "INSERT INTO listing_asset_privacy (asset_id, listing_id, processing_version,"
                " original_storage_key, processing_status, seller_confirmed, seller_confirmed_at,"
                " final_privacy_state, confirmed_sha256, redacted_storage_key, redacted_sha256, buyer_visible)"
                " VALUES (%s,%s,1,%s,'SELLER_CONFIRMED',true,now(),'NOT_SHOW',%s,%s,%s,true)"
                " ON CONFLICT (asset_id) DO NOTHING",
                (entry, listing_id, f"listings/{listing_id}/photos/{entry}/original.jpg",
                 "f" * 64, f"listings/{listing_id}/photos/{entry}/redacted.webp", "f" * 64),
            )
        cur.execute("UPDATE listing SET name='Hill Country Animal Hospital', city='Cedar Park',"
                    " zip='78613', type='Small animal', est=1998, price=1450000, state='TX',"
                    " market='Austin, TX', area='Cedar Park', status='published' WHERE id=%s",
                    (listing_id,))
```

- [ ] `poetry run pytest tests/api/test_listing_assets.py tests/scripts/test_seed_listings.py tests/perf/test_api_latency.py -q -W error` — GREEN.
- [ ] `poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100` — the whole backend suite GREEN. If a FOURTH direct publisher appears, it is fixed the same way, at source, and named in the commit body.

- [ ] **Step 7: the migration numbering carve-out (amendment A-C12)**

The id is `A-C12` and is derived, not remembered: `main` at `073aab8` already spends `A-C10` on the seller lifecycle's `030`–`039` carve-out (Census plan `:42`, cited again at `:62`) and `A-C11` on the Phase A final-review rulings (`:2089`, `:2553`). Confirm with `grep -o 'A-C[0-9]\+' docs/superpowers/plans/*.md | sort -u -V | tail -3` before writing a line; if the highest is not `A-C11`, use the next free id everywhere in this step and in Global Constraint (g).

- [ ] `npx vitest run tests/cross-plan-deltas.test.ts` from `frontend/` first, to see it green before the Census plan is edited.
- [ ] `docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md` — the numbering line (`:42`) and the D14 row (`:62`) already name the seller lifecycle's `030`–`039` carve-out and `090`–`099`; add `040`–`049` to both, in the same voice, naming this spec:

```
less the seller lifecycle's `030`–`039` (A-SL5) and the image identifiability sub-project's
`040`–`049` (A-C12, 2026-09-09 — spec `2026-09-09-image-identifiability-protection-design.md`)
```

- [ ] `DEPLOY.md`'s Migrations paragraph (`:110-115` on `main` at `073aab8`) — the clause that today reads **`017`–`059` the Census plan's Sub-project 3 Phase A** is stale on both trees (A-SL5's carve-out reached the Census plan and never this page). Replace lines `:112-114` — **the whole run from the `017`–`059` clause through the `090`–`099` clause, carrying that clause forward unchanged**, because `tests/test_docs.py:1717-1719` asserts the Migrations section still contains `017`, `059`, `090` and `099`, and a replacement that stopped at `080`–`089` would drop the last of them:

```
· **`017`–`029` and `050`–`059` the Census plan's Sub-project 3 Phase A** and **`060`+ its Phase B**
(that plan's D14) · **`030`–`039` the seller listing lifecycle** (A-SL5) · **`040`–`049` the image
identifiability protection sub-project** (A-C12, 2026-09-09) · `080`–`089` the map engines ·
**`090`–`099` platform and hotfix migrations on `main`**
```

so the paragraph still runs on into its existing `(A-L12, 2026-09-09 — …)` line and its `003`–`009` sentence, both untouched.

- [ ] `poetry run pytest tests/test_docs.py -q -W error` — the Migrations-section assertions still find `017`, `059`, `090` and `099`. GREEN. Read the rendered paragraph back before committing: the four numbers are what the test looks for, and the sentence has to still read as English.
- [ ] `cd frontend && npx vitest run tests/cross-plan-deltas.test.ts` — GREEN against the edited Census plan.

- [ ] **Step 8: John's directive, committed**

- [ ] Copy the directive verbatim — byte for byte, including its heading rules and its section 23 — to `docs/superpowers/specs/2026-09-09-image-identifiability-directive.md`, with **one** line prepended above its title so a reader knows what it is and where it came from:

```markdown
<!-- John's implementation directive, 2026-09-09 ~15:30 WITA, verbatim and unedited. It is the
     source of `2026-09-09-image-identifiability-protection-design.md` and of
     `../plans/2026-09-09-image-identifiability-protection.md`. Section 23 forbids a claim this
     file itself quotes in order to forbid it, which is why `tests/test_docs.py`'s copy test
     exempts this path by name. -->
```

- [ ] `poetry run pytest tests/test_docs.py -q -W error` — GREEN (`test_relative_markdown_links_resolve` and `test_no_tracked_text_file_cites_a_retired_number` both cover the new file).

- [ ] **Step 9: the task's gates**

```bash
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
cd frontend && npx vitest run tests/cross-plan-deltas.test.ts && cd ..
```

- [ ] **Step 10: commit**

```
feat(db): migrations 040-042 -- the listing visibility column, listing_asset_privacy, and the publish trigger

John's directive 7 gives the listing one authoritative setting, defaulting
to NOT_SHOW; 6 and 18 give every photograph an explicit state and an
auditable record; 11 blocks publication until every photograph is ready.
040 adds the column and backfills SHOW for every row whose photos hold a
path entry (a seed photograph has no asset row and can only be served
under SHOW). 041 adds listing_asset_privacy with the eleven states, the
staleness flag and six CHECKs that make an unready row unable to claim
readiness, visibility or a confirmation of a derivative other than the one
it serves. 042 adds listing_photos_not_ready() and the BEFORE UPDATE OF
status trigger that refuses a publish no route caught -- including the
test helper that used to publish regardless, fixed at source here.

042 also refuses the three publishers that existed before it, all fixed
here at source: scripts/seed_listings.py's UPSERT now writes SHOW in both
halves (a seed photograph is a path entry with no asset row, so SHOW is
the only state it can honestly be served under -- D-IDP-2, spec C.10),
and tests/api/test_listing_assets.py's _SEED_INSERT and _publish gain the
same value and the ready privacy rows respectively. _publish keeps every
one of the ten columns migration 030's two CHECKs require.

Migrations 040-049 are carved out of the Census plan's SP3-A range
(amendment A-C12 -- A-C10 and A-C11 are already spent), recorded in that
plan and in DEPLOY.md's numbering paragraph, whose 017-059 clause had been
stale since the seller lifecycle's own 030-039 carve-out. The 090-099
clause is carried forward unchanged.

John's directive is committed verbatim beside the spec as its source.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `git add migrations/040_listing_identifiable_content_visibility.sql migrations/041_listing_asset_privacy.sql migrations/042_listing_publish_photos_ready_trigger.sql tests/test_listing_privacy_schema.py scripts/seed_listings.py tests/scripts/test_seed_listings.py tests/api/test_listing_assets.py docs/superpowers/specs/2026-09-09-image-identifiability-directive.md docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md DEPLOY.md`

---

### Task P2: three objects per photograph — the upload stores and enqueues, the delete removes all three

**Files:**
- Create: `app/privacy/__init__.py` (`PROCESSING_VERSION`, `PHOTO_EXT`, the key builders)
- Create: `app/privacy/record.py` (`insert`, `enqueue_processing` — the module Task P3 extends with the transitions)
- Modify: `app/api/seller_listings.py` — `_insert_asset` (BRANCH `:810-828`), `upload_photo` (`:862-901`), `delete_asset` (`:990-1033`), the constants block (`:593-594`)
- Modify: `tests/conftest.py` (the promoted `store` fixture), `tests/api/conftest.py` (the three signed-header fixtures and two helpers), `tests/api/test_listing_assets.py`
- Unchanged: `app/media/encode.py` (the encode is moved to a thread, not changed), `app/storage.py`

**Interfaces:**
- Consumes: P1's `listing_asset_privacy`; `app/storage.py::ObjectStore.{exists,put,delete,list}`; `app/media/encode.py::encode_webp`; `app/tasks/celery_app.py::celery_app`.
- Produces, `app/privacy/__init__.py`:
  - `PROCESSING_VERSION: int` — the pipeline's version, `1` here, bumped when any engine, prompt, expansion rule or fill changes.
  - `PHOTO_EXT: dict[str, str]` — `{"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}`.
  - `photo_prefix(listing_id: object, asset_id: object) -> str` — `f"listings/{listing_id}/photos/{asset_id}/"`.
  - `original_key(listing_id: object, asset_id: object, ext: str) -> str`, `display_key(listing_id: object, asset_id: object) -> str`, `redacted_key(listing_id: object, asset_id: object) -> str`.
- Produces, `app/privacy/record.py`:
  - `insert(conn: Any, *, asset_id: UUID, listing_id: UUID, original_storage_key: str, version: int) -> None`
  - `enqueue_processing(asset_id: UUID, version: int) -> None` — publishes `media.process_photo` **by name**, so no deployed api process imports `app.tasks.media` and no engine wheel is ever loaded in it. P8 Step 6 adds one branch above that line for the Playwright launcher alone (controller amendment A-IDP-2), guarded by a setting `Settings` refuses at boot outside `ENVIRONMENT=test` and pinned at run time by `tests/api/test_import_surface.py`.
- Produces, `app/api/seller_listings.py`: `_sniffed_photo(data: bytes, declared: str) -> str | None`; `_listed(store, prefix)` and `_exists(store, key)`, both turning a bucket error into the module's own 503 `STORAGE_UNAVAILABLE` (`ObjectStore.list` and `.exists` re-raise); the refusal code `STORAGE_CONFLICT` (409, message from spec §H).
- Produces, `tests/conftest.py`: the `store` fixture, `BUCKET`, `ENDPOINT` and `_intercepted_by_moto`, moved verbatim out of `tests/api/test_listing_assets.py` (Step 0).
- Produces, `tests/api/conftest.py`: `seller`, `buyer` and `admin` (each a signed header dict), `_draft(client, headers)` and `_jpeg_bytes()`/`_png_bytes()` (Step 0).
- Every later task reads `display_key` as `listing_asset.storage_key`, `original_key` and `redacted_key` from the privacy row, and never any other shape.

**Every test snippet from here on is `async def` and awaits its client.** The merged suite's API client is `httpx.AsyncClient` over `ASGITransport` (`tests/api/conftest.py`'s `client`, BRANCH `:71-81`), and an un-awaited `client.post(...)` returns a coroutine that `-W error` turns into a "coroutine was never awaited" failure rather than a request. Authentication is a literal `Cookie` header through `auth_headers(cookies, headers)` and never httpx's `cookies=` argument, which httpx 0.28 deprecates and `-W error` therefore refuses (that file's own docstring says why).

- [ ] **Step 0: the shared test fixtures, moved once so every later task uses one of each**

Three suites below this one live outside `tests/api/` and need a bucket (`tests/tasks/test_media.py`, `tests/media/test_redact.py`, `tests/privacy/test_gate.py`'s store arm), and every API suite below needs a signed seller, buyer and admin. Today the moto fixture is **module-local** to `tests/api/test_listing_assets.py` (BRANCH `:60-72`) and there are no persona fixtures at all — `tests/api/conftest.py` has `client`, `member` and `auth_headers` and nothing more (BRANCH `:71-97`). Both are moved/added here, once, rather than copied into six files.

- [ ] Move `BUCKET`, `ENDPOINT`, `_intercepted_by_moto` and the `store` fixture **verbatim** from `tests/api/test_listing_assets.py` (BRANCH `:34-35`, `:50-72`) into `tests/conftest.py`, beside `_no_stray_network`. Nothing about them changes: the AWS-shaped endpoint, the assertion in `_intercepted_by_moto`, the four `monkeypatch.setattr(settings, …)` calls and the `ObjectStore.from_settings(settings)` yield are the same bytes in the new place. `tests/api/test_listing_assets.py` then imports what it still names (`from tests.conftest import BUCKET, ENDPOINT`) and keeps every one of its own cases unchanged.
- [ ] `tests/conftest.py::_no_stray_network`'s docstring names `tests/api/test_listing_assets.py::_intercepted_by_moto` (BRANCH `:29`). Update that one sentence to name the guard's new home in this file — a stale cross-reference in the fixture that explains the guard is exactly the kind of drift this plan's own doc pins exist to stop.
- [ ] Add to `tests/api/conftest.py`, beside `member`:

```python
@pytest.fixture
def seller(member):
    """A signed-in seller's request headers: the Cookie header plus the CSRF pair, ready to pass as
    `headers=seller`. Three personas rather than one `member(...)` call per test, because every
    suite from Task P2 on needs the same three and a per-test call would mint a new account (and a
    new rate-limit bucket) each time."""
    _account_id, cookies, headers = member(roles=("buyer", "seller"), email="idp-seller@example.org")
    return auth_headers(cookies, headers)


@pytest.fixture
def buyer(member):
    _account_id, cookies, headers = member(roles=("buyer",), email="idp-buyer@example.org")
    return auth_headers(cookies, headers)


@pytest.fixture
def admin(member):
    _account_id, cookies, headers = member(roles=("buyer", "admin"), email="idp-admin@example.org")
    return auth_headers(cookies, headers)


def _jpeg_bytes(width: int = 240, height: int = 180) -> bytes:
    """`test_listing_assets.py::_jpeg`'s bytes, reachable from every suite. Deterministic: the
    upload tests compare `store.get(original)` to this value byte for byte."""
    image = Image.new("RGB", (width, height), (120, 30, 30))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


def _png_bytes(width: int = 240, height: int = 180) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (30, 120, 30)).save(buffer, "PNG")
    return buffer.getvalue()


async def _draft(client, headers) -> str:
    """A fresh draft listing, as `test_listing_assets.py::_create` makes one."""
    response = await client.post("/api/seller/listings", headers=headers)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])
```

with `import io`, `from PIL import Image` at the top of that file.

- [ ] `poetry run pytest tests/api/test_listing_assets.py tests/test_storage.py -q -W error` — GREEN, unchanged behaviour, before a line of this task's own code is written. A red here is the move, not the feature.

- [ ] **Step 1: RED — the key layout**

Create `tests/privacy/__init__.py` (empty) and `tests/privacy/test_keys.py`:

```python
"""The three-object layout (spec 2026-09-09 C.2, D-IDP-15). The asset uuid is a DIRECTORY, never
guessable and never serialised, so a future signed-URL or CDN arm can be scoped to display.webp and
redacted.webp and never to the original."""
from __future__ import annotations

from uuid import UUID

from app.privacy import PHOTO_EXT, PROCESSING_VERSION, display_key, original_key, photo_prefix, redacted_key

LISTING = UUID("11111111-1111-4111-8111-111111111111")
ASSET = UUID("22222222-2222-4222-8222-222222222222")


def test_the_three_keys_share_the_asset_uuid_as_a_directory() -> None:
    prefix = photo_prefix(LISTING, ASSET)
    assert prefix == f"listings/{LISTING}/photos/{ASSET}/"
    assert original_key(LISTING, ASSET, ".jpg") == f"{prefix}original.jpg"
    assert display_key(LISTING, ASSET) == f"{prefix}display.webp"
    assert redacted_key(LISTING, ASSET) == f"{prefix}redacted.webp"
    assert len({original_key(LISTING, ASSET, ".jpg"), display_key(LISTING, ASSET), redacted_key(LISTING, ASSET)}) == 3


def test_every_accepted_photo_type_has_an_extension() -> None:
    assert PHOTO_EXT == {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def test_the_processing_version_is_an_integer_the_privacy_row_can_hold() -> None:
    assert isinstance(PROCESSING_VERSION, int) and PROCESSING_VERSION >= 1
```

- [ ] `poetry run pytest tests/privacy/test_keys.py -q -W error` — RED: `ModuleNotFoundError: No module named 'app.privacy'`.

- [ ] **Step 2: GREEN — `app/privacy/__init__.py`**

```python
"""The image-identifiability package: the pipeline's version, and the key layout every module in it
shares (spec 2026-09-09 C.2).

Three objects per photograph under `listings/{listing_id}/photos/{asset_id}/`, the asset uuid a
DIRECTORY rather than a filename:

  original.{jpg|png|webp}  the uploaded bytes as received. Written once, never overwritten, served
                           to the owner and the reviewer and to nobody else.
  display.webp             today's `encode_webp` output -- the normalised, metadata-free WebP.
                           `listing_asset.storage_key` keeps pointing at this one, which is what
                           `app/api/listings.py::_asset_bytes` already reads.
  redacted.webp            the NOT_SHOW representation. Regenerated in place and addressed to
                           buyers by its CONTENT HASH, so a stale URL is never a stale image.
"""
from __future__ import annotations

#: Bumped when any engine, prompt, expansion rule or fill changes; a privacy row below this is
#: stale and the sweeper flags it for an in-place re-run (spec C.5).
PROCESSING_VERSION = 1

#: The extension `original.*` takes, chosen by the MAGIC BYTES and cross-checked against the
#: declared Content-Type (`app/api/seller_listings.py::_sniffed_photo`).
PHOTO_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def photo_prefix(listing_id: object, asset_id: object) -> str:
    return f"listings/{listing_id}/photos/{asset_id}/"


def original_key(listing_id: object, asset_id: object, ext: str) -> str:
    return f"{photo_prefix(listing_id, asset_id)}original{ext}"


def display_key(listing_id: object, asset_id: object) -> str:
    return f"{photo_prefix(listing_id, asset_id)}display.webp"


def redacted_key(listing_id: object, asset_id: object) -> str:
    return f"{photo_prefix(listing_id, asset_id)}redacted.webp"
```

- [ ] `poetry run pytest tests/privacy/test_keys.py -q -W error` — GREEN.

- [ ] **Step 3: RED — the upload writes a privacy row, two objects, and one message**

Append to `tests/api/test_listing_assets.py`, using Step 0's promoted `store` fixture and its `seller` headers. **Async, awaited, and signed** — the suite's client is `httpx.AsyncClient` and every request carries `headers=seller`:

```python
async def test_an_upload_stores_the_original_and_the_display_and_enqueues_one_task(
    client: Any, seller: dict[str, str], store: Any, conn: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec C.5 step 0. The original is kept because directive 13 says "NEVER overwrite the
    original"; the display is the SHOW representation; the enqueue happens AFTER the commit, so a
    task can never find no row, and a lost enqueue leaves an UPLOADED row for the sweeper."""
    sent: list[tuple[str, list[object]]] = []
    monkeypatch.setattr("app.privacy.record.celery_app.send_task",
                        lambda name, args=None, **kw: sent.append((name, list(args or []))))
    listing_id = await _draft(client, seller)
    response = await client.post(f"/api/seller/listings/{listing_id}/photos",
                                 files={"file": ("sign.jpg", _jpeg_bytes(), "image/jpeg")},
                                 headers=seller)
    assert response.status_code == 201, response.text
    asset_id = response.json()["id"]
    prefix = f"listings/{listing_id}/photos/{asset_id}/"
    assert sorted(store.list(prefix)) == [f"{prefix}display.webp", f"{prefix}original.jpg"]
    assert store.get(f"{prefix}original.jpg") == _jpeg_bytes()          # byte for byte, as received
    assert store.get(f"{prefix}display.webp") != _jpeg_bytes()          # normalised and stripped
    with conn.cursor() as cur:
        cur.execute("SELECT storage_key FROM listing_asset WHERE id = %s", (asset_id,))
        assert cur.fetchone()[0] == f"{prefix}display.webp"
        cur.execute("SELECT processing_status, processing_version, original_storage_key,"
                    " redacted_storage_key, buyer_visible FROM listing_asset_privacy WHERE asset_id = %s",
                    (asset_id,))
        assert cur.fetchone() == ("UPLOADED", 1, f"{prefix}original.jpg", None, False)
    assert sent == [("media.process_photo", [asset_id, 1])]


async def test_a_file_whose_bytes_disagree_with_its_header_is_refused(
    client: Any, seller: dict[str, str], store: Any
) -> None:
    """The skeptic's decode-anything finding: the route used to accept "anything Pillow can open,
    labelled jpeg/png/webp", first frame only. The magic-byte sniff mirrors the document route's
    own `_sniffed`."""
    listing_id = await _draft(client, seller)
    res = await client.post(f"/api/seller/listings/{listing_id}/photos",
                            files={"file": ("sign.jpg", _png_bytes(), "image/jpeg")}, headers=seller)
    assert res.status_code == 422 and res.json()["error"]["code"] == "BAD_IMAGE"
    assert store.list(f"listings/{listing_id}/photos/") == []


async def test_a_second_put_of_the_same_original_key_is_a_refusal_not_a_write(
    client: Any, seller: dict[str, str], store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defence in depth (spec C.5 step 0): the asset uuid is minted per request, so `exists()` can
    only be true for a key some earlier, rolled-back request wrote. Reached here by planting an
    object at a patched uuid, never by a seller's action."""
    listing_id = await _draft(client, seller)
    planted = UUID("33333333-3333-4333-8333-333333333333")
    monkeypatch.setattr("app.api.seller_listings.uuid4", lambda: planted)
    store.put(f"listings/{listing_id}/photos/{planted}/original.jpg", b"older", "image/jpeg")
    res = await client.post(f"/api/seller/listings/{listing_id}/photos",
                            files={"file": ("sign.jpg", _jpeg_bytes(), "image/jpeg")}, headers=seller)
    assert res.status_code == 409 and res.json()["error"]["code"] == "STORAGE_CONFLICT"
    assert res.json()["error"]["message"] == "That photograph has already been stored."
    assert store.get(f"listings/{listing_id}/photos/{planted}/original.jpg") == b"older"


async def test_deleting_a_photograph_removes_all_three_objects_and_the_privacy_row(
    client: Any, seller: dict[str, str], store: Any, conn: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Directive 13's retention rule, unchanged: an asset's objects live exactly as long as its
    row. The privacy row goes by CASCADE (migration 041)."""
    monkeypatch.setattr("app.privacy.record.celery_app.send_task", lambda *a, **kw: None)
    listing_id = await _draft(client, seller)
    created = await client.post(f"/api/seller/listings/{listing_id}/photos",
                                files={"file": ("sign.jpg", _jpeg_bytes(), "image/jpeg")}, headers=seller)
    asset_id = created.json()["id"]
    prefix = f"listings/{listing_id}/photos/{asset_id}/"
    store.put(f"{prefix}redacted.webp", b"derivative", "image/webp")     # as the worker would
    gone = await client.delete(f"/api/seller/listings/{listing_id}/assets/{asset_id}", headers=seller)
    assert gone.status_code == 204
    assert store.list(prefix) == []
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM listing_asset_privacy WHERE asset_id = %s", (asset_id,))
        assert cur.fetchone() is None
```

`_draft`, `_jpeg_bytes` and `_png_bytes` are Step 0's helpers in `tests/api/conftest.py`; `seller` is its header fixture. Every case that reaches the upload route patches `send_task`, because without a broker the real call would raise inside the handler after the commit.

- [ ] `poetry run pytest tests/api/test_listing_assets.py -q -W error -k "original or disagree or STORAGE_CONFLICT or three_objects or all_three"` — RED: the first fails on `sorted(store.list(prefix)) == [...]` (today one object at `…/{asset_id}.webp`), the second returns 201, the third 201, the fourth leaves `redacted.webp` behind.

- [ ] **Step 4: GREEN — the record's writer and its enqueue**

Create `app/privacy/record.py`:

```python
"""The privacy row: its writer, and the message that starts its pipeline.

Task P3 adds the state machine on top of this module -- the claim, the reset rule and one function
per transition. Everything here is what the UPLOAD needs and nothing more, so the api's import of
this module pulls in no engine, no Pillow and no model.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.tasks.celery_app import celery_app


def insert(conn: Any, *, asset_id: UUID, listing_id: UUID, original_storage_key: str, version: int) -> None:
    """The row, in the UPLOAD's own transaction (spec C.4's first transition).

    Written inside the transaction that inserts `listing_asset` and appends to `listing.photos`, so
    a committed asset can never exist without a privacy record -- which is the whole of directive
    2's "NO path through which an image can bypass privacy processing" at the database level."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing_asset_privacy (asset_id, listing_id, processing_version, original_storage_key)"
            " VALUES (%s,%s,%s,%s)",
            (asset_id, listing_id, version, original_storage_key),
        )


def enqueue_processing(asset_id: UUID, version: int) -> None:
    """Publishes `media.process_photo` BY NAME, AFTER the caller's transaction has committed.

    By name (`send_task`) rather than by importing the task object: in every deployed environment
    the api must never import `app.tasks.media`, whose transitive imports are the OCR, barcode and
    vision adapters. The queue is named explicitly rather than left to `task_routes` so the routing
    is readable at the call site and does not change if a route is ever edited.

    A failure to publish is NOT swallowed here -- the caller runs this after the commit and outside
    its own `except Refusal`, so a broker outage answers 500 while the row stays `UPLOADED` and
    `media.sweep`'s rule (1) enqueues it within two minutes (spec C.5).

    Task P8 adds one branch above this line, for the Playwright launcher alone (controller
    amendment A-IDP-2): `send_task` does NOT honour `task_always_eager`, so the eager execution
    model cannot be had by a setting on this call."""
    celery_app.send_task("media.process_photo", args=[str(asset_id), version], queue="media")
```

- [ ] **Step 5: GREEN — the upload route**

In `app/api/seller_listings.py`, beside the constants (BRANCH `:593-594`):

```python
#: The magic bytes of the three photo types, checked against the DECLARED Content-Type (spec C.5
#: step 0). `PHOTO_TYPES` alone let through "anything Pillow can open, labelled jpeg/png/webp"; this
#: is the document route's own `_sniffed` rule (`:698-712`) applied to photographs.
PHOTO_MAGIC: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
)


def _sniffed_photo(data: bytes, declared: str) -> str | None:
    """The extension `original.*` takes, or None when the bytes and the header disagree."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return PHOTO_EXT["image/webp"] if declared == "image/webp" else None
    for magic, content_type, suffix in PHOTO_MAGIC:
        if data.startswith(magic):
            return suffix if declared == content_type else None
    return None
```

`_insert_asset` (`:810-828`) takes the key from its caller, because a photograph's key is now a directory and a document's is not — the id is still minted here, for the reason its docstring already gives:

```python
def _insert_asset(conn: Any, listing_id: UUID, kind: str, name: str, content_type: str,
                  data: bytes, digest: str, key_for: Callable[[UUID], str]) -> tuple[UUID, str]:
    asset_id = uuid4()
    key = key_for(asset_id)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing_asset (id, listing_id, kind, name, content_type, byte_size,"
                    " sha256, storage_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (asset_id, listing_id, kind, name, content_type, len(data), digest, key))
    return asset_id, key
```

The document route's call becomes `key_for=lambda a: f"listings/{listing_id}/documents/{a}{suffix}"` — the same string it built before, so no document key moves.

`upload_photo` (`:862-901`), with the encode in a thread and the enqueue after the commit:

```python
@router.post("/listings/{listing_id}/photos", status_code=201)
async def upload_photo(listing_id: str, request: Request, principal: Owner) -> Response:
    """One photograph: the original as received, the normalised display derivative, a privacy row
    and one message (spec 2026-09-09 C.5 step 0).

    Stripping metadata is still the point for the DISPLAY object -- a phone photograph carries GPS
    EXIF and a listing whose location is undisclosed must not ship its coordinates inside a picture
    (A10.2). The ORIGINAL is kept because directive 13 says "NEVER overwrite the original", and it
    is reachable by exactly two handler bodies (the owner's and the reviewer's) and by nothing else.
    """
    hit(sync_redis(), "listing:upload", str(principal.account_id), *LISTING_UPLOAD)
    started: tuple[UUID, int] | None = None
    try:
        store = store_for_request()
        name, content_type, data, _fields = await _upload_bytes(request, MAX_PHOTO_BYTES)
        if content_type not in PHOTO_TYPES:
            raise Refusal("UNSUPPORTED_TYPE", f"A photograph must be one of {', '.join(PHOTO_TYPES)}.", 415)
        ext = _sniffed_photo(data, content_type)
        if ext is None:
            raise Refusal("BAD_IMAGE", "That file could not be read as a photograph.", 422)
        # A thread, because `encode_webp` is a LANCZOS resize plus up to six WebP encodes at
        # method=6 and this handler is `async def` -- inline it blocks the event loop for every
        # other request. `anyio` is a main dependency (`app/auth/passwords.py`'s precedent).
        encoded = await anyio.to_thread.run_sync(encode_webp, data)
        if encoded is None:
            raise Refusal("BAD_IMAGE", "That file could not be read as a photograph.", 422)
        webp, digest = encoded
        with closing(sync_conn()) as conn, conn:
            row = locked_row(conn, listing_id, principal)
            _writable(row)
            photos = photo_list(row["photos"])
            asset_id, key = _insert_asset(conn, row["id"], "photo", name, "image/webp", webp, digest,
                                          lambda a: display_key(row["id"], a))
            source_key = original_key(row["id"], asset_id, ext)
            if _exists(store, source_key):
                raise Refusal("STORAGE_CONFLICT", "That photograph has already been stored.", 409)
            _put(store, source_key, data, content_type)
            _put(store, key, webp, "image/webp")
            privacy_record.insert(conn, asset_id=asset_id, listing_id=row["id"],
                                  original_storage_key=source_key, version=PROCESSING_VERSION)
            with conn.cursor() as cur:
                cur.execute("UPDATE listing SET photos = %s::jsonb, updated_at = now()"
                            " WHERE id = %s AND seller_id = %s",
                            (json.dumps([*photos, str(asset_id)]), row["id"], principal.account_id))
            claim_from_seed(conn, row, principal)
            on_market = take_off_market(conn, row, principal, request)
            payload = _asset_payload(asset_id, "photo", name, "image/webp", len(webp))
            started = (asset_id, PROCESSING_VERSION)
    except Refusal as exc:
        return _refused(exc)
    if on_market:
        drop_list_cache(sync_redis())
    # AFTER the commit (spec C.5 step 0): a task published inside the transaction could be taken by
    # a prefork child before the row it names exists. `started` is None on no path that reaches
    # here -- the `except` above returns -- and mypy needs the narrowing said out loud.
    assert started is not None
    privacy_record.enqueue_processing(*started)
    return JSONResponse(payload, status_code=201)
```

> **`assert started is not None` is a type narrowing, not a runtime check** — every path that leaves `started` unbound returns inside the `except`. `pyproject.toml`'s `[tool.ruff.lint]` carries no `select` key and only `extend-select = ["I", "RUF"]`, so ruff's default set (E4/E7/E9 + F) is what runs and `S101` is not in it — measured on `main` at `073aab8`. If the merged tree's config differs, replace the assert with `if started is None: raise Refusal("STORAGE_UNAVAILABLE", "Object storage is unavailable; try again.", 503)` and cover that branch, and say which you did in the commit body.

Imports added at the top of the module: `import anyio`, `from collections.abc import Callable`, `from app.privacy import PHOTO_EXT, PROCESSING_VERSION, display_key, original_key, photo_prefix`, `from app.privacy import record as privacy_record`.

- [ ] **Step 6: GREEN — the delete removes the prefix**

```python
def _listed(store: ObjectStore, prefix: str) -> list[str]:
    """Every key under `prefix`, with a bucket outage as a refusal rather than a 500 -- `_put` and
    `_drop_object`'s own shape (A-SL16 M2)."""
    try:
        return store.list(prefix)
    except (BotoCoreError, ClientError) as exc:
        raise Refusal("STORAGE_UNAVAILABLE", "Object storage is unavailable; try again.", 503) from exc


def _exists(store: ObjectStore, key: str) -> bool:
    """`store.exists`, with a bucket outage as the same 503 the rest of this module raises.

    `ObjectStore.exists` returns False for a 404 and RE-RAISES every other `ClientError`
    (`app/storage.py:54-61`), so the upload's immutability guard and P10's flip-time derivative
    check would both answer 500 on a bucket blip without this. Same shape as `_put` and
    `_drop_object`, for the same reason (A-SL16 M2)."""
    try:
        return store.exists(key)
    except (BotoCoreError, ClientError) as exc:
        raise Refusal("STORAGE_UNAVAILABLE", "Object storage is unavailable; try again.", 503) from exc
```

and in `delete_asset` (`:1018`), where one object used to go:

```python
            key, kind = found
            # All three (spec C.2): original, display and -- once the worker has written it --
            # redacted. Listed by PREFIX rather than assembled from the row, so a derivative the
            # row does not name (a regeneration interrupted between the put and the UPDATE) goes
            # with it. A document still has exactly one key.
            for gone in (_listed(store, photo_prefix(row["id"], parsed)) if kind == "photo" else [key]):
                _drop_object(store, gone)
```

The privacy row needs no DELETE: `041`'s `ON DELETE CASCADE` removes it with the `listing_asset` row.

- [ ] `poetry run pytest tests/api/test_listing_assets.py -q -W error` — GREEN, all of it.

- [ ] **Step 7: the task's gates**

```bash
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
```

Coverage note: `_sniffed_photo`'s four branches, `_listed`'s two, the `STORAGE_CONFLICT` arm and the document arm of the `for gone in …` expression each have a case above; if any is uncovered, write the case rather than a pragma.

- [ ] **Step 8: commit**

```
feat(api): store the original, the display derivative and a privacy row on every photograph upload

Directive 13: keep the original private and NEVER overwrite it. The upload
route now writes listings/{listing}/photos/{asset}/original.{ext} (the
bytes as received, guarded by exists() so a key is never written twice)
and .../display.webp (today's normalised, metadata-free encode, which
listing_asset.storage_key goes on naming), inserts the listing_asset_privacy
row in the same transaction, and publishes media.process_photo BY NAME
after the commit -- so the api imports no engine and a task can never find
no row. A lost publish leaves an UPLOADED row for the sweeper.

The encode moves to a worker thread (anyio.to_thread) so a 15 MiB upload
no longer blocks the event loop, and a magic-byte sniff cross-checks the
declared Content-Type: the route used to accept anything Pillow could open
under a jpeg header.

Delete removes every object under the asset's prefix rather than the one
key it knew about; the privacy row goes by CASCADE.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `git add app/privacy/__init__.py app/privacy/record.py app/api/seller_listings.py tests/conftest.py tests/api/conftest.py tests/privacy/__init__.py tests/privacy/test_keys.py tests/api/test_listing_assets.py`

---

### Task P3: the state machine — one function per transition, one test per transition and per dead end

**Note against the spec.** §C.5's module list names eight modules and puts the transition table in §C.4 without naming a module for it. Every later task needs one place that owns the claim statement, the confirmation-reset rule and the CHECK-safe writes, so `app/privacy/record.py` (created in P2) is that place. Recorded as controller amendment **A-IDP-1**; no engine, no Pillow and no boto import ever enters it.

**Files:**
- Modify: `app/privacy/record.py`
- Create: `tests/privacy/test_record.py`

**Interfaces:**
- Consumes: P1's table and its CHECKs; P2's `insert`.
- Produces, `app/privacy/record.py`:
  - `READY_STATES: tuple[str, ...] = ("READY_FOR_REVIEW", "SELLER_CONFIRMED", "PUBLISHED")`
  - `ERROR_STATES: tuple[str, ...] = ("PROCESSING_FAILED", "REDACTION_FAILED", "REVIEW_REQUIRED", "REPROCESS_REQUIRED")`
  - `CLAIMABLE_STATES: tuple[str, ...] = ("UPLOADED", "PROCESSING_FAILED", "REDACTION_FAILED", "REPROCESS_REQUIRED")`
  - `LOST_AFTER = "6 minutes"`, `MAX_ATTEMPTS = 3`, `BACKOFF = (30, 120, 600)` — **only the first `MAX_ATTEMPTS - 1` rungs are ever spent** (the third failure exhausts rather than re-enqueueing), so today's ladder is 30 s then 2 min and the 10-min rung is headroom for a raised bound. Pinned by a test, and said in every commit body and in the runbook rather than described as a three-rung ladder that runs.
  - `RESET_COLUMNS: str` — the confirmation-reset rule as one SQL fragment
  - `@dataclass(frozen=True) class PrivacyRow` with `asset_id: UUID`, `listing_id: UUID`, `processing_status: str`, `processing_version: int`, `attempts: int`, `original_storage_key: str`, `redacted_storage_key: str | None`, `redacted_sha256: str | None`, `confirmed_sha256: str | None`, `seller_confirmed: bool`, `buyer_visible: bool`, `redaction_regions: list[dict[str, Any]]`, `reprocess_reason: str | None`, `final_privacy_state: str | None`, `display_storage_key: str | None`, `display_sha256: str | None` — `final_privacy_state` is here from the start, not added later by P10: it is what P10's flip compares (`seller_confirmed AND final_privacy_state = 'NOT_SHOW'`), and a field added to a frozen dataclass in a later task breaks every constructor P9's `test_delivery.py` already wrote.
  - `read(conn, asset_id: UUID) -> PrivacyRow | None`, `rows_for(conn, listing_id: UUID) -> list[PrivacyRow]`
  - `claim(conn, asset_id: UUID, version: int) -> PrivacyRow | None`
  - `record_scan(conn, asset_id: UUID, *, ocr, identity_matches, vision, detected_regions) -> None`
  - `record_derivative(conn, asset_id: UUID, *, key: str, sha256: str, regions: list[dict[str, Any]]) -> None`
  - `fail(conn, asset_id: UUID, *, state: str, code: str) -> int`
  - `exhaust(conn, asset_id: UUID, *, code: str) -> None`
  - `confirm(conn, asset_id: UUID, *, account_id: UUID, visibility: str, edited: bool) -> bool`
  - `reset_confirmation(conn, asset_id: UUID, *, regions: list[dict[str, Any]] | None = None) -> bool` — guarded by `READY_STATES`; False means "this row was not ready, do not promote it"
  - `mark_ready(conn, asset_id: UUID, *, visible: bool, version: int) -> None`
  - `reset_for_retry(conn, asset_id: UUID) -> bool`
  - `flag_stale(conn, *, listing_id: UUID, reason: str) -> list[UUID]`
  - `advance_in_place(conn, asset_id: UUID, *, sha256: str, version: int, regions: list[dict[str, Any]]) -> None`
  - `mark_published(conn, listing_id: UUID) -> None`
  - `set_visibility(conn, asset_id: UUID, *, visible: bool) -> None`

- [ ] **Step 1: RED — the transition table, one case per row of spec §C.4**

Create `tests/privacy/test_record.py`:

```python
"""One case per transition of spec 2026-09-09 C.4, and one per dead end.

Directive 6: "No image may silently fall through the state machine." The proof of that is here: a
transition that is not in this table has no function to perform it, and every function refuses from
a state the table does not name."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.privacy import record

# (from, to, the call that performs it) -- the table read straight off spec C.4.
TRANSITIONS = (
    ("UPLOADED", "PROCESSING", "claim"),
    ("PROCESSING_FAILED", "PROCESSING", "claim"),
    ("REDACTION_FAILED", "PROCESSING", "claim"),
    ("REPROCESS_REQUIRED", "PROCESSING", "claim"),
    ("PROCESSING", "SCANNED", "record_scan"),
    ("SCANNED", "REDACTION_GENERATED", "record_derivative"),
    ("REDACTION_GENERATED", "READY_FOR_REVIEW", "mark_ready"),
    ("READY_FOR_REVIEW", "SELLER_CONFIRMED", "confirm"),
    ("PROCESSING", "PROCESSING_FAILED", "fail"),
    ("SCANNED", "REDACTION_FAILED", "fail"),
    ("PROCESSING", "REVIEW_REQUIRED", "exhaust"),
    ("REVIEW_REQUIRED", "UPLOADED", "reset_for_retry"),
    ("PROCESSING_FAILED", "UPLOADED", "reset_for_retry"),
    ("REDACTION_FAILED", "UPLOADED", "reset_for_retry"),
    ("REPROCESS_REQUIRED", "UPLOADED", "reset_for_retry"),
)

# States from which the claim must write NOTHING: a ready row is never re-run by this path (its
# in-place re-run is `advance_in_place`), and a fresh PROCESSING row is another child's work.
UNCLAIMABLE = ("PROCESSING", "SCANNED", "REDACTION_GENERATED", "READY_FOR_REVIEW",
               "SELLER_CONFIRMED", "PUBLISHED", "REVIEW_REQUIRED")


#: The builder Step 2 writes; every privacy suite imports it, so a CHECK that changes fails once.
from tests.privacy.conftest import make_account, make_row as _row  # noqa: E402

def _perform(conn: Any, call: str, asset_id: UUID, listing_id: UUID) -> None:
    """The one call each transition names, with the arguments that transition takes. A `match` and
    not a dict of partials: mypy --strict types each arm, and an arm added without a TRANSITIONS row
    (or a row added without an arm) is a compile error rather than a KeyError at run time."""
    match call:
        case "claim":
            record.claim(conn, asset_id, 1)
        case "record_scan":
            record.record_scan(conn, asset_id, ocr={"size": [800, 600], "lines": []},
                               identity_matches=[], vision={"status": "unavailable"}, detected_regions=[])
        case "record_derivative":
            record.record_derivative(conn, asset_id, key=f"listings/{listing_id}/photos/{asset_id}/redacted.webp",
                                     sha256="b" * 64, regions=[])
        case "mark_ready":
            record.mark_ready(conn, asset_id, visible=False, version=1)
        case "confirm":
            record.confirm(conn, asset_id, account_id=make_account(conn), visibility="NOT_SHOW", edited=False)
        case "fail":
            state = "REDACTION_FAILED" if record.read(conn, asset_id).processing_status == "SCANNED" \
                else "PROCESSING_FAILED"
            record.fail(conn, asset_id, state=state, code="UNDECODABLE")
        case "exhaust":
            record.exhaust(conn, asset_id, code="OCR_ERROR")
        case _:
            record.reset_for_retry(conn, asset_id)


@pytest.mark.parametrize(("start", "end", "call"), TRANSITIONS)
def test_every_contracted_transition_is_performed_by_its_own_function(
    conn: Any, start: str, end: str, call: str
) -> None:
    asset_id, listing_id = _row(conn, processing_status=start)
    _perform(conn, call, asset_id, listing_id)
    assert record.read(conn, asset_id).processing_status == end


@pytest.mark.parametrize("start", UNCLAIMABLE)
def test_the_claim_writes_nothing_from_a_state_it_does_not_own(conn: Any, start: str) -> None:
    """The dead ends. A duplicate message, a late retry and a redelivered task all land here, and
    what makes them harmless is that the claim is ONE conditional UPDATE that matches no row."""
    asset_id, _ = _row(conn, processing_status=start)
    before = record.read(conn, asset_id)
    assert record.claim(conn, asset_id, 1) is None
    assert record.read(conn, asset_id) == before


def test_a_lost_processing_row_is_claimable_after_six_minutes(conn: Any) -> None:
    """`acks_late` + `reject_on_worker_lost`: a child killed mid-run leaves the row PROCESSING. The
    redelivered run finds it recent and writes nothing; the sweeper's rule (2) marks it
    REPROCESS_REQUIRED. This is the window that separates the two."""
    asset_id, _ = _row(conn, processing_status="PROCESSING", attempts=1)
    assert record.claim(conn, asset_id, 1) is None
    with conn.cursor() as cur:
        cur.execute("UPDATE listing_asset_privacy SET updated_at = %s WHERE asset_id = %s",
                    (datetime.now(UTC) - timedelta(minutes=7), asset_id))
    claimed = record.claim(conn, asset_id, 1)
    assert claimed is not None and claimed.attempts == 2


def test_a_stale_enqueue_below_the_current_version_claims_nothing(conn: Any) -> None:
    asset_id, _ = _row(conn, processing_status="UPLOADED", processing_version=2)
    assert record.claim(conn, asset_id, 1) is None


def test_the_claim_applies_the_confirmation_reset_rule(conn: Any) -> None:
    """Spec C.4's reset rule: a derivative the seller has not seen can never inherit a
    confirmation. Applied IN THE CLAIM's own statement, so no window exists between the two."""
    asset_id, _ = _row(conn, processing_status="REDACTION_FAILED", confirmed=True)
    claimed = record.claim(conn, asset_id, 1)
    assert claimed is not None
    after = record.read(conn, asset_id)
    assert (after.seller_confirmed, after.confirmed_sha256, after.buyer_visible) == (False, None, False)


def test_a_confirmed_row_keeps_its_confirmation_through_an_in_place_re_run(conn: Any) -> None:
    """The ONE derivative write that does not reset (spec C.5): the in-place re-run of a confirmed
    row, whose region set is by construction a superset of the confirmed one, advances
    confirmed_sha256 with redacted_sha256 in the same UPDATE."""
    asset_id, _ = _row(conn, processing_status="SELLER_CONFIRMED", confirmed=True,
                       reprocess_reason="VERSION")
    record.advance_in_place(conn, asset_id, sha256="e" * 64, version=2, regions=[])
    after = record.read(conn, asset_id)
    assert after.processing_status == "SELLER_CONFIRMED"
    assert after.seller_confirmed and after.confirmed_sha256 == "e" * 64 == after.redacted_sha256
    assert after.reprocess_reason is None and after.processing_version == 2


def test_confirm_refuses_from_every_state_but_ready_and_is_idempotent_from_confirmed(conn: Any) -> None:
    """Directive 11: "Never allow AI_PASSED to mean READY_TO_PUBLISH." A failed photograph cannot
    be confirmed INTO readiness."""
    account = make_account(conn)   # `seller_confirmation_account_id` REFERENCES account(id)
    for start in ("UPLOADED", "PROCESSING", "SCANNED", "REDACTION_GENERATED", "REVIEW_REQUIRED"):
        asset_id, _ = _row(conn, processing_status=start)
        assert record.confirm(conn, asset_id, account_id=account, visibility="NOT_SHOW", edited=False) is False
    ready, _ = _row(conn, processing_status="READY_FOR_REVIEW")
    assert record.confirm(conn, ready, account_id=account, visibility="NOT_SHOW", edited=False) is True
    assert record.confirm(conn, ready, account_id=account, visibility="NOT_SHOW", edited=False) is True


def test_reset_for_retry_refuses_from_a_ready_state(conn: Any) -> None:
    for start in record.READY_STATES + ("PROCESSING", "SCANNED", "REDACTION_GENERATED"):
        asset_id, _ = _row(conn, processing_status=start)
        assert record.reset_for_retry(conn, asset_id) is False


def test_publishing_advances_only_the_gated_rows_and_never_reverts(conn: Any) -> None:
    """PUBLISHED means "published at least once": a pause, unpublish or withdrawal does not revert
    it -- `_published_photos`' status filter is what hides the listing (spec C.4)."""
    confirmed, listing_id = _row(conn, processing_status="SELLER_CONFIRMED", confirmed=True)
    pending, _ = _row(conn, processing_status="UPLOADED", listing_id=listing_id)
    record.mark_published(conn, listing_id)
    assert record.read(conn, confirmed).processing_status == "PUBLISHED"
    assert record.read(conn, pending).processing_status == "UPLOADED"


def _executed_sql(module: Any) -> list[str]:
    """Every `cur.execute(...)` call's SQL in `module`, one string per CALL.

    An AST walk and not a regex over the source: a regex that ends a "statement" at a blank line or
    a docstring quote can span two `execute` calls, and one that contains `updated_at = now()`
    would then hide a neighbour that does not. `ast` gives the call boundary exactly. The literal
    parts of an f-string are Constants inside the JoinedStr, so `{RESET_COLUMNS}` contributes
    nothing -- which is right: every statement writes `updated_at = now()` in its own text,
    outside that fragment."""
    import ast
    import inspect

    found: list[str] = []
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "execute" and node.args):
            continue
        found.append(" ".join(piece.value for piece in ast.walk(node.args[0])
                              if isinstance(piece, ast.Constant) and isinstance(piece.value, str)))
    return found


def test_every_update_in_the_module_sets_updated_at() -> None:
    """The sweeper's age windows and `listing_asset_privacy_sweep_idx` read `updated_at`, and there
    is no trigger precedent in `migrations/` -- `listing.updated_at` is maintained the same way, by
    hand, in `app/api/seller_listings.py`. A statement that forgets it makes a row invisible to the
    sweeper for ever, so the rule is checked rather than trusted (spec C.3)."""
    updates = [sql for sql in _executed_sql(record) if "UPDATE listing_asset_privacy" in sql]
    assert len(updates) >= 8, "far fewer UPDATEs than this module has -- the walk found the wrong calls"
    missing = [sql[:120] for sql in updates if "updated_at = now()" not in sql]
    assert missing == [], missing


def test_the_reset_promotes_nothing_from_a_state_that_is_not_ready(conn: Any) -> None:
    """Spec C.1 step 3 says the reset's transitions come "from SELLER_CONFIRMED/PUBLISHED". Without
    the READY_STATES guard this UPDATE is `WHERE asset_id = %s` and it PROMOTES: a REDACTION_FAILED
    row that still carries a stale derivative key would become READY_FOR_REVIEW, then confirmable,
    then buyer-visible over a derivative whose regeneration had failed."""
    for start in ("UPLOADED", "PROCESSING", "SCANNED", "PROCESSING_FAILED", "REDACTION_FAILED",
                  "REVIEW_REQUIRED", "REPROCESS_REQUIRED"):
        asset_id, _ = _row(conn, processing_status=start)
        assert record.reset_confirmation(conn, asset_id) is False
        assert record.read(conn, asset_id).processing_status == start
    for start in record.READY_STATES:
        asset_id, _ = _row(conn, processing_status=start, confirmed=start == "SELLER_CONFIRMED")
        assert record.reset_confirmation(conn, asset_id) is True
        assert record.read(conn, asset_id).processing_status == "READY_FOR_REVIEW"


def test_only_the_rungs_the_bound_can_spend_are_ever_spent() -> None:
    """`_retry_or_exhaust` re-enqueues only while `attempts < MAX_ATTEMPTS`, so with three attempts
    the ladder that actually runs is BACKOFF[0] and BACKOFF[1]. The third rung is headroom for a
    raised bound and is pinned here so no commit body, docstring or runbook can describe a
    "30 s / 2 min / 10 min ladder" that never reaches its last rung."""
    assert record.MAX_ATTEMPTS == 3
    assert record.BACKOFF[:record.MAX_ATTEMPTS - 1] == (30, 120)
    assert len(record.BACKOFF) >= record.MAX_ATTEMPTS - 1


def test_a_completed_run_stamps_the_version_it_ran_under(conn: Any) -> None:
    """Spec C.5 step 7. A row created before a version bump and completed after it must not be left
    below the constant: the sweeper would flag it VERSION within five minutes and re-run in place a
    scan that had just been done."""
    asset_id, _ = _row(conn, processing_status="REDACTION_GENERATED", processing_version=1)
    record.mark_ready(conn, asset_id, visible=False, version=4)
    assert record.read(conn, asset_id).processing_version == 4
```

- [ ] **Step 2: RED — the shared builder**

Create `tests/privacy/conftest.py` with `_row`'s real implementation, exported as a fixture-free helper the suites above and in P7–P13 all import:

```python
"""One builder for a privacy row in any state, with whatever migration 041's CHECKs require of
that state already true. Every privacy suite uses it, so a CHECK that changes fails in one place."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.privacy import display_key, original_key, redacted_key

#: The four states `lap_ready_has_derivative_ck` requires a derivative for.
HAS_DERIVATIVE = ("REDACTION_GENERATED", "READY_FOR_REVIEW", "SELLER_CONFIRMED", "PUBLISHED")

_INSERT = """
INSERT INTO listing_asset_privacy
  (asset_id, listing_id, processing_status, processing_version, attempts, original_storage_key,
   redacted_storage_key, redacted_sha256, confirmed_sha256, seller_confirmed, seller_confirmed_at,
   final_privacy_state, buyer_visible, reprocess_reason, reprocess_requested_at,
   redaction_regions, seller_review_status)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
"""


def make_account(conn: Any, email: str | None = None) -> UUID:
    """`seller_confirmation_account_id REFERENCES account(id)`, so a confirmation needs a real row."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, status) VALUES (%s,'active') RETURNING id",
                    (email or f"idp-{uuid4().hex[:8]}@example.org",))
        return UUID(str(cur.fetchone()[0]))


def make_listing(conn: Any, slug: str, *, status: str = "draft", visibility: str = "NOT_SHOW") -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, status,"
            " est, price, zip, photos, identifiable_content_visibility)"
            " VALUES (%s,'Hill Country Animal Hospital','Cedar Park','TX','Cedar Park','Small animal',"
            "'Austin, TX','seller',%s,1998,100,'78613','[]'::jsonb,%s) RETURNING id",
            (slug, status, visibility),
        )
        return UUID(str(cur.fetchone()[0]))


def make_row(conn: Any, *, listing_id: UUID | None = None, processing_status: str = "UPLOADED",
             processing_version: int = 1, attempts: int = 0, confirmed: bool = False,
             buyer_visible: bool = False, reprocess_reason: str | None = None,
             redaction_regions: list[dict[str, Any]] | None = None) -> tuple[UUID, UUID]:
    """(asset_id, listing_id). The asset row, its entry in `listing.photos` and its privacy row."""
    listing = listing_id if listing_id is not None else make_listing(conn, f"idp-{uuid4().hex[:8]}")
    asset_id = uuid4()
    now = datetime.now(UTC)
    ready = processing_status in HAS_DERIVATIVE
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing_asset (id, listing_id, kind, name, content_type, byte_size,"
                    " sha256, storage_key) VALUES (%s,%s,'photo','a.webp','image/webp',10,%s,%s)",
                    (asset_id, listing, "d" * 64, display_key(listing, asset_id)))
        cur.execute("UPDATE listing SET photos = photos || to_jsonb(%s::text) WHERE id = %s",
                    (str(asset_id), listing))
        cur.execute(_INSERT, (
            asset_id, listing, processing_status, processing_version, attempts,
            original_key(listing, asset_id, ".jpg"),
            redacted_key(listing, asset_id) if ready else None,
            "b" * 64 if ready else None,
            "b" * 64 if confirmed else None,
            confirmed, now if confirmed else None,
            "NOT_SHOW" if confirmed else None,
            buyer_visible, reprocess_reason, now if reprocess_reason else None,
            json.dumps(redaction_regions or []), "looks_good" if confirmed else "pending",
        ))
    return asset_id, listing
```

- [ ] `poetry run pytest tests/privacy/test_record.py -q -W error` — RED: `AttributeError: module 'app.privacy.record' has no attribute 'READY_STATES'`.

- [ ] **Step 3: GREEN — the state machine**

Append to `app/privacy/record.py`:

```python
#: Spec C.4's three ready states. `buyer_visible` is never true outside them (lap_visible_ready_ck).
READY_STATES = ("READY_FOR_REVIEW", "SELLER_CONFIRMED", "PUBLISHED")
#: Directive 6's four. Left only by the claim of a retry, a Try-again or a delete.
ERROR_STATES = ("PROCESSING_FAILED", "REDACTION_FAILED", "REVIEW_REQUIRED", "REPROCESS_REQUIRED")
#: What `media.process_photo` may take. REVIEW_REQUIRED is NOT here: its retries are spent and only
#: the seller's "Try again" moves it.
CLAIMABLE_STATES = ("UPLOADED", "PROCESSING_FAILED", "REDACTION_FAILED", "REPROCESS_REQUIRED")
#: The hard time limit (300 s) plus a minute -- past it a PROCESSING row is a lost child.
LOST_AFTER = "6 minutes"
MAX_ATTEMPTS = 3
#: Seconds before the first, second and third re-enqueue (spec C.5). Never `Task.retry()`.
BACKOFF = (30, 120, 600)

#: The confirmation-reset rule, as one fragment so every writer applies exactly the same one.
#: "Every write that produces, or will produce, a derivative the seller has not seen" (spec C.4).
RESET_COLUMNS = (
    "seller_confirmed = false, seller_confirmed_at = NULL, seller_confirmation_account_id = NULL,"
    " final_privacy_state = NULL, confirmed_sha256 = NULL, seller_review_status = 'pending',"
    " buyer_visible = false"
)

_READ = """
SELECT p.asset_id, p.listing_id, p.processing_status, p.processing_version, p.attempts,
       p.original_storage_key, p.redacted_storage_key, p.redacted_sha256, p.confirmed_sha256,
       p.seller_confirmed, p.buyer_visible, p.redaction_regions, p.reprocess_reason,
       p.final_privacy_state,
       a.storage_key AS display_storage_key, a.sha256 AS display_sha256
  FROM listing_asset_privacy p JOIN listing_asset a ON a.id = p.asset_id
"""


@dataclass(frozen=True)
class PrivacyRow:
    """One photograph's record, joined to the `listing_asset` row that holds the DISPLAY key and
    hash -- so `app/privacy/delivery.py::buyer_variant` can decide a request from one object and
    the resolver stays pure."""

    asset_id: UUID
    listing_id: UUID
    processing_status: str
    processing_version: int
    attempts: int
    original_storage_key: str
    redacted_storage_key: str | None
    redacted_sha256: str | None
    confirmed_sha256: str | None
    seller_confirmed: bool
    buyer_visible: bool
    redaction_regions: list[dict[str, Any]]
    reprocess_reason: str | None
    #: The listing's setting at the moment of confirmation. P10's SHOW -> NOT_SHOW flip compares it
    #: (`seller_confirmed AND final_privacy_state = 'NOT_SHOW'`); nothing else reads it.
    final_privacy_state: str | None
    display_storage_key: str | None
    display_sha256: str | None


def _row(values: tuple[Any, ...]) -> PrivacyRow:
    return PrivacyRow(*values)  # type: ignore[arg-type]  # psycopg2 returns Any; the SELECT's order is the dataclass's


def read(conn: Any, asset_id: UUID) -> PrivacyRow | None:
    with conn.cursor() as cur:
        cur.execute(f"{_READ} WHERE p.asset_id = %s", (asset_id,))
        found = cur.fetchone()
    return None if found is None else _row(found)


def rows_for(conn: Any, listing_id: UUID) -> list[PrivacyRow]:
    with conn.cursor() as cur:
        cur.execute(f"{_READ} WHERE p.listing_id = %s ORDER BY p.created_at, p.asset_id", (listing_id,))
        return [_row(r) for r in cur.fetchall()]


def claim(conn: Any, asset_id: UUID, version: int) -> PrivacyRow | None:
    """ONE conditional UPDATE, and the whole of this pipeline's idempotency (spec C.5).

    A run that claims nothing writes nothing and returns None -- which is what makes a duplicate
    message harmless, a redelivered task a no-op and a late retry unable to clobber a confirmation:
    a ready row is never claimed by this path. The reset rule is applied in the SAME statement, so
    a fresh run can never inherit a confirmation, and a version below the current one claims
    nothing at all (a stale enqueue)."""
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE listing_asset_privacy SET processing_status = 'PROCESSING',"
            f" attempts = attempts + 1, last_error = NULL, {RESET_COLUMNS}, updated_at = now()"
            f" WHERE asset_id = %s AND processing_version <= %s"
            f"   AND (processing_status = ANY(%s)"
            f"        OR (processing_status = 'PROCESSING' AND updated_at < now() - interval '{LOST_AFTER}'))"
            f" RETURNING asset_id",
            (asset_id, version, list(CLAIMABLE_STATES)),
        )
        if cur.fetchone() is None:
            return None
    return read(conn, asset_id)


def record_scan(conn: Any, asset_id: UUID, *, ocr: dict[str, Any], identity_matches: list[dict[str, Any]],
                vision: dict[str, Any], detected_regions: list[dict[str, Any]]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = 'SCANNED', ocr = %s::jsonb,"
            " identity_matches = %s::jsonb, vision = %s::jsonb, detected_regions = %s::jsonb,"
            " updated_at = now() WHERE asset_id = %s AND processing_status = 'PROCESSING'",
            (json.dumps(ocr), json.dumps(identity_matches), json.dumps(vision),
             json.dumps(detected_regions), asset_id),
        )


def record_derivative(conn: Any, asset_id: UUID, *, key: str, sha256: str,
                      regions: list[dict[str, Any]]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = 'REDACTION_GENERATED',"
            " redacted_storage_key = %s, redacted_sha256 = %s, redaction_regions = %s::jsonb,"
            " updated_at = now() WHERE asset_id = %s AND processing_status = 'SCANNED'",
            (key, sha256, json.dumps(regions), asset_id),
        )


def mark_ready(conn: Any, asset_id: UUID, *, visible: bool, version: int) -> None:
    """REDACTION_GENERATED -> READY_FOR_REVIEW, `detection_at` and `processing_version` stamped.
    Under SHOW the photograph becomes buyer-visible here without a confirmation; under NOT_SHOW only
    `confirm` does that.

    `processing_version = %s` is spec C.5 step 7's "processing_version stamped", and it is written
    HERE and not at the claim because the version a completed record should carry is the one the RUN
    used. A row created before a version bump and completed after it would otherwise stay below the
    constant, be flagged VERSION by the sweeper within five minutes, and be re-run in place for a
    scan it had just done."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = 'READY_FOR_REVIEW',"
            " detection_at = now(), processing_version = %s, buyer_visible = %s, updated_at = now()"
            " WHERE asset_id = %s AND processing_status = 'REDACTION_GENERATED'",
            (version, visible, asset_id),
        )


def fail(conn: Any, asset_id: UUID, *, state: str, code: str) -> int:
    """PROCESSING_FAILED or REDACTION_FAILED with a reason CODE, never bytes and never response
    text. Returns the attempts spent, which is what decides between a re-enqueue and `exhaust`."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = %s, last_error = %s,"
            " updated_at = now() WHERE asset_id = %s RETURNING attempts",
            (state, code, asset_id),
        )
        return int(cur.fetchone()[0])


def exhaust(conn: Any, asset_id: UUID, *, code: str) -> None:
    """The failure that spends the third attempt: REVIEW_REQUIRED, the reset rule applied,
    `buyer_visible` false -- a fail-closed null slot, on a published listing too. Never the
    original (directive 19)."""
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE listing_asset_privacy SET processing_status = 'REVIEW_REQUIRED',"
            f" last_error = %s, {RESET_COLUMNS}, updated_at = now() WHERE asset_id = %s",
            (code, asset_id),
        )


def confirm(conn: Any, asset_id: UUID, *, account_id: UUID, visibility: str, edited: bool) -> bool:
    """"Looks good". True when the row is (now) confirmed, False when its state forbids it.

    Idempotent from SELLER_CONFIRMED, refused from every other state -- 409 STATE at the route.
    `confirmed_sha256 := redacted_sha256` is what `lap_confirmed_ck` then holds, which makes
    "confirmed against its current derivative" a column comparison rather than an inference."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = 'SELLER_CONFIRMED',"
            " seller_confirmed = true, seller_confirmed_at = now(),"
            " seller_confirmation_account_id = %s, final_privacy_state = %s,"
            " confirmed_sha256 = redacted_sha256, buyer_visible = true,"
            " seller_review_status = CASE WHEN %s OR seller_review_status = 'edited'"
            "                             THEN 'edited' ELSE 'looks_good' END,"
            " updated_at = now()"
            " WHERE asset_id = %s AND processing_status IN ('READY_FOR_REVIEW','SELLER_CONFIRMED')"
            "   AND redacted_sha256 IS NOT NULL RETURNING asset_id",
            (account_id, visibility, edited, asset_id),
        )
        return cur.fetchone() is not None


def reset_confirmation(conn: Any, asset_id: UUID, *, regions: list[dict[str, Any]] | None = None) -> bool:
    """A mask added or removed, or the SHOW -> NOT_SHOW flip on a row not confirmed under NOT_SHOW:
    back to READY_FOR_REVIEW with the reset rule and `seller_review_status` 'edited'. True when a row
    moved.

    **Guarded by the three READY states**, which is the whole of its safety. Without the guard this
    is `WHERE asset_id = %s` and it PROMOTES: a REDACTION_FAILED or REVIEW_REQUIRED row that still
    carries a stale `redacted_storage_key` (which `lap_ready_has_derivative_ck` permits, since it
    only constrains the ready states downwards) would become READY_FOR_REVIEW, be confirmable, and
    end up `buyer_visible` over a derivative whose regeneration had failed. Spec C.1 step 3 says
    these transitions come "from SELLER_CONFIRMED/PUBLISHED"; a non-ready row belongs on the
    re-enqueue arm instead, and P10's `apply_visibility_change` reads this function's False as
    exactly that instruction.

    Under SHOW the row's visibility returns with readiness, which `mark_ready` does; here it goes
    false in every case, because between this write and the regeneration the derivative on the
    bucket is not the one the row describes."""
    with conn.cursor() as cur:
        if regions is None:
            cur.execute(f"UPDATE listing_asset_privacy SET processing_status = 'READY_FOR_REVIEW',"
                        f" {RESET_COLUMNS}, seller_review_status = 'edited', updated_at = now()"
                        f" WHERE asset_id = %s AND processing_status = ANY(%s) RETURNING asset_id",
                        (asset_id, list(READY_STATES)))
        else:
            cur.execute(f"UPDATE listing_asset_privacy SET processing_status = 'READY_FOR_REVIEW',"
                        f" {RESET_COLUMNS}, seller_review_status = 'edited',"
                        f" redaction_regions = %s::jsonb, updated_at = now()"
                        f" WHERE asset_id = %s AND processing_status = ANY(%s) RETURNING asset_id",
                        (json.dumps(regions), asset_id, list(READY_STATES)))
        return cur.fetchone() is not None


def reset_for_retry(conn: Any, asset_id: UUID) -> bool:
    """"Try again", from the four error states only -- 409 STATE from anywhere else."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = 'UPLOADED', attempts = 0,"
            " last_error = NULL, updated_at = now()"
            " WHERE asset_id = %s AND processing_status = ANY(%s) RETURNING asset_id",
            (asset_id, list(ERROR_STATES)),
        )
        return cur.fetchone() is not None


def flag_stale(conn: Any, *, listing_id: UUID, reason: str) -> list[UUID]:
    """Staleness is a FLAG, never a state (D-IDP-16): the ready rows of this listing are marked and
    their CURRENT derivatives go on being served while the in-place re-run replaces them. Returns
    the rows to enqueue after the commit."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET reprocess_reason = %s, reprocess_requested_at = now(),"
            " updated_at = now() WHERE listing_id = %s AND processing_status = ANY(%s)"
            "   AND reprocess_reason IS NULL RETURNING asset_id",
            (reason, listing_id, list(READY_STATES)),
        )
        return [UUID(str(r[0])) for r in cur.fetchall()]


def advance_in_place(conn: Any, asset_id: UUID, *, sha256: str, version: int,
                     regions: list[dict[str, Any]]) -> None:
    """The one derivative write that does not reset (spec C.5). The re-run's region set is the OLD
    set unioned with the new on a confirmed row, so the fresh derivative hides a superset of what
    the seller confirmed -- which is what makes advancing `confirmed_sha256` with `redacted_sha256`
    honest rather than a silent re-confirmation. The state, `buyer_visible` and
    `lap_visible_ready_ck` are untouched, so a version bump darkens no listing."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET redacted_sha256 = %s,"
            " confirmed_sha256 = CASE WHEN seller_confirmed THEN %s ELSE confirmed_sha256 END,"
            " redaction_regions = %s::jsonb, processing_version = %s, reprocessed_at = now(),"
            " reprocess_reason = NULL, reprocess_requested_at = NULL, attempts = 0,"
            " updated_at = now() WHERE asset_id = %s",
            (sha256, sha256, json.dumps(regions), version, asset_id),
        )


def mark_published(conn: Any, listing_id: UUID) -> None:
    """Every gated photograph of a listing that has just reached `published`. PUBLISHED means
    "published at least once" and is not reverted by a pause, unpublish or withdrawal -- the
    listing's own status filter is what hides it (spec C.4)."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = 'PUBLISHED', updated_at = now()"
            " WHERE listing_id = %s AND processing_status IN ('READY_FOR_REVIEW','SELLER_CONFIRMED')"
            "   AND buyer_visible",
            (listing_id,),
        )


def set_visibility(conn: Any, asset_id: UUID, *, visible: bool) -> None:
    """The NOT_SHOW -> SHOW flip's per-row arm (spec C.1 step 4): readiness alone decides."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET buyer_visible = %s, updated_at = now()"
            " WHERE asset_id = %s AND (NOT %s OR processing_status = ANY(%s))",
            (visible, asset_id, visible, list(READY_STATES)),
        )
```

Imports added at the top: `import json`, `from dataclasses import dataclass`, `from typing import Any`.

- [ ] `poetry run pytest tests/privacy/test_record.py -q -W error` — GREEN, every parametrised case.

- [ ] **Step 4: the task's gates**

```bash
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
```

- [ ] **Step 5: commit**

```
feat(privacy): the per-image state machine -- one function per transition, one test per dead end

Directive 6: "No image may silently fall through the state machine." Every
transition in the spec's C.4 table now has exactly one function, and every
function refuses from a state the table does not name -- proved by a
parametrised case per transition and a case per unclaimable state.

The claim is one conditional UPDATE and is the whole of the pipeline's
idempotency: a duplicate message, a redelivered task and a late retry all
match no row and write nothing, so a confirmation can never be clobbered
by a task that arrives after it. The confirmation-reset rule is applied
inside that same statement, so a derivative the seller has not seen can
never inherit a confirmation, and the one write that does NOT reset -- the
in-place re-run of a confirmed row -- advances confirmed_sha256 with
redacted_sha256 because its region set is a superset of the confirmed one.

Staleness is a flag, not a state: a marked ready row goes on serving the
derivative it has while the re-run replaces it.

Two guards are the point of their own cases. mark_ready stamps
processing_version with the version the RUN used, so a row created before
a bump and finished after it is not immediately stale. reset_confirmation
is scoped to the three ready states: unscoped it would promote a
REDACTION_FAILED row -- which may still carry a stale derivative key --
into READY_FOR_REVIEW and thence into buyer_visible.

The backoff ladder is (30, 120, 600) but the bound is three attempts, so
only the first two rungs are ever spent; the third is headroom and a test
says so, rather than three commit bodies describing a rung that never runs.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `git add app/privacy/record.py tests/privacy/conftest.py tests/privacy/test_record.py`

---

### Task P4: the OCR and 2D-symbol adapters, their engines, and the test-only settings

**Files:**
- Create: `app/privacy/ocr.py`, `app/privacy/barcodes.py`
- Create: `tests/privacy/test_ocr.py`, `tests/privacy/test_barcodes.py`
- Create: `tests/e2e/stub_engines.py`
- Modify: `app/config.py` (`privacy_engine_module`, `celery_task_always_eager`, the test-only validator), `.env.example`, `DEPLOY.md`, `pyproject.toml`, `poetry.lock`, `Dockerfile`, `tests/test_config.py`, `tests/test_docs.py`

**Interfaces:**
- Consumes: nothing from earlier tasks — these two modules import no `app.privacy` sibling, which is what keeps them the only importers of an engine.
- Produces, `app/privacy/ocr.py`: `class Line(NamedTuple)` with `text: str`, `confidence: float`, `quad: list[tuple[float, float]]`; `class OcrUnavailable(RuntimeError)`; `class OcrError(RuntimeError)`; `ENGINE: str`; `UPSCALE_BELOW_PX: int`; `read_text(image: Image.Image) -> list[Line]`.
- Produces, `app/privacy/barcodes.py`: `class Symbol(NamedTuple)` with `fmt: str`, `payload_kind: str`, `quad: list[tuple[float, float]]`; `class BarcodeUnavailable(RuntimeError)`; `class BarcodeError(RuntimeError)`; `ENGINE: str`; `EXPAND: float`; `classify(payload: str) -> str`; `read_symbols(image: Image.Image) -> list[Symbol]`.
- Produces, `app/config.py`: `privacy_engine_module: str | None = None`, `celery_task_always_eager: bool = False`, and a `model_validator` refusing either non-default value unless `environment == "test"`.
- Produces, `tests/e2e/stub_engines.py`: `class OcrEngine` with `run(image) -> list[Line]`, `class BarcodeEngine` with `read(image) -> list[Symbol]` — the deterministic pair the Playwright launcher loads (Task P8) and every pytest suite may load too.
- Later tasks call `read_text` and `read_symbols` and nothing else; `app/tasks/media.py` is their only caller in `app/`.

- [ ] **Step 1: RED — the test-only settings refuse to exist outside `ENVIRONMENT=test`**

Append to `tests/test_config.py`:

```python
@pytest.mark.parametrize(("name", "value"), [("privacy_engine_module", "tests.e2e.stub_engines"),
                                             ("celery_task_always_eager", True)])
def test_a_test_only_setting_is_refused_outside_the_test_environment(name: str, value: object) -> None:
    """The Playwright execution model (spec 2026-09-09 G) needs the pipeline to run eagerly with
    stub engines inside the api process. No DEPLOYED service may ever do that -- a stubbed OCR would
    mean a photograph that was never scanned reaching READY_FOR_REVIEW. Refused at boot, naming the
    variable and never its value, in the `_qa_never_serves_the_coming_soon_page` shape."""
    base = {"database_url": "postgresql://x/y", "redis_url": "redis://localhost:6379/0",
            "api_secret_key": "k", "environment": "qa", name: value}
    with pytest.raises(ValidationError) as caught:
        Settings(**base)
    assert name.upper() in str(caught.value) and str(value) not in str(caught.value)
    Settings(**{**base, "environment": "test"})
```

- [ ] `poetry run pytest tests/test_config.py -q -W error -k test_only_setting` — RED: `TypeError`/`ValidationError` naming an unexpected keyword (the fields do not exist).

- [ ] **Step 2: GREEN — the two settings and the validator**

In `app/config.py`, beside `census_api_key`:

```python
    # Test-only, and refused at boot everywhere else by the validator below (spec 2026-09-09 E).
    # `tests/e2e/api_under_test.py` -- the Playwright launcher -- exports both so the upload's
    # `send_task` runs `process_photo` inline with deterministic stub engines; no deployed service
    # may, because a stubbed OCR would let a photograph reach READY_FOR_REVIEW unscanned.
    privacy_engine_module: str | None = None
    celery_task_always_eager: bool = False
```

and, beside `_qa_never_serves_the_coming_soon_page`:

```python
    @model_validator(mode="after")
    def _test_only_settings_are_test_only(self) -> Settings:
        if self.environment.lower() != "test":
            for name in ("PRIVACY_ENGINE_MODULE", "CELERY_TASK_ALWAYS_EAGER"):
                if getattr(self, name.lower()) not in (None, False):
                    raise ValueError(f"{name} is only valid when ENVIRONMENT=test")
        return self
```

The refusal names the variable and never its value, the rule `tests/test_docs.py::test_claude_md_lists_variable_names_only` and `app/config.py`'s own precedent both hold.

- [ ] `.env.example`, two lines beside the Census pair:

```
# PRIVACY_ENGINE_MODULE=                                                 # test only — the Playwright api under test loads stub OCR/barcode engines from this module; refused at boot in every other environment
# CELERY_TASK_ALWAYS_EAGER=                                              # test only — runs media.process_photo inline in the api process for the Playwright suite; refused at boot in every other environment
```

- [ ] `DEPLOY.md`'s variables table, two rows with blank api/worker columns and the same sentence, so `test_every_setting_is_documented_in_env_example_and_deploy_md` holds.
- [ ] `poetry run pytest tests/test_config.py tests/test_docs.py -q -W error` — GREEN.

- [ ] **Step 3: RED — the OCR adapter's contract**

Create `tests/privacy/test_ocr.py`:

```python
"""The OCR adapter (spec 2026-09-09 C.5 step 2). Directive 4: "Run OCR against EVERY image." An
engine error is therefore a FAILURE, never a skip -- that distinction is what this suite pins.

No model is downloaded and no network is touched: every case loads the stub engine through
`PRIVACY_ENGINE_MODULE`, which is the same seam the Playwright launcher uses."""
from __future__ import annotations

from typing import Any

import pytest
from PIL import Image

from app.privacy import ocr


@pytest.fixture(autouse=True)
def _stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.privacy.ocr.settings.privacy_engine_module", "tests.e2e.stub_engines")
    monkeypatch.setattr("app.privacy.ocr._LOADED", None)


def _image(w: int = 800, h: int = 600) -> Image.Image:
    return Image.new("RGB", (w, h), (255, 255, 255))


def test_every_line_carries_its_text_confidence_and_quad_in_display_pixels() -> None:
    lines = ocr.read_text(_image())
    assert lines and all(len(line.quad) == 4 for line in lines)
    assert all(0.0 <= line.confidence <= 1.0 for line in lines)
    assert {line.text for line in lines} == {"HILL COUNTRY ANIMAL HOSPITAL", "(512) 555-0100"}
    assert all(0 <= x <= 800 and 0 <= y <= 600 for line in lines for x, y in line.quad)


def test_a_short_line_is_re_read_on_a_doubled_image_and_its_quad_is_halved_back() -> None:
    """Directories and business cards: a line under 24 px is the case the second pass exists for.

    The stub's FIRST pass returns one line whose quad is 12 px tall at 800x600, which is what makes
    `read_text` upscale; the telephone number exists only on the doubled image, so a missing second
    pass is a missing line rather than a subtle coordinate error. Its quad comes back halved into
    display space -- y in [180, 198] of a 600 px image, not the [360, 396] the doubled pass saw."""
    lines = ocr.read_text(_image())
    tiny = [line for line in lines if line.text == "(512) 555-0100"]
    assert tiny, "the second pass did not run: the first pass's only line was not short"
    assert max(y for _, y in tiny[0].quad) == pytest.approx(198.0)
    assert max(x for x, _ in tiny[0].quad) == pytest.approx(280.0)


def test_a_first_pass_of_tall_lines_alone_runs_no_second_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other side of the trigger, so the branch is a decision and not an accident: an engine
    whose only line is 90 px tall is read once, at display size, and never upscaled."""
    class Tall:
        """Records the size of every image it is handed, so "no second pass" is an observation."""

        def __init__(self) -> None:
            self.seen: list[tuple[int, int]] = []

        def run(self, image: Image.Image) -> list[ocr.Line]:
            self.seen.append(image.size)
            return [ocr.Line("TALL", 0.9, [(0.0, 0.0), (100.0, 0.0), (100.0, 90.0), (0.0, 90.0)])]

    engine = Tall()
    monkeypatch.setattr("app.privacy.ocr._LOADED", engine)
    assert [line.text for line in ocr.read_text(_image())] == ["TALL"]
    assert engine.seen == [(800, 600)]


def test_the_engine_is_built_once_per_process() -> None:
    first = ocr._engine()
    assert ocr._engine() is first


def test_an_engine_that_will_not_import_is_unavailable_and_one_that_raises_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two different reason codes, because they mean different things to an operator: the wheel is
    missing from the image, versus this photograph broke the engine."""
    monkeypatch.setattr("app.privacy.ocr.settings.privacy_engine_module", "tests.e2e.no_such_engine")
    monkeypatch.setattr("app.privacy.ocr._LOADED", None)
    with pytest.raises(ocr.OcrUnavailable):
        ocr.read_text(_image())

    class Broken:
        def run(self, image: Image.Image) -> list[ocr.Line]:
            raise RuntimeError("onnxruntime said no")

    monkeypatch.setattr("app.privacy.ocr._LOADED", Broken())
    with pytest.raises(ocr.OcrError):
        ocr.read_text(_image())


def test_the_engine_name_is_recorded_for_the_privacy_row() -> None:
    assert ocr.ENGINE.startswith("rapidocr-onnxruntime/")
```

- [ ] `poetry run pytest tests/privacy/test_ocr.py -q -W error` — RED: `ModuleNotFoundError: No module named 'app.privacy.ocr'`.

- [ ] **Step 4: GREEN — `app/privacy/ocr.py` and the stub engines**

```python
"""The OCR adapter -- the ONLY module in `app/` that imports an OCR engine (spec 2026-09-09 C.5).

`rapidocr-onnxruntime` bundles its PP-OCR models in the wheel, so nothing is downloaded at run time
and a network-blocked test proves it. The engine object is built once per prefork child (a
module-level lazy singleton) with `intra_op_num_threads = 1`, because the worker runs two children
and each would otherwise start a thread pool the size of the machine.

Directive 4 says "Run OCR against EVERY image", so this module has no "skip" outcome: an engine that
will not import raises `OcrUnavailable` and one that fails on a photograph raises `OcrError`, and
`app/tasks/media.py` turns both into PROCESSING_FAILED with the matching reason code."""
from __future__ import annotations

import importlib
from typing import Any, NamedTuple, Protocol

from PIL import Image

from app.config import settings

#: Recorded in the privacy row's `ocr.engine`, so a record says which engine produced it.
ENGINE = "rapidocr-onnxruntime/1.4.4"
#: A line shorter than this is re-read on a 2x upscale -- directories, business cards, door vinyl.
UPSCALE_BELOW_PX = 24


class Line(NamedTuple):
    """One recognised line, in DISPLAY-pixel space. The quad is the engine's rotated box, kept as
    four points rather than a bounding rectangle so a sign photographed at an angle is covered by
    the polygon it actually occupies."""

    text: str
    confidence: float
    quad: list[tuple[float, float]]


class OcrUnavailable(RuntimeError):
    """The engine is not installed or will not import. Reason code OCR_UNAVAILABLE."""


class OcrError(RuntimeError):
    """The engine raised on this photograph. Reason code OCR_ERROR."""


class Engine(Protocol):
    def run(self, image: Image.Image) -> list[Line]: ...


_LOADED: Engine | None = None


def _engine() -> Engine:
    global _LOADED
    if _LOADED is None:
        _LOADED = _load()
    return _LOADED


def _load() -> Engine:
    module = settings.privacy_engine_module
    if module is not None:
        try:
            return cast("Engine", importlib.import_module(module).OcrEngine())
        except (ImportError, AttributeError) as exc:
            raise OcrUnavailable("OCR_UNAVAILABLE") from exc
    try:
        from rapidocr_onnxruntime import RapidOCR  # noqa: PLC0415  (deliberately lazy -- see the docstring)
    except ImportError as exc:
        raise OcrUnavailable("OCR_UNAVAILABLE") from exc
    return _Rapid(RapidOCR(intra_op_num_threads=1))


class _Rapid:
    """`RapidOCR()(img)` answers `[[quad], text, score]` per line, or `None` for a blank image."""

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    def run(self, image: Image.Image) -> list[Line]:
        result, _elapsed = self._engine(image)
        return [Line(text, float(score), [(float(x), float(y)) for x, y in quad])
                for quad, text, score in (result or [])]


def _height(quad: list[tuple[float, float]]) -> float:
    return max(y for _, y in quad) - min(y for _, y in quad)


def read_text(image: Image.Image) -> list[Line]:
    """Every line the engine finds, plus a second pass on a 2x upscale whenever the first pass saw
    a short line or nothing at all. The second pass's coordinates are halved back into display
    space, and a line whose quad already overlaps one from the first pass is dropped."""
    engine = _engine()
    try:
        lines = list(engine.run(image))
        if not lines or any(_height(line.quad) < UPSCALE_BELOW_PX for line in lines):
            doubled = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
            found = engine.run(doubled)
        else:
            found = []
    except Exception as exc:  # the engine's own failures are not a documented, catchable set
        raise OcrError("OCR_ERROR") from exc
    for line in found:
        halved = Line(line.text, line.confidence, [(x / 2, y / 2) for x, y in line.quad])
        if not any(seen.text == halved.text for seen in lines):
            lines.append(halved)
    return lines
```

`from typing import cast` joins the imports. The one broad `except Exception` is deliberate and explained in place: an ONNX runtime failure is not a documented exception set, and letting it escape would take the worker's child down instead of writing `PROCESSING_FAILED`.

Create `tests/e2e/stub_engines.py`:

```python
"""Deterministic stand-ins for the OCR and 2D-symbol engines, loaded through
`PRIVACY_ENGINE_MODULE` (spec 2026-09-09 G).

Two fixed lines: a practice name that the identity matcher matches against the seeded listing, and
a NANP telephone number that the regex class flags whether or not it matches. Only the name is
returned on the FIRST pass, and its quad is deliberately shorter than `ocr.UPSCALE_BELOW_PX` -- which
is what makes `read_text` run its second pass at all, and therefore what makes the phone line
reachable. Get that the wrong way round and the second pass never fires: a first pass whose only
line is 60 px tall satisfies `_height(line.quad) >= UPSCALE_BELOW_PX`, `found` stays empty, and the
telephone number is never returned by anything. No barcode, so a scenario that needs one plants its
own engine.

This module lives under `tests/` and is imported by NAME: nothing test-shaped is importable from
`app/`, and `Settings` refuses the variable outside `ENVIRONMENT=test`."""
from __future__ import annotations

from PIL import Image

from app.privacy.barcodes import Symbol
from app.privacy.ocr import Line

NAME_LINE = "HILL COUNTRY ANIMAL HOSPITAL"
PHONE_LINE = "(512) 555-0100"

#: How the stub tells `read_text`'s first pass from its 2x second pass: by height alone, with the
#: threshold above every display size the suites use (800x600 in `test_ocr.py`, 1200x900 in
#: `test_media.py`) and below every doubling of them (1200, 1800).
UPSCALED_ABOVE_PX = 1000
#: The name line's quad is 2 % of the image's height -- 12 px at 600, 18 px at 900, both under
#: `ocr.UPSCALE_BELOW_PX` (24), so the first pass always triggers the second.
NAME_BAND = 0.02


class OcrEngine:
    def run(self, image: Image.Image) -> list[Line]:
        # Positions are fractions of the image, so the same stub serves any size the suites use.
        w, h = image.width, image.height
        name = [(w * 0.10, h * 0.10), (w * 0.70, h * 0.10),
                (w * 0.70, h * (0.10 + NAME_BAND)), (w * 0.10, h * (0.10 + NAME_BAND))]
        if h < UPSCALED_ABOVE_PX:         # the first pass: one short line, and no telephone number
            return [Line(NAME_LINE, 0.98, name)]
        phone = [(w * 0.10, h * 0.30), (w * 0.35, h * 0.30), (w * 0.35, h * 0.33), (w * 0.10, h * 0.33)]
        return [Line(NAME_LINE, 0.98, name), Line(PHONE_LINE, 0.91, phone)]


class BarcodeEngine:
    def read(self, image: Image.Image) -> list[Symbol]:
        return []
```

- [ ] `poetry run pytest tests/privacy/test_ocr.py -q -W error` — GREEN.

- [ ] **Step 5: RED then GREEN — the 2D-symbol adapter**

`tests/privacy/test_barcodes.py`:

```python
"""zxing-cpp behind an adapter (spec C.5 step 2b, D-IDP-7). EVERY 2D symbol is a redaction region
under NOT_SHOW regardless of payload: a QR cannot be reviewed by eye, and the worker never fetches
one -- no egress, no SSRF. The payload is classified offline and the STRING is never stored."""
from __future__ import annotations

import pytest
from PIL import Image

from app.privacy import barcodes


@pytest.mark.parametrize(("payload", "kind"), [
    ("https://hillcountryvet.example/appointments", "url"),
    ("hillcountryvet.example", "url"),
    ("tel:+15125550100", "phone"),
    ("(512) 555-0100", "phone"),
    ("BEGIN:VCARD\nFN:Hill Country\nEND:VCARD", "vcard"),
    ("staff room", "text"),
])
def test_a_payload_is_classified_and_never_returned(payload: str, kind: str) -> None:
    assert barcodes.classify(payload) == kind


def test_an_undecodable_finder_pattern_is_still_a_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    """`return_errors=True`: a QR the engine can see but not decode is exactly the case a seller
    would most want covered, and it has no payload to classify."""
    class Partial:
        def read(self, image: Image.Image) -> list[barcodes.Symbol]:
            return [barcodes.Symbol("QRCode", "undecodable", [(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0)])]

    monkeypatch.setattr("app.privacy.barcodes._LOADED", Partial())
    found = barcodes.read_symbols(Image.new("RGB", (200, 200)))
    assert [s.payload_kind for s in found] == ["undecodable"]


def test_an_engine_that_will_not_import_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.privacy.barcodes.settings.privacy_engine_module", "tests.e2e.no_such_engine")
    monkeypatch.setattr("app.privacy.barcodes._LOADED", None)
    with pytest.raises(barcodes.BarcodeUnavailable):
        barcodes.read_symbols(Image.new("RGB", (200, 200)))
```

`app/privacy/barcodes.py` — the same shape as `ocr.py`, with the classifier:

```python
"""The 2D-symbol adapter -- the ONLY module in `app/` that imports a barcode engine.

D-IDP-7 (queued for John): every 2D symbol is redacted under NOT_SHOW regardless of payload. The
directive says "QR codes where they resolve to identifying information", and this goes further
toward hiding: a QR cannot be reviewed by eye, and resolving one would mean the worker fetching a
URL a stranger put in a photograph. The payload is classified OFFLINE for the record and the string
itself is never stored; the seller can Remove a mask that was unnecessary."""
from __future__ import annotations

import importlib
import re
from typing import Any, NamedTuple, Protocol, cast

from PIL import Image

from app.config import settings

ENGINE = "zxing-cpp/3.1.1"
#: Each symbol's four corners, expanded about their centroid by this factor before the fill.
EXPAND = 1.15

_URL = re.compile(r"^(https?://|www\.)|^[\w-]+(\.[\w-]+)+(/|$)", re.I)
_PHONE = re.compile(r"^(tel:)?[\d\s()+.-]{7,}$")


class Symbol(NamedTuple):
    fmt: str
    payload_kind: str
    quad: list[tuple[float, float]]


class BarcodeUnavailable(RuntimeError):
    """Reason code BARCODE_UNAVAILABLE."""


class BarcodeError(RuntimeError):
    """Reason code BARCODE_ERROR."""


class Engine(Protocol):
    def read(self, image: Image.Image) -> list[Symbol]: ...


_LOADED: Engine | None = None


def classify(payload: str) -> str:
    """`url` | `phone` | `vcard` | `text`. Offline, and the ONLY thing kept about a payload."""
    if payload.startswith("BEGIN:VCARD"):
        return "vcard"
    if _URL.search(payload):
        return "url"
    if _PHONE.match(payload):
        return "phone"
    return "text"


def _engine() -> Engine:
    global _LOADED
    if _LOADED is None:
        module = settings.privacy_engine_module
        try:
            _LOADED = (cast("Engine", importlib.import_module(module).BarcodeEngine())
                       if module is not None else _Zxing())
        except (ImportError, AttributeError) as exc:
            raise BarcodeUnavailable("BARCODE_UNAVAILABLE") from exc
    return _LOADED


class _Zxing:
    def __init__(self) -> None:
        import zxingcpp  # noqa: PLC0415  (deliberately lazy -- the api must not import an engine)

        self._read = zxingcpp.read_barcodes

    def read(self, image: Image.Image) -> list[Symbol]:
        found: list[Symbol] = []
        for result in self._read(image, try_rotate=True, try_downscale=True, return_errors=True):
            corners: Any = result.position
            quad = [(float(p.x), float(p.y)) for p in (corners.top_left, corners.top_right,
                                                       corners.bottom_right, corners.bottom_left)]
            kind = classify(result.text) if result.valid else "undecodable"
            found.append(Symbol(str(result.format), kind, quad))
        return found


def read_symbols(image: Image.Image) -> list[Symbol]:
    engine = _engine()
    try:
        return list(engine.read(image))
    except Exception as exc:  # the engine's failures are not a documented, catchable set
        raise BarcodeError("BARCODE_ERROR") from exc
```

- [ ] `poetry run pytest tests/privacy/test_barcodes.py -q -W error` — GREEN.

- [ ] **Step 6: the dependencies, measured**

- [ ] Record the base image size first, so the delta is this change's and nothing else's (the `f454fe7` precedent):

```bash
docker build -t pm-before . && docker images --format '{{.Repository}} {{.Size}}' pm-before
```

- [ ] Add to `pyproject.toml`'s `[project].dependencies`, in the main group, each with its reason and its licence in the comment:

```toml
  # The image-identifiability pipeline's OCR (spec 2026-09-09 C.5 step 2, D-IDP-1a). Apache-2.0.
  # The PP-OCR models are bundled in the wheel, so the worker downloads nothing at run time and a
  # network-blocked test proves it. Requires the full `opencv-python`, hence the two apt packages
  # the Dockerfile now installs. WORKER ONLY in practice -- `app/privacy/ocr.py` imports it lazily
  # and the api never calls `read_text` -- but it is a main dependency because one image serves
  # both roles.
  "rapidocr-onnxruntime (>=1.4.4,<2.0.0)",
  "onnxruntime (>=1.29,<2.0.0)",              # MIT -- the runtime rapidocr drives
  # 2D symbols (spec C.5 step 2b, D-IDP-7). Apache-2.0, a pure wheel of about 1 MB.
  "zxing-cpp (>=3.1.1,<4.0.0)",
```

- [ ] `poetry lock` then `poetry install`. **Quote the resolved versions of all three, and of every transitive package the lock adds, in the commit body** — a lock diff is the only honest record of what entered the image.
- [ ] `Dockerfile:43-44` — the apt line gains the two OpenCV needs:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] `docker build -t pm-after . && docker images --format '{{.Repository}} {{.Size}}' pm-after` — **record both figures.** The spec's estimate is +120–150 MB on a 634 MB image; the measurement is what goes in `DEPLOY.md` and the commit body, whatever it says. A delta far outside that range is `NEEDS_CONTEXT`, not a fait accompli.
- [ ] `DEPLOY.md` — a line under the Migrations section's neighbours recording the measured image size before and after, the three packages, their licences, and the two apt packages, in the voice of the existing sizing notes.
- [ ] Prove the offline claim:

```bash
poetry run python - <<'PY'
import socket
socket.socket = None            # any attempt to open one is an AttributeError, not a hang
from PIL import Image
from app.privacy import ocr
print(len(ocr.read_text(Image.new("RGB", (1200, 900), (255, 255, 255)))), "lines, no socket")
PY
```

with `PRIVACY_ENGINE_MODULE` **unset** and `ENVIRONMENT=test`, so the real engine loads. Record the output in the commit body.

- [ ] **Step 7: the task's gates**

```bash
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
```

`tests/e2e/stub_engines.py` is measured by `--cov=tests/e2e` where the launcher's suite runs it (Task P8); here it is covered by `test_ocr.py` and `test_barcodes.py` loading it through the setting.

- [ ] **Step 8: commit**

```
feat(privacy): the OCR and 2D-symbol adapters, and the engines behind them

Directive 4 step 2: "Run OCR against EVERY image." app/privacy/ocr.py and
app/privacy/barcodes.py are the only modules in app/ that import an
engine; both build theirs once per prefork child, both distinguish "not
installed" from "failed on this photograph" with two reason codes, and
neither has a skip outcome. The OCR adapter re-reads a doubled image
whenever the first pass saw a short line, and halves the second pass's
coordinates back into display space.

Every 2D symbol is a region under NOT_SHOW regardless of payload (D-IDP-7,
queued for John): a QR cannot be reviewed by eye and resolving one would
mean the worker fetching a stranger's URL. The payload is classified
offline and the string is never stored.

rapidocr-onnxruntime <v> + onnxruntime <v> (Apache-2.0, MIT; models
bundled in the wheel, proved offline with sockets disabled) and zxing-cpp
<v> (Apache-2.0). Image size <before> -> <after>, measured with docker
images before and after this change alone; the two apt packages OpenCV
needs are named on the Dockerfile's existing line.

PRIVACY_ENGINE_MODULE and CELERY_TASK_ALWAYS_EAGER are test-only and
refused at boot in every other environment, naming the variable and never
its value.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `git add app/privacy/ocr.py app/privacy/barcodes.py app/config.py tests/privacy/test_ocr.py tests/privacy/test_barcodes.py tests/e2e/stub_engines.py tests/test_config.py pyproject.toml poetry.lock Dockerfile .env.example DEPLOY.md`

---

### Task P5: identity matching — normalisation, six methods, the regex classes

**Files:**
- Create: `app/privacy/identity.py`, `tests/privacy/test_identity.py`
- Unchanged: no new dependency — `difflib` is stdlib (controller ruling 5)

**Interfaces:**
- Consumes: `app/privacy/ocr.py::Line`.
- Produces, `app/privacy/identity.py`:
  - `GENERIC: frozenset[str]` — the words an abbreviation and a distinctive token both ignore.
  - `SUBSTITUTIONS: tuple[tuple[str, str], ...]` — the OCR confusions applied to BOTH sides.
  - `REGEX_CLASSES: dict[str, re.Pattern[str]]` — `phone`, `url`, `email`, `address`, `premises_number`, `handle`, `zip`.
  - `class Match(NamedTuple)` with `field: str`, `line: int`, `method: str`, `score: float`.
  - `normalise(text: str) -> str`
  - `identity_terms(listing: Mapping[str, Any], email: str | None) -> dict[str, list[str]]`
  - `match_lines(lines: Sequence[str], terms: Mapping[str, list[str]]) -> list[Match]`
  - `regex_hits(lines: Sequence[str]) -> list[Match]` — per line AND over the joined text (spec §C.5 step 2), a joined hit attributed to every line its span touches
  - `_informative(fragment: str) -> bool` — the substring rule: two tokens or more, at least one outside the generic set
  - `matches(lines: Sequence[str], listing: Mapping[str, Any], email: str | None) -> list[Match]` — the one call `app/tasks/media.py` makes.
- `Match.line` is an index into `ocr.lines`, exactly as the privacy row's `identity_matches` records it; `Match.method` is one of `exact`, `substring`, `token_set`, `fuzzy`, `distinctive`, `abbreviation`, `regex`.

- [ ] **Step 1: RED — the table-driven suite, OCR errors included**

Create `tests/privacy/test_identity.py`:

```python
"""Identity matching (spec 2026-09-09 C.5 step 3; directive 4 step 3).

The directive asks for exact, case-insensitive, punctuation- and whitespace-normalised, OCR-error-
tolerant, partial and abbreviation matching. Every row of the table below is one of those, and the
OCR-error rows are real substitutions a scene-text engine makes on signage: a serif I read as a 1, a
zero read as an O, an `rn` pair read as an `m`."""
from __future__ import annotations

from typing import Any

import pytest

from app.privacy import identity

LISTING: dict[str, Any] = {
    "name": "Hill Country Animal Hospital",
    "street": "1204 Cypress Creek Rd",
    "city": "Cedar Park",
    "state": "TX",
    "zip": "78613",
    "phone": "(512) 555-0100",
    "slug": "hill-country-animal-hospital",
    "facility": "Two-storey brick building on Cypress Creek",
    "services": "Dentistry, surgery, boarding",
    "hours": "Mon-Fri 8-6",
}
EMAIL = "practice.manager@hillcountryvet.example"

# (the OCR line, the field it must match, the method it must match by)
#
# The METHOD column is derived, not chosen: `_compare` returns the FIRST method that fires, in the
# order exact -> substring -> token_set -> fuzzy, so each row records which of them actually
# explains that line under the normalisation below. Three rows are worth reading twice.
# "HILL COUNTRY ANIMAL HOSP" is a prefix of the normalised name, so `substring` fires before
# `token_set` ever runs; "ANIIVIAL" scores a token-set overlap of exactly 3/5 = 0.6, which is
# `>= TOKEN_SET`, so it is a token_set and not a fuzzy; and `fuzzy` is only ever reached by a line
# of two or more tokens whose overlap is BELOW 0.6, which is what "Cedar Parh" is for.
HITS = (
    ("Hill Country Animal Hospital", "name", "exact"),
    ("HILL COUNTRY ANIMAL HOSPITAL", "name", "exact"),                 # case
    ("Hill Country Animal Hospital.", "name", "exact"),                # punctuation
    ("Hill  Country   Animal Hospital", "name", "exact"),              # whitespace
    ("Welcome to Hill Country Animal Hospital", "name", "substring"),  # partial
    ("HILL C0UNTRY ANIMAL H0SPITAL", "name", "exact"),                 # OCR: 0 for O
    ("HlLL COUNTRY ANIMAL HOSPITAL", "name", "exact"),                 # OCR: l for I
    ("HILL COUNTRY ANIIVIAL HOSPITAL", "name", "token_set"),           # OCR: IVI for M -- 3/5 = 0.60
    ("HILL COUNTRY ANIMAL HOSP", "name", "substring"),                 # truncated by the sign's frame
    ("Cedar Parh", "city", "fuzzy"),                                   # OCR: h for k -- overlap 0.33, ratio 0.90
    ("Hill Country", "name", "distinctive"),                           # the sign's top line alone
    ("HCAH", "name", "abbreviation"),
    ("1204 Cypress Creek Rd", "street", "exact"),
    ("Cedar Park", "city", "exact"),
    ("78613", "zip", "exact"),
    ("(512) 555-0100", "phone", "exact"),
    ("512.555.0100", "phone", "exact"),                                # punctuation again
    ("hillcountryvet.example", "email_domain", "exact"),
    ("hill-country-animal-hospital", "slug", "exact"),
)

# Lines that must NOT match anything: the generic words a veterinary sign carries everywhere, and a
# number that is not this practice's. A matcher that fires on "Animal Hospital" would black out
# every photograph of every listing and teach sellers to remove masks. Both rules `_informative`
# enforces have a row here, because both were found by a review reading the matcher against this
# very table: "Animal Hospital" is two tokens that are BOTH generic, and "Cedar" is a single token
# of a two-token city.
MISSES = (
    "Animal Hospital",
    "VETERINARY CLINIC",
    "Open 7 days",
    "Cedar",                       # one token of "Cedar Park": a substring, and not an identity
    "(512) 555-9999",
)


@pytest.mark.parametrize(("line", "field", "method"), HITS)
def test_every_contracted_match_is_found_by_its_contracted_method(line: str, field: str, method: str) -> None:
    found = identity.matches([line], LISTING, EMAIL)
    assert [(m.field, m.method) for m in found if m.field == field] != [], found
    assert any(m.field == field and m.method == method for m in found), found
    assert all(0.0 <= m.score <= 1.0 and m.line == 0 for m in found)


@pytest.mark.parametrize("line", MISSES)
def test_a_generic_or_foreign_line_matches_no_identity_field(line: str) -> None:
    assert [m for m in identity.matches([line], LISTING, EMAIL) if m.method != "regex"] == []


@pytest.mark.parametrize(("line", "cls"), [
    ("Call (512) 555-0100 today", "phone"),
    ("visit hillcountryvet.example", "url"),
    ("https://vetbook.example/hc", "url"),
    ("hello@somewhere.example", "email"),
    ("1204 Cypress Creek Rd", "address"),
    ("Suite 210", "address"),
    ("4140", "premises_number"),
    ("22113", "premises_number"),
    ("2101", "premises_number"),
    ("@hillcountryvet", "handle"),
    ("78613", "zip"),
])
def test_a_regex_class_is_an_identifying_region_whether_or_not_it_matches_the_listing(
    line: str, cls: str
) -> None:
    """Spec C.5 step 2: "each hit is an identifying region regardless of matching". A phone number
    that is not this practice's is still a phone number in a photograph of it. The three
    `premises_number` rows are the strings the Dallas seed photographs actually hold (A-IDP-7),
    Juliet's divergent `22113` included -- a number worn as signage belongs to no column of this
    listing or any other, which is exactly why the identity matcher can never reach it."""
    other: dict[str, Any] = {"name": "Somewhere Else Veterinary", "city": "Dallas", "zip": "75001"}
    assert any(m.field == f"regex:{cls}" and m.method == "regex"
               for m in identity.matches([line], other, None))


@pytest.mark.parametrize("line", ["EST. 2017", "EXAM ROOM 1", "24/7", "Open 7 days", "1"])
def test_a_line_that_is_not_only_a_number_is_not_a_premises_number(line: str) -> None:
    """`premises_number` is deliberately WHOLE-LINE and two to six digits (A-IDP-7), so an interior
    is not blanketed: an established-in year, a room number and an opening-hours pill all carry
    other tokens, and a single digit is too short. Where a number DOES share a line with the
    practice's own name, the identity match already makes that whole line one region."""
    assert [m for m in identity.matches([line], LISTING, EMAIL)
            if m.field == "regex:premises_number"] == []


def test_a_number_split_across_two_lines_is_still_a_hit_on_both_of_them() -> None:
    """Spec C.5 step 2 runs the regex classes "over every line and over the joined text". Scene text
    wraps: an area code on one line of a sign and the rest on the next is a telephone number no
    per-line pass can see, and the aggregator needs BOTH lines so the fill covers both halves rather
    than one rectangle spanning the gap between them."""
    found = identity.matches(["(512)", "555-0100"], LISTING, EMAIL)
    assert sorted(m.line for m in found if m.field == "regex:phone") == [0, 1]
    # and no line matched it on its own -- neither half is ten digits
    for half in ("(512)", "555-0100"):
        assert [m for m in identity.matches([half], LISTING, EMAIL) if m.field == "regex:phone"] == []


def test_a_joined_hit_is_recorded_once_per_line_and_not_twice() -> None:
    """The per-line pass and the joined pass see the same match on a single-line input; the record
    carries one entry, because `identity_matches` indexes into `ocr.lines` and a duplicate would
    make the same region twice."""
    found = [m for m in identity.matches(["Call (512) 555-0100 today"], LISTING, EMAIL)
             if m.field == "regex:phone"]
    assert len(found) == 1


def test_only_the_email_domain_is_ever_read() -> None:
    """Data minimisation (spec C.5 step 3): the part before the @ is a person's name as often as
    not, and no photograph of a building contains it.

    The domain is stored NORMALISED, like every other term -- `hillcountryvet.example` folds to
    `hlllcountryvet example` under the substitution map -- so the assertion is against that
    spelling. Asserting the raw address would fail against a correct matcher, which is the sort of
    row that gets a working rule "fixed"."""
    terms = identity.identity_terms(LISTING, EMAIL)
    assert terms["email_domain"] == [identity.normalise("hillcountryvet.example")]
    assert "manager" not in str(terms) and identity.normalise("practice") not in str(terms)


def test_the_seller_prose_fields_contribute_tokens_and_never_whole_string_matches() -> None:
    """`facility`, `services` and `hours` are free text: matching a whole sentence would fire on
    nothing, and matching every word in them would fire on everything. Distinctive tokens only."""
    terms = identity.identity_terms(LISTING, EMAIL)
    assert "Two-storey brick building on Cypress Creek" not in terms["name"]
    assert any("cypress" in t for t in terms["tokens"])
    assert not any(t in ("mon", "fri", "8", "6") for t in terms["tokens"])


def test_matching_is_deterministic_and_ordered_by_line_then_field() -> None:
    lines = ["HILL COUNTRY ANIMAL HOSPITAL", "(512) 555-0100"]
    once = identity.matches(lines, LISTING, EMAIL)
    assert once == identity.matches(lines, LISTING, EMAIL)
    assert [m.line for m in once] == sorted(m.line for m in once)


def test_a_listing_with_no_identity_yet_matches_nothing_and_does_not_raise() -> None:
    """A draft before step 1: every field null. The pipeline still runs -- the regex classes are
    what protect that photograph -- and the matcher must not divide by zero on an empty term set."""
    empty: dict[str, Any] = dict.fromkeys(LISTING)
    assert [m for m in identity.matches(["HILL COUNTRY ANIMAL HOSPITAL"], empty, None)
            if m.method != "regex"] == []
```

- [ ] `poetry run pytest tests/privacy/test_identity.py -q -W error` — RED: `ModuleNotFoundError: No module named 'app.privacy.identity'`.

- [ ] **Step 2: GREEN — `app/privacy/identity.py`**

```python
"""Matching a photograph's recognised text against this listing's own identity (spec C.5 step 3).

Stdlib only -- `difflib.SequenceMatcher` is the fuzzy method, so no dependency is added for it
(controller ruling 5). Nothing here is stored: the terms are read from the `listing` row at run
time, so a seller who corrects their practice name gets a re-run that matches the new one, and the
privacy row keeps only WHICH field matched WHICH line, by index, with a score.

Two directions have to be right at once. A matcher that fires on "Animal Hospital" blacks out every
photograph of every listing and teaches sellers to remove masks; one that only fires on the exact
registered name misses the sign, which is the whole point. Two rules hold the balance, and both are
about the same thing -- a fragment has to be SPECIFIC before it counts. The distinctive-token rule:
a name token of five characters or more, outside the generic set, is enough on its own. And
`_informative`, which every substring match must pass: at least two tokens, at least one of them
outside the generic set.

**The generic set is compared AFTER normalisation, and that is load-bearing.** `normalise` folds the
scene-text confusions on both sides, so "animal" becomes "anlmal" and "hospital" becomes "hospltal";
a generic set of un-normalised words would therefore match none of the tokens it is meant to filter,
`_informative` and the distinctive pool would both let them through, and the matcher would black out
a region on every photograph carrying the words "animal hospital". `normalise` is defined first for
that reason and `_GENERIC_N` is folded at import."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
from typing import Any, NamedTuple

#: Applied to BOTH sides before comparison, so "H0SPITAL" and "HOSPITAL" become the same string
#: rather than a near-miss the fuzzy ratio has to rescue. Ordered longest-first so `rn` -> `m` runs
#: before the single-character pairs.
SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("rn", "m"), ("vv", "w"), ("0", "o"), ("1", "l"), ("i", "l"), ("5", "s"), ("8", "b"), ("2", "z"),
)


def normalise(text: str) -> str:
    """Casefold, punctuation to spaces, whitespace collapsed, OCR confusions folded."""
    folded = re.sub(r"[^\w\s]", " ", text.casefold())
    collapsed = " ".join(folded.split())
    for wrong, right in SUBSTITUTIONS:
        collapsed = collapsed.replace(wrong, right)
    return collapsed


#: Words that identify no practice, as written. Used nowhere directly -- every comparison is against
#: `_GENERIC_N` below -- but kept in this spelling because it is the human-readable list, and a
#: reader adding a word to it should not have to know what the substitution map will do to it.
GENERIC = frozenset({"animal", "hospital", "veterinary", "vet", "clinic", "pet", "care", "center",
                     "centre", "of", "the", "and", "for", "dvm"})

#: The same words in the space every comparison actually happens in: "animal" -> "anlmal",
#: "hospital" -> "hospltal", "veterinary" -> "veterlnary", "clinic" -> "cllnlc". Folded once, at
#: import, because a set folded per call would be the same work in a loop.
_GENERIC_N = frozenset(normalise(word) for word in GENERIC)

#: Each hit is an identifying region REGARDLESS of matching (spec C.5 step 2).
REGEX_CLASSES: dict[str, re.Pattern[str]] = {
    "phone": re.compile(r"(?<!\d)(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"),
    "url": re.compile(r"\b(https?://\S+|www\.\S+|[\w-]+\.(com|net|org|vet|clinic|care|health|example)\b)", re.I),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    #: Two arms, and the second is not decoration: a suite number can stand with no street number
    #: in front of it. The specification's inline pattern (C.5 step 2) stated only the first and so
    #: would have missed "Suite 210"; A-IDP-7 corrects it there and folds both arms in here, so
    #: this module defines each class exactly once.
    "address": re.compile(
        r"(\b\d+\s+[\w'-]+(\s+[\w'-]+)*\s+(st|street|ave|avenue|rd|road|blvd|dr|drive|ln|lane|pkwy|parkway|hwy|highway)\b\.?"
        r"|\b(suite|ste)\s*\.?\s*\w+\b)", re.I),
    #: A number worn as signage, alone on its own line: "4140" above a door. John's ruling of
    #: 2026-09-10 (A-IDP-7) -- an invented street number is part of the invented identity, so it
    #: is redacted under NOT_SHOW like the name. WHOLE LINE, two to six digits: "EST. 2017",
    #: "EXAM ROOM 1" and "24/7" carry other tokens and are not premises numbers, so an interior
    #: is not blanketed; where a number shares a line with the practice's own name the identity
    #: match already makes the whole line one region (spec C.5 step 5).
    "premises_number": re.compile(r"\A\s*\d{2,6}\s*\Z"),
    "handle": re.compile(r"(?<!\w)@\w{3,}"),
    "zip": re.compile(r"(?<!\d)\d{5}(?!\d)"),
}

#: Below this a substring is a coincidence ("Rd" inside "Broadway").
MIN_SUBSTRING = 4
#: `difflib` ratio at or above this is a match.
FUZZY = 0.85
#: Token-set overlap at or above this is a match, for lines of two tokens or more.
TOKEN_SET = 0.6
#: A name token this long, outside GENERIC, identifies on its own.
DISTINCTIVE = 5


class Match(NamedTuple):
    field: str
    line: int
    method: str
    score: float


def _informative(fragment: str) -> bool:
    """Whether a normalised fragment is specific enough to be a substring match on its own.

    Two conditions, and a review found the matcher wrong on both. At least TWO tokens, or "Cedar"
    -- one token of the two-token city "Cedar Park" -- is a substring match on every photograph of
    every practice in Cedar Park. And at least one token outside the generic veterinary vocabulary,
    or "Animal Hospital" is a substring of "Hill Country Animal Hospital" and every photograph of
    every listing goes dark. `MISSES` in `tests/privacy/test_identity.py` has a row for each."""
    tokens = fragment.split()
    return len(tokens) >= 2 and any(token not in _GENERIC_N for token in tokens)


def _abbreviations(name: str) -> list[str]:
    words = [w for w in normalise(name).split() if w]
    if not words:
        return []
    full = "".join(w[0] for w in words)
    distinctive = "".join(w[0] for w in words if w not in _GENERIC_N)
    return [a for a in {full, distinctive} if len(a) >= 2]


def identity_terms(listing: Mapping[str, Any], email: str | None) -> dict[str, list[str]]:
    """The listing's own identity, normalised, by field.

    `tokens` is the distinctive-token pool: the name's own long words plus the long words of the
    seller's prose fields. `email_domain` is the part after the @ and never the part before it."""
    name = str(listing.get("name") or "")
    terms: dict[str, list[str]] = {
        field: [normalise(str(listing[field]))] if listing.get(field) else []
        for field in ("name", "street", "city", "state", "zip", "phone", "slug")
    }
    terms["email_domain"] = [normalise(email.split("@", 1)[1])] if email and "@" in email else []
    terms["abbreviation"] = _abbreviations(name)
    prose = " ".join(str(listing.get(f) or "") for f in ("facility", "services", "hours"))
    pool = {t for t in normalise(f"{name} {prose}").split() if len(t) >= DISTINCTIVE and t not in _GENERIC_N}
    terms["tokens"] = sorted(pool)
    return terms


def _token_set(a: str, b: str) -> float:
    left, right = set(a.split()), set(b.split())
    return len(left & right) / len(left | right) if left and right else 0.0


def _compare(field: str, term: str, line: str) -> Match | None:
    """The methods in order; the FIRST that fires wins, so a match is reported by the strongest
    method that explains it rather than by all of them at once."""
    if not term or not line:
        return None
    if term == line:
        return Match(field, 0, "exact", 1.0)
    # Containment either way -- a sign that carries the whole name inside a sentence, and a name
    # truncated by the sign's own frame -- but only where the CONTAINED fragment is informative.
    if len(term) >= MIN_SUBSTRING and term in line and _informative(term):
        return Match(field, 0, "substring", 0.9)
    if len(line) >= MIN_SUBSTRING and line in term and _informative(line):
        return Match(field, 0, "substring", 0.9)
    if len(line.split()) >= 2:
        overlap = _token_set(term, line)
        if overlap >= TOKEN_SET:
            return Match(field, 0, "token_set", round(overlap, 3))
    ratio = SequenceMatcher(None, term, line).ratio()
    if ratio >= FUZZY:
        return Match(field, 0, "fuzzy", round(ratio, 3))
    return None


def match_lines(lines: Sequence[str], terms: Mapping[str, list[str]]) -> list[Match]:
    found: list[Match] = []
    for index, raw in enumerate(lines):
        line = normalise(raw)
        for field, values in terms.items():
            if field in ("tokens", "abbreviation"):
                continue
            for term in values:
                hit = _compare(field, term, line)
                if hit is not None:
                    found.append(hit._replace(line=index))
                    break
        words = set(line.split())
        for token in terms.get("tokens", ()):
            if token in words:
                found.append(Match("name", index, "distinctive", 0.8))
                break
        upper = raw.strip()
        if 2 <= len(upper) <= 6 and upper.isalpha() and upper.isupper():
            if normalise(upper) in terms.get("abbreviation", ()):
                found.append(Match("name", index, "abbreviation", 0.75))
    return found


#: What the joined pass puts between two lines. One space, so a sign that wrapped reads as one
#: string; never a newline, because none of the classes is written with `re.M`.
JOIN = " "


def _spans(lines: Sequence[str]) -> tuple[str, list[tuple[int, int]]]:
    """The lines as one string, and each line's `[start, end)` span within it."""
    spans: list[tuple[int, int]] = []
    at = 0
    for line in lines:
        spans.append((at, at + len(line)))
        at += len(line) + len(JOIN)
    return JOIN.join(lines), spans


def regex_hits(lines: Sequence[str]) -> list[Match]:
    """Every class that fires on a line, plus every class that fires only on the JOINED text.

    Spec C.5 step 2 runs the classes "over every line and over the joined text", and the second half
    is not decoration: scene text wraps, so "(512)" on one line of a sign and "555-0100" on the next
    is a telephone number that no per-line pass can ever see. A joined hit is attributed to EVERY
    line whose span the match touches, so the aggregator covers both halves of the wrap rather than
    one rectangle spanning the gap between them, and `(field, line)` is deduplicated so a match the
    per-line pass already found is not recorded twice."""
    found = [Match(f"regex:{cls}", index, "regex", 1.0)
             for index, line in enumerate(lines)
             for cls, pattern in REGEX_CLASSES.items() if pattern.search(line)]
    if len(lines) < 2:
        return found
    joined, spans = _spans(lines)
    seen = {(m.field, m.line) for m in found}
    for cls, pattern in REGEX_CLASSES.items():
        for match in pattern.finditer(joined):
            for index, (start, end) in enumerate(spans):
                if start < match.end() and match.start() < end and (f"regex:{cls}", index) not in seen:
                    seen.add((f"regex:{cls}", index))
                    found.append(Match(f"regex:{cls}", index, "regex", 1.0))
    return found


def matches(lines: Sequence[str], listing: Mapping[str, Any], email: str | None) -> list[Match]:
    """Every match, ordered by line then field -- deterministic, so a re-run of the same inputs
    writes the same `identity_matches` and the same regions (spec C.5 step 5)."""
    found = match_lines(lines, identity_terms(listing, email)) + list(regex_hits(lines))
    return sorted(found, key=lambda m: (m.line, m.field, m.method))
```

> **Two entries for `address`.** The dict literal's first `address` pattern is immediately replaced by the one below it, which adds the bare-suite arm; write only the SECOND into the file. It is shown twice here so the reason for the second arm is visible beside the first — a directory board reads "Suite 210" with no street number, and the spec's own class list names `Suite|Ste`.

- [ ] `poetry run pytest tests/privacy/test_identity.py -q -W error` — GREEN. Read any failing row of `HITS` as a statement about the matcher, not about the row: if `HILL COUNTRY ANIIVIAL HOSPITAL` does not reach 0.85, the fix is a substitution pair, not a lowered floor.

- [ ] **Step 3: the task's gates**

```bash
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
```

Every branch of `_compare`, `_abbreviations` and `identity_terms` is reached by the table; if coverage names one that is not, add the row rather than the pragma.

- [ ] **Step 4: commit**

```
feat(privacy): identity matching -- six methods, OCR-error tolerance, and the regex classes

Directive 4 step 3 asks for exact, case-insensitive, punctuation- and
whitespace-normalised, OCR-error-tolerant, partial and abbreviation
matching against the listing's own identity. app/privacy/identity.py does
all six with stdlib difflib and no new dependency, folding the common
scene-text confusions (0/o, 1/l/i, 5/s, 8/b, 2/z, rn/m, vv/w) on BOTH
sides before comparing so a sign read as H0SPITAL is an exact match rather
than a near miss.

Two rules keep it from firing on every photograph of every listing. The
distinctive-token rule matches "Hill Country" on a sign against "Hill
Country Animal Hospital": a name token of five characters or more, outside
the generic veterinary vocabulary. And a substring must be INFORMATIVE --
two tokens or more, at least one of them non-generic -- so "Animal
Hospital" and "Cedar" match nothing at all. The generic set is folded
through the same substitution map before it is compared, or it would match
none of the tokens it exists to filter ("animal" normalises to "anlmal").

The six regex classes fire whether or not they match this listing -- a
telephone number in a photograph of a practice is identifying even when it
is somebody else's -- and they run over the joined text as well as over
each line, because a sign wraps: an area code on one line and the rest on
the next is a number no per-line pass can see. A joined hit is recorded
against every line its span touches, and deduplicated against the per-line
pass.

Only the domain of the owner's address is ever read, and the seller's
prose fields contribute tokens rather than whole-string matches.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `git add app/privacy/identity.py tests/privacy/test_identity.py`

---

### Task P6: the vision adapter — unavailable is not a failure, and a failure is never unavailable

**Files:**
- Create: `app/privacy/vision.py`, `tests/privacy/test_vision.py`
- Modify: `app/config.py` (`anthropic_api_key`), `.env.example`, `DEPLOY.md` (the variable row, the outbound-destinations line), `pyproject.toml`, `poetry.lock`

**Interfaces:**
- Consumes: nothing from earlier tasks; like the two engine adapters it stands alone.
- Produces, `app/privacy/vision.py`:
  - `VISION_MODEL: str = "claude-opus-5"`, `MAX_TOKENS: int = 2048`, `TIMEOUT_S: float = 60.0`, `SDK_RETRIES: int = 2`, `BETAS: list[str]`
  - `VISION_SCHEMA: dict[str, Any]` — the JSON schema `output_config.format` carries
  - `class VisionRegion(BaseModel)` with `kind: str`, `label: str`, `box: tuple[float, float, float, float]`, `confidence: str`
  - `class VisionResult(BaseModel)` with `identifies_practice: bool`, `regions: list[VisionRegion]`
  - `analyse(display: bytes, *, name: str | None, city: str | None, state: str | None) -> dict[str, Any]` — the privacy row's `vision` object, always, never an exception
- The returned object's `status` is one of `unavailable`, `ok`, `failed`; `app/tasks/media.py` treats `failed` as `PROCESSING_FAILED` with `last_error` from the object's `code`, and `unavailable` as no failure at all.

- [ ] **Step 1: probe the pinned SDK before a line of adapter code**

The spec's §C.5 step 4 requires this and nothing may be guessed about the SDK's surface:

```bash
poetry add "anthropic (>=1.0,<2.0)" && poetry lock
poetry run python - <<'PY'
import inspect, anthropic
print("anthropic", anthropic.__version__)
sig = inspect.signature(anthropic.Anthropic.__init__)
print("client:", [p for p in sig.parameters if p in ("api_key", "max_retries", "timeout")])
create = anthropic.Anthropic(api_key="probe-only-never-sent").beta.messages.create
params = inspect.signature(create).parameters
for name in ("model", "max_tokens", "messages", "betas", "fallbacks", "output_config"):
    print(f"beta.messages.create accepts {name}:", name in params)
print("stop_reason refusal is a literal:", "refusal" in str(anthropic.types))
PY
```

- [ ] **Quote that output verbatim in the commit body.** If `beta.messages.create` does not accept `output_config`, `fallbacks` or `betas`, **STOP with `NEEDS_CONTEXT`** — the adapter's one call form is a spec decision and a different one is a controller amendment, not an implementer's improvisation.
- [ ] `.env.example`, beside `CENSUS_API_KEY`:

```
# ANTHROPIC_API_KEY=                                                     # worker only — the vision step of the image identifiability pipeline; John holds it; never in git, chat, or CI
```

- [ ] `app/config.py`, beside `census_api_key`, with the same comment shape:

```python
    # The vision step of the image identifiability pipeline (spec 2026-09-09 C.5 step 4, D-IDP-1).
    # WORKER only; the api never reads it. Optional at boot for the same reason the Census and
    # Resend keys are -- it is refused at the moment it is USED, and its absence is a legitimate
    # state: with no key every photograph completes with `vision: unavailable` and the seller's
    # review carries the rest. Read from SETTINGS and never from `os.environ`, so an unset Railway
    # variable can never be satisfied by an ambient ANTHROPIC_AUTH_TOKEN, a profile or a workload
    # identity, and `monkeypatch.setattr(settings, ...)` is the test seam.
    anthropic_api_key: str | None = None
```

- [ ] `DEPLOY.md` — the variables table row (worker ✓, api blank, "John holds it; never in git, chat, or CI, same rule as `CENSUS_API_KEY`. `railway variable set ANTHROPIC_API_KEY=… --service worker --environment <env>`"), and a new outbound-destinations line beside the Census and Resend ones: **the worker reaches `api.anthropic.com`; the api reaches nothing new.**
- [ ] `poetry run pytest tests/test_docs.py -q -W error` — GREEN.

- [ ] **Step 2: RED — every outcome of the adapter**

Create `tests/privacy/test_vision.py`:

```python
"""The vision adapter (spec 2026-09-09 C.5 step 4).

Directive 4 step 4: vision "MUST NOT replace OCR. It supplements OCR", and is used "where
available". So there are three outcomes and the difference between two of them is the whole point:
UNAVAILABLE (no key) is not a failure and the pipeline continues; FAILED (a key that did not
produce a usable answer) is a failure and the photograph goes to PROCESSING_FAILED. A failure is
never treated as unavailable, because that would quietly downgrade a listing's protection.

The seam is the ADAPTER's own client, not an httpx transport: the SDK is built on httpx2 and a v1
MockTransport cannot be handed to it."""
from __future__ import annotations

import logging
from typing import Any

import pytest

from app.privacy import vision

IMAGE = b"\x00" * 64
PROMPT_FACTS = {"name": "Hill Country Animal Hospital", "city": "Cedar Park", "state": "TX"}


class _Client:
    """Stands in for `anthropic.Anthropic`, recording what the adapter sent."""

    def __init__(self, answer: Any) -> None:
        self.answer, self.sent = answer, []
        self.beta = type("B", (), {"messages": self})()

    def create(self, **kwargs: Any) -> Any:
        self.sent.append(kwargs)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _message(text: str, *, stop_reason: str = "end_turn", model: str = "claude-opus-5") -> Any:
    block = type("Block", (), {"type": "text", "text": text})()
    return type("Message", (), {"content": [block], "stop_reason": stop_reason, "model": model,
                                "stop_details": None, "_request_id": "req_abc123"})()


OK_BODY = ('{"identifies_practice": true, "regions": [{"kind": "signage", "label": "monument sign",'
           ' "box": [10, 20, 300, 90], "confidence": "high"}]}')


def test_no_key_is_unavailable_and_not_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", None)
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result == {"status": "unavailable"}


def test_a_usable_answer_is_recorded_with_the_model_that_actually_answered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client(_message(OK_BODY, model="claude-sonnet-5"))
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.privacy.vision._client", lambda: client)
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result["status"] == "ok" and result["identifies_practice"] is True
    assert result["model"] == "claude-sonnet-5" and result["request_id"] == "req_abc123"
    assert result["regions"][0]["box"] == [10, 20, 300, 90]
    sent = client.sent[0]
    assert sent["model"] == vision.VISION_MODEL and sent["max_tokens"] == vision.MAX_TOKENS
    assert sent["betas"] == vision.BETAS and sent["fallbacks"] == "default"
    assert sent["output_config"]["format"]["schema"] == vision.VISION_SCHEMA


def test_the_prompt_carries_the_name_city_and_state_and_never_the_phone_or_street(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Data minimisation (spec C.5 step 4): a third party is told what the practice is called and
    roughly where, because that is what makes a sign recognisable, and nothing else."""
    client = _Client(_message(OK_BODY))
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.privacy.vision._client", lambda: client)
    vision.analyse(IMAGE, **PROMPT_FACTS)
    text = str(client.sent[0]["messages"])
    assert "Hill Country Animal Hospital" in text and "Cedar Park" in text and "TX" in text
    assert "555-0100" not in text and "Cypress Creek" not in text


@pytest.mark.parametrize(("answer", "code"), [
    (RuntimeError("connection reset"), "VISION_FAILED"),
    (_message("not json at all"), "VISION_FAILED"),
    (_message('{"identifies_practice": "yes"}'), "VISION_FAILED"),
    (_message(OK_BODY, stop_reason="max_tokens"), "VISION_FAILED"),
    (_message("", stop_reason="refusal"), "VISION_REFUSED"),
])
def test_every_other_outcome_is_failed_with_its_own_code(
    monkeypatch: pytest.MonkeyPatch, answer: Any, code: str
) -> None:
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.privacy.vision._client", lambda: _Client(answer))
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result["status"] == "failed" and result["code"] == code


def test_a_refusal_is_read_before_the_content_is(monkeypatch: pytest.MonkeyPatch) -> None:
    """`stop_reason == "refusal"` is checked FIRST: reading `content[0].text` on a refusal is how a
    caller gets an IndexError instead of a recorded outcome."""
    refused = type("Message", (), {"content": [], "stop_reason": "refusal", "model": "claude-opus-5",
                                   "stop_details": type("D", (), {"category": "image_safety"})(),
                                   "_request_id": "req_x"})()
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.privacy.vision._client", lambda: _Client(refused))
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result["code"] == "VISION_REFUSED" and result["refusal_category"] == "image_safety"


def test_an_unlocalised_answer_still_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    """`identifies_practice` true with no usable box: the photograph still reaches the seller's
    review, and `unlocalised` is recorded so the record explains itself (D-IDP-8)."""
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.privacy.vision._client",
                        lambda: _Client(_message('{"identifies_practice": true, "regions": []}')))
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result["status"] == "ok" and result["unlocalised"] is True


def test_the_adapter_never_logs_the_image_or_the_response(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Global Constraint (h). The request id and the exception class, and nothing else -- no base64,
    no response text, no key, no prompt."""
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-secret-value")
    monkeypatch.setattr("app.privacy.vision._client", lambda: _Client(RuntimeError("boom: sk-secret-value")))
    with caplog.at_level(logging.DEBUG):
        vision.analyse(b"\xff\xd8\xffPHOTOBYTES", **PROMPT_FACTS)
    logged = caplog.text
    assert "RuntimeError" in logged
    assert "sk-secret-value" not in logged and "PHOTOBYTES" not in logged and "boom" not in logged
```

- [ ] `poetry run pytest tests/privacy/test_vision.py -q -W error` — RED: `ModuleNotFoundError: No module named 'app.privacy.vision'`.

- [ ] **Step 3: GREEN — `app/privacy/vision.py`**

```python
"""Visual identity signals, through the Anthropic Messages API (spec 2026-09-09 C.5 step 4).

Directive 4 step 4: this SUPPLEMENTS OCR and never replaces it. Three outcomes, and the difference
between two of them is load-bearing:

  unavailable  no key. Not a failure. The pipeline continues, the record says so, and the seller's
               review carries the OCR, regex and symbol regions. This is QA's state today.
  ok           a body that validated against VisionResult.
  failed       a key that did not produce one -- a transport error after the SDK's own retries, a
               refusal, a truncation, or a body the model refused to shape. PROCESSING_FAILED, and
               after three attempts REVIEW_REQUIRED. NEVER recorded as unavailable, because that
               would quietly downgrade a listing's protection to "we did not try".

This module NEVER raises: every outcome is the dict the privacy row's `vision` column takes. It
logs the SDK's request id and the exception class and nothing else -- never the image, never the
prompt, never the response text, never the key.

D-IDP-1 is queued for John: whether to send at all, which model, and a monthly cap. With the key
absent -- which is every deployed environment today -- this module makes no request."""
from __future__ import annotations

import base64
import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config import settings

log = logging.getLogger(__name__)

#: John may name another; `claude-sonnet-5` is the cost lever. One constant, one line.
VISION_MODEL = "claude-opus-5"
MAX_TOKENS = 2048
TIMEOUT_S = 60.0
SDK_RETRIES = 2
BETAS = ["server-side-fallback-2026-07-01"]

VISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["identifies_practice", "regions"],
    "properties": {
        "identifies_practice": {"type": "boolean"},
        "regions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "label", "box", "confidence"],
                "properties": {
                    "kind": {"enum": ["logo", "signage", "uniform", "vehicle", "wall_graphic",
                                      "document", "business_card", "directory", "text", "other"]},
                    "label": {"type": "string"},
                    "box": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
                    "confidence": {"enum": ["low", "medium", "high"]},
                },
            },
        },
    },
}

PROMPT = (
    "This photograph belongs to a veterinary practice listing. The practice is called {name} and is"
    " in {city}, {state}. Find every visible element that could let a reader identify this specific"
    " practice: signage, logos, branded uniforms, branded vehicles, wall graphics, documents,"
    " business cards, building directories, street or building numbers, and any other lettering."
    " Give each one a bounding box in the image's own pixel coordinates. Do not guess: report"
    " only what is visible."
)


class VisionRegion(BaseModel):
    kind: str
    label: str
    box: tuple[float, float, float, float]
    confidence: str


class VisionResult(BaseModel):
    identifies_practice: bool
    regions: list[VisionRegion]


def _client() -> Any:
    """The SDK client, built per call and never cached: a worker child may sit idle for hours and a
    connection pool held across that is a source of transport errors, not a saving. The key is
    passed EXPLICITLY from settings, so no ambient credential can satisfy an unset variable."""
    import anthropic  # noqa: PLC0415  (lazy -- the api imports this module's siblings, never this)

    return anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=SDK_RETRIES, timeout=TIMEOUT_S)


def _failed(code: str, request_id: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"status": "failed", "code": code, "model": VISION_MODEL, "request_id": request_id, **extra}


def analyse(display: bytes, *, name: str | None, city: str | None, state: str | None) -> dict[str, Any]:
    """The privacy row's `vision` object. Never raises."""
    if settings.anthropic_api_key is None:
        return {"status": "unavailable"}
    message: Any = None
    try:
        message = _client().beta.messages.create(
            model=VISION_MODEL,
            max_tokens=MAX_TOKENS,
            betas=BETAS,
            fallbacks="default",
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": VISION_SCHEMA}},
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/webp",
                                             "data": base64.b64encode(display).decode()}},
                {"type": "text", "text": PROMPT.format(name=name or "unnamed", city=city or "an unstated city",
                                                       state=state or "an unstated state")},
            ]}],
        )
    except Exception as exc:   # every SDK error class, after its own retries; the class name only
        log.warning("[vision] call failed: %s", type(exc).__name__)
        return _failed("VISION_FAILED")
    request_id = getattr(message, "_request_id", None)
    # BEFORE `content` is read: a refusal carries no text block and indexing it is an IndexError
    # instead of a recorded outcome.
    if message.stop_reason == "refusal":
        category = getattr(getattr(message, "stop_details", None), "category", None)
        log.warning("[vision] refused: %s", request_id)
        return _failed("VISION_REFUSED", request_id, refusal_category=category)
    if message.stop_reason == "max_tokens":
        log.warning("[vision] truncated: %s", request_id)
        return _failed("VISION_FAILED", request_id)
    body = next((block.text for block in message.content if getattr(block, "type", None) == "text"), "")
    try:
        parsed = VisionResult.model_validate_json(body)
    except ValidationError:
        # The response TEXT is never logged -- it is a model's description of a photograph.
        log.warning("[vision] body did not validate: %s", request_id)
        return _failed("VISION_FAILED", request_id)
    return {
        "status": "ok",
        # The model that ACTUALLY answered: `fallbacks: "default"` may route to another.
        "model": getattr(message, "model", VISION_MODEL),
        "request_id": request_id,
        "identifies_practice": parsed.identifies_practice,
        "regions": [{"kind": r.kind, "label": r.label, "box": list(r.box), "confidence": r.confidence}
                    for r in parsed.regions],
        # `identifies_practice` with nothing to draw: the photograph still reaches the seller's
        # review and the manual mask is the tool (D-IDP-8).
        "unlocalised": parsed.identifies_practice and not parsed.regions,
    }
```

- [ ] `poetry run pytest tests/privacy/test_vision.py -q -W error` — GREEN.
- [ ] Confirm the one broad `except Exception` is honest: it is there because the SDK's error classes are not a stable, catchable set across versions and an escape would take the worker's child down instead of writing `PROCESSING_FAILED`. The exception's `str()` is never logged, only its class, which is why the key in the test's exception message does not appear in the capture.

- [ ] **Step 4: the task's gates**

```bash
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
grep -rn "ANTHROPIC_API_KEY" app/ | grep -v "config.py"     # expect nothing: only Settings names it
grep -rn "os.environ" app/privacy/                          # expect nothing
```

- [ ] **Step 5: commit**

```
feat(privacy): the vision adapter -- unavailable is not a failure

Directive 4 step 4: visual identity detection supplements OCR and never
replaces it, "where available". app/privacy/vision.py has three outcomes
and the difference between two of them is the point: no key is
UNAVAILABLE, the pipeline continues and the record says so (which is
every deployed environment today); a key that did not produce a usable
answer -- a transport error after the SDK's own retries, a refusal, a
truncation, a body that did not validate -- is FAILED, which becomes
PROCESSING_FAILED and, after three attempts, REVIEW_REQUIRED. A failure is
never recorded as unavailable.

The module never raises: every outcome is the dict the privacy row takes.
It logs the request id and the exception class and nothing else -- never
the image, the prompt, the response text or the key, proved by a test that
plants the key inside an exception message and asserts it is absent from
the capture. The refusal branch is read before content is, because a
refusal carries no text block.

ANTHROPIC_API_KEY is worker-only, optional at boot, read from Settings
rather than os.environ so no ambient credential can satisfy an unset
Railway variable, and documented in .env.example and DEPLOY.md with the
same handling rule as CENSUS_API_KEY. The worker's egress to
api.anthropic.com is recorded in DEPLOY.md.

SDK probe output (pinned version and the accepted parameters):
<paste the Step 1 output>

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `git add app/privacy/vision.py tests/privacy/test_vision.py app/config.py .env.example DEPLOY.md pyproject.toml poetry.lock`

---

### Task P7: aggregation, and opaque irreversible redaction

**Files:**
- Create: `app/privacy/aggregate.py`, `tests/privacy/test_aggregate.py`
- Create: `app/media/redact.py`, `tests/media/test_redact.py`
- Unchanged: `app/media/encode.py` — `redact.py` extends its primitives and never duplicates them

**Interfaces:**
- Consumes: `app/privacy/ocr.py::Line`, `app/privacy/barcodes.py::Symbol`, `app/privacy/identity.py::Match`, `app/media/encode.py::encode_webp` and `sha256_hex`.
- Produces, `app/privacy/aggregate.py`:
  - `OCR_PAD_MIN = 12`, `OCR_PAD_FRACTION = 0.25`, `VISION_PAD_MIN = 24`, `VISION_PAD_FRACTION = 0.20`, `MERGE_GAP_PX = 8`, `BARCODE_EXPAND = 1.15`
  - `regions_for(*, lines, matches, symbols, vision, size) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]` — `(detected_regions, redaction_regions)`, the two jsonb columns, in that order
  - `fillable(regions: Sequence[Mapping[str, Any]]) -> list[list[tuple[float, float]]]` — every polygon whose `source` is not `removed-by-seller`
  - `rect(box: tuple[float, float, float, float]) -> list[list[float]]` — a box as the stored four-point polygon; **public**, because P12's mask routes build a manual region with it
  - `union_auto(old: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]], *, confirmed: bool) -> list[dict[str, Any]]` — the in-place re-run's rule
- A `redaction_regions` entry is `{"id": str, "polygon": [[x, y], …], "source": "auto"|"manual"|"removed-by-seller", "expanded_from": int|None, "pad_px": int, "by": str|None, "at": str|None}`; a `detected_regions` entry is `{"source": "ocr_match"|"regex"|"barcode"|"vision", "polygon": [[x, y], …], "line": int|None, "label": str|None}`.
- Produces, `app/media/redact.py`: `FILL: tuple[int, int, int] = (0, 58, 112)`; `fill_regions(display: bytes, polygons: Sequence[Sequence[tuple[float, float]]]) -> tuple[bytes, str] | None`.

- [ ] **Step 1: RED — aggregation**

Create `tests/privacy/test_aggregate.py`:

```python
"""Region aggregation (spec 2026-09-09 C.5 step 5; directive 4 step 5, 5).

Directive 5: "Where necessary, expand the redaction region sufficiently to prevent surrounding
pixels from reconstructing the identifying information", and "Do NOT crop away important image
content unnecessarily". Those two pull against each other, and the numbers below are the spec's
answer: a quarter of the shorter side for text, a fifth per side for a vision box (whose
coordinates are approximate), and a merge of anything within 8 px so a sign is one block rather
than a picket fence that leaks its letter count."""
from __future__ import annotations

from typing import Any

import pytest

from app.privacy import aggregate
from app.privacy.barcodes import Symbol
from app.privacy.identity import Match
from app.privacy.ocr import Line

SIZE = (1600, 1200)


def _line(text: str, x0: float, y0: float, x1: float, y1: float) -> Line:
    return Line(text, 0.95, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def _box(region: dict[str, Any]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in region["polygon"]]
    ys = [p[1] for p in region["polygon"]]
    return min(xs), min(ys), max(xs), max(ys)


def test_a_matched_line_becomes_one_padded_auto_region() -> None:
    lines = [_line("HILL COUNTRY ANIMAL HOSPITAL", 100, 100, 500, 140)]
    detected, redaction = aggregate.regions_for(
        lines=lines, matches=[Match("name", 0, "exact", 1.0)], symbols=[], vision={"status": "unavailable"},
        size=SIZE)
    assert [d["source"] for d in detected] == ["ocr_match"]
    assert len(redaction) == 1 and redaction[0]["source"] == "auto" and redaction[0]["expanded_from"] == 0
    x0, y0, x1, y1 = _box(redaction[0])
    pad = max(aggregate.OCR_PAD_MIN, round(40 * aggregate.OCR_PAD_FRACTION))   # 40 px is the shorter side
    assert (x0, y0, x1, y1) == (100 - pad, 100 - pad, 500 + pad, 140 + pad)


def test_an_unmatched_line_is_not_a_region_and_a_regex_line_is() -> None:
    """"each hit is an identifying region regardless of matching" -- but a line that matched
    nothing and hit no class is just a word on a wall."""
    lines = [_line("PLEASE KEEP DOGS ON A LEAD", 10, 10, 300, 40), _line("(512) 555-0100", 10, 60, 200, 90)]
    _detected, redaction = aggregate.regions_for(
        lines=lines, matches=[Match("regex:phone", 1, "regex", 1.0)], symbols=[],
        vision={"status": "unavailable"}, size=SIZE)
    assert len(redaction) == 1 and _box(redaction[0])[1] > 40


def test_every_symbol_is_a_region_and_is_expanded_about_its_centroid() -> None:
    symbol = Symbol("QRCode", "url", [(100.0, 100.0), (200.0, 100.0), (200.0, 200.0), (100.0, 200.0)])
    detected, redaction = aggregate.regions_for(lines=[], matches=[], symbols=[symbol],
                                                vision={"status": "unavailable"}, size=SIZE)
    assert [d["source"] for d in detected] == ["barcode"]
    x0, y0, x1, y1 = _box(redaction[0])
    # `pytest.approx`, not `==`: `_scaled` computes `(100.0 * 1.15) / 2` as 57.499999999999993 and
    # the width back out as 115.0, while `100 * 1.15` is 114.99999999999999. Both are correct
    # IEEE754 and they are not equal; asserting bit equality on a scaled float is a test that fails
    # for arithmetic rather than for behaviour.
    assert (x1 - x0) == pytest.approx(100 * aggregate.BARCODE_EXPAND)
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == pytest.approx((150.0, 150.0))


def test_a_vision_box_is_padded_more_because_its_coordinates_are_approximate() -> None:
    vision = {"status": "ok", "identifies_practice": True,
              "regions": [{"kind": "logo", "label": "wall logo", "box": [400, 400, 600, 500],
                           "confidence": "low"}]}
    _detected, redaction = aggregate.regions_for(lines=[], matches=[], symbols=[], vision=vision, size=SIZE)
    x0, _y0, x1, _y1 = _box(redaction[0])
    assert x0 == 400 - max(aggregate.VISION_PAD_MIN, round(200 * aggregate.VISION_PAD_FRACTION))
    assert x1 == 600 + max(aggregate.VISION_PAD_MIN, round(200 * aggregate.VISION_PAD_FRACTION))


def test_every_confidence_is_filled_because_the_seller_removes_what_is_unnecessary() -> None:
    vision = {"status": "ok", "identifies_practice": True, "regions": [
        {"kind": "signage", "label": "a", "box": [10, 10, 60, 40], "confidence": "low"},
        {"kind": "logo", "label": "b", "box": [800, 800, 900, 900], "confidence": "high"}]}
    _detected, redaction = aggregate.regions_for(lines=[], matches=[], symbols=[], vision=vision, size=SIZE)
    assert len(redaction) == 2


def test_two_lines_of_one_sign_merge_into_one_polygon() -> None:
    """A picket fence of per-line boxes leaks the shape of the words between them."""
    lines = [_line("HILL COUNTRY", 100, 100, 400, 140), _line("ANIMAL HOSPITAL", 100, 146, 400, 186)]
    _detected, redaction = aggregate.regions_for(
        lines=lines, matches=[Match("name", 0, "distinctive", 0.8), Match("name", 1, "token_set", 0.7)],
        symbols=[], vision={"status": "unavailable"}, size=SIZE)
    assert len(redaction) == 1
    x0, y0, x1, y1 = _box(redaction[0])
    assert y0 <= 100 - aggregate.OCR_PAD_MIN and y1 >= 186 + aggregate.OCR_PAD_MIN


def test_a_region_is_clamped_to_the_image() -> None:
    lines = [_line("HILL COUNTRY ANIMAL HOSPITAL", 0, 0, 200, 30)]
    _detected, redaction = aggregate.regions_for(
        lines=lines, matches=[Match("name", 0, "exact", 1.0)], symbols=[],
        vision={"status": "unavailable"}, size=(300, 200))
    x0, y0, x1, y1 = _box(redaction[0])
    assert (x0, y0) == (0, 0) and x1 <= 300 and y1 <= 200


def test_the_same_inputs_give_the_same_output_every_time() -> None:
    """Directive 23's "deterministic processing", and what makes a regeneration reproducible."""
    lines = [_line("HILL COUNTRY ANIMAL HOSPITAL", 100, 100, 500, 140), _line("(512) 555-0100", 20, 900, 300, 940)]
    args: dict[str, Any] = {"lines": lines,
                            "matches": [Match("name", 0, "exact", 1.0), Match("regex:phone", 1, "regex", 1.0)],
                            "symbols": [], "vision": {"status": "unavailable"}, "size": SIZE}
    first = aggregate.regions_for(**args)
    second = aggregate.regions_for(**args)
    assert [r["polygon"] for r in first[1]] == [r["polygon"] for r in second[1]]
    assert [r["polygon"] for r in first[0]] == [r["polygon"] for r in second[0]]


def test_fillable_excludes_what_the_seller_removed_and_keeps_what_they_added() -> None:
    regions = [
        {"id": "1", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]], "source": "auto"},
        {"id": "2", "polygon": [[20, 20], [30, 20], [30, 30], [20, 30]], "source": "removed-by-seller"},
        {"id": "3", "polygon": [[40, 40], [50, 40], [50, 50], [40, 50]], "source": "manual"},
    ]
    assert [p[0] for p in aggregate.fillable(regions)] == [(0, 0), (40, 40)]


def test_the_in_place_re_run_replaces_the_auto_set_but_unions_it_on_a_confirmed_row() -> None:
    """Spec C.5: on an unconfirmed row the fresh scan REPLACES the auto set; on a confirmed row the
    two are UNIONED, so the new derivative hides a superset of what the seller confirmed and
    nothing they never saw is revealed. The seller's own regions carry forward by id either way,
    and a new auto region inside a removed one is recorded and not filled."""
    old = [{"id": "a1", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]], "source": "auto"},
           {"id": "m1", "polygon": [[90, 90], [99, 90], [99, 99], [90, 99]], "source": "manual"},
           {"id": "r1", "polygon": [[40, 40], [60, 40], [60, 60], [40, 60]], "source": "removed-by-seller"}]
    fresh = [{"id": "a2", "polygon": [[20, 20], [30, 20], [30, 30], [20, 30]], "source": "auto"},
             {"id": "a3", "polygon": [[45, 45], [55, 45], [55, 55], [45, 55]], "source": "auto"}]

    unconfirmed = aggregate.union_auto(old, fresh, confirmed=False)
    assert {r["id"] for r in unconfirmed} == {"a2", "m1", "r1"}          # a1 gone, a3 inside r1
    confirmed = aggregate.union_auto(old, fresh, confirmed=True)
    assert {r["id"] for r in confirmed} == {"a1", "a2", "m1", "r1"}      # a1 kept -- never fewer
    assert all(r["source"] != "auto" or r["id"] != "a3" for r in confirmed)
```

- [ ] `poetry run pytest tests/privacy/test_aggregate.py -q -W error` — RED: `ModuleNotFoundError`.

- [ ] **Step 2: GREEN — `app/privacy/aggregate.py`**

```python
"""The union of everything the pipeline found, expanded and merged into what the fill covers.

Directive 4 step 5 asks for "a structured detection result"; directive 5 asks that a region be
expanded "sufficiently to prevent surrounding pixels from reconstructing the identifying
information" while not cropping away useful content. Two columns come out of this module:

  detected_regions   every candidate BEFORE expansion, tagged by source. The record, and what makes
                     a decision explainable months later.
  redaction_regions  what the fill covers: expanded, merged, each with an id the seller's Remove
                     targets.

Deterministic by construction -- sorted inputs, integer arithmetic, no set iteration order in the
output -- because a regeneration that produced different regions from the same scan would change a
derivative the seller had already confirmed."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from app.privacy.barcodes import Symbol
from app.privacy.identity import Match
from app.privacy.ocr import Line

#: Text: at least 12 px, or a quarter of the region's shorter side.
OCR_PAD_MIN = 12
OCR_PAD_FRACTION = 0.25
#: Vision: more, because a model's "coordinate and localization outputs are approximate".
VISION_PAD_MIN = 24
VISION_PAD_FRACTION = 0.20
#: Expanded boxes that overlap or sit within this many pixels become one polygon.
MERGE_GAP_PX = 8
#: A symbol's four corners, scaled about their centroid.
BARCODE_EXPAND = 1.15

Box = tuple[float, float, float, float]


def _bounds(polygon: Sequence[Sequence[float]]) -> Box:
    xs = [float(p[0]) for p in polygon]
    ys = [float(p[1]) for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def rect(box: Box) -> list[list[float]]:
    """A box as the four-point polygon every region is stored as. PUBLIC, because P12's mask routes
    build a manual region from the seller's dragged box and must not reach into a private helper of
    another module to do it."""
    x0, y0, x1, y1 = box
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _padded(box: Box, minimum: int, fraction: float, size: tuple[int, int]) -> tuple[Box, int]:
    x0, y0, x1, y1 = box
    pad = max(minimum, round(min(x1 - x0, y1 - y0) * fraction))
    w, h = size
    return (max(0.0, x0 - pad), max(0.0, y0 - pad), min(float(w), x1 + pad), min(float(h), y1 + pad)), pad


def _scaled(polygon: Sequence[Sequence[float]], factor: float, size: tuple[int, int]) -> Box:
    x0, y0, x1, y1 = _bounds(polygon)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hw, hh = (x1 - x0) * factor / 2, (y1 - y0) * factor / 2
    w, h = size
    return max(0.0, cx - hw), max(0.0, cy - hh), min(float(w), cx + hw), min(float(h), cy + hh)


def _near(a: Box, b: Box) -> bool:
    return not (a[2] + MERGE_GAP_PX < b[0] or b[2] + MERGE_GAP_PX < a[0]
                or a[3] + MERGE_GAP_PX < b[1] or b[3] + MERGE_GAP_PX < a[1])


def _merged(boxes: list[tuple[Box, int, int | None]]) -> list[tuple[Box, int, int | None]]:
    """Repeatedly absorb any two boxes within MERGE_GAP_PX. Quadratic in the number of regions,
    which is tens at most: a photograph with hundreds of separate identifying regions is a
    directory board, and merging it into one block is the right answer anyway."""
    out = list(boxes)
    changed = True
    while changed:
        changed = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                if _near(out[i][0], out[j][0]):
                    a, b = out[i], out[j]
                    box = (min(a[0][0], b[0][0]), min(a[0][1], b[0][1]),
                           max(a[0][2], b[0][2]), max(a[0][3], b[0][3]))
                    out[i] = (box, max(a[1], b[1]), a[2] if a[2] is not None else b[2])
                    del out[j]
                    changed = True
                    break
            if changed:
                break
    return sorted(out, key=lambda item: (item[0][1], item[0][0]))


def regions_for(*, lines: Sequence[Line], matches: Sequence[Match], symbols: Sequence[Symbol],
                vision: Mapping[str, Any], size: tuple[int, int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`(detected_regions, redaction_regions)` -- the two jsonb columns, in that order."""
    detected: list[dict[str, Any]] = []
    padded: list[tuple[Box, int, int | None]] = []

    for index in sorted({m.line for m in matches}):
        if index >= len(lines):
            continue
        source = "regex" if all(m.field.startswith("regex:") for m in matches if m.line == index) else "ocr_match"
        polygon = lines[index].quad
        detected.append({"source": source, "polygon": [[x, y] for x, y in polygon], "line": index, "label": None})
        box, pad = _padded(_bounds(polygon), OCR_PAD_MIN, OCR_PAD_FRACTION, size)
        padded.append((box, pad, index))

    for symbol in symbols:
        detected.append({"source": "barcode", "polygon": [[x, y] for x, y in symbol.quad],
                         "line": None, "label": symbol.payload_kind})
        padded.append((_scaled(symbol.quad, BARCODE_EXPAND, size), 0, None))

    for region in vision.get("regions", ()):
        box = (float(region["box"][0]), float(region["box"][1]), float(region["box"][2]), float(region["box"][3]))
        detected.append({"source": "vision", "polygon": rect(box), "line": None, "label": region.get("label")})
        grown, pad = _padded(box, VISION_PAD_MIN, VISION_PAD_FRACTION, size)
        padded.append((grown, pad, None))

    redaction = [{"id": str(uuid4()), "polygon": rect(box), "source": "auto",
                  "expanded_from": origin, "pad_px": pad, "by": None, "at": None}
                 for box, pad, origin in _merged(padded)]
    return detected, redaction


def fillable(regions: Sequence[Mapping[str, Any]]) -> list[list[tuple[float, float]]]:
    """Every polygon the fill covers: auto and manual, never `removed-by-seller`."""
    return [[(float(p[0]), float(p[1])) for p in r["polygon"]]
            for r in regions if r.get("source") != "removed-by-seller"]


def _inside(inner: Box, outer: Box) -> bool:
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def union_auto(old: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]], *,
               confirmed: bool) -> list[dict[str, Any]]:
    """The in-place re-run's rule (spec C.5).

    The seller's own regions -- manual, and the ones they removed -- carry forward by id, always. The
    AUTO set is replaced on an unconfirmed row and UNIONED on a confirmed one, so a confirmed
    derivative can only ever hide MORE than the seller approved and never less. A fresh auto region
    lying inside a region the seller removed is recorded in `detected_regions` by the caller and is
    not filled: they said that one was unnecessary and a re-run does not overrule them."""
    kept = [dict(r) for r in old if r.get("source") != "auto"]
    removed = [_bounds(r["polygon"]) for r in old if r.get("source") == "removed-by-seller"]
    fresh = [dict(r) for r in new
             if r.get("source") == "auto" and not any(_inside(_bounds(r["polygon"]), box) for box in removed)]
    if confirmed:
        kept += [dict(r) for r in old if r.get("source") == "auto"]
    return sorted(kept + fresh, key=lambda r: (_bounds(r["polygon"])[1], _bounds(r["polygon"])[0], r["id"]))
```

- [ ] `poetry run pytest tests/privacy/test_aggregate.py -q -W error` — GREEN.

- [ ] **Step 3: RED — the redaction, and the irreversibility property**

Create `tests/media/test_redact.py`:

```python
"""Opaque, irreversible redaction (spec 2026-09-09 C.5 step 6; directive 5).

"Use irreversible/opaque redaction rather than relying solely on Gaussian blur. The underlying
identifiable pixels must not remain recoverable from the buyer-facing derivative."

The strongest checkable form of that is the property in
`test_two_photographs_that_differ_only_under_the_mask_produce_identical_bytes`: a constant fill
carries no information about what it covers, so two display images whose only difference is inside
the region produce the SAME derivative, byte for byte. A blur, a pixelation or a mosaic all fail
that test, which is why none of them is used.

**Two facts about the encoder shape this file, and both were measured before it was written.**
(1) The two display inputs must be built LOSSLESSLY. `encode_webp`'s ladder is lossy
(`Image.save(..., "WEBP", quality=q)`, `app/media/encode.py:69-88`), so two sources that differ
inside the mask come back differing OUTSIDE it too — intra-prediction propagates across the block
boundary — and the property would then fail for a reason that has nothing to do with redaction.
Measured: with lossy sources the two derivatives differ; with lossless sources they are identical,
64 844 bytes each. (2) The fill does not survive the ladder EXACTLY. `redact.FILL` is
`(0, 58, 112)`; after the derivative's own lossy encode at the ladder's first rung the worst
per-channel error twelve pixels inside the region is 1, and at the region's edge it is around 19.
So the fill assertions sample well inside the region and compare within `FILL_TOLERANCE`, and the
byte-equality property above is what carries the security claim — not a colour triple."""
from __future__ import annotations

import io

from PIL import Image

from app.media import redact

BOX = [(100.0, 100.0), (400.0, 100.0), (400.0, 220.0), (100.0, 220.0)]
#: Measured, not guessed: the worst per-channel error at least 12 px inside a filled region, after
#: `encode_webp`'s ladder, is 1 on the fixture below. Four is that with headroom; a value this test
#: has to RAISE later is a change in the encoder and a `NEEDS_CONTEXT`, not a tuning knob.
FILL_TOLERANCE = 4
#: How far inside a region a fill assertion samples. The edge of a filled block is where the lossy
#: encoder's ringing lives (about 19 per channel at one pixel in), and asserting there would be
#: asserting a property of libwebp rather than of this module.
FILL_MARGIN_PX = 12


def _display(patch: tuple[int, int, int] | None = None) -> bytes:
    """A 900x600 display object with a little structure, optionally with a patch inside the region.

    LOSSLESS, so two calls differing only inside `BOX` are pixel-identical everywhere else — which
    is exactly the premise the irreversibility property needs and exactly what a lossy source
    destroys. It stands in for `display.webp` faithfully in every way that matters here: same size,
    same mode, same decode path."""
    image = Image.new("RGB", (900, 600), (210, 215, 220))
    for x in range(0, 900, 9):
        for y in range(0, 600, 7):
            image.putpixel((x, y), ((x * 7) % 256, (y * 11) % 256, 90))
    if patch is not None:
        for x in range(120, 380):
            for y in range(120, 200):
                image.putpixel((x, y), patch)
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", lossless=True, method=6)
    return buffer.getvalue()


def _is_fill(pixel: tuple[int, int, int]) -> bool:
    return all(abs(pixel[channel] - redact.FILL[channel]) <= FILL_TOLERANCE for channel in range(3))


def test_every_pixel_inside_the_region_is_the_fill_colour() -> None:
    out = redact.fill_regions(_display(), [BOX])
    assert out is not None
    image = Image.open(io.BytesIO(out[0])).convert("RGB")
    sampled = 0
    for x in range(100 + FILL_MARGIN_PX, 400 - FILL_MARGIN_PX, 7):
        for y in range(100 + FILL_MARGIN_PX, 220 - FILL_MARGIN_PX, 5):
            assert _is_fill(image.getpixel((x, y))), (x, y, image.getpixel((x, y)))
            sampled += 1
    assert sampled > 400, "the sampling grid collapsed -- this would pass vacuously"


def test_two_photographs_that_differ_only_under_the_mask_produce_identical_bytes() -> None:
    """The irreversibility property. A fill is a constant, so the lossy encoder receives no
    information about the covered pixels and none can survive in the output.

    The two sources are lossless and pixel-identical outside `BOX`; the patch is strictly inside it
    (120-380 x 120-200 against a region of 100-400 x 100-220), so nothing outside the fill differs
    between them and the only thing this can be measuring is the fill."""
    one = redact.fill_regions(_display((255, 0, 0)), [BOX])
    two = redact.fill_regions(_display((0, 255, 0)), [BOX])
    assert one is not None and two is not None
    assert one[0] == two[0] and one[1] == two[1]
    assert _display((255, 0, 0)) != _display((0, 255, 0)), "the two sources are the same file"


def test_the_derivative_keeps_the_display_dimensions() -> None:
    """Directive 5: "Preserve image dimensions/aspect ratio where possible." Display is already
    within the 1600 px bound, so the resize step never fires and in equals out."""
    source = _display()
    before = Image.open(io.BytesIO(source)).size
    out = redact.fill_regions(source, [BOX])
    assert out is not None and Image.open(io.BytesIO(out[0])).size == before


def test_the_derivative_carries_no_metadata() -> None:
    out = redact.fill_regions(_display(), [BOX])
    assert out is not None
    image = Image.open(io.BytesIO(out[0]))
    assert not image.info.get("exif") and not image.info.get("icc_profile") and not image.info.get("xmp")


def test_a_polygon_is_filled_as_a_polygon_and_not_as_its_bounding_box() -> None:
    """A rotated sign is covered by the quad the engine returned; the corner outside it is not."""
    triangle = [(100.0, 100.0), (400.0, 100.0), (100.0, 300.0)]
    out = redact.fill_regions(_display(), [triangle])
    assert out is not None
    image = Image.open(io.BytesIO(out[0])).convert("RGB")
    assert _is_fill(image.getpixel((140, 140)))          # well inside the triangle
    assert not _is_fill(image.getpixel((390, 290)))      # the corner the bounding box would cover


def test_no_regions_still_re_encodes_so_the_derivative_always_exists() -> None:
    """A photograph the pipeline found nothing in still gets a redacted.webp: the resolver serves
    that object under NOT_SHOW, and a null derivative would be a null slot for no reason."""
    out = redact.fill_regions(_display(), [])
    assert out is not None and len(out[1]) == 64


def test_a_two_point_polygon_is_ignored_rather_than_drawn() -> None:
    """`ImageDraw.polygon` needs three points; the guard is a branch and therefore needs a case."""
    out = redact.fill_regions(_display(), [[(10.0, 10.0), (20.0, 20.0)]])
    untouched = redact.fill_regions(_display(), [])
    assert out is not None and untouched is not None and out[1] == untouched[1]


def test_bytes_that_will_not_fit_the_ladder_are_None_not_an_exception(monkeypatch) -> None:
    """`encode_webp` -> None is REDACTION_FAILED with reason ENCODE_TOO_LARGE. Fail closed."""
    monkeypatch.setattr("app.media.redact.encode_webp", lambda data: None)
    assert redact.fill_regions(_display(), [BOX]) is None


def test_undecodable_bytes_are_None(monkeypatch) -> None:
    assert redact.fill_regions(b"not an image at all", [BOX]) is None
```

- [ ] `poetry run pytest tests/media/test_redact.py -q -W error` — RED: `ModuleNotFoundError: No module named 'app.media.redact'`.

- [ ] **Step 4: GREEN — `app/media/redact.py`**

```python
"""The buyer-safe derivative: an opaque fill over every region, re-encoded (spec C.5 step 6).

Never blur, never pixelate, never mosaic. Each of those leaves a function of the covered pixels in
the output, and each has been reversed in public before. A constant fill leaves nothing: two
photographs differing only under the mask encode to the same bytes, which is the property
`tests/media/test_redact.py` asserts directly rather than arguing for.

`encode_webp` does the re-encode -- the same quality ladder, the same 1600 px bound, the same
metadata-free save (`app/media/encode.py`), so the derivative is normalised exactly as display is
and this module owns no encoding rules of its own. Display is already within the bound, so the
resize never fires and the derivative's dimensions equal display's.

A future thumbnail generator must take THIS output as its input, never the display object."""
from __future__ import annotations

import io
from collections.abc import Sequence

from PIL import Image, ImageDraw, UnidentifiedImageError

from app.media.encode import encode_webp

#: The design's navy, `var(--color-navy)` -- the done card's colour (D-IDP-9; black is the
#: alternative John may rule for). A constant, and that is the whole of its security property.
FILL = (0, 58, 112)


def fill_regions(display: bytes, polygons: Sequence[Sequence[tuple[float, float]]]) -> tuple[bytes, str] | None:
    """The derivative's bytes and their SHA-256, or None when the source will not decode or the
    result will not fit the ladder -- REDACTION_FAILED at the caller, never a fallback."""
    try:
        image = Image.open(io.BytesIO(display)).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None
    draw = ImageDraw.Draw(image)
    for polygon in polygons:
        if len(polygon) >= 3:
            draw.polygon([(float(x), float(y)) for x, y in polygon], fill=FILL)
    buffer = io.BytesIO()
    # `lossless=True`, not `quality=100`: q=100 is still the lossy coder, so the pixels this module
    # just drew would be re-derived approximately before `encode_webp` ever saw them. The ladder
    # inside `encode_webp` is where the lossy step belongs and the only place it happens.
    image.save(buffer, "WEBP", lossless=True, method=0)
    return encode_webp(buffer.getvalue())
```

- [ ] `poetry run pytest tests/media/test_redact.py -q -W error` — GREEN. If `test_two_photographs_that_differ_only_under_the_mask_produce_identical_bytes` fails, there are exactly two causes and neither is answered by weakening the assertion. Check the intermediate save is `lossless=True` (a `quality=100` hand-off is still the lossy coder). Then check `_display` is `lossless=True` too: with a lossy source the two inputs differ OUTSIDE the mask through intra-prediction, and the derivatives then differ for a reason that has nothing to do with what the fill covers. Both were measured before this file was written — lossy sources give differing derivatives, lossless ones give 64 844 identical bytes. **Do not weaken the assertion.**

- [ ] **Step 5: the task's gates**

```bash
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
```

- [ ] **Step 6: commit**

```
feat(privacy): region aggregation, and opaque irreversible redaction

Directive 5: irreversible, opaque redaction rather than blur, with regions
expanded enough that surrounding pixels cannot reconstruct what was
covered, and without cropping away useful content. app/media/redact.py
fills a constant navy over every polygon and re-encodes through
app/media/encode.py's own ladder, so the derivative is normalised and
metadata-free exactly as display is and this module owns no encoding rules.

The irreversibility claim is asserted rather than argued: two photographs
differing ONLY under the mask encode to identical bytes, because a constant
carries no information about what it covers. A blur, a pixelation and a
mosaic all fail that test, which is why none is used.

app/privacy/aggregate.py unions the OCR-matched lines, the regex hits, the
2D symbols and the vision boxes; pads text by a quarter of its shorter side
and a vision box by a fifth per side (its coordinates are approximate);
merges anything within 8 px so a sign is one block rather than a picket
fence that leaks its letter count; and clamps to the image. It is
deterministic, which is what lets a regeneration reproduce a derivative the
seller already confirmed. The in-place re-run replaces the auto set on an
unconfirmed row and unions it on a confirmed one -- never fewer regions
than the seller approved -- and a fresh region inside one they removed is
recorded and not filled.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `git add app/privacy/aggregate.py app/media/redact.py tests/privacy/test_aggregate.py tests/media/test_redact.py`

---

### Task P8: the Celery task chain — the claim, the backoff ladder, the in-place re-run and the sweeper

**Files:**
- Create: `app/tasks/media.py`, `tests/tasks/__init__.py`, `tests/tasks/test_media.py`
- Create: `scripts/reprocess_photos.py`, `tests/scripts/test_reprocess_photos.py`
- Create: `tests/api/test_import_surface.py` (the api holds no engine wheel — the run-time form of spec §C.5's "The api never imports the engines")
- Modify: `app/privacy/record.py` (`bump_attempt`, `sweep_candidates`, `enqueue_processing`'s eager branch), `app/tasks/celery_app.py`, `scripts/start.sh`, `tests/test_celery.py`, `tests/scripts/test_start_sh.sh`, `.github/workflows/quality.yml`
- Modify: `tests/e2e/api_under_test.py`, `tests/e2e/test_api_under_test.py`, `frontend/tests/targets.ts`, `frontend/tests/targets.test.ts`

**Interfaces:**
- Consumes: `record.{read,claim,record_scan,record_derivative,mark_ready,fail,exhaust,advance_in_place,flag_stale,READY_STATES,ERROR_STATES,MAX_ATTEMPTS,BACKOFF,LOST_AFTER}`; `ocr.read_text`; `barcodes.read_symbols`; `identity.matches`; `vision.analyse`; `aggregate.{regions_for,fillable,union_auto}`; `redact.fill_regions`; `app/privacy.{redacted_key,PROCESSING_VERSION}`; `app/api/listings.drop_list_cache`; `ObjectStore.from_settings`.
- Produces, extending `app/privacy/record.py`:
  - `bump_attempt(conn, asset_id: UUID, *, code: str) -> int` — an in-place re-run's failure: the attempt and the reason code, **without** leaving the ready state, so the current derivative goes on being served.
  - `sweep_candidates(conn) -> dict[str, list[UUID]]` — the six rules' subjects, keyed `lost`, `unstarted`, `retry`, `reprocess`, `version`, `flagged`.
  - `enqueue_processing`'s eager branch (controller amendment **A-IDP-2**, Step 6) — the only place in `app/` that names `app.tasks.media`, unreachable outside `ENVIRONMENT=test`.
- Produces, `app/tasks/media.py` (beyond the two entry points): `_fetch(store, key) -> bytes | None` and `_store_object(store, key, body) -> bool` — the two guards that make the "does not raise" contract true, because `ObjectStore.get` re-raises every `ClientError` that is not a 404 and `ObjectStore.put` catches nothing.
- Produces, `app/tasks/media.py`:
  - `process_photo(asset_id: str, version: int) -> dict[str, object]` and `process_photo_task`
  - `sweep() -> dict[str, object]` and `sweep_task`
  - Neither ever raises: every outcome is a state write plus a returned summary — the `_NotReady`/`_refuse` shape `app/tasks/census.py` established.
- Produces, `scripts/reprocess_photos.py`: `main(argv: Sequence[str] | None = None) -> int`, flags `--listing <uuid>` and `--all-stale`.

- [ ] **Step 1: RED — idempotency, the ladder, and the sweeper**

Create `tests/tasks/test_media.py`:

```python
"""`media.process_photo` and `media.sweep` (spec 2026-09-09 C.5, E).

Directive 19: privacy processing failures fail CLOSED. Nothing in this module ever falls back to
the original, and nothing raises: a task that raised would leave the message unacked, the row
PROCESSING, and an operator with a traceback instead of a state -- which is exactly the shape
`app/tasks/census.py` already refuses.

Every case runs with the stub engines and a moto bucket. No model, no binary, no network."""
from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg2
import pytest
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image

from app.privacy import display_key, record, redacted_key
from app.tasks import media
from tests.privacy.conftest import make_listing, make_row


def _raises(exc: BaseException) -> Any:
    """A stand-in that raises whatever it was given, for any arguments. A lambda with a `throw`
    generator expression reads worse and hides which exception is being planted."""
    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise exc
    return boom


@pytest.fixture(autouse=True)
def _engines(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in ("ocr", "barcodes"):
        monkeypatch.setattr(f"app.privacy.{module}.settings.privacy_engine_module", "tests.e2e.stub_engines")
        monkeypatch.setattr(f"app.privacy.{module}._LOADED", None)
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", None)


def _photo_bytes(w: int = 1200, h: int = 900) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (w, h), (240, 240, 240)).save(buffer, "WEBP", quality=80, method=0)
    return buffer.getvalue()


def _seeded(conn: Any, store: Any, **kwargs: Any) -> tuple[UUID, UUID]:
    asset_id, listing_id = make_row(conn, **kwargs)
    store.put(display_key(listing_id, asset_id), _photo_bytes(), "image/webp")
    store.put(f"listings/{listing_id}/photos/{asset_id}/original.jpg", _photo_bytes(), "image/jpeg")
    return asset_id, listing_id


def test_a_photograph_runs_all_the_way_to_ready_and_writes_its_derivative(conn: Any, store: Any) -> None:
    asset_id, listing_id = _seeded(conn, store)
    assert media.process_photo(str(asset_id), 1)["result"] == "ready"
    row = record.read(conn, asset_id)
    assert row.processing_status == "READY_FOR_REVIEW"
    assert row.redacted_storage_key == redacted_key(listing_id, asset_id)
    assert row.redacted_sha256 and store.get(row.redacted_storage_key) is not None
    assert row.buyer_visible is False                       # NOT_SHOW: only `confirm` makes it visible
    assert row.redaction_regions and row.redaction_regions[0]["source"] == "auto"


def test_under_show_the_photograph_is_buyer_visible_the_moment_it_is_ready(conn: Any, store: Any) -> None:
    """Directive 8: "Selecting SHOW does NOT mean: skip scanning." The same pipeline runs, the
    derivative exists though it is not served, and switching to NOT_SHOW is then instant."""
    listing_id = make_listing(conn, "idp-show", visibility="SHOW")
    asset_id, _ = _seeded(conn, store, listing_id=listing_id)
    media.process_photo(str(asset_id), 1)
    row = record.read(conn, asset_id)
    assert row.buyer_visible is True and row.redacted_storage_key is not None


def test_a_duplicate_message_writes_nothing(conn: Any, store: Any) -> None:
    asset_id, _ = _seeded(conn, store)
    media.process_photo(str(asset_id), 1)
    before = record.read(conn, asset_id)
    assert media.process_photo(str(asset_id), 1)["result"] == "already_processed"
    assert record.read(conn, asset_id) == before


def test_a_message_that_finds_a_run_in_progress_returns_and_writes_nothing(conn: Any, store: Any) -> None:
    """`reject_on_worker_lost` redelivers the message of a killed child. The redelivered run finds
    the row PROCESSING with a recent `updated_at`, and the sweeper -- not this run -- finishes it."""
    asset_id, _ = _seeded(conn, store, processing_status="PROCESSING", attempts=1)
    assert media.process_photo(str(asset_id), 1)["result"] == "in_progress"
    assert record.read(conn, asset_id).processing_status == "PROCESSING"


def test_a_missing_row_is_a_summary_and_never_an_exception(conn: Any, store: Any) -> None:
    assert media.process_photo("44444444-4444-4444-8444-444444444444", 1)["result"] == "gone"


@pytest.mark.parametrize(("failure", "state", "code"), [
    ("undecodable", "PROCESSING_FAILED", "UNDECODABLE"),
    ("ocr", "PROCESSING_FAILED", "OCR_ERROR"),
    ("vision", "PROCESSING_FAILED", "VISION_REFUSED"),
    ("encode", "REDACTION_FAILED", "ENCODE_TOO_LARGE"),
])
def test_each_failure_class_writes_its_own_state_and_re_enqueues_with_the_ladder(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch, failure: str, state: str, code: str
) -> None:
    scheduled: list[dict[str, Any]] = []
    monkeypatch.setattr(media.process_photo_task, "apply_async",
                        lambda args, countdown: scheduled.append({"args": args, "countdown": countdown}))
    asset_id, listing_id = _seeded(conn, store)
    if failure == "undecodable":
        store.put(display_key(listing_id, asset_id), b"not an image", "image/webp")
    elif failure == "ocr":
        monkeypatch.setattr("app.tasks.media.ocr.read_text", _raises(media.ocr.OcrError("OCR_ERROR")))
    elif failure == "vision":
        monkeypatch.setattr("app.tasks.media.vision.analyse",
                            lambda *a, **k: {"status": "failed", "code": "VISION_REFUSED"})
    else:
        monkeypatch.setattr("app.tasks.media.redact.fill_regions", lambda display, polygons: None)

    for attempt, delay in enumerate(record.BACKOFF, start=1):
        media.process_photo(str(asset_id), 1)
        row = record.read(conn, asset_id)
        if attempt < record.MAX_ATTEMPTS:
            assert (row.processing_status, row.attempts) == (state, attempt)
            assert scheduled[-1]["countdown"] == delay
        else:
            # The third failure EXHAUSTS rather than re-enqueueing, which is why only the ladder's
            # first two rungs are ever spent -- `delay` on this pass is 600 and nothing scheduled it.
            assert row.processing_status == "REVIEW_REQUIRED" and len(scheduled) == record.MAX_ATTEMPTS - 1
            assert [s["countdown"] for s in scheduled] == list(record.BACKOFF[:record.MAX_ATTEMPTS - 1])
    assert record.read(conn, asset_id).buyer_visible is False
    assert record.read(conn, asset_id).redacted_storage_key is None or state == "REDACTION_FAILED"


def test_no_key_is_not_a_failure(conn: Any, store: Any) -> None:
    """The distinction P6 draws, end to end: the pipeline completes and the record says so."""
    asset_id, _ = _seeded(conn, store)
    media.process_photo(str(asset_id), 1)
    with conn.cursor() as cur:
        cur.execute("SELECT vision ->> 'status' FROM listing_asset_privacy WHERE asset_id = %s", (asset_id,))
        assert cur.fetchone()[0] == "unavailable"
    assert record.read(conn, asset_id).processing_status == "READY_FOR_REVIEW"


def test_a_stale_enqueue_below_the_current_version_does_nothing(conn: Any, store: Any) -> None:
    asset_id, _ = _seeded(conn, store, processing_version=3)
    assert media.process_photo(str(asset_id), 1)["result"] == "already_processed"


def test_an_in_place_re_run_replaces_the_derivative_without_leaving_the_ready_state(
    conn: Any, store: Any
) -> None:
    """D-IDP-16: a processing-version bump must darken no listing. The row keeps its state,
    `buyer_visible` and confirmation throughout; the OLD derivative is served under its old hash
    until the one UPDATE at the end."""
    asset_id, listing_id = _seeded(conn, store, processing_status="SELLER_CONFIRMED", confirmed=True,
                                   buyer_visible=True, reprocess_reason="VERSION")
    store.put(redacted_key(listing_id, asset_id), b"the old derivative", "image/webp")
    assert media.process_photo(str(asset_id), 1)["result"] == "rerun"
    row = record.read(conn, asset_id)
    assert row.processing_status == "SELLER_CONFIRMED" and row.buyer_visible is True
    assert row.seller_confirmed and row.confirmed_sha256 == row.redacted_sha256
    assert row.reprocess_reason is None and store.get(redacted_key(listing_id, asset_id)) != b"the old derivative"


def test_a_third_failed_in_place_re_run_ends_in_review_required_with_a_null_slot(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one way a published listing comes to hold a non-ready photograph. Fail closed: the slot
    is null to buyers, never the original and never display."""
    monkeypatch.setattr(media.process_photo_task, "apply_async", lambda args, countdown: None)
    monkeypatch.setattr("app.tasks.media.redact.fill_regions", lambda display, polygons: None)
    asset_id, _ = _seeded(conn, store, processing_status="PUBLISHED", confirmed=True,
                          buyer_visible=True, reprocess_reason="VERSION")
    for _ in range(record.MAX_ATTEMPTS):
        media.process_photo(str(asset_id), 1)
    row = record.read(conn, asset_id)
    assert row.processing_status == "REVIEW_REQUIRED" and row.buyer_visible is False
    assert row.seller_confirmed is False


def test_the_sweeper_applies_its_six_rules_and_enqueues_each_subject_once(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One UPDATE or one enqueue per rule (spec C.5). Every window is set by moving `updated_at`
    backwards, which is why every writer in `record.py` sets it explicitly."""
    sent: list[str] = []
    monkeypatch.setattr(media.process_photo_task, "apply_async",
                        lambda args, countdown=None: sent.append(args[0]))
    old = datetime.now(UTC) - timedelta(minutes=30)
    subjects = {
        "unstarted": _seeded(conn, store, processing_status="UPLOADED")[0],
        "lost": _seeded(conn, store, processing_status="PROCESSING", attempts=1)[0],
        "retry": _seeded(conn, store, processing_status="PROCESSING_FAILED", attempts=1)[0],
        "reprocess": _seeded(conn, store, processing_status="REPROCESS_REQUIRED", attempts=1)[0],
        "version": _seeded(conn, store, processing_status="READY_FOR_REVIEW", processing_version=0)[0],
        "flagged": _seeded(conn, store, processing_status="READY_FOR_REVIEW", reprocess_reason="OPERATOR")[0],
    }
    fresh = _seeded(conn, store, processing_status="PROCESSING", attempts=1)[0]   # not yet lost
    with conn.cursor() as cur:
        cur.execute("UPDATE listing_asset_privacy SET updated_at = %s WHERE asset_id = ANY(%s)",
                    (old, list(subjects.values())))
    summary = media.sweep()
    assert sorted(sent) == sorted(str(a) for a in subjects.values())
    assert str(fresh) not in sent
    assert record.read(conn, subjects["lost"]).processing_status == "REPROCESS_REQUIRED"
    assert record.read(conn, subjects["lost"]).reprocess_reason is None      # a state, not a flag
    assert record.read(conn, subjects["version"]).reprocess_reason == "VERSION"
    assert record.read(conn, subjects["version"]).processing_status == "READY_FOR_REVIEW"
    assert summary["enqueued"] == len(subjects)


@pytest.mark.parametrize(("broken", "code"), [
    ("display_object", "DISPLAY_MISSING"),
    ("display_read", "DISPLAY_MISSING"),
    ("ocr_import", "OCR_UNAVAILABLE"),
    ("barcode_import", "BARCODE_UNAVAILABLE"),
    ("barcode_run", "BARCODE_ERROR"),
    ("derivative_write", "STORAGE_ERROR"),
])
def test_every_remaining_failure_class_records_its_own_reason_code(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch, broken: str, code: str
) -> None:
    """The rest of directive 19's fail-closed surface, one case per branch, because
    `--cov-branch --cov-fail-under=100` counts them and because each is a DIFFERENT sentence in
    `docs/RUNBOOK-image-privacy.md`. Two of them exist only because `ObjectStore` re-raises: `get`
    passes on every `ClientError` that is not a 404, and `put` catches nothing at all."""
    monkeypatch.setattr(media.process_photo_task, "apply_async", lambda args, countdown: None)
    asset_id, listing_id = _seeded(conn, store)
    if broken == "display_object":
        store.delete(display_key(listing_id, asset_id))
    elif broken == "display_read":
        monkeypatch.setattr("app.tasks.media.ObjectStore.get", _raises(ClientError(
            {"Error": {"Code": "InternalError"}}, "GetObject")))
    elif broken == "ocr_import":
        monkeypatch.setattr("app.tasks.media.ocr.read_text",
                            _raises(media.ocr.OcrUnavailable("OCR_UNAVAILABLE")))
    elif broken == "barcode_import":
        monkeypatch.setattr("app.tasks.media.barcodes.read_symbols",
                            _raises(media.barcodes.BarcodeUnavailable("BARCODE_UNAVAILABLE")))
    elif broken == "barcode_run":
        monkeypatch.setattr("app.tasks.media.barcodes.read_symbols",
                            _raises(media.barcodes.BarcodeError("BARCODE_ERROR")))
    else:
        monkeypatch.setattr("app.tasks.media.ObjectStore.put", _raises(BotoCoreError()))
    media.process_photo(str(asset_id), 1)
    row = record.read(conn, asset_id)
    assert row.last_error == code
    assert row.processing_status == ("REDACTION_FAILED" if code == "STORAGE_ERROR" else "PROCESSING_FAILED")
    assert row.buyer_visible is False


def test_an_unconfigured_bucket_leaves_the_row_where_it_is(conn: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Not a per-photograph failure: `S3_*` is unset for the whole worker (which is every deployed
    service today, spec A.2). Writing PROCESSING_FAILED on every row of every listing would spend
    three attempts on an operator's configuration mistake."""
    monkeypatch.setattr("app.tasks.media.ObjectStore.from_settings", lambda settings: None)
    asset_id, _ = make_row(conn, processing_status="UPLOADED")
    assert media.process_photo(str(asset_id), 1)["result"] == "storage_unavailable"
    assert record.read(conn, asset_id).processing_status == "UPLOADED"


def test_an_asset_id_that_is_not_a_uuid_is_a_summary(conn: Any) -> None:
    """A hand-published message, or one from a version of the api that spelled the argument
    differently. `UUID(...)` raising inside a Celery task would be a traceback per redelivery."""
    assert media.process_photo("not-a-uuid", 1)["result"] == "gone"


def test_a_database_that_will_not_connect_is_a_summary_from_both_entry_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one failure that happens before there is any row to write a state onto. The reason is
    the exception CLASS and never its text, which can carry the DSN."""
    monkeypatch.setattr("app.tasks.media.psycopg2.connect", _raises(psycopg2.OperationalError("nope")))
    assert media.process_photo(str(uuid4()), 1)["result"] == "database_unavailable"
    assert media.sweep() == {"enqueued": 0, "error": "database_unavailable"}


def test_a_failed_row_that_has_spent_its_attempts_is_not_swept(conn: Any, store: Any,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule (3) is `attempts < 3`. REVIEW_REQUIRED is the seller's to leave, through Try again."""
    sent: list[str] = []
    monkeypatch.setattr(media.process_photo_task, "apply_async",
                        lambda args, countdown=None: sent.append(args[0]))
    spent, _ = _seeded(conn, store, processing_status="PROCESSING_FAILED", attempts=3)
    done, _ = _seeded(conn, store, processing_status="REVIEW_REQUIRED", attempts=3)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing_asset_privacy SET updated_at = %s WHERE asset_id = ANY(%s)",
                    (datetime.now(UTC) - timedelta(hours=1), [spent, done]))
    media.sweep()
    assert sent == []
```

- [ ] `poetry run pytest tests/tasks/test_media.py -q -W error` — RED: `ModuleNotFoundError: No module named 'app.tasks.media'`.

- [ ] **Step 2: GREEN — `record.bump_attempt` and `record.sweep_candidates`**

Append to `app/privacy/record.py`:

```python
def bump_attempt(conn: Any, asset_id: UUID, *, code: str) -> int:
    """An in-place re-run's failure: the attempt and the reason, WITHOUT leaving the ready state.

    The point of the flag design (D-IDP-16) is that a ready row goes on serving the derivative it
    already has while a re-run is pending. Writing PROCESSING_FAILED here would trip
    `lap_visible_ready_ck` and blank the slot for a reason the buyer should never see."""
    with conn.cursor() as cur:
        cur.execute("UPDATE listing_asset_privacy SET attempts = attempts + 1, last_error = %s,"
                    " updated_at = now() WHERE asset_id = %s RETURNING attempts", (code, asset_id))
        return int(cur.fetchone()[0])


def sweep_candidates(conn: Any) -> dict[str, list[UUID]]:
    """The six rules' subjects, in one round trip each (spec C.5).

    (1) UPLOADED older than 2 min -- the api's enqueue was lost.
    (2) PROCESSING older than 6 min -- a lost child; becomes REPROCESS_REQUIRED with TASK_LOST.
    (3) *_FAILED with attempts < 3 older than 12 min -- the longest backoff plus two; a re-enqueue
        was lost, or a mask route's regeneration failed and that route enqueues nothing itself.
    (4) REPROCESS_REQUIRED older than 6 min.
    (5) a ready row below PROCESSING_VERSION with no flag -- flagged VERSION, state untouched.
    (6) a flagged ready row older than 6 min."""
    from app.privacy import PROCESSING_VERSION  # noqa: PLC0415  (avoids a package-level cycle)

    windows = {
        "unstarted": ("processing_status = 'UPLOADED'", "2 minutes"),
        "lost": ("processing_status = 'PROCESSING'", LOST_AFTER),
        "retry": (f"processing_status = ANY(ARRAY['PROCESSING_FAILED','REDACTION_FAILED'])"
                  f" AND attempts < {MAX_ATTEMPTS}", "12 minutes"),
        "reprocess": ("processing_status = 'REPROCESS_REQUIRED'", LOST_AFTER),
        "flagged": (f"processing_status = ANY(ARRAY{list(READY_STATES)}) AND reprocess_reason IS NOT NULL",
                    LOST_AFTER),
    }
    found: dict[str, list[UUID]] = {}
    with conn.cursor() as cur:
        for name, (predicate, window) in windows.items():
            cur.execute(f"SELECT asset_id FROM listing_asset_privacy WHERE {predicate}"
                        f" AND updated_at < now() - interval '{window}'")
            found[name] = [UUID(str(r[0])) for r in cur.fetchall()]
        cur.execute("UPDATE listing_asset_privacy SET reprocess_reason = 'VERSION',"
                    " reprocess_requested_at = now(), updated_at = now()"
                    " WHERE processing_status = ANY(%s) AND reprocess_reason IS NULL"
                    "   AND processing_version < %s RETURNING asset_id",
                    (list(READY_STATES), PROCESSING_VERSION))
        found["version"] = [UUID(str(r[0])) for r in cur.fetchall()]
    return found
```

- [ ] **Step 3: GREEN — `app/tasks/media.py`**

```python
"""The image-identifiability pipeline's two Celery entry points (spec 2026-09-09 C.5, E).

Registered by CALLING `celery_app.task(...)` rather than by decorating, exactly as
`app/mail/tasks.py` and `app/tasks/census.py` do and for the same reason: celery ships no type
information, so a decorator on a typed function is untyped and mypy --strict refuses it, and a
suppression is not the fix. The functions stay ordinary, fully typed and directly callable -- which
is what the tests call.

NEITHER FUNCTION RAISES FOR ANY FAILURE THIS PIPELINE CAN PRODUCE. Every one of them is a state
write plus a returned summary, the `_NotReady`/`_refuse` shape census established
(`app/tasks/census.py:62-66`, `:118-124`): a database that will not connect, an object that is not
there, a bucket that answers an error, an engine that will not import, an engine that raises on this
photograph, a vision refusal, an encode that will not fit the ladder. A task that raised would leave
a traceback where an operator needs a state.

Two things are deliberately NOT swallowed, and neither is a failure this pipeline produces. An
exception outside that set escapes: `acks_late` acks a failed task, so the message is not
redelivered for ever, the row is left in `PROCESSING`, and `media.sweep`'s rule (2) recovers it
within six minutes — a recorded, bounded outcome, and better than silently converting an unknown
error into "done". And `store.get`/`store.put` failures are converted at the two helpers below
rather than at the entry point, so the state written names the STAGE that failed.

Retry is not `Task.retry()` (which raises and needs a bound task) but a fresh `apply_async` with a
countdown from the ladder, after the failure has been recorded. The ladder is `record.BACKOFF`
`(30, 120, 600)` and the bound is `record.MAX_ATTEMPTS = 3`, so the rungs actually spent are 30 s
then 2 min; the third failure exhausts to `REVIEW_REQUIRED` instead of re-enqueueing, and the
600-second rung is headroom for a raised bound (`test_record.py` pins that).

The api never imports this module -- it publishes `media.process_photo` by name -- so the OCR,
barcode and vision engines are importable in the worker process alone."""
from __future__ import annotations

import io
import logging
from typing import Any
from uuid import UUID

import psycopg2
import psycopg2.extensions
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image, UnidentifiedImageError

from app.api.listings import drop_list_cache
from app.cache import sync_redis
from app.config import settings
from app.db import sync_dsn
from app.media import redact
from app.media.encode import MAX_IMAGE_PIXELS
from app.privacy import PROCESSING_VERSION, aggregate, barcodes, identity, ocr, record, redacted_key, vision
from app.storage import ObjectStore
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

#: The listing facts the matcher and the prompt read, at run time and never from the privacy row.
_FACTS = """
SELECT l.name, l.street, l.city, l.state, l.zip, l.phone, l.slug, l.facility, l.services, l.hours,
       l.identifiable_content_visibility, a.email
  FROM listing l LEFT JOIN account a ON a.id = l.seller_id
 WHERE l.id = %s
"""


def _conn() -> psycopg2.extensions.connection:
    connection = psycopg2.connect(sync_dsn())
    connection.autocommit = True
    return connection


def _fetch(store: ObjectStore, key: str) -> bytes | None:
    """One object, or None for a missing key AND for a bucket that answered an error.

    `ObjectStore.get` returns None only for a 404 and RE-RAISES every other `ClientError`
    (`app/storage.py:66-72`), so an outage would otherwise leave this module -- whose contract is
    that it does not raise -- propagating a boto exception out of a Celery task. The caller's
    answer is the same either way and it is fail-closed: no derivative, a recorded reason, a retry.
    This is `app/api/listings.py::_asset_bytes`' own rule, in the worker."""
    try:
        return store.get(key)
    except (BotoCoreError, ClientError) as exc:
        log.error("[media] object read failed: %s", type(exc).__name__)
        return None


def _store_object(store: ObjectStore, key: str, body: bytes) -> bool:
    """The derivative, put; False when the bucket refused it. `ObjectStore.put` catches nothing."""
    try:
        store.put(key, body, "image/webp")
        return True
    except (BotoCoreError, ClientError) as exc:
        log.error("[media] object write failed: %s", type(exc).__name__)
        return False


def _facts(conn: Any, listing_id: UUID) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(_FACTS, (listing_id,))
        columns = [d[0] for d in cur.description]
        return dict(zip(columns, cur.fetchone(), strict=True))


def _summary(asset_id: str, result: str, **extra: Any) -> dict[str, object]:
    return {"asset": asset_id, "result": result, **extra}


def _retry_or_exhaust(conn: Any, asset_id: UUID, *, state: str, code: str, version: int) -> dict[str, object]:
    """The ladder. `record.fail` has already counted this attempt at the claim."""
    attempts = record.fail(conn, asset_id, state=state, code=code)
    if attempts < record.MAX_ATTEMPTS:
        delay = record.BACKOFF[attempts - 1]
        process_photo_task.apply_async(args=(str(asset_id), version), countdown=delay)
        return _summary(str(asset_id), state.lower(), error=code, retry_in=delay)
    record.exhaust(conn, asset_id, code=code)
    return _summary(str(asset_id), "review_required", error=code)


def _scan(conn: Any, row: record.PrivacyRow, store: ObjectStore) -> tuple[dict[str, Any], str | None]:
    """Steps 1-5. `(scan, failure_code)` -- exactly one of the two is meaningful."""
    display = _fetch(store, row.display_storage_key or "")
    if display is None:
        return {}, "DISPLAY_MISSING"
    try:
        image = Image.open(io.BytesIO(display)).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return {}, "UNDECODABLE"
    try:
        lines = ocr.read_text(image)
    except ocr.OcrUnavailable:
        return {}, "OCR_UNAVAILABLE"
    except ocr.OcrError:
        return {}, "OCR_ERROR"
    try:
        symbols = list(barcodes.read_symbols(image))
        original = _fetch(store, row.original_storage_key)
        if original is not None:
            # A fill cannot hide under an OCR region: the original is read once, for symbols only.
            with Image.open(io.BytesIO(original)) as source:
                symbols += barcodes.read_symbols(source.convert("RGB"))
    except barcodes.BarcodeUnavailable:
        return {}, "BARCODE_UNAVAILABLE"
    except (barcodes.BarcodeError, UnidentifiedImageError, OSError, ValueError):
        return {}, "BARCODE_ERROR"

    facts = _facts(conn, row.listing_id)
    found = identity.matches([line.text for line in lines], facts, facts["email"])
    seen = vision.analyse(display, name=facts["name"], city=facts["city"], state=facts["state"])
    if seen["status"] == "failed":
        return {}, str(seen["code"])
    detected, regions = aggregate.regions_for(lines=lines, matches=found, symbols=symbols,
                                              vision=seen, size=image.size)
    return {
        "display": display,
        "visibility": facts["identifiable_content_visibility"],
        "ocr": {"engine": ocr.ENGINE, "size": list(image.size),
                "lines": [{"text": l.text, "confidence": l.confidence,
                           "quad": [[x, y] for x, y in l.quad]} for l in lines],
                "barcodes": [{"format": s.fmt, "payload_kind": s.payload_kind,
                              "quad": [[x, y] for x, y in s.quad]} for s in symbols]},
        "identity_matches": [{"field": m.field, "line": m.line, "method": m.method, "score": m.score}
                             for m in found],
        "vision": seen,
        "detected_regions": detected,
        "redaction_regions": regions,
    }, None


def _run(conn: Any, row: record.PrivacyRow, store: ObjectStore, version: int) -> dict[str, object]:
    scan, failure = _scan(conn, row, store)
    if failure is not None:
        return _retry_or_exhaust(conn, row.asset_id, state="PROCESSING_FAILED", code=failure, version=version)
    record.record_scan(conn, row.asset_id, ocr=scan["ocr"], identity_matches=scan["identity_matches"],
                       vision=scan["vision"], detected_regions=scan["detected_regions"])
    filled = redact.fill_regions(scan["display"], aggregate.fillable(scan["redaction_regions"]))
    if filled is None:
        return _retry_or_exhaust(conn, row.asset_id, state="REDACTION_FAILED", code="ENCODE_TOO_LARGE",
                                 version=version)
    body, digest = filled
    key = redacted_key(row.listing_id, row.asset_id)
    if not _store_object(store, key, body):
        # The derivative exists but could not be written. REDACTION_FAILED and a retry: the row must
        # never claim a key whose object is not there (`lap_ready_has_derivative_ck` would let it,
        # because the CHECK sees the column and not the bucket).
        return _retry_or_exhaust(conn, row.asset_id, state="REDACTION_FAILED", code="STORAGE_ERROR",
                                 version=version)
    record.record_derivative(conn, row.asset_id, key=key, sha256=digest, regions=scan["redaction_regions"])
    record.mark_ready(conn, row.asset_id, visible=scan["visibility"] == "SHOW", version=PROCESSING_VERSION)
    drop_list_cache(sync_redis())
    return _summary(str(row.asset_id), "ready", regions=len(scan["redaction_regions"]))


def _rerun(conn: Any, row: record.PrivacyRow, store: ObjectStore, version: int) -> dict[str, object]:
    """The in-place re-run of a flagged READY row (D-IDP-16).

    The row does not leave its state, so `buyer_visible` and the CHECK that guards it are untouched
    and the OLD derivative goes on being served under its old hash until the one UPDATE at the end.
    A failure counts an attempt WITHOUT changing the state; the third moves the row to
    REVIEW_REQUIRED with the reset rule -- a fail-closed null slot, never the original."""
    scan, failure = _scan(conn, row, store)
    filled = None if failure is not None else redact.fill_regions(
        scan["display"], aggregate.fillable(aggregate.union_auto(row.redaction_regions,
                                                                 scan["redaction_regions"],
                                                                 confirmed=row.seller_confirmed)))
    if filled is None:
        code = failure or "ENCODE_TOO_LARGE"
        attempts = record.bump_attempt(conn, row.asset_id, code=code)
        if attempts < record.MAX_ATTEMPTS:
            process_photo_task.apply_async(args=(str(row.asset_id), version),
                                           countdown=record.BACKOFF[attempts - 1])
            return _summary(str(row.asset_id), "rerun_failed", error=code)
        record.exhaust(conn, row.asset_id, code=code)
        return _summary(str(row.asset_id), "review_required", error=code)
    body, digest = filled
    regions = aggregate.union_auto(row.redaction_regions, scan["redaction_regions"],
                                   confirmed=row.seller_confirmed)
    if digest != row.redacted_sha256:
        if not _store_object(store, redacted_key(row.listing_id, row.asset_id), body):
            # The OLD derivative is still on the bucket and still served: an in-place re-run that
            # cannot write counts an attempt and leaves everything else alone (D-IDP-16).
            attempts = record.bump_attempt(conn, row.asset_id, code="STORAGE_ERROR")
            if attempts < record.MAX_ATTEMPTS:
                process_photo_task.apply_async(args=(str(row.asset_id), version),
                                               countdown=record.BACKOFF[attempts - 1])
                return _summary(str(row.asset_id), "rerun_failed", error="STORAGE_ERROR")
            record.exhaust(conn, row.asset_id, code="STORAGE_ERROR")
            return _summary(str(row.asset_id), "review_required", error="STORAGE_ERROR")
        drop_list_cache(sync_redis())
    record.record_scan_in_place(conn, row.asset_id, ocr=scan["ocr"],
                                identity_matches=scan["identity_matches"], vision=scan["vision"],
                                detected_regions=scan["detected_regions"])
    record.advance_in_place(conn, row.asset_id, sha256=digest, version=PROCESSING_VERSION, regions=regions)
    return _summary(str(row.asset_id), "rerun", changed=digest != row.redacted_sha256)


def process_photo(asset_id: str, version: int) -> dict[str, object]:
    """One photograph, from UPLOADED (or a retry, or a flagged ready row) to its derivative."""
    try:
        conn = _conn()
    except psycopg2.Error as exc:
        # Before any row can be read there is nothing to write a state onto. The class name only --
        # a psycopg2 message can carry the DSN (A-C7 (7)'s rule, exit 3's own reason).
        log.error("[media] database unreachable: %s", type(exc).__name__)
        return _summary(asset_id, "database_unavailable")
    try:
        try:
            parsed = UUID(asset_id)
        except ValueError:
            return _summary(asset_id, "gone")
        row = record.read(conn, parsed)
        if row is None:
            return _summary(asset_id, "gone")
        store = ObjectStore.from_settings(settings)
        if store is None:
            # Not a per-photograph failure: the bucket is unconfigured for the whole worker. The
            # row is left where it is and the sweeper brings it back when the bucket returns.
            log.error("[media] object store not configured -- %s left in %s", asset_id, row.processing_status)
            return _summary(asset_id, "storage_unavailable")
        if row.processing_status in record.READY_STATES and row.reprocess_reason is not None:
            return _rerun(conn, row, store, version)
        claimed = record.claim(conn, parsed, version)
        if claimed is None:
            return _summary(asset_id, "in_progress" if row.processing_status == "PROCESSING"
                            else "already_processed")
        return _run(conn, claimed, store, version)
    finally:
        conn.close()


def sweep() -> dict[str, object]:
    """Six rules, every five minutes. Nothing here decides anything about a photograph -- it only
    puts rows the pipeline lost back on the queue (spec C.5). Like `process_photo`, it answers a
    database it cannot reach with a summary rather than a traceback: beat will call it again in
    five minutes and nothing has been lost."""
    try:
        conn = _conn()
    except psycopg2.Error as exc:
        log.error("[media] database unreachable: %s", type(exc).__name__)
        return {"enqueued": 0, "error": "database_unavailable"}
    try:
        found = record.sweep_candidates(conn)
        with conn.cursor() as cur:
            for asset_id in found["lost"]:
                cur.execute("UPDATE listing_asset_privacy SET processing_status = 'REPROCESS_REQUIRED',"
                            " last_error = 'TASK_LOST', updated_at = now() WHERE asset_id = %s", (asset_id,))
        subjects = sorted({a for group in found.values() for a in group})
        for asset_id in subjects:
            process_photo_task.apply_async(args=(str(asset_id), PROCESSING_VERSION), countdown=0)
        return {"enqueued": len(subjects), **{name: len(group) for name, group in found.items()}}
    finally:
        conn.close()


# Registered by CALLING `celery_app.task(...)`; see the module docstring. `acks_late` acks on
# return, so a retry is always a fresh message; `reject_on_worker_lost` redelivers the message of a
# child killed mid-run, and the redelivered run finds the row PROCESSING and writes nothing.
process_photo_task = celery_app.task(name="media.process_photo", acks_late=True, reject_on_worker_lost=True,
                                     time_limit=300, soft_time_limit=240)(process_photo)
sweep_task = celery_app.task(name="media.sweep", acks_late=True, reject_on_worker_lost=True,
                             time_limit=300, soft_time_limit=240)(sweep)
```

One more writer is needed for `_rerun` and is added beside `record_scan` in `app/privacy/record.py`:

```python
def record_scan_in_place(conn: Any, asset_id: UUID, *, ocr: dict[str, Any],
                         identity_matches: list[dict[str, Any]], vision: dict[str, Any],
                         detected_regions: list[dict[str, Any]]) -> None:
    """`record_scan` without the state change -- the in-place re-run's scan columns, written while
    the row stays in its ready state."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET ocr = %s::jsonb, identity_matches = %s::jsonb,"
            " vision = %s::jsonb, detected_regions = %s::jsonb, updated_at = now()"
            " WHERE asset_id = %s",
            (json.dumps(ocr), json.dumps(identity_matches), json.dumps(vision),
             json.dumps(detected_regions), asset_id),
        )
```

- [ ] `poetry run pytest tests/tasks/test_media.py -q -W error` — GREEN.

- [ ] **Step 4: RED then GREEN — the Celery wiring**

- [ ] `tests/test_celery.py` — widen the two pins in the same edit that changes `celery_app.py`:

```python
def test_the_media_queue_and_its_sweep_are_registered_and_scheduled() -> None:
    """Spec 2026-09-09 E. The set-equality assertions above are what stop a future edit wiping
    either sub-project's entries; these are this sub-project's rows in them.

    `app.tasks.media` is imported here for the reason this file's own docstring already gives of
    `app.mail.tasks` and `app.tasks.census`: "`include=[...]` only makes `celery worker`/`celery
    beat` import a module at start-up, never a bare `celery_app.tasks` access under pytest". Without
    the import the two lookups below raise `KeyError` and this case would be testing the import
    system rather than the wiring."""
    from app.tasks import media as MM   # importing the module is what registers them

    assert (MM.process_photo_task.name, MM.sweep_task.name) == ("media.process_photo", "media.sweep")
    assert {"media.process_photo", "media.sweep"} <= set(celery_app.tasks)
    assert "app.tasks.media" in celery_app.conf.include
    assert celery_app.conf.task_routes["media.*"] == {"queue": "media"}
    assert celery_app.conf.beat_schedule["media-sweep-5min"] == {"task": "media.sweep", "schedule": 300.0}
    for name in ("media.process_photo", "media.sweep"):
        task = celery_app.tasks[name]
        assert task.acks_late and task.reject_on_worker_lost
        assert (task.time_limit, task.soft_time_limit) == (300, 240)
    assert celery_app.conf.task_always_eager is False
```

and add `"media.process_photo"`, `"media.sweep"` to the registered-names set and `"media-sweep-5min"` to the beat set the existing assertions compare.

- [ ] `app/tasks/celery_app.py`:

```python
celery_app = Celery("practice_match", broker=settings.redis_url, backend=settings.redis_url,
                    include=["app.mail.tasks", "app.tasks.census", "app.tasks.media"])
```

and, after the Census `.update(...)` block and in the same idiom (A-C0 ¶2 — never a second `beat_schedule=` keyword):

```python
# The image-identifiability sweeper (spec 2026-09-09 C.5): six rules, every five minutes, each of
# them one UPDATE or one enqueue. It decides nothing about a photograph -- it puts back what the
# pipeline lost, which is what makes "no image may silently fall through" true across a worker
# restart, a killed child or a lost message.
celery_app.conf.beat_schedule.update({"media-sweep-5min": {"task": "media.sweep", "schedule": 300.0}})
# `media.*` on its own queue so a burst of fifty photographs cannot delay the minutely mail drain.
celery_app.conf.update(task_routes={"media.*": {"queue": "media"}},
                       task_always_eager=settings.celery_task_always_eager)
```

- [ ] `scripts/start.sh:52` — `--queues=celery,media` (one worker process consumes both), and the matching line in `tests/scripts/test_start_sh.sh`.
- [ ] `poetry run pytest tests/test_celery.py -q -W error && bash tests/scripts/test_start_sh.sh` — GREEN.

- [ ] **Step 5: RED then GREEN — the operator's script**

`tests/scripts/test_reprocess_photos.py` asserts: `--listing <uuid>` flags that listing's ready rows `OPERATOR` and enqueues each; `--all-stale` flags every ready row below `PROCESSING_VERSION`; neither flag is an exit 2 with a one-line message; a listing with no ready rows prints a count of zero and exits 0; nothing is printed but counts.

`scripts/reprocess_photos.py`:

```python
#!/usr/bin/env python3
"""Flag photographs for an in-place re-run, and enqueue them (spec 2026-09-09 C.5).

    ENVIRONMENT=qa poetry run python scripts/reprocess_photos.py --listing <uuid>
    ENVIRONMENT=qa poetry run python scripts/reprocess_photos.py --all-stale

Run inside the WORKER container: it publishes to the same broker the worker consumes. It marks
`reprocess_reason = 'OPERATOR'` and nothing else -- a marked ready row keeps its state and goes on
serving the derivative it has, so this is safe on a published listing (D-IDP-16).

The `app.*` imports are inside `main()` for the reason `scripts/bootstrap_admin.py` records:
`python scripts/reprocess_photos.py` puts `scripts/` on `sys.path`, not the repository root."""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(argv: Sequence[str] | None = None) -> int:
    from contextlib import closing

    from app.db import sync_conn
    from app.privacy import PROCESSING_VERSION, record

    parser = argparse.ArgumentParser(description="Flag photographs for an in-place privacy re-run.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--listing", type=UUID, help="every ready photograph of one listing")
    group.add_argument("--all-stale", action="store_true",
                       help=f"every ready photograph below processing version {PROCESSING_VERSION}")
    args = parser.parse_args(argv)

    with closing(sync_conn()) as conn, conn:
        if args.listing is not None:
            flagged = record.flag_stale(conn, listing_id=args.listing, reason="OPERATOR")
        else:
            with conn.cursor() as cur:
                cur.execute("UPDATE listing_asset_privacy SET reprocess_reason = 'OPERATOR',"
                            " reprocess_requested_at = now(), updated_at = now()"
                            " WHERE processing_status = ANY(%s) AND reprocess_reason IS NULL"
                            "   AND processing_version < %s RETURNING asset_id",
                            (list(record.READY_STATES), PROCESSING_VERSION))
                flagged = [UUID(str(r[0])) for r in cur.fetchall()]
    for asset_id in flagged:
        record.enqueue_processing(asset_id, PROCESSING_VERSION)
    print(f"[reprocess_photos] flagged and enqueued {len(flagged)} photograph(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] `.github/workflows/quality.yml:63` — append `scripts/reprocess_photos.py` to the strict-mypy list.
- [ ] `poetry run pytest tests/scripts/test_reprocess_photos.py tests/test_docs.py -q -W error` — GREEN.

- [ ] **Step 6: the Playwright execution model — controller amendment A-IDP-2**

> **The spec's §G execution model does not work as written, and this is the ruled correction.** §G says `CELERY_TASK_ALWAYS_EAGER=1` makes "the `apply_async` after the upload's commit run `process_photo` inline in the api process". The upload does not call `apply_async`: it calls `record.enqueue_processing`, which calls `celery_app.send_task`, and **`send_task` does not honour `task_always_eager`**. Verified against this repository's pinned celery (5.6.3, `celery/app/base.py:865-868`):
>
> ```python
> if conf.task_always_eager:  # pragma: no cover
>     warnings.warn(AlwaysEagerIgnored('task_always_eager has no effect on send_task'), stacklevel=2)
> ```
>
> (That `# pragma: no cover` is celery's own, quoted verbatim from the installed package. Global Constraint (e) forbids adding one to this repository's code, and this sub-project adds none.)
>
> So as written the launcher publishes to Redis, no worker consumes it, nothing ever reaches `READY_FOR_REVIEW`, and every Playwright assertion that depends on it (Step 6's journey, scenarios O/S/T/U, the Review pill) is unreachable. Worse, under the backend gate's `-W error` any pytest that sets eager and calls `enqueue_processing` turns that `AlwaysEagerIgnored` warning into an error.
>
> **Ruled (controller amendment A-IDP-2):** `enqueue_processing` gains an explicit eager branch, guarded by the setting `Settings` already refuses outside `ENVIRONMENT=test`. The alternative — starting a real worker inside the launcher — was rejected: it doubles the harness's moving parts, makes every Playwright assertion wait on a broker round trip, and gives the flakiest surface in the suite a second process to lose.
>
> **The substantive property survives and is now pinned rather than asserted in prose.** The rule was never "this function contains no import of `app.tasks.media`"; it is "no deployed api process imports an OCR, barcode or vision ENGINE". The import inside the branch is unreachable in every deployed environment, because `Settings._test_only_settings_are_test_only` refuses the value at boot outside `ENVIRONMENT=test` (Task P4). Step 6's last box pins that at run time instead of by reading.

- [ ] Amend `app/privacy/record.py::enqueue_processing`:

```python
def enqueue_processing(asset_id: UUID, version: int) -> None:
    """Publishes `media.process_photo`, AFTER the caller's transaction has committed.

    By NAME (`send_task`) in every deployed environment, so the api process never imports
    `app.tasks.media`, whose transitive imports are the OCR, barcode and vision adapters. The queue
    is named explicitly rather than left to `task_routes` so the routing is readable at the call
    site and does not change if a route is ever edited.

    The eager branch is the Playwright launcher's and nothing else's (controller amendment A-IDP-2,
    spec G). It exists because `send_task` IGNORES `task_always_eager` -- celery warns
    `AlwaysEagerIgnored` and publishes anyway -- so the eager model cannot be had by a setting on
    the line below; `apply_async` is the call form that honours it. `settings.celery_task_always_eager`
    is refused at boot by `Settings` in every environment but `test`, so the import is unreachable
    on QA and in production, and `tests/api/test_import_surface.py` proves the api process holds no
    engine module after `create_app()`.

    A failure to publish is NOT swallowed here -- the caller runs this after the commit and outside
    its own `except Refusal`, so a broker outage answers 500 while the row stays `UPLOADED` and
    `media.sweep`'s rule (1) enqueues it within two minutes (spec C.5)."""
    if settings.celery_task_always_eager:
        from app.tasks.media import process_photo_task  # noqa: PLC0415  (see the docstring)

        process_photo_task.apply_async(args=(str(asset_id), version), queue="media")
        return
    celery_app.send_task("media.process_photo", args=[str(asset_id), version], queue="media")
```

with `from app.config import settings` joining that module's imports.

- [ ] Two cases in `tests/tasks/test_media.py`:

```python
def test_the_eager_branch_runs_the_pipeline_inline_and_never_calls_send_task(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Controller amendment A-IDP-2. `send_task` ignores `task_always_eager` and warns
    `AlwaysEagerIgnored`, which `-W error` turns into a failure -- so the eager path must not reach
    it at all, and the assertion below is on the WARNING as much as on the state."""
    monkeypatch.setattr("app.privacy.record.settings.celery_task_always_eager", True)
    monkeypatch.setattr("app.tasks.media.celery_app.conf", media.celery_app.conf)
    media.celery_app.conf.task_always_eager = True
    monkeypatch.setattr("app.privacy.record.celery_app.send_task",
                        _raises(AssertionError("send_task must not be reached while eager")))
    asset_id, _ = _seeded(conn, store, processing_status="UPLOADED")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        record.enqueue_processing(asset_id, 1)
    assert record.read(conn, asset_id).processing_status == "READY_FOR_REVIEW"


def test_the_default_path_publishes_by_name_and_imports_no_task_module(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr("app.privacy.record.settings.celery_task_always_eager", False)
    monkeypatch.setattr("app.privacy.record.celery_app.send_task",
                        lambda name, **kw: sent.append((name, kw)))
    record.enqueue_processing(uuid4(), 1)
    assert sent == [("media.process_photo", {"args": [sent[0][1]["args"][0]], "queue": "media"})]
```

with `import warnings` at the top of the file. The second case's shape is deliberately awkward so the asset id is read back from the call rather than restated.

- [ ] The import-surface pin, `tests/api/test_import_surface.py` — the rule I7 asked for, stated as what it actually is:

```python
"""The api process imports no detection ENGINE (spec 2026-09-09 C.5's "The api never imports the
engines").

Not "no api module imports `app.tasks.media`" -- `app/privacy/aggregate.py` imports `Symbol` and
`Line` from the two adapter modules at module scope, so `app/api/seller_listings.py` importing
`aggregate` for P12's mask routes pulls `app.privacy.ocr` and `app.privacy.barcodes` into the api
process by design. That is fine and is not what the rule protects: the adapters load their engines
LAZILY, inside `_load` and `_Zxing.__init__`, so importing them costs nothing and reaches no wheel.
What must never happen is the api holding `rapidocr_onnxruntime`, `onnxruntime`, `zxingcpp` or
`anthropic`, which is what this asserts -- at run time, on the real object the app builds."""
from __future__ import annotations

import sys
from typing import Any

ENGINE_MODULES = ("rapidocr_onnxruntime", "onnxruntime", "zxingcpp", "anthropic")


def test_building_the_app_loads_no_engine_wheel(dist: Any) -> None:
    from app.main import create_app

    create_app(dist=dist)
    assert [name for name in ENGINE_MODULES if name in sys.modules] == []


def test_the_task_module_is_not_imported_by_building_the_app(dist: Any) -> None:
    """The eager branch (A-IDP-2) is the only importer, and it cannot run outside ENVIRONMENT=test."""
    from app.main import create_app

    create_app(dist=dist)
    assert "app.tasks.media" not in sys.modules
```

> This file must run in a fresh interpreter to mean anything, because another test that imported an engine first would satisfy `sys.modules` for it. Add `tests/api/test_import_surface.py` to the `-p no:randomly`-free part of the suite by giving it `pytestmark = pytest.mark.forked` **only if** `pytest-forked` is already a dev dependency; it is not on `main` at `073aab8`, so instead the two cases run as written and the plan records the limitation plainly: they prove the app's own import graph is clean **in the process order pytest happens to use**, and the stronger proof is the one-line command in the task's gates below, which runs the file alone.

- [ ] `tests/e2e/api_under_test.py` — export both settings, beside the ones it already sets:

```python
    # The privacy pipeline is worker-only, and the Playwright launcher starts no worker. Eager
    # Celery runs `process_photo` inline in the api process the moment the upload commits, with
    # deterministic stub engines, so the wizard's own journey reaches READY_FOR_REVIEW without a
    # broker. CELERY_TASK_ALWAYS_EAGER is read by `record.enqueue_processing`'s eager branch
    # (A-IDP-2) and by `apply_async` inside the retry ladder; both variables are refused by
    # `Settings` outside ENVIRONMENT=test (spec 2026-09-09 E).
    env.setdefault("CELERY_TASK_ALWAYS_EAGER", "1")
    env.setdefault("PRIVACY_ENGINE_MODULE", "tests.e2e.stub_engines")
```

- [ ] `tests/e2e/test_api_under_test.py` — pin both exports, and that the module sets `ENVIRONMENT=test`.
- [ ] `frontend/tests/targets.ts` — pass both into the api web server's environment under its existing "process env wins" rule; `frontend/tests/targets.test.ts` pins them.
- [ ] With eager Celery the `apply_async` in `_retry_or_exhaust` executes inline; Celery ignores `countdown` when eager, so a failing photograph recurses at most `MAX_ATTEMPTS` times and stops at `REVIEW_REQUIRED` — correct behaviour, bounded, and asserted by a launcher test.

- [ ] **Step 7: the task's gates**

```bash
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run mypy scripts/migrate.py scripts/bootstrap_admin.py scripts/seed_persona.py scripts/reset_rate_limits.py scripts/prepare_photos.py scripts/seed_listings.py scripts/census_load.py scripts/reprocess_photos.py --strict
poetry run pytest tests/api/test_import_surface.py -q -W error   # ALONE: a fresh interpreter is what makes sys.modules mean anything
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
bash tests/scripts/test_start_sh.sh
cd frontend && npx vitest run tests/targets.test.ts && cd ..
```

- [ ] **Step 8: commit**

```
feat(worker): media.process_photo and media.sweep -- the pipeline, its ladder and its sweeper

Directive 4's five steps run in the worker, on the media queue, behind an
atomic claim: one conditional UPDATE decides whether this message does the
work, so a duplicate, a redelivery and a late retry all write nothing.
Neither task raises for any failure this pipeline can produce -- every one
is a state write plus a summary, census's own shape. That needed two
guards the first cut did not have: ObjectStore.get re-raises every
ClientError that is not a 404 and ObjectStore.put catches nothing, so both
now go through helpers that record the stage that failed. A database that
will not connect is a summary from both entry points, named by exception
class and never by message, which can carry the DSN.

A retry is therefore a fresh apply_async rather than Task.retry. The
ladder constant is (30, 120, 600) but the bound is three attempts, so the
rungs actually spent are 30 s then 2 min and the third failure exhausts to
REVIEW_REQUIRED with the confirmation reset: a null slot for buyers, never
the original (directive 19). The 600-second rung is headroom for a raised
bound, and a test says so rather than a commit body describing a ladder
that never reaches its end.

A flagged ready row is re-run IN PLACE: it never leaves its state, its
current derivative goes on being served under its old hash, and one UPDATE
at the end advances the hash and clears the flag -- so a processing-version
bump darkens no published listing. On a confirmed row the fresh auto
regions are unioned with the confirmed ones, never replaced, so the new
derivative hides a superset of what the seller approved.

media.sweep runs every five minutes and applies six rules, each one UPDATE
or one enqueue: a lost enqueue, a lost child, a lost retry, a stuck
reprocess, a version bump and a flagged row. It decides nothing about a
photograph; it puts back what the pipeline lost.

scripts/reprocess_photos.py gives an operator the same flag by hand, and
joins CI's strict-mypy list.

The Playwright launcher runs the pipeline eagerly with stub engines, behind
two settings no deployed service may set. That needed a ruled correction to
the spec's G (controller amendment A-IDP-2): celery's send_task IGNORES
task_always_eager -- it warns AlwaysEagerIgnored and publishes anyway -- so
enqueue_processing gains an explicit eager branch that calls apply_async,
which does honour it. The branch imports app.tasks.media, and cannot run
outside ENVIRONMENT=test because Settings refuses the value at boot.
tests/api/test_import_surface.py pins the property that actually matters at
run time: after create_app() the api process holds no rapidocr_onnxruntime,
onnxruntime, zxingcpp or anthropic, and no app.tasks.media.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `git add app/tasks/media.py app/tasks/celery_app.py app/privacy/record.py scripts/reprocess_photos.py scripts/start.sh tests/tasks/__init__.py tests/tasks/test_media.py tests/api/test_import_surface.py tests/scripts/test_reprocess_photos.py tests/scripts/test_start_sh.sh tests/test_celery.py tests/e2e/api_under_test.py tests/e2e/test_api_under_test.py frontend/tests/targets.ts frontend/tests/targets.test.ts .github/workflows/quality.yml`

---

### Task P9: one resolver, every delivery path — and the owner and reviewer routes

**Files:**
- Create: `app/privacy/delivery.py`, `tests/privacy/test_delivery.py`, `tests/api/test_buyer_photo_delivery.py`
- Modify: `app/privacy/record.py` (`delivery_row` — the aggregate's object as a `PrivacyRow`)
- Modify: `app/api/listings.py` (`PHOTO_CACHE_CONTROL` `:85`, `_SELECT` `:88-95`, `serialise` `:291-299`, `_asset_bytes` → `_object_bytes` `:438-469`, `_published_photos` → `_published_photos_and_visibility` `:416-427`, `get_listing_photo` `:472-497`, new `seed_digests`, `_photo_urls`, `_privacy_for`)
- Modify: `app/api/seller_listings.py` (the owner bytes route; `photo_tiles`, `assets_for` and `serialise_draft`'s tiles — Step 6), `app/api/admin_listings.py` (the reviewer bytes route; the draft read's own tile prefix)
- Modify: `tests/api/test_listings.py` (`:227` header pin), `tests/api/test_listing_assets.py` (`:642`/`:643`), `tests/api/test_seller_listings.py`, `tests/api/test_admin_listings.py`, `tests/perf/test_api_latency.py`, `tests/perf/test_query_plans.py`, `tests/test_storage.py`, `tests/test_static.py`

**Interfaces:**
- Consumes: `record.PrivacyRow` (with its `display_storage_key`/`display_sha256` join), `app/privacy.original_key`.
- Produces, `app/privacy/delivery.py`:
  - `@dataclass(frozen=True) class Variant` with `key: str`, `sha256: str`, `from_disk: bool`
  - `buyer_variant(visibility: str, asset: PrivacyRow | None, entry: str, seed_sha: str | None = None) -> Variant | None`
  - `PHOTO_HEADERS: dict[str, str]` — `{"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff"}`
  - `OWNER_HEADERS: dict[str, str]` — `{"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"}`
  - `photo_url(listing_id: object, n: int, sha256: str) -> str` — `/api/listings/{id}/photos/{n}?v=<sha12>`
  - `owner_url(route_prefix: str, asset_id: object, sha256: str) -> str` — the seller's and the reviewer's tile URL; the prefix is the caller's, so one function serves both routes and there is one producer of the `?v=`
- Produces, `app/privacy/record.py`: `delivery_row(entry: str, listing_id: object, found: Mapping[str, Any]) -> PrivacyRow` — the list aggregate's JSON object as the row the resolver reads; the ONE place that does it, so `original_storage_key` gains no fourth module.
- Produces, `app/api/listings.py`: `seed_digests() -> dict[str, str]`, the `visible_photos` aggregate inside `_SELECT` (the spec's own name for it, §C.7 row 3), `photo_response(body, sha256, request) -> Response`, `_photo_urls(listing_id, photos, row) -> list[str | None]`, `_privacy_for(conn, listing_id, entry) -> PrivacyRow | None`, `_object_bytes(key) -> bytes | None`, `_published_photos_and_visibility(conn, listing_id) -> tuple[list[str | None], str] | None`.
- Produces, `app/api/seller_listings.py` (Step 6): `TILE_PILL`, `RETRYING`, `photo_tiles(row, assets, *, owner_route)`, `_tile_privacy`, `_mask_box`, `photo_variant_response`, `VARIANTS`, `ORIGINAL_MEDIA_TYPE`, `_fetch`.
- Produces, the two new routes and their guards `REQUIRE_MANAGE_OWN` (existing) and `REQUIRE_REVIEW` (existing) — no new permission.
- **Imports this task adds**, named here because a later task calling one of them must not have to guess where it came from: `app/privacy/record.py` gains `from collections.abc import Mapping` (for `delivery_row`); `app/api/listings.py` gains `from functools import lru_cache`, `from collections.abc import Mapping`, `from app.privacy import record`, `from app.privacy.delivery import PHOTO_HEADERS, buyer_variant, photo_url`; `app/api/seller_listings.py` gains `from collections.abc import Mapping`, `from app.media.encode import sha256_hex`, `from app.privacy import record`, `from app.privacy.delivery import OWNER_HEADERS, owner_url`.

> **One deviation from the spec, recorded.** §C.7 sketches `buyer_variant(visibility, asset, entry)`. A seed entry's `?v=` must be the inventory's sha256 (§C.7 row 12) and the resolver is pure, so the digest is a fourth argument with a `None` default rather than a hidden read. Same behaviour, one more parameter. `seed_digests()` lives in `app/api/listings.py` and not beside `seed_captions()` in `app/api/seller_listings.py`, because `seller_listings` imports from `listings` and the reverse would be a cycle.

- [ ] **Step 1: RED — the resolver, every cell**

Create `tests/privacy/test_delivery.py`:

```python
"""The one resolver (spec 2026-09-09 C.7; directive 9 and 12).

Directive 12: "Every buyer-facing image request must resolve the authoritative listing privacy
state." This function IS that resolution, and it is pure, so every cell of
(visibility x status x buyer_visible x key-present) is a unit test rather than an integration
argument. Its `None` is a 404 on the bytes route and a null slot in the JSON.

The three rules it can never break: never the original, never display under NOT_SHOW, and never a
fallback when something is missing."""
from __future__ import annotations

import dataclasses
import itertools
from typing import Any
from uuid import uuid4

import pytest

from app.privacy import record
from app.privacy.delivery import Variant, buyer_variant

STATUSES = ("UPLOADED", "PROCESSING", "SCANNED", "REDACTION_GENERATED", "READY_FOR_REVIEW",
            "SELLER_CONFIRMED", "PUBLISHED", "PROCESSING_FAILED", "REDACTION_FAILED",
            "REVIEW_REQUIRED", "REPROCESS_REQUIRED")
NOT_SHOW_OK = ("SELLER_CONFIRMED", "PUBLISHED")
SHOW_OK = ("READY_FOR_REVIEW", "SELLER_CONFIRMED", "PUBLISHED")


def _row(status: str, *, visible: bool, redacted: bool = True) -> record.PrivacyRow:
    asset_id, listing_id = uuid4(), uuid4()
    return record.PrivacyRow(
        asset_id=asset_id, listing_id=listing_id, processing_status=status, processing_version=1,
        attempts=0, original_storage_key=f"listings/{listing_id}/photos/{asset_id}/original.jpg",
        redacted_storage_key=f"listings/{listing_id}/photos/{asset_id}/redacted.webp" if redacted else None,
        redacted_sha256="b" * 64 if redacted else None, confirmed_sha256=None, seller_confirmed=False,
        buyer_visible=visible, redaction_regions=[], reprocess_reason=None, final_privacy_state=None,
        display_storage_key=f"listings/{listing_id}/photos/{asset_id}/display.webp",
        display_sha256="d" * 64)


@pytest.mark.parametrize(("visibility", "status", "visible", "redacted"),
                         itertools.product(("SHOW", "NOT_SHOW"), STATUSES, (True, False), (True, False)))
def test_every_cell_resolves_to_the_one_answer_the_policy_allows(
    visibility: str, status: str, visible: bool, redacted: bool
) -> None:
    row = _row(status, visible=visible, redacted=redacted)
    got = buyer_variant(visibility, row, str(row.asset_id))
    if not visible:
        assert got is None
        return
    if visibility == "NOT_SHOW":
        expected = Variant(row.redacted_storage_key, "b" * 64, False) if (status in NOT_SHOW_OK and redacted) else None
    else:
        expected = Variant(row.display_storage_key, "d" * 64, False) if status in SHOW_OK else None
    assert got == expected


def test_the_original_is_never_the_answer() -> None:
    for visibility in ("SHOW", "NOT_SHOW"):
        for status in STATUSES:
            for visible in (True, False):
                got = buyer_variant(visibility, _row(status, visible=visible), "x")
                assert got is None or "original" not in got.key


def test_display_is_never_the_answer_under_not_show() -> None:
    for status in STATUSES:
        got = buyer_variant("NOT_SHOW", _row(status, visible=True), "x")
        assert got is None or got.key.endswith("redacted.webp")


def test_a_photograph_with_no_privacy_row_is_nothing_to_a_buyer() -> None:
    """A seller asset whose row is somehow absent -- there is no such path, and if one appeared the
    answer is still a null slot rather than the bytes."""
    assert buyer_variant("NOT_SHOW", None, "3f2a…") is None
    assert buyer_variant("SHOW", None, "3f2a…") is None


def test_a_seed_path_entry_is_the_disk_file_under_show_and_nothing_under_not_show() -> None:
    """Spec C.10: a seed photograph has no asset row and no derivative, so NOT_SHOW has nothing it
    could honestly serve."""
    assert buyer_variant("SHOW", None, "round-rock/1.webp", "a" * 64) == Variant("round-rock/1.webp", "a" * 64, True)
    assert buyer_variant("NOT_SHOW", None, "round-rock/1.webp", "a" * 64) is None


def test_a_stale_flag_changes_nothing_the_buyer_sees() -> None:
    """The resolver never reads `reprocess_reason`: a stale redaction is still a redaction, and the
    in-place re-run replaces it under a new hash (D-IDP-16)."""
    row = _row("PUBLISHED", visible=True)
    # `dataclasses.replace`, not `_asdict()`: `PrivacyRow` is a frozen dataclass and not a
    # NamedTuple, so it has no `_asdict`, and `vars()` on a frozen instance is an implementation
    # detail. `replace` is the supported way and it type-checks under --strict.
    flagged = dataclasses.replace(row, reprocess_reason="VERSION")
    assert buyer_variant("NOT_SHOW", flagged, "x") == buyer_variant("NOT_SHOW", row, "x")
```

- [ ] `poetry run pytest tests/privacy/test_delivery.py -q -W error` — RED: `ModuleNotFoundError`.

- [ ] **Step 2: GREEN — `app/privacy/delivery.py`**

```python
"""What a buyer receives, decided per request from the authoritative listing state (spec C.7).

Directive 12: "Do not trust frontend state, browser state, hidden fields, JavaScript variables,
client-side image URLs." Every one of those reaches this codebase as a query string, and this
function reads none of them. It takes the listing's own visibility, the photograph's own record,
and nothing else.

Three rules it cannot break, each asserted directly in `tests/privacy/test_delivery.py`:
the original is never the answer; display is never the answer under NOT_SHOW; a missing derivative
is a null slot and never a fallback to something else."""
from __future__ import annotations

from dataclasses import dataclass

from app.privacy.record import PrivacyRow

#: The buyer bytes route. `no-cache` means "revalidate", not "do not store": with an ETag a browser
#: gets a 304 for an unchanged derivative and the network cost is a header exchange. What it stops
#: is a buyer's browser rendering, from cache, a variant a flip has already replaced -- which
#: `private, max-age=86400` allowed for 24 hours (directive 14, D-IDP-11).
PHOTO_HEADERS = {"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff"}
#: The owner and reviewer routes: never stored at all, and inline rather than an attachment.
OWNER_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                 "Content-Disposition": "inline"}

_NOT_SHOW_READY = ("SELLER_CONFIRMED", "PUBLISHED")
_SHOW_READY = ("READY_FOR_REVIEW", "SELLER_CONFIRMED", "PUBLISHED")


@dataclass(frozen=True)
class Variant:
    """What to serve: an object key (or, for a seed photograph, a relative disk path) and the
    content hash that is both the URL's `?v=` and the response's ETag."""

    key: str
    sha256: str
    from_disk: bool = False


def buyer_variant(visibility: str, asset: PrivacyRow | None, entry: str,
                  seed_sha: str | None = None) -> Variant | None:
    """The one representation this caller may have, or None -- a 404 on the bytes route and a null
    slot in the JSON.

    A seed entry is a PATH (it contains a "/") and has no asset row: it can only ever be served
    under SHOW, because no derivative of it exists to serve under NOT_SHOW (spec C.10)."""
    if asset is None:
        if "/" in entry and visibility == "SHOW" and seed_sha is not None:
            return Variant(entry, seed_sha, True)
        return None
    if not asset.buyer_visible:
        return None
    if visibility == "NOT_SHOW":
        if asset.processing_status in _NOT_SHOW_READY and asset.redacted_storage_key and asset.redacted_sha256:
            return Variant(asset.redacted_storage_key, asset.redacted_sha256)
        return None
    if asset.processing_status in _SHOW_READY and asset.display_storage_key and asset.display_sha256:
        return Variant(asset.display_storage_key, asset.display_sha256)
    return None


def photo_url(listing_id: object, n: int, sha256: str) -> str:
    """The buyer's positional URL, plus a content hash. The hash is a CACHE KEY and never a
    selector: the server decides the variant, so `?v=` naming an old hash still resolves to the
    current one (spec F, "predictable asset URLs")."""
    return f"/api/listings/{listing_id}/photos/{n}?v={sha256[:12]}"


def owner_url(route_prefix: str, asset_id: object, sha256: str) -> str:
    """The owner's and reviewer's tile URL, and the ONLY producer of the `src` the wizard renders.

    `route_prefix` is the caller's own -- `/api/seller/listings/{id}/photos` for the owner,
    `/api/admin/listings/{id}/photos` for the reviewer -- because the two payloads must point at
    the route each principal's permission opens (spec C.6) and one function cannot know which. It
    is a parameter rather than two near-identical functions so there is exactly one place that
    decides what the `?v=` is: the content hash of the variant actually served, which is what makes
    the step-6 thumbnail change the moment a mask does.

    `serialise_draft`'s `photos[]` calls this (Task P9 Step 6) and `frontend/src/logic.js`'s A20.4
    tile map reads the result verbatim."""
    return f"{route_prefix}/{asset_id}?v={sha256[:12]}"
```

- [ ] `poetry run pytest tests/privacy/test_delivery.py -q -W error` — GREEN.

- [ ] **Step 3: RED — the buyer bytes route and the payloads**

Create `tests/api/test_buyer_photo_delivery.py` with the shared helper the whole scenario suite uses:

```python
"""Directive 20's security matrix, and directive 21's standing rule for every NOT_SHOW test:
"ASSERT buyer receives REDACTED representation. ASSERT buyer cannot access ORIGINAL
representation." One helper asserts both, in one place, so a scenario cannot forget half of it."""
from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

import pytest


def _privacy_of(conn: Any, listing_id: str, n: int) -> Any:
    """The `PrivacyRow` behind the nth entry of a listing's photographs -- what the helper below
    compares the delivered bytes against. Every scenario reads its expectations from the DATABASE
    rather than from a value the test computed, so a test cannot agree with a bug it caused.

    Synchronous, because `conn` is psycopg2 and always has been; only the CLIENT is async."""
    from app.privacy import record

    with conn.cursor() as cur:
        cur.execute("SELECT photos ->> %s FROM listing WHERE id = %s", (n - 1, listing_id))
        entry = cur.fetchone()[0]
    return record.read(conn, UUID(entry))


async def assert_buyer_sees_only_redacted(client: Any, buyer: dict[str, str], seller: dict[str, str],
                                          admin: dict[str, str], store: Any, listing_id: str, n: int,
                                          row: Any) -> None:
    """(1) the bytes are the redacted derivative and neither display nor the original; (2) no query
    parameter changes that; (3) the owner and reviewer routes refuse this caller; (4) neither
    payload names a hidden photograph; (5) an anonymous caller is refused even with production's
    indexing setting.

    `async def`, and every call awaited: the suite's client is `httpx.AsyncClient` over
    `ASGITransport` (`tests/api/conftest.py`), so an un-awaited call returns a coroutine and asserts
    nothing at all -- and `-W error` turns the "coroutine was never awaited" warning into the
    failure that catches it. Every caller writes `await assert_buyer_sees_only_redacted(...)`."""
    url = f"/api/listings/{listing_id}/photos/{n}"
    body = (await client.get(url, headers=buyer)).content
    display = store.get(row.display_storage_key)
    original = store.get(row.original_storage_key)
    assert hashlib.sha256(body).hexdigest() == row.redacted_sha256
    assert body != display and body != original

    for query in ("?variant=original", "?variant=display", f"?v={hashlib.sha256(display).hexdigest()[:12]}",
                  "?v=deadbeef", "?variant=original&v=deadbeef"):
        assert (await client.get(url + query, headers=buyer)).content == body
    # HEAD is 200 with the same validators and no body -- which is true only because the route
    # DECLARES `methods=["GET", "HEAD"]`. A `@router.get` route answers HEAD with 405 (FastAPI's
    # APIRoute does not add HEAD the way Starlette's Route does), and asserting 200 here is what
    # would catch a future edit that dropped the method.
    head = await client.head(url, headers=buyer)
    assert head.status_code == 200 and head.content == b""
    assert head.headers["etag"] == f'"{row.redacted_sha256}"'
    assert head.headers["cache-control"] == "private, no-cache"

    owner = f"/api/seller/listings/{listing_id}/photos/{row.asset_id}"
    assert (await client.get(owner + "?variant=original", headers=buyer)).status_code == 403
    assert (await client.get(owner + "?variant=display", headers=buyer)).status_code == 403
    assert (await client.get(owner + "?variant=original", headers=seller)).status_code in (200, 404)
    forbidden_admin = await client.get(f"/api/admin/listings/{listing_id}/photos/{row.asset_id}",
                                       headers=buyer)
    assert forbidden_admin.status_code == 403

    for payload in ((await client.get("/api/listings", headers=buyer)).text,
                    (await client.get(f"/api/listings/{listing_id}", headers=buyer)).text):
        for forbidden in (row.display_sha256[:12], hashlib.sha256(original).hexdigest()[:12],
                          "storage_key", "original", "ocr", "identity_matches", "redaction_regions"):
            assert forbidden not in payload, forbidden

    assert (await client.get(url)).status_code == 401


async def test_assert_helper_fails_on_a_display_body(
    client: Any, buyer: dict[str, str], seller: dict[str, str], admin: dict[str, str], store: Any,
    published_show_listing: Any
) -> None:
    """The helper is itself tested: a SHOW listing serves display, so the helper must refuse it.
    Without this the suite could pass by asserting nothing."""
    listing_id, row = published_show_listing
    with pytest.raises(AssertionError):
        await assert_buyer_sees_only_redacted(client, buyer, seller, admin, store, listing_id, 1, row)


# `published_show_listing` is a fixture in this file: a published listing with
# `identifiable_content_visibility = 'SHOW'` and one processed photograph, yielding
# `(listing_id, PrivacyRow)`. It exists for the case above and for scenario D's arms.
```

plus the named §20 cases the spec's §F column lists: `test_a_buyer_cannot_obtain_the_original_by_any_query_parameter`, `test_the_original_key_is_read_only_where_the_spec_says`, `test_the_v_parameter_selects_nothing`, `test_photo_responses_are_private_and_uncacheable_by_intermediaries`, `test_a_stale_url_after_a_flip_serves_the_redacted_bytes_not_a_304_of_the_original`, `test_head_on_the_photo_route_leaks_nothing`, `test_the_listing_route_table_is_exactly_the_pinned_literal`, `test_buyer_payloads_carry_no_key_no_ocr_no_region`, `test_anonymous_gets_401_on_the_photo_route_on_a_production_shaped_config`.

The original-key grep is a literal set, and the set is **derived by running the grep against the finished tree**, not assumed:

```python
ORIGINAL_KEY_MODULES = {
    # The row's own SELECT and INSERT. `delivery_row` builds a PrivacyRow here, for the same
    # reason: the list route must never name this identifier.
    "app/privacy/record.py",
    # The ONE handler body that can return original.* -- the owner route, mounted twice. The
    # admin router reuses this body rather than repeating it, so app/api/admin_listings.py is
    # NOT in this set; if an implementer writes a second body there, that is a fourth entry and
    # a deliberate edit to this literal whose review asks "why two?".
    "app/api/seller_listings.py",
    # The barcode pass reads the original once: a fill cannot hide under an OCR region, and a
    # symbol in the source that the display encode softened must still be found (spec C.5 2b).
    "app/tasks/media.py",
}


def test_the_original_key_is_read_only_where_the_spec_says() -> None:
    """Directive 20, "unauthorised original-image access". The identifier is the thing to count:
    three modules name it, and `app/privacy/delivery.py` -- the resolver every buyer request goes
    through -- is deliberately not one of them, because the resolver has no arm that could return
    it."""
    found = {path for path in sorted(str(f.relative_to(ROOT)) for f in (ROOT / "app").rglob("*.py"))
             if "original_storage_key" in (ROOT / path).read_text()}
    assert found == ORIGINAL_KEY_MODULES
    assert "original_storage_key" not in (ROOT / "app/privacy/delivery.py").read_text()
```

The route-table pin is a literal, because what a route can return is not derivable by walking `create_app().routes`:

```python
LISTING_ROUTES = {
    ("GET", "/api/listings"), ("GET", "/api/listings/{listing_id}"),
    # Both methods, because the buyer bytes route declares both. FastAPI's APIRoute does not add
    # HEAD beside GET the way Starlette's Route does, so this row exists only when the handler says
    # `methods=["GET", "HEAD"]` -- which spec F's "HEAD mirrors GET" requires it to.
    ("GET", "/api/listings/{listing_id}/photos/{n}"),
    ("HEAD", "/api/listings/{listing_id}/photos/{n}"),
    ("GET", "/api/seller/listings"), ("POST", "/api/seller/listings"),
    ("GET", "/api/seller/listings/{listing_id}"), ("PATCH", "/api/seller/listings/{listing_id}"),
    ("POST", "/api/seller/listings/{listing_id}/photos"),
    ("PATCH", "/api/seller/listings/{listing_id}/photos"),
    ("GET", "/api/seller/listings/{listing_id}/photos/{asset_id}"),
    ("POST", "/api/seller/listings/{listing_id}/photos/{asset_id}/confirm"),
    ("POST", "/api/seller/listings/{listing_id}/photos/{asset_id}/masks"),
    ("DELETE", "/api/seller/listings/{listing_id}/photos/{asset_id}/masks/{mask_id}"),
    ("POST", "/api/seller/listings/{listing_id}/photos/{asset_id}/reprocess"),
    ("PATCH", "/api/seller/listings/{listing_id}/assets/{asset_id}"),
    ("DELETE", "/api/seller/listings/{listing_id}/assets/{asset_id}"),
    ("POST", "/api/seller/listings/{listing_id}/documents"),
    ("GET", "/api/seller/listings/{listing_id}/documents/{asset_id}"),
    ("POST", "/api/seller/listings/{listing_id}/submit"),
    ("POST", "/api/seller/listings/{listing_id}/status"),
    ("GET", "/api/admin/listings"), ("GET", "/api/admin/listings/{listing_id}"),
    ("GET", "/api/admin/listings/{listing_id}/photos/{asset_id}"),
    ("POST", "/api/admin/listings/{listing_id}/decide"),
}
```

> The four routes P12 adds (`confirm`, the two mask routes, `reprocess`) are in this literal from the start and their rows fail until P12 lands. Write the literal here with those four **commented out**, uncomment them in P12 Step 5, and say so in both commit bodies — a pin that is edited twice is honest; a pin written to match whatever exists is not.

- [ ] `poetry run pytest tests/api/test_buyer_photo_delivery.py -q -W error` — RED throughout.

- [ ] **Step 4: GREEN — the buyer route, the payload and the headers**

In `app/api/listings.py`:

```python
#: D-IDP-11, replacing `private, max-age=86400`. See `app/privacy/delivery.py::PHOTO_HEADERS`.
PHOTO_CACHE_CONTROL = PHOTO_HEADERS["Cache-Control"]


@lru_cache(maxsize=1)
def seed_digests() -> dict[str, str]:
    """`<slug>/<file>` -> the SHA-256 `scripts/prepare_photos.py` recorded, read once per process.

    The sibling of `seed_captions()` (which lives in `app/api/seller_listings.py`); it is HERE
    because `serialise` is here and `seller_listings` imports from this module, never the reverse.
    An absent or malformed inventory falls back to an empty map, and a seed URL then carries no
    `?v=` -- a missing cache key, never a missing photograph."""
    try:
        index = json.loads((PHOTOS_ROOT / "index.json").read_text())
        return {f"{slug}/{photo['file']}": photo["sha256"]
                for slug, photos in index["hospitals"].items() for photo in photos if photo["file"]}
    except (OSError, ValueError, KeyError):
        return {}


def photo_response(body: bytes, sha256: str, request: Request) -> Response:
    """The bytes, or a 304. The ETag is the CONTENT hash, so a flip changes it and no browser can
    revalidate its way back to the variant it had (directive 14, "cached browser response")."""
    etag = f'"{sha256}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={**PHOTO_HEADERS, "ETag": etag})
    return Response(content=body, media_type="image/webp", headers={**PHOTO_HEADERS, "ETag": etag})
```

`_SELECT` gains the aggregate that lets the list route stay one statement — named `visible_photos`, the spec's own name for it (§C.7 row 3), and joined to `listing_asset` because the resolver's SHOW arm needs the DISPLAY key and hash and the privacy table holds neither:

```sql
       coalesce((SELECT jsonb_object_agg(p.asset_id::text, jsonb_build_object(
                          'status', p.processing_status,
                          'visible', p.buyer_visible,
                          'redacted_key', p.redacted_storage_key,
                          'redacted', p.redacted_sha256,
                          'display_key', a.storage_key,
                          'display', a.sha256))
                   FROM listing_asset_privacy p
                   JOIN listing_asset a ON a.id = p.asset_id
                  WHERE p.listing_id = listing.id),
                '{}'::jsonb) AS visible_photos,
```

**The join is not optional.** `buyer_variant`'s SHOW arm returns a `Variant` only when `asset.display_storage_key` and `asset.display_sha256` are both present, so an aggregate carrying status, visibility and the redacted hash alone would resolve to `None` for every SHOW photograph — every seeded demo hospital included — and `serialise` would answer `photos: [null, …]`. Scenario D asserts the opposite, and this is the reason it can.

`serialise` (`:291-299`) resolves each slot instead of naming it unconditionally:

```python
        # Directive 9: under NOT_SHOW the buyer must not receive the original by "an API response"
        # either. A slot the resolver refuses is a JSON null -- the design's own empty-slot
        # placeholder (A-L10) -- and never a URL that would 404 or, worse, resolve to something else.
        "photos": urls,
        # A-L11's parallel array, with one change: a caption whose slot resolved to None becomes
        # "", so no description of a hidden photograph is delivered beside a null.
        "photo_captions": [caption if url is not None else ""
                           for url, caption in zip(urls, captions, strict=True)],
```

where `urls` and `captions` are computed once above the literal:

```python
    urls = _photo_urls(listing_id, photos, row)
    captions = photo_captions(photos, photo_list(row["photo_captions"]), row["asset_captions"])
```

and `_photo_urls` is:

```python
def _photo_urls(listing_id: str, photos: list[str | None], row: Mapping[str, Any]) -> list[str | None]:
    """One URL per slot, or None where the resolver refuses it (spec C.7 rows 3-4).

    Every decision here belongs to `buyer_variant`; this function's whole job is to hand it the
    listing's visibility and the photograph's own record and to turn its answer into a positional
    URL. The record comes from `_SELECT`'s `visible_photos` aggregate -- one query for the whole
    page, never a lookup per photograph -- and a seed PATH entry has no record at all, which is why
    the entry and the inventory digest are passed too."""
    visibility = str(row["identifiable_content_visibility"])
    aggregate = row["visible_photos"]
    digests = seed_digests()
    out: list[str | None] = []
    for n, entry in enumerate(photos, start=1):
        if entry is None:
            out.append(None)
            continue
        found = aggregate.get(entry)
        asset = None if found is None else record.delivery_row(entry, row["id"], found)
        variant = buyer_variant(visibility, asset, entry, digests.get(entry))
        out.append(None if variant is None else photo_url(listing_id, n, variant.sha256))
    return out
```

`record.delivery_row` is the one place that turns the aggregate's JSON object back into the dataclass the resolver reads, and it lives in `app/privacy/record.py` (added in this task) rather than in `app/api/listings.py` for a reason the security matrix names: `original_storage_key` is a constructor argument of `PrivacyRow`, and building one here would put that identifier in a fourth module and defeat `::test_the_original_key_is_read_only_where_the_spec_says`.

```python
def delivery_row(entry: str, listing_id: object, found: Mapping[str, Any]) -> PrivacyRow:
    """`app/api/listings.py`'s `visible_photos` aggregate object, as the row `buyer_variant` reads.

    Only the six fields the resolver actually reads carry a value; the rest take the dataclass's
    neutral ones, and NOTHING built here is ever serialised -- it exists for the length of one
    `buyer_variant` call. `original_storage_key` is the empty string rather than the real key
    because the resolver never reads it and the list route must never carry it: that is the
    security matrix's "unauthorised original-image access" row, and it is why this function is here
    rather than in the module that calls it."""
    return PrivacyRow(
        asset_id=UUID(entry), listing_id=UUID(str(listing_id)),
        processing_status=str(found["status"]), processing_version=0, attempts=0,
        original_storage_key="", redacted_storage_key=found.get("redacted_key"),
        redacted_sha256=found.get("redacted"), confirmed_sha256=None, seller_confirmed=False,
        buyer_visible=bool(found["visible"]), redaction_regions=[], reprocess_reason=None,
        final_privacy_state=None, display_storage_key=found.get("display_key"),
        display_sha256=found.get("display"),
    )
```

`get_listing_photo` (`:472-497`) resolves before it reads a byte, and **declares HEAD explicitly**:

```python
@router.api_route("/listings/{listing_id}/photos/{n}", methods=["GET", "HEAD"],
                  dependencies=[Depends(REQUIRE_LISTING_READ)])
async def get_listing_photo(listing_id: str, n: int, request: Request) -> Response:
    """The ONE buyer bytes route. Every query parameter is ignored for resolution: `?variant=`,
    `?v=` and anything else a caller invents cannot change what this returns (directive 20,
    "alternate image endpoints").

    `api_route(methods=["GET", "HEAD"])` and not `@router.get`: Starlette's own `Route` adds HEAD
    beside GET (`starlette/routing.py:237-238`) but FastAPI's `APIRoute` does not
    (`fastapi/routing.py:1019-1021`), so a `@router.get` route answers HEAD with **405**. Measured
    on this repository's pinned FastAPI: `GET /x -> 200`, `HEAD /x -> 405`, `route.methods ==
    {'GET'}`; with both methods declared, `HEAD` is 200 with the same ETag, the same
    `Content-Length` and an empty body. Spec F's "HEAD mirrors GET on the buyer route and returns
    the same headers and no body" is a claim, and this is what makes it true rather than a comment
    that says Starlette will handle it."""
    with closing(sync_conn()) as conn, conn:
        found = _published_photos_and_visibility(conn, listing_id)
        if found is None:
            return _error("NOT_FOUND", "No such listing.", 404)
        photos, visibility = found
        entry = photos[n - 1] if 1 <= n <= len(photos) else None
        if entry is None:
            return _error("NOT_FOUND", "No such photograph.", 404)
        variant = buyer_variant(visibility, _privacy_for(conn, listing_id, entry), entry,
                                seed_digests().get(entry))
        if variant is None:
            return _error("NOT_FOUND", "No such photograph.", 404)
        if not variant.from_disk:
            body = _object_bytes(variant.key)
            if body is None:
                # A bucket outage stays a 404 -- never a fallback to another key (directive 19).
                return _error("NOT_FOUND", "No such photograph.", 404)
            return photo_response(body, variant.sha256, request)
    path = photo_file(photos, n)
    if path is None:
        return _error("NOT_FOUND", "No such photograph.", 404)
    return photo_response(path.read_bytes(), variant.sha256, request)
```

with the single-photograph lookup beside it:

```python
def _privacy_for(conn: Any, listing_id: str, entry: str) -> record.PrivacyRow | None:
    """The one photograph's record, for the bytes route -- the single-row sibling of the list
    route's `visible_photos` aggregate.

    None for three different things, all of which the resolver answers the same way: a seed PATH
    entry (which is not a uuid at all), an entry whose row is gone, and an entry whose row belongs
    to another listing. The last is the IDOR check and it is in SQL through `record.read`'s own
    join plus the comparison below, never in a query parameter."""
    try:
        parsed = UUID(entry)
    except ValueError:
        return None                                   # a seed path entry: `buyer_variant` handles it
    row = record.read(conn, parsed)
    return row if row is not None and str(row.listing_id) == str(listing_id) else None
```

`_asset_bytes` keeps its "every no is the same None" rule but is renamed `_object_bytes` and now takes a KEY rather than an entry, because the decision of WHICH key is the resolver's. `_published_photos` becomes `_published_photos_and_visibility`, selecting `identifiable_content_visibility` beside `photos` in the same statement (spec §C.7 row 1).

- [ ] **Step 5: GREEN — the owner and reviewer routes**

One handler body, two mount points (spec §C.6). In `app/api/seller_listings.py`:

```python
VARIANTS = ("display", "redacted", "original")
#: The inverse of `app.privacy.PHOTO_EXT` -- the extension the upload's magic-byte sniff chose.
ORIGINAL_MEDIA_TYPE = {ext: content_type for content_type, ext in PHOTO_EXT.items()}


def _fetch(store: ObjectStore, key: str) -> bytes | None:
    """One object, or None for a missing key AND for a bucket that answered an error -- the same
    rule `app/api/listings.py::_object_bytes` follows, and for the same reason: `ObjectStore.get`
    re-raises every `ClientError` that is not a 404 (`app/storage.py:66-72`), and an owner route
    that 500s on a bucket blip tells a caller more than a 404 does."""
    try:
        return store.get(key)
    except (BotoCoreError, ClientError) as exc:
        log.warning("[seller] object read failed: %s", type(exc).__name__)
        return None


def photo_variant_response(conn: Any, listing_row: dict[str, Any], asset_id: str,
                           requested: str | None, request: Request) -> Response:
    """The bytes of one variant, for a caller who has already been proved owner or reviewer.

    The ONLY handler body in this codebase that can return `original.*`, and it can do so only for
    `?variant=original`. The default is the listing's own BUYER-facing variant, so the step-6 tile
    and the review dialog show what a buyer would see rather than what the seller uploaded."""
    parsed = _asset_uuid(asset_id)
    row = record.read(conn, parsed)
    if row is None or row.listing_id != listing_row["id"]:
        raise Refusal("NOT_FOUND", "No such photograph.", 404)
    if requested is not None and requested not in VARIANTS:
        raise Refusal("BAD_REQUEST", f"variant must be one of {', '.join(VARIANTS)}.", 400)
    default = "redacted" if listing_row["identifiable_content_visibility"] == "NOT_SHOW" else "display"
    wanted = requested or default
    key, digest = {
        "original": (row.original_storage_key, None),
        "display": (row.display_storage_key, row.display_sha256),
        "redacted": (row.redacted_storage_key, row.redacted_sha256),
    }[wanted]
    if key is None:
        raise Refusal("NOT_FOUND", "No such photograph.", 404)
    body = _fetch(store_for_request(), key)
    if body is None:
        raise Refusal("NOT_FOUND", "No such photograph.", 404)
    etag = f'"{digest or sha256_hex(body)}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={**OWNER_HEADERS, "ETag": etag})
    # The original's media type comes from its own key's extension -- the sniff at upload chose
    # that extension from the magic bytes, so it is the one fact about those bytes we know.
    media_type = "image/webp" if wanted != "original" else ORIGINAL_MEDIA_TYPE[key[key.rfind("."):]]
    return Response(content=body, media_type=media_type, headers={**OWNER_HEADERS, "ETag": etag})


@router.get("/listings/{listing_id}/photos/{asset_id}")
async def read_photo(listing_id: str, asset_id: str, request: Request, principal: Owner) -> Response:
    """The owner's own photograph. Ownership is in the SQL (`owned_row`), so another seller's is a
    404 byte-identical to a missing one (D7). NOT audited: a polled bytes route must not write an
    audit row per poll -- the `users.review` lesson."""
    try:
        with closing(sync_conn()) as conn, conn:
            row = owned_row(conn, listing_id, principal)
            return photo_variant_response(conn, row, asset_id, request.query_params.get("variant"), request)
    except Refusal as exc:
        return _refused(exc)
```

and in `app/api/admin_listings.py` the same body behind `REQUIRE_REVIEW`, with the listing read by id and no ownership scope, so the reviewer sees what the seller confirmed before deciding — the §A.4 row 6 gap, closed.

- [ ] `poetry run pytest tests/api/test_buyer_photo_delivery.py tests/api/test_listings.py tests/api/test_listing_assets.py -q -W error` — GREEN, with two pins re-recorded in the same commit: `tests/api/test_listings.py:227` (the header string) and `tests/api/test_listing_assets.py:642-643` (the header, and the byte-identity assertion, which becomes the SHOW case).

- [ ] **Step 6: the draft payload's tiles — the fields the whole seller UI reads**

Spec §C.6's closing paragraph: "`serialise_draft.photos[]` … gains, per tile — for the owner and the reviewer alike — `src` …, `variant`, `state` …, `masks` … and `width`/`height`. `assets_for` … joins the privacy row; it still never selects a storage key." Nothing produces those fields today: `photo_tiles` (BRANCH `seller_listings.py:301-319`) emits `{id, name}` and `assets_for` (`:418-435`) selects `listing_id, id, kind, name, content_type, byte_size, caption`. Without this step P11's `A20.4` tiles read `a.src` and `a.state` from a payload that has neither, `logic.test.ts` passes only because its stub adapter invents them, and steps 2, 4, 5 and 6 of the QA click-through are impossible.

- [ ] `assets_for` selects the privacy columns the tiles need — and no key, which is the pinned part:

```python
    with conn.cursor() as cur:
        cur.execute("SELECT a.listing_id, a.id, a.kind, a.name, a.content_type, a.byte_size, a.caption,"
                    "       a.sha256, p.processing_status, p.attempts, p.redacted_sha256,"
                    "       p.redaction_regions, p.ocr -> 'size' AS size"
                    "  FROM listing_asset a"
                    "  LEFT JOIN listing_asset_privacy p ON p.asset_id = a.id"
                    " WHERE a.listing_id = ANY(%s) ORDER BY a.listing_id, a.created_at, a.id",
                    (listing_ids,))
        for r in cur.fetchall():
            grouped[r[0]].append({"id": str(r[1]), "kind": r[2], "name": r[3],
                                  "content_type": r[4], "byte_size": r[5], "caption": r[6],
                                  # Underscored and never serialised: `photo_tiles` reads these and
                                  # emits the five public fields; `documents[]` and `_asset_payload`
                                  # keep emitting exactly what they emit today.
                                  "_sha256": r[7], "_status": r[8], "_attempts": r[9],
                                  "_redacted": r[10], "_regions": r[11] or [], "_size": r[12]})
```

A `LEFT JOIN`, because a document has no privacy row (D19) and the join must not decide that. No storage key is selected, which is the property `tests/api/test_listing_assets.py`'s existing "storage_key never emitted" pin already holds and which this task extends to the three new keys.

**The underscored keys never reach a response.** `serialise_draft` returns `"assets": assets` and builds `"documents"` with `{**asset, …}`, so without this the draft payload would carry `_redacted`, `_status` and the raw `_regions` — including `expanded_from` and `pad_px`, which spec §F's "API response leakage" row and directive 15 both forbid. One helper strips them at both projections:

```python
def _public(asset: Mapping[str, Any]) -> dict[str, Any]:
    """An asset entry without the underscored privacy columns `assets_for` carries for
    `photo_tiles`. Those are INPUTS to the tile projection and never part of a payload: a draft
    response carries no hash of any variant, no processing status under that name and no raw
    region. Underscore-prefixed rather than a second return value, so a column added to the SELECT
    for the tiles cannot be leaked by forgetting to remove it from a list somewhere else."""
    return {key: value for key, value in asset.items() if not key.startswith("_")}
```

```python
        "assets": [_public(asset) for asset in assets],
        "photos": photo_tiles(row, assets, owner_route=f"/api/seller/listings/{row['id']}/photos"),
        "documents": [{**_public(asset), "url": f"/api/seller/listings/{row['id']}/documents/{asset['id']}"}
                      for asset in assets if asset["kind"] != "photo"],
```

- [ ] `photo_tiles` gains the five fields, and the pill:

```python
#: The four words a tile can say (spec H). A status the map does not name is a status migration 041
#: does not have -- a `KeyError` here is the right answer, not a default that invents a pill.
TILE_PILL = {
    "UPLOADED": "processing", "PROCESSING": "processing", "SCANNED": "processing",
    "REDACTION_GENERATED": "processing", "REPROCESS_REQUIRED": "processing",
    "READY_FOR_REVIEW": "review", "SELLER_CONFIRMED": "confirmed", "PUBLISHED": "confirmed",
    "REVIEW_REQUIRED": "failed",
}
#: The two states whose pill depends on whether a retry is still coming. Directive 15: do not make
#: the seller understand technical detection results -- a photograph the worker will try again reads
#: "Processing..." and only one whose attempts are spent reads "Failed".
RETRYING = ("PROCESSING_FAILED", "REDACTION_FAILED")


def photo_tiles(row: dict[str, Any], assets: list[dict[str, Any]], *, owner_route: str) -> list[dict[str, Any]]:
    """Step 6's tiles in `listing.photos`' own order, named by what the photograph SHOWS, and now
    carrying what the seller's review needs: the buyer-facing variant's URL, its state pill, the
    masks the dialog draws, and the display size those masks are measured in.

    `owner_route` is the caller's own prefix -- the seller router's for the owner, the admin
    router's for the reviewer -- so each payload points at the route that principal's permission
    opens (spec C.6). No storage key, no OCR text, no identity match, no confidence, no engine and
    no model name: `::test_the_draft_payload_carries_masks_and_state_and_nothing_technical` is the
    pin and directive 15 is the reason."""
    by_id = {asset["id"]: asset for asset in assets if asset["kind"] == "photo"}
    seeded = seed_captions()
    tiles: list[dict[str, Any]] = []
    for entry in photo_list(row["photos"]):
        if entry is None:
            continue
        asset = by_id.get(entry)
        name = (asset["caption"] if asset else None) or seeded.get(entry) or ""
        tiles.append({"id": entry, "name": name,
                      **_tile_privacy(row, entry, asset, owner_route=owner_route)})
    return tiles


def _tile_privacy(row: dict[str, Any], entry: str, asset: dict[str, Any] | None, *,
                  owner_route: str) -> dict[str, Any]:
    """The five privacy fields of one tile. A seed PATH entry has no asset row at all, and a
    photograph whose privacy row is somehow absent is treated the same way: the shape with nothing
    in it, so the design's badge band renders exactly as it does today and no `src` is invented."""
    if asset is None or asset.get("_status") is None:
        return {"src": None, "variant": None, "state": "processing", "masks": [],
                "width": None, "height": None}
    status = str(asset["_status"])
    not_show = row["identifiable_content_visibility"] == "NOT_SHOW"
    variant = "redacted" if not_show else "display"
    digest = asset["_redacted"] if not_show else asset["_sha256"]
    state = TILE_PILL[status] if status not in RETRYING else (
        "processing" if int(asset["_attempts"]) < record.MAX_ATTEMPTS else "failed")
    size = asset["_size"] or [None, None]
    return {
        "src": None if digest is None else owner_url(owner_route, entry, str(digest)),
        "variant": variant,
        "state": state,
        # Only what the dialog draws and what Remove targets: an id, a box in display pixels, and
        # whether the seller put it there. Never `expanded_from`, never `pad_px`, never `by`, and
        # never a region the seller has already removed.
        "masks": [{"id": region["id"], "box": _mask_box(region["polygon"]), "source": region["source"]}
                  for region in asset["_regions"] if region["source"] != "removed-by-seller"],
        "width": size[0],
        "height": size[1],
    }


def _mask_box(polygon: list[list[float]]) -> list[float]:
    """A stored polygon as the axis-aligned box the dialog outlines. The dialog draws rectangles;
    the record keeps the polygon, because a rotated sign is covered by the quad the engine returned
    and the FILL uses that quad, not this box."""
    xs = [float(point[0]) for point in polygon]
    ys = [float(point[1]) for point in polygon]
    return [min(xs), min(ys), max(xs), max(ys)]
```

The `src` is built by `app/privacy/delivery.py::owner_url` and by nothing else — this passes it the caller's own prefix, so the reviewer's copy of the payload points at `/api/admin/listings/{id}/photos/{asset_id}` and the seller's at `/api/seller/listings/{id}/photos/{asset_id}`, from one function with one rule about the `?v=`. `record.MAX_ATTEMPTS` is P3's; `width`/`height` come from `ocr.size`, which `app/tasks/media.py::_scan` writes as `list(image.size)` — spec §C.3 keeps the dimensions nowhere else. A tile whose photograph has not been scanned yet reports both as `None`, which is correct and is what the dialog's draw mode refuses to start on.

- [ ] The admin draft read (`app/api/admin_listings.py:280-291`) passes its own prefix, `owner_route=f"/api/admin/listings/{row['id']}/photos"`, and nothing else about it changes.

- [ ] Cases in `tests/api/test_seller_listings.py` — one for the shape, one for the pill's two-state rule, one for the leak pin:

```python
async def test_a_draft_photo_tile_carries_its_variant_state_masks_and_size(
    client: Any, seller: dict[str, str], store: Any, conn: Any
) -> None:
    """Spec C.6. Every field the wizard reads is produced here, and the shape is asserted whole so
    a missing one fails in this task rather than becoming a mystery in P11."""
    listing_id, asset_id = await _uploaded_and_processed(client, seller, store, conn)
    tile = (await client.get(f"/api/seller/listings/{listing_id}", headers=seller)).json()["photos"][0]
    row = record.read(conn, UUID(asset_id))
    assert tile["id"] == asset_id and tile["variant"] == "redacted" and tile["state"] == "review"
    assert tile["src"] == f"/api/seller/listings/{listing_id}/photos/{asset_id}?v={row.redacted_sha256[:12]}"
    assert (tile["width"], tile["height"]) == (1200, 900)
    assert tile["masks"] and all(set(mask) == {"id", "box", "source"} for mask in tile["masks"])
    assert all(len(mask["box"]) == 4 for mask in tile["masks"])


@pytest.mark.parametrize(("status", "attempts", "pill"), [
    ("UPLOADED", 0, "processing"), ("PROCESSING", 1, "processing"), ("SCANNED", 1, "processing"),
    ("REDACTION_GENERATED", 1, "processing"), ("REPROCESS_REQUIRED", 1, "processing"),
    ("PROCESSING_FAILED", 1, "processing"), ("REDACTION_FAILED", 2, "processing"),
    ("PROCESSING_FAILED", 3, "failed"), ("REVIEW_REQUIRED", 3, "failed"),
    ("READY_FOR_REVIEW", 0, "review"), ("SELLER_CONFIRMED", 0, "confirmed"),
    ("PUBLISHED", 0, "confirmed"),
])
async def test_the_pill_says_processing_while_a_retry_is_pending_and_failed_once_they_are_spent(
    client: Any, seller: dict[str, str], conn: Any, status: str, attempts: int, pill: str
) -> None:
    """Directive 15: "Do NOT force the seller to understand technical detection results." A
    photograph the worker will try again says Processing..., and only one whose attempts are spent
    says Failed. Twelve rows, which is every status the map names plus both sides of the retry
    rule -- the parametrisation IS the coverage of `_tile_privacy`'s branch."""
    listing_id, _asset_id = await _plant_photo(client, seller, conn, status=status, attempts=attempts)
    tile = (await client.get(f"/api/seller/listings/{listing_id}", headers=seller)).json()["photos"][0]
    assert tile["state"] == pill


async def test_a_seed_path_entry_still_renders_the_design_s_badge_band(
    client: Any, seller: dict[str, str], conn: Any
) -> None:
    """A claimed demo hospital: `listing.photos` holds paths, there is no asset row and no privacy
    row, and the tile must come back with the shape and no `src` rather than not come back at all."""
    listing_id = await _claimed_seed_listing(client, seller, conn)
    tile = (await client.get(f"/api/seller/listings/{listing_id}", headers=seller)).json()["photos"][0]
    assert tile["src"] is None and tile["state"] == "processing" and tile["masks"] == []


async def test_the_draft_payload_carries_masks_and_state_and_nothing_technical(
    client: Any, seller: dict[str, str], store: Any, conn: Any
) -> None:
    """Directive 15 again, and spec F's "API response leakage" row: the owner's own payload carries
    boxes and a pill, and nothing from `ocr`, `identity_matches` or `vision`."""
    listing_id, _asset_id = await _uploaded_and_processed(client, seller, store, conn)
    body = (await client.get(f"/api/seller/listings/{listing_id}", headers=seller)).text
    for forbidden in ("storage_key", "original", "\"ocr\"", "identity_matches", "vision", "confidence",
                      "expanded_from", "pad_px", "detected_regions", "rapidocr", "zxing", "claude"):
        assert forbidden not in body, forbidden
```

`_uploaded_and_processed`, `_plant_photo` and `_claimed_seed_listing` are three helpers written beside them in that file: the first uploads a photograph and runs `media.process_photo` inline against the moto bucket, the second plants a privacy row in a named state with `tests/privacy/conftest.py`'s builder, the third inserts a `source='seed'` row with a path entry and PATCHes it once so `claim_from_seed` fires.

- [ ] The reviewer's copy: one case in `tests/api/test_admin_listings.py` asserting the admin draft read returns the same five fields with `src` under `/api/admin/listings/…`, and that a buyer gets 403 from it.

- [ ] `poetry run pytest tests/api/test_seller_listings.py tests/api/test_admin_listings.py -q -W error` — GREEN.

- [ ] **Step 7: the perf, storage and static pins**

- [ ] `tests/perf/test_query_plans.py::PLANS` — one row for the buyer route's privacy lookup and one for the list route's aggregate; both must show an index scan on `listing_asset_privacy_listing_idx`.
- [ ] `tests/perf/test_api_latency.py` — a moto-backed seller-arm case under the existing `photo: 150` budget; the budget is not raised.
- [ ] `tests/test_storage.py::test_no_presigning_exists` — `grep presign app/` is empty and `ObjectStore` has no `generate_presigned_url`.
- [ ] `tests/test_static.py::test_public_photos_are_exactly_the_three_design_fixtures` and `::test_index_html_carries_no_share_image_no_preload_and_no_manifest`; plus a grep test that no path under `frontend/public` is ever written by `app/`.

- [ ] **Step 8: the task's gates**, then the commit:

```
feat(api): one resolver decides every buyer image request, and the owner and reviewer can finally look

Directive 9 and 12: under NOT_SHOW the buyer must not receive the original
through the image URL, an API response, a thumbnail, a download, a CDN URL,
an alternate endpoint or a cache, and the backend must enforce it.
app/privacy/delivery.py::buyer_variant is that enforcement -- pure, total,
and unit-tested over every cell of visibility x status x buyer_visible x
key-present. It reads no query parameter, so ?variant=original and any
?v= a caller invents resolve to exactly what the policy allows.

The bytes route and serialise both call it. A slot it refuses is a JSON
null -- the design's own empty-slot placeholder -- and a caption is emptied
with it, so no description of a hidden photograph is delivered beside a
null. Photo URLs carry ?v=<content hash>, and the response carries
private, no-cache with an ETag instead of private, max-age=86400: a flip
changes both the URL and the validator, so no browser can render a variant
the policy has replaced. The list route stays one statement, through an
aggregate over listing_asset_privacy.

The route declares methods=["GET", "HEAD"] rather than @router.get:
FastAPI's APIRoute does not add HEAD beside GET the way Starlette's Route
does, so a GET-only route answers HEAD with 405 and the security matrix's
"HEAD mirrors GET" would have been false.

Two new routes serve one handler body: the owner's, scoped in SQL, and the
reviewer's under listing.review. They are the only bodies that can return
original.*, and only for ?variant=original. Before this, nobody could look
at an uploaded photograph before publication -- the reviewer decided blind.

The draft payload finally carries what the seller's review needs, which
nothing produced before: per tile, the buyer-facing variant's URL with its
content hash, the variant's name, a four-word state pill, the masks the
dialog draws in display-pixel space, and the display size those masks are
measured in. assets_for joins the privacy row for it and still selects no
storage key; the pill says Processing... while a retry is pending and
Failed only once the attempts are spent, because directive 15 says the
seller must not have to understand detection results.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `git add app/privacy/delivery.py app/privacy/record.py app/api/listings.py app/api/seller_listings.py app/api/admin_listings.py tests/privacy/test_delivery.py tests/api/test_buyer_photo_delivery.py tests/api/test_listings.py tests/api/test_listing_assets.py tests/api/test_seller_listings.py tests/api/test_admin_listings.py tests/perf/test_query_plans.py tests/perf/test_api_latency.py tests/test_storage.py tests/test_static.py`

---

### Task P10: the publishing gate, the listing setting's one writer, and the flip

**Files:**
- Create: `app/privacy/gate.py`, `tests/privacy/test_gate.py`, `tests/api/test_listing_privacy.py` (started here)
- Modify: `app/api/seller_listings.py` (`STEP_FIELDS` `:115-122`, `columns_for` `:231-273`, `serialise_draft` `:322-362`, `patch_step` `:525-584`, `submit_listing` `:1181-1219`, `set_status` `:1222-1256`, `Refusal` `:163-168`, `_refused` `:443-444`)
- Modify: `app/api/admin_listings.py` (`decide_listing` `:201-277`)
- Modify: `frontend/src/listings/step-fields.json`, `tests/api/test_seller_listings.py`, `tests/api/test_admin_listings.py`

**Interfaces:**
- Consumes: P1's `listing_photos_not_ready()`; `record.{rows_for,flag_stale,set_visibility,reset_confirmation,mark_published,enqueue_processing,READY_STATES}`; `app/privacy.redacted_key`; `store_for_request`.
- Produces, `app/privacy/gate.py`:
  - `NOT_READY_MESSAGE: dict[str, str]` — the two §H strings, keyed `SHOW` / `NOT_SHOW`
  - `photos_not_ready(conn, listing_id: UUID) -> list[tuple[str, str]]` — `(entry, status)` offenders, from the SQL function, in `listing.photos` order
  - `not_ready_extra(offenders: Sequence[tuple[str, str]]) -> dict[str, list[dict[str, str]]]` — the additive `photos` key inside A5's `error`
- Produces, `app/api/seller_listings.py`: `Refusal.extra: dict[str, Any] | None`; `STEP_FIELDS[7]` gains `showIdentifiable`; `serialise_draft` gains `showIdentifiable`; `apply_visibility_change(conn, row, principal, request, *, to: str) -> list[UUID]` — the flip, returning the rows to enqueue after the commit.

- [ ] **Step 1: RED — the predicate**

`tests/privacy/test_gate.py` builds one listing per offender class with `tests/privacy/conftest.py`'s builder and asserts:

```python
def test_under_not_show_only_a_confirmed_photograph_with_a_derivative_passes(conn: Any) -> None:
    """Directive 11 (3): under NOT_SHOW "seller explicitly confirms the result". SELLER_CONFIRMED
    is the floor and READY_FOR_REVIEW is not enough -- "Never allow AI_PASSED to mean
    READY_TO_PUBLISH"."""
    listing_id = make_listing(conn, "gate-ns", visibility="NOT_SHOW")
    ready, _ = make_row(conn, listing_id=listing_id, processing_status="READY_FOR_REVIEW")
    confirmed, _ = make_row(conn, listing_id=listing_id, processing_status="SELLER_CONFIRMED",
                            confirmed=True, buyer_visible=True)
    assert gate.photos_not_ready(conn, listing_id) == [(str(ready), "READY_FOR_REVIEW")]


def test_under_show_the_floor_is_ready_for_review_and_not_scanned(conn: Any) -> None:
    """Controller ruling 8 gave a range from SCANNED; the spec narrows it to READY_FOR_REVIEW,
    because directive 11 (1) says "completed processing" and SCANNED is mid-run."""
    listing_id = make_listing(conn, "gate-show", visibility="SHOW")
    scanned, _ = make_row(conn, listing_id=listing_id, processing_status="SCANNED")
    ready, _ = make_row(conn, listing_id=listing_id, processing_status="READY_FOR_REVIEW", buyer_visible=True)
    assert gate.photos_not_ready(conn, listing_id) == [(str(scanned), "SCANNED")]


@pytest.mark.parametrize("status", ["UPLOADED", "PROCESSING", "PROCESSING_FAILED", "REDACTION_FAILED",
                                    "REVIEW_REQUIRED", "REPROCESS_REQUIRED"])
def test_every_unfinished_or_failed_state_is_an_offender_under_both_settings(conn: Any, status: str) -> None:
    for visibility in ("SHOW", "NOT_SHOW"):
        listing_id = make_listing(conn, f"gate-{status}-{visibility}", visibility=visibility)
        asset_id, _ = make_row(conn, listing_id=listing_id, processing_status=status)
        assert gate.photos_not_ready(conn, listing_id) == [(str(asset_id), status)]


def test_a_flagged_row_is_stale_and_a_new_publication_waits_for_it(conn: Any) -> None:
    listing_id = make_listing(conn, "gate-stale", visibility="NOT_SHOW")
    asset_id, _ = make_row(conn, listing_id=listing_id, processing_status="SELLER_CONFIRMED",
                           confirmed=True, buyer_visible=True, reprocess_reason="VERSION")
    assert gate.photos_not_ready(conn, listing_id) == [(str(asset_id), "STALE")]


def test_a_photograph_with_no_privacy_row_at_all_is_an_offender(conn: Any) -> None:
    """There is no path that creates one -- the upload writes both rows in one transaction -- and
    if one appeared the gate refuses rather than assuming."""
    listing_id = make_listing(conn, "gate-orphan", visibility="NOT_SHOW")
    asset_id, _ = make_row(conn, listing_id=listing_id, processing_status="SELLER_CONFIRMED",
                           confirmed=True, buyer_visible=True)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM listing_asset_privacy WHERE asset_id = %s", (asset_id,))
    assert gate.photos_not_ready(conn, listing_id) == [(str(asset_id), "NO_PRIVACY_ROW")]


def test_a_seed_path_entry_passes_under_show_and_is_seed_unprocessed_under_not_show(conn: Any) -> None:
    for visibility, expected in (("SHOW", []), ("NOT_SHOW", [("round-rock/1.webp", "SEED_UNPROCESSED")])):
        listing_id = make_listing(conn, f"gate-seed-{visibility}", visibility=visibility)
        with conn.cursor() as cur:
            cur.execute("UPDATE listing SET photos = '[\"round-rock/1.webp\"]'::jsonb WHERE id = %s",
                        (listing_id,))
        assert gate.photos_not_ready(conn, listing_id) == expected


def test_a_listing_with_no_photographs_has_no_offenders(conn: Any) -> None:
    """A listing may be published with none -- the design's empty slots are a legitimate state, and
    the gate is about the photographs there ARE."""
    assert gate.photos_not_ready(conn, make_listing(conn, "gate-empty")) == []


def test_the_offenders_come_back_in_listing_photos_order(conn: Any) -> None:
    """The wizard names them by position, so the order has to be the array's and not the table's."""
    listing_id = make_listing(conn, "gate-order", visibility="NOT_SHOW")
    first, _ = make_row(conn, listing_id=listing_id, processing_status="UPLOADED")
    second, _ = make_row(conn, listing_id=listing_id, processing_status="PROCESSING")
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET photos = %s::jsonb WHERE id = %s",
                    (json.dumps([str(second), str(first)]), listing_id))
    assert [entry for entry, _status in gate.photos_not_ready(conn, listing_id)] == [str(second), str(first)]
```

- [ ] `poetry run pytest tests/privacy/test_gate.py -q -W error` — RED: `ModuleNotFoundError`.

- [ ] **Step 2: GREEN — `app/privacy/gate.py`**

```python
"""The publishing gate (spec 2026-09-09 C.8; directive 11).

ONE predicate, evaluated by every publication route, and evaluated again in SQL by migration 042's
trigger for whatever a route might miss. The two live in the same file in the migration and are read
against each other here: this function calls the SQL function the trigger calls, so there is exactly
one definition of "ready" and it cannot drift.

The messages are the spec's own (H), and they are queued for John's vet as D-IDP-13."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

NOT_READY_MESSAGE = {
    "NOT_SHOW": "Every photograph must finish processing and be reviewed before this listing can be submitted.",
    "SHOW": "Every photograph must finish processing before this listing can be submitted.",
}


def photos_not_ready(conn: Any, listing_id: UUID) -> list[tuple[str, str]]:
    """The offenders, in `listing.photos` order, as `(entry, status)`.

    The SAME SQL function migration 042's trigger evaluates, called with the row's own visibility
    and photos so a route and the database can never disagree about what ready means."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT n.entry, n.status FROM listing l,"
            "       LATERAL listing_photos_not_ready(l.id, l.identifiable_content_visibility, l.photos) n"
            " WHERE l.id = %s"
            " ORDER BY coalesce((SELECT ordinality FROM jsonb_array_elements_text(l.photos)"
            "                     WITH ORDINALITY t(e, ordinality) WHERE t.e = n.entry LIMIT 1), 0)",
            (listing_id,),
        )
        return [(str(entry), str(status)) for entry, status in cur.fetchall()]


def not_ready_extra(offenders: Sequence[tuple[str, str]]) -> dict[str, list[dict[str, str]]]:
    """The additive key inside decision A5's `error` object -- `{"photos": [{"id", "status"}]}`.

    Additive rather than a new envelope shape: every existing client reads `error.code` and
    `error.message` and is unaffected, and the wizard's error slot renders the message while the
    step-6 tiles are what name the photographs."""
    return {"photos": [{"id": entry, "status": status} for entry, status in offenders]}
```

- [ ] `poetry run pytest tests/privacy/test_gate.py -q -W error` — GREEN.

- [ ] **Step 3: RED — the gate at all three publication routes**

Add to `tests/api/test_listing_privacy.py` (created here, extended by P12 and P13) the scenario-M cases: submit, decide-publish and republish each answering `422 PHOTOS_NOT_READY` with `error.photos` naming exactly the offending id and status; a direct `UPDATE listing SET status='published'` raising `P0001`; and the same three succeeding once every photograph is confirmed. Then:

- [ ] **Step 4: GREEN — the routes**

`Refusal` gains an optional `extra`, and `_refused` renders it:

```python
class Refusal(Exception):
    """A refusal the route renders through `_error`. Carries the envelope, never a status alone.

    `extra` is an ADDITIVE key inside A5's `error` object -- today only `PHOTOS_NOT_READY`'s
    `photos` list (spec C.8) -- so an existing client that reads `code` and `message` is
    unaffected."""

    def __init__(self, code: str, message: str, status: int, extra: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.status, self.extra = code, message, status, extra


def _refused(exc: Refusal) -> JSONResponse:
    if exc.extra is None:
        return _error(exc.code, exc.message, exc.status)
    return JSONResponse({"error": {"code": exc.code, "message": exc.message, **exc.extra}},
                        status_code=exc.status)
```

and one helper both seller routes call:

```python
def refuse_unready_photographs(conn: Any, row: dict[str, Any]) -> None:
    """Directive 11's gate, at every route that can put a listing on the market."""
    offenders = gate.photos_not_ready(conn, row["id"])
    if offenders:
        raise Refusal("PHOTOS_NOT_READY",
                      gate.NOT_READY_MESSAGE[row["identifiable_content_visibility"]], 422,
                      gate.not_ready_extra(offenders))
```

- `submit_listing` calls it immediately after `_complete_enough(row)`.
- `set_status`'s republish arm calls it before the UPDATE, and on success calls `record.mark_published(conn, row["id"])` in the same transaction.
- `decide_listing`'s publish branch calls `gate.photos_not_ready` before its UPDATE and returns `JSONResponse({"error": {"code": "PHOTOS_NOT_READY", "message": gate.NOT_READY_MESSAGE[visibility], **gate.not_ready_extra(offenders)}}, status_code=422)` — the admin router's own `_error` idiom, with the same additive key — then `record.mark_published` after the UPDATE succeeds.

- [ ] **Step 5: RED then GREEN — `showIdentifiable`, the one writer**

- [ ] `STEP_FIELDS[7]` becomes `("anon", "revBand", "docsLocked", "showIdentifiable")`; `frontend/src/listings/step-fields.json` gains the key under `"7"`; both two-way pins (`tests/api/test_seller_listings.py:1391`, `:1415`) re-run unchanged.
- [ ] `columns_for` gains one arm — **direct polarity, unlike its three neighbours**:

```python
        elif field == "showIdentifiable":
            # NOT the inverted polarity of `anon`/`revBand`/`docsLocked`. Those three are "hide
            # this"; John's control is "IDENTIFIABLE IMAGE CONTENT [ SHOW ] [ NOT SHOW ]" with the
            # default at NOT SHOW, so the switch is off for the safe state and ON means SHOW
            # (spec C.1, C.9 (a)).
            out["identifiable_content_visibility"] = "SHOW" if _flag("showIdentifiable", raw) else "NOT_SHOW"
```

- [ ] `serialise_draft` gains `"showIdentifiable": row["identifiable_content_visibility"] == "SHOW"`.
- [ ] `patch_step` gains the flip, before its existing `EDIT_REENTERS_REVIEW` arm, and the enqueue after the commit:

```python
            changed = ("identifiable_content_visibility" in columns
                       and columns["identifiable_content_visibility"] != row["identifiable_content_visibility"])
            ...
            if changed:
                requeue = apply_visibility_change(conn, row, principal, request,
                                                  to=columns["identifiable_content_visibility"])
```

with

```python
def apply_visibility_change(conn: Any, row: dict[str, Any], principal: S.Principal, request: Request,
                            *, to: str) -> list[UUID]:
    """Directive 16, both directions. Returns the rows to enqueue AFTER the commit.

    SHOW -> NOT_SHOW: "the system must immediately require/verify that redacted derivatives exist
    for EVERY image". Verified against the BUCKET and not only the row -- a key whose object is gone
    is a row that claims a derivative it cannot serve -- so the store must be configured: with it
    unconfigured this refuses 503 rather than skipping the check. A row confirmed under NOT_SHOW
    against the derivative it serves keeps its state; every other row goes back to review with the
    confirmation reset; a row whose object is missing loses its key and is re-processed.

    NOT_SHOW -> SHOW: nothing is deleted (16 again -- "Retain them for future switching back"),
    confirmations stand as recorded, and visibility follows readiness."""
    audit.write(conn, actor=principal, action="listing.privacy", target_type="listing",
                target_id=row["id"], reason="visibility",
                before={"identifiable_content_visibility": row["identifiable_content_visibility"]},
                after={"identifiable_content_visibility": to}, request=request)
    rows = record.rows_for(conn, row["id"])
    if to == "SHOW":
        for asset in rows:
            record.set_visibility(conn, asset.asset_id, visible=asset.processing_status in record.READY_STATES)
        return []
    store = store_for_request() if rows else None
    requeue: list[UUID] = []
    for asset in rows:
        if asset.redacted_storage_key is None or store is None or not _exists(
                store, asset.redacted_storage_key):
            _reprocess_from_scratch(conn, asset.asset_id)
            requeue.append(asset.asset_id)
        elif asset.seller_confirmed and asset.final_privacy_state == "NOT_SHOW":
            # Confirmed under NOT_SHOW against the derivative it serves (`lap_confirmed_ck` holds
            # `confirmed_sha256 = redacted_sha256`), so the confirmation stands and the row is
            # visible again at once -- spec C.1 step 3's "keeps its state".
            record.set_visibility(conn, asset.asset_id, visible=True)
        elif not record.reset_confirmation(conn, asset.asset_id):
            # NOT ready, so `reset_confirmation` refused it -- which is the answer, not a problem.
            # A REDACTION_FAILED or REVIEW_REQUIRED row can still carry a stale
            # `redacted_storage_key` whose object is present (`lap_ready_has_derivative_ck` only
            # constrains the ready states), so the `exists()` arm above passes it through and an
            # unguarded reset would PROMOTE it into READY_FOR_REVIEW, then into confirmable, then
            # into `buyer_visible` over a derivative whose regeneration had failed. It goes on the
            # re-enqueue arm instead: back to UPLOADED, key cleared, pipeline re-run.
            _reprocess_from_scratch(conn, asset.asset_id)
            requeue.append(asset.asset_id)
    return requeue


def _reprocess_from_scratch(conn: Any, asset_id: UUID) -> None:
    """The row loses its derivative claim and starts again: spec C.1 step 3's "a key whose object is
    gone has `redacted_storage_key`/`redacted_sha256` cleared, the reset rule applied,
    `processing_status := 'UPLOADED'`, and is enqueued after the commit"."""
    with conn.cursor() as cur:
        cur.execute("UPDATE listing_asset_privacy SET redacted_storage_key = NULL,"
                    " redacted_sha256 = NULL, processing_status = 'UPLOADED', attempts = 0,"
                    f" {record.RESET_COLUMNS}, updated_at = now() WHERE asset_id = %s",
                    (asset_id,))
```

`final_privacy_state` is already on `PrivacyRow` (Task P3's Interfaces say why it is there from the start and not added here), so this comparison needs no change to `record.py`. `_exists` is Task P2's — one guarded existence check, used by the upload's immutability guard and by this flip, so "a flip on a listing with photographs refuses rather than skips the check" (spec §C.1 step 3) is true for a bucket that ERRORS as well as for one that is unconfigured. `_reprocess_from_scratch` is module-level in `app/api/seller_listings.py`, beside `_put` and `_drop_object`.

Two cases in `tests/api/test_listing_privacy.py` for the two arms a reader would otherwise never see (`_raises` is the one-line helper Task P8 wrote in `tests/tasks/test_media.py`, imported here rather than restated; `ClientError` comes from `botocore.exceptions`, as it does in the suites that already plant one):

```python
async def test_a_failed_row_with_a_stale_derivative_is_re_processed_and_never_promoted(
    client: Any, seller: dict[str, str], store: Any, conn: Any
) -> None:
    """The SHOW -> NOT_SHOW flip's third arm. A REDACTION_FAILED row may still carry a
    `redacted_storage_key` whose object is on the bucket -- the CHECK permits it -- so the
    existence pass lets it through, and only `reset_confirmation`'s own READY_STATES guard stops it
    becoming reviewable, then confirmable, then visible over a derivative that failed."""
    listing_id, asset_id = await _show_listing_with(client, seller, store, conn,
                                                    status="REDACTION_FAILED", keep_derivative=True)
    res = await client.patch(f"/api/seller/listings/{listing_id}?step=7",
                             json={"showIdentifiable": False}, headers=seller)
    assert res.status_code == 200
    row = record.read(conn, UUID(asset_id))
    assert row.processing_status == "UPLOADED" and row.redacted_storage_key is None
    assert row.buyer_visible is False and row.seller_confirmed is False


async def test_a_bucket_outage_during_a_flip_is_a_503_and_changes_nothing(
    client: Any, seller: dict[str, str], store: Any, conn: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec C.1 step 3 refuses rather than skipping the check, and that has to hold for a bucket
    that ERRORS as well as for one that is unconfigured -- `ObjectStore.exists` re-raises anything
    that is not a 404."""
    listing_id, asset_id = await _show_listing_with(client, seller, store, conn,
                                                    status="SELLER_CONFIRMED", keep_derivative=True)
    before = record.read(conn, UUID(asset_id))
    monkeypatch.setattr("app.api.seller_listings.ObjectStore.exists",
                        _raises(ClientError({"Error": {"Code": "InternalError"}}, "HeadObject")))
    res = await client.patch(f"/api/seller/listings/{listing_id}?step=7",
                             json={"showIdentifiable": False}, headers=seller)
    assert res.status_code == 503 and res.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert record.read(conn, UUID(asset_id)) == before
```

`_show_listing_with(client, seller, store, conn, *, status, keep_derivative)` is an `async` helper written beside them in `tests/api/test_listing_privacy.py`: it creates a draft, uploads one photograph, runs `media.process_photo` inline against the moto bucket, plants the named `processing_status` and `attempts` with `tests/privacy/conftest.py`'s builder, sets the listing to `SHOW`, and leaves `redacted.webp` on the bucket or deletes it according to `keep_derivative`. It returns `(listing_id, asset_id)`.

- [ ] The cache drop for a visibility change is **unconditional** — `patch_step`'s existing conditional `leaving_market` arm stays for every other field:

```python
    if leaving_market or visibility_changed:
        drop_list_cache(sync_redis())
    for asset_id in requeue:
        record.enqueue_processing(asset_id, PROCESSING_VERSION)
```

- [ ] A test pins that `listing.privacy`'s `before`/`after` carry the visibility key and **no `status` key** — `_COLUMNS`' decline-reason subquery reads the latest `audit_log` row whose `after ->> 'status' = 'declined'`, and a new action that wrote `after.status` would corrupt it.

- [ ] **Step 6: the task's gates**, then the commit:

```
feat(api): the publishing gate, the listing's one visibility writer, and the flip

Directive 11: publishing is blocked until every photograph has completed
processing, has a valid state, and -- under NOT_SHOW -- has a buyer-safe
derivative the seller has explicitly confirmed. app/privacy/gate.py is one
predicate calling the same SQL function migration 042's trigger calls, so a
route and the database cannot disagree about what ready means, and submit,
decide-publish and republish all answer 422 PHOTOS_NOT_READY naming the
offending photographs and their states in an additive key inside the A5
envelope. Under SHOW the floor is READY_FOR_REVIEW rather than SCANNED,
because "completed processing" is what the directive says and SCANNED is
mid-run.

Directive 7's single authoritative setting has exactly one writer: the
owner's step-7 PATCH. Its polarity is direct, unlike the three switches
beside it -- off is the safe state, NOT SHOW. No admin route can write it
(Decision forbids the field and there is no admin PATCH).

Directive 16, both directions. SHOW -> NOT_SHOW verifies every derivative
against the BUCKET, not only the row: a key whose object is gone is
cleared and re-processed, a row confirmed under NOT_SHOW against the
derivative it serves keeps its state, and every other row goes back to
review with the confirmation reset. With the store unconfigured the flip
refuses 503 rather than skipping the check. NOT_SHOW -> SHOW deletes
nothing and keeps every confirmation, so switching back needs no
reprocessing. Either way the Browse cache is dropped unconditionally and a
listing.privacy audit row is written that carries no status key -- the
decline-reason subquery reads those.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `git add app/privacy/gate.py app/privacy/record.py app/api/seller_listings.py app/api/admin_listings.py frontend/src/listings/step-fields.json tests/privacy/test_gate.py tests/privacy/test_record.py tests/api/test_listing_privacy.py tests/api/test_seller_listings.py tests/api/test_admin_listings.py`

---

### Task P11: the wizard's control, tiles, copy and preview — amendments A20.1–A20.9

**The family id is derived, never remembered.** Everything below writes `A20`; if the Preconditions snippet printed a different next-free id, substitute it in every entry, every test, every `LOCAL_AMENDMENTS.md` row and every comment before writing a line.

**Files:**
- Modify: `frontend/tests/design-amendments.ts`, `frontend/tests/design-amendments.test.ts`
- Regenerated: `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html`, `frontend/src/logic.js`, `frontend/src/App.vue`, `frontend/src/generated/pseudo.css`
- Modify: `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md`, `frontend/src/app.setup.js`, `frontend/src/logic.test.ts`, `frontend/src/listings/seller.ts`, `frontend/src/listings/seller.test.ts`, `frontend/tests/design-wizard-draft.mjs`, `frontend/tests/screens.ts`, `frontend/tests/reference-baselines.spec.ts`, `frontend/tests/baseline-manifest.json`, `frontend/tests/baseline-manifest.test.ts`, `CLAUDE.md`, `tests/test_docs.py`, `docs/design-reference/requests/2026-09-08-rev3-listing-disclosure-controls.md`

**Interfaces:**
- Consumes: P9's `owner_url` shape and P10's `showIdentifiable` in `serialise_draft`; the A19 lightbox's `openLightbox`/`closeLightbox`/`lightboxVals` (merge precondition 2).
- Produces, in the design's script (and therefore in `logic.js`): `w.showIdentifiable` in the state literal and in `openDraft`'s defaults; a fourth `byStep[7].toggles` entry; `uploads[]` entries carrying `src`, `hasSrc`, `state`, `pill` and `open`; `previewPhotos`.
- Produces, `frontend/src/listings/seller.ts`: `ApiPhoto` gains `src: string | null`, `variant: string`, `state: 'processing' | 'review' | 'confirmed' | 'failed'`, `masks: { id: string; box: [number, number, number, number]; source: string }[]`, `width: number | null`, `height: number | null`; `Draft` gains `showIdentifiable: boolean`; `toWizardDraft` carries all of them.
- Produces, `frontend/src/app.setup.js`: the declared prototype prop `startWizardPhotos` (default `""`), never passed by the app.
- Produces, `frontend/tests/screens.ts`: `wizard-step-6-photos`, `wizard-step-6-review` (the second is reached in P12; its entry is appended here so `screens.ts` moves once).

**The entries.** Counts are measured at the point of application, in list order; `applyAmendments` throws naming the entry otherwise.

| Id | Kind | Anchor (`find`, quoted from the merged design; each measured 1 at its point of application) | What it puts there |
|---|---|---|---|
| A20.1 | script — the `w` state literal | `facilityType: "Standalone", docsLocked: true },\n` (the trailing newline is what makes it unique — `openDraft`'s copy is followed by `, (d && d.w)`) | `… docsLocked: true, showIdentifiable: false },` |
| A20.2 | script — `openDraft`'s defaults | `docsLocked: true }, (d && d.w) \|\| {})` | the same key, so a draft opened from the dashboard carries it |
| A20.3 | script — `byStep[7].toggles` | `{ key: "docsLocked", label: "Keep floor plans and financial packet locked", help: "Buyers see the document titles and can ask for access." }\n      ] }` | a fourth toggle whose `help` is chosen by state — the A12 `practiceName` class of change, a new VALUE in an existing slot |
| A20.4 | script — the `uploads` map | `.map((a, i) => ({ kind: a.kind, name: a.name \|\| (slots[i] ? slots[i].caption : "Photo " + (i + 1)) }))` | `src`, `hasSrc`, `state`, `pill`, `open` per tile |
| A20.5 | template — the step-6 tile band | `height: 68px; border-radius: 8px; background: var(--rf-band); display: grid; place-items: center;` (unique in the file) | an `sc-if u.hasSrc` `<image-slot>` — the detail grid's own tile idiom — beside the band, which moves under `sc-if u.noSrc` |
| A20.6 | template — under the tile name | the tile-name `<div style="font-size: 11px; color: var(--color-steel); margin-top: 4px;">` | the state pill, in the dashboard's `statusPill` idiom |
| A20.7 | template — above the tiles | `Exterior, lobby, treatment area and exam rooms cover most of what buyers ask for.` (the step blurb's own `<p>`) | the once-only line in the same `<p>` style, `sc-if wiz.privacyNote` |
| A20.8 | script — `renderVals()`'s wizard block | `isPreview: !s.wizSubmitted && step === 8,` | `previewPhotos` and `privacyNote` beside it |
| A20.9 | template — step 8 | `<div style="margin-top: 18px; padding: 14px 16px; background: var(--color-off-white); border-left: 3px solid #339dde;` (the `previewNote` card) | a strip of the same `<image-slot>` tiles above it, `sc-if wiz.previewPhotos.length`, and the form's error div (`background: #f5f5f5; border-left: 3px solid var(--vf-text);`) copied into the preview card |

Every `sc-if` carries `hint-placeholder-val="{{ false }}"`; no new `font-family`; no new icon; nothing is invented — each element is copied from the cited design line and the citation goes in its `LOCAL_AMENDMENTS.md` row.

- [ ] **Step 1: RED — `frontend/src/logic.test.ts`**

```ts
describe('A20 — the identifiable-image control and the step-6 tiles', () => {
  // John's directive, 15: "Keep the UI extremely simple ... Do not expose OCR controls, AI
  // confidence scores, bounding boxes by default, technical privacy settings, model configuration,
  // API details, redaction engine details." Every assertion here is either that the control exists
  // in the design's own idiom, or that none of those does.
  it('step 7 carries a fourth toggle whose help changes with its state', () => {
    const logic = mount({ screen: 'seller', sellerView: 'wizard', wizStep: 7 });
    const toggles = logic.renderVals().wiz.toggles;
    expect(toggles.map((t: any) => t.key)).toEqual(['anon', 'revBand', 'docsLocked', 'showIdentifiable']);
    expect(toggles[3].label).toBe('Identifiable image content');
    expect(toggles[3].help).toBe('Not shown to buyers — recommended');
    logic.setW({ showIdentifiable: true });
    expect(logic.renderVals().wiz.toggles[3].help)
      .toBe('Shown to buyers — signage, logos and names may be visible');
  });

  it('a tile with a src renders the design\'s image slot and a state pill', () => {
    const logic = mountWithPhotos();                       // three tiles, the first with a src
    const [first, second] = logic.renderVals().wiz.uploads;
    expect(first.hasSrc).toBe(true);
    expect(first.src).toMatch(/^\/api\/seller\/listings\/[^/]+\/photos\/[^?]+\?v=[0-9a-f]{12}$/);
    expect(first.pill).toBe('Review');
    expect(second.hasSrc).toBe(false);
  });

  it('a tile with no src keeps the badge band exactly as it was', () => {
    const logic = mount({ screen: 'seller', sellerView: 'wizard', wizStep: 6 });   // no adapter
    const [tile] = logic.renderVals().wiz.uploads;
    expect(tile.hasSrc).toBe(false);
    expect(tile.kind).toBe('Photo');
    expect(tile.src).toBe(null);
  });

  it('the once-only line appears above the tiles under NOT_SHOW and never under SHOW', () => {
    const logic = mountWithPhotos();
    expect(logic.renderVals().wiz.privacyNote).toBe(
      "We've automatically hidden information that could identify the hospital. " +
      'Review your images before publishing.');
    logic.setW({ showIdentifiable: true });
    expect(logic.renderVals().wiz.privacyNote).toBe('');
  });
  it('the pills are the four contracted words and nothing technical is rendered', () => {
    const rendered = JSON.stringify(mountWithPhotos().renderVals());
    for (const forbidden of ['confidence', 'ocr', 'vision', 'claude', 'rapidocr', 'zxing',
                             'identity_matches', 'processing_version', 'storage_key']) {
      expect(rendered.toLowerCase()).not.toContain(forbidden);
    }
  });
  it('step 8 shows the buyer-facing variant of every visible photograph', () => {
    const logic = mountWithPhotos({ wizStep: 8 });
    const strip = logic.renderVals().wiz.previewPhotos;
    expect(strip.map((p: any) => p.src)).toEqual(
      logic.renderVals().wiz.uploads.filter((u: any) => u.hasSrc).map((u: any) => u.src));
  });

  it('a PHOTOS_NOT_READY refusal from Submit lands in the design\'s own error slot', async () => {
    const listings = stubAdapter({
      submit: () => Promise.reject(new ListingError('PHOTOS_NOT_READY',
        'Every photograph must finish processing and be reviewed before this listing can be submitted.')),
    });
    const logic = mountWithPhotos({ wizStep: 8, listings });
    await logic.renderVals().wiz.submit();
    expect(logic.renderVals().wiz.error).toBe(true);
    expect(logic.renderVals().wiz.errorText).toContain('must finish processing');
  });

  it('the reference path — no adapter — renders exactly what it rendered before', () => {
    const logic = mount({ screen: 'seller', sellerView: 'wizard', wizStep: 6 });
    expect(logic.renderVals().wiz.uploads.map((u: any) => u.name))
      .toEqual(['Exterior.jpg', 'Lobby.jpg', 'Treatment.jpg']);
    expect(logic.renderVals().wiz.privacyNote).toBe('');
  });
});
```

`mount`, `mountWithPhotos` and `stubAdapter` are `logic.test.ts`'s own existing helpers from the A16 blocks; `mountWithPhotos` is the one addition — `mount` with an adapter whose draft carries three tiles, the first with a `src`, a `state` of `review` and one auto mask — and it is written beside them.

- [ ] `cd frontend && npx vitest run src/logic.test.ts` — RED.

- [ ] **Step 2: RED — `frontend/tests/design-amendments.test.ts`**

- [ ] Extend `AMENDMENT_IDS` after A19's last entry with `'A20.1' … 'A20.9'`, each with the comment naming John's directive sentence it serves.
- [ ] Raise `toHaveLength(<current>)` by nine.
- [ ] Add one case per surface: the fourth toggle exists exactly once; the step-6 band has both branches; the once-only string appears exactly once; the preview strip appears exactly once; **and a census case** — the amended file contains none of `confidence`, `bounding`, `ocr`, `model`, `engine` in any seller-visible string (directive 15).
- [ ] `npx vitest run tests/design-amendments.test.ts` — RED on the id list, the count and every new case.

- [ ] **Step 3: GREEN — the nine entries**

Written into `frontend/tests/design-amendments.ts` immediately after A19's last entry, definition order matching list order, each carrying John's directive sentence as its `ruling`:

```ts
/** A20 — the identifiable-image control and the seller's review surface (John's implementation
 *  directive, 2026-09-09). Ruling, quoted on every entry of this family and in every
 *  LOCAL_AMENDMENTS.md row of it:
 *
 *    "The seller should have ONE simple listing-level control: IDENTIFIABLE IMAGE CONTENT
 *     [ SHOW ] [ NOT SHOW ] ... DEFAULT: NOT SHOW. The safest privacy state is the default."
 *
 *  Composed from the design's own idioms and nothing else (spec C.9): the step-7 toggle is the
 *  fourth entry of a list of three, rendered by the checkbox+label+help markup already there; the
 *  tile thumbnail is the detail grid's own <image-slot>; the pill is the dashboard's statusPill;
 *  the preview strip is the same slot again. No new element, no new colour, no new font.
 */
export const IDENTIFIABLE_RULING =
  'The seller should have ONE simple listing-level control: IDENTIFIABLE IMAGE CONTENT ' +
  '[ SHOW ] [ NOT SHOW ] ... DEFAULT: NOT SHOW. The safest privacy state is the default.';

export const A20_1 = {
  id: 'A20.1', date: '2026-09-09', ruling: IDENTIFIABLE_RULING, count: 1,
  find: 'facilityType: "Standalone", docsLocked: true },\n',
  replace: 'facilityType: "Standalone", docsLocked: true, showIdentifiable: false },\n',
};

export const A20_2 = {
  id: 'A20.2', date: '2026-09-09', ruling: IDENTIFIABLE_RULING, count: 1,
  find: 'docsLocked: true }, (d && d.w) || {})',
  replace: 'docsLocked: true, showIdentifiable: false }, (d && d.w) || {})',
};

export const A20_3 = {
  id: 'A20.3', date: '2026-09-09', ruling: IDENTIFIABLE_RULING, count: 1,
  find: '{ key: "docsLocked", label: "Keep floor plans and financial packet locked", '
      + 'help: "Buyers see the document titles and can ask for access." }\n      ] }',
  replace: '{ key: "docsLocked", label: "Keep floor plans and financial packet locked", '
      + 'help: "Buyers see the document titles and can ask for access." },\n'
      + '        { key: "showIdentifiable", label: "Identifiable image content", '
      + 'help: w.showIdentifiable ? "Shown to buyers \u2014 signage, logos and names may be visible" '
      + ': "Not shown to buyers \u2014 recommended" }\n      ] }',
};

export const A20_4 = {
  id: 'A20.4', date: '2026-09-09', ruling: IDENTIFIABLE_RULING, count: 1,
  find: '.map((a, i) => ({ kind: a.kind, name: a.name || (slots[i] ? slots[i].caption : "Photo " + (i + 1)) }))',
  replace: '.map((a, i) => ({ kind: a.kind, name: a.name || (slots[i] ? slots[i].caption : "Photo " + (i + 1)),'
      + ' src: a.src || null, hasSrc: !!a.src, noSrc: !a.src, state: a.state || "processing",'
      + ' pill: ({ processing: "Processing\u2026", review: "Review", confirmed: "Confirmed", failed: "Failed" })'
      + '[a.state || "processing"], open: this.openPhotoReview(a.id) }))',
};
```

`A20_3`'s `help` reads `w.showIdentifiable` — a state-dependent value in an existing slot, which is exactly what A12's `practiceName` established as legal inside a ruled amendment. `A20_4`'s `open` is a bound handler A20.10 defines in P12; until then it is `undefined` on every tile and no template reads it, which the citation case and `logic.test.ts`'s reference-path case both confirm.

**`A20_4` reads `a.src` and `a.state` off the draft's own asset entries, and Task P9 Step 6 is what puts them there** — `photo_tiles` emits `src`, `variant`, `state`, `masks`, `width` and `height` per tile, and `frontend/src/listings/seller.ts`'s `toWizardDraft` carries them into `wizAssets` unchanged. On the REFERENCE side there is no adapter and no draft, so `a.src` is `undefined`, `hasSrc` is false, and every tile keeps the badge band it has today: that is why no step-6 pixel moves and why `logic.test.ts`'s reference-path case can assert exactly the three fixture names it asserted before.

**Every one of these strings is re-measured against the merged file before it is written** — the actual `find` of each entry, not a paraphrase of it. Each was counted at `2510278` and each was 1; the two merges may have moved them:

```bash
python3 - <<'MEASURE'
import pathlib
A = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html").read_text()
FINDS = {
    # id: (the entry's own `find`, byte for byte, and what it counted at 2510278)
    "A20.1": ('facilityType: "Standalone", docsLocked: true },\n', 1),
    "A20.2": ('docsLocked: true }, (d && d.w) || {})', 1),
    "A20.3": ('{ key: "docsLocked", label: "Keep floor plans and financial packet locked", '
              'help: "Buyers see the document titles and can ask for access." }\n      ] }', 1),
    "A20.4": ('.map((a, i) => ({ kind: a.kind, name: a.name || '
              '(slots[i] ? slots[i].caption : "Photo " + (i + 1)) }))', 1),
    "A20.5": ('height: 68px; border-radius: 8px; background: var(--rf-band); '
              'display: grid; place-items: center;', 1),
    "A20.6": ('font-size: 11px; color: var(--color-steel); margin-top: 4px;', 1),
    "A20.7": ('Exterior, lobby, treatment area and exam rooms cover most of what buyers ask for.', 1),
    "A20.8": ('isPreview: !s.wizSubmitted && step === 8,', 1),
    "A20.9": ('<div style="margin-top: 18px; padding: 14px 16px; '
              'background: var(--color-off-white); border-left: 3px solid #339dde;', 1),
}
for name, (find, expected) in FINDS.items():
    got = A.count(find)
    print(f"{name:6s} count={got}  {'OK' if got == expected else 'MOVED -- NEEDS_CONTEXT'}")
# The two traps these anchors were chosen around, printed so a reader can see they are still traps.
print("A20.1 WITHOUT its trailing newline:",
      A.count('facilityType: "Standalone", docsLocked: true },'), "-- expected 2, which is why the newline is in the find")
print("the form error div's own style string:",
      A.count('background: #f5f5f5; border-left: 3px solid var(--vf-text);'),
      "-- expected 9, which is why A20.9 anchors on the previewNote card and inserts the div relative to it")
MEASURE
```

A `find` that is not 1 at its point of application is `NEEDS_CONTEXT`, not a looser anchor.

- [ ] **Step 4: regenerate**

```bash
cd frontend && npm run gen:design      # expect "<n> amendments applied"
python3 ../scripts-local/report.py     # not a step: the re-port snippet is the one in the lightbox plan, Task L2 Step 5
npm run gen:app
npx vitest run tests/design-amendments.test.ts tests/app-generated.test.ts src/logic.test.ts
```

- [ ] `git diff --stat frontend/src/logic.js frontend/src/App.vue frontend/src/generated/pseudo.css` — all three move; none is hand-edited.

- [ ] **Step 5: the prototype prop and the adapter**

- [ ] `frontend/src/app.setup.js` declares `startWizardPhotos` (default `""`) — prop parity, enforced by `app-generated.test.ts`; the app never passes it, and `frontend/tests/reference-server.mjs` injects it from `?props=` as it does the other seven.
- [ ] `frontend/src/listings/seller.ts` — `ApiPhoto` and `Draft` gain the fields listed in the Interfaces block; `toWizardDraft` carries them; `frontend/src/listings/seller.test.ts` gains a case per field and one asserting `STEP_FIELDS[7]` includes `showIdentifiable` and `toWizardState` round-trips it.
- [ ] `frontend/tests/design-wizard-draft.mjs` — the harness draft stub's three tiles carry `state: "review"` and **no `src`**, so the reference and the app render the same tiles and no oracle moves for a reason other than the ruled ones.

- [ ] **Step 6: the two new approved states**

- [ ] `frontend/tests/screens.ts` — append `wizard-step-6-photos` and `wizard-step-6-review`, each entry starting its line with `{ name: '` (the count regex reads that), reached on both targets through `?props=startWizardPhotos=…` on the reference and the D6 stub on the app, each waiting for the tile `<img>`'s `complete && naturalWidth > 0` and ending with `atTop`.
- [ ] `frontend/tests/reference-baselines.spec.ts` — both names added to `placeholderRings`.
- [ ] `frontend/tests/cross-plan-deltas.test.ts`'s `SCREENS.slice(0, 28)` is unaffected: the two are appended.

- [ ] **Step 7: `LOCAL_AMENDMENTS.md`, and every citation recomputed**

- [ ] Nine rows, in apply order, each quoting `IDENTIFIABLE_RULING` byte for byte and citing the design line it lands on.
- [ ] A20's template insertions move every `V3:<line>` citation below the first of them. Run `npx vitest run tests/design-amendments.test.ts` and let the citation case name each stale row; recompute all of them.

- [ ] **Step 8: `CLAUDE.md` and the doc pins**

- [ ] The "Source of truth for the UI" paragraph gains one clause for A20, in the voice of the A14/A15 clauses, naming John's directive and what the family composes.
- [ ] Both derived counts rewritten from the Preconditions snippet's fresh output: `<Word> families, <n> entries` and `A1's 24 derived edits plus <n> literals`.
- [ ] The Layout line's approved-state count rewritten from `grep -c "^  { name: '" frontend/tests/screens.ts`.
- [ ] `tests/test_docs.py`'s `number_words` extended if the family count outruns it.
- [ ] `docs/design-reference/requests/2026-09-08-rev3-listing-disclosure-controls.md` gains a fifth "What Rev 3 must design" item — the Identifiable image content switch and the review dialog as composed here — through the seller spec's §14 mechanism, in this commit.
- [ ] `poetry run pytest tests/test_docs.py -q -W error` — GREEN.

- [ ] **Step 9: the oracles, and the one row that moves**

```bash
cd frontend
npm run test:visual:baselines
npm run test:e2e
npx vitest run tests/baseline-manifest.test.ts
```

- [ ] **Expect exactly one failure**, `every frozen baseline still hashes to its recorded SHA-256`, and in its diff **only `wizard-step-7`**. That row moves because the fourth toggle is design and the pixel oracle compares the app to the reference, which has no adapter to gate on — the ruling itself names it as a new approved state (spec §I, "Ruling-9 wording"). **Anything else moved is a leak: STOP and diff.**
- [ ] `node tests/baseline-manifest.mjs`, then `git diff --stat frontend/tests/baseline-manifest.json` — exactly one changed line.
- [ ] Extend `frontend/tests/baseline-manifest.test.ts`'s header comment with an A20 paragraph in the same voice, saying which row moved and why, and that the other twelve unchanged is the proof the family reached nothing else.

- [ ] **Step 10: commit**

```
feat(design): A20.1-A20.9 -- the identifiable-image control, the step-6 tiles and the step-8 preview

John's directive 1: one simple listing-level control, IDENTIFIABLE IMAGE
CONTENT [ SHOW ] [ NOT SHOW ], defaulting to NOT SHOW. Nine ruled
amendments compose it from the approved design's own idioms and invent
nothing: the control is a fourth entry in step 7's list of three, rendered
by the checkbox+label+help markup already there; the step-6 tile gains the
detail grid's own <image-slot> when it has a source and keeps its badge
band when it does not; the pill is the dashboard's statusPill; step 8's
preview strip is the same slot again, with the form's own error surface
copied in so a blocked Submit is rendered where the wizard already renders
its errors.

Directive 15: nothing technical is exposed. A census case asserts the
amended design contains no confidence, no bounding box, no OCR text, no
engine and no model name anywhere a seller can see.

wizard-step-7 re-bases -- one row, by ruled design change, re-pinned with
its reason; the other twelve frozen hashes are unchanged, which is the
proof the family reached nothing else. Two approved states are appended,
reached through one new declared prototype prop the app never passes.

Rev 3's request document gains a fifth item for the switch and the review
dialog, through the seller spec's own routing mechanism.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `git add frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md frontend/src/logic.js frontend/src/App.vue frontend/src/generated/pseudo.css frontend/src/app.setup.js frontend/src/logic.test.ts frontend/src/listings/seller.ts frontend/src/listings/seller.test.ts frontend/tests/design-wizard-draft.mjs frontend/tests/screens.ts frontend/tests/reference-baselines.spec.ts frontend/tests/baseline-manifest.json frontend/tests/baseline-manifest.test.ts CLAUDE.md tests/test_docs.py docs/design-reference/requests/2026-09-08-rev3-listing-disclosure-controls.md`

---

### Task P12: the review dialog, and the three routes behind it — amendments A20.10–A20.15

**Files:**
- Modify: `frontend/tests/design-amendments.ts` (+ its test), the V3 file (regenerated), `LOCAL_AMENDMENTS.md`, `logic.js` (re-ported), `App.vue`/`pseudo.css` (regenerated), `frontend/src/logic.test.ts`, `frontend/src/listings/seller.ts` (+ its test), `CLAUDE.md`
- Modify: `app/api/seller_listings.py` (the three routes), `tests/api/test_listing_privacy.py`, `tests/api/test_buyer_photo_delivery.py` (uncomment the four route-table rows)
- Modify: `frontend/tests/listing-flows.spec.ts`

**Interfaces:**
- Consumes: P3's `record.{confirm,reset_confirmation,reset_for_retry}`; P7's `redact.fill_regions` and `aggregate.fillable`; P9's `OWNER_HEADERS` and the owner route; P11's tiles and `startWizardPhotos`; A19's `openLightbox`/`closeLightbox`/`lightboxVals`/`stepLightbox`.
- Produces, `app/api/seller_listings.py`:
  - `POST /listings/{listing_id}/photos/{asset_id}/confirm` → the refreshed draft; 409 `STATE` with the §H message from any state but the two.
  - `POST /listings/{listing_id}/photos/{asset_id}/masks` with body `{"box": [x0, y0, x1, y1]}` → the refreshed draft; 400 `BAD_REQUEST` for a box outside `[0, w] × [0, h]` or under 4 px².
  - `DELETE /listings/{listing_id}/photos/{asset_id}/masks/{mask_id}` → the refreshed draft; 404 for a mask id this asset does not carry.
  - `POST /listings/{listing_id}/photos/{asset_id}/reprocess` → the refreshed draft; 409 `STATE` outside the four error states.
  - `regenerate(conn, store, row) -> bool` — the shared synchronous fill-and-put both mask routes call.
- **Imports this task adds to `app/api/seller_listings.py`**, named so nothing below has to guess: `from app.media import redact`, `from app.privacy import aggregate` (for `fillable` and `rect`), `from app.privacy import redacted_key`. `record`, `sha256_hex`, `OWNER_HEADERS` and `owner_url` are already there from P9.
- Produces, `frontend/src/listings/seller.ts`: `confirmPhoto(id, assetId)`, `addMask(id, assetId, box)`, `removeMask(id, assetId, maskId)`, `reprocess(id, assetId)`, each returning the refreshed `WizardDraft`.
- Produces, in the design's script: `openPhotoReview`, `closePhotoReview`, `photoReviewVals`, the draw-mode handlers, and the dialog markup extending A19's overlay.

- [ ] **Step 1: RED — the three routes**

`tests/api/test_listing_privacy.py` gains scenario L's cases and the state refusals:

The scenario-L case carries the name the spec's §G table and Task P13's map both use — `test_a_manual_mask_regenerates_and_resets_confirmation` — and no other. A test written under one name here and cited under another there is a coverage claim nobody can check by grep:

```python
async def test_a_manual_mask_regenerates_and_resets_confirmation(
    client: Any, seller: dict[str, str], store: Any, conn: Any, confirmed_published_listing: Any
) -> None:
    """Directive 10: "The seller must be able to manually draw/select an additional redaction
    region if the system missed something." Adding one is an ASSET WRITE like a reorder or a
    caption, so A-SL15 applies: a published listing re-enters review and the Browse cache drops."""
    listing_id, asset_id, before = confirmed_published_listing
    response = await client.post(f"/api/seller/listings/{listing_id}/photos/{asset_id}/masks",
                                 json={"box": [10, 10, 200, 90]}, headers=seller)
    assert response.status_code == 200, response.text
    row = record.read(conn, asset_id)
    assert row.processing_status == "READY_FOR_REVIEW" and row.seller_confirmed is False
    assert row.buyer_visible is False and row.redacted_sha256 != before.redacted_sha256
    added = [r for r in row.redaction_regions if r["source"] == "manual"]
    assert len(added) == 1 and added[0]["by"] and added[0]["at"]
    image = Image.open(io.BytesIO(store.get(row.redacted_storage_key))).convert("RGB")
    # `_is_fill`, not `== redact.FILL`: the derivative goes through `encode_webp`'s lossy ladder,
    # so the fill comes back within a few units per channel and never exactly. `tests/media/
    # test_redact.py` measured the worst case at 1 twelve pixels inside a region, and this samples
    # the middle of a 190x80 box for the same reason.
    assert _is_fill(image.getpixel((105, 50)))
    assert _status(conn, listing_id) == "in_review"
    assert response.json()["photos"][0]["state"] == "review"


async def test_removing_a_mask_records_it_and_restores_those_pixels(...): ...
async def test_confirming_a_photograph_that_is_not_ready_is_409(...): ...
async def test_a_box_outside_the_image_is_400_and_writes_nothing(...): ...
async def test_try_again_is_refused_from_a_ready_state_and_accepted_from_the_four_error_states(...): ...
async def test_another_seller_gets_404_on_every_one_of_the_four_routes(...): ...
async def test_every_one_of_the_four_routes_writes_a_listing_privacy_audit_row_with_its_own_reason(...): ...
```

`_is_fill` is `tests/media/test_redact.py`'s tolerance helper, imported here rather than restated (`from tests.media.test_redact import _is_fill`), so one measured number governs every fill assertion in the suite. `confirmed_published_listing` is a fixture in this file — a NOT_SHOW listing with one processed, confirmed, published photograph, yielding `(listing_id, asset_id, row)` where `row` is the `PrivacyRow` as it stood before the test acted — and `_status(conn, listing_id)` is the one-line `SELECT status FROM listing WHERE id = %s` the file's other cases already use.

- [ ] **Step 2: GREEN — the routes**

```python
def regenerate(conn: Any, store: ObjectStore, row: record.PrivacyRow) -> bool:
    """Fill the current region set and replace `redacted.webp`. Synchronous, in the api.

    Redaction is not OCR and not vision: it is one Pillow draw and one re-encode, and the api runs
    neither engine (controller ruling 11). The seller pressed a button and is waiting for the
    picture to change, so a background round trip would be a worse answer, not a safer one.

    False when the encode refuses: the caller writes REDACTION_FAILED and fails closed. The route
    enqueues nothing itself -- `media.sweep`'s rule (3) picks the row up (spec C.5)."""
    display = _fetch(store, row.display_storage_key or "")
    filled = None if display is None else redact.fill_regions(display, aggregate.fillable(row.redaction_regions))
    if filled is None:
        return False
    body, digest = filled
    try:
        store.put(redacted_key(row.listing_id, row.asset_id), body, "image/webp")
    except (BotoCoreError, ClientError) as exc:
        # `ObjectStore.put` catches nothing. A bucket that refuses the write is the same answer as
        # an encode that will not fit: REDACTION_FAILED at the caller, and the sweeper's rule (3)
        # picks the row up.
        log.warning("[seller] derivative write failed: %s", type(exc).__name__)
        return False
    with conn.cursor() as cur:
        cur.execute("UPDATE listing_asset_privacy SET redacted_sha256 = %s, updated_at = now()"
                    " WHERE asset_id = %s", (digest, row.asset_id))
    return True
```

with `add_mask` appending `{"id": str(uuid4()), "polygon": aggregate.rect(box), "source": "manual", "expanded_from": None, "pad_px": 0, "by": str(principal.account_id), "at": now}` — `aggregate.rect` is the public helper P7 makes of `_rect`, so this module never reaches into another's private name — and `remove_mask` rewriting the named region's `source` to `removed-by-seller` (kept for the record, excluded from the fill — `aggregate.fillable` is what excludes it), each then calling `record.reset_confirmation` — which returns False when the row is not in one of the three ready states, and both routes then refuse **409 `STATE`** with the §H message rather than editing the masks of a photograph that has no derivative to regenerate — then `regenerate`, `audit.write(action="listing.privacy", reason="mask_add"|"mask_remove")`, `take_off_market` and, when that returns true, `drop_list_cache` after the commit. `confirm` calls `record.confirm` and refuses `409 STATE` with `This photograph is not ready to be reviewed.` when it returns False; `reprocess` calls `record.reset_for_retry` and `record.enqueue_processing` after the commit.

- [ ] **Step 3: RED then GREEN — the adapter**

`frontend/src/listings/seller.ts` gains the four methods, each `toWizardDraft(await json<Draft>('POST'|'DELETE', …))`, and `seller.test.ts` a case each including the refusal path (a `ListingError` carrying the server's code, which is what the dialog renders in `wizErr`).

- [ ] **Step 4: RED then GREEN — amendments A20.10–A20.15**

| Id | Kind | Anchor | What it puts there |
|---|---|---|---|
| A20.10 | script — class members, beside A19's `openLightbox` | A19's `openLightbox(e, …) {` line | `openPhotoReview`, `closePhotoReview`, `photoReviewVals`, `startDraw`, `moveDraw`, `endDraw`, `removeMask` |
| A20.11 | script — `renderVals()` | A19's `lightbox: this.lightboxVals(),` line | `photoReview: this.photoReviewVals(),` beside it |
| A20.12 | template — inside A19's overlay | A19's counter/caption pill row | the mask outlines (`1px solid var(--border-subtle)`, the design's own line idiom) and the two buttons in the step form's primary/secondary idiom |
| A20.13 | template — the enlarged `<img>` | A19's `<img>` line | the three pointer handlers and the draw rectangle, drawn in the same outline idiom |
| A20.14 | template — the step-6 tile | A20.5's `<image-slot>` block | the transparent absolute `<button aria-label="Review photo: …">` (the A19 hit-target composition) |
| A20.15 | script — the shared `key` closure | A19.9's Escape branch | Escape leaves draw mode before it closes the dialog |

Copy, byte for byte (spec §H, queued for John as D-IDP-13): `✓ Looks good` · `+ Hide something` · `Remove` · `Try again`.

- [ ] **Step 5: regenerate, and the four route-table rows**

```bash
cd frontend && npm run gen:design && npm run gen:app
npx vitest run tests/design-amendments.test.ts tests/app-generated.test.ts src/logic.test.ts src/listings/seller.test.ts
```

- [ ] Uncomment the four rows in `tests/api/test_buyer_photo_delivery.py::LISTING_ROUTES` and run `poetry run pytest tests/api/test_buyer_photo_delivery.py -q -W error` — GREEN, the pin now naming the whole table.

- [ ] **Step 6: the Playwright journey**

`frontend/tests/listing-flows.spec.ts` gains the NOT_SHOW journey end to end against the eager launcher: create a draft → upload a photograph → the tile shows a thumbnail and the **Review** pill (the eager model runs the pipeline before the 201 returns, so "Processing…" is a vitest assertion with a stub adapter, never a Playwright one) → open the dialog → drag a rectangle → the derivative's `?v=` changes → "✓ Looks good" → the pill reads **Confirmed** → Submit succeeds; and the blocked path: Submit before confirming → the design's error surface shows the server's `PHOTOS_NOT_READY` message.

- [ ] **Step 7: `LOCAL_AMENDMENTS.md`, the citations, `CLAUDE.md`**

Six rows in apply order; every `V3:<line>` recomputed again (A20.12 and A20.13 insert inside the overlay, so citations below it move); both derived counts rewritten.

- [ ] **Step 8: the oracles, and the manifest that must NOT move**

```bash
cd frontend && npm run test:visual:baselines && npm run test:e2e
npx vitest run tests/baseline-manifest.test.ts
```

- [ ] **GREEN with zero moves.** The dialog is unmounted in every approved state but `wizard-step-6-review`, and the hit-target is transparent — so a moved hash here is a leak, exactly as it was for A19. STOP and diff.

- [ ] **Step 9: commit**

```
feat(design): A20.10-A20.15 -- the review dialog, and the confirm, mask and retry routes

Directive 10: "present a SIMPLE review experience ... The seller can:
✓ Looks good, or: + Hide something", with the ability to "manually
draw/select an additional redaction region if the system missed
something", to remove an unnecessary mask, and to navigate every image.
The dialog is A19's lightbox with two buttons in the step form's own
button idiom and the mask outlines in the design's own line idiom -- no
new overlay, no new scrim, no new control.

Four routes behind it. A mask is an asset write like a reorder or a
caption, so it regenerates the derivative synchronously (one Pillow draw
and one re-encode; the api runs no engine), resets the confirmation, takes
a published listing off the market and drops the Browse cache -- which is
what stops a live NOT_SHOW listing showing a hidden slot until the seller
confirms. A removed mask is kept in the record as removed-by-seller and
excluded from the fill. Confirming a photograph that is not ready is a 409,
never a way into readiness. Try again is offered only where the retries
are spent.

Zero frozen hashes move: the dialog is unmounted in every approved state
but the new one, and the hit-target is transparent. The listing route
table's pin now names the whole table, the four new rows included.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `git add frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md frontend/src/logic.js frontend/src/App.vue frontend/src/generated/pseudo.css frontend/src/logic.test.ts frontend/src/listings/seller.ts frontend/src/listings/seller.test.ts frontend/tests/listing-flows.spec.ts app/api/seller_listings.py tests/api/test_listing_privacy.py tests/api/test_buyer_photo_delivery.py CLAUDE.md`

---

### Task P13: John's scenarios A–Z, test by test

**Files:**
- Modify: `tests/api/test_listing_privacy.py`, `tests/api/test_buyer_photo_delivery.py`, `tests/tasks/test_media.py`, `tests/media/test_redact.py` (scenario K's three DB-level assertions; its buyer-404 half is the companion case in `test_listing_privacy.py`)
- Modify: `frontend/tests/listing-flows.spec.ts`, `frontend/src/components/ImageSlot.test.ts`, `frontend/src/logic.test.ts`
- Modify: `tests/test_static.py`, `tests/mail/test_templates.py`, `tests/test_storage.py`

**Interfaces:**
- Consumes: everything P1–P12 produced, and `assert_buyer_sees_only_redacted` from P9.
- Produces: no `app/` code. This task adds tests only — the point of it is that every letter of directive §21 and every path of directive §14 is a NAMED test, so a reader can check the coverage claim by reading a list rather than by trusting one.

**The map.** Each row is written, run and read to green before the next is started; a row that fails names a defect in P1–P12 and is fixed there, in a commit of its own, before this task continues.

| § | Scenario | Test | Layer |
|---|---|---|---|
| A | One image + NOT_SHOW | `test_listing_privacy.py::test_one_photograph_under_not_show_is_redacted_for_buyers_after_confirmation` | py |
| B | Multiple images + NOT_SHOW | `::test_five_photographs_are_each_processed_confirmed_and_redacted` | py |
| C | 50+ images + NOT_SHOW | `::test_fifty_two_photographs_under_the_real_upload_limit` | py |
| D | SHOW | `::test_show_runs_the_same_pipeline_and_serves_display` | py |
| E | SHOW → NOT_SHOW | `::test_a_flip_to_not_show_resets_visibility_and_re_checks_every_derivative` | py |
| F | NOT_SHOW → SHOW | `::test_a_flip_to_show_keeps_the_derivatives_and_serves_display` | py |
| G | New image after publication | `::test_a_photograph_added_after_publication_is_a_null_slot_until_confirmed` | py |
| H | Processing failure | `tests/tasks/test_media.py::test_an_undecodable_display_object_fails_closed` | py |
| I | OCR failure | `::test_an_ocr_engine_error_is_processing_failed_never_a_skip` | py |
| J | Vision detection failure | `::test_vision_failed_is_not_vision_unavailable` | py |
| K | Redaction failure | `tests/media/test_redact.py::test_a_derivative_that_will_not_fit_the_ladder_is_redaction_failed` **plus** `test_listing_privacy.py::test_a_redaction_failure_leaves_the_slot_null_to_buyers` | py |
| L | Seller adds manual redaction | `test_listing_privacy.py::test_a_manual_mask_regenerates_and_resets_confirmation` | py |
| M | Publish before processing completes | `::test_submit_decide_and_republish_refuse_while_a_photograph_is_processing` | py |
| N | Original URL requested by buyer | `test_buyer_photo_delivery.py::test_a_buyer_cannot_obtain_the_original_by_any_query_parameter` | py |
| O | Original thumbnail requested by buyer | `::test_the_thumbnail_slot_is_the_same_redacted_url` | py + pw |
| P | Original download endpoint | `::test_no_photo_route_offers_an_attachment_and_the_document_route_refuses_a_photo` | py |
| Q | CDN URL | `::test_photo_responses_are_private_and_uncacheable_by_intermediaries` + `tests/test_static.py::test_public_photos_are_exactly_the_three_design_fixtures` | py |
| R | API response | `::test_buyer_payloads_carry_no_key_no_ocr_no_region` | py |
| S | Mobile client | `listing-flows.spec.ts::"a buyer on the phone frame sees the redacted photograph"` | pw |
| T | Desktop client | `::"a buyer on desktop Browse sees the redacted photograph"` | pw |
| U | Cached image | `test_buyer_photo_delivery.py::test_a_stale_url_after_a_flip_serves_the_redacted_bytes_not_a_304_of_the_original` | py + pw |
| V | Multiple upload batches | `test_listing_privacy.py::test_two_upload_sessions_are_each_processed_and_gated` | py |
| W | Image replacement | `::test_replace_is_delete_then_upload_and_the_new_asset_starts_unprocessed` | py |
| X | Image deletion / re-upload | `::test_deleting_a_confirmed_photograph_removes_its_row_and_objects` | py |
| Y | Listing duplication / draft cloning | `::test_no_clone_path_exists_and_create_starts_private_and_empty` | py |
| Z | Unauthorised seller changing privacy state | `::test_a_non_owner_cannot_change_visibility_and_no_admin_route_exists` | py |

**Scenario K is two tests, and the split is a fixture fact, not a preference.** The spec's §G row names one file and four assertions: `encode_webp` stubbed to `None` gives `REDACTION_FAILED`, `redacted_storage_key` is NULL, the gate refuses, and a buyer GET is 404. The first three are reachable in `tests/media/test_redact.py` — `conn` and `redis` are root fixtures and `store` is one from Task P2 Step 0, and `app/privacy/gate.py::photos_not_ready` is a SQL predicate that needs no client. The fourth is not: `client` is defined in `tests/api/conftest.py` and exists only under `tests/api/`. So the buyer-404 half lives in `tests/api/test_listing_privacy.py::test_a_redaction_failure_leaves_the_slot_null_to_buyers`, each file's docstring names the other, and the acceptance table below cites both. Recorded as a deviation from the spec's single cell; the alternative — promoting `client` to the root conftest — would move a fixture the whole suite depends on for the sake of one assertion.

And directive §14's four paths that are not a scenario: the responsive-image endpoint (`ImageSlot.test.ts::"renders one src and no srcset, sizes, loading or fetchpriority"`, which reads the component source), the signed URL (`test_storage.py::test_no_presigning_exists`), the social/share preview (`test_static.py::test_index_html_carries_no_share_image_no_preload_and_no_manifest` and `tests/mail/test_templates.py::test_no_template_carries_an_img`), and the preloaded image (`logic.test.ts::"no runtime code constructs a photo URL"` — `frontend/src` builds the string `/photos/` nowhere, has no `new Image()` and no `rel="preload"`).

- [ ] **Step 1: scenario C, the one with a real rate limit in it**

Written first, because it is the only scenario that needs a mechanism the others do not and the mechanism is John's own ruling (#12c: real limits are kept, the test resets them):

```python
async def test_fifty_two_photographs_under_the_real_upload_limit(
    client: Any, seller: dict[str, str], buyer: dict[str, str], admin: dict[str, str],
    store: Any, conn: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Directive 21 C, against `LISTING_UPLOAD = (40, 3600)` as it actually is.

    The limit is NOT loosened for this test. The 41st upload is a 429, exactly as it would be for a
    seller, and the counters are cleared between batches by the script that exists for this --
    `scripts/reset_rate_limits.py`, which refuses to run anywhere but ENVIRONMENT=test against a
    loopback Redis, so it can only ever do this here."""
    from scripts.reset_rate_limits import main as reset_rate_limits

    monkeypatch.setattr("app.privacy.record.celery_app.send_task", lambda *a, **kw: None)
    listing_id = await _draft(client, seller)
    for n in range(40):
        created = await client.post(f"/api/seller/listings/{listing_id}/photos",
                                    files={"file": (f"p{n}.jpg", _jpeg_bytes(), "image/jpeg")},
                                    headers=seller)
        assert created.status_code == 201, created.text
    refused = await client.post(f"/api/seller/listings/{listing_id}/photos",
                                files={"file": ("p40.jpg", _jpeg_bytes(), "image/jpeg")}, headers=seller)
    assert refused.status_code == 429 and refused.json()["error"]["code"] == "RATE_LIMITED"

    assert reset_rate_limits([]) == 0
    for n in range(40, 52):
        created = await client.post(f"/api/seller/listings/{listing_id}/photos",
                                    files={"file": (f"p{n}.jpg", _jpeg_bytes(), "image/jpeg")},
                                    headers=seller)
        assert created.status_code == 201, created.text

    for asset_id in _photo_ids(conn, listing_id):
        media.process_photo(str(asset_id), PROCESSING_VERSION)
    assert media.sweep()["enqueued"] == 0                      # nothing was lost

    assert len(gate.photos_not_ready(conn, listing_id)) == 52   # none confirmed yet
    for asset_id in _photo_ids(conn, listing_id):
        confirmed = await client.post(
            f"/api/seller/listings/{listing_id}/photos/{asset_id}/confirm", headers=seller)
        assert confirmed.status_code == 200, confirmed.text
    assert gate.photos_not_ready(conn, listing_id) == []

    await _submit_and_publish(client, seller, admin, listing_id)
    with _count_queries(conn) as counted:
        await client.get("/api/listings", headers=buyer)
    assert counted.statements == 1                              # the aggregate, not 52 lookups
    for n in (1, 26, 52):
        await assert_buyer_sees_only_redacted(client, buyer, seller, admin, store, listing_id, n,
                                              _privacy_of(conn, listing_id, n))
```

`_photo_ids(conn, listing_id)` reads `listing.photos` in order, `_submit_and_publish` is an `async` helper that posts `/submit` as the seller and `/decide` as the admin, and `_count_queries(conn)` is a context manager that installs a psycopg2 cursor factory counting `execute` calls — all three are written beside this case in `tests/api/test_listing_privacy.py`, and all three are used by the scenarios in Step 2.

- [ ] `poetry run pytest tests/api/test_listing_privacy.py -q -W error -k fifty_two` — read it to green. A one-statement assertion that fails means P9's aggregate is not being used; a 429 in the second batch means the reset did not run.

- [ ] **Step 2: scenarios A, B, D, E, F, G, V, W, X, Y, Z**

Each written from the spec's §G table, in that order, each ending with `assert_buyer_sees_only_redacted` where it is a NOT_SHOW scenario. Three of them carry an assertion that is easy to leave out and is the point of the scenario:

- **E** — the row whose `redacted.webp` was deleted from the bucket before the flip: the PATCH's `exists()` pass finds it, clears its key and hash, applies the reset rule and re-enqueues it. With the store unconfigured the same PATCH is `503 STORAGE_UNAVAILABLE` and **no column changes**.
- **G** — at no point does any buyer GET return display or original bytes; asserted after every step of the sequence, not only at the end.
- **Y** — no route path in `create_app().routes` contains `clone`, `duplicate` or `copy`; `POST /api/seller/listings` starts at `NOT_SHOW` with no assets; the seeder's UPSERT SQL names neither `listing_asset` nor `listing_asset_privacy` (a source grep); `claim_from_seed` changes no privacy column.

- [ ] **Step 3: scenarios S, T, U's Playwright arms and O's**

In `frontend/tests/listing-flows.spec.ts`, against the eager launcher: publish a NOT_SHOW listing through the harness, then at 390 × 800 read the mobile card's `<img>` URL and fetch it with `page.request`, asserting its sha256 equals the row's `redacted_sha256`; the same at 1280 × 800 for the Browse card, the docked panel's current photograph and the A19 lightbox's enlarged `<img>`; and for U, reload after a flip and assert the `<img>` request hits the network and receives the redacted bytes.

- [ ] **Step 4: the whole suite, and the coverage claim**

```bash
poetry run pytest -q -W error --cov=app --cov=scripts --cov=tests/e2e --cov-branch --cov-fail-under=100
cd frontend && npm run typecheck && npm test && npm run build
cd frontend && npm run test:visual:baselines && npm run test:e2e
```

- [ ] **Step 5: commit**

```
test(privacy): John's scenarios A-Z, and directive 14's four remaining paths

Directive 21 lists twenty-six scenarios and a standing rule for every
NOT_SHOW one: assert the buyer receives the redacted representation and
cannot access the original. One shared helper asserts both -- the bytes,
every query parameter, the owner and reviewer routes as a buyer, both
payloads, and an anonymous request -- so a scenario cannot pass by
asserting half of it, and the helper is itself tested against a SHOW
listing it must refuse.

Scenario C runs against the real 40-per-hour upload limit: the 41st upload
is a 429 exactly as it would be for a seller, and the counters are cleared
between batches by scripts/reset_rate_limits.py, which refuses to run
anywhere but a test environment on a loopback Redis. The limit is not
loosened. Fifty-two photographs, fifty-two offenders at the gate before
confirmation, none after, and the list route still one statement.

Directive 14's four paths that are not scenarios each name a test too: the
responsive endpoint that does not exist, the signed URL that does not
exist, the share preview that does not exist, and the preloaded image no
runtime code can construct.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `git add tests/api/test_listing_privacy.py tests/api/test_buyer_photo_delivery.py tests/tasks/test_media.py tests/media/test_redact.py tests/test_static.py tests/mail/test_templates.py tests/test_storage.py frontend/tests/listing-flows.spec.ts frontend/src/components/ImageSlot.test.ts frontend/src/logic.test.ts`

---

### Task P14: the documents, the runbook, the honesty test, and the hand-back

**Files:**
- Create: `docs/RUNBOOK-image-privacy.md`
- Modify: `DEPLOY.md`, `CLAUDE.md`, `tests/test_docs.py`, this plan

**Interfaces:**
- Consumes: every documentation row P1, P4, P6 and P8 wrote.
- Produces: `tests/test_docs.py::test_the_identifiability_copy_makes_no_detection_claim`, and the operator's page.

- [ ] **Step 1: RED — the honesty test**

```python
# --- Directive 23: no claim of perfect detection, anywhere ------------------------------------
#
# John: "Do NOT document or advertise: 'AI guarantees 100% that the hospital cannot be identified.'
# That claim is technically unjustifiable." Two patterns, and the scope of each is deliberate.
#
# The stem and the percentage sign are scanned in PROSE -- every tracked Markdown file with its
# fenced code blocks and inline code spans removed -- and in the three copy surfaces below, scanned
# whole. Not in every tracked text file: `detected_regions = %s` in a SQL statement is a psycopg2
# placeholder beside a column name, not a claim, and a rule that fired on it would be a rule nobody
# could keep. A claim is made in prose and in copy, and that is where this looks.
IDENTIFIABILITY_PROSE_PATTERNS = {
    r"guarant.{0,80}?(identif|redact|hidden|detect)": "no claim of certain detection (directive 23)",
    r"(identif|redact|hidden|detect).{0,80}?guarant": "no claim of certain detection (directive 23)",
    r"%.{0,40}?(detect|accura)": "no percentage claim about detection or accuracy (directive 23)",
    r"(detect|accura).{0,40}?%": "no percentage claim about detection or accuracy (directive 23)",
}
#: Seller- and buyer-facing copy, and the mail templates -- scanned whole, and additionally for the
#: four phrases that overstate what the system can know.
IDENTIFIABILITY_COPY_FILES = ("app/privacy/gate.py", "app/mail/templates.py",
                              "frontend/tests/design-amendments.ts")
IDENTIFIABILITY_COPY_PHRASES = ("cannot be identified", "fully protected", "AI-verified", "certified")
#: This file spells the patterns it forbids, and John's own directive quotes the claim in order to
#: ban it. Neither can check itself.
IDENTIFIABILITY_EXEMPT = {"tests/test_docs.py",
                          "docs/superpowers/specs/2026-09-09-image-identifiability-directive.md"}

_FENCE = re.compile(r"^```.*?^```", re.M | re.S)
_SPAN = re.compile(r"`[^`\n]*`")


def _prose(text: str) -> str:
    """Markdown with its code removed: a fenced block is an implementation, and an inline span is a
    quoted identifier. Neither is a claim."""
    return _SPAN.sub(" ", _FENCE.sub(" ", text))


def test_the_identifiability_copy_makes_no_detection_claim():
    """Directive 23, pinned. The allowed vocabulary is what the copy actually uses -- "automatically
    hidden", "may be visible", "review your images" -- and the engineering stance the directive
    names is what it reflects: maximum automated detection, deterministic processing, seller visual
    confirmation, a mandatory publication gate, fail-closed security."""
    hits = []
    for name, text in tracked_text_files():
        if name in IDENTIFIABILITY_EXEMPT:
            continue
        if name.endswith(".md"):
            body = _prose(text)
        elif name in IDENTIFIABILITY_COPY_FILES:
            body = text
        else:
            continue
        for pattern, why in IDENTIFIABILITY_PROSE_PATTERNS.items():
            for match in re.finditer(pattern, body, re.I | re.S):
                hits.append(f"{name}: {body[match.start():match.end()][:60]!r} -- {why}")
    for name in IDENTIFIABILITY_COPY_FILES:
        body = (ROOT / name).read_text()
        hits += [f"{name}: {phrase!r} overstates what the system can know"
                 for phrase in IDENTIFIABILITY_COPY_PHRASES if phrase in body]
    assert hits == [], hits


def test_the_honesty_rule_bites_on_the_exact_sentence_the_directive_forbids():
    """A rule nobody can trip is a spelling check. This is the sentence, verbatim from directive 23."""
    forbidden = "AI guarantees 100" + "% that the hospital cannot be identified."
    assert any(re.search(pattern, forbidden, re.I | re.S) for pattern in IDENTIFIABILITY_PROSE_PATTERNS)
```

- [ ] `poetry run pytest tests/test_docs.py -q -W error -k identifiability` — run it and read every hit. A hit in a file this sub-project wrote is a sentence to rewrite; a hit in a file it did not is reported as `NEEDS_CONTEXT` with the file and the line rather than fixed by widening the exemption set.

- [ ] **Step 2: the runbook**

Create `docs/RUNBOOK-image-privacy.md` — the operator's page, in `docs/RUNBOOK-identity.md`'s voice. It opens with two relative Markdown links, to `../docs/superpowers/specs/2026-09-09-image-identifiability-protection-design.md` and `../docs/superpowers/plans/2026-09-09-image-identifiability-protection.md` (written from the runbook's own directory, so the link targets written as `superpowers/specs/…` and `superpowers/plans/…` (relative to `docs/`, the runbook's own directory)), and `DEPLOY.md` links to it beside `docs/RUNBOOK-identity.md`. Those three links are what `tests/test_docs.py::test_relative_markdown_links_resolve` actually covers for this sub-project — no other file it writes contains a Markdown link.

- **A photograph that will not process.** What the seller sees (the tile reads *Processing…* while a retry is pending, *Failed* once the attempts are spent), what to read (`SELECT processing_status, attempts, last_error, updated_at FROM listing_asset_privacy WHERE asset_id = …`), and what each reason code means: `UNDECODABLE`, `DISPLAY_MISSING`, `OCR_UNAVAILABLE`, `OCR_ERROR`, `BARCODE_UNAVAILABLE`, `BARCODE_ERROR`, `VISION_FAILED`, `VISION_REFUSED`, `ENCODE_TOO_LARGE`, `STORAGE_ERROR`, `TASK_LOST`.
- **The retry ladder, as it actually runs.** Three attempts, and the delays between them are 30 seconds and then 2 minutes: `record.BACKOFF` is `(30, 120, 600)` but `_retry_or_exhaust` re-enqueues only while `attempts < MAX_ATTEMPTS`, so the third failure exhausts to `REVIEW_REQUIRED` instead of waiting 10 minutes. An operator who has waited two and a half minutes and sees `REVIEW_REQUIRED` has seen the whole ladder, not two thirds of it. (`media.sweep`'s rule (3) is the longer window — a row whose re-enqueue was lost is picked up 12 minutes after its last write.)
- **A row stuck in `PROCESSING`.** The one thing this pipeline deliberately does not swallow is an exception outside the failure set above: the task fails, `acks_late` acks the message anyway, the row stays `PROCESSING`, and `media.sweep`'s rule (2) marks it `REPROCESS_REQUIRED` with `TASK_LOST` and re-enqueues it within 6 minutes. Nothing to do; check the worker log for the exception class if it repeats.
- **What to do.** Ask the seller to press *Try again* first — it is the supported path and it resets the attempt count. `scripts/reprocess_photos.py --listing <id>` is the operator's equivalent for a photograph that is READY and stale. Nothing else touches `listing_asset_privacy` by hand: the CHECKs will refuse most mistakes and the ones they do not are worse.
- **Why a photograph is a blank slot to buyers, and why that is correct.** A failed photograph is not published; the listing keeps its other photographs; the gate refuses a new publication. Directive 19: never a fallback to the original.
- **The worker is down.** Uploads sit at `UPLOADED`, the gate blocks publication, the tile reads *Processing…*, and `media.sweep` catches every row within two minutes of the worker returning. Nothing is lost and nothing leaks.
- **`ANTHROPIC_API_KEY` is unset.** Every photograph completes with `vision: unavailable`. That is a supported state, not an incident.
- **Worker sizing, before the `media` queue is enabled on QA.** `railway ssh --service worker`, measure one prefork child's RSS with the OCR model loaded (`ps -o rss= -p <pid>`), record the figure here, and confirm the worker plan's memory is at least twice that plus 300 MB of headroom. `CELERY_CONCURRENCY` stays 2 unless the measurement says otherwise.
- **Rotating the key.** `railway variable set ANTHROPIC_API_KEY=… --service worker --environment <env>`; never printed, never pasted into a log, never into chat.
- **What the seeded demo hospitals are.** `SHOW`, written by `scripts/seed_listings.py`'s UPSERT in both halves (D-IDP-2). A seed photograph is a path entry with no `listing_asset` row and therefore no derivative, so `SHOW` is the only state under which it can be served at all; a re-seed rewrites it, and a listing a seller has claimed keeps whatever they set. If a seeded listing will not publish with `SEED_UNPROCESSED`, its visibility has been changed to `NOT_SHOW` — that is the gate working, and the answer is either flipping it back or D-SL25's materialisation, never a hand-edited row.

- [ ] `DEPLOY.md` links it beside `docs/RUNBOOK-identity.md`, and `poetry run pytest tests/test_docs.py -q -W error` confirms the relative link resolves.

- [ ] **Step 3: `CLAUDE.md`**

One clause in the "Non-negotiables"/"Legally load-bearing" neighbourhood, in the page's own voice, recording the three facts a future session must not rediscover: the buyer's photograph is chosen by `app/privacy/delivery.py::buyer_variant` and by nothing else; `ANTHROPIC_API_KEY` is worker-only and never leaves Railway; and no copy anywhere may claim certain detection, pinned by `tests/test_docs.py::test_the_identifiability_copy_makes_no_detection_claim`.

- [ ] **Step 4: the plan's own record**

Append the controller's record at hand-back — the commits, the measured image size, the measured OCR child RSS, the counts, what moved in the oracles — in the style of the metro, Give and lightbox plans' closing records.

- [ ] **Step 5: the full gate**, then the commit:

```
docs(privacy): the operator's runbook, the honesty pin, and CLAUDE.md's three facts

Directive 23: engineer for maximum automated detection, deterministic
processing, seller visual confirmation, a mandatory publication gate and
fail-closed security -- and never claim more. tests/test_docs.py now pins
exactly that, over the prose of every tracked Markdown file (code fences
and inline spans removed, because a placeholder beside a column name is
not a claim) and over the three copy surfaces whole. Its companion case
asserts the rule bites on the sentence the directive quotes, so it is a
rule and not a spelling check.

docs/RUNBOOK-image-privacy.md is the operator's page: what each reason
code means, why Try again is the supported path, why a failed photograph
is a blank slot and not a fallback, what happens while the worker is down,
and the worker sizing measurement to take before the media queue is
enabled on QA.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `git add docs/RUNBOOK-image-privacy.md DEPLOY.md CLAUDE.md tests/test_docs.py docs/superpowers/plans/2026-09-09-image-identifiability-protection.md`

---

## The gate, then QA

All four, in order (CLAUDE.md § Non-negotiables), on the final tree of the worktree. A gate log must show `N passed`; a seconds-long "green" e2e is the API web server failing to start.

1. - [ ] `docker compose -f docker-compose.dev.yml up -d` (the one shared stack) with this worktree's environment exported
   - [ ] `poetry run ruff check app tests scripts`
   - [ ] `poetry run mypy app --strict`
   - [ ] `poetry run mypy scripts/migrate.py scripts/bootstrap_admin.py scripts/seed_persona.py scripts/reset_rate_limits.py scripts/prepare_photos.py scripts/seed_listings.py scripts/census_load.py scripts/reprocess_photos.py --strict`
   - [ ] `poetry run pytest -q -W error --cov=app --cov=scripts --cov=tests/e2e --cov-branch --cov-fail-under=100`
   - [ ] `bash tests/scripts/test_start_sh.sh`
   - [ ] `cd frontend && npm run typecheck && npm test && npm run build`
2. - [ ] `lsof -nP -iTCP:5573,5574,5575,8147 -sTCP:LISTEN` — nothing listening
   - [ ] `cd frontend && npm run test:visual:baselines && npm run test:e2e` — visual + DOM oracle + smoke, green
   - [ ] `npx vitest run tests/baseline-manifest.test.ts` — green against P11's one-row re-pin, with **zero** further moves
   - [ ] `docker build -t pm-final .` — the image builds with the two apt packages, and its size matches P4's measurement
3. - [ ] Controller: `railway status` → **Project: Practice Match**; `scripts/deploy.sh QA .worktrees/feat-image-identifiability` (SOURCE_DIR is mandatory for a worktree, P14/DEPLOY.md); `railway variable set ANTHROPIC_API_KEY=… --service worker --environment QA` **only if John has ruled D-IDP-1(a)** — with it unset the whole flow works and every photograph records `vision: unavailable`; then the click-through below.
4. - [ ] Controller, after merge and the lockstep bump: `scripts/deploy.sh production && scripts/verify-deploy.sh production`. Production runs `SITE_MODE=coming_soon` until launch, so the change is not publicly visible there; the smoke is still required and the hand-back says so.

**Before the `media` queue carries real work on QA:** take the worker-sizing measurement from `docs/RUNBOOK-image-privacy.md` (one prefork child's RSS with the OCR model loaded, `railway ssh --service worker`), record it in `DEPLOY.md`, and confirm the plan's memory is at least twice that plus 300 MB. This is a deployment prerequisite, not a nicety: two children each load the model.

---

## The QA click-through (controller — John does not run the app locally)

On https://qa.foundation.vin, signed in as the seller persona, then as a buyer, then as staff.

1. **The control exists and is off.** Seller → a new listing → step 7: a fourth row, *Identifiable image content*, switched **off**, help reading "Not shown to buyers — recommended". Turn it on: the help becomes "Shown to buyers — signage, logos and names may be visible". Turn it back off.
2. **Upload.** Step 6 → *Add files* → a photograph with a visible practice sign (use one of John's own hospital photographs). The tile appears with a pill. Reload after a few seconds: the pill reads **Review** and the tile shows a thumbnail with the sign covered by a solid navy block.
3. **The once-only line** is above the tiles: "We've automatically hidden information that could identify the hospital. Review your images before publishing." Turn step 7's switch on and back: the line disappears and returns.
4. **Review.** Click the tile: the dialog opens on the enlarged derivative with outlines around each mask, `<` and `>` if there are several, an X, and two buttons — **✓ Looks good** and **+ Hide something**.
5. **Hide something.** Press it and drag a rectangle over something the system missed. The picture updates with that area filled; the pill returns to **Review**.
6. **Remove.** Click an existing mask outline → **Remove** → that area comes back.
7. **Looks good.** Press it: the pill reads **Confirmed**.
8. **The gate.** Upload a second photograph and press **Submit for review** before confirming it: the wizard's own error surface shows "Every photograph must finish processing and be reviewed before this listing can be submitted." Confirm it, submit again: accepted.
9. **The reviewer can look.** Staff → Admin › Listings → the submitted listing: the reviewer can view each photograph before deciding. Publish it.
10. **The buyer.** Sign in as a buyer → Browse → the listing's card, its detail grid, the docked panel's photograph and the A19 lightbox: **every one of them shows the redacted picture**. Copy the photo URL from the browser's network panel, open it in a new tab with `?variant=original` appended: the same redacted picture.
11. **The flip.** Seller → step 7 → switch **on** → save. The listing re-enters review; staff republish. As a buyer, reload: the picture is now the unredacted one and its URL's `?v=` has changed. Switch back off: the listing re-enters review again, every photograph needs confirming again, and after republishing the buyer sees the redacted picture.
12. **A photograph added after publication.** On the published listing, upload a third photograph. The listing re-enters review. Before it is confirmed, check the buyer's detail grid: that slot is the design's empty placeholder — **never the new photograph**.
13. **Delete.** Delete a photograph; the slot goes; the buyer's grid follows after the republish.
14. **Screenshots for the hand-back:** step 7's fourth row in both states; the step-6 tiles with pills; the review dialog with an outline; the drag in progress; the blocked Submit; the reviewer's view; the buyer's Browse card, detail grid and lightbox showing the redacted picture; the same photograph before and after the flip.

---

---

## Acceptance — John's section 22, criterion by criterion

His list is twenty-seven checkboxes, and "The implementation is NOT COMPLETE unless ALL of the following are true." Each one names the task that makes it true and the test that proves it; the hand-back reports this table with each row's test result beside it.

| Criterion | Task | The test that proves it |
|---|---|---|
| One simple SHOW / NOT SHOW control exists | P1, P10, P11 | `test_listing_privacy_schema.py::test_the_listing_carries_one_authoritative_visibility_defaulting_to_not_show`; `logic.test.ts` "step 7 carries a fourth toggle" |
| NOT_SHOW is the default | P1 | the same schema case; scenario Y |
| The setting applies to every image in the listing | P9, P10 | `test_delivery.py` (every cell); `test_gate.py` over every entry |
| Every image is automatically scanned | P2, P8 | `test_listing_assets.py::test_an_upload_stores_the_original_and_the_display_and_enqueues_one_task`; the sweeper's rule (1) |
| OCR is performed on every image | P4, P8 | scenario I — an engine error is a failure, never a skip |
| Seller identity data is matched against OCR | P5 | `test_identity.py`'s table, every row |
| Visual identity detection supplements OCR | P6, P8 | scenario J — unavailable is not failed, and vision never short-circuits the rest |
| Identifying regions can be automatically redacted | P7 | `test_aggregate.py`, `test_redact.py` |
| Redaction is irreversible in the buyer-facing derivative | P7 | `test_redact.py::test_two_photographs_that_differ_only_under_the_mask_produce_identical_bytes` |
| Seller can manually add a redaction | P12 | scenario L |
| Seller reviews the processed gallery | P11, P12 | `wizard-step-6-photos`, `wizard-step-6-review`; the Playwright journey |
| Seller confirmation is mandatory for NOT_SHOW | P3, P10 | `test_gate.py::test_under_not_show_only_a_confirmed_photograph_with_a_derivative_passes` |
| Publishing is blocked until all images are ready | P1, P10 | scenario M, and the trigger's own schema cases |
| Processing failures fail closed | P3, P8 | scenarios H, I, J, K; `test_media.py`'s ladder case |
| Original images remain private | P2, P9 | `test_buyer_photo_delivery.py::test_the_original_key_is_read_only_where_the_spec_says`; scenario N |
| Redacted images are used for buyer delivery | P9 | `assert_buyer_sees_only_redacted`, in every NOT_SHOW scenario |
| Buyer APIs cannot leak originals | P9 | scenario R |
| Thumbnail APIs cannot leak originals | P9, P13 | scenario O |
| CDN cannot leak originals | P9 | scenario Q, and `test_storage.py::test_no_presigning_exists` |
| Download endpoints cannot leak originals | P9 | scenario P |
| Newly uploaded images cannot bypass the workflow | P2, P10 | scenario G — a null slot from the moment the photograph exists |
| SHOW/NOT_SHOW state is enforced server-side | P9 | `test_delivery.py`; `::test_the_v_parameter_selects_nothing` |
| Audit records exist | P1, P10, P12 | the privacy row's own columns; the `listing.privacy` audit cases |
| Automated tests cover all critical paths | P13 | the A–Z map, plus the coverage gate at 100 for lines and branches |
| Existing image-upload functionality remains intact | P2 | `tests/api/test_listing_assets.py` green, with only the two header pins re-recorded |
| Existing listing functionality remains intact | P9, P10 | `test_listings.py`, `test_seller_listings.py`, `test_admin_listings.py` green; the frozen oracles unchanged but `wizard-step-7` |
| No duplicate privacy controls create contradictory states | P10 | one column, one writer; `::test_admin_cannot_change_visibility_by_any_route`; `buyer_visible` is derived readiness and never a seller choice |

## Open questions — D-IDP-1 to D-IDP-16, with the default this plan applies

Each is the spec's; each is applied as written until John rules otherwise. The ones marked **(Q)** are queued for him with the hand-back.

| Id | Question | Default applied here |
|---|---|---|
| **D-IDP-1 (Q)** | Vision through the Anthropic API sends the un-redacted photograph to a third party, with `ANTHROPIC_API_KEY` a worker-only Railway secret. Model default `claude-opus-5`; per-image cost about $0.04 (an estimate, to be measured from `response.usage`). Anthropic's data-retention documentation is re-confirmed at dispatch. | The adapter is built; the key is absent on QA, so every photograph completes with `vision: unavailable` and the seller's review carries the OCR, regex and symbol regions. Nothing blocks on the key. John rules on (a) sending at all, (b) the model, (c) a monthly cap. |
| **D-IDP-2 (Q)** | The eighteen seeded demo hospitals under the `NOT_SHOW` default. | The seeder writes `SHOW` under its existing `WHERE listing.source = 'seed'`; migration `040` backfills `SHOW` for every row whose `photos` holds a path entry, claimed rows included — a seed photograph has no asset row and can only be served under SHOW. If John says "seeds NOT SHOW", they need asset rows and a pipeline run before they can publish. |
| **D-IDP-3 (Q)** | Seed filename-derived captions delivered beside the image (thirteen of the inventory's captions name signage). | Unchanged: they are descriptive ("Exterior — monument sign"), not identifying, and a seller's own words on their photographs stay theirs. John may rule captions filtered under NOT_SHOW. |
| **D-IDP-4 (Q)** | Whether Rev 3 designs a dedicated review screen later. | This composition ships first — the A19 dialog, the step-6 tiles, a fourth step-7 row. Rev 3's request document gains a fifth item naming the switch and the dialog (Task P11 Step 8). |
| **D-IDP-5** | The privacy record's columns. | Migration `041` as written: one row per photo asset, twenty-seven columns, six named CHECKs, two indexes. Documents get no row. |
| **D-IDP-6** | The pipeline's stages and their module layout. | `app/tasks/media.py` + `app/privacy/{ocr,barcodes,identity,vision,aggregate,delivery,gate,record}.py` + `app/media/redact.py`, extended by one module the spec did not name (`record.py`, controller amendment A-IDP-1) and one correction to spec §G's execution model (`enqueue_processing`'s eager branch, controller amendment A-IDP-2, because celery's `send_task` ignores `task_always_eager`). No deployed api process loads an engine wheel — pinned at run time by `tests/api/test_import_surface.py`; the worker serves no bytes. |
| **D-IDP-7 (Q)** | Every 2D symbol is redacted under NOT_SHOW regardless of payload — the directive says "where they resolve to identifying information". | Redact all; classify the payload offline for the record; never fetch one; the seller may Remove an unnecessary mask. |
| **D-IDP-8 (Q)** | A per-photograph hint when the vision model reports an identifier it cannot localise. | None beyond the once-only line. `vision.unlocalised` is recorded and the seller's manual mask is the tool. |
| **D-IDP-9 (Q)** | The redaction fill colour. | The design's navy `#003a70` (`app/media/redact.py::FILL`); black is the alternative, and it is one constant. |
| **D-IDP-10 (Q)** | The OCR image growth: `rapidocr-onnxruntime` + `onnxruntime` + the full `opencv-python` with apt `libgl1 libglib2.0-0`, or vendored ONNX models on `onnxruntime` alone with no OpenCV and no apt. | The pip route with the two apt packages; the **measured** delta goes in P4's commit body and in `DEPLOY.md`, whatever it says. |
| **D-IDP-11** | Content-hashed URLs, `private, no-cache` and an ETag, replacing `private, max-age=86400`. | Applied (Task P9). A flip changes both the URL and the validator, so no browser can revalidate its way back to a variant the policy has replaced. |
| **D-IDP-12** | The publishing gate and its database backstop. | One predicate (`app/privacy/gate.py::photos_not_ready`) at submit, decide-publish and republish, and migration `042`'s trigger evaluating the same SQL function behind them. Under SHOW the floor is `READY_FOR_REVIEW`, not `SCANNED` — the directive says "completed processing". |
| **D-IDP-13 (Q)** | The seller-facing strings beyond the controller's three and John's own once-only line. | Shipped as the spec's §H table writes them, byte for byte, queued for his vet. |
| **D-IDP-14** | The listing setting, its name, its default and its one writer. | `listing.identifiable_content_visibility`, `NOT_SHOW` by default, written only by the owner's step-7 PATCH. No admin route can write it. |
| **D-IDP-15** | The three-object storage layout. | `listings/{listing_id}/photos/{asset_id}/{original.{ext},display.webp,redacted.webp}`; `listing_asset.storage_key` keeps naming display; delete removes the whole prefix. |
| **D-IDP-16** | What a processing-version bump does to a published listing. | Staleness is a **flag** (`reprocess_reason`), never a state: the ready row keeps serving its current derivative while the in-place re-run replaces it, and on a confirmed row the fresh auto regions are unioned with the confirmed ones so the new derivative hides a superset of what the seller approved. |

Three more of the spec's open items, recorded here so they are not lost: **worker sizing** (no CPU or memory figure exists for the worker; measured on QA before the `media` queue is enabled, recorded in `DEPLOY.md`); **the three Round Rock design fixtures** (whether they depict a real practice is John's fact to confirm — they are the design's own bundle assets, served public and unauthenticated, and the directory's contents are pinned); and **documents** (PDF, CSV and XLSX stay out of redaction scope under the D19 owner-and-staff lock, and the question re-opens when the requests sub-project adds its "accepted request" arm).

---

## Hand-back — John's section 24 FINAL OUTPUT list, verbatim

The hand-back report answers every line of this list, in this order, with evidence rather than assertion. John's words:

```
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
```

How each line is answered:

- **files changed** — `git diff --stat <merge SHA>..HEAD`, pasted, with the File Structure table above as its key.
- **database/schema changes** — migrations `040`, `041`, `042`: the column and its default, the table's twenty-seven columns and six CHECKs, the SQL function and the trigger. Named, with what each refuses.
- **APIs/endpoints changed** — the six new routes and the four changed ones, each with its guard, its refusals and what it can return; the route-table pin quoted as the proof the list is complete.
- **processing pipeline implemented** — the seven stages, the engines and their measured sizes and licences, the queue, the ladder, the sweeper's six rules, and the in-place re-run.
- **privacy state machine** — the eleven states, the transition table, and the invariants the CHECKs hold; the count of transition tests.
- **security controls** — directive §20's thirteen items, each with the control and the test that proves it.
- **tests created** — the new files and their case counts.
- **tests executed** — the exact commands from *The gate, then QA*.
- **test results** — the `N passed` lines and the coverage figures, pasted.
- **known limitations** — at least these, stated plainly: detection is best-effort and the seller's confirmation is the gate, which is why the confirmation is mandatory and not advisory; the retry ladder's third rung (10 minutes) is never spent under a three-attempt bound, so the delays a seller actually experiences are 30 seconds and 2 minutes; `tests/api/test_import_surface.py` proves the api holds no engine wheel in the process order pytest happens to use, and the stronger proof is the same file run alone, which the gate does; scenario K is two tests because `client` is not reachable from `tests/media/`; with `ANTHROPIC_API_KEY` unset the vision stage is unavailable and only OCR, the regex classes and 2D symbols contribute regions; a reviewer's first-publish `state`/`market` marks no photograph stale, so a two-letter state code alone is not matched (the city token already carries the locality); a put that fails after `original.*` was written leaves one unreferenced object, which is the one orphan this design knowingly leaves; documents are not scanned; every listing including the eighteen seeded demo hospitals is `NOT_SHOW` by default, which overrules D-IDP-2 (controller amendment A-IDP-4, and A-IDP-6 for the gate it narrows); and the copy is queued for John's vet (D-IDP-13).
- **explicit confirmation that every upload path and every buyer image-delivery path was audited** — the spec's §A.1 nine ingress paths and §A.4 twelve delivery paths, each named with what now happens on it and the test that holds it; and the statement that this was verified by running those tests, not by reading the code.

Plus what CLAUDE.md's "Close the loop" requires and this report adds: a forwardable plain-language summary, the screenshots from the QA click-through, and a one-line engineer's note naming the risks — the image grew by the measured amount and the worker's memory headroom was confirmed; the vision stage is off until John rules D-IDP-1; the fill colour, the seed setting, the barcode policy and the copy are defaults awaiting his word.

**Nothing in the report says "implemented" for anything whose code, tests, security controls and publication gates have not actually been run and read.**
