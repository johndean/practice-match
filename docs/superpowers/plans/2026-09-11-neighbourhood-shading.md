# Neighbourhood Shading — Real Census Boundary Polygons — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Browse map's 3,070-to-12,560-rectangle grid mosaic with real Census boundary polygons — ZCTA for `income`, place for `growth`, county for `econ` — each drawn at its own honest geography, each carrying its own value, margin of error and suppression verdict, served by one member-gated endpoint inside the existing `market:gate:v` licence cache key.

**Architecture:** Three layers, in the order the risk demands. (1) The **amendment engine** grows a second bundle file so `MarketMapV3.jsx` can be changed the way every other design edit is changed — pristine + ruled edits, proved byte for byte — because the reference draws the shading itself and the zero-pixel gate compares the app against baselines generated from it. (2) The **design** (amendment family **A24**) stops drawing a grid and starts drawing a `FeatureCollection` of real polygons, coloured through the design's own `bucket()`/`fmtMetric()` so the fill and the legend cannot disagree; the polygons themselves come from a committed fixture generated from `geo_area` by `scripts/export_design_boundaries.py`, and their VALUES are the design's own nine Austin community figures assigned to the nearest polygon — the one line of `mosaicCells` that survives. (3) The **backend** fills a new `geo_metric` table nightly from datasets already loaded (plus one new ACS load at summary level `860`) and serves it as GeoJSON from `GET /api/markets/{cbsa}/boundaries`, which the app reaches through a `market` adapter prop in the seam A16/A17 established: with the adapter present the map draws what the API answered or nothing at all; with no adapter — the reference, and the Claude Design preview — the design's fixture path is untouched.

**Tech Stack:** the design bundle's own dc runtime (React 18 + `support.js`) on the reference side · Vue 3 + `frontend/scripts/convert-dc.mjs` on the app side · Leaflet 1.9.4 behind `frontend/src/map/engine.ts` · Vitest 3 · Playwright (`visual.spec.ts`, `dom.spec.ts`, `smoke.spec.ts`, the `reference` project) · FastAPI + SQLAlchemy async + psycopg2 + PostGIS 3 · Celery beat · pytest. **No new runtime dependency, in either half.**

**Branch:** one worktree per task, cut from `main` at the time the task starts — A-NS5: the plan named a single worktree `.worktrees/feat-neighbourhood-shading` at HEAD `6ca26a5` / version 0.1.17, and `main` has since taken four merges and two releases, so a branch cut from that SHA would be cutting from history. Tasks 1 and 2 are already merged. **Cut from `main`, derive the base, and never quote the old SHA or version.** Implementers never push, deploy or run `railway`; the controller does those at hand-back.

---

## The source of truth

`docs/superpowers/specs/2026-09-10-neighbourhood-shading-design.md`, whose three open questions were all answered on the evening of 2026-09-10 (§14) and whose decisions `D-NS1`–`D-NS18` this plan implements without revisiting. Above it sit John's four rulings of 2026-09-10 ~15:50 WITA — **D-C34** (ZCTA first, tract later and evidence-gated), **D-C35** (every layer at its own geography, and the legend names it), **D-C36** (keep the design's published bands, show the margin of error in the tip, reuse `materialize._suppression` verbatim), **D-C37** (a member-gated endpoint, not CDN tiles) — recorded in `docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md` under "John's four rulings on neighbourhood shading", with controller amendment **A-C33** immediately above them. Those four are settled and are not reopened here.

### The amendment family id, and how it was derived

**A24**, derived from `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md` — the ledger, which is the authority, not this plan and not the spec. Counted with:

```bash
cd "/Users/johndean/Development/Practice Match"
python3 - <<'PY'
import re, pathlib
md = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md").read_text(encoding="utf-8")
fams = sorted({int(re.match(r"A(\d+)", c).group(1))
               for line in md.split("\n") if line.startswith("| ")
               for c in [line.split("|")[1].strip()] if re.fullmatch(r"A\d+(\.\w+)*", c)})
print("families in the ledger:", fams)
PY
```

which prints `[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25]`. Two numbers are missing from that run and both are **reserved by name in the ledger's own A25.1 row** (Task MP1, 2026-09-10): "Ids A20 and A24 are RESERVED and were skipped, not orphaned: A20 by the image-identifiability plan … and A24 by the neighbourhood-shading spec … so the next free id after this family is A26, not A24." **A24 is this work's reservation**, `grep -c "id: 'A24" frontend/tests/design-amendments.ts` is `0`, and nothing else in the tree claims it. So A24 it is — not A26, which is the next free id for the NEXT piece of work. If the precondition grep below shows A24 already in `design-amendments.ts`, `main` has moved: **STOP** and re-derive.

---

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from the spec, the ledger or the code they pin.

- **(a) `frontend/src/logic.js` is NEVER hand-edited, and neither is any bundle file.** Every change to the design is an entry in `frontend/tests/design-amendments.ts`, applied to the pristine copy by `npm run gen:design`, after which `logic.js` is re-ported and `App.vue`/`pseudo.css` are regenerated by `npm run gen:app`; `frontend/tests/app-generated.test.ts` proves byte equality. `Practice Match V3.rev2.dc.html` (SHA-256 `335753c3164c10b80f9779de637a2358f40cde5c22d9195cc0a79f06bcf4f01d`) and, from Task 1, `MarketMapV3.rev2.jsx` (SHA-256 `662e4105fd258b6380f1f66f6289629d999aa657b8dc5a4d1303be88e26c0adc`) are pristine and are never edited.
- **(b) Every amendment's `find` is grepped as a FIXED STRING against the pristine file before it is written, with Python and never `grep -c -F`.** Two amendments shipped this week whose `find` occurred nowhere and were silent no-ops. `grep` splits on newlines, so a multi-line `find` makes it OR the lines and report the wrong count. Use:
  ```bash
  python3 -c "import pathlib,sys; print(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').count(open(sys.argv[2],encoding='utf-8').read()))" <file> <anchor.txt>
  ```
  or an inline `.count(...)` as every task below does. `applyAmendments` throws if the count at the point of application is wrong, but the point of this rule is to know BEFORE the run.
- **(c) A guard must test the sentinel the producer actually emits.** Five review rounds went on guards asking `!== undefined` while the producer coerced absence to `0`. Before writing any guard, run the real producer and print what it returns. Two measurements this plan already made, and every task that touches them repeats them as a step:
  - `app.census.materialize._suppression(None, None)` returns **`(False, None)`** — a MISSING VALUE is not suppressed, because there is nothing to suppress. `_suppression(72400, None)` returns `(True, "no_moe")`. So "no data" is `value is None`, and it is a DIFFERENT state from `suppressed is True`; a guard that tests only `suppressed` renders a null as a measured figure.
  - `app.census.acs._num(None)` returns `None`; `_num("-666666666")` returns `Decimal("-666666666")`. ACS jam values are NOT filtered anywhere in this tree today, and this plan does not add a filter (out of scope, named in the Known gaps).
- **(d) Backend coverage is 100 % lines AND branches, warnings as errors:** `docker compose -f docker-compose.dev.yml up -d && poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e --cov-fail-under=100`. `scripts/` is in the measured set, so a new script needs full-coverage tests. **Do not write a defensive branch no test can reach** — `app/api/market.py:155-169`'s own comment is the house rule: "a branch nothing can reach is one no test can close".
- **(e) Frontend coverage is 100 % lines, branches, functions and statements:** `cd frontend && npx vitest run --coverage`. `logic.js` is excluded from the measured set (it is the design's script) but every new branch in it is characterised in `frontend/src/logic.test.ts` regardless.
- **(f) Zero pixel tolerance, never relaxed.** `maxDiffPixels: 0` beside `threshold: 0.1` in `frontend/tests/playwright.config.ts:64-65` stays. Baselines regenerate from the amended design in the same run (`npm run test:visual:baselines`, the `reference` project), so a ruled change is legal there; a failure AFTER regeneration means the app and the design diverged — stop and diff, never widen the tolerance.
- **(g) `frontend/tests/baseline-manifest.json`'s THIRTEEN frozen hashes must not move.** `mobile-list`, `mobile-detail`, `detail`, `requests`, `seller-dash`, `wizard-step-1`, `wizard-step-7`, `wizard-preview`, `wizard-done`, `admin-users`, `admin-listings`, `admin-requests`, `admin-data-sources`. **Not one of them mounts a map.** A moved hash means the change leaked outside Browse: stop with NEEDS_CONTEXT, do not re-pin. The only two mechanisms that have ever legitimately moved a frozen hash are a ruled removal from every screen (A6) and a ruled change to the shared header (A14); nothing here is either.
- **(h) Playwright ports and databases never collide across worktrees.** Every task that runs Playwright exports `PW_APP_PORT=5583 PW_REF_PORT=5584 PW_CS_PORT=5585 PW_API_PORT=8157` explicitly and `lsof`s them first. pytest and Playwright never share a database: pytest clones per test from a template (`tests/conftest.py::scratch_dsn`) off `DATABASE_URL`, and `frontend/tests/targets.ts:126` runs `migrate.py` + `reset_rate_limits.py` + `seed_persona.py` + `seed_listings.py` against whatever `DATABASE_URL` names. This worktree's is `practice_match_shading` and its Redis index is `/10`; siblings hold `/0`, `/3`, `/7`, `/8`, `/9` and ports 5473-5475/8047, 5503-5505/8347, 5513-5515/8357, 5573-5575/8147.
- **(i) A hand-maintained number in a comment or a document is a defect waiting to happen.** Where a figure can be derived from the tree, derive it. `tests/test_docs.py` already pins CLAUDE.md's amendment counts and approved-state count against `design-amendments.ts` and `screens.ts`; every new document claim in this plan gets its own drift test in the same file or in `frontend/tests/`.
- **(j) The design's published bands are unchanged (D-C36) — except `growth`, SUPERSEDED for that one layer by D-C46 (John, 2026-09-11), applied in Task 4 as amendment A24.13.** `income` `stops: [50000, 75000, 100000, 150000]`, buckets `< $50K`, `$50–75K`, `$75–100K`, `$100–150K`, `> $150K`. `growth` **was** `stops: [10, 20, 35]`, buckets `< 10%`, `10–20%`, `20–35%`, `> 35%`; it **is now** `stops: [0, 5, 15]`, buckets `Declining`, `0–5%`, `5–15%`, `> 15%`. Why the freeze had to give: those stops cannot represent data that runs roughly −5 % to +15 %, and there was no band below zero at all, so Task 4 would have shipped real Census polygons that are still one colour and the complaint this whole stream exists to answer would have survived it. Measured against ACS 2014–2018 against 2019–2023 place populations — the exact pair `population_growth_pct` divides, read from the Census Bureau's keyless summary files, 29,232 places — `[10, 20, 35]` put **79.9 %** of US places of 10,000 people or more into ONE bucket, while **30.5 %** of them were declining with no band to say so. The new stops are the tertiles of the non-declining half of that distribution, rounded to legend-readable numbers. `income` and `econ` stay frozen under D-C36; this ruling does not reach them. `econ` `stops: [450000, 650000, 900000]`, buckets `< $450K`, `$450–650K`, `$650–900K`, `> $900K`. Labels: `Median Household Income (ACS)`, `Population Growth (ACS)`, `Average Practice Payroll (CBP)`.
- **(k) The three geographies are D-C35's, and no layer is ever promoted into a finer slot.** `income` → summary level `'860'`, label `ZIP Code Tabulation Area`. `growth` → `'160'`, label `Place (city/town)`. `econ` → `'050'`, label `County`. The three graduated-symbol layers (`pets`, `households`, `competition`) are NOT moved onto polygons.
- **(l) The no-data class is the design's own `#e6e6e6` at `fillOpacity: 0.5`, always drawn, never omitted** (D-NS16, ruled by John 2026-09-10 §14 Q1), with one extra legend row reading exactly `No data`. Grey means UNMEASURED and only that: a figure that WAS measured but whose margin spans a legend band is shown with its value and a caveat, never greyed (D-C36).
- **(m) The snapshot strip's footnote becomes, verbatim** (John, 2026-09-10 §14 Q2): `Community areas are Census ZIP Code Tabulation Areas (2023 boundaries); figures describe the area, not the practice.`
- **(n) `materialize._suppression` is reused, never reimplemented** (D-C36, D-NS6), and a test asserts `app.census.geo_metric._suppression is app.census.materialize._suppression`. It is applied to `median_hh_income` only (D-NS17): `growth` and `econ` carry no published margin and say so in the tip.
- **(o) Attribution is legally load-bearing.** Every boundary payload carries `attribution[]` read from `dataset_registry.attribution_text`, never composed in the frontend. `tiger_cb`'s is exactly `Boundaries: U.S. Census Bureau, TIGER/Line Cartographic Boundary Files 2023`; `acs5`'s is exactly `Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023`. The map's own Leaflet attribution control keeps carrying `Tiles © Esri`. The Esri-vs-CARTO basemap question is one open decision record and is not touched.
- **(p) Surgical diffs, no destructive actions, conventional commits with explicit pathspecs.** `git add <path> …`, never `git add -A`. Every commit ends with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Implementers do not push, deploy, run `railway`, or touch another worktree; they never `git stash`.
- **(q) Deviations STOP.** A `find` that does not match with `count: 1` at its point of application, a frozen hash the plan did not predict, a DOM-oracle line after regeneration, a coverage gate that needs relaxing, a Census response that does not match what §2.3 records — stop and report as NEEDS_CONTEXT. Do not improvise.

---

## Controller note on the spec's slicing

**I agree that slice (a) leads, and I have split it in two.** The spec argues (a) leads because it is the only slice that can invalidate the others and needs no backend, and R1's kill condition is stated precisely: "If `design-amendments.test.ts` cannot prove pristine + amendments == amended for the `.jsx`, the shape in §9.2 is wrong and the whole estimate moves."

That kill condition is answerable **without changing a single pixel**, and that is what Task 1 does: extend the engine to two files, freeze `MarketMapV3.rev2.jsx` as a byte copy, prove `pristine_jsx + [] == amended_jsx`, run the full pixel and DOM gate, and see thirteen frozen hashes and forty-nine baselines unmoved. That is the measurement, and it is a day rather than three. It also proves the thing that would actually break: that `apply-amendments.ts` can write a file it has never written and reproduce it byte for byte (encoding, line endings, trailing newline). A reviewer can reject the engine's shape there without touching any geometry.

The rest of slice (a) — the geometry swap itself — then splits again along a real reviewable seam: Task 2 adds the `geoJson` engine primitive (a pure addition nothing calls yet, zero pixels), Task 3 produces the design's boundary fixture from real `geo_area` rows (zero pixels), and Task 4 swaps the mosaic for polygons on both targets in one commit, because the app and the reference must move together or every Browse state fails.

**Two other departures from §15, both stated so nobody reads them as drift:**

1. **The fixture carries geometry, not values.** §9.4 says the fixture is "real `geo_area` shapes for the design's own Austin metro" and A24.1 puts it in the design's state literal — this plan does that. It does NOT put figures in it: `geo_metric` does not exist when the fixture is generated, ACS at ZCTA is not loaded, and inventing figures for a design fixture is exactly the thing the programme keeps being bitten by. Instead each fixture feature carries its own centroid, and the design's own script assigns it the value of the nearest of the design's own nine Austin communities — `mosaicCells`'s own assignment rule, "spatial ASSIGNMENT of existing community data, not interpolation, and not new data", applied to real polygons instead of grid cells. The picture is a real multi-class choropleth on real boundaries with no invented number anywhere, `expectBoundaryShading` still finds ramp colours, and `frontend/tests/design-boundaries.mjs` derives the harness stub from the same class member rather than re-implementing it (R8).
2. **The hover tip's HTML moves into `logic.js`.** Today it is built twice — once inline in `MarketMapV3.jsx:258-266` and once in `MarketMapView.vue:105-114` — and kept in step by hand. §8.5 says the tip "keeps the `rf-tip` sticky tooltip mechanism exactly and changes what it contains"; the mechanism is kept, but the STRING is built once, in the design's own `areaVals`, beside `fmtMetric`, and both renderers bind `f.properties.tip`. The honesty lines are then unit-testable in `frontend/src/logic.test.ts` rather than only through a map component, and two implementations of the sentence "Estimate too imprecise to show at this geography" cannot drift.

Sequencing after slice (a) follows the spec: values (b), read path (c), map wiring (d). One refinement inside (c): `/api/layers`'s `shading` member and the contract-document section land in the SAME task as the route, because `tests/api/test_contract_doc.py::test_contract_doc_names_every_market_and_admin_route` walks every mounted path and goes red the moment the route exists. That is the intended forcing function, and splitting it would leave a task ending red.

**Three spec paths that do not exist in the tree, corrected here rather than propagated.** `tests/api/test_boundaries.py` → the market API's tests live at `tests/census/test_market_api.py`, so the new file is `tests/census/test_boundaries.py`. `app/census/acs.load_acs` → the function is `app.census.acs.load` (`load_acs` is the Celery wrapper in `app/tasks/census.py`). `app.census.vintage.active_vintage` → the function is `active` (`active_vintage` is the table).

---

## Preconditions

> **Amendment A-NS5 (Task 3, 2026-09-11) — this block was rewritten because every literal in it had
> rotted.** The plan was cut at HEAD `6ca26a5` (version 0.1.17) and the block below asserted twelve
> hand-typed numbers against a tree that has since taken four merges. Measured on `main` at `ec79594`
> the morning Task 3 was dispatched, **every single count line was wrong** — and the block's own
> instruction is "If any check fails, **STOP**", so a literal reading of it halts the stream on its
> first command. It also contradicted itself: the line asserting `the 52 approved states` in
> CLAUDE.md sat two lines above one asserting `49` entries in `screens.ts`, and those two count the
> same set. (Commit `3e47c66`, "the approved-screen count is 52, not 49", fixed the CLAUDE.md line
> and left the `screens.ts` line behind.)
>
> **What moved, and why.** Nothing here is a defect in Tasks 1 and 2; it is four unrelated streams
> landing on `main` while this plan sat still:
>
> | Precondition | At plan cut (`6ca26a5`) | Measured `main` (`ec79594`) | Why it moved |
> |---|---|---|---|
> | `grep -c "id: 'A"` (literal entries) | 158 | **181** | A26 (filter-bar dropdowns, F1b + F2) added 23 literals |
> | `grep -c "^| A"` (ledger rows) | 159 | **182** | same 23; rows = literals + 1 (A1 collapses to one row) |
> | CLAUDE.md family/entry sentence | `Twenty-three families, 182 entries` | **`Twenty-four families, 205 entries`** | A26 is a new family; 205 = 181 + 24 |
> | CLAUDE.md literals sentence | `…plus 158 literals` | **`…plus 181 literals`** | same |
> | `toHaveLength(…)` in `design-amendments.test.ts` | 182 | **205** | same |
> | `screens.ts` entries | 49 | **52** | A19's three lightbox states (`detail-lightbox`, `browse-panel-lightbox`, `detail-lightbox-next`) |
> | CLAUDE.md approved-state sentence | — | **`the 52 approved states`** | same; already corrected on `main` by `3e47c66` |
> | `frontend/package.json` / `pyproject.toml` | 0.1.17 | **0.1.19** | releases 0.1.18 and 0.1.19 |
> | `migrations/` tail | `062…, 063…, 090…` | **`062…, 063…, 090…, 091…`** | `091_listing_provenance.sql`; **064 is still free** |
> | pristine SHA-256s | as printed | **unchanged, both** | pristine files are never edited — the one class of literal that is safe here |
>
> **And `main` is about to move again.** `feat/card-geography` (HEAD `8c7c3b6`, 20 commits, under final
> review) carries amendment families **A27 and A28**, a 53rd approved state (`browse-market-strip`),
> and takes the tree to **196 literals / 197 rows / `Twenty-six families, 220 entries` /
> `toHaveLength(220)` / 53 screens**. It does **not** carry a version bump: both manifests on that
> branch still read 0.1.19, so the 0.1.20 this stream was told to expect does not exist yet.
> `grep -c "id: 'A24"` is **0 on both branches** — A24 is still this work's reservation, as the
> ledger's A25.1 row reserved it.
>
> **The mechanism, not the numbers.** Absolute counts in a plan rot the moment a sibling branch
> merges, and this stream lost two days to exactly that. So from here:
>
> 1. **Every count in this plan is a DELTA off a value derived when the task starts**, never an
>    absolute typed at plan-cut time. The invariants are arithmetic and do not rot:
>    `entries = literals + A1's derived count` (24 today, itself read from
>    `design-amendments.test.ts`) · `ledger rows = literals + 1` · `baselines = screens.ts entries`
>    (`reference-baselines.spec.ts` emits exactly one test per `SCREENS` entry) ·
>    `families = distinct numbered ids in design-amendments.ts, PLUS ONE for A1` (A1 is derived by
>    `deriveTypographyB` and never appears as a literal id, which is exactly how
>    `tests/test_docs.py` counts it).
> 2. **The per-task deltas, which are properties of the work and therefore stable:** Task 4 adds
>    **+15** entries (and +15 ledger rows, +1 family); Task 10 adds **+5**; Tasks 3, 5–9 and 11 add
>    **0**. Total for family A24: **20 entries** — note the File Map row for
>    `design-amendments.ts` says "the sixteen A24 entries", which is wrong on the plan's own
>    arithmetic (158→172→177). **Task 4 MEASURED +15, not the +14 this line first carried:** D-C46
>    (John, 2026-09-11) was moved into that task and is one more literal, `A24.13`, so the family is
>    twenty and not nineteen. Derive it from `design-amendments.ts`; never copy any of the three.
> 3. **No task adds an approved state.** `screens.ts` keeps whatever count it has when the task
>    starts; Task 11's "stays at 49 entries" is to be read as "stays at `SCREENS.length`".
> 4. **The release version is `next free patch in MERGE order`**, never a number written here.
>    Task 11's "0.1.17 → 0.1.18" is void: read the two manifests at hand-back and take the next
>    patch. If `feat/card-geography` merges first and releases, this stream's release moves again.
> 5. **The real enforcement is not this block.** `tests/test_docs.py` already cross-checks
>    CLAUDE.md's sentences against `design-amendments.ts` and `screens.ts`
>    (`test_claude_md_amendment_family_and_entry_counts_match_design_amendments`,
>    `test_local_amendments_row_count_matches_design_amendments`,
>    `test_claude_md_approved_screen_count_matches_screens_ts`). Running the backend gate proves the
>    counts agree with each other; the script below only has to prove the things a test cannot
>    know — that A24 is unclaimed, that migration slot 064 is unclaimed, that the pristine twins are
>    byte-identical, and that the two version manifests are in lockstep.
>
> **One live trap this re-derivation found, and Task 4 must carry it.**
> `tests/test_docs.py`'s `number_words` tuple on `main` stops at `"Twenty-four"` and the assertion
> immediately above it is `assert family_count in number_words`. `main` is at exactly twenty-four
> families, so A24 makes it **twenty-five** and that test fails *on its own vocabulary* before it
> ever compares a string to CLAUDE.md. The plan currently says, in Task 4's counts paragraph,
> "`tests/test_docs.py`'s `number_words` already runs to `"Twenty-four"` — no edit needed there."
> **That sentence is now false and Task 4 must extend the tuple.** `feat/card-geography` hit this
> same wall at A27 and already extended it (with a comment recording that A18 hit it at "Fifteen"),
> so if that branch merges first the edit is already made and Task 4 must check rather than assume.

Verify by derivation, not by memory, and not against a number typed into this document. Run this and
read the verdicts; **any `FAIL` means STOP** and re-derive as this amendment did.

```bash
cd "/Users/johndean/Development/Practice Match"
python3 - <<'PY'
import hashlib, pathlib, re, subprocess

root = pathlib.Path(".")
ok = True
def check(label, passed, detail=""):
    """A BLOCKER. A FAIL here means `main` has moved under this plan: STOP and re-derive."""
    global ok
    ok = ok and passed
    print(f"{'PASS' if passed else 'FAIL'}  {label}{'  ' + detail if detail else ''}")

def todo(task, label, satisfied, detail=""):
    """NOT a blocker for the task in hand -- a named prerequisite for a LATER task, printed here
    because this is the one place anybody reads before starting. It never sets the exit code."""
    print(f"{'PASS' if satisfied else 'TODO'}  [{task}] {label}{'  ' + detail if detail else ''}")

amd = (root / "frontend/tests/design-amendments.ts").read_text(encoding="utf-8")
ledger = (root / "docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md").read_text(encoding="utf-8")
claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
screens = (root / "frontend/tests/screens.ts").read_text(encoding="utf-8")
amd_test = (root / "frontend/tests/design-amendments.test.ts").read_text(encoding="utf-8")

# --- DERIVED, never typed -----------------------------------------------------------------
literals = len(re.findall(r"id: 'A", amd))
# A1's derived count is read from design-amendments.test.ts, exactly as tests/test_docs.py reads
# it -- never retyped here, so the two cannot drift.
a1       = int(re.search(r"Array\.from\(\{ length: (\d+) \}, \(_, i\) => `A1\.\$\{i \+ 1\}`\)", amd_test).group(1))
entries  = literals + a1
rows     = len(re.findall(r"^\| A", ledger, re.M))
# +1 for A1: it is DERIVED and never appears as a literal id, so the regex cannot see it.
families = len({int(m) for m in re.findall(r"id: 'A(\d+)", amd)}) + 1
nscreens = len(re.findall(r"^\s*\{ name: '", screens, re.M))
print(f"\nDERIVED  literals={literals}  a1={a1}  entries={entries}  rows={rows} "
      f"families={families}  screens={nscreens}  baselines={nscreens}\n")

# --- INVARIANTS that cannot rot ------------------------------------------------------------
check("ledger rows == literals + 1 (A1 collapses to one row)", rows == literals + 1, f"{rows} vs {literals + 1}")
check("design-amendments.test.ts pins the derived entry count",
      f"toHaveLength({entries})" in amd_test, f"expected toHaveLength({entries})")
check("CLAUDE.md's entry sentence matches, twice",
      claude.count(f"families, {entries} entries") == 2)
check("CLAUDE.md's literals sentence matches, twice",
      claude.count(f"A1's {a1} derived edits plus {literals} literals") == 2)
check("CLAUDE.md's approved-state sentence matches screens.ts, once",
      claude.count(f"the {nscreens} approved states") == 1)

# --- THIS WORK'S RESERVATIONS --------------------------------------------------------------
check("A24 is unclaimed (this plan's family)", amd.count("id: 'A24") == 0)
check("migration slot 064 is unclaimed",
      not list((root / "migrations").glob("064_*.sql")),
      "last migration on disk: " + sorted(p.name for p in (root / "migrations").glob("*.sql"))[-1])

# --- PRISTINE TWINS: the only safe literals in this block ----------------------------------
B = root / "docs/design-reference/design_handoff_practice_match_v3"
for name, want in (("Practice Match V3.rev2.dc.html", "335753c3164c10b80f9779de637a2358f40cde5c22d9195cc0a79f06bcf4f01d"),
                   ("MarketMapV3.rev2.jsx",           "662e4105fd258b6380f1f66f6289629d999aa657b8dc5a4d1303be88e26c0adc")):
    got = hashlib.sha256((B / name).read_bytes()).hexdigest()
    check(f"pristine {name} is untouched", got == want, got)

# --- VERSION: derived and in lockstep, never a number written in the plan -------------------
fe = re.search(r'"version": "([^"]+)"', (root / "frontend/package.json").read_text(encoding="utf-8")).group(1)
be = re.search(r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
check("frontend and backend versions are in lockstep", fe == be, f"{fe} / {be}")
print(f"\nRELEASE  current {fe}; this stream ships the next free patch IN MERGE ORDER, not a number from this plan.")

# --- THE TRAP Task 4 MUST CARRY ------------------------------------------------------------
words = (root / "tests/test_docs.py").read_text(encoding="utf-8")
need = families + 1        # A24 is a NEW family
vocab = re.search(r"number_words = \{n: w for n, w in enumerate\(\s*\((.*?)\)\)\}", words, re.S)
have = len(re.findall(r'"[^"]+"', vocab.group(1))) if vocab else 0
todo("Task 4", f"tests/test_docs.py's number_words must reach {need} families (A24 is a NEW family)",
     have > need, f"tuple holds {have} words, indices 0..{have - 1}"
                  + ("" if have > need else f" -- extend it past {need} or the docs test fails on its own vocabulary"))

print("\nHEAD:", subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip())
raise SystemExit(0 if ok else 1)
PY
```

**What the derived numbers are FOR.** Task 4 and Task 10 are the only tasks that change them, and both
now read their targets off the run above rather than off a literal:

| | Task 4 target | Task 10 target |
|---|---|---|
| literals | `literals + 15` | `literals + 20` |
| entries / `toHaveLength(N)` | `entries + 15` | `entries + 20` |
| ledger rows | `rows + 15` | `rows + 20` |
| families | `families + 1` (A24 is new) | unchanged |
| CLAUDE.md | `<word(families+1)> families, <entries+15> entries` and `A1's 24 derived edits plus <literals+15> literals`, **both twice** | same sentences at `+20` |
| `screens.ts` | unchanged | unchanged |

For orientation only — **not to be asserted**: on `main` at `ec79594` that reads Task 4 → 195 literals /
219 entries / 196 rows / `Twenty-five families`; Task 10 → 200 / 224 / 201. If `feat/card-geography`
merges first it reads Task 4 → 210 / 234 / 211 / `Twenty-seven families`; Task 10 → 215 / 239 / 216.
Derive it; do not copy it.

### Step 0 — the worktree and its environment

> **A-NS5 — every port and database name below is an EXAMPLE, and this machine now runs enough
> parallel worktrees that copying them is a collision.** `docker-compose.dev.yml` publishes
> `5433:5432` and `6380:6379`, and on 2026-09-11 both were already held by the `feat-identity`
> stack, so a bare `docker compose -f docker-compose.dev.yml up -d` in a fresh worktree does not
> get you a fresh database — it fails, or worse, you end up pointed at a sibling's. **Derive free
> ports, name the compose project after your branch, and never delete a container you did not
> create.** Task 3 used project `shd3` on `5553`/`6453` with database `practice_match_shading_t3`.

```bash
cd "/Users/johndean/Development/Practice Match"
git worktree add .worktrees/<your-worktree> -b <your-branch> main
cd .worktrees/<your-worktree>

# Pick ports nothing holds, and give the stack its own compose project name.
docker ps --format '{{.Names}}\t{{.Ports}}'                     # read what is already taken
PGPORT=<free> RPORT=<free> PROJ=<short-name>
sed -e "s/\"5433:5432\"/\"$PGPORT:5432\"/" -e "s/\"6380:6379\"/\"$RPORT:6379\"/" \
    docker-compose.dev.yml > /tmp/$PROJ-compose.yml
docker compose -f /tmp/$PROJ-compose.yml -p $PROJ up -d
psql "postgresql://pm:pm_dev_pw@127.0.0.1:$PGPORT/postgres" -c 'CREATE DATABASE practice_match_shading_<suffix>'
cd frontend && npm ci && cd ..
```

Every command in every task runs with this environment, and nothing is ever pointed at `practice_match`, the shared dev database:

```bash
export DATABASE_URL=postgresql://pm:pm_dev_pw@127.0.0.1:$PGPORT/practice_match_shading_<suffix>
export REDIS_URL=redis://127.0.0.1:$RPORT/10
export ENVIRONMENT=test
export API_SECRET_KEY=local_only_secret_change_me
export CENSUS_CONTACT_EMAIL=engineering@vinfoundation.org      # TIGER downloads only; no API key is needed for boundaries
export PW_APP_PORT=<free> PW_REF_PORT=<free> PW_CS_PORT=<free> PW_API_PORT=<free>
lsof -nP -iTCP:$PW_APP_PORT,$PW_REF_PORT,$PW_CS_PORT,$PW_API_PORT -sTCP:LISTEN || true   # expect nothing; `reuseExistingServer: !CI` would adopt anything it finds
```

`127.0.0.1`, not `localhost`: on this machine `localhost` resolves to `::1` first and the compose
port publication is IPv4, which produced a "connection refused" that looked like a dead container.

A gate log must show `N passed`. A seconds-long "green" e2e run is the API web server failing to start, not a pass.

---

## File Map

| File | Kind | Responsibility | Task |
|---|---|---|---|
| `frontend/tests/design-amendments.ts` | modify | `AmendmentFile`, `Amendment.file`, `PRISTINE_JSX`/`AMENDED_JSX`, `amendmentsFor()`; then the **twenty** A24 entries (15 in Task 4, 5 in Task 10 — A-NS5 corrected this from "sixteen"; Task 4 then MEASURED fifteen rather than fourteen, because D-C46 moved into it as A24.13) | 1, 4, 10 |
| `frontend/scripts/apply-amendments.ts` | modify | writes BOTH outputs, partitioned by `file` | 1 |
| `frontend/tests/design-amendments.test.ts` | modify | the jsx pristine hash, both byte equalities, per-file count walk; then A24's ids and cases | 1, 4, 10 |
| `frontend/tests/reference-bundle.test.ts` | modify | `MarketMapV3.rev2.jsx` joins the required-file list | 1 |
| `docs/design-reference/design_handoff_practice_match_v3/MarketMapV3.rev2.jsx` | **create** (byte copy) | the pristine twin, never edited | 1 |
| `docs/design-reference/design_handoff_practice_match_v3/MarketMapV3.jsx` | **regenerated** | `npm run gen:design` | 1, 4 |
| `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html` | **regenerated** | `npm run gen:design` | 4, 10 |
| `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md` | modify | one row per A24 entry, in apply order, ruling verbatim | 4, 10 |
| `frontend/src/map/engine.ts` | modify | `AreaFeature`, `AreaFeatureCollection`, `MapEngine.geoJson` | 2 |
| `frontend/src/map/engines/leaflet.ts` | modify | `geoJson` on the shared canvas renderer | 2 |
| `frontend/src/map/engines/leaflet.test.ts` | modify | the `geoJson` cases | 2 |
| `frontend/src/map/testing/leaflet-stub.ts` | modify | the `geoJSON` factory | 2 |
| `frontend/src/map/boundary.test.ts` | modify | `geoJSON` joins the `L.(…)` alternation | 2 |
| `scripts/export_design_boundaries.py` | **create** | the fixture generator, reading `geo_area` | 3 |
| `tests/scripts/test_export_design_boundaries.py` | **create** | its tests, 100 % lines and branches | 3 |
| `frontend/tests/design-boundary-fixture.ts` | **create** (generated) | `DESIGN_AREAS_LITERAL`, embedded into A24.1 | 3 |
| `frontend/tests/design-boundary-fixture.test.ts` | **create** | size, shape and provenance pins on the generated file | 3 |
| `frontend/src/components/MarketMapView.vue` | modify | `areas` prop, `drawOverlay` through `geoJson`, `communities` kept | 4 |
| `frontend/src/components/MarketMapView.test.ts` | modify | off `cellCount`, onto feature counts; `roleOf` reads `data` | 4 |
| `frontend/src/map/mosaic.js`, `frontend/src/map/mosaic.test.ts` | **delete** | the grid is gone | 4 |
| `frontend/tests/visual.spec.ts` | modify | `expectMosaicShading` → `expectBoundaryShading` | 4 |
| `frontend/tests/smoke.spec.ts` | modify | the two tests that name the mosaic | 4 |
| `frontend/tests/cross-plan-deltas.test.ts` | modify | the two doc assertions at `:87` and `:96` | 4 |
| `frontend/src/logic.js`, `frontend/src/App.vue`, `frontend/src/generated/pseudo.css` | **re-ported / regenerated** | never hand-edited | 4, 10 |
| `frontend/src/logic.test.ts` | modify | `describe('A24 — real boundary polygons')` | 4, 10 |
| `migrations/064_geo_metric.sql` | **create** | `geo_metric` + `geo_metric_license_gate` | 5 |
| `tests/census/test_migration_064.py` | **create** | the table, the index, the trigger and its three refusals | 5 |
| `app/census/acs.py` | modify | summary level `860`, and `load(..., levels=)` | 6 |
| `scripts/census_load.py` | modify | `acs --levels` | 6 |
| `tests/census/test_acs.py`, `tests/scripts/test_census_load.py` | modify | the ZCTA cases and the CLI flag | 6 |
| `app/census/bands.py` | **create** | `INCOME_STOPS`, `band_index`, `band_ambiguous` | 7 |
| `tests/census/test_bands.py` | **create** | its cases, plus the two-way design pin | 7 |
| `scripts/measure_band_ambiguity.py` | **create** | the D-C34 measurement, off the request path | 7 |
| `tests/scripts/test_measure_band_ambiguity.py` | **create** | its tests | 7 |
| `app/census/geo_metric.py` | **create** | `materialize_geo`, the only writer of `geo_metric` | 8 |
| `app/tasks/census.py`, `app/tasks/celery_app.py` | modify | `census.materialize_geo_metrics`, `geo-metric-nightly` | 8 |
| `tests/census/test_geo_metric.py`, `tests/test_celery.py`, `tests/census/test_tasks.py` | create/modify | the writer's cases and the beat pin | 8 |
| `app/api/market.py` | modify | `GET /api/markets/{cbsa}/boundaries`, `/api/layers`'s `shading` | 9 |
| `docs/integrations/market-data-api.md` | modify | the route's row and its own section | 9 |
| `tests/census/test_boundaries.py` | **create** | guard, refusals, caps, gzip, cache key, vintages, parity | 9 |
| `frontend/src/market/boundaries.ts` | **create** | the `market` adapter | 10 |
| `frontend/src/market/boundaries.test.ts` | **create** | every method, every failure path | 10 |
| `frontend/src/app.setup.js` | modify | the `market` prop, in `listings`/`adminListings`' shape | 10 |
| `frontend/tests/design-boundaries.mjs` | **create** | the oracle's answer, derived from `areaSet` | 10 |
| `frontend/tests/harness.ts` | modify | one `page.route` for the boundaries endpoint, disarmed on a remote target | 10 |
| `frontend/tests/boundary-flows.spec.ts` | **create** | value assertions against the real API | 11 |
| `frontend/tests/playwright.config.ts` | modify | `boundary-flows` joins the `app` project's `testMatch` | 11 |
| `CLAUDE.md` | modify | the A24 clause and the two derived count sentences | 4, 10, 11 |
| `tests/test_docs.py` | modify | the drift pins for the new document claims | 9, 11 |
| `frontend/package.json`, `pyproject.toml` | modify | the lockstep version bump | 11 |


---

## Task 1: The two-file amendment engine — R1's kill condition, measured, with zero pixels moved

The largest single line item in this work is the zero-pixel gate, and the thing that could invalidate every other estimate is whether the D15 amendment engine can reach a bundle file other than the `.dc.html` at all. This task answers that and nothing else: the engine grows `file?: 'dc' | 'jsx'`, `MarketMapV3.jsx` gains a frozen pristine twin, and `npm run gen:design` writes both files. The jsx amendment list is **empty**, which is the point — the proof wanted is that the machinery round-trips a file it has never touched, byte for byte, and that all 53 approved states and all 13 frozen hashes are exactly where they were. (52 until 2026-09-11, when D-C40 appended `browse-market-strip` so A27.5's corrected sentence had an oracle; read the count from `screens.ts`, never from this line.)

**Re-basing states: NONE.** Nothing in the design changes. **`baseline-manifest.json`'s thirteen frozen hashes must not move**, and neither may any of the baselines — **`SCREENS.length` of them** (`reference-baselines.spec.ts` emits one test per `screens.ts` entry; 52 on `main` at `ec79594`, 53 once `feat/card-geography` merges). A-NS5: derive it, never type it.

**Files:**
- Create: `docs/design-reference/design_handoff_practice_match_v3/MarketMapV3.rev2.jsx` (a byte copy of `MarketMapV3.jsx`)
- Modify: `frontend/tests/design-amendments.ts:1-10` (constants and the type), `:68-76` (`applyAmendments` is unchanged; `amendmentsFor` is added after it)
- Modify: `frontend/scripts/apply-amendments.ts:22-28`
- Modify: `frontend/tests/design-amendments.test.ts:4` (imports), `:12-14` (beside the dc hash), `:675-677`, `:715-731`
- Modify: `frontend/tests/reference-bundle.test.ts:25`
- Test: `frontend/tests/design-amendments.test.ts`, `frontend/tests/reference-bundle.test.ts`

**Interfaces:**
- Consumes: nothing from an earlier task.
- Produces, from `frontend/tests/design-amendments.ts`:
  - `export type AmendmentFile = 'dc' | 'jsx';`
  - `export type Amendment = { id: string; date: string; ruling: string; find: string; replace: string; count: number; text?: string; file?: AmendmentFile };` — `file` is OPTIONAL and defaults to `'dc'`, so all 158 existing entries are unchanged.
  - `export const PRISTINE_JSX: string;` — absolute path of `MarketMapV3.rev2.jsx`
  - `export const AMENDED_JSX: string;` — absolute path of `MarketMapV3.jsx`
  - `export function amendmentsFor(file: AmendmentFile): Amendment[];` — `amendments().filter((a) => (a.file ?? 'dc') === file)`, in list order
  - `applyAmendments(html: string, list: Amendment[]): string` — signature unchanged; it is now called once per file with that file's partition.
  Tasks 4 and 10 add entries carrying `file: 'jsx'`; nothing else in the tree consumes these.

- [ ] **Step 1: Write the failing test**

Add to `frontend/tests/design-amendments.test.ts`. First extend the import on line 4 to:

```ts
import { AMENDED, AMENDED_JSX, type Amendment, LOCAL_AMENDMENTS_MD, PRISTINE, PRISTINE_JSX, amendments, amendmentsFor, applyAmendments, deriveTypographyB, templateRegions, V2 } from './design-amendments';
```

Then add these three cases immediately after the existing pristine-hash case (which ends at line 14):

```ts
  // The bundle's SECOND amendable file (spec §9.2, ruled by the controller 2026-09-10 §14 Q3).
  // A24 is the first amendment in the programme's history that has to reach a file other than
  // the `.dc.html`, and the alternative — hand-editing an approved bundle file — is the exact
  // failure mode spec D15 exists to remove. Same contract, same proof: a frozen pristine twin
  // that is never edited, and byte equality with the amended file it plus its own amendments
  // produce. This hash changes only when a re-issued bundle lands.
  it('the pristine MarketMapV3 copy is the bundle\'s file, untouched', () => {
    expect(createHash('sha256').update(readFileSync(PRISTINE_JSX)).digest('hex')).toBe('662e4105fd258b6380f1f66f6289629d999aa657b8dc5a4d1303be88e26c0adc');
  });

  it('the amended MarketMapV3.jsx is the pristine copy plus exactly the ruled edits', () => {
    expect(applyAmendments(readFileSync(PRISTINE_JSX, 'utf8'), amendmentsFor('jsx'))).toBe(readFileSync(AMENDED_JSX, 'utf8'));
  });

  // The partition itself, both ways: every entry lands in exactly one file's list, an entry with
  // no `file` is a `.dc.html` entry (which is what leaves all 158 pre-A24 entries unchanged), and
  // the two partitions reassemble into the whole list in the original order.
  it('amendmentsFor partitions the list by file, defaulting to the .dc.html', () => {
    const all = amendments();
    const dc = amendmentsFor('dc');
    const jsx = amendmentsFor('jsx');
    expect(dc.length + jsx.length, 'an amendment landed in neither partition, or in both').toBe(all.length);
    expect(dc.every((a) => (a.file ?? 'dc') === 'dc')).toBe(true);
    expect(jsx.every((a) => a.file === 'jsx')).toBe(true);
    expect(dc.map((a) => a.id)).toEqual(all.filter((a) => a.file === undefined || a.file === 'dc').map((a) => a.id));
    expect(all.filter((a) => a.file === undefined).length, 'every pre-A24 entry declares no file at all').toBeGreaterThan(150);
  });
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run tests/design-amendments.test.ts
```

Expected: FAIL at import resolution — `"./design-amendments" has no exported member 'PRISTINE_JSX'` (and `AMENDED_JSX`, `amendmentsFor`). Not one of the three new cases runs.

- [ ] **Step 3: Create the pristine twin**

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-neighbourhood-shading"
cp "docs/design-reference/design_handoff_practice_match_v3/MarketMapV3.jsx" \
   "docs/design-reference/design_handoff_practice_match_v3/MarketMapV3.rev2.jsx"
cmp "docs/design-reference/design_handoff_practice_match_v3/MarketMapV3.jsx" \
    "docs/design-reference/design_handoff_practice_match_v3/MarketMapV3.rev2.jsx" && echo "byte-identical"
```

Expected: `byte-identical`, and `shasum -a 256` on the copy prints `662e4105fd258b6380f1f66f6289629d999aa657b8dc5a4d1303be88e26c0adc`.

- [ ] **Step 4: Write the minimal implementation**

In `frontend/tests/design-amendments.ts`, replace lines 5-10 with:

```ts
export const PRISTINE = fileURLToPath(new URL('Practice Match V3.rev2.dc.html', V3_DIR));
export const AMENDED = fileURLToPath(new URL('Practice Match V3.dc.html', V3_DIR));
// The bundle's second amendable file (spec §9.2; controller ruling 2026-09-10 §14 Q3). A24 is the
// first family that has to reach `MarketMapV3.jsx` — the component that draws the shading — and
// the engine had only ever known the `.dc.html`. Same contract on both: a frozen pristine twin
// that is never edited, plus the ruled edits, equals the amended file byte for byte.
export const PRISTINE_JSX = fileURLToPath(new URL('MarketMapV3.rev2.jsx', V3_DIR));
export const AMENDED_JSX = fileURLToPath(new URL('MarketMapV3.jsx', V3_DIR));
export const V2 = fileURLToPath(new URL('../../docs/design-reference/design_handoff_practice_match_v2/Practice Match V2.dc.html', import.meta.url));
export const LOCAL_AMENDMENTS_MD = fileURLToPath(new URL('LOCAL_AMENDMENTS.md', V3_DIR));

/** Which bundle file an amendment edits. Absent means `'dc'`, so every entry written before A24
 *  is unchanged and the field never has to be back-filled. */
export type AmendmentFile = 'dc' | 'jsx';

export type Amendment = { id: string; date: string; ruling: string; find: string; replace: string; count: number; text?: string; file?: AmendmentFile };
```

and add, immediately after `applyAmendments` (which is unchanged):

```ts
/** The entries that edit one bundle file, in `amendments()`' own order. `applyAmendments` counts
 *  every `find` at the point it is applied, so the partition has to preserve order: an entry whose
 *  `find` is an earlier entry's output is only correct where that earlier entry has already run. */
export function amendmentsFor(file: AmendmentFile): Amendment[] {
  return amendments().filter((a) => (a.file ?? 'dc') === file);
}
```

- [ ] **Step 5: Run the three new cases to verify they pass**

```bash
cd frontend && npx vitest run tests/design-amendments.test.ts
```

Expected: the three new cases PASS. `the amended reference is the pristine Rev 2 file plus exactly the ruled edits` and `every find occurs exactly count times at the point it is applied, in list order (spec D15)` still pass too — with an empty jsx partition, `amendments()` and `amendmentsFor('dc')` are the same list — but they are corrected in the next step so a jsx entry cannot break them later.

- [ ] **Step 6: Make the two whole-list cases per-file, and require the new bundle file**

In `frontend/tests/design-amendments.test.ts`, replace the case at lines 675-677 with:

```ts
  it('the amended reference is the pristine Rev 2 file plus exactly the ruled edits', () => {
    expect(applyAmendments(pristine, amendmentsFor('dc'))).toBe(readFileSync(AMENDED, 'utf8'));
  });
```

and replace the body of `every 'find' occurs exactly 'count' times at the point it is applied, in list order (spec D15)` (lines 715-731) — its first five lines only, leaving the A2.4/A2.5 ordering assertions below it untouched — with:

```ts
  it('every `find` occurs exactly `count` times at the point it is applied, in list order (spec D15)', () => {
    // Per FILE, since A24: `applyAmendments` walks one string, and an entry that edits
    // MarketMapV3.jsx can never be counted against the .dc.html (it would read 0 and throw).
    for (const [file, from, to] of [
      ['dc', pristine, readFileSync(AMENDED, 'utf8')],
      ['jsx', readFileSync(PRISTINE_JSX, 'utf8'), readFileSync(AMENDED_JSX, 'utf8')]
    ] as const) {
      let out = from;
      for (const a of amendmentsFor(file)) {
        expect(out.split(a.find).length - 1, `${a.id}: find count at the point of application`).toBe(a.count);
        out = out.split(a.find).join(a.replace);
      }
      expect(out, `${file}: pristine + amendments is not the amended file`).toBe(to);
    }
```

In `frontend/tests/reference-bundle.test.ts:25`, replace the file list with:

```ts
    for (const f of ['Practice Match V3.dc.html', 'Practice Match V3.rev2.dc.html', 'LOCAL_AMENDMENTS.md', 'MarketMapV3.jsx', 'MarketMapV3.rev2.jsx', 'README.md', 'CHANGE_LOG.md', 'DEAD_CODE_CHECKLIST.md', 'FILE_INDEX.md', 'support.js', 'image-slot.js', 'Census Data Source Specification.dc.html']) {
```

- [ ] **Step 7: Teach the generator to write both files**

Replace `frontend/scripts/apply-amendments.ts:22-28` with:

```ts
import { readFileSync, writeFileSync } from 'node:fs';
import { AMENDED, AMENDED_JSX, PRISTINE, PRISTINE_JSX, amendments, amendmentsFor, applyAmendments } from '../tests/design-amendments';

// Both bundle files, partitioned by each entry's own `file` (spec §9.2; controller ruling
// 2026-09-10 §14 Q3). An entry with no `file` is a `.dc.html` entry, so this is a no-op for every
// amendment written before A24 — and a jsx list that is EMPTY still rewrites MarketMapV3.jsx from
// its pristine twin, which is the round-trip proof `design-amendments.test.ts` measures.
for (const [pristine, amended, file] of [[PRISTINE, AMENDED, 'dc'], [PRISTINE_JSX, AMENDED_JSX, 'jsx']] as const) {
  const list = amendmentsFor(file);
  const out = applyAmendments(readFileSync(pristine, 'utf8'), list);
  writeFileSync(amended, out);
  console.log(`wrote ${amended}\n  ${list.length} amendments applied, ${out.length} bytes`);
}
console.log(`${amendments().length} amendments in total`);
```

- [ ] **Step 8: Run the generator and prove it changed nothing**

```bash
cd frontend && npm run gen:design && npm run gen:app && cd ..
git diff --exit-code -- "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
  "docs/design-reference/design_handoff_practice_match_v3/MarketMapV3.jsx" \
  frontend/src/App.vue frontend/src/generated/pseudo.css frontend/src/logic.js
```

Expected: `gen:design` prints `158 amendments applied` for the `.dc.html` and `0 amendments applied` for `MarketMapV3.jsx`, then `182 amendments in total`; `git diff --exit-code` exits **0** — the generator reproduced both files byte for byte and regenerating the app changed nothing. **This is R1's measurement.** If `MarketMapV3.jsx` differs at all (a trailing newline, a line ending, an encoding), the two-file shape has a defect and the fallback recorded in the spec's R1 applies: STOP and report.

- [ ] **Step 9: Run the frontend gates**

```bash
cd frontend && npm run typecheck && npx vitest run --coverage && npm run build
```

Expected: PASS, with 100 % lines/branches/functions/statements. `design-amendments.ts` gains one exported function with one branch (`a.file ?? 'dc'`), covered by the partition case; `amendmentsFor('jsx')` returning `[]` covers the false arm.

- [ ] **Step 10: Run the visual, DOM and smoke gates and read the manifest**

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-neighbourhood-shading"
docker compose -f docker-compose.dev.yml up -d
export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_shading
export REDIS_URL=redis://localhost:6380/10 ENVIRONMENT=test API_SECRET_KEY=local_only_secret_change_me
export PW_APP_PORT=5583 PW_REF_PORT=5584 PW_CS_PORT=5585 PW_API_PORT=8157
lsof -nP -iTCP:5583,5584,5585,8157 -sTCP:LISTEN || true
cd frontend && npm run test:visual:baselines && npm run test:e2e
node tests/baseline-manifest.mjs --check || npx vitest run tests/baseline-manifest.test.ts
```

Expected: **`SCREENS.length` passed** from the reference project (A-NS5 — 52 on `main` at `ec79594`, 53 once `feat/card-geography` merges; derive it, never type it), then the `app` project green (visual + DOM + smoke), and `baseline-manifest.test.ts` green with **zero** hashes moved. Nothing in the design changed, so nothing may have moved. A single moved row here is a defect in the engine change: STOP.

- [ ] **Step 11: Commit**

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-neighbourhood-shading"
git add frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts \
  frontend/scripts/apply-amendments.ts frontend/tests/reference-bundle.test.ts \
  "docs/design-reference/design_handoff_practice_match_v3/MarketMapV3.rev2.jsx"
git commit -m "feat(design): the amendment engine reaches a second bundle file

MarketMapV3.jsx gains a frozen pristine twin and Amendment gains file?: 'dc' | 'jsx',
so A24 can change the component that draws the shading through the D15 engine rather
than by hand. The jsx list is empty here on purpose: pristine + [] == amended, byte for
byte, is the round-trip proof, and no approved pixel and no frozen hash moves.

Controller ruling 2026-09-10, spec 2026-09-10-neighbourhood-shading-design.md §14 Q3.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 2: The `geoJson` map primitive — one shared canvas renderer, nothing calls it yet

`frontend/src/map/engine.ts` has exactly one shading primitive and it is a rectangle. This task adds `geoJson` beside it, implements it in the Leaflet engine on the SAME shared canvas renderer every rectangle already uses, teaches the test stub `L.geoJSON`, and adds `geoJSON` to the import-boundary regex so a stray `L.geoJSON(` outside `map/engines/*` is caught the way every other Leaflet call is. Nothing calls the new method: this task is a pure addition and moves no pixel.

**Re-basing states: NONE.** **The thirteen frozen hashes must not move** (nothing renders differently).

**Files:**
- Modify: `frontend/src/map/engine.ts:5-6` (the `AreaStyle` comment), and the interface at `:33` (add `geoJson` after `rectangle`)
- Modify: `frontend/src/map/engines/leaflet.ts:1` (the type import), `:49-51` (the renderer comment), and after `rectangle` at `:92`
- Modify: `frontend/src/map/testing/leaflet-stub.ts:31` (a `geoJSON` factory after `rectangle`)
- Modify: `frontend/src/map/boundary.test.ts:15` (the alternation)
- Test: `frontend/src/map/engines/leaflet.test.ts`, `frontend/src/map/boundary.test.ts`

**Interfaces:**
- Consumes: nothing from an earlier task.
- Produces, from `frontend/src/map/engine.ts`:
  ```ts
  export interface AreaFeature {
    type: 'Feature';
    id?: string | number;
    properties: Record<string, unknown>;
    geometry: { type: string; coordinates: unknown };
  }
  export interface AreaFeatureCollection { type: 'FeatureCollection'; features: AreaFeature[] }
  // on MapEngine, immediately after `rectangle`:
  geoJson(
    fc: AreaFeatureCollection,
    styleFor: (f: AreaFeature) => AreaStyle,
    group: string,
    tooltipFor?: (f: AreaFeature) => TooltipSpec,
    onClick?: (f: AreaFeature) => void
  ): Handle;
  ```
  `AreaStyle` (`{ fillColor: string; fillOpacity: number; stroke?: boolean; interactive?: boolean }`), `TooltipSpec` and `Handle` are unchanged. Task 4's `MarketMapView.vue` is the only caller; Task 4 also relies on the stub's recorded call name being exactly `'geoJSON'` and on each created child layer carrying the `FakeLayer` shape.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/map/engines/leaflet.test.ts`, inside its existing top-level `describe`. `mounted()` and `stub` are that file's own helpers (a mounted `LeafletMapEngine` over `installLeafletStub()`); use whichever names the file already uses for them — the assertions below are what matter.

```ts
  // A24 (spec 2026-09-10, D-C34/D-C37): the mosaic's rectangles become one L.geoJSON layer of
  // real Census boundary polygons. The renderer is the load-bearing part — `leaflet.ts`'s own
  // note, "ONE canvas renderer per mount, shared by every mosaic cell. A renderer per rectangle
  // is what makes a mosaic this dense unusable" — survives the mosaic, so it is asserted here
  // the way it is asserted for `rectangle`.
  const fc = {
    type: 'FeatureCollection' as const,
    features: [
      { type: 'Feature' as const, id: '78704', properties: { geo_id: '78704', color: '#4c9a6a', tip: '<b>78704</b>' }, geometry: { type: 'Polygon', coordinates: [[[-97.8, 30.2], [-97.7, 30.2], [-97.7, 30.3], [-97.8, 30.2]]] } },
      { type: 'Feature' as const, id: '78745', properties: { geo_id: '78745', color: '#e6e6e6', tip: '<b>78745</b>' }, geometry: { type: 'Polygon', coordinates: [[[-97.9, 30.1], [-97.8, 30.1], [-97.8, 30.2], [-97.9, 30.1]]] } }
    ]
  };
  const style = (f: { properties: Record<string, unknown> }) => ({ fillColor: f.properties.color as string, fillOpacity: 0.5, stroke: false, interactive: true });

  it('geoJson draws the collection on the SHARED canvas renderer, in the named group', async () => {
    const { engine, stub } = await mounted();
    engine.geoJson(fc, style, 'overlay');
    const call = stub.calls.find((c) => c.fn === 'geoJSON')!;
    expect(call, 'geoJson did not reach L.geoJSON').toBeDefined();
    expect(call.args[0]).toBe(fc);
    expect((call.args[1] as { renderer: unknown }).renderer, 'a renderer per layer is what made the mosaic unusable').toBe(stub.canvas);
    // The style function is forwarded, not pre-applied: Leaflet calls it per feature.
    expect((call.args[1] as { style: (f: unknown) => unknown }).style(fc.features[0])).toEqual({ renderer: stub.canvas, stroke: false, fillColor: '#4c9a6a', fillOpacity: 0.5, interactive: true });
    expect((call.args[1] as { style: (f: unknown) => unknown }).style(fc.features[1])).toEqual({ renderer: stub.canvas, stroke: false, fillColor: '#e6e6e6', fillOpacity: 0.5, interactive: true });
  });

  it('geoJson binds a tooltip and a click handler PER FEATURE, and Handle.remove() removes the layer', async () => {
    const { engine, stub } = await mounted();
    const clicked: string[] = [];
    const handle = engine.geoJson(
      fc, style, 'overlay',
      (f) => ({ html: f.properties.tip as string, sticky: true, className: 'rf-tip' }),
      (f) => clicked.push(f.properties.geo_id as string)
    );
    const layer = stub.calls.find((c) => c.fn === 'geoJSON')!;
    const children = (layer as unknown as { features?: unknown[] }).features
      ?? (stub.L as { lastGeoJson?: { features: unknown[] } }).lastGeoJson!.features;
    expect(children).toHaveLength(2);
    for (const [i, child] of (children as { tooltip?: { text: string; opts: unknown }; on_click?: () => void }[]).entries()) {
      expect(child.tooltip!.text).toBe(fc.features[i].properties.tip);
      expect(child.tooltip!.opts).toEqual({ sticky: true, className: 'rf-tip' });
      child.on_click!();
    }
    expect(clicked).toEqual(['78704', '78745']);
    handle.remove();
    expect((stub.map.added as { added?: unknown[] }[]).some((g) => (g.added ?? []).length > 0), 'the layer survived remove()').toBe(false);
  });

  it('geoJson is inert after destroy(), like every other handle-returning method', async () => {
    const { engine, stub } = await mounted();
    engine.destroy();
    const before = stub.calls.length;
    expect(() => engine.geoJson(fc, style, 'overlay').remove()).not.toThrow();
    expect(stub.calls.length, 'a destroyed engine still reached Leaflet').toBe(before);
  });
```

And in `frontend/src/map/boundary.test.ts:15`, extend the alternation:

```ts
      return /from\s+['"]leaflet|require\(['"]leaflet|window\.L\b|\bL\.(map|tileLayer|marker|divIcon|circle|rectangle|geoJSON|canvas|layerGroup|control)\(/.test(s);
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd frontend && npx vitest run src/map/engines/leaflet.test.ts src/map/boundary.test.ts
```

Expected: the three new cases FAIL with `engine.geoJson is not a function`, and `npm run typecheck` would fail with `Property 'geoJson' does not exist on type 'MapEngine'`. `boundary.test.ts` still passes (no `L.geoJSON(` exists yet outside the engines directory — and none ever will).

- [ ] **Step 3: Write the minimal implementation**

In `frontend/src/map/engine.ts`, replace lines 5-6 with:

```ts
/** A shaded area: a filled, strokeless polygon on the shared canvas renderer. Was V3's mosaic
 *  CELL until A24 (spec 2026-09-10); it is now a real Census boundary polygon, and the style
 *  contract did not have to change for that. */
export interface AreaStyle { fillColor: string; fillOpacity: number; stroke?: boolean; interactive?: boolean }
/** One boundary polygon as the API and the design's own fixture both spell it — RFC 7946, with
 *  whatever foreign members the caller's `styleFor`/`tooltipFor` read out of `properties`. The
 *  geometry is passed to Leaflet untouched; nothing in this layer inspects it. */
export interface AreaFeature { type: 'Feature'; id?: string | number; properties: Record<string, unknown>; geometry: { type: string; coordinates: unknown } }
export interface AreaFeatureCollection { type: 'FeatureCollection'; features: AreaFeature[] }
```

and add to the `MapEngine` interface, immediately after the `rectangle` line:

```ts
  geoJson(fc: AreaFeatureCollection, styleFor: (f: AreaFeature) => AreaStyle, group: string, tooltipFor?: (f: AreaFeature) => TooltipSpec, onClick?: (f: AreaFeature) => void): Handle;
```

In `frontend/src/map/engines/leaflet.ts`, extend the type import on line 1 to include `AreaFeature` and `AreaFeatureCollection`:

```ts
import type { AreaFeature, AreaFeatureCollection, AreaStyle, BaseKind, CircleStyle, Handle, LatLng, MapEngine, MarkerOptions, MountOptions, RingStyle, TooltipSpec } from '../engine';
```

replace the comment at `:49-50` with:

```ts
    // ONE canvas renderer per mount, shared by every shaded area (MarketMapV3.jsx). A renderer
    // per polygon is what made the 12,560-rectangle mosaic unusable, and the rule survives the
    // mosaic: `geoJson` passes this same renderer to L.geoJSON, so every boundary polygon in a
    // metro draws into one canvas.
```

and add, immediately after the `rectangle` method:

```ts
  // A24 (spec 2026-09-10; D-C34/D-C35): one L.geoJSON layer per fill layer, on the shared canvas
  // renderer. `renderer` is set at the TOP level rather than only inside `style`, because that is
  // the option L.GeoJSON forwards to each path it constructs (`geometryToLayer(geojson, options)`);
  // the style function repeats it so a later `setStyle` cannot drop it.
  geoJson(fc: AreaFeatureCollection, styleFor: (f: AreaFeature) => AreaStyle, group: string, tooltipFor?: (f: AreaFeature) => TooltipSpec, onClick?: (f: AreaFeature) => void): Handle {
    if (this.destroyed) return NOOP_HANDLE;
    const layer = this.L.geoJSON(fc, {
      renderer: this.canvas,
      style: (f: AreaFeature) => {
        const s = styleFor(f);
        return { renderer: this.canvas, stroke: s.stroke ?? false, fillColor: s.fillColor, fillOpacity: s.fillOpacity, interactive: s.interactive ?? true };
      },
      onEachFeature: (f: AreaFeature, l: { bindTooltip(html: string, opts: unknown): unknown; on(ev: string, cb: () => void): unknown }) => {
        if (tooltipFor) { const t = tooltipFor(f); l.bindTooltip(t.html, tipOptions(t)); }
        if (onClick) l.on('click', () => onClick(f));
      }
    });
    layer.addTo(this.group(group));
    return { remove: () => layer.remove(), openTooltip: () => layer.openTooltip() };
  }
```

In `frontend/src/map/testing/leaflet-stub.ts`, add after the `rectangle` entry on line 31:

```ts
    // L.geoJSON constructs one path per feature and hands each to `onEachFeature`, which is where
    // MarketMapView's tooltip and click handler are bound — so the fake has to construct them too,
    // or a per-feature binding would be untestable.
    geoJSON: rec('geoJSON', (data: { features?: unknown[] }, options: { onEachFeature?: (f: unknown, l: unknown) => void }) => {
      const group = Object.assign(new FakeLayer(), { data, options, features: [] as FakeLayer[] });
      for (const f of data?.features ?? []) {
        const child = new FakeLayer();
        group.features.push(child);
        options?.onEachFeature?.(f, child);
      }
      return group;
    }),
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd frontend && npx vitest run src/map/engines/leaflet.test.ts src/map/boundary.test.ts && npm run typecheck
```

Expected: PASS. The three new cases are green, `boundary.test.ts` still reports `offenders: []` (the only `L.geoJSON(` in the tree is inside `map/engines/`, which `ALLOWED` exempts), and `vue-tsc` is clean.

- [ ] **Step 5: Run the frontend coverage gate**

```bash
cd frontend && npx vitest run --coverage
```

Expected: PASS at 100 %. The new method's branches are `this.destroyed`, `s.stroke ?? false`, `s.interactive ?? true`, `if (tooltipFor)` and `if (onClick)`; the three cases above take both arms of each (case 1 passes neither optional callback, case 2 passes both, case 3 takes the destroyed arm; `stroke: false`/`interactive: true` are explicit in `style` and the `??` fallbacks are exercised by a fourth assertion — add `engine.geoJson(fc, () => ({ fillColor: '#000', fillOpacity: 1 }), 'overlay')` to case 1 and assert the style function returns `stroke: false, interactive: true` if the coverage report says otherwise).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/map/engine.ts frontend/src/map/engines/leaflet.ts \
  frontend/src/map/engines/leaflet.test.ts frontend/src/map/testing/leaflet-stub.ts \
  frontend/src/map/boundary.test.ts
git commit -m "feat(map): a geoJson primitive on the shared canvas renderer

One L.geoJSON layer per fill layer, styled and tooltipped per feature, on the same
single canvas renderer every rectangle already uses. Nothing calls it yet; A24 swaps
the mosaic onto it next. boundary.test.ts's alternation gains geoJSON so a stray call
outside map/engines is caught like every other Leaflet call.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```


---

## Task 3: The design's own boundary fixture, generated from real `geo_area` rows

A24.1 puts a `FeatureCollection` per fill layer into the design's state literal, and the geometry in it has to be REAL — the whole point of the swap is that the edges are Census lines rather than grid artefacts. This task builds the generator, runs it against real TIGER data loaded into this worktree's own database, and commits the result as one generated TypeScript module that Task 4's amendment interpolates.

The fixture carries **geometry and a centroid, and no figures**. `geo_metric` does not exist yet, ACS at ZCTA is not loaded, and a design fixture with invented numbers in it is the failure this programme keeps being bitten by. The design's own script assigns each polygon the value of the nearest of the design's own nine Austin communities in Task 4 — `mosaicCells`'s own rule, "spatial ASSIGNMENT of existing community data, not interpolation, and not new data", applied to real polygons.

**Re-basing states: NONE.** Nothing imports the new module yet. **The thirteen frozen hashes must not move.**

**Files:**
- Create: `scripts/export_design_boundaries.py`
- Create: `tests/scripts/test_export_design_boundaries.py`
- Create: `frontend/tests/design-boundary-fixture.ts` (generated; committed)
- Create: `frontend/tests/design-boundary-fixture.test.ts`
- Test: both of the above

**Interfaces:**
- Consumes: nothing from an earlier task.
- Produces, from `scripts/export_design_boundaries.py`:
  ```python
  DESIGN_CBSA: str = "12420"                  # Austin–Round Rock–San Marcos, the design's own metro
  LEVELS: tuple[str, ...] = ("860", "160", "050")
  SIMPLIFY_DEG: float = 0.005                 # ten times coarser than the write-time tolerance Census spec §2b recommends
  MAX_FIXTURE_BYTES: int = 120_000
  def export(conn: psycopg2.extensions.connection, cbsa_geoid: str, geo_vintage: str) -> dict[str, dict[str, object]]
  def module_text(fixture: dict[str, dict[str, object]]) -> str
  def main(argv: list[str] | None = None) -> int
  ```
- Produces, from `frontend/tests/design-boundary-fixture.ts`:
  ```ts
  export const DESIGN_AREAS_LITERAL: string;
  ```
  a single line of pure-ASCII JSON text, shaped `{"860":{"type":"FeatureCollection","features":[…]},"160":{…},"050":{…}}`, where every feature is `{"type":"Feature","id":"<geo_id>","properties":{"geo_id":"…","name":"…","c":[<lat>,<lng>]},"geometry":{…}}`. Task 4's amendment `A24_1` interpolates it verbatim into the design's `state` literal as `areas: <literal>,` — JSON is valid JavaScript object-literal syntax, so no conversion happens anywhere.

- [ ] **Step 1: Load the boundaries this worktree's database needs**

Not a code step, but a prerequisite the generator cannot invent, and the one step in this plan that reaches the network. `load_boundaries` downloads the TIGER cartographic-boundary shapefiles from `https://www2.census.gov/geo/tiger/GENZ2023/shp` — **no `CENSUS_API_KEY` is involved**, only the `CENSUS_CONTACT_EMAIL` User-Agent, which is why an implementer can run it and the ACS load in Task 6 is left to the controller.

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-neighbourhood-shading"
export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_shading
export CENSUS_CONTACT_EMAIL=engineering@vinfoundation.org
poetry run python scripts/migrate.py
poetry run python - <<'PY'
import os, httpx, psycopg2
from app.census.tiger import load_boundaries
conn = psycopg2.connect(os.environ["DATABASE_URL"]); conn.autocommit = True
with httpx.Client(timeout=300, headers={"User-Agent": f"practice-match ({os.environ['CENSUS_CONTACT_EMAIL']})"}) as http:
    print(load_boundaries(conn, http, ["48"], "2023"))
PY
psql "$DATABASE_URL" -c "SELECT summary_level, count(*) FROM geo_area WHERE vintage='2023' GROUP BY 1 ORDER BY 1"
psql "$DATABASE_URL" -c "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES ('tiger_cb','2023',now(),'plan-task-3') ON CONFLICT (dataset_key) DO UPDATE SET vintage=EXCLUDED.vintage"
```

Expected: rows at `010`, `040`, `050`, `140`, `160`, `310` and `860`. **Confirm the ZCTA count before going on** — spec §2.3 records it as unverified, and D-C34's figure is "about 130 ZCTAs across the Austin metro":

```bash
psql "$DATABASE_URL" -c "SELECT count(*) FROM geo_area g JOIN geo_area m ON m.summary_level='310' AND m.vintage=g.vintage AND m.geo_id='12420' WHERE g.summary_level='860' AND g.vintage='2023' AND ST_Contains(m.geom, g.centroid)"
```

Expected: a count in the low hundreds. If it is `0`, the GENZ2023 ZCTA file did not load (`tiger.py:207` falls back to GENZ2020 on a 404 — check `ingest_run`), and **STOP**: the fixture cannot be generated and D-C34's geography needs re-confirming before anything downstream is built.

- [ ] **Step 2: Write the failing test**

Create `tests/scripts/test_export_design_boundaries.py`:

```python
"""scripts/export_design_boundaries.py — the design's own boundary fixture (plan Task 3).

The fixture is GEOMETRY ONLY: `geo_metric` does not exist when it is generated and ACS at ZCTA is
not loaded, so a fixture carrying figures would be carrying invented ones. Each feature carries its
own centroid instead, and the design's own script (A24.2's `areaSet`) assigns it the value of the
nearest of the design's nine Austin communities — `mosaicCells`'s own assignment rule, applied to
real polygons."""
import json
import runpy
import sys
from pathlib import Path

import psycopg2
import pytest

from scripts import export_design_boundaries as EB

ROOT = Path(__file__).resolve().parent.parent.parent

# A 1-degree metro square, one ZCTA inside it, one place inside it, one county inside it, and one
# ZCTA whose centroid is OUTSIDE it — the case that proves the scope really is the metro.
_METRO = "POLYGON((-98 30,-97 30,-97 31,-98 31,-98 30))"
_INSIDE = "POLYGON((-97.8 30.2,-97.7 30.2,-97.7 30.3,-97.8 30.3,-97.8 30.2))"
_OUTSIDE = "POLYGON((-96.8 30.2,-96.7 30.2,-96.7 30.3,-96.8 30.3,-96.8 30.2))"


def _geo(conn: psycopg2.extensions.connection, geo_id: str, level: str, name: str, wkt: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) "
            "VALUES (%s, %s, '2023', %s, ST_Multi(ST_GeomFromText(%s, 4269)), ST_Centroid(ST_GeomFromText(%s, 4269)))",
            (geo_id, level, name, wkt, wkt),
        )


@pytest.fixture
def world(conn: psycopg2.extensions.connection) -> psycopg2.extensions.connection:
    _geo(conn, "12420", "310", "Austin-Round Rock-San Marcos, TX Metro Area", _METRO)
    _geo(conn, "78704", "860", "ZCTA5 78704", _INSIDE)
    _geo(conn, "77001", "860", "ZCTA5 77001", _OUTSIDE)
    _geo(conn, "4805000", "160", "Austin", _INSIDE)
    _geo(conn, "48453", "050", "Travis County", _INSIDE)
    return conn


def test_export_returns_one_collection_per_ruled_level_scoped_to_the_metro(world: psycopg2.extensions.connection) -> None:
    fixture = EB.export(world, EB.DESIGN_CBSA, "2023")
    assert sorted(fixture) == ["050", "160", "860"]
    assert [f["id"] for f in fixture["860"]["features"]] == ["78704"], "a ZCTA outside the metro was exported"
    assert [f["id"] for f in fixture["160"]["features"]] == ["4805000"]
    assert [f["id"] for f in fixture["050"]["features"]] == ["48453"]
    for collection in fixture.values():
        assert collection["type"] == "FeatureCollection"


def test_every_feature_carries_a_geo_id_a_name_a_centroid_and_a_geometry(world: psycopg2.extensions.connection) -> None:
    feature = EB.export(world, EB.DESIGN_CBSA, "2023")["860"]["features"][0]
    assert feature["type"] == "Feature" and feature["id"] == "78704"
    assert feature["properties"]["geo_id"] == "78704"
    assert feature["properties"]["name"] == "ZCTA5 78704"
    lat, lng = feature["properties"]["c"]
    assert 30.2 < lat < 30.3 and -97.8 < lng < -97.7, "the centroid is not [lat, lng] in WGS84"
    assert feature["geometry"]["type"] in ("Polygon", "MultiPolygon")
    # 4326, not 4269: geo_area.geom is NAD83 and GeoJSON is WGS84.
    assert -98 < feature["geometry"]["coordinates"][0][0][0][0] < -97 or -98 < feature["geometry"]["coordinates"][0][0][0] < -97


def test_the_module_text_is_pure_ascii_one_line_and_names_its_generator(world: psycopg2.extensions.connection) -> None:
    text = EB.module_text(EB.export(world, EB.DESIGN_CBSA, "2023"))
    assert text.isascii(), "a non-ASCII byte would change the design file's encoding footprint"
    assert "scripts/export_design_boundaries.py" in text, "the generated file must name its generator"
    body = [line for line in text.split("\n") if line.startswith("export const DESIGN_AREAS_LITERAL")]
    assert len(body) == 1, "the literal must be exactly one line, so a diff on it is one line"
    literal = body[0].split(" = ", 1)[1].rstrip(";").strip()
    assert literal.startswith("'") and literal.endswith("'")
    assert json.loads(literal[1:-1].replace("\\'", "'").replace("\\\\", "\\"))["860"]["features"][0]["id"] == "78704"


def test_main_writes_the_module_and_reports_the_counts(world: psycopg2.extensions.connection, scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "design-boundary-fixture.ts"
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert EB.main(["--out", str(out), "--vintage", "2023"]) == 0
    assert "860=1" in capsys.readouterr().out
    assert out.read_text(encoding="utf-8").count("DESIGN_AREAS_LITERAL") == 1


def test_main_refuses_without_a_database_url(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert EB.main(["--out", str(tmp_path / "x.ts")]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_main_refuses_a_fixture_over_the_cap(world: psycopg2.extensions.connection, scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """The cap is not decoration: the literal is embedded in a 306 KB design file that
    `applyAmendments` string-searches once per amendment."""
    out = tmp_path / "too-big.ts"
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(EB, "MAX_FIXTURE_BYTES", 10)
    assert EB.main(["--out", str(out), "--vintage", "2023"]) == 1
    assert "over the 10" in capsys.readouterr().err
    assert not out.exists(), "a refused fixture must not be written"


def test_the_main_guard_is_covered(monkeypatch: pytest.MonkeyPatch) -> None:
    """runpy re-executes the file in THIS process with __name__ == "__main__", so pytest-cov
    sees the guard (the idiom tests/scripts/test_seed_listings.py established)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["export_design_boundaries.py"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / "export_design_boundaries.py"), run_name="__main__")
    assert exc.value.code == 2
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-neighbourhood-shading"
poetry run pytest tests/scripts/test_export_design_boundaries.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'scripts.export_design_boundaries'`.

- [ ] **Step 4: Write the minimal implementation**

Create `scripts/export_design_boundaries.py`:

```python
"""Generate the DESIGN's own boundary fixture from real `geo_area` rows (plan Task 3, spec §9.4).

Amendment A24.1 puts a `FeatureCollection` per fill layer into the approved design's `state`
literal, and the geometry in it has to be real: the whole point of this change is that the edges
are Census lines rather than the grid artefacts `mosaicCells` drew. This writes that literal once,
as a generated TypeScript module the amendment interpolates.

GEOMETRY ONLY, deliberately. `geo_metric` does not exist when this runs and ACS carries no ZCTA
row, so a fixture with figures in it would be a fixture with INVENTED figures in it. Each feature
carries its own centroid instead, and the design's own `areaSet` (A24.2) assigns it the value of
the nearest of the design's nine Austin communities — `mosaicCells`'s own rule ("spatial ASSIGNMENT
of existing community data, not interpolation, and not new data") applied to real polygons.

Simplified at 0.005 degrees — TEN TIMES coarser than the ~0.0005 degrees Census spec §2b
recommends for production write-time simplification — because this is a fixture, in the same class
as `design-listings.mjs`'s `name: null`: pixels only ever compare the reference against an app fed
this same fixture, and production geometry is proved by pytest, not by pixels.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import psycopg2
import psycopg2.extensions

# Austin-Round Rock-San Marcos: the design's own metro, and `MARKETS`'s default (`logic.js`).
DESIGN_CBSA = "12420"
# D-C35's three, in the order the fixture lists them: ZCTA (income), place (growth), county (econ).
LEVELS: tuple[str, ...] = ("860", "160", "050")
SIMPLIFY_DEG = 0.005
MAX_FIXTURE_BYTES = 120_000

# Scoped by CENTROID-inside-the-metro, not by ST_Intersects: a place or a ZCTA that merely grazes
# the metro boundary belongs to its neighbour, and an intersects test would drag a ring of
# half-outside polygons into a fixture whose whole job is to be small. The CBSA row is joined at
# the SAME vintage as the geography, never at a hard-coded one.
_SQL = """
SELECT g.summary_level, g.geo_id, g.name,
       ST_AsGeoJSON(ST_SimplifyPreserveTopology(ST_Transform(g.geom, 4326), %(tol)s), 5) AS geometry,
       ST_Y(ST_Transform(g.centroid, 4326)) AS lat,
       ST_X(ST_Transform(g.centroid, 4326)) AS lng
  FROM geo_area g
  JOIN geo_area m ON m.summary_level = '310' AND m.vintage = g.vintage AND m.geo_id = %(cbsa)s
 WHERE g.summary_level = ANY(%(levels)s) AND g.vintage = %(vintage)s
   AND ST_Contains(m.geom, g.centroid)
 ORDER BY g.summary_level, g.geo_id
"""


def export(conn: psycopg2.extensions.connection, cbsa_geoid: str, geo_vintage: str) -> dict[str, dict[str, Any]]:
    """One `FeatureCollection` per ruled summary level, keyed by that level."""
    fixture: dict[str, dict[str, Any]] = {level: {"type": "FeatureCollection", "features": []} for level in LEVELS}
    with conn.cursor() as cur:
        cur.execute(_SQL, {"tol": SIMPLIFY_DEG, "cbsa": cbsa_geoid, "levels": list(LEVELS), "vintage": geo_vintage})
        for level, geo_id, name, geometry, lat, lng in cur.fetchall():
            fixture[level]["features"].append({
                "type": "Feature",
                "id": geo_id,
                "properties": {"geo_id": geo_id, "name": name, "c": [round(float(lat), 5), round(float(lng), 5)]},
                "geometry": json.loads(geometry),
            })
    return fixture


def module_text(fixture: dict[str, dict[str, Any]]) -> str:
    """The generated TypeScript module. The payload is `ensure_ascii=True` JSON on ONE line, so the
    design file gains no non-ASCII byte and a regeneration is a one-line diff; `\\` and `'` are
    escaped because it is emitted as a single-quoted TS string, and it is interpolated back into
    A24.1's `replace` verbatim, since JSON is valid JavaScript object-literal syntax."""
    payload = json.dumps(fixture, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    escaped = payload.replace("\\", "\\\\").replace("'", "\\'")
    counts = ", ".join(f"{level}: {len(fixture[level]['features'])}" for level in LEVELS)
    return (
        "// GENERATED by scripts/export_design_boundaries.py — never hand-edited.\n"
        "//\n"
        "// The DESIGN's own boundary fixture (amendment A24.1, spec 2026-09-10 §9.4): real\n"
        "// `geo_area` polygons for the design's own Austin metro, at D-C35's three geographies —\n"
        "// '860' ZCTA (income), '160' place (growth), '050' county (econ) — simplified at 0.005\n"
        "// degrees and scoped to polygons whose centroid falls inside CBSA 12420.\n"
        "//\n"
        "// GEOMETRY ONLY. Each feature carries `c: [lat, lng]`, its own centroid, and no figure:\n"
        "// the design's `areaSet` assigns it the value of the nearest of the design's own nine\n"
        "// Austin communities, which is `mosaicCells`'s assignment rule on real polygons.\n"
        f"// Feature counts at generation: {counts}.\n"
        f"export const DESIGN_AREAS_LITERAL = '{escaped}';\n"
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="write the design's boundary fixture from geo_area")
    p.add_argument("--out", default="frontend/tests/design-boundary-fixture.ts")
    p.add_argument("--cbsa", default=DESIGN_CBSA)
    p.add_argument("--vintage", default="2023")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[export_design_boundaries] DATABASE_URL is not set", file=sys.stderr)
        return 2
    conn = psycopg2.connect(dsn)
    try:
        fixture = export(conn, args.cbsa, args.vintage)
    finally:
        conn.close()
    text = module_text(fixture)
    size = len(text.encode("utf-8"))
    if size > MAX_FIXTURE_BYTES:
        print(f"[export_design_boundaries] fixture is {size} bytes, over the {MAX_FIXTURE_BYTES} cap", file=sys.stderr)
        return 1
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote " + args.out + ": " + ", ".join(f"{level}={len(fixture[level]['features'])}" for level in LEVELS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
poetry run pytest tests/scripts/test_export_design_boundaries.py -q -W error
```

Expected: `8 passed`.

- [ ] **Step 6: Generate the real fixture and read its size**

```bash
export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_shading
poetry run python scripts/export_design_boundaries.py
wc -c frontend/tests/design-boundary-fixture.ts
```

Expected: a line like `wrote frontend/tests/design-boundary-fixture.ts: 860=NNN, 160=NN, 050=N` and a size **at or under 120,000 bytes**. If it refuses at the cap, raise `SIMPLIFY_DEG` in steps of 0.005 and regenerate until it fits, recording the value used in the commit message — a coarser fixture is still correct, because it is a fixture. Note the three counts: the next step pins them from the file rather than by hand.

- [ ] **Step 7: Write the fixture's own pins**

Create `frontend/tests/design-boundary-fixture.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { DESIGN_AREAS_LITERAL } from './design-boundary-fixture';

// The fixture is generated (scripts/export_design_boundaries.py) and embedded verbatim into
// amendment A24.1's `replace`, which means it is embedded verbatim into the approved design file.
// Everything asserted here is a property the amendment depends on; nothing here is a number typed
// by hand — the counts are read from the fixture itself.
describe('the design boundary fixture (A24.1, spec §9.4)', () => {
  const fixture = JSON.parse(DESIGN_AREAS_LITERAL) as Record<string, { type: string; features: { type: string; id: string; properties: { geo_id: string; name: string; c: [number, number] }; geometry: { type: string } }[] }>;

  it('carries one FeatureCollection per ruled geography, and nothing else (D-C35)', () => {
    expect(Object.keys(fixture).sort()).toEqual(['050', '160', '860']);
    for (const level of Object.keys(fixture)) expect(fixture[level].type).toBe('FeatureCollection');
  });

  it('is valid JavaScript object-literal syntax, on one line, so A24.1 can interpolate it raw', () => {
    expect(DESIGN_AREAS_LITERAL).not.toContain('\n');
    // A JSON text is a JS object literal; this proves it parses as one on the runtime that will
    // evaluate the design's script, not only as JSON.
    expect(() => new Function(`return ${DESIGN_AREAS_LITERAL};`)()).not.toThrow();
  });

  it('every feature carries the geo_id, the name, the centroid and the geometry areaSet reads', () => {
    for (const level of Object.keys(fixture)) {
      expect(fixture[level].features.length, `${level} is empty`).toBeGreaterThan(0);
      for (const f of fixture[level].features) {
        expect(f.type).toBe('Feature');
        expect(f.id).toBe(f.properties.geo_id);
        expect(typeof f.properties.name).toBe('string');
        expect(f.properties.c).toHaveLength(2);
        const [lat, lng] = f.properties.c;
        // The design's own metro. A centroid outside it is a scoping bug in the generator.
        expect(lat, `${f.id} is not in the Austin metro`).toBeGreaterThan(29);
        expect(lat).toBeLessThan(32);
        expect(lng).toBeGreaterThan(-99);
        expect(lng).toBeLessThan(-96);
        expect(['Polygon', 'MultiPolygon']).toContain(f.geometry.type);
      }
    }
    // No feature carries a figure: the design assigns those from its own communities (§9.4).
    const props = fixture['860'].features.flatMap((f) => Object.keys(f.properties));
    expect([...new Set(props)].sort()).toEqual(['c', 'geo_id', 'name']);
  });

  it('is pure ASCII and inside the 120 KB cap the design file can carry', () => {
    const source = readFileSync(fileURLToPath(new URL('design-boundary-fixture.ts', import.meta.url)), 'utf8');
    expect(/^[\x00-\x7F]*$/.test(source), 'a non-ASCII byte reaches the design file through A24.1').toBe(true);
    expect(Buffer.byteLength(source, 'utf8')).toBeLessThanOrEqual(120_000);
    expect(source, 'the generated file must name its generator').toContain('scripts/export_design_boundaries.py');
  });
});
```

- [ ] **Step 8: Run the frontend gates**

```bash
cd frontend && npx vitest run tests/design-boundary-fixture.test.ts && npm run typecheck && npx vitest run --coverage
```

Expected: PASS at 100 %. The new module is a single exported constant and adds no branch.

- [ ] **Step 9: Run the backend gate**

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-neighbourhood-shading"
poetry run ruff check app tests scripts && poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e --cov-fail-under=100
```

Expected: PASS at 100 % lines and branches. `export_design_boundaries.py`'s four branches (`if not dsn` both ways, `if size > MAX_FIXTURE_BYTES` both ways) and its main guard are all covered by Step 2's cases.

- [ ] **Step 10: Commit**

```bash
git add scripts/export_design_boundaries.py tests/scripts/test_export_design_boundaries.py \
  frontend/tests/design-boundary-fixture.ts frontend/tests/design-boundary-fixture.test.ts
git commit -m "feat(design): generate the design's boundary fixture from real geo_area rows

Real TIGER polygons for the design's own Austin metro at the three ruled geographies
(860 ZCTA, 160 place, 050 county), simplified at 0.005 degrees, scoped by centroid to
CBSA 12420, emitted as one generated TypeScript constant under 120 KB. Geometry and a
centroid only: geo_metric does not exist yet and a fixture with figures would be a
fixture with invented figures. A24.1 interpolates it next.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```


---

## Task 4: A24 — the mosaic out, real polygons in, on both targets at once

The design draws the shading itself, so the app and the reference must move in the same commit or every Browse state fails and no tolerance can be relaxed to make it pass. Fourteen amendment entries — nine in `Practice Match V3.dc.html`, four in `MarketMapV3.jsx`, and one that is two template edits — plus the Vue port's own swap, plus the deletion of `mosaic.js` and its nine cases.

**Re-basing states: DERIVE THE SET, do not copy the count.** A state re-bases if and only if it mounts a map, and `MarketMapView` is mounted in exactly two places (the desktop Browse column and the phone frame's map tab — find the lines, they move).

> **MEASURED IN TASK 4, 2026-09-11: SIXTEEN, not the thirteen written below.** The rule is right and the count was stale: A26 (the filter-bar dropdowns, merged after this plan was cut) added `browse-filter-menu`, `browse-more-filters` and `browse-more-filters-menu`, all three of them DESKTOP BROWSE captures that therefore mount the map. Predicted sixteen before running the generator and measured sixteen, the same set, by hashing every baseline before and after — exactly the class of stale literal A-NS5 rewrote the Preconditions block for.

| Re-basing | Why |
|---|---|
| `browse`, `browse-layer-menu`, `browse-compare-open`, `browse-legend-collapsed`, `browse-layers-open`, `browse-market-panel`, `browse-metro-menu`, `browse-filter-menu`, `browse-more-filters`, `browse-more-filters-menu`, `header-give-menu`, `browse-panel-lightbox`, `header-1100`, `header-1000` | the desktop Browse map (14) |
| `mobile-map`, `mobile-sheet` | the phone frame's map (2) |

`interest-modal`, `detail`, `detail-lightbox` and `detail-lightbox-next` pass THROUGH Browse on their way but capture the detail screen, where the map is unmounted; they must not move. `mobile-detail` calls `waitMap` on its way to the detail screen for the same reason and must not move either — which makes it the sharpest single check in the set, because it is both frozen and map-adjacent.

**The invariant: `frontend/tests/baseline-manifest.json`'s thirteen frozen hashes must not move.** Not one of them mounts a map. A moved hash means the change leaked outside Browse: **stop with NEEDS_CONTEXT and do not re-pin**.

**Counts after this task — REWRITTEN AS DELTAS by A-NS5, because every absolute here had rotted.** Run the Preconditions script FIRST and read `literals`, `entries`, `rows`, `families` off it; this task's targets are `literals + 15`, `entries + 15`, `rows + 15`, `families + 1` (A24 is a new family). `frontend/tests/design-amendments.test.ts` reads `toHaveLength(entries + 15)`, and `CLAUDE.md` must contain exactly `<word(families + 1)> families, <entries + 15> entries` and `A1's 24 derived edits plus <literals + 15> literals` — **both strings appear twice in that file**. For orientation only, not to be asserted: on `main` at `ec79594` that is 195 literals / 219 entries / 196 rows / `Twenty-five families`; once `feat/card-geography` merges it is 210 / 234 / 211 / `Twenty-seven families`.

> **MEASURED IN TASK 4, 2026-09-11: the delta is +15, not +14.** D-C46 (John, 2026-09-11) was moved into this task deliberately — it moves the same Browse captures — and is one more literal, `A24.13`. On `main` at `ec79594` plus this branch that reads **196 literals / 220 entries / 197 rows / `Twenty-five families`**. Derive it; do not copy it.

> **⚠ A-NS5 correction.** This paragraph used to say "`tests/test_docs.py`'s `number_words` already runs to `"Twenty-four"` — no edit needed there." **That is false.** The tuple stops at `"Twenty-four"` (indices 0..24) and `main` is at exactly twenty-four families, so A24 makes twenty-five and `test_claude_md_amendment_family_and_entry_counts_match_design_amendments` fails on `assert family_count in number_words` — on its own vocabulary, before it ever looks at CLAUDE.md. **Task 4 must extend the tuple**, unless `feat/card-geography` merged first: it hit the same wall at A27 and already extended it to thirty-three words. Check, do not assume — the Preconditions script prints this as a `[Task 4]` line.

**Files:**
- Modify: `frontend/tests/design-amendments.ts` (the fourteen A24 entries + the `amendments()` list tail at `:3529`)
- Modify: `frontend/tests/design-amendments.test.ts` (`AMENDMENT_IDS` + 14, `toHaveLength(N)` → `(N + 14)` where `N` is what the file reads today — A-NS5, was `(182)` → `(196)`, both now stale — one A24 case)
- Modify: `tests/test_docs.py` (`number_words` extended past `families + 1`, if `feat/card-geography` has not already done it — A-NS5)
- Modify: `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md` (14 rows, appended in apply order)
- **Regenerated:** `…/Practice Match V3.dc.html`, `…/MarketMapV3.jsx`, `frontend/src/logic.js`, `frontend/src/App.vue`, `frontend/src/generated/pseudo.css`
- Modify: `frontend/src/components/MarketMapView.vue:44` (the import), `:47-55` (props), `:87-114` (`drawOverlay`, `tipHtml`), `:136-171` (the watcher)
- Modify: `frontend/src/components/MarketMapView.test.ts:28`, `:58-83`, and every case keyed on a cell count
- **Delete:** `frontend/src/map/mosaic.js`, `frontend/src/map/mosaic.test.ts`
- Modify: `frontend/tests/visual.spec.ts:27`, `:40-79`, `:92`
- Modify: `frontend/tests/smoke.spec.ts:230-244`, `:396-408`
- Modify: `docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md:52`, `:4189-4194`
- Modify: `frontend/tests/cross-plan-deltas.test.ts:87`, `:96`
- Modify: `frontend/src/logic.test.ts` (a new `describe`)
- Modify: `CLAUDE.md`
- Test: `frontend/tests/design-amendments.test.ts`, `frontend/src/logic.test.ts`, `frontend/src/components/MarketMapView.test.ts`, `frontend/tests/cross-plan-deltas.test.ts`, then the full Playwright gate

**Interfaces:**
- Consumes: `AmendmentFile`, `Amendment.file`, `PRISTINE_JSX`, `AMENDED_JSX`, `amendmentsFor` (Task 1); `MapEngine.geoJson(fc, styleFor, group, tooltipFor?, onClick?)`, `AreaFeature`, `AreaFeatureCollection` (Task 2); `DESIGN_AREAS_LITERAL` (Task 3).
- Produces, inside the design's script (reachable from `frontend/src/logic.js`'s exported `Component`):
  - `AREA_LEVEL = { income: "860", growth: "160", econ: "050" }`, `AREA_LABEL = { income: "ZIP Code Tabulation Area", growth: "Place (city/town)", econ: "County" }`, `NO_DATA_FILL = "#e6e6e6"`, `NO_DATA_LABEL = "No data"` — module constants beside `FILL_KEYS`.
  - `state.areas` — the fixture, keyed by summary level.
  - `Component.prototype.areaSet(layer: string): AreaFeatureCollection` — the design's own fixture given the design's own figures; each feature's `properties` is `{ geo_id, name, value, moe, suppressed, suppress_reason, band_ambiguous }`. **Task 10's `frontend/tests/design-boundaries.mjs` calls exactly this** to derive the harness's answer.
  - `Component.prototype.areaVals(fc, layer): AreaFeatureCollection` — the ONE door: adds `color`, `label`, `tip`, `suppressReason`, `ambiguous` per feature, through `bucket()`/`fmtMetric()`. **Task 10's adapter path enters here too.**
  - `Component.prototype.areaTip(p, layer, shown): string` — the `rf-tip` HTML, built once.
  - `md.areas` — the drawable `AreaFeatureCollection` the two `<x-import>`s pass on as `areas`.
  - `md.active.hasGeo: boolean`, `md.active.geoLine: string` — the legend's geography line.
- Produces, in `frontend/src/components/MarketMapView.vue`: a new `areas: { type: Object, default: null }` prop. `communities` STAYS a prop and stays in the watcher's dep list — the fixture's values are derived from it, so it is not dead.

- [ ] **Step 1: Grep every `find` as a fixed string, with Python, before writing one entry**

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-neighbourhood-shading"
python3 - <<'PY'
import pathlib
B = "docs/design-reference/design_handoff_practice_match_v3/"
A = pathlib.Path(B + "Practice Match V3.dc.html").read_text(encoding="utf-8")
J = pathlib.Path(B + "MarketMapV3.jsx").read_text(encoding="utf-8")
dc = {
  "A24.1": '    adminTab: "users", sellerView: "dash",\n',
  "A24.2": 'const FILL_KEYS = ["income", "growth", "econ"];\n',
  "A24.3": '  communities() {\n',
  "A24.4": '      communities: comms.filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lng)).map((c) => {\n',
  # A24.5's real `find` is the seven-line block below; these two lines are its unique prefix, and
  # `applyAmendments` counts the whole thing at the point of application.
  "A24.5": '          hasRamp: !!valueLayer,\n          ramp: valueLayer\n',
  "A24.6a": ' practices="{{ md.practices }}" communities="{{ md.communities }}" active-layer="{{ md.activeLayer }}" basemap="{{ md.basemap }}" active-id="{{ md.activeId }}" on-select="{{ md.selectFromMap }}"',
  "A24.6b": ' practices="{{ md.practices }}" communities="{{ md.communities }}" active-layer="{{ md.activeLayer }}" basemap="{{ md.basemap }}" active-id="{{ md.activeId }}" on-select="{{ mob.selectMarker }}"',
  "A24.7": 'Community areas on the map are approximate — production draws Census ZCTA boundaries.',
  "A24.8a": '                    <div style="margin-top: 11px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.sourceLine }}</div>\n',
  "A24.8b": '                        <div style="margin-top: 10px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.sourceLine }}</div>\n',
}
jsx = {
  "A24.9":  '// GEOMETRY NOTE: the prototype has no ZCTA boundary file, so community areas are\n',
  "A24.10": '// ---- Fine-grained mosaic ---------------------------------------------------\n',
  "A24.11": '    communities = [],\n',
  "A24.12": '    if (!activeLayer || !communities.length) return;\n',
}
for k, v in dc.items():  print(f"{k:8s} dc  count={A.count(v)}")
for k, v in jsx.items(): print(f"{k:8s} jsx count={J.count(v)}")
PY
```

Expected: **every line reads `count=1`.** Anything else and `main` has moved: STOP. (`grep -c -F` is forbidden here for the reason Global Constraint (b) gives — a `find` with an embedded newline makes grep OR the lines and report the wrong number.)

- [ ] **Step 2: Print the two long jsx `find` strings, deterministically, rather than transcribing them**

A24.10 deletes 23 lines and A24.12 replaces 35. Transcribing either by hand is how a silent no-op gets written. Build both from the pristine file's own bytes and paste the printed TypeScript straight into `design-amendments.ts`:

```bash
python3 - <<'PY'
import json, pathlib
J = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/MarketMapV3.rev2.jsx").read_text(encoding="utf-8")

def block(start_marker, end_marker, include_end=True):
    i = J.index(start_marker)
    j = J.index(end_marker, i) + (len(end_marker) if include_end else 0)
    return J[i:j]

a24_10 = block('// ---- Fine-grained mosaic ---', '  return out;\n}\n\n')
a24_12 = block('    if (!activeLayer || !communities.length) return;\n',
               '  }, [communities, activeLayer, showDrive, driveCenter && driveCenter[0], status]);\n')
for name, text in (("A24_10", a24_10), ("A24_12", a24_12)):
    print(f"// {name}: {text.count(chr(10))} lines, {len(text)} chars, count in pristine = {J.count(text)}")
    print(f"  find: {json.dumps(text)},")
    print()
PY
```

Expected: `A24_10: 23 lines`, `A24_12: 35 lines`, and `count in pristine = 1` for both. A24.10's block starts `// ---- Fine-grained mosaic ---…` and ends `  return out;\n}\n\n`; A24.12's starts `    if (!activeLayer || !communities.length) return;` and ends with the dep array line. Paste each printed `find:` line verbatim into the entry below. **If either count is not 1, STOP.**

- [ ] **Step 3: Write the failing test**

In `frontend/tests/design-amendments.test.ts`, append the fourteen ids to `AMENDMENT_IDS` (after the last A-family block — A-NS5: the plan said "line 242" and `main` has moved; find it, do not seek to a line number), change `toHaveLength(N)` to `toHaveLength(N + 14)` for the `N` the file actually reads, and add one A24 case:

```ts
    // A24 — real Census boundary polygons replace the grid mosaic (2026-09-10; John's rulings
    // D-C34–D-C37, spec 2026-09-10-neighbourhood-shading-design.md). The four `.jsx` entries are
    // the first amendments in the programme's history to reach a bundle file other than the
    // `.dc.html`; `amendmentsFor` partitions them and each file is proved on its own.
    'A24.1', 'A24.2', 'A24.3', 'A24.4', 'A24.5', 'A24.6a', 'A24.6b', 'A24.7', 'A24.8a', 'A24.8b',
    'A24.9', 'A24.10', 'A24.11', 'A24.12',
```

```ts
  it('A24 draws real boundary polygons, at the three ruled geographies, through the design\'s own bucket()', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    const jsx = readFileSync(AMENDED_JSX, 'utf8');

    // D-C35's three geographies and their legend labels, and nothing wider: the three symbol
    // layers are not in either map.
    expect(amended).toContain('const AREA_LEVEL = { income: "860", growth: "160", econ: "050" };');
    expect(amended).toContain('const AREA_LABEL = { income: "ZIP Code Tabulation Area", growth: "Place (city/town)", econ: "County" };');
    for (const k of ['pets', 'households', 'competition']) {
      expect(amended, `${k} must not gain a geography — D-C35 keeps it a graduated symbol`).not.toContain(`AREA_LEVEL = { ${k}`);
    }

    // D-NS16 (John, 2026-09-10): the no-data class is the design's own --border-subtle value and
    // the legend gains one row reading exactly "No data".
    expect(amended).toContain('const NO_DATA_FILL = "#e6e6e6";');
    expect(amended).toContain('const NO_DATA_LABEL = "No data";');

    // The one door (spec §2.2): every polygon's colour comes from the design's own bucket() and
    // its label from the design's own fmtMetric(), so the fill and the legend cannot disagree.
    expect(amended).toContain('const b = shown ? this.bucket(layer, p.value) : null;');
    expect(amended).toContain('label: shown ? this.fmtMetric(layer, p.value) : NO_DATA_LABEL,');

    // The tip is built ONCE, in the script, and both renderers bind it — the design and the port
    // used to build it twice and keep the two in step by hand.
    expect(amended.split('Estimate too imprecise to show at this geography')).toHaveLength(2);
    expect(jsx).not.toContain('Estimate too imprecise');
    expect(jsx).toContain('l.bindTooltip(f.properties.tip, { sticky: true, className: "rf-tip" });');

    // The grid is gone from the reference, name and all.
    expect(jsx).not.toContain('mosaicCells');
    expect(jsx).not.toContain('0.0055');
    expect(jsx).not.toContain('GEOMETRY NOTE');
    expect(jsx).toContain('// GEOMETRY: real Census boundary polygons, handed in as `areas`');
    // `voronoiCells`/`clipPolygon` were dead before this change and are left alone: the bundle's
    // dead-code rule applies to orphans a change CREATES (A2.3, A13.6), not to pre-existing ones.
    expect(jsx).toContain('function voronoiCells(sites, bbox) {');

    // Both maps are handed the polygons, and `communities` stays passed — the fixture's figures
    // are derived from it, so it is not dead.
    expect(amended.split('areas="{{ md.areas }}"')).toHaveLength(3);
    expect(amended.split('communities="{{ md.communities }}"')).toHaveLength(3);

    // The footnote John ruled on, byte for byte (§14 Q2), and the sentence it replaced is gone.
    expect(amended).toContain('Community areas are Census ZIP Code Tabulation Areas (2023 boundaries); figures describe the area, not the practice.');
    expect(amended).not.toContain('production draws Census ZCTA boundaries');

    // The legend names the geography, on the desktop panel and in the phone sheet, and nowhere
    // introduces a style the design does not already carry.
    expect(amended.split('{{ md.active.geoLine }}')).toHaveLength(3);
    expect(amended.split('value="{{ md.active.hasGeo }}"')).toHaveLength(3);
  });
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
cd frontend && npx vitest run tests/design-amendments.test.ts
```

Expected: `amendments() is exactly the pinned id list` FAILS (182 received, 196 expected; the fourteen ids are in `AMENDMENT_IDS` and in no list), and the new A24 case FAILS on its first assertion (`AREA_LEVEL` is nowhere in the design). `LOCAL_AMENDMENTS.md carries exactly one table row per amendment id` still passes, because no entry exists yet.

- [ ] **Step 5: Write the fourteen amendments**

In `frontend/tests/design-amendments.ts`, immediately after the `A25_6` definition, add the shared metadata and the entries. `DESIGN_AREAS_LITERAL` is imported at the top of the file: add `import { DESIGN_AREAS_LITERAL } from './design-boundary-fixture';` beside the two existing imports.

```ts
// A24 — real Census boundary polygons (John, 2026-09-10; rulings D-C34–D-C37; spec
// docs/superpowers/specs/2026-09-10-neighbourhood-shading-design.md). Nine `.dc.html` entries and
// four in `MarketMapV3.jsx`, the first family to reach a second bundle file (controller ruling,
// §14 Q3). A24.1's payload is GENERATED — scripts/export_design_boundaries.py — so the design
// carries real geometry and no hand-typed coordinate.
const NS = {
  date: '2026-09-10',
  ruling: 'the data is not to the granular level required at neighborhood level — right now it’s just a blob over the whole city and misses the entire point of what is required and the required level of detail and data per neighborhood required to make a decision to buy a practice'
};

const A24_1: Amendment = {
  id: 'A24.1', ...NS,
  find: '    adminTab: "users", sellerView: "dash",\n',
  replace: '    areas: ' + DESIGN_AREAS_LITERAL + ',\n'
    + '    adminTab: "users", sellerView: "dash",\n',
  count: 1
};

const A24_2: Amendment = {
  id: 'A24.2', ...NS,
  find: 'const FILL_KEYS = ["income", "growth", "econ"];\n',
  replace: 'const FILL_KEYS = ["income", "growth", "econ"];\n'
    + '// A24 (D-C35): each fill layer draws at the geography its figure is honest at, and the\n'
    + '// legend names it. `pets`, `households` and `competition` stay graduated symbols at the\n'
    + '// listing point — city-scale class breaks on small areas produce a picture with no\n'
    + '// information, and `households`’ first `< 10K` bucket would swallow essentially every one.\n'
    + 'const AREA_LEVEL = { income: "860", growth: "160", econ: "050" };\n'
    + 'const AREA_LABEL = { income: "ZIP Code Tabulation Area", growth: "Place (city/town)", econ: "County" };\n'
    + '// D-NS16 (John, 2026-09-10): a polygon with no usable figure is drawn in a neutral class\n'
    + '// and never omitted — a hole in a choropleth reads as a boundary, not as an absence. The\n'
    + '// colour is the design’s own --border-subtle value at the same fillOpacity every other\n'
    + '// class uses, so this adds no style vocabulary. Grey means UNMEASURED and only that: a\n'
    + '// figure that WAS measured but whose margin spans a band is shown with its value (D-C36).\n'
    + 'const NO_DATA_FILL = "#e6e6e6";\n'
    + 'const NO_DATA_LABEL = "No data";\n',
  count: 1
};

const A24_3: Amendment = {
  id: 'A24.3', ...NS,
  find: '  communities() {\n',
  replace: '  // A24 (spec §9.4): the design’s own boundary fixture, given the design’s own figures.\n'
    + '  // Each polygon takes the value of the NEAREST community centroid — the one line of\n'
    + '  // `mosaicCells` that survives ("spatial ASSIGNMENT of existing community data, not\n'
    + '  // interpolation, and not new data"), applied to real Census boundaries instead of grid\n'
    + '  // cells, with longitude scaled by cos(lat) exactly as the mosaic scaled it.\n'
    + '  areaSet(layer) {\n'
    + '    const src = (this.state.areas || {})[AREA_LEVEL[layer]];\n'
    + '    if (!src) return { type: "FeatureCollection", features: [] };\n'
    + '    const comms = this.communities().filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lng));\n'
    + '    return {\n'
    + '      type: "FeatureCollection",\n'
    + '      features: src.features.map((f) => {\n'
    + '        const p = f.properties;\n'
    + '        let best = null, bestD = Infinity;\n'
    + '        for (let i = 0; i < comms.length; i++) {\n'
    + '          const s = comms[i];\n'
    + '          const dLat = s.lat - p.c[0];\n'
    + '          const dLng = (s.lng - p.c[1]) * Math.cos((p.c[0] * Math.PI) / 180);\n'
    + '          const d = dLat * dLat + dLng * dLng;\n'
    + '          if (d < bestD) { bestD = d; best = s; }\n'
    + '        }\n'
    + '        const raw = best ? best[layer] : undefined;\n'
    + '        return {\n'
    + '          type: "Feature", id: p.geo_id, geometry: f.geometry,\n'
    + '          properties: {\n'
    + '            geo_id: p.geo_id, name: p.name,\n'
    + '            value: (raw === undefined || raw === null) ? null : num(raw),\n'
    + '            moe: null, suppressed: false, suppress_reason: null, band_ambiguous: false\n'
    + '          }\n'
    + '        };\n'
    + '      })\n'
    + '    };\n'
    + '  }\n'
    + '\n'
    + '  // The ONE door every polygon enters by, whichever side produced it (spec §2.2): the\n'
    + '  // colour is `bucket()`’s and the label is `fmtMetric()`’s, so the fill and the legend\n'
    + '  // cannot disagree. A value that is absent OR suppressed takes the no-data class; a value\n'
    + '  // that is present takes its band even when its margin spans one (D-C36).\n'
    + '  areaVals(fc, layer) {\n'
    + '    const feats = (fc && fc.features) || [];\n'
    + '    return {\n'
    + '      type: "FeatureCollection",\n'
    + '      features: feats.map((f) => {\n'
    + '        const p = f.properties;\n'
    + '        const shown = p.value !== null && p.value !== undefined && !p.suppressed;\n'
    + '        const b = shown ? this.bucket(layer, p.value) : null;\n'
    + '        return {\n'
    + '          type: "Feature", id: p.geo_id, geometry: f.geometry,\n'
    + '          properties: {\n'
    + '            geo_id: p.geo_id, name: p.name, value: p.value, moe: p.moe,\n'
    + '            suppressed: !!p.suppressed, suppressReason: p.suppress_reason || null,\n'
    + '            ambiguous: !!p.band_ambiguous,\n'
    + '            color: shown ? b.color : NO_DATA_FILL,\n'
    + '            label: shown ? this.fmtMetric(layer, p.value) : NO_DATA_LABEL,\n'
    + '            tip: this.areaTip(p, layer, shown)\n'
    + '          }\n'
    + '        };\n'
    + '      })\n'
    + '    };\n'
    + '  }\n'
    + '\n'
    + '  // The hover tip, built ONCE. Every honesty line is the wording the market-data contract’s\n'
    + '  // copy rules already mandate, so the map says what the docked panel says. `growth` and\n'
    + '  // `econ` carry no published margin (D-NS17) and say why rather than being greyed.\n'
    + '  areaTip(p, layer, shown) {\n'
    + '    const meta = LAYER_META[layer] || {};\n'
    + '    const absent = p.suppressed\n'
    + '      ? (p.suppress_reason === "source_flag" ? "Not published for this county" : "Estimate too imprecise to show at this geography")\n'
    + '      : "No data for this area";\n'
    + '    const margin = (p.moe !== null && p.moe !== undefined)\n'
    + '      ? "± " + this.fmtMetric(layer, p.moe) + (p.band_ambiguous ? " — this margin spans two legend bands." : "")\n'
    + '      : (layer === "growth"\n'
    + '          ? "Derived from two ACS 5-year periods. No combined margin of error is published."\n'
    + '          : layer === "econ"\n'
    + '            ? "Payroll per establishment (NAICS 541940), county level. County Business Patterns is a census of establishments, not a sample; no margin of error applies."\n'
    + '            : "");\n'
    + '    return \'<div style="font-family:ProximaNova,Arial,Helvetica,sans-serif;min-width:150px">\' +\n'
    + '      \'<div style="font-size:12.5px;font-weight:800;color:#003a70">\' + p.name + "</div>" +\n'
    + '      \'<div style="font-size:11px;color:#494949;margin-top:3px">\' + (meta.title || "") + "</div>" +\n'
    + '      \'<div style="font-size:15px;font-weight:800;color:#003a70;margin-top:1px">\' + (shown ? this.fmtMetric(layer, p.value) : NO_DATA_LABEL) + "</div>" +\n'
    + '      \'<div style="font-size:10.5px;color:#494949;margin-top:4px">\' + (shown ? margin : absent) + "</div>" +\n'
    + '      \'<div style="font-size:10px;color:#767676;margin-top:5px">\' + (meta.source || "") + "</div>" +\n'
    + '    "</div>";\n'
    + '  }\n'
    + '\n'
    + '  communities() {\n',
  count: 1
};

const A24_4: Amendment = {
  id: 'A24.4', ...NS,
  find: '      communities: comms.filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lng)).map((c) => {\n',
  replace: '      areas: this.areaVals(this.areaSet(valueLayer), valueLayer),\n'
    + '      communities: comms.filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lng)).map((c) => {\n',
  count: 1
};

const A24_5: Amendment = {
  id: 'A24.5', ...NS,
  find: '          hasRamp: !!valueLayer,\n'
    + '          ramp: valueLayer\n'
    + '            ? ramp(valueLayer).map((c, i) => ({\n'
    + '                style: "flex: 1; height: 9px; background: " + c + ";",\n'
    + '                label: cfg.buckets[i]\n'
    + '              }))\n'
    + '            : []\n',
  replace: '          hasRamp: !!valueLayer,\n'
    + '          hasGeo: FILL_KEYS.indexOf(valueLayer) > -1,\n'
    + '          geoLine: AREA_LABEL[valueLayer] || "",\n'
    + '          ramp: valueLayer\n'
    + '            ? ramp(valueLayer).map((c, i) => ({\n'
    + '                style: "flex: 1; height: 9px; background: " + c + ";",\n'
    + '                label: cfg.buckets[i]\n'
    + '              })).concat(FILL_KEYS.indexOf(valueLayer) > -1\n'
    + '                ? [{ style: "flex: 1; height: 9px; background: " + NO_DATA_FILL + ";", label: NO_DATA_LABEL }]\n'
    + '                : [])\n'
    + '            : []\n',
  count: 1
};

const A24_6a: Amendment = {
  id: 'A24.6a', ...NS,
  find: ' practices="{{ md.practices }}" communities="{{ md.communities }}" active-layer="{{ md.activeLayer }}" basemap="{{ md.basemap }}" active-id="{{ md.activeId }}" on-select="{{ md.selectFromMap }}"',
  replace: ' practices="{{ md.practices }}" communities="{{ md.communities }}" areas="{{ md.areas }}" active-layer="{{ md.activeLayer }}" basemap="{{ md.basemap }}" active-id="{{ md.activeId }}" on-select="{{ md.selectFromMap }}"',
  count: 1
};

const A24_6b: Amendment = {
  id: 'A24.6b', ...NS,
  find: ' practices="{{ md.practices }}" communities="{{ md.communities }}" active-layer="{{ md.activeLayer }}" basemap="{{ md.basemap }}" active-id="{{ md.activeId }}" on-select="{{ mob.selectMarker }}"',
  replace: ' practices="{{ md.practices }}" communities="{{ md.communities }}" areas="{{ md.areas }}" active-layer="{{ md.activeLayer }}" basemap="{{ md.basemap }}" active-id="{{ md.activeId }}" on-select="{{ mob.selectMarker }}"',
  count: 1
};

const A24_7: Amendment = {
  id: 'A24.7', ...NS,
  find: 'Community areas on the map are approximate — production draws Census ZCTA boundaries.',
  replace: 'Community areas are Census ZIP Code Tabulation Areas (2023 boundaries); figures describe the area, not the practice.',
  count: 1
};

const A24_8a: Amendment = {
  id: 'A24.8a', ...NS,
  find: '                    <div style="margin-top: 11px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.sourceLine }}</div>\n',
  replace: '                    <sc-if value="{{ md.active.hasGeo }}" hint-placeholder-val="{{ true }}">\n'
    + '                      <div style="margin-top: 11px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.geoLine }}</div>\n'
    + '                    </sc-if>\n'
    + '                    <div style="margin-top: 11px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.sourceLine }}</div>\n',
  count: 1
};

const A24_8b: Amendment = {
  id: 'A24.8b', ...NS,
  find: '                        <div style="margin-top: 10px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.sourceLine }}</div>\n',
  replace: '                        <sc-if value="{{ md.active.hasGeo }}" hint-placeholder-val="{{ true }}">\n'
    + '                          <div style="margin-top: 10px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.geoLine }}</div>\n'
    + '                        </sc-if>\n'
    + '                        <div style="margin-top: 10px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.sourceLine }}</div>\n',
  count: 1
};

const A24_9: Amendment = {
  id: 'A24.9', ...NS, file: 'jsx',
  find: '// GEOMETRY NOTE: the prototype has no ZCTA boundary file, so community areas are\n'
    + '// approximated as Voronoi cells around each community’s centroid, clipped to the metro\n'
    + '// bounding box. Cells are contiguous and non-overlapping, which is what a choropleth\n'
    + '// requires, but they are NOT real Census boundaries — the UI labels them "approximate\n'
    + '// community areas". Production must load tiger_cb ZCTA polygons per the Census Data\n'
    + '// Source Specification and drop this approximation.\n',
  replace: '// GEOMETRY: real Census boundary polygons, handed in as `areas` — one GeoJSON\n'
    + '// FeatureCollection for the active fill layer, each feature already carrying the colour\n'
    + '// `bucket()` chose and the tooltip `areaVals()` built, so this component classes nothing\n'
    + '// and formats nothing. The approximation this file used to draw (grid cells nearest each\n'
    + '// community’s centroid, clipped to the metro bounding box) is gone: amendment A24, spec\n'
    + '// 2026-09-10, John’s rulings D-C34–D-C37 of 2026-09-10.\n',
  count: 1
};

const A24_10: Amendment = {
  id: 'A24.10', ...NS, file: 'jsx',
  // Paste the `find:` line Step 2's snippet printed for A24_10 here — 23 lines, ending
  // `  return out;\n}\n\n`. Deleted outright under the bundle's own dead-code rule (spec D8/D12,
  // as A2.3–A2.5 and A13.6–A13.7 applied it): A24.12 removes its only caller.
  find: '<<< paste the printed A24_10 find here >>>',
  replace: '',
  count: 1
};

const A24_11: Amendment = {
  id: 'A24.11', ...NS, file: 'jsx',
  find: '    communities = [],\n',
  replace: '    communities = [],\n    areas = null,\n',
  count: 1
};

const A24_12: Amendment = {
  id: 'A24.12', ...NS, file: 'jsx',
  // Paste the `find:` line Step 2's snippet printed for A24_12 here — 35 lines, from
  // `    if (!activeLayer || !communities.length) return;` through the dep array.
  find: '<<< paste the printed A24_12 find here >>>',
  replace: '    if (!activeLayer || !areas || !areas.features.length) return;\n'
    + '\n'
    + '    const canvas = L.canvas({ padding: 0.3 });\n'
    + '    L.geoJSON(areas, {\n'
    + '      renderer: canvas,\n'
    + '      style: (f) => ({ renderer: canvas, stroke: false, fillColor: f.properties.color, fillOpacity: 0.5, interactive: true }),\n'
    + '      onEachFeature: (f, l) => {\n'
    + '        l.bindTooltip(f.properties.tip, { sticky: true, className: "rf-tip" });\n'
    + '        l.on("click", () => onArea && onArea(f.properties.name));\n'
    + '      }\n'
    + '    }).addTo(g);\n'
    + '  }, [areas, communities, activeLayer, showDrive, driveCenter && driveCenter[0], status]);\n',
  count: 1
};
```

and extend `amendments()`' returned array (line 3529) from `A25_1, A25_2, A25_3, A25_4, A25_5, A25_6];` to:

```ts
    A25_1, A25_2, A25_3, A25_4, A25_5, A25_6,
    // A24 — real Census boundary polygons (2026-09-10). Numerically before A25 and applied after
    // it: A25 was written and merged while A24 was reserved, and every A24 `find` is measured
    // against the file A25 leaves behind. Nine `.dc.html` entries, then the four `MarketMapV3.jsx`
    // ones — `amendmentsFor` partitions them, so the jsx entries' position in this list only
    // decides their order among themselves.
    A24_1, A24_2, A24_3, A24_4, A24_5, A24_6a, A24_6b, A24_7, A24_8a, A24_8b,
    A24_9, A24_10, A24_11, A24_12];
```

- [ ] **Step 6: Regenerate both design files and the app**

```bash
cd frontend && npm run gen:design
```

Expected: `172 amendments applied` for the `.dc.html`, `4 amendments applied` for `MarketMapV3.jsx`, `196 amendments in total`. Any `expected 1 match(es) … found 0` names the entry whose `find` is wrong: fix it, do not adjust `count`.

Then re-port `logic.js` and regenerate the Vue app (the design's script block is the source; `logic.js` is never hand-edited):

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-neighbourhood-shading"
python3 - <<'PY'
import pathlib, re
DC = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html").read_text(encoding="utf-8")
m = re.search(r'<script type="text/x-dc" data-dc-script[^>]*>', DC)
body = DC[m.end():DC.index("</script>", m.end())].replace('"assets/', '"/assets/')
body = re.sub(r"\n+$", "\n", body)
HEADER = ("// Ported verbatim from the approved prototype 'Practice Match V3.dc.html'.\n"
          "// Do not restyle or restructure: every value here is design-approved.\n"
          "import { DCLogic } from './dc-logic.js';\n")
FOOTER = "\nexport { Component, MARKETS, P, VETS, ECON_K };\n"
pathlib.Path("frontend/src/logic.js").write_text(HEADER + body + FOOTER, encoding="utf-8")
print("re-ported logic.js")
PY
cd frontend && npm run gen:app && npx vitest run tests/app-generated.test.ts
```

Expected: `app-generated.test.ts` green — `logic.js` byte-identical to the amended script block under the four documented normalisations, `App.vue`/`pseudo.css` byte-identical to what the converter produces, and every design prop still declared in `app.setup.js` (A24 adds no prototype prop).

- [ ] **Step 7: Run the amendment tests to verify they pass**

```bash
cd frontend && npx vitest run tests/design-amendments.test.ts
```

Expected: the A24 case PASSES; the `toHaveLength(N + 14)` count passes (A-NS5 — derived, was written `196`); `every find occurs exactly count times at the point it is applied, in list order` passes for BOTH files. `LOCAL_AMENDMENTS.md carries exactly one table row per amendment id` still FAILS — the rows come in Step 12.

- [ ] **Step 8: Swap the Vue port onto the same polygons**

`frontend/src/components/MarketMapView.vue` — delete line 44's mosaic import, add the `areas` prop, replace `drawOverlay`, delete `tipHtml`, and add `areas` to the two dep lists:

```js
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { practiceCallout, practicePin } from '../map/markers.js';
import { createEngine } from '../map/create';

const props = defineProps({
  practices: { type: Array, default: () => [] }, communities: { type: Array, default: () => [] },
  // A24: the drawable FeatureCollection `md.areas` produces — colour, label and tip per feature,
  // all decided in logic.js. `communities` stays: the design's own fixture path derives the
  // figures from it, so a change to it IS a change to the polygons.
  areas: { type: Object, default: null },
  activeLayer: { type: String, default: null }, basemap: { type: String, default: 'map' },
  onBasemap: { type: Function, default: null }, activeId: { type: String, default: null },
  onSelect: { type: Function, default: null }, onArea: { type: Function, default: null },
  center: { type: Array, default: () => [30.31, -97.75] }, zoom: { type: Number, default: 10 },
  driveCenter: { type: Array, default: null }, showDrive: { type: Boolean, default: false },
  resizeKey: { type: String, default: '' }, recenterKey: { type: Number, default: 0 }
});
```

```js
// C7 drive-time ring + A24 community boundary shading.
function drawOverlay() {
  if (!engine) return;
  engine.clear('overlay');
  if (props.showDrive && props.driveCenter) {
    engine.ring(props.driveCenter, 16000, { color: '#003a70', weight: 1.5, dashArray: '4 4', fill: false, interactive: false }, 'overlay');
  }
  if (!props.activeLayer || !props.areas || !props.areas.features.length) return;
  engine.geoJson(
    props.areas,
    (f) => ({ fillColor: f.properties.color, fillOpacity: 0.5, stroke: false, interactive: true }),
    'overlay',
    (f) => ({ html: f.properties.tip, sticky: true, className: 'rf-tip' }),
    (f) => props.onArea && props.onArea(f.properties.name)
  );
}
```

`tipHtml` is deleted outright: the string is `logic.js`'s `areaTip` now, on both targets, so the two copies that had to be kept in step by hand are one.

In `areaChanged()` and the watcher, add `areas` as the first dependency, mirroring A24.12's dep array exactly:

```js
let lastArea = null;
function areaChanged() {
  const next = [props.areas, props.communities, props.activeLayer, props.showDrive, props.driveCenter && props.driveCenter[0], status.value];
  const changed = lastArea === null || next.some((d, i) => !Object.is(d, lastArea[i]));
  lastArea = next;
  return changed;
}

watch(
  [() => props.areas, () => props.communities, () => props.activeLayer, () => props.showDrive, () => props.driveCenter && props.driveCenter[0],
    () => props.practices, () => props.activeId, status],
  () => { if (areaChanged()) drawOverlay(); drawPins(); },
  { deep: true }
);
```

Also correct the watcher's own comment block at `:151-157`: "A pin or card SELECTION still rebuilds the mosaic" becomes "still rebuilds the polygon layer", and the sentence naming "12,560 rectangles" becomes "What no longer rebuilds the polygon layer is a trigger that leaves all six untouched" — the number is gone with the grid, and per Global Constraint (i) it is not replaced with another hand-maintained one.

Then delete the grid:

```bash
git rm frontend/src/map/mosaic.js frontend/src/map/mosaic.test.ts
```

- [ ] **Step 9: Move `MarketMapView.test.ts` off cell counts and onto features**

Replace line 28's import (`import { MOSAIC_STEP, mosaicBbox, mosaicCells } from '../map/mosaic.js';`) with nothing, replace `cellCount` (`:58-62`) with a fixture builder, and re-express `drawOrder`/`roleOf` (`:64-83`) for a GeoJSON layer:

```ts
// A24: the overlay's cardinality is the FeatureCollection's, not a grid's. Fixtures are still
// BUILT rather than fixed, so every assertion holds for any cardinality.
const areas = (n: number) => ({
  type: 'FeatureCollection' as const,
  features: Array.from({ length: n }, (_, i) => ({
    type: 'Feature' as const,
    id: `z${i}`,
    properties: { geo_id: `z${i}`, name: `Community ${i}`, value: 90000 + i, moe: null, suppressed: false, suppressReason: null, ambiguous: false, color: '#4c9a6a', label: `$${90 + i}K`, tip: `<b>Community ${i}</b>` },
    geometry: { type: 'Polygon', coordinates: [[[-97.8 + i / 100, 30.2], [-97.7 + i / 100, 30.2], [-97.7 + i / 100, 30.3], [-97.8 + i / 100, 30.2]]] }
  }))
});

// V3 tells the two draws apart by the Leaflet factory each uses: the overlay is one geoJSON
// layer plus (when a listing is selected) the dashed drive-time circle; the pins are divIcon
// markers.
function drawOrder(stub: LeafletStub, from: number): string[] {
  return stub.calls
    .slice(from)
    .filter((c) => c.fn === 'geoJSON' || c.fn === 'circle' || c.fn === 'divIcon')
    .map((c) => (c.fn === 'divIcon' ? 'pins' : 'overlay'));
}

type StubLayer = { seq: number; data?: unknown; options?: { radius?: number; icon?: { icon?: { html?: string } } } };
type StubGroup = { clearLayers?: unknown; added: StubLayer[] };

const roleOf = (l: StubLayer): 'overlay' | 'pins' => {
  if (l.data !== undefined) return 'overlay';                   // the L.geoJSON boundary layer
  if (typeof l.options?.radius === 'number') return 'overlay';  // the dashed drive-time ring
  return 'pins';
};
```

Every case that asserted a cell count now asserts a FEATURE count. The mechanical rule: `expect(rects).toHaveLength(cellCount(n))` becomes `expect(stub.calls.filter((c) => c.fn === 'geoJSON')).toHaveLength(1)` plus `expect((stub.calls.find((c) => c.fn === 'geoJSON')!.args[0] as { features: unknown[] }).features).toHaveLength(n)`. The three cases whose SUBJECT was the mosaic are rewritten rather than mechanically translated:

```ts
  it('shades one polygon per feature for the active layer, on the shared canvas renderer', async () => {
    const { stub } = await mounted({ communities: 2, practices: 1 }, { areas: areas(7) });
    const call = stub.calls.find((c) => c.fn === 'geoJSON')!;
    expect((call.args[0] as { features: unknown[] }).features).toHaveLength(7);
    expect((call.args[1] as { renderer: unknown }).renderer).toBe(stub.canvas);
  });

  it('draws nothing when no layer is active, and nothing when the collection is empty', async () => {
    const a = await mounted({ communities: 2, practices: 1 }, { areas: areas(7), activeLayer: null });
    expect(a.stub.calls.filter((c) => c.fn === 'geoJSON')).toHaveLength(0);
    const b = await mounted({ communities: 2, practices: 1 }, { areas: areas(0) });
    expect(b.stub.calls.filter((c) => c.fn === 'geoJSON')).toHaveLength(0);
    const c = await mounted({ communities: 2, practices: 1 }, { areas: null });
    expect(c.stub.calls.filter((c2) => c2.fn === 'geoJSON')).toHaveLength(0);
  });

  it('binds the sticky rf-tip logic.js built, and a click reports the polygon through onArea', async () => {
    const reported: string[] = [];
    const { stub } = await mounted({ communities: 2, practices: 1 }, { areas: areas(2), onArea: (n: string) => reported.push(n) });
    const layer = stub.calls.find((c) => c.fn === 'geoJSON')!;
    const children = (layer.args as unknown[]) && ((stub.map.added as StubGroup[]).flatMap((g) => g.added) as unknown as { features?: { tooltip?: { text: string; opts: unknown }; on_click?: () => void }[] }[]).find((l) => (l as { data?: unknown }).data !== undefined)!.features!;
    expect(children[0].tooltip!.text).toBe('<b>Community 0</b>');
    expect(children[0].tooltip!.opts).toEqual({ sticky: true, className: 'rf-tip' });
    children[1].on_click!();
    expect(reported).toEqual(['Community 1']);
  });
```

`mounted()` gains a second parameter that is merged into the props it mounts with (`{ areas: areas(2), activeLayer: 'income', ... }` by default), so every existing case keeps its call shape. The case `skips a community missing a value for the active layer, drawing nothing for it` becomes `draws a feature with no value in the no-data class` and asserts the fill is `#e6e6e6` — the class is chosen in `logic.js` now, so this case passes an `areas` fixture whose feature already carries `color: '#e6e6e6'` and asserts the style function forwards it.

- [ ] **Step 10: Rename the end-to-end shading guard and correct the two smoke tests**

`frontend/tests/visual.spec.ts`: rename `expectMosaicShading` → `expectBoundaryShading` at `:40` and `:92`, and replace the header comment at `:27`'s "community mosaic" with "community boundary shading". The METHOD is unchanged and so is its purpose, which is worth restating in the comment because it is the one guard the pixel gate cannot replace:

```ts
// It asserts against the design's own palette, not a remembered colour: `PALETTES.distinct`
// is the default and `browse` opens on "Median household income", so the map must contain at
// least one pixel of the `distinct.income` ramp as the map composites it — fillOpacity 0.5
// (A24.12) over Leaflet's #ddd ground, which is what shows through the transparent tile stub.
// ±1 per channel absorbs the compositor's rounding.
async function expectBoundaryShading(page: Page): Promise<void> {
```

`frontend/tests/smoke.spec.ts:230-244`:

```ts
  test('the Map tab shows community boundary shading', async ({ page }) => {
    await mobileMap(page);
    // The polygons are drawn on the engine's shared L.canvas renderer, so "shading is showing"
    // means that canvas has painted pixels. Nothing is drawn from a cross-origin image, so
    // the canvas is untainted and readable.
    const painted = await page.evaluate(() => {
      const c = document.querySelector('.leaflet-overlay-pane canvas') as HTMLCanvasElement | null;
      if (!c) return -1;
      const px = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 3; i < px.length; i += 4) if (px[i] > 0) n++;
      return n;
    });
    expect(painted, 'no canvas in the Leaflet overlay pane — the boundary layer never drew').toBeGreaterThan(0);
  });
```

and at `:396-408`, the repaint-budget test's rationale: `the community mosaic really is rebuilt on the second tap` becomes `the polygon layer really is rebuilt on the second tap`; the test body and its budget are unchanged.

- [ ] **Step 11: Move the census plan's rendering table off the mosaic, and pin it**

`docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md` says "community mosaic shading" in seven places and the mosaic no longer exists. Replace each:

- `:52` (D3) — `Browse V3 ships *community mosaic shading* — client-side `L.rectangle` cells over community areas from the market-data payload — which is community granularity, not tract.` becomes `Browse V3 shipped *community mosaic shading* — client-side `L.rectangle` cells over community areas — until A-C33 and John's rulings D-C34–D-C37 replaced it with real Census boundary polygons at ZCTA, place and county (spec 2026-09-10). Tract polygons remain deferred, now gated on the band-ambiguity measurement rather than on a date.`
- `:4189` (income), `:4191` (growth), `:4193` (econ) — `community mosaic shading` becomes `community boundary shading (real `geo_area` polygons through `L.geoJSON`, `fillOpacity: 0.5`)`, and each row's geography column takes D-C35's: **ZCTA (860)**, **place (160)**, **county (050)**.
- `:4190` (pets), `:4192` (households), `:4194` (competition) — `community mosaic shading` becomes `graduated symbols at the listing point (D-C35)`; these three were never fills (`SYMBOL_KEYS`, `logic.js:121`) and the table was already describing something else.

`frontend/tests/cross-plan-deltas.test.ts:87` and `:96`:

```ts
    expect(md).toContain('community boundary shading');
    expect(md, 'the grid is gone from the product and from this plan').not.toContain('community mosaic shading');
```
```ts
    expect(md).toContain('| Veterinary Competition (`competition`) | graduated symbols at the listing point (D-C35)');
```

- [ ] **Step 12: Write the fourteen ledger rows and the CLAUDE.md clause**

Append fourteen rows to `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md`, in apply order (A24.1 … A24.12), each quoting `NS.ruling` **byte for byte** in the third column — `every LOCAL_AMENDMENTS.md row quotes its amendment's ruling verbatim` compares that cell to `a.ruling` exactly. The fourth column is free prose; write what the entry changes and why. **Cite `V3:<line>` only for the nine `.dc.html` entries** and recompute every citation after `gen:design` (Step 14); the four jsx rows cite `MarketMapV3.jsx:<line>` instead, which the citation test's `/V3:(\d+)/` pattern deliberately cannot match — there is a `.` between `V3` and the colon.

In `CLAUDE.md`, add the A24 clause to the "Source of truth for the UI" paragraph (both copies of that paragraph carry the family list; A24's clause goes after A23's), and update the two derived sentences to `<word(families + 1)> families, <entries + 15> entries` and `A1's 24 derived edits plus <literals + 15> literals` — **in both places each**. (A-NS5: the plan named the old and new strings literally — `Twenty-three families, 182 entries` → `Twenty-four families, 196 entries` — and all four are stale. Read the current sentence out of CLAUDE.md and add the delta; `tests/test_docs.py` is what proves it.)

- [ ] **Step 13: Characterise the new script branches in vitest**

Append to `frontend/src/logic.test.ts`:

```ts
describe('A24 — real boundary polygons', () => {
  const fc = (features: unknown[]) => ({ type: 'FeatureCollection', features });

  it('areaSet gives every polygon the value of the NEAREST community, and null where there is none', () => {
    const c: any = new Component({});
    const set = c.areaSet('income');
    expect(set.features.length, 'the design fixture has no ZCTA features').toBeGreaterThan(0);
    for (const f of set.features) {
      expect(f.properties.geo_id).toBe(f.id);
      expect(f.properties.moe).toBeNull();
      expect(f.properties.suppressed).toBe(false);
      expect(f.properties.band_ambiguous).toBe(false);
    }
    // Every design community carries an income, so no ZCTA comes out null on this layer.
    expect(set.features.every((f: any) => typeof f.properties.value === 'number')).toBe(true);
  });

  it('areaSet returns an empty collection for a layer with no geography — the three symbol layers', () => {
    const c: any = new Component({});
    for (const k of ['pets', 'households', 'competition']) expect(c.areaSet(k).features).toEqual([]);
    expect(c.areaSet(null).features).toEqual([]);
  });

  it('areaVals colours a measured value through bucket() and labels it through fmtMetric()', () => {
    const c: any = new Component({});
    const out = c.areaVals(fc([{ type: 'Feature', geometry: null, properties: { geo_id: '78704', name: 'ZCTA5 78704', value: 92150, moe: 6420, suppressed: false, suppress_reason: null, band_ambiguous: false } }]), 'income');
    expect(out.features[0].properties.color).toBe(c.bucket('income', 92150).color);
    expect(out.features[0].properties.label).toBe(c.fmtMetric('income', 92150));
    expect(out.features[0].properties.tip).toContain('ZCTA5 78704');
  });

  // Global Constraint (c): the producer's sentinel, measured rather than assumed. A MISSING value
  // is `value: null` with `suppressed: false` (that is what `_suppression(None, None)` returns and
  // what the endpoint serialises), so a guard on `suppressed` alone would paint a null as measured.
  it('a null value takes the no-data class even though it is not suppressed', () => {
    const c: any = new Component({});
    const out = c.areaVals(fc([{ type: 'Feature', geometry: null, properties: { geo_id: '78745', name: 'ZCTA5 78745', value: null, moe: null, suppressed: false, suppress_reason: null, band_ambiguous: false } }]), 'income');
    expect(out.features[0].properties.color).toBe('#e6e6e6');
    expect(out.features[0].properties.label).toBe('No data');
    expect(out.features[0].properties.tip).toContain('No data for this area');
  });

  it('the four honesty lines are the contract\'s own wording, one per case', () => {
    const c: any = new Component({});
    const tip = (props: Record<string, unknown>, layer = 'income') =>
      c.areaVals(fc([{ type: 'Feature', geometry: null, properties: { geo_id: 'g', name: 'g', moe: null, suppressed: false, suppress_reason: null, band_ambiguous: false, ...props } }]), layer).features[0].properties.tip;
    expect(tip({ value: 1, suppressed: true, suppress_reason: 'no_moe' })).toContain('Estimate too imprecise to show at this geography');
    expect(tip({ value: 1, suppressed: true, suppress_reason: 'high_moe' })).toContain('Estimate too imprecise to show at this geography');
    expect(tip({ value: 1, suppressed: true, suppress_reason: 'source_flag' })).toContain('Not published for this county');
    expect(tip({ value: null })).toContain('No data for this area');
    expect(tip({ value: 92150, moe: 6420, band_ambiguous: true })).toContain('this margin spans two legend bands.');
    expect(tip({ value: 92150, moe: 6420, band_ambiguous: false })).not.toContain('spans two legend bands');
    expect(tip({ value: 12.4 }, 'growth')).toContain('No combined margin of error is published.');
    expect(tip({ value: 640000 }, 'econ')).toContain('a census of establishments, not a sample');
  });

  it('the legend names the geography and gains a No data row, for the three fill layers only', () => {
    const c: any = new Component({});
    for (const [layer, label] of [['income', 'ZIP Code Tabulation Area'], ['growth', 'Place (city/town)'], ['econ', 'County']] as const) {
      c.state.mdValue = layer;
      const active = c.marketVals(P).active;
      expect(active.hasGeo).toBe(true);
      expect(active.geoLine).toBe(label);
      expect(active.ramp[active.ramp.length - 1]).toEqual({ style: 'flex: 1; height: 9px; background: #e6e6e6;', label: 'No data' });
    }
    c.state.mdValue = 'households';
    const symbols = c.marketVals(P).active;
    expect(symbols.hasGeo).toBe(false);
    expect(symbols.geoLine).toBe('');
    expect(symbols.ramp.some((r: { label: string }) => r.label === 'No data')).toBe(false);
  });
});
```

- [ ] **Step 14: Run every frontend gate, then re-base and read the manifest**

```bash
cd frontend && npm run typecheck && npx vitest run --coverage && npm run build
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-neighbourhood-shading"
export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_shading
export REDIS_URL=redis://localhost:6380/10 ENVIRONMENT=test API_SECRET_KEY=local_only_secret_change_me
export PW_APP_PORT=5583 PW_REF_PORT=5584 PW_CS_PORT=5585 PW_API_PORT=8157
lsof -nP -iTCP:5583,5584,5585,8157 -sTCP:LISTEN || true
cd frontend && npm run test:visual:baselines && npm run test:e2e
npx vitest run tests/baseline-manifest.test.ts
```

Expected: **`SCREENS.length` passed** from the reference project (A-NS5 — derive it, never type it), the `app` project green, and — the acceptance criterion — **`baseline-manifest.test.ts` GREEN with zero hashes moved.** The thirteen baselines that DID move are all Browse or phone-frame map states and none of them is in the manifest. If `mobile-detail` or `detail` has moved, the change reached the detail screen and something is wrong with the port, not with the manifest: **STOP with NEEDS_CONTEXT.**

`design-amendments.test.ts`'s citation case will now name any stale `V3:<line>` row in `LOCAL_AMENDMENTS.md` — A24 inserts well over a hundred lines into the script, so every citation below the insertion points goes stale. Recompute each one it names; the test prints the id and the line.

- [ ] **Step 15: Run the backend gate**

```bash
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e --cov-fail-under=100
```

Expected: PASS. `tests/test_docs.py`'s two count pins now compare against the new `design-amendments.ts` and the new `CLAUDE.md`; `test_relative_markdown_links_resolve` covers this plan's own links.

- [ ] **Step 16: Commit**

```bash
git add frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts \
  "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
  "docs/design-reference/design_handoff_practice_match_v3/MarketMapV3.jsx" \
  "docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md" \
  frontend/src/logic.js frontend/src/App.vue frontend/src/generated/pseudo.css frontend/src/logic.test.ts \
  frontend/src/components/MarketMapView.vue frontend/src/components/MarketMapView.test.ts \
  frontend/tests/visual.spec.ts frontend/tests/smoke.spec.ts frontend/tests/cross-plan-deltas.test.ts \
  docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md CLAUDE.md
git rm frontend/src/map/mosaic.js frontend/src/map/mosaic.test.ts
git commit -m "feat(design): A24 — real Census boundary polygons replace the grid mosaic

The Browse map draws geo_area polygons at the three geographies D-C35 ruled — ZCTA for
income, place for growth, county for econ — coloured through the design's own bucket()
and labelled through its own fmtMetric(), with a no-data class at #e6e6e6 that is always
drawn and never omitted (D-NS16) and a legend row and geography line to name both. The
hover tip is built once, in the script, instead of twice by hand. mosaic.js and its nine
cases are deleted; MarketMapV3.jsx draws props.areas through L.geoJSON on the same shared
canvas renderer, and its GEOMETRY NOTE now says what the file does.

Thirteen approved states re-base, all of them map states; baseline-manifest.json's
thirteen frozen hashes did not move, which is the proof the change stayed inside Browse.

John, 2026-09-10 (rulings D-C34-D-C37); spec 2026-09-10-neighbourhood-shading-design.md.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```


---

## Task 5: `migrations/064_geo_metric.sql` — the table and its licence gate

`market_metric` is per (listing, band, metric, vintage) and answers "what is the market around this practice". A polygon has no listing, and shading a metro's ZCTAs off `market_metric` would mean one row per listing per polygon, recomputed whenever a listing moved. `geo_metric` is its sibling: same column vocabulary, same licence trigger, a different subject (D-NS1).

**`064`, not `091`** (D-NS2): D14 of the Census plan assigns SP3-B the `060`+ range and `060`–`063` are taken; `090` belongs to main's platform range. The ledger runner applies each file exactly once and refuses only files whose bytes no longer match a recorded checksum (`scripts/migrate.py::refuse_changed_files`), so a file that sorts before an already-applied `090` is applied on the next run without incident.

**Re-basing states: NONE. The thirteen frozen hashes must not move.**

**Files:**
- Create: `migrations/064_geo_metric.sql`
- Create: `tests/census/test_migration_064.py`
- Test: `tests/census/test_migration_064.py`

**Interfaces:**
- Consumes: `dataset_registry` (`migrations/017`), which `064` references and nothing later.
- Produces, for Tasks 8 and 9: the table `geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, is_derived, formula_version, moe, suppressed, suppress_reason, inputs, source_dataset, computed_at)`, primary key `(geo_id, summary_level, vintage, metric_key)`, index `geo_metric_layer_idx (summary_level, metric_key, vintage)`, and the `BEFORE INSERT OR UPDATE … FOR EACH ROW` trigger `geo_metric_license_gate`.

- [ ] **Step 1: Write the failing test**

Create `tests/census/test_migration_064.py`:

```python
"""migrations/064_geo_metric.sql — `market_metric`'s sibling, per geography (D-NS1, D-NS3).

Modelled on tests/census/test_migration_062.py, which proves the twin trigger on `market_metric`.
The trigger's UPDATE arm is asserted as well as its INSERT arm: `061`'s equivalent fired
`BEFORE INSERT OR UPDATE` for months and was only ever exercised by INSERTs (finding 1, A-C16)."""
import psycopg2
import pytest


def _row(conn: psycopg2.extensions.connection, dataset: str = "acs5", geo_id: str = "78704") -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, source_dataset, computed_at) "
            "VALUES (%s, '860', '2019–2023', 'median_hh_income', 92150, 'usd', %s, now())",
            (geo_id, dataset),
        )


def test_the_table_carries_market_metrics_own_column_vocabulary(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'geo_metric' ORDER BY column_name")
        cols = {name: (dtype, nullable) for name, dtype, nullable in cur.fetchall()}
    assert sorted(cols) == [
        "computed_at", "formula_version", "geo_id", "inputs", "is_derived", "metric_key",
        "moe", "source_dataset", "summary_level", "suppress_reason", "suppressed", "unit",
        "value_num", "vintage",
    ]
    assert cols["summary_level"][0] == "character"
    assert cols["value_num"] == ("numeric", "YES"), "a geography with no figure must be storable"
    assert cols["moe"] == ("numeric", "YES")
    assert cols["inputs"][0] == "jsonb"
    for required in ("geo_id", "summary_level", "vintage", "metric_key", "unit", "is_derived", "suppressed", "source_dataset", "computed_at"):
        assert cols[required][1] == "NO", required


def test_the_primary_key_is_geography_metric_vintage_and_the_read_paths_index_exists(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'geo_metric' ORDER BY indexname"
        )
        idx = dict(cur.fetchall())
    assert "geo_metric_pkey" in idx
    for column in ("geo_id", "summary_level", "vintage", "metric_key"):
        assert column in idx["geo_metric_pkey"], column
    # The read path's ONLY access pattern: one layer, one geography level, one vintage.
    assert "geo_metric_layer_idx" in idx
    assert "summary_level" in idx["geo_metric_layer_idx"] and "metric_key" in idx["geo_metric_layer_idx"] and "vintage" in idx["geo_metric_layer_idx"]


def test_a_second_row_for_the_same_geography_metric_and_vintage_conflicts(conn: psycopg2.extensions.connection) -> None:
    _row(conn)
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _row(conn)


def test_the_licence_gate_admits_a_cleared_dataset(conn: psycopg2.extensions.connection) -> None:
    _row(conn, "acs5")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM geo_metric")
        assert cur.fetchone()[0] == 1


@pytest.mark.parametrize("status", ["unresolved", "blocked"])
def test_the_licence_gate_refuses_a_dataset_that_is_not_cleared(conn: psycopg2.extensions.connection, status: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = %s WHERE dataset_key = 'acs5'", (status,))
    with pytest.raises(psycopg2.errors.RaiseException) as exc:
        _row(conn, "acs5")
    assert "geo_metric write refused" in str(exc.value)
    # `062`'s own correction: the message names the dataset KEY, which cannot go stale, and never
    # the status it happened to read a second time.
    assert status not in str(exc.value)
    assert "acs5" in str(exc.value)


def test_the_licence_gate_refuses_a_dataset_with_no_registry_row_at_all(conn: psycopg2.extensions.connection) -> None:
    """`IS DISTINCT FROM` catches NULL: a key the registry does not carry is not a key awaiting a
    decision. The foreign key refuses it first, so the refusal is asserted on either arm."""
    with pytest.raises((psycopg2.errors.RaiseException, psycopg2.errors.ForeignKeyViolation)):
        _row(conn, "not_a_dataset")


def test_the_licence_gate_fires_on_UPDATE_as_well_as_INSERT(conn: psycopg2.extensions.connection) -> None:
    """`061`'s equivalent fired BEFORE INSERT OR UPDATE and was only ever exercised by INSERTs
    (A-C16 finding 1). Existing rows survive a status flip — the read path hides them within 60 s
    — but a WRITE naming an uncleared dataset is refused whichever statement makes it."""
    _row(conn, "acs5")
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'blocked' WHERE dataset_key = 'acs5'")
        cur.execute("SELECT count(*) FROM geo_metric")
        assert cur.fetchone()[0] == 1, "an existing row must survive the flip"
    with pytest.raises(psycopg2.errors.RaiseException):
        with conn.cursor() as cur:
            cur.execute("UPDATE geo_metric SET value_num = 1 WHERE geo_id = '78704'")


def test_the_migration_manages_no_transaction_of_its_own(conn: psycopg2.extensions.connection) -> None:
    """`tests/test_migrate.py::test_migration_files_never_manage_their_own_transaction` reads `;`
    immediately before `BEGIN` as a self-managed transaction, which is why `061` and `062` carry no
    DECLARE section. Asserted here too, at the file the runner will actually apply."""
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[2] / "migrations" / "064_geo_metric.sql").read_text(encoding="utf-8")
    assert "DECLARE" not in sql
    assert "$$\nBEGIN" in sql
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
poetry run pytest tests/census/test_migration_064.py -q -W error
```

Expected: FAIL — `psycopg2.errors.UndefinedTable: relation "geo_metric" does not exist` on every case, and the last case fails on `FileNotFoundError`.

- [ ] **Step 3: Write the migration**

Create `migrations/064_geo_metric.sql`:

```sql
-- Neighbourhood shading (spec 2026-09-10; D-C34, D-C35). One row per geography per metric per
-- vintage, at the geography the metric is honest at -- ZCTA '860' for income, place '160' for
-- growth, county '050' for payroll per establishment. `market_metric`'s sibling: same column
-- vocabulary, same licence gate, a different subject. `market_metric` answers "what is the market
-- around THIS PRACTICE"; this answers "what is true of THIS ZIP CODE". A polygon has no listing,
-- and shading a metro's ZCTAs off market_metric would mean one row per listing per polygon,
-- recomputed whenever a listing moved.
--
-- `064`, not `091`: D14 assigns SP3-B the `060`+ range (060/061/062/063 are taken) and `090`-`099`
-- is main's platform range (A-C10). The ledger runner applies each file exactly once and refuses
-- only files whose bytes no longer match a recorded checksum, so sorting before an already-applied
-- `090` is not a problem. Depends on `dataset_registry` (017) and nothing later.
CREATE TABLE geo_metric (
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL,          -- '860' zcta | '160' place | '050' county (018's own comment)
  vintage text NOT NULL,                   -- the VALUE's vintage: '2019–2023' (acs5, en dash) | '2022' (cbp)
  metric_key text NOT NULL,                -- 'median_hh_income' | 'population_growth_pct' | 'revenue_per_establishment'
  value_num numeric,
  unit text NOT NULL,                      -- 'usd' | 'pct' -- market_metric's own vocabulary
  is_derived boolean NOT NULL DEFAULT false,
  formula_version text,
  moe numeric,
  suppressed boolean NOT NULL DEFAULT false,
  suppress_reason text,                    -- 'no_moe' | 'high_moe' | 'input_suppressed' | 'source_flag'
  inputs jsonb,                            -- D9's shape: {"acs5":"2019–2023","geo_level":"zcta"}
  source_dataset text NOT NULL REFERENCES dataset_registry(dataset_key),
  computed_at timestamptz NOT NULL,
  PRIMARY KEY (geo_id, summary_level, vintage, metric_key)
);
-- The read path's only access pattern: one layer, one geography level, one vintage, joined to
-- geo_area by geo_id. Without this it is a sequential scan of every geography in six states. A
-- PARTIAL index per summary level measured 25.0 ms against this one's 49.8 ms on an Austin z11
-- viewport; it is not here because at ~130 ZCTAs the 25 ms is not the cost that matters and three
-- indexes on a table with one access pattern is three things to keep in step. It is the first
-- thing to add if this query ever appears in a slow log.
CREATE INDEX geo_metric_layer_idx ON geo_metric (summary_level, metric_key, vintage);

-- The twin of market_metric_license_gate (061:59-68, body replaced at 062:22-28). Same reason: a
-- table that will accept a blocked dataset's values is one code path away from shading them. The
-- read path filters live and gate.py expires a cached answer inside 60 s, but neither stops a
-- nightly writer from filling the table with figures nobody may show -- and a polygon layer is
-- exactly where that would go unnoticed, because a map has no per-figure attribution line to look
-- wrong. IS DISTINCT FROM also catches a missing registry row (NULL).
--
-- No DECLARE section, deliberately: `tests/test_migrate.py::
-- test_migration_files_never_manage_their_own_transaction` treats `; BEGIN` as a self-managed
-- transaction, and 061 and 062 both carry that note. The message names only the dataset key,
-- following 062's own correction -- 061 read license_status twice and a concurrent registry update
-- between the two reads could name a stale status.
CREATE OR REPLACE FUNCTION geo_metric_license_gate() RETURNS trigger AS $$
BEGIN
  IF (SELECT license_status FROM dataset_registry WHERE dataset_key = NEW.source_dataset) IS DISTINCT FROM 'cleared' THEN
    RAISE EXCEPTION 'geo_metric write refused: dataset % is not licence-cleared (licence gate)', NEW.source_dataset;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER geo_metric_license_gate BEFORE INSERT OR UPDATE ON geo_metric
  FOR EACH ROW EXECUTE FUNCTION geo_metric_license_gate();
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
poetry run pytest tests/census/test_migration_064.py tests/test_migrate.py -q -W error
```

Expected: `PASS` on both files. `test_migrate.py`'s file-shape guards (numbering, no self-managed transaction, checksum ledger) cover the new file automatically.

- [ ] **Step 5: Run the backend gate**

```bash
poetry run ruff check app tests scripts && poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e --cov-fail-under=100
```

Expected: PASS at 100 %.

- [ ] **Step 6: Commit**

```bash
git add migrations/064_geo_metric.sql tests/census/test_migration_064.py
git commit -m "feat(census): geo_metric — market_metric's per-geography sibling, licence-gated

One row per (geography, metric, vintage) at the geography the metric is honest at, with
market_metric's own column vocabulary and the twin of its BEFORE INSERT OR UPDATE licence
trigger — including the UPDATE arm 061's equivalent never had a test for. 064, in SP3-B's
own 060+ range (D14/D-NS2), depending on dataset_registry and nothing later.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 6: ACS at summary level `860`, and a `--levels` filter

A-C33's "no new ingest is required to start" is true of GEOMETRY and only of geometry. `app/census/acs.py`'s `GEOGRAPHIES()` loads `140`, `160`, `050`, `040`, `310` and `010`; `geoid()` raises `ValueError` for anything else. So `acs_measure` carries no ZCTA row, and `B19013_001E` — the median household income D-C34 wants shaded at ZCTA — does not exist at that geography. **Aggregating tracts up is refused** (D-NS4): `metrics.weighted_median` is a household-weighted average, it has no combined margin of error by construction, and a figure that can never be suppression-tested would hollow out D-C36 for the one layer it governs. **Amended 2026-09-12 (Task INCOME-MEDIAN): `weighted_median` is now a true interpolated weighted median; the refusal to aggregate tract medians into ZCTA polygons stands — a weighted median still carries no combined margin of error.**

**The load itself is NOT run in this task.** `CENSUS_API_KEY` is worker-only and John holds it (CLAUDE.md), so the implementer writes and unit-tests the code against a stubbed `CensusClient` — exactly as `tests/census/test_acs.py` already does — and the real run against QA is Task 11's deploy step, with R5's kill condition attached to it.

**Re-basing states: NONE. The thirteen frozen hashes must not move.**

**Files:**
- Modify: `app/census/acs.py:35` (a second column constant), `:54-64` (`GEOGRAPHIES`), `:67-86` (`geoid`), `:120-141` (`load`)
- Modify: `scripts/census_load.py:157-216` (`cmd_acs`), and its sub-parser at `:660-663`
- Modify: `tests/census/test_acs.py`, `tests/scripts/test_census_load.py`
- Test: both of the above

**Interfaces:**
- Consumes: nothing from an earlier task.
- Produces:
  ```python
  # app/census/acs.py
  ZCTA_COL: str = "zip code tabulation area"
  def GEOGRAPHIES(states: list[str]) -> list[Geo]      # + Geo("860", f"{ZCTA_COL}:*", None), national, once
  def geoid(row: Mapping[str, str | None], summary_level: str) -> str   # + the '860' branch
  def load(conn, client_factory, dataset_key: str, states: list[str], levels: list[str] | None = None) -> int
  ```
  Task 8's `geo_metric.py` reads `acs_measure` rows at `summary_level = '860'` for `B19013_001E`/`B19013_001M`; nothing calls `load` with `levels` except `scripts/census_load.py acs --levels`.

- [ ] **Step 1: Write the failing test**

Append to `tests/census/test_acs.py`:

```python
# --- D-NS4: ZCTA income is LOADED, never aggregated from tracts -------------------------------
# A weighted median has no combined margin of error by construction, so an aggregated figure could
# never fail the CV test — and shading ~130 ZCTAs with figures that can never be suppressed would
# hollow out D-C36, whose whole point is that the margin is shown and measured.


def test_geographies_carries_the_zcta_level_once_nationally() -> None:
    from app.census import acs

    geos = acs.GEOGRAPHIES(["48", "06"])
    zcta = [g for g in geos if g.summary_level == "860"]
    assert len(zcta) == 1, "ZCTAs have not been nested inside states in the ACS 5-year API since 2019"
    assert zcta[0].for_ == "zip code tabulation area:*"
    assert zcta[0].in_ is None
    # The six that were already there are untouched, and the two national levels stay last.
    assert [g.summary_level for g in geos if g.in_ is not None] == ["140", "160", "050", "140", "160", "050"]


def test_geoid_builds_a_zcta_id_from_the_apis_own_column_name() -> None:
    from app.census import acs

    assert acs.geoid({"zip code tabulation area": "78704"}, "860") == "78704"
    with pytest.raises(ValueError, match="zip code tabulation area"):
        acs.geoid({"state": "48"}, "860")
    with pytest.raises(ValueError, match="999"):
        acs.geoid({}, "999")


def test_load_with_a_levels_filter_fetches_that_level_alone_and_still_records_an_ingest_run(conn) -> None:
    """`--levels 860` exists so the ZCTA level can be loaded on its own rather than re-running all
    six geographies for six states. The run is recorded in `ingest_run` exactly as any other."""
    from app.census import acs

    seen: list[tuple[str, str | None]] = []

    class _Client:
        request_count = 3
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def fetch_table(self, get, for_, variables, in_):
            seen.append((for_, in_))
            return [{"NAME": "ZCTA5 78704", "zip code tabulation area": "78704", "B19013_001E": "92150", "B19013_001M": "6420"}]

    n = acs.load(conn, lambda ds: _Client(), "acs5", ["48", "06"], levels=["860"])
    assert seen == [("zip code tabulation area:*", None)], "a level filter must not fetch the other five"
    assert n > 0
    with conn.cursor() as cur:
        cur.execute("SELECT geo_id, summary_level FROM acs_measure WHERE variable = 'B19013_001E'")
        assert cur.fetchall() == [("78704", "860")]
        cur.execute("SELECT status, rows_written, request_count FROM ingest_run WHERE dataset_key = 'acs5' ORDER BY id DESC LIMIT 1")
        status, rows, requests = cur.fetchone()
    assert status == "succeeded" and rows == n and requests == 3


def test_load_without_a_levels_filter_still_fetches_every_geography(conn) -> None:
    from app.census import acs

    seen: list[str] = []

    class _Client:
        request_count = 0
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def fetch_table(self, get, for_, variables, in_):
            seen.append(for_)
            return []

    acs.load(conn, lambda ds: _Client(), "acs5", ["48"])
    assert "zip code tabulation area:*" in seen
    assert len(seen) == len(acs.GEOGRAPHIES(["48"])), "the default must still be every geography"
```

(`conn` and the registry fixtures come from `tests/conftest.py`; `tests/census/test_acs.py` already imports `pytest` and uses `conn`. Match that file's existing client-stub shape if it differs from the one above — the assertions are what matter.)

Append to `tests/scripts/test_census_load.py`:

```python
def test_cmd_acs_passes_a_levels_filter_through(monkeypatch: pytest.MonkeyPatch, scratch_dsn: str) -> None:
    """The CLI's own half of D-NS4: `census_load.py acs --levels 860` loads the one level."""
    from scripts import census_load

    captured: dict[str, object] = {}
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "test-only-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "engineering@vinfoundation.org")
    from app.census import acs
    monkeypatch.setattr(acs, "load", lambda conn, factory, key, states, levels=None: captured.setdefault("levels", levels) or 0)
    assert census_load.main(["acs", "--dataset", "acs5", "--levels", "860"]) == 0
    assert captured["levels"] == ["860"]


def test_cmd_acs_defaults_to_every_level(monkeypatch: pytest.MonkeyPatch, scratch_dsn: str) -> None:
    from scripts import census_load

    captured: dict[str, object] = {}
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "test-only-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "engineering@vinfoundation.org")
    from app.census import acs
    monkeypatch.setattr(acs, "load", lambda conn, factory, key, states, levels=None: captured.setdefault("levels", levels) or 0)
    assert census_load.main(["acs", "--dataset", "acs5"]) == 0
    assert captured["levels"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
poetry run pytest tests/census/test_acs.py tests/scripts/test_census_load.py -q -W error
```

Expected: FAIL — `assert len(zcta) == 1` gets `0`, `geoid(..., "860")` raises `ValueError: 860`, `load()` gets `unexpected keyword argument 'levels'`, and `census_load.py acs --levels` is an unrecognised argument.

- [ ] **Step 3: Write the minimal implementation**

In `app/census/acs.py`, add beside `CBSA_COL` on line 35:

```python
CBSA_COL = "metropolitan statistical area/micropolitan statistical area"
# D-NS4: ZCTAs have not been nested inside states in the ACS 5-year API since the 2019 vintage, so
# the query is NATIONAL and returns roughly 33,700 rows per variable in one page — the largest
# single ACS page this pipeline issues. It is loaded rather than aggregated from tracts because a
# household-weighted median has no combined margin of error by construction and could therefore
# never be suppression-tested, which is the one thing D-C36 governs for this layer.
ZCTA_COL = "zip code tabulation area"
```

replace `GEOGRAPHIES` (lines 54-64):

```python
def GEOGRAPHIES(states: list[str]) -> list[Geo]:
    geos: list[Geo] = []
    for st in states:
        geos += [
            Geo("140", "tract:*", f"state:{st}"),
            Geo("160", "place:*", f"state:{st}"),
            Geo("050", "county:*", f"state:{st}"),
            Geo("040", f"state:{st}", None),
        ]
    geos += [Geo("860", f"{ZCTA_COL}:*", None), Geo("310", f"{CBSA_COL}:*", None), Geo("010", "us:1", None)]
    return geos
```

add the `860` branch to `geoid`, immediately before the `310` branch:

```python
    if summary_level == "860":
        return field(ZCTA_COL)
```

and give `load` the filter (lines 120-141):

```python
def load(
    conn: psycopg2.extensions.connection,
    client_factory: Callable[[Dataset], CensusClient],
    dataset_key: str,
    states: list[str],
    levels: list[str] | None = None,
) -> int:
    """`levels` restricts the load to those summary levels — D-NS4's reason: `860` can be loaded on
    its own rather than re-running all six geographies for six states. `None` is every geography,
    which is what every existing caller passes."""
    ds = load_registry(conn)[dataset_key]
    if not ds.cleared:
        raise PermissionError(f"{dataset_key} is {ds.license_status}; loads are refused (spec §1 licensing gate)")
    variables = VARIABLES[dataset_key]
    wanted = [g for g in GEOGRAPHIES(states) if levels is None or g.summary_level in levels]
    with ingest.run(conn, dataset_key, ds.vintage) as run, client_factory(ds) as client:
        for geo in wanted:
            rows = client.fetch_table(["NAME", *variables], geo.for_, variables, geo.in_)
            measures = to_measures(rows, variables, geo.summary_level)
            with conn.cursor() as cur:
                cur.executemany(
                    UPSERT,
                    [(m.geo_id, m.summary_level, ds.vintage, m.variable, m.estimate, m.moe, run.id) for m in measures],
                )
            run.rows += len(measures)
        run.requests = client.request_count
        return run.rows
```

In `scripts/census_load.py`, add the argument to the `acs` sub-parser (after its `--dataset` line at `:661-662`):

```python
    a.add_argument("--levels", nargs="+", default=None,
                   help="restrict to these ACS summary levels (e.g. 860 for ZCTAs alone); default is every geography")
```

and pass it through in `cmd_acs`, replacing `n = acs.load(conn, factory, ds_key, states)` with:

```python
                n = acs.load(conn, factory, ds_key, states, levels=args.levels)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
poetry run pytest tests/census/test_acs.py tests/scripts/test_census_load.py -q -W error
```

Expected: PASS.

- [ ] **Step 5: Verify the `for=` clause against the Census API's own geography list**

Not a code step, and it does not need a key: the geography list is public. Spec §2.3 records the ZCTA `for=`/`in=` clause as **unverified**, and D-NS4 says the implementer must check it before the load.

```bash
curl -s "https://api.census.gov/data/2023/acs/acs5/geography.json" \
  | python3 -c "import json,sys; print([g['name'] for g in json.load(sys.stdin)['fips'] if 'zip' in g['name']])"
```

Expected: `['zip code tabulation area']`, with no `requires` entry — a national query. **If the name differs, change `ZCTA_COL` to whatever it prints and re-run Step 4; if the level is absent for this vintage, STOP** — D-C34's ZCTA ruling has to go back to John with the tract alternative rather than being quietly satisfied with a weighted average.

- [ ] **Step 6: Run the backend gate**

```bash
poetry run ruff check app tests scripts && poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e --cov-fail-under=100
```

Expected: PASS at 100 %. `load`'s new branch (`levels is None or …`) has both arms covered by Step 1's two `load` cases; `geoid`'s new branch by its own case.

- [ ] **Step 7: Commit**

```bash
git add app/census/acs.py scripts/census_load.py tests/census/test_acs.py tests/scripts/test_census_load.py
git commit -m "feat(census): load ACS at summary level 860, and a --levels filter

D-NS4: ZCTA income is LOADED, never aggregated from tracts — a household-weighted
median has no combined margin of error by construction and could never be suppression-
tested, which would hollow out D-C36 for the one layer it governs. The query is national
(ZCTAs have not been nested inside states in the ACS 5-year API since 2019), and
--levels lets 860 be loaded on its own instead of re-running six geographies for six
states. The real run against QA is a deploy step: CENSUS_API_KEY is worker-only.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```


---

## Task 7: `app/census/bands.py` — band ambiguity, computed server-side and pinned to the design

For `income`, a polygon's value is band-ambiguous when its margin of error crosses a legend stop. D-C36 rules that such a polygon is **shown with its value and a caveat, never greyed** — "greying a measured figure is its own false statement" — and the SHARE of polygons carrying that flag is the measurement that gates D-C34's tract toggle. Both need one implementation, and the stops it bands against must be the design's own or the tip and the legend disagree.

**Re-basing states: NONE. The thirteen frozen hashes must not move.**

**Files:**
- Create: `app/census/bands.py`
- Create: `tests/census/test_bands.py`
- Create: `scripts/measure_band_ambiguity.py`
- Create: `tests/scripts/test_measure_band_ambiguity.py`
- Test: both test files

**Interfaces:**
- Consumes: `geo_metric` (Task 5) — the measurement script reads it.
- Produces:
  ```python
  # app/census/bands.py
  INCOME_STOPS: tuple[int, ...] = (50000, 75000, 100000, 150000)
  def band_index(value: float, stops: tuple[int, ...] = INCOME_STOPS) -> int
  def band_ambiguous(value: float | None, moe: float | None, stops: tuple[int, ...] = INCOME_STOPS) -> bool
  ```
  Task 9's endpoint calls `band_ambiguous(value, moe)` for the `income` layer only and serialises the result as each feature's `band_ambiguous`.
  ```python
  # scripts/measure_band_ambiguity.py
  def measure(conn, metric_key: str, vintage: str) -> dict[str, dict[str, int]]
  def main(argv: list[str] | None = None) -> int
  ```

- [ ] **Step 1: Write the failing test**

Create `tests/census/test_bands.py`:

```python
"""Band ambiguity for the income layer (D-C36, D-NS17).

The design's bands are not re-cut: they are dollar-meaningful, legible, and what the design
published. The honesty is carried by the hover tip, and this is what the tip and the tract-toggle
measurement both read — ONE implementation, because two would put different sentences on the same
polygon."""
import re
from pathlib import Path

import pytest

from app.census import bands

ROOT = Path(__file__).resolve().parents[2]


def test_band_index_is_the_designs_own_right_open_rule() -> None:
    """`logic.js`'s `bucket`: `while (i < cfg.stops.length && v >= cfg.stops[i]) i++`. Right-open,
    so a value exactly ON a stop belongs to the band ABOVE it."""
    assert bands.band_index(0) == 0
    assert bands.band_index(49999.99) == 0
    assert bands.band_index(50000) == 1
    assert bands.band_index(74999) == 1
    assert bands.band_index(75000) == 2
    assert bands.band_index(100000) == 3
    assert bands.band_index(149999) == 3
    assert bands.band_index(150000) == 4
    assert bands.band_index(10 ** 9) == 4


def test_band_ambiguous_is_true_only_when_the_margin_crosses_a_stop() -> None:
    # The spec's own example: $92,150 ± $6,420 spans 85,730..98,570 — both inside 75K-100K.
    assert bands.band_ambiguous(92150, 6420) is False
    # Widen it past 100,000 and it spans two bands.
    assert bands.band_ambiguous(92150, 9000) is True
    # And past 75,000 downwards.
    assert bands.band_ambiguous(78000, 4000) is True
    # Exactly to the stop is not across it: the rule is right-open, so 100,000 IS the next band —
    # hi == 100000 lands in band 3 and lo in band 2, which IS a crossing.
    assert bands.band_ambiguous(95000, 5000) is True
    assert bands.band_ambiguous(94999, 5000) is False


def test_a_missing_value_or_a_missing_margin_is_never_ambiguous() -> None:
    """Global Constraint (c): the producer's sentinel. `_suppression(None, None)` returns
    `(False, None)` — a missing VALUE is not suppressed and there is nothing to band — and a
    present value with a missing margin is already `suppressed='no_moe'`, so it is greyed rather
    than caveated. Neither is 'ambiguous', and a guard that said otherwise would put a margin
    caveat on a polygon that has no margin."""
    assert bands.band_ambiguous(None, 6420) is False
    assert bands.band_ambiguous(92150, None) is False
    assert bands.band_ambiguous(None, None) is False
    assert bands.band_ambiguous(92150, 0) is False


def test_the_design_income_stops_equal_the_band_constants() -> None:
    """Two-way, against the AMENDED design file itself — the shape
    `tests/api/test_seller_listings.py::test_the_design_ownership_options_equal_ownerships_tuple`
    (A22, Task SL10) established. If the design's bands are ever re-cut, this fails on both sides
    at once instead of the map and the legend quietly disagreeing."""
    design = (ROOT / "docs" / "design-reference" / "design_handoff_practice_match_v3" / "Practice Match V3.dc.html").read_text(encoding="utf-8")
    m = re.search(r'income:\s*\{[^}]*?stops:\s*\[([^\]]*)\]', design)
    assert m, "VALUE_LAYERS.income no longer declares `stops` — the design's bands moved"
    assert tuple(int(s) for s in m.group(1).split(",")) == bands.INCOME_STOPS
    # …and the buckets the legend prints are still five, one more than the stops (D-C36).
    b = re.search(r'income:\s*\{[^}]*?buckets:\s*\[([^\]]*)\]', design)
    assert b and len(b.group(1).split(",")) == len(bands.INCOME_STOPS) + 1
```

Create `tests/scripts/test_measure_band_ambiguity.py`:

```python
"""scripts/measure_band_ambiguity.py — D-C34's trigger for the tract toggle, as a number.

A reporting script: it reads `geo_metric` and `bands.py`, runs nowhere on the request path and
builds nothing."""
import runpy
import sys
from pathlib import Path

import psycopg2
import pytest

from scripts import measure_band_ambiguity as MB

ROOT = Path(__file__).resolve().parent.parent.parent


def _metric(conn, geo_id: str, level: str, value: float | None, moe: float | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, source_dataset, computed_at) "
            "VALUES (%s, %s, '2019–2023', 'median_hh_income', %s, 'usd', %s, 'acs5', now())",
            (geo_id, level, value, moe),
        )


def test_measure_reports_the_share_per_summary_level(conn: psycopg2.extensions.connection) -> None:
    _metric(conn, "78704", "860", 92150, 6420)    # measured, not ambiguous
    _metric(conn, "78745", "860", 92150, 9000)    # measured, ambiguous
    _metric(conn, "78702", "860", 92150, None)    # no margin — counted, never ambiguous
    _metric(conn, "78701", "860", None, None)     # no value at all
    _metric(conn, "48453000", "140", 92150, 9000)
    out = MB.measure(conn, "median_hh_income", "2019–2023")
    assert out["860"] == {"polygons": 4, "with_value": 3, "with_moe": 2, "ambiguous": 1}
    assert out["140"] == {"polygons": 1, "with_value": 1, "with_moe": 1, "ambiguous": 1}


def test_measure_returns_nothing_when_the_table_is_empty(conn: psycopg2.extensions.connection) -> None:
    assert MB.measure(conn, "median_hh_income", "2019–2023") == {}


def test_main_prints_one_line_per_level(conn: psycopg2.extensions.connection, scratch_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _metric(conn, "78704", "860", 92150, 9000)
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert MB.main(["--vintage", "2019–2023"]) == 0
    out = capsys.readouterr().out
    assert "860" in out and "100.0%" in out


def test_main_refuses_without_a_database_url(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert MB.main(["--vintage", "2019–2023"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_the_main_guard_is_covered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["measure_band_ambiguity.py", "--vintage", "2019–2023"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / "measure_band_ambiguity.py"), run_name="__main__")
    assert exc.value.code == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
poetry run pytest tests/census/test_bands.py tests/scripts/test_measure_band_ambiguity.py -q -W error
```

Expected: collection errors — `No module named 'app.census.bands'` and `No module named 'scripts.measure_band_ambiguity'`.

- [ ] **Step 3: Run the real producer and print what it returns, before writing the guard**

Global Constraint (c), for the two sentinels this module's guard has to agree with:

```bash
poetry run python -c "
from app.census.materialize import _suppression
for args in [(None, None), (92150, None), (92150, 6420), (92150, 99999)]:
    print(args, '->', _suppression(*args))
"
```

Expected, exactly:

```
(None, None) -> (False, None)
(92150, None) -> (True, 'no_moe')
(92150, 6420) -> (False, None)
(92150, 99999) -> (True, 'high_moe')
```

So a MISSING value is `(False, None)`: it is not suppressed, and the thing that makes it "no data" is `value_num IS NULL`, not `suppressed`. `band_ambiguous` must therefore return `False` for a `None` value rather than raising, and the endpoint must test the value as well as the flag.

- [ ] **Step 4: Write the minimal implementation**

Create `app/census/bands.py`:

```python
"""Legend bands for the shaded layers (D-C36, D-NS17).

The design's published bands are kept — they are dollar-meaningful, legible, and what the design
published — and the honesty is carried by the hover tip rather than by re-cutting the legend. This
is the one implementation of "does this polygon's margin of error cross a legend stop", read both
by the endpoint (which puts the caveat in the tip) and by `scripts/measure_band_ambiguity.py`
(which produces the share D-C34 gates the tract toggle on). Two implementations would put
different sentences on the same polygon.

`INCOME_STOPS` is pinned two-way against the amended design file itself by
`tests/census/test_bands.py::test_the_design_income_stops_equal_the_band_constants`."""
from __future__ import annotations

# logic.js's VALUE_LAYERS.income.stops. Five buckets, four stops (V3 widened income's ramp from
# V2's four; every other layer keeps four buckets and three stops).
INCOME_STOPS: tuple[int, ...] = (50000, 75000, 100000, 150000)


def band_index(value: float, stops: tuple[int, ...] = INCOME_STOPS) -> int:
    """The design's own right-open rule, `logic.js`'s `bucket`:
    `while (i < cfg.stops.length && v >= cfg.stops[i]) i++`. A value exactly ON a stop belongs to
    the band above it, on both sides of the wire."""
    i = 0
    while i < len(stops) and value >= stops[i]:
        i += 1
    return i


def band_ambiguous(value: float | None, moe: float | None, stops: tuple[int, ...] = INCOME_STOPS) -> bool:
    """Whether `value ± moe` spans more than one legend band.

    `False` for a missing value and for a missing margin, and those are two DIFFERENT states:
    a missing value is `_suppression(None, None) == (False, None)` — not suppressed, nothing to
    band — and a present value with no margin is already suppressed `no_moe`, so it is greyed
    rather than caveated. A margin of exactly zero spans nothing. None of these is "ambiguous",
    and a caveat on a polygon with no margin would be a sentence about a number that was never
    reported."""
    if value is None or not moe:
        return False
    return band_index(value - moe, stops) != band_index(value + moe, stops)
```

Create `scripts/measure_band_ambiguity.py`:

```python
"""D-C34's trigger for the tract toggle, as a number rather than a date.

"A tract toggle follows, and ITS TRIGGER IS A MEASUREMENT, NOT A DATE: the share of tract polygons
whose margin of error spans more than one legend band, measured under D-C36 and reported before
the toggle is built." This reports that share per summary level, from `geo_metric` and
`app.census.bands`. It runs nowhere on the request path and builds nothing."""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import psycopg2
import psycopg2.extensions

from app.census.bands import band_ambiguous


def measure(conn: psycopg2.extensions.connection, metric_key: str, vintage: str) -> dict[str, dict[str, int]]:
    """`{summary_level: {polygons, with_value, with_moe, ambiguous}}` for one metric and vintage.

    Every polygon in the table is counted, including the ones with no figure: the share that
    matters to D-C34 is over the polygons a reader would SEE, and a no-data polygon is drawn."""
    out: dict[str, dict[str, int]] = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT summary_level, value_num, moe FROM geo_metric WHERE metric_key = %s AND vintage = %s",
            (metric_key, vintage),
        )
        for level, value, moe in cur.fetchall():
            row = out.setdefault(level, {"polygons": 0, "with_value": 0, "with_moe": 0, "ambiguous": 0})
            row["polygons"] += 1
            if value is not None:
                row["with_value"] += 1
            if moe is not None:
                row["with_moe"] += 1
            if band_ambiguous(None if value is None else float(value), None if moe is None else float(moe)):
                row["ambiguous"] += 1
    return out


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="report the share of polygons whose margin spans a legend band")
    p.add_argument("--metric", default="median_hh_income")
    p.add_argument("--vintage", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[measure_band_ambiguity] DATABASE_URL is not set", file=sys.stderr)
        return 2
    conn = psycopg2.connect(dsn)
    try:
        result: dict[str, dict[str, Any]] = measure(conn, args.metric, args.vintage)
    finally:
        conn.close()
    for level in sorted(result):
        row = result[level]
        share = (100.0 * row["ambiguous"] / row["with_moe"]) if row["with_moe"] else 0.0
        print(
            f"{level}: {row['polygons']} polygons, {row['with_value']} with a value, "
            f"{row['with_moe']} with a margin, {row['ambiguous']} ambiguous ({share:.1f}% of those with a margin)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
poetry run pytest tests/census/test_bands.py tests/scripts/test_measure_band_ambiguity.py -q -W error
```

Expected: `10 passed`.

- [ ] **Step 6: Run the backend gate**

```bash
poetry run ruff check app tests scripts && poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e --cov-fail-under=100
```

Expected: PASS at 100 %. Every branch has a case: `band_index`'s loop both ways, `band_ambiguous`'s three refusal arms and its true/false result, `measure`'s two `is not None` arms and its empty return, `main`'s `if not dsn` both ways and the `if row["with_moe"]` ternary both ways (the empty-margin level comes from the `78701` row).

- [ ] **Step 7: Commit**

```bash
git add app/census/bands.py tests/census/test_bands.py \
  scripts/measure_band_ambiguity.py tests/scripts/test_measure_band_ambiguity.py
git commit -m "feat(census): band ambiguity, server-side, pinned to the design's own stops

D-C36 keeps the design's published dollar bands and carries the honesty in the tip: a
polygon whose margin spans a stop is shown WITH its value and a caveat, never greyed.
One implementation, read by the endpoint and by the measurement D-C34 gates the tract
toggle on, with INCOME_STOPS pinned two-way against the amended design file itself.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 8: `app/census/geo_metric.py` — the only writer, nightly, never on the request path

Three metrics at three levels, from datasets already loaded, scoped to the six `market_state` states, per-triple delete-and-rewrite in one transaction each. It calls `app.census.metrics` and imports `materialize._suppression`; it reimplements neither, and a test asserts the function identity (D-NS6, R2).

**Re-basing states: NONE. The thirteen frozen hashes must not move.**

**Files:**
- Create: `app/census/geo_metric.py`
- Create: `tests/census/test_geo_metric.py`
- Modify: `app/tasks/census.py` (a task beside `materialize_metrics`, and its registration at `:408`)
- Modify: `app/tasks/celery_app.py:44-52` (one beat entry)
- Modify: `tests/test_celery.py` (the set-equality pin), `tests/census/test_tasks.py` (the task's own case)
- Test: `tests/census/test_geo_metric.py`, `tests/census/test_tasks.py`, `tests/test_celery.py`

**Interfaces:**
- Consumes: `geo_metric` (Task 5); `acs_measure` at summary level `860` (Task 6); `app.census.materialize._suppression`; `app.census.metrics.{population_growth_pct, revenue_per_establishment, FORMULA_VERSION}`; `app.census.vintage.active`; `app.census.registry.load`.
- Produces:
  ```python
  # app/census/geo_metric.py
  LAYERS: tuple[tuple[str, str, str, tuple[str, ...]], ...]   # (metric_key, summary_level, source_dataset, also_gated_on)
  GEO_VERSION_KEY: str = "market:geo:version"
  def materialize_geo(conn: psycopg2.extensions.connection, redis: redis_sync.Redis) -> dict[str, int]
  ```
  Task 9's endpoint reads `geo_metric` rows written here and puts `GEO_VERSION_KEY`'s value in its cache key.
  ```python
  # app/tasks/census.py
  def materialize_geo_metrics() -> dict[str, object]
  materialize_geo_metrics_task = celery_app.task(name="census.materialize_geo_metrics")(materialize_geo_metrics)
  ```

- [ ] **Step 1: Write the failing test**

Create `tests/census/test_geo_metric.py`:

```python
"""app/census/geo_metric.py — the only writer of `geo_metric` (D-NS5 through D-NS9).

`app/census/materialize.py` stays the only writer of `market_metric` and is not edited by this
sub-project at all, except that `_suppression` gains a second importer."""
import fakeredis
import psycopg2
import pytest

from app.census import geo_metric, materialize

STATE_TX, STATE_CA = "48", "06"


def _geo(conn, geo_id: str, level: str, name: str, state: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid) VALUES "
            "(%s, %s, '2023', %s, %s, ST_Multi(ST_GeomFromText('POLYGON((-98 30,-97 30,-97 31,-98 31,-98 30))',4269)), ST_Point(-97.75,30.31,4269))",
            (geo_id, level, name, state),
        )


def _acs(conn, geo_id: str, level: str, vintage: str, variable: str, estimate, moe=None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO acs_measure (geo_id, summary_level, vintage, variable, estimate, moe) VALUES (%s,%s,%s,%s,%s,%s)",
            (geo_id, level, vintage, variable, estimate, moe),
        )


def _cbp(conn, geo_id: str, payroll_k, establishments, flag=None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO cbp_industry (geo_id, summary_level, vintage, naics_code, establishments, annual_payroll_k, flag) "
            "VALUES (%s, '050', '2022', '541940', %s, %s, %s)",
            (geo_id, establishments, payroll_k, flag),
        )


def _activate(conn) -> None:
    with conn.cursor() as cur:
        for key, vintage in (("tiger_cb", "2023"), ("acs5", "2019–2023"), ("acs5_prior", "2014–2018"), ("cbp", "2022")):
            cur.execute(
                "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s,%s,now(),'test') "
                "ON CONFLICT (dataset_key) DO UPDATE SET vintage = EXCLUDED.vintage",
                (key, vintage),
            )


@pytest.fixture
def world(conn: psycopg2.extensions.connection) -> psycopg2.extensions.connection:
    _activate(conn)
    # ZCTA rows carry no state_fips (tiger.py's BoundarySpec for '860' has none) — the loader
    # already filters the national ZCTA file to centroids inside a market state, so geo_area IS
    # the scope at that level. Place and county rows carry one, and are filtered on it.
    _geo(conn, "78704", "860", "ZCTA5 78704", None)
    _geo(conn, "78745", "860", "ZCTA5 78745", None)
    _geo(conn, "4805000", "160", "Austin", STATE_TX)
    _geo(conn, "1600000", "160", "Elsewhere", "17")          # Illinois: not a market_state
    _geo(conn, "48453", "050", "Travis County", STATE_TX)
    _acs(conn, "78704", "860", "2019–2023", "B19013_001E", 92150, 6420)   # measured
    _acs(conn, "78745", "860", "2019–2023", "B19013_001E", 41000, 40000)  # CV over 0.30 -> high_moe
    _acs(conn, "4805000", "160", "2019–2023", "B01003_001E", 1_100_000)
    _acs(conn, "4805000", "160", "2014–2018", "B01003_001E", 1_000_000)
    _acs(conn, "1600000", "160", "2019–2023", "B01003_001E", 500_000)
    _acs(conn, "1600000", "160", "2014–2018", "B01003_001E", 400_000)
    _cbp(conn, "48453", 32_000, 40)
    return conn


def test_the_three_ruled_metrics_land_at_the_three_ruled_levels(world) -> None:
    counts = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert counts == {"median_hh_income": 2, "population_growth_pct": 1, "revenue_per_establishment": 1}
    with world.cursor() as cur:
        cur.execute("SELECT metric_key, summary_level, geo_id, value_num, moe, unit, is_derived, formula_version, suppressed, suppress_reason, source_dataset, vintage FROM geo_metric ORDER BY metric_key, geo_id")
        rows = cur.fetchall()
    by = {(r[0], r[2]): r for r in rows}
    inc = by[("median_hh_income", "78704")]
    assert inc[1] == "860" and float(inc[3]) == 92150 and float(inc[4]) == 6420
    assert inc[5] == "usd" and inc[6] is False and inc[7] is None, "a published ACS estimate is not derived"
    assert inc[8] is False and inc[9] is None
    assert inc[10] == "acs5" and inc[11] == "2019–2023"
    growth = by[("population_growth_pct", "4805000")]
    assert growth[1] == "160" and round(float(growth[3]), 4) == 10.0 and growth[4] is None
    assert growth[5] == "pct" and growth[6] is True and growth[7] == "v1"
    econ = by[("revenue_per_establishment", "48453")]
    assert econ[1] == "050" and float(econ[3]) == 800_000 and econ[4] is None
    assert econ[5] == "usd" and econ[6] is True and econ[10] == "cbp" and econ[11] == "2022"


def test_scope_is_the_six_market_state_states(world) -> None:
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    with world.cursor() as cur:
        cur.execute("SELECT geo_id FROM geo_metric WHERE metric_key = 'population_growth_pct'")
        assert [r[0] for r in cur.fetchall()] == ["4805000"], "an Illinois place was materialised"


def test_suppression_is_applied_to_income_only_and_through_the_one_function(world) -> None:
    """D-NS17: feeding growth or econ through `_suppression` with `moe = None` would return
    `(True, 'no_moe')` and grey out EVERY growth and payroll polygon in the country, which is the
    opposite of honest — neither has a published margin, and both say so in the tip instead."""
    assert geo_metric._suppression is materialize._suppression, "a second CV/Z90 implementation"
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    with world.cursor() as cur:
        cur.execute("SELECT metric_key, geo_id, suppressed, suppress_reason FROM geo_metric ORDER BY metric_key, geo_id")
        rows = cur.fetchall()
    assert ("median_hh_income", "78745", True, "high_moe") in rows
    assert ("median_hh_income", "78704", False, None) in rows
    assert all(not r[2] for r in rows if r[0] != "median_hh_income"), "growth or econ was greyed"


def test_a_cbp_flag_suppresses_the_county_as_source_flag(conn, world) -> None:
    """§6: CBP withheld or noise-flagged the county cell. The figure is not shown and the tip says
    which of the four reasons it is."""
    with world.cursor() as cur:
        cur.execute("UPDATE cbp_industry SET flag = 'D' WHERE geo_id = '48453'")
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    with world.cursor() as cur:
        cur.execute("SELECT suppressed, suppress_reason FROM geo_metric WHERE metric_key = 'revenue_per_establishment'")
        assert cur.fetchone() == (True, "source_flag")


def test_the_write_is_idempotent_and_rewrites_rather_than_accumulating(world) -> None:
    first = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    second = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert first == second
    with world.cursor() as cur:
        cur.execute("SELECT count(*) FROM geo_metric")
        assert cur.fetchone()[0] == 4


def test_a_failed_triple_rolls_back_and_leaves_the_earlier_rows_standing(world, monkeypatch) -> None:
    """D-NS7: one transaction per (level, metric, vintage). A failure inside one leaves the
    previous vintage's rows in place — Census spec §11's 'keep the prior vintage active'."""
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    real = geo_metric._rewrite

    def boom(conn, level, metric_key, vintage, rows):
        if metric_key == "revenue_per_establishment":
            raise RuntimeError("the third triple failed")
        return real(conn, level, metric_key, vintage, rows)

    monkeypatch.setattr(geo_metric, "_rewrite", boom)
    with pytest.raises(RuntimeError):
        geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    with world.cursor() as cur:
        cur.execute("SELECT count(*) FROM geo_metric WHERE metric_key = 'revenue_per_establishment'")
        assert cur.fetchone()[0] == 1, "the earlier generation was lost"
    assert world.autocommit is True, "the caller's autocommit was not restored"


def test_a_layer_whose_licence_is_not_cleared_writes_nothing(world) -> None:
    """The trigger would refuse the write anyway (D-NS3); this is the writer declining to try, so
    a nightly run does not fail on a dataset the VIN Foundation has withdrawn."""
    with world.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'blocked' WHERE dataset_key = 'cbp'")
    counts = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert counts["revenue_per_establishment"] == 0
    assert counts["median_hh_income"] == 2


def test_growth_is_gated_on_acs5_prior_as_well_as_acs5(world) -> None:
    """R3's specific hole: growth is stamped `source_dataset = 'acs5'` but folds `acs5_prior`, and
    a gate that reads only the stamped key reproduces the licence hole A-C23 (1) closed."""
    with world.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'unresolved' WHERE dataset_key = 'acs5_prior'")
    counts = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert counts["population_growth_pct"] == 0
    assert counts["median_hh_income"] == 2


def test_a_dataset_with_no_active_vintage_writes_nothing(conn) -> None:
    """No `active_vintage` row at all: nothing to read and nothing to stamp."""
    assert geo_metric.materialize_geo(conn, fakeredis.FakeRedis()) == {
        "median_hh_income": 0, "population_growth_pct": 0, "revenue_per_establishment": 0
    }


def test_the_geo_version_is_bumped_on_every_run_so_cached_payloads_expire(world) -> None:
    """The endpoint's cache key carries this. Without it a nightly rewrite that changes values but
    not the vintage would be invisible for up to the 24 h TTL."""
    r = fakeredis.FakeRedis()
    geo_metric.materialize_geo(world, r)
    first = int(r.get(geo_metric.GEO_VERSION_KEY))
    geo_metric.materialize_geo(world, r)
    assert int(r.get(geo_metric.GEO_VERSION_KEY)) > first
```

Append to `tests/census/test_tasks.py`:

```python
def test_materialize_geo_metrics_rebuilds_the_polygon_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """`app/tasks/census.py`'s wrapper, in `materialize_metrics`' own shape: no Census I/O, so no
    key gate and no `_NotReady` handling — a missing active vintage is a real configuration error
    and is left to raise (A-C18 (3))."""
    from app.tasks import census as T

    closed: list[bool] = []

    class _Conn:
        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(T, "_conn", lambda: _Conn())
    monkeypatch.setattr("app.census.geo_metric.materialize_geo", lambda conn, redis: {"median_hh_income": 130})
    assert T.materialize_geo_metrics() == {"metrics": {"median_hh_income": 130}}
    assert closed == [True]
```

And in `tests/test_celery.py`, extend the beat set-equality assertion with the new entry:

```python
    assert beat["geo-metric-nightly"]["task"] == "census.materialize_geo_metrics"
    # 03:30 UTC, half an hour after materialize-nightly's 03:00: the two are independent (neither
    # reads the other's table) and the stagger keeps two heavy read-only passes over acs_measure
    # off one database at the same moment (D-NS9).
    assert beat["geo-metric-nightly"]["schedule"].hour == {3} and beat["geo-metric-nightly"]["schedule"].minute == {30}
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
poetry run pytest tests/census/test_geo_metric.py tests/census/test_tasks.py tests/test_celery.py -q -W error
```

Expected: `No module named 'app.census.geo_metric'`; `AttributeError: module 'app.tasks.census' has no attribute 'materialize_geo_metrics'`; `KeyError: 'geo-metric-nightly'`.

- [ ] **Step 3: Write the minimal implementation**

Create `app/census/geo_metric.py`:

```python
"""Materialise `geo_metric` — one row per (geography, metric, vintage), at the geography each
metric is honest at (spec 2026-09-10; D-C35, D-NS5 through D-NS9). The ONLY writer of this table.

`app/census/materialize.py` stays the only writer of `market_metric` and is not edited by this
sub-project at all, except that `_suppression` gains a second importer here. A listing's docked
panel keeps reading `market_metric`; the map reads `geo_metric`;
`tests/census/test_boundaries.py::test_the_endpoint_and_community_rows_agree_on_suppression` is
the test that makes the two agree.

Nothing here reimplements a formula or a suppression rule: `metrics.population_growth_pct` and
`metrics.revenue_per_establishment` are called unmodified, and `_suppression` is IMPORTED, with
its underscore kept — renaming it would touch `materialize.py`'s three call sites for no
behavioural reason, and "surgical diffs" outranks the naming convention here (D-NS6)."""
from __future__ import annotations

import json
import time
from typing import Any

import psycopg2.extensions
import redis as redis_sync

from app.census import metrics as M
from app.census.materialize import _suppression
from app.census.registry import load as load_registry
from app.census.vintage import active

# (metric_key, summary_level, source_dataset, also gated on). D-C35's assignment and nothing
# wider: `pets`, `households` and `competition` stay graduated symbols at the listing point.
# `population_growth_pct` folds acs5_prior but can only be STAMPED with one dataset key, which is
# exactly the hole A-C23 (1) closed for `vets_per_10k_households` — hence the fourth element.
LAYERS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("median_hh_income", "860", "acs5", ()),
    ("population_growth_pct", "160", "acs5", ("acs5_prior",)),
    ("revenue_per_establishment", "050", "cbp", ()),
)

# Bumped on every run, and carried in the boundary endpoint's cache key. Without it a nightly
# rewrite that changes values but not the vintage would be invisible for up to the 24 h TTL --
# `materialize_listing`'s own `listing:{id}:market:version` idiom, one table wider.
GEO_VERSION_KEY = "market:geo:version"

_UPSERT = """
INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, is_derived, formula_version, moe, suppressed, suppress_reason, inputs, source_dataset, computed_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
ON CONFLICT (geo_id, summary_level, vintage, metric_key) DO UPDATE SET value_num = EXCLUDED.value_num, unit = EXCLUDED.unit,
  is_derived = EXCLUDED.is_derived, formula_version = EXCLUDED.formula_version, moe = EXCLUDED.moe, suppressed = EXCLUDED.suppressed,
  suppress_reason = EXCLUDED.suppress_reason, inputs = EXCLUDED.inputs, source_dataset = EXCLUDED.source_dataset, computed_at = now()
"""

_DELETE = "DELETE FROM geo_metric WHERE summary_level = %s AND metric_key = %s AND vintage = %s"

# ZCTA rows in `geo_area` carry NO state_fips (tiger.py's BoundarySpec for '860' declares none),
# and they do not need one: `load_boundaries` already keeps only the ZCTAs whose centroid falls
# inside a market state, so joining geo_area IS the scope at this level.
_INCOME_SQL = """
SELECT g.geo_id, a.estimate, a.moe
  FROM geo_area g
  JOIN acs_measure a ON a.geo_id = g.geo_id AND a.summary_level = '860' AND a.vintage = %(av)s AND a.variable = 'B19013_001E'
 WHERE g.summary_level = '860' AND g.vintage = %(gv)s
"""

_GROWTH_SQL = """
SELECT g.geo_id, now_.estimate, prior.estimate
  FROM geo_area g
  JOIN acs_measure now_ ON now_.geo_id = g.geo_id AND now_.summary_level = '160' AND now_.vintage = %(av)s AND now_.variable = 'B01003_001E'
  JOIN acs_measure prior ON prior.geo_id = g.geo_id AND prior.summary_level = '160' AND prior.vintage = %(pv)s AND prior.variable = 'B01003_001E'
 WHERE g.summary_level = '160' AND g.vintage = %(gv)s AND g.state_fips = ANY(%(states)s)
"""

_ECON_SQL = """
SELECT g.geo_id, c.annual_payroll_k, c.establishments, c.flag
  FROM geo_area g
  JOIN cbp_industry c ON c.geo_id = g.geo_id AND c.summary_level = '050' AND c.vintage = %(cv)s AND c.naics_code = '541940'
 WHERE g.summary_level = '050' AND g.vintage = %(gv)s AND g.state_fips = ANY(%(states)s)
"""

_Row = tuple[str, str, str, str, float | None, str, bool, str | None, float | None, bool, str | None, str, str]


def _row(geo_id: str, level: str, vintage: str, key: str, value: float | None, unit: str, *,
         derived: bool = False, moe: float | None = None, suppressed: bool = False,
         reason: str | None = None, source: str = "acs5", inputs: dict[str, object]) -> _Row:
    return (
        geo_id, level, vintage, key, value, unit, derived, M.FORMULA_VERSION if derived else None,
        moe, suppressed, reason, json.dumps(inputs), source,
    )


def _income(cur: psycopg2.extensions.cursor, act: dict[str, str], states: list[str]) -> list[_Row]:
    cur.execute(_INCOME_SQL, {"av": act["acs5"], "gv": act["tiger_cb"]})
    out: list[_Row] = []
    for geo_id, estimate, moe in cur.fetchall():
        value = None if estimate is None else float(estimate)
        margin = None if moe is None else float(moe)
        suppressed, reason = _suppression(value, margin)
        out.append(_row(geo_id, "860", act["acs5"], "median_hh_income", value, "usd", moe=margin,
                        suppressed=suppressed, reason=reason, source="acs5",
                        inputs={"acs5": act["acs5"], "geo_level": "zcta"}))
    return out


def _growth(cur: psycopg2.extensions.cursor, act: dict[str, str], states: list[str]) -> list[_Row]:
    cur.execute(_GROWTH_SQL, {"av": act["acs5"], "pv": act["acs5_prior"], "gv": act["tiger_cb"], "states": states})
    out: list[_Row] = []
    for geo_id, now_, prior in cur.fetchall():
        value = M.population_growth_pct(None if now_ is None else float(now_), None if prior is None else float(prior))
        # No `moe`, and no `_suppression`: a difference of two ACS 5-year estimates has no
        # published combined margin, and running it through `_suppression` with `moe = None` would
        # return `(True, 'no_moe')` and grey out every growth polygon in the country (D-NS17).
        out.append(_row(geo_id, "160", act["acs5"], "population_growth_pct", value, "pct", derived=True,
                        source="acs5",
                        inputs={"acs5": act["acs5"], "acs5_prior": act["acs5_prior"], "geo_level": "place"}))
    return out


def _econ(cur: psycopg2.extensions.cursor, act: dict[str, str], states: list[str]) -> list[_Row]:
    cur.execute(_ECON_SQL, {"cv": act["cbp"], "gv": act["tiger_cb"], "states": states})
    out: list[_Row] = []
    for geo_id, payroll_k, establishments, flag in cur.fetchall():
        value = M.revenue_per_establishment(None if payroll_k is None else float(payroll_k),
                                            None if establishments is None else float(establishments))
        # CBP is a census of establishments, not a sample, so there is no margin to test — the one
        # thing that hides a county is the Census Bureau's own withholding/noise flag (§6).
        flagged = bool(flag)
        out.append(_row(geo_id, "050", act["cbp"], "revenue_per_establishment", value, "usd", derived=True,
                        suppressed=flagged, reason="source_flag" if flagged else None, source="cbp",
                        inputs={"cbp": act["cbp"], "geo_level": "county",
                                "note": "payroll per establishment, not revenue"}))
    return out


_BUILDERS = {"median_hh_income": _income, "population_growth_pct": _growth, "revenue_per_establishment": _econ}


def _rewrite(conn: psycopg2.extensions.connection, level: str, metric_key: str, vintage: str, rows: list[_Row]) -> int:
    """One transaction per (level, metric, vintage) — D-NS7. Production connections come from
    `app.db`'s pool with `autocommit=True`, so without this a failure between the DELETE and the
    INSERT would leave a layer half-written; `materialize_listing`'s own shape, restored in a
    `finally` so this is safe whatever the caller's autocommit state."""
    previous_autocommit = conn.autocommit
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(_DELETE, (level, metric_key, vintage))
            cur.executemany(_UPSERT, rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = previous_autocommit
    return len(rows)


def materialize_geo(conn: psycopg2.extensions.connection, redis: redis_sync.Redis) -> dict[str, int]:
    """Rebuild `geo_metric` for every geography in a `market_state` state, at the three ruled
    levels. Returns `{metric_key: rows_written}`.

    A layer whose dataset (or whose SECOND dataset) is not licence-cleared, or which has no active
    vintage, writes nothing and reports 0: the trigger would refuse the write anyway (D-NS3), and a
    nightly run must not fail because the VIN Foundation withdrew a licence."""
    reg = load_registry(conn)
    act = active(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT state_fips FROM market_state ORDER BY 1")
        states = [r[0] for r in cur.fetchall()]
    written: dict[str, int] = {}
    for metric_key, level, dataset, extra in LAYERS:
        needed = ("tiger_cb", dataset, *extra)
        if any(act.get(k) is None for k in needed) or not all(reg[k].cleared for k in (dataset, *extra)):
            written[metric_key] = 0
            continue
        with conn.cursor() as cur:
            rows = _BUILDERS[metric_key](cur, act, states)
        written[metric_key] = _rewrite(conn, level, metric_key, act[dataset], rows)
    redis.set(GEO_VERSION_KEY, time.time_ns())
    return written
```

In `app/tasks/census.py`, add immediately after `materialize_metrics` (which ends at `:371`):

```python
def materialize_geo_metrics() -> dict[str, object]:
    """Nightly job (D-NS9): rebuilds `geo_metric` for every geography in a `market_state` state,
    at the three ruled levels, from whatever vintages are currently active. Like
    `materialize_metrics` it does no Census I/O at all — only local aggregation over `geo_area`,
    `acs_measure` and `cbp_industry` — so it needs no `CENSUS_API_KEY`/`CENSUS_CONTACT_EMAIL` gate
    and no `_NotReady` handling, and a missing active vintage is left to fail the task visibly
    rather than being folded into a success-shaped result (A-C18 (3))."""
    from app.cache import sync_redis
    from app.census import geo_metric

    conn = _conn()
    try:
        return {"metrics": geo_metric.materialize_geo(conn, sync_redis())}
    finally:
        conn.close()
```

and register it beside its sibling at `:408`:

```python
materialize_geo_metrics_task = celery_app.task(name="census.materialize_geo_metrics")(materialize_geo_metrics)
```

In `app/tasks/celery_app.py`, add one entry inside the existing `.update({…})` at `:44-52`, after `materialize-nightly`:

```python
    # D-NS9: the polygon table, half an hour after the listing table. The two are independent —
    # neither reads the other's rows — and the stagger keeps two heavy read-only passes over
    # acs_measure off one database at the same moment. Never on the request path (spec §10).
    "geo-metric-nightly": {"task": "census.materialize_geo_metrics", "schedule": crontab(minute=30, hour=3)},
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
poetry run pytest tests/census/test_geo_metric.py tests/census/test_tasks.py tests/test_celery.py tests/test_tasks_never_activates_vintage.py -q -W error
```

Expected: PASS. The AST guard in `test_tasks_never_activates_vintage.py` stays green: `app/tasks/census.py` imports `app.census.geo_metric`, which imports `app.census.vintage.active` — the guard forbids `app/tasks/**` importing `app.census.vintage`, and it does so **indirectly**, exactly as it already does through `app.census.materialize`. **If the guard goes red, STOP and read it**: it may walk imports transitively, in which case `geo_metric.py` needs the `active_geo_vintage`-style wrapper `materialize.py` already carries.

- [ ] **Step 5: Run the backend gate**

```bash
poetry run ruff check app tests scripts && poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e --cov-fail-under=100
```

Expected: PASS at 100 % lines and branches. Every branch has a case: the `any(act.get(k) is None …)` arm (`test_a_dataset_with_no_active_vintage_writes_nothing`), the `not all(reg[k].cleared …)` arm on both the stamped dataset and the extra one (`…licence_is_not_cleared…`, `…gated_on_acs5_prior…`), `_rewrite`'s except arm (`…rolls_back…`), the `estimate is None` / `moe is None` arms (add a ZCTA row with a null estimate to `world` if the report says otherwise), and `flagged` both ways.

- [ ] **Step 6: Commit**

```bash
git add app/census/geo_metric.py tests/census/test_geo_metric.py \
  app/tasks/census.py app/tasks/celery_app.py tests/census/test_tasks.py tests/test_celery.py
git commit -m "feat(census): materialize_geo — the only writer of geo_metric, nightly

Three metrics at D-C35's three levels from datasets already loaded, scoped to the six
market_state states, per-triple delete-and-rewrite in one transaction each so a failure
leaves the prior vintage standing. _suppression is IMPORTED from materialize (a test
asserts the function identity) and applied to income alone: growth and econ have no
published margin and would be greyed everywhere if fed through it. Growth is gated on
acs5_prior as well as the acs5 key it is stamped with — the hole A-C23 (1) closed for
vets_per_10k_households. Beat entry at 03:30 UTC, never on the request path.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```


---

## Task 9: `GET /api/markets/{cbsa}/boundaries`, `/api/layers`'s `shading`, and the contract document

One route, on the existing router, guarded by the existing module constant, inside the existing `market:gate:v` cache key — D-C37's "one route inside the existing cache key honours both", where "both" is §10's CDN row and §11's "the layer disappears within one minute", which a value-carrying tile cannot satisfy at once.

`tests/api/test_contract_doc.py::test_contract_doc_names_every_market_and_admin_route` walks every mounted path, so the document changes in the SAME commit or the backend gate is red. That is the intended forcing function.

**Re-basing states: NONE. The thirteen frozen hashes must not move.**

**Files:**
- Modify: `app/api/market.py:65-83` (imports), `:89-119` (constants and `LAYERS`), `:181-199` (`layers`), and a new handler after `communities` at `:270`
- Modify: `docs/integrations/market-data-api.md:15-46` (the routes table), a new section after the `/api/layers` one at `:89`, and the `Copy rules` list at `:343-354`
- Modify: `tests/api/test_contract_doc.py`
- Create: `tests/census/test_boundaries.py`
- Test: `tests/census/test_boundaries.py`, `tests/api/test_contract_doc.py`

**Interfaces:**
- Consumes: `geo_metric` (Task 5), `app.census.bands.band_ambiguous` (Task 7), `app.census.geo_metric.GEO_VERSION_KEY` (Task 8), `app.census.gate.version`, `app.census.serve._active/_registry/_extra_cleared`, `app.api.market._error/_cleared/_layer_state/REQUIRE_MARKET_READ`.
- Produces, for Task 10's adapter:
  ```
  GET /api/markets/{cbsa}/boundaries?layer=income|growth|econ[&bbox=minLng,minLat,maxLng,maxLat]
  ```
  `200` `application/geo+json`, a `FeatureCollection` with foreign members `cbsa_geoid`, `layer`, `metric_key`, `summary_level`, `geo_label`, `unit`, `state`, `boundary_vintage`, `value_vintage`, `source_dataset`, `attribution` (array), `values_without_geometry` (integer), and `features[]` whose `properties` are exactly `{geo_id, name, value, moe, suppressed, suppress_reason, band_ambiguous}`. Headers: `x-cache: hit|miss`, `Vary: Accept-Encoding`, and `Content-Encoding: gzip` when the request accepted it. Refusals are `{"error": {"code", "message"}}` with `code` in `BAD_LAYER` / `BAD_BBOX` / `BBOX_TOO_LARGE` / `AREA_TOO_LARGE` (422) and `NOT_FOUND` (404).
  `GET /api/layers` gains `"shading": {"summary_level", "label"}` on the three fill layers and `"shading": null` on the other six.
  ```python
  # app/api/market.py
  MAX_BBOX_DEG: float = 4.0
  MAX_FEATURES: int = 4000
  MAX_BODY_BYTES: int = 2_000_000
  BOUNDARY_TTL: int = 86400
  SHADING: dict[str, dict[str, str]]
  BOUNDARY_METRIC: dict[str, tuple[str, str]]   # layer -> (metric_key, stamped source_dataset)
  ```

- [ ] **Step 1: Write the failing test**

Create `tests/census/test_boundaries.py`. It sits beside `tests/census/test_market_api.py` (the market API's tests live here, not in `tests/api/` — the spec's `tests/api/test_boundaries.py` names a directory this route's siblings are not in) and reuses that file's `client`/`H` fixtures by importing them.

```python
"""GET /api/markets/{cbsa}/boundaries — the member-gated boundary layer (D-NS10 through D-NS18).

Reuses tests/census/test_market_api.py's `client` and `H` fixtures: one scratch database per test,
a real `buyer` session presented as a literal Cookie header (Task I9a)."""
import gzip
import json

import fakeredis
import pytest

from app.api import market
from app.cache import sync_redis
from app.census import gate, geo_metric
from app.config import settings
from tests.api.conftest import ORIGIN, auth_headers
from tests.census.test_market_api import H, client  # noqa: F401 -- the fixtures, by name

AUSTIN = "POLYGON((-98 30,-97 30,-97 31,-98 31,-98 30))"
INSIDE = "POLYGON((-97.8 30.2,-97.7 30.2,-97.7 30.3,-97.8 30.3,-97.8 30.2))"


@pytest.fixture
def seeded(conn):
    with conn.cursor() as cur:
        for key, vintage in (("tiger_cb", "2023"), ("acs5", "2019–2023"), ("acs5_prior", "2014–2018"), ("cbp", "2022")):
            cur.execute("INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s,%s,now(),'test')", (key, vintage))
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) VALUES "
            "('12420','310','2023','Austin-Round Rock-San Marcos, TX Metro Area', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.5,30.5,4269))",
            (AUSTIN,),
        )
        for geo_id, name in (("78704", "ZCTA5 78704"), ("78745", "ZCTA5 78745")):
            cur.execute(
                "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) VALUES "
                "(%s,'860','2023',%s, ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.75,30.25,4269))",
                (geo_id, name, INSIDE),
            )
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, suppressed, suppress_reason, source_dataset, computed_at) VALUES "
            "('78704','860','2019–2023','median_hh_income',92150,'usd',6420,false,NULL,'acs5',now()), "
            "('78745','860','2019–2023','median_hh_income',41000,'usd',40000,true,'high_moe','acs5',now())"
        )
    return conn


async def _body(client, H, query: str = "?layer=income"):
    r = await client.get(f"/api/markets/12420/boundaries{query}", headers=H)
    return r, (json.loads(r.content) if r.status_code == 200 else r.json())


async def test_the_route_is_guarded_by_the_same_dependency_object_as_its_siblings(client, seeded, member, monkeypatch) -> None:
    path = "/api/markets/12420/boundaries?layer=income"
    assert (await client.get(path)).status_code == 401
    _aid, cookies, _csrf = member(("buyer",))
    assert (await client.get(path, headers=auth_headers(cookies))).status_code == 200
    monkeypatch.setattr(settings, "market_data_public", True)
    assert (await client.get(path)).status_code == 200
    # By IDENTITY, the way tests/auth/test_permissions.py resolves a guard: a fresh
    # `require("market.read")` per route reads as unguarded (market.py's correction 4).
    route = next(r for r in market.router.routes if getattr(r, "path", "") == "/api/markets/{cbsa}/boundaries")
    assert any(d.dependency is market.REQUIRE_MARKET_READ.dependency for d in route.dependant.dependencies)


async def test_a_feature_carries_the_value_the_margin_and_the_suppression_verdict(client, seeded, H) -> None:
    r, body = await _body(client, H)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/geo+json")
    assert body["type"] == "FeatureCollection"
    assert (body["cbsa_geoid"], body["layer"], body["metric_key"]) == ("12420", "income", "median_hh_income")
    assert (body["summary_level"], body["geo_label"], body["unit"]) == ("860", "ZIP Code Tabulation Area", "usd")
    assert (body["state"], body["boundary_vintage"], body["value_vintage"], body["source_dataset"]) == ("enabled", "2023", "2019–2023", "acs5")
    assert body["attribution"][0] == "Boundaries: U.S. Census Bureau, TIGER/Line Cartographic Boundary Files 2023"
    assert body["attribution"][1].startswith("Source: U.S. Census Bureau, American Community Survey")
    assert body["values_without_geometry"] == 0
    by = {f["id"]: f for f in body["features"]}
    assert sorted(by) == ["78704", "78745"]
    assert by["78704"]["properties"] == {
        "geo_id": "78704", "name": "ZCTA5 78704", "value": 92150.0, "moe": 6420.0,
        "suppressed": False, "suppress_reason": None, "band_ambiguous": False,
    }
    assert by["78745"]["properties"]["suppressed"] is True and by["78745"]["properties"]["suppress_reason"] == "high_moe"
    # 4326, not geo_area's own 4269.
    assert by["78704"]["geometry"]["type"] in ("Polygon", "MultiPolygon")


async def test_a_polygon_with_no_row_at_all_is_returned_with_a_null_value_and_is_never_omitted(client, seeded, conn, H) -> None:
    """D-NS16: omitting it leaves a hole, and a hole on a choropleth reads as a boundary — a park,
    a lake, or the edge of the market, none of which is what happened. Global Constraint (c): the
    sentinel is `value: null` with `suppressed: false`, which is what `_suppression(None, None)`
    produces, so a client guard on `suppressed` alone would paint it as measured."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM geo_metric WHERE geo_id = '78745'")
    _r, body = await _body(client, H)
    missing = next(f for f in body["features"] if f["id"] == "78745")
    assert missing["properties"]["value"] is None
    assert missing["properties"]["suppressed"] is False
    assert missing["properties"]["suppress_reason"] is None
    assert len(body["features"]) == 2, "a polygon with no value was dropped"


async def test_a_value_with_no_geometry_is_dropped_and_counted(client, seeded, conn, H) -> None:
    """§7, the other direction: the writer never invents a shape, and the endpoint never silently
    loses a row. A non-zero counter on a metro that has previously reported zero is how a boundary
    vintage that moved out from under the values announces itself."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, source_dataset, computed_at) "
            "VALUES ('99999','860','2019–2023','median_hh_income',50000,'usd','acs5',now())"
        )
    _r, body = await _body(client, H)
    assert body["values_without_geometry"] == 1
    assert "99999" not in [f["id"] for f in body["features"]]


async def test_band_ambiguity_is_computed_server_side_from_the_designs_own_stops(client, seeded, conn, H) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE geo_metric SET moe = 9000 WHERE geo_id = '78704'")
    _r, body = await _body(client, H)
    assert next(f for f in body["features"] if f["id"] == "78704")["properties"]["band_ambiguous"] is True


@pytest.mark.parametrize("query,code", [
    ("?layer=pets", "BAD_LAYER"),
    ("?layer=nonsense", "BAD_LAYER"),
    ("", "BAD_LAYER"),
    ("?layer=income&bbox=not,a,box,at-all", "BAD_BBOX"),
    ("?layer=income&bbox=-98,30,-97", "BAD_BBOX"),
    ("?layer=income&bbox=-110,25,-90,35", "BBOX_TOO_LARGE"),
])
async def test_every_refusal_uses_decision_A5s_envelope_and_names_what_it_wants(client, seeded, H, query, code) -> None:
    r = await client.get(f"/api/markets/12420/boundaries{query}", headers=H)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == code
    assert "detail" not in r.json()
    if code == "BAD_LAYER":
        for name in ("income", "growth", "econ"):
            assert name in r.json()["error"]["message"]
    if code == "BBOX_TOO_LARGE":
        assert "4.0" in r.json()["error"]["message"]


async def test_a_bbox_at_the_cap_is_served_and_one_over_it_is_refused(client, seeded, H) -> None:
    assert (await client.get("/api/markets/12420/boundaries?layer=income&bbox=-98,30,-94,34", headers=H)).status_code == 200
    over = await client.get("/api/markets/12420/boundaries?layer=income&bbox=-98,30,-93.99,34", headers=H)
    assert over.status_code == 422 and over.json()["error"]["code"] == "BBOX_TOO_LARGE"


async def test_too_many_features_is_refused_rather_than_served_slowly(client, seeded, H, monkeypatch) -> None:
    monkeypatch.setattr(market, "MAX_FEATURES", 1)
    r = await client.get("/api/markets/12420/boundaries?layer=income", headers=H)
    assert r.status_code == 422 and r.json()["error"]["code"] == "AREA_TOO_LARGE"
    assert "1" in r.json()["error"]["message"]


async def test_too_large_a_body_is_refused_under_the_same_code(client, seeded, H, monkeypatch) -> None:
    """A whole-Texas box measured 6,884 tracts and 9.2 MB, and there was no bound anywhere in
    `app/` before this route (R6)."""
    monkeypatch.setattr(market, "MAX_BODY_BYTES", 10)
    r = await client.get("/api/markets/12420/boundaries?layer=income", headers=H)
    assert r.status_code == 422 and r.json()["error"]["code"] == "AREA_TOO_LARGE"


async def test_an_unknown_metro_is_a_404(client, seeded, H) -> None:
    r = await client.get("/api/markets/99999/boundaries?layer=income", headers=H)
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


async def test_a_layer_whose_licence_is_withdrawn_answers_200_with_no_features(client, seeded, conn, H) -> None:
    """Never a 403: `/api/layers` already lists a blocked layer so the UI can render it as
    unavailable, and a map that 403s cannot draw that state."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='acs5'")
    gate.invalidate(sync_redis(), "acs5")
    r, body = await _body(client, H)
    assert r.status_code == 200 and body["state"] == "disabled" and body["features"] == []
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='blocked', notes='Counsel declined the terms.' WHERE dataset_key='acs5'")
    gate.invalidate(sync_redis(), "acs5")
    _r2, blocked = await _body(client, H)
    assert blocked["state"] == "blocked" and blocked["blocked_reason"] == "Counsel declined the terms."


async def test_growth_is_gated_on_acs5_prior_as_well_as_the_key_its_rows_are_stamped_with(client, seeded, conn, H) -> None:
    """R3's specific hole, at the read path this time."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='acs5_prior'")
    gate.invalidate(sync_redis(), "acs5_prior")
    _r, body = await _body(client, H, "?layer=growth")
    assert body["state"] == "disabled" and body["features"] == []


async def test_the_cache_key_carries_the_gate_version_and_the_geo_version(client, seeded, H) -> None:
    """D-NS13 plus the geo version (this plan's own addition): a licence decision makes every
    cached body unreachable in the same instant, and so does a nightly rewrite that changes values
    without moving a vintage."""
    first = await client.get("/api/markets/12420/boundaries?layer=income", headers=H)
    assert first.headers["x-cache"] == "miss"
    assert (await client.get("/api/markets/12420/boundaries?layer=income", headers=H)).headers["x-cache"] == "hit"
    gate.invalidate(sync_redis(), "acs5")
    assert (await client.get("/api/markets/12420/boundaries?layer=income", headers=H)).headers["x-cache"] == "miss"
    sync_redis().set(geo_metric.GEO_VERSION_KEY, 12345)
    assert (await client.get("/api/markets/12420/boundaries?layer=income", headers=H)).headers["x-cache"] == "miss"


async def test_gzip_is_applied_in_the_handler_and_the_identity_branch_serves_the_same_json(client, seeded, H) -> None:
    """D-NS14: no global GZipMiddleware — that would change every response in the application,
    including the ones carrying x-cache and the security headers, which is far wider than the ask.
    The compressed bytes are what Redis holds, so a hit costs no second compression."""
    zipped = await client.get("/api/markets/12420/boundaries?layer=income", headers={**H, "Accept-Encoding": "gzip"})
    assert zipped.headers["content-encoding"] == "gzip"
    assert zipped.headers["vary"] == "Accept-Encoding"
    plain = await client.get("/api/markets/12420/boundaries?layer=income", headers={**H, "Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers
    # httpx transparently decodes gzip, so both bodies read the same either way.
    assert json.loads(plain.content) == json.loads(zipped.content)


def test_no_sql_string_in_this_module_simplifies_geometry_on_the_request_path() -> None:
    """R7. ST_SimplifyPreserveTopology measured five to EIGHT times the cost of the query itself,
    which makes it the dominant term of every request for a saving the response does not need.
    Simplification belongs at write time or not at all: if a future geography needs it, the
    simplified geometry is materialised into its own column by the nightly job, once per vintage."""
    from pathlib import Path

    source = Path(market.__file__).read_text(encoding="utf-8")
    assert "ST_Simplify" not in source


async def test_the_endpoint_and_community_rows_agree_on_suppression(client, seeded, conn, H) -> None:
    """D-NS18/R2: "$72,400" in the docked panel over a grey polygon is the failure this stops.
    The parity case runs at the PLACE level, because `serve.community_rows` reads `market_metric`
    at its hard-coded `place` band and only `growth` shades at place — so the income parity is
    asserted against a place-level `geo_metric` row written for the test, and the ZCTA path is
    covered by the shared-function assertion in tests/census/test_geo_metric.py."""
    from app.census import serve
    from tests.census.listing_fixtures import make_listing

    lid = make_listing(conn, city="Austin")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO practice_location (listing_id, place_geoid, cbsa_geoid, geo_precision) VALUES (%s,'4805000','12420','rooftop')",
            (lid,),
        )
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid) VALUES "
            "('4805000','160','2023','Austin','48', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.75,30.25,4269))",
            (INSIDE,),
        )
        for suppressed, reason in ((False, None), (True, "high_moe")):
            cur.execute("DELETE FROM market_metric WHERE listing_id = %s", (lid,))
            cur.execute("DELETE FROM geo_metric WHERE geo_id = '4805000'")
            cur.execute(
                "INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, moe, suppressed, suppress_reason, source_dataset, computed_at) "
                "VALUES (%s,'place','median_hh_income','2019–2023',92150,'usd',6420,%s,%s,'acs5',now())",
                (lid, suppressed, reason),
            )
            cur.execute(
                "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, suppressed, suppress_reason, source_dataset, computed_at) "
                "VALUES ('4805000','160','2019–2023','median_hh_income',92150,'usd',6420,%s,%s,'acs5',now())",
                (suppressed, reason),
            )
            reg = {r["dataset_key"]: dict(r) for r in _registry_sync(conn)}
            rows = serve.community_rows(conn, [str(lid)], active={"acs5": "2019–2023", "acs5_prior": "2014–2018"}, registry=reg)
            panel_hides = rows[str(lid)]["income"] is None
            assert panel_hides is suppressed, "the panel and the table disagree on suppression"


def _registry_sync(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_key, attribution_text, vintage, license_status, notes FROM dataset_registry")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


async def test_layers_gains_a_shading_member_on_the_three_fills_and_null_on_the_other_six(client, seeded, H) -> None:
    """D-NS15: a NEW member, never a change to `geo_level`. `income`'s `geo_level` is
    "place|catchment" and describes the PANEL's geography; the docked panel and the map answer
    different questions about the same layer, and collapsing them is exactly the "silently promote
    a coarse figure into a fine slot" failure D-C35 forbids."""
    layers = {l["key"]: l for l in (await client.get("/api/layers", headers=H)).json()}
    assert layers["income"]["shading"] == {"summary_level": "860", "label": "ZIP Code Tabulation Area"}
    assert layers["growth"]["shading"] == {"summary_level": "160", "label": "Place (city/town)"}
    assert layers["econ"]["shading"] == {"summary_level": "050", "label": "County"}
    for key in ("pets", "households", "competition", "practices", "drive_10", "drive_20"):
        assert layers[key]["shading"] is None, key
    assert layers["income"]["geo_level"] == "place|catchment", "the panel's geography must not move"
```

Append to `tests/api/test_contract_doc.py`:

```python
def test_contract_doc_states_the_boundary_caps_and_geographies_the_code_enforces() -> None:
    """A hand-maintained number in a document is a defect waiting to happen: every figure below is
    read off `app.api.market` rather than typed here, so the document cannot drift from the caps
    the route really applies (plan Global Constraint (i))."""
    from app.api import market

    text = DOC.read_text(encoding="utf-8")
    assert f"`MAX_BBOX_DEG = {market.MAX_BBOX_DEG}`" in text
    assert f"`MAX_FEATURES = {market.MAX_FEATURES}`" in text
    assert f"`MAX_BODY_BYTES = {market.MAX_BODY_BYTES:_}`" in text
    assert f"`BOUNDARY_TTL = {market.BOUNDARY_TTL}`" in text
    for layer, shading in market.SHADING.items():
        assert f'"{layer}"' in text or f"`{layer}`" in text, layer
        assert f'"summary_level": "{shading["summary_level"]}"' in text, layer
        assert shading["label"] in text, layer
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
poetry run pytest tests/census/test_boundaries.py tests/api/test_contract_doc.py -q -W error
```

Expected: every boundary case FAILS with `404` (the route is not mounted, so `not_found_router` answers), `test_layers_gains_a_shading_member…` FAILS with `KeyError: 'shading'`, and the contract-doc case FAILS with `AttributeError: module 'app.api.market' has no attribute 'MAX_BBOX_DEG'`.

- [ ] **Step 3: Write the minimal implementation**

In `app/api/market.py`, extend the imports:

```python
import gzip
import json
import logging
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from app.auth.deps import require
from app.cache import sync_redis
from app.census import gate
from app.census import metrics as M
from app.census.bands import band_ambiguous
from app.census.geo_metric import GEO_VERSION_KEY
from app.census.serve import _active, _extra_cleared, _registry
from app.db import engine
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)
```

add the constants after `DEFAULT_BLOCKED_REASON` at `:92`:

```python
BOUNDARY_TTL = 86400
# D-NS12. The caps are chosen against the GEOGRAPHY, not against a load test: the Austin metro's
# own envelope is roughly 1.0 deg x 0.9 deg, and 4 deg on a side covers any single CBSA in the six
# states with room to spare while refusing a state. MAX_FEATURES sits above the largest plausible
# single-metro ZCTA count and below the 6,884 tracts a whole-Texas box returns (9.2 MB, and there
# was no bound anywhere in app/ before this route).
MAX_BBOX_DEG = 4.0
MAX_FEATURES = 4000
MAX_BODY_BYTES = 2_000_000

# D-C35's three geographies, and the label the legend prints. A NEW member on /api/layers rather
# than a change to `geo_level`: `income`'s geo_level is "place|catchment" and describes the
# PANEL's geography — the docked panel and the map answer different questions about the same
# layer (D-NS15).
SHADING: dict[str, dict[str, str]] = {
    "income": {"summary_level": "860", "label": "ZIP Code Tabulation Area"},
    "growth": {"summary_level": "160", "label": "Place (city/town)"},
    "econ": {"summary_level": "050", "label": "County"},
}
# layer -> (metric_key, the dataset its geo_metric rows are STAMPED with, whose active vintage is
# therefore the value vintage).
BOUNDARY_METRIC: dict[str, tuple[str, str]] = {
    "income": ("median_hh_income", "acs5"),
    "growth": ("population_growth_pct", "acs5"),
    "econ": ("revenue_per_establishment", "cbp"),
}

# D-NS11. Three things about it are deliberate. `ST_Transform(g.geom, 4326)` is required, not
# decorative: geo_area.geom is geometry(MultiPolygon, 4269) and GeoJSON is WGS84. The `6` is
# measured to be a NO-OP -- cb_500k already carries six or fewer decimals -- and is kept as an
# explicit ceiling. And the envelope is transformed INTO 4269 rather than the geometry column out
# of it, so the geo_area_geom_gix GiST index is usable on the predicate (an Austin z11 tract
# viewport: 49.8 ms).
_BOUNDARY_SQL = """
SELECT g.geo_id, g.name, m.value_num, m.moe, m.suppressed, m.suppress_reason,
       ST_AsGeoJSON(ST_Transform(g.geom, 4326), 6) AS geometry
  FROM geo_area g
  LEFT JOIN geo_metric m
    ON m.geo_id = g.geo_id AND m.summary_level = g.summary_level
   AND m.metric_key = :metric AND m.vintage = :value_vintage
 WHERE g.summary_level = :level AND g.vintage = :geo_vintage
   AND ST_Intersects(g.geom, ST_Transform(ST_MakeEnvelope(:w, :s, :e, :n, 4326), 4269))
 ORDER BY g.geo_id
"""

# §7, the other direction: a value whose geography the boundary vintage no longer carries. The
# writer never invents a shape and the endpoint never silently loses a row.
_ORPHAN_SQL = """
SELECT count(*) FROM geo_metric m
 WHERE m.summary_level = :level AND m.metric_key = :metric AND m.vintage = :value_vintage
   AND NOT EXISTS (SELECT 1 FROM geo_area g WHERE g.geo_id = m.geo_id AND g.summary_level = :level AND g.vintage = :geo_vintage)
"""
```

give `_layer_state`'s companion a bbox parser, after `_resolve_band` at `:140`:

```python
def _parse_bbox(raw: str) -> tuple[float, float, float, float] | None:
    """`minLng,minLat,maxLng,maxLat`, or `None` when it is not four numbers in that order. Parsed
    by hand rather than through `Query(ge=…)` so a bad value gets decision A5's envelope, which is
    the shape `_resolve_band` already uses for BAD_BAND."""
    parts = raw.split(",")
    if len(parts) != 4:
        return None
    try:
        w, s, e, n = (float(p) for p in parts)
    except ValueError:
        return None
    if e <= w or n <= s:
        return None
    return w, s, e, n
```

and add the handler immediately after `communities` (`:270`):

```python
@router.get("/markets/{cbsa}/boundaries", dependencies=[Depends(REQUIRE_MARKET_READ)])
async def boundaries(cbsa: str, request: Request, layer: str | None = Query(None), bbox: str | None = Query(None)) -> Response:
    """Real Census boundary polygons for one metro and one shaded layer (D-C34–D-C37).

    Served as a member-gated ENDPOINT rather than CDN tiles: `MARKET_DATA_PUBLIC` is false so
    tiles would have to be member-gated anyway, and spec §10's "30 days, immutable" CDN row
    directly contradicts §11's "the layer disappears within one minute" the moment a tile carries
    values rather than only geometry. One route inside the existing `market:gate:v` cache key
    honours both."""
    if layer not in SHADING:
        return _error("BAD_LAYER", "layer must be one of ('income', 'growth', 'econ')", 422)
    box: tuple[float, float, float, float] | None = None
    if bbox is not None:
        box = _parse_bbox(bbox)
        if box is None:
            return _error("BAD_BBOX", "bbox must be minLng,minLat,maxLng,maxLat with maxima above minima", 422)
        if box[2] - box[0] > MAX_BBOX_DEG or box[3] - box[1] > MAX_BBOX_DEG:
            return _error("BBOX_TOO_LARGE", f"bbox spans {box[2] - box[0]:.2f} x {box[3] - box[1]:.2f} degrees; the cap is {MAX_BBOX_DEG} on either axis", 422)

    metric_key, source = BOUNDARY_METRIC[layer]
    r = sync_redis()
    geo_version = cast("bytes | str | None", r.get(GEO_VERSION_KEY))
    async with engine().connect() as conn:
        act, reg = await _active(conn), await _registry(conn)
        geo_vintage, value_vintage = act.get("tiger_cb"), act.get(source)
        key = (f"boundaries:{cbsa}:{layer}:{geo_vintage}:{value_vintage}:g{gate.version(r)}"
               f":m{int(geo_version) if geo_version else 0}:b{bbox or 'metro'}")
        cached = cast("bytes | None", r.get(key))
        if cached is not None:
            return _geojson(cached, request, "hit")
        metro = (await conn.execute(text(
            "SELECT ST_XMin(geom), ST_YMin(geom), ST_XMax(geom), ST_YMax(geom) FROM geo_area "
            "WHERE geo_id = :cbsa AND summary_level = '310' AND vintage = :gv"), {"cbsa": cbsa, "gv": geo_vintage})).first()
        if metro is None:
            return _error("NOT_FOUND", "No such metro.", 404)
        if box is None:
            box = (float(metro[0]), float(metro[1]), float(metro[2]), float(metro[3]))
        entry = next(l for l in LAYERS if l["key"] == layer)
        state, blocked_reason = _layer_state(reg, entry["dataset_key"])
        if state == "enabled" and not (_cleared(reg, source) and _extra_cleared(reg, metric_key, source)):
            state = "disabled"
        rows: list[RowMapping] = []
        orphans = 0
        if state == "enabled":
            params = {"metric": metric_key, "value_vintage": value_vintage, "level": SHADING[layer]["summary_level"],
                      "geo_vintage": geo_vintage, "w": box[0], "s": box[1], "e": box[2], "n": box[3]}
            rows = list((await conn.execute(text(_BOUNDARY_SQL), params)).mappings().all())
            orphans = int((await conn.execute(text(_ORPHAN_SQL), params)).scalar_one())
    if len(rows) > MAX_FEATURES:
        return _error("AREA_TOO_LARGE", f"{len(rows)} features in this area; the cap is {MAX_FEATURES}. Zoom in or pass a smaller bbox.", 422)
    if orphans:
        # A non-zero count on a metro that has previously reported zero is how a boundary vintage
        # that has moved out from under the values announces itself (R4).
        log.warning("boundaries: %d %s values at level %s have no %s geometry", orphans, value_vintage, SHADING[layer]["summary_level"], geo_vintage)

    used = sorted({source} | ({"acs5_prior"} if metric_key == "population_growth_pct" else set()))
    body: dict[str, Any] = {
        "type": "FeatureCollection", "cbsa_geoid": cbsa, "layer": layer, "metric_key": metric_key,
        "summary_level": SHADING[layer]["summary_level"], "geo_label": SHADING[layer]["label"],
        "unit": "usd" if layer in ("income", "econ") else "pct", "state": state,
        "boundary_vintage": geo_vintage, "value_vintage": value_vintage, "source_dataset": source,
        # Read from dataset_registry, never composed here: attribution is legally load-bearing and
        # a terms change must be one UPDATE rather than a redeploy. Boundaries first — the map
        # carries the geometry's attribution beside the values' (Census spec §2b).
        "attribution": [reg["tiger_cb"]["attribution_text"]] + [reg[k]["attribution_text"] for k in used],
        "values_without_geometry": orphans,
        "features": [_boundary_feature(row, layer) for row in rows],
    }
    if blocked_reason is not None:
        body["blocked_reason"] = blocked_reason
    raw = json.dumps(body).encode("utf-8")
    if len(raw) > MAX_BODY_BYTES:
        return _error("AREA_TOO_LARGE", f"{len(raw)} bytes in this area; the cap is {MAX_BODY_BYTES}. Zoom in or pass a smaller bbox.", 422)
    packed = gzip.compress(raw)
    r.set(key, packed, ex=BOUNDARY_TTL)
    return _geojson(packed, request, "miss")


def _boundary_feature(row: RowMapping, layer: str) -> dict[str, Any]:
    """One polygon. `value` is `None` both when the geography has no row at all and when its row
    is suppressed, and the two are told apart by `suppressed`/`suppress_reason` — the client draws
    both in the no-data class but says something different about each (§6)."""
    value = None if row["value_num"] is None else float(row["value_num"])
    moe = None if row["moe"] is None else float(row["moe"])
    return {
        "type": "Feature", "id": row["geo_id"],
        "properties": {
            "geo_id": row["geo_id"], "name": row["name"],
            "value": None if row["suppressed"] else value, "moe": moe,
            "suppressed": bool(row["suppressed"]), "suppress_reason": row["suppress_reason"],
            # Only `income` can be band-ambiguous: growth and econ carry no published margin
            # (D-NS17), so `band_ambiguous` is False for them by construction, not by omission.
            "band_ambiguous": layer == "income" and band_ambiguous(value, moe),
        },
        "geometry": json.loads(row["geometry"]),
    }


def _geojson(packed: bytes, request: Request, cache: str) -> Response:
    """D-NS14: gzip in the HANDLER, and the COMPRESSED bytes are what Redis holds, so a cache hit
    costs no second compression. No global `GZipMiddleware`: that would change every response in
    the application, including the ones carrying `x-cache` and the four security headers
    `SecurityHeadersMiddleware` puts on EVERY answer, which is far wider than the ask."""
    headers = {"x-cache": cache, "Vary": "Accept-Encoding"}
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(packed, media_type="application/geo+json", headers={**headers, "Content-Encoding": "gzip"})
    return Response(gzip.decompress(packed), media_type="application/geo+json", headers=headers)
```

and give `/api/layers` its new member — inside the `entry` dict at `:190-195`, after `"geo_level"`:

```python
            "shading": SHADING.get(layer["key"]),
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
poetry run pytest tests/census/test_boundaries.py -q -W error
```

Expected: PASS. `tests/api/test_contract_doc.py` still FAILS — the document has not been written.

- [ ] **Step 5: Document the route**

In `docs/integrations/market-data-api.md`, add one row to the Routes table at `:15-46`:

```markdown
| GET | `/api/markets/{cbsa}/boundaries` | `market.read` |
```

and add a section immediately after the `## GET /api/layers` one, in that section's own shape:

````markdown
## `GET /api/markets/{cbsa}/boundaries?layer=income|growth|econ[&bbox=minLng,minLat,maxLng,maxLat]`

The shaded map layer: real Census boundary polygons joined to `geo_metric`, one geography per
layer (John's rulings D-C34–D-C37, 2026-09-10). `income` draws ZIP Code Tabulation Areas
(`"summary_level": "860"`), `growth` draws Place (city/town) (`"summary_level": "160"`), `econ`
draws County (`"summary_level": "050"`). **No layer is ever painted at a geography finer than its
figure is honest at** — spec §6's standing rule, "Never silently promote a county figure into a
tract-labeled slot", applied to the map. The three graduated-symbol layers (`pets`, `households`,
`competition`) are not shaded and are not served here.

One GeoJSON `FeatureCollection` with foreign members (RFC 7946 permits them; `L.geoJSON` ignores
what it does not know):

```json
{
  "type": "FeatureCollection",
  "cbsa_geoid": "12420", "layer": "income", "metric_key": "median_hh_income",
  "summary_level": "860", "geo_label": "ZIP Code Tabulation Area", "unit": "usd",
  "state": "enabled", "boundary_vintage": "2023", "value_vintage": "2019–2023",
  "source_dataset": "acs5",
  "attribution": ["Boundaries: U.S. Census Bureau, TIGER/Line Cartographic Boundary Files 2023",
                  "Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023"],
  "values_without_geometry": 0,
  "features": [
    { "type": "Feature", "id": "78704",
      "properties": { "geo_id": "78704", "name": "ZCTA5 78704",
                      "value": 92150, "moe": 6420,
                      "suppressed": false, "suppress_reason": null, "band_ambiguous": false },
      "geometry": { "type": "MultiPolygon", "coordinates": [] } }
  ]
}
```

**Two vintages, named separately.** `tiger_cb` is a bare year and `acs5` is an en-dashed range;
they advance on different calendars and are not interchangeable. A geography present in one and
not the other is handled in both directions: **geometry with no value** is returned with
`"value": null, "suppressed": false, "suppress_reason": null` and drawn in the no-data class —
never omitted, because a hole in a choropleth reads as a boundary; **a value with no geometry** is
dropped from `features` (there is nothing to draw) and counted in `values_without_geometry`, which
is logged on every cache miss. A non-zero count on a metro that has previously reported zero means
a boundary vintage has moved out from under the values.

**`value` is `null` in two different cases and the client must tell them apart.** A geography with
no row at all is `value: null, suppressed: false`; a suppressed one is `value: null, suppressed:
true` with a `suppress_reason` of `no_moe`, `high_moe`, `input_suppressed` or `source_flag`. Both
are drawn grey; they say different things. `band_ambiguous: true` means the margin of error spans
a legend stop — that polygon keeps its value and takes a caveat, and is **never** greyed.

**Bounds.** `bbox` is optional and defaults to the metro's own envelope. `MAX_BBOX_DEG = 4.0`
degrees on either axis, `MAX_FEATURES = 4000`, `MAX_BODY_BYTES = 2_000_000` uncompressed; a breach
is `422` with `{"error": {"code": "BBOX_TOO_LARGE" | "AREA_TOO_LARGE", "message": …}}`. A bbox
that is not four ordered numbers is `422 BAD_BBOX`; a layer that is not one of the three is
`422 BAD_LAYER`; an unknown metro is `404 NOT_FOUND`.

**Licence.** A layer whose dataset is not `cleared` answers `200` with `"features": []` and
`"state": "disabled"` or `"blocked"` (+ `blocked_reason`) — never a `403`, because `/api/layers`
already lists a blocked layer so the UI can render it as unavailable, and a map that 403s cannot
draw that state. `growth` is additionally gated on `acs5_prior`, the second dataset its rows
cannot be stamped with (see the licence-gates table below). The response is cached for
`BOUNDARY_TTL = 86400` seconds under a key carrying `gate.version()`, so a licence decision makes
every cached body unreachable in the same instant (§11's one-minute ceiling), and the nightly
writer's own version counter, so a rewrite that changes values without moving a vintage does too.

**Compression is applied by the handler**, not by a global middleware, and the compressed bytes
are what the cache holds: `Content-Encoding: gzip` with `Vary: Accept-Encoding` when the request
accepted it, the same JSON otherwise. **Geometry is never simplified on the request path** —
`ST_SimplifyPreserveTopology` measured five to eight times the cost of the query itself; if a
future geography needs it, the simplified geometry is materialised by the nightly job, once per
vintage.
````

and add one bullet to the `Copy rules` list at `:343-354`:

```markdown
* On the map, `value: null` with `suppressed: false` → the no-data class with "No data for this
  area"; `suppressed: true` → the same class with the suppression wording above; `band_ambiguous:
  true` → the value, plus "this margin spans two legend bands" — never grey, because greying a
  measured figure is its own false statement.
```

- [ ] **Step 6: Run the contract-document tests to verify they pass**

```bash
poetry run pytest tests/api/test_contract_doc.py tests/census/test_boundaries.py -q -W error
```

Expected: PASS. `test_contract_doc_names_every_market_and_admin_route` now finds `/api/markets/{cbsa}/boundaries` in the document, and the new derived pin finds every cap and every geography label.

- [ ] **Step 7: Run the backend gate**

```bash
poetry run ruff check app tests scripts && poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e --cov-fail-under=100
```

Expected: PASS at 100 % lines and branches. Every branch in the handler has a case: `layer not in SHADING`, `bbox is None` / parsed / malformed / too large, cache hit and miss, `metro is None`, `state == "enabled"` and not, `len(rows) > MAX_FEATURES`, `if orphans`, the growth `used` arm, `blocked_reason is not None`, `len(raw) > MAX_BODY_BYTES`, and both arms of `_geojson`'s `Accept-Encoding` test. `_parse_bbox`'s four refusal arms are covered by the parametrised case plus one more for the `e <= w` arm — **add `("?layer=income&bbox=-97,30,-98,31", "BAD_BBOX")` to that list if the coverage report says the ordering arm is unreached.**

- [ ] **Step 8: Commit**

```bash
git add app/api/market.py docs/integrations/market-data-api.md \
  tests/census/test_boundaries.py tests/api/test_contract_doc.py
git commit -m "feat(api): GET /api/markets/{cbsa}/boundaries — the shaded layer, member-gated

D-C37: one route on the existing router, behind the existing REQUIRE_MARKET_READ object,
inside the existing market:gate:v cache key — which is the only way §10's CDN row and
§11's one-minute licence ceiling are both true of something that carries values. Bounds
where there were none anywhere in app/ (a whole-Texas box was 6,884 tracts and 9.2 MB),
gzip in the handler rather than a global middleware, and no simplification on the request
path. A polygon with no value is returned and drawn, never omitted. /api/layers gains a
`shading` member — new, never a change to geo_level, which describes the panel — and the
contract document gains the route, both caps and every geography label, pinned by a test
that reads them off the code.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```


---

## Task 10: the `market` adapter — the app draws what the API answered, or nothing at all

The seam A16 and A17 established: an app-only prop the reference never receives, and a ternary in the design's own script that branches on ADAPTER PRESENCE, not on data. With the adapter present the map draws the polygons the API answered **or none at all, whatever it answered** (A-SL23 (2)); with no adapter — the reference, and the Claude Design preview — Task 4's fixture path is untouched. Five more amendments, one new adapter module, one prop, one derived oracle module and one harness route.

**Re-basing states: NONE — and that is this task's acceptance criterion.** The harness answers the app's adapter with the design's own polygons, derived from `areaSet`, so both targets draw the same thirteen maps they drew at the end of Task 4. **The thirteen frozen hashes must not move either.**

**Counts after this task — DELTAS, per A-NS5.** Off the Preconditions script's derived values: literals `+ 19`, entries `+ 19`, ledger rows `+ 19`, families `+ 1` (counting from before Task 4; this task's own step adds 5 to Task 4's 14). `toHaveLength(entries + 19)`; `CLAUDE.md` reads `<word(families + 1)> families, <entries + 19> entries` and `A1's 24 derived edits plus <literals + 19> literals`. For orientation only: on `main` at `ec79594` that is 200 / 224 / 201; after `feat/card-geography`, 215 / 239 / 216.

**Files:**
- Create: `frontend/src/market/boundaries.ts`, `frontend/src/market/boundaries.test.ts`
- Create: `frontend/tests/design-boundaries.mjs`
- Modify: `frontend/src/app.setup.js` (one prop, in `listings`/`adminListings`' shape)
- Modify: `frontend/tests/design-amendments.ts` (A24.13–A24.17), `frontend/tests/design-amendments.test.ts`, `LOCAL_AMENDMENTS.md`, `CLAUDE.md`
- Modify: `frontend/tests/harness.ts` (`prepare()` gains two routes; two exported url helpers beside `collectionStubUrls`), `frontend/tests/harness.test.ts`
- Modify: `frontend/src/logic.test.ts`
- Modify: `tests/census/test_boundaries.py` (the label drift pin)
- **Regenerated:** the design file, `logic.js`, `App.vue`, `pseudo.css`

**Interfaces:**
- Consumes: `areaSet`/`areaVals`/`md.areas` (Task 4); `GET /api/markets/{cbsa}/boundaries` and `GET /api/markets` (Task 9).
- Produces:
  ```ts
  // frontend/src/market/boundaries.ts
  export const FILL_LAYERS: readonly ['income', 'growth', 'econ'];
  export interface BoundaryProperties { geo_id: string; name: string; value: number | null; moe: number | null; suppressed: boolean; suppress_reason: string | null; band_ambiguous: boolean }
  export interface BoundaryFeature { type: 'Feature'; id: string; properties: BoundaryProperties; geometry: unknown }
  export interface BoundaryCollection { type: 'FeatureCollection'; state: string; features: BoundaryFeature[] }
  /** What `logic.js` sees as `this.props.market`. */
  export interface MarketAdapter { boundaries(marketName: string): Promise<Record<string, BoundaryCollection>> }
  export function makeMarketAdapter(fetchFn?: typeof fetch): MarketAdapter
  ```
  ```js
  // frontend/tests/design-boundaries.mjs
  export function designAreaSet(layer)        // the design's own raw FeatureCollection
  export function designBoundariesBody(layer) // that collection in the endpoint's own shape
  export function designMarketsBody()         // `/api/markets`, from the design's own MARKETS
  ```
  ```ts
  // frontend/tests/harness.ts
  export function boundariesStubUrl(env?: NodeJS.ProcessEnv): string | null   // null on a remote target
  export function marketsStubUrl(env?: NodeJS.ProcessEnv): string | null
  ```
  - Inside the design: `state.mdAreas`, `Component.prototype.loadAreas(marketName)`, and the ternary in `md.areas`.

- [ ] **Step 1: Write the failing test for the adapter**

Create `frontend/src/market/boundaries.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { FILL_LAYERS, makeMarketAdapter } from './boundaries';

const MARKETS = [{ cbsa_geoid: '12420', name: 'Austin, TX', center: [30.31, -97.75], zoom: 10 }];
const collection = (layer: string) => ({
  type: 'FeatureCollection', layer, state: 'enabled',
  features: [{ type: 'Feature', id: '78704', properties: { geo_id: '78704', name: 'ZCTA5 78704', value: 92150, moe: 6420, suppressed: false, suppress_reason: null, band_ambiguous: false }, geometry: { type: 'Polygon', coordinates: [] } }]
});

function fakeFetch(handler: (url: string) => { ok?: boolean; status?: number; body?: unknown }) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const r = handler(url);
    return { ok: r.ok ?? true, status: r.status ?? 200, json: async () => r.body } as unknown as Response;
  });
}

describe('the market adapter (spec §8.3)', () => {
  it('names the three fill layers and nothing else', () => {
    expect([...FILL_LAYERS]).toEqual(['income', 'growth', 'econ']);
  });

  it('resolves the metro by NAME through /api/markets, then reads one collection per fill layer', async () => {
    const seen: string[] = [];
    const f = fakeFetch((url) => { seen.push(url); return { body: url.includes('/boundaries') ? collection(new URL(url, 'http://x').searchParams.get('layer')!) : MARKETS }; });
    const out = await makeMarketAdapter(f as unknown as typeof fetch).boundaries('Austin, TX');
    expect(seen[0]).toContain('/api/markets');
    expect(seen.filter((u) => u.includes('/boundaries'))).toHaveLength(3);
    for (const layer of FILL_LAYERS) expect(seen.some((u) => u.includes(`/api/markets/12420/boundaries?layer=${layer}`))).toBe(true);
    expect(Object.keys(out).sort()).toEqual(['econ', 'growth', 'income']);
    expect(out.income.features[0].properties.value).toBe(92150);
  });

  it('reads /api/markets ONCE, however many times boundaries is asked for', async () => {
    const f = fakeFetch((url) => ({ body: url.includes('/boundaries') ? collection('income') : MARKETS }));
    const adapter = makeMarketAdapter(f as unknown as typeof fetch);
    await adapter.boundaries('Austin, TX');
    await adapter.boundaries('Austin, TX');
    expect((f.mock.calls as unknown[][]).filter(([u]) => String(u).endsWith('/api/markets'))).toHaveLength(1);
  });

  it('rejects when the metro is not in the catalogue, rather than guessing a geoid', async () => {
    const f = fakeFetch(() => ({ body: MARKETS }));
    await expect(makeMarketAdapter(f as unknown as typeof fetch).boundaries('Nowhere, ZZ')).rejects.toThrow(/Nowhere, ZZ/);
  });

  it('rejects on a refused catalogue, a refused layer and an unparseable body — every path has an arm', async () => {
    await expect(makeMarketAdapter(fakeFetch(() => ({ ok: false, status: 401 })) as unknown as typeof fetch).boundaries('Austin, TX')).rejects.toThrow();
    const refusedLayer = fakeFetch((url) => (url.includes('/boundaries') ? { ok: false, status: 422 } : { body: MARKETS }));
    await expect(makeMarketAdapter(refusedLayer as unknown as typeof fetch).boundaries('Austin, TX')).rejects.toThrow();
    const rubbish = fakeFetch((url) => ({ body: url.includes('/boundaries') ? { type: 'FeatureCollection' } : MARKETS }));
    await expect(makeMarketAdapter(rubbish as unknown as typeof fetch).boundaries('Austin, TX')).rejects.toThrow(/features/);
  });

  it('sends the session cookie and bounds every request with a deadline', async () => {
    const f = fakeFetch((url) => ({ body: url.includes('/boundaries') ? collection('income') : MARKETS }));
    await makeMarketAdapter(f as unknown as typeof fetch).boundaries('Austin, TX');
    for (const [, init] of f.mock.calls as unknown as [string, RequestInit][]) {
      expect(init.credentials).toBe('same-origin');
      expect(init.signal).toBeInstanceOf(AbortSignal);
    }
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/market/boundaries.test.ts
```

Expected: FAIL — `Failed to resolve import "./boundaries"`.

- [ ] **Step 3: Write the adapter**

Create `frontend/src/market/boundaries.ts`:

```ts
/**
 * `GET /api/markets/{cbsa}/boundaries` → the design's `market` adapter prop (spec §8.3).
 *
 * The seam A16 and A17 established: an app-only prop the reference never receives, declared in
 * `app.setup.js` with a `default` that builds the real client. The design's own script branches
 * on adapter PRESENCE, not on data — with this present the map draws what the API answered or
 * NOTHING, whatever it answered (A-SL23 (2)); with no adapter the design's fixture path runs
 * unchanged, which is what keeps the reference and the Claude Design preview on their pixels.
 *
 * The metro is resolved by NAME through `/api/markets` — the first thing in the product to call
 * that route, which has existed and been guarded since Phase B — because `logic.js` speaks in
 * market names ("Austin, TX") and knows no CBSA geoid, and teaching it one would be a change to
 * the design for the adapter's convenience. The catalogue is read once per page.
 */
const LIST_URL = '/api/markets';
const TIMEOUT_MS = 8000;

export const FILL_LAYERS = ['income', 'growth', 'econ'] as const;

export interface BoundaryProperties {
  geo_id: string; name: string;
  value: number | null; moe: number | null;
  suppressed: boolean; suppress_reason: string | null; band_ambiguous: boolean;
}
export interface BoundaryFeature { type: 'Feature'; id: string; properties: BoundaryProperties; geometry: unknown }
export interface BoundaryCollection { type: 'FeatureCollection'; state: string; features: BoundaryFeature[] }
interface MetroRow { cbsa_geoid: string; name: string }

/** What `logic.js` sees as `this.props.market`. */
export interface MarketAdapter {
  boundaries(marketName: string): Promise<Record<string, BoundaryCollection>>;
}

async function read(fetchFn: typeof fetch, url: string): Promise<unknown> {
  const res = await fetchFn(url, {
    credentials: 'same-origin',
    headers: { Accept: 'application/geo+json, application/json' },
    signal: AbortSignal.timeout(TIMEOUT_MS)
  });
  if (!res.ok) throw new Error(`${url} answered ${res.status}`);
  return res.json();
}

export function makeMarketAdapter(fetchFn: typeof fetch = globalThis.fetch.bind(globalThis)): MarketAdapter {
  let metros: Promise<MetroRow[]> | null = null;
  const catalogue = () => (metros ??= read(fetchFn, LIST_URL) as Promise<MetroRow[]>);
  return {
    async boundaries(marketName: string) {
      const rows = await catalogue();
      const metro = rows.find((m) => m.name === marketName);
      if (!metro) throw new Error(`no CBSA for market ${marketName}`);
      const collections = await Promise.all(
        FILL_LAYERS.map((layer) => read(fetchFn, `/api/markets/${encodeURIComponent(metro.cbsa_geoid)}/boundaries?layer=${layer}`))
      );
      const out: Record<string, BoundaryCollection> = {};
      FILL_LAYERS.forEach((layer, i) => {
        const body = collections[i] as BoundaryCollection;
        if (!Array.isArray(body?.features)) throw new Error(`${layer}: the answer carries no features array`);
        out[layer] = body;
      });
      return out;
    }
  };
}
```

Declare it in `frontend/src/app.setup.js`, after the `adminListings` prop at `:89`:

```js
  // A24: the real /api/markets client, as the prototype's `market` adapter — the seam the
  // design's own script branches on. With it present the Browse map draws the polygons the API
  // answered or NONE at all, whatever it answered; with no adapter — the reference server and the
  // Claude Design preview — the design's own boundary fixture is drawn instead, which is what
  // keeps both targets on the same pixels. Nothing in the template reads `market`; only logic.js
  // does. Built by the factory in `src/market/boundaries.ts`, not an object literal here, for the
  // reason `auth` records: this file is copied by the generator and a literal would drift.
  market: { type: Object, default: () => makeMarketAdapter() }
```

with `import { makeMarketAdapter } from './market/boundaries';` beside the other three factory imports at the top.

- [ ] **Step 4: Run the adapter tests to verify they pass**

```bash
cd frontend && npx vitest run src/market/boundaries.test.ts && npm run typecheck
```

Expected: PASS.

- [ ] **Step 5: Write the failing test for the five amendments**

Append the five ids to `AMENDMENT_IDS`, change `toHaveLength(…)` from Task 4's value to that value `+ 5` (A-NS5 — the plan wrote `196` → `201`, both stale), and add:

```ts
    'A24.13', 'A24.14', 'A24.15', 'A24.16', 'A24.17',
```

```ts
  it('A24.13–A24.17 wire the map to the API on adapter presence, never on data', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    // A16.1's exact shape (A-SL23 (2)): with the adapter present the map draws what the API
    // answered or NOTHING, and never the design's fixture, whatever the API answered.
    expect(amended).toContain('areas: this.areaVals(this.props.market ? ((s.mdAreas || {})[valueLayer] || { type: "FeatureCollection", features: [] }) : this.areaSet(valueLayer), valueLayer),');
    expect(amended).toContain('mdAreas: null,');
    // One loader, with the rejection arm every adapter path in this design keeps forgetting
    // (A16.17's own lesson): a refused load empties the map, it does not restore the fixture.
    expect(amended).toContain('loadAreas(market) {');
    expect(amended).toContain('() => this.setState({ mdAreas: {} })');
    // Two call sites and exactly two: the bootstrap, and a change of metro.
    expect(amended.split('this.loadAreas(')).toHaveLength(3);   // exactly two call sites
    expect(amended.split('loadAreas(market) {')).toHaveLength(2); // and exactly one definition
    // NO new prototype prop: the reference reaches the fixture path by having no adapter at all,
    // exactly as it does for `listings` and `adminListings`. `market` is an app-only prop, so it
    // must NOT appear in the design's declared `data-props` (which `app-generated.test.ts`
    // requires app.setup.js to mirror).
    const props = /data-props="([^"]*)"/.exec(amended)![1].replace(/&quot;/g, '"').replace(/&amp;/g, '&');
    expect(Object.keys(JSON.parse(props))).not.toContain('market');
  });
```

- [ ] **Step 6: Grep the five `find` strings, then write the amendments**

```bash
python3 - <<'PY'
import pathlib
A = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html").read_text(encoding="utf-8")
for k, v in {
  "A24.13": '    adminTab: "users", sellerView: "dash",\n',
  "A24.14": '  componentDidMount() {\n',
  "A24.15": '      areas: this.areaVals(this.areaSet(valueLayer), valueLayer),\n',
  "A24.16": '    if (this.props.adminListings && me && me.state === "active" && (me.roles || []).some((r) => r === "staff" || r === "admin")) this.props.adminListings.list().then((rows) => this.setState({ adminListingRows: rows }), () => this.setState({ adminListingRows: [] }));\n',
  "A24.17": '  setMarket = (e) => {\n    const v = e && e.target ? e.target.value : e;\n',
}.items():
    print(f"{k} count={A.count(v)}")
PY
```

Expected: every line `count=1`. (A24.13 shares A24.1's anchor, which A24.1 preserved in its own `replace` — the count is measured at the point of application, in list order, and A24.13 runs after A24.1.)

```ts
const A24_13: Amendment = {
  id: 'A24.13', ...NS,
  find: '    adminTab: "users", sellerView: "dash",\n',
  replace: '    mdAreas: null,\n    adminTab: "users", sellerView: "dash",\n',
  count: 1
};

const A24_14: Amendment = {
  id: 'A24.14', ...NS,
  find: '  componentDidMount() {\n',
  replace: '  // The ONE loader (A16.17\'s lesson: every adapter path in this design shares one, and the\n'
    + '  // rejection arm is the thing callers keep forgetting). A refused or empty load EMPTIES the\n'
    + '  // map — it never restores the design\'s fixture, because a member must not be shown\n'
    + '  // boundaries that are not the ones the API holds (A-SL23 (2)).\n'
    + '  loadAreas(market) {\n'
    + '    if (!this.props.market) return;\n'
    + '    this.props.market.boundaries(market || "Austin, TX").then(\n'
    + '      (areas) => this.setState({ mdAreas: areas }),\n'
    + '      () => this.setState({ mdAreas: {} })\n'
    + '    );\n'
    + '  }\n'
    + '\n'
    + '  componentDidMount() {\n',
  count: 1
};

const A24_15: Amendment = {
  id: 'A24.15', ...NS,
  find: '      areas: this.areaVals(this.areaSet(valueLayer), valueLayer),\n',
  replace: '      areas: this.areaVals(this.props.market ? ((s.mdAreas || {})[valueLayer] || { type: "FeatureCollection", features: [] }) : this.areaSet(valueLayer), valueLayer),\n',
  count: 1
};

const A24_16: Amendment = {
  id: 'A24.16', ...NS,
  find: '    if (this.props.adminListings && me && me.state === "active" && (me.roles || []).some((r) => r === "staff" || r === "admin")) this.props.adminListings.list().then((rows) => this.setState({ adminListingRows: rows }), () => this.setState({ adminListingRows: [] }));\n',
  replace: '    if (this.props.adminListings && me && me.state === "active" && (me.roles || []).some((r) => r === "staff" || r === "admin")) this.props.adminListings.list().then((rows) => this.setState({ adminListingRows: rows }), () => this.setState({ adminListingRows: [] }));\n'
    + '    this.loadAreas(this.state.market);\n',
  count: 1
};

const A24_17: Amendment = {
  id: 'A24.17', ...NS,
  find: '  setMarket = (e) => {\n    const v = e && e.target ? e.target.value : e;\n',
  replace: '  setMarket = (e) => {\n    const v = e && e.target ? e.target.value : e;\n    this.loadAreas(v);\n',
  count: 1
};
```

and extend `amendments()`' tail:

```ts
    A24_9, A24_10, A24_11, A24_12,
    // A24.13-A24.17 — the adapter path. A24.13 reads A24.1's own output and A24.15 reads
    // A24.4's, so they run after the family's first pass; the reference passes no `market`
    // adapter, so every one of them is inert there and both targets keep the same pixels.
    A24_13, A24_14, A24_15, A24_16, A24_17];
```

- [ ] **Step 7: Regenerate, re-port and run**

```bash
cd frontend && npm run gen:design
```
then the re-port snippet from Task 4 Step 6, then:
```bash
cd frontend && npm run gen:app && npx vitest run tests/app-generated.test.ts tests/design-amendments.test.ts
```

Expected: `177 amendments applied` / `4 amendments applied` / `201 amendments in total`, and both test files green once the five ledger rows are written (Step 10).

- [ ] **Step 8: Derive the oracle's answer from `areaSet`, and stub it**

Create `frontend/tests/design-boundaries.mjs`:

```js
// The design-fixture stub for the boundary endpoint, in the D6 stub's own shape and for the same
// reason (A-SL2, as re-ruled by A-SL23 (2)).
//
// Thirteen approved states mount a map, and with the `market` adapter present the app draws what
// the API answered and NOTHING else — so the oracle has to ANSWER, through the success path, with
// the design's own polygons. It is DERIVED from the design's own `areaSet`, exactly as
// `design-seller-listings.mjs` is derived from `state.sellerListings` and `design-listings.mjs`
// from `P`, so the reference and the app cannot draw different geometry: ONE implementation
// assigns the design's figures to the design's polygons, and this reads it out of the exported
// class rather than repeating it.
import { Component, MARKETS } from '../src/logic.js';

/** The design's own raw FeatureCollection for one fill layer. */
export function designAreaSet(layer) {
  return new Component({}).areaSet(layer);
}

/** That collection in the endpoint's own shape. `state`, the two vintages and the attribution are
 *  the values the real endpoint sends for a cleared layer; the FEATURES are the design's. */
export function designBoundariesBody(layer) {
  const level = { income: '860', growth: '160', econ: '050' }[layer];
  const label = { income: 'ZIP Code Tabulation Area', growth: 'Place (city/town)', econ: 'County' }[layer];
  const set = designAreaSet(layer);
  return JSON.stringify({
    type: 'FeatureCollection', cbsa_geoid: '12420', layer,
    metric_key: { income: 'median_hh_income', growth: 'population_growth_pct', econ: 'revenue_per_establishment' }[layer],
    summary_level: level, geo_label: label,
    unit: layer === 'growth' ? 'pct' : 'usd', state: 'enabled',
    boundary_vintage: '2023', value_vintage: layer === 'econ' ? '2022' : '2019–2023',
    source_dataset: layer === 'econ' ? 'cbp' : 'acs5',
    attribution: ['Boundaries: U.S. Census Bureau, TIGER/Line Cartographic Boundary Files 2023'],
    values_without_geometry: 0,
    features: set.features
  });
}

/** `/api/markets`, from the design's OWN market catalogue: the adapter resolves a metro by name
 *  before it asks for a boundary, and the design's default is "Austin, TX". */
export function designMarketsBody() {
  return JSON.stringify(Object.keys(MARKETS).map((name, i) => ({
    cbsa_geoid: ['12420', '40900', '36740', '12060'][i] ?? String(90000 + i),
    name, center: MARKETS[name].center, zoom: MARKETS[name].zoom
  })));
}
```

In `frontend/tests/harness.ts`, add two url helpers beside `collectionStubUrls` and two routes at the end of `prepare()`:

```ts
/** `null` for a REMOTE target (`PW_APP_URL`): there the real, seeded API answers, and stubbing it
 *  would hide the very thing the QA parity run exists to check — the same rule `listingsStubUrl`
 *  and `collectionStubUrls` already follow, and pinned in harness.test.ts for the same reason. */
export function marketsStubUrl(env: NodeJS.ProcessEnv = process.env): string | null {
  return env.PW_APP_URL ? null : new URL('/api/markets', appOrigin(env)).href;
}
export function boundariesStubUrl(env: NodeJS.ProcessEnv = process.env): string | null {
  return env.PW_APP_URL ? null : new URL('/api/markets/12420/boundaries', appOrigin(env)).href;
}
```

```ts
  // A24: the boundary layer. Thirteen approved states mount a map and the app draws what the API
  // answered and nothing else, so the oracle answers with the DESIGN's own polygons — derived
  // from `areaSet` by design-boundaries.mjs, never hand-copied, so the two targets cannot diverge.
  const markets = marketsStubUrl();
  if (markets !== null) {
    await page.route((url) => url.href === markets, (route) => route.fulfill({ status: 200, contentType: 'application/json', body: designMarketsBody() }));
    await page.route(
      (url) => url.pathname.startsWith('/api/markets/') && url.pathname.endsWith('/boundaries'),
      (route) => route.fulfill({
        status: 200, contentType: 'application/geo+json',
        body: designBoundariesBody(new URL(route.request().url()).searchParams.get('layer') ?? 'income')
      })
    );
  }
```

with `import { designBoundariesBody, designMarketsBody } from './design-boundaries.mjs';` beside the other design-fixture imports. Add the remote-disarm cases to `harness.test.ts` in the shape its `listingsStubUrl`/`collectionStubUrls` cases already use:

```ts
  it('the boundary stubs are disarmed against a remote target', () => {
    expect(marketsStubUrl({ PW_APP_URL: 'https://qa.foundation.vin' } as NodeJS.ProcessEnv)).toBeNull();
    expect(boundariesStubUrl({ PW_APP_URL: 'https://qa.foundation.vin' } as NodeJS.ProcessEnv)).toBeNull();
    expect(marketsStubUrl({} as NodeJS.ProcessEnv)).toContain('/api/markets');
  });
```

- [ ] **Step 9: Pin the design's geography labels to the endpoint's**

**A call this plan makes, recorded here.** Spec §8.4 says the legend's geography line comes from `/api/layers`'s new `shading.label` when the adapter is present. It does not: the string is identical on both sides, and a runtime read would add a third fetch, a loading state on a surface whose pixels are frozen, and a second source of truth for one word. §8.4's own scope note already keeps `sourceLine`/`updatedLine` on `LAYER_META` rather than the API's strings, because that is A-C1 (11)'s separate John-ruled task; the geography line is the same class of copy. `/api/layers` still gains `shading` (D-NS15 — the contract document and the admin surface need it regardless), and the two are pinned instead. Append to `tests/census/test_boundaries.py`:

```python
def test_the_designs_geography_labels_equal_the_apis_shading_labels() -> None:
    """The legend's geography line is the design's own AREA_LABEL rather than a runtime read of
    /api/layers — identical strings, one fetch fewer, no loading state on a frozen surface — so
    the two are pinned instead, both ways, in the shape
    `tests/api/test_seller_listings.py::test_the_design_ownership_options_equal_ownerships_tuple`
    established."""
    import re
    from pathlib import Path

    design = (Path(__file__).resolve().parents[2] / "docs" / "design-reference" / "design_handoff_practice_match_v3" / "Practice Match V3.dc.html").read_text(encoding="utf-8")
    m = re.search(r"const AREA_LABEL = \{([^}]*)\};", design)
    assert m, "the design no longer declares AREA_LABEL"
    labels = dict(re.findall(r'(\w+):\s*"([^"]*)"', m.group(1)))
    assert labels == {k: v["label"] for k, v in market.SHADING.items()}
    lv = re.search(r"const AREA_LEVEL = \{([^}]*)\};", design)
    assert lv and dict(re.findall(r'(\w+):\s*"([^"]*)"', lv.group(1))) == {k: v["summary_level"] for k, v in market.SHADING.items()}
```

- [ ] **Step 10: Write the ledger rows, the CLAUDE.md counts, and the adapter-path characterisation**

Five rows in `LOCAL_AMENDMENTS.md` (A24.13 … A24.17, in apply order, ruling verbatim, `V3:<line>` recomputed after `gen:design`), and CLAUDE.md's two derived sentences to Task 4's values `+ 5` entries and `+ 5` literals, in both places each (A-NS5 — the plan wrote `Twenty-four families, 201 entries` / `plus 177 literals`, both stale). Append to `frontend/src/logic.test.ts`:

```ts
describe('A24 — the market adapter', () => {
  const adapter = (areas: Record<string, unknown>) => ({ boundaries: () => Promise.resolve(areas) });

  it('with an adapter present the map draws the API\'s polygons and NEVER the design\'s fixture', async () => {
    const api = { income: { type: 'FeatureCollection', features: [{ type: 'Feature', properties: { geo_id: 'x', name: 'X', value: 60000, moe: null, suppressed: false, suppress_reason: null, band_ambiguous: false }, geometry: null }] } };
    const c: any = new Component({ market: adapter(api) });
    c.componentDidMount();
    await Promise.resolve();
    expect(c.state.mdAreas).toBe(api);
    const drawn = c.marketVals(P).areas;
    expect(drawn.features.map((f: any) => f.properties.geo_id)).toEqual(['x']);
  });

  it('an EMPTY answer empties the map — it does not fall back to the fixture', async () => {
    const c: any = new Component({ market: adapter({}) });
    c.componentDidMount();
    await Promise.resolve();
    expect(c.marketVals(P).areas.features).toEqual([]);
  });

  it('a REFUSED load empties the map too, and the rejection arm exists', async () => {
    const c: any = new Component({ market: { boundaries: () => Promise.reject(new Error('401')) } });
    c.componentDidMount();
    await Promise.resolve();
    await Promise.resolve();
    expect(c.state.mdAreas).toEqual({});
    expect(c.marketVals(P).areas.features).toEqual([]);
  });

  it('with NO adapter the design\'s own fixture path runs, untouched', () => {
    const c: any = new Component({});
    c.componentDidMount();
    expect(c.state.mdAreas).toBeNull();
    expect(c.marketVals(P).areas.features.length).toBeGreaterThan(0);
  });

  it('changing the metro reloads the polygons for the metro chosen', async () => {
    const asked: string[] = [];
    const c: any = new Component({ market: { boundaries: (n: string) => { asked.push(n); return Promise.resolve({}); } } });
    c.componentDidMount();
    c.setMarket('Sacramento, CA');
    expect(asked).toEqual(['Austin, TX', 'Sacramento, CA']);
  });
});
```

- [ ] **Step 11: Run every gate, and read the manifest AND the baselines**

```bash
cd frontend && npm run typecheck && npx vitest run --coverage && npm run build
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-neighbourhood-shading"
export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_shading
export REDIS_URL=redis://localhost:6380/10 ENVIRONMENT=test API_SECRET_KEY=local_only_secret_change_me
export PW_APP_PORT=5583 PW_REF_PORT=5584 PW_CS_PORT=5585 PW_API_PORT=8157
lsof -nP -iTCP:5583,5584,5585,8157 -sTCP:LISTEN || true
cd frontend && npm run test:visual:baselines && npm run test:e2e
npx vitest run tests/baseline-manifest.test.ts
cd .. && poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e --cov-fail-under=100
```

Expected: **ZERO re-bases and zero moved hashes.** The app now takes the adapter path and the reference still takes the fixture path, and the harness feeds the app the design's own polygons through `areaSet` — so every one of the thirteen map states must be pixel-identical to what it was at the end of Task 4. **A single moved baseline here means `design-boundaries.mjs` and `areaSet` have diverged (R8): stop and diff the two collections, do not re-base.**

- [ ] **Step 12: Commit**

```bash
git add frontend/src/market/boundaries.ts frontend/src/market/boundaries.test.ts frontend/src/app.setup.js \
  frontend/tests/design-boundaries.mjs frontend/tests/harness.ts frontend/tests/harness.test.ts \
  frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts \
  "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
  "docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md" \
  frontend/src/logic.js frontend/src/App.vue frontend/src/generated/pseudo.css frontend/src/logic.test.ts \
  tests/census/test_boundaries.py CLAUDE.md
git commit -m "feat(map): the market adapter — the Browse map reads the real boundary API

A16/A17's seam, a fourth time: an app-only \`market\` prop the reference never receives,
and a ternary keyed on adapter PRESENCE. With it the map draws the polygons the API
answered or none at all — a refused or empty load empties the map and never restores the
design's fixture. The oracle answers with the design's OWN polygons, derived from the
script's own areaSet rather than hand-copied, so the reference and the app cannot draw
different geometry: zero baselines re-based and zero frozen hashes moved.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```


---

## Task 11: the boundary flows against the real API, the four-part gate, and the release

Everything before this proved the design and the app agree on the design's own fixture. This proves the product works against the REAL, seeded API — value assertions, not pixels, in `listing-flows.spec.ts`'s shape, with no stub armed — and then runs CLAUDE.md's four-part verification gate and hands back.

**Re-basing states: NONE, and no new approved state is added** — `frontend/tests/screens.ts` stays at whatever `SCREENS.length` it has when this task starts (A-NS5 — the plan said 49; `main` is at 52 and `feat/card-geography` takes it to 53), so `tests/test_docs.py::test_claude_md_approved_screen_count_matches_screens_ts` needs no edit. **The thirteen frozen hashes must not move.**

**Files:**
- Create: `frontend/tests/boundary-flows.spec.ts`
- Modify: `frontend/tests/playwright.config.ts:80` (the `app` project's `testMatch`)
- Modify: `frontend/package.json`, `pyproject.toml` (the lockstep version bump)
- Modify: `DEPLOY.md` (the ZCTA load and the nightly job, in the "Seeding the demo hospitals" section's shape)
- Test: `frontend/tests/boundary-flows.spec.ts`, then every gate

**Interfaces:**
- Consumes: everything. Produces: nothing another task reads.

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/boundary-flows.spec.ts`. It runs in the `app` project against the local API web server (`tests/targets.ts:126`, which migrates, resets rate limits and seeds), with **no boundary stub armed** — the point is the real route.

```ts
import { test, expect } from '@playwright/test';
import { booted, prepare, signInAs, waitMap } from './harness';

// ---------------------------------------------------------------------------------------
// A24 / D-C34–D-C37, against the REAL API: value assertions, never pixels (the pixel gates are
// visual.spec.ts and dom.spec.ts, and both compare against the design's own fixture). This is
// the only suite that exercises `GET /api/markets/{cbsa}/boundaries` end to end, so it is where
// the licence gate, the geography per layer and the margin of error are proved on real rows.
//
// It needs geo_area geometry and geo_metric values for a metro, and neither is there on a fresh
// checkout: a TIGER download needs the network and an ACS load needs CENSUS_API_KEY, which is
// worker-only and John holds (CLAUDE.md). So the suite seeds both, offline, from the SAME
// committed real polygons the design draws (frontend/tests/design-boundary-fixture.ts), and then
// materialises through the very entry point the beat schedule calls. Skipping the suite without a
// key was the alternative and is refused: a gate that skips itself is never run.
// ---------------------------------------------------------------------------------------
test.beforeAll(async () => {
  const { execFileSync } = await import('node:child_process');
  execFileSync('poetry', ['run', 'python', 'scripts/seed_boundary_e2e.py'], { cwd: '../..', stdio: 'inherit' });
  execFileSync('poetry', ['run', 'python', '-c',
    'from app.tasks.census import materialize_geo_metrics; print(materialize_geo_metrics())'],
    { cwd: '../..', stdio: 'inherit' });
});

test.describe('the boundary layer, against the real API', () => {
  test('Browse draws more than one fill class, from real polygons', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    const body = await page.evaluate(async () => {
      const metros = await (await fetch('/api/markets', { credentials: 'same-origin' })).json();
      const r = await fetch(`/api/markets/${metros[0].cbsa_geoid}/boundaries?layer=income`, { credentials: 'same-origin' });
      return { status: r.status, cache: r.headers.get('x-cache'), body: await r.json() };
    });
    expect(body.status).toBe(200);
    expect(body.body.summary_level, 'income must draw at ZCTA (D-C35)').toBe('860');
    expect(body.body.geo_label).toBe('ZIP Code Tabulation Area');
    expect(body.body.features.length, 'the seeded metro has no boundary polygons').toBeGreaterThan(1);
    expect(body.body.attribution[0]).toContain('TIGER/Line Cartographic Boundary Files');
    // "one to two orders of magnitude FEWER objects" than the 3,070-to-12,560 the mosaic drew.
    expect(body.body.features.length).toBeLessThan(1000);
    // More than one class, or the choropleth says nothing.
    const values = body.body.features.map((f: { properties: { value: number | null } }) => f.properties.value).filter((v: number | null) => v !== null);
    expect(new Set(values).size).toBeGreaterThan(1);
  });

  test('each layer answers at its OWN geography, and never at a finer one', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'design', '/browse');
    const seen = await page.evaluate(async () => {
      const metros = await (await fetch('/api/markets', { credentials: 'same-origin' })).json();
      const out: Record<string, string> = {};
      for (const layer of ['income', 'growth', 'econ']) {
        const r = await (await fetch(`/api/markets/${metros[0].cbsa_geoid}/boundaries?layer=${layer}`, { credentials: 'same-origin' })).json();
        out[layer] = `${r.summary_level}|${r.geo_label}`;
      }
      return out;
    });
    expect(seen).toEqual({
      income: '860|ZIP Code Tabulation Area',
      growth: '160|Place (city/town)',
      econ: '050|County'
    });
  });

  test('a polygon with a margin of error carries it, and one with no value is still returned', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'design', '/browse');
    const props = await page.evaluate(async () => {
      const metros = await (await fetch('/api/markets', { credentials: 'same-origin' })).json();
      const r = await (await fetch(`/api/markets/${metros[0].cbsa_geoid}/boundaries?layer=income`, { credentials: 'same-origin' })).json();
      return r.features.map((f: { properties: Record<string, unknown> }) => f.properties);
    });
    expect(props.some((p: { moe: number | null }) => typeof p.moe === 'number'), 'no ZCTA carried a margin of error').toBe(true);
    for (const p of props) {
      expect(Object.keys(p).sort()).toEqual(['band_ambiguous', 'geo_id', 'moe', 'name', 'suppress_reason', 'suppressed', 'value']);
      // Global Constraint (c): a null value is NOT the same state as a suppressed one.
      if (p.value === null && !p.suppressed) expect(p.suppress_reason).toBeNull();
    }
  });

  test('the legend names the geography of whichever layer is shading', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    await expect(page.getByText('ZIP Code Tabulation Area').first()).toBeVisible();
    await page.locator('button[aria-haspopup="listbox"]:not([aria-label])').first().click();
    await page.getByRole('option', { name: 'Population growth' }).click();
    await expect(page.getByText('Place (city/town)').first()).toBeVisible();
  });

  test('hovering a polygon shows the value and its honesty line', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    const map = page.locator('.leaflet-container').first();
    const box = (await map.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    const tip = page.locator('.rf-tip').first();
    await expect(tip).toBeVisible();
    await expect(tip).toContainText(/ZCTA5 \d{5}|No data/);
  });

  // The flip MUST go through the admin route, not through SQL: `gate.invalidate` is what bumps
  // `market:gate:v`, and without that bump a cached body stands until its own 24 h TTL. The
  // `design` persona holds buyer+seller+staff+admin (`scripts/seed_persona.py`), and
  // `licence.decide` additionally needs a session re-authenticated within ten minutes — this one
  // is seconds old. If the POST answers 403, STOP and read `app/auth/permissions.py`'s REAUTH
  // list rather than widening anything.
  test('withdrawing the licence empties the layer within a minute, and clearing it brings it back', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'design', '/browse');
    const geoid = await page.evaluate(async () => (await (await fetch('/api/markets', { credentials: 'same-origin' })).json())[0].cbsa_geoid);
    const read = async () => page.evaluate(async (g) => (await (await fetch(`/api/markets/${g}/boundaries?layer=income`, { credentials: 'same-origin' })).json()), geoid);
    expect((await read()).state).toBe('enabled');
    const decide = (status: string) => page.evaluate(async ([s, csrf]) => (await fetch('/api/admin/data-sources/acs5/license', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf as string },
      body: JSON.stringify({ license_status: s, notes: 'boundary-flows e2e' })
    })).status, [status, (document.cookie.match(/pm_csrf=([^;]+)/) ?? [])[1] ?? '']);
    await decide('unresolved');
    const off = await read();
    expect(off.state).toBe('disabled');
    expect(off.features, 'a withdrawn licence must empty the layer, not 403 it').toEqual([]);
    await decide('cleared');
    expect((await read()).state).toBe('enabled');
  });
});
```

Add the file to the `app` project's `testMatch` in `frontend/tests/playwright.config.ts:80`:

```ts
    { name: 'app', testMatch: /(^|\/)(visual|smoke|dom|signin-form|account-flows|listing-flows|boundary-flows)\.spec\.ts$/, use: { ...devices['Desktop Chrome'], viewport: VIEWPORT, baseURL } },
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npx playwright test --config=tests/playwright.config.ts --project=app boundary-flows.spec.ts
```

Expected: every case fails in `beforeAll` with `can't open file 'scripts/seed_boundary_e2e.py'`.

- [ ] **Step 3: Write the offline seed's tests, then the seed**

The suite drives the REAL endpoint, which needs `geo_area` polygons and `geo_metric` values, and a fresh checkout has neither: a TIGER download needs the network and an ACS load needs `CENSUS_API_KEY`, which is worker-only and John holds. Skipping the suite behind a flag was the alternative and is **refused** — a gate that skips itself is never run. So the GEOMETRY comes from the same committed, real TIGER polygons the design itself draws (Task 3's fixture); nothing here invents a shape. The FIGURES are e2e fixtures, stated literally in one place, spanning several legend bands because a single-class choropleth proves nothing; they reach no design file and no pixel.

Create `tests/scripts/test_seed_boundary_e2e.py`:

```python
"""scripts/seed_boundary_e2e.py — offline geometry and figures for the boundary e2e suite."""
import runpy
import sys
from pathlib import Path

import psycopg2
import pytest

from scripts import seed_boundary_e2e as SB

ROOT = Path(__file__).resolve().parent.parent.parent


def test_seed_writes_geometry_values_and_the_metro_envelope(conn: psycopg2.extensions.connection) -> None:
    written = SB.seed(conn)
    assert written["geo_area"] > 3 and written["acs_measure"] > 0 and written["cbp_industry"] > 0
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM geo_area WHERE summary_level = '310' AND geo_id = %s", (SB.CBSA,))
        assert cur.fetchone()[0] == 1, "the metro envelope the endpoint resolves a missing bbox from is absent"
        cur.execute("SELECT count(*) FROM geo_area WHERE summary_level = '860'")
        assert cur.fetchone()[0] > 0
        cur.execute("SELECT count(DISTINCT vintage) FROM acs_measure WHERE variable = 'B01003_001E'")
        assert cur.fetchone()[0] == 2, "growth needs both ACS vintages"
        cur.execute("SELECT count(*) FROM active_vintage")
        assert cur.fetchone()[0] == 4


def test_seed_is_idempotent(conn: psycopg2.extensions.connection) -> None:
    first = SB.seed(conn)
    assert SB.seed(conn) == first
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM geo_area WHERE summary_level = '860' AND vintage = %s", (SB.TIGER,))
        before = cur.fetchone()[0]
    SB.seed(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM geo_area WHERE summary_level = '860' AND vintage = %s", (SB.TIGER,))
        assert cur.fetchone()[0] == before, "a second run duplicated rows"


def test_the_seeded_incomes_span_more_than_one_legend_band() -> None:
    """A choropleth with one class says nothing, and boundary-flows.spec.ts asserts on this."""
    from app.census.bands import band_index

    assert len({band_index(v) for v, _ in SB.INCOMES}) > 1


def test_the_seeded_incomes_include_a_suppressed_and_an_ambiguous_case() -> None:
    """The two states the tip has different sentences for, present in every run."""
    from app.census.bands import band_ambiguous
    from app.census.materialize import _suppression

    assert any(_suppression(float(v), float(m))[0] for v, m in SB.INCOMES)
    assert any(band_ambiguous(float(v), float(m)) for v, m in SB.INCOMES)


def test_main_reports_what_it_wrote(scratch_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert SB.main([]) == 0
    assert "geo_area=" in capsys.readouterr().out


def test_main_refuses_without_a_database_url(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert SB.main([]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_a_fixture_without_the_literal_is_a_loud_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    empty = tmp_path / "design-boundary-fixture.ts"
    empty.write_text("export const SOMETHING_ELSE = 1;\n", encoding="utf-8")
    monkeypatch.setattr(SB, "FIXTURE", empty)
    with pytest.raises(RuntimeError, match="DESIGN_AREAS_LITERAL"):
        SB._fixture()


def test_the_main_guard_is_covered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["seed_boundary_e2e.py"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / "seed_boundary_e2e.py"), run_name="__main__")
    assert exc.value.code == 2
```

Create `scripts/seed_boundary_e2e.py`:

```python
"""Offline geometry and figures for `frontend/tests/boundary-flows.spec.ts`.

That suite drives the REAL boundary endpoint, which needs `geo_area` polygons and `geo_metric`
values — and on a fresh checkout there are neither: a TIGER download needs the network and an ACS
load needs `CENSUS_API_KEY`, which is worker-only and John holds (CLAUDE.md). Skipping the suite
without a key was the alternative and is refused: a gate that skips itself is never run.

The GEOMETRY is the same committed, real TIGER polygons the design itself draws
(`frontend/tests/design-boundary-fixture.ts`, generated by `scripts/export_design_boundaries.py`)
— nothing here invents a shape. The FIGURES below are e2e fixtures, stated literally in one place
and chosen to span several legend bands, to include one margin wide enough to fail the CV test and
one wide enough to cross a stop; they are not data, and they reach no design file and no pixel.

Idempotent: every write is an upsert on the table's own key, so the suite may run twice."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import psycopg2
import psycopg2.extensions

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "frontend" / "tests" / "design-boundary-fixture.ts"
CBSA = "12420"
ACS, ACS_PRIOR, CBP, TIGER = "2019–2023", "2014–2018", "2022", "2023"

# (estimate, moe) per ZCTA, cycled over however many polygons the fixture carries. Four of
# income's five bands are represented; (51000, 40000) fails the CV test at Z90/0.30 and is
# suppressed `high_moe`; (97000, 9000) crosses the 100,000 stop and is `band_ambiguous`.
INCOMES: tuple[tuple[int, int], ...] = (
    (42000, 2100), (58000, 3000), (68000, 3400), (81000, 4000), (92150, 6420),
    (97000, 9000), (118000, 5000), (134000, 6000), (162000, 7000), (51000, 40000),
)
POPULATIONS: tuple[int, int] = (1_100_000, 1_000_000)   # now, prior — growth needs both vintages
CBP_ROW: tuple[int, int] = (32_000, 40)                  # annual payroll (thousands), establishments


def _fixture() -> dict[str, dict[str, list[dict[str, object]]]]:
    m = re.search(r"export const DESIGN_AREAS_LITERAL = '(.*)';", FIXTURE.read_text(encoding="utf-8"))
    if m is None:
        raise RuntimeError(f"{FIXTURE} does not declare DESIGN_AREAS_LITERAL")
    return json.loads(m.group(1).replace("\\'", "'").replace("\\\\", "\\"))


_GEO_UPSERT = """
INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid) VALUES
  (%s, %s, %s, %s, %s,
   ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 4269)),
   ST_Transform(ST_SetSRID(ST_Point(%s, %s), 4326), 4269))
ON CONFLICT (geo_id, summary_level, vintage) DO UPDATE SET geom = EXCLUDED.geom, centroid = EXCLUDED.centroid
"""

# The envelope the endpoint resolves a missing bbox from: the union of the polygons themselves, so
# it cannot disagree with what it is supposed to contain.
_METRO_UPSERT = """
INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid)
SELECT %s, '310', %s, 'Austin-Round Rock-San Marcos, TX Metro Area', ST_Multi(ST_Union(geom)), ST_Centroid(ST_Union(geom))
  FROM geo_area WHERE summary_level = '860' AND vintage = %s
ON CONFLICT (geo_id, summary_level, vintage) DO UPDATE SET geom = EXCLUDED.geom, centroid = EXCLUDED.centroid
"""

_ACS_UPSERT = """
INSERT INTO acs_measure (geo_id, summary_level, vintage, variable, estimate, moe) VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (geo_id, summary_level, vintage, variable) DO UPDATE SET estimate = EXCLUDED.estimate, moe = EXCLUDED.moe
"""


def seed(conn: psycopg2.extensions.connection) -> dict[str, int]:
    fixture = _fixture()
    written = {"geo_area": 0, "acs_measure": 0, "cbp_industry": 0}
    with conn.cursor() as cur:
        for key, vintage in (("tiger_cb", TIGER), ("acs5", ACS), ("acs5_prior", ACS_PRIOR), ("cbp", CBP)):
            cur.execute(
                "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), 'seed_boundary_e2e') "
                "ON CONFLICT (dataset_key) DO UPDATE SET vintage = EXCLUDED.vintage",
                (key, vintage),
            )
        for level, collection in fixture.items():
            # ZCTA rows carry no state_fips (tiger.py declares none for '860'); place and county
            # rows do, and geo_metric.py filters on it.
            state = None if level == "860" else "48"
            for feature in collection["features"]:
                props = feature["properties"]
                cur.execute(_GEO_UPSERT, (props["geo_id"], level, TIGER, props["name"], state,
                                          json.dumps(feature["geometry"]), props["c"][1], props["c"][0]))
                written["geo_area"] += 1
        cur.execute(_METRO_UPSERT, (CBSA, TIGER, TIGER))
        written["geo_area"] += 1

        cur.execute("SELECT geo_id FROM geo_area WHERE summary_level = '860' AND vintage = %s ORDER BY geo_id", (TIGER,))
        for i, (geo_id,) in enumerate(cur.fetchall()):
            estimate, moe = INCOMES[i % len(INCOMES)]
            cur.execute(_ACS_UPSERT, (geo_id, "860", ACS, "B19013_001E", estimate, moe))
            cur.execute(_ACS_UPSERT, (geo_id, "860", ACS, "B19013_001M", moe, None))
            written["acs_measure"] += 2

        cur.execute("SELECT geo_id FROM geo_area WHERE summary_level = '160' AND vintage = %s ORDER BY geo_id", (TIGER,))
        for (geo_id,) in cur.fetchall():
            for vintage, population in ((ACS, POPULATIONS[0]), (ACS_PRIOR, POPULATIONS[1])):
                cur.execute(_ACS_UPSERT, (geo_id, "160", vintage, "B01003_001E", population, None))
                written["acs_measure"] += 1

        cur.execute("SELECT geo_id FROM geo_area WHERE summary_level = '050' AND vintage = %s ORDER BY geo_id", (TIGER,))
        for (geo_id,) in cur.fetchall():
            cur.execute(
                "INSERT INTO cbp_industry (geo_id, summary_level, vintage, naics_code, establishments, annual_payroll_k) "
                "VALUES (%s, '050', %s, '541940', %s, %s) "
                "ON CONFLICT (geo_id, summary_level, vintage, naics_code) DO UPDATE SET establishments = EXCLUDED.establishments, annual_payroll_k = EXCLUDED.annual_payroll_k",
                (geo_id, CBP, CBP_ROW[1], CBP_ROW[0]),
            )
            written["cbp_industry"] += 1
    return written


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="seed offline boundary geometry and figures for the e2e suite").parse_args(argv)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[seed_boundary_e2e] DATABASE_URL is not set", file=sys.stderr)
        return 2
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        written = seed(conn)
    finally:
        conn.close()
    print(", ".join(f"{table}={n}" for table, n in written.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Check two schema facts before running, rather than trusting this script's `ON CONFLICT` clauses** — both are named by their table's own key and neither is guessed here:

```bash
psql "$DATABASE_URL" -c "\d acs_measure"   | sed -n '/Indexes/,$p'
psql "$DATABASE_URL" -c "\d cbp_industry"  | sed -n '/Indexes/,$p'
```

Expected: `acs_measure` keyed on `(geo_id, summary_level, vintage, variable)` (the shape `app/census/acs.py`'s own `UPSERT` already names) and `cbp_industry` on `(geo_id, summary_level, vintage, naics_code)`. If either differs, use the key the table declares; if a table has no unique key at all, replace that upsert with a `DELETE … WHERE vintage = %s` before the insert, which keeps the idempotency `test_seed_is_idempotent` asserts.

- [ ] **Step 4: Run it again to verify it passes**

```bash
cd frontend && npx playwright test --config=tests/playwright.config.ts --project=app boundary-flows.spec.ts
```

Expected: `6 passed`. A seconds-long "green" is the API web server failing to start, not a pass — read the log for `N passed`.

- [ ] **Step 5: Bump the version, in lockstep**

`frontend/package.json` and `pyproject.toml` both go to **the next free patch in MERGE order** (one patch per release, `tests/test_versions.py`). A-NS5: the plan wrote `0.1.17` → `0.1.18` and both manifests now read **0.1.19**, so read them at hand-back rather than taking a number from here. `feat/card-geography` carries no release commit as of `8c7c3b6`, so it does not reserve 0.1.20 yet.

- [ ] **Step 6: Document the operator steps**

In `DEPLOY.md`, beside "Seeding the demo hospitals (QA)", add a section in its shape:

````markdown
### Loading ZCTA incomes for the boundary layer (QA, then production)

The shaded map reads `geo_metric`, which the nightly `geo-metric-nightly` job fills from
`acs_measure`, `cbp_industry` and `geo_area`. Two of the three inputs are already loaded; the ACS
figures at summary level `860` are not, and they are the one new ingest this feature needs
(D-NS4). Run inside the **worker** container, which is the only service holding `CENSUS_API_KEY`:

```bash
railway status                                  # must say Project: Practice Match
python scripts/census_load.py acs --dataset acs5 --levels 860
python scripts/census_load.py activate acs5 "$(psql "$DATABASE_URL" -tAc "SELECT vintage FROM dataset_registry WHERE dataset_key='acs5'")" --by "<operator>"
python -c "from app.tasks.census import materialize_geo_metrics; print(materialize_geo_metrics())"
python scripts/measure_band_ambiguity.py --vintage "$(psql "$DATABASE_URL" -tAc "SELECT vintage FROM active_vintage WHERE dataset_key='acs5'")"
```

Read the `ingest_run` row before going on: a national ZCTA query returns roughly 33,700 rows per
variable in one page and is the largest single ACS page this pipeline issues.

```bash
psql "$DATABASE_URL" -c "SELECT status, rows_written, request_count, started_at FROM ingest_run WHERE dataset_key='acs5' ORDER BY id DESC LIMIT 1"
```

**If the run is `aborted` or the client's size cap refuses the page, STOP** and take D-C34's ZCTA
ruling back to John with the tract alternative — the aggregation alternative is refused (D-NS4).
The last command prints the share of polygons whose margin of error spans a legend band; that
number is D-C34's own trigger for the tract toggle and belongs in the hand-back.
````

- [ ] **Step 7: Run the verification gate — all four parts**

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-neighbourhood-shading"
export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_shading
export REDIS_URL=redis://localhost:6380/10 ENVIRONMENT=test API_SECRET_KEY=local_only_secret_change_me
export PW_APP_PORT=5583 PW_REF_PORT=5584 PW_CS_PORT=5585 PW_API_PORT=8157
lsof -nP -iTCP:5583,5584,5585,8157 -sTCP:LISTEN || true
docker compose -f docker-compose.dev.yml up -d

# (1)
poetry run ruff check app tests scripts && poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e --cov-fail-under=100
cd frontend && npm run typecheck && npx vitest run --coverage && npm run build

# (2)
npm run test:visual:baselines && npm run test:e2e
npx vitest run tests/baseline-manifest.test.ts
```

Expected: all green, and `baseline-manifest.test.ts` reporting **zero moved hashes**. Parts (3) and (4) — the QA click-through and the production smoke — are the controller's at hand-back, with `scripts/deploy.sh QA`, the operator steps in Step 5, and then `scripts/deploy.sh production` + `scripts/verify-deploy.sh production`. The QA click-through covers: the three fill layers each drawing at their own geography; the legend's geography line changing with the layer; a hover tip carrying a margin of error; a grey polygon carrying "No data for this area" or the suppression wording; the snapshot strip's new footnote; and the licence flip (`acs5` → `unresolved`, the income layer empties inside 60 s, `cleared` again brings it back).

- [ ] **Step 8: Commit**

```bash
git add frontend/tests/boundary-flows.spec.ts frontend/tests/playwright.config.ts \
  scripts/seed_boundary_e2e.py tests/scripts/test_seed_boundary_e2e.py \
  frontend/package.json pyproject.toml DEPLOY.md
git commit -m "test(map): boundary flows against the real API, and the release

Six value assertions with no stub armed: each layer at its own geography, more than one
fill class from real polygons, a margin of error on a real ZCTA, the legend's geography
line following the layer, the hover tip, and the licence flip emptying the layer within
a minute and refilling it. Version 0.1.18 in lockstep; DEPLOY.md carries the one new
ingest (ACS at 860) with its ingest_run check and its stop condition.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Hand-back

A forwardable plain-language summary, screenshots of the live screens, and a one-line engineer's note with any risk (CLAUDE.md, "Close the loop"). What the summary must carry, because each is a thing John asked about or ruled on:

- The map now draws real Census boundaries. Income shades ZIP Code Tabulation Areas, population growth shades cities and towns, and average practice payroll shades counties — each at the level that figure is actually measured at, with the legend naming which.
- A ZIP code with no usable figure is drawn grey and says why: no data, an estimate too imprecise to show, or a figure the Census Bureau did not publish for that county. It is never left blank, because a hole in a shaded map reads as a boundary.
- Where a figure IS measured but its margin of error spans two legend bands, the figure is still shown, with a note. Greying a measured figure would be its own false statement.
- **The measurement D-C34 asked for**, from `scripts/measure_band_ambiguity.py` on QA: the share of polygons whose margin spans a band, per geography. That number is the trigger for the tract-level layer, and it should go to John with this release rather than after it.
- The picture is also faster, not slower: one to two orders of magnitude fewer objects than the grid it replaces.

---

## Self-review

Run with fresh eyes against the spec after writing, per the writing-plans skill. Findings and what was done about them.

### 1. Spec coverage

| Spec requirement | Task |
|---|---|
| §3 / D-NS1, D-NS2 — `geo_metric`, numbered `064` | 5 |
| §3 / D-NS3 — the licence trigger, including the UPDATE and NULL arms | 5 |
| §4 / D-NS4 — ACS at `860`, loaded not aggregated; `levels` filter | 6 (code), 11 (the QA run) |
| §4 / D-NS5, D-NS8 — `materialize_geo`, three metrics, six states | 8 |
| §4 / D-NS6 — `_suppression` imported, identity asserted; `metrics.py` unmodified | 8 |
| §4 / D-NS7 — per-triple delete-and-rewrite, transactional, idempotent, prior vintage survives | 8 |
| §4 / D-NS9 — `geo-metric-nightly` at 03:30 UTC | 8 |
| §5 / D-NS10 — one route, the module-constant guard, `site_mode == "app"` | 9 |
| §5 / D-NS11 — the SQL, the transform, no simplification on the request path | 9 |
| §5 / D-NS12 — the four bounds and their `_error` envelope | 9 |
| §5 / D-NS13 — the cache key with `gate.version`, plus the live `_cleared`/`_extra_cleared` re-filter | 9 |
| §5 / D-NS14 — gzip in the handler, compressed bytes cached, no global middleware | 9 |
| §5 / D-NS15 — `/api/layers`'s `shading`; the contract document | 9 |
| §6 / D-NS16 — the no-data class, always drawn, four reasons | 4 (the class and the tip), 9 (the payload) |
| §6 / D-NS17 — `_suppression` on income only; the two honesty lines; `bands.py` and its two-way pin | 7, 8, 4 |
| §6 / D-NS18 — the two suppression-parity assertions | 8 (identity), 9 (outcome) |
| §7 — two vintages named separately; both divergence directions; `values_without_geometry` | 9 |
| §8.1 — the `geoJson` primitive on the shared canvas renderer; the stub; `boundary.test.ts` | 2 |
| §8.2 — everything the mosaic leaves behind, enumerated and deleted | 4 |
| §8.3 — the `market` adapter and its boot wiring | 10 |
| §8.4 — the legend's geography line and its no-data row | 4 (see the call below) |
| §8.5 — the hover tip | 4 (see the call below) |
| §9.1–9.2 — the two-file amendment engine | 1 |
| §9.3 — the A24 members | 4, 10 |
| §9.4 — the fixture, generated and derived, never hand-copied | 3, 10 |
| §9.5 — the thirteen re-basing states and the frozen-hash invariant | stated per task |
| §10 — every listed test | 1–11 |
| §14 Q1 — grey with a legend row | 4 |
| §14 Q2 — the footnote, verbatim | 4 |
| §14 Q3 — extend the engine | 1 |

**Gaps found, and closed inline:**

- **The cache had no way to expire after a nightly rewrite.** D-NS13's key carries the two vintages and the gate version, none of which moves when the writer changes a VALUE at the same vintage — so a new figure would be invisible for up to `BOUNDARY_TTL`, 24 hours. Closed by `GEO_VERSION_KEY` (Task 8) and an `:m{n}` segment (Task 9), which is `materialize_listing`'s own `listing:{id}:market:version` idiom one table wider, and which also gives the `redis` parameter D-NS5's signature already declares something to do.
- **The cache key had no bbox segment.** `bbox` changes the response and D-NS13's key does not name it, so two viewports of one metro would collide. Closed by a `:b{bbox|metro}` segment (Task 9).
- **`values_without_geometry` was undefined for the bbox case.** Counting "values whose geography is not in this viewport" would be non-zero on every zoomed request and would mean nothing. Defined (Task 9) as values with no `geo_area` row at that level and vintage AT ALL — which is what §7's "a boundary vintage that has moved out from under the values" actually describes.
- **§10 lists `tests/api/test_boundaries.py`, `acs.load_acs` and `vintage.active_vintage`; none exists.** Corrected to `tests/census/test_boundaries.py`, `acs.load` and `vintage.active`, with the reason in the controller note.
- **§8.2 lists `cross-plan-deltas.test.ts:221` and `:306` as changing.** Measured: neither window mentions the mosaic. Only `:87` and `:96` change (Task 4).

**Not in scope and not covered, matching §12:** tract polygons and the geography toggle; vector tiles and the CDN path; any change to the three symbol layers; tract-level growth; the Esri-vs-CARTO decision; the Satellite tab; national coverage; `opportunity_score`. Plus the four §12 adds: `market_metric` and the docked panel are not edited; the legend's source and vintage lines stay `LAYER_META`'s; no global `GZipMiddleware`; `logic.js`'s trailing export and D-C14 are untouched (the fixture goes in the design's state literal precisely so this plan does not have to answer that). **One further gap left open deliberately and named here:** ACS jam values (`-666666666`, `-555555555`) are not filtered anywhere in this tree today and this plan does not add a filter — a ZCTA carrying one would shade as a large negative income. It is a pre-existing defect of the ACS loader, it is out of this change's ask, and it is written into the hand-back's risk line rather than fixed silently.

### 2. Placeholder scan

Searched for `TBD`, `TODO`, `implement later`, `appropriate error handling`, `add validation`, `handle edge cases`, `similar to Task`, `write tests for the above`. **None present.** Two places carry a `<<< paste the printed … here >>>` marker, and both are deliberate and are not placeholders: Task 4 Step 2 is a real, deterministic code block that PRINTS those two exact 23- and 35-line `find` strings from the pristine file's own bytes, with the expected line counts and the expected `count in pristine = 1` stated. Transcribing 58 lines of someone else's code into a plan is how a silent no-op gets written, which is the failure Global Constraint (b) exists to stop. Every other code step carries the literal code.

### 3. Type and name consistency

Checked every name a later task uses against the task that defines it.

- `Amendment.file` / `AmendmentFile` / `PRISTINE_JSX` / `AMENDED_JSX` / `amendmentsFor` — defined Task 1, used Tasks 4 and 10. ✓
- `geoJson(fc, styleFor, group, tooltipFor?, onClick?)`, `AreaFeature`, `AreaFeatureCollection`, `AreaStyle` — defined Task 2, called Task 4's `MarketMapView.vue` with exactly that arity and order. The stub records the call as `'geoJSON'` (Leaflet's own capitalisation) and the engine method is `geoJson` (the interface's camelCase); Tasks 2 and 4 both use the right one in the right place. ✓
- `DESIGN_AREAS_LITERAL` — produced Task 3, imported Task 4's `design-amendments.ts`. ✓
- `areaSet(layer)` returns features whose `properties` are `{geo_id, name, value, moe, suppressed, suppress_reason, band_ambiguous}` (Task 4). Task 10's `design-boundaries.mjs` emits those same features as the endpoint's `features`, and Task 9's `_boundary_feature` emits exactly those seven keys — **checked key by key, including the snake_case `suppress_reason`/`band_ambiguous`, which `areaVals` re-exposes camelCased as `suppressReason`/`ambiguous` for the design's own consumers while leaving the wire names alone.** ✓
- `AREA_LEVEL`/`AREA_LABEL` (Task 4) vs `market.SHADING` (Task 9) — same three levels, same three labels, pinned by the drift test in Task 10 Step 9. ✓
- `GEO_VERSION_KEY` — defined Task 8, imported Task 9. ✓
- `band_ambiguous(value, moe)` — defined Task 7, called Task 9. ✓
- `MarketAdapter.boundaries(marketName) → Record<string, BoundaryCollection>` — defined Task 10, called by A24.14's `loadAreas`, and A24.15 reads `(s.mdAreas || {})[valueLayer]`, which is that record keyed by layer. ✓
- Migration `064` is referenced as `064_geo_metric.sql` in Tasks 5, 8, 9 and the File Map. ✓
- Amendment ids are contiguous and unique: A24.1–A24.5, A24.6a/b, A24.7, A24.8a/b, A24.9–A24.12 (Task 4, fourteen) and A24.13–A24.17 (Task 10, five) — **nineteen entries, no id used twice**, which is what `expect(new Set(AMENDMENT_IDS).size).toBe(AMENDMENT_IDS.length)` checks.
- Counts are consistent across tasks and derived, not asserted: 158 → 172 (Task 4) → 177 (Task 10) literals; 182 → 196 → 201 entries; 159 → 173 → 178 ledger rows; families 23 → 24, which `tests/test_docs.py`'s `number_words` already spells ("Twenty-four") without an edit. ✓

**Four things found and fixed inline:**

1. **A naming collision that would have read as a bug.** An earlier draft had Task 4's `areaVals` emit `suppress_reason` and Task 9's payload emit `suppressReason`. The wire name is snake_case everywhere — it is the column's name, and `market_metric`'s panel serialiser already spells it that way — and the design's own render values are camelCase (`suppressReason`, `ambiguous`) because that is how the rest of `renderVals()` names things. Both spellings are now stated explicitly in Task 4's Interfaces block, so an implementer reading only that task gets both.
2. **An assertion that could not have passed.** Task 10's `expect(amended.split('this.loadAreas(')).toHaveLength(4)` counted "the definition plus two calls", but the definition is `loadAreas(market) {` with no `this.` — two occurrences, not three. Corrected to `toHaveLength(3)`, with a second assertion pinning the single definition.
3. **An assertion that would have failed for the wrong reason.** The same case asserted the design declares exactly eight prototype props; `data-props` also declares `layerPalette` and others, so the number is wrong and, worse, it would go stale on any unrelated prop change. Replaced with the thing actually being claimed: `market` is an app-only prop and must NOT appear in the design's `data-props` at all.
4. **A placeholder, in the only place one had crept in.** Task 11 originally described `scripts/seed_boundary_e2e.py` as being "in `seed_persona.py`'s own shape" rather than giving it — which is exactly the "similar to Task N" failure the no-placeholders rule names. Rewritten with the real script and its seven tests, and with its design changed while writing it: the geometry now comes from Task 3's committed real polygons rather than needing a network TIGER load at e2e time, which is what lets the suite run on a fresh checkout with no `CENSUS_API_KEY`. Its two `ON CONFLICT` clauses are checked against the tables' own keys before the first run rather than trusted.

### 4. Sequencing check

Task 1 needs nothing. Task 2 needs nothing. Task 3 needs a TIGER load (its own Step 1) and nothing from Tasks 1–2. Task 4 needs 1, 2 and 3. Task 5 needs nothing. Task 6 needs nothing. Task 7 needs 5. Task 8 needs 5, 6, 7's neighbours (none — `bands.py` is read by the endpoint, not the writer). Task 9 needs 5, 7, 8. Task 10 needs 4 and 9. Task 11 needs everything. **No task reads a name a later task defines.** Tasks 5 and 6 could run in parallel with 1–4 by a second implementer; nothing else can.

---

## Controller amendments from Tasks 1 and 2 (2026-09-11) — BINDING ON TASK 4 AND AFTER

Both tasks are merged and both reviews returned APPROVED. Three findings change what later tasks must do, and one of them changes what "zero pixels" means. They are recorded here rather than in a scratch file because every remaining task's brief has to carry them.

**A-NS1 — a jsx amendment reaches the REFERENCE, not the app, and that makes every real one a two-sided change.** For `Practice Match V3.dc.html` an amendment propagates into shipped code through `npm run gen:app` (`convert-dc.mjs` → `App.vue`, `pseudo.css`, `app.setup.js`). `MarketMapV3.jsx` has **no such generator**: the app's port of it is hand-written across `frontend/src/components/MarketMapView.vue`, `frontend/src/map/mosaic.js` and `frontend/src/map/engines/leaflet.ts`. The reference DOES render the jsx — the amended `.dc.html` carries `x-import component="MarketMapV3" from="./MarketMapV3.jsx"` and `reference-server.mjs` serves it. So from the first real A24 entry onward, **a jsx amendment moves the forty-nine reference baselines while leaving the app untouched, and the `app` project then compares the app against those regenerated baselines at `maxDiffPixels: 0`.** Consequence, and it is not optional: **an A24 jsx amendment and its hand port land in the SAME commit, or the visual gate fails.** Task 1 moved no pixel only because its jsx list was empty. Neither the spec nor the plan said this; it is the most valuable thing Task 1's measurement surfaced.

**A-NS2 — two of the engine's guards are still dc-only, and Task 4 extends them.** The byte-identity and find-count cases were made per-file; two were not. `no amendment introduces a doubled blank line (A-I8.1)` compares only the amended `.dc.html` to its pristine, so a jsx removal amendment can leave a doubled blank line unseen. And `every V3:<line> citation in LOCAL_AMENDMENTS.md lands on the line that amendment produced` resolves every citation against the `.dc.html`, so a jsx row citing `V3:<n>` fails with a misleading "stale citation" message while a jsx row with no citation is skipped silently — there is no `MMV3:<line>` convention yet, and Task 4 must introduce one. Also unconverted: `design-amendments.test.ts`'s A8.7 style-composition case still slices the UNFILTERED list against the dc pristine, which is safe only while every jsx entry sorts after A8.7.

**A-NS3 — nothing in CI exercises a non-empty jsx list.** All three of Task 1's new cases are satisfied by an empty partition, and v8 reports 100 % branches regardless because the non-nullish arm of `a.file ?? 'dc'` is never taken by a shipped entry. The path was proved twice by hand — the implementer's probe and the reviewer's independent one — and **both were reverted**, so no standing gate covers it. Task 4 is otherwise the first thing to exercise it in anger. Add the four-line synthetic-list case (`applyAmendments` over an in-test `[{…, file: 'jsx'}]`, in the shape of the existing `bogus` amendment case) so the risk this whole task existed to retire has a gate rather than a memory.

**A-NS4 — the map stub never invokes `options.style`, and Task 4 should know before it depends on it.** Real `L.GeoJSON.addData` calls the style function via `resetStyle` with `layer.feature` attached, BEFORE `onEachFeature`; the stub does not, so Task 2's tests assert the style function in isolation and never its wiring. Acceptable at this stub's established fidelity and adequate for Task 4's planned usage, which reads style per feature and binds tooltips through `onEachFeature`. Recorded so it is stated rather than discovered. Related: the `geoJson` handle deliberately carries **no** `openTooltip` (removed before merge — it could only ever have been a no-op, since tooltips bind on the children and not on the returned group). If a later task needs to open a named polygon's tooltip programmatically, that is a new capability and the blocker is the stub's missing `feature` back-references, not the primitive.
